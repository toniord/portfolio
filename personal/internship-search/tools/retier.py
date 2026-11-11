"""Re-derive every stored tier from the scores already stored. Free.

    .venv/bin/python -m tools.retier --dry-run    # what would move, and why
    .venv/bin/python -m tools.retier              # store it

WHY THIS EXISTS.

A tier is derived in `ranker.settle` the moment a posting is scored, and a
posting is scored once. So when the tier bands in `rubric.md` change, every
posting scored before the edit keeps the tier the old bands gave it. Built on
2026-10-20, when tier 1 started requiring a minimum reach as well as a minimum
fit: 2,830 surfaced postings were already scored, and their fit and reach were
sitting in the database the whole time.

This makes no model call. The model's fit and reach are kept exactly as they
are; only the tier, and the REACH flag that rides on reach, are recomputed from
them. `tools.rescore` is the one that re-asks the model, and costs money.

HOW IT DIFFERS FROM tools.reapply_caps. That tool starts from the stored tier
and only ever lowers it, because it cannot know what the tier was before a cap.
This one starts from the scores, so it moves tiers both ways, and it applies
the caps itself exactly as `ranker.settle` does. Running both is harmless.

WHAT IT USES. His own `fit_override` and `reach_override` where he wrote them,
the model's scores where he did not, exactly as `ranker.settle` does, by calling
it. His fit override is still never capped.

WHAT IT NEVER TOUCHES. Scores, overrides, labels, applied status and every
stamp, per CLAUDE.md rule 10: re-tiering must not re-send or un-send anything.
Closed and killed postings are left alone. Run `tools.sync_airtable` afterwards
so the base shows the new tiers.

ONE SIDE EFFECT TO READ BEFORE STORING. The urgent "open too long" email fires
on tier 1 postings older than `stale_after_days` that he has neither labelled
nor applied to. A posting promoted into tier 1 here can be old enough to
qualify the moment it arrives, so the dry run counts how many would.
"""

from __future__ import annotations

import argparse
import sys
import tomllib
from collections import Counter
from datetime import datetime, timedelta, timezone

from agent import config, db, ranker, rubric

SCORED_OPEN = (
    "SELECT * FROM postings WHERE fit_score IS NOT NULL "
    "AND closed_detected_at IS NULL AND prefilter_verdict = 'surface'"
)


def changes(conn, cfg: dict | None = None) -> list[tuple[dict, dict]]:
    """Every scored, open, surfaced posting whose tier or REACH flag would move."""
    cfg = cfg or rubric.settings()
    out = []
    for row in conn.execute(SCORED_OPEN):
        row = dict(row)
        answer = {"fit": row["fit_score"], "reach": row["reach_score"],
                  "reason": row["reason"] or ""}
        # Strip the stored REACH flag before settling, so a posting whose reach
        # no longer earns it loses it. settle only ever adds flags.
        base = ",".join(f for f in (row["flags"] or "").split(",") if f and f != "reach")
        settled = ranker.settle({**row, "flags": base}, answer, row["scored_by"] or "", cfg)
        # Compared as sets: re-adding REACH puts it at the end, and a flag that
        # merely moved position is not a change worth writing.
        before = {f for f in (row["flags"] or "").split(",") if f}
        after = {f for f in settled["flags"].split(",") if f}
        if settled["tier"] != row["tier"] or before != after:
            out.append((row, settled))
    return out


def _stale_after_days() -> float:
    with open(config.EMAIL_RULES_PATH, "rb") as fh:
        return float((tomllib.load(fh).get("urgent") or {}).get("stale_after_days", 10))


def would_trigger_stale(row: dict, new_tier: int, days: float) -> bool:
    """Whether a newly tier 1 posting would land in the next "open too long" email.

    Mirrors `db.urgent_by_age` with its default `stale_needs_action`, which is
    what sources/email.toml sets. Only for the dry run's warning; nothing here
    decides what is sent.
    """
    if new_tier != 1 or row["tier"] == 1 or row["urgent_stale_alerted_at"]:
        return False
    if (row["label"] or "").strip() or (row["applied_status"] or "not_applied") != "not_applied":
        return False
    if row.get("closed_by_me"):
        return False
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat(timespec="seconds")
    return (row["first_seen"] or "") <= cutoff


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dry-run", action="store_true", help="print, store nothing")
    parser.add_argument("--samples", type=int, default=5,
                        help="example postings to print per tier move")
    args = parser.parse_args()

    conn = db.connect()
    total = conn.execute(f"SELECT COUNT(*) FROM ({SCORED_OPEN})").fetchone()[0]
    moved = changes(conn)
    tier_moves = [(r, s) for r, s in moved if s["tier"] != r["tier"]]
    flag_only = len(moved) - len(tier_moves)

    print(f"{total:,} scored, open, surfaced posting(s) re-derived from stored scores.")
    print(f"{len(tier_moves):,} would change tier; {flag_only:,} more change only "
          f"their REACH flag.\n")

    by_move = Counter((r["tier"], s["tier"]) for r, s in tier_moves)
    for (old, new), n in sorted(by_move.items()):
        print(f"  tier {old} -> {new}: {n:,}")
        shown = [m for m in tier_moves if (m[0]["tier"], m[1]["tier"]) == (old, new)]
        for row, settled in shown[: args.samples]:
            print(f"      fit {settled['effective_fit']} reach {settled['effective_reach']}"
                  f"  {row['company']}: {row['title'][:70]}")

    days = _stale_after_days()
    stale = [r for r, s in tier_moves if would_trigger_stale(r, s["tier"], days)]
    print(f"\n{len(stale)} newly tier 1 posting(s) are older than {days:g} days with no "
          f"label and no application, so the next run's urgent \"open too long\" "
          f"email would carry them.")

    if args.dry_run:
        print("\nDry run. Nothing was written.")
        return 0
    conn.executemany(
        "UPDATE postings SET tier = ?, flags = ? WHERE id = ?",
        [(s["tier"], s["flags"], r["id"]) for r, s in moved],
    )
    conn.commit()
    print(f"\n{len(moved):,} posting(s) updated. Run tools.sync_airtable so the base "
          f"shows it.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
