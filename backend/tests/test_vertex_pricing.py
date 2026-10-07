"""Vertex prices: Google's published rates as dated records, synthetic usage, no ADC or model request."""

import time
from datetime import date
from decimal import Decimal

import pytest
from google.genai import types
from pydantic import ValidationError

from app.ai import costs, gemini, vertex
from app.ai.orchestration import AIRunner, current_engine, vertex_settings
from app.ai.vertex_pricing import FLASH, FLASH_INTRO, FLASH_LITE, PRO_PREVIEW, SEARCH, SOURCE, VERIFIED_VERTEX_PRICES
from app.core.config import Settings
from app.core.errors import PermanentStageError
from app.jobs.models import Engine, ServiceSelection
from app.pricing.quote import _step_usd, price

MODEL = "gemini-3.8-flash"
REF = "vertex:" + MODEL
PRO = "vertex:gemini-3.1-pro-preview"


@pytest.fixture(autouse=True)
def isolate(monkeypatch):
    for name in ("VERTEX_PRICES", "MODEL_PRICES", "MODEL_UNIT_PRICES", "GEMINI_FALLBACKS", "VERTEX_SEARCH_ENABLED",
                 "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GEMINI_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(gemini, "pricing_date", lambda: date(2026, 10, 7))


def settings(**kw):
    return Settings(_env_file=None, vertex_project="paperaid", vertex_location="global",
                    openai_api_key=None, anthropic_api_key=None, gemini_api_key=None, **kw)


@pytest.mark.parametrize("day,expected", [
    (date(2026, 10, 6), (0.75, 3.75, 0.075)),
    (date(2026, 12, 31), (0.75, 3.75, 0.075)),
    (date(2027, 1, 1), (1.50, 7.50, 0.15)),
    (date(2027, 6, 1), (1.50, 7.50, 0.15)),
])
def test_published_dated_rates(day, expected, monkeypatch):
    monkeypatch.setattr(gemini, "pricing_date", lambda: day)
    s = settings()
    assert s.model_prices[REF] == expected
    record = s.vertex_prices[MODEL].at()
    assert record.status == "VERIFIED" and record.source == SOURCE
    assert record.location == "global" and record.service_tier == "standard" and not record.schedule


def test_every_workflow_model_has_a_published_rate():
    s = settings()
    assert s.model_prices["vertex:gemini-3.5-flash-lite"] == (0.30, 2.50, 0.03)
    assert s.model_prices[PRO] == (2.00, 12.00, 0.20)
    assert s.model_long_prices[PRO] == (200_000, 4.00, 18.00, 0.40)
    models = {getattr(s, f"{stage}_model") for stage in gemini.STAGES}
    assert models == set(VERIFIED_VERTEX_PRICES) == set(gemini.CONFIRMED_MODELS)
    assert FLASH_LITE.verified_on == PRO_PREVIEW.verified_on == date(2026, 10, 7)


def test_pro_bills_the_whole_request_at_its_long_context_rates_above_200k():
    s = settings()
    short = costs.cost_usd("vertex", "gemini-3.1-pro-preview", 200_000, 1_000, 0, s.model_prices, long_prices=s.model_long_prices)
    long = costs.cost_usd("vertex", "gemini-3.1-pro-preview", 200_001, 1_000, 0, s.model_prices, long_prices=s.model_long_prices)
    assert short == pytest.approx((200_000 * 2 + 1_000 * 12) / 1e6)
    assert long == pytest.approx((200_001 * 4 + 1_000 * 18) / 1e6)
    # The estimate picks the tier on the worst-case token count, so a request near the line is estimated dear.
    near = costs.estimate_usd("vertex", "gemini-3.1-pro-preview", 420_000, 8_000, s.model_prices, long_prices=s.model_long_prices)
    assert near > costs.estimate_usd("vertex", "gemini-3.1-pro-preview", 420_000, 8_000, s.model_prices)


def test_no_backdating_or_wrong_location():
    assert VERIFIED_VERTEX_PRICES[MODEL].at(date(2026, 10, 5)).status == "UNVERIFIED"
    s = settings().model_copy(update={"vertex_location": "us-central1"})
    assert not s.provider_configured(REF)
    assert REF not in Settings.model_validate(s.model_dump()).model_prices


def test_smoke_usage_exact_decimal_and_no_double_counting():
    response = types.GenerateContentResponse.model_validate({
        "candidates": [{"content": {"parts": [{"text": '{"ready":true}'}]}, "finishReason": "STOP"}],
        "usageMetadata": {"promptTokenCount": 116, "candidatesTokenCount": 5, "thoughtsTokenCount": 109, "cachedContentTokenCount": 0},
    })
    u = vertex.VertexGeminiProvider._result(response, MODEL, time.monotonic(), False).usage
    assert (u.input_tokens, u.visible_output_tokens, u.thinking_tokens, u.output_tokens, u.cached_tokens) == (116, 5, 109, 114, 0)
    exact = costs.vertex_token_cost(u.input_tokens, u.output_tokens, u.cached_tokens, settings().model_prices[REF])
    assert exact == Decimal("0.0005145") == Decimal("0.000087") + Decimal("0.0004275")
    assert Decimal(str(costs.cost_usd("vertex", MODEL, 116, 114, 0, settings().model_prices))) == exact


@pytest.mark.parametrize("record,expected", [(FLASH_INTRO, "0.075"), (FLASH, "0.15"), (FLASH_LITE, "0.03"), (PRO_PREVIEW, "0.2")])
def test_cache_reads_at_discounted_rate(record, expected):
    rates = (record.input, record.output, record.cached)
    assert costs.vertex_token_cost(0, 0, 1_000_000, rates) == Decimal(expected)


def test_unknown_cache_creation_not_given_other_providers_rate():
    with pytest.raises(PermanentStageError, match="VERTEX_PRICING_UNVERIFIED"):
        costs.cost_usd("vertex", MODEL, 10, 5, 0, settings().model_prices, cache_write_tokens=10)


def test_vertex_budget_guard_does_not_borrow_cache_write_multiplier():
    rates = settings().model_prices
    allowed = costs.affordable_output_tokens("vertex", MODEL, 0, 10_000, 0.01075, rates)
    assert allowed == 2666
    assert costs.vertex_token_cost(1000, allowed, 0, rates[REF]) <= Decimal("0.01075")


def test_date_transition_reprices_new_quotes_never_frozen_ones(monkeypatch):
    s = settings()
    original = current_engine(s)
    before = _step_usd(s, "plan", 1000, 100, original)
    frozen = Engine.model_validate_json(original.model_dump_json())
    assert frozen.vertex_prices[MODEL]["effective_until"] == "2026-12-31" and not frozen.vertex_prices[MODEL]["schedule"]
    monkeypatch.setattr(gemini, "pricing_date", lambda: date(2027, 1, 1))
    new = current_engine(s)  # s is deliberately the same object: get_settings() lives for the process
    assert new.vertex_prices[MODEL]["input"] == 1.50
    assert _step_usd(s, "plan", 1000, 100, new) == pytest.approx(2 * before)
    assert _step_usd(s, "plan", 1000, 100, frozen) == before
    assert vertex_settings(s, frozen).model_prices[REF] == (0.75, 3.75, 0.075)


def test_expired_frozen_rate_refuses_new_spend_without_repricing_quote(monkeypatch):
    def unexpected(*args, **kw):
        raise AssertionError("An expired quote must not reach the SDK")

    monkeypatch.setattr(vertex, "_vertex_client", unexpected)
    engine = current_engine(settings())
    before = engine.model_dump_json()
    monkeypatch.setattr(gemini, "pricing_date", lambda: date(2027, 1, 1))
    records = []
    ai = AIRunner(settings(), records.append, lambda: 0, 10, engine=engine)
    with pytest.raises(PermanentStageError, match="VERTEX_PRICE_PERIOD_CHANGED"):
        ai._call("plan", {}, {"type": "object"}, None)
    assert not records and engine.model_dump_json() == before


def test_unverified_model_cannot_bypass_pricing():
    s = settings(model_prices={"vertex:unknown": (0, 0, 0)})
    assert not s.provider_configured("vertex:unknown")
    with pytest.raises(PermanentStageError, match="VERTEX_PRICING_UNVERIFIED"):
        costs.cost_usd("vertex", "unknown", 100, 10, 0, s.model_prices)


def test_explicit_empty_price_registry_closes_the_workflow():
    s = settings(vertex_prices={}, model_prices={REF: (0, 0, 0)})
    assert not s.provider_configured(REF) and REF not in s.model_prices and not s.ai_configured


def test_every_grounding_query_is_charged_at_the_published_rate_above_the_free_allowance():
    assert SEARCH.free_queries_per_month == 5000 and SEARCH.excess_usd_per_1000_queries == 14
    assert SEARCH.per_query_usd == pytest.approx(0.014) and SEARCH.billing_unit == "individual_query"
    assert not SEARCH.grounding_input_tokens_charged and "all Gemini 3" in SEARCH.allowance_scope
    s = settings()
    assert s.model_unit_prices[REF + ":google_search_query"] == pytest.approx(0.014)
    assert costs.search_fee_usd("vertex", 3, s.model_unit_prices, MODEL) == pytest.approx(0.042)
    assert costs.cost_usd("vertex", MODEL, 0, 0, 0, s.model_prices, search_calls=2, unit_prices=s.model_unit_prices) == pytest.approx(0.028)


def test_actual_grounding_queries_and_free_tool_tokens_preserved():
    response = types.GenerateContentResponse.model_validate({
        "candidates": [{"content": {"parts": [{"text": '{"ready":true}'}]}, "finishReason": "STOP",
                        "groundingMetadata": {"webSearchQueries": ["query one", "query one", "query two"]}}],
        "usageMetadata": {"promptTokenCount": 120, "cachedContentTokenCount": 20,
                          "toolUsePromptTokenCount": 500, "candidatesTokenCount": 5, "thoughtsTokenCount": 109},
    })
    result = vertex.VertexGeminiProvider._result(response, MODEL, time.monotonic(), True)
    assert result.queries == ["query one", "query one", "query two"]
    assert result.usage.search_calls == result.usage.billable_units["google_search_query"] == 3
    assert result.usage.tool_input_tokens == 500 and result.usage.input_tokens == 100 and result.usage.cached_tokens == 20


def test_gemini_only_quote_without_keys_adc_or_sdk(monkeypatch):
    def unexpected(*args, **kw):
        raise AssertionError("Quoting must never load ADC or call Vertex")

    monkeypatch.setattr(vertex, "_vertex_client", unexpected)
    s = settings()
    assert s.ai_configured and s.roles_configured
    engine = current_engine(s)
    for selection in (ServiceSelection(writing="AI_CHECK"), ServiceSelection(writing="REFINE", source_check=True)):
        quoted = price(s, selection, 1000, engine=engine)
        assert quoted.lines and quoted.lines[0].amount > 0 and quoted.budget_usd > 0
    assert all(engine.vertex_prices[m]["status"] == "VERIFIED" for m in engine.vertex_prices)


@pytest.mark.parametrize("periods", [(FLASH_INTRO, FLASH_INTRO), (FLASH, FLASH_INTRO), (FLASH, FLASH)])
def test_overlapping_or_unordered_dates_refused(periods):
    with pytest.raises(ValidationError):
        gemini.VertexPrice.model_validate({**FLASH_INTRO.model_dump(), "schedule": [p.model_dump() for p in periods]})


def test_a_long_context_tier_needs_all_its_rates():
    with pytest.raises(ValidationError):
        gemini.VertexPrice.model_validate({**PRO_PREVIEW.model_dump(), "long_output": None})
