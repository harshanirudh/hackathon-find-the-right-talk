# Next task: Dash0 observability MVP

Implement a useful, verified observability increment in approximately **30 minutes**.
Keep the working conference planner and deployment stable. This task is about
understanding and improving real requests, not adding a decorative dashboard.

## Official track guidance

Read these before implementation:

- Resources: https://www.wemakedevs.org/hackathons/cnh/resources
- Judging: https://www.wemakedevs.org/hackathons/cnh

The Dash0 track emphasizes instrumentation depth, using **Agent0 or Dash0 MCP
to find and fix something real**, observability integrated into the product
experience, and making conferences easier. A dashboard or SLO is **bonus work**.
The resources suggest tracing an attendee assistant with OpenLIT, but do not
require replacing existing instrumentation or using OpenLIT specifically.

## Goal and demo story

Trace a real planning/search request through OpenAI interpretation, Elasticsearch
retrieval, and schedule selection. Use the resulting telemetry to investigate
an actual slow or degraded request, act on the finding, and record evidence.

Example story, only if the measurements establish it:

> We identified which stage made planning slow, used Agent0 or MCP to investigate
> the cause, changed that behavior, and measured the result on equivalent requests.

Do not invent a bottleneck, before/after measurements, token costs, or an AI
investigation. Do not manufacture a failure in the public demo to create evidence.

## Prerequisites

The user needs a Dash0 account/workspace, an OTLP HTTP ingestion endpoint, and
an ingestion token. Use hackathon-provided access or credits if available.

Expected project configuration, subject to verification against the workspace:

```dotenv
OTEL_EXPORTER_OTLP_ENDPOINT=<Dash0 OTLP base URL>
DASH0_AUTH_TOKEN=<ingestion token>
OTEL_SERVICE_NAME=find-the-right-talk
```

Keep credentials in ignored `.env` locally and secret environment fields on
the host. Never print values, commit secrets, or ask for tokens in chat. Check
whether the workspace requires an explicit dataset header and configure it
correctly. Endpoint examples are not proof that ingestion works.

## Working constraints

- Read `AGENTS.md`, `AGENT-BRIEF.md`, `MVP-PLAN.md`, and the current progress
  handoff. Inspect the current code: other feature work may have changed it.
- Work inside `/Users/harsha/hackathon`. Do not access personal folders or
  copy `talk-search-starter/` implementation.
- Inspect `app/telemetry.py` and existing request/model/search spans first.
  Extend the current setup; do not install duplicate providers or exporters.
- Preserve FastAPI, static HTML/CSS/JavaScript, Elasticsearch as the primary
  data layer, explicit fallback labels, and the current deployment.
- Coordinate with any ongoing UI/planner work and avoid overlapping edits.
- Do not add authentication, Kubernetes, Radar, or another required service.
  Radar is a separate track; organizers provide a cluster, but moving this
  app there is outside this observability increment. Auth0 is not a resource
  listed for this track.

## Required implementation

### 1. Establish real ingestion first

- Connect the existing OpenTelemetry exporter to Dash0.
- Verify that a real request produces a visible trace in the intended dataset.
- Correlate relevant logs with trace/span IDs and export useful metrics.
- Telemetry being configured, `/health` reporting export enabled, or a local
  span being created does not establish successful Dash0 ingestion.

### 2. Trace useful stages

Use a connected parent/child trace, adapting names to existing conventions:

```text
Planning request
├── OpenAI preference interpretation, when used
├── Elasticsearch retrieval for each requested day
│   └── Actual keyword / semantic / fusion stages where available
└── Schedule selection for each requested day
```

Record bounded, non-secret attributes where applicable:

- Stage duration, outcome, and sanitized error category.
- Actual retrieval mode and source, including fallback/degradation reasons.
- Conference date, candidate count, selected count, and requested session cap.
- OpenAI model and input/output token counts when the response provides them.
- Interpretation cache hits/misses; do not claim a cached request made an API call.

Preserve single-day behavior. If full-conference planning exists, distinguish
each day's work under the same request without duplicating interpretation
unnecessarily.

Never export API keys, authorization headers, private plan keys, or full
prompts/responses by default. Review existing query logging before expanding
it. Avoid sensitive or unbounded values as metric labels. Do not calculate
monetary cost without verified model pricing and actual usage data.

### 3. Include the frontend proportionately

The judging criteria mention real-user monitoring for frontend applications.
If a supported Dash0 browser integration can be added quickly without a build
step or exposing backend credentials, capture useful page/request timing or
errors. Use the appropriate browser-safe configuration, not the server token.

If frontend monitoring cannot fit the time budget, explicitly report it as
unverified or deferred. Backend HTTP traces are not browser RUM. Keep actual
fallback explanations understandable in the app; do not add an unrelated
technical dashboard to the attendee workflow.

### 4. Investigate and act

- Generate a few representative requests, including normal and degraded or
  empty-result behavior when naturally available.
- Use **Agent0 or Dash0 MCP** to investigate an observed issue or bottleneck.
- Follow the evidence. Possible areas to inspect include repeated OpenAI
  calls, redundant retrieval, cache behavior, or avoidable sequential work;
  these are hypotheses, not established bugs.
- Apply one small, justified fix if evidence supports it and time permits.
- Compare equivalent inputs, data, retrieval modes, and cache conditions.
  Separate cold and warm requests; do not attribute cache effects to another fix.
- Record the trace references, investigation, change, measurements, and limits.

Assess OpenLIT only if it quickly adds missing LLM telemetry without duplicate
spans or conflicting SDK setup. Existing manual spans are acceptable; do not
spend the window replacing instrumentation that already works.

## Acceptance criteria

1. A real request is visible in Dash0 with the correct service/dataset and
   connected stage spans.
2. Timings distinguish interpretation, retrieval, and selection. Per-day work
   is identifiable if multi-day planning is implemented.
3. Actual keyword/hybrid modes, result counts, and fallback/error categories
   can be investigated without inspecting raw secrets or prompts.
4. OpenAI usage is recorded when supplied; cached interpretation is identified
   separately from a fresh model request.
5. Missing or unavailable telemetry export does not break core app behavior.
6. Agent0 or MCP is used on real telemetry, and the investigation and resulting
   action are documented. If this is blocked or no fix is established, state
   that clearly rather than claiming track completion.
7. Any performance claim has actual before/after evidence with cache and
   request conditions recorded.
8. Relevant automated checks pass, and existing search/planning behavior still
   works. Do not inject a live outage merely to test telemetry failure handling.
9. Verify ingestion from the deployed app separately before claiming hosted
   observability works. Do not deploy untested changes or restart a concurrent
   user's process without coordination.
10. Document frontend monitoring as verified, deferred, or blocked.

## Optional bonus: dashboard or SLO

Only after ingestion and the investigation work, create one small dashboard,
saved view, or SLO showing useful service health, such as request volume,
latency, and errors/fallbacks. Distinguish keyword, hybrid, and AI-assisted
requests where practical. Do not claim the earlier 500 ms target is met by
Cloud hybrid or AI planning without measurements.

Do not let dashboard building displace the Agent0/MCP investigation.

## Time budget and cut line

- **0–5 minutes:** Inspect existing hooks, configure export, verify a first trace.
- **5–15 minutes:** Complete stage spans, attributes, logs, and metrics.
- **15–25 minutes:** Investigate real requests using Agent0 or MCP; make a
  small evidence-backed fix if feasible.
- **25–30 minutes:** Verify behavior and record evidence, blockers, and omissions.

If ingestion or account access is blocked, report the exact blocker early.
Do not spend 30 minutes building views without data. Do not invent a fix to
meet the deadline. Report partial completion honestly if the full outcome
cannot be achieved in the time available.

## Required handoff

Return a concise account of:

- Changed files and configuration variable names, never secret values.
- Tests and integration checks actually run.
- A real trace link/ID and Agent0/MCP investigation evidence, when available.
- The observed issue, resulting change, and measured result, if established.
- Hosted ingestion and frontend-monitoring verification status.
- Remaining blockers and optional work deferred.

Update the project progress handoff with actual results. A dashboard screenshot
alone is not evidence of an investigation, a fix, or complete instrumentation.
