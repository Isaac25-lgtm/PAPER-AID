"""Gemini on Vertex AI using ADC. No Developer API key and no legacy-provider fallback.

All structured requests use response_json_schema, not the narrower OpenAPI response_schema.
Unsupported schema keywords fail before a request; the original schema is also validated locally.
Search makes one grounded structured request (verified live 2026-10-07). With a JSON answer, Google
returns the queries it ran but no source list: the sources are the grounding redirect links the model
writes into its answer. Google issues those links; one the model invented does not resolve. Each is
resolved to the page it stands for, and only resolved pages count as sources the search opened.
Google exposes no hard cap on queries: they are counted and charged as run, never a failure.
"""

import atexit
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor, wait
from threading import Lock
from typing import Any
from urllib.parse import urlsplit

import google.auth
import httpx
from google import genai
from google.auth import exceptions as auth_errors
from google.genai import errors, types
from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError, ValidationError
from pydantic import ValidationError as SDKValidationError

from app.ai.gemini import Capability, check_model
from app.ai.providers import GEMINI_BLOCKED, MISCONFIGURED, UNAVAILABLE, ModelResult, Usage, render_user_message
from app.ai.vertex_request import VertexOptions
from app.core.config import Settings
from app.core.errors import PermanentStageError, RetryableStageError

SCHEMA_KEYS = {"$defs", "$ref", "type", "properties", "required", "additionalProperties", "items", "prefixItems", "anyOf", "oneOf",
               "enum", "minimum", "maximum", "minItems", "maxItems", "title", "description", "format", "$id", "$schema"}


def check_schema(schema: dict[str, Any]) -> None:
    """Subset documented for GenerationConfig.responseJsonSchema. Never drop constraints."""
    def visit(node: dict[str, Any], path: str) -> None:
        if not isinstance(node, dict):
            raise PermanentStageError("VERTEX_SCHEMA_UNSUPPORTED", "This response format is not supported by the AI provider.",
                                      "boolean or non-object schema nodes are not supported")
        unknown = set(node) - SCHEMA_KEYS
        if unknown:
            raise PermanentStageError("VERTEX_SCHEMA_UNSUPPORTED", "This response format is not supported by the AI provider.",
                                      "unsupported response-schema constraints")
        ref = node.get("$ref", "")
        if ref and (not ref.startswith("#/$defs/") or ref.count("/") != 2):
            raise PermanentStageError("VERTEX_SCHEMA_UNSUPPORTED", "This response format is not supported by the AI provider.", "only local $defs references supported")
        for key in ("properties", "$defs"):
            for name, value in node.get(key, {}).items():
                visit(value, path + "/" + name)
        for key in ("items", "additionalProperties"):
            if isinstance(node.get(key), dict):
                visit(node[key], path + "/" + key)
        for key in ("anyOf", "oneOf", "prefixItems"):
            for i, value in enumerate(node.get(key, [])):
                visit(value, path + f"/{key}/{i}")

    try:
        Draft202012Validator.check_schema(schema)
    except SchemaError:
        raise PermanentStageError("VERTEX_SCHEMA_UNSUPPORTED", "This response format is not supported by the AI provider.", "invalid JSON schema") from None
    visit(schema, "root")


_CLIENTS: dict[tuple[str, str, float], genai.Client] = {}
_CLIENT_LOCK = Lock()
GENERATION_CAPABILITIES = frozenset({Capability.JSON, Capability.WRITING, Capability.REASONING, Capability.SEARCH,
                                     Capability.DOCUMENTS, Capability.IMAGES, Capability.AUDIO, Capability.TOOLS})
MEDIA_TYPES = {
    **dict.fromkeys(("image/png", "image/jpeg", "image/webp", "image/heic", "image/heif"), Capability.IMAGES),
    **dict.fromkeys(("application/pdf", "text/plain"), Capability.DOCUMENTS),
    **dict.fromkeys(("audio/x-aac", "audio/flac", "audio/mp3", "audio/m4a", "audio/mpeg", "audio/mpga", "audio/mp4",
                     "audio/ogg", "audio/pcm", "audio/wav", "audio/webm"), Capability.AUDIO),
}


# Many students share Gemini's capacity (owner, 2026-10-07: 20 at once). A throttled (429) or briefly
# unavailable (503) request is retried here within seconds, with jitter, before the stage fails and waits for
# the queue's backoff: Google bills neither, and nothing else is retried here (a timeout may have been billed).
THROTTLE_RETRY = types.HttpRetryOptions(attempts=4, initial_delay=2.0, max_delay=20.0, exp_base=2.0, jitter=1.0, http_status_codes=[429, 503])
# Each call gets the time its own token allowance needs: thinking counts against it, and a HIGH call that
# thinks to its full room (32k) at Flash's measured 145-165 tokens a second needs about four minutes. A
# fixed 180 seconds cut such calls off (live run 2026-10-07: three timeouts in a row, each possibly
# billed, and the same retry each time). Never less than the configured timeout, never past the stage's
# hand-over margin (STAGE_WORK_LIMIT 20 minutes inside the 25-minute lease).
TOKENS_PER_SECOND = 120  # below the slowest rate measured, so a call that runs to its limit still ends in time
CALL_SECONDS_CAP = 290


def call_timeout(max_output_tokens: int | None, floor: float) -> float:
    return min(CALL_SECONDS_CAP, max(floor, 30 + (max_output_tokens or 0) / TOKENS_PER_SECOND))


def _vertex_client(project: str, location: str, timeout: float) -> genai.Client:
    """One client per server-configured project/location/timeout, including concurrent cold starts.

    No eviction of clients being used by other worker threads. Closed at process exit or by
    explicit teardown. Request model/options never create additional clients.
    """
    key = (project, location, timeout)
    try:
        with _CLIENT_LOCK:
            if key not in _CLIENTS:
                credentials, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"], quota_project_id=project)
                _CLIENTS[key] = genai.Client(vertexai=True, project=project, location=location, credentials=credentials,
                                            http_options=types.HttpOptions(api_version="v1", timeout=int(timeout * 1000),
                                                                           retry_options=THROTTLE_RETRY))
            return _CLIENTS[key]
    except (auth_errors.DefaultCredentialsError, auth_errors.RefreshError):
        raise PermanentStageError("VERTEX_AUTH", MISCONFIGURED, "Vertex ADC unavailable") from None
    except auth_errors.TransportError:
        raise RetryableStageError("PROVIDER_UNAVAILABLE", UNAVAILABLE, "Vertex ADC transport unavailable") from None
    except (SDKValidationError, ValueError):
        raise PermanentStageError("VERTEX_REQUEST_UNSUPPORTED", MISCONFIGURED, "Vertex client configuration invalid") from None


def close_vertex_clients() -> None:
    """Call only after requests/workers have stopped; do not close an in-flight shared client."""
    with _CLIENT_LOCK:
        clients = list(_CLIENTS.values())
        _CLIENTS.clear()
    for client in clients:
        client.close()


atexit.register(close_vertex_clients)


def _web_url(value: str) -> bool:
    try:
        parsed = urlsplit(value)
    except ValueError:
        return False
    return parsed.scheme in ("https", "http") and bool(parsed.hostname) and not parsed.username and not parsed.password


def _error(exc: errors.APIError, search: bool) -> PermanentStageError | RetryableStageError:
    # Never return/log SDK messages: they can contain the submitted text or request URI.
    code = exc.code or 0
    status = exc.status or ""
    if code == 401:
        return PermanentStageError("VERTEX_AUTH", MISCONFIGURED, "vertex HTTP 401")
    if code == 403:
        return PermanentStageError("VERTEX_PERMISSION", MISCONFIGURED, "vertex HTTP 403")
    if code == 404:
        return PermanentStageError("VERTEX_MODEL_UNAVAILABLE", MISCONFIGURED, "vertex model unavailable")
    if code == 429:
        # Quota failures identified by a quota-specific detail are terminal; generic capacity/rate
        # failures remain retryable. Do not claim all RESOURCE_EXHAUSTED errors are empty balances.
        details = json.dumps(exc.details).lower()
        renewable = any(marker in details for marker in ("rate_limit_exceeded", "perminute", "per_minute", "/min/", "persecond", "per_second"))
        if not renewable and ("quotafailure" in details or "billing" in details or "quota exceeded" in details):
            return PermanentStageError("VERTEX_QUOTA", MISCONFIGURED, "vertex quota/billing unavailable")
        return RetryableStageError("VERTEX_RATE_LIMIT", UNAVAILABLE, "vertex HTTP 429")
    if code in (408, 499, 504):
        return RetryableStageError("VERTEX_TIMEOUT", UNAVAILABLE, f"vertex HTTP {code}")
    if code >= 500:
        return RetryableStageError("PROVIDER_UNAVAILABLE", UNAVAILABLE, f"vertex HTTP {code}")
    if code == 400 and status == "INVALID_ARGUMENT":
        # SDK versions retain either the full error envelope or its details. Inspect reason/field
        # codes at any nesting level, never return the provider's messages or submitted values.
        pending = [exc.details]
        invalid_model = False
        while pending:
            detail = pending.pop()
            if isinstance(detail, dict):
                invalid_model |= detail.get("reason") in ("INVALID_MODEL", "MODEL_NOT_FOUND") or detail.get("field") == "model"
                pending.extend(detail.values())
            elif isinstance(detail, list):
                pending.extend(detail)
        if invalid_model:
            return PermanentStageError("VERTEX_INVALID_MODEL", MISCONFIGURED, "vertex rejected model identifier")
        return PermanentStageError("VERTEX_REQUEST_UNSUPPORTED", MISCONFIGURED,
                                  "vertex rejected grounded schema request" if search else "vertex rejected schema/config request")
    return PermanentStageError("VERTEX_GROUNDING_ERROR" if search else "PROVIDER_REJECTED", MISCONFIGURED, f"vertex HTTP {code}")


def _thinking(level: str | None) -> types.ThinkingConfig | None:
    return types.ThinkingConfig(thinking_level=level) if level else None


REDIRECT_HOST = "vertexaisearch.cloud.google.com"
_REDIRECT = re.compile(r"https://vertexaisearch\.cloud\.google\.com/grounding-api-redirect/[A-Za-z0-9_\-=]+")


# Resolving grounding links is bounded (Codex audit 2026-10-07, finding 3): at most this many links, each
# within its own timeout, all within a total deadline, so a long answer can't hold a stage past its task
# deadline. The runner records the call's usage and keeps the raw answer before resolving.
MAX_LINKS = 20
LINK_TIMEOUT_S = 5.0
RESOLVE_DEADLINE_S = 25.0


def _resolve(link: str) -> str | None:
    """The page a grounding redirect stands for: Google answers a link it issued with a redirect, and
    one it did not issue with 404. Only the Location header is read; the page itself is not fetched."""
    try:
        response = httpx.get(link, follow_redirects=False, timeout=LINK_TIMEOUT_S)
    except httpx.HTTPError:
        return None
    location = response.headers.get("location", "")
    if response.status_code not in (301, 302, 303, 307, 308) or not _web_url(location) or urlsplit(location).hostname == REDIRECT_HOST:
        return None
    return location


def _strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [s for v in value for s in _strings(v)]
    if isinstance(value, dict):
        return [s for v in value.values() for s in _strings(v)]
    return []


def resolve_sources(result: ModelResult, request_text: str) -> None:
    """Replace the grounding redirects in a searched answer with the pages they stand for, and record
    which pages count as sources of THIS search (`result.sources`).

    Provenance (Codex audit 2026-10-07, finding 7): with a JSON answer Vertex returns the queries it ran
    but no source list, so the only evidence is the redirect links the model wrote. A link counts only if
    a search actually ran, Google resolves it (an invented one does not), and it was not already in the
    request (a link copied from the input is not something this search returned). That shows the page
    came through Google's grounding; it does not show the quotation is on it: the callers' existing checks
    (the page fetched, the quotation found on it, the second model's reading) still decide. Where Google
    returns source metadata, those pages are the sources; `grounding["provenance"]` says which.
    Links are looked for in the DECODED answer (finding 6: valid JSON may escape a slash)."""
    try:
        decoded: Any = json.loads(result.text)
    except json.JSONDecodeError:
        decoded = result.text
    chunks = [s["url"] for s in result.grounding.get("sources", [])]
    found = [m for text in _strings(decoded) for m in _REDIRECT.findall(text)]
    links = list(dict.fromkeys([*found, *(u for u in chunks if _REDIRECT.fullmatch(u))]))
    supplied = {link for link in links if link in request_text}
    candidates = [link for link in links if link not in supplied][:MAX_LINKS] if result.queries else []
    resolved: dict[str, str] = {}
    if candidates:
        pool = ThreadPoolExecutor(max_workers=min(8, len(candidates)))
        futures = {pool.submit(_resolve, link): link for link in candidates}
        done, _ = wait(futures, timeout=RESOLVE_DEADLINE_S)
        pool.shutdown(wait=False, cancel_futures=True)
        resolved = {futures[f]: page for f in done if (page := f.result())}

    def swap(value: Any) -> Any:
        if isinstance(value, str):
            return _REDIRECT.sub(lambda m: resolved.get(m.group(0), m.group(0)), value)
        if isinstance(value, list):
            return [swap(v) for v in value]
        if isinstance(value, dict):
            return {k: swap(v) for k, v in value.items()}
        return value

    swapped = swap(decoded)
    result.text = swapped if isinstance(swapped, str) else json.dumps(swapped, ensure_ascii=False)
    metadata_pages = [u for u in chunks if not _REDIRECT.fullmatch(u)]
    result.sources = list(dict.fromkeys([*resolved.values(), *metadata_pages]))
    result.grounding.update({"provenance": "provider_metadata" if chunks else "resolved_answer_links", "resolvedSources": len(resolved),
                             "unresolvedLinks": len(candidates) - len(resolved), "linksFromRequest": len(supplied),
                             "linksOverLimit": max(0, len(links) - len(supplied) - MAX_LINKS)})


def _model_id(value: str) -> str:
    if not isinstance(value, str):
        raise PermanentStageError("VERTEX_INVALID_MODEL", MISCONFIGURED, "model identifier must be text")
    if ":" in value:
        namespace, _, value = value.partition(":")
        if namespace != "vertex":
            raise PermanentStageError("VERTEX_INVALID_MODEL", MISCONFIGURED, "non-Vertex provider reference")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", value):
        raise PermanentStageError("VERTEX_INVALID_MODEL", MISCONFIGURED, "invalid model identifier")
    return value


def _content_capabilities(contents: str | types.Content | list[types.Content]) -> set[Capability]:
    if isinstance(contents, str):
        if not contents.strip():
            raise PermanentStageError("VERTEX_REQUEST_UNSUPPORTED", MISCONFIGURED, "empty user content")
        return set()
    items = [contents] if isinstance(contents, types.Content) else contents
    if not isinstance(items, list) or not items:
        raise PermanentStageError("VERTEX_REQUEST_UNSUPPORTED", MISCONFIGURED, "canonical SDK content required")
    needs: set[Capability] = set()
    payload_fields = {"text", "inline_data", "file_data", "function_call", "function_response"}
    allowed = payload_fields | {"thought", "thought_signature", "media_resolution"}
    for content in items:
        if not isinstance(content, types.Content) or content.role not in (None, "user", "model", "tool") or not content.parts:
            raise PermanentStageError("VERTEX_REQUEST_UNSUPPORTED", MISCONFIGURED, "invalid SDK content envelope")
        for part in content.parts:
            if not isinstance(part, types.Part):
                raise PermanentStageError("VERTEX_REQUEST_UNSUPPORTED", MISCONFIGURED, "invalid SDK content part")
            fields = {name for name in types.Part.model_fields if getattr(part, name, None) is not None} | set(part.model_extra or {})
            if fields - allowed or len(fields & payload_fields) != 1:
                raise PermanentStageError("VERTEX_REQUEST_UNSUPPORTED", MISCONFIGURED, "unsupported or ambiguous content part")
            media = part.inline_data or part.file_data
            if media is not None:
                capability = MEDIA_TYPES.get(media.mime_type or "")
                if capability is None:
                    raise PermanentStageError("AI_CAPABILITY_UNSUPPORTED", MISCONFIGURED, "unsupported input media type")
                needs.add(capability)
                if part.inline_data is not None and not part.inline_data.data:
                    raise PermanentStageError("VERTEX_REQUEST_UNSUPPORTED", MISCONFIGURED, "empty inline media")
                if part.file_data is not None:
                    uri = part.file_data.file_uri or ""
                    try:
                        parsed = urlsplit(uri)
                    except ValueError:
                        raise PermanentStageError("VERTEX_REQUEST_UNSUPPORTED", MISCONFIGURED, "invalid media URI") from None
                    if not ((parsed.scheme == "gs" and parsed.netloc and parsed.path not in ("", "/") and not parsed.query and not parsed.fragment
                             and not parsed.username and not parsed.password) or (parsed.scheme == "https" and _web_url(uri))):
                        raise PermanentStageError("VERTEX_REQUEST_UNSUPPORTED", MISCONFIGURED, "media URI must be GCS or HTTPS")
            if part.function_call is not None or part.function_response is not None:
                needs.add(Capability.TOOLS)
    return needs


def _tools(options: VertexOptions) -> tuple[list[types.Tool], set[str]]:
    tools = list(options.tools)
    if options.grounding is not None:
        tools.append(types.Tool(google_search=options.grounding))
    names: set[str] = set()
    search_tools = 0
    for tool in tools:
        fields = {name for name in types.Tool.model_fields if getattr(tool, name, None) is not None} | set(tool.model_extra or {})
        if not fields or fields - {"google_search", "function_declarations"}:
            raise PermanentStageError("AI_SERVICE_UNIMPLEMENTED", MISCONFIGURED, "requested tool adapter is not implemented")
        search_tools += int(tool.google_search is not None)
        for function in tool.function_declarations or []:
            if not function.name or function.name in names:
                raise PermanentStageError("VERTEX_REQUEST_UNSUPPORTED", MISCONFIGURED, "function declarations need unique names")
            names.add(function.name)
        if tool.google_search is None and not tool.function_declarations:
            raise PermanentStageError("VERTEX_REQUEST_UNSUPPORTED", MISCONFIGURED, "empty tool declaration")
    if search_tools > 1:
        raise PermanentStageError("VERTEX_GROUNDING_ERROR", MISCONFIGURED, "duplicate Google Search tools")
    if options.tool_config is not None:
        if not tools:
            raise PermanentStageError("VERTEX_REQUEST_UNSUPPORTED", MISCONFIGURED, "tool configuration requires a tool")
        functions = options.tool_config.function_calling_config
        if functions and (not names or set(functions.allowed_function_names or []) - names):
            raise PermanentStageError("VERTEX_REQUEST_UNSUPPORTED", MISCONFIGURED, "function configuration must name declared tools")
    return tools, names


class VertexGeminiProvider:
    name = "vertex"

    def __init__(self, settings: Settings):
        if not (settings.vertex_project or "").strip() or not (settings.vertex_location or "").strip():
            raise PermanentStageError("AI_NOT_CONFIGURED", MISCONFIGURED, "Vertex project and location required")
        self.settings = settings

    def json(self, task: str, model: str, system: str, payload: dict[str, Any], schema: dict[str, Any], max_tokens: int,
             thinking: str | None = None) -> ModelResult:
        # task is caller metadata, not a provider routing/capability policy.
        return self.generate(model, system, render_user_message(payload),
                             {"response_mime_type": "application/json", "response_json_schema": schema, "max_output_tokens": max_tokens,
                              "thinking_config": _thinking(thinking)})

    def search_json(self, task: str, model: str, system: str, payload: dict[str, Any], schema: dict[str, Any], max_tokens: int, max_searches: int,
                    thinking: str | None = None) -> ModelResult:
        return self.generate(model, system, render_user_message(payload),
                             {"response_mime_type": "application/json", "response_json_schema": schema, "max_output_tokens": max_tokens,
                              "grounding": types.GoogleSearch(), "max_grounding_queries": max_searches, "thinking_config": _thinking(thinking)})

    def _grounding_allowed(self) -> None:
        if not self.settings.vertex_search_enabled:
            raise PermanentStageError("VERTEX_GROUNDING_DISABLED", MISCONFIGURED, "Vertex grounding is switched off (VERTEX_SEARCH_ENABLED)")

    def generate(self, model: str, system: str, contents: str | types.Content | list[types.Content], options: VertexOptions | dict[str, Any]) -> ModelResult:
        """One explicit-model request: no role/task selection, retries, fallback or tool execution.

        Content is plain text or canonical SDK Content/Part values (inline bytes or file URIs).
        This method never reads/uploads files, fetches URLs or calls another Google service.
        Calling workflows own prompts, untrusted-data delimiters and any subsequent tool turn.
        """
        model = _model_id(model)
        try:
            options = VertexOptions.model_validate(options.model_dump() if isinstance(options, VertexOptions) else options)
        except SDKValidationError:
            raise PermanentStageError("VERTEX_REQUEST_UNSUPPORTED", MISCONFIGURED, "invalid Vertex request options") from None
        if not isinstance(system, str):
            raise PermanentStageError("VERTEX_REQUEST_UNSUPPORTED", MISCONFIGURED, "system instruction must be text")
        needs = _content_capabilities(contents)
        if options.response_mime_type == "application/json":
            needs.add(Capability.JSON)
        else:
            needs.add(Capability.WRITING)
        if options.response_json_schema is not None:
            check_schema(options.response_json_schema)
        tools, names = _tools(options)
        search = any(t.google_search is not None for t in tools)
        if search:
            self._grounding_allowed()
            needs.add(Capability.SEARCH)
            if options.max_grounding_queries is None:
                raise PermanentStageError("VERTEX_GROUNDING_ERROR", MISCONFIGURED, "positive grounding query allowance required")
        elif options.max_grounding_queries is not None:
            raise PermanentStageError("VERTEX_GROUNDING_ERROR", MISCONFIGURED, "query allowance supplied without grounding")
        if names:
            needs.add(Capability.TOOLS)
        if options.thinking_config is not None:
            needs.add(Capability.REASONING)
        spec = check_model(model, frozenset(needs), self.settings.paperaid_gemini_models, implemented=GENERATION_CAPABILITIES)
        if options.max_output_tokens > spec.max_output_tokens:
            raise PermanentStageError("VERTEX_REQUEST_UNSUPPORTED", MISCONFIGURED, "output limit exceeds model capability")
        thinking = options.thinking_config
        if thinking:
            if thinking.thinking_level is not None and thinking.thinking_level.value not in spec.thinking_levels:
                raise PermanentStageError("AI_CAPABILITY_UNSUPPORTED", MISCONFIGURED, "thinking level not verified for selected model")
            if thinking.thinking_budget is not None and (spec.thinking_budget_range is None or not
                spec.thinking_budget_range[0] <= thinking.thinking_budget <= spec.thinking_budget_range[1]):
                raise PermanentStageError("AI_CAPABILITY_UNSUPPORTED", MISCONFIGURED, "thinking budget not verified for selected model")
        config = types.GenerateContentConfig(system_instruction=system, response_mime_type=options.response_mime_type,
                                             response_json_schema=options.response_json_schema, max_output_tokens=options.max_output_tokens,
                                             temperature=options.temperature, top_p=options.top_p, thinking_config=thinking,
                                             safety_settings=list(options.safety_settings) or None, tools=tools or None,
                                             tool_config=options.tool_config,
                                             automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
                                             http_options=types.HttpOptions(timeout=int(call_timeout(options.max_output_tokens, self.settings.provider_timeout_sec) * 1000),
                                                                            retry_options=THROTTLE_RETRY))
        started = time.monotonic()
        client = _vertex_client(self.settings.vertex_project, self.settings.vertex_location, self.settings.provider_timeout_sec)
        try:
            response = client.models.generate_content(model=model, contents=contents, config=config)
        except errors.APIError as exc:
            raise _error(exc, search) from None
        except (httpx.ConnectError, httpx.ConnectTimeout):  # never reached Google: nothing billed
            raise RetryableStageError("PROVIDER_UNAVAILABLE", UNAVAILABLE, "vertex unreachable") from None
        except httpx.TimeoutException:  # sent, answer not received: Google may have billed it
            raise RetryableStageError("VERTEX_TIMEOUT", UNAVAILABLE, "vertex transport timeout") from None
        except httpx.TransportError:  # the connection broke after sending: Google may have billed it
            raise RetryableStageError("VERTEX_CONNECTION_LOST", UNAVAILABLE, "vertex connection lost after sending") from None
        except (auth_errors.DefaultCredentialsError, auth_errors.RefreshError):
            raise PermanentStageError("VERTEX_AUTH", MISCONFIGURED, "Vertex ADC authentication failed") from None
        except auth_errors.TransportError:
            raise RetryableStageError("PROVIDER_UNAVAILABLE", UNAVAILABLE, "Vertex ADC transport unavailable") from None
        except (SDKValidationError, json.JSONDecodeError):  # a successful (billed) answer the SDK could not read
            raise RetryableStageError("VERTEX_MALFORMED_ENVELOPE", UNAVAILABLE, "vertex malformed response envelope; usage unknown") from None
        except (ValueError, TypeError):
            raise PermanentStageError("VERTEX_REQUEST_UNSUPPORTED", MISCONFIGURED, "SDK rejected Vertex request configuration") from None
        try:
            response = types.GenerateContentResponse.model_validate(response)
        except SDKValidationError:
            raise RetryableStageError("VERTEX_MALFORMED_ENVELOPE", UNAVAILABLE, "vertex malformed response envelope; usage unknown") from None
        result = self._result(response, model, started, search)
        if result.tool_calls and any(c["name"] not in names for c in result.tool_calls):
            result.error_code = "VERTEX_TOOL_ERROR"
        if result.stop == "end_turn" and not result.error_code and not result.tool_calls and options.response_mime_type == "application/json":
            try:
                data = json.loads(result.text)
            except (json.JSONDecodeError, TypeError):
                result.error_code, result.error_retryable = "MALFORMED_OUTPUT", True
            else:
                if options.response_json_schema is not None:
                    try:
                        Draft202012Validator(options.response_json_schema).validate(data)
                    except ValidationError:
                        result.error_code, result.error_retryable = "SCHEMA_VALIDATION_FAILED", True
        if search:
            # Queries beyond the allowance were run and are charged; the runner caps what follows. The
            # answer's links are resolved by the caller AFTER the call's usage is recorded (resolve_sources).
            result.grounding["queriesOverAllowance"] = max(0, len(result.queries) - (options.max_grounding_queries or 0))
        return result

    @staticmethod
    def _result(response: types.GenerateContentResponse, model: str, started: float, search: bool) -> ModelResult:
        u = response.usage_metadata
        cached = max(0, u.cached_content_token_count or 0) if u else 0
        thinking = max(0, u.thoughts_token_count or 0) if u else 0
        tool_tokens = max(0, u.tool_use_prompt_token_count or 0) if u else 0
        visible = max(0, u.candidates_token_count) if u and u.candidates_token_count is not None else None
        first = (response.candidates or [None])[0]
        finish = first.finish_reason.value if first and first.finish_reason else ""
        blocked = bool(response.prompt_feedback and response.prompt_feedback.block_reason) or finish in GEMINI_BLOCKED
        parts = first.content.parts or [] if first and first.content else []
        text = "".join(p.text or "" for p in parts if not p.thought)
        calls = [{"name": p.function_call.name or "", "args": p.function_call.args or {}, "id": p.function_call.id,
                  "thoughtSignature": p.thought_signature} for p in parts if p.function_call and not p.thought]
        ratings = [{"category": r.category.value if r.category else "", "blocked": r.blocked,
                    "probability": r.probability.value if r.probability else ""} for r in first.safety_ratings or []] if first else []
        result = ModelResult(text=text, provider="vertex", model=model,
                             # Google Search's tool-provided input is not billed under Gemini 3
                             # grounding pricing. Preserve the count as metadata, not input cost.
                             usage=Usage(max(0, (u.prompt_token_count or 0) - cached) + (0 if search else tool_tokens) if u else 0,
                                         (visible or 0) + thinking, cached,
                                         int((time.monotonic() - started) * 1000), thinking_tokens=thinking,
                                         tool_input_tokens=tool_tokens, visible_output_tokens=visible),
                             stop="refusal" if blocked else "max_tokens" if finish == "MAX_TOKENS" else "end_turn",
                             finish_reason=finish, safety_block=blocked, model_version=response.model_version or "", tool_calls=calls,
                             safety={"promptBlockReason": response.prompt_feedback.block_reason.value if response.prompt_feedback and
                                     response.prompt_feedback.block_reason else "", "ratings": ratings})
        if not u or u.prompt_token_count is None or (not blocked and finish == "STOP" and u.candidates_token_count is None):
            result.error_code = "VERTEX_USAGE_MISSING"  # do not silently account an unmetered response as zero
        elif any((count or 0) < 0 for count in (u.prompt_token_count, u.candidates_token_count, u.thoughts_token_count,
                                              u.cached_content_token_count, u.tool_use_prompt_token_count)) or cached > u.prompt_token_count:
            result.error_code = "VERTEX_USAGE_MISSING"  # contradictory usage is not verified accounting
        elif result.stop == "end_turn" and (finish != "STOP" or (not text and not calls)):
            result.error_code, result.error_retryable = "VERTEX_EMPTY_RESPONSE", True
        if any(p.inline_data is not None or p.file_data is not None or p.executable_code is not None or
               p.code_execution_result is not None for p in parts):
            result.error_code = "VERTEX_OUTPUT_UNSUPPORTED"
        if finish in ("MALFORMED_FUNCTION_CALL", "UNEXPECTED_TOOL_CALL") or any(p.function_call and
                (p.function_call.partial_args or p.function_call.will_continue) for p in parts):
            result.error_code = "VERTEX_TOOL_ERROR"
        metadata = first.grounding_metadata if first else None
        if search and metadata:
            result.queries = list(metadata.web_search_queries or [])  # preserve repeats for actual billable queries
            source_items = []
            chunks = metadata.grounding_chunks or []
            for index, chunk in enumerate(chunks):
                if chunk.web and chunk.web.uri and _web_url(chunk.web.uri):
                    source_items.append({"index": index, "url": chunk.web.uri, "title": chunk.web.title or ""})
            result.sources = list(dict.fromkeys(s["url"] for s in source_items))
            citations = []
            for support in metadata.grounding_supports or []:
                urls = [s["url"] for s in source_items if s["index"] in (support.grounding_chunk_indices or [])]
                if urls and support.segment:
                    citations.append({"text": support.segment.text or "", "start": support.segment.start_index,
                                      "end": support.segment.end_index, "urls": urls})
            result.grounding = {"sources": source_items, "citations": citations,
                                "searchSuggestions": metadata.search_entry_point.rendered_content if metadata.search_entry_point else ""}
        if search:
            result.usage.search_calls = len(result.queries)
            result.usage.billable_units["google_search_query"] = len(result.queries)
        return result
