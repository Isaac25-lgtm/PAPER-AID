# ruff: noqa: F811  (tests take the shared `sdk` fixture imported below)
"""Codex's audit of the Gemini integration (2026-10-07): one regression per finding. SDK boundary mocked."""

import json
import time

import httpx
import pytest
from google.genai import errors
from pydantic import ValidationError as SDKValidationError

from app.ai import orchestration, vertex
from app.ai.orchestration import FINAL_PART_WORDS, AIRunner, priced_engine
from app.ai.providers import ModelResult, Usage
from app.core.errors import PermanentStageError, RetryableStageError
from app.jobs.models import Engine
from tests.test_vertex import (
    FORGED,
    LINK,
    MODEL,
    SCHEMA,
    Answer,
    Cache,
    Found,
    flat,
    response,
    runner,
    sdk,  # noqa: F401  (the mocked SDK boundary, shared)
    searched,
    settings,
)

# --- 1. Google Search can't run up spending past the cap ------------------------------------------


def test_a_search_that_runs_far_more_queries_is_charged_and_nothing_more_is_bought(sdk):
    calls, answers = sdk
    answers[:] = [searched(json.dumps({"findings": []}), [f"q{i}" for i in range(50)]), response()]
    ai, records = runner(flat(), budget=0.15)
    ai._call("research", {"claim": "c"}, {"type": "object"}, Found, max_searches=1)
    assert records[0].billable_units == {"google_search_query": 50} and records[0].cost_usd > 0.15
    assert ai.budget_reached
    with pytest.raises(PermanentStageError, match="BUDGET_EXCEEDED"):
        ai._call("plan", {}, SCHEMA, Answer)
    assert len(calls) == 1  # the second call was refused before the SDK


def test_spend_is_reserved_for_the_queries_a_search_really_runs():
    from app.ai import costs

    s = flat()
    assert costs.SEARCH_RESERVE_FACTOR >= 3
    one = costs.search_fee_usd("vertex", 2 * costs.SEARCH_RESERVE_FACTOR, s.model_unit_prices, MODEL)
    assert one == pytest.approx(2 * costs.SEARCH_RESERVE_FACTOR * 0.01)
    ai, records = runner(s, budget=one + 0.001)  # tokens are not covered: refused before the call
    with pytest.raises(PermanentStageError, match="BUDGET_EXCEEDED"):
        ai._call("research", {"claim": "c"}, {"type": "object"}, Found, max_searches=2)
    assert not records


# --- 2. A request that may have been billed reserves its estimate ------------------------------------


@pytest.mark.parametrize("exc,code,reserved", [
    (httpx.ReadTimeout("slow"), "VERTEX_TIMEOUT", True),
    (httpx.ReadError("reset"), "VERTEX_CONNECTION_LOST", True),
    (httpx.RemoteProtocolError("broken"), "VERTEX_CONNECTION_LOST", True),
    (SDKValidationError.from_exception_data("GenerateContentResponse", []), "VERTEX_MALFORMED_ENVELOPE", True),
    (httpx.ConnectError("refused"), "PROVIDER_UNAVAILABLE", False),
    (errors.APIError(503, {}), "PROVIDER_UNAVAILABLE", False),
])
def test_unknown_billing_is_reserved_against_the_cap_and_kept_apart_from_cost(sdk, exc, code, reserved):
    _, answers = sdk
    answers[:] = [exc]
    ai, records = runner(flat())
    with pytest.raises(RetryableStageError, match=code):
        ai._call("plan", {}, SCHEMA, Answer)
    call = records[0]
    assert call.cost_usd == 0 and (call.reserved_usd > 0) == reserved
    assert call.pricing_status == ("UNKNOWN_BILLING" if reserved else "NOT_CHARGED")


def test_a_lost_answer_then_a_fallback_reserves_one_and_confirms_the_other(sdk):
    from tests.test_vertex import fallback_settings

    _, answers = sdk
    answers[:] = [httpx.ReadError("reset"), response()]
    ai, records = runner(fallback_settings())
    assert ai._call("plan", {}, SCHEMA, Answer).ok
    assert records[0].reserved_usd > 0 and records[0].cost_usd == 0
    assert records[1].cost_usd > 0 and records[1].reserved_usd == 0


def test_a_jobs_spend_counts_its_reservations():
    import inspect

    from app.jobs import pipeline

    source = inspect.getsource(pipeline.StageContext.ai)
    assert "j.reserved_usd = round(j.reserved_usd + call.reserved_usd, 6)" in source
    assert source.count("+ current.reserved_usd") == 2  # both the estimate's and the job's cap


# --- 3. Link resolution is bounded, after the call is recorded, and never buys the answer twice -----


def test_many_slow_links_stop_at_the_deadline_and_the_limit(monkeypatch):
    def slow(link):
        time.sleep(0.3)
        return "https://example.org/" + link[-6:]

    monkeypatch.setattr(vertex, "_resolve", slow)
    monkeypatch.setattr(vertex, "RESOLVE_DEADLINE_S", 0.5)
    links = [f"https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQ{i:06d}" for i in range(300)]
    result = ModelResult(text=json.dumps({"findings": [{"url": u} for u in links]}), usage=Usage(0, 0, 0, 0), provider="vertex", model=MODEL,
                         queries=["q"])
    started = time.monotonic()
    vertex.resolve_sources(result, "")
    assert time.monotonic() - started < 2
    assert result.grounding["linksOverLimit"] == 300 - vertex.MAX_LINKS and len(result.sources) <= vertex.MAX_LINKS


def test_a_retry_after_a_crash_in_link_resolution_reuses_the_paid_answer(sdk, monkeypatch):
    calls, answers = sdk
    answers[:] = [searched(json.dumps({"findings": [{"url": LINK, "quote": "q"}]}), ["q"])]
    cache = Cache()
    ai, records = runner(flat(), cache=cache)

    def crash(result, request_text):
        raise RuntimeError("worker stopped while resolving")

    monkeypatch.setattr(vertex, "resolve_sources", crash)
    with pytest.raises(RuntimeError):
        ai._call("research", {"claim": "c"}, {"type": "object"}, Found, max_searches=2)
    assert len(records) == 1 and records[0].cost_usd > 0  # recorded before resolving
    monkeypatch.undo()
    monkeypatch.setattr(vertex, "_resolve", lambda link: "https://www.who.int/report" if link == LINK else None)
    again, more = runner(flat(), cache=cache)
    answer = again._call("research", {"claim": "c"}, {"type": "object"}, Found, max_searches=2)
    assert answer.findings[0]["url"] == "https://www.who.int/report"
    assert len(calls) == 1 and not more  # no second paid call


# --- 4. A rolled-back release refuses a job priced on this one -------------------------------------------


def test_an_older_release_refuses_a_gemini_priced_engine_instead_of_switching_models(sdk, monkeypatch):
    calls, _ = sdk
    engine = priced_engine(settings())
    assert "prompt:signoff-v1" in engine.content and "prompt:vertex-search-v1" in engine.content
    # How the 2026-10-05 image reads it: no Vertex fields (they are unknown to it), and its prompts lack the new ones.
    older = Engine.model_validate({k: v for k, v in engine.model_dump(by_alias=True).items() if not k.startswith("vertex")})
    assert not older.vertex_routes and orchestration.model_for_engine(older, "analyse") == "openai:gpt-6-luna"
    now = orchestration.content_now()
    monkeypatch.setattr(orchestration, "content_now", lambda: {k: v for k, v in now.items() if k not in ("prompt:signoff-v1", "prompt:vertex-search-v1")})
    ai = AIRunner(settings(), lambda _: None, lambda: 0, 5, engine=older)
    with pytest.raises(PermanentStageError, match="ENGINE_CHANGED"):
        ai._call("analyse", {}, SCHEMA, Answer)
    assert not calls


def test_every_priced_quote_freezes_its_content(fixed_client):
    from app.runtime import get_runtime
    from tests.test_api import start_job

    job_id, _ = start_job(fixed_client, selection={"writing": "AI_CHECK"})
    engine = get_runtime().store.get(job_id).quote.engine
    assert engine.vertex_routes and "prompt:analyse-v3" in engine.content and "prompt:signoff-v1" in engine.content


# --- 5. Sign-off history: per part, never doubled, within the review bound ---------------------------------


def test_each_parts_sign_off_sees_only_that_parts_findings(sdk):
    calls, answers = sdk
    answers[:] = [response() for _ in range(4)]
    ai, _ = runner(flat(), budget=50)
    for round_ in ai.audit_rounds(2):
        for part in ("1 of 2", "2 of 2"):
            ai._call("w_final", {"part": part, "round": round_}, SCHEMA, Answer)
    signoff_part_one = calls[2]["contents"]
    assert '"part": "1 of 2"' in signoff_part_one and signoff_part_one.count('{"ok": true}') == 1


def test_a_pipeline_that_passes_its_own_findings_gets_no_second_copy(sdk):
    calls, answers = sdk
    answers[:] = [response(), response()]
    ai, _ = runner(flat(), budget=50)
    for round_ in ai.audit_rounds(2):
        ai._call("d_report_review", {"part": "1 of 1", **({"previousIssues": ["x"]} if round_ else {})}, SCHEMA, Answer)
    assert "previousAudit" not in calls[1]["contents"]


def test_a_review_part_stays_within_the_bound_once_its_history_is_added(sdk):
    calls, answers = sdk
    long_answer = '{"ok": true}'
    answers[:] = [response(long_answer), response()]
    ai, _ = runner(flat(), budget=50)
    near = " ".join(["word"] * (FINAL_PART_WORDS - 50))
    for _ in ai.audit_rounds(2):
        ai._call("w_final", {"part": "1 of 1", "document": near}, SCHEMA, Answer)
    sent = json.loads(calls[1]["contents"].split("<paper_data>\n", 1)[1].rsplit("\n</paper_data>", 1)[0])
    assert orchestration._words(sent) <= FINAL_PART_WORDS
    assert orchestration._words(orchestration._history([{"issues": ["a b c d e f"] * 500}], 100)) <= 110


# --- 6 and 7. Links found in decoded JSON; provenance claims only what was shown -----------------------


def test_links_written_with_escaped_slashes_are_found(sdk):
    escaped = LINK.replace("/", "\\/")
    result = ModelResult(text='{"findings": [{"url": "' + escaped + '", "quote": "q"}]}', usage=Usage(0, 0, 0, 0), provider="vertex", model=MODEL, queries=["q"])
    vertex.resolve_sources(result, "")
    assert result.sources == ["https://www.who.int/report"] and json.loads(result.text)["findings"][0]["url"] == "https://www.who.int/report"


def test_a_link_from_the_request_or_without_a_search_is_not_a_source_of_this_search(sdk):
    text = json.dumps({"findings": [{"url": LINK, "quote": "q"}]})
    copied = ModelResult(text=text, usage=Usage(0, 0, 0, 0), provider="vertex", model=MODEL, queries=["q"])
    vertex.resolve_sources(copied, json.dumps({"paper": f"see {LINK}"}))
    assert copied.sources == [] and copied.grounding["linksFromRequest"] == 1
    unsearched = ModelResult(text=text, usage=Usage(0, 0, 0, 0), provider="vertex", model=MODEL, queries=[])
    vertex.resolve_sources(unsearched, "")
    assert unsearched.sources == []
    listed = ModelResult(text=json.dumps({"findings": []}), usage=Usage(0, 0, 0, 0), provider="vertex", model=MODEL, queries=["q"],
                         grounding={"sources": [{"index": 0, "url": "https://example.org/page", "title": "t"}]})
    vertex.resolve_sources(listed, "")
    assert listed.sources == ["https://example.org/page"] and listed.grounding["provenance"] == "provider_metadata"
    forged = ModelResult(text=json.dumps({"findings": [{"url": FORGED}]}), usage=Usage(0, 0, 0, 0), provider="vertex", model=MODEL, queries=["q"])
    vertex.resolve_sources(forged, "")
    assert forged.sources == [] and forged.grounding["provenance"] == "resolved_answer_links"


# --- 8. The terms describe what each kind of data sends -----------------------------------------------------


def test_the_terms_disclose_transcripts_and_were_versioned_again():
    from pathlib import Path

    from app.core.config import Settings

    assert Settings(_env_file=None).terms_version == "2026-10-07"
    terms = (Path(__file__).parents[2] / "web/src/features/account/terms.tsx").read_text(encoding="utf-8")
    assert "transcripts" in terms and "after the names and contact details you listed are replaced" in terms
    assert not any(name in terms for name in ("OpenAI", "Anthropic", "Gemini"))

