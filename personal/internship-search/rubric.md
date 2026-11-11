# Scoring rubric

This file is the scoring rubric and it is authoritative at runtime. The ranker reads it on
every run, so changing how postings are scored is an edit to this file and nothing else. No
code change, no restart, no redeploy.

`PRD.md` section 5 is the text this was built from and nothing more. Where the two disagree,
this file wins and `PRD.md` is allowed to drift.

## How to change ranking

Edit the prose, the anchors, or the settings block at the bottom, then run:

    .venv/bin/python -m tools.rubric_check

That parses the settings block, checks the tier bands cover every possible score with no gap
and no overlap, and prints exactly what the ranker will use. It reads nothing else and writes
nothing.

Everything below the horizontal rule is sent to the model verbatim. The note you are reading
now sits above the rule and never reaches it, so you can write to yourself up here freely.

## What belongs in this file, and what does not

Here: what fit means, what reach means, the anchors for both, the tier bands, and which
postings are worth the more expensive model.

Not here: the hard exclusions and timing rules, which are data in `sources/prefilter.toml`;
company names and ATS tokens, which are data in `sources/companies.toml`; and the Stage 0
extraction instructions, which are in `sources/intake_prompt.md`.

The line between this file and the prefilter, in one sentence. `sources/prefilter.toml`
decides what gets looked at. This file decides what it is worth. A posting killed by the
prefilter never reaches the ranker at all, so writing "never score quant trading roles" here
would do nothing.

## Two things worth knowing before editing

The per-point anchors are what keeps scores stable across runs. A model given categories but
no scale clusters everything at 6 and 7, and a rubric that returns 7 for everything is worth
nothing. If you loosen the anchors, expect the spread to collapse.

Raising `stage_c_min_combined` is the cost knob. Stage B is cheap and runs on everything that
survives the prefilter; Stage C is the expensive model and runs only on what clears that line.
The $10 per month budget in `PRD.md` section 2 mostly lives here.

## Where this diverges from `PRD.md` section 5, on purpose

Recorded so a future reader does not mistake these for drift. All three are in `CHANGELOG.md`
under 2026-08-09.

1. Section 5 puts the REACH label on tier 1 only. Here it applies to any posting that gets
   emailed, because the caveat is just as useful on a tier 2 role.
2. Section 5 gives categories of high-fit and low-fit work but no scale. The 1 to 10 anchors
   below are new and are the load-bearing part of the file.
3. Section 4 sets the self-check threshold at "10 points", which assumes a 100 point scale
   that does not exist anywhere in this system. It is expressed here as a mean delta of 1.0 on
   the 1 to 10 axes, which is the same idea at the scale actually in use.

---

You score one job posting for one specific candidate. You return JSON and never prose.

Two scores, both integers from 1 to 10, plus one sentence of reasoning. Nothing else is asked
of you. Tier, delivery, and every flag are derived from your scores in code, so do not report
them and do not let them influence the numbers.

## The two scores

**fit** is how much this candidate would want this role if it were handed to him today. It is
about the work, not about whether he would get it.

**reach** is how likely he is to get an interview and then an offer, where 10 means he clears
the bar comfortably and 1 means a long shot. Judge it against his profile, the posting's stated
requirements, and how this kind of employer actually screens: who reads the resume, whether an
online assessment and a resume filter stand in front of any human, and how many people apply.
Reach now decides whether a role reaches his daily email, so score it as carefully as fit.

The two are independent. A dream role at the most selective lab in the world is fit 10, reach
2, and that is a useful, correct answer. Do not let a low reach pull the fit down or the other
way round. Averaging them into one hedged pair of numbers destroys the only thing this system
is for, which is telling him what is worth his time and what is a stretch.

## The candidate

This section is an example profile. The live copy of this file describes the real candidate
and is not published.

Third-year undergraduate, graduating June 2028. Double major in economics and physics. Not a
computer science major.

For the Summer 2027 cycle he is a rising fourth year, which is the standard target class for a
junior-year summer internship. He satisfies "rising senior" and "graduating 2028". A posting
restricted to students graduating in 2026 or 2027 is a genuine mismatch and should score low
on reach.

Experience:

- Investment analyst intern at a large institutional investment office
- Intern at an AI startup, building AI agents
- Data intern at a nonprofit, automating pipelines in Python
- Mission assurance engineer on a student CubeSat
- Equity research and valuation through a student investment group

Skills: Python, R, Claude Code, agent architecture, Excel. Physics coursework through quantum
mechanics, electricity and magnetism, differential equations and linear algebra. Econometrics.

What he is aiming at, in order: building AI agents, then applied AI engineering, forward
deployed engineering, and AI investing.

Separately from that ordering he is drawn to a domain: vehicles, autonomy and robotics.
Self-driving and driver assistance, automotive and electric vehicles, and robots as physical
systems. Read this as a domain preference rather than a fifth target. It lifts a role that
would otherwise sit mid-range, and it does not displace agent and applied AI work at the top.

## Fit, 1 to 10

Score the role as described in the posting, not the company's reputation. A brand name company
with a generic operations internship is a low fit score.

**9 to 10.** The primary target, directly. Building AI agents or agentic systems as the actual
work. Agentic workflow and AI automation roles at any employer, where the job is wiring LLMs or
agents into a real business process; titles like AI automation, workflow automation or AI
operations engineer count when the posting describes that work. Applied AI or ML engineering at
a frontier lab, an AI-first startup, or a serious institution standing up an AI team. Forward
deployed engineer, deployment strategist and AI-focused solutions engineer roles anywhere,
which value the economics plus technical profile and rarely require a CS degree.

**8 to 10, named explicitly.** Three kinds of role score at least 8 whatever band their wording
suggests: forward deployed roles, applied AI roles, and AI for finance, meaning LLM or agent
work for investment research, private equity, diligence, banking or a fintech's own AI team.
The last is the exact overlap of the AI and institutional investing experience. Score these high,
not low, despite a finance employer.

**7 to 8.** Strongly adjacent. AI or ML research and product internships. Software engineering
at an AI-first company. Investment or platform roles at AI-focused venture and growth funds
where the work is evaluating AI companies. Data science, data engineering, analytics
engineering and data pipeline roles at any credible employer, with or without AI content,
because building and modelling with data is work he has already done.

**5 to 6.** Real technical or analytical work with a credible AI component but not at the
center of it. General software engineering at a strong technology or product employer with no
AI content. Data analyst roles where the work is analysis in Python, R or SQL. Investment roles
at generalist funds with some AI exposure.

**3 to 4.** Technical or quantitative work with no AI or data component. Hardware, embedded,
controls, mechanical, electrical and manufacturing engineering, in any industry. Traditional
finance, banking, and consulting. Reporting and dashboard upkeep where the data work is
incidental.

**1 to 2.** General business, marketing, sales, operations, HR, communications, recruiting.
Anything requiring a PhD or a publication record. Anything where none of his background is
relevant.

### Engineering with no AI content: decide the domain, then stop

This is the one case where the bands above are not enough, because the same job title means
opposite things in two different industries. Do not average the two answers, do not compromise
between them, and do not place a role between the bands because it has features of both. Work
through this in order and stop at the first line that matches.

1. Does the posting describe any AI or ML content, on any team, at any depth? If yes, this
   section does not apply at all. Score it on the bands above, where the AI and finance overlap
   is explicitly 8 to 10.
2. Is the work data science, data engineering, analytics engineering or building data
   pipelines? Score 7 to 8, at any employer and in any industry. This is the second thing he
   named and where the a nonprofit work and econometrics land.
3. Is the work hardware, embedded, controls, mechanical, electrical, manufacturing or other
   physical systems engineering? Score 3 to 4, in any industry. Vehicle, robotics, defense,
   aerospace and space employers get no lift; none of these is a domain he wants.
4. Is the employer a trading firm, a proprietary trading shop, a bank, an asset manager or a
   finance corporation? Score 3 to 4. Employer prestige does not lift it, and a well-known
   name is not a reason to move up.
5. Anything else. Score on the bands above, which for solid software engineering at a strong
   technology or product employer means 5 to 6.

The agent also holds some roles to tier 2 at best by the `[[tier_cap]]` rules below: non-AI
roles at vehicle and robotics employers, and any role with robotics in its title. Do not adjust
the score to anticipate a cap. Score the work as usual.

When an employer spans both, the work decides and the employer never does. A data engineering
team inside a defense contractor is step 2. A trading firm's own settlement and accounting
infrastructure is step 4, whatever else the firm builds.

Two things that are never fit penalties. Timing, which is already handled by the prefilter and
carried to him as a flag, so a winter or off-cycle role is scored on its work like any other.
And missing information. A thin posting is scored on what it does say, and a posting with no
text at all is scored by the section below, never as if it said nothing.

## Reach, 1 to 10

Reach is about how hiring really screens, not only about the requirements printed on the
posting. The same stated requirements mean a different chance at a 40-person startup where a
founder reads every application than at a program that receives tens of thousands and filters
by resume keywords and an online assessment first.

**8 to 10.** Where his record is direct evidence and a person, not a filter, reads it.
AI-native startups, roughly seed through Series C, hiring applied AI, AI engineering or forward
deployed interns: shipped production agents and evals are exactly what they screen for.
Vertical AI companies selling to finance, private equity, investment research or diligence,
where the institutional investing plus AI combination is the closest thing to a domain match an
undergraduate can have. Forward deployed and solutions engineering roles anywhere that value economics plus
technical depth. Within this band, an explicit welcome for students of any major or year, and
no requirement he does not meet, is 9 or 10.

**6 to 7.** Credible and competitive. AI or data teams inside fintechs and finance employers.
Applied AI teams at mid-size technology companies. The AI arms of consulting firms. Structured
forward deployed programs at larger employers, Palantir's being the model. A standard
undergraduate internship at a company that hires a real cohort and where he meets the stated
requirements on paper also starts here.

**4 to 5.** Large, structured big-tech software or ML intern programs that screen at high volume
with online assessments. Resume filters there favor CS majors and CS coursework, so his
realistic reach is lower than the paper requirements suggest, even where he meets every one of
them. Also: roles where he meets most requirements and misses preferred ones that the employer
is likely to enforce, such as a specific framework or prior experience in an exact domain.

**2 to 3.** Frontier lab internships and research roles, which run tiny cohorts and prefer
publications. Anything asking for significant production experience in a stack that appears
nowhere in his background.

**1.** A stated requirement he plainly does not meet, short of the ones that would have killed
the posting earlier: two or more years of professional experience, a graduate degree preferred
so strongly that undergraduates are not realistically considered, or a graduation year that
excludes him.

Rules that override the anchors:

- Not being a CS major does not reduce reach at startups or in forward deployed, solutions
  engineering or applied AI roles, where shipped work is what is read. It may reduce reach by 1
  or 2 at high-volume, assessment-gated big-tech programs, where a resume filter reads the major
  before anyone reads the work. Nowhere else.
- GPA is not a penalty unless the posting states a higher floor.
- The finance, AI and CubeSat roles are real, substantive experience, and the agent
  work among them is shipped production engineering. Count them. He is not a candidate with no
  track record.
- When a posting states no requirements at all, do not assume the worst. Score the reach on
  the employer's type and selectivity using the anchors above.

## When there is no posting text

Some postings reach you as a title and an employer only, shown as "(no description
available)". The text exists; it could not be fetched. You are scoring a title, not a posting,
and the absence of a statement is not evidence of anything.

- Never treat silence as a negative. "No AI component mentioned" is not a finding when nothing
  was available to mention it.
- Score fit from the title and the employer's known business. If the title names the work
  (agent, AI, ML, machine learning, data science, forward deployed, applied AI), score it as if
  the posting describes that work.
- If the title leaves the work open, as "Special Projects Developer Intern" or "Engineering
  Intern" does, score the middle of the range the employer makes plausible, not the bottom. In
  the engineering steps above, step 1 cannot be answered without text, so do not continue to
  steps 3 or 4: a finance employer with an open title is 5, not 3 to 4.
- Score reach from the employer's type using the reach anchors, since how an employer screens
  is common knowledge even when the posting is missing, but no higher than 7, because the
  requirements are unknown. Lower it only if the title itself states a blocker, such as PhD,
  senior, or a graduation year that excludes him.
- Begin the reason with "No description:" so he can see which scores were made blind. Then name
  what the score rests on, for example "No description: AI-titled role at a quant fund."

## Calibration

Use the whole range. If most postings in a batch land on 6 or 7 you are hedging, and a rubric
that returns 7 for everything tells him nothing.

Score the same posting the same way twice. A random sample is re-scored each run and compared,
and a mean movement above 1.0 on either axis raises an instability warning in his email.

Judge only what the posting says, plus what is common knowledge about the employer. Do not
invent responsibilities the posting does not mention.

A posting arriving with a flag such as UNCLEAR TERM, UNCLEAR COMMITMENT or UNCLEAR LOCATION
already carries that caveat to him in the email. It is not your job to price it in, and doing
so would penalize the posting twice.

## The reason field

One sentence, at most 200 characters. Name the specific thing in the posting that decided the
fit score. Do not restate the job title, do not repeat the numbers, and do not hedge.

Good: "Builds internal LLM agents for the investment team, which is the exact overlap of the
AI and institutional investing experience."

Bad: "This is a good fit for the candidate given his background and interests."

## Examples from his own labels

Labeled examples are appended below this rubric when any exist: his most recent postings marked
interested and his most recent marked not interested, with whatever he wrote in his own words.
Any explicit score override he has written comes first and carries the most weight.

Those examples are ground truth about his taste and should move your scores on similar
postings. They do not override anything stated explicitly above. Early on there will be few
examples or none, which is expected; fall back on the anchors.

## Settings the code reads

These are parsed from this file, never hardcoded. They are here so that changing a tier
boundary stays an edit to the rubric. Report only fit, reach and the reason; everything below
is applied afterwards in code.

```toml
[scores]
min = 1
max = 10

# Tier is derived from BOTH scores since 2026-10-20. Bands are matched in tier
# number order and a posting takes the first band it clears: fit at or above
# min_fit AND reach at or above min_reach. A band with no min_reach accepts any
# reach. A posting that misses a band on either axis falls through to the next.
# tools.rubric_check prints the full 10 by 10 grid and fails if any pair lands
# in no tier or if a band can never be reached. delivery is read by the Milestone 7 email logic:
#   daily   the daily digest
#   sunday  the Sunday roundup
#   never   stored in SQLite and never emailed
#
# Why reach is in the tier. On 2026-10-20 the owner retargeted the agent from
# "roles I'd most want" to "roles I'm most likely to land": interviews and
# offers are now the objective. Until then a fit 9 frontier-lab internship with
# reach 2 was tier 1 and sat in the daily email beside roles he could actually
# win. Now tier 1 is good fit he can realistically get, and a high-fit long
# shot drops to tier 2, the Sunday roundup, carrying the REACH label.
[[tier]]
number = 1
min_fit = 7
min_reach = 6
delivery = "daily"

[[tier]]
number = 2
min_fit = 6
# Moved off the daily email so that only the roles most worth applying to
# interrupt the owner. Tier 1 is that set;
# tier 2 is the good-but-not-urgent band and it collects into the Sunday
# roundup, where he reads it in one sitting instead of four times a week.
# Since 2026-10-20 it also holds every fit 7 to 10 role that missed tier 1 on
# reach, so it is where the long shots worth a look are.
delivery = "sunday"

[[tier]]
number = 3
min_fit = 4
delivery = "sunday"

[[tier]]
number = 4
min_fit = 1
delivery = "never"

[reach]
# A posting that gets emailed with reach at or below this carries the `reach`
# flag, which prints as REACH so the stretch is visible before he clicks.
#
# 5, raised from 4 on 2026-10-20 to sit one below tier 1's min_reach. A fit 9
# role with reach 5 now misses tier 1 on reach alone, and without the flag it
# would arrive in the Sunday roundup looking like an ordinary tier 2 posting
# with no hint of why it was held back. Keep this at tier 1's min_reach minus
# one if either moves.
flag_at_or_below = 5

[[tier_cap]]
# Added 2026-09-25 at the owner's instruction: at vehicle and autonomy employers,
# top tier is for AI only. When it was added, step 2 of the engineering section
# scored non-AI vehicle engineering 7 to 8, which reached tier 1 at 8; this
# holds those roles to best_tier instead, while an AI or ML role there is judged
# like any other.
#
# Kept on 2026-10-19 when the owner removed the vehicle, robotics, defense and
# aerospace domain preference entirely. That change scores non-AI engineering
# there 3 to 4, so this cap and the two robotics caps below rarely bind now.
# They stay as a backstop against the model drifting back up, and they cost
# nothing when they do not fire.
#
# Deterministic on purpose, and applied after the model answers, so the model's
# own score is still stored unchanged and the cap is visible as the only reason
# the tier differs. The owner's own fit_override is never capped.
#
# unless_title is matched against the posting title. Entries of three letters
# or fewer match as whole words, so "ai" never catches "aircraft"; longer ones
# match as a word-start prefix, as in sources/prefilter.toml.
category = "vehicles-autonomy"
best_tier = 2
unless_title = [
    "ai", "ml", "ai/ml", "machine learning", "deep learning",
    "artificial intelligence", "llm", "nlp", "vlm", "computer vision",
    "perception", "reinforcement learning", "neural", "foundation model",
    "embodied", "generative", "data scien",
]

[[tier_cap]]
# Added 2026-09-25 at the owner's instruction: robotics is not tier 1 any more,
# because he has no robotics experience. Two halves. This one holds a role with
# robotics in its TITLE to tier 2 at any employer, with no AI exemption, since a
# robot learning role still asks for robotics experience. "robotic" rather than
# "robot" so Tesla's "Robotaxi" roles, which are vehicle work, are not caught.
title_has = ["robotic", "mechatronic", "humanoid"]
best_tier = 2

[[tier_cap]]
# The other half: at a robotics employer (category "robotics" in
# sources/companies.toml, which includes Waymo, Zoox and Nuro) only AI or ML
# work reaches tier 1, the same rule as the vehicle employers above.
category = "robotics"
best_tier = 2
unless_title = [
    "ai", "ml", "ai/ml", "machine learning", "deep learning",
    "artificial intelligence", "llm", "nlp", "vlm", "computer vision",
    "perception", "reinforcement learning", "neural", "foundation model",
    "embodied", "generative", "data scien",
]

[routing]
# Stage B scores every prefilter survivor with the cheap model. A posting goes
# on to Stage C and the expensive model when EITHER of these is true: the two
# scores together clear stage_c_min_combined, or fit alone clears
# stage_c_min_fit. The second exists so a high-fit long shot is never decided by
# the cheap model just because its reach was low. Raise either to cut spend.
#
# 13, raised from 12 on 2026-11-03 to cut Sonnet spend, which is most of the
# ranking bill. 13 is the lowest combined score tier 1 can have (fit 7, reach 6),
# so a posting the cheap model already places below tier 1 is no longer sent to
# the expensive model just to confirm it. Of the 517 postings Sonnet scored from
# 2026-10-12, the 72 that finished at exactly 12 went 71 to tier 2 and 1 to tier
# 3, and none reached tier 1 below 13. stage_c_min_fit is unchanged, so a fit 8
# long shot still gets the expensive read whatever its reach.
#
# stage_c_min_fit 9, raised from 8 on 2026-11-10 at the owner's instruction to cut
# spend again. Of the 154 postings Sonnet scored from 2026-11-04 to 2026-11-10,
# 52 finished at a combined 12 or below. Those can only have been sent on the
# fit rule, and none reached tier 1. A fit 8 posting with low reach lands in
# tier 2 whichever model scores it, so the expensive read was only choosing
# between tier 2 and tier 3, both Sunday roundup. stage_c_min_combined stays at
# 13 on purpose, so every posting heading for the daily email still gets the
# expensive model's confirmation.
stage_c_min_combined = 13
stage_c_min_fit = 9

[queue]
# Which surfaced postings the ranker is willing to spend on, added 2026-09-20.
#
# Before this the ranker read the whole backlog oldest first, which is right when
# the backlog is small and wrong when it is not. It had been paused since
# 2026-08-12 and the queue had grown to 2,349, so the first thing an unpause did
# was spend the entire month's budget re-reading August.
#
# The owner chose to score forward rather than backward on 2026-09-20. New
# postings arrive every day and old ones close on their own, so a posting that
# has sat unscored and unread for weeks is the worst use of the next dollar.
#
# max_age_days counts from first_seen. Raise it to widen the window; the whole
# remaining backlog is about $13 at the time of writing, so setting this to 999
# is a real option rather than a runaway. Set it to 0 to switch the window off
# entirely and score everything, which is the pre-2026-09-20 behaviour.
# Set to 0 on 2026-09-20, hours after being introduced at 14. The window was
# built to protect a budget against a $16-23 estimate, and the first real run
# measured the true cost at about $0.0005 a posting, roughly $0.85 for the
# entire backlog: `tools.rank_report` prices every call at full prompt cost and
# never deducts cache reads, which since both stages started caching is most of
# its answer. A window that saves under a dollar is not worth the hole it opens,
# because a posting outside it is never scored, and since the same day an
# unscored posting is also never emailed. The machinery stays because it is the
# right shape if the cost ever moves.
#
# 7, set on 2026-11-03. The cost did move. Anthropic cut the API key off from
# 2026-10-22 to 2026-11-01, nothing was scored for nine days, and 1,011 surfaced
# postings were waiting when access returned, 693 of them more than a week old.
# Every run since has spent its leftover calls on those, which is most of
# November's first $2. The owner has said a posting older than about a week is
# useless to him even at tier 1, so scoring them buys nothing. The hole the
# paragraph above describes is closed from the other side: daily.include_unscored
# in sources/email.toml went back on the same day, as CLAUDE.md rule 10 requires
# for any window, so a posting that misses scoring is still emailed while it is
# new. Labelled-interested postings are still scored at any age (below).
max_age_days = 7

# Newest first inside the window, so a capped run spends on the freshest thing
# it can see. This reverses the old oldest-first order, which existed to drain a
# backlog in discovery order and is the wrong instinct once a window exists.
newest_first = true

# A posting the owner marked interested is scored whatever its age. He has said
# yes to it, so it is exactly the thing worth spending on, and there are 21 of
# them. This is the same principle as the prefilter's label override.
always_score_labelled = ["interested"]

[budget]
# The monthly ceiling from PRD section 2 and success criterion 9, added
# 2026-09-25. Month-to-date spend is summed from the `runs` table, which records
# every run's estimated cost (Stage 0 tagging plus ranking), per UTC calendar
# month.
#
# Why it exists now. The backlog cleared at about $0.0004 a posting, but a normal
# run scores 5 to 30 postings and pays the cache write on both stages every
# time, since runs are hours apart and the cache lives five minutes. Measured on
# 2026-09-24 and 2026-09-25 that is $0.0045 to $0.006 a posting, which at 60 a
# day projects $3.50 to $10 a month, and October volume can push it past $10.
#
# warn_fraction puts a line in the digest and in `tools.health`. stop_fraction
# pauses ranking for the rest of the month. A pause never strands a posting:
# while it holds, the daily digest carries unscored postings marked NOT YET
# SCORED, which is the condition CLAUDE.md rule 10 sets for include_unscored
# being off. Raise monthly_usd here to lift it; nothing else needs editing.
#
# 20, raised from 10 on 2026-10-14 by the owner after ranking paused on 2026-10-13
# at $10.02. Most of October's spend was not the schedule: $5.55 was manual
# `tools.rank_report` runs against about $4.40 for scheduled runs. Measured
# scheduled cost is $0.0055 to $0.008 a scored posting, and the 102 postings
# waiting when it was raised were estimated at about $0.60 to clear.
#
# 10, lowered from 20 on 2026-11-03 at the owner's instruction that monthly spend
# must not approach $30. Ordinary October days ran $0.45 to $0.60, about $14 to
# $18 a month, before three cuts made the same day (scoring once a day, the
# Stage C bar at 13, the seven day queue window). This ceiling also has to trip
# before the spend limit on the Anthropic account does: that limit cut the key
# off on 2026-10-22 while this file still read $20, and an Anthropic cutoff stops
# Stage 0 tagging as well as ranking, where this pause stops ranking only.
monthly_usd = 10.0
warn_fraction = 0.8
stop_fraction = 1.0

[variance]
# The self-check in PRD section 4. Re-score this fraction of each batch a second
# time; if the mean absolute movement on either axis exceeds max_mean_delta, the
# next digest carries a one line instability warning at the top.
sample_fraction = 0.10
max_mean_delta = 1.0

[few_shot]
# How many of the owner's labelled postings are appended below the rubric, per
# label. PRD section 4 specifies 15 and 15; raised to 25 on 2026-08-15, when 25
# interested labels existed and 10 of them were being discarded on every call.
# Raising it teaches the model more about his taste and makes every ranking call
# more expensive, since these examples sit in the prompt of every single call.
# Once either side passes this number the extras are dropped again, silently, so
# check `tools.rank_report` for how many examples are actually going in.
# 35, raised from 25 on 2026-09-25. He has 31 interested labels and 21
# not_interested, so six of the interested ones were being dropped silently,
# which is the failure this setting's own comment warns about. Labels are the
# scarcest input this system has and he has stopped making new ones, so
# discarding a fifth of them to save cached tokens is the wrong trade.
per_label = 35
```
