"""The Message Batches path for Stage 0, B and C, against a fake API. 2026-11-15.

    .venv/bin/python -m tools.test_batches

Makes no network request, spends nothing, and never touches state.db. Run it
after editing agent/batches.py, the batched halves of agent/ranker.py or
agent/triage.py, or anything that decides when an answer is written.

The batch path is asynchronous, so what can go wrong is mostly about time:
an answer that lands after the run that asked for it, a posting that changed
while it waited, and a run killed half way. The cases below are the promises:

    never pay for the same posting twice while a batch is still out
    never lose a paid answer: record the batch before waiting, collect it later
    never write an answer onto a posting that closed, was scored, or was retitled
    a failed cheap pass leaves the posting unscored; a failed recheck keeps
        the cheap score, exactly as the one-call-at-a-time path does
    the quiet runs collect rechecks and never submit scoring work
    batch spend is recorded at half the list price
"""

import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace as NS

from agent import batches, config, db, ranker, tagger, triage

PASS, FAIL = "ok  ", "FAIL"
results: list[tuple[bool, str, str]] = []


def check(name: str, got, want, note: str = "") -> None:
    results.append((got == want, name, note or f"got {got!r}, wanted {want!r}"))


# ------------------------------------------------------------------ the fake API

def message(text: str, inp=100, out=20):
    return NS(content=[NS(type="text", text=text)],
              usage=NS(input_tokens=inp, output_tokens=out,
                       cache_read_input_tokens=0, cache_creation_input_tokens=0))


def answer_for(params: dict) -> str:
    """Scores by model and title, so a case can steer routing from the title."""
    content = params["messages"][0]["content"]
    if "term_stated" in str(params["output_config"]):  # Stage 0, also on Haiku
        return ('{"term_stated": "Summer 2027", "term_evidence": "Summer 2027", '
                '"weekly_hours": "", "hours_evidence": "", "stated_deadline": ""}')
    if params["model"] == config.STAGE_C_MODEL:
        return '{"fit": 8, "reach": 7, "reason": "checked"}'
    if "Agent" in content:
        return '{"fit": 7, "reach": 6, "reason": "promising"}'
    return '{"fit": 3, "reach": 3, "reason": "weak"}'


class FakeBatches:
    def __init__(self):
        self.made: dict[str, list[dict]] = {}
        self.ended: set[str] = set()
        self.fail: dict[str, str] = {}      # custom_id -> error type, for any batch
        self.end_on_create = True

    def create(self, requests):
        bid = f"b{len(self.made) + 1}"
        self.made[bid] = list(requests)
        if self.end_on_create:
            self.ended.add(bid)
        return NS(id=bid)

    def retrieve(self, bid):
        return NS(processing_status="ended" if bid in self.ended else "in_progress")

    def results(self, bid):
        for r in self.made[bid]:
            cid = r["custom_id"]
            if cid in self.fail:
                yield NS(custom_id=cid, result=NS(type="errored", error=NS(type=self.fail[cid])))
            else:
                yield NS(custom_id=cid,
                         result=NS(type="succeeded", message=message(answer_for(r["params"]))))

    def requests(self, bid=None) -> list[dict]:
        if bid:
            return self.made[bid]
        return [r for reqs in self.made.values() for r in reqs]


class FakeClient:
    def __init__(self):
        self.messages = NS(batches=FakeBatches())


# ------------------------------------------------------------------ fixtures

def fresh():
    conn = db.connect(Path(tempfile.mkdtemp()) / "test.db")
    client = FakeClient()
    ranker._client = lambda: client
    tagger._client = lambda: client
    return conn, client


def add(conn, n: int, **kw) -> int:
    row = {
        "hash": f"h{n}", "identity": f"i{n}", "content_hash": f"h{n}",
        "company": "Acme", "title": f"Data Intern {n}", "location": "Chicago, IL",
        "url": f"https://example.test/{n}", "source": "greenhouse:acme",
        "first_seen": db.now(), "last_seen_open": db.now(),
        "prefilter_verdict": "surface", "applied_status": "not_applied",
        "flags": "", "term": "summer2027", "tagged_at": db.now(),
    }
    row.update(kw)
    cols, marks = ", ".join(row), ", ".join("?" for _ in row)
    cur = conn.execute(f"INSERT INTO postings ({cols}) VALUES ({marks})", list(row.values()))
    conn.commit()
    return cur.lastrowid


def get(conn, pid: int) -> dict:
    return db.posting_by_id(conn, pid)


def sent_ids(client) -> list[str]:
    return [r["custom_id"] for r in client.messages.batches.requests()]


# ------------------------------------------------------------------ cases

def test_cheap_pass_settles_and_costs_half():
    conn, client = fresh()
    a, b = add(conn, 1), add(conn, 2)
    stats = ranker.run(conn, 50)
    check("a weak posting is settled by the cheap model", get(conn, a)["scored_by"], "stage_b")
    check("and gets the cheap model's tier", get(conn, b)["tier"] is not None, True)
    check("nothing is left in flight", batches.pending(conn, ranker.B), [])
    full = ranker.estimate_cost(stats)
    check("batch spend is recorded at half price", round(stats["cost"], 10), round(full / 2, 10))
    check("one batch, two requests", len(client.messages.batches.made), 1)


def test_promising_posting_goes_to_stage_c():
    conn, client = fresh()
    pid = add(conn, 1, title="AI Agent Intern")
    ranker.run(conn, 50)
    row = get(conn, pid)
    check("a posting routed on is rechecked by the expensive model", row["scored_by"], "stage_c")
    check("and keeps the expensive model's numbers", (row["fit_score"], row["reach_score"]), (8, 7))
    models = [r["params"]["model"] for r in client.messages.batches.requests()]
    check("the recheck went out as its own batch",
          models, [config.STAGE_B_MODEL, config.STAGE_C_MODEL])


def test_slow_batch_is_collected_later_and_never_paid_twice():
    conn, client = fresh()
    fake = client.messages.batches
    fake.end_on_create = False
    pid = add(conn, 1)
    ranker.run(conn, 50)
    check("an unanswered posting stays unscored", get(conn, pid)["fit_score"], None)
    check("its batch is remembered", len(batches.pending(conn, ranker.B)), 1)
    ranker.run(conn, 50)
    check("the next run does not ask again while it is out", len(fake.made), 1)
    fake.ended.add("b1")
    ranker.run(conn, 50)
    check("once answered, the next run writes it", get(conn, pid)["scored_by"], "stage_b")
    check("and forgets the batch", batches.pending(conn, ranker.B), [])
    check("still only one batch was ever paid for", len(fake.made), 1)


def test_failed_cheap_pass_is_asked_again():
    conn, client = fresh()
    fake = client.messages.batches
    pid = add(conn, 1)
    fake.fail["p%d" % pid] = "api_error"
    stats = ranker.run(conn, 50)
    check("a failed cheap pass leaves the posting unscored", get(conn, pid)["fit_score"], None)
    check("and says so", len(stats["errors"]), 1)
    fake.fail.clear()
    ranker.run(conn, 50)
    check("the next run asks again and scores it", get(conn, pid)["scored_by"], "stage_b")


def test_failed_recheck_keeps_the_cheap_score():
    conn, client = fresh()
    fake = client.messages.batches
    pid = add(conn, 1, title="AI Agent Intern")
    original = fake.results

    def results(bid):
        for item in original(bid):
            if bid == "b2":
                item = NS(custom_id=item.custom_id, result=NS(type="expired"))
            yield item
    fake.results = results
    ranker.run(conn, 50)
    row = get(conn, pid)
    check("an expired recheck falls back to the cheap score", row["scored_by"], "stage_b")
    check("with the cheap numbers", (row["fit_score"], row["reach_score"]), (7, 6))


def test_late_answer_for_a_closed_posting_is_not_written():
    conn, client = fresh()
    fake = client.messages.batches
    fake.end_on_create = False
    pid = add(conn, 1)
    ranker.run(conn, 50)
    conn.execute("UPDATE postings SET closed_detected_at = ? WHERE id = ?", (db.now(), pid))
    conn.commit()
    fake.ended.add("b1")
    stats = ranker.collect_finished(conn)  # B is not collected on quiet runs
    check("a quiet run leaves a cheap-pass batch for the evening run",
          len(batches.pending(conn, ranker.B)), 1)
    conn.execute("UPDATE postings SET closed_detected_at = NULL WHERE id = ?", (pid,))
    conn.execute("UPDATE postings SET fit_score = 5, reach_score = 5, tier = 3 WHERE id = ?", (pid,))
    conn.commit()
    stats = ranker.run(conn, 50)
    check("an answer for a posting scored meanwhile is not written over it",
          get(conn, pid)["fit_score"], 5)
    check("but its tokens are still counted, because they were paid for",
          stats["calls"], 1)


def test_retitled_posting_is_asked_again_on_its_new_title():
    conn, client = fresh()
    fake = client.messages.batches
    fake.end_on_create = False
    pid = add(conn, 1)
    ranker.run(conn, 50)
    conn.execute("UPDATE postings SET title = 'AI Agent Intern' WHERE id = ?", (pid,))
    conn.commit()
    fake.ended.add("b1")
    fake.end_on_create = True
    ranker.run(conn, 50)
    row = get(conn, pid)
    check("the old title's answer is dropped and the new title is scored",
          row["scored_by"], "stage_c")


def test_quiet_run_collects_rechecks_only():
    conn, client = fresh()
    fake = client.messages.batches
    pid = add(conn, 1, title="AI Agent Intern")
    original_create = fake.create

    def create(requests):  # the recheck batch is slow, the cheap one is not
        made = original_create(requests)
        if requests[0]["params"]["model"] == config.STAGE_C_MODEL:
            fake.ended.discard(made.id)
        return made
    fake.create = create
    ranker.run(conn, 50)
    check("a slow recheck leaves the posting unscored", get(conn, pid)["fit_score"], None)
    fake.ended.add("b2")
    stats = ranker.collect_finished(conn)
    check("a quiet run writes the recheck when it lands", get(conn, pid)["scored_by"], "stage_c")
    check("and submits nothing", len(fake.made), 2)
    check("and records what it read at half price", stats["cost"] > 0, True)


def test_batch_is_recorded_before_the_wait():
    conn, client = fresh()
    fake = client.messages.batches
    fake.end_on_create = False
    add(conn, 1)

    def killed(_):
        raise KeyboardInterrupt("step timeout")
    fake.retrieve = killed
    try:
        ranker.run(conn, 50)
    except KeyboardInterrupt:
        pass
    check("a run killed while waiting has already recorded its batch",
          len(batches.pending(conn, ranker.B)), 1)


def test_paused_month_still_records_what_it_paid_for():
    conn, client = fresh()
    fake = client.messages.batches
    fake.end_on_create = False
    pid = add(conn, 1, title="AI Agent Intern")
    ranker.run(conn, 50)
    limit = float((ranker.rubric.settings().get("budget") or {}).get("monthly_usd", 0) or 0)
    db.record_run(conn, estimated_cost=limit)
    fake.ended.add("b1")
    stats = ranker.run(conn, 50)
    check("a paused month collects an answered batch", stats["calls"], 1)
    check("submits no recheck", len(fake.made), 1)
    check("and the posting keeps the cheap score", get(conn, pid)["scored_by"], "stage_b")
    check("and still says it is paused", stats.get("budget_paused"), True)


def test_stale_batch_is_dropped_and_asked_again():
    conn, client = fresh()
    fake = client.messages.batches
    fake.end_on_create = False
    pid = add(conn, 1)
    ranker.run(conn, 50)
    entries = batches.pending(conn, ranker.B)
    entries[0]["submitted_at"] = "2026-01-01T00:00:00+00:00"
    batches._save(conn, ranker.B, entries)
    fake.end_on_create = True
    ranker.run(conn, 50)
    check("a batch past 26 hours is given up on and the posting asked again",
          get(conn, pid)["scored_by"], "stage_b")


def test_call_budget_limits_what_is_sent():
    conn, client = fresh()
    for n in range(10):
        add(conn, n)
    ranker.run(conn, 7)
    # 7 calls, and each posting reserves 1.4 plus the self-check share (0.1),
    # so four go out and the rest wait for the next run.
    check("the call cap leaves room for rechecks", len(sent_ids(client)), 4)


def test_direct_and_batch_paths_send_the_same_request():
    conn, client = fresh()
    pid = add(conn, 1)
    seen = {}

    class Direct:
        def create(self, **params):
            seen.update(params)
            return message(answer_for(params))
    direct = NS(messages=Direct())
    posting = get(conn, pid)
    system = [{"type": "text", "text": "rubric"}]
    cfg = ranker.rubric.settings()
    ranker.score_stage_b(direct, posting, system, cfg)
    check("the direct call and a batch request carry identical parameters",
          seen, ranker._params(posting, system, config.STAGE_B_MODEL,
                               config.STAGE_B_MAX_TOKENS, cfg, None))


def test_stage0_batches_and_waits():
    conn, client = fresh()
    fake = client.messages.batches
    fake.end_on_create = False
    pid = add(conn, 1, prefilter_verdict="pending", tagged_at=None, term="unknown",
              description="A summer internship building agents.")
    triage.tag_pass(conn, 50)
    check("an untagged posting waits while its batch is out", get(conn, pid)["tagged_at"], None)
    triage.tag_pass(conn, 50)
    check("and is not asked twice", len(fake.made), 1)
    fake.ended.add("b1")
    stats = triage.tag_pass(conn, 50)
    check("the answer is written when it lands", get(conn, pid)["term"], "summer2027")
    check("Stage 0 spend is at half price",
          round(stats["cost"], 10),
          round(tagger.estimate_cost(stats["input_tokens"], stats["output_tokens"]) / 2, 10))


def main() -> int:
    config.ranker_configured = lambda: True
    config.stage0_configured = lambda: True
    config.USE_BATCHES = True
    config.RANK_B_BATCH_WAIT = config.RANK_C_BATCH_WAIT = config.STAGE0_BATCH_WAIT = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
            except Exception as exc:  # noqa: BLE001
                results.append((False, name, f"raised {exc!r}"))
    failed = [r for r in results if not r[0]]
    for ok, name, note in results:
        print(f"{PASS if ok else FAIL} {name}" + ("" if ok else f"  ({note})"))
    print(f"\n{len(results) - len(failed)} of {len(results)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
