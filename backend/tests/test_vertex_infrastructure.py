"""Provider capability tests only. No task/model routing policy or external requests.

SDK generation/ADC/network are fake at their boundaries. All inputs are artificial.
"""

from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import google.auth
import httpx
import pytest
from google.auth.credentials import AnonymousCredentials
from google.auth.exceptions import DefaultCredentialsError, RefreshError, TransportError
from google.genai import errors, models, types

from app.ai import gemini, providers, vertex
from app.ai.vertex_request import VertexOptions
from app.core.config import Settings
from app.core.errors import PermanentStageError, RetryableStageError

MODEL = "gemini-3.8-flash"  # tested connectivity/capability, not a PaperAid function assignment
SCHEMA = {"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"], "additionalProperties": False}


@pytest.fixture(autouse=True)
def no_http_or_auth_refresh(monkeypatch):
    from google.auth.transport.requests import Request

    def blocked(*args, **kw):
        raise AssertionError("Infrastructure tests cannot make HTTP requests or refresh ADC")
    monkeypatch.setattr(httpx.Client, "request", blocked)
    monkeypatch.setattr(httpx.Client, "send", blocked)
    monkeypatch.setattr(Request, "__call__", blocked)


def settings(**kw):
    return Settings(_env_file=None, vertex_project="paperaid", vertex_location="global",
                    openai_api_key=None, anthropic_api_key=None, gemini_api_key=None, **kw)


def response(text='{"ok":true}', finish="STOP", **kw):
    return types.GenerateContentResponse.model_validate({
        "candidates": [{"content": {"parts": [{"text": text}]}, "finishReason": finish}],
        "usageMetadata": {"promptTokenCount": 116, "candidatesTokenCount": 5, "thoughtsTokenCount": 109,
                          "cachedContentTokenCount": 0},
        "modelVersion": MODEL, **kw,
    })


@pytest.fixture
def sdk(monkeypatch):
    calls, answers = [], [response()]
    def generate(**kw):
        calls.append(kw)
        value = answers.pop(0)
        if isinstance(value, Exception):
            raise value
        return value
    monkeypatch.setattr(vertex, "_vertex_client", lambda *args: SimpleNamespace(models=SimpleNamespace(generate_content=generate)))
    return calls, answers


def test_explicit_model_and_existing_json_boundary_need_no_task_policy(sdk):
    calls, _ = sdk
    provider, model = providers.provider_for("vertex:" + MODEL, settings())
    result = provider.json("unclassified_caller_label", model, "Exact caller instructions", {"artificial": "input"}, SCHEMA, 512)
    assert calls[0]["model"] == model == result.model == MODEL and result.provider == "vertex"
    assert calls[0]["config"].system_instruction == "Exact caller instructions"
    assert calls[0]["config"].response_json_schema == SCHEMA
    assert calls[0]["config"].response_mime_type == "application/json"
    assert "<paper_data>" in calls[0]["contents"]
    assert result.text == '{"ok":true}' and not result.error_code and len(calls) == 1


@pytest.mark.parametrize("ref", [MODEL, "vertex:" + MODEL])
def test_generic_boundary_accepts_explicit_model_reference(sdk, ref):
    calls, _ = sdk
    result = vertex.VertexGeminiProvider(settings()).generate(ref, "verbatim", "artificial input", VertexOptions(max_output_tokens=512))
    assert calls[0]["model"] == result.model == MODEL
    assert calls[0]["contents"] == "artificial input" and calls[0]["config"].system_instruction == "verbatim"


def test_other_registered_model_is_not_replaced_by_flash(sdk):
    calls, answers = sdk
    model = "gemini-contract-only"
    spec = gemini.GeminiModel(capabilities=frozenset({gemini.Capability.JSON, gemini.Capability.WRITING}),
                             evidence="test fixture only", max_output_tokens=1000, context_tokens=8000)
    provider = vertex.VertexGeminiProvider(settings(paperaid_gemini_models={model: spec}))
    answers[:] = [response().model_copy(update={"model_version": model})]
    result = provider.generate(model, "s", "artificial input", VertexOptions(max_output_tokens=123))
    assert result.model_version == result.model == calls[0]["model"] == model
    assert calls[0]["config"].max_output_tokens == 123 and len(calls) == 1


@pytest.mark.parametrize("model,code", [("", "VERTEX_INVALID_MODEL"), ("openai:gpt-6-sol", "VERTEX_INVALID_MODEL"),
                                      ("google:" + MODEL, "VERTEX_INVALID_MODEL"), ("bad/model", "VERTEX_INVALID_MODEL"),
                                      ("gemini-unregistered", "GEMINI_MODEL_UNVERIFIED")])
def test_invalid_or_unregistered_identifiers_never_reach_sdk(sdk, model, code):
    calls, _ = sdk
    with pytest.raises(PermanentStageError, match=code):
        vertex.VertexGeminiProvider(settings()).generate(model, "s", "artificial input", VertexOptions(max_output_tokens=100))
    assert not calls


@pytest.mark.parametrize("level", ["LOW", "MEDIUM", "HIGH"])
def test_request_options_forward_without_feature_defaults(sdk, level):
    calls, _ = sdk
    safety = types.SafetySetting(category="HARM_CATEGORY_HARASSMENT", threshold="BLOCK_MEDIUM_AND_ABOVE")
    options = VertexOptions(max_output_tokens=512, temperature=0.25, top_p=0.8,
                            response_mime_type="application/json", response_json_schema=SCHEMA,
                            thinking_config=types.ThinkingConfig(thinking_level=level, include_thoughts=True), safety_settings=(safety,))
    vertex.VertexGeminiProvider(settings()).generate(MODEL, "exact system", "artificial content", options)
    config = calls[0]["config"]
    assert config.temperature == 0.25 and config.top_p == 0.8 and config.max_output_tokens == 512
    assert config.thinking_config == options.thinking_config and config.safety_settings == [safety]
    assert config.system_instruction == "exact system" and config.automatic_function_calling.disable


def test_supported_options_and_media_convert_to_native_vertex_payload(sdk):
    """Use the installed SDK's actual converter without invoking its model/HTTP methods."""
    calls, _ = sdk
    safety = types.SafetySetting(category="HARM_CATEGORY_HARASSMENT", threshold="BLOCK_MEDIUM_AND_ABOVE")
    contents = [types.Content(role="user", parts=[types.Part.from_text(text="artificial"),
                                                types.Part.from_bytes(data=b"fixture", mime_type="application/pdf")])]
    options = VertexOptions(max_output_tokens=512, temperature=0.2, top_p=0.8,
        thinking_config=types.ThinkingConfig(thinking_level="LOW"), response_mime_type="application/json",
        response_json_schema=SCHEMA, safety_settings=(safety,))
    vertex.VertexGeminiProvider(settings()).generate(MODEL, "verbatim", contents, options)
    params = types._GenerateContentParameters(**calls[0])
    body = models._GenerateContentParameters_to_vertex(SimpleNamespace(project="paperaid", location="global", vertexai=True), params)
    config = body["generationConfig"]
    assert body["_url"]["model"] == "publishers/google/models/" + MODEL
    assert config["maxOutputTokens"] == 512 and config["responseJsonSchema"] == SCHEMA
    assert config["temperature"] == 0.2 and config["topP"] == 0.8
    assert config["thinkingConfig"].thinking_level == types.ThinkingLevel.LOW
    assert body["systemInstruction"]["parts"][0]["text"] == "verbatim"
    assert body["contents"][0]["parts"][1]["inlineData"].mime_type == "application/pdf"
    assert body["contents"][0]["parts"][1]["inlineData"].data == b"fixture"


def test_unspecified_options_do_not_add_thinking_or_sampling_policy(sdk):
    calls, _ = sdk
    vertex.VertexGeminiProvider(settings()).generate(MODEL, "", "artificial input", VertexOptions(max_output_tokens=100))
    config = calls[0]["config"]
    assert config.thinking_config is None and config.temperature is None and config.top_p is None
    assert config.tools is None and config.tool_config is None and config.safety_settings is None


@pytest.mark.parametrize("opts", [{"temperature": float("nan")}, {"temperature": 3}, {"top_p": -0.1},
                                 {"max_output_tokens": True}, {"max_output_tokens": 0}, {"http_options": {"base_url": "https://bad"}},
                                 {"automatic_function_calling": {"disable": False}},
                                 {"response_json_schema": SCHEMA},
                                 {"thinking_config": {"thinking_level": "LOW", "thinking_budget": 100}}])
def test_invalid_options_are_sanitized_before_sdk(sdk, opts):
    calls, _ = sdk
    with pytest.raises(PermanentStageError, match="VERTEX_REQUEST_UNSUPPORTED"):
        vertex.VertexGeminiProvider(settings()).generate(MODEL, "private sentinel", "private sentinel", {"max_output_tokens": 100, **opts})
    assert not calls


@pytest.mark.parametrize("opts", [{"max_output_tokens": 100_000}, {"thinking_config": {"thinking_level": "MINIMAL"}},
                                 {"thinking_config": {"thinking_budget": 100}}])
def test_unsupported_model_limits_or_thinking_settings_refused(sdk, opts):
    calls, _ = sdk
    with pytest.raises(PermanentStageError):
        vertex.VertexGeminiProvider(settings()).generate(MODEL, "s", "artificial input", {"max_output_tokens": 100, **opts})
    assert not calls


def test_budget_style_thinking_is_configurable_for_model_that_declares_it(sdk):
    calls, _ = sdk
    name = "gemini-budget-contract"
    spec = gemini.GeminiModel(capabilities=frozenset({gemini.Capability.JSON, gemini.Capability.REASONING}),
                             evidence="test fixture only", max_output_tokens=1000, context_tokens=8000, thinking_budget_range=(-1, 1000))
    vertex.VertexGeminiProvider(settings(paperaid_gemini_models={name: spec})).generate(name, "s", "artificial input",
        VertexOptions(max_output_tokens=512, response_mime_type="application/json", thinking_config=types.ThinkingConfig(thinking_budget=100)))
    assert calls[0]["config"].thinking_config.thinking_budget == 100


@pytest.mark.parametrize("mime", ["image/png", "image/jpeg", "application/pdf", "audio/wav", "audio/mpeg", "text/plain"])
def test_multimodal_inline_input_is_forwarded_without_file_io(sdk, mime):
    calls, _ = sdk
    contents = [types.Content(role="user", parts=[types.Part.from_text(text="Artificial media test"),
                                                types.Part.from_bytes(data=b"artificial fixture", mime_type=mime)])]
    result = vertex.VertexGeminiProvider(settings()).generate(MODEL, "caller system", contents, VertexOptions(max_output_tokens=100))
    assert not result.error_code and calls[0]["contents"] is contents
    assert calls[0]["contents"][0].parts[1].inline_data.data == b"artificial fixture"


@pytest.mark.parametrize("uri", ["gs://fixture-bucket/fixture.pdf", "https://example.org/fixture.pdf"])
def test_document_uri_is_forwarded_without_fetching_or_uploading(sdk, uri):
    calls, _ = sdk
    content = types.Content(role="user", parts=[types.Part.from_uri(file_uri=uri, mime_type="application/pdf")])
    vertex.VertexGeminiProvider(settings()).generate(MODEL, "s", content, VertexOptions(max_output_tokens=100))
    assert calls[0]["contents"] is content and content.parts[0].file_data.file_uri == uri


@pytest.mark.parametrize("part,code", [
    (types.Part.from_bytes(data=b"test", mime_type="video/mp4"), "AI_CAPABILITY_UNSUPPORTED"),
    (types.Part.from_bytes(data=b"", mime_type="image/png"), "VERTEX_REQUEST_UNSUPPORTED"),
    (types.Part.from_uri(file_uri="file:///private/file.pdf", mime_type="application/pdf"), "VERTEX_REQUEST_UNSUPPORTED"),
    (types.Part.from_uri(file_uri="https://user:secret@example.org/file.pdf", mime_type="application/pdf"), "VERTEX_REQUEST_UNSUPPORTED"),
    (types.Part(text="ambiguous", inline_data=types.Blob(data=b"test", mime_type="image/png")), "VERTEX_REQUEST_UNSUPPORTED"),
])
def test_unsupported_media_refused_without_sdk_or_sensitive_uri(sdk, part, code):
    calls, _ = sdk
    with pytest.raises(PermanentStageError, match=code) as err:
        vertex.VertexGeminiProvider(settings()).generate(MODEL, "s", [types.Content(role="user", parts=[part])], VertexOptions(max_output_tokens=100))
    assert not calls and "secret" not in str(err.value) and "private" not in str(err.value)


def test_media_requires_declared_model_capability(sdk):
    calls, _ = sdk
    spec = gemini.GeminiModel(capabilities=frozenset({gemini.Capability.JSON, gemini.Capability.WRITING}),
                             evidence="test fixture only", max_output_tokens=1000, context_tokens=8000)
    s = settings(paperaid_gemini_models={MODEL: spec})
    with pytest.raises(PermanentStageError, match="AI_CAPABILITY_UNSUPPORTED"):
        vertex.VertexGeminiProvider(s).generate(MODEL, "s", [types.Content(parts=[types.Part.from_bytes(data=b"test", mime_type="image/png")])],
                                                VertexOptions(max_output_tokens=100))
    assert not calls


def grounded():
    return response().model_copy(update={"candidates": [types.Candidate(content=types.Content(parts=[types.Part(text='{"ok":true}')]),
        finish_reason="STOP", grounding_metadata=types.GroundingMetadata(web_search_queries=["artificial query", "artificial query"],
        grounding_chunks=[types.GroundingChunk(web=types.GroundingChunkWeb(uri="https://example.org/source", title="Artificial source"))],
        grounding_supports=[types.GroundingSupport(segment=types.Segment(start_index=0, end_index=11, text='{"ok":true}'), grounding_chunk_indices=[0])],
        search_entry_point=types.SearchEntryPoint(rendered_content="<div>Artificial suggestions</div>")))]})


def test_grounding_config_metadata_and_verbatim_system(sdk):
    calls, answers = sdk
    answers[:] = [grounded()]
    options = VertexOptions(max_output_tokens=512, response_mime_type="application/json", response_json_schema=SCHEMA,
                            grounding=types.GoogleSearch(exclude_domains=["example.invalid"]), max_grounding_queries=2)
    result = vertex.VertexGeminiProvider(settings(vertex_search_enabled=True)).generate(MODEL, "verbatim original instructions", "artificial input", options)
    config = calls[0]["config"]
    assert config.system_instruction == "verbatim original instructions"
    assert config.tools[0].google_search.exclude_domains == ["example.invalid"]
    assert result.queries == ["artificial query", "artificial query"]
    assert result.usage.search_calls == result.usage.billable_units["google_search_query"] == 2
    assert result.sources == ["https://example.org/source"] and result.grounding["sources"][0]["title"] == "Artificial source"
    assert result.grounding["citations"] and result.grounding["searchSuggestions"] and not result.error_code


@pytest.mark.parametrize("environment", ["local", "production"])
def test_grounding_switched_off_is_refused_by_generic_boundary(sdk, environment):
    calls, _ = sdk
    s = settings(vertex_search_enabled=False).model_copy(update={"env": environment})
    with pytest.raises(PermanentStageError, match="VERTEX_GROUNDING_DISABLED"):
        vertex.VertexGeminiProvider(s).generate(MODEL, "s", "artificial input", VertexOptions(max_output_tokens=100,
            grounding=types.GoogleSearch(), max_grounding_queries=1))
    assert not calls


def test_missing_grounding_and_query_overrun_are_charged_not_failed(sdk):
    """No sources is a legitimate answer (the caller's source check decides); extra queries are billed."""
    _, answers = sdk
    p = vertex.VertexGeminiProvider(settings(vertex_search_enabled=True))
    options = VertexOptions(max_output_tokens=100, grounding=types.GoogleSearch(), max_grounding_queries=1)
    answers[:] = [response(), grounded()]
    empty = p.generate(MODEL, "s", "artificial input", options)
    assert not empty.error_code and not empty.sources and not empty.queries
    overrun = p.generate(MODEL, "s", "artificial input", options)
    assert not overrun.error_code and overrun.usage.search_calls == 2 and overrun.grounding["queriesOverAllowance"] == 1


def test_declared_functions_forward_without_execution_or_second_request(sdk):
    calls, answers = sdk
    answers[:] = [response().model_copy(update={"candidates": [types.Candidate(finish_reason="STOP", content=types.Content(role="model", parts=[
        types.Part(function_call=types.FunctionCall(name="fixture_lookup", args={"key": "synthetic"}), thought_signature=b"signature")]))]})]
    tool = types.Tool(function_declarations=[types.FunctionDeclaration(name="fixture_lookup", parameters_json_schema={"type": "object"})])
    options = VertexOptions(max_output_tokens=100, tools=(tool,), tool_config=types.ToolConfig(
        function_calling_config=types.FunctionCallingConfig(mode="ANY", allowed_function_names=["fixture_lookup"])))
    result = vertex.VertexGeminiProvider(settings()).generate(MODEL, "s", "artificial input", options)
    assert len(calls) == 1 and calls[0]["config"].automatic_function_calling.disable
    assert calls[0]["config"].tool_config == options.tool_config
    assert result.tool_calls[0]["name"] == "fixture_lookup" and result.tool_calls[0]["args"] == {"key": "synthetic"}
    assert result.tool_calls[0]["thoughtSignature"] == b"signature" and not result.error_code


@pytest.mark.parametrize("tool", [types.Tool(code_execution=types.ToolCodeExecution()), types.Tool(google_maps=types.GoogleMaps()),
                                types.Tool(url_context=types.UrlContext()), types.Tool()])
def test_unimplemented_google_services_do_not_run(sdk, tool):
    calls, _ = sdk
    with pytest.raises(PermanentStageError, match="AI_SERVICE_UNIMPLEMENTED"):
        vertex.VertexGeminiProvider(settings()).generate(MODEL, "s", "artificial input", VertexOptions(max_output_tokens=100, tools=(tool,)))
    assert not calls


def test_nested_schema_and_json_without_schema(sdk):
    calls, answers = sdk
    nested = {"type": "object", "properties": {"rows": {"type": "array", "items": {"type": "object",
              "properties": {"n": {"type": "integer"}}, "required": ["n"], "additionalProperties": False}}}, "required": ["rows"]}
    answers[:] = [response('{"rows":[{"n":"bad"}]}'), response('{"rows":[{"n":3}]}'), response("[")]
    p = vertex.VertexGeminiProvider(settings())
    options = VertexOptions(max_output_tokens=100, response_mime_type="application/json", response_json_schema=nested)
    invalid = p.generate(MODEL, "s", "artificial input", options)
    assert invalid.error_code == "SCHEMA_VALIDATION_FAILED" and invalid.usage.output_tokens == 114
    assert not p.generate(MODEL, "s", "artificial input", options).error_code
    assert p.generate(MODEL, "s", "artificial input", VertexOptions(max_output_tokens=100, response_mime_type="application/json")).error_code == "MALFORMED_OUTPUT"
    assert len(calls) == 3  # three explicitly initiated calls, no automatic repair/retry


@pytest.mark.parametrize("schema", [{"type": "object", "properties": {"private sentinel": False}},
                                   {"type": "object", "private sentinel": 1}])
def test_incompatible_nested_schemas_are_refused_without_content_leaks(sdk, schema):
    calls, _ = sdk
    with pytest.raises(PermanentStageError, match="VERTEX_SCHEMA_UNSUPPORTED") as err:
        vertex.VertexGeminiProvider(settings()).generate(MODEL, "s", "artificial input",
            VertexOptions(max_output_tokens=100, response_mime_type="application/json", response_json_schema=schema))
    assert not calls and "private sentinel" not in str(err.value)


def test_modified_option_instance_still_validates_before_sdk(sdk):
    calls, _ = sdk
    options = VertexOptions(max_output_tokens=100).model_copy(update={"max_output_tokens": 0})
    with pytest.raises(PermanentStageError, match="VERTEX_REQUEST_UNSUPPORTED"):
        vertex.VertexGeminiProvider(settings()).generate(MODEL, "s", "artificial input", options)
    assert not calls


@pytest.mark.parametrize("answer,code", [("", "VERTEX_EMPTY_RESPONSE"), ("{", "MALFORMED_OUTPUT")])
def test_bad_structured_text_preserves_metered_usage(sdk, answer, code):
    _, answers = sdk
    answers[:] = [response(answer)]
    result = vertex.VertexGeminiProvider(settings()).json("caller_label", MODEL, "s", {}, SCHEMA, 512)
    assert result.error_code == code and result.usage.output_tokens == 114 and result.error_retryable


def test_truncation_and_missing_usage_and_invalid_envelope(sdk):
    calls, answers = sdk
    answers[:] = [response("{", "MAX_TOKENS"), response(usageMetadata=None), {"usageMetadata": "invalid private sentinel"}]
    p = vertex.VertexGeminiProvider(settings())
    assert p.json("caller_label", MODEL, "s", {}, SCHEMA, 512).stop == "max_tokens"
    assert p.json("caller_label", MODEL, "s", {}, SCHEMA, 512).error_code == "VERTEX_USAGE_MISSING"
    with pytest.raises(RetryableStageError, match="MALFORMED_OUTPUT") as err:
        p.json("caller_label", MODEL, "s", {}, SCHEMA, 512)
    assert "private sentinel" not in str(err.value) and len(calls) == 3


@pytest.mark.parametrize("usage", [{"promptTokenCount": -1, "candidatesTokenCount": 5},
                                 {"promptTokenCount": 10, "candidatesTokenCount": 5, "cachedContentTokenCount": 20}])
def test_contradictory_usage_cannot_be_verified_or_reduce_cost(sdk, usage):
    _, answers = sdk
    answers[:] = [response(usageMetadata=usage)]
    result = vertex.VertexGeminiProvider(settings()).generate(MODEL, "s", "artificial input", VertexOptions(max_output_tokens=100))
    assert result.error_code == "VERTEX_USAGE_MISSING"
    assert min(result.usage.input_tokens, result.usage.output_tokens, result.usage.cached_tokens) >= 0


def test_unsupported_output_modality_is_not_a_successful_text_response(sdk):
    _, answers = sdk
    answers[:] = [response().model_copy(update={"candidates": [types.Candidate(finish_reason="STOP",
        content=types.Content(parts=[types.Part.from_bytes(data=b"artificial image", mime_type="image/png")]))]})]
    result = vertex.VertexGeminiProvider(settings()).generate(MODEL, "s", "artificial input", VertexOptions(max_output_tokens=100))
    assert result.error_code == "VERTEX_OUTPUT_UNSUPPORTED" and result.usage.output_tokens == 114


def test_usage_normalization_thought_text_and_safety_metadata(sdk):
    _, answers = sdk
    answers[:] = [response().model_copy(update={"candidates": [types.Candidate(finish_reason="STOP", content=types.Content(parts=[
        types.Part(text="private reasoning", thought=True), types.Part(text='{"ok":true}')]))]}),
        response("", "SAFETY", promptFeedback={"blockReason": "SAFETY"})]
    p = vertex.VertexGeminiProvider(settings())
    first = p.generate(MODEL, "s", "artificial input", VertexOptions(max_output_tokens=100))
    assert first.text == '{"ok":true}' and first.model_version == MODEL
    assert (first.usage.input_tokens, first.usage.visible_output_tokens, first.usage.thinking_tokens,
            first.usage.output_tokens, first.usage.cached_tokens) == (116, 5, 109, 114, 0)
    assert first.usage.latency_ms >= 0 and first.finish_reason == "STOP"
    blocked = p.generate(MODEL, "s", "artificial input", VertexOptions(max_output_tokens=100))
    assert blocked.stop == "refusal" and blocked.safety_block and blocked.safety["promptBlockReason"] == "SAFETY"


@pytest.mark.parametrize("exc,code,retryable", [
    (errors.APIError(401, {}), "VERTEX_AUTH", False), (errors.APIError(403, {}), "VERTEX_PERMISSION", False),
    (errors.APIError(404, {}), "VERTEX_MODEL_UNAVAILABLE", False), (errors.APIError(429, {}), "VERTEX_RATE_LIMIT", True),
    (errors.APIError(429, {"error": {"message": "quota exceeded"}}), "VERTEX_QUOTA", False),
    (errors.APIError(429, {"error": {"details": [{"reason": "RATE_LIMIT_EXCEEDED", "@type": "google.rpc.QuotaFailure"}]}}), "VERTEX_RATE_LIMIT", True),
    (errors.APIError(400, {"error": {"status": "INVALID_ARGUMENT", "details": [{"reason": "INVALID_MODEL"}]}}), "VERTEX_INVALID_MODEL", False),
    (errors.APIError(500, {}), "PROVIDER_UNAVAILABLE", True),
    (httpx.ReadTimeout("private sentinel"), "VERTEX_TIMEOUT", True),
    (httpx.ConnectError("private sentinel"), "PROVIDER_UNAVAILABLE", True),
    (RefreshError("private sentinel"), "VERTEX_AUTH", False), (TransportError("private sentinel"), "PROVIDER_UNAVAILABLE", True),
    (ValueError("private sentinel"), "VERTEX_REQUEST_UNSUPPORTED", False),
])
def test_error_categories_are_sanitized_and_do_not_retry(sdk, exc, code, retryable, caplog):
    calls, answers = sdk
    answers[:] = [exc]
    with pytest.raises(RetryableStageError if retryable else PermanentStageError, match=code) as err:
        vertex.VertexGeminiProvider(settings()).generate(MODEL, "private sentinel", "private sentinel", VertexOptions(max_output_tokens=100))
    assert len(calls) == 1 and "private sentinel" not in str(err.value) and "private sentinel" not in caplog.text
    assert err.value.__cause__ is None


def test_client_reuse_thread_safety_and_teardown(monkeypatch):
    vertex.close_vertex_clients()
    accounts, clients, closed = [], [], []
    credentials = AnonymousCredentials()
    monkeypatch.setattr(google.auth, "default", lambda **kw: accounts.append(kw) or (credentials, "different-inferred-project"))
    def client(**kw):
        clients.append(kw)
        return SimpleNamespace(close=lambda: closed.append(True))
    monkeypatch.setattr(vertex.genai, "Client", client)
    try:
        with ThreadPoolExecutor(max_workers=8) as pool:
            returned = list(pool.map(lambda _: vertex._vertex_client("paperaid", "global", 120), range(30)))
        assert len(accounts) == len(clients) == 1 and all(c is returned[0] for c in returned)
        assert clients[0]["credentials"] is credentials and clients[0]["vertexai"]
        assert clients[0]["project"] == accounts[0]["quota_project_id"] == "paperaid"
        assert clients[0]["location"] == "global" and "api_key" not in clients[0]
        assert clients[0]["http_options"].retry_options.attempts == 1
        vertex._vertex_client("paperaid", "global", 60)
        assert len(clients) == 2  # timeout is server config, not a per-model selection
    finally:
        vertex.close_vertex_clients()
    assert len(closed) == 2 and not vertex._CLIENTS


def test_real_sdk_constructor_prefers_explicit_adc_over_legacy_key_environment(monkeypatch):
    """Construct/close SDK only; no auth refresh and no HTTP/model method is called."""
    vertex.close_vertex_clients()
    credentials = AnonymousCredentials()
    monkeypatch.setenv("GEMINI_API_KEY", "artificial-unused-legacy-key")
    monkeypatch.setattr(google.auth, "default", lambda **kw: (credentials, "other"))
    try:
        client = vertex._vertex_client("paperaid", "global", 60)
        assert client._api_client._credentials is credentials and client._api_client.api_key is None
        assert client._api_client.project == "paperaid" and client._api_client.location == "global"
    finally:
        vertex.close_vertex_clients()


def test_missing_adc_is_not_cached_or_logged(monkeypatch, caplog):
    vertex.close_vertex_clients()
    monkeypatch.setattr(google.auth, "default", lambda **kw: (_ for _ in ()).throw(DefaultCredentialsError("private sentinel")))
    with pytest.raises(PermanentStageError, match="VERTEX_AUTH") as err:
        vertex._vertex_client("paperaid", "global", 60)
    assert not vertex._CLIENTS and "private sentinel" not in str(err.value) and "private sentinel" not in caplog.text


@pytest.mark.parametrize("ref,cls", [("openai:gpt-6-sol", providers.OpenAIProvider),
    ("anthropic:claude-opus-5-5", providers.AnthropicProvider), ("google:" + MODEL, providers.GeminiProvider),
    ("vertex:" + MODEL, vertex.VertexGeminiProvider)])
def test_provider_namespaces_still_mean_their_original_adapters(ref, cls):
    s = Settings(_env_file=None, vertex_project="paperaid", vertex_location="global",
                 openai_api_key="artificial", anthropic_api_key="artificial", gemini_api_key="artificial")
    p, model = providers.provider_for(ref, s)
    assert isinstance(p, cls) and model == ref.partition(":")[2]
