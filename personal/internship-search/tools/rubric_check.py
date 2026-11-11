"""Check rubric.md parses and is internally consistent. Run with:

    .venv/bin/python -m tools.rubric_check

Read-only. No database, no network, no model call, no dependencies.

Run it after every edit to rubric.md. The failure this guards is quiet: a tier
band edited to leave a gap means a posting gets scored and lands in no tier, so
it is never emailed and never appears anywhere the owner would notice. Same
asymmetry as the prefilter, and the same reason tools/test_prefilter.py exists.

What it prints is what the ranker will actually apply, so it doubles as the
answer to "what does fit 7 reach 5 do right now".
"""

import sys

from agent import rubric


def main() -> int:
    try:
        text = rubric.prompt_text()
        cfg = rubric.settings()
    except rubric.RubricError as exc:
        print(f"rubric.md is unusable:\n\n  {exc}\n")
        return 1

    lo, hi = cfg["scores"]["min"], cfg["scores"]["max"]

    print("rubric.md parses.\n")

    print("Tier bands, matched in tier order; a posting takes the first it clears")
    for band in rubric.tiers(cfg):
        need = f"fit {band['min_fit']}+"
        if band.get("min_reach") is not None:
            need += f" and reach {band['min_reach']}+"
        print(f"  tier {band['number']}   {need:<22} -> {band['delivery']}")

    # The whole rule as a table, added 2026-10-20 when reach joined the tier.
    # validate() has already proved every pair lands in exactly one tier and no
    # band is unreachable; this is
    # the same table printed so the answer to "what does fit 8 reach 4 do" is
    # one glance rather than a reading of the bands.
    table = rubric.grid(cfg)
    print(f"\nTier for every (fit, reach) pair, {lo} to {hi}. Rows are fit, columns reach.")
    print("  fit\\reach " + " ".join(f"{r:>2}" for r in range(lo, hi + 1)))
    for fit in range(hi, lo - 1, -1):
        cells = " ".join(f"{table[(fit, r)]:>2}" for r in range(lo, hi + 1))
        print(f"  {fit:>9} {cells}")
    counts = {}
    for tier in table.values():
        counts[tier] = counts.get(tier, 0) + 1
    print(
        "  " + ", ".join(f"tier {t}: {n} pairs" for t, n in sorted(counts.items()))
        + f", {len(table)} in all, each in exactly one tier."
    )

    reach_at = cfg["reach"]["flag_at_or_below"]
    routing = cfg["routing"]
    variance = cfg["variance"]
    print(
        f"\nREACH flag on any emailed posting with reach {reach_at} or below."
        f"\nStage C when fit + reach >= {routing['stage_c_min_combined']}"
        f" or fit >= {routing['stage_c_min_fit']}."
        f"\nSelf-check re-scores {variance['sample_fraction']:.0%} of a batch,"
        f" warns above a mean delta of {variance['max_mean_delta']}."
    )

    # The prompt text is the cacheable prefix in Milestone 6. Anthropic's
    # minimum cacheable prefix is 4,096 tokens on Haiku 4.5 and 1,024 on Sonnet,
    # so whether caching will do anything depends on this length plus the
    # few-shot block. Four characters per token is the usual rough estimate.
    approx = len(text) // 4
    print(
        f"\nPrompt text sent to the model: {len(text):,} characters,"
        f" roughly {approx:,} tokens."
    )

    return 0


if __name__ == "__main__":
    sys.exit(main())
