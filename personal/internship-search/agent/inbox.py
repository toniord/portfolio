"""Reads application emails from Gmail and turns them into Applied status.

Milestone 7.5, revived 2026-10-08. A "thank you for applying" email sets Applied
status on the posting it is about, and when the agent does not hold that
posting it creates it, already applied. The owner is never asked which posting
an email meant; that was the first design and he overruled it the same day.

Rejections were added 2026-10-09, at his request.
A rejection sets Rejected on the application it answers, or creates the
posting already rejected when the agent never held the application. See the
section headed "rejections" for why every rejection costs one model call.

REVERSAL, recorded because the old warning here said not to look again. This
module was shelved on 2026-08-16 on the claim that UChicago's Workspace leaves
no route into the mailbox, including OAuth with gmail.readonly for an
unverified personal app. That half was wrong. The life-dashboard project
(~/agents/life-dashboard) already reads the UChicago inbox through OAuth
gmail.readonly: Workspace allowed the app once the owner accepted
its policy prompt, and an OAuth app published "In production" keeps its refresh
token past seven days. App passwords and forwarding really are disabled, so
IMAP stays dead, and the code below reads Gmail's own API instead. CHANGELOG.md
for 2026-10-08 has the details.

Four rules hold this module together and none of them is a preference.

Read-only is enforced by the scope, not by remembering. The token is refused
unless gmail.readonly is the only scope it carries, when it is created and every
time it is loaded. That scope cannot mark a message read, label it, move it or
send anything, so nothing here can either. The owner's unread count is not the
agent's to change.

The slice is narrow. Nothing is read that the search in `build_query` did not
match on a sender domain or a subject phrase, inside the lookback window. A
body is read only after its headers matched, and only when the snippet named a
company without saying which role.

Never attach an email to a posting on resemblance. A wrong Applied status hides
a live role from every list that asks "what has he not applied to yet", and the
ranker learns from that column. So an existing posting is marked only when the
email names it, by requisition id or by a title that equals the stored one once
case and punctuation are set aside. Anything short of that creates a new
posting instead, whose worst case is a visible duplicate rather than a hidden
role. A posting already past not_applied is never touched, so status only
moves forward.

No address, sender name, subject line or phrase appears below this docstring.
All of it is data in sources/inbox.toml, per CLAUDE.md rule 2. Company names
come from the postings table, never from here.
"""

from __future__ import annotations

import base64
import re
import tomllib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.utils import parseaddr
from html import unescape

from . import config, db, grouping
from .sources import normalize_company

GMAIL_READONLY = "https://www.googleapis.com/auth/gmail.readonly"
ALLOWED_SCOPES = frozenset({GMAIL_READONLY})
API = "https://gmail.googleapis.com/gmail/v1/users/me"

# A company name's legal suffix, dropped so "Acme Inc." in the database matches
# "Acme" in an email. Grammar, not data: no company is named here.
_LEGAL = {"inc", "llc", "ltd", "corp", "corporation", "co", "plc", "company"}

# The longest slice of an email the extraction call reads. Billed per token, and
# a confirmation states the role in its first few paragraphs.
EXTRACT_CHARS = 3000


class InboxError(RuntimeError):
    """Raised for anything that stops the mailbox being read."""


class NotConnected(InboxError):
    """No client or no token yet. Not a failure: the reader is not set up."""


# ------------------------------------------------------------------- config

@dataclass(frozen=True)
class Application:
    enabled: bool = False
    sender_domains: tuple[str, ...] = ()
    subject_phrases: tuple[str, ...] = ()
    ack_phrases: tuple[str, ...] = ()
    not_ack_phrases: tuple[str, ...] = ()
    rejection_phrases: tuple[str, ...] = ()
    fetch_body: bool = True
    max_extractions: int = 20
    title_noise_words: tuple[str, ...] = ()
    same_application_days: float = 3
    stale_after_days: float = 3


@dataclass(frozen=True)
class InboxConfig:
    lookback_days: int = 7
    max_messages: int = 50
    application: Application = field(default_factory=Application)


def load(path=None) -> InboxConfig:
    """Read sources/inbox.toml. Every sender and phrase in the system is here."""
    path = path or config.INBOX_PATH
    with open(path, "rb") as fh:
        raw = tomllib.load(fh)
    gmail = raw.get("gmail", {})
    app = raw.get("application", {})
    return InboxConfig(
        lookback_days=int(gmail.get("lookback_days", 7)),
        max_messages=int(gmail.get("max_messages", 50)),
        application=Application(
            enabled=bool(app.get("enabled", False)),
            sender_domains=tuple(app.get("sender_domains", [])),
            subject_phrases=tuple(app.get("subject_phrases", [])),
            ack_phrases=tuple(app.get("ack_phrases", [])),
            not_ack_phrases=tuple(app.get("not_ack_phrases", [])),
            rejection_phrases=tuple(app.get("rejection_phrases", [])),
            fetch_body=bool(app.get("fetch_body", True)),
            max_extractions=int(app.get("max_extractions", 20)),
            title_noise_words=tuple(w.lower() for w in app.get("title_noise_words", [])),
            same_application_days=float(app.get("same_application_days", 3)),
            stale_after_days=float(app.get("stale_after_days", 3)),
        ),
    )


# --------------------------------------------------------------------- auth

def check_scopes(scopes) -> None:
    """Refuse any token that carries more than gmail.readonly, or lacks it."""
    granted = set(scopes or ())
    extra = granted - ALLOWED_SCOPES
    if extra:
        raise InboxError(f"refusing a Gmail token with non-read-only scopes: {sorted(extra)}")
    if GMAIL_READONLY not in granted:
        raise InboxError("the Gmail token does not carry gmail.readonly")


def _client_config() -> dict:
    if not config.gmail_client_configured():
        raise NotConnected("GMAIL_CLIENT_ID and GMAIL_CLIENT_SECRET are not set in .env")
    return {
        "installed": {
            "client_id": config.GMAIL_CLIENT_ID,
            "client_secret": config.GMAIL_CLIENT_SECRET,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": ["http://localhost"],
        }
    }


def _save(creds) -> None:
    path = config.GMAIL_TOKEN_PATH
    path.write_text(creds.to_json())
    path.chmod(0o600)


def authorize():
    """Browser consent, once. Interactive, so never run by launchd."""
    from google_auth_oauthlib.flow import InstalledAppFlow

    flow = InstalledAppFlow.from_client_config(_client_config(), scopes=[GMAIL_READONLY])
    # select_account so the UChicago account is picked on purpose rather than
    # whichever Google account the browser happens to be signed into first.
    creds = flow.run_local_server(port=0, open_browser=True, prompt="select_account consent")
    check_scopes(creds.granted_scopes or creds.scopes)
    _save(creds)
    return config.GMAIL_TOKEN_PATH


def session():
    """An authorized HTTP session. Refreshes and re-saves an expired token."""
    from google.auth.transport.requests import AuthorizedSession, Request
    from google.oauth2.credentials import Credentials

    path = config.GMAIL_TOKEN_PATH
    if not path.exists():
        raise NotConnected(f"no Gmail token at {path.name}. Run: tools.inbox --authorize")
    creds = Credentials.from_authorized_user_file(str(path))
    check_scopes(creds.scopes)
    if not creds.valid:
        if not creds.refresh_token:
            raise InboxError("the Gmail token expired and has no refresh token. Re-authorize")
        creds.refresh(Request())
        _save(creds)
    return AuthorizedSession(creds)


# ------------------------------------------------------------------ reading

@dataclass
class Mail:
    id: str
    sender: str
    subject: str
    snippet: str
    received_at: str
    body: str = ""

    @property
    def sender_name(self) -> str:
        return parseaddr(self.sender)[0]

    @property
    def sender_domain(self) -> str:
        return parseaddr(self.sender)[1].rpartition("@")[2].lower()

    def text(self, with_body: bool = True) -> str:
        parts = [self.sender_name, self.subject, self.snippet]
        if with_body:
            parts.append(self.body)
        return "\n".join(p for p in parts if p)


def _quote(phrase: str) -> str:
    return '"' + phrase.replace('"', "") + '"'


def build_query(app: Application, days: int, exclude_from: tuple[str, ...] = ()) -> str:
    """The one search the reader runs. Narrow by construction.

    Sent mail is excluded so a message the owner wrote quoting a phrase is never
    read as one he received, and so is anything from the agent's own sending
    address, which is how the digest reaches this inbox.
    """
    terms = [f"from:{d}" for d in app.sender_domains]
    terms += [f"subject:{_quote(p)}" for p in app.subject_phrases]
    if not terms:
        raise InboxError("sources/inbox.toml [application] has no sender_domains or subject_phrases")
    query = f"newer_than:{int(days)}d -in:sent -in:chats -in:drafts ({' OR '.join(terms)})"
    for addr in exclude_from:
        if addr:
            query += f" -from:{addr}"
    return query


def list_ids(http, query: str, limit: int) -> tuple[list[str], bool]:
    """Message ids matching the query, newest first, and whether the limit cut it."""
    ids: list[str] = []
    params = {"q": query, "maxResults": min(limit, 100), "fields": "messages(id),nextPageToken"}
    while True:
        resp = http.get(f"{API}/messages", params=params, timeout=20)
        resp.raise_for_status()
        data = resp.json()
        ids.extend(m["id"] for m in data.get("messages", []))
        if len(ids) >= limit:
            return ids[:limit], True
        if not data.get("nextPageToken"):
            return ids, False
        params["pageToken"] = data["nextPageToken"]


def _stamp(internal_date) -> str:
    """Gmail's epoch milliseconds, in exactly the format `db.now()` writes.

    CLAUDE.md rule 15. `applied_at` has two writers already and every one of
    them writes an aware ISO timestamp to the second with a +00:00 offset. This
    is the third and writes the same, from when the email arrived rather than
    when the run happened to read it, which is the better date for when he
    applied.
    """
    when = datetime.fromtimestamp(int(internal_date or 0) / 1000, timezone.utc)
    return when.isoformat(timespec="seconds")


def parse_message(msg: dict) -> Mail:
    """A Gmail API message in metadata or full format, as a Mail."""
    headers = {h["name"].lower(): h["value"] for h in msg.get("payload", {}).get("headers", [])}
    return Mail(
        id=msg["id"],
        sender=headers.get("from", ""),
        subject=unescape(headers.get("subject", "")),
        # Gmail HTML-encodes snippets.
        snippet=unescape(msg.get("snippet", "")),
        received_at=_stamp(msg.get("internalDate")),
    )


def get_mail(http, message_id: str) -> Mail:
    resp = http.get(
        f"{API}/messages/{message_id}",
        params={
            "format": "metadata",
            "metadataHeaders": ["From", "Subject"],
            "fields": "id,snippet,internalDate,payload/headers",
        },
        timeout=20,
    )
    resp.raise_for_status()
    return parse_message(resp.json())


def _decode(data: str) -> str:
    raw = base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))
    return raw.decode("utf-8", errors="replace")


def body_text(payload: dict) -> str:
    """The readable text of a message payload, plain text preferred over HTML.

    HTML is reduced to its text, because a job title split across tags is
    still a job title, and the matcher compares words, not markup.
    """
    plain, html = [], []

    def walk(part):
        mime = part.get("mimeType", "")
        data = part.get("body", {}).get("data")
        if data and mime == "text/plain":
            plain.append(_decode(data))
        elif data and mime == "text/html":
            html.append(_decode(data))
        for child in part.get("parts", []) or []:
            walk(child)

    walk(payload or {})
    if plain:
        return "\n".join(plain)
    text = "\n".join(html)
    text = re.sub(r"(?is)<(script|style)\b.*?</\1>", " ", text)
    text = re.sub(r"<[^>]+>", " ", text)
    return unescape(text)


def get_body(http, message_id: str) -> str:
    resp = http.get(
        f"{API}/messages/{message_id}",
        params={"format": "full", "fields": "payload"},
        timeout=20,
    )
    resp.raise_for_status()
    return body_text(resp.json().get("payload", {}))


# ----------------------------------------------------------- classification

def words(text: str) -> str:
    """Lowercase letters and digits, single-spaced and padded, for whole-word tests."""
    return " " + re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip() + " "


def find_phrase(haystack: str, phrases) -> str | None:
    """The first phrase present as whole words in an already-`words` haystack."""
    for phrase in phrases:
        needle = words(phrase)
        if needle.strip() and needle in haystack:
            return phrase
    return None


def classify(text: str, app: Application) -> tuple[str, str]:
    """("reject", phrase), ("ack", phrase), ("not_ack", phrase) or ("other", "").

    "reject" means only that the email might be a rejection, and the model
    decides (see "rejections" below). It wins over everything, because a
    rejection very often opens by thanking him for applying and footers carry
    job-alert and account wording. A not-ack phrase wins over every ack phrase.
    """
    hay = words(text)
    hit = find_phrase(hay, app.rejection_phrases)
    if hit:
        return "reject", hit
    hit = find_phrase(hay, app.not_ack_phrases)
    if hit:
        return "not_ack", hit
    hit = find_phrase(hay, app.ack_phrases)
    if hit:
        return "ack", hit
    return "other", ""


# ----------------------------------------------------------------- matching

def _company_keys(name: str) -> set[str]:
    """A company name as joined tokens, with and without a legal suffix."""
    toks = words(name).split()
    keys = {"".join(toks)}
    while toks and toks[-1] in _LEGAL:
        toks = toks[:-1]
        keys.add("".join(toks))
    return {k for k in keys if len(k) >= 3}


def _windows(text: str, longest: int = 5) -> set[str]:
    """Every run of up to `longest` consecutive words, joined without spaces.

    Lets "BlueSky Robotics" in an email meet "Blue Sky Robotics" in the database,
    while still only ever matching on word boundaries: "meta" is a window of
    "Meta Platforms" and never of "metadata".
    """
    toks = words(text).split()
    out = set()
    for i in range(len(toks)):
        for n in range(1, longest + 1):
            if i + n <= len(toks):
                out.add("".join(toks[i:i + n]))
    return out


def companies_in(text: str, companies) -> list[str]:
    """Companies from the postings table that the text names, longest name winning.

    Where "Globex AI" and "Globex" are both companies and the text says "Globex
    AI", only the longer is kept, because the shorter is a word inside it.
    """
    windows = _windows(text)
    hits = {}
    for name in companies:
        matched = [k for k in _company_keys(name) if k in windows]
        if matched:
            hits[name] = max(matched, key=len)
    return [
        name for name, key in hits.items()
        if not any(key != other and key in other for other in hits.values())
    ]


def _req_id(value) -> str | None:
    """A requisition id worth searching for: six or more characters with a digit."""
    norm = words(str(value or "")).strip()
    if len(norm.replace(" ", "")) >= 6 and re.search(r"\d", norm):
        return norm
    return None


def _title(row) -> str | None:
    """A title worth searching for: two words or more, so "Intern" never matches."""
    norm = grouping.normalize_title(row.get("title"))
    return norm if len(norm.split()) >= 2 else None


@dataclass
class Match:
    outcome: str                 # apply, already, create, unsure (needs extraction)
    company: str = ""
    posting: dict | None = None
    reason: str = ""
    new: dict | None = None      # for create: company, title, location, url, req_id
    title_said: str | None = None  # the email's own title, when the model read one


def _lead(rows: list[dict]) -> dict:
    """The row of a location group that stands for the role. Airtable's lead.

    One application is one application, so one row is written however many
    cities the role was posted in, and it is the row the owner sees in the base.
    Writing every city would count one application several times in the
    waiting and silent lists.
    """
    return min(rows, key=grouping.by_oldest)


def _one_role(rows: list[dict]) -> dict | None:
    groups: dict = {}
    for row in rows:
        groups.setdefault(grouping.group_key(row), []).append(row)
    if len(groups) == 1:
        return _lead(next(iter(groups.values())))
    return None


def match(mail: Mail, postings_by_company: dict[str, list[dict]],
          with_body: bool = True) -> Match:
    """Which posting an acknowledgement is about, from evidence alone and for free.

    "unsure" means this could not decide, and the extraction below gets asked.

    Evidence, in order of strength:
      a requisition id of one posting appears in the email
      a full title of one role appears in the email
    and the company of that posting must be named by the email as well. A title
    alone is never enough, because "Software Engineer Intern" exists at a
    hundred companies.

    Where the sender name or subject names a company, that is the company. The
    body is consulted for a company only when the headers name none, because a
    body mentions other companies in footers and signatures.
    """
    head = "\n".join([mail.sender_name, mail.subject])
    named = companies_in(head, postings_by_company)
    if not named:
        named = companies_in(mail.text(with_body), postings_by_company)
    if not named:
        return Match("unsure", reason="no tracked company is named")

    company = named[0] if len(named) == 1 else ", ".join(sorted(named))
    rows = [r for name in named for r in postings_by_company[name]]
    hay = words(mail.text(with_body))

    by_id = [r for r in rows if (rid := _req_id(r.get("external_id"))) and f" {rid} " in hay]
    if by_id:
        lead = _one_role(by_id)
        if lead:
            return _settle(lead, company, "requisition id")

    titled = [r for r in rows if (t := _title(r)) and f" {t} " in hay]
    # A title that is only part of a longer matched title is not evidence of its
    # own: "software engineer intern" is inside "software engineer intern
    # infrastructure", and an email naming the second names the first too.
    titles = {_title(r) for r in titled}
    titled = [
        r for r in titled
        if not any(_title(r) != t and f" {_title(r)} " in f" {t} " for t in titles)
    ]
    if titled:
        lead = _one_role(titled)
        if lead:
            return _settle(lead, company, "title")
        return Match("unsure", company, reason="several roles match the title")

    return Match("unsure", company, reason="names the company but not the role")


def _settle(lead: dict, company: str, evidence: str) -> Match:
    if (lead.get("applied_status") or "not_applied") != "not_applied":
        return Match("already", company, posting=lead,
                     reason=f"{evidence}; already {lead.get('applied_status')}")
    return Match("apply", company, posting=lead, reason=evidence)


# --------------------------------------------------------------- extraction
#
# Added 2026-10-08, the same day as the reader, at the owner's instruction: he
# applied, so the agent should know about it without asking him which posting
# it was. Where the free matching above cannot place an email, one small Haiku
# call reads the company, title, location and requisition id off it, and that
# is matched again, exactly, against what the agent holds. If nothing matches,
# the posting is created. The prompt is sources/inbox_prompt.md, data per
# CLAUDE.md rule 2, sent verbatim.
#
# Why create rather than guess. Creating a row for a role the agent already
# holds under a different spelling costs a duplicate: the real row still says
# not applied and the created one says applied, both visible. Attaching an
# email to the wrong existing row hides a live role. So the extracted title has
# to equal a stored title after normalising case and punctuation, never merely
# resemble one, and everything short of that is created.

EXTRACT_SCHEMA = {
    "type": "object",
    "properties": {
        "kind": {
            "type": "string",
            "enum": ["confirmation", "rejection", "other"],
            "description": "confirmation: the email confirms the reader submitted an "
                           "application. rejection: it tells the reader an application "
                           "will not go further. other: anything else.",
        },
        "company": {"type": "string",
                    "description": "The employer, as the email names it, or ''."},
        "title": {"type": "string",
                  "description": "The job title exactly as the email states it, or ''."},
        "location": {"type": "string",
                     "description": "The job location if the email states one, or ''."},
        "requisition_id": {"type": "string",
                           "description": "A job or requisition number if stated, or ''."},
        "job_url": {"type": "string",
                    "description": "A link to the job posting itself if the email has "
                                   "one, or ''. Never an unsubscribe or account link."},
    },
    "required": ["kind", "company", "title", "location",
                 "requisition_id", "job_url"],
    "additionalProperties": False,
}

_PROMPT: str | None = None


def load_prompt(path=None) -> str:
    """Everything below the first `---` line of sources/inbox_prompt.md."""
    global _PROMPT
    if _PROMPT is not None and path is None:
        return _PROMPT
    text = (path or config.INBOX_PROMPT_PATH).read_text()
    prompt = text.split("\n---\n", 1)[1].strip() if "\n---\n" in text else text.strip()
    if path is None:
        _PROMPT = prompt
    return prompt


def extract(client, mail: Mail) -> dict:
    """One small Haiku call. Returns the fields plus the token counts."""
    import json

    text = mail.text()[:EXTRACT_CHARS]
    response = client.messages.create(
        model=config.STAGE0_MODEL,
        max_tokens=config.INBOX_MAX_TOKENS,
        system=load_prompt(),
        messages=[{"role": "user", "content": f"<email>\nFrom: {mail.sender}\n{text}\n</email>"}],
        output_config={"format": {"type": "json_schema", "schema": EXTRACT_SCHEMA}},
    )
    raw = next((b.text for b in response.content if b.type == "text"), "{}")
    data = json.loads(raw)
    data["input_tokens"] = response.usage.input_tokens
    data["output_tokens"] = response.usage.output_tokens
    return data


def _clean(value) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _stem(word: str) -> str:
    """Engineering and engineer, services and service, read as one word."""
    if word.endswith("ing") and len(word) > 6:
        return word[:-3]
    if word.endswith("s") and not word.endswith("ss") and len(word) > 4:
        return word[:-1]
    return word


def title_words(title: str, noise=()) -> frozenset[str]:
    """The words of a title that say which role it is.

    The noise words in sources/inbox.toml (intern, summer, a year) are dropped,
    because two listings of one role disagree about them constantly: one board
    writes "2027 Summer Intern - Software Engineer, AV/AI Platform" and another
    "Software Engineer Intern - AV/AI Platform". Order is ignored for the same
    reason. Nothing else is: a word one title has and the other lacks makes
    them different roles.
    """
    drop = {_stem(w) for w in noise}
    return frozenset(
        w for w in (_stem(t) for t in grouping.normalize_title(title).split())
        if w not in drop
    )


def _same_company(a: str, b: str) -> bool:
    na, nb = normalize_company(a), normalize_company(b)
    return bool(na) and na == nb


def resolve(found: Match, data: dict, by_company: dict[str, list[dict]],
            noise=()) -> Match:
    """What an extraction means: an existing posting, a new one, or nothing."""
    if data.get("kind") != "confirmation":
        return Match("ignored", reason="the model read it as not an application confirmation")

    company_said = _clean(data.get("company"))
    title = _clean(data.get("title"))
    if company_said:
        # The model's reading of the employer wins over anything the free
        # matcher found in the body, which can be a footer or, on 2026-10-08, a
        # feed's junk company literally named "Internship".
        named = companies_in(company_said, by_company) or [
            n for n in by_company if _same_company(n, company_said)
        ]
    else:
        named = [n for n in (x.strip() for x in found.company.split(",")) if n in by_company]
    company = named[0] if len(named) == 1 else company_said or found.company
    if not company:
        return Match("ignored", reason="no employer could be read from the email")

    rows = [r for n in named for r in by_company.get(n, [])]
    rid = _req_id(data.get("requisition_id"))
    by_id = [r for r in rows if rid and _req_id(r.get("external_id")) == rid]
    lead = _one_role(by_id) if by_id else None
    if lead:
        return _settle(lead, company, "requisition id, read by the model")
    want = grouping.normalize_title(title)
    same = [r for r in rows if want and grouping.normalize_title(r.get("title")) == want]
    if not same and title:
        words_ = title_words(title, noise)
        same = [r for r in rows if words_ and title_words(r.get("title"), noise) == words_]
    lead = _one_role(same) if same else None
    if lead:
        return _settle(lead, company, "title, read by the model")

    return Match("create", company, reason="not among the postings the agent holds",
                 title_said=title, new={
        "company": company,
        # A confirmation that names no role at all still records the application.
        # The row says so plainly rather than inventing a title.
        "title": title or "Role not named in the confirmation email",
        "location": _clean(data.get("location")),
        "url": _clean(data.get("job_url")),
        "req_id": _clean(data.get("requisition_id")),
    })


# --------------------------------------------------------------- rejections
#
# Added 2026-10-09. A rejection costs one model call every time, never free
# matching alone, for a reason found in his real mail the same day: the
# acknowledgements carry rejection wording. One says "if you are not selected
# for this position", another "if there is not an immediate fit".
# A phrase is therefore only a reason to ask, and the model's `kind` decides.
# An email it reads as a confirmation goes on as one; nothing is lost.
#
# Which posting. Rejected is the last word on an application, and a wrong one
# drops a live application out of every waiting and follow-up list. So it
# lands on an existing application only when the email names that posting (by
# requisition id or title, exactly as a confirmation does), or names a role
# whose words contain the application's, or names no role at a company where
# exactly one application is open. Two open applications and no way to tell
# them apart writes nothing ("unplaced"). Anything else creates the posting,
# already rejected, so the application is on record either way.

OPEN_APPLICATIONS = ("applied", "interviewing")


def _settle_rejection(lead: dict, company: str, evidence: str) -> Match:
    if (lead.get("applied_status") or "not_applied") not in db.REJECTABLE:
        return Match("already", company, posting=lead,
                     reason=f"{evidence}; already {lead.get('applied_status')}")
    return Match("reject", company, posting=lead, reason=evidence)


def resolve_rejection(data: dict, by_company: dict[str, list[dict]], noise=()) -> Match:
    """Which posting a rejection answers: reject, already, create or unplaced."""
    company_said = _clean(data.get("company"))
    if not company_said:
        return Match("unplaced", reason="no employer could be read from the rejection")
    named = companies_in(company_said, by_company) or [
        n for n in by_company if _same_company(n, company_said)
    ]
    company = named[0] if len(named) == 1 else company_said
    rows = [r for n in named for r in by_company.get(n, [])]
    title = _clean(data.get("title"))

    rid = _req_id(data.get("requisition_id"))
    by_id = [r for r in rows if rid and _req_id(r.get("external_id")) == rid]
    lead = _one_role(by_id) if by_id else None
    if lead:
        return _settle_rejection(lead, company, "requisition id, read by the model")
    want = grouping.normalize_title(title)
    email_words = title_words(title, noise) if title else None
    same = [r for r in rows if want and grouping.normalize_title(r.get("title")) == want]
    if not same and email_words:
        same = [r for r in rows if title_words(r.get("title"), noise) == email_words]
    lead = _one_role(same) if same else None
    if lead:
        return _settle_rejection(lead, company, "title, read by the model")

    open_ = [r for r in rows if r.get("applied_status") in OPEN_APPLICATIONS]
    if email_words is not None:
        open_ = [r for r in open_
                 if (w := title_words(r.get("title"), noise)) and w <= email_words]
    groups: dict = {}
    for r in open_:
        groups.setdefault(grouping.group_key(r), []).append(r)
    if len(groups) == 1:
        lead = _lead(next(iter(groups.values())))
        how = "the only open application there" if email_words is None else \
            "the open application whose title it contains"
        return _settle_rejection(lead, company, how)
    if len(groups) > 1:
        return Match("unplaced", company,
                     reason=f"{len(groups)} open applications at {company} and the "
                            "email does not say which")

    return Match("create", company, reason="no application on record to reject",
                 title_said=title, new={
        "company": company,
        "title": title or "Role not named in the rejection email",
        "location": _clean(data.get("location")),
        "url": _clean(data.get("job_url")),
        "req_id": _clean(data.get("requisition_id")),
    })


# ------------------------------------------------- one application, one row
#
# Added 2026-10-08 after the first real dry run. Applications logged by hand
# weeks before the reader existed had their confirmations read as evidence of
# new ones: some emails name no role, one uses a campus programme's long title
# for the role logged under the short one, and one matched a second listing of
# the same role from another feed. Every one of them would have been counted
# twice. The logged date and the email's date were within two days each time.


def _when(ts):
    try:
        when = datetime.fromisoformat(str(ts))
    except (TypeError, ValueError):
        return None
    return when if when.tzinfo else when.replace(tzinfo=timezone.utc)


def same_application(applications: list[dict], company: str, title: str, received_at: str,
                     app: Application) -> dict | None:
    """The application already on record that this email is confirming, if any.

    Same company, recorded within same_application_days of the email, and
    either the email names no role or every meaningful word of the recorded
    title is in the email's title. A requisition id never comes here, because
    it is definitive on its own.

    The cost of this rule is a real second application at one company in the
    same few days whose title contains the first one's words. That one would
    be recorded as the first. Two or three roles at one company in one week,
    each named differently, are unaffected.
    """
    sent = _when(received_at)
    if sent is None:
        return None
    email_words = title_words(title, app.title_noise_words) if title else None
    for a in applications:
        if not _same_company(a["company"], company):
            continue
        when = _when(a["applied_at"])
        if when is None or abs((sent - when).total_seconds()) > app.same_application_days * 86400:
            continue
        if email_words is None:
            return a
        recorded = title_words(a["title"], app.title_noise_words)
        if recorded and recorded <= email_words:
            return a
    return None


def _applications(conn) -> list[dict]:
    marks = ",".join("?" for _ in grouping.SENT_STATUSES)
    return [dict(r) for r in conn.execute(
        f"SELECT {_POSTING_COLUMNS} FROM postings WHERE applied_status IN ({marks}) "
        "AND applied_at IS NOT NULL", list(grouping.SENT_STATUSES))]


# ---------------------------------------------------------------- the run

_POSTING_COLUMNS = (
    "id, company, title, location, external_id, applied_status, applied_at, "
    "airtable_record_id, label, prefilter_verdict, closed_detected_at, url"
)


def postings_by_company(conn) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for r in conn.execute(f"SELECT {_POSTING_COLUMNS} FROM postings"):
        out.setdefault(r["company"], []).append(dict(r))
    return out


@dataclass
class Outcome:
    mail: Mail
    kind: str            # applied, rejected, created, already, kept, unplaced,
                         # not_ack, ignored, deferred
    match: Match | None = None
    reason: str = ""
    topic: str = "application"   # or "rejection": what the email turned out to be


@dataclass
class Spend:
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0


def process(conn, app: Application, mails: list[Mail], get_body=None, push=None,
            extractor=None, dry_run: bool = False, spend: Spend | None = None) -> list[Outcome]:
    """Handle every message not already in the ledger. Returns what happened.

    get_body(message_id) -> str is called only when the headers and snippet
    were not enough. extractor(mail) -> dict is the paid call, made only when
    the free matching could not place the email or it may be a rejection.
    push(rows_and_status, only_if_blank=..., only_from=...) is
    `airtable_sync.push_applied_status`. All three are passed in so tests
    never reach the network.

    A message the extractor could not be asked about, because there is no key,
    the call failed, or the run's cap was reached, is left out of the ledger
    and comes back next run. It is never guessed at.

    The order of writes is the point of this function. Airtable first, because
    Airtable is authoritative for Applied status and a SQLite write it does not
    know about is undone by the next pull. Only after it succeeds does SQLite
    get the status and the ledger get the message. If the push raises, nothing
    about those messages is recorded, so the next run tries them again instead
    of believing they were done. A created posting has no Airtable row yet, so
    it needs no push; the sync's create path carries the status up with it.

    Rejections are placed after every confirmation in the batch is written, so
    a first run over weeks of mail that holds both the acknowledgement and the
    rejection for one role finds the application the acknowledgement created,
    rather than creating a second posting for the rejection. A dry run writes
    nothing, so there a rejection can show as a create that a real run would not make.
    """
    spend = spend if spend is not None else Spend()
    seen = db.inbox_seen(conn, [m.id for m in mails])
    by_company = postings_by_company(conn)
    applications = _applications(conn)
    outcomes: list[Outcome] = []
    to_apply: list[Outcome] = []
    to_create: list[Outcome] = []
    rejections: list[tuple[Mail, dict, str]] = []
    claimed: set[int] = set()

    def ask(mail: Mail, found: Match | None) -> dict | None:
        """The paid call, or None with a deferred outcome recorded."""
        if extractor is None or spend.calls >= app.max_extractions:
            outcomes.append(Outcome(mail, "deferred", found,
                                    "needs the model call, not made this run"))
            return None
        try:
            data = extractor(mail)
        except Exception as exc:  # noqa: BLE001 - one email must not stop the rest
            outcomes.append(Outcome(mail, "deferred", found,
                                    f"model call failed: {type(exc).__name__}"))
            return None
        spend.calls += 1
        spend.input_tokens += int(data.get("input_tokens") or 0)
        spend.output_tokens += int(data.get("output_tokens") or 0)
        return data

    for mail in mails:
        if mail.id in seen:
            continue
        can_read = app.fetch_body and get_body is not None
        kind, phrase = classify(mail.text(), app)
        if kind == "other" and can_read and not mail.body:
            # Workday and some company senders put "thank you for applying" in
            # the body under a subject that is only the job title.
            mail.body = get_body(mail.id)
            kind, phrase = classify(mail.text(), app)

        found = match(mail, by_company) if kind == "ack" else None
        if found and found.outcome == "unsure" and can_read and not mail.body:
            mail.body = get_body(mail.id)
            # The body is read again for rejection wording too. A rejection
            # phrase sends it to the model rather than to a write.
            kind, phrase = classify(mail.text(), app)
            found = match(mail, by_company) if kind == "ack" else None

        data = None
        if kind == "reject":
            if can_read and not mail.body:
                # The rejection's role is usually a paragraph down, and the
                # model cannot place a rejection it was not shown the role of.
                mail.body = get_body(mail.id)
            data = ask(mail, None)
            if data is None:
                continue
            if data.get("kind") == "rejection":
                rejections.append((mail, data, phrase))
                continue
            if data.get("kind") != "confirmation":
                outcomes.append(Outcome(mail, "not_ack", reason=f"{phrase}; the model read "
                                        "it as neither a confirmation nor a rejection"))
                continue
            kind, found = "ack", match(mail, by_company)

        if kind != "ack":
            outcomes.append(Outcome(mail, "not_ack" if kind == "not_ack" else "ignored",
                                    reason=phrase))
            continue

        if found.outcome == "unsure":
            if data is None:
                data = ask(mail, found)
                if data is None:
                    continue
            if data.get("kind") == "rejection":
                rejections.append((mail, data, "read by the model"))
                continue
            found = resolve(found, data, by_company, app.title_noise_words)

        if found.outcome in ("apply", "create") and "requisition id" not in found.reason:
            title = (found.title_said if found.outcome == "create"
                     else found.posting.get("title"))
            prior = same_application(applications, found.company, title or "",
                                     mail.received_at, app)
            if prior and not (found.posting and prior["id"] == found.posting["id"]):
                found = Match("already", found.company, posting=prior,
                              reason=f"the application logged {str(prior['applied_at'])[:10]}")
        if found.outcome == "apply":
            # Counted from here on, so a later email in this run can be read as
            # confirming it. A posting created this run is not added: it has no
            # id yet, and db.insert_applied_posting's content match already
            # stops a second identical email creating it twice.
            applications.append({**found.posting, "applied_at": mail.received_at})

        if found.outcome in ("apply", "create") and found.posting and found.posting["id"] in claimed:
            found = Match("already", found.company, posting=found.posting,
                          reason="a second email for a posting this run already applied")
        if found.outcome == "apply":
            claimed.add(found.posting["id"])
            to_apply.append(Outcome(mail, "applied", found, found.reason))
        elif found.outcome == "create":
            to_create.append(Outcome(mail, "created", found, found.reason))
        else:
            outcomes.append(Outcome(mail, found.outcome, found, found.reason))

    if not dry_run:
        for o in outcomes:
            if o.kind != "deferred":
                db.record_inbox(conn, _ledger_row(o), commit=False)
        conn.commit()
        _write(conn, push, to_apply, to_create, "applied")

    rejected = _place_rejections(conn, app, rejections, outcomes, dry_run)
    if not dry_run:
        _write(conn, push, rejected["write"], rejected["create"], "rejected")
    return (outcomes + to_apply + to_create + rejected["other"]
            + rejected["write"] + rejected["create"])


def _place_rejections(conn, app: Application, rejections, outcomes, dry_run) -> dict:
    """Resolve each rejection against the postings as they stand now."""
    by_company = postings_by_company(conn)
    out: dict[str, list[Outcome]] = {"write": [], "create": [], "other": []}
    claimed: set[int] = set()
    for mail, data, phrase in rejections:
        found = resolve_rejection(data, by_company, app.title_noise_words)
        if found.posting and found.posting["id"] in claimed:
            found = Match("already", found.company, posting=found.posting,
                          reason="a second rejection for a posting this run already rejected")
        kind = {"reject": "rejected", "create": "created"}.get(found.outcome, found.outcome)
        o = Outcome(mail, kind, found, found.reason, topic="rejection")
        if found.outcome == "reject":
            claimed.add(found.posting["id"])
            out["write"].append(o)
        elif found.outcome == "create":
            out["create"].append(o)
        else:
            out["other"].append(o)
            if not dry_run:
                db.record_inbox(conn, _ledger_row(o), commit=False)
    if not dry_run:
        conn.commit()
    return out


def _write(conn, push, to_mark: list[Outcome], to_create: list[Outcome], status: str) -> None:
    """Airtable, then SQLite, then the ledger, for one status. See process."""
    kept: set[int] = set()
    if to_mark and push is not None:
        rows = [(o.match.posting, status) for o in to_mark]
        if status == "applied":
            result = push(rows, only_if_blank=True)
        else:
            result = push(rows, only_from=db.REJECTABLE)
        kept = set(result.get("kept", []))

    for o in to_mark:
        pid = o.match.posting["id"]
        if pid in kept:
            # The base already says something this may not replace, and the
            # base wins. The next pull brings that status down to SQLite.
            o.kind = "kept"
            o.reason = "Airtable already holds a status for this posting"
        elif status == "applied":
            db.mark_applied(conn, pid, o.mail.received_at)
        else:
            db.mark_rejected(conn, pid, o.mail.received_at)
        db.record_inbox(conn, _ledger_row(o), commit=False)

    for o in to_create:
        n = o.match.new
        row, created = db.insert_applied_posting(
            conn, company=n["company"], title=n["title"], location=n["location"],
            url=n["url"] or f"https://mail.google.com/mail/#all/{o.mail.id}",
            external_id=n["req_id"] or o.mail.id, applied_at=o.mail.received_at,
            status=status,
        )
        o.match.posting = row
        if not created:
            # Stored already under the same content; db marked that row instead.
            o.kind = "already"
        db.record_inbox(conn, _ledger_row(o), commit=False)
    conn.commit()


def _ledger_row(o: Outcome) -> dict:
    m = o.match
    outcome = {"kept": "already"}.get(o.kind, o.kind)
    return {
        "message_id": o.mail.id,
        "kind": o.topic,
        "outcome": outcome,
        "sender": o.mail.sender,
        "subject": o.mail.subject,
        "received_at": o.mail.received_at,
        "company": m.company if m else None,
        "posting_id": m.posting["id"] if m and m.posting else None,
        "reason": o.reason,
    }


# ------------------------------------------------------------ for the digest

STATE_LAST_OK = "inbox_last_ok"


def mark_ok(conn) -> None:
    db.set_state(conn, STATE_LAST_OK, db.now())


def stale_since(conn, cfg: InboxConfig | None = None, now: datetime | None = None) -> str | None:
    """None while the reader is healthy, else when it last succeeded ("never").

    A revoked token is a failure of an optional step, which the run log records
    and nothing emails, so without this line in the digest Applied status would
    quietly stop updating.
    """
    cfg = cfg or load()
    if not cfg.application.enabled:
        return None
    now = now or datetime.now(timezone.utc)
    raw = db.get_state(conn, STATE_LAST_OK)
    try:
        last = datetime.fromisoformat(str(raw)) if raw else None
    except ValueError:
        last = None
    if last is None:
        return "never"
    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    if (now - last).total_seconds() / 86400 > cfg.application.stale_after_days:
        return last.date().isoformat()
    return None
