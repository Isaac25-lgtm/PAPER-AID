"""Number tokens (Codex review 2026-09-30 #6): a figure that lives in the Results Model, the budget,
the requirement set or the student's answers enters the text only as a token such as
⟦N:budget.total⟧ or ⟦N:indicator.I1.target⟧. Code fills every token from the current data, with its
unit, rounding and currency, before any length check; an unknown token fails the section. So the
narrative, the tables and the budget can never disagree about a figure."""

import re
from typing import Any

from app.works import budget as budget_engine
from app.works.models import Budget, ResolvedSpec, ResultsModel, WorkInputs

NUMBER_TOKEN = re.compile(r"⟦N:([A-Za-z][A-Za-z0-9_\-]*(?:\.[A-Za-z0-9_\-]+)*)⟧")
NUMERIC_ANSWERS = {"duration_months": "months", "budget_envelope": "money", "amount_requested": "money", "word_limit": "words"}


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:40] or "other"


def _plain(value: float) -> str:
    return f"{value:,.2f}".rstrip("0").rstrip(".") if value != int(value) else f"{int(value):,}"


def values(spec: ResolvedSpec, results: ResultsModel | None, money_plan: Budget | None, inputs: WorkInputs) -> dict[str, tuple[str, str]]:
    """Every token available to this work: path → (how it prints, what it means)."""
    out: dict[str, tuple[str, str]] = {}
    currency = (money_plan.currency if money_plan else "") or spec.currency or ""
    if spec.ceiling is not None:
        out["ceiling"] = (budget_engine.money(spec.ceiling, spec.currency or currency), "the funding ceiling in the call")
    if spec.duration_months:
        out["duration"] = (f"{spec.duration_months} months", "the project's duration")
    if spec.cost_share is not None:
        out["cost_share_rate"] = (f"{spec.cost_share:g}%", "the cost share the call requires")
    if money_plan and money_plan.lines:
        t = budget_engine.totals(money_plan)
        out["budget.total"] = (budget_engine.money(t.total, currency), "the budget's grand total")
        out["budget.requested"] = (budget_engine.money(money_plan.requested if money_plan.requested is not None else t.total, currency), "the amount requested")
        if t.indirect:
            out["budget.indirect"] = (budget_engine.money(t.indirect, currency), "indirect costs")
        if money_plan.cost_share_provided is not None:
            out["budget.cost_share"] = (budget_engine.money(money_plan.cost_share_provided, currency), "the applicant's cost share")
        for category, amount in t.by_category.items():
            out[f"budget.category.{slug(category)}"] = (budget_engine.money(amount, currency), f"the {category} category's total")
        for year, amount in t.by_year.items():
            out[f"budget.year.{year}"] = (budget_engine.money(amount, currency), f"year {year}'s total")
        for line in money_plan.lines:
            out[f"budget.line.{line.id}"] = (budget_engine.money(budget_engine.line_total(line), currency), f"budget line {line.id}: {line.description[:60]}")
    for ind in results.indicators if results else []:
        percent = ind.unit.strip().lower() in ("%", "percent", "percentage")
        for part in ("target", "baseline"):
            value = getattr(ind, part)
            if value is not None:
                out[f"indicator.{ind.id}.{part}"] = (_plain(value) + ("%" if percent else ""), f"the {part} of indicator {ind.id} ({ind.definition[:60]}), in {ind.unit or 'its unit'}")
    for key, kind in NUMERIC_ANSWERS.items():
        raw = inputs.answers.get(key, "").replace(",", "").strip()
        try:
            number = float(raw)
        except ValueError:
            continue
        text = budget_engine.money(number, currency) if kind == "money" else f"{_plain(number)} {kind}"
        out[f"answer.{key}"] = (text, f"your answer: {key.replace('_', ' ')}")
    return out


def for_model(tokens: dict[str, tuple[str, str]]) -> list[dict[str, Any]]:
    """What the writer is told about each token: its exact spelling, its value and its meaning."""
    return [{"token": f"⟦N:{path}⟧", "value": text, "meaning": meaning} for path, (text, meaning) in sorted(tokens.items())]


def render(text: str, tokens: dict[str, tuple[str, str]]) -> tuple[str, list[str]]:
    """The text with every number token filled; the unknown ones are returned (and left visible)."""
    unknown: list[str] = []

    def fill(m: re.Match[str]) -> str:
        found = tokens.get(m.group(1))
        if found is None:
            unknown.append(m.group(0))
            return m.group(0)
        return found[0]

    return NUMBER_TOKEN.sub(fill, text), unknown


def strip(text: str) -> str:
    """The text without number tokens, for the evidence checks (a token is not a citation)."""
    return NUMBER_TOKEN.sub(" ", text)
