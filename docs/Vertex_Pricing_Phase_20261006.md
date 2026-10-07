# PaperAid: local verified Vertex pricing phase — 2026-10-06

## Authorization and scope

The owner authorized local price verification/configuration and offline tests only, in the
instructions attached as `ed5687bd-671d-472e-9915-7cd9871abc92/Pasted text.txt`.
The previous, separately approved smoke request succeeded. It was not repeated in this phase.
No billable model call, Google Search request, deployment, IAM/Cloud Run change, production
environment change, commit or push was made. All implementation changes remain local and
sit on top of the preceding architectural phase's uncommitted work.

## Published pricing verified

Source: https://cloud.google.com/gemini-enterprise-agent-platform/generative-ai/pricing
Checked 2026-10-06. Applies only to `vertex:gemini-3.8-flash`, **Standard / Global**.

| Effective period | Input USD / million | Cached input USD / million | Output including thinking USD / million |
| --- | ---: | ---: | ---: |
| Verification date 2026-10-06 through 2026-12-31 inclusive | 0.75 | 0.075 | 3.75 |
| From 2027-01-01 | 1.50 | 0.15 | 7.50 |

The published input rate covers text/image/video/audio token input; this does not implement
new modality services in PaperAid. No rates were copied from the Gemini Developer API.
Non-global, Priority, Batch/Flex and other models are not covered by these verification records.

**Billing qualification:** Google's footnote describes introductory pricing as 50% credits
back on eligible net spend. The implementation stores the requested published net rates and
that qualification. Verify the net amount/credit application in Google billing before taking
customer money. The separate $300 Google Cloud promotional credit is not a unit-price discount.

## Date handling and historical records

`VertexPrice.schedule` retains both dated records. `at()` uses the current UTC date unless
an offline test supplies a date. `freeze_vertex()` resolves the schedule at each new quote,
even if the application Settings object was cached before the pricing transition. Only one
flat rate record is persisted in each engine, with source, verification date, effective dates,
location, service tier and grounding metadata.

Existing flat Vertex records stay flat. Existing legacy `PRICE_TABLES` and `google:*`
cached-input rates are unchanged. Historical quotes, rates, amounts and projected caps do not
move when the current date changes. A new uncached call cannot use an expired/future frozen
rate: AIRunner refuses it before SDK construction with VERTEX_PRICE_PERIOD_CHANGED. The
job must be quoted anew rather than silently understating Google's new price. Already cached
valid work can still replay without further provider spend.

No actual `.env` was edited. Omit a VERTEX_PRICES override to use the verified schedule;
an explicit empty registry (`VERTEX_PRICES={}`) intentionally disables it.

## Token accounting

- `visible_output_tokens`: Google's candidates token count, separate from thoughts.
- `thinking_tokens`: Google's thoughts token count.
- `output_tokens`: visible + thinking, the billable output passed to the cost calculator.
- `cached_tokens`: cache reads, charged at the verified discounted rate.
- `input_tokens`: uncached prompt input. Tool-provided Google Search input remains in
  `tool_input_tokens` for audit and is excluded from paid grounding input.

`vertex_token_cost()` calculates with Decimal. `cost_usd()` converts once at the existing
float persistence boundary; per-call cost keeps sub-microdollar precision. Existing job total
accumulation still rounds to six decimal places and the customer ledger still uses exact UGX.
No additional thinking fee is added. Explicit cache creation/storage is not implemented and
its price is not guessed; nonzero cache-write usage fails closed. The Vertex budget guard
uses uncached input for its input ceiling, not another provider's cache-write multiplier.

Offline replay of the completed smoke usage:

```text
Input:   116 × 0.75 / 1,000,000 = 0.000087 USD
Output: (5 + 109) × 3.75 / 1,000,000 = 0.0004275 USD
Cached: 0
Total: 0.0005145 USD
```

This is an offline published-rate calculation, not a new model request or a claim that a
Google billing invoice was inspected. The manual smoke tool's pure summary formatter now
reports verified costs and visible tokens; its main function was not run in this phase.

## Grounding metadata and gate

The metadata records 5,000 free queries/month shared across Gemini 3 models, then USD 14 per
1,000 actual queries (USD 0.014 each above the allowance). Returned query lists retain repeats;
`search_calls` and `billable_units.google_search_query` record their count. A request may contain
several queries. Ordinary prompt/response/thinking token charges are separate.

PaperAid cannot reconcile billing-wide allowance consumption, including other tools using
the same allowance. No monthly counter or claim of 5,000 free queries per student was added.
`customer_pricing_ready` is fixed false; the published grounding record is not exported as a
flat unit charge, even with an accidental flat override. AIRunner/quoting reject that charge
before a model call. Prior explicit test verification records remain test fixtures, not official
customer rates. Search is still disabled by default and explicitly blocked in production.

## Offline availability and remaining work

Gemini-only text quoting succeeds without OpenAI/Anthropic/Developer API keys or ADC access
in the test. The test explicitly opts in its own isolated settings; production/default routing
remains unchanged and disabled for Vertex. Prices do not themselves prove authenticated
access or acceptable model quality. Any quote requiring Vertex grounding remains blocked.

Ready for the next **offline task/model routing test** phase. Before live rollout: reconcile
introductory net pricing with billing, design grounded-query reconciliation/display/redirect/
budget handling, and separately authorize live task-quality trials. Additional models or
endpoints require separate rate/capability verification.

## Files changed in this pricing phase

1. `backend/app/ai/vertex_pricing.py` — new verified dated catalog and search metadata.
2. `backend/app/ai/gemini.py` — typed dated price/grounding records and selection.
3. `backend/app/core/config.py` — verified defaults, location guard and grounding gate.
4. `backend/app/ai/orchestration.py` — freeze current record, persist visible usage, refuse
   new spending outside a frozen rate period.
5. `backend/app/ai/costs.py` — Decimal Vertex costs and input budget ceiling; reject unpriced cache creation.
6. `backend/app/ai/providers.py` — additive visible-output field in normalized usage.
7. `backend/app/ai/vertex.py` — preserve visible tokens; exclude free grounding tool input.
8. `backend/app/jobs/models.py` — additive visible-output field in persisted calls.
9. `backend/scripts/vertex_smoke.py` — pure verified-price summary; script was not run.
10. `backend/tests/test_vertex_pricing.py` — new offline pricing regressions.
11. `backend/tests/test_vertex.py` — preserve explicit-unverified test, correct grounding fee
    fixture expectation for free tool input.
12. `backend/.env.example` — comments only; no actual environment changes.
13. `CLAUDE.md`, `docs/decisions.md`, `docs/deployment.md`, this report — phase documentation.

## Verification results

- Final targeted command: `.venv/Scripts/python -m pytest tests/test_vertex_pricing.py
  tests/test_vertex.py -q --basetemp C:/Users/USER/AppData/Local/Temp/pa_vertex_price_closed_20261006`
  from `backend`: **138 passed in 19.11 seconds** (25 pricing regressions plus 113 architectural
  tests). These include the mocked API/quote/hold/worker/export/settlement and failure-refund
  paths. Every SDK model boundary is guarded against real paid requests in pytest.
- Ruff over `app`, `tests` and `scripts/vertex_smoke.py`: **all checks passed**.
- Scoped tracked diff whitespace check: passed. No frontend code changed; no web build or
  browser journey was repeated for this pricing-only phase.
- Wider backend run, started before the final test corrections/additions: **1,029 passed,
  2 failed, 3 existing SciPy warnings**, 27 minutes 21 seconds. It is **not** a clean full-suite
  result on the final tree. One failure was the earlier copy of the new quote test, which
  referenced `QuoteLine.ugx` instead of `amount`; pytest had already loaded that copy before
  the correction. The final targeted run passes the corrected test.
- The other failure was the existing
  `tests/test_api.py::test_duplicate_delivery_after_completion_does_nothing`. Isolated rerun:
  **1 passed in 15.94 seconds**. The completed-job duplicate claim returns without mutation;
  the original worker can still update notification state after publishing COMPLETED, so a
  comparison of entire job snapshots can race with that work. This is the likely explanation,
  not a proved diagnosis of the observed diff (the full-run failure did not show field-level
  differences). The test/notification code was not changed in this pricing phase. Claude
  should stabilize or investigate that assertion separately; do not claim all backend tests
  passed based on this phase.

The remaining pricing risks are billing reconciliation of introductory credits back, the
shared grounding allowance, and verification for additional endpoints/models/modalities.
Historical quotes are protected from silent repricing; new spending at an expired frozen
rate is refused. The implementation is ready for **offline routing tests**, not a production
switch or an additional paid call.
