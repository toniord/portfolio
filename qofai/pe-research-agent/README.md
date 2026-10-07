# pe-research-agent

Built as pre-work for my internship at QofAI. It produces a sourced dossier on any private
equity firm: the firm's profile, its portfolio companies, revenue and EBITDA estimates
for the private ones, and recent activity. Every load-bearing claim carries two labels: a
confidence band (high, medium or low) and a source type (public document, public inference or
private inference).

Eight skills with written contracts run under Claude Code on Sonnet 4.6, with one parallel
subagent per portfolio company and a final audit pass that critiques the dossier. An
interrupted run resumes from assembly or audit. In an eval on 50 labeled claims, adding a
one-line source summary per claim raised the API labeler from 25 of 50 correct to 39 of 49
scored (one failed on an API overload), against 43 of 50 for a human scorer.

The code is not published. A sanitized copy is under review by QofAI and stays private until
QofAI approves its release. A live walkthrough is available on request.

## How it works

The agent is split into eight skills, each with its own contract (trigger, input, output,
failure modes):

| Skill | What it does |
|---|---|
| firm-profiler | The firm-level profile |
| portfolio-discoverer | The portfolio company inventory, with status conflicts and add-ons resolved |
| portco-profiler | One portfolio company, run as a parallel subagent per company |
| private-data-approximator | Revenue and EBITDA bands for private companies, from public comparables |
| confidence-scorer | Applies the confidence rubric to every claim |
| source-typer | Applies the source rubric to every claim |
| dossier-assembler | Assembles the dossier (plain Python, no model call) |
| audit-pass | Critiques the finished dossier and flags weak claims |

A Python orchestrator runs them through Claude Code. Firm profiling and portfolio discovery run
in parallel, then one portco-profiler subagent per company, then estimates, a combined labeling
pass, assembly and the audit. Every run writes a plan and a log, and a partial run can resume
from assembly or from the audit.

The agent's instructions include the two rubrics, with worked examples of each label.

## Evaluation

An API scorer labels claims through the Claude API with a forced, machine-readable label. On a
50-claim eval set with reference labels, it got 25 of 50 right when it saw only the claim text.
Adding a one-line summary of each claim's source raised that to 39 of the 49 it scored (79.6%;
one claim failed on an API overload), against 43 of 50 (86%) for the human scorer. That closed
82% of the gap to the human. Both figures come from a single run.

Python, Claude Code subagents, Claude API.
