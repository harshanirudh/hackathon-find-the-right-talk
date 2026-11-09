# Find the Right Talk — MVP scope

## Product promise

Turn an attendee's interests into a useful, accessible, clash-free conference
day, with transparent Elasticsearch search and editable personal choices.

## Required features, in delivery order

1. **Search foundation:** an official 2026 KubeCon schedule snapshot plus 28
   clearly labelled illustrative samples;
   FastAPI; Elasticsearch `talks` index; keyword search with boosted title,
   tags, and speaker fields; track, level, and captioned filters; health
   endpoint reporting connectivity and actual indexed count.
2. **Personal agenda:** add/remove sessions, persist choices in the browser,
   detect overlapping intervals, and offer up to three related replacements
   that fit the remaining agenda. Back-to-back talks do not overlap.
3. **Build my day:** free-text interests produce relevant sessions in time
   order, with zero overlaps and a truthful reason for each choice. Empty
   input yields a helpful validation error. Respect accessibility filters.
4. **Accessible demo UI:** responsive search and day timeline, labelled form
   controls, keyboard access, readable contrast, accessibility notes per
   session, loading/empty/error states, and a visible data-source indicator.
5. **Operational evidence:** structured search logs and OTEL traces/metrics,
   optional Dash0 export using environment configuration, documented latency
   SLO and a repeatable demo. Only claim a Dash0 investigation or Gitar review
   after it actually happens.

## Definition of done

- A browser can search, filter, build a day, edit it, and resolve a conflict.
- A real Elasticsearch instance indexes the published schedule and powers searches.
- Automated tests cover ranking/query construction, filters, API validation,
  boundary times, clash handling, replacement validity, and generated days.
- An integration check verifies actual Elasticsearch indexing and search;
  unit tests alone do not establish that the integration works.
- README includes installation, seed/start/test commands, environment setup,
  limitations, and a two-minute demo script.
- No credentials or reference-starter implementation are committed.

## Demo sequence

1. Build a day for “kubernetes, security, beginner”; show reasons and no clashes.
2. Search “observability”; show the Elasticsearch source and accessibility filter.
3. Add simultaneous talks; replace one with a compatible recommendation.
4. Show real Dash0 investigation and Gitar review evidence if configured.

## Deferred until core passes

Authentication, multi-user persistence, Kubernetes/Radar, and calendar export.
Keyword search must not be described as semantic search. Greedy scheduling is
not a claim of a globally optimal agenda.

## Initial environment findings

- New workspace has no root Git repository or remote configured.
- Default `python3` reports 3.9.12; locate/install a suitable runtime.
- Docker CLI exists, but this agent session cannot access the Docker socket.
  Resolve runtime access or use an explicitly configured Elasticsearch Cloud
  endpoint before claiming the primary integration is demo-ready.
- Starter use permission is unknown: rebuild independently per agent brief.

## Verified after full session access

- Fixed Elasticsearch 8.15 bundled-JVM SIGILL with the Compose SVE workaround.
- Elasticsearch healthy; 28 sample talks indexed; live smoke check passes
  using `source: elasticsearch` for search, filters, day building and agenda.
- All 23 automated tests pass (no dependency skips).
- Chromium browser check passes: search, captions, generated day, agenda
  persistence, conflict replacement, no JavaScript errors, and mobile overflow.
- Desktop/mobile screenshots saved to ignored `artifacts/`.
- Dash0 export and Gitar review evidence remain pending; no claims of usage.

## Next milestone: local AI and hybrid search

Authorized after core verification. Keep the existing working keyword demo.

- Backend task: Ollama embeddings, Elasticsearch dense vectors, lexical/vector
  fusion, explicit degradation, optional grounded Llama explanations.
- UI task: keyword/hybrid selection, actual search-mode display, explain-match
  interaction, preserve independent scrolling and accessible controls.
- Test task: new boundary/failure tests and updated browser acceptance checks.
- Main agent: project-scoped local runtime, model downloads, documentation,
  embedding backfill, real retrieval checks and latency measurement.

Use EmbeddingGemma and Qwen2.5 1.5B (the smaller generation model selected after the initial Llama proposal). Do not train models, require a paid API,
or mount personal folders. Docker uses CPU on this Mac; measure latency.
Do not claim semantic retrieval until real vectors are indexed and queried.

## Verified Elastic Cloud path

The user selected the hackathon-provided Elastic Cloud/Jina route instead of
local model downloads. The optional Ollama image download was cancelled;
no native model installation or personal-folder access is required.

- Cloud Elasticsearch 9.7 project authenticated; secrets remain in ignored env files.
- All 28 sample talks indexed and semantic content populated using
  `.jina-embeddings-v5-text-small`.
- Real hybrid retrieval uses native Elasticsearch RRF, with filters on both
  keyword and semantic branches. “diagnose sluggish microservices” returns
  zero keyword results and relevant hybrid results.
- Observed hybrid query latency roughly 1.1–1.5 seconds; the earlier 500 ms
  latency objective is not demonstrated for this Cloud semantic path.
- Browser checks pass for hybrid search, literal source evidence, filters,
  day building, persistence, conflict replacement, and mobile overflow.
- All 63 automated tests pass. Main demo restarted on port 8000 with Cloud config.
- Source evidence is extractive, not a generative answer. No paid completion
  calls made. Dash0/Gitar evidence remains pending.

## Current official schedule catalogue

- Fetched 478 main-conference sessions for November 10–12 from the Sessionize
  API linked by the CNCF End User Community page; each record includes its
  official schedule URL. The JSON is a dated snapshot, not a live sync.
- Added these alongside, without deleting, the 28 labeled illustrative samples.
  Accessibility values missing from the public schedule remain unknown in UI.
- The combined 506 records are indexed in Elastic Cloud and all have Jina
  semantic content. The UI offers four query examples and loads results 24 at
  a time; clicking a session opens its official listing.
- Verified hybrid query “tracing observability OpenTelemetry” returned relevant
  sessions including “Tracing at Scale” with `mode: hybrid` and Elasticsearch
  as source. Cloud latency varies; one request timed out and correctly
  degraded to keyword mode. This is not a sub-500 ms latency claim.
- Hybrid day building produced 16 scheduled sessions without overlaps in one
  live run; one transient Cloud timeout caused that run to use keyword mode.
- All 63 tests and the browser flow pass, including real hybrid mode, source
  evidence, pagination, agenda persistence, conflict replacement, and mobile
  layout. Dash0/Gitar evidence remains pending.

## Follow-up brief: completed steps 1–3

- Added an `Around the venue` section for The Shop Workspace (350 E 400 S).
  It queries the `places` index with geo-distance filtering and ascending
  Elasticsearch geo sort; cards show measured distance, estimated walk time,
  address, and an OpenStreetMap link.
- The primary Overpass request returned HTTP 502 and two mirrors timed out.
  Used eight real nearby OSM features verified from Photon’s OSM-backed search
  (object IDs and coordinates are recorded in `scripts/fetch_places.py`). The
  API reports Elasticsearch as the data source and identifies this as curated
  fallback data. OSM attribution is visible in the UI. No business ratings,
  prices, hours, availability, or photos are shown.
- Talk reseeding now uses partial updates, preserving `semantic_content`.
  All 506 talks were re-embedded after the earlier full-document reseed.
- `GET /api/search` now returns Elasticsearch facets for track, level, and
  captioned sessions plus highlight fragments; the UI displays live counts and
  restores only escaped `<mark>` tags from Elasticsearch output.
- Live venue API returned 2 hotels, 4 restaurants, and 2 cafes, all sourced
  from Elasticsearch and sorted by distance. Live “observability” search
  returned 10 track facets, 4 level facets, 2 captioned buckets, and title /
  description highlight fragments.
- 71 tests pass. Browser acceptance passes for venue filters, live facets,
  Elasticsearch highlights, real hybrid search and evidence, agenda conflicts,
  and mobile layout. Autocomplete and similar-talk recommendations are
  deferred per the brief’s cut line; Dash0/Gitar remain pending.

## Build My Day cap and date fix

- “Maximum 5 talks” (also “max 5”, “up to five”, and similar forms) is parsed
  as a count limit and removed from the search terms. Common filler words such
  as “with” no longer count as interests.
- The UI selects one conference date (Nov 10–12); the same half-open local-day
  range filters keyword and hybrid retrieval before conflict-free selection.
- Reproduced the original phrase against Cloud: it returned 37 talks across
  several dates. After the fix, selecting Nov 10 returns exactly 5 talks, all
  on Nov 10, with no overlap. Automated tests now cover cap parsing and the
  half-open date filter.
