# pe-research-agent

Built as pre-work for my internship at QofAI. It turns a folder of public source documents on a
private equity firm into a dossier: the firm's profile, leadership, strategy, portfolio
companies, revenue and EBITDA estimates for the private ones, and recent activity. Every
load-bearing claim carries two labels: a confidence band (high, medium or low) and a source type
(public document, public inference or private inference). A blocking audit checks the draft,
sends each problem back to the step that wrote it for one retry, and withholds the dossier if a
problem survives.

The code is not published. A sanitized copy is under review by QofAI and stays private until
QofAI approves its release. A live walkthrough is available on request.

## How it works

Eight skills, each with a written contract (input, output, scoring rules, failure modes), run
through Claude Code on Sonnet 4.6. A Python orchestrator runs them in nine phases:

| Phase | Step | Model call |
|---|---|---|
| 1 | Firm profile and portfolio inventory, in parallel | yes, read-only |
| 2 | Choose companies from the inventory (active first, then disputed status) | no |
| 3 | One portfolio company profile per company, as parallel Claude Code subagents | yes, read-only |
| 4 | Revenue and EBITDA bands per company, from public comparables (optional) | yes, no tools |
| 5 | Recent activity, taken from the firm profile | only as a fallback |
| 6 | Build the portfolio section | no |
| 7 | Confidence band and source type on every claim, one call per section | yes, no tools |
| 8 | Assemble the dossier and compare it with the previous dossier on the same firm | one comparison call |
| 9 | Audit, with one retry on FAIL | yes, read-only |

The portfolio inventory and the audit verdict come back as JSON checked against a schema, so
the company list and the pass or fail decision never depend on parsing prose.

The audit has four critical flags: a figure the firm reported about itself labeled high
confidence, a deal-pace claim without the date math behind it, a conflict between sources
resolved without saying so, and a missing section. Everything else is advisory. On a FAIL, each
critical flag goes back once to the step that wrote the content (the labeler, the firm profiler
or the company profiler), the dossier is reassembled and audited again, and the run halts with
both drafts and both audit reports if a flag remains.

Sources are matched to each company by full name and ranked before the company profiler sees
them. Below 15 source documents the run writes a sourcing gap report and puts a warning at the
top of the dossier. Every run writes its plan, log, intermediate sections and per-call spend to
its own folder, and a partial run resumes from assembly or from the audit.

## Safety

Source documents come from the open web, so every model call is treated as exposed to prompt
injection.

- Each call can read files inside the repo or has no tools at all. No call can run commands,
  edit files or browse.
- No call can reach the user's MCP servers and connectors, or load personal hooks and settings.
- Reads outside the repo are denied and logged.
- Each call and each run has a spend cap, and a live run refuses to start without an API key,
  so it never bills a personal subscription.
- No dossier is written without an audit pass.

## Evaluation

An API scorer labels 50 hand-labeled claims through the Claude API, with forced tool output for a
machine-readable band. A human scorer got 43 of 50 (86%). Each arm runs three times:

| Prompt | Source summary | Mean accuracy |
|---|---|---|
| The pipeline's own confidence contract | on | 92.0% |
| The pipeline's own confidence contract | off | 48.7% |
| Hand-written rubric summary (the first eval) | on | 80.7% |
| Hand-written rubric summary (the first eval) | off | 49.3% |

With a one-line summary of each claim's source, the pipeline's contract beats the human scorer,
and every miss is one band off. Without the summary both prompts fall to about 50%, so the input
format matters more than the rubric wording. The prompts were not tuned to this eval set.

## Example run

The sanitized copy ships a full run on an invented firm, Sample Equity Partners, built from 18
invented source documents with planted problems: two Form ADV filings with different figures, a
professional profile whose tenure dates disagree with the firm's team page, and a portfolio
page that still lists a company a later news article reports as sold. The pipeline flagged
that company as conflicting and the dossier reports both sources:

> One exit occurred within the window. Example Outdoor Holdings acquired Lakeside Paddle Co. from
> Sample Equity Partners in August 2026, according to an independent news article citing a
> statement from the buyer. (confidence: high | source: public document — The Midwest Deal
> Journal, dated 2026-08-04, independently reported with named buyer)

That run passed the audit on the first try with no critical flags, in 17 model calls for 0.90 USD.

## Testing

81 tests cover flag validation, source matching, the JSON contracts, audit retry routing and a
full pipeline run against a fake model, so they need no API key. CI runs them and a lint on
Python 3.11 and 3.12 for every change.

Python, Claude Code subagents, Claude API.
