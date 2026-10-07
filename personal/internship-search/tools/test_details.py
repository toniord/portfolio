"""Descriptions for feed postings, against fake boards. 2026-10-03.

    .venv/bin/python -m tools.test_details

Makes no network request, spends nothing, and never touches state.db. Run it
after editing agent/triage.feed_detail_pass, agent/fetchers.locate_job or
anything that fetches a single job's description.

Built after a Walleye Capital internship about building AI agents sat in tier 4
because the ranker scored it on its title. The cases below are mostly about
what the pass must never do while fixing that:

    never treat a board that dropped the job as the posting closing
    never clear an alert stamp or an override when it sends a score back
    never take a surfaced posting out of the digest just because it gained text
    never spend its budget on links nothing can fetch, or on the same job twice
    never read a link by company name, only by its shape
"""

import sqlite3
import sys
import tempfile
from pathlib import Path

from agent import config, db, fetchers, prefilter, triage

PASS, FAIL = "ok  ", "FAIL"
results: list[tuple[bool, str, str]] = []

# A failing request is retried with a sleep. The fake fails instantly and on
# purpose, so the retry only slows the suite down.
config.HTTP_RETRIES = 0


def check(name: str, got, want, note: str = "") -> None:
    results.append((got == want, name, note or f"got {got!r}, wanted {want!r}"))


GH = "https://job-boards.greenhouse.io/acme/jobs/{}"
LEVER_ID = "ab7dd1c4-7196-4cae-8fbd-cddec993b9b8"
ASHBY_A = "85bad69a-ac4e-4090-910f-04d321001f73"
ASHBY_B = "1871fdc6-6eba-4397-8725-c4e5c036ab54"

AGENTS = ("&lt;p&gt;Build AI-native internal tools and custom agents for the "
          "investment team.&lt;/p&gt;")
CLEARED = "<p>Candidates must have an active security clearance.</p>"


class FakeResponse:
    def __init__(self, status, payload=None):
        self.status_code, self.payload = status, payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self.payload


class FakeBoards:
    """Greenhouse, Lever and Ashby, answering the way the real APIs do.

    `pages` maps a request URL to a payload, an int status, or an exception.
    Anything not listed is a 404, which is what a board says about a job it
    no longer lists.
    """

    def __init__(self, pages):
        self.pages, self.calls = pages, []

    def get(self, url):
        self.calls.append(url)
        page = self.pages.get(url, 404)
        if isinstance(page, Exception):
            raise page
        if isinstance(page, int):
            return FakeResponse(page)
        return FakeResponse(200, page)


def gh_api(job_id):
    return f"https://boards-api.greenhouse.io/v1/boards/acme/jobs/{job_id}"


ASHBY_API = ("https://api.ashbyhq.com/posting-api/job-board/rocket"
             "?includeCompensation=false")


def make_db() -> sqlite3.Connection:
    return db.connect(Path(tempfile.mkdtemp()) / "test.db")


_n = 0


def add(conn, url, external_id="", verdict="surface", tier=4, **cols) -> int:
    """One open feed posting, scored blind unless told otherwise."""
    global _n
    _n += 1
    row = {
        "hash": f"h{_n}", "identity": f"feed:test|{_n}", "content_hash": f"h{_n}",
        "company": "Acme", "title": f"Special Projects Intern {_n}",
        "location": "New York, NY", "url": url, "source": "feed:test",
        "ats_platform": "feed", "external_id": external_id or f"x{_n}",
        "description": "", "first_seen": f"2026-09-{_n:02d}T00:00:00+00:00",
        "last_seen_open": "2026-10-01T00:00:00+00:00",
        "prefilter_verdict": verdict, "prefilter_reason": "term summer_2027",
        "tagged_at": "2026-09-01", "term": "summer_2027", "flags": "",
        "fit_score": 2 if tier else None, "reach_score": 3 if tier else None,
        "tier": tier, "reason": "no AI or ML component mentioned" if tier else None,
        "scored_at": "2026-09-02" if tier else None,
    }
    row.update(cols)
    names = ", ".join(row)
    conn.execute(f"INSERT INTO postings ({names}) VALUES ({', '.join('?' for _ in row)})",
                 list(row.values()))
    conn.commit()
    return conn.execute("SELECT id FROM postings WHERE hash = ?", (row["hash"],)).fetchone()[0]


def get(conn, pid) -> dict:
    return dict(conn.execute("SELECT * FROM postings WHERE id = ?", (pid,)).fetchone())


# ---------------------------------------------------------------- the locator


def test_links_are_read_by_shape():
    cases = [
        ("https://job-boards.greenhouse.io/walleyecapital-external-students/jobs/4716166006", "",
         ("greenhouse", "walleyecapital-external-students", "4716166006")),
        ("https://boards.greenhouse.io/acme/jobs/123?gh_src=x", "", ("greenhouse", "acme", "123")),
        ("https://boards.greenhouse.io/embed/job_app?for=acme&token=123", "",
         ("greenhouse", "acme", "123")),
        (f"https://jobs.lever.co/CesiumAstro/{LEVER_ID}/apply", "",
         ("lever", "CesiumAstro", LEVER_ID)),
        (f"https://jobs.ashbyhq.com/rocket/{ASHBY_A.upper()}/application?embed=true", "",
         ("ashby", "rocket", ASHBY_A)),
        ("https://marmon.wd501.myworkdayjobs.com/Marmon_Internships/job/Milwaukee-WI/Data-Intern_JR37", "",
         ("workday", "marmon.wd501.myworkdayjobs.com/Marmon_Internships", "/job/Milwaukee-WI/Data-Intern_JR37")),
        ("https://acme.wd1.myworkdayjobs.com/en-US/Campus/job/Boston/Quant-Intern_R15", "",
         ("workday", "acme.wd1.myworkdayjobs.com/Campus", "/job/Boston/Quant-Intern_R15")),
        ("https://egug.fa.us2.oraclecloud.com/hcmUI/CandidateExperience/en/sites/CX_1/job/26013191", "",
         ("oracle", "egug.fa.us2.oraclecloud.com/CX_1", "26013191")),
        ("https://jobs.smartrecruiters.com/BoschGroup/744000145507908-ai-security-intern", "",
         ("smartrecruiters", "BoschGroup", "744000145507908")),
        # A company's own careers page wrapping a board: the link names nothing,
        # the feed's id still does.
        ("https://www.acme.com/careers?gh_jid=55", "greenhouse:acme:55", ("greenhouse", "acme", "55")),
    ]
    for url, ext, want in cases:
        ref = fetchers.locate_job(url, ext)
        check(f"locates {url[:60]}", ref and tuple(ref)[:3], want)


def test_unreadable_links_are_left_alone():
    for url, ext in [
        ("https://www.tesla.com/careers/search/job/intern-123", ""),
        ("https://job-boards.greenhouse.io/acme", ""),           # a board, not a job
        ("https://jobs.lever.co/acme/not-a-uuid", ""),
        ("not a url at all", "greenhouse:acme:notdigits"),
        ("https://acme.wd1.myworkdayjobs.com/en-US/job/Boston/Intern_R1", ""),  # locale, no site
        ("https://acme.wd1.myworkdayjobs.com/en-US/Careers/details/Intern_R1?q=R1", ""),
        ("https://acme.wd1.myworkdayjobs.com/Careers", ""),
        ("https://acme.fa.us2.oraclecloud.com/hcmUI/CandidateExperience/en/sites/CX_1/jobs", ""),
        ("https://jobs.smartrecruiters.com/Acme", ""),
        ("", ""),
    ]:
        check(f"ignores {url or '(empty)'}", fetchers.locate_job(url, ext), None)


def test_escaped_greenhouse_markup_becomes_text():
    check("greenhouse's escaped html is stripped, not re-inserted",
          fetchers._strip_html(AGENTS),
          "Build AI-native internal tools and custom agents for the investment team.")
    check("ordinary html still works", fetchers._strip_html("<p>a &amp; b</p>"), "a & b")


# --------------------------------------------------------------- the pass


def test_text_arrives_and_the_score_goes_back():
    conn = make_db()
    pid = add(conn, GH.format(1), alerted_at="2026-09-03T00:00:00+00:00",
              label="maybe", applied_status="not_applied")
    fake = FakeBoards({gh_api(1): {"content": AGENTS}})
    stats = triage.feed_detail_pass(conn, max_fetches=10, client=fake)
    row = get(conn, pid)
    check("description stored as text", "custom agents" in row["description"], True)
    check("score cleared so the ranker judges it again",
          (row["fit_score"], row["tier"], row["scored_at"]), (None, None, None))
    check("still surfaced, so it stays in front of the ranker",
          row["prefilter_verdict"], "surface")
    check("timing reason kept", row["prefilter_reason"], "term summer_2027")
    check("alert stamp untouched (rule 10)", row["alerted_at"], "2026-09-03T00:00:00+00:00")
    check("label untouched", row["label"], "maybe")
    check("counted", (stats["fetched"], stats["rescored"]), (1, 1))
    check("and the ranker's queue now holds it",
          [p["id"] for p in db.unscored(conn)], [pid])


def test_an_override_keeps_its_score():
    conn = make_db()
    pid = add(conn, GH.format(2), fit_override=5)
    triage.feed_detail_pass(conn, max_fetches=10,
                            client=FakeBoards({gh_api(2): {"content": AGENTS}}))
    row = get(conn, pid)
    check("text still stored", bool(row["description"]), True)
    check("an overridden posting is not re-scored", row["fit_score"], 2)


def test_a_dropped_job_is_not_a_closure():
    conn = make_db()
    pid = add(conn, GH.format(3))
    stats = triage.feed_detail_pass(conn, max_fetches=10, client=FakeBoards({}))
    row = get(conn, pid)
    check("not closed", row["closed_detected_at"], None)
    check("no miss counted", row["consecutive_misses"], 0)
    check("score kept, nothing new to judge", row["fit_score"], 2)
    check("marked so it is not asked again", bool(row["detail_unavailable_at"]), True)
    check("counted as unavailable, not as an error",
          (stats["unavailable"], len(stats["errors"])), (1, 0))
    fake = FakeBoards({})
    triage.feed_detail_pass(conn, max_fetches=10, client=fake)
    check("and the next run does not ask", fake.calls, [])


def test_a_network_error_is_asked_again():
    conn = make_db()
    pid = add(conn, GH.format(4))
    stats = triage.feed_detail_pass(
        conn, max_fetches=10, client=FakeBoards({gh_api(4): ConnectionError("dns")}))
    row = get(conn, pid)
    check("an error is reported", len(stats["errors"]), 1)
    check("and not marked unavailable", row["detail_unavailable_at"], None)
    check("still queued", stats["remaining"], 1)
    check("score kept", row["fit_score"], 2)


def test_a_server_error_is_not_a_dropped_job():
    conn = make_db()
    pid = add(conn, GH.format(5))
    triage.feed_detail_pass(conn, max_fetches=10, client=FakeBoards({gh_api(5): 503}))
    check("a 503 leaves it queued", get(conn, pid)["detail_unavailable_at"], None)


def test_text_can_kill_but_never_revive():
    conn = make_db()
    surfaced = add(conn, GH.format(6))
    killed = add(conn, GH.format(7), verdict="killed", tier=None)
    stats = triage.feed_detail_pass(conn, max_fetches=10, client=FakeBoards({
        gh_api(6): {"content": CLEARED}, gh_api(7): {"content": AGENTS}}))
    check("an existing-clearance requirement kills it",
          get(conn, surfaced)["prefilter_verdict"], "killed")
    check("a killed posting is never fetched or revived",
          (get(conn, killed)["prefilter_verdict"], get(conn, killed)["description"]),
          ("killed", ""))
    check("killed, not sent to the ranker", (stats["killed"], stats["rescored"]), (1, 0))


def test_a_pending_posting_goes_first_and_stays_pending():
    conn = make_db()
    old_surfaced = add(conn, GH.format(8))
    new_pending = add(conn, GH.format(9), verdict="pending", tier=None)
    fake = FakeBoards({gh_api(8): {"content": AGENTS}, gh_api(9): {"content": AGENTS}})
    triage.feed_detail_pass(conn, max_fetches=1, client=fake)
    check("a new posting is not queued behind the backlog", fake.calls, [gh_api(9)])
    check("pending stays pending for the timing pass",
          get(conn, new_pending)["prefilter_verdict"], "pending")
    check("the backlog posting waits for the next run",
          get(conn, old_surfaced)["description"], "")


def test_the_budget_counts_requests_on_readable_links_only():
    conn = make_db()
    for _ in range(3):
        add(conn, "https://www.tesla.com/careers/job/1")
    for i in (10, 11, 12):
        add(conn, GH.format(i))
    fake = FakeBoards({gh_api(i): {"content": AGENTS} for i in (10, 11, 12)})
    stats = triage.feed_detail_pass(conn, max_fetches=2, client=fake)
    check("two requests, both on fetchable links", len(fake.calls), 2)
    check("one left for next run, unreadable ones not counted", stats["remaining"], 1)


def test_two_feeds_one_job_one_request():
    conn = make_db()
    a = add(conn, GH.format(13), source="feed:simplify")
    b = add(conn, "https://www.acme.com/careers", external_id="greenhouse:acme:13",
            source="feed:zshah")
    fake = FakeBoards({gh_api(13): {"content": AGENTS}})
    triage.feed_detail_pass(conn, max_fetches=1, client=fake)
    check("asked once", len(fake.calls), 1)
    check("both rows got it", (bool(get(conn, a)["description"]),
                               bool(get(conn, b)["description"])), (True, True))


def test_ashby_board_is_read_once():
    conn = make_db()
    a = add(conn, f"https://jobs.ashbyhq.com/rocket/{ASHBY_A}")
    b = add(conn, f"https://jobs.ashbyhq.com/rocket/{ASHBY_B}")
    gone = add(conn, "https://jobs.ashbyhq.com/rocket/00000000-0000-0000-0000-000000000000")
    fake = FakeBoards({ASHBY_API: {"jobs": [
        {"id": ASHBY_A, "descriptionPlain": "Agents for the desk."},
        {"id": ASHBY_B, "descriptionHtml": "<p>Robotics.</p>"},
    ]}})
    triage.feed_detail_pass(conn, max_fetches=10, client=fake)
    check("one request for the whole board", fake.calls, [ASHBY_API])
    check("each posting answered from it",
          (get(conn, a)["description"], get(conn, b)["description"]),
          ("Agents for the desk.", "Robotics."))
    check("a job missing from the board is unavailable, not closed",
          (bool(get(conn, gone)["detail_unavailable_at"]), get(conn, gone)["closed_detected_at"]),
          (True, None))


def test_lever_and_its_eu_host():
    conn = make_db()
    us = add(conn, f"https://jobs.lever.co/acme/{LEVER_ID}")
    eu = add(conn, f"https://jobs.eu.lever.co/acme/{LEVER_ID}/apply")
    fake = FakeBoards({
        f"https://api.lever.co/v0/postings/acme/{LEVER_ID}": {"descriptionPlain": "US text"},
        f"https://api.eu.lever.co/v0/postings/acme/{LEVER_ID}": {"descriptionPlain": "EU text"},
    })
    triage.feed_detail_pass(conn, max_fetches=10, client=fake)
    check("each region asks its own API",
          (get(conn, us)["description"], get(conn, eu)["description"]), ("US text", "EU text"))


def test_workday_links_ask_the_tenant_detail_api():
    conn = make_db()
    live = add(conn, "https://acme.wd1.myworkdayjobs.com/en-US/Campus/job/Boston/Quant-Intern_R15")
    gone = add(conn, "https://acme.wd1.myworkdayjobs.com/Campus/job/Boston/Old-Intern_R9")
    api = "https://acme.wd1.myworkdayjobs.com/wday/cxs/acme/Campus/job/Boston/"
    fake = FakeBoards({api + "Quant-Intern_R15": {"jobPostingInfo": {
        "jobDescription": "<p>Research tooling and agents.</p>"}}})
    stats = triage.feed_detail_pass(conn, max_fetches=10, client=fake)
    check("the locale is dropped and the tenant read from the host",
          fake.calls[0], api + "Quant-Intern_R15")
    check("text stored", get(conn, live)["description"], "Research tooling and agents.")
    check("and the score sent back", get(conn, live)["fit_score"], None)
    check("a 404 from the tenant is unavailable, not closed",
          (bool(get(conn, gone)["detail_unavailable_at"]), get(conn, gone)["closed_detected_at"]),
          (True, None))
    check("counted", (stats["fetched"], stats["unavailable"]), (1, 1))

    # A taken-down requisition answers 403 or 422 on Workday, never 404.
    pulled = add(conn, "https://acme.wd1.myworkdayjobs.com/Campus/job/Boston/Pulled-Intern_R8")
    odd = add(conn, "https://acme.wd1.myworkdayjobs.com/Campus/job/Boston/Odd-Intern_R7")
    triage.feed_detail_pass(conn, max_fetches=10, client=FakeBoards({
        api + "Pulled-Intern_R8": 403, api + "Odd-Intern_R7": 422}))
    check("Workday 403 and 422 mean taken down, marked not closed",
          [(bool(get(conn, i)["detail_unavailable_at"]), get(conn, i)["closed_detected_at"])
           for i in (pulled, odd)], [(True, None), (True, None)])


def test_a_403_elsewhere_is_retried():
    # Only Workday's detail endpoint means "gone" by 403. On Greenhouse it is
    # an error and the posting is asked again.
    conn = make_db()
    pid = add(conn, GH.format(15))
    triage.feed_detail_pass(conn, max_fetches=10, client=FakeBoards({gh_api(15): 403}))
    check("a Greenhouse 403 leaves it queued", get(conn, pid)["detail_unavailable_at"], None)


def test_oracle_and_smartrecruiters():
    conn = make_db()
    ora = add(conn, "https://acme.fa.us2.oraclecloud.com/hcmUI/CandidateExperience/en/sites/CX_1/job/101")
    ora_gone = add(conn, "https://acme.fa.us2.oraclecloud.com/hcmUI/CandidateExperience/en/sites/CX_1/job/102")
    sr = add(conn, "https://jobs.smartrecruiters.com/Acme/744000001")
    oapi = ("https://acme.fa.us2.oraclecloud.com/hcmRestApi/resources/latest/"
            "recruitingCEJobRequisitionDetails?expand=all&onlyData=true&finder=ById;Id=\"{}\",siteNumber=CX_1")
    fake = FakeBoards({
        oapi.format(101): {"items": [{"ExternalDescriptionStr": "<p>Agents.</p>",
                                      "ExternalQualificationsStr": "<p>Python.</p>",
                                      "CorporateDescriptionStr": "<p>Boilerplate.</p>"}]},
        oapi.format(102): {"items": [], "count": 0},
        "https://api.smartrecruiters.com/v1/companies/Acme/postings/744000001": {"jobAd": {"sections": {
            "companyDescription": {"text": "We are Acme."},
            "jobDescription": {"text": "<p>Build models.</p>"}}}},
    })
    triage.feed_detail_pass(conn, max_fetches=10, client=fake)
    check("oracle: the job's own sections, not the boilerplate",
          get(conn, ora)["description"], "Agents. Python.")
    check("oracle: an empty answer is taken down, not closed",
          (bool(get(conn, ora_gone)["detail_unavailable_at"]), get(conn, ora_gone)["closed_detected_at"]),
          (True, None))
    check("smartrecruiters: the job first, the company last",
          get(conn, sr)["description"], "Build models. We are Acme.")


def test_company_board_postings_are_not_this_pass():
    conn = make_db()
    pid = add(conn, GH.format(14), ats_platform="greenhouse", source="greenhouse:acme")
    fake = FakeBoards({gh_api(14): {"content": AGENTS}})
    triage.feed_detail_pass(conn, max_fetches=10, client=fake)
    check("a company board posting is the watcher's, not fetched here", fake.calls, [])
    check("untouched", get(conn, pid)["fit_score"], 2)


def test_the_shipped_cap_is_in_data():
    from agent import sources
    cap = sources.load_feed_settings().get("max_details_per_run")
    check("sources/feeds.toml sets max_details_per_run", isinstance(cap, int) and cap > 0, True)


def main() -> int:
    for fn in [
        test_links_are_read_by_shape,
        test_unreadable_links_are_left_alone,
        test_escaped_greenhouse_markup_becomes_text,
        test_text_arrives_and_the_score_goes_back,
        test_an_override_keeps_its_score,
        test_a_dropped_job_is_not_a_closure,
        test_a_network_error_is_asked_again,
        test_a_server_error_is_not_a_dropped_job,
        test_text_can_kill_but_never_revive,
        test_a_pending_posting_goes_first_and_stays_pending,
        test_the_budget_counts_requests_on_readable_links_only,
        test_two_feeds_one_job_one_request,
        test_ashby_board_is_read_once,
        test_lever_and_its_eu_host,
        test_workday_links_ask_the_tenant_detail_api,
        test_a_403_elsewhere_is_retried,
        test_oracle_and_smartrecruiters,
        test_company_board_postings_are_not_this_pass,
        test_the_shipped_cap_is_in_data,
    ]:
        try:
            fn()
        except Exception as exc:
            # A case that raises is a failure, not the end of the run.
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
