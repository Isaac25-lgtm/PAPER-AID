"""The Gemini workflow on Vertex, against the real SDK types with the SDK boundary mocked: no network,
no spend. Test-only model IDs and prices below are fixtures, never production configuration."""

import json
from types import SimpleNamespace

import google.auth
import httpx
import pytest
from google.auth import exceptions as auth_errors
from google.genai import errors, types
from pydantic import BaseModel, ValidationError

from app.ai import costs, gemini, orchestration, providers, vertex
from app.ai.orchestration import STEPS, AIRunner, current_engine, output_allowance, work_engine
from app.core.config import Settings
from app.core.errors import PermanentStageError, RetryableStageError
from app.jobs.models import Engine

MODEL = "gemini-3.8-flash"
REF = "vertex:" + MODEL
SCHEMA = {"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"], "additionalProperties": False}
PRICE = {"status": "VERIFIED", "source": "test fixture only, NOT a real rate", "input": 1, "output": 2, "cached": 0.1,
         "units": {"google_search_query": 0.01}}
LINK = "https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQissuedByGoogle=="
FORGED = "https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQforgedByModel=="


class Answer(BaseModel):
    ok: bool


class Found(BaseModel):
    findings: list[dict[str, str]]


def settings(**kw):
    return Settings(_env_file=None, vertex_project="paperaid", vertex_location="global", **kw)


def flat(**kw):
    """Every stage on one model at a test-only price."""
    values = {f"{stage}_model": MODEL for stage in gemini.STAGES} | {"vertex_prices": {MODEL: PRICE}, "gemini_fallbacks": {}}
    return settings(**(values | kw))


def response(text='{"ok":true}', finish="STOP", **kw):
    value = {"candidates": [{"content": {"parts": [{"text": text}]}, "finishReason": finish}],
             "usageMetadata": {"promptTokenCount": 120, "candidatesTokenCount": 30, "thoughtsTokenCount": 50,
                               "cachedContentTokenCount": 20, "toolUsePromptTokenCount": 12}}
    value.update(kw)
    return types.GenerateContentResponse.model_validate(value)


def searched(text, queries):
    """What Vertex returns for a grounded JSON answer (live 2026-10-07): the queries, no source list."""
    value = response(text).model_dump(by_alias=True, exclude_none=True)
    value["candidates"][0]["groundingMetadata"] = {"webSearchQueries": queries}
    return types.GenerateContentResponse.model_validate(value)


@pytest.fixture
def sdk(monkeypatch):
    calls = []
    answers = [response()]

    def generate(**kw):
        calls.append(kw)
        value = answers.pop(0)
        if isinstance(value, Exception):
            raise value
        return value

    monkeypatch.setattr(vertex, "_vertex_client", lambda *args: SimpleNamespace(models=SimpleNamespace(generate_content=generate)))
    monkeypatch.setattr(vertex, "_resolve", lambda link: "https://www.who.int/report" if link == LINK else None)
    return calls, answers


def runner(s, engine=None, cache=None, budget=5):
    records = []
    ai = AIRunner(s, records.append, lambda: sum(r.cost_usd + r.reserved_usd for r in records), budget, cache=cache, engine=engine)
    return ai, records


class Cache:
    def __init__(self):
        self.values = {}

    def get(self, key):
        return self.values.get(key)

    def put(self, key, value):
        self.values[key] = value


# --- routing -----------------------------------------------------------------------------------


def test_every_step_has_a_stage_and_new_engines_route_all_of_them_to_vertex():
    assert gemini.TASK_STAGES.keys() == STEPS.keys()
    assert gemini.SIGNOFF_TASKS <= {t for t, s in gemini.TASK_STAGES.items() if s == "premium_audit"}
    e = current_engine(settings())
    assert e.vertex_routes.keys() == STEPS.keys() and all(refs[0].startswith("vertex:") for refs in e.vertex_routes.values())
    assert e.vertex_routes["w_read"] == ["vertex:gemini-3.5-flash-lite"]
    assert e.vertex_routes["plan"] == e.vertex_routes["refine"] == e.vertex_routes["research"] == [REF]
    assert e.vertex_routes["review"] == e.vertex_routes["w_final"] == ["vertex:gemini-3.1-pro-preview", REF]  # Pro, then Flash if Pro is busy
    assert e.vertex_routes["analyse"] == [REF] and e.vertex_routes["analyse_peer"] == ["vertex:gemini-3.5-flash-lite"]
    assert e.vertex_signoff == [REF]
    assert e.vertex_thinking == {"intake": "LOW", "planner": "HIGH", "research": "LOW", "execution": "MEDIUM", "first_audit": "MEDIUM",
                                 "second_check": "MEDIUM", "premium_audit": "HIGH", "fix": "MEDIUM", "final_signoff": "MEDIUM"}
    assert e.vertex_project == "paperaid" and e.vertex_location == "global"


def test_premium_works_tier_has_sections_evaluated_by_the_premium_auditor():
    s = settings()
    assert work_engine(s, "FUNDING_PROPOSAL").vertex_routes["w_evaluate"] == ["vertex:gemini-3.1-pro-preview", REF]
    assert work_engine(s, "COURSEWORK").vertex_routes["w_evaluate"] == [REF]


def test_workflow_off_and_older_engines_keep_their_provider_routes():
    off = current_engine(settings(gemini_workflow=False))
    assert not off.vertex_routes and orchestration.model_for_engine(off, "review") == "openai:gpt-6-sol"
    old = Engine(lead_model="openai:gpt-6-sol", writer_model="anthropic:claude-opus-5-5", prompts={"plan": "plan-v1"})
    assert AIRunner(settings(), lambda _: None, lambda: 0, 1, engine=old).model_for("plan") == old.lead_model
    assert not old.vertex_routes


@pytest.mark.parametrize("prefix,cls", [("openai:gpt-6-sol", providers.OpenAIProvider),
                                      ("anthropic:claude-opus-5-5", providers.AnthropicProvider),
                                      ("google:" + MODEL, providers.GeminiProvider), (REF, vertex.VertexGeminiProvider)])
def test_provider_namespaces_preserved(prefix, cls):
    s = settings(openai_api_key="test", anthropic_api_key="test", gemini_api_key="test")
    provider, model = providers.provider_for(prefix, s)
    assert isinstance(provider, cls) and model == prefix.partition(":")[2]


def test_a_stage_model_without_the_capability_or_thinking_level_is_refused_at_pricing():
    no_reasoning = gemini.CONFIRMED_MODELS[MODEL].model_copy(update={"capabilities": frozenset({gemini.Capability.JSON, gemini.Capability.WRITING})})
    with pytest.raises(PermanentStageError, match="AI_CAPABILITY_UNSUPPORTED"):
        current_engine(flat(paperaid_gemini_models={MODEL: no_reasoning}))
    with pytest.raises(PermanentStageError, match="thinking MINIMAL not verified"):
        current_engine(flat(intake_thinking="MINIMAL"))
    with pytest.raises(PermanentStageError, match="GEMINI_MODEL_UNVERIFIED"):
        current_engine(flat(planner_model="gemini-invented"))


def test_gemini_only_configuration_needs_no_provider_keys():
    s = settings(openai_api_key=None, anthropic_api_key=None, gemini_api_key=None)
    assert s.ai_configured and s.roles_configured and s.search_configured
    assert not s.provider_configured("openai:any") and s.provider_configured(REF)
    assert not s.model_copy(update={"vertex_project": None}).ai_configured


@pytest.mark.parametrize("provider", ["openai", "anthropic"])
def test_single_legacy_provider_configuration_requires_only_its_key(provider):
    ref = provider + ":test-only"
    s = Settings(_env_file=None, gemini_workflow=False, lead_model=ref, writer_model=ref, routine_model=ref, drafting_model=ref,
                 ai_check_model=ref, ai_check_peer_model=ref, **{provider + "_api_key": "test"})
    assert s.ai_configured
    provider_object, _ = providers.provider_for(ref, s)
    assert provider_object.name == provider


def test_search_switched_off_closes_only_the_searching_services():
    from app.jobs.service import availability

    on, off = availability(settings()), availability(settings(vertex_search_enabled=False))
    assert on["SOURCE_CHECK"] == on["PROPOSAL"] == on["AI_CHECK"] == "available"
    assert off["SOURCE_CHECK"] == off["PROPOSAL"] == "not_configured" and off["AI_CHECK"] == "available"


# --- the provider ---------------------------------------------------------------------------------


def test_adc_client_reused_and_no_keys_passed(monkeypatch):
    vertex.close_vertex_clients()
    credentials = object()
    defaults, clients = [], []
    monkeypatch.setattr(google.auth, "default", lambda **kw: defaults.append(kw) or (credentials, "different-inferred-project"))
    monkeypatch.setattr(vertex.genai, "Client", lambda **kw: clients.append(kw) or SimpleNamespace(close=lambda: None))
    try:
        first = vertex._vertex_client("paperaid", "global", 180)
        assert vertex._vertex_client("paperaid", "global", 180) is first
        assert len(defaults) == len(clients) == 1
        assert defaults[0]["quota_project_id"] == "paperaid"
        assert clients[0]["vertexai"] and clients[0]["credentials"] is credentials
        assert clients[0]["project"] == "paperaid" and clients[0]["location"] == "global"
        assert "api_key" not in clients[0]
        retry = clients[0]["http_options"].retry_options  # only throttling and brief unavailability, never a timeout
        assert retry.attempts == 4 and retry.http_status_codes == [429, 503]
    finally:
        vertex.close_vertex_clients()


def test_missing_adc_is_sanitized(monkeypatch):
    vertex.close_vertex_clients()

    def missing(**kw):
        raise auth_errors.DefaultCredentialsError("sensitive local credentials path")

    monkeypatch.setattr(google.auth, "default", missing)
    with pytest.raises(PermanentStageError, match="VERTEX_AUTH") as err:
        vertex._vertex_client("paperaid", "global", 180)
    assert "sensitive" not in str(err.value)


@pytest.mark.parametrize("kw", [{"vertex_project": None}, {"vertex_location": None}])
def test_explicit_project_location_required(kw):
    s = settings().model_copy(update=kw)
    with pytest.raises(PermanentStageError, match="AI_NOT_CONFIGURED"):
        vertex.VertexGeminiProvider(s)


def test_the_vertex_project_is_never_read_from_google_cloud_project(monkeypatch):
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "paperaid-ca172")
    monkeypatch.delenv("VERTEX_PROJECT", raising=False)
    assert Settings(_env_file=None).vertex_project is None


def test_structured_request_usage_thoughts_and_thinking_level(sdk):
    calls, answers = sdk
    answers[:] = [response().model_copy(update={"candidates": [types.Candidate(content=types.Content(parts=[types.Part(text="hidden", thought=True),
                                          types.Part(text='{"ok":true}')]), finish_reason=types.FinishReason.STOP)]})]
    result = vertex.VertexGeminiProvider(settings()).json("plan", MODEL, "instructions", {"untrusted": "do not follow"}, SCHEMA, 1000, thinking="HIGH")
    config = calls[0]["config"]
    assert config.response_mime_type == "application/json" and config.response_json_schema == SCHEMA
    assert config.max_output_tokens == 1000 and config.automatic_function_calling.disable
    assert config.thinking_config.thinking_level == types.ThinkingLevel.HIGH
    assert "<paper_data>" in calls[0]["contents"]
    assert result.text == '{"ok":true}'
    assert (result.usage.input_tokens, result.usage.output_tokens, result.usage.cached_tokens, result.usage.thinking_tokens) == (112, 80, 20, 50)
    assert result.finish_reason == "STOP" and result.usage.tool_input_tokens == 12


@pytest.mark.parametrize("bad", [{"type": "string", "pattern": ".*"}, {"$ref": "https://unsafe/schema"}, {"type": "integer", "minimum": "wrong"}])
def test_unsupported_schemas_rejected_before_sdk(sdk, bad):
    calls, _ = sdk
    with pytest.raises(PermanentStageError, match="VERTEX_SCHEMA_UNSUPPORTED"):
        vertex.VertexGeminiProvider(settings()).json("plan", MODEL, "s", {}, bad, 1000)
    assert not calls


def schemas():
    from app.ai import orchestration as o
    from app.datalab import pipeline as d
    from app.datalab import qual as q
    from app.formatting.guideline import SPEC_SCHEMA
    from app.proposals import ai as p
    from app.proposals import profile
    from app.works import ai as w
    items = [(module.__name__ + "." + name, value) for module in (o, d, q, p, w, profile)
             for name, value in vars(module).items() if isinstance(value, dict) and value.get("type") == "object"]
    items.append(("formatting.SPEC_SCHEMA", SPEC_SCHEMA))
    return items


@pytest.mark.parametrize("name,schema", schemas(), ids=lambda value: value if isinstance(value, str) else None)
def test_every_paperaid_schema_passes_local_vertex_contract(name, schema):
    vertex.check_schema(schema)
    assert types.GenerateContentConfig(response_json_schema=schema).response_json_schema == schema


@pytest.mark.parametrize("finish,code", [("SAFETY", "VERTEX_SAFETY_BLOCK"), ("RECITATION", "VERTEX_SAFETY_BLOCK"),
                                       ("OTHER", "VERTEX_EMPTY_RESPONSE")])
def test_refusals_block_approval_and_record_usage(sdk, finish, code):
    _, answers = sdk
    answers[:] = [response("", finish)]
    ai, records = runner(flat())
    with pytest.raises((PermanentStageError, RetryableStageError), match=code):
        ai._call("plan", {}, SCHEMA, Answer)
    assert records[0].cost_usd > 0


def test_prompt_block_and_truncation_and_missing_usage(sdk):
    _, answers = sdk
    provider = vertex.VertexGeminiProvider(settings())
    answers[:] = [response("", "STOP", candidates=[], promptFeedback={"blockReason": "SAFETY"}), response("{", "MAX_TOKENS"),
                 response("", "STOP"), response(usageMetadata=None)]
    assert provider.json("plan", MODEL, "s", {}, SCHEMA, 1000).safety_block
    assert provider.json("plan", MODEL, "s", {}, SCHEMA, 1000).stop == "max_tokens"
    assert provider.json("plan", MODEL, "s", {}, SCHEMA, 1000).error_code == "VERTEX_EMPTY_RESPONSE"
    assert provider.json("plan", MODEL, "s", {}, SCHEMA, 1000).error_code == "VERTEX_USAGE_MISSING"


@pytest.mark.parametrize("exc,code,retry", [(errors.APIError(401, {"error": {"message": "secret"}}), "VERTEX_AUTH", False),
                                         (errors.APIError(403, {}), "VERTEX_PERMISSION", False),
                                         (errors.APIError(404, {}), "VERTEX_MODEL_UNAVAILABLE", False),
                                         (errors.APIError(429, {}), "VERTEX_RATE_LIMIT", True),
                                         (errors.APIError(429, {"error": {"message": "quota exceeded"}}), "VERTEX_QUOTA", False),
                                         (errors.APIError(503, {}), "PROVIDER_UNAVAILABLE", True),
                                         (errors.APIError(400, {"error": {"status": "INVALID_ARGUMENT"}}), "VERTEX_REQUEST_UNSUPPORTED", False),
                                         (httpx.ReadTimeout("sensitive"), "VERTEX_TIMEOUT", True),
                                         (httpx.ConnectError("sensitive"), "PROVIDER_UNAVAILABLE", True),
                                         (auth_errors.RefreshError("sensitive"), "VERTEX_AUTH", False)])
def test_sdk_errors_are_classified_without_sensitive_message(sdk, exc, code, retry):
    _, answers = sdk
    answers[:] = [exc]
    with pytest.raises(RetryableStageError if retry else PermanentStageError, match=code) as err:
        vertex.VertexGeminiProvider(settings()).json("plan", MODEL, "s", {}, SCHEMA, 1000)
    assert "secret" not in str(err.value) and "sensitive" not in str(err.value) and err.value.__cause__ is None


@pytest.mark.parametrize("capability", [gemini.Capability.IMAGES, gemini.Capability.AUDIO, gemini.Capability.TOOLS])
def test_capabilities_without_a_workflow_adapter_fail_explicitly(capability):
    with pytest.raises(PermanentStageError, match="AI_SERVICE_UNIMPLEMENTED"):
        gemini.check_model(MODEL, frozenset({capability}), gemini.CONFIRMED_MODELS)


# --- the runner ---------------------------------------------------------------------------------------


@pytest.mark.parametrize("text,code", [("{", "MALFORMED_OUTPUT"), ('{"ok":"yes"}', "SCHEMA_VALIDATION_FAILED"),
                                      ('{"ok":true,"extra":1}', "SCHEMA_VALIDATION_FAILED")])
def test_invalid_billed_response_is_recorded_not_cached(sdk, text, code):
    _, answers = sdk
    answers[:] = [response(text)]
    ai, records = runner(flat())
    with pytest.raises(RetryableStageError, match=code):
        ai._call("plan", {}, SCHEMA, Answer)
    assert len(records) == 1 and records[0].cost_usd > 0 and records[0].error_code == code


def test_each_stage_sends_its_thinking_level_with_room_for_it(sdk):
    calls, answers = sdk
    answers[:] = [response(), response()]
    s = flat()
    ai, records = runner(s, budget=50)
    ai._call("plan", {}, SCHEMA, Answer)
    ai._call("refine", {}, SCHEMA, Answer)
    assert [c["config"].thinking_config.thinking_level for c in calls] == [types.ThinkingLevel.HIGH, types.ThinkingLevel.MEDIUM]
    assert calls[0]["config"].max_output_tokens == STEPS["plan"].max_tokens + gemini.THINKING_ROOM["HIGH"]
    assert calls[1]["config"].max_output_tokens == STEPS["refine"].max_tokens + gemini.THINKING_ROOM["MEDIUM"]
    assert [(r.workflow_stage, r.thinking_level) for r in records] == [("planner", "HIGH"), ("execution", "MEDIUM")]
    assert output_allowance(current_engine(s), "plan") == (STEPS["plan"].max_tokens + 32_000, 16_000)
    assert output_allowance(current_engine(settings(gemini_workflow=False)), "plan") == (STEPS["plan"].max_tokens, costs.THINKING_ALLOWANCE_TOKENS)


def test_success_cache_uses_frozen_engine_after_settings_change(sdk):
    calls, _ = sdk
    s = flat()
    engine = current_engine(s)
    ai, records = runner(s, engine, Cache())
    assert ai._call("plan", {}, SCHEMA, Answer).ok
    s.planner_model = "unverified-after-quote"
    s.vertex_project = "different-project"
    s.vertex_prices = {}
    replay, other = runner(s, engine, ai._cache)
    assert replay._call("plan", {}, SCHEMA, Answer).ok and not other and len(calls) == 1
    assert replay.settings.vertex_project == "paperaid"
    assert records[0].workflow_stage == "planner" and records[0].thinking_tokens == 50
    assert records[0].visible_output_tokens == 30 and records[0].output_tokens == 80


def test_repaired_deliverables_are_signed_off_against_the_earlier_audit(sdk):
    """Round 0 of a review loop is the premium audit; a re-review after a repair is the final sign-off,
    on its own model, with the sign-off instructions and every earlier answer."""
    calls, answers = sdk
    answers[:] = [response(), response(), response()]
    s = flat(premium_audit_model="gemini-3.1-pro-preview", vertex_prices={MODEL: PRICE, "gemini-3.1-pro-preview": PRICE})
    ai, records = runner(s, budget=50)
    for round_ in ai.audit_rounds(3):
        ai._call("review", {"passage": "x", "round": round_}, SCHEMA, Answer)
    assert [c["model"] for c in calls] == ["gemini-3.1-pro-preview", MODEL, MODEL]
    assert [r.workflow_stage for r in records] == ["premium_audit", "final_signoff", "final_signoff"]
    assert "FINAL SIGN-OFF ROUND" not in calls[0]["config"].system_instruction
    assert "FINAL SIGN-OFF ROUND" in calls[1]["config"].system_instruction
    assert '"previousAudit": [{"ok": true}]' in calls[1]["contents"]
    assert '"previousAudit": [{"ok": true}, {"ok": true}]' in calls[2]["contents"]
    answers[:] = [response()]
    ai._call("review", {"passage": "y"}, SCHEMA, Answer)  # after the loop: a new deliverable's premium audit
    assert calls[-1]["model"] == "gemini-3.1-pro-preview" and "previousAudit" not in calls[-1]["contents"]


def test_a_loop_whose_first_review_came_before_it_starts_at_the_sign_off(sdk):
    calls, answers = sdk
    answers[:] = [response(), response()]
    ai, records = runner(flat(), budget=50)
    ai._call("review", {"passage": "x"}, SCHEMA, Answer)
    for _ in ai.audit_rounds(1, start=1):
        ai._call("review", {"passage": "x, repaired"}, SCHEMA, Answer)
    assert [r.workflow_stage for r in records] == ["premium_audit", "final_signoff"]
    assert '"previousAudit": [{"ok": true}]' in calls[1]["contents"]


def test_grounded_search_resolves_google_links_and_charges_every_query(sdk):
    calls, answers = sdk
    text = json.dumps({"findings": [{"url": LINK, "quote": "597 000 deaths"}, {"url": FORGED, "quote": "made up"}]})
    answers[:] = [searched(text, ["who malaria 2023", "who malaria 2023", "world malaria report"])]
    ai, records = runner(flat())
    seen = []
    answer = ai._call("research", {"claim": "c"}, {"type": "object"}, Found, max_searches=2, accept=lambda a, r: seen.append(r) or a)
    assert isinstance(calls[0]["config"].tools[0].google_search, types.GoogleSearch)
    assert "Run at most 2 search queries" in calls[0]["config"].system_instruction
    result = seen[0]
    assert answer.findings[0]["url"] == "https://www.who.int/report" and answer.findings[1]["url"] == FORGED
    assert result.sources == ["https://www.who.int/report"]  # the forged link resolves to nothing: not a source
    from app.analysis import research
    assert research.opened(answer.findings[0]["url"], result.sources) and not research.opened(FORGED, result.sources)
    assert result.grounding["queriesOverAllowance"] == 1 and not records[0].error_code  # charged, not failed
    assert records[0].billable_units == {"google_search_query": 3}
    assert records[0].cost_usd == pytest.approx((100 * 1 + 80 * 2 + 20 * 0.1) / 1e6 + 3 * 0.01)  # grounding tool input is free


def test_redirect_resolution_reads_only_the_location_header(monkeypatch):
    seen = []

    def get(url, follow_redirects, timeout):
        seen.append((url, follow_redirects))
        return SimpleNamespace(status_code=302 if url == LINK else 404, headers={"location": "https://example.org/page"} if url == LINK else {})

    monkeypatch.setattr(vertex.httpx, "get", get)
    assert vertex._resolve(LINK) == "https://example.org/page" and vertex._resolve(FORGED) is None
    assert all(not follow for _, follow in seen)


def test_grounding_switched_off_is_refused_before_any_call(sdk):
    calls, _ = sdk
    with pytest.raises(PermanentStageError, match="VERTEX_GROUNDING_DISABLED"):
        vertex.VertexGeminiProvider(settings(vertex_search_enabled=False)).search_json("research", MODEL, "s", {}, SCHEMA, 1000, 1)
    production = settings().model_copy(update={"env": "production"})
    assert vertex.VertexGeminiProvider(production).search_json("research", MODEL, "s", {}, SCHEMA, 1000, 1).provider == "vertex"
    assert len(calls) == 1


def fallback_settings(**kw):
    second = "gemini-test-fallback"
    return flat(**{"paperaid_gemini_models": {**gemini.CONFIRMED_MODELS, second: gemini.CONFIRMED_MODELS[MODEL]},
                   "first_audit_model": second, "gemini_fallbacks": {"planner": ["first_audit"]},
                   "vertex_prices": {MODEL: PRICE, second: PRICE}} | kw)


def test_fallback_is_frozen_vertex_only_and_budget_checked(sdk):
    calls, answers = sdk
    answers[:] = [errors.APIError(503, {}), response()]
    ai, records = runner(fallback_settings())
    assert ai._call("plan", {}, SCHEMA, Answer).ok
    assert [c["model"] for c in calls] == [MODEL, "gemini-test-fallback"]
    assert [r.provider for r in records] == ["vertex", "vertex"]
    assert records[0].error_code == "PROVIDER_UNAVAILABLE" and records[0].cost_usd == 0 and records[1].fallback_attempt == 1


def test_permission_error_never_falls_back(sdk):
    calls, answers = sdk
    answers[:] = [errors.APIError(403, {}), response()]
    ai, _ = runner(fallback_settings())
    with pytest.raises(PermanentStageError, match="VERTEX_PERMISSION"):
        ai._call("plan", {}, SCHEMA, Answer)
    assert len(calls) == 1


def test_no_fallback_on_billed_invalid_response(sdk):
    calls, answers = sdk
    answers[:] = [response("{"), response()]
    ai, records = runner(fallback_settings())
    with pytest.raises(RetryableStageError, match="MALFORMED_OUTPUT"):
        ai._call("plan", {}, SCHEMA, Answer)
    assert len(calls) == 1 and records[0].cost_usd > 0


def test_a_timeout_reserves_its_estimate_against_the_cap(sdk):
    calls, answers = sdk
    answers[:] = [httpx.ReadTimeout("slow"), httpx.ReadTimeout("slow")]
    ai, records = runner(fallback_settings())
    with pytest.raises(RetryableStageError, match="VERTEX_TIMEOUT"):
        ai._call("plan", {}, SCHEMA, Answer)
    assert len(calls) == len(records) == 2
    assert all(r.cost_usd == 0 and r.reserved_usd == r.estimated_cost_usd > 0 and r.pricing_status == "UNKNOWN_BILLING" for r in records)


def test_more_expensive_or_unverified_fallback_refused():
    with pytest.raises(PermanentStageError, match="VERTEX_FALLBACK_PRICE"):
        current_engine(fallback_settings(vertex_prices={MODEL: PRICE, "gemini-test-fallback": {**PRICE, "output": 10}}))
    with pytest.raises(PermanentStageError, match="VERTEX_PRICING_UNVERIFIED"):
        current_engine(fallback_settings(vertex_prices={MODEL: PRICE}))


def test_fallbacks_must_name_stages():
    with pytest.raises(ValidationError, match="GEMINI_FALLBACKS"):
        settings(gemini_fallbacks={"planner": ["openai:gpt-6-sol"]})


def test_budget_refusal_makes_no_call(sdk):
    calls, _ = sdk
    ai, records = runner(flat(), budget=0)
    with pytest.raises(PermanentStageError, match="BUDGET_EXCEEDED"):
        ai._call("plan", {}, SCHEMA, Answer)
    assert not calls and not records


def test_unverified_vertex_prices_block_quote_and_calls(sdk):
    calls, _ = sdk
    s = flat(vertex_prices={}, model_prices={REF: (1, 2, .1)})
    assert REF not in s.model_prices  # bypassing verification via MODEL_PRICES is refused
    assert not s.provider_configured(REF) and not s.ai_configured
    ai, records = runner(s)
    with pytest.raises(PermanentStageError, match="VERTEX_PRICING_UNVERIFIED"):
        ai._call("plan", {}, SCHEMA, Answer)
    from app.pricing.quote import _step_usd
    with pytest.raises(PermanentStageError, match="VERTEX_PRICING_UNVERIFIED"):
        _step_usd(s, "plan", 100, 10)
    assert not calls and not records
    assert costs.price_for("google", MODEL) == (.75, 3.75, .75)  # the direct Gemini API's historical pricing is untouched


def test_frozen_prices_do_not_move_with_settings():
    from app.pricing.quote import _step_usd

    s = flat()
    e = work_engine(s, "COURSEWORK")
    before = _step_usd(s, "w_draft", 1000, 100, e)
    changed = flat(vertex_prices={MODEL: {**PRICE, "output": 200}})
    assert _step_usd(changed, "w_draft", 1000, 100, e) == before
    assert _step_usd(changed, "w_draft", 1000, 100, work_engine(changed, "COURSEWORK")) > before


@pytest.mark.parametrize("block", [False, True])
def test_real_job_pipeline_runs_on_the_gemini_workflow_and_refunds_failed_generation(fixed_client, monkeypatch, block):
    """Full API → quote/hold → worker → Vertex adapter → schema → export/settle, with only the SDK faked."""
    from app.runtime import get_runtime
    from tests.fake_models import FakeModels
    from tests.test_api import REFINE_FORMAT, STUDENT, start_job, wait

    rt = get_runtime()
    configured = Settings.model_validate({**rt.settings.model_dump(), "openai_api_key": None, "anthropic_api_key": None, "gemini_api_key": None})
    monkeypatch.setattr(rt, "settings", configured)
    monkeypatch.setattr(orchestration, "provider_for", providers.provider_for)
    by_prompt = sorted(((orchestration.PROMPTS[step.prompt], task) for task, step in STEPS.items()), key=lambda p: -len(p[0]))
    calls = []

    def generate(**kw):
        system = kw["config"].system_instruction
        task = next(t for prompt, t in by_prompt if system.startswith(prompt))
        data = json.loads(kw["contents"].split("<paper_data>\n", 1)[1].rsplit("\n</paper_data>", 1)[0])
        calls.append((task, kw["model"]))
        return response("", "SAFETY") if block and task == "refine" else response(json.dumps(FakeModels.default(task, data)))

    monkeypatch.setattr(vertex, "_vertex_client", lambda *args: SimpleNamespace(models=SimpleNamespace(generate_content=generate)))
    balance_before = fixed_client.get("/api/wallet", headers=STUDENT).json()
    job_id, quote = start_job(fixed_client, selection=REFINE_FORMAT)
    assert fixed_client.post(f"/api/jobs/{job_id}/submit", headers=STUDENT, json={"quoteId": quote["id"]}).status_code == 200
    job = wait(fixed_client, job_id)
    actual = rt.store.get(job_id)
    assert calls and all(c.provider == "vertex" for c in actual.model_calls)
    assert actual.quote.engine.vertex_routes and actual.cost_usd > 0
    if block:
        assert job["status"] == "FAILED" and job["failure"]["code"] == "VERTEX_SAFETY_BLOCK"
        after = fixed_client.get("/api/wallet", headers=STUDENT).json()
        assert not job["outputs"]
        assert (after["available"], after["held"]) == (balance_before["available"], balance_before["held"])
        assert job["billing"]["state"] == "RELEASED" and job["paymentStatus"] == "REFUNDED"
    else:
        assert job["status"] == "COMPLETED" and job["paymentStatus"] == "PAID"
        assert ("review", "gemini-3.1-pro-preview") in calls and ("refine", MODEL) in calls
        assert fixed_client.get(f"/api/jobs/{job_id}/outputs/paper", headers=STUDENT).content.startswith(b"PK")


def test_live_check_refuses_without_opt_in(monkeypatch, sdk):
    import sys

    from app.ai import vertex_check

    calls, _ = sdk
    monkeypatch.setattr(sys, "argv", ["vertex_check"])
    with pytest.raises(SystemExit) as stopped:
        vertex_check.main()
    assert stopped.value.code == 2 and not calls


def test_a_search_gemini_declines_to_recite_finds_nothing_and_the_step_goes_on(sdk):
    """Live 2026-10-07: Gemini stopped one proposal search with RECITATION (it will not repeat a web page
    word for word) and the whole chapter failed. A declined search now finds nothing for that need."""
    from app.proposals.ai import ProposalRunner
    from app.works.ai import WorkRunner

    _, answers = sdk
    answers[:] = [response("", "RECITATION") for _ in range(3)]
    records = []
    s = flat()
    for cls in (ProposalRunner, WorkRunner):
        ai = cls(s, records.append, lambda: 0, 5)
        assert ai.search("vaccine uptake", "malaria vaccine uptake Mukono", 2, lambda q: True) == []
    answer = AIRunner(s, records.append, lambda: 0, 5).research_claim("Uptake was 60%.", "malaria vaccine uptake", True, 2, lambda q: True)
    assert answer.support == "NOT_FOUND" and not answer.sources
    assert [r.error_code for r in records] == ["", "", ""] and all(r.safety_block and r.cost_usd > 0 for r in records)
