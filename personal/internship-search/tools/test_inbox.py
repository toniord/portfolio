"""The inbox reader: confirmations to Applied, rejections to Rejected. 2026-10-08.

    .venv/bin/python -m tools.test_inbox

Spends nothing, sends nothing, never reaches Gmail, Airtable or the model, and
never touches state.db. Gmail is replaced by Mail objects, Airtable by a fake
push and the Haiku call by a fake extractor, so every case runs offline in a
temporary database.

What it guards, and why each one leaves no trace when it breaks:

    a wrong match      writes Applied on a role he never applied to, which
                       hides a live posting from every "not applied yet" list
                       and teaches the ranker the wrong lesson
    a wrong rejection  drops a live application out of every waiting and
                       follow-up list, and acknowledgements carry rejection
                       wording, so a phrase alone must never write it
    the write order    Airtable before SQLite before the ledger. Get it wrong
                       and a failed push is recorded as done, and the next
                       pull silently undoes the SQLite half
    the ledger         a message handled twice creates a second posting
    a created posting  must reach Airtable, must never be emailed as a new
                       find, and must survive the filter being re-applied
    the stamp format   applied_at has two other writers, and a format that
                       differs from theirs took the agent down for 44 hours
                       on 2026-09-22 (CLAUDE.md rule 15)
    the spine          nothing in the inbox may be able to stop the watcher

Run this after editing agent/inbox.py, the inbox half of agent/delivery.py,
airtable_sync.push_applied_status, or sources/inbox.toml.
"""

import base64
import sqlite3
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from agent import airtable_sync, config, db, delivery, emailhtml, fetchers, inbox, notify, schedule

PASS, FAIL = "ok  ", "FAIL"
results: list[tuple[bool, str, str]] = []


def check(name: str, got, want, note: str = "") -> None:
    results.append((got == want, name, note or f"got {got!r}, wanted {want!r}"))


APP = inbox.Application(
    enabled=True,
    sender_domains=("greenhouse-mail.io", "myworkday.com"),
    subject_phrases=("thank you for applying",),
    ack_phrases=("thank you for applying", "thank you for your application",
                 "application received"),
    not_ack_phrases=("job alert", "schedule an interview"),
    rejection_phrases=("unfortunately", "other candidates", "not selected"),
    fetch_body=True,
    max_extractions=20,
    title_noise_words=("intern", "internship", "summer", "spring", "2027"),
    same_application_days=3,
    stale_after_days=3,
)
CFG = inbox.InboxConfig(lookback_days=7, max_messages=50, application=APP)


def make_db() -> sqlite3.Connection:
    return db.connect(Path(tempfile.mkdtemp()) / "test.db")


_n = [0]


def add(conn, **kw) -> int:
    _n[0] += 1
    n = _n[0]
    row = {
        "hash": f"h{n}", "identity": f"i{n}", "content_hash": f"h{n}",
        "company": "Acme", "title": f"Role {n}", "location": "Chicago, IL",
        "url": f"https://example.test/{n}", "source": "greenhouse:acme",
        "first_seen": "2026-09-01T00:00:00+00:00",
        "last_seen_open": "2026-10-01T00:00:00+00:00",
        "prefilter_verdict": "surface", "applied_status": "not_applied",
        "flags": "", "term": "summer2027", "external_id": f"ext{n}",
    }
    row.update(kw)
    cur = conn.execute(
        f"INSERT INTO postings ({', '.join(row)}) VALUES ({', '.join('?' for _ in row)})",
        list(row.values()),
    )
    conn.commit()
    return cur.lastrowid


def mail(subject: str, snippet: str = "", sender: str = "Acme <no-reply@greenhouse.example.com>",
         body: str = "", mid: str | None = None) -> inbox.Mail:
    _n[0] += 1
    return inbox.Mail(id=mid or f"m{_n[0]}", sender=sender, subject=subject,
                      snippet=snippet, received_at="2026-10-05T14:03:00+00:00", body=body)


def status(conn, pid) -> tuple:
    r = conn.execute("SELECT applied_status, applied_at FROM postings WHERE id = ?",
                     (pid,)).fetchone()
    return (r["applied_status"], r["applied_at"])


class FakePush:
    """Stands in for airtable_sync.push_applied_status and records its calls."""

    def __init__(self, kept=(), fail=False):
        self.calls, self.kept, self.fail = [], list(kept), fail

    def __call__(self, rows_and_status, only_if_blank=False, only_from=None):
        self.calls.append(([r["id"] for r, _ in rows_and_status],
                           only_from if only_from is not None else only_if_blank))
        if self.fail:
            raise RuntimeError("airtable down")
        return {"written": len(rows_and_status) - len(self.kept), "kept": self.kept}


class FakeExtractor:
    """Stands in for the Haiku call. Returns one canned answer per call."""

    def __init__(self, *answers, fail=False):
        self.answers, self.fail, self.calls = list(answers), fail, []

    def __call__(self, m):
        self.calls.append(m.id)
        if self.fail:
            raise RuntimeError("api down")
        base = {"kind": "confirmation", "company": "", "title": "",
                "location": "", "requisition_id": "", "job_url": "",
                "input_tokens": 900, "output_tokens": 60}
        base.update(self.answers.pop(0) if self.answers else {})
        return base


def row(conn, pid) -> dict:
    return dict(conn.execute("SELECT * FROM postings WHERE id = ?", (pid,)).fetchone())


# ------------------------------------------------------------------ scope

def test_only_gmail_readonly_is_accepted():
    """A token is read-only because the scope is, so the scope check is the guarantee."""
    def refused(scopes):
        try:
            inbox.check_scopes(scopes)
        except inbox.InboxError:
            return True
        return False

    check("exactly gmail.readonly passes", refused([inbox.GMAIL_READONLY]), False)
    check("a modify scope alongside is refused",
          refused([inbox.GMAIL_READONLY, "https://www.googleapis.com/auth/gmail.modify"]), True)
    check("a calendar scope alongside is refused",
          refused([inbox.GMAIL_READONLY, "https://www.googleapis.com/auth/calendar"]), True)
    check("a token without gmail.readonly is refused", refused([]), True)


def test_no_token_is_not_a_failure():
    """Not connected yet is a source that is not set up, so the step exits 0."""
    saved = (config.GMAIL_TOKEN_PATH, config.DB_PATH, inbox.load)
    try:
        config.GMAIL_TOKEN_PATH = Path(tempfile.mkdtemp()) / "missing.json"
        config.DB_PATH = Path(tempfile.mkdtemp()) / "test.db"
        inbox.load = lambda path=None: CFG
        from tools import inbox as tool
        check("no token exits 0", tool.main([]), 0)
    finally:
        config.GMAIL_TOKEN_PATH, config.DB_PATH, inbox.load = saved


# ------------------------------------------------------------- the search

def test_query_is_narrow_and_skips_own_mail():
    q = inbox.build_query(APP, 7, ("agent@example.test",))
    check("query is bounded in time", "newer_than:7d" in q, True)
    check("query never reads sent mail", "-in:sent" in q, True)
    check("query names the sender domains", "from:myworkday.com" in q, True)
    check("query names the subject phrases", 'subject:"thank you for applying"' in q, True)
    check("the agent's own address is excluded", "-from:agent@example.test" in q, True)


def test_body_is_decoded_and_html_stripped():
    enc = lambda s: base64.urlsafe_b64encode(s.encode()).decode().rstrip("=")
    plain = {"mimeType": "multipart/alternative", "parts": [
        {"mimeType": "text/html", "body": {"data": enc("<p>ignored</p>")}},
        {"mimeType": "text/plain", "body": {"data": enc("Thank you for applying")}},
    ]}
    check("plain text is preferred", inbox.body_text(plain), "Thank you for applying")
    html = {"mimeType": "text/html",
            "body": {"data": enc("<style>x{}</style><b>Data</b> <i>Intern</i>")}}
    check("html is reduced to words", inbox.words(inbox.body_text(html)), " data intern ")


# --------------------------------------------------------- classification

def test_a_rejection_is_never_an_acknowledgement():
    """Rejections open by thanking him for applying. The rejection list wins."""
    kind, _ = inbox.classify("Thank you for your application. Unfortunately we", APP)
    check("a rejection phrase wins over an ack phrase", kind, "reject")
    kind, _ = inbox.classify("Thank you for applying. Job alert: other candidates", APP)
    check("and over a not-ack phrase", kind, "reject")
    kind, _ = inbox.classify("Thank you for applying. Please schedule an interview", APP)
    check("a not-ack phrase wins over an ack phrase", kind, "not_ack")
    kind, _ = inbox.classify("Thank you for applying to Acme", APP)
    check("acknowledgement is ack", kind, "ack")
    kind, _ = inbox.classify("New jobs at Acme this week", APP)
    check("anything else is other", kind, "other")


def test_company_names_match_on_word_boundaries():
    check("spacing differences still match",
          inbox.companies_in("Thanks from BlueSky Robotics", ["Blue Sky Robotics"]), ["Blue Sky Robotics"])
    check("a name inside a longer word does not match",
          inbox.companies_in("your metadata request", ["Meta"]), [])
    check("the longer company wins over a word inside it",
          inbox.companies_in("Thank you for applying to Globex AI", ["Globex", "Globex AI"]),
          ["Globex AI"])
    check("a legal suffix is optional",
          inbox.companies_in("Thank you for applying to Acme", ["Acme Inc."]), ["Acme Inc."])


# ---------------------------------------------------------------- matching

def test_requisition_id_is_decisive():
    conn = make_db()
    a = add(conn, title="Software Engineer Intern", external_id="4703343005")
    add(conn, title="Software Engineer Intern", external_id="4703343099", location="NYC")
    m = inbox.match(mail("Thank you for applying to Acme",
                         body="Job 4703343005 Software Engineer Intern"),
                    inbox.postings_by_company(conn))
    check("the requisition id picks its posting", (m.outcome, m.posting and m.posting["id"]),
          ("apply", a))


def test_title_and_company_together_apply():
    conn = make_db()
    a = add(conn, title="Data Science Intern")
    add(conn, title="Mechanical Engineer Intern")
    m = inbox.match(mail("Thank you for applying", "for the Data Science Intern role at Acme"),
                    inbox.postings_by_company(conn))
    check("a full title at a named company applies", (m.outcome, m.posting["id"]), ("apply", a))


def test_a_title_without_its_company_is_never_enough():
    """'Software Engineer Intern' exists at a hundred companies."""
    conn = make_db()
    add(conn, company="Acme", title="Software Engineer Intern")
    m = inbox.match(mail("Thank you for applying", "Software Engineer Intern at Globex",
                         sender="Globex <no-reply@globex.test>"),
                    inbox.postings_by_company(conn))
    check("the free matcher does not decide it", (m.outcome, m.posting), ("unsure", None))


def test_a_contained_title_is_not_a_second_role():
    conn = make_db()
    add(conn, title="Software Engineer Intern")
    b = add(conn, title="Software Engineer Intern, Infrastructure")
    m = inbox.match(mail("Thank you for applying to Acme",
                         "Software Engineer Intern, Infrastructure"),
                    inbox.postings_by_company(conn))
    check("the longer title wins", (m.outcome, m.posting and m.posting["id"]), ("apply", b))


def test_a_one_word_title_is_not_evidence():
    """A posting titled "Intern" would otherwise match every email that says intern."""
    conn = make_db()
    add(conn, title="Intern")
    add(conn, title="Data Science Intern")
    m = inbox.match(mail("Thank you for applying to Acme", "your intern application"),
                    inbox.postings_by_company(conn))
    check("a one-word title is not decided for free", m.outcome, "unsure")


def test_one_city_of_a_location_group_is_written():
    """One application is one row, the one the base shows, never every city."""
    conn = make_db()
    a = add(conn, title="Quant Research Intern", location="New York")
    add(conn, title="Quant Research Intern", location="Chicago")
    add(conn, title="Quant Research Intern", location="London")
    m = inbox.match(mail("Thank you for applying to Acme", "Quant Research Intern"),
                    inbox.postings_by_company(conn))
    check("the oldest city leads, as in Airtable", (m.outcome, m.posting["id"]), ("apply", a))


def test_two_roles_with_matching_titles_are_unsure():
    conn = make_db()
    add(conn, title="Research Intern")
    add(conn, title="Product Intern")
    m = inbox.match(mail("Thank you for applying to Acme", "Research Intern and Product Intern"),
                    inbox.postings_by_company(conn))
    check("two named roles go to the model", m.outcome, "unsure")


# ---------------------------------------------------------- the model call

def test_the_model_is_asked_only_when_the_free_match_fails():
    conn = make_db()
    add(conn, title="Data Science Intern")
    ext = FakeExtractor()
    inbox.process(conn, APP, [mail("Thank you for applying", "Data Science Intern at Acme")],
                  push=FakePush(), extractor=ext)
    check("a title in the snippet costs nothing", ext.calls, [])


def test_an_extracted_title_marks_the_existing_posting():
    conn = make_db()
    a = add(conn, title="Data Science Intern", airtable_record_id="recA")
    add(conn, title="Mechanical Engineer Intern")
    push = FakePush()
    out = inbox.process(conn, APP, [mail("Thank you for applying to Acme", "We got it")],
                        push=push, extractor=FakeExtractor({"company": "Acme",
                                                            "title": "Data Science Intern"}))
    check("it applied to the posting held", [o.kind for o in out], ["applied"])
    check("and pushed it, only if blank", push.calls, [([a], True)])
    check("SQLite holds applied", status(conn, a)[0], "applied")
    check("no posting was created", conn.execute("SELECT COUNT(*) FROM postings").fetchone()[0], 2)


def test_a_resembling_title_creates_rather_than_guesses():
    """Never attach on resemblance. A duplicate is visible, a wrong Applied is not."""
    conn = make_db()
    a = add(conn, title="Data Science Intern")
    out = inbox.process(conn, APP, [mail("Thank you for applying to Acme", "We got it")],
                        push=FakePush(), extractor=FakeExtractor(
                            {"company": "Acme", "title": "Data Science Intern, Ads"}))
    check("a different title is a new posting", [o.kind for o in out], ["created"])
    check("the similar posting is untouched", status(conn, a)[0], "not_applied")
    b = add(conn, title="Software Engineer Intern, Infrastructure")
    out = inbox.process(conn, APP, [mail("Thank you for applying to Acme", "We got it")],
                        push=FakePush(), extractor=FakeExtractor(
                            {"company": "Acme", "title": "Software Engineer Intern"}))
    check("a shorter title is a new posting too", [o.kind for o in out], ["created"])
    check("the longer posting is untouched", status(conn, b)[0], "not_applied")


def test_an_unknown_posting_is_created_applied():
    conn = make_db()
    m = mail("Thank you for applying!", "We received your application.",
             sender="Globex Hiring <no-reply@greenhouse.example.com>")
    out = inbox.process(conn, APP, [m], push=FakePush(), extractor=FakeExtractor(
        {"company": "Globex", "title": "Quant Research Intern", "location": "London",
         "requisition_id": "R-20931", "job_url": "https://globex.test/jobs/20931"}))
    check("it was created", [o.kind for o in out], ["created"])
    r = row(conn, out[0].match.posting["id"])
    check("company, title, location and link are the email's",
          (r["company"], r["title"], r["location"], r["url"]),
          ("Globex", "Quant Research Intern", "London", "https://globex.test/jobs/20931"))
    check("it is applied, dated by the email", (r["applied_status"], r["applied_at"]),
          ("applied", m.received_at))
    check("it is surfaced, so Airtable carries it", r["prefilter_verdict"], "surface")
    check("its identity is the fetchers rule (rule 6)",
          r["identity"], fetchers._identity("inbox:applications", "R-20931", r["content_hash"]))
    check("no email carried it, so nothing is stamped (rule 10)", r["alerted_at"], None)
    check("the ledger records it", db.inbox_seen(conn, [m.id]), {m.id})


def test_a_company_already_held_keeps_its_spelling():
    conn = make_db()
    add(conn, company="Blue Sky Robotics", title="Markets Intern")
    out = inbox.process(conn, APP, [mail("Thank you for applying", "",
                                         sender="BlueSky Robotics <x@workday.example.com>")],
                        push=FakePush(), extractor=FakeExtractor(
                            {"company": "BlueSky Robotics", "title": "Data Analyst Intern"}))
    check("the created posting uses the stored company name",
          out[0].match.posting["company"], "Blue Sky Robotics")


def test_a_confirmation_naming_no_role_still_records_it():
    conn = make_db()
    out = inbox.process(conn, APP, [mail("Thank you for applying to Initech", "",
                                         sender="Initech <a@initech.test>")],
                        push=FakePush(), extractor=FakeExtractor({"company": "Initech"}))
    check("a posting is created anyway", [o.kind for o in out], ["created"])
    check("and says plainly the role was not named", out[0].match.posting["title"],
          "Role not named in the confirmation email")


def test_the_model_saying_no_writes_nothing():
    conn = make_db()
    out = inbox.process(conn, APP, [mail("Thank you for applying to our newsletter", "")],
                        push=FakePush(), extractor=FakeExtractor(
                            {"kind": "other", "company": "Acme",
                             "title": "Newsletter Subscriber"}))
    check("it is ignored", [o.kind for o in out], ["ignored"])
    check("nothing created", conn.execute("SELECT COUNT(*) FROM postings").fetchone()[0], 0)


def test_no_model_means_wait_never_guess():
    conn = make_db()
    out = inbox.process(conn, APP, [mail("Thank you for applying to Acme", "", mid="w1")],
                        push=FakePush(), extractor=None)
    check("deferred without a model", [o.kind for o in out], ["deferred"])
    check("and left out of the ledger, so it returns", db.inbox_seen(conn, ["w1"]), set())
    out = inbox.process(conn, APP, [mail("Thank you for applying to Acme", "", mid="w2")],
                        push=FakePush(), extractor=FakeExtractor(fail=True))
    check("a failed call defers too", (out[0].kind, db.inbox_seen(conn, ["w2"])),
          ("deferred", set()))


def test_the_call_cap_holds():
    conn = make_db()
    capped = inbox.Application(**{**APP.__dict__, "max_extractions": 1})
    ext = FakeExtractor({"company": "A1", "title": "Role One Intern"},
                        {"company": "A2", "title": "Role Two Intern"})
    spend = inbox.Spend()
    out = inbox.process(conn, capped, [mail("Thank you for applying", "", sender="A1 <a@a1.test>"),
                                       mail("Thank you for applying", "", sender="A2 <a@a2.test>")],
                        push=FakePush(), extractor=ext, spend=spend)
    check("one call, one deferred", (len(ext.calls), sorted(o.kind for o in out)),
          (1, ["created", "deferred"]))
    check("the spend is counted", (spend.calls, spend.input_tokens, spend.output_tokens),
          (1, 900, 60))


def test_two_emails_for_one_new_posting_create_one():
    conn = make_db()
    answer = {"company": "Globex", "title": "Quant Research Intern"}
    out = inbox.process(conn, APP, [mail("Thank you for applying", "", sender="Globex <a@g.test>"),
                                    mail("Thank you for applying", "", sender="Globex <a@g.test>")],
                        push=FakePush(), extractor=FakeExtractor(answer, dict(answer)))
    check("one created, one already", sorted(o.kind for o in out), ["already", "created"])
    check("one row", conn.execute("SELECT COUNT(*) FROM postings").fetchone()[0], 1)


# ---------------- problem shapes from the first real dry run, 2026-10-08, invented data

def test_company_names_meet_through_the_normalizer():
    """"Initech" in an email is "Initech AI" in the database."""
    conn = make_db()
    a = add(conn, company="Initech AI", title="Example Role Intern",
            prefilter_verdict="killed", prefilter_reason="location: Example City")
    add(conn, company="Internship", title="Junk Feed Row")
    out = inbox.process(conn, APP, [mail("Thank you for applying to Initech", "",
                                         sender="Initech Hiring Team <x@ashby.example.com>",
                                         body="Example Role Intern")],
                        push=FakePush(), extractor=FakeExtractor(
                            {"company": "Initech", "title": "Example Role Intern"}))
    check("the stored Initech AI posting is marked", (out[0].kind, out[0].match.posting["id"]),
          ("applied", a))


def test_an_application_brings_a_killed_posting_back():
    conn = make_db()
    a = add(conn, title="Example Role Intern", prefilter_verdict="killed",
            prefilter_reason="location: Example City")
    inbox.process(conn, APP, [mail("Thank you for applying", "Example Role Intern at Acme")],
                  push=FakePush())
    r = row(conn, a)
    check("it is surfaced again, so Airtable can show it", r["prefilter_verdict"], "surface")
    check("and still says why the rules disliked it", r["prefilter_reason"],
          "applied, overriding: location: Example City")


def test_word_order_and_noise_do_not_make_a_new_role():
    conn = make_db()
    a = add(conn, title="Software Engineer Intern - Perception Platform")
    add(conn, title="Software Verification Engineer Intern - Perception Platform")
    out = inbox.process(conn, APP, [mail("Thank you for applying", "", mid="o1")],
                        push=FakePush(), extractor=FakeExtractor(
                            {"company": "Acme",
                             "title": "2027 Summer Intern - Software Engineer, Perception Platform"}))
    check("the reordered title is the same role", (out[0].kind, out[0].match.posting["id"]),
          ("applied", a))
    check("an extra word is still a different role",
          inbox.title_words("Software Verification Engineer Intern - Perception Platform", APP.title_noise_words)
          == inbox.title_words("Software Engineer Intern - Perception Platform", APP.title_noise_words),
          False)


def test_a_logged_application_absorbs_its_own_confirmation():
    """One email names no role; another uses a longer title. Neither is a second application."""
    conn = make_db()
    a = add(conn, title="Data Engineer Intern, Payments Platform",
            applied_status="applied", applied_at="2026-10-04T00:00:00+00:00")
    add(conn, title="Campus Summer Internship Program - 2027 Data Engineer, Payments Platform")
    out = inbox.process(conn, APP, [
        mail("Thank you for applying to Acme", "", mid="s1"),
        mail("Thank you for applying", "Campus Summer Internship Program - 2027 Data Engineer, "
             "Payments Platform at Acme", mid="s2"),
    ], push=FakePush(), extractor=FakeExtractor({"company": "Acme"}))
    check("both read as the logged application",
          [(o.kind, o.match.posting["id"]) for o in out], [("already", a), ("already", a)])
    check("nothing created", conn.execute("SELECT COUNT(*) FROM postings").fetchone()[0], 2)


def test_a_different_role_the_same_week_is_still_new():
    """Two differently named roles at one company in one week are two applications."""
    conn = make_db()
    add(conn, title="AI Engineering Intern", applied_status="applied",
        applied_at="2026-10-05T00:00:00+00:00")
    b = add(conn, title="Data Science Intern")
    out = inbox.process(conn, APP, [mail("Thank you for applying", "Data Science Intern at Acme")],
                        push=FakePush())
    check("a role with other words is applied", (out[0].kind, out[0].match.posting["id"]),
          ("applied", b))


def test_an_old_application_does_not_absorb_a_new_one():
    conn = make_db()
    add(conn, applied_status="applied", applied_at="2026-08-01T00:00:00+00:00")
    out = inbox.process(conn, APP, [mail("Thank you for applying to Acme", "")],
                        push=FakePush(), extractor=FakeExtractor({"company": "Acme"}))
    check("two months apart is a new application", [o.kind for o in out], ["created"])


def test_a_requisition_id_is_never_absorbed():
    conn = make_db()
    add(conn, title="AI Engineer", applied_status="applied", applied_at="2026-10-05T00:00:00+00:00")
    b = add(conn, title="AI Engineer Platform", external_id="9988776655")
    out = inbox.process(conn, APP, [mail("Thank you for applying to Acme", "Job 9988776655")],
                        push=FakePush())
    check("the id decides", (out[0].kind, out[0].match.posting["id"]), ("applied", b))


# ------------------------------------------- a created posting downstream

def _created(conn):
    out = inbox.process(conn, APP, [mail("Thank you for applying", "", sender="Globex <a@g.test>")],
                        push=FakePush(), extractor=FakeExtractor(
                            {"company": "Globex", "title": "Quant Research Intern",
                             "location": "Paris, France"}))
    return out[0].match.posting["id"]


def test_a_created_posting_is_never_emailed_as_new():
    conn = make_db()
    pid = _created(conn)
    conn.execute("UPDATE postings SET tier = 1, fit_score = 9, scored_at = ? WHERE id = ?",
                 (db.now(), pid))
    conn.commit()
    check("not in the daily carryover", [r["id"] for r in db.carryover(conn, 36)], [])
    check("not in the roundup", [r["id"] for r in db.roundup_candidates(conn, [1], 8)], [])
    check("not in the backlog", [r["id"] for r in db.surfaced(conn, unalerted_only=True)], [])
    conn.execute("UPDATE postings SET stated_deadline = ? WHERE id = ?",
                 ((datetime.now(timezone.utc) + timedelta(hours=10)).date().isoformat(), pid))
    conn.commit()
    check("no urgent deadline email", [r["id"] for r in db.urgent_by_deadline(conn, [1], 72)], [])
    conn.execute("UPDATE postings SET first_seen = '2026-01-01T00:00:00+00:00' WHERE id = ?", (pid,))
    conn.commit()
    check("no stale email, even nagging on age alone",
          [r["id"] for r in db.urgent_by_age(conn, [1], 7, needs_action=False)], [])


def test_a_created_posting_reaches_airtable():
    conn = make_db()
    pid = _created(conn)
    ids = [r["id"] for r in conn.execute(
        f"SELECT id FROM postings WHERE {airtable_sync.CANDIDATE_BASE}")]
    check("it is an Airtable candidate", pid in ids, True)


def test_re_applying_the_filter_never_kills_an_application():
    """A Paris role would die on location; an application is not the filter's to judge."""
    conn = make_db()
    pid = _created(conn)
    skipped = add(conn, title="Skipped Role Intern", applied_status="skipped")
    db.clear_verdicts(conn, [])
    check("the application keeps its verdict", row(conn, pid)["prefilter_verdict"], "surface")
    check("a skipped posting is re-judged", row(conn, skipped)["prefilter_verdict"], None)


def test_status_only_moves_forward():
    conn = make_db()
    a = add(conn, title="Data Science Intern", applied_status="interviewing",
            applied_at="2026-09-01T00:00:00+00:00")
    push = FakePush()
    out = inbox.process(conn, APP, [mail("Thank you for applying", "Data Science Intern at Acme")],
                        push=push)
    check("an interviewing posting is left alone", [o.kind for o in out], ["already"])
    check("its status is unchanged", status(conn, a),
          ("interviewing", "2026-09-01T00:00:00+00:00"))
    check("nothing was pushed", push.calls, [])


# -------------------------------------------------------- writes, in order

def test_applied_writes_airtable_then_sqlite_then_ledger():
    conn = make_db()
    a = add(conn, title="Data Science Intern", airtable_record_id="recA")
    push = FakePush()
    out = inbox.process(conn, APP, [mail("Thank you for applying", "Data Science Intern at Acme",
                                         mid="g1")], push=push)
    check("it applied", [o.kind for o in out], ["applied"])
    check("Airtable was asked first, only if blank", push.calls, [([a], True)])
    check("SQLite holds applied", status(conn, a)[0], "applied")
    check("the ledger holds the message", db.inbox_seen(conn, ["g1"]), {"g1"})


def test_applied_at_is_written_like_every_other_writer():
    """Rule 15: aware, to the second, +00:00, exactly the shape of db.now()."""
    stamp = inbox._stamp(1759673000000)
    check("the stamp has db.now()'s shape", len(stamp), len(db.now()))
    check("the stamp carries the offset", stamp.endswith("+00:00"), True)
    check("the stamp parses aware", delivery._parse(stamp).tzinfo is not None, True)
    conn = make_db()
    a = add(conn, title="Data Science Intern")
    m = mail("Thank you for applying", "Data Science Intern at Acme")
    inbox.process(conn, APP, [m], push=FakePush())
    check("applied_at is the email's time", status(conn, a)[1], m.received_at)


def test_a_failed_push_records_nothing_so_it_is_retried():
    conn = make_db()
    a = add(conn, title="Data Science Intern", airtable_record_id="recA")
    try:
        inbox.process(conn, APP, [
            mail("Thank you for applying", "Data Science Intern at Acme", mid="g1"),
            mail("Thank you for your application", "Job alert for you", mid="g2"),
        ], push=FakePush(fail=True))
        raised = False
    except RuntimeError:
        raised = True
    check("the failure reaches the caller", raised, True)
    check("the posting was not written", status(conn, a)[0], "not_applied")
    check("the applying message is not in the ledger", db.inbox_seen(conn, ["g1"]), set())
    check("mail that writes nothing was still recorded", db.inbox_seen(conn, ["g2"]), {"g2"})
    out = inbox.process(conn, APP, [
        mail("Thank you for applying", "Data Science Intern at Acme", mid="g1")], push=FakePush())
    check("the next run applies it", (status(conn, a)[0], [o.kind for o in out]),
          ("applied", ["applied"]))


def test_a_status_already_in_the_base_wins():
    conn = make_db()
    a = add(conn, title="Data Science Intern", airtable_record_id="recA")
    out = inbox.process(conn, APP, [mail("Thank you for applying", "Data Science Intern at Acme")],
                        push=FakePush(kept=[a]))
    check("reported as kept", [o.kind for o in out], ["kept"])
    check("SQLite left for the pull to fill", status(conn, a)[0], "not_applied")


def test_a_message_is_handled_once():
    conn = make_db()
    answer = {"company": "Acme", "title": "Brand New Intern"}
    inbox.process(conn, APP, [mail("Thank you for applying to Acme", "", mid="q1")],
                  push=FakePush(), extractor=FakeExtractor(answer))
    ext = FakeExtractor(dict(answer))
    again = inbox.process(conn, APP, [mail("Thank you for applying to Acme", "", mid="q1")],
                          push=FakePush(), extractor=ext)
    check("the second run does nothing", (again, ext.calls), ([], []))
    check("one ledger row, one posting",
          (conn.execute("SELECT COUNT(*) FROM inbox_messages").fetchone()[0],
           conn.execute("SELECT COUNT(*) FROM postings").fetchone()[0]), (1, 1))


def test_two_emails_for_one_posting_apply_once():
    conn = make_db()
    add(conn, title="Data Science Intern")
    out = inbox.process(conn, APP, [
        mail("Thank you for applying", "Data Science Intern at Acme"),
        mail("Thank you for applying", "Data Science Intern at Acme"),
    ], push=FakePush())
    check("one applies and one is already", sorted(o.kind for o in out), ["already", "applied"])


def test_a_dry_run_writes_nothing():
    conn = make_db()
    a = add(conn, title="Data Science Intern")
    push = FakePush()
    out = inbox.process(conn, APP, [mail("Thank you for applying", "Data Science Intern at Acme",
                                         mid="d1")], push=push, dry_run=True)
    check("it would apply", [o.kind for o in out], ["applied"])
    check("nothing pushed", push.calls, [])
    check("nothing written", status(conn, a)[0], "not_applied")
    check("nothing recorded", db.inbox_seen(conn, ["d1"]), set())


def test_the_body_is_read_only_when_needed():
    conn = make_db()
    add(conn, title="Data Science Intern")
    reads = []

    def get_body(mid):
        reads.append(mid)
        return "Data Science Intern"

    inbox.process(conn, APP, [mail("Thank you for applying", "Data Science Intern at Acme",
                                   mid="b1")], get_body=get_body, push=FakePush())
    check("a snippet that names the role needs no body", reads, [])
    out = inbox.process(conn, APP, [mail("Thank you for applying to Acme", "We received it",
                                         mid="b2")], get_body=get_body, push=FakePush())
    check("a company-only snippet reads the body", reads, ["b2"])
    check("and the body settles it", [o.kind for o in out], ["already"])


# ---------------------------------------------------------- the digest

def _with_config(fn):
    saved = inbox.load
    inbox.load = lambda path=None: CFG
    try:
        return fn()
    finally:
        inbox.load = saved


def test_a_stalled_reader_says_so():
    conn = make_db()
    check("never run reads as never", inbox.stale_since(conn, CFG), "never")
    db.set_state(conn, inbox.STATE_LAST_OK, "2026-10-01T08:10:00+00:00")
    later = datetime(2026, 10, 5, tzinfo=timezone.utc)
    check("four days quiet is stale", inbox.stale_since(conn, CFG, now=later), "2026-10-01")
    db.set_state(conn, inbox.STATE_LAST_OK, "2026-10-04")
    check("a bare date still parses (rule 15)", inbox.stale_since(conn, CFG, now=later), None)
    off = inbox.InboxConfig(application=inbox.Application(enabled=False))
    check("switched off says nothing", inbox.stale_since(conn, off), None)
    content = _with_config(lambda: delivery.action_content(conn))
    check("a stale reader alone makes the block worth showing",
          (content["inbox_stale"] is not None, delivery.has_actions(content)), (True, True))


def test_a_broken_inbox_never_stops_the_watcher():
    conn = make_db()
    saved = inbox.load

    def broken(path=None):
        raise ValueError("bad toml")

    inbox.load = broken
    try:
        content = delivery.action_content(conn)
        raised = None
    except Exception as exc:  # noqa: BLE001
        raised, content = exc, {}
    finally:
        inbox.load = saved
    check("action_content survives a broken inbox.toml", raised, None)
    check("and carries no inbox line", content.get("inbox_stale"), None)


def test_the_stale_line_renders_in_both_formats():
    conn = make_db()
    content = _with_config(lambda: delivery.action_content(conn))
    text = "\n".join(notify._action_lines(content, {}))
    check("text names the reader", "The Gmail reader has never run successfully" in text, True)
    check("html carries it", "Gmail reader" in emailhtml.render(text, "test"), True)


# ---------------------------------------------------------- the schedule

def test_the_step_is_optional_and_runs_first():
    sched = schedule.load()
    names = [s.name for s in sched.steps]
    step = next((s for s in sched.steps if s.module == "tools.inbox"), None)
    check("the inbox is a step", step is not None, True)
    check("it is not required", step and step.required, False)
    check("it runs before the watcher",
          step and names.index(step.name) < names.index("watcher"), True)


# ------------------------------------------------------------- rejections

def _from_inbox(conn) -> list[dict]:
    return [dict(r) for r in conn.execute(
        "SELECT * FROM postings WHERE source = 'inbox:applications'")]


def _rejection(company="Acme", title="", **kw) -> dict:
    return {"kind": "rejection", "company": company, "title": title, **kw}


def test_a_rejection_phrase_alone_writes_nothing():
    """No model, no rejection: the phrase only buys the question."""
    conn = make_db()
    a = add(conn, title="Data Science Intern", applied_status="applied",
            applied_at="2026-09-01T00:00:00+00:00")
    out = inbox.process(conn, APP, [mail("Acme Application Update",
                                         "we chose other candidates", mid="r1")],
                        push=FakePush(), extractor=None)
    check("deferred without a model", [o.kind for o in out], ["deferred"])
    check("still applied", status(conn, a)[0], "applied")
    check("and back next run", db.inbox_seen(conn, ["r1"]), set())


def test_an_acknowledgement_with_rejection_wording_still_applies():
    """Thanks for applying, and 'if you are not selected', in one acknowledgement."""
    conn = make_db()
    a = add(conn, title="Data Science Intern")
    ext = FakeExtractor({"kind": "confirmation", "company": "Acme",
                         "title": "Data Science Intern"})
    out = inbox.process(conn, APP, [mail("Thank you for applying",
                                         "Data Science Intern at Acme. If you are not "
                                         "selected we keep your resume")],
                        push=FakePush(), extractor=ext)
    check("the model was asked once", len(ext.calls), 1)
    check("it applied", ([o.kind for o in out], status(conn, a)[0]), (["applied"], "applied"))


def test_a_rejection_marks_the_one_open_application():
    conn = make_db()
    a = add(conn, title="Data Science Intern", applied_status="applied",
            applied_at="2026-09-01T00:00:00+00:00", airtable_record_id="recA")
    add(conn, title="Quant Intern")  # not applied, so not a candidate
    push = FakePush()
    out = inbox.process(conn, APP, [mail("Acme Application Update",
                                         "Unfortunately we have decided", mid="r1")],
                        push=push, extractor=FakeExtractor(_rejection()))
    check("it rejected", [o.kind for o in out], ["rejected"])
    check("the applied date is kept", status(conn, a),
          ("rejected", "2026-09-01T00:00:00+00:00"))
    check("Airtable asked first, never over an offer", push.calls, [([a], db.REJECTABLE)])
    check("offer is not replaceable", "offer" in db.REJECTABLE, False)
    kind = conn.execute("SELECT kind FROM inbox_messages WHERE message_id='r1'").fetchone()[0]
    check("the ledger says rejection", kind, "rejection")


def test_a_rejection_naming_the_role_picks_it():
    conn = make_db()
    a = add(conn, title="Data Science Intern", applied_status="applied",
            applied_at="2026-09-01T00:00:00+00:00")
    b = add(conn, title="Quant Research Intern", applied_status="applied",
            applied_at="2026-09-02T00:00:00+00:00")
    inbox.process(conn, APP, [mail("Acme Application Update", "Unfortunately")],
                  push=FakePush(), extractor=FakeExtractor(
                      _rejection(title="Summer 2027 Quant Research Intern, Equities")))
    check("the named role is rejected", status(conn, b)[0], "rejected")
    check("the other is untouched", status(conn, a)[0], "applied")


def test_two_open_applications_and_no_role_write_nothing():
    conn = make_db()
    a = add(conn, title="Data Science Intern", applied_status="applied",
            applied_at="2026-09-01T00:00:00+00:00")
    b = add(conn, title="Quant Research Intern", applied_status="interviewing",
            applied_at="2026-09-02T00:00:00+00:00")
    push = FakePush()
    out = inbox.process(conn, APP, [mail("Acme Application Update", "Unfortunately",
                                         mid="r1")],
                        push=push, extractor=FakeExtractor(_rejection()))
    check("unplaced", [o.kind for o in out], ["unplaced"])
    check("neither is touched", (status(conn, a)[0], status(conn, b)[0]),
          ("applied", "interviewing"))
    check("nothing created", conn.execute("SELECT COUNT(*) FROM postings").fetchone()[0], 2)
    check("nothing pushed", push.calls, [])
    check("recorded, so the call is not paid again", db.inbox_seen(conn, ["r1"]), {"r1"})


def test_a_rejection_with_no_application_creates_it_rejected():
    """He applied, the agent never knew, and the rejection says so."""
    conn = make_db()
    add(conn, company="Umbrella Labs", title="Trading Intern")  # never applied
    m = mail("Thank you for applying to Umbrella Labs", "Unfortunately we are unable",
             sender="Umbrella Labs Recruiting <jobs@recruiting.example.com>")
    out = inbox.process(conn, APP, [m], push=FakePush(),
                        extractor=FakeExtractor(_rejection(company="Umbrella Labs")))
    check("created", [o.kind for o in out], ["created"])
    r = _from_inbox(conn)
    check("one posting, rejected, dated by the email",
          [(x["company"], x["title"], x["applied_status"], x["applied_at"]) for x in r],
          [("Umbrella Labs", "Role not named in the rejection email", "rejected",
            m.received_at)])
    check("the role it never applied to is untouched",
          conn.execute("SELECT applied_status FROM postings WHERE title='Trading Intern'"
                       ).fetchone()[0], "not_applied")


def test_a_rejection_never_replaces_an_offer():
    conn = make_db()
    a = add(conn, title="Data Science Intern", applied_status="offer",
            applied_at="2026-09-01T00:00:00+00:00")
    push = FakePush()
    out = inbox.process(conn, APP, [mail("Acme Application Update", "Unfortunately")],
                        push=push, extractor=FakeExtractor(
                            _rejection(title="Data Science Intern")))
    check("already", [o.kind for o in out], ["already"])
    check("still an offer", status(conn, a)[0], "offer")
    check("nothing pushed", push.calls, [])


def test_the_base_wins_over_a_rejection():
    conn = make_db()
    a = add(conn, title="Data Science Intern", applied_status="applied",
            applied_at="2026-09-01T00:00:00+00:00", airtable_record_id="recA")
    out = inbox.process(conn, APP, [mail("Acme Application Update", "Unfortunately")],
                        push=FakePush(kept=[a]), extractor=FakeExtractor(_rejection()))
    check("kept", [o.kind for o in out], ["kept"])
    check("SQLite left for the pull", status(conn, a)[0], "applied")


def test_a_failed_push_records_no_rejection():
    conn = make_db()
    a = add(conn, title="Data Science Intern", applied_status="applied",
            applied_at="2026-09-01T00:00:00+00:00", airtable_record_id="recA")
    try:
        inbox.process(conn, APP, [mail("Acme Application Update", "Unfortunately", mid="r1")],
                      push=FakePush(fail=True), extractor=FakeExtractor(_rejection()))
        raised = False
    except RuntimeError:
        raised = True
    check("the failure reaches the caller", raised, True)
    check("still applied", status(conn, a)[0], "applied")
    check("not in the ledger, so retried", db.inbox_seen(conn, ["r1"]), set())


def test_a_rejection_after_its_acknowledgement_in_one_run():
    """A backlog run reads one role's acknowledgement and rejection together."""
    conn = make_db()
    ack = mail("Thank you for applying to Acme", "", mid="a1")
    rej = mail("Acme Application Update", "we chose other candidates", mid="r1")
    rej.received_at = "2026-10-20T09:00:00+00:00"
    out = inbox.process(conn, APP, [ack, rej], push=FakePush(), extractor=FakeExtractor(
        {"company": "Acme", "title": "Robotics Intern"},
        _rejection(title="Robotics Intern")))
    r = _from_inbox(conn)
    check("one posting, not two", len(r), 1)
    check("rejected, with the applied date of the acknowledgement",
          [(x["applied_status"], x["applied_at"]) for x in r],
          [("rejected", ack.received_at)])
    check("reported as created then rejected", sorted(o.kind for o in out),
          ["created", "rejected"])


def test_the_model_can_find_a_rejection_the_phrases_missed():
    conn = make_db()
    a = add(conn, title="Data Science Intern", applied_status="applied",
            applied_at="2026-09-01T00:00:00+00:00")
    out = inbox.process(conn, APP, [mail("Thank you for applying to Acme",
                                         "we have gone another direction")],
                        push=FakePush(), extractor=FakeExtractor(_rejection()))
    check("rejected", ([o.kind for o in out], status(conn, a)[0]), (["rejected"], "rejected"))


def test_a_rejection_reads_neither_as_writes_nothing():
    conn = make_db()
    a = add(conn, title="Data Science Intern", applied_status="applied",
            applied_at="2026-09-01T00:00:00+00:00")
    out = inbox.process(conn, APP, [mail("Acme event", "Unfortunately the talk moved")],
                        push=FakePush(), extractor=FakeExtractor({"kind": "other"}))
    check("not_ack", [o.kind for o in out], ["not_ack"])
    check("still applied", status(conn, a)[0], "applied")


def test_a_dry_run_rejects_nothing():
    conn = make_db()
    a = add(conn, title="Data Science Intern", applied_status="applied",
            applied_at="2026-09-01T00:00:00+00:00")
    push = FakePush()
    out = inbox.process(conn, APP, [mail("Acme Application Update", "Unfortunately",
                                         mid="r1")],
                        push=push, extractor=FakeExtractor(_rejection()), dry_run=True)
    check("it would reject", [o.kind for o in out], ["rejected"])
    check("but did not", (status(conn, a)[0], push.calls, db.inbox_seen(conn, ["r1"])),
          ("applied", [], set()))


def test_a_rejection_reads_the_body_for_its_role():
    conn = make_db()
    seen = []
    ext = FakeExtractor(_rejection())
    inner = ext.__call__
    inbox.process(conn, APP, [mail("Acme Application Update", "Unfortunately", mid="r1")],
                  get_body=lambda mid: "the Data Science Intern position",
                  push=FakePush(), extractor=lambda m: (seen.append(m.body), inner(m))[1])
    check("the model was shown the body", seen, ["the Data Science Intern position"])


def test_two_rejections_for_one_application_write_once():
    conn = make_db()
    a = add(conn, title="Data Science Intern", applied_status="applied",
            applied_at="2026-09-01T00:00:00+00:00", airtable_record_id="recA")
    push = FakePush()
    out = inbox.process(conn, APP, [mail("Acme Application Update", "Unfortunately"),
                                    mail("Acme Application Update", "Unfortunately")],
                        push=push, extractor=FakeExtractor(_rejection(), _rejection()))
    check("one rejected, one already", sorted(o.kind for o in out), ["already", "rejected"])
    check("one id pushed once", push.calls, [([a], db.REJECTABLE)])


class FakeAirtable:
    base_id = "appTEST"

    def __init__(self, live):
        self.live, self.updated = live, []

    def request(self, method, path):
        return {"fields": {"Applied status": v} if (v := self.live[path.rsplit("/", 1)[1]])
                else {}}

    def update_records(self, table, records):
        self.updated += [r["id"] for r in records]
        return len(records)


def test_the_real_push_never_overwrites_an_offer():
    """push_applied_status itself, against a fake client, for both callers."""
    client = FakeAirtable({"r1": "applied", "r2": "offer", "r3": None, "r4": "interviewing"})
    rows = [({"id": i, "airtable_record_id": f"r{i}"}, "rejected") for i in (1, 2, 3, 4)]
    out = airtable_sync.push_applied_status(rows, client=client, only_from=db.REJECTABLE)
    check("rejected replaces applied, blank and interviewing", sorted(client.updated),
          ["r1", "r3", "r4"])
    check("an offer is kept", out["kept"], [2])
    client = FakeAirtable({"r1": "applied", "r3": None})
    rows = [({"id": i, "airtable_record_id": f"r{i}"}, "applied") for i in (1, 3)]
    out = airtable_sync.push_applied_status(rows, client=client, only_if_blank=True)
    check("applied only fills a blank", (client.updated, out["kept"]), (["r3"], [1]))


def main() -> int:
    for fn in [
        test_only_gmail_readonly_is_accepted,
        test_no_token_is_not_a_failure,
        test_query_is_narrow_and_skips_own_mail,
        test_body_is_decoded_and_html_stripped,
        test_a_rejection_is_never_an_acknowledgement,
        test_company_names_match_on_word_boundaries,
        test_requisition_id_is_decisive,
        test_title_and_company_together_apply,
        test_a_title_without_its_company_is_never_enough,
        test_a_contained_title_is_not_a_second_role,
        test_a_one_word_title_is_not_evidence,
        test_one_city_of_a_location_group_is_written,
        test_two_roles_with_matching_titles_are_unsure,
        test_the_model_is_asked_only_when_the_free_match_fails,
        test_an_extracted_title_marks_the_existing_posting,
        test_a_resembling_title_creates_rather_than_guesses,
        test_an_unknown_posting_is_created_applied,
        test_a_company_already_held_keeps_its_spelling,
        test_a_confirmation_naming_no_role_still_records_it,
        test_the_model_saying_no_writes_nothing,
        test_no_model_means_wait_never_guess,
        test_the_call_cap_holds,
        test_two_emails_for_one_new_posting_create_one,
        test_company_names_meet_through_the_normalizer,
        test_an_application_brings_a_killed_posting_back,
        test_word_order_and_noise_do_not_make_a_new_role,
        test_a_logged_application_absorbs_its_own_confirmation,
        test_a_different_role_the_same_week_is_still_new,
        test_an_old_application_does_not_absorb_a_new_one,
        test_a_requisition_id_is_never_absorbed,
        test_a_created_posting_is_never_emailed_as_new,
        test_a_created_posting_reaches_airtable,
        test_re_applying_the_filter_never_kills_an_application,
        test_status_only_moves_forward,
        test_applied_writes_airtable_then_sqlite_then_ledger,
        test_applied_at_is_written_like_every_other_writer,
        test_a_failed_push_records_nothing_so_it_is_retried,
        test_a_status_already_in_the_base_wins,
        test_a_message_is_handled_once,
        test_two_emails_for_one_posting_apply_once,
        test_a_dry_run_writes_nothing,
        test_the_body_is_read_only_when_needed,
        test_a_stalled_reader_says_so,
        test_a_broken_inbox_never_stops_the_watcher,
        test_the_stale_line_renders_in_both_formats,
        test_the_step_is_optional_and_runs_first,
        test_a_rejection_phrase_alone_writes_nothing,
        test_an_acknowledgement_with_rejection_wording_still_applies,
        test_a_rejection_marks_the_one_open_application,
        test_a_rejection_naming_the_role_picks_it,
        test_two_open_applications_and_no_role_write_nothing,
        test_a_rejection_with_no_application_creates_it_rejected,
        test_a_rejection_never_replaces_an_offer,
        test_the_base_wins_over_a_rejection,
        test_a_failed_push_records_no_rejection,
        test_a_rejection_after_its_acknowledgement_in_one_run,
        test_the_model_can_find_a_rejection_the_phrases_missed,
        test_a_rejection_reads_neither_as_writes_nothing,
        test_a_dry_run_rejects_nothing,
        test_the_real_push_never_overwrites_an_offer,
        test_a_rejection_reads_the_body_for_its_role,
        test_two_rejections_for_one_application_write_once,
    ]:
        try:
            fn()
        except Exception as exc:
            results.append((False, fn.__name__, f"raised {type(exc).__name__}: {exc}"))

    failed = 0
    for ok, name, note in results:
        if ok:
            print(f"{PASS} {name}")
        else:
            failed += 1
            print(f"{FAIL} {name}: {note}")

    print(f"\n{len(results) - failed} of {len(results)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
