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
- Clash-check confirmation is now a fixed, visible notification; the agenda
  panel states that selected talks are saved in this browser. Clash checks only
  validate the current saved choices; they do not change them.

## Verification status

Last recorded verification (not rerun during this handoff update):

- `71 passed` from `.venv/bin/python -m pytest -q` (one harmless Starlette
  deprecation warning).
- `scripts/smoke.py` passed against Elastic Cloud.
- Browser smoke passed, including real hybrid retrieval, facets/highlights,
  venues, agenda conflicts, and the five-talk/date day-builder case.
- Cloud API has been used for live Elastic verification. Do not assume current
  connectivity or that a server is still running; check `/health` before demo.

## Current follow-up implementation and verification

- Latest UX: no separate Saved Plans tab. Open a saved plan is a collapsed
  library beside Save in My Day. A zero-match build clears the result cards
  and shows its date/zero count; any retained earlier draft is explicitly
  identified beside the agenda. Generic main copy describes a conference
  helper while KubeCon stays the honest current dataset attribution.
- Removed manual retrieval-mode choices. The UI submits `mode: auto`: filter
  browsing and strong short literal matches use keyword retrieval; weak
  lexical matches, natural-language intent cues, or broader queries try hybrid.
  Actual mode and selection reason remain visible. Keyword degradation keeps
  pagination/total correct. No eligible filter documents returns empty results
  without claiming missing embeddings. API explicit modes remain supported.
- **114 pytest tests pass**, plus 11 subtests. Final live automatic API probes
  verified keyword for “kubernetes security”, real hybrid for “diagnose sluggish
  microservices”, and zero results for intermediate Kubernetes on Nov11.
  Updated mocked/live UI runs passed inline library, no-results state, retained
  draft identity, auto-mode payloads, keyboard, and mobile. The final combined
  `CHECK_OPENAI=1 CHECK_CLOUD_AI=1` browser rehearsal **passed**, including real
  automatic hybrid retrieval and extractive evidence, OpenAI interpretation,
  inline library CRUD, empty results, persistence, clashes, and mobile layout.
  Hosting remains prepared but undeployed; Dash0/Gitar evidence remains pending.

- Fixed the exact request “beginer friendly and medium day 1 with 5 sessions
  covering essential on kubernetes and security.” The original intent schema
  only allowed one level and dropped medium. Structured intent now preserves
  a list, maps medium to intermediate, and Elasticsearch uses a terms filter.
  Verified the official Sessionize audience categories are Beginner, Advanced,
  and Any Level (no Intermediate). Experience ranges also include explicitly
  Any Level sessions, with real labels preserved. The UI shows applied levels
  joined with “+”. Exact user request now returns **five** Nov 10 sessions
  without overlaps using real OpenAI interpretation and Elasticsearch retrieval.
  **107 tests pass**, plus 11 subtests; mocked browser multi-level display
  regression passes. Single explicitly chosen level filters remain exact.
- A dedicated UI/UX subagent implemented build → review/edit → save in My Day.
  Saved Plans is the open/delete library. Built/loaded day suggestions replace
  unrelated catalogue results, with a Browse other talks action. Planner
  controls are independent of discovery filters and collapsed by default.
  Restored drafts and save/unsaved status are explicitly labelled.
- Plans are strictly per conference date in UI and API. Cross-date additions,
  mixed-date saves/updates, wrong date metadata, and moving an existing plan
  to another date are rejected. Alternatives stay on the plan date. Clear
  starts a fresh draft without retaining saved-plan identity. Invalid/mixed
  restored drafts remain clearable; old mixed saved plans return a clear error.
- Concise judge tooltips explain planning, weighted search, facets/highlights,
  hybrid retrieval, plan storage, clashes, and geo search. They support
  focus/hover/touch and dismissal. Notifications no longer cover Save controls.
- Latest checks: **104 pytest tests pass**, plus 11 subtests. Updated live
  `CHECK_OPENAI=1` browser acceptance passed inline saving, day suggestions,
  actual OpenAI interpretation, existing search/clash flows, and mobile.
  `scripts/browser_workflow.py` passed with explicitly mocked APIs: cross-day
  rejection, stale build/pagination protection, invalid/mixed restored draft
  recovery, inline save/open/update, tooltips, and mobile. Screenshots are in
  ignored `artifacts/workflow-desktop.png` and `workflow-mobile.png`.

- A user-requested independent MVP review found and prompted fixes for hidden
  Saved Plans notifications, empty-build agenda loss, hybrid pagination,
  missing per-session dates, and the planner overwriting discovery source
  labels. These fixes are implemented with focused API/browser coverage.
- `beginner session atmost 7` now supports filter-only browsing without
  inventing a topic. Live OpenAI + Elastic verification found four beginner
  candidates on Nov 10 and three compatible picks. API/UI explain this
  shortfall with `candidate_count` and `selection_note`; they do not promise
  seven talks where compatible source sessions do not exist. Automated suite
  now has **96 passing tests**, plus 11 subtests.
  The updated `CHECK_OPENAI=1` browser acceptance passed agenda preservation,
  visible Saved Plans feedback, independent planner/discovery source labels,
  session dates, existing search/venue flows, and mobile layouts. The review
  agent's code-only follow-up found no additional MVP-blocking regressions.
- Fixed the reported exact request `beginer kubernets atmost 3 sessions`:
  normalize these common spelling variants and accept `atmost` as a count cap.
  Before the fix the live API returned 24 talks with no recognized cap/level.
  Regression coverage now checks the corrected topic, beginner filter, and
  maximum of three. Automated suite: **83 passed**, plus 11 subtests.
- Beginner phrases (“getting started”, “new to”, “first steps”, and introductory
  level words) are separated from topic keywords. Inferred beginner intent
  applies an Elasticsearch level filter before retrieval; an explicit UI/API
  level wins. The response includes `effective_level`; reasons accurately say
  “listed as beginner.” The planner uses schedule metadata, not an independent
  difficulty assessment. On Nov 10, the live Kubernetes beginner request
  returned two compatible sessions, not five: the cap is an upper bound.
- My Day, Saved Plans, and Around Venue tabs now work, with keyboard navigation.
  The agenda date reflects selected sessions rather than a fixed Nov 9 label.
- Saved Plans supports save/list/load/update/delete in a separate Elasticsearch
  index. A browser-generated 256-bit private key scopes access; only its hash
  is stored. Key copying/import is supported, deletion requires confirmation,
  and Elasticsearch failures are explicit. Plans persist until deletion; no
  expiry, account recovery, or automatic retention job exists. Lists are capped
  at 100. The README explains these limits.
- Current automated run: **81 passed**, plus 11 subtests; one Starlette
  deprecation warning. Live smoke passed against all 506 Elasticsearch sessions.
  Browser acceptance passed real Saved Plans create/load/update/delete, beginner
  planning, venues, facets/highlights, persistence, clash replacement, and mobile
  layout. A further browser run passed keyboard tab navigation and mobile
  overflow checks in all three tabs. Browser test plans were deleted by that
  acceptance flow.
- Hybrid service code is unchanged in this follow-up. Unit coverage verifies
  inferred level/date/caption filters reach hybrid retrieval; a new live hybrid
  run has not yet been performed during this follow-up.
- The app is running on localhost:8000. All file work stayed in the project;
  reference starter and separate OpenAI credentials were not accessed.

## Next work, in order

1. Evaluate beginner results with the user. The official schedule has sparse
   beginner labels on some dates; do not fill requested caps with advanced talks
   or claim beginner relevance beyond the source metadata.
2. Recheck live hybrid retrieval if demonstrating semantic mode. Saved Plans
   is implemented and tested; keep its private-key and retention limits visible.
3. Rerun the test suite and live smoke checks; inspect `/health` and the UI's
   source/mode labels before the demo. Record current results here.
4. If time permits, configure Dash0 export and collect actual evidence of a
   search trace or investigation. Do not claim Dash0 use until done.
5. Gitar review evidence is pending and may require a Git remote/real integration.
   Do not claim a review occurred unless it did.
6. Rehearse the README's two-minute demo. Do not spend time on Radar/Kubernetes
   setup unless core behavior and verification are complete.

## OpenAI key decision

The user explicitly changed the earlier decision and authorized enabling
OpenAI on November 9. The existing project key was copied safely from the
ignored `openaiapikey.env` into ignored `.env`; its value was never printed.
`OPENAI_SMART_SEARCH_ENABLED=true` is configured. Smart Search and Smart
Planning use `gpt-4.1-mini` structured Responses API output, while Elasticsearch
remains the factual retrieval layer. No OpenAI key reaches the browser.

Live verification succeeded for `beginer kubernets atmost 3 sessions`: OpenAI
returned topic Kubernetes, beginner level, and cap three; Elastic Cloud returned
two compatible Nov 10 sessions. Both source labels were verified. The opt-in
`scripts/smart_smoke.py` passed both smart planning and smart search. This was
a real API call, not a mock; inference usage may be billed.

The current automated suite has **93 passed**, plus 11 subtests. Tests cover
output validation, refusal/incomplete output, timeout, opt-out/missing key,
preserving explicit caps/filters/date, caching, and budget fallback. The UI
shows interpreted fields and basic fallback explicitly. Requests time out after
8 seconds; successful parses are cached; new calls are limited to 20/minute
per process. Search's smart checkbox is optional; planner smart mode defaults
on. Backend API requests default to smart off unless explicitly requested.
The `CHECK_OPENAI=1` browser acceptance run passed real OpenAI planning and
smart search, Saved Plans CRUD, venues, facets/highlights, persistence, clash
replacement, keyboard tabs, and mobile overflow checks.

Deployment is prepared in `render.yaml` and `DEPLOY-DEMO.md` using a free
Render Python web service with Elastic Cloud. `/health/live` is process
liveness only; `/health` and live smoke checks establish integration health.
No hosted service has been deployed or verified. The user has been asked for
a hosting preference; Render is the proposed default.

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
