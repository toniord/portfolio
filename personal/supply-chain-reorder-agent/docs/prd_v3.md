**Build doc, case 10, Brickyard Industrial Supply**

Version 3, October 28, 2026. Built from version 2 (October 21), the Door 3 test (screen_these_30.csv and supplier_portal_snapshot_30.csv), the Table 7 score doc (27 of 30 against Kevin's answers) and Kevin's follow-up answers. Every change gets a new version number.

## What changed from the last version, and why

1. The agent reads the supplier's actual lead time from the supplier portal file: the average of po_to_receipt_days_last_3, by item and branch. Girder's lead time is no longer the only one used. **From the test**
2. New, inside rule 1: a contract line that is short today, with a supplier whose actual lead time is more than 7 days, "comes to Kevin" the same day, because "a PO does not fix this week." The row names the shortfall, the actual lead time and the freight call. It fixes BRG-10009. **From the test**
3. The freight call on a short contract line is Kevin's: "Pete calls him first and he decides on the freight." **From our user**
4. New rule 10: on a plain line where the supplier takes twice Girder's lead time or more, "order up for the extra days" (extra days times daily sales, rounded up), and put the line on Kevin's fix list so the lead time gets fixed in Girder. It fixes CUT-10052 (Kevin's 29). **From the test**
5. The threshold is twice Girder's lead time, because under that Kevin "mostly we leave it as printed. A few days late doesn't empty the shelf, because the gap between the min and the max covers it." Dee's bumps on a remembered late order live in her head, so the agent does not copy them. **From our user**
6. The rush rule stays ahead of both lead-time rules, so MTR-10011 stays "call first." The rush hand-back now also shows the actual lead time. **From the test**
7. New rule 5b: when the supplier's minimum order on the item is more than a year of 12-month sales at that branch, the line goes back to the buyer: "Dee decides whether to take the minimum, source it elsewhere or let it go." It fixes PLM-10015. **From the test**
8. The output is one row per item and branch. PLM-10011 gets a Joliet row and a Rockford row. **From the test**
9. The "don't order, it's D" reason now starts "hand back to Dee" (or Pete), so it can't be read as a change to zero. **From the test**
10. The test section now records the Door 3 test, how it is scored, and the before and after scores. **From the test**

## What changed from version 1 to version 2

1. Contract items come into the first job. They come from customer_contract_stock_clauses.txt and are no longer waiting on Ron Spiller. **Found in the interview**
2. A contract item is never ordered below "what the contract says," and the contract minimum counts on-hand stock only. **In a file**
3. A contract item that is D is never swapped for the replacement. It "comes to Kevin," because Midvale 6.4 and Starr Ridge 9.4 bar substitution without the customer's written consent. **In a file**
4. Contract items under the contract minimum today go to Kevin on one list, because the plant manager calls Kevin and the contracts carry same-day duties. **In a file**
5. Rush items get no proposed number. Girder's number is shown in its own column, and the quantity stays blank until the call. **In a file**
6. The rush hand-back says who to call: the customer, the supplier or Marty. **In a file**
7. Every item on the 2025 rush log counts as a rush item, not only the top 200. **Found in the interview**
8. A D item with a replacement that is also on the rush log is "call first," with the replacement named. It is not ordered at Girder's number. **In a file**
9. A D item with an open order is handed back: "the PO sits open forever and the supplier never ships." **In a file**
10. New rule: every Prairie Harvest glove line goes to max, however far over max it is. Version 1 got 13 of the 25 glove lines wrong. **Found in the interview**
11. "Order to max" and "order to min" are defined as the level minus on hand minus on order, which is Girder's own calculation. The triad confirmed this. **In a file**
12. Section 2 no longer says "the agent caps at max." It caps known one-offs and flags lines at twice max or more. **In a file**
13. Shelf life is read from the price-list column, never from the supplier name. **In a file**
14. The November 1 price rise moves from out of scope into the rules: never raise a quantity because of it. **In a file**
15. Approval is partly settled: Marty signs POs over $10K only when Kevin is out. It stays with PO grouping, which is out of scope. **In a file**
16. Every hand-back names who gets it. **In a file**
17. Input handling: read every field as text, skip the report total line, never save over the file. **In a file**
18. The test is rebuilt with contract, glove, open-order and rush-replacement lines, and new costly misses. **In a file**
19. Counts are recounted on the October 12 list. They now add up to 1,740. **In a file**
20. The policy line is now checked against Purchasing_Policy_2023.pdf (PP-04). It confirms the "order to max" definition (3.2) and why D items still print (3.5). It also puts Kevin's "comes to me" in writing (3.3, 6.1), so the reason column is written as the line note the policy asks for. **In a file**
21. Rush freight approval belongs to the receiving branch manager under the policy (5.1), but buyers approve in practice. This is noted, and stays out of scope. **In a file**
22. Rule 9 (twice max or more: "order to max," flagged "check F7 first") is confirmed by the triad and no longer open. **In a file**
23. New rule 9b: lines more than 1.5 times max but under twice max keep Girder's quantity, flagged "check F7 first" (34 lines). It's a flag, not a cut, because Girder's quarter-of-a-year rule is deliberate for fast movers (PP-04 3.2), and the known one-off shows one-offs sit under twice max: 22 of the 25 Prairie Harvest glove lines are under twice max, and 11 are above 1.5 times. **In a file**

## 1. The user and the decision

The users are Kevin Doyle's two buyers, Dee Alvarez (Joliet and Rockford) and Pete Sorensen (Fort Wayne). Kevin owns the decision and the policy behind it. Every Monday after Girder prints its 5:30 report, they decide which of the suggested lines (1,740 this week) to order as printed, change, or not order, and they finish by Tuesday.

When it goes wrong:
- POs sit open on discontinued items that never ship.
- Rush freight runs about $180,000 a year ($179,842 in 2025).
- A contract customer's plant manager calls the same day, and the contracts attach money to it: Lockport charges up to $24,000 per occurrence, and two Midvale shortfalls in a quarter are a material breach.
- Fill rate stays at 94 percent against a 97 target.

## 2. Trigger and inputs

**Trigger:** erp_suggested_orders_<date>.csv, Monday 5:30, exported from Girder. This week's file is **erp_suggested_orders_2026-10-12.csv**.
- It has a banner first line, a subtotal line after each branch and a report total line at the end. The agent skips all of them.
- It reads every field as text and never saves over the file, because "the item numbers with leading zeros get eaten."
- It matches on item number, never description.

**Also read:**
- customer_contract_stock_clauses.txt: the three schedules, 40 items, each with a branch and a Minimum On-Hand Quantity.
- supplier_price_list_2026-10.csv: status, replacement item, shelf life, discontinue date, and the supplier's minimum order (min_order_qty).
- The supplier portal file (in the test, supplier_portal_snapshot_30.csv): po_to_receipt_days_last_3, the days each of the last three orders took. Their average is the actual lead time. If an item has no portal row, the lead-time rules don't apply and the reason says "no portal lead time."
- rush_freight_log_2025.csv: 270 items, who called, the note.

**The numbers not to trust:** Girder's suggested quantity and Girder's lead time. They rest on a min, max and lead time last reset in 2023. It uses a quarter of 12-month sales when that beats max, so one big order inflates it. On contract items, the min "is nothing like what the contract says."

Instead, the agent:
- orders contract items to the contract minimum,
- caps the known one-off (the Prairie Harvest gloves) at max,
- flags lines at twice max or more,
- checks the price list status,
- checks chemicals against 12-month sales,
- reads the actual lead time from the portal file,
- checks the supplier's minimum against a year of sales.

## 3. The first job

**Input:** erp_suggested_orders_2026-10-12.csv, with the files above.

**Output:** one row per line, which means one row per item and branch, with these columns: item, branch, Girder's quantity, verdict, quantity, reason, and who it goes to. The verdicts are in the buyers' words:
- "order as printed"
- "order to max"
- "order to min"
- "order to the bigger number"
- "order to what the contract says"
- "order the replacement"
- "don't order, it's D"
- "order nothing, write it on the reset list"
- "count the shelf"
- "don't order more than a year's worth"
- "call first"
- "comes to Kevin"
- "order up for the extra days"
- "buyer decides: take the minimum, source it elsewhere or let it go"

On a "call first" line the quantity is blank, and Girder's number is shown only in its own column.

**The check:** known answers from this list.
- Dee orders every nitrile glove line from the Prairie Harvest order to max (SAF-10018 at Joliet: 20, not 55).
- Sheldon cap screws flagged D (FAS-10007) are never ordered.
- Min-above-max lines go to the bigger number.
- MHD-10011 at Rockford (Starr Ridge, rushed twice in 2025) is "call first," with no number.
- CUT-10043 at Joliet (a Lockport critical item, now D) "comes to Kevin."
- In the Door 3 test: BRG-10009 at Fort Wayne (Midvale short, Great Lakes at 14 days) "comes to Kevin"; PLM-10015 at Joliet (Illini minimum 12, 5 a year) goes back to Dee; CUT-10052 at Joliet (Wabash at 30 days) is "order up for the extra days," 29.

Working means all of these come out right, no D line is ever marked "order," and no contract line is ordered below what the contract says.

## 4. The rules

Apply in this order; the first rule that fits decides the line. Counts are from the October 12 list. "Order to max" means max minus on hand minus on order, and "order to min" means min minus on hand minus on order.

1. **If the item is on a contract schedule at that branch (22 lines):**
   - If on hand is negative, "count the shelf" (0 this week).
   - If the price list says D, "comes to Kevin." Don't order the replacement: Midvale and Starr Ridge must consent in writing to any substitute (1 line, CUT-10043).
   - If the item is on the 2025 rush log, "call first": call the customer (8).
   - If on hand is under the contract minimum and the supplier's actual lead time is more than 7 days, "comes to Kevin" today: "a PO does not fix this week." Name the shortfall, the actual lead time and Girder's, and the freight call: the buyer calls Kevin first, and he decides on the freight.
   - Otherwise order the larger of Girder's quantity and the contract minimum minus on hand minus on order: "order to what the contract says" (6) or "order as printed" (7).
   - If on hand is under the contract minimum today, the line also goes on Kevin's contract list (21 of 22). On-order stock does not count toward the minimum.
2. **If the price list says D:**
   - With a replacement listed, "order the replacement" at Girder's quantity (43). If the item is also on the rush log, "call first" and name the replacement (2).
   - With no replacement listed, "don't order, it's D," and hand it back (85).
3. **If on hand is negative,** "count the shelf" (12).
4. **If 12-month sales at that branch are zero,** "order nothing, write it on the reset list" (15).
5. **If the item is on the 2025 rush log,** "call first," with no number (211). Show the actual lead time when the portal has it.
   - 5b. **If the supplier's minimum order is more than a year of 12-month sales at that branch,** "buyer decides: take the minimum, source it elsewhere or let it go." Name the minimum, the sales and the supplier (62 on October 12).
6. **If max is zero,** "order to min" (17). **If min is above max,** "order to the bigger number" and add the line to Kevin's fix list (26).
7. **If the item has a shelf life in the price list column,** cap on hand plus on order plus the new order at 12 months of sales: "don't order more than a year's worth." Use the column, never the supplier name, because Granite Electric, Pine Bend Hydraulics and Maumee Electric Motor have no shelf life, while Hoosier Oil and Driftless Paint do. This week 83 lines are checked and 1 is capped (ADH-10009, 26 cut to 6).
8. **If the item is one of the 25 Prairie Harvest nitrile gloves,** "order to max" (24; SAF-10180 goes to rule 5b). These are the 4 mil blue, 6 mil black, 3 mil food grade, 8 mil orange, 5 mil textured and extended cuff, all at Joliet.
9. **If suggested is twice max or more,** "order to max" and flag it "check F7 first" (43).
   - 9b. **If suggested is more than 1.5 times max,** "order as printed" at Girder's quantity, flagged "check F7 first" (32). This flags the line and never cuts it.
10. **If the supplier's actual lead time is twice Girder's or more,** "order up for the extra days": add the extra days times 12-month sales divided by 365, rounded up, and put the line on Kevin's fix list so the lead time gets fixed in Girder. (The October 12 list has no portal file, so this rule and the contract lead-time check could not run on it.)
11. **Otherwise,** "order as printed" (1,145).

**Never raise a quantity because of the price rise.** Sheldon, Calumet and Maumee go up November 1 (197 price-list rows). Kevin says "do not pre-buy… order the normal quantity."

**Where the written rule and the practice differ, the agent follows Dee.** The 2023 policy assumes a yearly min and max reset ("reviewed and reset for every stock item at every branch each January," PP-04 4.1) and has buyers "order the suggested quantity" (3.3), but neither has held since 2023. Dee's rules are what the buyers apply and what the test is scored against. The contract schedules override both.

**The policy backs three rules.**
- It defines Girder's quantity as the one that "brings on hand plus on order up to the maximum" (3.2), which is how "order to max" is defined here.
- It says discontinued items "do not appear" on the report once a buyer sets the status (3.5). That step is what was skipped on 600 items, which is why the agent has to check the price list.
- It requires "a disposition on every line" (3.1), which is the one row per line the agent hands back.

**Approval:** Kevin's "comes to me" holds and is policy: a buyer may change a suggested quantity only with the Purchasing Manager's written approval, "recorded in the line note in the System with the reason" (3.3, 6.1). The agent's reason column is written so it can serve as that note. Dee's "Marty signs the POs over $10K" applies only when Kevin is out. Rush freight approval is the receiving branch manager's under the policy (5.1), but the 2025 log shows the buyers approving. Both approvals sit with PO grouping and rushes, which are not in scope.

## 5. What the agent hands back

Each hand-back goes to the branch buyer (Dee for Joliet and Rockford, Pete for Fort Wayne) unless it says Kevin.

- **Contract items under the contract minimum today, to Kevin:** customer, item, branch, contract minimum, on hand, and what the agent ordered. The contracts carry same-day duties, and Lockport's monthly report is certified by Kevin.
- **Contract item that is D, to Kevin:** item, customer, discontinue date, and "comes to Kevin: the customer must approve any substitute."
- **Contract items not on this week's list, to the buyer:** the 18 schedule items Girder did not print, with "check the on hand screen against what the contract says." Girder only prints lines under its own min, so these may still be short.
- **Rush items, to the buyer:** "call first," Girder's number in its own column, last year's rush count, cost, the customer who called and the note, and who to call. Call the customer if the item is on a contract schedule, and the supplier if the note says "receipt late" or "PO sat open, supplier backlog" (36 lines). Otherwise the buyer chooses between the customer, the supplier, or Marty if it has to come over from another branch.
- **Contract line short today with a slow supplier, to Kevin:** the customer, the shortfall (on hand against the contract minimum), the actual lead time against Girder's, and "a PO does not fix this week; the buyer calls Kevin first, he decides on the freight."
- **Supplier minimum over a year of sales, to the buyer:** the minimum, the 12-month sales and the supplier, with "decides whether to take the minimum, source it elsewhere or let it go."
- **Slow supplier on a plain line, to Kevin's fix list:** the actual lead time, Girder's lead time and the units added.
- **Discontinued with no replacement:** "hand back to" the buyer, the item, supplier and discontinue date, and "write it down and find one, that's buyer work, don't guess." If it is also a rush item, the rush history goes with it.
- **Discontinued with an open order (11 lines):** the open quantity and "the PO sits open forever and the supplier never ships."
- **Negative on hand:** the on-hand figure and branch, and "count the shelf, fix the count, then decide."
- **Over 1.5 times max, and not a Prairie Harvest glove (rules 9 and 9b):** max, suggested and 12-month sales side by side, with "go look at the sales history screen (F7 from the item) and look for one big line."
- **Min above max, to Kevin's fix list. Zero sales, to the reset list:** "Kevin decides in January if it stays."

## 6. The test

**The Door 3 test (October 21, rerun October 28).** The test set is screen_these_30.csv: 30 lines covering 29 items, with PLM-10011 at both Joliet and Rockford. The supplier portal file stands in for what the buyers check by hand. Kevin gave his answer on all 30 in the score doc.

**How it is scored:**
- Each row is matched to Kevin's answer on the same item and branch.
- Verdicts map to Kevin's words. "Order as printed" is order as suggested. Verdicts that change Girder's number are change. "Count the shelf," "call first," "comes to Kevin," "buyer decides…" and "don't order, it's D" are hand back to buyer.
- Change rows score on direction and reason; the exact quantity does not count.

**Scores:**

| Run | Score |
|---|---|
| Version 2 | 27 of 30. Misses: BRG-10009 and PLM-10015. Arguable: CUT-10052. |
| Version 3 | 30 of 30 |

**The planned set from version 2, kept for the next test.** Thirty lines from the October 12 list:

| Kind of line | Lines |
|---|---|
| Discontinued with a replacement | 3 |
| Discontinued with a replacement, on the rush log (LTG-10161 or FAS-10911) | 1 |
| Discontinued, no replacement (one with an open order, FAS-10728 at Joliet) | 2 |
| Contract item that is D (CUT-10043) | 1 |
| Contract lines (MHD-10011 at Rockford for a rush, SAF-10186 at Fort Wayne for "order to what the contract says," ABR-10008 at Fort Wayne for a plain one) | 3 |
| Min above max | 2 |
| Max zero | 2 |
| Negative on hand | 2 |
| Zero sales | 2 |
| Chemicals (including ADH-10009) | 2 |
| Prairie Harvest gloves (SAF-10018 and SAF-10050 under twice max, SAF-10024 over) | 3 |
| Twice max, not gloves | 2 |
| Rush items | 2 |
| Plain | 3 |

The answer key is written from Dee's notes and the contract schedules before the run. Kevin confirms any disputed lines, and Dee sets the key for the two twice-max lines from the sales history screen.

**Scoring:**
- A match on verdict and quantity is a hit. A "call first" line is a hit on verdict and who to call, with the quantity blank.
- Any other result is a miss.
- Some misses are costly and fail the test on their own: ordering a D, negative or zero-sales line; going over a year on a chemical; ordering a contract item below what the contract says; ordering a replacement for a contract item; or putting a number on a rush line.

**Working means 27 of 30 with no costly misses.** The Evaluator scores.

## 7. Not in scope

**Second job:** the Monday pre-check of the 18 contract items Girder did not print, against the on hand screen. It waits until the first job works, because that screen does not export.

**Also waiting until the first job works:**
- finding substitutes for discontinued items
- grouping into POs against supplier minimums and free freight, including holding or moving under-minimum orders and the $10K approval (a single line whose minimum is more than a year of sales is now in scope, under rule 5b)
- resetting min, max and lead times
- Alan's cash number
- supplier lateness on lines with no portal row
- Dee's bumps on a remembered late order (they live in her head)
- Pete's sticky notes
