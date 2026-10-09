"""Read application emails from Gmail and set Applied or Rejected. Milestone 7.5.

    .venv/bin/python -m tools.inbox --authorize          # once, in a browser
    .venv/bin/python -m tools.inbox --dry-run --days 60  # read, write nothing
    .venv/bin/python -m tools.inbox --days 60 --max-messages 200   # a backlog
    .venv/bin/python -m tools.inbox                      # what the schedule runs

The first step of every scheduled run, and not a required one. A Gmail outage,
a revoked token or a typo in sources/inbox.toml is logged and stepped over, and
the watcher runs exactly as it would have. Gmail is a convenience on top of the
spine and must never be able to stop it (CLAUDE.md rules 11 and 12).

Exit codes, because the scheduled run reads them. 0 when the reader did its
job, and also when it is switched off or not connected yet, because a source
that is not set up has not failed. 1 when it was set up and could not finish.
A failure here is recorded in the run log and nowhere else, which is why the
digest says so once the reader has gone `stale_after_days` without success.

Cost. Gmail API calls are free. A confirmation the free matching cannot place,
and every possible rejection, costs one Haiku call, about $0.0015, capped at `max_extractions` a run and
recorded in the `spend` table so the monthly figure in rubric.md counts it. It
is not paused by that ceiling, which governs ranking: a confirmation left
unread for the rest of a month would fall out of the 7 day search for good.
Airtable (CLAUDE.md rule 8) costs one read and a tenth of a write per
application marked on an existing row, and nothing on a run that marks none. A
created posting costs nothing here; the evening sync creates its record.
"""

from __future__ import annotations

import argparse
import sys

from agent import airtable_sync, config, db, inbox, tagger

VERBS = {
    "applied": "SET APPLIED",
    "rejected": "SET REJECTED",
    "created": "CREATED",
    "unplaced": "unplaced",
    "already": "already",
    "kept": "kept (base already has a status)",
    "deferred": "deferred",
    "not_ack": "not an acknowledgement",
    "ignored": "ignored",
}


def _describe(o: inbox.Outcome) -> list[str]:
    m = o.match
    verb = VERBS.get(o.kind, o.kind)
    if o.topic == "rejection" and o.kind != "rejected":
        verb = f"{verb} (rejection)"
    lines = [f"  {verb:12} {o.mail.received_at[:10]}  {o.mail.subject[:70]}",
             f"               from {o.mail.sender[:70]}   id {o.mail.id}"]
    if m and m.posting:
        p = m.posting
        lines.append(f"               -> posting {p['id']}  {p['company']}: {p['title']}"
                     f"  ({o.reason})")
    elif m and m.new:
        n = m.new
        where = f", {n['location']}" if n["location"] else ""
        lines.append(f"               -> new posting  {n['company']}: {n['title']}{where}"
                     f"  ({o.reason})")
    elif o.reason:
        lines.append(f"               ({o.reason})")
    return lines


def _extractor(spend_log: list):
    """The paid call, or None when there is no API key (messages then wait)."""
    try:
        client = tagger._client()
    except tagger.TaggerUnavailable as exc:
        spend_log.append(f"no model call possible: {exc}")
        return None
    return lambda mail: inbox.extract(client, mail)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--authorize", action="store_true", help="browser consent, once")
    ap.add_argument("--dry-run", action="store_true",
                    help="read and match, write nothing. Works while [application] is disabled")
    ap.add_argument("--days", type=int, help="override lookback_days")
    ap.add_argument("--max-messages", type=int,
                    help="override max_messages, for a backlog run over many weeks")
    args = ap.parse_args(argv)

    if args.authorize:
        try:
            path = inbox.authorize()
        except inbox.InboxError as exc:
            print(f"FAILED: {exc}", file=sys.stderr)
            return 1
        print(f"Saved a gmail.readonly token to {path.name}.")
        return 0

    conn = db.connect()
    try:
        cfg = inbox.load()
    except (OSError, ValueError) as exc:
        print(f"inbox: could not read sources/inbox.toml: {exc}", file=sys.stderr)
        return 1
    app = cfg.application
    if not app.enabled and not args.dry_run:
        print("inbox: [application] is disabled in sources/inbox.toml, nothing to do.")
        return 0

    days = args.days or cfg.lookback_days
    try:
        http = inbox.session()
        query = inbox.build_query(app, days, (config.SMTP_USER or "",))
        limit = args.max_messages or cfg.max_messages
        ids, capped = inbox.list_ids(http, query, limit)
        new = sorted(set(ids) - db.inbox_seen(conn, ids))
        mails = [inbox.get_mail(http, mid) for mid in new]
        mails.sort(key=lambda m: m.received_at)
        notes: list[str] = []
        spend = inbox.Spend()
        try:
            outcomes = inbox.process(
                conn, app, mails,
                get_body=lambda mid: inbox.get_body(http, mid),
                push=airtable_sync.push_applied_status if config.airtable_configured() else None,
                extractor=_extractor(notes),
                dry_run=args.dry_run,
                spend=spend,
            )
        finally:
            # Recorded even when the run fails part way, and on a dry run too:
            # a dry run that reads an email with the model has spent the money.
            if spend.calls:
                db.record_spend(conn, "inbox", spend.calls,
                                tagger.estimate_cost(spend.input_tokens, spend.output_tokens))
    except inbox.NotConnected as exc:
        print(f"inbox: not connected ({exc}), skipped.")
        return 0
    except Exception as exc:  # noqa: BLE001 - an optional step reports and exits 1
        print(f"inbox: FAILED: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    if not args.dry_run:
        inbox.mark_ok(conn)
    for note in notes:
        print(f"inbox: {note}")
    if spend.calls:
        cost = tagger.estimate_cost(spend.input_tokens, spend.output_tokens)
        print(f"inbox: {spend.calls} model call(s), about ${cost:.4f}.")

    counts: dict[str, int] = {}
    for o in outcomes:
        counts[o.kind] = counts.get(o.kind, 0) + 1
    summary = ", ".join(f"{n} {k}" for k, n in sorted(counts.items())) or "nothing new"
    head = "DRY RUN, nothing written. " if args.dry_run else ""
    print(f"inbox: {head}{len(ids)} matched the search in {days} days, "
          f"{len(mails)} new: {summary}.")
    if capped:
        print(f"inbox: the search hit max_messages ({limit}). A phrase in "
              "sources/inbox.toml is probably too broad.")
    loud = ("applied", "rejected", "created", "kept", "unplaced", "deferred")
    order = ["applied", "rejected", "created", "kept", "unplaced", "deferred", "already",
             "not_ack", "ignored"]
    for o in sorted(outcomes, key=lambda o: order.index(o.kind)):
        if args.dry_run or o.kind in loud:
            print("\n".join(_describe(o)))
    if not config.airtable_configured() and any(o.kind in ("applied", "rejected")
                                                for o in outcomes):
        print("inbox: Airtable is not configured, so statuses went to SQLite only.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
