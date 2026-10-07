"""Live check of the Gemini workflow on Vertex: one small structured call per stage, with the stage's
frozen model and thinking level, plus one grounded search. Synthetic content only, never student data.

It makes paid calls (a few US cents in total), so it refuses to run without --allow-paid-calls. It runs
wherever the image runs: locally with developer ADC, or in production as a one-off Cloud Run job under
the worker's service account, which proves the worker identity reaches Vertex in VERTEX_PROJECT:
  python -m app.ai.vertex_check --allow-paid-calls
"""

import argparse
import json
import logging

from app.ai import costs
from app.ai.orchestration import SIGNOFF, current_engine, vertex_settings
from app.ai.providers import ModelResult
from app.ai.vertex import VertexGeminiProvider, resolve_sources
from app.core.config import get_settings
from app.core.errors import StageError

PASSAGE = ("The 2019 survey of 412 smallholder farmers in Lira District found that 63% used improved seed. "
           "Adoption therefore doubled since 2015, which proves that extension visits caused it.")
FINDINGS = {"type": "object", "properties": {"verdict": {"type": "string", "enum": ["PASS", "REPAIR_REQUIRED"]},
                                             "issues": {"type": "array", "items": {"type": "string"}}},
            "required": ["verdict", "issues"], "additionalProperties": False}
TEXT = {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"], "additionalProperties": False}
PLAN = {"type": "object", "properties": {"sections": {"type": "array", "items": {"type": "object", "properties": {
    "heading": {"type": "string"}, "purpose": {"type": "string"}}, "required": ["heading", "purpose"], "additionalProperties": False}}},
    "required": ["sections"], "additionalProperties": False}
FIELDS = {"type": "object", "properties": {"documentType": {"type": "string"}, "wordLimit": {"type": "integer"}},
          "required": ["documentType", "wordLimit"], "additionalProperties": False}
LEVEL = {"type": "object", "properties": {"generic": {"type": "boolean"}, "reason": {"type": "string"}},
         "required": ["generic", "reason"], "additionalProperties": False}
FOUND = {"type": "object", "properties": {"findings": {"type": "array", "items": {"type": "object", "properties": {
    "url": {"type": "string"}, "quote": {"type": "string"}}, "required": ["url", "quote"], "additionalProperties": False}}},
    "required": ["findings"], "additionalProperties": False}

# stage → (a task of that stage, instruction, payload, schema)
CHECKS = {
    "intake": ("w_read", "Extract the document type and the word limit from the brief.",
               {"brief": "Write a 1,500-word coursework essay on climate adaptation in East Africa."}, FIELDS),
    "planner": ("plan", "Plan a short research note in three sections.", {"topic": "Improved seed adoption among smallholder farmers"}, PLAN),
    "execution": ("refine", "Rewrite the passage more clearly in about 60 words. Keep every number exactly.", {"passage": PASSAGE}, TEXT),
    "first_audit": ("academic", "Audit the passage for unsupported claims and logical errors.", {"passage": PASSAGE}, FINDINGS),
    "second_check": ("analyse_peer", "Is this passage generic, formulaic writing? Give one short reason.", {"passage": PASSAGE}, LEVEL),
    "premium_audit": ("review", "Audit the passage as a strict academic reviewer: methodology, causal claims, evidence.", {"passage": PASSAGE}, FINDINGS),
    "fix": ("repair", "Repair only the issues named. Keep every number exactly.",
            {"passage": PASSAGE, "issues": ["'proves that extension visits caused it' is a causal claim the survey cannot support"]}, TEXT),
    SIGNOFF: ("review", "Final sign-off: check the earlier finding was resolved and the repair broke nothing.",
              {"passage": PASSAGE.replace("which proves that extension visits caused it", "which may be associated with extension visits"),
               "previousAudit": [{"verdict": "REPAIR_REQUIRED", "issues": ["unsupported causal claim about extension visits"]}]}, FINDINGS),
}


def _line(stage: str, model: str, thinking: str, result: ModelResult | None, settings, error: str = "") -> dict:
    line = {"stage": stage, "model": model, "thinking": thinking, "error": error}
    if result is not None:
        u = result.usage
        line.update(error=result.error_code or error, finish=result.finish_reason, latencyMs=u.latency_ms, inputTokens=u.input_tokens,
                    visibleOutputTokens=u.visible_output_tokens, thinkingTokens=u.thinking_tokens, outputTokens=u.output_tokens,
                    cachedTokens=u.cached_tokens, queries=len(result.queries), sources=result.sources,
                    costUsd=round(costs.cost_usd("vertex", model, u.input_tokens, u.output_tokens, u.cached_tokens, settings.model_prices,
                                                 search_calls=u.search_calls, billable_units=u.billable_units,
                                                 unit_prices=settings.model_unit_prices, long_prices=settings.model_long_prices), 6),
                    answer=result.text[:400])
    return line


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--allow-paid-calls", action="store_true", help="Required: the check makes about ten small billable requests")
    args = parser.parse_args()
    if not args.allow_paid_calls:
        parser.error("No call made. --allow-paid-calls is required.")
    for name in ("google.genai", "google.auth", "httpx", "httpcore"):
        logging.getLogger(name).setLevel(logging.WARNING)
    engine = current_engine(get_settings())
    if not engine.vertex_routes:
        print(json.dumps({"error": "GEMINI_WORKFLOW is off: nothing to check"}))
        return 1
    settings = vertex_settings(get_settings(), engine)
    provider = VertexGeminiProvider(settings)
    print(json.dumps({"vertexProject": engine.vertex_project, "vertexLocation": engine.vertex_location}))
    failures = 0
    for stage, (task, instruction, payload, schema) in CHECKS.items():
        ref = engine.vertex_signoff[0] if stage == SIGNOFF else engine.vertex_routes[task][0]
        model, thinking = ref.partition(":")[2], engine.vertex_thinking[stage]
        try:
            result = provider.json(task, model, instruction, payload, schema, 6000, thinking=thinking)
            ok = not result.error_code and result.stop == "end_turn"
            print(json.dumps(_line(stage, model, thinking, result, settings)))
        except StageError as exc:
            ok = False
            print(json.dumps(_line(stage, model, thinking, None, settings, f"{exc.code}: {exc.detail}")))
        failures += not ok
    model, thinking = engine.vertex_routes["research"][0].partition(":")[2], engine.vertex_thinking["research"]
    try:
        result = provider.search_json("research", model, "Find one authoritative source. Give its URL exactly as the search provides it "
                                      "and a short verbatim quote.", {"claim": "WHO estimated 597,000 malaria deaths worldwide in 2023."},
                                      FOUND, 6000, 2, thinking=thinking)
        if not result.error_code:
            resolve_sources(result, "")
        found = json.loads(result.text).get("findings", []) if not result.error_code else []
        ok = not result.error_code and bool(result.queries) and bool(result.sources) and all(f["url"] in result.sources for f in found)
        print(json.dumps(_line("research (grounded)", model, thinking, result, settings)))
    except StageError as exc:
        ok = False
        print(json.dumps(_line("research (grounded)", model, thinking, None, settings, f"{exc.code}: {exc.detail}")))
    failures += not ok
    print(json.dumps({"failures": failures}))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())

