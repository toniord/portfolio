# Antonio Rodriguez Diaz

I love building AI agents. I study physics and economics at the University of Chicago (class of
2028). In summer 2026 I built AI agents as an intern at QofAI, and I still work with
QofAI today.

[LinkedIn](https://www.linkedin.com/in/antonio-rodriguez-diaz-76115632a)

## Layout

- [`personal/`](personal/) holds my personal projects. Each folder is a published copy of a
  working project.
- [`qofai/`](qofai/) covers my internship work: what each agent does, how it is built, and
  screenshots of its output. The code is under review by QofAI and not yet public, and a
  walkthrough is available on request.

## Projects

<!-- projects:start -->

### Personal projects

#### [internship-search](personal/internship-search/)

Tracks internship postings across 180 company job boards (Greenhouse, Lever, Ashby, Workday)
and three aggregator feeds, four times a day. As of October 2026 it has tracked 40,659
postings. A rules filter defined as data cuts the 27,968 open ones to 2,485 (8.9%). Claude
Haiku 4.5 reads the term and weekly hours once from each new posting that passes the first
rules and that no feed has already labelled. Feeds carry only a link, so the agent reads
each link's shape to find the Greenhouse, Lever, Ashby or Workday job behind it and fetches the
description before ranking, re-scoring anything already judged without it. A two-stage ranker then scores survivors against a
fixed-anchor rubric. Haiku scores every posting, and only those above a routing threshold go to
Claude Sonnet 5. Each prompt carries all 53 of my Airtable labels as few-shot examples, which
also pushed the prompt past Haiku's caching threshold, so every call after the first in a run
reads it at a tenth of the input price. A hard per-run call cap bounds spending. Output goes to
a daily email, an Airtable base and a local dashboard, on a launchd schedule with health
alerts. About 11,000 lines of Python including tests, and 523 checks.

Python, SQLite, Claude API, Airtable API, launchd.

#### [trip-planner](personal/trip-planner/)

Plans a group trip from one shared link and a two-minute form per person. A deterministic
planner filters 61 destinations on hard constraints (passports, each person's budget against
their real cost, maximum flight time). It scores the rest on five weighted factors, including
coverage for the least-served traveler. It re-ranks the top five on Open-Meteo weather for the
actual dates and prices live flights and hotels through SerpApi. Claude Opus 5.5 handles the
two language tasks. It converts free-text notes ("I use a wheelchair") into constraints, with
structured output limited to tags the planner recognizes. It also writes the itinerary, which
gets three drafts to pass validation before a template takes over. Every external call has a
fallback. Built for a UChicago AI program in winter 2026 and since deployed at
grouptrip-planner.vercel.app, with 69 tests.

TypeScript, React, Vite, Vercel Functions, Neon Postgres, Claude API, Open-Meteo, SerpApi.

#### [apartment-chores](personal/apartment-chores/)

Assigns chores in a shared apartment on a rotation that balances every chore across roommates
over a quarter, sends a weekly digest, and privately nudges anyone overdue. Claude Sonnet 5
reads the landlord's emails into proposed cleaner visits through structured output, and plain
code verifies each one. The quoted sentence must appear in the email, the date must fall in
range, and any named weekday must match the date. A visit whose date fails a check becomes an
undated request for a person to fill in, and nothing takes effect until a roommate confirms
it. All configuration lives in Airtable. Runs on GitHub Actions, with over 400 tests.

Python, Airtable API, Gmail SMTP/IMAP, Claude API, GitHub Actions.

#### [life-dashboard](personal/life-dashboard/)

A personal morning brief that builds one local page at 6 AM and emails a digest at 7. Live
sources: Open-Meteo weather, five Google calendars including Canvas due dates, two Gmail
inboxes, chore and internship reports from my other agents, NYT, and the AI Daily Brief. Claude
Haiku 4.5 triages email in batches of 10. Claude Opus 5.5 rates each upcoming event's lead
time, then ranks up to seven Pressing actions using my feedback. Code rejects non-read-only
Google scopes, fetches email metadata and never bodies, and falls back to rules when a model
call fails. Work meetings reach only the lead-time call, never the ranking. 126 offline tests.

Python 3.12, uv, launchd, Gmail and Google Calendar APIs, Open-Meteo, NYT API, Claude API
(Haiku 4.5, Opus 5.5), Tailscale.

<!-- projects:end -->

### QofAI internship

Three agents built during my 2026 internship at QofAI. The code is held back while QofAI
reviews a sanitized copy; each folder describes the agent and shows real output on invented
data.

- [deck-generator](qofai/deck-generator/) writes proposal and status decks, guards every value
  against its sources, and gives reviewers a studio that turns plain-language edits into exact
  text swaps. 2,447 tests and about 38,000 lines of application code.
- [content-calendar](qofai/content-calendar/) sequences a month of posts per author with one
  schema-constrained Claude call under a YAML policy, and routes every post through a human
  approval queue. I took it over from a teammate and wrote 98% of the current code. 171 tests.
- [pe-research-agent](qofai/pe-research-agent/) writes a sourced dossier on a private equity
  firm with eight Claude Code skills and parallel subagents, labeling every claim with a
  confidence band and source type.

## How this repo is maintained

Each personal project lives in its own private repo. [`tools/sync.py`](tools/sync.py) runs
after every commit to any of them. It exports the project's main branch, removes private files
(personal configuration, application history, planning notes), and replaces personal details
with example values. Two gates follow. A scanner checks for credentials, email addresses and
known identifying text, and then Claude reviews exactly what changed for personal or
confidential details the rules did not anticipate. If either gate finds anything, nothing is
published. Each project's entry above comes from a short `PORTFOLIO.md` in its own repo, so the
descriptions update with the projects. What to redact lives in a private file on my machine,
because a public list of what is being hidden would reveal it.

A few documents are left out for privacy, including the PRDs and changelogs of
internship-search and life-dashboard. Some links inside the project READMEs point to those
files and will not resolve here.
