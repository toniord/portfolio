# Monday reorder agent

A rules agent that triages an ERP's weekly suggested purchase order list for an industrial
distributor. It recommends and never places orders.

## The problem

Every Monday the ERP prints a suggested order list for three branches (Joliet, Rockford and
Fort Wayne), about 1,740 lines in the week this case uses. The purchasing manager's two buyers
decide by Tuesday which lines to order as printed, change, or skip. The ERP's numbers rest on
min, max and lead-time settings last reset in 2023, so the list cannot be trusted as printed.
Mistakes show up as open POs on discontinued items, about $180,000 a year in rush freight,
penalties under customer stocking contracts, and a 94 percent fill rate against a 97 percent
target.

## What the agent does

For each item and branch it returns a verdict, a quantity (blank when a person has to decide
first), a one-line reason in the buyers' own words, and who gets the line: the branch buyer,
the purchasing manager, or both. The buyers place every PO themselves.

It reads five inputs and identifies each by its first line, not its file name: the suggested
order list, the customer contract schedules, the supplier price list, the supplier portal
lead times and the 2025 rush freight log.

## Rule order

The first rule that fits decides the line.

1. Contract item at its contract branch. Count the shelf if on hand is negative, escalate if
   discontinued, call first if it was rushed, escalate if short with a long actual lead time,
   otherwise order at least to the contract minimum.
2. Discontinued. Order the listed replacement, or hand back to the buyer if there is none.
3. Negative on hand. Count the shelf.
4. Zero 12-month sales. Order nothing, add it to the reset list.
5. On the 2025 rush log. Call first, no quantity.
   5b. Supplier minimum above a year of sales. Buyer decides, no quantity.
6. Max of zero, or min above max. Order to min or to the larger number.
7. Shelf-life item. Cap stock at a year of sales.
8. One of 25 known one-off glove lines. Order to max.
9. Suggested at twice max or more. Order to max, flagged to check sales history.
   9b. Between 1.5 and 2 times max. Order as printed, flagged.
10. Actual lead time at twice the ERP's or more. Order up for the extra days.
11. Otherwise, order as printed.

A guard applies to every line: never raise a quantity because of an announced price rise. The
full rules and the reasoning behind each one are in [docs/agent_instructions_v3.md](docs/agent_instructions_v3.md)
and [docs/prd_v3.md](docs/prd_v3.md).

## Run the test

The "Door 3" test is 30 lines (`data/screen_these_30.csv`) plus a supplier portal snapshot,
scored against the purchasing manager's answers.

```
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python3 agent.py data 30
```

The script prints 30 rows and writes `output/out.csv` and `output/missing.csv`. Set `OUT` to
write somewhere else. The expected result is 30 of 30 against the manager's answers. Three lines
to check:

| Item | Branch | Verdict | Qty |
|---|---|---|---|
| BRG-10009 | FTW | comes to Kevin | |
| PLM-10015 | JOL | buyer decides: take the minimum, source it elsewhere or let it go | |
| CUT-10052 | JOL | order up for the extra days | 29 |

`data/test_run_v2.csv` is the scored result of the earlier version 2 run, kept for comparison.

## Not included

The full October 12 suggested order list (1,740 lines) is not published, so the full run and
its expected counts in the spec cannot be reproduced from this copy.

## Note

Brickyard Industrial Supply, its staff, customers, suppliers and all data here are a fictional
case study.
