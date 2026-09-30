"""The compliance report (rulebook §21, Appendix A4) as the readiness checklist PaperAid already
uses: each applicable rule becomes one item (PASS / NEEDS_REVIEW / MISSING / NOT_APPLICABLE /
BLOCKED, settled by CODE, AI or the AUTHOR) with its severity. The overall result is worked out by
code: Not ready (a blocking item is not met), Ready with warnings, or Ready. It is PaperAid's
assessment, never an approval, a grade or a promise of funding (§21, CW-074)."""

from typing import Any

from app.jobs.models import ReadinessItem
from app.rules import library
from app.rules.validators import VALIDATORS, Context

AUTHOR_VALIDATORS = {"eligibility.thresholds", "eligibility.evaluated", "gate.core_inputs", "gate.task_present", "gate.experience_present", "requirements.conflict"}


def _status(result: str, severity: str) -> str:
    if result == "PASS":
        return "PASS"
    if result == "NOT_APPLICABLE":
        return "NOT_APPLICABLE"
    if result == "FAIL" and severity == "BLOCKING":
        return "BLOCKED"
    return "NEEDS_REVIEW"


def report(ctx: Context, stages: tuple[str, ...]) -> list[ReadinessItem]:
    """One item per applicable rule checked at these stages. Duplicate checks (several rules on
    one validator) show once, under the first rule, with the most severe status."""
    rules = [r for r in library.rules_for(ctx.spec.kind) if r["id"] in set(ctx.spec.active_rules) and set(r["stages"]) & set(stages)]
    items: list[ReadinessItem] = []
    seen: dict[tuple[str, str], ReadinessItem] = {}
    for rule in rules:
        validator = rule["check"]["validator"]
        if validator == "semantic":
            verdict = ctx.semantic.get(rule["id"])
            if verdict is None:
                continue  # not judged in this step (another stage, or a section this document does not have)
            result, note, where = verdict
            basis = "AI"
        else:
            check = VALIDATORS.get(validator)
            if check is None:
                raise KeyError(f"no validator {validator} for {rule['id']}")
            outcome = check(ctx, rule)
            if outcome is None:
                continue
            result, note, where = outcome
            basis = "AUTHOR" if validator in AUTHOR_VALIDATORS else "CODE"
        # "WARN": a point the student should check that does not hold the document back (an uncertainty
        # such as whether references count toward a limit): shown as needing review, at warning level.
        severity = "WARNING" if result == "WARN" and rule["severity"] == "BLOCKING" else rule["severity"]
        item = ReadinessItem(id=rule["id"], question=rule["ui_message"], status=_status(result, rule["severity"]), basis=basis, note=note[:600], where=where, severity=severity)  # type: ignore[arg-type]
        key = (validator, note) if validator != "semantic" else (rule["id"], "")
        if key in seen:
            first = seen[key]
            if _rank(item) > _rank(first):
                first.status, first.severity = item.status, item.severity
            continue
        seen[key] = item
        items.append(item)
    return items


def _rank(item: ReadinessItem) -> int:
    return {"PASS": 0, "NOT_APPLICABLE": 0, "NEEDS_REVIEW": 1, "MISSING": 2, "BLOCKED": 3}[item.status] * 3 + {"INFO": 0, "WARNING": 1, "BLOCKING": 2}[item.severity]


def overall(items: list[ReadinessItem], exploratory: bool = False) -> str:
    if exploratory or any(i.severity == "BLOCKING" and i.status not in ("PASS", "NOT_APPLICABLE") for i in items):
        return "NOT_READY"
    if any(i.status not in ("PASS", "NOT_APPLICABLE") and i.severity != "INFO" for i in items):
        return "READY_WITH_WARNINGS"
    return "READY"


def blocking(items: list[ReadinessItem]) -> list[ReadinessItem]:
    return [i for i in items if i.severity == "BLOCKING" and i.status not in ("PASS", "NOT_APPLICABLE")]


def semantic_for(rules: list[dict[str, Any]], verdicts: list[dict[str, Any]], where: str) -> dict[str, tuple[str, str, str]]:
    """The evaluator's per-rule verdicts for one section (or the whole document), keyed by rule id."""
    known = {r["id"] for r in rules}
    out: dict[str, tuple[str, str, str]] = {}
    for v in verdicts:
        rid = v.get("rule", "")
        if rid in known:
            out[rid] = (v.get("status", "FAIL"), str(v.get("note", ""))[:500], where)
    return out
