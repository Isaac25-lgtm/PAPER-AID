"""Proposal rulebooks: versioned, structured rules read from an institution's manual (UCU's 2018
Academic Research Manual first). A project keeps the rulebook it was created with, so a later
revision never changes a proposal already under way. Prompts receive only the rules they need,
never the whole manual."""

import json
from collections.abc import Callable
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Any

from app.core.errors import AppError
from app.proposals import sampling
from app.proposals.models import Level, ProposalPlan

RULEBOOKS = Path(__file__).parent / "rulebooks"
DEFAULT = "ucu-2018-v1"


_stored: tuple[Callable[[str], bytes], Callable[[str], bool]] | None = None  # (read, exists) for saved profiles, set by the runtime
PROFILE_MISSING = "Your institution's profile could not be found. Read your guide again, or use the standard structure."


def use_storage(reader: Callable[[str], bytes], exists: Callable[[str], bool]) -> None:
    global _stored
    _stored = (reader, exists)
    load.cache_clear()


def available(rulebook_id: str) -> bool:
    try:
        load(rulebook_id)
    except AppError:
        return False
    return True


def stored_path(rulebook_id: str) -> str:
    return f"rulebooks/{rulebook_id}.json"


@cache
def load(rulebook_id: str) -> dict[str, Any]:
    """A packaged rulebook, or a profile built from a student's guide (saved once, never changed:
    a new guide gives a new id)."""
    if not rulebook_id.replace("-", "").isalnum():
        raise ValueError("invalid rulebook id")
    packaged = RULEBOOKS / f"{rulebook_id}.json"
    if packaged.exists():
        return json.loads(packaged.read_text(encoding="utf-8"))
    if _stored is None or not rulebook_id.startswith("custom-"):
        raise ValueError(f"unknown rulebook {rulebook_id}")
    read, exists = _stored
    if not exists(stored_path(rulebook_id)):  # Codex audit 56c4f83 M17: refused clearly, never a server error
        raise AppError(PROFILE_MISSING, code="PROFILE_MISSING", status=409)
    return json.loads(read(stored_path(rulebook_id)))


def chapter_spec(rulebook_id: str, number: int) -> dict[str, Any]:
    return next(c for c in load(rulebook_id)["chapters"] if c["number"] == number)


def target_words(rulebook_id: str, level: Level) -> int:
    """The whole proposal's length: the middle of the manual's page range for the level."""
    book = load(rulebook_id)
    low, high = book["levels"][level]["pages"]
    return (low + high) // 2 * book["words_per_page"]


@dataclass(frozen=True)
class SectionPlan:
    key: str
    number: str  # "1.2" (chapters are numbered; the manual makes numbering optional)
    heading: str
    brief: str
    words: int
    table: bool = False
    objective: str = ""  # the specific objective an empirical-review section covers


def sections(rulebook_id: str, number: int, level: Level, plan: ProposalPlan) -> list[SectionPlan]:
    """The chapter's sections in order, with word targets. The empirical review gets one
    sub-section per specific objective, as the manual asks the review to follow the objectives."""
    spec = chapter_spec(rulebook_id, number)
    concept = spec.get("kind") == "CONCEPT"  # the concept paper: fixed lengths from the manual, sections numbered 1, 2, 3…
    chapter_words = spec["words"] if concept else target_words(rulebook_id, level) * spec["share"]
    out: list[SectionPlan] = []
    for section in spec["sections"]:
        if plan.study_type in section.get("skip_for", []):
            continue  # e.g. no independent/dependent variables in a qualitative study (manual §2.1 note, §7.4)
        words = section["words"] if "words" in section else max(60, round(chapter_words * section["share"] / 10) * 10)
        heading = section["heading"]
        if number in (1, 4) and section["key"] == "questions" and plan.questions_kind != "QUESTIONS":
            heading = "Research Hypotheses" if plan.questions_kind == "HYPOTHESES" else "Research Propositions"
        if section.get("per_objective"):
            count = max(1, len(plan.specific_objectives))
            for i, objective in enumerate(plan.specific_objectives, start=1):
                out.append(SectionPlan(f"{section['key']}{i}", "", _objective_heading(objective), section["brief"], max(120, round(words / count / 10) * 10), objective=objective))
            continue
        out.append(SectionPlan(section["key"], "", heading, section["brief"], words, bool(section.get("table"))))
    return [SectionPlan(s.key, str(i + 1) if concept else f"{number}.{i}", s.heading, s.brief, s.words, s.table, s.objective) for i, s in enumerate(out)]


def _objective_heading(objective: str) -> str:
    """A sub-heading from an objective: "To assess the effect of X on Y" → "Effect of X on Y"."""
    text = objective.strip().rstrip(".")
    for lead in ("to examine ", "to assess ", "to establish ", "to determine ", "to investigate ", "to explore ", "to analyse ", "to analyze ", "to evaluate ", "to identify ", "to describe ", "to find out ", "to "):
        if text.lower().startswith(lead):
            text = text[len(lead) :]
            break
    text = text[:1].upper() + text[1:]
    return text if len(text) <= 120 else text[:117].rsplit(" ", 1)[0] + "…"


def vetting(rulebook_id: str, number: int) -> list[dict[str, Any]]:
    return list(load(rulebook_id)["vetting"]["questions"][str(number)])


def rules_for(rulebook_id: str) -> list[dict[str, str]]:
    """The general rules every chapter follows, as sent to the models (id and requirement only)."""
    return [{"id": r["id"], "requirement": r["requirement"]} for r in load(rulebook_id)["rules"] if r["enforcement"] != "INFORMATIONAL"]


MAX_OBJECTIVES = 8  # a hard limit for the software; the manual's two to five is a recommendation


def plan_problems(rulebook_id: str, plan: ProposalPlan) -> list[str]:
    """What must be fixed before a plan can be approved: code-checkable structure only. The manual's
    two-to-five guidance is a recommendation (`plan_advice`), not a blocker."""
    problems = []
    objectives = [o for o in plan.specific_objectives if o.strip()]
    questions = [q for q in plan.research_questions if q.strip()]
    if not objectives:
        problems.append("Add at least one specific objective.")
    if len(objectives) > MAX_OBJECTIVES:
        problems.append(f"PaperAid supports up to {MAX_OBJECTIVES} specific objectives.")
    if len(questions) != len(objectives):
        problems.append(f"Each objective needs its own research question: {len(objectives)} objectives, {len(questions)} questions.")
    if len(objectives) != len(plan.specific_objectives) or len(questions) != len(plan.research_questions):
        problems.append("Remove empty objectives or questions.")
    for label, value in (("a title", plan.title), ("a problem statement", plan.problem), ("a purpose", plan.purpose), ("a research design", plan.design), ("a scope", plan.scope)):
        if not value.strip():
            problems.append(f"The plan needs {label}.")
    if plan.study_type != "NON_EMPIRICAL" and not plan.population.strip():
        problems.append("The plan needs a study population.")
    rows = {r.objective: r for r in plan.alignment}
    for i in range(1, len(objectives) + 1):
        row = rows.get(i)
        if row is None or not (row.data.strip() and row.collection.strip() and row.analysis.strip()):
            problems.append(f"Objective {i} needs its data, collection method and analysis in the alignment table.")
    if any(r.objective < 1 or r.objective > len(objectives) for r in plan.alignment):
        problems.append("The alignment table has a row for an objective that does not exist.")
    if plan.questions_kind == "HYPOTHESES" and plan.study_type in ("QUALITATIVE", "NON_EMPIRICAL"):
        problems.append("Hypotheses are for studies with statistical testing; use research questions or propositions for this study.")
    return problems


def plan_advice(rulebook_id: str, plan: ProposalPlan) -> list[str]:
    """The manual's recommendations the plan does not follow; shown, never blocking."""
    book = load(rulebook_id)
    low, high = book["objectives"]["min"], book["objectives"]["max"]
    count = len([o for o in plan.specific_objectives if o.strip()])
    if not low <= count <= high:
        return [f"{low} to {high} specific objectives are generally expected; this plan has {count}."]
    return []


def chapter_blockers(plan: ProposalPlan, number: int) -> list[str]:
    """Facts only the student can give, without which a chapter would have to invent them."""
    if number != 3 or plan.study_type == "NON_EMPIRICAL":
        return []
    result = sampling.calculate(plan.sample_size)
    if sampling.needs_numbers(plan.study_type) and plan.sample_size.method in ("NOT_APPLICABLE", "SATURATION"):
        return ["Choose how the sample size will be determined (for example Yamane, Cochran, Krejcie and Morgan, or a census)."]
    if plan.study_type == "QUALITATIVE" and plan.sample_size.method == "NOT_APPLICABLE":
        return ["Say how many participants you expect (saturation, or a number you state) and why."]
    return [result.missing] if result.missing else []
