A live group trip planner (grouptrip-planner.vercel.app) that turns one shared link and a
two-minute form per person into dates, a destination and an itinerary, in 22 seconds and $0.05
of Claude calls for a six-person sample group. A deterministic planner filters 61 destinations
on hard constraints (passports, each person's real cost against their budget, maximum flight
time), scores the rest on five weighted factors including the least-served traveler, re-ranks
the top five on Open-Meteo weather for the dates, and prices flights and hotels through SerpApi.
Claude Opus 5.5 turns free-text notes into constraints, limited by structured output to tags the
planner knows, and writes the itinerary, which gets three drafts to pass validation before a
template takes over. Every external call has a fallback, and 69 tests run offline.

TypeScript, React, Vite, Vercel Functions, Neon Postgres, Claude API, Open-Meteo, SerpApi.
