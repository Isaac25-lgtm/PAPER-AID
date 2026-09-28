"""Approved research decisions and what depends on them (Proposal V1, owner decision 2026-09-28).

Every decision in a plan has a stable id ("O2" is the second specific objective) and a hash of its
content. A generated section records the hashes of the decisions it was written from; when the
student changes an approved decision, every section built on the old value shows "needs review".
Nothing is invalidated by writing flags: staleness is recomputed from the current plan, so it can
never drift from the truth."""

import hashlib
import json
from typing import Any

from app.proposals.models import ChapterDocument, ProposalPlan


def decisions(plan: ProposalPlan) -> dict[str, Any]:
    """Decision id → its value."""
    out: dict[str, Any] = {
        "title": plan.title,
        "problem": plan.problem,
        "purpose": plan.purpose,
        "study_type": plan.study_type,
        "design": plan.design,
        "area": plan.study_area,
        "population": plan.population,
        "sampling": [plan.sampling, plan.inclusion],
        "sample_size": plan.sample_size.model_dump(),
        "variables": plan.variables.model_dump(),
        "theory": plan.theory,
        "scope": plan.scope,
        "timeline": plan.timeline_months,
        "questions_kind": plan.questions_kind,
        "gap": plan.research_gap.model_dump(),
    }
    # The whole sets: a section covering every objective changes when one is added or removed, not
    # only when an existing one is edited (Codex audit 2026-09-28 #12).
    out["objectives_set"] = plan.specific_objectives
    out["questions_set"] = plan.research_questions
    out["alignment_set"] = [row.model_dump() for row in plan.alignment]
    for i, objective in enumerate(plan.specific_objectives, start=1):
        out[f"O{i}"] = objective
    for i, question in enumerate(plan.research_questions, start=1):
        out[f"Q{i}"] = question
    for row in plan.alignment:
        out[f"A{row.objective}"] = row.model_dump()
    return out


def hashes(plan: ProposalPlan) -> dict[str, str]:
    return {k: hashlib.sha256(json.dumps(v, sort_keys=True).encode()).hexdigest()[:12] for k, v in decisions(plan).items()}


def depends_on(chapter: int, key: str, plan: ProposalPlan) -> list[str]:
    """The decisions a section is written from. Unknown sections depend on the whole plan."""
    objectives, questions, rows = ["objectives_set"], ["questions_set"], ["alignment_set"]
    if chapter == 2 and key.startswith("empirical"):
        n = key.removeprefix("empirical")
        return ["title", f"O{n}", f"Q{n}"]
    table: dict[tuple[int, str], list[str]] = {
        (1, "intro"): ["title"],
        (1, "background"): ["title", "problem", "area"],
        (1, "problem"): ["title", "problem", "area", "population", "gap"],
        (1, "purpose"): ["purpose"],
        (1, "objectives"): ["purpose", *objectives],
        (1, "questions"): ["questions_kind", *questions],
        (1, "scope"): ["scope", "area", "population"],
        (1, "justification"): ["problem", "purpose", "gap"],
        (1, "significance"): ["problem", "purpose"],
        (1, "framework"): ["theory", "variables", *objectives],
        (1, "synopsis"): ["title"],
        (2, "intro"): ["title", *objectives],
        (2, "theory"): ["theory", "variables"],
        (2, "gap"): ["problem", "gap", *objectives],
        (3, "intro"): ["title"],
        (3, "design"): ["study_type", "design", *objectives],
        (3, "area"): ["area"],
        (3, "sources"): ["study_type", *rows],
        (3, "population"): ["population", "area"],
        (3, "sampling"): ["population", "sampling", "sample_size"],
        (3, "variables"): ["variables", *objectives],
        (3, "procedure"): ["design", *rows],
        (3, "instruments"): ["variables", *rows],
        (3, "quality"): ["design", *rows],
        (3, "analysis"): ["study_type", "questions_kind", *objectives, *questions, *rows],
        (3, "ethics"): ["population", "design"],
        (3, "constraints"): ["design", "sampling", "sample_size"],
        (3, "workplan"): ["timeline", "design"],
    }
    # The concept paper summarises the plan: its sections share Chapter One's, plus two of its own.
    table |= {(4, k): v for (c, k), v in table.items() if c == 1}
    table[(4, "literature")] = ["title", "problem", "gap", "theory", *objectives]
    table[(4, "methodology")] = ["study_type", "design", "area", "population", "sampling", "sample_size", *rows]
    return table.get((chapter, key), list(decisions(plan)))


def stamp(chapter: int, key: str, plan: ProposalPlan) -> dict[str, str]:
    current = hashes(plan)
    return {d: current.get(d, "") for d in depends_on(chapter, key, plan)}


def stale(document: ChapterDocument, plan: ProposalPlan) -> list[str]:
    """Headings of the sections whose decisions have changed since they were written."""
    current = hashes(plan)
    return [f"{s.number} {s.heading}" for s in document.sections if any(current.get(d) != h for d, h in s.depends.items())]


def changed(before: ProposalPlan | None, after: ProposalPlan) -> list[str]:
    """Decision ids whose value differs between two versions of a plan."""
    if before is None:
        return list(decisions(after))
    old, new = hashes(before), hashes(after)
    return sorted(k for k in set(old) | set(new) if old.get(k) != new.get(k))
