# Deploy and demo

**Verified hosted demo:** https://find-the-right-talk.onrender.com/

On November 9, 2026, the hosted app passed `/health` with Elasticsearch up and
506 sessions, core smoke, real OpenAI/Elasticsearch smoke, and the combined
`CHECK_OPENAI=1 CHECK_CLOUD_AI=1` browser acceptance. Verified inline plan
CRUD, automatic hybrid retrieval and source evidence, empty results, clashes,
persistence, keyboard navigation, and mobile layout. Test plans were deleted.
The user's mixed-level Nov10 request returned five compatible sessions; the
intermediate Kubernetes Nov11 request correctly returned zero.

## Render free web service

Prepared demo branch: `feature/smart-search-demo`.
Open [Deploy this branch to Render](https://render.com/deploy?repo=https%3A%2F%2Fgithub.com%2Fharshanirudh%2Fhackathon-find-the-right-talk%2Ftree%2Ffeature%2Fsmart-search-demo)
after that branch has been pushed. The setup page asks for secret environment
values without putting them into Git.

1. Push the reviewed app changes and `render.yaml` to the GitHub repository.
   Exclude `.env`, `openaiapikey.env`, editor swap files, and the reference
   `talk-search-starter/` directory. Run pytest before the PR.
2. In Render, choose **New → Blueprint**, connect the repository, and select
   the branch containing `render.yaml`. Review that the service plan is Free.
3. Supply `ELASTICSEARCH_URL`, `ELASTICSEARCH_API_KEY`, and `OPENAI_API_KEY`
   from the project's ignored `.env` using Render's secret environment fields.
   Do not put credentials in YAML, commits, terminal output, or screenshots.
4. Deploy. The blueprint installs `requirements.txt` and starts:
   `uvicorn app.main:app --host 0.0.0.0 --port $PORT`.
   It uses Python 3.11.11, Elastic Cloud, and `gpt-4.1-mini` for intent extraction.
   It does not start Docker, reseed talks, or download local models.
5. Check `/health/live` (process alive) and `/health` (actual Elasticsearch
   state and indexed count). A green process health check alone does not prove
   Elasticsearch or OpenAI works. Expect Elasticsearch up and 506 talks.
6. Run the live checks from this project with the deployed HTTPS URL:

   ```sh
   APP_URL=https://YOUR-SERVICE.onrender.com .venv/bin/python scripts/smoke.py
   APP_URL=https://YOUR-SERVICE.onrender.com .venv/bin/python scripts/smart_smoke.py
   APP_URL=https://YOUR-SERVICE.onrender.com CHECK_OPENAI=1 PLAYWRIGHT_BROWSERS_PATH="$PWD/.browser-cache" .venv/bin/python scripts/browser_smoke.py
   ```

Render's free service sleeps after 15 minutes without inbound traffic and may
take about a minute to wake. Open the hosted page several minutes before the
demo and verify health. Hosting limits and external OpenAI/Elastic usage or
trial credits still apply. The local agenda and private plan key are scoped
to the browser origin: localhost choices do not automatically appear on the
hosted URL. Import the private key if you need existing saved plans there.

Official setup references: [FastAPI on Render](https://render.com/docs/deploy-fastapi),
[Blueprint configuration](https://render.com/docs/blueprint-spec),
[free service limits](https://render.com/docs/free).

## Optional Dash0 environment

After deploying the telemetry privacy/stage changes, add these values in
Render's secret environment settings and redeploy:

- `OTEL_EXPORTER_OTLP_ENDPOINT=https://ingress.us-west-2.aws.dash0.com`
- `DASH0_AUTH_TOKEN`: the token from ignored local configuration.
- `DASH0_DATASET=default`
- `OTEL_SERVICE_NAME=find-the-right-talk`

The MCP endpoint is `https://api.us-west-2.aws.dash0.com/mcp`; it is used for
investigation and is not needed by the running app. Never put the backend
token in browser code. `/health` reports exporter configuration, not confirmed
ingestion. Verify a request from the hosted app in Dash0 separately.

## Two-minute demo

Lead with the attendee problem: choosing a few relevant talks without opening
dozens of schedule pages or accidentally booking overlapping sessions. Explain
the technology only after showing that useful result.

Short feature tooltips explain the implementation for judges. Open only the
relevant note while presenting; the source/mode indicators remain the evidence
of what actually served a request, including any fallback.

1. **Smart planning:** select Nov 10, leave Smart Planning checked, type
   `beginer kubernets atmost 3 sessions`, then Build My Day. Show the interpreted
   topic, beginner level, cap, and real Elasticsearch source. Expect fewer than
   three when only fewer compatible sessions exist; never claim an exact count
   is guaranteed. Show no clashes and the source-based reasons.
2. **Search:** enable Smart Search for a natural request. Then disable it and
   search `observability` to show live facets and Elasticsearch highlights.
   The app chooses keyword or Elastic/Jina hybrid retrieval automatically and
   shows the actual mode and reason; no search-mode selection is required.
3. **Plans:** name and save the day beside its agenda in My Day. Expand Open
   saved plan beside Save, open the saved day, edit it, and save changes in
   that same workspace.
4. **Optional venue utility:** choose a five-minute versus ten-minute walking
   budget and Coffee or Eat & drink. Elasticsearch filters the radius/category
   and returns nearest places first. The current eight-place snapshot produced
   five results within 400 m and eight within 800 m during verification. This is a
   small convenience near The Shop hackathon demo venue, not live business
   availability or a claim that this is the KubeCon conference venue.
5. Mention Dash0/Gitar only if real evidence has subsequently been collected.

## What actually demonstrates Elasticsearch

- Weighted search, query-time filters, live facets, and highlights over 506
  indexed sessions; the UI shows the real source and actual retrieval mode.
- Natural-language retrieval combines lexical and Elastic/Jina semantic
  branches with RRF. Do not claim zero keyword matches for a phrase without
  measuring the current catalogue; the official snapshot changed those counts.
- Date and experience filters apply before selecting a personal day. Python
  handles interval compatibility and selection; Elasticsearch supplies sessions.
- Saved days live in a separate Elasticsearch index. Nearby places use real
  geo-distance filtering/sorting. Seeded snapshot data remains snapshot data;
  dynamic query behavior and useful attendee choices are the evidence.

## Recovery during the demo

- OpenAI failure: the UI explicitly shows basic interpretation. Uncheck smart
  mode and use `kubernetes max 3`; do not present this as OpenAI success.
- Elasticsearch failure: the UI labels fallback. Check the Cloud endpoint,
  key permissions, and availability; do not present fallback as Elasticsearch.
- Keep localhost:8000 available as a backup. A local demo is not evidence of
  hosted deployment success.
