"""The worker stages of work steps (concept notes, coursework, funding proposals). A step is an
ordinary job (claim lease → run stage → save artifact → next stage), so retries, the response
cache, the spend cap and billing all come from app.jobs.pipeline. What is particular to works:

  READ:   ANALYSING (requirements read from the student's documents, quotes checked by code) → EXPORTING
  PLAN:   RESEARCHING → PLANNING (plan; for funding the Results Model and budget skeleton) → EXPORTING
  DRAFT:  RESEARCHING → DRAFTING → AUDITING (code checks, integrity, evaluation, bounded repair,
          final review, length compression) → EXPORTING
  REVISE: AUDITING (the student's requests, then the same checks) → EXPORTING

Every step reads the input frozen when it was priced, never the live work, and publishes only at
EXPORTING, in one transaction. A step whose own output fails a blocking rule after its bounded
repairs fails without charge; nothing half-checked is delivered (Codex review 2026-09-30 #4)."""

import hashlib
import json
import re
from typing import TYPE_CHECKING, Any

from app.ai.orchestration import check_content
from app.analysis import fetch, research
from app.core.errors import PermanentStageError
from app.jobs import state
from app.jobs.models import Job, JobStatus, ReadinessItem, Stage, Wallet, utcnow
from app.pricing.billing import settle_completed
from app.proposals import evidence as ev
from app.proposals.ai import SectionText, Table
from app.proposals.models import EvidenceItem, EvidenceSource
from app.proposals.pipeline import _from_literature, _from_web, load_library
from app.rules import compliance, library
from app.rules.extract import KEYS, requirements_from
from app.rules.validators import Context
from app.works import directives, numbers, templates
from app.works.ai import Evaluation, WorkRunner
from app.works.models import (
    AI_NOTE,
    Budget,
    BudgetLine,
    PlanSection,
    ResolvedSpec,
    ResultsModel,
    StoredDocVersion,
    Work,
    WorkDocument,
    WorkPlan,
    WorkSection,
    WorkStepInput,
)

if TYPE_CHECKING:
    from app.jobs.pipeline import StageContext

INPUT = "work_input.json"
DISCLOSURE = "Disclosure: this document was drafted with the assistance of an AI writing service (PaperAid)."
READING_CHUNK = 3000
READING_CHUNKS = 12  # the parts of a reading searched for one need: the most relevant, from anywhere in it
READ_CHARS = 120_000  # the most one reading call is sent
READ_OVERLAP = 2_000  # consecutive parts overlap, so a requirement split at a boundary is read whole
READING_OPENING = 12_000
HIGH_RISK = ("problem", "method", "result", "finding", "budget", "mel", "expected", "technical", "analysis", "discussion", "evaluation", "diagnosis", "capacity",
             "significance", "context")
NOT_REVIEWED = "The section was not reviewed within this step's limits."
STYLE = (
    "Write as a careful human author in the student's field: specific, concrete and grounded in the student's own facts and the evidence given; "
    "vary sentence length and structure naturally; avoid stock phrases and filler (for example 'delve', 'tapestry', 'multifaceted', 'plays a pivotal role', "
    "'in today's world', 'it is important to note'); no bullet lists unless the section asks for one; British or American spelling as the student writes."
)


def step_input(ctx: "StageContext") -> WorkStepInput:
    """The input frozen when the step was priced; every stage first checks it still runs the exact
    prompts and rules the quote froze (a stage may apply rules without any model call)."""
    check_content(ctx.job.quote.engine if ctx.job.quote else None)
    return WorkStepInput.model_validate(ctx.get_json(INPUT))


def _runner(ctx: "StageContext") -> WorkRunner:
    runner = ctx.ai(WorkRunner)
    assert isinstance(runner, WorkRunner)
    return runner


def _spec(inp: WorkStepInput) -> ResolvedSpec:
    if inp.spec is None:
        raise PermanentStageError("SPEC_MISSING", "PaperAid could not find what this work must satisfy. Nothing was charged; please start the step again.", "no spec in step input")
    return inp.spec


def _compact_spec(spec: ResolvedSpec) -> dict[str, Any]:
    """What the models get (rulebook §23): the resolved specification, never the rule library."""
    return {
        "documentType": spec.kind, "variant": spec.variant, "mode": spec.mode, "level": spec.level, "targetWords": spec.target_words,
        "limits": [limit.model_dump(by_alias=True) for limit in spec.limits], "formFields": [f.model_dump(by_alias=True) for f in spec.fields],
        "templateHeadings": spec.template_headings, "citationStyle": spec.citation_style, "sourcePolicy": spec.source_policy,
        "requiredReadings": spec.required_readings, "directives": [{"id": d, "expectation": directives.expectation(d)} for d in spec.directives],
        "subject": spec.subject, "limiting": spec.limiting, "coverage": [c.model_dump(by_alias=True) for c in spec.coverage],
        "scoring": [c.model_dump(by_alias=True) for c in spec.scoring], "priorities": spec.priorities, "overlays": spec.overlays,
        "duration": spec.duration_months, "currency": spec.currency, "eligibility": spec.eligibility, "exploratory": spec.exploratory,
        "hardConstraints": [r.label + ": " + r.value for r in spec.requirements if r.hard and r.locked and r.key not in ("eligibility", "subquestion", "directive")][:60],
        "assumptions": spec.assumptions,
    }


def _student(inp: WorkStepInput) -> dict[str, Any]:
    answers = {k: v for k, v in inp.inputs.answers.items() if v != "SKIPPED" and not k.startswith(("confirm:", "conflict:", "eligible:"))}
    return {"title": inp.inputs.title, "description": inp.inputs.description, "answers": answers, "experience": inp.inputs.experience}


def _allowed_text(inp: WorkStepInput) -> str:
    """What the student supplied or the documents state: figures in it need no citation."""
    spec = _spec(inp)
    return " ".join([json.dumps(_student(inp)), " ".join(r.value + " " + r.quote for r in spec.requirements), str(spec.duration_months or "")])


def _tokens(inp: WorkStepInput) -> dict[str, tuple[str, str]]:
    return numbers.values(_spec(inp), inp.results, inp.budget, inp.inputs)


# --- READ: the student's documents ---------------------------------------------------------------


def read_parts(inp: WorkStepInput, texts: dict[str, str]) -> list[list[dict[str, str]]]:
    """Every instruction document read in full, in overlapping parts packed into calls of at most
    READ_CHARS (Codex audit 2026-09-30 #7: a limit near the end of a long call is never missed). A set
    reading is a text to cite, not an instruction: only its opening is read, for its details."""
    parts: list[dict[str, str]] = []
    for s in inp.sources:
        text = texts.get(s.id, "")
        if s.role == "READING":
            parts.append({"id": s.id, "name": s.name, "role": s.role, "part": "opening", "text": text[:READING_OPENING]})
            continue
        starts = list(range(0, max(1, len(text) - READ_OVERLAP), READ_CHARS - READ_OVERLAP))
        for n, start in enumerate(starts, start=1):
            parts.append({"id": s.id, "name": s.name, "role": s.role, "part": f"{n} of {len(starts)}", "text": text[start : start + READ_CHARS]})
    calls: list[list[dict[str, str]]] = [[]]
    for part in parts:
        if calls[-1] and sum(len(p["text"]) for p in calls[-1]) + len(part["text"]) > READ_CHARS:
            calls.append([])
        calls[-1].append(part)
    return calls


def stage_analysing(ctx: "StageContext") -> None:
    inp = step_input(ctx)
    runner = _runner(ctx)
    texts = {s.id: ctx.rt.files.get(s.path).decode("utf-8") for s in inp.sources if ctx.rt.files.exists(s.path)}
    gone = [s.name for s in inp.sources if s.id not in texts]
    if gone:  # a document that cannot be read is never marked read (Codex audit 2026-09-30, second round)
        raise PermanentStageError("SOURCES_MISSING", "Some of your documents are no longer stored: " + ", ".join(gone)[:300] + ". Upload them again. Nothing was charged.",
                                  f"{len(gone)} source(s) missing")
    found: list[Any] = []
    unclear: list[str] = []
    readings: dict[str, Any] = {}
    for sources in read_parts(inp, texts):  # a call that cannot finish fails the step: nothing is marked read unread
        answer = runner.read({"documentType": inp.kind, "variant": inp.variant, "question": inp.inputs.description,
                              "keys": {k: label for k, (label, _) in KEYS.items()}, "sources": sources})
        found += answer.requirements
        unclear += answer.unclear
        for r in answer.readings:
            if isinstance(r, dict) and r.get("sourceId") and r["sourceId"] not in readings:
                readings[r["sourceId"]] = r
    requirements, unclear = requirements_from({"requirements": found, "unclear": list(dict.fromkeys(unclear))}, inp.sources, texts)
    ctx.put_json("read.json", {"requirements": [r.model_dump(by_alias=True) for r in requirements], "unclear": unclear, "readings": readings})


# --- RESEARCHING ------------------------------------------------------------------------------------


def _reading_items(runner: WorkRunner, inp: WorkStepInput, ctx: "StageContext", need: str, today: str) -> list[EvidenceItem]:
    """Evidence from the student's own readings (a closed source list, or required readings)."""
    out: list[EvidenceItem] = []
    for source in inp.sources:
        if source.role != "READING" or not ctx.rt.files.exists(source.path):
            continue
        text = ctx.rt.files.get(source.path).decode("utf-8")
        chunks = _relevant_chunks(text, need)
        bib = source.bibliography
        listed = [{"id": f"r{n}", "title": bib.get("title") or source.name, "year": bib.get("year", ""), "abstract": chunk} for n, chunk in enumerate(chunks, start=1)]
        by_id = {f"r{n}": chunk for n, chunk in enumerate(chunks, start=1)}
        for finding in runner.extract(need, listed):
            evidence_source = EvidenceSource(
                url=f"reading:{source.id}", title=bib.get("title") or source.name, authors=bib.get("authors", []), organisation=bib.get("organisation", ""),
                year=bib.get("year", ""), container=bib.get("container", ""), doi=bib.get("doi", ""), kind="ARTICLE" if bib.get("container") else "REPORT", metadata="PAGE",
            )
            out.append(EvidenceItem(
                id=ev.evidence_id(evidence_source.url, finding.passage), chapter=0, need=need, statement=finding.statement.strip(), passage=finding.passage.strip(),
                scope=finding.scope.strip(), access="FULL_TEXT", verified=research.quote_found(finding.passage, by_id[finding.work]), source=evidence_source, retrieved_on=today,
            ))
        if runner.budget_reached:
            break
    return out


def _relevant_chunks(text: str, need: str) -> list[str]:
    """The parts of a reading most related to a need, from anywhere in it, in their reading order
    (Codex audit 2026-09-30 #7: never only its opening pages)."""
    chunks = [text[i : i + READING_CHUNK] for i in range(0, len(text), READING_CHUNK)]
    if len(chunks) <= READING_CHUNKS:
        return chunks
    wanted = {w for w in re.findall(r"[a-z]+", need.lower()) if len(w) > 3}
    ranked = sorted(range(len(chunks)), key=lambda n: (-len(wanted & set(re.findall(r"[a-z]+", chunks[n].lower()))), n))
    return [chunks[n] for n in sorted(ranked[:READING_CHUNKS])]


def stage_researching(ctx: "StageContext") -> None:
    """Research needs are planned from the specification and plan; each is answered from the
    student's readings (always first), and, unless the sources are closed, from scholarly abstracts
    or live web search. PaperAid confirms every quoted passage itself; the integrity checker then
    confirms each finding supports its statement."""
    inp = step_input(ctx)
    spec = _spec(inp)
    settings = ctx.rt.settings
    runner = _runner(ctx)
    existing = load_library(ctx.rt.files, inp.evidence_files)
    if spec.variant == "REFLECTIVE" and spec.source_policy != "CLOSED" and not spec.required_readings and inp.step == "PLAN":
        ctx.put_json("evidence.json", [])
        return
    limit = 5 if inp.step == "PLAN" else 8
    payload = {
        "spec": _compact_spec(spec), "student": _student(inp), "step": inp.step,
        "sections": [{"key": s.key, "heading": s.heading, "requirement": s.brief} for s in (inp.plan.sections if inp.plan else [])],
        "library": [{"id": i.id, "statement": i.statement} for i in existing.values() if i.usable][:80], "limit": limit, "note": inp.note,
    }
    private = {w.lower() for w in inp.private}

    def safe(query: str) -> bool:
        return research.query_safe(query, set(), private)

    today = utcnow().date().isoformat()
    found: list[EvidenceItem] = []
    def named(text: str) -> bool:  # the need's own words reach the searching model too
        return bool({w.lower() for w in re.findall(r"[A-Za-z'’-]+", text)} & private)

    for need in [n for n in runner.research_needs(payload) if safe(n.query) and not named(n.need)][:limit]:
        items = _reading_items(runner, inp, ctx, need.need, today)
        if spec.source_policy != "CLOSED" and not runner.budget_reached:
            if need.kind == "LITERATURE":
                items += _from_literature(runner, need.need, need.query, 0, today, settings.proposal_works_per_need)  # type: ignore[arg-type]
            if not items and not runner.budget_reached:
                items += _from_web(runner, need.need, need.query, 0, today, settings.research_max_searches, safe)  # type: ignore[arg-type]
        found += items
        if runner.budget_reached:
            break
    found = ev.dedupe(found)
    checked = [i for i in found if i.verified]
    verdicts = runner.verify(
        [{"id": i.id, "claim": i.statement, "context": i.need, "sources": [{"title": i.source.title, "published": i.source.year, "access": i.access, "passage": i.passage, "scope": i.scope}]}
         for i in checked]
    ) if checked else {}
    for item in checked:
        verdict = verdicts.get(item.id)
        item.support = verdict.support if verdict else "NOT_FOUND"  # an unchecked finding is never usable
    ctx.put_json("evidence.json", [i.model_dump(by_alias=True) for i in found])
    if runner.budget_reached:
        ctx.update(lambda j: _warn(j, ["The research reached this step's spending limit, so fewer sources were gathered than planned."]))


def _library(ctx: "StageContext", inp: WorkStepInput) -> dict[str, EvidenceItem]:
    base = load_library(ctx.rt.files, inp.evidence_files)
    new = [EvidenceItem.model_validate(i) for i in ctx.get_json("evidence.json")] if ctx.has("evidence.json") else []
    return {i.id: i for i in ev.dedupe([*base.values(), *new])}


def _for_model(items: list[EvidenceItem], passages: bool = False) -> list[dict[str, str]]:
    out = []
    for i in items:
        entry = {"id": i.id, "statement": i.statement, "scope": i.scope, "source": f"{ev.author_label(i.source)}, {i.source.year or 'n.d.'}"}
        if passages:
            entry["sourceWords"] = i.passage
        out.append(entry)
    return out


# --- PLANNING -----------------------------------------------------------------------------------------


def _plan_from(answer: dict[str, Any], skeleton: list[PlanSection], spec: ResolvedSpec) -> WorkPlan:
    """The writer's plan, held to the skeleton by code: every skeleton section stays, locked
    headings keep their wording, words stay within each section's range, and the total within the
    target (a coursework theme's heading and brief are the writer's)."""
    by_key = {s.get("key", ""): s for s in answer.get("sections", []) if isinstance(s, dict)}
    coverage_ids = {c.id for c in spec.coverage}
    criteria_ids = {c.id for c in spec.scoring}
    sections = []
    for s in skeleton:
        proposed = by_key.get(s.key, {})
        words = proposed.get("words") if isinstance(proposed.get("words"), int) else s.words
        if s.max_words:
            words = max(s.min_words, min(s.max_words, words))
        heading = s.heading if s.locked else " ".join(str(proposed.get("heading") or s.heading).split())[:200]
        sections.append(s.model_copy(update={
            "heading": heading, "words": words,
            "brief": " ".join(str(proposed.get("brief") or s.brief).split())[:1500],
            "criteria": list(dict.fromkeys([*s.criteria, *[c for c in proposed.get("criteria", []) if c in criteria_ids]])),
            "coverage": [c for c in proposed.get("coverage", []) if c in coverage_ids],
        }))
    total = sum(s.words for s in sections) or 1
    if total > spec.target_words:
        sections = [s.model_copy(update={"words": max(s.min_words, round(s.words * spec.target_words / total))}) for s in sections]
    # Every part of the question needs a home (CW-003). The student's plan editor cannot move them, so
    # code places any the writer left out: a paid plan is always one the student can approve
    # (Codex audit 2026-09-30 #3).
    planned = {c for s in sections for c in s.coverage}
    body = [s for s in sections if s.key.startswith("theme") or s.key in ("analysis", "findings", "reflection", "diagnosis")] or sections
    for n, item in enumerate(c for c in spec.coverage if c.id not in planned):
        body[n % len(body)].coverage.append(item.id)
    return WorkPlan(
        title=" ".join(str(answer.get("title") or "").split())[:300] or spec.subject[:300] or "Untitled",
        position=" ".join(str(answer.get("position", "")).split())[:2000], sections=sections,
        questions_for_student=[str(q)[:300] for q in answer.get("questionsForStudent", [])][:10], notes=[str(n)[:300] for n in answer.get("notes", [])][:10],
    )


def _results_from(answer: dict[str, Any]) -> tuple[ResultsModel, list[BudgetLine]]:
    """The writer's Results Model. Baselines and targets are the applicant's figures: the writer
    never supplies them (the schema has no field for them); the student adds them."""
    data = {k: v for k, v in answer.items() if k != "budgetLines"}
    for indicator in data.get("indicators", []):
        indicator.update({"baseline": None, "target": None, "baselineYear": None})
    for activity in data.get("activities", []):
        for key in ("startMonth", "endMonth"):
            if isinstance(activity.get(key), int) and not 1 <= activity[key] <= 120:
                activity[key] = None
    model = ResultsModel.model_validate(_clip_strings(data))
    lines = [
        BudgetLine(id=f"B{n}", category=str(li.get("category", ""))[:80] or "Other", description=str(li.get("description", ""))[:300], quantity=0, unit=str(li.get("unit", ""))[:40],
                   unit_cost=0, activity_ids=[str(a) for a in li.get("activityIds", [])][:10], support=bool(li.get("support")), role=str(li.get("role", ""))[:120])
        for n, li in enumerate(answer.get("budgetLines", [])[:120], start=1)
    ]
    return model, lines


def _clip_strings(value: Any, limit: int = 600) -> Any:
    if isinstance(value, str):
        return value[:limit]
    if isinstance(value, list):
        return [_clip_strings(v, limit) for v in value]
    if isinstance(value, dict):
        return {k: _clip_strings(v, 120 if k in ("ownerRole", "responsibleRole") else 60 if k in ("unit", "frequency") else limit) for k, v in value.items()}
    return value


def stage_planning(ctx: "StageContext") -> None:
    inp = step_input(ctx)
    spec = _spec(inp)
    runner = _runner(ctx)
    usable = [i for i in _library(ctx, inp).values() if i.usable]
    skeleton = templates.skeleton(spec)
    rules = [r for r in library.rules_for(spec.kind) if r["id"] in set(spec.active_rules)]
    plan_rules = [{"rule": r["id"], "requirement": r["requirement"]} for r in library.scoped_rules(rules, "PLAN")]
    payload = {
        "spec": _compact_spec(spec), "student": _student(inp), "skeleton": [s.model_dump(by_alias=True) for s in skeleton],
        "evidence": _for_model(usable), "note": inp.note, "style": STYLE,
    }
    answer = runner.plan(payload).model_dump()
    plan = _plan_from(answer, skeleton, spec)
    review = runner.review_plan({**payload, "plan": plan.model_dump(by_alias=True), "rules": plan_rules,
                                 "paperaidChecks": _plan_problems(plan, spec)})
    if review.verdict == "REPAIR" or _plan_problems(plan, spec):
        answer = runner.plan({**payload, "draft": plan.model_dump(by_alias=True), "critique": [*review.issues, *_plan_problems(plan, spec)]}).model_dump()
        plan = _plan_from(answer, skeleton, spec)
    if _plan_problems(plan, spec):  # never charge for a plan the student could not approve
        raise PermanentStageError("PLAN_INCOMPLETE", "PaperAid could not make a plan that fits your requirements this time. Nothing was charged; please try again.",
                                  "plan: " + "; ".join(_plan_problems(plan, spec))[:300])
    out: dict[str, Any] = {"plan": plan.model_dump(by_alias=True), "review": review.model_dump()}
    if spec.kind == "FUNDING_PROPOSAL":
        results_payload = {"spec": _compact_spec(spec), "student": _student(inp), "plan": plan.model_dump(by_alias=True), "evidence": _for_model(usable), "note": inp.note}
        model, lines = _results_from(runner.results(results_payload))
        results_rules = [{"rule": r["id"], "requirement": r["requirement"]} for r in library.scoped_rules(rules, "RESULTS")]
        checked = runner.review_results({**results_payload, "results": model.model_dump(by_alias=True), "rules": results_rules})
        wrong = [c for c in checked.classified if c.reads != c.statedAs.lower()]
        if wrong or checked.issues:
            critique = [*checked.issues, *[f"{c.id} is stated as a {c.statedAs} but reads as a {c.reads}: {c.note}" for c in wrong]]
            model, lines = _results_from(runner.results({**results_payload, "draft": model.model_dump(by_alias=True), "critique": critique}))
        out["results"] = model.model_dump(by_alias=True)
        out["budgetLines"] = [li.model_dump(by_alias=True) for li in lines]
    ctx.put_json("plan.json", out)


def _plan_problems(plan: WorkPlan, spec: ResolvedSpec) -> list[str]:
    """What stops a plan being approved (the same test at planning and at approval)."""
    problems = []
    planned = {c for s in plan.sections for c in s.coverage}
    problems += [f"No section answers this part of the question: {c.text}" for c in spec.coverage if c.id not in planned]
    if plan.total_words > spec.target_words * 1.02:
        problems.append(f"The plan has {plan.total_words} words; the target is {spec.target_words}.")
    hard = next((limit.max for limit in spec.limits if limit.type == "WORD"), None)
    if hard is not None and plan.total_words > hard:
        problems.append(f"The plan has {plan.total_words:,} words; your limit is {int(hard):,}.")
    return problems


# --- DRAFTING ------------------------------------------------------------------------------------------


def _section_items(inp: WorkStepInput, library_items: dict[str, EvidenceItem], only: set[str] | None = None) -> list[dict[str, Any]]:
    assert inp.plan is not None
    spec = _spec(inp)
    usable = [i for i in library_items.values() if i.usable]
    coverage = {c.id: c.text for c in spec.coverage}
    criteria = {c.id: {"name": c.name, "weight": c.weight, "descriptor": c.descriptor} for c in spec.scoring}
    field_limits = {f.id: {"maxWords": f.max_words, "maxCharacters": f.max_characters} for f in spec.fields}
    items = []
    for s in inp.plan.sections:
        if only is not None and s.key not in only:
            continue
        relevant = _relevant(s, usable)
        items.append({
            "key": s.key, "heading": s.heading, "brief": s.brief, "words": s.words, "minWords": s.min_words, "maxWords": s.max_words,
            "coverage": [coverage[c] for c in s.coverage if c in coverage], "criteria": [criteria[c] for c in s.criteria if c in criteria],
            "field": field_limits.get(s.field_id), "evidence": _for_model(relevant, passages=True),
            "_words": " ".join(["w"] * s.words),
        })
    return items


def _relevant(section: PlanSection, usable: list[EvidenceItem], limit: int = 12) -> list[EvidenceItem]:
    """The evidence most related to a section's heading and brief (by shared words), for the writer."""
    words = {w for w in re.findall(r"[a-z]+", (section.heading + " " + section.brief).lower()) if len(w) > 3}

    def score(item: EvidenceItem) -> int:
        return len(words & {w for w in re.findall(r"[a-z]+", (item.need + " " + item.statement).lower()) if len(w) > 3})

    return sorted(usable, key=score, reverse=True)[:limit]


def _common(inp: WorkStepInput) -> dict[str, Any]:
    tokens = _tokens(inp)
    return {
        "spec": _compact_spec(_spec(inp)), "student": _student(inp), "position": inp.plan.position if inp.plan else "", "title": inp.plan.title if inp.plan else inp.inputs.title,
        "numberTokens": numbers.for_model(tokens), "results": inp.results.model_dump(by_alias=True) if inp.results else None,
        "style": STYLE, "note": inp.note,
        "rulesForWriting": [
            "Cite only with evidence tokens exactly as given (for example ⟦E1a2b3c⟧); never type a citation by hand.",
            "Use a number token whenever a figure from the budget, Results Model, call or the student's answers is needed; never type such a figure yourself.",
            "Never invent the student's experience, data, figures, partners, results or organisational facts: say what is known and flag what the student must add.",
            "Keep every quotation and figure the student gave exactly as given.",
        ],
    }


def stage_drafting(ctx: "StageContext") -> None:
    inp = step_input(ctx)
    runner = _runner(ctx)
    items = _section_items(inp, _library(ctx, inp))
    common = _common(inp)
    drafted = runner.draft(items, common)
    for item in items:  # a writer that leaves a section out of a batch is asked for it on its own, once
        if item["key"] not in drafted and not runner.budget_reached:
            drafted.update(runner.draft([item], common))
    ctx.put_json("drafted.json", {k: v.model_dump() for k, v in drafted.items()})


# --- AUDITING ------------------------------------------------------------------------------------------


def _cells(text: SectionText) -> list[str]:
    return [text.table.caption, *[cell for row in text.table.rows for cell in row]]


def _rendered_words(text: SectionText, tokens: dict[str, tuple[str, str]]) -> int:
    return sum(len(ev.ANY_TOKEN.sub(" ", numbers.render(p, tokens)[0]).split()) for p in text.paragraphs)


def _checks(inp: WorkStepInput, section: PlanSection, text: SectionText, library_items: dict[str, EvidenceItem], allowed: str, tokens: dict[str, tuple[str, str]]) -> list[str]:
    """Code checks on one section: citations, figures, number tokens, length, and the source rule."""
    spec = _spec(inp)
    usable = {i for i, item in library_items.items() if item.usable}
    problems: list[str] = []
    for paragraph in [*text.paragraphs, *(_cells(text) if text.table.rows else [])]:
        plain = numbers.strip(paragraph)
        problems += ev.citation_problems(plain, usable)
        problems += [p + " Use a number token for figures from the budget, Results Model or your answers." for p in ev.figure_problems(plain, library_items, allowed)]
        problems += [f"{t} is not an available number token." for t in numbers.render(paragraph, tokens)[1]]
        if spec.source_policy == "CLOSED":
            problems += [f"⟦{i}⟧ is not one of the set readings." for i in ev.cited_ids(plain) if i in library_items and not library_items[i].source.url.startswith("reading:")]
    words = _rendered_words(text, tokens)
    if not any(p.strip() for p in text.paragraphs):
        problems.append("The section is empty.")
    elif section.max_words and words > section.max_words * 1.1:
        problems.append(f"The section has {words} words; keep it to about {section.words} (at most {section.max_words}).")
    elif section.min_words and words < section.min_words * 0.8:
        problems.append(f"The section has {words} words; it needs about {section.words}.")
    field = next((f for f in spec.fields if f.id == section.field_id), None)
    if field is not None:
        rendered = " ".join(numbers.render(p, tokens)[0] for p in text.paragraphs)
        if field.max_characters and len(rendered) > field.max_characters:
            problems.append(f"The box allows {field.max_characters} characters; this has {len(rendered)}.")
        if field.max_words and len(rendered.split()) > field.max_words:
            problems.append(f"The box allows {field.max_words} words; this has {len(rendered.split())}.")
    return list(dict.fromkeys(problems))


def _risk(section: PlanSection, text: SectionText) -> str:
    if any(k in section.key for k in HIGH_RISK) or any(ev.cited_ids(p) for p in text.paragraphs) or any(numbers.NUMBER_TOKEN.search(p) for p in text.paragraphs):
        return "high"
    return "medium" if section.key.startswith("theme") else "low"


def _rules_for(spec: ResolvedSpec, key: str) -> list[dict[str, Any]]:
    active = set(spec.active_rules)
    return [r for r in library.section_rules([r for r in library.rules_for(spec.kind) if r["id"] in active], key)]


def _review_items(inp: WorkStepInput, sections: dict[str, PlanSection], current: dict[str, SectionText], problems: dict[str, list[str]], keys: list[str]) -> list[dict[str, Any]]:
    spec = _spec(inp)
    coverage = {c.id: c.text for c in spec.coverage}
    return [
        {
            "key": k, "heading": sections[k].heading, "brief": sections[k].brief, "words": sections[k].words, "text": current[k].paragraphs,
            "table": current[k].table.model_dump() if current[k].table.rows else None,
            "rules": [{"rule": r["id"], "requirement": r["requirement"], "severity": r["severity"]} for r in _rules_for(spec, k)],
            "coverage": [coverage[c] for c in sections[k].coverage if c in coverage], "paperaidChecks": problems.get(k, []),
            "_words": " ".join(current[k].paragraphs),
        }
        for k in keys
    ]


def _issues_from(evaluation: Evaluation | None, integrity: Any) -> list[str]:
    issues: list[str] = []
    if evaluation is not None and evaluation.verdict != "PASS":
        issues += [i.instruction for i in evaluation.issues]
        issues += [f"{r.rule}: {r.note}" for r in evaluation.rules if r.status == "FAIL"]
    if integrity is not None and (not integrity.meaningKept or integrity.invented or integrity.lockedChanged):
        issues += [f"Remove or qualify what is not supported: {x}" for x in integrity.invented]
        issues += [f"Restore exactly as the student gave it: {x}" for x in integrity.lockedChanged]
        if not integrity.meaningKept and integrity.note:
            issues.append(integrity.note)
    return list(dict.fromkeys(i for i in issues if i.strip()))


def _audit(ctx: "StageContext", runner: WorkRunner, inp: WorkStepInput, current: dict[str, SectionText], targets: list[str], rounds: int | None = None) -> dict[str, Any]:
    """Code checks, integrity and evaluation on `targets`; the writer repairs only what fails; at most
    `rounds` repair rounds (the configured number unless given). Returns what is known about each
    section afterwards, always about its text as it now stands."""
    assert inp.plan is not None
    library_items = _library(ctx, inp)
    allowed = _allowed_text(inp)
    tokens = _tokens(inp)
    sections = {s.key: s for s in inp.plan.sections}
    common = _common(inp)
    premium = runner._engine.tier == "PREMIUM"
    rounds = ctx.rt.settings.repair_attempts if rounds is None else rounds
    evaluations: dict[str, Evaluation] = {}
    integrity: dict[str, Any] = {}
    unresolved: dict[str, list[str]] = {}
    pending = [k for k in targets if k in current]
    for round_ in range(rounds + 1):
        for key in pending:  # verdicts on earlier wording never carry over to repaired text (Codex audit, second round)
            integrity.pop(key, None)
            evaluations.pop(key, None)
        problems = {k: _checks(inp, sections[k], current[k], library_items, allowed, tokens) for k in pending}
        items = _review_items(inp, sections, current, problems, pending)
        integrity.update(runner.integrity([{**i, "lockedFacts": common["student"]} for i in items], {"spec": common["spec"], "student": common["student"]}))
        judged = [i for i in items if i["rules"] or premium or _risk(sections[i["key"]], current[i["key"]]) != "low"]
        evaluations.update(runner.evaluate(judged, {**common, "tier": runner._engine.tier}))
        unresolved = {}
        for key in pending:
            issues = [*problems[key], *_issues_from(evaluations.get(key), integrity.get(key))]
            if key not in integrity or (key in {i["key"] for i in judged} and key not in evaluations):
                issues.append(NOT_REVIEWED)
            if issues:
                unresolved[key] = issues
        if premium and unresolved:  # the evaluator and the integrity check disagree: the adjudicator settles it
            split = [k for k in unresolved if (evaluations.get(k) and evaluations[k].verdict == "PASS") != bool(integrity.get(k) and integrity[k].meaningKept and not integrity[k].invented)]
            if split:
                decided = runner.adjudicate([{"key": k, "text": current[k].paragraphs, "evaluation": evaluations[k].model_dump() if k in evaluations else None,
                                              "integrity": integrity[k].model_dump() if k in integrity else None} for k in split], common)
                for key, decision in decided.items():
                    if decision.decision == "PASS" and not [p for p in unresolved[key] if p in problems.get(key, [])]:
                        unresolved.pop(key, None)
                    elif decision.instruction.strip():
                        unresolved[key].append(decision.instruction)
        if not unresolved or runner.budget_reached or round_ == rounds:
            break
        fixes = [{**i, "issues": unresolved[i["key"]]} for i in _review_items(inp, sections, current, problems, list(unresolved))]
        for key, fixed in runner.repair(fixes, common).items():
            current[key] = fixed
        pending = list(unresolved)
    return {"unresolved": unresolved, "evaluations": evaluations, "integrity": integrity, "library": library_items, "tokens": tokens, "allowed": allowed}


def _strip(inp: WorkStepInput, text: SectionText, library_items: dict[str, EvidenceItem], allowed: str) -> SectionText:
    """The last line of defence: a sentence (or table cell) that still carries an untraceable
    citation or figure is withheld whole, never left without its support (Codex review 2026-09-30 #3)."""
    usable = {i for i, item in library_items.items() if item.usable}

    def clean(paragraph: str) -> str:
        # Placeholders without digits: a digit in one would read as an unsupported figure.
        protected = {"⟪" + "".join(chr(97 + int(d)) for d in str(n)) + "⟫": m.group(0) for n, m in enumerate(numbers.NUMBER_TOKEN.finditer(paragraph))}
        plain = paragraph
        for placeholder, token in protected.items():
            plain = plain.replace(token, placeholder, 1)
        kept = ev.strip_unsupported(plain, library_items, usable, allowed)
        for placeholder, token in protected.items():
            kept = kept.replace(placeholder, token)
        return kept

    for _ in range(5):  # removing a cited sentence can leave a neighbour's figure unsupported
        tidy = text.model_copy(update={
            "paragraphs": [p for p in (clean(p) for p in text.paragraphs) if p],
            # Table cells and the caption are delivered like prose, so they are held to the same rule
            # (Codex audit 2026-09-30 #6); a withheld cell stays as an empty cell.
            "table": Table(caption=clean(text.table.caption), rows=[[clean(c) for c in row] for row in text.table.rows]),
        })
        if tidy == text:
            break
        text = tidy
    return text


def _final(ctx: "StageContext", runner: WorkRunner, inp: WorkStepInput, current: dict[str, SectionText], library_items: dict[str, EvidenceItem], tokens: dict[str, tuple[str, str]]):
    spec = _spec(inp)
    assert inp.plan is not None
    citer = ev.Citer(library_items, spec.citation_style)
    rules = [r for r in library.rules_for(spec.kind) if r["id"] in set(spec.active_rules)]
    doc_rules = library.scoped_rules(rules, "DOCUMENT")
    payload = {
        "spec": _compact_spec(spec), "student": _student(inp), "position": inp.plan.position,
        "document": [{"key": s.key, "heading": s.heading, "text": [numbers.render(citer.render(p), tokens)[0] for p in current[s.key].paragraphs]}
                     for s in inp.plan.sections if s.key in current],
        "rules": [{"rule": r["id"], "requirement": r["requirement"], "severity": r["severity"]} for r in doc_rules],
        "coverage": [c.model_dump(by_alias=True) for c in spec.coverage], "priorities": spec.priorities,
    }
    return runner.final(payload), doc_rules


def _where_keys(where: str, plan_sections: list[PlanSection]) -> list[str]:
    text = where.lower()
    return [s.key for s in plan_sections if s.key in text or s.heading.lower() in text or text in s.heading.lower()]


def _word_excess(inp: WorkStepInput, current: dict[str, SectionText], library_items: dict[str, EvidenceItem], tokens: dict[str, tuple[str, str]]) -> tuple[int, set[str] | None]:
    """How many words must go for the text the word limit counts (its scope: sections, their tables,
    and the references or generated tables where the instructions count them) to fit with a margin,
    and the sections the limit covers (None: all). 0 when it already fits."""
    spec = _spec(inp)
    limit = next((lim for lim in spec.limits if lim.type == "WORD"), None)
    if limit is None:
        return 0, None
    context = Context(spec=spec, stage="FINAL", inputs=inp.inputs, plan=inp.plan, results=inp.results, budget=inp.budget,
                      doc=_document(inp, current, set()), library=library_items, tokens=tokens)
    total = sum(len(t.split()) for t in context.limit_texts(limit)[0])
    named = set(limit.scope) & set(current)
    covered = named if named and named == set(limit.scope) else None
    if total <= limit.max * (1 + limit.tolerance / 100):
        return 0, covered
    return int(total - limit.max * 0.95), covered


def _compress_to_limits(ctx: "StageContext", runner: WorkRunner, inp: WorkStepInput, current: dict[str, SectionText], tokens: dict[str, tuple[str, str]],
                        library_items: dict[str, EvidenceItem], keys: list[str]) -> None:
    """Targeted compression for hard limits (§6.1): only the sections this step may change shrink,
    each by its share of what the limit's whole scope is over."""
    spec = _spec(inp)
    assert inp.plan is not None
    fields = {f.id: f for f in spec.fields}
    for _ in range(2):
        over: dict[str, int] = {}
        excess, covered = _word_excess(inp, current, library_items, tokens)
        if excess:
            sizes = {k: _rendered_words(current[k], tokens) for k in keys if k in current and (covered is None or k in covered)}
            pool = sum(sizes.values()) or 1
            over.update({k: max(40, int(w - excess * w / pool)) for k, w in sizes.items() if w})
        for s in inp.plan.sections:
            field = fields.get(s.field_id)
            if field and s.key in current and s.key in keys:
                rendered = " ".join(numbers.render(p, tokens)[0] for p in current[s.key].paragraphs)
                if field.max_characters and len(rendered) > field.max_characters:
                    over[s.key] = int(field.max_characters * 0.92 / 6.5)
                if field.max_words and len(rendered.split()) > field.max_words:
                    over[s.key] = int(field.max_words * 0.95)
        if not over:
            return
        items = [{"key": k, "heading": next(s.heading for s in inp.plan.sections if s.key == k), "text": current[k].paragraphs,
                  "table": current[k].table.model_dump(), "targetWords": w, "_words": " ".join(current[k].paragraphs)} for k, w in over.items()]
        for key, shorter in runner.compress(items, _common(inp)).items():
            current[key] = shorter


def _document(inp: WorkStepInput, current: dict[str, SectionText], reviewed: set[str]) -> WorkDocument:
    assert inp.plan is not None
    spec = _spec(inp)
    sections: list[WorkSection] = []
    cited: list[str] = []
    for s in inp.plan.sections:
        text = current.get(s.key)
        if text is None or not text.paragraphs:
            continue
        rows = [[c.strip() for c in r] for r in text.table.rows if any(c.strip() for c in r)]
        width = max((len(r) for r in rows), default=0)
        rows = [r + [""] * (width - len(r)) for r in rows]  # rectangular: a writer's uneven rows are padded, never cut
        table = rows if len(rows) >= 2 and width >= 2 else None
        for field in [*text.paragraphs, *(_cells(text) if table else [])]:
            cited += [i for i in ev.cited_ids(field) if i not in cited]
        sections.append(WorkSection(key=s.key, heading=s.heading, paragraphs=text.paragraphs, table=table, table_caption=text.table.caption if table else "",
                                    field_id=s.field_id, reviewed=s.key in reviewed))
    note = ""
    if spec.kind == "COURSEWORK":
        if spec.ai_policy == "BANNED" or (spec.ai_policy == "UNKNOWN" and inp.ai_note):
            note = AI_NOTE  # never removable for a banned policy (owner decision 2026-09-30)
        elif spec.ai_policy == "ALLOWED_WITH_DISCLOSURE":
            note = DISCLOSURE
    return WorkDocument(kind=inp.kind, variant=inp.variant, title=inp.plan.title, spec_version=spec.version, plan_version=inp.plan_version,
                        results_version=inp.results_version, budget_version=inp.budget_version, sections=sections, cited=cited, exploratory=spec.exploratory, ai_note=note,
                        spec_snapshot=spec, results_snapshot=inp.results, budget_snapshot=inp.budget,
                        number_values={k: [v[0], v[1]] for k, v in _tokens(inp).items()})


def _base(ctx: "StageContext", inp: WorkStepInput) -> WorkDocument:
    path = inp.base
    if not ctx.rt.files.exists(path):
        raise PermanentStageError("VERSION_MISSING", "The version being revised is no longer stored. Nothing was charged.", "revise: base missing")
    data = ctx.rt.files.get(path)
    if hashlib.sha256(data).hexdigest() != inp.base_sha:
        raise PermanentStageError("VERSION_CHANGED", "The version being revised changed. Nothing was charged; price the changes again.", "revise: base changed")
    return WorkDocument.model_validate_json(data)


def stage_auditing(ctx: "StageContext") -> None:
    """Every check runs on the exact text that will be published (Codex audit 2026-09-30 #2): the
    sections are reviewed and repaired, the whole document is reviewed and repaired, then lengths are
    compressed and unsupported sentences withheld; whatever that changed is reviewed again, and so is
    the whole document. A revision delivers only the requested changes that passed their review
    (the rest stay exactly as they were) and is charged for that share (Codex audit 2026-09-30 #4)."""
    inp = step_input(ctx)
    spec = _spec(inp)
    assert inp.plan is not None
    runner = _runner(ctx)
    headings = {s.key: s.heading for s in inp.plan.sections}
    base: WorkDocument | None = None
    original: dict[str, SectionText] = {}
    if inp.step == "REVISE":
        base = _base(ctx, inp)
        current = {s.key: SectionText(key=s.key, paragraphs=s.paragraphs, table=Table(caption=s.table_caption, rows=s.table or [])) for s in base.sections}
        original = dict(current)
        targets = [k for k in inp.revise if k in current]
        requests = [{"key": k, "heading": headings.get(k, k), "text": current[k].paragraphs, "table": current[k].table.model_dump(),
                     "issues": [f"The student asks: {r}" for r in inp.revise[k]], "_words": " ".join(current[k].paragraphs)} for k in targets]
        for key, revised in runner.repair(requests, _common(inp)).items():
            if key in targets:
                current[key] = revised
        # A requested section the writer did not return, or returned unchanged, was not revised: never
        # charged for, and its request stays open (Codex audit 2026-09-30, second round).
        unchanged = [k for k in targets if current[k] == original[k]]
        if len(unchanged) == len(targets):
            raise PermanentStageError("NOTHING_REVISED", "PaperAid could not make these changes this time, so your document is unchanged and nothing was charged.",
                                      "revise: nothing returned changed")
    else:
        unchanged = []
        current = {k: SectionText.model_validate(v) for k, v in ctx.get_json("drafted.json").items()}
        targets = [s.key for s in inp.plan.sections if s.key in current]
        missing = [s.heading for s in inp.plan.sections if s.required and s.key not in current]
        if missing:
            raise PermanentStageError("DOCUMENT_INCOMPLETE", "PaperAid could not write every section of this draft within its limits. Nothing was charged; please try again.",
                                      f"not drafted: {', '.join(missing)}")
    library_items, tokens, allowed = _library(ctx, inp), _tokens(inp), _allowed_text(inp)
    editable = [k for k in targets if k not in unchanged]  # what this step may still change; a revision's other sections stay exactly as delivered
    unresolved: dict[str, list[str]] = {}
    evaluations: dict[str, Evaluation] = {}
    integrity: dict[str, Any] = {}
    reviewed_text: dict[str, SectionText] = {}  # each section's text when it was last reviewed
    reverted: list[str] = list(unchanged)

    def review(keys: list[str], rounds: int | None = None) -> None:
        keys = [k for k in dict.fromkeys(keys) if k in current and k in editable]
        if not keys:
            return
        known = _audit(ctx, runner, inp, current, keys, rounds)
        for k in keys:
            unresolved.pop(k, None)
            evaluations.pop(k, None)
            integrity.pop(k, None)
            reviewed_text[k] = current[k]
        unresolved.update(known["unresolved"])
        evaluations.update(known["evaluations"])
        integrity.update(known["integrity"])
        if base is not None:  # a requested change that did not pass its review is not delivered
            for k in [k for k in keys if k in unresolved]:
                current[k] = original[k]
                unresolved.pop(k)
                evaluations.pop(k, None)
                integrity.pop(k, None)
                editable.remove(k)
                reverted.append(k)
            if not editable:
                raise PermanentStageError("NOTHING_REVISED", "PaperAid could not make these changes this time, so your document is unchanged and nothing was charged.",
                                          "revise: nothing resolved")

    review(targets)
    # The whole document: rules judged across sections, every part of the question, every priority.
    final, doc_rules = _final(ctx, runner, inp, current, library_items, tokens)
    judged_document = dict(current)
    blocking_ids = {r["id"] for r in doc_rules if r["severity"] == "BLOCKING"}
    failed_blocking = [r for r in (final.rules if final else []) if r.status == "FAIL" and r.rule in blocking_ids]
    missed_coverage = [c for c in (final.coverage if final else []) if not c.answered]
    if final is not None and (failed_blocking or missed_coverage):
        fix: dict[str, list[str]] = {}

        def fixable(keys: list[str]) -> list[str]:
            return [k for k in keys if k in editable] or editable[-1:]

        for r in failed_blocking:
            for key in fixable(_where_keys(r.where, inp.plan.sections)):
                fix.setdefault(key, []).append(f"{r.rule}: {r.note}")
        texts = {c.id: c.text for c in spec.coverage}
        for c in missed_coverage:
            for key in fixable([s.key for s in inp.plan.sections if c.id in s.coverage] or _where_keys(c.where, inp.plan.sections)):
                fix.setdefault(key, []).append(f"Answer this part of the question explicitly: {texts.get(c.id, c.id)}")
        repaired = runner.repair(
            [{"key": k, "heading": headings.get(k, k), "text": current[k].paragraphs, "table": current[k].table.model_dump(),
              "issues": v, "_words": " ".join(current[k].paragraphs)} for k, v in fix.items() if k in current], _common(inp))
        current.update({k: v for k, v in repaired.items() if k in fix})
        review(list(fix))
    _compress_to_limits(ctx, runner, inp, current, tokens, library_items, editable)
    stripped: list[str] = []
    for key in list(editable):
        cleaned = _strip(inp, current[key], library_items, allowed)
        if cleaned != current[key]:
            stripped.append(key)
            current[key] = cleaned
    review([k for k in editable if current[k] != reviewed_text.get(k)], rounds=0)  # changed after its review: reviewed again, not repaired
    if current != judged_document:
        final, doc_rules = _final(ctx, runner, inp, current, library_items, tokens)
    stripped = [headings.get(k, k) for k in stripped if k not in reverted]
    empty = [s.heading for s in inp.plan.sections if s.required and s.key in current and not current[s.key].paragraphs]
    if empty:
        raise PermanentStageError("DOCUMENT_NOT_VERIFIED", "PaperAid could not write parts of this draft that it could verify. Nothing was charged; please try again.",
                                  f"empty after checks: {', '.join(empty)}")
    if base is not None:  # only sections whose saved text changed count as revised (and are charged for)
        for key in [k for k in editable if current[k] == original[k]]:
            editable.remove(key)
            reverted.append(key)
        if not editable:
            raise PermanentStageError("NOTHING_REVISED", "PaperAid could not make these changes this time, so your document is unchanged and nothing was charged.",
                                      "revise: nothing changed")

    document = _document(inp, current, set(evaluations) | set(integrity))
    if base is not None:
        document.revised = list(editable)
        earlier = {s.key: s.reviewed for s in base.sections}
        for s in document.sections:
            if s.key not in editable:
                s.reviewed = earlier.get(s.key, s.reviewed)
    semantic: dict[str, tuple[str, str, str]] = {}
    for key, evaluation in evaluations.items():
        for r in evaluation.rules:
            previous = semantic.get(r.rule)
            if previous is None or (r.status == "FAIL" and previous[0] != "FAIL"):
                semantic[r.rule] = (r.status, r.note, key)
    for r in (final.rules if final else []):
        semantic[r.rule] = (r.status, r.note, r.where)
    retracted = {i.source.doi for i in library_items.values() if i.source.doi and i.id in document.cited and fetch.openalex_retracted(i.source.doi)}
    pages = _pages(ctx, inp, document, library_items) if any(limit.type == "PAGE" for limit in spec.limits) else None
    context = Context(
        spec=spec, stage="FINAL", inputs=inp.inputs, plan=inp.plan, results=inp.results, budget=inp.budget, doc=document, library=library_items, tokens=tokens,
        pages=pages, research_done=bool([i for i in library_items.values() if i.usable]), stripped=stripped, retracted=retracted, semantic=semantic,
        coverage={c.id: c.answered for c in (final.coverage if final else [])}, priorities={p.priority: p.addressed for p in (final.priorities if final else [])},
    )
    items = compliance.report(context, ("DRAFT", "FINAL", "RENDER", "PLAN"))
    concerns = [f"{next((s.heading for s in inp.plan.sections if s.key == k), k)}: " + "; ".join(v[:3]) for k, v in unresolved.items() if v != [NOT_REVIEWED]]
    if concerns:
        items.append(ReadinessItem(id="W-OPEN", question="Points PaperAid's reviewers raised that still need your attention", status="NEEDS_REVIEW", basis="AI",
                                   note=" | ".join(concerns)[:600], severity="WARNING"))
    unreviewed = [k for k, v in unresolved.items() if NOT_REVIEWED in v]
    if unreviewed or final is None:
        items.append(ReadinessItem(id="W-REVIEWED", question="Every section was reviewed after its last change", status="NEEDS_REVIEW", basis="CODE", severity="WARNING",
                                   note="Not fully reviewed within this step's limits: " + ", ".join(unreviewed or ["the whole-document review"])))
    # PaperAid's own output breaking a blocking rule after its repairs is never delivered. What only
    # the student can settle (eligibility, their facts) or PaperAid cannot measure (an estimated page
    # count) stays visible as "Not ready" instead.
    own_failures = [i for i in items if i.status == "BLOCKED" and i.basis != "AUTHOR"]
    if own_failures:
        raise PermanentStageError(
            "DOCUMENT_NOT_READY", "PaperAid could not produce a draft that meets every required rule this time. Nothing was charged; please try again.",
            "blocking: " + "; ".join(f"{i.id} {i.note[:80]}" for i in own_failures)[:400],
        )
    document.readiness = items
    document.status = compliance.overall(items, spec.exploratory)  # type: ignore[assignment]
    document.words = context.words()
    from app.works import export

    # The Word file is built once before the step can complete and be charged: a document that cannot
    # be exported fails here, without charge, never at the student's download (Codex audit, second round).
    export.build(document, spec, inp.results, inp.budget, library_items, tokens, draft=document.status == "NOT_READY")
    warnings = []
    if stripped:
        warnings.append(f"PaperAid withheld sentences it could not trace to confirmed evidence or your own details in: {', '.join(stripped)}.")
    if concerns:
        warnings.append("Some points still need your attention: " + " | ".join(concerns)[:800])
    share = len(editable) / len(targets) if base is not None and targets else 1.0
    if share < 1:
        warnings.append("PaperAid could not make the changes you asked for in: " + ", ".join(headings.get(k, k) for k in reverted)
                        + ". Those sections are unchanged, your requests for them stay open, and you are charged only for the changes made.")
    ctx.put_json("document.json", document.model_dump(by_alias=True))

    def delivered(j: Job) -> Job:
        j = _warn(j, warnings)
        if share < 1:  # fixed prices charge each line for what was delivered (billing.delivered_share)
            j.delivery[j.selection.work_band] = round(share, 4)
            j.outcome = "PARTIAL"
        return j

    ctx.update(delivered)


def _pages(ctx: "StageContext", inp: WorkStepInput, document: WorkDocument, library_items: dict[str, EvidenceItem]) -> float | None:
    """The rendered page count, when rendering is switched on (Workstream H)."""
    if not ctx.rt.settings.render_pages:
        return None
    from app.works import export, render

    data = export.build(document, _spec(inp), inp.results, inp.budget, library_items, _tokens(inp), draft=False)
    return render.page_count(data)


# --- EXPORTING --------------------------------------------------------------------------------------------


def stage_exporting(ctx: "StageContext") -> None:
    inp = step_input(ctx)
    work = ctx.rt.store.get_work(inp.work_id)
    if work is None or work.deleting:
        raise PermanentStageError("WORK_DELETED", "This work was deleted before the step finished, so nothing was charged.", "work gone at export")
    job_id = ctx.job.id
    evidence_path = ""
    if ctx.has("evidence.json"):
        evidence_path = f"{work.storage_prefix()}/evidence/{job_id}.json"
        ctx.rt.files.put(evidence_path, ctx.get_bytes("evidence.json"), "application/json")
    doc_path = ""
    document: WorkDocument | None = None
    if inp.step in ("DRAFT", "REVISE"):
        document = WorkDocument.model_validate(ctx.get_json("document.json"))
        doc_path = f"{work.storage_prefix()}/documents/{job_id}.json"
        ctx.rt.files.put(doc_path, document.model_dump_json(by_alias=True).encode(), "application/json")
    planned = ctx.get_json("plan.json") if inp.step == "PLAN" else None
    read = ctx.get_json("read.json") if inp.step == "READ" else None
    requirements_path = ""
    if read is not None:
        requirements_path = f"{work.storage_prefix()}/requirements/{job_id}.json"
        ctx.rt.files.put(requirements_path, json.dumps(read).encode(), "application/json")
    notes: list[str] = []

    def publish(k: Work) -> None:
        k.published.append(job_id)
        if evidence_path and evidence_path not in k.evidence_files:
            k.evidence_files.append(evidence_path)
        if read is not None:
            from app.works import service as work_service  # the one place that resolves a specification

            for source in k.sources:
                bib = read["readings"].get(source.id)
                if bib:
                    source.bibliography = {key: bib.get(key) for key in ("title", "authors", "organisation", "year", "container", "doi") if bib.get(key)}
            k.requirements_path = requirements_path
            k.read_sources = [s.id for s in inp.sources]
            work_service.respec(ctx.rt, k)
        if planned is not None:
            plan = WorkPlan.model_validate(planned["plan"])
            if k.plan_version == inp.plan_version:
                k.plan, k.plan_status, k.plan_version = plan, "DRAFT", k.plan_version + 1
                k.candidate_plan = None
            else:
                k.candidate_plan = plan
                notes.append("You edited your plan while PaperAid was drafting one, so the new plan is kept alongside yours for you to compare.")
            if "results" in planned:
                if k.results_version == inp.results_version:
                    k.results, k.results_status, k.results_version = ResultsModel.model_validate(planned["results"]), "DRAFT", k.results_version + 1
                else:
                    notes.append("You edited your Results Model meanwhile, so PaperAid's suggestion was not applied.")
                if (k.budget is None or not k.budget.lines) and planned.get("budgetLines"):
                    k.budget = Budget(currency=(_spec(inp).currency or "USD")[:8], lines=[BudgetLine.model_validate(li) for li in planned["budgetLines"]])
                    k.budget_version += 1
        if document is not None:
            version = len(k.documents) + 1
            k.documents.append(StoredDocVersion(version=version, job_id=job_id, words=document.words, status=document.status, path=doc_path,
                                                note=(inp.note or ("Your requested changes" if inp.step == "REVISE" else ""))[:300]))
            if inp.step == "REVISE" and k.current != inp.base_version:
                notes.append("You chose another version while PaperAid was revising, so the revision is saved without replacing your choice.")
            else:
                k.current = version
            for request in k.requests:
                # Applied only when every section it asked about was revised; a request on the whole
                # document asked about every section this step targeted.
                asked = [s for s in (request.sections or list(inp.revise)) if s in inp.revise]
                if request.id in inp.request_ids and request.status == "OPEN" and asked and all(s in document.revised for s in asked):
                    request.status, request.applied_in = "APPLIED", version
        k.updated_at = utcnow()

    gone = False

    def finish(j: Job, w: Wallet, k: Work | None) -> tuple[Job, Wallet, Work] | None:
        """Publish, complete and settle as one unit (Codex audit 2026-09-30 #1): a published result is
        never refunded by a later failure or by an older release taking over, and a refunded step is
        never published."""
        nonlocal gone
        notes.clear()  # the transaction may run more than once
        gone = k is None or k.deleting
        if k is None or k.deleting:
            return None
        if j.status != JobStatus.PROCESSING or j.stage != Stage.EXPORTING:
            return None  # failed, cancelled or already completed meanwhile: nothing more to do
        if job_id not in k.published:
            publish(k)
        j = _warn(j, notes)
        j.outcome = j.outcome or "FULL"
        if Stage.EXPORTING not in j.completed_stages:
            j.completed_stages.append(Stage.EXPORTING)
        j.attempts, j.lease_until, j.stage = 0, None, None
        state.transition(j, JobStatus.COMPLETED, "Completed with warnings" if j.outcome == "PARTIAL" else "Completed")
        settle_completed(j, w)
        return j, w, k

    ctx.rt.store.update_job_wallet_and_work(job_id, inp.work_id, finish)
    if gone:
        raise PermanentStageError("WORK_DELETED", "This work was deleted before the step finished, so nothing was charged.", "work deleting at export")


def _warn(j: Job, warnings: list[str]) -> Job:
    j.warnings = list(dict.fromkeys(j.warnings + [w for w in warnings if w]))
    return j


STAGES = {
    Stage.ANALYSING: stage_analysing,
    Stage.RESEARCHING: stage_researching,
    Stage.PLANNING: stage_planning,
    Stage.DRAFTING: stage_drafting,
    Stage.AUDITING: stage_auditing,
    Stage.EXPORTING: stage_exporting,
}

