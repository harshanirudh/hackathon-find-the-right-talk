# Project instructions

Build Find the Right Talk for the November 9, 2026 WeMakeDevs hackathon.
Read AGENT-BRIEF.md and MVP-PLAN.md before making changes.

- The root workspace is the new project. `talk-search-starter/` is reference
  material only; do not copy its implementation or commit its contents.
- Use Python 3.11+, FastAPI, static HTML/CSS/JavaScript, Elasticsearch 8.15,
  and optional OpenTelemetry export to Dash0. No frontend build step.
- Finish and verify core features before optional integrations or polish.
- Elasticsearch is the primary data layer. Any fallback must be explicit in
  API responses and visible in the UI; never describe it as Elasticsearch.
- Keep credentials in gitignored `.env`; do not print their values.
- Use small feature branches/PRs when a remote is available. Run pytest
  before each PR. Never invent reviews, deployment results, or telemetry.
- Preserve back-to-back sessions as compatible; intervals are half-open.
- Report infrastructure blockers and distinguish tested behavior from
  unverified integrations. Do not silently substitute a different stack.
- The user permits delegation. Keep tasks bounded to conserve tokens and
  avoid multiple agents editing the same files.
