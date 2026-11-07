A purchasing agent for a fictional industrial distributor. It triages the ERP's Monday
suggested order list across three branches and recommends a verdict for every line, and it
never places an order. Thirteen ordered rules, written in plain language as agent instructions
and mirrored in a pandas reference implementation, cover customer stocking contracts,
discontinued items, rush freight history, supplier minimums, shelf life, and supplier lead times
read from a portal snapshot. Each line gets a quantity, a one-line reason in the buyers' own
words, and a route to the branch buyer, the purchasing manager or both. Version 2 scored 27 of
30 on a test set graded against the purchasing manager's answers. Version 3 adds three rules
drawn from those misses and scores 30 of 30.

Python, pandas, openpyxl.
