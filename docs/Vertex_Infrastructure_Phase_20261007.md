# PaperAid: Gemini / Vertex infrastructure completion

Local work began 2026-10-06 and finished 2026-10-07 (Africa/Kampala).
Owner instructions: attachment `ea77ef06-224f-4a00-9900-4a05a1ed9fdd/Pasted text.txt`.

## 1. Integration status

Implemented for standard text generation, structured generation, multimodal understanding
input, optional Google Search grounding and manually handled function declarations.
One request enters `VertexGeminiProvider.generate()` with the caller's explicit model,
system instruction, contents and options, then leaves as the existing `ModelResult` / `Usage`.
The provider neither selects a model for a PaperAid feature nor executes a workflow/tool loop.

This is local infrastructure readiness, not a production rollout or proof of every capability
against the live API. The previously approved real structured-text smoke succeeded; it was
not repeated. New request combinations and media inputs are verified offline.

## 2. Files involved

Changed in **this phase**, on top of the earlier uncommitted architecture/pricing work:

- `backend/app/ai/vertex.py`: generic explicit-model generation, multimodal validation,
  request forwarding, typed tool metadata, safety metadata, error categories, synchronized
  client creation and process-exit teardown. Existing structured wrappers retained.
- `backend/app/ai/vertex_request.py`: new typed `VertexOptions`; no feature/task bindings.
- `backend/app/ai/gemini.py`: model thinking capabilities and an optional implemented-capability
  argument to the existing capability check. Existing model-role/task mappings retained.
- `backend/app/ai/providers.py`: optional tool-call and safety metadata in `ModelResult`.
- `backend/tests/test_vertex_infrastructure.py`: 81 provider-only offline cases.
- `backend/tests/test_vertex.py`: existing adapter tests updated for explicit teardown and
  the distinction between 401 authentication and 403 authorization.
- `CLAUDE.md`, `docs/decisions.md`, `docs/deployment.md`, this report: phase documentation.

Supporting **existing/prior-phase** files inspected but not changed in this phase:
`backend/app/core/config.py`, `backend/app/ai/orchestration.py`, `backend/app/ai/costs.py`,
`backend/app/ai/vertex_pricing.py`, `backend/app/jobs/models.py`, `backend/app/runtime.py`,
`backend/app/main.py`, `backend/pyproject.toml`, `backend/Dockerfile`, `backend/.dockerignore`,
`backend/.env.example`, `release-four-models.ps1`, `backend/scripts/vertex_smoke.py`.
No prompts, academic workflows, feature schemas, statistics, credits, pricing policy,
formatting, citation rules or frontend code were changed in this phase.

## 3. Provider methods

- `json(task, model, system, payload, schema, max_tokens)`: existing structured interface.
  The task string is caller metadata; provider validation does not use the task/role registry.
  The existing `<paper_data>` payload wrapper remains.
- `search_json(task, model, system, payload, schema, max_tokens, max_searches)`: existing
  grounded structured interface, preserving the rollout gate and post-response query check.
- `generate(model, system, contents, options)`: new generic request boundary.
- `close_vertex_clients()`: explicit process-level teardown after requests/workers stop;
  also registered at process exit. Never called between ordinary requests.

`provider_for()` still resolves `openai:*`, `anthropic:*`, `google:*` and `vertex:*` to their
original adapters. Concrete historical references keep their meaning.

## 4. Request parameters

Explicit bare model IDs or `vertex:<id>`; caller-supplied system text and string/canonical
SDK `Content`/`Part` inputs; required positive output limit; optional temperature, top-p,
JSON/plain-text MIME, JSON schema, thinking configuration, safety settings, typed tools,
tool configuration, Google Search configuration and positive grounding query allowance.

Sampling/thinking/safety parameters are omitted when the caller omits them. No feature gets
an assigned temperature or thinking level. Model IDs must be declared in the configurable
capability registry; another registered ID is forwarded unchanged. Unsupported/unregistered
IDs fail explicitly. Output limits exceeding declared model limits fail before a request.
Transport/auth overrides, automatic retries and automatic function execution are not options.

## 5. Structured output

JSON with or without a schema; supported nested response JSON schemas checked before the
SDK call and validated again locally after the response. Unsupported constraints are refused,
not silently removed. Malformed JSON, invalid schema answers, truncation, empty responses,
blocked responses and malformed SDK envelopes have explicit outcomes. All pre-existing
PaperAid response schemas still pass the offline SDK/local compatibility contract.

## 6. Multimodal input

Text, inline image/PDF/plain-text/audio bytes and GCS/HTTPS document/media URIs are supported
through canonical SDK content. Supported MIME families follow the verified Flash model card.
The selected model must declare the requested modality. The provider does not read a file,
upload a file, fetch a URI or change any PaperAid document-processing pipeline. DOCX is not
passed directly as a supported media MIME; the current extraction pipeline remains intact.
Model/API media-size and context limits still apply and can produce a normalized rejection.

## 7. Grounding

Optional Google Search configuration is forwarded. Sources/URLs/titles, citation segments,
Search Suggestions and repeated actual queries are preserved privately in `ModelResult`.
Queries are counted individually. Missing required grounding metadata and observed overrun
are distinct errors; observed usage is retained. Google does not expose a hard max-query
parameter, so the query allowance is a post-response check, not a guaranteed spend cap.

Grounding remains off by default and explicitly blocked in production. Customer grounding
pricing remains gated pending billing reconciliation from the previous pricing phase.
The provider now forwards the original system instruction exactly instead of appending the
search instruction introduced by the earlier Vertex adapter. No PaperAid prompt was edited.

## 8. Thinking

Optional native `ThinkingConfig`, including include-thoughts, a supported thinking level or
a verified model-specific thinking budget. The two mechanisms cannot be set together.
Flash 3.8 capability evidence permits LOW/MEDIUM/HIGH, not MINIMAL or a Gemini 2.5-style budget.
No default thinking choice was added. Reasoning text is excluded from final visible text;
thinking counts remain available. Function-call thought signatures are retained for a caller
that later supplies its own explicit next turn.

## 9. Usage/accounting

Input, cached input, visible output, thinking, combined billable output, tool input, actual
grounding query count, requested model, provider, reported model version, finish reason,
latency and block metadata remain available. Billable output remains visible + thinking once.
Google Search tool-provided input is excluded from charged input. Missing/contradictory usage
is marked unknown rather than becoming a verified result; quantities cannot become negative.
No price, credit policy, frozen quote or settlement formula was changed in this phase.

## 10. Errors

401/ADC refresh: VERTEX_AUTH; 403: VERTEX_PERMISSION; 404: VERTEX_MODEL_UNAVAILABLE;
structured invalid-model detail: VERTEX_INVALID_MODEL; hard quota/billing: VERTEX_QUOTA;
renewable rate/capacity limits: VERTEX_RATE_LIMIT; timeout: VERTEX_TIMEOUT; transport/5xx:
PROVIDER_UNAVAILABLE; unsupported request/capability/schema/service errors; malformed output,
failed schema, safety refusal, missing/over-budget grounding and malformed tool output.
Messages contain classification codes, not provider payloads, secrets or private schema keys.
No SDK retry, provider fallback, automatic repair or automatic function execution is performed.

## 11. Authentication

`google.auth.default()` supplies ADC with cloud-platform scope and configured quota project.
`genai.Client(vertexai=True, project=..., location=..., credentials=...)` uses the explicit ADC.
An offline test using the real installed SDK constructor confirms a legacy GEMINI_API_KEY
environment variable does not override explicit ADC. No JSON key or credential file was created,
copied, printed or embedded. `google:*` retains its independent Developer API key adapter.

## 12. Local readiness

Existing project `paperaid`, location `global`, ADC identity, IAM and the single real structured
smoke were already verified in previous phases. No new authentication or live inference check
was run. The caller must supply project/location via existing Settings; CLI project selection
alone does not replace explicit application settings. The provider needs no OpenAI/Anthropic/
Developer API key. Offline tests guard all HTTP sends and ADC refreshes.

## 13–14. Cloud Run readiness and eventual configuration

Repository architecture: one Python 3.12/FastAPI image, API and internal worker in the app/data
project `paperaid-ca172`, `europe-west1`; model project stays separately `paperaid`, `global`.
The image installs the SDK through pyproject and copies only application/package files, not
local ADC. The provider is compatible with attached service-account ADC. Client creation is
serialized across concurrent first requests and reused by project/location/server timeout.
There is no eviction/closure of clients while another worker can be using them.

Before a separately authorized rollout, verify the **actual deployed worker identity**, then
ensure that identity has `aiplatform.endpoints.predict` and `serviceusage.services.use` in
`paperaid`. Vertex AI User and, only if needed, Service Usage Consumer are the relevant
predefined roles; do not grant redundant roles. The documented design uses
`paperaid-worker@paperaid-ca172.iam.gserviceaccount.com`, but live identity/grants were not
queried or changed in this phase. API identity needs inference access only if it makes calls.

Eventually configure application model project/location and approved explicit model selections;
retain existing app/data settings and legacy secrets for historical jobs. Model/API availability,
billing and quota must hold for selected models. Private GCS media access must be verified
before URI-based inference, especially across projects. No IAM, service account, API enablement,
Cloud Run, secret, environment or traffic modification was applied.

## 15. Intentionally not implemented

Image generation/editing, audio generation/TTS, a transcription workflow, embeddings, live/
streaming interaction, video input, Files API uploads, explicit cache creation/storage, RAG/
retrieval, Google Maps, URL-context, computer use, code execution, automatic tool execution,
multi-request agents and account-wide grounding allowance reconciliation. Future service
methods/result types can extend this provider boundary; existing workflows stay separate.

## 16–17. Unapproved model/function decisions retained for the owner

These were introduced during the **earlier local migration work**, not during this phase.
They were not silently removed. They are real opt-in routing configuration, not fake models.

| File:line | Assignment | Runtime effect/status |
| --- | --- | --- |
| `backend/app/core/config.py:63` | gemini_routine model defaults to gemini-3.8-flash | Used if a logical role is opted in; retained, not approved as a function strategy |
| `backend/app/core/config.py:64` | gemini_writer model defaults to gemini-3.8-flash | Same |
| `backend/app/core/config.py:65` | gemini_reasoner model defaults to gemini-3.8-flash | Same |
| `backend/app/core/config.py:66` | gemini_reviewer model defaults to gemini-3.8-flash | Same |
| `backend/app/core/config.py:67` | gemini_search model defaults to gemini-3.8-flash | Same; grounding gates also apply |
| `backend/app/ai/gemini.py:140` | analyse/peer/after, claims, p_needs/p_extract/p_profile, spec_plan, w_read/w_needs/w_extract, q_code → gemini_routine | Opt-in task classification; retained for decision |
| `backend/app/ai/gemini.py:141` | plan/finalise/refine/repair/redraft, spec finalise/fix, proposal planning/brief/draft/fix/profile finalise, works planning/results/draft/repair/compress, d_report/d_chapter4, q_themes → gemini_writer | Same |
| `backend/app/ai/gemini.py:142` | critique/guide, spec critique/guide, proposal critique/guide/profile critique/guide, w_adjudicate → gemini_reasoner | Same |
| `backend/app/ai/gemini.py:143` | academic/audit/review/verify, spec reviews, proposal reviews/readiness/profile reviews, works verification/plan/results/integrity/evaluate/final, d_report_review/q_review → gemini_reviewer | Same |
| `backend/app/ai/gemini.py:144` | research/p_search/w_search → gemini_search | Same |
| `backend/.env.example:45` (also 46–49) | Commented example bindings of those five roles to Flash | Comments only, unless copied into configuration |
| `backend/.env.example:51` | Commented w_draft/w_final task-to-role example | Comments only, unless copied into configuration |

`core/config.py:75` defaults automatic routing off, and task overrides at line 74 default empty.
`gemini.py:185` resolves opted-in mappings; `orchestration.freeze_vertex()` freezes them for quotes.
Thus **yes, current code outside the provider can assign Gemini models to features if opted in**.
No such final strategy was chosen/enabled/approved by this infrastructure phase.

Earlier `backend/tests/test_vertex.py` tests such as
`test_model_role_registry_is_not_a_live_switch`, `test_gemini_only_configuration_needs_no_provider_keys`
and `test_automatic_task_classes_and_frozen_prices` also encode these mappings as test
expectations; `backend/tests/test_vertex_pricing.py` contains mapping-enabled quote fixtures.
Those are test-only, were retained, and were excluded from this phase's selected run.
Earlier architectural/pricing reports describe the same prospective bindings; this latest
owner boundary supersedes any implication of approval in that wording.

The **pre-existing approved** `role_models.WRITER = google:gemini-3.8-flash` at
`core/config.py:86` is present in HEAD and uses the direct Gemini adapter. It is not a new Vertex
assignment. Likewise the confirmed model capability/pricing catalog is evidence about a model,
not a decision that it should perform any feature.

## 18. Tests

Final selected run: **156 passed in 13.04 seconds** (81 new provider cases plus 75 existing
provider/schema/usage/price conformance cases). Ruff over app/tests/manual smoke source:
**all checks passed**. Scoped tracked whitespace diff check passed.

Coverage: namespaces, explicit and additional registered IDs, arbitrary caller labels,
verbatim instructions, options/thinking/safety forwarding, media bytes/URIs, native SDK payload
conversion, nested JSON validation, blocked/truncated/empty/malformed responses, usage/cache/
thinking arithmetic, grounding metadata/gates, manual function declarations, error categories,
explicit ADC over a legacy key, project/quota/location, concurrent client reuse and teardown.
Tests forbid real HTTP sends/auth refresh and replace generation at the SDK boundary.

No task-to-model mapping tests were run. No whole backend suite, browser journeys, deployment,
commit, push, package installation, real model call or real grounding call was performed in
this phase. The preceding pricing report's broader-suite results remain separate; this run
does not assert the whole repository has no bugs.

## 19. Remaining limitations

No known defect in the tested provider contract remains. Live combinations (grounding with
structured schemas; model-specific media/thinking/function behavior) are unproven beyond the
earlier basic structured-text smoke. Declared registry capabilities/limits and API support must
be verified for each additional model. Grounding rollout/reconciliation and production identity
verification remain gates. The earlier duplicate-delivery snapshot test remains a separate issue.

## 20. Can existing workflows invoke an explicit Vertex model?

Yes: select a registered compatible model outside the provider and use the existing json/
search_json interface or generic generate interface. No provider rewrite is needed for the
implemented capabilities. Quote availability still needs verified prices and existing product
configuration; changing which feature calls which model is a separate owner decision.

**Stopped after this infrastructure report. No model/function strategy has been selected.**

### Official references

- Google Gen AI SDK: https://googleapis.github.io/python-genai/
- Flash capability card: https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/gemini/3-8-flash
- Thinking levels/budgets: https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/thinking
- Inference permissions: https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/access-control
- Quota-project permission: https://docs.cloud.google.com/service-usage/docs/access-control
- Attached service-account ADC: https://docs.cloud.google.com/docs/authentication/set-up-adc-attached-service-account
