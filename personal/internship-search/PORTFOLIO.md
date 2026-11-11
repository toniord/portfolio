Has run my internship search unattended since August 7, 2026: 231 runs, 41,980 postings
tracked from 196 company job boards and three aggregator feeds, and 3,422 postings scored by
Claude for $13.12 in total, under half a cent each. A rules filter defined as data cuts the
28,361 open postings to 2,646 (9.3%). Claude Haiku 4.5 tags each new posting's term and weekly
hours once, and the agent follows feed links to the Greenhouse, Lever, Ashby, Workday, Oracle
or SmartRecruiters job behind them to fetch the description. A two-stage ranker scores
survivors against a fixed-anchor rubric on two axes, how much I would want the role and how
likely I am to land it, and both decide the tier, so a good-fit role I can realistically win
outranks a high-fit long shot. Haiku scores every posting, and only those above a
routing threshold go to Claude Sonnet 5. Each prompt carries my 54 labelled postings as
few-shot examples, cached at a tenth of the input price. Per-run call caps and a monthly
budget bound spending. Output goes to a daily email, an Airtable base and a local dashboard,
with health alerts checked by mutation testing. A read-only Gmail reader turns application
confirmations into Applied status and rejections into Rejected, with a Haiku call deciding any
email whose wording could be either, and creates the posting from the email when the agent
never found it. About 21,300 lines of Python including tests, and 746 checks.

Python, SQLite, Claude API, Airtable API, Gmail API, launchd.
