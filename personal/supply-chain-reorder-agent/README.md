# Monday reorder agent

An agent that does a purchasing team's hardest Monday task. The ERP prints a suggested order
list for three branches, 1,740 lines in the test week, and the buyers have until Tuesday to
decide what to actually order. The agent reads that list alongside four other sources (customer
stocking contracts, the supplier price list, a supplier portal snapshot and last year's rush
freight log) and returns a verdict, a quantity, a one-line reason and an owner for every line.
It recommends and never places an order.

On the full list it finishes in under a second. It changes or holds 556 of the 1,740 lines
(32%), sends 296 of them back to a person with no quantity because a number would be a guess,
and flags 32 more for a second look. On a 30-line test graded against the purchasing manager's
own answers, version 3 scores 30 of 30, up from 27 of 30.

## What it hands back

Five rows from the test run, with the reasons exactly as the agent writes them.

| Item | Branch | ERP qty | Verdict | Qty | Reason | Goes to |
|---|---|---|---|---|---|---|
| PILLOW BLOCK 1-7/16 | FTW | 7 | comes to Kevin | | Midvale Castings short today (3 against 8); Great Lakes Bearing is 14 days now (Girder says 7), so a PO does not fix this week; Pete calls Kevin first, he decides on the freight | Kevin + Pete |
| JOBBER DRILL 3/8 HSS | JOL | 24 | order up for the extra days | 29 | Wabash Cutting Tool takes 30 days now against Girder's 14: Girder's 24 covers the old lead time, add 5 for the extra 16 days; fix the lead time in Girder | Dee + Kevin (fix list) |
| BALL VALVE 2 IN BRASS | JOL | 3 | buyer decides: take the minimum, source it elsewhere or let it go | | Illini Pipe & Valve minimum is 12, more than a year of sales (5 in 12 months) | Dee |
| HEX CAP SCREW 5/16-18 | JOL | 9 | don't order, it's D | 0 | hand back to Dee: Sheldon Fastener Co., D since 2026-06-07: write it down and find one, that's buyer work, don't guess | Dee |
| NITRILE GLOVE 4 MIL | JOL | 71 | order to max | 31 | Prairie Harvest glove: I order to the max on every glove line that was on that order | Dee |

The first row is the one that matters most. The ERP would have ordered 7 and moved on. The
agent sees a contract customer already below its minimum and a supplier now taking twice the
lead time the ERP assumes, so it concludes a purchase order cannot fix this week. It sends the
line to the manager the same day with the freight decision attached.

## Why the ERP's list can't be trusted

The ERP's min, max and lead-time settings were last reset in 2023. It sizes orders on a
quarter of annual sales, so one large order inflates every suggestion after it. Discontinued
items still print because nobody flipped their status. Its minimums have nothing to do with
what customer contracts require, and those contracts carry real penalties: up to $24,000 per
occurrence at one customer, and two shortfalls in a quarter count as a material breach at
another. The cost shows up as about $180,000 a year in rush freight and a 94% fill rate against
a 97% target.

## How it decides

Thirteen rules run in a fixed order, and the first rule that fits decides the line.

1. Customer contract item at its contract branch, with its own sub-rules. Count the shelf if
   on hand is negative. Escalate if the item is discontinued, because the contracts bar
   substitutes. Call first if it was rushed. Escalate today if the customer is already short
   and the supplier is slow. Otherwise order at least to the contract minimum.
2. Discontinued. Order the listed replacement, or hand it back if there is none.
3. Negative on hand. Count the shelf first.
4. No sales in 12 months. Order nothing and add it to the January reset list.
5. Rushed in 2025. Call first, with no quantity, and name who to call.
   5b. Supplier minimum above a year of sales. The buyer decides.
6. Max of zero, or min keyed above max. Order to min or to the bigger number.
7. Shelf-life item. Cap stock at a year of sales.
8. One of 25 glove lines inflated by a known one-off order. Order to max.
9. Suggested at twice max or more. Order to max and flag the sales history.
   9b. Between 1.5 and 2 times max. Keep the ERP's number, but flag it.
10. Supplier now takes twice the ERP's lead time or more. Order up for the extra days.
11. Otherwise, order as printed.

The order carries most of the judgment. Contract obligations come first because they cost the
most to get wrong. The rush rule sits ahead of both lead-time rules, so a line that was
expedited last year always reaches a person before any formula touches it. Rule 9b flags lines
rather than cutting them, because the ERP's quarter-of-a-year sizing is deliberate for fast
movers.

A few lines are hard limits, whatever rule fires. The agent never orders a discontinued item,
never orders below a contract minimum, never puts a number on a line that needs a phone call,
and never pre-buys ahead of an announced price increase.

## How it was built

The rules come from the people who do the job and the documents they work under. They started
from interviews with the purchasing manager and both buyers, checked against the customer
contracts, the 2023 purchasing policy, the supplier price list and the 2025 rush
freight log. Where the written policy and the buyers' practice disagree, the agent follows the
practice, and the [PRD](docs/prd_v3.md) records why.

Each version was scored against the manager's own answers.

| Version | What changed | Result |
|---|---|---|
| 1 | First rule set | Got 13 of 25 glove lines wrong |
| 2 | 23 changes from interviews and documents: contracts, rush history, glove rule, discontinued items with open orders | 27 of 30 |
| 3 | 10 changes from the test misses and the manager's follow-up: actual lead times from the supplier portal, three new rules, one row per branch | 30 of 30 |

Every change in the PRD's change log is tagged with where it came from: the test, an
interview, or a specific file.

The rules exist in two forms. [docs/agent_instructions_v3.md](docs/agent_instructions_v3.md) is
the plain-language spec an AI agent follows. [agent.py](agent.py) is a 110-line pandas reference
implementation of the same rules, which runs deterministically and is the version tested here.

## Results

On the full October 12 list (1,740 lines), the reference implementation reproduces every
expected count in the spec.

| Verdict | Lines |
|---|---|
| order as printed | 1,184 (32 flagged to check sales history) |
| call first | 221 |
| don't order, it's D | 85 |
| order to max | 67 |
| buyer decides: take the minimum, source it elsewhere or let it go | 62 |
| order the replacement | 43 |
| order to the bigger number | 26 |
| order to min | 17 |
| order nothing, write it on the reset list | 15 |
| count the shelf | 12 |
| order to what the contract says | 6 |
| comes to Kevin | 1 |
| don't order more than a year's worth | 1 |

It also puts 21 contract lines on the manager's list and finds 18 contract items the ERP never
printed. A full run writes a workbook with one tab per buyer, one for the manager and one for
the unprinted contract items.

## Run the test

```
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python3 agent.py data 30
```

The script prints all 30 rows and writes `output/out.csv`. Set `OUT` to write somewhere else.
Three lines to check against the manager's answers:

| Item | Branch | Verdict | Qty |
|---|---|---|---|
| BRG-10009 | FTW | comes to Kevin | |
| PLM-10015 | JOL | buyer decides: take the minimum, source it elsewhere or let it go | |
| CUT-10052 | JOL | order up for the extra days | 29 |

`data/test_run_v2.csv` holds the scored version 2 run for comparison. The full October 12 list
is not published, so the full-run counts above can't be reproduced from this copy.

## What it deliberately leaves out

Grouping lines into purchase orders against supplier minimums and free-freight thresholds,
finding substitutes for discontinued items, and resetting the ERP's min, max and lead times.
Each of these needs the first job to be trusted first, and the [PRD](docs/prd_v3.md) lists
them as the next steps.

## Files

- `agent.py`, the reference implementation
- `docs/prd_v3.md`, the product requirements, with the full change log
- `docs/agent_instructions_v3.md`, the agent spec
- `data/`, the 30-line test inputs, price list, rush log, contract schedules and the version 2 result

Brickyard Industrial Supply, its staff, customers, suppliers and data are a fictional case
provided by a course. I built this with an AI assistant, which drafted the PRD, the agent spec
and the reference implementation under my direction.
