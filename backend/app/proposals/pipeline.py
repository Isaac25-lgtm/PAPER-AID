"""The worker stages of proposal steps. A step is an ordinary job (claim lease → run stage → save
artifact → next stage), so retries, the response cache, the spend ceiling and billing all come
from app.jobs.pipeline. What is particular to proposals lives here:

  plan step:    RESEARCHING → PLANNING → EXPORTING
  chapter step: RESEARCHING → PLANNING → DRAFTING → AUDITING → EXPORTING
  review:       EXTRACTING (shared) → ANALYSING → EXPORTING  (app.proposals.review)

Every step reads the input frozen when it was priced (`proposal_input.json`), never the live
project, and publishes to the project only at EXPORTING, in one transaction."""

import hashlib
import json
import re
from typing import TYPE_CHECKING, Any

from pydantic import ValidationError

from app.analysis import fetch, research
from app.core.errors import PermanentStageError
from app.jobs.models import Job, ReadinessItem, Stage, utcnow
from app.proposals import decisions, evidence, rulebook, sampling
from app.proposals.ai import Grade, ProposalRunner, SectionText, Table
from app.proposals.models import (
    ChapterDocument,
    ChapterSection,
    EvidenceItem,
    EvidenceSource,
    Project,
    ProposalPlan,
    StepInput,
    StoredChapterVersion,
)

if TYPE_CHECKING:
    from app.jobs.pipeline import StageContext

INPUT = "proposal_input.json"
YEAR = re.compile(r"\b(?:19|20)\d{2}\b")  # "8 December 2025" gives 2025
LITERATURE_YEARS = 15  # scholarly search window; foundational theory comes through the web search
NOT_REVIEWED = "The section was not reviewed."
TENSE_SECTIONS = {1: {"purpose", "objectives", "questions", "scope", "synopsis"}, 4: {"purpose", "objectives", "questions", "scope", "methodology"}}  # chapter 3: every section


def step_input(ctx: "StageContext") -> StepInput:
    return StepInput.model_validate(ctx.get_json(INPUT))


def load_library(files, paths: list[str]) -> dict[str, EvidenceItem]:
    items: list[EvidenceItem] = []
    for path in paths:
        if files.exists(path):
            items += [EvidenceItem.model_validate(i) for i in json.loads(files.get(path))]
    return {i.id: i for i in evidence.dedupe(items)}


def _label(item: EvidenceItem) -> str:
    return f"{evidence.author_label(item.source)}, {item.source.year or 'n.d.'}"


def _for_model(items: list[EvidenceItem], passages: bool = False) -> list[dict[str, str]]:
    out = []
    for i in items:
        entry = {"id": i.id, "statement": i.statement, "scope": i.scope, "source": _label(i)}
        if passages:
            entry["sourceWords"] = i.passage
        out.append(entry)
    return out


def _study(inp: StepInput) -> dict[str, Any]:
    return inp.inputs.model_dump(by_alias=True)


def _plan(inp: StepInput) -> dict[str, Any]:
    assert inp.plan is not None
    return inp.plan.model_dump(by_alias=True)


def _allowed_text(inp: StepInput, extra: str = "") -> str:
    """Everything the student supplied or approved: figures in it need no source."""
    return json.dumps(_study(inp)) + " " + (json.dumps(_plan(inp)) if inp.plan else "") + " " + extra


# --- RESEARCHING --------------------------------------------------------------------------------


def stage_researching(ctx: "StageContext") -> None:
    """Plan the research needs, then answer each from scholarly abstracts (OpenAlex) or live web
    search; PaperAid confirms every quoted passage itself and the writer checks each finding."""
    inp, settings = step_input(ctx), ctx.rt.settings
    runner = ctx.ai(ProposalRunner)
    assert isinstance(runner, ProposalRunner)
    library = load_library(ctx.rt.files, inp.evidence_files)
    limit = settings.proposal_needs.get(inp.chapter, 6)
    sections = rulebook.sections(inp.rulebook, inp.chapter, inp.inputs.level, inp.plan) if inp.plan and inp.chapter else []
    payload = {
        "study": _study(inp),
        "plan": _plan(inp) if inp.plan else None,
        "part": "plan" if inp.step == "PLAN" else inp.chapter,
        "sections": [{"key": s.key, "heading": s.heading, "requirement": s.brief} for s in sections],
        "library": [{"id": i.id, "statement": i.statement} for i in library.values() if i.usable][:80],
        "limit": limit,
        "note": inp.note,
    }
    private = {w.lower() for w in inp.private}

    def safe(query: str) -> bool:
        return research.query_safe(query, set(), private)

    found: list[EvidenceItem] = []
    today = utcnow().date().isoformat()
    for need in [n for n in runner.research_needs(payload) if safe(n.query)][:limit]:
        items: list[EvidenceItem] = []
        if need.kind == "LITERATURE":
            items = _from_literature(runner, need.need, need.query, inp.chapter, today, settings.proposal_works_per_need)
        if not items and not runner.budget_reached:
            items = _from_web(runner, need.need, need.query, inp.chapter, today, settings.research_max_searches, safe)
        found += items
        if runner.budget_reached:
            break
    found = evidence.dedupe(found)
    checked = [i for i in found if i.verified]
    verdicts = runner.verify_claims(
        [{"id": i.id, "claim": i.statement, "context": i.need, "sources": [{"title": i.source.title, "published": i.source.year, "access": i.access, "passage": i.passage, "scope": i.scope}]} for i in checked]
    ) if checked else {}
    for item in checked:
        verdict = verdicts.get(item.id)
        item.support = verdict.support if verdict else "NOT_FOUND"  # an unchecked finding is never usable
    ctx.put_json("evidence.json", [i.model_dump(by_alias=True) for i in found])
    if runner.budget_reached:
        ctx.update(lambda j: _warn(j, ["The research reached this step's spending limit, so fewer sources were gathered than planned."], partial=True))


def _from_literature(runner: ProposalRunner, need: str, query: str, chapter: int, today: str, limit: int) -> list[EvidenceItem]:
    works = fetch.openalex_search(query, utcnow().year - LITERATURE_YEARS, limit)
    if not works:
        return []
    listed = [{"id": f"w{n}", "title": w["title"], "year": w["year"], "abstract": w["abstract"][:3000]} for n, w in enumerate(works, start=1)]
    by_id = {f"w{n}": w for n, w in enumerate(works, start=1)}
    items = []
    for finding in runner.extract(need, listed):
        work = by_id[finding.work]
        source = _scholarly_source(work)
        items.append(
            EvidenceItem(
                id=evidence.evidence_id(source.doi or source.url, finding.passage),
                chapter=chapter,
                need=need,
                statement=finding.statement.strip(),
                passage=finding.passage.strip(),
                scope=finding.scope.strip(),
                access="ABSTRACT",
                verified=research.quote_found(finding.passage, work["abstract"]),
                source=source,
                retrieved_on=today,
            )
        )
    return items


def _authors(value: str) -> list[str]:
    return [a.strip() for a in value.split(";") if a.strip()]


def _scholarly_source(work: dict[str, str]) -> EvidenceSource:
    """Registered details from Crossref when the work has a DOI, else OpenAlex's record."""
    record = fetch.crossref_work(work["doi"]) if work.get("doi") else None
    data, origin = (record, "CROSSREF") if record and record.get("title") else (work, "OPENALEX")
    return EvidenceSource(
        url=work["url"],
        title=data["title"],
        authors=_authors(data.get("authors", "")),
        year=data.get("year", ""),
        container=data.get("container", ""),
        volume=data.get("volume", ""),
        issue=data.get("issue", ""),
        pages=data.get("pages", ""),
        doi=work.get("doi", ""),
        kind="ARTICLE" if "article" in (data.get("type") or "") or data.get("container") else "REPORT",
        metadata=origin,  # type: ignore[arg-type]
    )


def _from_web(runner: ProposalRunner, need: str, query: str, chapter: int, today: str, searches: int, safe) -> list[EvidenceItem]:
    items = []
    for finding in runner.search(need, query, searches, safe):
        page = fetch.page_text(finding.url)
        verified = page is not None and research.quote_found(finding.passage, page)
        access = finding.access
        if not verified:
            abstract = fetch.abstract_text(finding.url)
            if abstract is not None and research.quote_found(finding.passage, abstract):
                verified, access = True, "ABSTRACT"
        doi = fetch.resolve_doi(finding.url)
        record = fetch.crossref_work(doi) if doi else None
        if record and record.get("title"):
            source = EvidenceSource(
                url=finding.url, title=record["title"], authors=_authors(record["authors"]), year=record["year"], container=record["container"],
                volume=record["volume"], issue=record["issue"], pages=record["pages"], doi=doi, kind="ARTICLE", metadata="CROSSREF",
            )
        else:
            year = YEAR.search(finding.published)
            source = EvidenceSource(
                url=finding.url, title=finding.title.strip(), organisation=finding.publisher.strip(), year=year.group(0) if year else "",
                container=finding.publisher.strip(), kind="REPORT", metadata="PAGE",
            )
        items.append(
            EvidenceItem(
                id=evidence.evidence_id(source.doi or source.url, finding.passage),
                chapter=chapter,
                need=need,
                statement=finding.statement.strip(),
                passage=finding.passage.strip(),
                scope=finding.scope.strip(),
                access=access,
                verified=verified,
                source=source,
                retrieved_on=today,
            )
        )
    return items


def _library(ctx: "StageContext", inp: StepInput) -> dict[str, EvidenceItem]:
    """The project's library at pricing time plus what this step gathered."""
    library = load_library(ctx.rt.files, inp.evidence_files)
    new = [EvidenceItem.model_validate(i) for i in ctx.get_json("evidence.json")] if ctx.has("evidence.json") else []
    return {i.id: i for i in evidence.dedupe([*library.values(), *new])}


# --- PLANNING -------------------------------------------------------------------------------------


def stage_planning(ctx: "StageContext") -> None:
    inp = step_input(ctx)
    runner = ctx.ai(ProposalRunner)
    assert isinstance(runner, ProposalRunner)
    usable = [i for i in _library(ctx, inp).values() if i.usable]
    rules = rulebook.rules_for(inp.rulebook)
    if inp.step == "PLAN":
        payload = {"study": _study(inp), "level": inp.inputs.level, "rules": rules, "evidence": _for_model(usable), "note": inp.note}
        final, draft, critique = runner.negotiate("plan", payload)
        plan = _confirmed_gap(_student_figures_only(_plan_from_model(final), inp), {i.id for i in usable})
        ctx.put_json("plan.json", {"plan": plan.model_dump(by_alias=True), "draft": draft, "critique": critique.model_dump()})
        return
    assert inp.plan is not None
    sections = rulebook.sections(inp.rulebook, inp.chapter, inp.inputs.level, inp.plan)
    sample = sampling.calculate(inp.plan.sample_size) if inp.chapter == 3 else None
    payload = {
        "plan": _plan(inp),
        "chapter": inp.chapter,
        "sections": [{"key": s.key, "number": s.number, "heading": s.heading, "requirement": s.brief, "words": s.words, "table": s.table} for s in sections],
        "rules": rules,
        "evidence": _for_model(usable),
        "sampleSize": sample.steps if sample else "",
        "note": inp.note,
    }
    final, draft, critique = runner.negotiate("briefs", payload)
    ids = {i.id for i in usable}
    briefs = {b["key"]: {"points": [p for p in b.get("points", []) if p.strip()], "evidence": [e for e in b.get("evidence", []) if e in ids]} for b in final.get("sections", [])}
    ctx.put_json("briefs.json", {"briefs": briefs, "draft": draft, "critique": critique.model_dump()})


def _plan_from_model(data: dict[str, Any]) -> ProposalPlan:
    """The model's plan as a ProposalPlan. The schema has no length limits (providers cannot
    enforce them), so an over-long field is shortened to the plan's limit rather than failing the
    step; anything else invalid fails it once, since a retry would replay the same saved answer."""
    for _ in range(3):
        try:
            return ProposalPlan.model_validate(data)
        except ValidationError as exc:
            errors = exc.errors()
            if any(e["type"] != "string_too_long" for e in errors):
                raise PermanentStageError("PLAN_INVALID", "PaperAid could not build a usable plan this time. Nothing was charged; please try again.", f"plan invalid: {errors[0]['type']}") from exc
            for error in errors:
                *path, last = error["loc"]
                target: Any = data
                for key in path:
                    target = target[key]
                limit = error["ctx"]["max_length"]
                target[last] = target[last][: limit - 1].rsplit(" ", 1)[0] + "…"
    return ProposalPlan.model_validate(data)


def _confirmed_gap(plan: ProposalPlan, usable: set[str]) -> ProposalPlan:
    """The research gap rests only on confirmed evidence: any other id is removed."""
    gap = plan.research_gap
    kept = [e for e in dict.fromkeys(gap.evidence) if e in usable]
    return plan if kept == gap.evidence else plan.model_copy(update={"research_gap": gap.model_copy(update={"evidence": kept})})


def _student_figures_only(plan: ProposalPlan, inp: StepInput) -> ProposalPlan:
    """A population size or stated sample is kept only when it is exactly the figure the student
    entered for it (Codex audit 2026-09-28 #13: a number anywhere in the notes, such as the year
    2026, used to count). Otherwise it is removed and asked for."""
    student = inp.inputs
    size = plan.sample_size
    asks = list(plan.questions_for_student)
    if size.population is not None and size.population != student.population_size:
        size = size.model_copy(update={"population": None, "population_source": ""})
        asks.append("How many people are in the accessible population, and where does that figure come from?")
    elif size.population is not None:
        size = size.model_copy(update={"population_source": student.population_source or size.population_source})
    if size.stated is not None and size.stated != student.expected_participants:
        size = size.model_copy(update={"stated": None})
        asks.append("How many participants do you expect to include, and why is that enough?")
    return plan.model_copy(update={"sample_size": size, "questions_for_student": list(dict.fromkeys(asks))})


# --- DRAFTING ------------------------------------------------------------------------------------


def _common(inp: StepInput, sample_steps: str) -> dict[str, Any]:
    assert inp.plan is not None
    spec = rulebook.chapter_spec(inp.rulebook, inp.chapter)
    return {
        "plan": _plan(inp),
        "level": inp.inputs.level,
        "rules": rulebook.rules_for(inp.rulebook),
        "chapter": {"number": inp.chapter, "title": spec["title"], "purpose": spec["purpose"]},
        "sampleSize": sample_steps,
        "note": inp.note,
    }


def _section_items(inp: StepInput, library: dict[str, EvidenceItem], briefs: dict[str, Any]) -> list[dict[str, Any]]:
    assert inp.plan is not None
    items = []
    for s in rulebook.sections(inp.rulebook, inp.chapter, inp.inputs.level, inp.plan):
        brief = briefs.get(s.key, {"points": [], "evidence": []})
        assigned = [library[i] for i in brief["evidence"] if i in library and library[i].usable]
        items.append(
            {
                "key": s.key, "number": s.number, "heading": s.heading, "requirement": s.brief, "words": s.words, "table": s.table,
                "objective": s.objective, "points": brief["points"], "evidence": _for_model(assigned, passages=True),
                "_words": " ".join(["w"] * s.words),  # batches are sized by the words each section will produce
            }
        )
    return items


def stage_drafting(ctx: "StageContext") -> None:
    inp = step_input(ctx)
    assert inp.plan is not None
    runner = ctx.ai(ProposalRunner)
    assert isinstance(runner, ProposalRunner)
    library = _library(ctx, inp)
    sample = sampling.calculate(inp.plan.sample_size) if inp.chapter == 3 else None
    items = _section_items(inp, library, ctx.get_json("briefs.json")["briefs"])
    drafted = runner.draft(items, _common(inp, sample.steps if sample else ""))
    ctx.put_json("drafted.json", {k: v.model_dump() for k, v in drafted.items()})
    missing = [i["heading"] for i in items if i["key"] not in drafted]
    if missing:
        ctx.update(lambda j: _warn(j, [f"These sections could not be written within this step's limits: {', '.join(missing)}."], partial=True))


# --- AUDITING ------------------------------------------------------------------------------------


def _table_allowed(inp: StepInput, allowed: str) -> str:
    """A work-plan table may also number the months of the student's own timeline."""
    months = inp.plan.timeline_months if inp.plan else 0
    return allowed + " " + " ".join(str(m) for m in range(1, months + 1))


def _cells(text: SectionText) -> list[str]:
    return [text.table.caption, *[cell for row in text.table.rows for cell in row]]


def _checks(inp: StepInput, key: str, text: SectionText, library: dict[str, EvidenceItem], allowed: str) -> list[str]:
    """Every text the student will receive is checked: paragraphs, and a table's cells and caption
    (Codex audit 2026-09-28 #7), which are delivered and exported like prose."""
    usable = {i for i, item in library.items() if item.usable}
    problems: list[str] = []
    tense = inp.chapter == 3 or key in TENSE_SECTIONS.get(inp.chapter, set())
    for paragraph in text.paragraphs:
        problems += evidence.citation_problems(paragraph, usable)
        problems += evidence.figure_problems(paragraph, library, allowed)
        if tense:
            problems += evidence.tense_problems(paragraph)
    table_allowed = _table_allowed(inp, allowed)
    for cell in _cells(text):
        found = evidence.citation_problems(cell, usable) + evidence.figure_problems(cell, library, table_allowed)
        problems += [f"In the table: {p}" for p in found]
    if not any(p.strip() for p in text.paragraphs):
        problems.append("The section is empty.")
    return list(dict.fromkeys(problems))


def _strip_table(inp: StepInput, text: SectionText, library: dict[str, EvidenceItem], usable: set[str], allowed: str) -> Table:
    table_allowed = _table_allowed(inp, allowed)

    def clean(cell: str) -> str:
        return evidence.strip_unsupported(cell, library, usable, table_allowed)

    return Table(caption=clean(text.table.caption), rows=[[clean(c) for c in row] for row in text.table.rows])


def stage_auditing(ctx: "StageContext") -> None:
    """Code checks every section; the lead reviews with those results; the writer fixes what is
    raised; bounded rounds. Whatever still breaks a code rule afterwards is removed, never shipped."""
    inp = step_input(ctx)
    assert inp.plan is not None
    settings = ctx.rt.settings
    runner = ctx.ai(ProposalRunner)
    assert isinstance(runner, ProposalRunner)
    library = _library(ctx, inp)
    usable = {i for i, item in library.items() if item.usable}
    sample = sampling.calculate(inp.plan.sample_size) if inp.chapter == 3 else None
    allowed = _allowed_text(inp, sample.figures if sample else "")
    common = _common(inp, sample.steps if sample else "")
    vetting = rulebook.vetting(inp.rulebook, inp.chapter)
    warnings: list[str] = []
    base: ChapterDocument | None = None
    if inp.step == "REVISE":
        base, items, current = _revision(ctx, runner, inp, library, common)
    else:
        items = {i["key"]: i for i in _section_items(inp, library, ctx.get_json("briefs.json")["briefs"])}
        current = {k: SectionText.model_validate(v) for k, v in ctx.get_json("drafted.json").items()}
    unresolved: dict[str, list[str]] = {}
    grades: dict[str, Grade] = {}
    rounds = settings.repair_attempts
    # review, fix, review ... review: the delivered text is always the reviewed text, with at most
    # `rounds` fixes, as priced (Codex audit 2026-09-28 #11).
    for round_ in range(rounds + 1):
        problems = {k: _checks(inp, k, t, library, allowed) for k, t in current.items()}
        review = [
            {**items[k], "text": t.paragraphs, "table": t.table.model_dump(), "paperaidChecks": problems[k], "_words": " ".join(t.paragraphs)}
            for k, t in current.items()
        ]
        grades = runner.grade(review, {**common, "vetting": vetting})
        unresolved = {}
        for key in current:
            grade = grades.get(key)
            issues = [*problems[key], *(grade.issues if grade and grade.grade == "REPAIR" else [])]
            if grade is None:  # never silently passed, whether or not the budget ran out (#10)
                issues.append(NOT_REVIEWED)
            if issues:
                unresolved[key] = issues
        if not unresolved or runner.budget_reached or round_ == rounds:
            break
        fixes = [{**items[k], "text": current[k].paragraphs, "table": current[k].table.model_dump(), "issues": unresolved[k], "_words": " ".join(current[k].paragraphs)} for k in unresolved]
        for key, fixed in runner.fix(fixes, common).items():
            if key in unresolved:
                current[key] = fixed

    stripped = []
    for key, text in current.items():
        cleaned = [evidence.strip_unsupported(p, library, usable, allowed) for p in text.paragraphs]
        table = _strip_table(inp, text, library, usable, allowed)
        if cleaned != text.paragraphs or table != text.table:
            stripped.append(items[key]["heading"])
        current[key] = text.model_copy(update={"paragraphs": [p for p in cleaned if p], "table": table})
    if stripped:
        warnings.append(f"PaperAid removed sentences it could not trace to confirmed evidence or your plan in: {', '.join(stripped)}.")
    unreviewed = [f"{items[k]['number']} {items[k]['heading']}" for k in current if k not in grades]
    if unreviewed:
        warnings.append(f"PaperAid could not fully check these sections this time, so read them carefully: {', '.join(unreviewed)}.")
    concerns = []
    for key, issues in unresolved.items():
        raised = [i for i in issues if i != NOT_REVIEWED][:3]
        if raised:
            concerns.append(f"{items[key]['number']} {items[key]['heading']}: " + "; ".join(raised))
    if concerns:
        warnings.append("Some points still need your attention: " + " | ".join(concerns))
    for key, grade in grades.items():  # Codex audit #16: reviewer notes are delivered, never dropped
        if key in items and grade.grade == "PASS_WITH_WARNINGS" and grade.note.strip():
            warnings.append(f"Note on {items[key]['number']} {items[key]['heading']}: {grade.note.strip()}")

    document = _document(inp, current, items, library)
    if base is not None:
        document, kept = _merge(base, document, set(current))
        if kept:
            warnings.append(f"These sections could not be revised this time, so your earlier text is kept: {', '.join(kept)}.")
    document.readiness = _readiness(ctx, runner, inp, document, library, bool(stripped), unreviewed)
    document.warnings = warnings
    ctx.put_json("chapter.json", document.model_dump(by_alias=True))
    if warnings:
        ctx.update(lambda j: _warn(j, warnings, partial=bool(unresolved or stripped or unreviewed)))


def _revision(
    ctx: "StageContext", runner: ProposalRunner, inp: StepInput, library: dict[str, EvidenceItem], common: dict[str, Any]
) -> tuple[ChapterDocument, dict[str, dict[str, Any]], dict[str, SectionText]]:
    """A chapter revised from supervisor comments: the sections they concern, from the current
    version, with the comments as what the writer must fix (the revision is the rewrite; the usual
    review and at most two fixes follow). The comments are also points the reviewer checks."""
    base = ChapterDocument.model_validate_json(ctx.rt.files.get(inp.base))
    items = {i["key"]: i for i in _section_items(inp, library, {})}
    current: dict[str, SectionText] = {}
    for s in base.sections:
        if s.key in inp.revise and s.key in items:
            current[s.key] = SectionText(key=s.key, paragraphs=s.paragraphs, table=Table(caption=s.table_caption, rows=s.table or []))
            asked = [f"Your supervisor asked: {c}" for c in inp.revise[s.key]]
            cited = [library[i] for i in evidence.cited_ids(" ".join(s.paragraphs)) if i in library and library[i].usable]
            items[s.key] = {**items[s.key], "points": asked, "evidence": _for_model(cited, passages=True) or items[s.key]["evidence"]}
    if not current:
        raise PermanentStageError("NOTHING_TO_REVISE", "The sections your comments are on are no longer in this chapter. Nothing was charged.", "revise: no sections")
    first = [
        {**items[k], "text": t.paragraphs, "table": t.table.model_dump(), "issues": inp.revise[k], "_words": " ".join(t.paragraphs)}
        for k, t in current.items()
    ]
    for key, fixed in runner.fix(first, common).items():
        if key in current:
            current[key] = fixed
    return base, {k: v for k, v in items.items() if k in current}, current


def _merge(base: ChapterDocument, revised: ChapterDocument, keys: set[str]) -> tuple[ChapterDocument, list[str]]:
    """The revised sections in place of their earlier text; every other section unchanged. A
    section that came back empty keeps its earlier text (and is named)."""
    fresh = {s.key: s for s in revised.sections}
    sections = [fresh.get(s.key, s) for s in base.sections]
    cited: list[str] = []
    for section in sections:
        for field in [*section.paragraphs, section.table_caption, *[c for row in section.table or [] for c in row]]:
            cited += [i for i in evidence.cited_ids(field) if i not in cited]
    words = sum(len(evidence.ANY_TOKEN.sub(" ", p).split()) for s in sections for p in s.paragraphs)
    merged = ChapterDocument(number=base.number, title=base.title, plan_version=revised.plan_version, sections=sections, cited=cited, words=words)
    return merged, [f"{s.number} {s.heading}" for s in base.sections if s.key in keys and s.key not in fresh]


def _document(inp: StepInput, current: dict[str, SectionText], items: dict[str, dict[str, Any]], library: dict[str, EvidenceItem]) -> ChapterDocument:
    assert inp.plan is not None
    sections: list[ChapterSection] = []
    cited: list[str] = []
    for key, item in items.items():
        text = current.get(key)
        if text is None or not text.paragraphs:
            continue
        table = _table(text.table) if item["table"] else None
        for field in [*text.paragraphs, *(_cells(text) if table else [])]:
            cited += [i for i in evidence.cited_ids(field) if i not in cited]
        sections.append(
            ChapterSection(
                key=key, number=item["number"], heading=item["heading"], paragraphs=text.paragraphs, table=table,
                table_caption=text.table.caption if table else "", depends=decisions.stamp(inp.chapter, key, inp.plan),
            )
        )
    words = sum(len(evidence.ANY_TOKEN.sub(" ", p).split()) for s in sections for p in s.paragraphs)
    spec = rulebook.chapter_spec(inp.rulebook, inp.chapter)
    return ChapterDocument(number=inp.chapter, title=spec["title"], plan_version=inp.plan_version, sections=sections, cited=cited, words=words)


def _table(table: Table) -> list[list[str]] | None:
    rows = [[c.strip() for c in r] for r in table.rows if any(c.strip() for c in r)]
    width = len(rows[0]) if rows else 0
    return [r[:width] + [""] * (width - len(r)) for r in rows] if len(rows) >= 2 and width >= 2 else None


def _readiness(
    ctx: "StageContext", runner: ProposalRunner, inp: StepInput, document: ChapterDocument, library: dict[str, EvidenceItem], stripped: bool, unreviewed: list[str]
) -> list[ReadinessItem]:
    assert inp.plan is not None
    n = inp.chapter
    questions = [q for q in rulebook.vetting(inp.rulebook, n) if not q.get("deterministic")]
    others = {}
    for number, path in inp.chapters.items():
        if number != n and ctx.rt.files.exists(path):
            other = ChapterDocument.model_validate_json(ctx.rt.files.get(path))
            others[str(number)] = [{"heading": s.heading, "text": " ".join(s.paragraphs)[:2500]} for s in other.sections]
    sources = {library[i].source.doi or research.normalise_url(library[i].source.url) for i in document.cited if i in library}
    payload = {
        "plan": _plan(inp),
        "chapter": n,
        "sections": [{"heading": f"{s.number} {s.heading}", "text": s.paragraphs} for s in document.sections],
        "questions": [{"id": q["id"], "question": q["question"]} for q in questions],
        "otherChapters": others,
        "facts": {"distinctSourcesCited": len(sources), "words": document.words},
    }
    try:
        judged = runner.readiness(payload)
    except PermanentStageError as exc:
        if exc.code != "BUDGET_EXCEEDED":
            raise
        judged = None
    items: list[ReadinessItem] = []
    known = {q["id"]: q["question"] for q in questions}
    answered = {j.id: j for j in (judged.items if judged else []) if j.id in known}
    for qid, question in known.items():
        j = answered.get(qid)
        items.append(
            ReadinessItem(id=qid, question=question, status=j.status if j else "NEEDS_REVIEW", basis="AI", note=j.note if j else "Not assessed within this step's limits.", where=j.where if j else "", chapter=n)
        )
    for k, j in enumerate(judged.consistency if judged else [], start=1):
        items.append(ReadinessItem(id=f"C{n}-K{k}", question=j.question or "Consistency with the other chapters", status="NEEDS_REVIEW", basis="AI", note=j.note, where=j.where, chapter=n))
    items.append(
        ReadinessItem(
            id=f"C{n}-TRACE", question="Every citation and figure traces to confirmed evidence or your approved plan", basis="CODE", chapter=n,
            status="NEEDS_REVIEW" if stripped else "PASS",
            note="Untraceable sentences were removed; check that the sections still read well." if stripped else "Checked by PaperAid on every sentence.",
        )
    )
    items.append(
        ReadinessItem(
            id=f"C{n}-REVIEWED", question="Every section was reviewed after its last change", basis="CODE", chapter=n,
            status="NEEDS_REVIEW" if unreviewed else "PASS",
            note=f"Not reviewed: {', '.join(unreviewed)}." if unreviewed else "Each section's final text was reviewed.",
        )
    )
    if n == 2:
        count = len(sources)
        items.append(
            ReadinessItem(
                id="C2-REFS30", question="Are there a minimum of 30 quality references?", basis="CODE", chapter=2, status="PASS" if count >= 30 else "NEEDS_REVIEW",
                note=f"{count} distinct confirmed sources cited in this chapter. Many programmes expect at least 30; check yours.",
            )
        )
    if n == 4:  # the manual's limits for a concept paper (§1.4)
        pages = document.words / 250
        items.append(
            ReadinessItem(
                id="C4-LENGTH", question="Is the concept paper at most five pages?", basis="CODE", chapter=4, status="PASS" if pages <= 5 else "NEEDS_REVIEW",
                note=f"About {pages:.1f} pages at double spacing.",
            )
        )
        count = len(sources)
        items.append(
            ReadinessItem(
                id="C4-REFS", question="Does it cite five to eight sources?", basis="CODE", chapter=4, status="PASS" if 5 <= count <= 8 else "NEEDS_REVIEW",
                note=f"{count} confirmed sources cited; the annotated list is built from them.",
            )
        )
    if n == 3:
        size = inp.plan.sample_size
        result = sampling.calculate(size)
        if result.size is not None:
            has_source = bool(size.population_source.strip()) or size.method in ("SATURATION", "AUTHOR_STATED")
            items.append(
                ReadinessItem(
                    id="C3-FIGURES", question="The sample size comes from your own figures", basis="AUTHOR", chapter=3, status="PASS" if has_source else "NEEDS_REVIEW",
                    note=result.steps if has_source else "Add where your population figure comes from (for example district records) in the plan.",
                )
            )
    return items


# --- EXPORTING ------------------------------------------------------------------------------------


def stage_exporting(ctx: "StageContext") -> None:
    """Publish the result to the project in one transaction. Files are written first under paths
    unique to this job, so a retry rewrites the same files and the record gains them only once."""
    inp = step_input(ctx)
    project = ctx.rt.store.get_project(inp.project_id)
    if project is None or project.deleting:
        raise PermanentStageError("PROJECT_DELETED", "This proposal was deleted before the step finished, so nothing was charged.", "project gone at export")
    job_id = ctx.job.id
    evidence_path = ""
    if ctx.has("evidence.json"):
        evidence_path = f"{project.storage_prefix()}/evidence/{job_id}.json"
        ctx.rt.files.put(evidence_path, ctx.get_bytes("evidence.json"), "application/json")
    chapter_path = ""
    document: ChapterDocument | None = None
    if inp.step in ("CHAPTER", "REVISE"):
        document = ChapterDocument.model_validate(ctx.get_json("chapter.json"))
        chapter_path = f"{project.storage_prefix()}/chapters/{inp.chapter}/{job_id}.json"
        ctx.rt.files.put(chapter_path, document.model_dump_json(by_alias=True).encode(), "application/json")
    plan = ProposalPlan.model_validate(ctx.get_json("plan.json")["plan"]) if inp.step == "PLAN" else None
    library_paths = list(dict.fromkeys([*project.evidence_files, *([evidence_path] if evidence_path else [])]))
    usable = sum(1 for i in load_library(ctx.rt.files, library_paths).values() if i.usable)
    candidate = False

    def publish(p: Project) -> Project | None:
        nonlocal candidate
        if p.deleting:
            return None
        if job_id in p.published:  # a retry after this job's transaction already committed
            return p
        p.published.append(job_id)
        if evidence_path and evidence_path not in p.evidence_files:
            p.evidence_files.append(evidence_path)
        p.evidence_count = usable
        if plan is not None:
            if p.plan_version == inp.plan_version:
                p.plan, p.plan_status, p.plan_version = plan, "DRAFT", p.plan_version + 1
                p.candidate_plan = None
            else:  # the student edited their plan meanwhile: never overwrite it
                p.candidate_plan, candidate = plan, True
        if document is not None:
            state = p.chapter(inp.chapter)
            version = len(state.versions) + 1
            state.versions.append(
                StoredChapterVersion(
                    version=version, job_id=job_id, words=document.words, plan_version=inp.plan_version, path=chapter_path,
                    note=(inp.note or ("Revised from your supervisor's comments" if inp.step == "REVISE" else ""))[:300],
                    passed=sum(1 for r in document.readiness if r.status in ("PASS", "NOT_APPLICABLE")), total=len(document.readiness),
                )
            )
            state.current, state.approved = version, False
            for comment in p.feedback:
                if comment.id in inp.comment_ids and comment.status == "OPEN":
                    comment.status, comment.applied_in = "APPLIED", version
        p.updated_at = utcnow()
        return p

    if ctx.rt.store.update_project(inp.project_id, publish) is None:
        raise PermanentStageError("PROJECT_DELETED", "This proposal was deleted before the step finished, so nothing was charged.", "project deleting at export")
    notes = ["You edited your plan while PaperAid was drafting one, so the new plan is kept alongside yours for you to compare."] if candidate else []

    def done(j: Job) -> Job:
        j = _warn(j, notes, partial=False)
        j.outcome = j.outcome or "FULL"
        return j

    ctx.update(done)


def _warn(j: Job, warnings: list[str], partial: bool) -> Job:
    j.warnings = list(dict.fromkeys(j.warnings + warnings))
    if partial:
        j.outcome = "PARTIAL"
    return j


def input_sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


STAGES = {
    Stage.RESEARCHING: stage_researching,
    Stage.PLANNING: stage_planning,
    Stage.DRAFTING: stage_drafting,
    Stage.AUDITING: stage_auditing,
    Stage.EXPORTING: stage_exporting,
}
