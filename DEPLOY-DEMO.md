# Deploy and demo

The local app and real OpenAI/Elastic Cloud path have been verified. A hosted
deployment has not yet been created or verified.

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

## Two-minute demo

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
4. **Venue:** show Stay and Eat & drink; distances come from Elasticsearch geo
   sorting over the visibly labelled curated OSM snapshot.
5. Mention Dash0/Gitar only if real evidence has subsequently been collected.

## Recovery during the demo

- OpenAI failure: the UI explicitly shows basic interpretation. Uncheck smart
  mode and use `kubernetes max 3`; do not present this as OpenAI success.
- Elasticsearch failure: the UI labels fallback. Check the Cloud endpoint,
  key permissions, and availability; do not present fallback as Elasticsearch.
- Keep localhost:8000 available as a backup. A local demo is not evidence of
  hosted deployment success.
