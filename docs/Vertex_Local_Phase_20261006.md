# Vertex Gemini local architecture — 2026-10-06

This phase adds architecture and tests only. No live services, environment values, secrets,
IAM, Firebase, Tasks, project settings, commits or pushes have been changed. No model was called.
The existing production/default routes are retained.

## Architecture

`Provider`/`ModelResult` → `AIRunner` → `vertex:*` → `VertexGeminiProvider` → official
`google-genai` SDK → ADC → Vertex `generateContent`.

The old namespaces still resolve to their original adapters/endpoints. No `google:*` job is
reinterpreted as Vertex. Existing engine snapshots without Vertex fields remain readable.
The worker's queue retries, bounded repairs, prompt locking, response cache and settlement
remain in charge; the Vertex SDK has one attempt and automatic function calling disabled.

`app/ai/gemini.py` contains the task classification, logical-role bindings, capability checks,
model declarations and verification-record types. No model ID is scattered through feature
pipelines. `PAPERAID_GEMINI_ROUTING_ENABLED=false` is the default. Explicit local opt-in selects
the task's logical role; `PAPERAID_GEMINI_TASK_ROLES` can override individual tasks. Concrete
Vertex references and logical references are also understood when pricing a new engine.

Each quote freezes concrete preferred/fallback IDs, logical roles, model capabilities,
project/location, grounding opt-in and verified prices. Changing local settings cannot
reroute an already priced job. Vertex cache keys also include schema, project/location and
fallback chain. Successful grounded metadata is a private companion cache artifact, under
the job's existing file retention; queries, titles, snippets and paper text never enter logs.

Logical roles: `gemini_routine`, `gemini_writer`, `gemini_reasoner`, `gemini_reviewer`,
`gemini_search`, `gemini_multimodal`, `gemini_image`, `gemini_audio`, `gemini_live`,
`gemini_embeddings`. The first five bind to the owner-confirmed `gemini-3.8-flash`; all others
are intentionally unset. Flash as reviewer is a configuration choice, not a quality claim.
No stronger model name or rate is invented. The registry can accept another verified model
declaration and role binding later without feature changes.

Implemented: schema-controlled text generation, writing/reasoning task selection, grounded
structured requests, usage normalization, fallback policy and clear capability failures.
Prepared in the capability vocabulary only: multimodal/image/audio/transcription/live/tools/
embeddings services. No upload interpretation, image creation or streaming API is added.
Statistics, maps, privacy, disclosure, citation rendering, number protection, budget sums,
formatting and document generation still run in existing deterministic code.

## Authentication and local configuration

Vertex does not use any of the three provider API keys. Set project and location in a separate
local configuration when approved: `GOOGLE_CLOUD_PROJECT=paperaid`,
`GOOGLE_CLOUD_LOCATION=global`. ADC is loaded lazily; Cloud Run would use its service identity.
The SDK client is cached by project, location and timeout for process/runtime reuse.
Provider availability checks inspect required routes, project/location and verified token rates,
not ADC network access. Unverified Vertex prices close the local job UI as well as quoting.
OpenAI-only and Anthropic-only routes now need only their own keys; a missing key for an
actually required legacy route still closes that service. Works checks its own routes.

Manual cloud work still needed, not performed here: confirm the local ADC identity has
Vertex inference permission and billable/quota project `paperaid`, enabled API/billing and model
access in `global`. A later production phase must grant the worker service identity inference
permission in that project (cross-project if the app stays in `paperaid-ca172`). Do not move
the app's Firebase/data project merely to change its model billing project.

ADC explicitly uses the configured Vertex project as quota project, rather than inheriting an
unrelated project from the developer's saved credentials. Confirm that the identity may consume
services in `paperaid`; no saved ADC file or Google Cloud account setting was changed here.

## Structured output

The adapter uses `response_json_schema` (full supported JSON Schema subset), not the narrower
OpenAPI `response_schema`. It checks schema keywords before requests and uses `jsonschema`
to enforce the original schema, including additional properties, after a response. No field
or constraint is silently discarded and no released prompt/schema is redesigned.

The tests enumerate PaperAid's object schemas across orchestration, proposals/profile, works,
formatting, Data Lab and qualitative analysis, and construct the actual SDK configuration.
These are local compatibility checks only: remote schema complexity limits are not proven
by SDK construction. Unsupported keywords/external refs are refused before paid calls; a
remote invalid-argument response is reported as VERTEX_REQUEST_UNSUPPORTED rather than
silently altering the schema. A later controlled request must verify the largest schemas.

## Search and limitations

`search_json` adds `Tool(google_search=GoogleSearch())` to a schema-controlled request. Sources
come only from grounding chunks, citations only from grounding supports, and queries only
from actual metadata. Source snippets are not invented: citation segments are generated-text
segments, not quotations from source pages. Existing page/abstract verification remains.
No/insufficient grounding metadata fails after preserving provider usage. Repeat queries
remain repeated for billing. Unsafe URL schemes are excluded. Google redirect links are
retained honestly; compatibility with existing page-verification must be checked live.

Grounding plus JSON Schema in one request is implemented and tested against SDK objects,
but not yet called against this model. Unsupported combinations are a clear failure, with
no hidden extra model call. Google does not expose an exact per-request query limit for
this tool. The requested limit is a prompt instruction plus post-response validation, not
a guaranteed provider spend bound. Grounding stays disabled by default and is blocked in
production in this phase. Google's Search Suggestions and inline/aggregate grounding display
requirements still need a product implementation before releasing Vertex search. Metadata
is preserved privately so that work can be added; this phase changes no frontend screens.

## Costs and usage

No Vertex prices are built in. `VERTEX_PRICES` records are UNVERIFIED by default; VERIFIED
needs a source and finite non-negative input/output/cache rates. Rates are USD per million
tokens; additional units are USD per actual unit. `MODEL_PRICES` cannot bypass Vertex
verification. Unknown grounding unit rates also stop before the request. Historical dated
tables remain untouched. Tests use explicitly test-only prices, never product defaults.

Thinking tokens are included once in output_tokens and separately recorded as a subset.
Input is uncached prompt plus tool-input tokens; cache tokens stay separate. Tool-input
tokens are also recorded as an informational subset. Grounding bills actual query units.
Each ModelCall records task, logical role, actual model/provider, estimates, tokens, billable
units, latency, finish/safety/error state and fallback attempt. SDK failures record an
UNMETERED_ERROR observation: zero here is NOT evidence of a free request. Missing usage
marks UNKNOWN_USAGE and refuses delivery. Reconciliation against Cloud Billing is needed.

Fallbacks are opt-in logical Gemini roles only, frozen at quote time. They need all requested
capabilities and verified rates no higher in every dimension than the preferred model. No
OpenAI/Anthropic fallback. Authentication, quota/billing, malformed billed output and safety
blocks never trigger a fallback. Capacity/rate/timeout/model-unavailable errors may use the
configured next Vertex model; absent/exhausted fallback fails clearly. Network failures can
have unknown provider spend; no claim of exactly-once provider billing is made.

## One controlled call, AFTER explicit approval

`scripts/vertex_smoke.py` makes exactly one SDK request: tiny artificial input, JSON schema,
maximum 2,048 output tokens, no search, no SDK retry, no fallback, no student data and no
customer quote/hold. It refuses to call without `--allow-paid-call`. It reports tokens and
UNVERIFIED pricing, never an invented USD charge. Only `--help` was run during this phase.

From the repository root, after separate approval and ADC setup:

```powershell
Set-Location -LiteralPath 'F:\MY FILES\DATA SCIENCE\PAPER AID\backend'
.\.venv\Scripts\python.exe -m scripts.vertex_smoke --allow-paid-call --project paperaid --location global --model gemini-3.8-flash
```

This checks connectivity and a small schema only. It does not prove search, prices, quality,
all feature schemas, successful drafts or production readiness.

## Sources checked

- Model capabilities: https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/gemini/3-8-flash
- SDK: https://googleapis.github.io/python-genai/
- Structured output: https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/capabilities/control-generated-output
- Grounding behavior/display/query billing: https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/grounding/grounding-with-google-search
- Usage semantics: https://docs.cloud.google.com/gemini-enterprise-agent-platform/reference/rest/v1/GenerateContentResponse

## Changed-file inventory

New files:

- `backend/app/ai/gemini.py` — logical roles, 69 task classifications, capabilities, model declarations, verified-pricing records and fallback resolution.
- `backend/app/ai/vertex.py` — official SDK adapter, cached ADC client, schema contract, grounded request, normalized response and error handling.
- `backend/tests/test_vertex.py` — 113 offline provider/registry/schema/routing/accounting tests, including full job success and refund paths.
- `backend/scripts/vertex_smoke.py` — explicit opt-in single-request manual check; not executed against any model.
- `docs/Vertex_Local_Phase_20261006.md` — this implementation report and handoff.

Modified files:

- `backend/app/ai/providers.py` — separate namespace dispatch, additive usage/result fields, legacy adapters need only their own key.
- `backend/app/ai/orchestration.py` — freeze/resolve Vertex routes, capabilities/project/rates; bounded fallbacks; cost/error telemetry and private grounding cache.
- `backend/app/ai/costs.py` — explicit unverified-price failure and additional Vertex billing units; historical tables retained.
- `backend/app/core/config.py` — externalized Vertex role/model/project/location settings, route-aware availability and verified rate normalization.
- `backend/app/core/logging.py` — silence SDK/auth informational logs alongside existing provider loggers.
- `backend/app/jobs/models.py` — additive Engine and ModelCall fields; old records keep their existing defaults.
- `backend/app/jobs/service.py` — Works/Data Lab check their own configured providers, rather than depending on the Paper Check providers too.
- `backend/app/pricing/quote.py` — pricing uses the same frozen Vertex rates and query-unit fees as execution.
- `backend/pyproject.toml` — backend-only SDK and independent JSON Schema validator.
- `backend/.env.example` — commented local opt-in examples and intentionally empty Vertex prices; actual `.env` untouched.
- `backend/tests/conftest.py` — SDK guards last the whole pytest process, including late background workers; default feature fixtures keep their fakes.
- `backend/tests/serve_e2e.py` — explicitly disable Vertex routing and guard provider SDK boundaries in browser-test backend.
- `docs/deployment.md` — future ADC/IAM/pricing/display prerequisites; no deployment commands were executed.
- `docs/decisions.md` — local phase authorization, constraints and remaining gates.
- `CLAUDE.md` — phase rules and report link.
- `release-four-models.ps1` — comment marking it as a legacy release script; executable routes/commands untouched and script not run.

No feature pipeline, released prompt, feature schema, frontend source, live/default model route,
actual environment file or historical price table was edited.

## Dependencies and validation

Manifest additions: `google-genai==2.28.0`, `jsonschema>=4.23,<5`. Installed locally:
google-genai 2.28.0 and jsonschema 4.26.0. Their new transitive installations were attrs 26.1.0,
distro 1.9.0, jsonschema-specifications 2025.9.1, referencing 0.37.0, rpds-py 2026.9.1 and
tenacity 9.1.4. The SDK's constraint changed local websockets 17.1 to 16.1.1. Existing provider
dependencies remain. `pip check` passes. No frontend dependency was added.

- Full backend run: **1,005 passed**, three existing SciPy constant-group warnings, no failures.
- After adding four more tests and final refinements: **200 affected tests passed** (Vertex, AI, Works, One Start), then **116 passed** (all 113 Vertex tests plus availability/key-removal regressions).
- Final ADC/project-quota checks: passed. The latest suite collects **1,009 tests**. The full 1,009-test suite was not repeated; final changes were covered by the affected tests.
- All 49 collected object-schema declarations/aliases pass local supported-key checks and actual SDK config construction. No current PaperAid schema was rejected locally. Remote complexity/combined grounding support remains unverified.
- Backend Ruff and dependency check pass; `git diff --check` passes.
- Web: 10 tests pass; typecheck and production build pass (build output in system temp, leaving `web/dist` alone).
- Main browser journey passes: writing check, refine, changes, source check, formatting, PDF/DOCX, template, credits and ownership.
- One Start browser journey passes: coursework, requested revision, funding with figures, research Chapter One/framework, mobile width and work list.

Intermediate failures were corrected, not hidden: the new full-job test initially lacked its
`json` import, then assumed the wrong wallet endpoint/ledger state. The actual refund contract
is unchanged: billing hold state RELEASED, payment status REFUNDED, available/held balances
restored. The successful Word path and safety-block/no-output/full-refund path both pass.
An early timed-out test left a queued worker after its fakes were restored; it attempted ADC
refresh and failed DNS before reaching Vertex. Guards now persist for the entire test process,
including that teardown window. No billable model request completed. Two existing spend-ceiling
tests also caught an initial preflight regression; execution now prices the adapter's actual
provider/model before the call, and both tests pass.

No known failing test remains in the executed final checks. The unexecuted full rerun is stated
above explicitly. This is ready for ONE separately approved small text/schema connection check,
not for production cutover, paid customer jobs or a grounded-search rollout.
