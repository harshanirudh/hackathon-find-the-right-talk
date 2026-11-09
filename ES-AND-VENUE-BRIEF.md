# FOLLOW-UP BRIEF — Around the Venue + Elasticsearch features
# (paste this to Claude Code / Codex, in ~/hackathon, after UI polish)

You are continuing the Find the Right Talk hackathon app, Mon Nov 9, 2026,
9 AM-7 PM MST, in ~/hackathon. Read AGENT-BRIEF.md, MVP-PLAN.md and
UI-POLISH.md first. Do NOT redo finished work. Do NOT change the core
search/agenda/Build My Day logic unless a step below says so.

## Where things stand (verified, do not re-claim otherwise)

- FastAPI + static frontend, running at http://localhost:8000
- Elasticsearch is CLOUD, not local Docker: Elastic Cloud 9.7, configured
  via ignored env files (ELASTICSEARCH_URL, ELASTICSEARCH_API_KEY,
  ELASTICSEARCH_SEMANTIC_PROVIDER=elastic,
  ELASTICSEARCH_INFERENCE_ID=.jina-embeddings-v5-text-small).
  Local Docker Elasticsearch is STOPPED / not the demo source. Do not
  restart it, do not re-seed local ES.
- `talks` index: 28 talks, keyword multi_match (title^3, tags^2, speaker^2,
  description^1), filters track/level/captioned, hybrid search with native
  Elasticsearch RRF + semantic_text, 63 tests pass.
- Hybrid latency on cloud is ~1.1-1.5s. Do NOT claim a 500ms SLO for
  hybrid. Keyword is fast; hybrid is ~1s and smarter — say that.
- Dash0 export and Gitar review evidence are still PENDING — do not claim
  them. UI polish (UI-POLISH.md) is a separate prompt; do it first if it
  is not done yet.

## Goal of this brief

Add ONE new section, "Around the venue", covering before/during/after the
conference, AND make the Elasticsearch search visibly smarter, using named
Elasticsearch features the judges can see on screen. No Google Cloud,
no Google Maps API, no new paid service, no new API key.

## Cut line — read this first

Do the steps in order. If it is after 3 PM, or Dash0/Gitar evidence is
still undone, do ONLY steps 1-3, then stop and rehearse the demo.
Steps 4-5 are nice-to-have. Never sacrifice a working demo for step 4-5.

## Step 1 — Around the Venue with geo search (~45 min, highest priority)

Venue: The Shop Workspace, 350 E 400 S, Salt Lake City.
Coordinates: lat 40.76032, lon -111.88099. Radius: 1000m, walking.

Data source: OpenStreetMap Overpass API — free, NO API key.
Endpoint: https://overpass-api.de/api/interpreter
Query (Overpass QL, timeout 25, POST with a non-browser User-Agent,
e.g. "find-the-right-talk-hackathon"):
  [out:json][timeout:25];
  (
    node["tourism"="hotel"](around:1000,40.76032,-111.88099);
    way["tourism"="hotel"](around:1000,40.76032,-111.88099);
    node["amenity"~"restaurant|cafe|bar|pub"](around:1000,40.76032,-111.88099);
    way["amenity"~"restaurant|cafe|bar|pub"](around:1000,40.76032,-111.88099);
  );
  out center;

Rules:
- Fetch ONCE at seed time (a `scripts/fetch_places.py` or in `app.seed`),
  store the result in Elasticsearch, and demo FROM Elasticsearch.
  NEVER call Overpass live during the demo — the public instance is
  volunteer-run, slow, and rate-limited (2 concurrent slots per IP).
- If Overpass fails or returns <5 places, fall back to a small seeded
  list of ~8 real nearby places you verify by name in the code comments,
  labelled as a curated fallback in the README, and keep the app working.
- Fields per place: id, name, category (hotel / restaurant / cafe /
  bar), address (if OSM has one, else ""), website (if OSM has one),
  lat, lon. NO ratings, NO prices, NO photos, NO availability —
  OpenStreetMap does not store them. Never invent them.
- Attribution, visible in the UI footer of this section:
  "© OpenStreetMap contributors".

Elasticsearch:
- New index `places`, mapping:
  name: text, category: keyword, address: text, website: keyword,
  location: geo_point
- Seed it from the Overpass result (or fallback list).
- Endpoint: GET /api/places?category=&radius_m=1000
  Query: geo_distance filter on `location` from the venue point,
  sort by _geo_distance ascending, size 50.
  Response: {places: [...], source: "elasticsearch", total: N}
  Each place includes distance_m (computed by ES sort, or haversine
  in Python — use the ES sort value) and walking time = distance_m / 80
  metres per minute, rounded up.
- UI: a new "Around the venue" tab/section, below Build My Day.
  Three chips: Stay / Eat & drink / Coffee. Each place card shows
  name, category, distance + walking time, address, and a link
  "Open in OpenStreetMap" (https://www.openstreetmap.org/?mlat={lat}&mlon={lon}).
  No map tiles, no Google Maps link, no booking button.

Verify: curl /api/places returns source elasticsearch, places sorted
by distance ascending, at least 5 places, no invented ratings/prices.

## Step 2 — Facets / aggregations (~30 min)

- In GET /api/search, add an Elasticsearch `aggs` block alongside the
  query: terms aggregations on track, level, and accessibility.captioned.
  Return them as `facets: {track: [{key, doc_count}], level: [...],
  captioned: [...]}`.
- UI: show the count next to every filter option, e.g. "Kubernetes (12)",
  "Beginner (9)", "Captioned (14)". Counts must come from the live
  aggs response, never hardcoded. Update counts when the query changes.

## Step 3 — Highlighting (~15 min)

- In GET /api/search, add `highlight: {fields: {title: {}, description: {},
  tags: {}}, pre_tags: ["<mark>"], post_tags: ["</mark>"]}`.
- UI: render the highlighted title/description from the ES response
  (sanitise: only <mark> tags are allowed through, escape everything else).
  When the user searches "observability", the word lights up in lime
  (#d9edaa, the existing <mark> colour). Do NOT do highlighting in
  JavaScript by string-matching — it must come from Elasticsearch.

## Step 4 — Autocomplete / suggester (~30 min, only if steps 1-3 done)

- Add a `completion` field `suggest` to the talks mapping, populated
  from title + tags + speaker at seed time.
- Endpoint: GET /api/suggest?q=kub — Elasticsearch suggest query on
  `suggest`, size 5. Return {suggestions: ["Kubernetes Without the Jargon", ...]}.
- UI: a dropdown under the search box as the user types (debounce 200ms),
  clicking a suggestion runs the search. No suggestion = no dropdown,
  never a fake list.

## Step 5 — Similar talks (~30-45 min, only if steps 1-4 done)

- On each talk card add a "More like this" button.
- Endpoint: GET /api/talks/{id}/similar — kNN query against the
  talk's existing embedding / semantic_text (reuse the hybrid vector
  already indexed, do NOT re-embed at request time), size 3, excluding
  the talk itself. Return {talks: [...], source: "elasticsearch",
  mode: "hybrid"}.
- If no vector exists for that talk, return a clear degraded message
  and hide the button — never fall back to a keyword guess and call
  it similar.

## Demo script update (2 minutes, use this order)

1. Hybrid search live: "diagnose sluggish microservices" — zero keyword
   results, relevant hybrid results. Say hybrid is ~1s on cloud.
2. Around the venue: "Stay" chip — nearest hotel, distance + walking
   time, all from Elasticsearch geo search. Then "Eat & drink".
3. Facets + highlighting: search "observability", show counts and the
   highlighted word.
4. Build My Day for "kubernetes, security, beginner" — clash-free day.
5. Dash0 / Gitar evidence ONLY if actually collected — never claim it.

## Rules for this build

- No Google Cloud / Google Maps API key, no new paid service.
- No secrets in the repo. Tokens in `.env` only (gitignored).
- No invented ratings, prices, photos, opening hours, or availability.
- Search must query Elasticsearch first. If ES is down, the API must
  say "source": "fallback" — never demo the fallback as the product.
- `pytest -q` passes before every PR. One small PR per step above.
- Keep the working demo alive at all times. Core first, polish second.

## Verify before you finish

1. `pytest -q` passes (add tests for: geo sort ascending, facet counts
   match the index, highlight tags present, suggest returns ≤5, similar
   excludes the source talk).
2. `curl localhost:8000/health` shows elasticsearch up, talks_indexed 28.
3. `curl 'localhost:8000/api/places?category=hotel'` — source
   elasticsearch, sorted by distance, ≥1 hotel.
4. Search "observability" in the browser: facets show counts, matched
   word is highlighted, source pill shows real Elasticsearch ms.
5. Around the venue tab works with the app server running on cloud
   config and local Docker Elasticsearch stopped.
