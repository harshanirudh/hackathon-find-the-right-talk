# Project Progress Handoff

Last updated: November 9, 2026 (America/Denver)

This file is the current handoff for another AI model. Read `AGENTS.md`,
`AGENT-BRIEF.md`, `MVP-PLAN.md`, and `README.md` before making changes. The
workspace root is the project. `talk-search-starter/` is reference material
only; do not copy its implementation or include it in a commit. Keep work
inside this project; do not access personal folders.

## Product and stack

Find the Right Talk: search the KubeCon + CloudNativeCon NA 2026 program and
build an accessible, clash-free personal agenda. Python 3.11+, FastAPI, static
HTML/CSS/JS, Elasticsearch. Elasticsearch is the primary data layer. Any
fallback must be identified as fallback in API and UI. Do not silently change
the stack or claim unverified integrations.

## Implemented

- **Talk catalogue:** 478 sessions from the published main-conference schedule
  plus 28 clearly labeled illustrative samples (506 total). The schedule is a
  snapshot, not a live sync. The catalogue is indexed in Elastic Cloud and
  semantic content has been embedded with the configured Jina model.
- **Search:** Elasticsearch keyword search with title/tag/speaker weighting,
  facets, highlights, track/level/caption filters, and pagination. Optional
  hybrid mode combines lexical search and Elasticsearch semantic retrieval via
  RRF. Keyword mode is the default. Hybrid retrieval is semantic matching, not
  generated/chat answers. Observed Cloud hybrid latency was roughly 1.1–1.5s;
  a <500ms latency target has not been demonstrated.
- **Agenda:** browser-persisted selections, overlap detection using half-open
  intervals (back-to-back sessions are compatible), and compatible alternative
  suggestions.
- **Build My Day:** Elasticsearch-ranked candidates, conflict-free schedule,
  date selection, accessibility filters, and natural-language talk-count caps
  such as “maximum 5 talks.” Query constraints are removed before search. The
  chosen date is applied to both keyword and hybrid retrieval.
- **Nearby places:** Elasticsearch geo-distance query/sort over eight curated
  OSM places near the venue. The UI shows distance and OSM attribution. This
  data is limited; no prices, hours, ratings, photos, or availability are
  claimed. API/UI identify the curated OSM snapshot.
- **Observability hooks:** OpenTelemetry instrumentation and optional Dash0
  export are implemented, but a real Dash0 investigation/evidence is pending.
- The UI includes independent scrolling for search results and the day panel.

## Verification status

Last recorded verification (not rerun during this handoff update):

- `71 passed` from `.venv/bin/python -m pytest -q` (one harmless Starlette
  deprecation warning).
- `scripts/smoke.py` passed against Elastic Cloud.
- Browser smoke passed, including real hybrid retrieval, facets/highlights,
  venues, agenda conflicts, and the five-talk/date day-builder case.
- Cloud API has been used for live Elastic verification. Do not assume current
  connectivity or that a server is still running; check `/health` before demo.

The latest known Build My Day fix makes the explicit date and cap work. Its
relevance for requests like “getting started with Kubernetes” still needs
improvement: retrieved talks may not feel sufficiently beginner-oriented.

## Next work, in order

1. Improve and verify Build My Day relevance for realistic requests, especially
   beginner/introductory intent. Use the schedule metadata and Elasticsearch
   results; keep factual session selection in Elasticsearch. Add focused tests
   and update the browser acceptance case if behavior changes.
2. Rerun the test suite and live smoke checks; inspect `/health` and the UI's
   source/mode labels before the demo. Record current results here.
3. If time permits, configure Dash0 export and collect actual evidence of a
   search trace or investigation. Do not claim Dash0 use until done.
4. Gitar review evidence is pending and may require a Git remote/real integration.
   Do not claim a review occurred unless it did.
5. Rehearse the README's two-minute demo. Do not spend time on Radar/Kubernetes
   setup unless core behavior and verification are complete.

## OpenAI key decision

The user explicitly decided **not to connect the OpenAI API key to the app**.
No OpenAI request has been made. Search does not need OpenAI: Elasticsearch
handles lexical and semantic retrieval. Do not load or use the separate
`openaiapikey.env` file, and do not send requests using that key unless the user
changes this instruction explicitly.

## Useful commands

```sh
.venv/bin/python -m pytest -q
.venv/bin/python scripts/smoke.py
PLAYWRIGHT_BROWSERS_PATH="$PWD/.browser-cache" .venv/bin/python scripts/browser_smoke.py
.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Credentials belong in ignored environment files; never display or commit their
values. Do not restart Docker Elasticsearch without need: the active project
uses Elastic Cloud. Report infrastructure failures separately from tested app
behavior.
