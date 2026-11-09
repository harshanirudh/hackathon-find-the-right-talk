# AGENT BRIEF — Find the Right Talk (paste this to Claude Code / Codex)

You are building a hackathon project TODAY, Mon Nov 9, 2026, 9 AM–7 PM MST,
in this empty repo. Solo developer, first hackathon. Build everything in
this repo NOW, during the event, in small steps. Do not claim work done
before the event. Ask the organisers at the 10 AM kickoff if a boilerplate
starter is allowed — until they say yes, treat the local reference starter
(see "Reference" below) as a DESIGN REFERENCE ONLY. Do not copy its files
wholesale into this repo. Rebuild the features here, in this repo, now.

## The idea (the organisers' brief, not a separate invention)

Theme: make conferences better.
Primary track: Elasticsearch — "Find the Right Talk" ($4,000)
Second track: Dash0 — "Stop Flying Blind" ($4,000)
Process track: Gitar — "Never Merge Broken" ($4,000)
Optional, only if time: Radar — "AI SRE" ($4,000)
Merge Forward angle: accessibility.

App: conference-talk finder + personal agenda builder.
Problem: hundreds of talks, overlapping slots, you pick the wrong one.
- Search talks in plain language, e.g. "beginner Kubernetes security"
- Filter by track, level, captioned-only
- Add talks to a personal agenda; it flags time clashes and suggests a
  same-track talk that fits in a free slot instead
- "Build my day" (catchy headline feature, inside this same app): type
  2-3 interests and it builds a whole clash-free day for you in one click

## Stack — keep it simple

Python + FastAPI, static HTML/JS frontend (no build step), Elasticsearch
via docker-compose (single node) as the CORE data layer, OpenTelemetry
to Dash0. Plain classes/functions only — NO abstract classes. Simple,
readable code. Python 3.11+, Docker, git.

## Build order — one small PR per feature, in this order

1. PR 1 — Core: FastAPI app + Elasticsearch index `talks` + seed 28
   realistic KubeCon-style talks (title, speaker, track, level, start/end,
   room, description, tags, accessibility: captioned / step-free /
   plain-language-summary). `GET /api/search?q=` — ES multi_match,
   title boosted x3, tags x2, speaker x2, description x1. Filters as ES
   term filters. `GET /health` must report elasticsearch up/down and
   talks indexed. `docker-compose.yml` for ES 8.15 single-node, no security.
   Verify: `docker compose up -d`, seed, `curl localhost:8000/health`
   shows elasticsearch up, 28 talks, search "kubernetes" returns results.
2. PR 2 — Agenda: `POST /api/agenda {"talk_ids": [...]}` — clash detection
   (back-to-back, one ends 11:15 next starts 11:15, is NO clash), and
   suggest up to 3 same-track/tag alternatives that do NOT clash with the
   rest of the agenda. Simple frontend: search box, filters, Add to agenda,
   Check for clashes. Verify with pytest — tests for ranking, filters,
   clash detection, alternatives. `pytest -q` must pass.
2b. PR 2.5 — "Build my day" (headline feature, do right after PR 2):
   `POST /api/build-my-day {"interests": "kubernetes, security, beginner"}`
   — run the Elasticsearch search for those interests, rank by relevance,
   then greedily pick the best talk per time slot, skipping any talk that
   overlaps an already-picked one, so the result is a whole day with zero
   clashes. Return the picked talks in time order, each with a one-line
   "why this talk" reason, e.g. "matches your interest in security,
   captioned, no clash". UI: one input + "Build my day" button above the
   search results, result shown as a day timeline. Verify with pytest:
   no overlaps in the returned day, every pick matches at least one
   interest, and an empty-interest request returns a clear error, not a
   crash. ~30-45 min, no new service. If PR 1-2 are not done, skip this
   and come back to it — it depends on search + clash logic.
3. PR 3 — Accessibility: captioned-only filter in UI + API, accessibility
   notes shown on every talk card. This is the Merge Forward angle.
4. PR 4 — Dash0 find-and-fix: OTEL instrumentation on FastAPI, every
   search logged with query, source, latency ms. Dashboard idea: search
   latency p50/p95 + count by source + error rate. SLO: 95% of searches
   under 500 ms. During the day, use Dash0 Agent0 / MCP to find the
   slowest search query, fix the real cause, land the fix as this PR,
   show before/after latency in the demo. Never put the Dash0 token in
   code — `.env` only, gitignored.
5. PR 5 — ONLY if time: hybrid/vector search spike (dense_vector + kNN
   next to multi_match). Do NOT fake it — if it is not wired, say so.
6. PR 6 — ONLY if core is solid: k8s manifests + Radar. If Radar setup
   takes more than ~45 minutes, drop it.

## Judging — what each track checks

- Elasticsearch: ES is the CORE data layer, not a side feature. Smart
  keyword / hybrid search. Makes conferences easier.
- Dash0: depth of instrumentation (traces, logs, metrics, RUM if
  frontend), Agent0/MCP used to find AND fix something real, shown in
  the demo. Observability part of the product, not bolted on. Bonus:
  dashboard / SLO.
- Gitar: features land through PRs Gitar reviewed across the day, not
  one PR at the end. Project-aware review instructions, CI failure
  diagnosis. Keep PRs small, one feature each, tests passing.
- Radar: run on Kubernetes with Radar connected, use its UI + MCP
  throughout, run one AI investigation on a real issue, show what you
  learned.

## Demo script (2 minutes)

1. "Build my day" live — type "kubernetes, security, beginner", show
   the clash-free day it builds, then one search — "observability" —
   to show it is Elasticsearch.
2. Agenda clash — add two talks at the same time, show clash + alternative.
3. Dash0 — slowest search, cause, fix, before/after latency + SLO.
4. Gitar — one real review comment acted on.

## Rules for this build

- No secrets in the repo. Tokens in `.env` only (gitignored).
- No new build step, no new required service, without a README update.
- `pytest -q` passes before every PR.
- Search must query Elasticsearch first. If ES is down, an in-memory
  fallback is allowed ONLY as a labelled safety net — the API must say
  `"source": "fallback"` — never demo the fallback as the product.
- Keep the working demo alive at all times. Core first, polish second.

## Reference (design only — see warning at top)

Local reference starter on the developer's laptop (NOT in this repo):
`/Users/harsha/hackathon/talk-search-starter/`
Also: `HACKATHON-PLAN.md` in the same folder on the laptop, and the
planning-only repo README (`EMPTY-REPO-README.md`).

## First command to run

```bash
cd <this repo>
python3 -m venv .venv && source .venv/bin/activate
pip install fastapi "uvicorn[standard]" elasticsearch==8.15.0 \
  opentelemetry-api opentelemetry-sdk \
  opentelemetry-instrumentation-fastapi \
  opentelemetry-instrumentation-requests \
  opentelemetry-exporter-otlp-proto-http httpx pytest
docker compose up -d
```
Then start PR 1. Work in small steps, test after each one, commit often.
