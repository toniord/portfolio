# Monday reorder agent

An agent that reviews a distributor's weekly reorder list and tells the buyers, line by line,
what to order, what to change, and what needs a person to decide first. It recommends and never
places an order.

## What it does

Every Monday an industrial distributor's ERP prints a list of what it thinks each of three
branches should reorder. In the test week that came to 1,740 lines, and the two buyers had until
Tuesday to work through it.

The agent reads that list alongside four other files: the customer stocking contracts, the
supplier price list, a supplier portal snapshot of real delivery times, and last year's rush
freight log. For every line it returns:

- a verdict in the buyers' own words, such as "order as printed", "order to max", "call first"
  or "comes to Kevin" (the purchasing manager)
- a quantity, left blank when the line needs a conversation before anyone picks a number
- a one-line reason the buyer can paste into the order as the note the purchasing policy
  requires
- who gets the line: the branch buyer, the manager, or both

On the full list it finishes in under a second and writes a workbook with a tab for each buyer,
one for the manager, and one for contract items the ERP never printed.

Five rows from the test run, with the reasons exactly as the agent writes them:

| Item | Branch | ERP qty | Verdict | Qty | Reason | Goes to |
|---|---|---|---|---|---|---|
| PILLOW BLOCK 1-7/16 | FTW | 7 | comes to Kevin | | Midvale Castings short today (3 against 8); Great Lakes Bearing is 14 days now (Girder says 7), so a PO does not fix this week; Pete calls Kevin first, he decides on the freight | Kevin + Pete |
| JOBBER DRILL 3/8 HSS | JOL | 24 | order up for the extra days | 29 | Wabash Cutting Tool takes 30 days now against Girder's 14: Girder's 24 covers the old lead time, add 5 for the extra 16 days; fix the lead time in Girder | Dee + Kevin (fix list) |
| BALL VALVE 2 IN BRASS | JOL | 3 | buyer decides: take the minimum, source it elsewhere or let it go | | Illini Pipe & Valve minimum is 12, more than a year of sales (5 in 12 months) | Dee |
| HEX CAP SCREW 5/16-18 | JOL | 9 | don't order, it's D | 0 | hand back to Dee: Sheldon Fastener Co., D since 2026-06-07: write it down and find one, that's buyer work, don't guess | Dee |
| NITRILE GLOVE 4 MIL | JOL | 71 | order to max | 31 | Prairie Harvest glove: I order to the max on every glove line that was on that order | Dee |

In the first row the ERP would have ordered 7 and moved on. The agent sees a contract customer
already under its minimum and a supplier now taking twice the lead time the ERP assumes. An
order placed today would arrive too late, so the agent sends the line to the manager the same
day with the freight decision attached.

## Why it's useful

The ERP's settings were last reset in 2023, so its list can't be trusted as printed. The
business pays for that in four ways, and each maps to something the agent catches on the
1,740-line list.

| What goes wrong | What it costs | What the agent does |
|---|---|---|
| Discontinued items still print, and orders for them sit open forever | Stock that never arrives | Catches all 131 discontinued lines, orders the listed replacement or hands the line back, and never orders the discontinued item itself |
| Contract customers run short | Up to $24,000 per occurrence at one customer, and two shortfalls in a quarter breach another contract | Never orders a contract item below its minimum, puts the 21 short lines on the manager's list, and finds 18 contract items the ERP never printed |
| Items get rushed in by expensive freight | About $180,000 a year | Sends the 221 lines rushed last year to "call first", with the rush history and who to call, before anyone orders |
| One big order inflates every suggestion after it | Overstock and tied-up cash | Cuts 67 inflated lines back to max and flags 32 more to check against sales history |

## Evals

The agent is checked four ways, and `python3 evals.py` runs every check and prints a pass or fail
table.

| Eval | What it checks | Result |
|---|---|---|
| Graded test | 30 lines covering all 14 verdicts, each scored against the purchasing manager's own answer | 30 of 30, up from 27 of 30 in version 2 |
| Full-list counts | Verdict counts on all 1,740 lines against the 13 expected in the spec, plus the 32 flagged lines, 21 contract shortfalls and 18 unprinted contract items | All 16 match |
| Known answers | Lines the buyers named in advance, such as a glove line that should get 20, not 55, and a chemical that should be cut from 26 to 6 | 8 of 8 |
| Hard limits | No discontinued item ordered, no contract item below its minimum, no quantity on a line that needs a person, no order on negative stock or zero sales | 0 violations on 1,740 lines |

How the graded test is scored. Each verdict maps to one of the manager's three answers: order as
suggested, change it, or hand it back to the buyer. A "change" line scores on direction and
reason, not the exact quantity. Some misses fail the test on their own, whatever the score:
ordering a discontinued, negative-stock or zero-sales line, ordering a chemical beyond a year's
supply, ordering a contract item below its minimum or substituting it, or putting a number on a
rush line.

Each version 2 miss became a version 3 rule:

| Line | The manager's answer | Fix in version 3 |
|---|---|---|
| BRG-10009, Fort Wayne | Hand back today, Midvale short (3 against 8) and Great Lakes at 14 days | A short contract line with a slow supplier escalates to the manager the same day |
| PLM-10015, Joliet | Hand back to Dee, Illini minimum of 12 | Rule 5b, supplier minimum above a year of sales |
| CUT-10052, Joliet (scored arguable) | Change up to 29 for the 30-day Wabash lead time | Rule 10, order up for the extra lead time |

The scored run is [data/door3_scored_run.csv](data/door3_scored_run.csv), from October 28. Each
row holds the agent's verdict, the manager's answer and the score, and `evals.py` checks that
the agent still reproduces every verdict and quantity in it. The evals can fail: a copy of the
agent with the rush rule disabled fails that check on the one line it changes.

The hard-limit checks also caught a bug that the graded test and the expected counts had both
missed. In version 3, ADH-10114 at Rockford was discontinued with a listed replacement and had
sold nothing in 12 months. The replacement rule ran before the zero-sales rule, so the agent
ordered 2 of the replacement, breaking the spec's own rule never to order a zero-sales line. The
expected counts had been built from the same rule order, so they agreed with the bug. Version
3.1 checks stock and sales before ordering any replacement, and the line now goes to the reset
list. It is the only one of the 1,740 lines that changed.

## How it decides

Thirteen rules run in a fixed order, and the first rule that fits decides the line.

1. Contract item at its contract branch. This rule has its own checks for negative stock,
   discontinued items, rush history and a slow supplier. Otherwise it orders at least to the
   contract minimum.
2. Discontinued. Order the listed replacement, unless stock is negative or nothing sold, or
   hand it back if there is none.
3. Negative on hand. Count the shelf first.
4. No sales in 12 months. Order nothing and add it to the January reset list.
5. Rushed in 2025. Call first, with no quantity.
   5b. Supplier minimum above a year of sales. The buyer decides.
6. Max of zero, or min keyed above max. Order to min or to the bigger number.
7. Shelf-life item. Cap stock at a year of sales.
8. One of 25 glove lines inflated by a known one-off order. Order to max.
9. Suggested at twice max or more. Order to max and flag the sales history.
   9b. Between 1.5 and 2 times max. Keep the ERP's number and flag it.
10. Supplier now takes twice the ERP's lead time or more. Order up for the extra days.
11. Otherwise, order as printed.

The order carries the judgment. Contract obligations come first because they cost the most to
get wrong. The rush rule sits ahead of both lead-time rules, so any line expedited last year
reaches a person before a formula touches it. Rule 9b flags lines without cutting them, because
the ERP's sizing is deliberate for fast movers.

## How it was built

The rules started from interviews with the purchasing manager and both buyers, checked against
the customer contracts, the 2023 purchasing policy, the supplier price list and the rush
freight log. Where the written policy and the buyers' practice disagree, the agent follows the
practice, and the [PRD](docs/prd_v3.md) records why. Every change in the PRD's change log is
tagged with where it came from: the test, an interview, or a specific file.

| Version | What changed | Result |
|---|---|---|
| 1 | First rule set | Got 13 of 25 glove lines wrong |
| 2 | 23 changes from interviews and documents | 27 of 30 |
| 3 | 10 changes from the test misses, including actual lead times from the supplier portal and three new rules | 30 of 30 |
| 3.1 | Fix for the zero-sales bug the hard-limit evals found | 30 of 30, 19 of 19 checks |

The rules exist in two forms. [docs/agent_instructions_v3.md](docs/agent_instructions_v3.md) is
the plain-language spec an AI agent follows. [agent.py](agent.py) is a 110-line pandas reference
implementation of the same rules. It runs deterministically, and it's the version the evals
above measure.

## Run the test

```
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python3 evals.py
```

That runs the graded test and its checks and should print `9 of 9 checks passed`. To see the
agent's own output, run `python3 agent.py data 30`. It prints all 30 rows and writes
`output/out.csv`, and setting `OUT` writes somewhere else. Three lines to check:

| Item | Branch | Verdict | Qty |
|---|---|---|---|
| BRG-10009 | FTW | comes to Kevin | |
| PLM-10015 | JOL | buyer decides: take the minimum, source it elsewhere or let it go | |
| CUT-10052 | JOL | order up for the extra days | 29 |

The full October 12 list is not published, so the full-list evals (`python3 evals.py --full
PATH`) can't be run from this copy.

## Out of scope

Grouping lines into purchase orders against supplier minimums and free-freight thresholds,
finding substitutes for discontinued items, and resetting the ERP's min, max and lead times.
Each depends on the buyers trusting this first job, and the [PRD](docs/prd_v3.md) lists them as
next steps.

## Files

- `agent.py`, the reference implementation
- `evals.py`, the evals
- `docs/prd_v3.md`, the product requirements and full change log
- `docs/agent_instructions_v3.md`, the agent spec
- `data/`, the 30-line test inputs, the scored run, the price list, the rush log and the contract
  schedules

Brickyard Industrial Supply, its staff, customers, suppliers and data are a fictional case
provided by a course. I built this with an AI assistant, which drafted the PRD, the agent spec
and the reference implementation under my direction.
