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
from collections.abc import Callable, Iterable, Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import TYPE_CHECKING, Any

from pydantic import ValidationError

from app.ai.orchestration import REVIEW_REPAIRS
from app.analysis import fetch, research
from app.core.errors import CapacityWait, PermanentStageError, RetryableStageError
from app.jobs import state
from app.jobs.models import Approval, Job, JobStatus, ReadinessItem, Stage, TopicRoute, Wallet, utcnow
from app.pricing.billing import settle_completed
from app.pricing.quote import round_up
from app.proposals import decisions, evidence, profile, rulebook, sampling
from app.proposals.ai import LOST_SEARCH, Correction, Grade, ProposalRunner, SectionText, Table
from app.proposals.models import (
    ChapterDocument,
    ChapterSection,
    EvidenceItem,
    EvidenceSource,
    Level,
    PlanReview,
    Project,
    ProposalPlan,
    StepInput,
    StoredChapterVersion,
    moved_path,
)
from app.proposals.structure import structure_current

if TYPE_CHECKING:
    from app.jobs.pipeline import StageContext

INPUT = "proposal_input.json"
YEAR = re.compile(r"\b(?:19|20)\d{2}\b")  # "8 December 2025" gives 2025
LITERATURE_YEARS = 15  # scholarly search window for studies (workflow 1: foundational theory comes through the web search)
NOT_REVIEWED = "The section was not reviewed."
TENSE_SECTIONS = {1: {"purpose", "objectives", "questions", "scope", "synopsis"}, 4: {"purpose", "objectives", "questions", "scope", "methodology"}}  # chapter 3: every section


def step_input(ctx: "StageContext") -> StepInput:
    return StepInput.model_validate(ctx.get_json(INPUT))


def _runner(ctx: "StageContext", inp: StepInput) -> ProposalRunner:
    runner = ctx.ai(ProposalRunner)
    assert isinstance(runner, ProposalRunner)
    if runner._engine.editor and inp.step in ("CHAPTER", "COMPLETE", "REVISE") and inp.plan is not None:
        # A chapter's final review is paid for before research or drafting may spend its share (every stage of the step).
        written = [s for s in rulebook.sections(inp.rulebook, inp.chapter, inp.inputs.level, inp.plan) if not inp.only or s.key in inp.only]
        runner.keep_for_editor(8 * sum(s.words for s in written), "p")
    return runner


def load_library(files, paths: list[str]) -> dict[str, EvidenceItem]:
    items: list[EvidenceItem] = []
    for path in paths:
        found = path if files.exists(path) else moved_path(path)  # a step priced before its project was migrated
        if files.exists(found):
            items += [EvidenceItem.model_validate(i) for i in json.loads(files.get(found))]
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
    """Everything the student supplied or approved: figures in it need no source. Written unescaped:
    JSON's default escaping wrote the dash in "6–24" as a code that hid the 24 from the figure check,
    so every sentence about children aged 6–24 months was refused (live, 2026-10-01)."""
    return json.dumps(_study(inp), ensure_ascii=False) + " " + (json.dumps(_plan(inp), ensure_ascii=False) if inp.plan else "") + " " + extra


# --- RESEARCHING --------------------------------------------------------------------------------


def stage_researching(ctx: "StageContext") -> None:
    """Plan the research needs, then answer each from scholarly abstracts (OpenAlex) or live web
    search; PaperAid confirms every quoted passage itself and the writer checks each finding."""
    inp, settings = step_input(ctx), ctx.rt.settings
    runner = _runner(ctx, inp)
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

    today = utcnow().date().isoformat()

    needs, covered, left = topics_to_search([n for n in runner.research_needs(payload) if safe(n.query)], library, limit, runner)
    routes = {_topic(n): TopicRoute(category=n.category or n.kind, essential=n.essential) for n in needs}

    def answer(need, other: bool = False) -> list[EvidenceItem]:
        route = routes[_topic(need)]
        return checkpointed(ctx, runner, need, lambda: gather(runner, need, settings, inp.chapter, today, safe, route, other=other), route,
                            part="other" if other else "")

    def check(items: list[EvidenceItem]) -> None:
        checked = [i for i in items if i.verified]
        verdicts = runner.verify_claims(
            [{"id": i.id, "claim": i.statement, "context": i.need, "sources": [{"title": i.source.title, "published": i.source.year, "access": i.access, "passage": i.passage, "scope": i.scope}]} for i in checked]
        ) if checked else {}
        for item in checked:
            verdict = verdicts.get(item.id)
            item.support = verdict.support if verdict else "NOT_FOUND"  # an unchecked finding is never usable

    gathered = research_topics(ctx, needs, answer, settings.research_parallel)
    found = evidence.dedupe(gathered)
    check(found)
    gathered, found = other_route(ctx, runner, needs, routes, gathered, found, lambda need: answer(need, other=True), check, settings.research_parallel)
    unsearched = research_gaps(ctx, needs)
    ctx.put_json("evidence.json", [i.model_dump(by_alias=True) for i in found])
    record_topics(ctx, needs, covered, routes, left)
    essential_answered(runner, needs, gathered, found, left)
    if runner.budget_reached:
        ctx.update(lambda j: _warn(j, ["The research reached this step's spending limit, so fewer sources were gathered than planned."], partial=True))
    if unsearched:
        ctx.update(lambda j: _warn(j, [unsearched], partial=False))


# --- how a topic is answered (algorithm revision 2026-10-09) ------------------------------------------
INDEX_FAILED = frozenset({"RATE_LIMITED", "ALLOWANCE_USED", "UNAVAILABLE", "ACCESS_DENIED", "INVALID"})  # could not be asked: not "nothing found"
SCHOLARLY = frozenset({"STUDY", "METHOD"})


def topics_to_search(asked: list, library: dict[str, EvidenceItem], limit: int, runner) -> tuple[list, list, list]:
    """(the needs to search, the needs saved evidence already answers, the needs left unsearched). Workflow 1: the
    first `limit`, none covered, none recorded as left (as priced).

    Workflow 2 (Codex audit of fd74ff3, finding 5). A need is covered only when every piece of evidence it names is in
    the library and usable AND at least one of them can be about it (`research.about`): the planner's word alone is
    not coverage. Of the others, what the work depends on is never the part cut off: every essential need is searched
    (up to twice the allowance), optional ones fill what is left of `limit`, and the rest are returned as left, so an
    essential need beyond that is reported as unanswered, never forgotten. The planner's order is kept."""
    if runner._engine.workflow < 2:
        return asked[:limit], [], []
    usable = {i.id: i for i in library.values() if i.usable}

    def answered(need) -> bool:
        named = [usable[e] for e in need.covered_by if e in usable]
        return bool(need.covered_by) and len(named) == len(need.covered_by) and any(
            research.about(need.need, need.query, " ".join([i.statement, i.scope, i.need, i.source.title])) for i in named)

    covered = [n for n in asked if answered(n)]
    rest = [n for n in asked if not any(n is c for c in covered)]
    room = max(limit, min(sum(1 for n in rest if n.essential), 2 * limit))
    first = [n for n in rest if n.essential] + [n for n in rest if not n.essential]
    chosen = {id(n) for n in first[:room]}
    return [n for n in rest if id(n) in chosen], covered, [n for n in rest if id(n) not in chosen]


def gather(runner: ProposalRunner, need, settings, chapter: int, today: str, safe, route: TopicRoute,
           readings: Callable[[], list[EvidenceItem]] | None = None, open_sources: bool = True, other: bool = False) -> list[EvidenceItem]:
    """One topic's findings, and in `route` how it was answered. The student's own readings come first (works).

    Workflow 1, as priced: the scholarly index for a LITERATURE need, the web when that gave nothing or for a FACT.
    Workflow 2: the kind of source decides. Research findings, theories and methods are looked for in the index, from
    a ranked pool, with one broader query when the first finds nothing; official figures and policies on the web. The
    other route is tried only when the first could not be asked at all, or found nothing for a need the work depends
    on: a web search is the exception, not the fallback for every empty result.

    The index is asked within the last LITERATURE_YEARS for a study; a method or theory is cited from its own source
    however old, and the second, broader search has no date floor (Codex audit of fd74ff3, finding 8: workflow 2 no
    longer sends every empty search to the web, where older sources used to come from). `other`: only the route not
    yet tried, for a need whose findings did not survive the support check (`other_route`)."""
    items = readings() if readings and not other else []
    if not open_sources or runner.budget_reached:
        return items
    window = utcnow().year - LITERATURE_YEARS

    def index(query: str, pool: int, keep: int | None, from_year: int | None = window) -> list[EvidenceItem]:
        return _from_index(runner, need.need, query, chapter, today, pool, keep, route, from_year)

    def web(reason: str) -> list[EvidenceItem]:
        route.reason = reason
        found = _from_web(runner, need.need, need.query, chapter, today, settings.research_max_searches, safe)
        route.web = "FOUND" if found else "NOTHING"
        route.findings += len(found)
        route.verified += sum(1 for i in found if i.verified)
        return found

    if runner._engine.workflow < 2:
        if need.kind == "LITERATURE":
            items += index(need.query, settings.proposal_works_per_need, None)
        if not items and not runner.budget_reached:
            items += web("AS_PRICED")
        return items

    def answered() -> bool:
        return any(i.verified for i in items)

    def from_index() -> list[EvidenceItem]:
        floor = None if need.category == "METHOD" else window
        found = index(need.query, settings.index_candidates, settings.index_abstracts, floor)
        broader = need.broader.strip()
        wider = broader if broader and broader.casefold() != need.query.strip().casefold() and safe(broader) else ""
        if (not any(i.verified for i in found) and route.index not in INDEX_FAILED and (wider or floor is not None) and not runner.budget_reached):
            found += index(wider or need.query, settings.index_candidates, settings.index_abstracts, None)
        return found

    if other:  # the first route's findings did not survive the support check: the route not yet tried, once
        if need.category in SCHOLARLY:
            return web("NOT_SUPPORTED") if route.web == "NOT_USED" else []
        return from_index() if route.index == "NOT_TRIED" else []
    if need.category in SCHOLARLY:
        items += from_index()
        failed = route.index in INDEX_FAILED
        if not answered() and (failed or need.essential) and not runner.budget_reached:
            items += web("INDEX_FAILED" if failed else "INDEX_EMPTY")
    else:
        if not answered():
            items += web("OFFICIAL_SOURCE")
        if not answered() and need.essential and not runner.budget_reached:
            items += from_index()  # a published study may carry the figure
    return items


def other_route(ctx: "StageContext", runner, needs: Sequence, routes: dict[str, TopicRoute], gathered: list[EvidenceItem], found: list[EvidenceItem],
                search: Callable[[Any], list[EvidenceItem]], check: Callable[[list[EvidenceItem]], None], parallel: int) -> tuple[list[EvidenceItem], list[EvidenceItem]]:
    """Workflow 2 (Codex audit of fd74ff3, finding 7): whether a topic is answered is known only after the support
    check, which can reject a finding whose quoted words were found. A need the work depends on that is left with no
    usable finding is asked once on the route not yet tried, and those findings are checked too. `search` saves its
    result like any topic. Returns everything gathered and the evidence, one entry per id."""
    if runner._engine.workflow < 2 or runner.budget_reached:
        return gathered, found
    usable = {i.id for i in found if i.usable}
    answered = {i.need for i in gathered if i.id in usable}

    def untried(need) -> bool:
        route = routes[_topic(need)]
        return route.web == "NOT_USED" if need.category in SCHOLARLY else route.index == "NOT_TRIED"

    again = [n for n in needs if n.essential and n.need not in answered and untried(n)]
    if not again:
        return gathered, found
    more = research_topics(ctx, again, search, parallel)
    known = {i.id for i in found}
    new = [i for i in evidence.dedupe(more) if i.id not in known]
    check(new)
    return [*gathered, *more], evidence.dedupe([*found, *new])


def record_topics(ctx: "StageContext", needs: Sequence, covered: Sequence, routes: dict[str, TopicRoute], left: Sequence = ()) -> None:
    """How each topic was answered, on the job: labels and counts only (never a topic's words)."""
    topics = ([routes[_topic(n)] for n in needs] + [TopicRoute(category=n.category or n.kind, essential=n.essential, covered=True) for n in covered]
              + [TopicRoute(category=n.category or n.kind, essential=n.essential, reason="OVER_ALLOWANCE") for n in left])

    def keep(j: Job) -> Job:
        j.topics = topics[:40]
        return j

    ctx.update(keep)


def essential_answered(runner, needs: Sequence, gathered: list[EvidenceItem], found: list[EvidenceItem], left: Sequence = ()) -> None:
    """Workflow 2: a need the work depends on must have at least one finding that may be cited. Without one the step
    stops here, in its first minutes and without charge, instead of writing around the gap and failing its review
    later (missing compulsory evidence is never turned into a warning: Codex's plan, 2026-10-09, and its audit of
    cbb99cb, which reversed an exception for theories and methods and one for the simplified path)."""
    if runner._engine.workflow < 2:
        return
    usable = {i.id for i in found if i.usable}
    answered = {i.need for i in gathered if i.id in usable}
    missing = [n.need.strip() for n in [*needs, *left] if n.essential and n.need not in answered]
    if missing:
        why = "its spending limit was reached first" if runner.budget_reached else "no source PaperAid could confirm answers it"
        raise PermanentStageError(
            "EVIDENCE_MISSING",
            f"PaperAid could not find reliable evidence for something this work depends on ({why}): \u201c{missing[0][:200]}\u201d. "
            "Nothing was charged. Add a source or more detail about it, then start again.",
            f"essential topics unanswered: {len(missing)} of {len(needs) + len(left)}")


# A topic whose search the provider leaves unanswered fails its stage, which is retried. Each run asks twice
# (searched_once_more); after this many runs (four tries, about seven minutes) the work goes on without that one topic
# and says so in the document's checks (owner decision 2026-10-08, after a tester's essay waited half an hour on one
# search of five while the verified sources for the other four were ready). Too many requests is never such a loss.
LOST_TOPIC_RUNS = 2
RESEARCH_GAPS = "research-gaps.json"


def _topic(need) -> str:
    """Within one job the topic (its need, query and kind, and in workflow 2 its category) identifies it: the job's
    input is frozen."""
    category = getattr(need, "category", "")
    return hashlib.sha256(json.dumps([need.need, need.query, need.kind, *([category] if category else [])]).encode()).hexdigest()[:24]


def _lost_runs(ctx: "StageContext", need) -> int:
    name = f"research/lost-{_topic(need)}.json"
    return int(ctx.get_json(name)["runs"]) if ctx.has(name) else 0


def checkpointed(ctx: "StageContext", runner, need, search: Callable[[], list[EvidenceItem]], route: TopicRoute | None = None,
                 part: str = "") -> list[EvidenceItem]:
    """A research topic answered in full is saved (speed plan 2026-10-08, Codex: checkpoints before anything else): a
    retry of this stage reads it back instead of fetching its sources again, with how it was answered (`route`). A
    topic cut short by the spending cap is not saved. A topic lost in LOST_TOPIC_RUNS runs is not asked again: it has
    no sources and is reported (research_gaps). `part` names a second search of the same topic (`other_route`)."""
    name = f"research/{_topic(need)}{'-' + part if part else ''}.json"
    if ctx.has(name):  # already answered: read back even when nothing more may be spent (Codex audit, finding 1)
        saved = ctx.get_json(name)
        if isinstance(saved, dict):  # saved with its route (algorithm revision 2026-10-09); a list is an earlier save
            if route is not None:
                for field, value in TopicRoute.model_validate(saved.get("route") or {}).model_dump().items():
                    setattr(route, field, value)
            saved = saved.get("items") or []
        if route is not None:
            route.reused = True
        return [EvidenceItem.model_validate(i) for i in saved]
    runs = _lost_runs(ctx, need)
    if runner.budget_reached or runs >= LOST_TOPIC_RUNS:
        if route is not None and runs >= LOST_TOPIC_RUNS:
            route.web = "LOST"
        return []
    try:
        items = search()
    except RetryableStageError as exc:
        if exc.code not in LOST_SEARCH:
            raise
        ctx.put_json(f"research/lost-{_topic(need)}.json", {"runs": runs + 1})
        if runs + 1 < LOST_TOPIC_RUNS:
            raise
        if route is not None:
            route.web = "LOST"
        return []
    if not runner.budget_reached:
        saved_items = [i.model_dump(by_alias=True) for i in items]
        ctx.put_json(name, saved_items if route is None else {"items": saved_items, "route": route.model_dump(by_alias=True)})
    return items


def research_gaps(ctx: "StageContext", needs: Sequence) -> str:
    """What the student is told when topics went unsearched, saved for the stage that builds the document's checks.
    Empty when every topic was searched."""
    lost = [n.need.strip()[:200] for n in needs if _lost_runs(ctx, n) >= LOST_TOPIC_RUNS]
    note = ""
    if lost:
        note = (f"PaperAid could not search {len(lost)} of {len(needs)} research topics because the search did not answer after several tries, "
                f"so it went on without {'it' if len(lost) == 1 else 'them'}: " + "; ".join(f"“{t}”" for t in lost) + ".")
    ctx.put_json(RESEARCH_GAPS, {"note": note})
    return note


def research_gap_items(ctx: "StageContext", item_id: str, chapter: int = 0) -> list[ReadinessItem]:
    note = ctx.get_json(RESEARCH_GAPS)["note"] if ctx.has(RESEARCH_GAPS) else ""
    if not note:
        return []
    return [ReadinessItem(id=item_id, question="Every research topic was searched", status="NEEDS_REVIEW", basis="CODE", chapter=chapter, severity="WARNING",
                          note=note[:600], reason="SEARCH_UNAVAILABLE", action="Check that your document covers this, or ask for changes to add it.")]


def research_topics[N](ctx: "StageContext", needs: Sequence[N], answer: Callable[[N], list[EvidenceItem]], parallel: int) -> list[EvidenceItem]:
    """The research topics, `parallel` at a time (speed plan 2026-10-08: they ran one after another, so every slow
    source held up the rest). Every Gemini call still waits its turn under the shared limit. All topics finish before
    an error from any is raised, and the results keep the topics' order, so the evidence and its order do not depend
    on which finished first. The student sees "topic n of N"; only this thread writes it."""
    total = len(needs)
    ctx.activity("SOURCES", 0, total)
    if parallel <= 1 or total <= 1:
        out: list[EvidenceItem] = []
        for done, need in enumerate(needs, start=1):
            out += answer(need)
            ctx.activity("SOURCES", done, total)
        return out
    with ThreadPoolExecutor(max_workers=parallel) as pool:
        futures = [pool.submit(answer, need) for need in needs]
        for done, _ in enumerate(as_completed(futures), start=1):
            ctx.activity("SOURCES", done, total)
    errors = [error for future in futures if (error := future.exception()) is not None]
    if errors:  # finished topics are saved; the most serious outcome decides (Codex audit, finding 13)
        raise min(errors, key=_severity)
    return [item for future in futures for item in future.result()]


def _severity(error: BaseException) -> int:
    """Which of several topics' errors decides the stage: a job no longer ours first, then an error no retry can fix,
    then one a retry may fix, and a wait for capacity last (it would hide a terminal problem already met)."""
    from app.jobs.pipeline import StageContinues  # the stage runner's own signal (imported here: it imports this module)

    if isinstance(error, StageContinues):
        return 0
    if isinstance(error, PermanentStageError):
        return 1
    if isinstance(error, CapacityWait):
        return 3
    return 2


def _from_index(runner: ProposalRunner, need: str, query: str, chapter: int, today: str, pool: int, keep: int | None, route: TopicRoute,
                from_year: int | None = None) -> list[EvidenceItem]:
    """Findings for a need from the scholarly index, each quoted from a work's abstract. `keep` (workflow 2): `pool`
    candidates are read, ranked in code and the best `keep` passed to the reader; None: the works as the index
    returned them (as priced before). `route` records what the search came to. `from_year`: None for any year."""
    outcome, works = fetch.openalex_find(query, from_year, pool)
    route.index = outcome
    route.candidates += len(works)
    if keep is not None:
        works = research.rank_works(works, need, query, keep)
    route.kept += len(works)
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
    route.findings += len(items)
    route.verified += sum(1 for i in items if i.verified)
    if not items:
        route.index = "NOTHING_RELEVANT"  # works came back, none answered the need
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


def _registered_by_title(title: str, published: str) -> dict[str, str] | None:
    """A web page that is a registered article (a journal's own page without a DOI in its address):
    its authors, journal and DOI from Crossref, taken only for the same title and, when the page gives
    one, the same year, so it is cited by its authors rather than its journal's name."""
    wanted = re.sub(r"[^a-z0-9]", "", title.casefold())
    if len(wanted) < 20:
        return None
    year = YEAR.search(published)
    for record in fetch.crossref_search(title, rows=3) or []:
        same_year = not year or not record.get("year") or record["year"] == year.group(0)
        if record.get("doi") and record.get("authors") and re.sub(r"[^a-z0-9]", "", record.get("title", "").casefold()) == wanted and same_year:
            return record
    return None


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
        if not record:
            record = _registered_by_title(finding.title, finding.published)
            doi = record["doi"] if record else doi
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
    if inp.step == "PROFILE":
        guide_path = inp.guide if ctx.rt.files.exists(inp.guide) else moved_path(inp.guide)
        if not ctx.rt.files.exists(guide_path):
            raise PermanentStageError("GUIDE_EXPIRED", "Your guide is no longer stored. Upload it again, then read it. Nothing was charged.", "profile: guide missing")
        guide = ctx.rt.files.get(guide_path).decode("utf-8")
        final, draft, critique = runner.profile({"guide": guide, "reference": profile.reference()})

        def built(answer: dict[str, Any]) -> dict[str, Any]:
            try:
                book = profile.build(answer, inp.guide_name)
            except profile.AmbiguousGuide as exc:
                raise PermanentStageError(
                    "GUIDE_AMBIGUOUS", "Your guide's Chapter One seems to have two sections for the same objectives or questions, so PaperAid could not tell "
                    "where your approved statements go. Nothing was charged. Check the guide's Chapter One headings, or keep the standard structure.",
                    f"profile: {exc}",
                ) from exc
            except profile.NotAGuide as exc:
                raise PermanentStageError(
                    "NOT_A_GUIDE", "PaperAid could not find a proposal structure in this guide, so nothing was charged. Check it is your institution's research guide.", f"profile: {exc}"
                ) from exc
            book["guide_sha256"] = hashlib.sha256(guide.encode()).hexdigest()  # which upload it was read from
            return book

        book = built(final)
        payload = {"guide": guide, "reference": profile.reference()}
        if not runner._engine.single_reviewer:  # older engines: both approvals, as they were priced
            runner.approve_profile({**payload, "finalProfile": book})
        else:
            # One final reviewer (owner decision 2026-09-30): an objection is repaired and the repaired profile
            # reviewed again, at most twice (Codex audit 2026-10-01). A profile still not approved is never used:
            # proposals are built on it, so the step fails without charge.
            for round_ in runner.audit_rounds(REVIEW_REPAIRS + 1):
                # the exact profile to be used, with what code filled from the standard profile (review v2 on)
                v1 = runner._prompt_for("p_profile_review") == "p-profile-review-v1"
                reviewed = book if v1 else {k: v for k, v in book.items() if k != "preliminary_pages"}  # never used in writing
                shown = {} if v1 else {"fromStandard": book.get("from_standard", [])}
                approved, objections = runner.review_profile({**payload, "finalProfile": reviewed, **shown})
                if approved:
                    break
                if round_ == REVIEW_REPAIRS or runner.budget_reached or not objections:
                    raise PermanentStageError(
                        "PROFILE_NOT_APPROVED", "PaperAid could not confirm your institution's structure from this guide, so nothing was changed and you were not charged. "
                        "You can try again, or continue with the standard structure.", f"profile not approved after {round_} repairs",
                    )
                final = runner.repair_profile(payload, final, objections)
                book = built(final)
        ctx.put_json("profile.json", {"profile": book, "draft": draft, "critique": critique.model_dump()})
        return
    usable = [i for i in _library(ctx, inp).values() if i.usable]
    rules = rulebook.rules_for(inp.rulebook)
    if inp.step == "PLAN":
        payload = {"study": _study(inp), "level": inp.inputs.level, "rules": rules, "evidence": _for_model(usable), "note": inp.note}
        if runner._prompt_for("p_plan") not in ("p-plan-v1", "p-plan-v2"):
            low, high = rulebook.objective_range(inp.rulebook, inp.inputs.level, inp.inputs.four_objectives, inp.goal == "CONCEPT")
            payload["objectiveCount"] = {"min": low, "max": high}
        final, draft, critique = runner.negotiate("plan", payload)

        def settled(answer: dict[str, Any]) -> ProposalPlan:
            return _confirmed_gap(_student_figures_only(_plan_from_model(answer), inp), {i.id for i in usable})

        plan = settled(final)
        if not runner._engine.single_reviewer:  # older engines: both approvals, as they were priced
            runner.approve_plan({**payload, "finalPlan": plan.model_dump(by_alias=True)})
            ctx.put_json("plan.json", {"plan": plan.model_dump(by_alias=True), "draft": draft, "critique": critique.model_dump()})
            return
        plan, review = _reviewed_plan(runner, payload, plan, usable, settled,
                                      lambda answer: rulebook.plan_problems(inp.rulebook, answer, inp.inputs.level, inp.inputs.four_objectives, inp.goal == "CONCEPT"))
        ctx.put_json("plan.json", {"plan": plan.model_dump(by_alias=True), "draft": draft, "critique": critique.model_dump(), "review": review.model_dump(by_alias=True)})
        if review.outcome != "APPROVED":  # kept for the student to edit, never charged for (owner decision 2026-09-30)
            ctx.update(lambda j: _unapproved_plan(j, review))
        return
    assert inp.plan is not None
    sections = [s for s in rulebook.sections(inp.rulebook, inp.chapter, inp.inputs.level, inp.plan) if not inp.only or s.key in inp.only]
    sample = sampling.calculate(inp.plan.sample_size) if inp.chapter == 3 else None
    payload = {
        "plan": _plan(inp),
        "chapter": inp.chapter,
        "sections": [{"key": s.key, "number": s.number, "heading": s.heading, "requirement": s.brief, "words": s.words, "table": s.table} for s in sections],
        "rules": rules,
        "evidence": _for_model(usable),
        "sampleSize": sample.steps if sample else "",
        "note": inp.note,
        **_finish_context(ctx, inp),
    }
    final, draft, critique = runner.negotiate("briefs", payload)
    ids = {i.id for i in usable}
    briefs = {b["key"]: {"points": [p for p in b.get("points", []) if p.strip()], "evidence": [e for e in b.get("evidence", []) if e in ids]} for b in final.get("sections", [])}
    ctx.put_json("briefs.json", {"briefs": briefs, "draft": draft, "critique": critique.model_dump()})




def _reviewed_plan(runner: ProposalRunner, payload: dict[str, Any], plan: ProposalPlan, usable: list[EvidenceItem], settled,
                   rules=lambda answer: []) -> tuple[ProposalPlan, PlanReview]:
    """The one accountable final review of the exact plan (Sol), after code has converted any
    hand-typed citation it can match to confirmed evidence. An objection is repaired (Sonnet, only
    what was named) and the repaired plan reviewed again, at most twice. What remains is returned
    as objections; a review that could not complete is "not reviewed", never approval."""
    plan, code_issues = _typed_citations(plan, usable)
    code_issues = [*code_issues, *rules(plan)]  # the guide's code-checkable rules (objective counts, primary question, hypothesis pairs)
    review = PlanReview(outcome="NOT_REVIEWED", reason="REVIEW_UNAVAILABLE")
    for round_ in runner.audit_rounds(REVIEW_REPAIRS + 1):
        approved, objections, reason = runner.review_plan({**payload, "finalPlan": _as_reviewed(plan)})
        objections = [*code_issues, *objections]
        if approved and not code_issues:
            return plan, PlanReview(outcome="APPROVED")
        review = PlanReview(outcome="OBJECTIONS" if reason == "REVIEW_OBJECTION" or code_issues else "NOT_REVIEWED",
                            reason="CODE_RULE" if approved and code_issues else reason, objections=list(dict.fromkeys(objections))[:20])
        if round_ == REVIEW_REPAIRS or runner.budget_reached or review.outcome == "NOT_REVIEWED":
            break
        plan = settled(runner.repair_plan(payload, plan.model_dump(by_alias=True), review.objections))
        plan, code_issues = _typed_citations(plan, usable)
        code_issues = [*code_issues, *rules(plan)]
    return plan, review


def _as_reviewed(plan: ProposalPlan) -> dict[str, Any]:
    """The plan as the reviewer judges it. Sampling settings a method does not calculate from (a
    margin or proportion for a power analysis or a qualitative sample) are left out: they only hold
    standard placeholder values, which read as contradictions (real-model pilot 2026-09-30)."""
    data = plan.model_dump(by_alias=True)
    if plan.sample_size.method not in QUANTITATIVE:
        for key in ("margin", "proportion", "confidence"):
            data["sampleSize"].pop(key, None)
    return data


def _unapproved_plan(j: Job, review: PlanReview) -> Job:
    """A plan the final reviewer did not approve is delivered for editing, charged nothing and marked
    partial, with the reason the student can act on."""
    j.delivery["PLAN"] = 0.0
    j.outcome = "PARTIAL"
    if review.outcome == "NOT_REVIEWED":
        message = ("PaperAid could not complete its final review of this plan, so it is not approved and you were not charged. "
                   "You can edit it and approve it yourself once you have checked it, or make the plan again.")
    else:
        message = ("PaperAid's final reviewer still had objections after two rounds of repair, so this plan is not approved and you were not charged. "
                   "The objections are shown with the plan: edit it to address them, then approve it, or make the plan again.")
    j.warnings = list(dict.fromkeys([*j.warnings, message]))
    return j


def _typed_citations(plan: ProposalPlan, usable: list[EvidenceItem]) -> tuple[ProposalPlan, list[str]]:
    """A citation typed by hand in the plan ("(Uganda Communications Commission, 2025)"; live case
    prj_c704b0c370f7) is converted by code only when it matches exactly one confirmed source by author
    and year: removed when that source's id already cites the same text, otherwise replaced by the id.
    Any other is left for a targeted repair, named exactly. A source is never invented."""
    issues: list[str] = []

    def match(typed: str) -> EvidenceItem | None:
        year = YEAR.search(typed)
        if year is None:
            return None
        name = typed.split("(")[0] if not typed.startswith("(") else typed.strip("()").rsplit(",", 1)[0]
        name = re.sub(r"\bet al\.?", "", re.sub(r"[,&]|\band\b", " ", name)).strip().casefold()
        if not name:
            return None
        found = [i for i in usable if i.source.year == year.group(0) and (
            (i.source.organisation and (name in i.source.organisation.casefold() or i.source.organisation.casefold() in name))
            or any(a.split(",")[0].strip().casefold() == name.split()[0] for a in i.source.authors))]
        return found[0] if len({i.id for i in found}) == 1 else None

    def clean(text: str, where: str) -> str:
        for typed in evidence.TYPED_CITATION.findall(evidence.ANY_TOKEN.sub(" ", text)):
            item = match(typed)
            if item is None:
                issues.append(f"Remove the citation typed by hand \"{typed}\" in {where}: cite only with the evidence ids given, and only what that evidence supports.")
            elif item.id in text:
                text = text.replace(typed, "").replace("  ", " ").replace(" ,", ",").replace(" .", ".").replace("( )", "").replace("()", "")
            elif typed.startswith("("):
                text = text.replace(typed, f"({item.id})")
            else:
                text = text.replace(typed, re.sub(r"\((?:19|20)\d{2}[a-z]?\)", f"({item.id})", typed))
        return " ".join(text.split())

    def walk(value: Any, where: str) -> Any:
        if isinstance(value, str):
            return clean(value, where)
        if isinstance(value, list):
            return [walk(v, where) for v in value]
        if isinstance(value, dict):
            return {k: walk(v, k if where == "the plan" else where) for k, v in value.items()}
        return value

    data = walk(plan.model_dump(by_alias=True), "the plan")
    return ProposalPlan.model_validate(data), list(dict.fromkeys(issues))


SAMPLING_DEFAULTS = {"margin": (0.0, 0.5, 0.05), "proportion": (0.0, 1.0, 0.5)}


QUANTITATIVE = ("YAMANE", "COCHRAN", "KREJCIE_MORGAN")  # the methods whose calculation uses these settings


def _sane_sampling(data: dict[str, Any]) -> None:
    """A sampling setting outside its range (a margin or proportion of 0, for a qualitative study)
    takes its standard value instead of discarding the whole plan; a population or stated size that
    is not a positive whole number is left for the student to give. Sizes are the student's anyway
    (`_student_figures_only`). When the method calculates a sample from these settings, the student
    is asked to confirm the standard values, which they can change in the plan before approving it
    (Codex audit 2026-09-30, second round: never a quiet quantitative assumption)."""
    size = data.get("sampleSize")
    if not isinstance(size, dict):
        return
    assumed = []
    for key, (low, high, default) in SAMPLING_DEFAULTS.items():
        value = size.get(key)
        if value is not None and not (isinstance(value, int | float) and low < value < high):
            size[key] = default
            assumed.append(f"{'a margin of error of 5%' if key == 'margin' else 'an expected proportion of 0.5'}")
    for key in ("population", "stated"):
        value = size.get(key)
        if value is not None and not (isinstance(value, int) and value >= 1):
            size[key] = None
    if size.get("confidence") not in (90, 95, 99):
        size["confidence"] = 95
        assumed.append("a 95% confidence level")
    if assumed and size.get("method") in QUANTITATIVE:
        ask = (f"The sample size calculation needs values the plan did not give, so PaperAid used the usual {', '.join(assumed)}. "
               "Confirm these in the sample size settings, or change them, before approving the plan.")
        data["questionsForStudent"] = [*[q for q in data.get("questionsForStudent", []) if isinstance(q, str)], ask]
        data["samplingAssumed"] = assumed  # approving the plan then needs the student's explicit acknowledgment


def _plan_from_model(data: dict[str, Any]) -> ProposalPlan:
    """The model's plan as a ProposalPlan. The schema has no length limits (providers cannot
    enforce them), so an over-long field is shortened to the plan's limit rather than failing the
    step; anything else invalid fails it once, since a retry would replay the same saved answer."""
    _sane_sampling(data)
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
                shortened = _shorten(target[last], error["ctx"]["max_length"])
                if shortened is None:
                    raise PermanentStageError(
                        "PLAN_INVALID", "PaperAid could not fit part of the plan within its limits this time. Nothing was charged; please try again.",
                        f"plan field {'.'.join(str(k) for k in error['loc'])} has no sentence end to shorten at",
                    ) from exc
                target[last] = shortened
    return ProposalPlan.model_validate(data)


def _shorten(text: str, limit: int) -> str | None:
    """Text within `limit`, ending at a complete sentence in its second half; None when there is none.
    A sentence cut mid-way reads as an error to the reviewers and to the student (Phase 4 pilot), so it
    is never delivered (Codex review 2026-09-30 #7)."""
    head = text[:limit]
    end = max(head.rfind(mark) for mark in (". ", "? ", "! "))
    if end < limit // 2:
        return None
    return head[: end + 1]


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


# Told to the writer and the reviewer of every section whose statements code places from the approved plan. Live runs
# 2026-10-08: the reviewer asked to remove the placed objectives (Chapter One), then the placed sub-headings of a
# concept paper's hypotheses ("Remove the extra headings 5.1 Primary Research Question and 5.2 Research Hypotheses"),
# which code puts back, so the document could never be approved. Always added, whatever the guide's own brief says.
PLACED = (" PaperAid places the student's approved statements after the introduction, word for word, under numbered sub-headings where "
          "they have them (such as \"General Objective\", \"Specific Objectives\", \"Primary Research Question\", \"Specific Research "
          "Questions\" or \"Research Hypotheses\", each null hypothesis with its alternative). Those sub-headings and statements are the "
          "approved plan and are correct as they stand: write only the introduction, and never ask to remove, merge, renumber, reword or "
          "shorten them.")


def _section_items(inp: StepInput, library: dict[str, EvidenceItem], briefs: dict[str, Any]) -> list[dict[str, Any]]:
    assert inp.plan is not None
    items = []
    for s in rulebook.sections(inp.rulebook, inp.chapter, inp.inputs.level, inp.plan):
        if inp.only and s.key not in inp.only:  # finishing a chapter: its missing sections only
            continue
        brief = briefs.get(s.key, {"points": [], "evidence": []})
        assigned = [library[i] for i in brief["evidence"] if i in library and library[i].usable]
        requirement = s.brief + PLACED if s.from_plan else s.brief
        items.append(
            {
                "key": s.key, "number": s.number, "heading": s.heading, "requirement": requirement, "words": s.words, "table": s.table,
                "objective": s.objective, "points": brief["points"], "evidence": _for_model(assigned, passages=True),
                "_words": " ".join(["w"] * s.words),  # batches are sized by the words each section will produce
            }
        )
    return items


def stage_drafting(ctx: "StageContext") -> None:
    inp = step_input(ctx)
    assert inp.plan is not None
    runner = _runner(ctx, inp)
    library = _library(ctx, inp)
    sample = sampling.calculate(inp.plan.sample_size) if inp.chapter == 3 else None
    items = _section_items(inp, library, ctx.get_json("briefs.json")["briefs"])
    ctx.activity("WRITING", 0, len(items))
    drafted = runner.draft(items, {**_common(inp, sample.steps if sample else ""), **_finish_context(ctx, inp)})
    ctx.put_json("drafted.json", {k: v.model_dump() for k, v in drafted.items()})
    missing = [i["heading"] for i in items if i["key"] not in drafted]
    if missing:
        ctx.update(lambda j: _warn(j, [f"These sections could not be written within this step's limits: {', '.join(missing)}."], partial=True))


# --- AUDITING ------------------------------------------------------------------------------------


ROMAN = ("i", "ii", "iii", "iv", "v", "vi", "vii", "viii")
# A writer's line that lists or restates the plan's statements rather than introducing them: never kept.
_LISTED = re.compile(r"^\s*(?:[ivx]{1,4}[.)]|\d{1,2}[.)]|h[0a]\d|to\s)", re.I)
# "To address these gaps, the study's objectives are ..." introduces the statements: an objective never names
# objectives, questions or the study itself (live runs 2026-10-08).
_INTRODUCES = re.compile(r"\b(?:objectives?|questions?|hypothes[ie]s|propositions?|this study|the study)\b", re.I)


def stated_fragments(plan: ProposalPlan, number: str) -> list[str]:
    """The opening words of every approved statement, objectives and questions alike: a writer's line repeating
    any of them is not an introduction. Sub-headings are left out: an introduction may name "the primary
    research question" (live run 2026-10-08)."""
    lines = [*plan_statements(plan, "objectives", number), *plan_statements(plan, "questions", number)]
    return [line.split(" ", 1)[-1].strip().lower()[:40] for line in lines if len(line) > 20 and not evidence.SUBHEADING.match(line)]


def _introduction(paragraph: str, stated: list[str]) -> bool:
    if not paragraph.strip() or _restates(paragraph, stated):
        return False
    return not _LISTED.match(paragraph) or (paragraph.lstrip()[:3].lower() == "to " and bool(_INTRODUCES.search(paragraph)))


def _owned_kinds(inp: StepInput) -> dict[str, str]:
    """The sections whose statements code places from the approved plan (rulebook v2 on): key -> kind."""
    assert inp.plan is not None
    return {s.key: s.from_plan for s in rulebook.sections(inp.rulebook, inp.chapter, inp.inputs.level, inp.plan) if s.from_plan}


_LABEL = re.compile(r"^\s*H\s*(?:0|o|₀|a|A|1)\s*\d*\s*[:.)]\s*", re.I)  # a hypothesis label a plan's own text carries


def plan_statements(plan: ProposalPlan, kind: str, number: str) -> list[str]:
    """The general and specific objectives, or the primary research question with the specific questions
    (each null hypothesis with its alternative; or the propositions), as approved, under numbered sub-headings
    (handbook §5.3.3-5.3.4; vetting form, p. 51)."""
    specific = [f"{ROMAN[i]}. {o.strip()}" for i, o in enumerate(o for o in plan.specific_objectives if o.strip())]
    if kind == "objectives":
        return [f"{number}.1 General Objective", plan.purpose.strip(), f"{number}.2 Specific Objectives", *specific]
    if kind == "specific_objectives":  # the guide (or the concept paper, §1.4) states the purpose in a section of its own
        return specific
    if kind == "purpose":  # that section: the general objective, as approved (Codex audit 29343c2 #2)
        return [plan.purpose.strip()]
    lines: list[str] = []
    sub = 1
    if plan.primary_question.strip():
        lines += [f"{number}.1 Primary Research Question", plan.primary_question.strip()]
        sub = 2
    questions = [q.strip() for q in plan.research_questions if q.strip()]
    label = {"QUESTIONS": "Specific Research Questions", "HYPOTHESES": "Research Hypotheses", "PROPOSITIONS": "Research Propositions"}[plan.questions_kind]
    if plan.questions_kind == "HYPOTHESES":
        asked = [q for q in questions if rulebook.is_question(q)]

        def bare(text: str) -> str:
            # In a mixed plan (new on 2026-10-10: such plans were refused before) a label the plan's own text carries
            # ("H01:", "Ha1:") is not printed twice. A plan of hypotheses only prints exactly as it always has, so the
            # chapters already written from one still match their plan.
            return _LABEL.sub("", text) if asked else text

        alternatives = [bare(a.strip()) for a in plan.alternative_hypotheses if a.strip()]
        # A descriptive objective keeps its research question beside the hypotheses (it takes none).
        lines.append(f"{number}.{sub} {'Research Questions and Hypotheses' if asked else label}")
        lines += [f"{ROMAN[i]}. {q}" for i, q in enumerate(asked)]
        for i, null in enumerate((q for q in questions if not rulebook.is_question(q)), start=1):
            lines.append(f"H0{i}: {bare(null)}")
            if i <= len(alternatives):
                lines.append(f"HA{i}: {alternatives[i - 1]}")
    else:
        lines.append(f"{number}.{sub} {label}")
        lines += [f"{ROMAN[i]}. {q}" for i, q in enumerate(questions)]
    return lines


def _restates(paragraph: str, stated: list[str]) -> bool:
    return any(fragment and fragment in paragraph.lower() for fragment in stated)


def _owned(inp: StepInput, items: dict[str, dict[str, Any]], current: dict[str, SectionText]) -> dict[str, SectionText]:
    """Each plan-owned section: the writer's short introduction (never its own list of the statements), then the
    approved statements exactly as approved. Applied after drafting and after every repair, so no review or
    repair can change them (Codex review 2026-10-08)."""
    assert inp.plan is not None
    kinds = _owned_kinds(inp)
    out = dict(current)
    for key, kind in kinds.items():
        if key not in out or key not in items:
            continue
        statements = plan_statements(inp.plan, kind, items[key]["number"])
        stated = stated_fragments(inp.plan, items[key]["number"])

        lead = [p for p in out[key].paragraphs if _introduction(p, stated)][:2]  # the brief asks for one or two sentences
        out[key] = out[key].model_copy(update={"paragraphs": [*lead, *statements]})
    return out


# --- workflow 2: the final editor's corrections, applied by paragraph (works and chapters alike) --------


_WORDS_AND_TOKENS = re.compile(r"⟦[^⟧]*⟧|[^\W_]+")


def changes_words(before: str, after: str) -> bool:
    """Whether a correction changed any word, figure or citation, or their order. False only when code can see that
    nothing but case, spacing or punctuation differs. The editor's own label is never the test (Codex audit of
    fd74ff3, finding 3: a change of substance marked WORDING skipped the support check)."""
    return _WORDS_AND_TOKENS.findall(before.casefold()) != _WORDS_AND_TOKENS.findall(after.casefold())


def placed_apart(inp: StepInput, items: dict[str, dict[str, Any]], key: str, text: SectionText) -> tuple[list[str], list[str]]:
    """A plan-owned section as (the writer's introduction, the statements code placed after it); any other section
    as (its paragraphs, nothing). A reviewer judges what the writer wrote and is told what PaperAid places."""
    kind = _owned_kinds(inp).get(key) if inp.plan is not None else None
    if not kind or key not in items:
        return text.paragraphs, []
    statements = plan_statements(inp.plan, kind, items[key]["number"])
    if statements and text.paragraphs[-len(statements):] == statements:
        return text.paragraphs[: -len(statements)], statements
    return text.paragraphs, []


def review_item(inp: StepInput, items: dict[str, dict[str, Any]], key: str, text: SectionText, checks: list[str], apart: bool) -> dict[str, Any]:
    """One section as a reviewer is asked about it. `apart` (review prompts from p-review-v4, which says what
    "placedByPaperAid" is): a plan-owned section is its writer's introduction, with what PaperAid places given apart.
    Nothing a reviewer then says is set aside by code (Codex's audit of cbb99cb, finding 1: a keyword filter dropped a
    genuine rejection); a job priced on an earlier prompt is asked exactly as it was."""
    lead, statements = placed_apart(inp, items, key, text) if apart else (text.paragraphs, [])
    return {**items[key], "text": lead, **({"placedByPaperAid": statements} if statements else {}), "table": text.table.model_dump(), "paperaidChecks": checks,
            "_words": " ".join(text.paragraphs)}


def numbered(text: SectionText) -> list[dict[str, str]]:
    return [{"id": f"p{n}", "text": p} for n, p in enumerate(text.paragraphs, start=1)]


def apply_corrections(current: dict[str, SectionText], corrections: list[Correction], editable: list[str]) -> tuple[list[dict[str, str]], dict[str, list[str]]]:
    """Applies the final editor's corrections to `current`. A correction names its paragraph by the id it had when
    reviewed; one that names an unknown place, a section this step may not change, or a paragraph already corrected is
    refused, never guessed at. Returns the corrections applied (the text before and after, and the paragraph's id as
    it now is) and, by section, why any was refused."""
    rows = {k: [[p["id"], p["text"]] for p in numbered(current[k])] for k in editable if k in current}
    removed: dict[str, set[str]] = {}
    touched: set[tuple[str, str]] = set()
    applied: list[dict[str, str]] = []
    refused: dict[str, list[str]] = {}
    for n, c in enumerate(corrections, start=1):
        def refuse(why: str, c: Correction = c) -> None:
            refused.setdefault(c.section if c.section in rows else "", []).append(f"A correction to paragraph {c.paragraph} could not be applied: {why}.")

        if c.section not in rows:
            refuse("that section may not be changed in this step")
            continue
        entry = {"id": f"c{n}", "key": c.section, "ref": c.paragraph, "kind": c.kind, "action": c.action, "before": "", "after": ""}
        if c.action in ("REMOVE_TABLE", "REMOVE_FIGURE"):
            removed.setdefault(c.section, set()).add(c.action)
            applied.append(entry)
            continue
        index = next((i for i, row in enumerate(rows[c.section]) if row[0] == c.paragraph), None)
        text = " ".join(c.text.split())
        if index is None and text and c.action in ("REPLACE", "INSERT_AFTER") and not any(row[0].startswith("p") and "+" not in row[0] for row in rows[c.section]):
            # A section code left empty has no paragraph to name (trial 2026-10-10: the editor wrote the missing section
            # twice and both were refused, so the chapter failed as "empty"): what it writes there opens the section.
            entry.update(ref=f"new+{n}", after=text)
            rows[c.section].append([entry["ref"], text])
            applied.append(entry)
            continue
        if index is None:
            refuse("there is no such paragraph")
            continue
        if c.action == "INSERT_AFTER":
            if not text:
                refuse("no text was given")
                continue
            entry.update(ref=f"{c.paragraph}+{n}", after=text)
            rows[c.section].insert(index + 1, [entry["ref"], text])
            applied.append(entry)
            continue
        if (c.section, c.paragraph) in touched:
            refuse("that paragraph was already corrected")
            continue
        entry["before"] = rows[c.section][index][1]
        if c.action == "DELETE":
            rows[c.section].pop(index)
        elif not text:
            refuse("no text was given")
            continue
        elif text == entry["before"]:
            continue  # nothing changes
        else:
            entry["after"] = text
            rows[c.section][index][1] = text
        touched.add((c.section, c.paragraph))
        applied.append(entry)
    for key, section_rows in rows.items():
        update: dict[str, Any] = {"paragraphs": [text for _, text in section_rows]}
        if "REMOVE_TABLE" in removed.get(key, ()):
            update["table"] = Table(caption="", rows=[])
        if "REMOVE_FIGURE" in removed.get(key, ()):
            update["figure"] = None
        position = {ref: f"p{i}" for i, (ref, _) in enumerate(section_rows, start=1)}
        for entry in applied:
            if entry["key"] == key:
                entry["paragraph"] = position.get(entry["ref"], "")
        current[key] = current[key].model_copy(update=update)
    return applied, refused


ALIGNED_NOTE = "Restructured to your institution's guide"
CONCEPT_NUMBER = 4  # the concept paper is stored as chapter 4 and keeps its own layout


def align_document(doc: ChapterDocument, before: str, after: str, level: Level, plan: ProposalPlan) -> ChapterDocument:
    """A written chapter in the structure of the student's institution guide (owner decision 2026-10-08):
    the guide's order, numbering and headings; the text of every section the guide keeps, unchanged (the
    approved statements placed again under their new numbers); sections the guide drops left out; sections
    it adds still to write (`missing`, written by "Finish chapter"); and sections whose requirement differs
    in the guide listed in `to_align`, to be revised to it. Code only: no model is called."""
    old_briefs = {s.key: s.brief for s in rulebook.sections(before, doc.number, level, plan)}
    planned = rulebook.sections(after, doc.number, level, plan)
    earlier = {s.key: s for s in doc.sections}
    sections = []
    for spec in planned:
        section = earlier.get(spec.key)
        if section is None:
            continue
        paragraphs = section.paragraphs
        if spec.from_plan:  # the writer's introduction, then the approved statements under their new numbers
            stated = stated_fragments(plan, spec.number)
            lead = [par for par in paragraphs if not evidence.SUBHEADING.match(par) and _introduction(par, stated)][:2]
            paragraphs = [*lead, *plan_statements(plan, spec.from_plan, spec.number)]
            # rebuilt from the plan as it is now: its decisions are the current ones (Codex audit, finding 3)
            section = section.model_copy(update={"depends": decisions.stamp(doc.number, spec.key, plan)})
        sections.append(section.model_copy(update={"number": spec.number, "heading": spec.heading, "paragraphs": paragraphs}))
    for spec in planned:
        if spec.from_plan and spec.key not in earlier:  # the approved statements need no writer (Codex audit 29343c2 #2)
            sections.insert(next((i for i, s in enumerate(sections) if [p.key for p in planned].index(s.key) > [p.key for p in planned].index(spec.key)), len(sections)),
                            ChapterSection(key=spec.key, number=spec.number, heading=spec.heading, paragraphs=plan_statements(plan, spec.from_plan, spec.number),
                                           depends=decisions.stamp(doc.number, spec.key, plan)))
    keys = {s.key for s in sections}
    missing = [spec.key for spec in planned if spec.key not in keys]
    # A section still to revise stays so, whatever guide is read next (Codex audit, finding 2: reading the same guide
    # again compared its brief with itself and cleared the flag, though the wording was never revised).
    to_align = [spec.key for spec in planned if spec.key in keys and not spec.from_plan
                and (spec.brief != old_briefs.get(spec.key) or spec.key in doc.to_align)]
    dropped = [f"{s.number} {s.heading}" for s in doc.sections if s.key not in {spec.key for spec in planned}]
    cited: list[str] = []
    for section in sections:
        for field in [*section.paragraphs, section.table_caption, *[c for row in section.table or [] for c in row]]:
            cited += [i for i in evidence.cited_ids(field) if i not in cited]
    words = sum(len(evidence.ANY_TOKEN.sub(" ", par).split()) for s in sections for par in s.paragraphs)
    n = doc.number
    readiness = [r for r in doc.readiness if not r.id.endswith("-WRITTEN") and r.id != f"C{n}-ALIGNED"]
    readiness += [
        ReadinessItem(id=f"C{n}-{spec.key}-WRITTEN", question=f"Is {spec.number} {spec.heading} written?", status="MISSING", basis="CODE",
                      note="Your institution's guide adds this section. Write the new sections to add it.")
        for spec in planned if spec.key in missing
    ]
    changes = []
    if dropped:
        changes.append("Left out because your guide does not include them: " + "; ".join(dropped) + ".")
    if to_align:
        changes.append("Your guide asks for something different in: " + "; ".join(f"{spec.number} {spec.heading}" for spec in planned if spec.key in to_align)
                       + ". Revise them to your guide.")
    readiness.append(ReadinessItem(
        id=f"C{n}-ALIGNED", question="Does the chapter follow your institution's guide?", basis="CODE", chapter=n,
        status="NEEDS_REVIEW" if (to_align or missing) else "PASS",
        note=(" ".join(changes) or "Restructured to your guide's order, numbering and headings; the earlier version is kept.")[:600]))
    return doc.model_copy(update={"sections": sections, "cited": cited, "words": words, "missing": missing, "to_align": to_align,
                                  "readiness": readiness, "revised": [], "warnings": []})


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


def _cleaned(inp: StepInput, text: SectionText, library: dict[str, EvidenceItem], usable: set[str], allowed: str) -> SectionText:
    """A section with every untraceable sentence removed, repeated until nothing more changes
    (removing a cited sentence can leave a neighbour's figure unsupported)."""
    for _ in range(5):
        paragraphs = [p for p in (evidence.strip_unsupported(p, library, usable, allowed) for p in text.paragraphs) if p]
        tidy = text.model_copy(update={"paragraphs": paragraphs, "table": _strip_table(inp, text, library, usable, allowed)})
        if tidy == text:
            break
        text = tidy
    return text


def _strip_table(inp: StepInput, text: SectionText, library: dict[str, EvidenceItem], usable: set[str], allowed: str) -> Table:
    table_allowed = _table_allowed(inp, allowed)

    def clean(cell: str) -> str:
        return evidence.strip_unsupported(cell, library, usable, table_allowed)

    return Table(caption=clean(text.table.caption), rows=[[clean(c) for c in row] for row in text.table.rows])


def _text_hash(current: dict[str, SectionText]) -> str:
    return hashlib.sha256(json.dumps({k: v.model_dump() for k, v in sorted(current.items())}, sort_keys=True).encode()).hexdigest()


UNTRACED = ("Paragraph {id} carries a citation or figure that cannot be traced to the section's evidence or the plan. Cite it with a token from "
            "the evidence, or remove it.")


def _edited(ctx: "StageContext", runner: ProposalRunner, inp: StepInput, items: dict[str, dict[str, Any]], current: dict[str, SectionText],
            library: dict[str, EvidenceItem], allowed: str, common: dict[str, Any],
            ) -> tuple[dict[str, SectionText], dict[str, Grade], dict[str, list[str]], list[str], Approval]:
    """Workflow 2 (the owner's one fixed principle, 2026-10-09): the premium model reads each written section once,
    corrects it itself and gives the final decision; no writer rewrites a section after it.

    Before it, code withholds what it cannot trace and runs its checks (findings for the editor, never a repair round).
    Its corrections are applied by paragraph, by code, and the plan's own statements are put back word for word. Then
    code checks the corrected text and a standard-model check may flag a corrected claim its evidence does not support.
    Only the sections with something flagged or found go to the editor once more, and that is the end: a section code
    still finds a problem in, or the editor did not pass, is not approved (`unresolved`)."""
    usable = {i for i, item in library.items() if item.usable}
    current = dict(current)
    stripped: list[str] = []
    for key, text in list(current.items()):
        tidy = _cleaned(inp, text, library, usable, allowed)
        if tidy != text:
            stripped.append(items[key]["heading"])
            current[key] = tidy
    reviewed = _text_hash(current)

    def found(keys: Iterable[str]) -> dict[str, list[str]]:
        out: dict[str, list[str]] = {}
        for key in keys:
            problems = _checks(inp, key, current[key], library, allowed)
            traced = set(_cleaned(inp, current[key], library, usable, allowed).paragraphs)
            problems += [UNTRACED.format(id=p["id"]) for p in numbered(current[key]) if p["text"] not in traced]
            if problems:
                out[key] = list(dict.fromkeys(problems))
        return out

    def request(checks: dict[str, list[str]], flagged: list[dict[str, str]] | None = None) -> list[dict[str, Any]]:
        asked = list(current) if flagged is None else [k for k in current if checks.get(k) or any(f["key"] == k for f in flagged)]
        out = []
        for key in asked:
            item = {**items[key], "paragraphs": numbered(current[key]), "table": current[key].table.model_dump(), "paperaidChecks": checks.get(key, []),
                    "_words": " ".join(current[key].paragraphs)}
            if flagged is not None:
                item["flagged"] = [{"paragraph": f["paragraph"], "problem": f["problem"]} for f in flagged if f["key"] == key]
            out.append(item)
        return out

    def apply(edits: dict[str, Any]) -> tuple[list[dict[str, str]], dict[str, list[str]]]:
        corrections = [c.model_copy(update={"section": key}) for key, edit in edits.items() for c in edit.corrections]
        applied, refused = apply_corrections(current, corrections, [k for k in edits if k in current])
        current.update(_owned(inp, items, current))  # the plan's statements stay as approved, whatever was corrected
        placed = []
        for a in applied:  # a correction code undid (a placed statement) is no longer in the text: nothing to check
            now = {p["text"]: p["id"] for p in numbered(current[a["key"]])}
            if not a["after"] or a["after"] in now:
                placed.append({**a, "paragraph": now.get(a["after"], a["paragraph"])})
        return placed, {k: v for k, v in refused.items() if k}

    def unsupported(applied: list[dict[str, str]]) -> list[dict[str, str]]:
        asked = [a for a in applied if a["after"] and changes_words(a["before"], a["after"])]  # never by the editor's own label
        if not asked:
            return []
        flags = runner.flag([{"id": a["id"], "before": a["before"], "after": a["after"],
                              "evidence": _for_model([library[i] for i in dict.fromkeys(evidence.cited_ids(a["after"])) if i in library], passages=True)} for a in asked],
                            {"plan": _plan(inp)})
        return [{"key": a["key"], "paragraph": a["paragraph"],
                 "problem": (flags[a["id"]].problem.strip() if a["id"] in flags else "") or "The check could not confirm this correction against its evidence."}
                for a in asked if a["id"] not in flags or not flags[a["id"]].supported]

    ctx.activity("CHECKING", 1, 2)
    edits = runner.edit(request(found(current)), common)
    applied, refused = apply(edits)
    grades: dict[str, Grade] = {k: Grade(key=k, grade=e.grade, issues=e.issues, note=e.note) for k, e in edits.items() if k in current}
    checks = found(grades)
    for key, why in refused.items():
        checks.setdefault(key, []).extend(why)
    for key, grade in grades.items():
        if grade.grade != "REPAIR" and any(i.strip() for i in grade.issues):
            # An answer that passes a section and lists what is wrong with it contradicts itself: it is asked again,
            # never read as approval (Codex audit of fd74ff3, finding 2).
            checks.setdefault(key, []).append("Your answer passed this section and also listed issues in it. Settle each with a correction, or grade the section "
                                              "REPAIR and say what remains: " + "; ".join(i.strip() for i in grade.issues if i.strip())[:400])
    flagged = unsupported(applied)
    refusals = sum(len(v) for v in refused.values())
    resolved = bool(checks or flagged) and not runner.budget_reached
    if resolved:
        ctx.activity("CHECKING", 2, 2)
        again = request(checks, flagged)
        edits = runner.edit(again, common, resolve=True)
        more, refused = apply(edits)
        applied += more
        refusals += sum(len(v) for v in refused.values())
        for item in again:  # a section sent back has the editor's last answer, or none: its first grade was for other text
            edit = edits.get(item["key"])
            grades.pop(item["key"], None)
            if edit is not None:
                grades[item["key"]] = Grade(key=edit.key, grade=edit.grade, issues=edit.issues, note=edit.note)
        checks = found(current)
        for key, why in refused.items():  # its grade was for the text with every correction applied
            checks.setdefault(key, []).extend(why)
        late = unsupported(more)  # what it wrote last is checked like what it wrote first; there is no further look
        for flag in late:
            checks.setdefault(flag["key"], []).append("A claim corrected on the final look could not be confirmed against its evidence: " + flag["problem"])
        flagged += late
    unresolved: dict[str, list[str]] = {}
    for key in current:
        grade = grades.get(key)
        raised = [i.strip() for i in grade.issues if i.strip()] if grade else []  # an issue blocks whatever the grade says
        issues = [*checks.get(key, []), *raised, *(["REVIEW_REJECTED"] if grade and grade.grade == "REPAIR" and not raised else []), *([] if grade else [NOT_REVIEWED])]
        if issues:
            unresolved[key] = list(dict.fromkeys(issues))
    approval = Approval(
        reviewer=(runner._engine.vertex_routes.get("p_edit") or [runner.model_for("p_edit")])[0], reviewed_sha256=reviewed, accepted_sha256=_text_hash(current),
        corrections=len(applied), substantive=sum(1 for a in applied if a["kind"] != "WORDING"), flagged=len(flagged), resolved=resolved, refused=refusals)
    return current, grades, unresolved, stripped, approval


def stage_auditing(ctx: "StageContext") -> None:
    """Code checks every section; the lead reviews with those results; the writer fixes what is
    raised; bounded rounds. Whatever still breaks a code rule afterwards is removed, never shipped.
    Workflow 2: the final editor reviews, corrects and decides instead (`_edited`)."""
    inp = step_input(ctx)
    assert inp.plan is not None
    settings = ctx.rt.settings
    runner = _runner(ctx, inp)
    workflow2 = runner._engine.editor  # the final editor's path; False: the earlier review and fixes
    library = _library(ctx, inp)
    usable = {i for i, item in library.items() if item.usable}
    sample = sampling.calculate(inp.plan.sample_size) if inp.chapter == 3 else None
    allowed = _allowed_text(inp, sample.figures if sample else "")
    common = {**_common(inp, sample.steps if sample else ""), **_finish_context(ctx, inp)}
    vetting = rulebook.vetting(inp.rulebook, inp.chapter)
    warnings: list[str] = []
    base: ChapterDocument | None = None
    if inp.step == "REVISE":
        base, items, current = _revision(ctx, runner, inp, library, common)
    else:
        items = {i["key"]: i for i in _section_items(inp, library, ctx.get_json("briefs.json")["briefs"])}
        current = {k: SectionText.model_validate(v) for k, v in ctx.get_json("drafted.json").items()}
        if inp.step == "COMPLETE":
            base = _base_document(ctx, inp)
    current = _owned(inp, items, current)
    apart = runner._engine.prompts.get("p_review", "p-review-v3") != "p-review-v3"  # from p-review-v4 the prompt explains "placedByPaperAid"
    unresolved: dict[str, list[str]] = {}
    grades: dict[str, Grade] = {}
    stripped: list[str] = []
    approval: Approval | None = None
    if workflow2:
        current, grades, unresolved, stripped, approval = _edited(ctx, runner, inp, items, current, library, allowed, {**common, "vetting": vetting})
    rounds = settings.repair_attempts
    # review, fix, review ... review: the delivered text is always the reviewed text, with at most
    # `rounds` fixes, as priced (Codex audit 2026-09-28 #11).
    for round_ in ([] if workflow2 else runner.audit_rounds(rounds + 1)):
        ctx.activity("CHECKING", round_ + 1, rounds + 1)
        problems = {k: _checks(inp, k, t, library, allowed) for k, t in current.items()}
        review = [review_item(inp, items, k, t, problems[k], apart) for k, t in current.items()]
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
        current = _owned(inp, items, current)

    if runner._engine.require_dual_approval and not workflow2:
        # Code removes what it cannot trace BEFORE the final approval, so both reviewers approve the
        # exact wording that is delivered (Codex, plan review 2026-09-29).
        cleaned = {key: tidy for key, text in current.items() if (tidy := _cleaned(inp, text, library, usable, allowed)) != text}
        if cleaned:
            stripped += [items[key]["heading"] for key in cleaned]
            current.update(cleaned)
            problems = {k: _checks(inp, k, current[k], library, allowed) for k in cleaned}
            regraded = runner.grade([review_item(inp, items, k, current[k], problems[k], apart) for k in cleaned], {**common, "vetting": vetting})
            for key in cleaned:
                grade = regraded.get(key)
                grades.pop(key, None)
                if grade is not None:
                    grades[key] = grade
                issues = [*problems[key], *(grade.issues if grade and grade.grade == "REPAIR" else [])] + ([] if grade else [NOT_REVIEWED])
                if issues:
                    unresolved[key] = issues
                else:
                    unresolved.pop(key, None)
    missing: list[str] = []
    approved_only = runner._engine.require_dual_approval or workflow2  # workflow 2: nothing the final editor did not approve
    if approved_only:
        # Only wording both reviewers approved is delivered. A revision keeps the earlier text of the
        # rest; a new chapter (or a finish) delivers what was approved and records the rest as not
        # written yet, for "Finish chapter" (owner decision 2026-09-29). Nothing approved: no document.
        approved = [k for k in items if k in current and k not in unresolved]
        missing = [k for k in items if k not in approved] if inp.step in ("CHAPTER", "COMPLETE") else []
        if base is None and (not approved or (missing and not runner._engine.partial_chapters)):
            raise PermanentStageError(
                "DOCUMENT_NOT_APPROVED",
                "PaperAid could not finish these sections to its standard: " + ", ".join(f"{items[k]['number']} {items[k]['heading']}" for k in items if k in unresolved)[:300]
                + ". No document was released and nothing was charged. Please try again.",
                # Admin-only: which sections and why, so the next failure is diagnosed from its record.
                (f"{len(approved)} of {len(items)} sections approved; not approved: "
                 + "; ".join(f"{items[k]['heading']}: {unresolved[k][0][:90]}" for k in items if k in unresolved))[:470],
            )
        for key in unresolved:
            current.pop(key, None)  # never rejected new text: _merge keeps earlier wording, a finish keeps it missing

    for key, text in current.items():
        cleaned = [evidence.strip_unsupported(p, library, usable, allowed) for p in text.paragraphs]
        table = _strip_table(inp, text, library, usable, allowed)
        if cleaned != text.paragraphs or table != text.table:
            if approved_only:  # the final guard: nothing changes after approval
                raise PermanentStageError(
                    "DOCUMENT_NOT_APPROVED", "PaperAid could not verify the final wording. No document was released and nothing was charged. Please try again.",
                    "post-review evidence cleanup would change approved wording",
                )
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
    for section in document.sections:
        section.reviewed = section.key in grades
    if approval is not None:  # the text accepted is what is left to deliver: a section not approved is not in it
        approval.accepted_sha256 = _text_hash(current)
    delivered: list[str] = []
    if base is not None and inp.step == "COMPLETE":
        document, delivered = _completed(inp, base, document)
        if not delivered:
            raise PermanentStageError(
                "NOTHING_WRITTEN", "PaperAid could not write the remaining sections this time, so your chapter is unchanged and nothing was charged.", "complete: nothing written"
            )
        warnings = [w for w in base.warnings if not w.startswith(STILL_MISSING)] + warnings
        stripped = stripped or [i.note for i in base.readiness if i.id.endswith("-TRACE") and i.status != "PASS"]
        unreviewed = _unreviewed(base, document)
    elif base is not None:
        document, kept = _merge(base, document, set(current))
        delivered = _delivered(base, document, set(current))
        # answered: changed AND passed the final review (Codex re-check H05); changed text alone is not an answer
        resolved = [k for k in delivered if k not in unresolved]
        if not resolved:
            raise PermanentStageError(
                "NOTHING_REVISED", "PaperAid could not resolve these comments this time, so your chapter is unchanged and nothing was charged.", "revise: nothing resolved"
            )
        document.revised = resolved
        # a section to align with the student's guide is done only when its revision changed it and passed review
        document.to_align = [k for k in base.to_align if k not in resolved]
        if kept:
            warnings.append(f"These sections could not be revised this time, so your earlier text is kept: {', '.join(kept)}.")
        # untouched sections keep what was known about them (Codex audit 56c4f83 H06)
        warnings = _carried_warnings(base, delivered) + warnings
        unreviewed = _unreviewed(base, document)
        stripped = stripped or [i.note for i in base.readiness if i.id.endswith("-TRACE") and i.status != "PASS"]
    if inp.step == "CHAPTER":
        document.missing = missing
    total = {k: items[k]["words"] for k in items}  # sections are weighed by their planned length
    if document.missing:
        headings = [f"{items[k]['number']} {items[k]['heading']}" for k in document.missing if k in items] or [
            f"{s.number} {s.heading}" for s in rulebook.sections(inp.rulebook, inp.chapter, inp.inputs.level, inp.plan) if s.key in document.missing
        ]
        warnings.append(f"{STILL_MISSING} {', '.join(headings)}. Finish the chapter to write them; you are charged only for the sections delivered.")
    document.readiness = (_readiness(ctx, runner, inp, document, library, bool(stripped), unreviewed) + _missing_items(inp, document.missing)
                          + research_gap_items(ctx, f"C{inp.chapter}-RESEARCH", inp.chapter))
    document.warnings = warnings
    document.approval = approval
    share: float | None = None
    if inp.step in ("CHAPTER", "COMPLETE") and approved_only:
        written = delivered if inp.step == "COMPLETE" else [k for k in items if k not in missing]
        share = sum(total.get(k, 0) for k in written) / max(1, sum(total.values()))
    if document.missing or inp.step == "COMPLETE":
        # The draft and its finishes never cost more than one chapter, however many finishes it takes
        # (Codex review 2026-09-30 #3): each charge is added to what the chapter has cost so far, and a
        # finish is priced at most at the rest. The charge is settlement's own: line x delivered share.
        line = next((ln.amount for ln in (ctx.job.quote.lines if ctx.job.quote else []) if ln.service == _line_key(inp)), 0)
        charge = round_up(line * min(1.0, share if share is not None else 1.0))
        document.full_price = base.full_price if base is not None and inp.step == "COMPLETE" else line
        document.paid = (base.paid if base is not None and inp.step == "COMPLETE" else 0) + charge
    ctx.put_json("chapter.json", document.model_dump(by_alias=True))
    if share is not None:
        ctx.update(lambda j: j.model_copy(update={"delivery": {**j.delivery, _line_key(inp): share}}))
    if base is not None and inp.step == "REVISE":
        targeted = [k for k in inp.revise if any(s.key == k for s in base.sections)]
        share = len(document.revised) / len(targeted) if targeted else 0.0
        ctx.update(lambda j: j.model_copy(update={"delivery": {**j.delivery, "REVISE": share}}))
    if warnings:
        ctx.update(lambda j: _warn(j, warnings, partial=bool(unresolved or stripped or unreviewed or document.missing) or len(document.revised) < len(inp.revise)))


STILL_MISSING = "These sections are not written yet:"


def _line_key(inp: StepInput) -> str:
    """The quote line a chapter step (or its finish) is priced and settled on."""
    return "CONCEPT" if inp.chapter == 4 else f"CHAPTER_{inp.chapter}"


def _finish_context(ctx: "StageContext", inp: StepInput) -> dict[str, Any]:
    """Show every approved section and give nearby ones most of the bounded text budget."""
    if inp.step != "COMPLETE":
        return {}
    base = _base_document(ctx, inp)
    assert inp.plan is not None
    planned = [s.key for s in rulebook.sections(inp.rulebook, inp.chapter, inp.inputs.level, inp.plan)]
    approved = {s.key for s in base.sections}
    nearby = set()
    for key in inp.only:
        if key not in planned:
            continue
        index = planned.index(key)
        nearby.update(k for k in planned[max(0, index - 1):index + 2] if k in approved)

    def excerpt(value: str, limit: int) -> str:
        if len(value) <= limit:
            return value
        head = value[:max(0, limit - 2)].rsplit(" ", 1)[0]
        return head + " …" if head else ""

    texts = {s.key: " ".join(" ".join(s.paragraphs).split()) for s in base.sections}
    budget = max(0, 9000 - sum(len(s.number) + len(s.heading) + 40 for s in base.sections))
    # Reserve a short excerpt for every section before expanding the neighbors of missing ones.
    preview = min(180, budget // max(1, 3 * len(base.sections)))
    shown = [{"number": s.number, "heading": s.heading, "text": excerpt(texts[s.key], preview)} for s in base.sections]
    budget -= sum(len(row["text"]) for row in shown)
    for s, row in zip(base.sections, shown, strict=True):
        if s.key not in nearby or budget <= 0:
            continue
        expanded = excerpt(texts[s.key], min(1500, len(row["text"]) + budget))
        budget -= max(0, len(expanded) - len(row["text"]))
        row["text"] = expanded
    return {"approvedSections": shown}


def _base_document(ctx: "StageContext", inp: StepInput) -> ChapterDocument:
    """The chapter version a revision or a finish was priced on."""
    path = inp.base if ctx.rt.files.exists(inp.base) else moved_path(inp.base)
    return ChapterDocument.model_validate_json(ctx.rt.files.get(path))


def _completed(inp: StepInput, base: ChapterDocument, written: ChapterDocument) -> tuple[ChapterDocument, list[str]]:
    """A finished chapter: the base version's sections with the newly written ones in their place in
    the chapter's order. Returns (document, the sections written now)."""
    assert inp.plan is not None
    fresh = {s.key: s for s in written.sections}
    earlier = {s.key: s for s in base.sections}
    order = [s.key for s in rulebook.sections(inp.rulebook, inp.chapter, inp.inputs.level, inp.plan)]
    order += [k for k in earlier if k not in order]
    sections = [fresh.get(k) or earlier[k] for k in order if k in fresh or k in earlier]
    cited: list[str] = []
    for section in sections:
        for field in [*section.paragraphs, section.table_caption, *[c for row in section.table or [] for c in row]]:
            cited += [i for i in evidence.cited_ids(field) if i not in cited]
    words = sum(len(evidence.ANY_TOKEN.sub(" ", p).split()) for s in sections for p in s.paragraphs)
    done = [k for k in base.missing if k in fresh]
    document = ChapterDocument(
        number=base.number, title=base.title, plan_version=base.plan_version, sections=sections, cited=cited, words=words,
        missing=[k for k in base.missing if k not in fresh], to_align=list(base.to_align),
    )
    return document, done


def _missing_items(inp: StepInput, missing: list[str]) -> list[ReadinessItem]:
    """Each section not written yet is a MISSING readiness item, settled by code."""
    if not missing or inp.plan is None:
        return []
    return [
        ReadinessItem(id=f"C{inp.chapter}-{s.key}-WRITTEN", question=f"Is {s.number} {s.heading} written?", status="MISSING", basis="CODE", note="Finish the chapter to write it.")
        for s in rulebook.sections(inp.rulebook, inp.chapter, inp.inputs.level, inp.plan)
        if s.key in missing
    ]


def _revision(
    ctx: "StageContext", runner: ProposalRunner, inp: StepInput, library: dict[str, EvidenceItem], common: dict[str, Any]
) -> tuple[ChapterDocument, dict[str, dict[str, Any]], dict[str, SectionText]]:
    """A chapter revised from supervisor comments: the sections they concern, from the current
    version, with the comments as what the writer must fix (the revision is the rewrite; the usual
    review and at most two fixes follow). The comments are also points the reviewer checks."""
    base_path = inp.base if ctx.rt.files.exists(inp.base) else moved_path(inp.base)
    base = ChapterDocument.model_validate_json(ctx.rt.files.get(base_path))
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
    kept = runner._engine.editor
    if kept and ctx.has("revised.json"):  # written before a wait for the final editor
        fixes = {k: SectionText.model_validate(v) for k, v in ctx.get_json("revised.json").items()}
    else:
        fixes = runner.fix(first, common)
        if kept:
            ctx.put_json("revised.json", {k: v.model_dump() for k, v in fixes.items()})
    for key, fixed in fixes.items():
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
    merged = ChapterDocument(number=base.number, title=base.title, plan_version=revised.plan_version, sections=sections, cited=cited, words=words,
                             to_align=[k for k in base.to_align if k not in fresh],
                             # what the chapter still lacks and has cost is not the revision's to forget (Codex audit, finding 5)
                             missing=list(base.missing), full_price=base.full_price, paid=base.paid)
    return merged, [f"{s.number} {s.heading}" for s in base.sections if s.key in keys and s.key not in fresh]


def _delivered(base: ChapterDocument, merged: ChapterDocument, targeted: set[str]) -> list[str]:
    """The targeted sections whose text a revision actually changed."""
    before = {s.key: (s.paragraphs, s.table, s.table_caption) for s in base.sections}
    return [s.key for s in merged.sections if s.key in targeted and (s.paragraphs, s.table, s.table_caption) != before.get(s.key)]


def _heading(s: ChapterSection) -> str:
    return f"{s.number} {s.heading}"


def _carried_warnings(base: ChapterDocument, delivered: list[str]) -> list[str]:
    """The earlier version's warnings that still apply: all but those only about revised sections."""
    revised = [_heading(s) for s in base.sections if s.key in delivered]
    untouched = [_heading(s) for s in base.sections if s.key not in delivered]
    return [w for w in base.warnings if not any(h in w for h in revised) or any(h in w for h in untouched)]


def _unreviewed(base: ChapterDocument, merged: ChapterDocument) -> list[str]:
    """Every final section not known to have been reviewed: revised ones from this run, untouched
    ones from their own record (or, for a version written before sections recorded it, from that
    version's review result)."""
    earlier_all_reviewed = all(i.status == "PASS" for i in base.readiness if i.id.endswith("-REVIEWED"))
    return [_heading(s) for s in merged.sections if s.reviewed is False or (s.reviewed is None and not earlier_all_reviewed)]


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
        path = path if ctx.rt.files.exists(path) else moved_path(path)
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
    items += _core_checks(inp, document, others_words(ctx, inp) if n == 3 else 0)
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
                id="C4-LENGTH", question="Is the concept paper about five pages or less (estimated)?", basis="CODE", chapter=4, status="PASS" if pages <= 5 else "NEEDS_REVIEW",
                note=f"About {pages:.1f} pages of text at double spacing, estimated from its words; check the page count in Word.",
            )
        )
        count = len(sources)
        items.append(
            ReadinessItem(
                id="C4-REFS", question="Does it cite five to eight sources?", basis="CODE", chapter=4, status="PASS" if 5 <= count <= 8 else "NEEDS_REVIEW",
                note=f"{count} confirmed sources cited; the annotated list is built from them.",
            )
        )
        items += _concept_checks(inp, document)
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
        if inp.plan.sampling_assumed:  # no consent is asked at Start (owner decision 2026-10-08): confirmed here
            items.append(
                ReadinessItem(
                    id="C3-ASSUMED", question="Do you confirm the sample-size settings PaperAid assumed?", basis="AUTHOR", chapter=3, status="NEEDS_REVIEW",
                    note=("You gave no figures for these, so the standard settings were used and the chapter says so: "
                          + "; ".join(inp.plan.sampling_assumed) + ". Confirm them with your supervisor, or set your own in the plan.")[:600],
                )
            )
    return items


def others_words(ctx: "StageContext", inp: StepInput) -> int:
    """The words of the proposal's other chapters (One and Two), for the length check on Chapter Three."""
    total = 0
    for number, path in inp.chapters.items():
        path = path if ctx.rt.files.exists(path) else moved_path(path)
        if int(number) in (1, 2) and ctx.rt.files.exists(path):
            total += ChapterDocument.model_validate_json(ctx.rt.files.get(path)).words
    return total


def _core_checks(inp: StepInput, document: ChapterDocument, other_words: int) -> list[ReadinessItem]:
    """The handbook's core requirements, checked by code on the delivered text (rulebook v2 on): the general
    and specific objectives and the questions exactly as approved and in the allowed number; questions in the
    present or future where they can be; the proposal's length for the level. A failed core requirement is
    MISSING and blocks a complete export; the rest are for the student to review."""
    assert inp.plan is not None
    plan, n, items = inp.plan, inp.chapter, []
    kinds = _owned_kinds(inp)
    by_key = {s.key: s for s in document.sections}
    for key, kind in kinds.items():
        section = by_key.get(key)
        if section is None:
            continue
        expected = plan_statements(plan, kind, section.number)
        present = all(line in section.paragraphs for line in expected)
        if kind in ("objectives", "specific_objectives"):
            low, high = rulebook.objective_range(inp.rulebook, inp.inputs.level, inp.inputs.four_objectives, inp.goal == "CONCEPT")
            count = len([o for o in plan.specific_objectives if o.strip()])
            within = low <= count <= high or not rulebook.enforced_counts(inp.rulebook)
            ok = present and (bool(plan.purpose.strip()) or kind == "specific_objectives") and within
            allowed = f"{low}" if low == high else f"{low} to {high}"
            items.append(ReadinessItem(
                id=f"C{n}-STATED-OBJECTIVES", question="Are the general objective and the specific objectives stated as approved?", basis="CODE", chapter=n,
                status="PASS" if ok else "MISSING",
                note=(f"The general objective and {count} specific objectives, word for word from the approved plan." if ok else
                      "The general objective or a specific objective is missing or differs from the approved plan." if not present else
                      f"This takes {allowed} specific objectives; the plan has {count}.")))
        else:
            aligned = len([q for q in plan.research_questions if q.strip()]) == len([o for o in plan.specific_objectives if o.strip()])
            primary = bool(plan.primary_question.strip()) or not rulebook.load(inp.rulebook).get("primary_question")
            ok = present and aligned and primary
            items.append(ReadinessItem(
                id=f"C{n}-STATED-QUESTIONS", question="Is there a primary research question, with one specific question per objective, as approved?", basis="CODE", chapter=n,
                status="PASS" if ok else "MISSING",
                note="Word for word from the approved plan, one per specific objective." if ok else "The primary question or a specific question is missing, or they do not match the objectives one to one."))
            if plan.questions_kind == "QUESTIONS":
                past = [q for q in [plan.primary_question, *plan.research_questions] if q.strip() and rulebook.past_tense(q)]
                items.append(ReadinessItem(
                    id=f"C{n}-QUESTION-TENSE", question="Are the research questions in the present or future tense?", basis="CODE", chapter=n,
                    status="NEEDS_REVIEW" if past else "PASS",
                    note=("Some questions are in the past tense; keep them in the present or future unless the study is about past events: " + " | ".join(past))[:400]
                    if past else "No question is in the past tense."))
    if n == 3 and rulebook.enforced_counts(inp.rulebook):
        book = rulebook.load(inp.rulebook)
        low, high = book["levels"][inp.inputs.level]["pages"]
        pages = (other_words + document.words) / book["words_per_page"]
        items.append(ReadinessItem(
            id="C3-LENGTH", question=f"Is the proposal within {low} to {high} pages for its level?", basis="CODE", chapter=3,
            status="PASS" if low <= pages <= high else "NEEDS_REVIEW",
            note=f"About {pages:.0f} pages for Chapters One to Three, estimated at {book['words_per_page']} words a page; check the page count in Word."))
    return items


ETHICS = re.compile(r"\b(ethic|consent|approval|confidential|anonym)", re.I)


def _concept_checks(inp: StepInput, document: ChapterDocument) -> list[ReadinessItem]:
    """Two checks from the rulebook's research concept note (CN-032, CN-034), made by code on the
    concept paper: each objective has its question and a method that answers it, and a study with
    people says how it will be ethical."""
    assert inp.plan is not None
    plan = inp.plan
    answered = {row.objective for row in plan.alignment if row.collection.strip() and row.analysis.strip()}
    missing = [n for n in range(1, len(plan.specific_objectives) + 1) if n not in answered]
    paired = len(plan.research_questions) == len(plan.specific_objectives)
    items = [
        ReadinessItem(
            id="C4-METHODS", question="Your plan gives each objective its research question and a method that answers it", basis="CODE", chapter=4,
            status="PASS" if paired and not missing else "NEEDS_REVIEW",
            note="Every objective has a question, data collection and analysis in the plan." if paired and not missing
            else ("Objectives without a method in the plan: " + ", ".join(str(n) for n in missing) + "." if missing else "The plan has a different number of questions and objectives."),
        )
    ]
    with_people = plan.study_type not in ("SECONDARY", "NON_EMPIRICAL")
    if with_people:
        text = " ".join(p for s in document.sections for p in s.paragraphs)
        mentioned = bool(ETHICS.search(text))
        items.append(
            ReadinessItem(
                id="C4-ETHICS", question="The study says how it will protect participants (approval and consent)", basis="CODE", chapter=4,
                status="PASS" if mentioned else "NEEDS_REVIEW",
                note="Ethics is mentioned." if mentioned else "Add a sentence on ethical approval and informed consent to the methodology.",
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
        ctx.assert_owner()
        evidence_path = f"{project.storage_prefix()}/evidence/{job_id}-{ctx.owner}.json"
        ctx.rt.files.put(evidence_path, ctx.get_bytes("evidence.json"), "application/json")
    chapter_path = ""
    document: ChapterDocument | None = None
    if inp.step in ("CHAPTER", "REVISE", "COMPLETE"):
        document = ChapterDocument.model_validate(ctx.get_json("chapter.json"))
        ctx.assert_owner()
        chapter_path = f"{project.storage_prefix()}/chapters/{inp.chapter}/{job_id}-{ctx.owner}.json"
        ctx.rt.files.put(chapter_path, document.model_dump_json(by_alias=True).encode(), "application/json")
    planned = ctx.get_json("plan.json") if inp.step == "PLAN" else None
    plan = ProposalPlan.model_validate(planned["plan"]) if planned else None
    review = PlanReview.model_validate(planned["review"]) if planned and planned.get("review") else None  # None: an older engine's plan
    book = ctx.get_json("profile.json")["profile"] if inp.step == "PROFILE" else None
    aligned: dict[int, tuple[int, str, ChapterDocument]] = {}  # chapter -> (the version it was made from, path, document)
    aligned_plan = project.plan_version  # the plan the chapters were restructured with
    if book is not None:  # written once under its own id; a retry writes the same file again
        ctx.assert_owner()
        ctx.rt.files.put(rulebook.stored_path(book["id"]), json.dumps(book).encode(), "application/json")
        if project.plan is not None:  # a guide read after chapters were written: each is restructured to it
            for stored in project.chapters:
                if stored.number == CONCEPT_NUMBER or not stored.current:
                    continue
                base_path = next(v.path for v in stored.versions if v.version == stored.current)
                base_path = base_path if ctx.rt.files.exists(base_path) else moved_path(base_path)
                doc = align_document(ChapterDocument.model_validate_json(ctx.rt.files.get(base_path)), project.rulebook, book["id"], project.inputs.level, project.plan)
                path = f"{project.storage_prefix()}/chapters/{stored.number}/{job_id}-{ctx.owner}-aligned.json"
                ctx.rt.files.put(path, doc.model_dump_json(by_alias=True).encode(), "application/json")
                aligned[stored.number] = (stored.current, path, doc)
    written_meanwhile = False
    library_paths = list(dict.fromkeys([*project.evidence_files, *([evidence_path] if evidence_path else [])]))
    usable = sum(1 for i in load_library(ctx.rt.files, library_paths).values() if i.usable)
    candidate = False
    kept_choice = False
    left_open: list[str] = []

    def publish(p: Project) -> Project | None:
        nonlocal candidate
        if p.deleting:
            return None
        if job_id in p.published:  # a retry after this job's transaction already committed: settle it, never refund it
            return p
        if not structure_current(p, inp):
            raise PermanentStageError(  # replaced while this step ran: nothing is saved, nothing charged (Codex review #2)
                "INPUTS_CHANGED", "Your institution's guide or proposal structure changed while this step was running, so nothing was saved and nothing was charged. Start it again.",
                "guide or rulebook changed during the step",
            )
        nonlocal written_meanwhile, kept_choice
        p.published.append(job_id)
        if book is not None:
            p.profiles = list(dict.fromkeys([*p.profiles, book["id"]]))
            written = {c.number: c.current for c in p.chapters if c.current and c.number != CONCEPT_NUMBER}
            if {n: v for n, (v, _, _) in aligned.items()} != written or (aligned and p.plan_version != aligned_plan):  # Codex audit 29343c2 #5
                raise PermanentStageError(  # a chapter changed while the guide was read: nothing saved, nothing charged
                    "INPUTS_CHANGED", "A chapter or your plan changed while PaperAid read your guide, so nothing was saved and nothing was charged. Start it again.",
                    "chapter changed during the profile step",
                )
            p.rulebook = book["id"]
            if not written:
                p.citation = book["default_citation"]  # written chapters keep the style they were written in
            for number, (_, path, doc) in sorted(aligned.items()):
                chapter_state = p.chapter(number)
                version = len(chapter_state.versions) + 1
                chapter_state.versions.append(StoredChapterVersion(
                    version=version, job_id=job_id, words=doc.words, plan_version=p.plan_version, path=path, note=ALIGNED_NOTE,
                    passed=sum(1 for r in doc.readiness if r.status in ("PASS", "NOT_APPLICABLE")), total=len(doc.readiness)))
                chapter_state.current, chapter_state.approved = version, False
        if evidence_path and evidence_path not in p.evidence_files:
            p.evidence_files.append(evidence_path)
        p.evidence_count = usable
        if plan is not None:
            if p.auto and ctx.job.selection.bundled:
                p.auto_next = ctx.job.id  # one Start: the first chapter (or a stop) is still to happen
            if p.plan_version == inp.plan_version:
                p.plan, p.plan_status, p.plan_version = plan, "DRAFT", p.plan_version + 1
                p.candidate_plan = None
                p.plan_review = review.model_copy(update={"plan_version": p.plan_version}) if review else None
            else:  # the student edited their plan meanwhile: never overwrite it
                p.candidate_plan, candidate = plan, True
                p.candidate_review = review
            if review is not None and review.outcome != "APPROVED":
                p.auto_chapter_one = False  # an unapproved plan never starts Chapter One by itself
        if document is not None:
            state = p.chapter(inp.chapter)
            version = len(state.versions) + 1
            state.versions.append(
                StoredChapterVersion(
                    version=version, job_id=job_id, words=document.words, plan_version=inp.plan_version, path=chapter_path,
                    note=(inp.note or ("Revised from your supervisor's comments" if inp.step == "REVISE" else "Finished: the sections still to write" if inp.step == "COMPLETE" else ""))[:300],
                    passed=sum(1 for r in document.readiness if r.status in ("PASS", "NOT_APPLICABLE")), total=len(document.readiness),
                )
            )
            if inp.step in ("REVISE", "COMPLETE") and state.current != inp.base_version:
                kept_choice = True  # the student chose another version meanwhile: saved, not made current (H07)
            else:
                state.current, state.approved = version, False
            left_open.clear()
            for comment in p.feedback:
                if comment.id not in inp.comment_signatures or comment.status != "OPEN":
                    continue
                answered = [k for k in comment.sections if k in inp.revise]
                # A chapter-wide request without named sections is not complete after one section changes.
                # Every targeted section must change and pass its own review before it is marked applied.
                whole = {s.key for s in document.sections} <= set(comment.sections)
                # sections whose statements come from the approved plan change only with the plan, never by a revision
                owned = _owned_kinds(inp)
                targets = [k for k in (comment.required if whole and comment.required else comment.sections) if k not in owned]
                done = bool(targets) and all(k in document.revised for k in targets)
                if comment.signature() == inp.comment_signatures[comment.id] and answered and done:
                    comment.status, comment.applied_in = "APPLIED", version
                else:
                    left_open.append(comment.text[:60])
        p.updated_at = utcnow()
        return p

    gone = False

    def finish(j: Job, w: Wallet, p: Project | None) -> tuple[Job, Wallet, Project] | None:
        """Publish, complete and settle as one unit (Codex audit 2026-10-01, as works already do): a
        published result is never refunded by a later failure, and a refunded step is never published."""
        nonlocal gone, candidate, kept_choice, written_meanwhile
        candidate = kept_choice = written_meanwhile = False  # the transaction may run more than once
        left_open.clear()
        gone = p is None or p.deleting
        if p is None or p.deleting:
            return None
        if j.status != JobStatus.PROCESSING or j.stage != Stage.EXPORTING or j.lease_owner != ctx.owner:
            return None  # failed, cancelled or already completed meanwhile: nothing more to do
        already = job_id in p.published
        if publish(p) is None:
            gone = True
            return None
        notes = ["You edited your plan while PaperAid was drafting one, so the new plan is kept alongside yours for you to compare."] if candidate else []
        if kept_choice:
            notes.append("You chose another version while PaperAid was revising, so the revision is saved as a new version without replacing your choice.")
        if left_open:
            notes.append(f"{len(left_open)} of the requested changes stay open because their sections were not revised or were changed meanwhile.")
        if written_meanwhile:
            notes.append("A chapter was written before your institution's profile was ready, so your proposal keeps its current structure.")
        j = _warn(j, notes if not already else [], partial=False)
        j.outcome = j.outcome or "FULL"
        if Stage.EXPORTING not in j.completed_stages:
            j.completed_stages.append(Stage.EXPORTING)
        j.attempts, j.lease_until, j.stage, j.lease_owner = 0, None, None, ""
        state.transition(j, JobStatus.COMPLETED, "Completed with warnings" if j.outcome == "PARTIAL" else "Completed")
        settle_completed(j, w)
        return j, w, p

    ctx.rt.store.update_job_wallet_and_project(ctx.job.id, inp.project_id, finish)
    if gone:
        raise PermanentStageError("PROJECT_DELETED", "This proposal was deleted before the step finished, so nothing was charged.", "project deleting at export")
    if inp.step == "PLAN":
        from app.proposals import service as project_service

        project_service.continue_after_plan(ctx.rt, inp.project_id, ctx.job.id)  # one Start: the first chapter follows an approved plan


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
