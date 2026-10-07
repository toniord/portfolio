A personal morning brief that is read-only by construction: code rejects any Google token with a
scope beyond read-only Calendar and Gmail, Claude sees email metadata and never bodies, and every
model call falls back to rules. At 6 AM it builds one local page from weather, five calendars,
two Gmail inboxes, reports from my other agents and the news, and at 7 it emails a digest.
Claude Haiku 4.5 triages email in batches of 10, and Claude Opus 5.5 rates each event's lead
time, then ranks up to seven Pressing actions using my feedback. Work meetings reach only the
lead-time call, never the ranking. 126 offline tests.

Python 3.12, uv, launchd, Gmail and Google Calendar APIs, Open-Meteo, NYT API, Claude API
(Haiku 4.5, Opus 5.5), Tailscale.
