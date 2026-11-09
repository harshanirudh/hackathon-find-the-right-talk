# Find the Right Talk

A conference talk finder and personal day planner built during the November
9, 2026 WeMakeDevs Cloud Native Hackathon. The searchable catalogue combines
**478 sessions from the published KubeCon + CloudNativeCon North America 2026
main-conference schedule** with 28 clearly identified fictional demo samples.
The official-session records include abstracts, speaker names, track, audience
level, room, date/time, and links to their official listings. Accessibility
details absent from the source are shown as “not listed,” not guessed.

Search by interests, filter for accessible sessions, build a clash-free day,
resolve conflicts, compare live Elasticsearch facet counts, and see matches
highlighted by Elasticsearch. The venue section uses Elasticsearch geo search.
The current demo uses Elastic Cloud; its local Docker Elasticsearch service
is stopped.

Project repository: https://github.com/harshanirudh/hackathon-find-the-right-talk

## Elastic Cloud demo setup

The hackathon Track 4 resources recommend an Elasticsearch Serverless project
and Cloud Jina inference. The Cloud path does not require Ollama or a paid
external LLM key. Cloud inference consumes the account's applicable trial or
usage allowance; do not assume unlimited free usage.

Save the project endpoint and encoded API key in ignored `.env`:

```dotenv
ELASTICSEARCH_URL=https://your-project-endpoint
ELASTICSEARCH_API_KEY=your-encoded-api-key
ELASTICSEARCH_SEMANTIC_PROVIDER=elastic
ELASTICSEARCH_INFERENCE_ID=.jina-embeddings-v5-text-small
```

Use an inference endpoint actually available in your project. Seed the official
schedule snapshot and sample sessions, then explicitly create/backfill their
semantic field:

```sh
.venv/bin/python -m app.seed
.venv/bin/python -m app.embed
.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Select **Hybrid** in the UI and try “production AI inference on Kubernetes”,
“Kubernetes security supply chain”, or “tracing observability OpenTelemetry”.
The example buttons run these queries for you. Click **Official listing** on a
result to check its source schedule entry. Verify the response reports
`mode: hybrid`, source Elasticsearch, and the configured embedding model.
Missing inference access must produce a visible downgrade; keyword fallback is
not a semantic-search success.

Cloud recommendations use source evidence from indexed sessions. Extractive
quotes are labelled as evidence, not represented as an LLM-generated answer.
The 28 added demo samples remain fictional regardless of where they are
indexed. The KubeCon schedule is a snapshot and may change; use its live link
for current session details. Refresh the snapshot with
`.venv/bin/python scripts/fetch_kubecon_sessions.py`, then reseed and backfill
if the changed catalogue needs semantic content.

Switching providers requires changing `.env` and restarting the app. Existing
running processes do not pick up environment changes automatically. Never
replace an existing credential file with the example file.

## Around the venue

The venue is The Shop Workspace, 350 E 400 S, Salt Lake City. The app queries
the Elasticsearch `places` index for hotels, restaurants, bars, and cafes
within a walking radius, sorted by Elasticsearch geo distance. Walking minutes
are estimated at 80 metres per minute. No ratings, prices, hours, availability,
or photos are shown.

Places are fetched once with `scripts/fetch_places.py`; the application never
calls Overpass during a demo. The Overpass endpoint returned HTTP 502 during
this build, so the current index uses eight nearby OSM places curated from
Photon's OSM-backed search, visibly labeled as fallback data. Their OSM object
IDs and source coordinates are in `scripts/fetch_places.py`. The section shows
© OpenStreetMap contributors. Refresh from Overpass and reseed with:

```sh
.venv/bin/python scripts/fetch_places.py
.venv/bin/python -m app.seed
```

## Elasticsearch features

`GET /api/search` returns live terms facets for track, level, and captioned
sessions, plus Elasticsearch highlight fragments for title, description, and
tags. The UI only restores `<mark>` from those fragments after escaping all
other markup. Search results load 24 at a time.

`GET /api/places?category=stay&radius_m=1000` returns nearby hotels with
`source: elasticsearch`, distance in metres, and estimated walking minutes.

Build My Day lets you choose November 10, 11, or 12. It recognizes limits such
as “maximum 5 talks,” removes that constraint from search keywords, and returns
no more than the requested number on the selected date.

## Run locally

### Optional local AI setup

Local AI runs in a project-scoped Docker service, with models and runtime
state under ignored `.local-ai/ollama/`. It does not mount your home directory
or install a global application. The local API binds only to loopback.
On this Mac, Docker inference uses CPU; latency must be measured rather than
assuming native Apple GPU performance. Only one model is loaded at a time.

```sh
docker compose --profile local-ai up -d ollama
docker compose exec ollama ollama pull embeddinggemma
docker compose exec ollama ollama pull qwen2.5:1.5b
```

Model downloads require several GB of disk space and network access. No paid
inference API is used. Keyword search remains available without this service.
Model weights have their own licenses; they are not part of this repository.

Requires Python 3.11+. The current hackathon demo uses Elastic Cloud; do not
start Docker for this configuration. From this directory:

```sh
python3.11 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

The ignored `.env` must already contain the Cloud endpoint and API key. The
index is seeded and semantic content backfilled. Open http://localhost:8000
and check http://localhost:8000/health; it should report Elasticsearch up and
the current catalogue count. If you deliberately switch to local development,
start `docker compose up -d` and configure `.env` for localhost first.

The Compose configuration includes `-XX:UseSVE=0` in `_JAVA_OPTIONS` to avoid a
bundled-JVM `SIGILL` startup crash on affected Apple Silicon Docker hosts.
This applies to both the launcher and server JVMs; an ignore-unrecognized
option keeps the workaround portable to Intel. Elasticsearch stays on 8.15.

When Elasticsearch is unreachable, the talk UI and API explicitly label their
sample-data fallback. Venue lookup returns an error rather than claiming a
local substitute came from Elasticsearch. Browser local storage retains agenda
selections; there are no user accounts or shared agendas.

## Verify

```sh
.venv/bin/python -m pytest -q
.venv/bin/python scripts/smoke.py
curl http://localhost:8000/health
curl 'http://localhost:8000/api/search?q=kubernetes'
curl -X POST http://localhost:8000/api/build-my-day \
  -H 'Content-Type: application/json' \
  -d '{"interests":"kubernetes, security, beginner"}'
```

Unit/API tests use controlled data and mock service boundaries. Verify the
live health and search responses separately to establish real Elasticsearch
connectivity; `source` must be `elasticsearch`.

Optional browser acceptance check (keep the app running):

```sh
.venv/bin/python -m pip install --no-cache-dir playwright
PLAYWRIGHT_BROWSERS_PATH="$PWD/.browser-cache" .venv/bin/python -m playwright install chromium
PLAYWRIGHT_BROWSERS_PATH="$PWD/.browser-cache" .venv/bin/python scripts/browser_smoke.py
```

This checks search, venue geo results, live facets and highlights, caption
filtering, generated days, saved agenda choices, conflict replacement, and
mobile overflow. Screenshots go to ignored
`artifacts/`. Playwright is a verification tool, not an app dependency.

## Demo in two minutes

1. Search “diagnose sluggish microservices” in Hybrid; point out relevant
   results and the Elasticsearch source. Cloud latency varies.
2. In Around the venue, choose Stay, then Eat & drink; show distance and walk
   time from the Elasticsearch geo query.
3. Search “observability”; point out live facet counts and Elasticsearch
   highlights.
4. Build a clash-free day for “kubernetes, security, beginner”.
5. Show Dash0 or Gitar only if real evidence has been collected.

The scheduler greedily selects relevant sessions without overlaps; it does
not guarantee a globally optimal agenda. All schedule times are conference
local time (America/Denver), with offsets supplied in session timestamps.

## Sponsor evidence

Elasticsearch: demonstrate real indexed data, weighted multi-match search,
facets, highlights, hybrid retrieval, and geo filtering. Dash0: configure the
optional OTLP environment values documented in `.env.example`, then verify
ingestion before presenting it. Suggested SLO:
95% of keyword searches finish under 500 ms. Hybrid Cloud queries are slower
and do not meet that target consistently. Inspect a real query, record its
cause, apply a measured fix, and keep before/after evidence.

Gitar requires a GitHub remote and the actual integration installed there.
Land small feature PRs reviewed during development. CI is provided, but a
workflow file alone does not establish Gitar usage. Radar/Kubernetes,
autocomplete, and similar-talk recommendations remain deferred.

Never commit `.env` or tokens. Local Elasticsearch disables security for
development: keep port 9200 bound to loopback and do not expose it publicly.

See [MVP-PLAN.md](MVP-PLAN.md) for feature acceptance criteria and
[AGENT-BRIEF.md](AGENT-BRIEF.md) for the supplied build brief.
