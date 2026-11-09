Triages an industrial distributor's weekly ERP reorder list, 1,740 lines across three branches,
in under a second, and recommends a verdict, quantity, reason and owner for every line without
ever placing an order. It changes or holds 556 lines (32%), and it sends 296 back to a person
with no quantity because a number would be a guess. One example is a contract customer already
short with a supplier running twice the ERP's lead time. The agent sends that line to the
purchasing manager the same day, because a purchase order can't fix this week. Thirteen ordered
rules, drawn from interviews with the manager and buyers and checked against the customer
contracts, purchasing policy, price list and rush freight log, exist as a plain-language agent
spec and a pandas reference implementation. Version 3 scores 30 of 30 against the manager's own
answers, up from 27, and reproduces all 13 expected verdict counts on the full list. The case is
fictional and was provided by a course, and an AI assistant drafted the docs and code under my
direction.

Python, pandas, openpyxl.
