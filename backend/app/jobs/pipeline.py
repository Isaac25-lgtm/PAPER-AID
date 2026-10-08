"""The worker. Each queue task runs exactly one stage of one job:

  claim lease → run stage → save its artifact → mark stage complete → enqueue the next stage

Duplicate deliveries find the lease held (or the job finished) and exit without doing anything.
A crash leaves an expiring lease; the next delivery or the reconciler resumes from the last
completed stage. Inside a stage, every model response is saved under a fingerprint of its
request, so re-running an interrupted stage reuses responses already paid for. The only call
that can be paid twice is one interrupted between the provider billing it and the response
being saved; the job's spend ceiling bounds even that."""

import hashlib
import json
import logging
import random
import re
import secrets
from datetime import timedelta
from pathlib import PurePosixPath
from typing import Any, Literal

from app.ai.orchestration import (
    NOT_RETURNED,
    AIRunner,
    ClaimCandidate,
    FoundSource,
    PlanItem,
    ResearchAnswer,
    ReviewOutcome,
    Revision,
    Target,
    priced_engine,
)
from app.ai.styles import writing_brief
from app.analysis import fetch, paper_checks, references, research, signals, structure
from app.core.errors import CapacityWait, InvalidDocument, PermanentStageError, StageError
from app.core.logging import job_id as job_id_var
from app.core.logging import log
from app.documents import groups as paragraph_groups
from app.documents import protect
from app.documents.docx_io import apply_group_rewrites, apply_revisions, read_docx
from app.documents.intake import inspect_upload
from app.documents.model import DocumentModel
from app.formatting.apply import add_logo, apply_formatting
from app.formatting.guideline import MAX_GUIDE_WORDS, to_spec
from app.formatting.presets import PRESETS, with_custom
from app.jobs import state
from app.jobs.models import (
    Activity,
    AnalysisResult,
    ChangedBlock,
    CheckedClaim,
    Finding,
    FormattingResult,
    FormattingRule,
    Job,
    JobEvent,
    JobFailure,
    JobStatus,
    LatexResult,
    ModelCall,
    RefinementResult,
    ResearchResult,
    ServiceId,
    Source,
    Stage,
    StageTiming,
    StoredOutput,
    Wallet,
    utcnow,
)
from app.jobs.service import DOCX_TYPE, processing_enabled, task_name
from app.latex import package as latex
from app.pricing import credits
from app.pricing.billing import refund_job, settle_completed
from app.pricing.quote import Passage, bound_quote, to_ugx
from app.proposals import pipeline as proposal_pipeline
from app.proposals import review as proposal_review
from app.reports.builder import change_report, source_report, writing_report
from app.runtime import Runtime
from app.works import pipeline as work_pipeline

logger = logging.getLogger("paperaid.worker")
LEASE = timedelta(minutes=25)
# A stage stops starting new model calls after this long and hands the rest to a fresh delivery,
# which replays finished calls from the response cache. Keeps every delivery inside the lease
# and the 30-minute task deadline, however many batches a long paper needs.
STAGE_WORK_LIMIT = timedelta(minutes=20)
GENERIC_FAILURE = "Something went wrong while processing your paper. PaperAid recorded the problem so it can be fixed."
ESTIMATE_FAILURE = "We couldn't estimate this paper right now. Your credits were returned; please try again shortly."
REFINE_STAGES = (Stage.PLANNING, Stage.REFINING, Stage.REDRAFTING, Stage.AUDITING)


class StageContinues(Exception):  # noqa: N818 - a signal, not an error
    """Raised between model calls to hand the rest of a long stage to a new delivery."""


class StageContext:
    """One delivery's view of a job. `phase` is "estimate" for the paid scan that sizes a
    refinement before it is quoted, and "job" once the student has accepted the quote."""

    def __init__(self, rt: Runtime, job: Job, phase: Literal["estimate", "job"] = "job"):
        self.rt = rt
        self.job = job
        self.phase = phase
        self.prefix = job.storage_prefix()
        self.owner = job.estimate.lease_owner if phase == "estimate" and job.estimate else job.lease_owner
        self.started = utcnow()
        self._paid_calls = 0

    def heartbeat(self) -> None:
        """Before each paid call: renew the lease, or stop if the job is no longer ours (cancelled,
        failed) or this delivery has worked long enough. At least one call is made per delivery, so
        a continuation always makes progress."""
        now = utcnow()
        if self._paid_calls and now - self.started > STAGE_WORK_LIMIT:
            raise StageContinues()
        stage = self.job.stage
        run_id = self.job.estimate.id if self.phase == "estimate" and self.job.estimate else None

        def renew(j: Job) -> Job | None:
            if self.phase == "estimate":
                if (j.status != JobStatus.DRAFT or j.estimate is None or j.estimate.id != run_id
                        or j.estimate.status != "RUNNING" or j.estimate.lease_owner != self.owner):
                    return None
                j.estimate.lease_until = now + LEASE
                return j
            if j.status != JobStatus.PROCESSING or j.stage != stage or j.lease_owner != self.owner:
                return None
            j.lease_until = now + LEASE
            return j

        if self.rt.store.update(self.job.id, renew) is None:
            raise StageContinues()
        self._paid_calls += 1

    # artifacts -------------------------------------------------------------------------
    def assert_owner(self) -> None:
        current = self.rt.store.get(self.job.id)
        if self.phase == "estimate":
            if (current is None or current.status != JobStatus.DRAFT or current.estimate is None
                    or current.estimate.status != "RUNNING" or current.estimate.lease_owner != self.owner):
                raise StageContinues()
        elif current is None or current.status != JobStatus.PROCESSING or current.stage != self.job.stage or current.lease_owner != self.owner:
            raise StageContinues()

    def _artifact(self, name: str) -> str:
        return self.job.artifact_paths.get(name, f"{self.prefix}/internal/{name}")

    def _put_artifact(self, name: str, data: bytes, media: str) -> None:
        self.assert_owner()
        path = f"{self.prefix}/internal/attempts/{self.owner}/{name}"
        self.rt.files.put(path, data, media)
        self.update(lambda j: _artifact_written(j, name, path))

    def put_json(self, name: str, data: Any) -> None:
        self._put_artifact(name, json.dumps(data, ensure_ascii=False).encode(), "application/json")

    def get_json(self, name: str) -> Any:
        return json.loads(self.get_bytes(name))

    def has(self, name: str) -> bool:
        return self.rt.files.exists(self._artifact(name))

    def put_bytes(self, name: str, data: bytes) -> None:
        self._put_artifact(name, data, DOCX_TYPE)

    def get_bytes(self, name: str) -> bytes:
        return self.rt.files.get(self._artifact(name))

    def document(self) -> DocumentModel:
        return DocumentModel.model_validate(self.get_json("document.json"))

    def update(self, mutate) -> Job:
        def owned(j: Job) -> Job | None:
            if self.phase == "job" and (j.status != JobStatus.PROCESSING or j.stage != self.job.stage or j.lease_owner != self.owner):
                return None
            if self.phase == "estimate" and (j.status != JobStatus.DRAFT or j.estimate is None or j.estimate.status != "RUNNING"
                                              or self.job.estimate is None or j.estimate.id != self.job.estimate.id
                                              or j.estimate.lease_owner != self.owner):
                return None
            return mutate(j)

        updated = self.rt.store.update(self.job.id, owned)
        if updated is None:
            raise StageContinues()
        self.job = updated
        return updated

    def ai(self, runner: type[AIRunner] = AIRunner) -> AIRunner:
        def record(call: ModelCall) -> None:
            def add(j: Job) -> Job:
                j.model_calls = (j.model_calls + [call])[-200:]
                j.cost_usd = round(j.cost_usd + call.cost_usd, 6)
                j.reserved_usd = round(j.reserved_usd + call.reserved_usd, 6)
                if call.phase == "estimate":
                    j.estimate_cost_usd = round(j.estimate_cost_usd + call.cost_usd, 6)
                elif call.stage in REFINE_STAGES:
                    j.refine_cost_usd = round(j.refine_cost_usd + call.cost_usd, 6)
                return j

            self.update(add)

        estimate = self.job.estimate if self.phase == "estimate" else None

        def spent() -> float:
            current = self.rt.store.get(self.job.id)
            if current is None:
                return 0.0
            if estimate is not None:
                return current.estimate_cost_usd - estimate.cost_base_usd + current.reserved_usd
            return current.cost_usd - current.estimate_cost_usd + current.reserved_usd

        budget = estimate.budget_usd if estimate is not None else self.job.budget_usd
        # The run executes with the engine it was priced with (its estimate's, then its quote's).
        engine = estimate.engine if estimate is not None else self.job.quote.engine if self.job.quote else None
        from app.jobs import capacity

        gate = capacity.gate(self.rt.store, self.rt.settings, self.job.id) if self.rt.settings.capacity_gate else None  # estimates too (Codex audit, finding 11)
        return runner(self.rt.settings, record, spent, budget, cache=_ResponseCache(self), heartbeat=self.heartbeat, phase=self.phase, engine=engine, gate=gate)

    def activity(self, kind: str, done: int = 0, total: int = 0, note: str = "") -> None:
        """Tell the student what the stage is doing now (speed plan 2026-10-08). Never fails the stage."""
        self.update(lambda j: _set(j, activity=Activity(kind=kind, done=done, total=total, note=note)))


class _ResponseCache:
    """Saved model responses for this job, keyed by request fingerprint (see app.ai.orchestration)."""

    def __init__(self, ctx: StageContext):
        self._ctx = ctx

    def get(self, key: str) -> str | None:
        name = f"calls/{key}.json"
        return self._ctx.get_bytes(name).decode("utf-8") if self._ctx.has(name) else None

    def put(self, key: str, text: str) -> None:
        self._ctx._put_artifact(f"calls/{key}.json", text.encode("utf-8"), "application/json")


def _artifact_written(job: Job, name: str, path: str) -> Job:
    job.artifact_paths[name] = path
    return job


# --- stages -------------------------------------------------------------------------------


def stage_extracting(ctx: StageContext) -> None:
    quote = ctx.job.quote
    assert quote is not None
    model = _extract(ctx, quote.source_sha256, quote.guideline_sha256, quote.selection.formatting)
    if model.warnings:
        ctx.update(lambda j: _add_warnings(j, model.warnings))


def _extract(ctx: StageContext, source_sha: str, guide_sha: str | None, formatting: str) -> DocumentModel:
    """Re-validate the exact files that were priced and save the document (and guide) models."""
    job, settings = ctx.job, ctx.rt.settings
    assert job.source is not None
    data = ctx.rt.files.get(job.source.path)
    if hashlib.sha256(data).hexdigest() != source_sha:
        raise PermanentStageError("SOURCE_CHANGED", "Your file changed after it was priced. Please start a new job.")
    try:  # the worker repeats every security check; it never trusts the upload step alone
        model = inspect_upload(data, job.source.name, settings.max_upload_bytes, settings.max_words, settings.max_pdf_pages)
    except InvalidDocument as exc:
        raise PermanentStageError(exc.code, exc.message) from exc
    ctx.put_json("document.json", model.model_dump())
    if formatting == "TEMPLATE_FORMAT":
        if job.guideline is None:
            raise PermanentStageError("NO_GUIDELINE", "This job needs your university's formatting guide. Please start a new job and upload it.")
        guide_bytes = ctx.rt.files.get(job.guideline.path)
        if hashlib.sha256(guide_bytes).hexdigest() != guide_sha:
            raise PermanentStageError("SOURCE_CHANGED", "Your guide changed after it was priced. Please start a new job.")
        try:
            guide = inspect_upload(guide_bytes, job.guideline.name, settings.max_upload_bytes, MAX_GUIDE_WORDS, settings.max_pdf_pages, min_words=20)
        except InvalidDocument as exc:
            raise PermanentStageError(exc.code, f"Your formatting guide couldn't be used: {exc.message}") from exc
        ctx.put_json("guide.json", {"text": "\n".join(b.text for b in guide.blocks)})
    return model


def _estimate_artifacts(ctx: StageContext) -> dict[str, Any] | None:
    """The analysis, targets and draft plan the job's estimate paid for, if its quote came from
    one. Reusing them means no change to PaperAid between estimate and submission (prompts,
    rules, code) can make the job pay for that work again (Codex audit #7)."""
    quote = ctx.job.quote
    name = f"estimates/{quote.estimate_id}.json" if quote is not None and quote.estimate_id else None
    return ctx.get_json(name) if name and ctx.has(name) else None


def stage_analysing(ctx: StageContext) -> None:
    model = ctx.document()
    saved = _estimate_artifacts(ctx)
    if saved is not None:
        ctx.put_json("analysis.json", saved["analysis"])
        result, coverage_warning = AnalysisResult.model_validate(saved["analysis"]["result"]), saved["coverageWarning"]
    else:
        result, coverage_warning = _analyse(ctx, model)
    checks = paper_checks.check(model)  # the paper's integrity, reported apart from AI-likeness
    review, review_warning = _academic_review(ctx, model) if _runs_academic(ctx.job) else ([], None)
    result = result.model_copy(update={"review": review + structure.formatting_findings(model)})
    protected = structure.protected_summary(model)
    verified = references.verify_all(model) if ctx.job.selection.academic else None

    def save(j: Job) -> Job:
        j.analysis = result
        j.paper_checks = checks
        j.protected = protected
        j.references = verified
        if review_warning:  # part of the paper was not reviewed: a partial result, charged for what was (M24)
            _add_warnings(j, [review_warning])
            j.outcome = "PARTIAL"
            j.delivery = {**j.delivery, "ACADEMIC": 0.5}
        if coverage_warning:
            j.outcome = "PARTIAL"
            _add_warnings(j, [coverage_warning])
        if result.coverage_complete is False and j.selection.writing == "AI_CHECK":
            # no complete result, no charge for the check (owner decision 2026-09-29); other parts still count
            j.delivery = {**j.delivery, "AI_CHECK": 0.0}
            _add_warnings(j, [NOT_CHARGED_CHECK])
        return j

    ctx.update(save)


NOT_CHARGED_CHECK = "You were not charged for the writing check, because it could not assess every passage."


def _runs_academic(job: Job) -> bool:
    """The academic review runs only for jobs priced with it (Codex audit 56c4f83 M28): a job priced
    before the step existed has no frozen prompt for it and never paid for it."""
    engine = job.quote.engine if job.quote else None
    return job.selection.academic and (engine is None or "academic" in engine.prompts)


ANCHOR = re.compile(r"objective|question|hypothes|\baims?\b|purpose", re.I)
SAFE_ACADEMIC = {"OVERCLAIMING", "EXCESSIVE_HEDGING", "VAGUE_WORDING", "TENSE_INCONSISTENCY", "WEAK_FLOW"}


def _academic_review(ctx: StageContext, model: DocumentModel) -> tuple[list[Finding], str | None]:
    """Academic, evidence and methodology findings from the lead, with the study's objectives as
    context. Rewording findings (overclaiming, vague wording, tense) are safe to fix; evidence and
    methodology need the student's judgement."""
    prose = signals.analysable(model)
    if not prose:
        return [], None
    anchors, words = [], 0
    for block in model.blocks:
        if block.kind in ("paragraph", "list_item") and ANCHOR.search(block.section or "") and words < 600:
            anchors.append(block.text)
            words += block.words
    passages = [{"id": b.id, "section": b.section or "Body", "text": b.text} for b in prose]
    runner = ctx.ai()
    items = runner.academic_review(passages, model.outline(), anchors)
    blocks = model.by_id()
    findings = [
        Finding(
            id=f"{i.id}-a{n}",
            block_id=i.id,
            section=blocks[i.id].section or "Body",
            reason=i.code,  # type: ignore[arg-type]
            severity=i.severity,
            excerpt=i.excerpt[:280],
            explanation=i.explanation,
            suggestion=i.suggestion,
            category=i.category,
            safe=i.category == "ACADEMIC" and i.code in SAFE_ACADEMIC,
        )
        for n, i in enumerate(items, start=1)
    ]
    warning = "The academic review reached this job's spending limit before it covered the whole paper, so some sections were not reviewed." if runner.budget_reached else None
    return findings, warning


def _analyse(ctx: StageContext, model: DocumentModel, saved_name: str = "analysis.json") -> tuple[AnalysisResult, str | None]:
    """Stages 2–4 of the revised algorithm: PaperAid measures writing signals, then the lead
    confirms or rejects each one in context, adds what the rules missed and marks passages that
    must not be rewritten. Saves analysis.json. The estimate runs this too (without showing the
    result), so the job replays the lead's answer from the cache."""
    runner = ctx.ai()
    found = signals.scan(model)
    block_signals = found.blocks
    passages = [
        {"id": s.block.id, "section": s.block.section or "Body", "sectionType": s.kind, "text": s.block.masked or s.block.text, "signals": s.evidence()}
        for s in block_signals
    ]
    model_results, seen = runner.analyse(passages, model.outline(), found.evidence(), after=saved_name != "analysis.json")
    result = signals.aggregate(block_signals, found.excluded_words, _method(ctx, "analysis"))
    submitted, covered = len(block_signals), len(seen)
    coverage_warning = None
    if submitted == 0:
        coverage_warning = "This paper has no body passages of at least 25 words, so its writing could not be assessed."
    if covered < submitted:
        coverage_warning = (
            f"PaperAid could fully assess only {covered} of {submitted} passages. The findings for the assessed passages are listed."
            if covered
            else "PaperAid could not assess this paper's writing this time."
        )
        method = f"PaperAid writing-pattern signals and AI analysis ({covered} of {submitted} passages)" if covered else "PaperAid writing-pattern signals only"
        result = result.model_copy(update={"method": method})
    rejected: dict[str, list[str]] = {}
    scores: dict[str, float] = {}
    if seen:
        # New engines count only explicit judgments by every required checker. Older frozen
        # prompts permitted omitted LOW passages; only those engines retain that interpretation.
        scores = {bid: signals.MODEL_SCORE["low"] for bid in seen}
        for s in block_signals:
            judgment = model_results.get(s.block.id)
            if judgment is None:
                continue
            item = judgment.answer
            scores[s.block.id] = judgment.score
            dropped = {h.rule for h in s.hits} & set(item.rejected)
            if dropped:  # false positives in context: they no longer count or show
                rejected[s.block.id] = sorted(dropped)
                s.hits = [h for h in s.hits if h.rule not in dropped]
                s.rescore()
            if s.findings:
                s.findings[0].explanation, s.findings[0].suggestion = item.explanation or s.findings[0].explanation, item.suggestion or s.findings[0].suggestion
            covered_reasons = {f.reason for f in s.findings}
            extra = [r for r in item.reasons if r not in covered_reasons]
            if extra:  # what the rules missed
                s.findings.append(
                    Finding(
                        id=f"{s.block.id}-m",
                        block_id=s.block.id,
                        section=s.block.section or "Body",
                        reason=extra[0],
                        severity="major" if item.riskBand == "high" else "moderate",
                        excerpt=item.excerpt[:280],
                        explanation=item.explanation,
                        suggestion=item.suggestion,
                    )
                )
        result = signals.aggregate(block_signals, found.excluded_words, result.method, scores)
    complete = submitted > 0 and covered == submitted
    # Every difference between the checkers is kept (reviewerBands, below); only low against high is
    # shown to the student as uncertainty, and it lowers confidence (owner decision 2026-09-29).
    disagreements = sorted(bid for bid, j in model_results.items() if {"low", "high"} <= set(j.bands))
    confidence = result.confidence
    if disagreements:
        words = {s.block.id: s.block.words for s in block_signals}
        share = sum(words.get(bid, 0) for bid in disagreements) / max(1, sum(words.values()))
        confidence = "LOW" if share >= signals.DISAGREEMENT_SHARE else "MEDIUM" if confidence == "HIGH" else confidence
    result = result.model_copy(update={"coverage_complete": complete, "disagreement_blocks": disagreements, "confidence": confidence,
                                     **({"percent": None, "confidence": "LOW"} if not complete else {})})
    ctx.put_json(
        saved_name,
        {
            "result": result.model_dump(),
            "scores": {s.block.id: s.score for s in block_signals},
            "modelScores": scores,
            "reviewerBands": {bid: j.bands for bid, j in model_results.items()},
            "rejected": rejected,
            "hits": {s.block.id: s.evidence() for s in block_signals if s.hits},
            "preserve": sorted(bid for bid, j in model_results.items() if j.answer.preserve),
            "risks": {bid: j.answer.risk for bid, j in model_results.items() if j.answer.risk},
            "document": found.evidence(),
        },
    )
    return result, coverage_warning


def _deep(ctx: StageContext) -> bool:
    """Deep Redraft: the student chose to have groups of paragraphs reworked, not single passages."""
    return ctx.job.selection.writing == "REDRAFT"


def _brief(ctx: StageContext) -> dict[str, str]:
    return writing_brief(ctx.job.selection.style, "DEEP" if _deep(ctx) else ctx.job.selection.intensity)


# --- the source check (phase 4 of the revised algorithm) --------------------------------------

RESEARCH_METHOD = "Claims found by PaperAid, checked against live web sources, and each source checked again against its claim"


def stage_researching(ctx: StageContext) -> None:
    """Find the paper's important public claims, research each one on the live web, and have the
    writer check the evidence without searching. The paper itself is never changed by this."""
    settings = ctx.rt.settings
    model = ctx.document()
    runner = ctx.ai()
    blocks = model.by_id()
    prose = signals.analysable(model)
    passages = [{"id": b.id, "section": b.section or "Body", "sectionType": signals.section_type(b.section), "text": b.text} for b in prose]
    limit = research.claims_for(sum(b.words for b in prose), settings.research_max_claims)
    own, names = research.own_numbers(model), research.front_matter_names(model)
    order = {"high": 0, "medium": 1, "low": 2}
    position = {b.id: i for i, b in enumerate(prose)}
    candidates = [
        c
        for c in (runner.find_claims(passages, model.outline(), limit) if limit else [])
        if c.id in blocks
        and signals.section_type(blocks[c.id].section) not in research.OWN_DATA_SECTIONS
        and research.verbatim(c.claim, blocks[c.id].text)
        and research.safe_to_search(c.claim, c.query, own, names)
    ]
    candidates = sorted(dict((c.claim.strip().lower(), c) for c in candidates).values(), key=lambda c: (order[c.importance], position[c.id]))[:limit]

    found: list[tuple[str, ClaimCandidate, ResearchAnswer]] = []
    stopped = False
    for n, candidate in enumerate(candidates, start=1):
        try:
            answer = runner.research_claim(
                candidate.claim.strip(), candidate.query.strip(), candidate.cited, settings.research_max_searches, lambda q: research.query_safe(q, own, names)
            )
        except PermanentStageError as exc:
            if exc.code != "BUDGET_EXCEEDED":
                raise
            stopped = True
            break  # the quote's research allowance is spent: the rest are reported as not checked
        if answer is not None:
            found.append((f"c{n}", candidate, answer))

    # A quotation counts only if PaperAid finds it itself (Codex audit #4): on the page, or for a
    # journal article whose page is blocked, in its abstract. The second model then judges only
    # confirmed passages.
    confirmed = {cid: [_confirm(s) for s in a.sources] for cid, _, a in found}
    items = [
        {
            "id": cid,
            "claim": c.claim,
            "context": blocks[c.id].text[:900],
            "sources": [s.model_dump(exclude={"url", "supports", "verified"}) for s in confirmed[cid] if s.verified],
        }
        for cid, c, _ in found
        if any(s.verified for s in confirmed[cid])
    ]
    try:
        verdicts = runner.verify_claims(items) if items else {}
    except PermanentStageError as exc:
        if exc.code != "BUDGET_EXCEEDED":
            raise
        verdicts, stopped = {}, True
    claims = []
    for cid, c, a in found:
        check = verdicts.get(cid)
        if not a.sources:
            support, note = "NOT_FOUND", a.note
        elif not any(s.verified for s in confirmed[cid]) and any(s.readable for s in confirmed[cid]):
            support = "UNCERTAIN"  # a page opened but the quotation is not on it: a warning sign
            note = f"{a.note} PaperAid could not find the quoted passage on the source page, so it is not treated as evidence."
        elif not any(s.verified for s in confirmed[cid]):
            support = "UNCONFIRMED"
            note = f"{a.note} PaperAid could not open these sources to confirm the quotations (publishers often block automated reading). Open the links to check them yourself."
        else:
            support = research.combine(a.support, check.support if check else None)
            note = a.note if check is None or check.support == a.support else f"{a.note} Second check: {check.note}"
        claims.append(
            CheckedClaim(
                id=cid,
                block_id=c.id,
                section=blocks[c.id].section or "Body",
                claim=c.claim.strip(),
                cited=c.cited,
                support=support,  # type: ignore[arg-type]
                note=note.strip(),
                sources=confirmed[cid],
            )
        )
    result = ResearchResult(claims=claims, checked=len(claims), candidates=len(candidates), retrieved_on=utcnow().date().isoformat(), method=RESEARCH_METHOD)
    warnings = []
    contradicted = sum(1 for c in claims if c.support == "CONTRADICTED")
    if contradicted:
        warnings.append(f"{contradicted} of your claims appear{'s' if contradicted == 1 else ''} to be contradicted by the sources we found. See Source check before you submit.")
    unchecked = len(candidates) - len(claims)
    if stopped or unchecked:
        warnings.append(f"{unchecked} of {len(candidates)} claims could not be checked within this job's price, so they are not in the source check.")

    def save(j: Job) -> Job:
        j.research = result
        if stopped or unchecked:
            j.outcome = "PARTIAL"
        return _add_warnings(j, warnings)

    ctx.update(save)


def _confirm(source: FoundSource) -> Source:
    """Look for the quoted passage on the source page, then, for an article with a DOI, in its
    abstract (read at "abstract only" level)."""
    data = source.model_dump()
    page = fetch.page_text(source.url)
    if page is not None and research.quote_found(source.passage, page):
        return Source(**data, verified=True, readable=True)
    abstract = fetch.abstract_text(source.url)
    if abstract is not None and research.quote_found(source.passage, abstract):
        return Source(**{**data, "access": "ABSTRACT"}, verified=True, readable=True)
    return Source(**data, verified=False, readable=page is not None or abstract is not None)


# --- the refinement estimate ---------------------------------------------------------------


def run_estimate(ctx: StageContext) -> tuple[list[Passage], int]:
    """The paid scan that sizes a refinement: extraction, the lead's analysis and its draft plan,
    exactly the first calls the job itself will make (and then replay from the cache). Nothing is
    shown to the student except the resulting quote."""
    run = ctx.job.estimate
    assert run is not None
    model = _extract(ctx, run.source_sha256, run.guideline_sha256, run.selection.formatting)
    _, coverage_warning = _analyse(ctx, model)
    targets = _select_targets(ctx, model)
    draft = ctx.ai().draft_plan(targets, model.outline(), _brief(ctx)) if targets else {}
    ctx.put_json(
        f"estimates/{run.id}.json",
        {
            "analysis": ctx.get_json("analysis.json"),
            "coverageWarning": coverage_warning,
            "targets": [t.__dict__ for t in targets],
            "draft": {k: v.model_dump() for k, v in draft.items()},
        },
    )
    passages = [
        Passage(chars=len(t.masked), words=len(t.masked.split()), rewrite=draft[t.id].action == "rewrite", instruction_chars=len(draft[t.id].instruction) + len(draft[t.id].preserve))
        for t in targets
        if t.id in draft
    ]
    guide_words = len(ctx.get_json("guide.json")["text"].split()) if run.selection.formatting == "TEMPLATE_FORMAT" else 0
    return passages, guide_words


def _run_estimate_task(rt: Runtime, job_id: str) -> None:
    now = utcnow()

    def claim(j: Job) -> Job | None:
        if j.status != JobStatus.DRAFT or j.estimate is None or j.estimate.status != "RUNNING":
            return None
        if j.estimate.lease_until and j.estimate.lease_until > now:
            return None
        j.estimate.lease_until = now + LEASE
        j.estimate.lease_owner = secrets.token_hex(12)
        return j

    job = rt.store.update(job_id, claim)
    if job is None or job.estimate is None:
        return
    run_id = job.estimate.id
    ctx = StageContext(rt, job, phase="estimate")
    try:
        passages, guide_words = run_estimate(ctx)
    except (StageContinues, CapacityWait) as signal:
        waiting = isinstance(signal, CapacityWait)  # no Gemini capacity free: the estimate continues a little later

        def release(j: Job) -> Job | None:
            if j.estimate is None or j.estimate.id != run_id or j.estimate.status != "RUNNING" or j.estimate.lease_owner != ctx.owner:
                return None
            j.estimate.lease_until, j.estimate.lease_owner = None, ""
            j.events.append(JobEvent(label="Waiting for capacity to finish the estimate" if waiting else "Continuing the estimate in a new task"))
            return j

        released = rt.store.update(job_id, release)
        if released is not None:  # the model-call display is capped at 200; event count keeps increasing
            rt.queue.enqueue(job_id, f"{job_id}-e{run_id}-h{len(released.events)}", delay_sec=rt.settings.capacity_retry_sec if waiting else 0)
        return
    except StageError as exc:
        try:
            ctx.assert_owner()
        except StageContinues:
            return
        from app import notify

        notify.provider_problem(rt, exc.code, exc.detail)
        _estimate_failed(rt, job_id, run_id, ctx.owner, exc.code, exc.user_message, exc.detail, exc.retryable)
        return
    except Exception as exc:  # unexpected: classify as retryable so a transient bug can recover
        try:
            ctx.assert_owner()
        except StageContinues:
            return
        logger.exception("estimate crashed")
        _estimate_failed(rt, job_id, run_id, ctx.owner, "INTERNAL", ESTIMATE_FAILURE, f"{type(exc).__name__}: {exc}", True)
        return
    _finish_estimate(rt, job_id, run_id, ctx.owner, passages, guide_words)


def _finish_estimate(rt: Runtime, job_id: str, run_id: str, owner: str, passages: list[Passage], guide_words: int) -> None:
    settings = rt.settings

    def finish(j: Job, w: Wallet) -> tuple[Job, Wallet] | None:
        run = j.estimate
        if j.status != JobStatus.DRAFT or run is None or run.id != run_id or run.status != "RUNNING" or run.lease_owner != owner or j.source is None:
            return None
        fee = min(run.fee_cap, to_ugx(j.estimate_cost_usd - run.cost_base_usd, settings)) if run.held else 0
        if run.held:
            credits.settle(w, held=run.fee_cap, charge=fee, job_id=j.id, note="AI estimate")
        run.status, run.fee, run.lease_until, run.lease_owner = "READY", fee, None, ""
        run.passages, run.guide_words = passages, guide_words
        rewrite_words = sum(p.words for p in passages if p.rewrite)
        run.intervention = round(min(1.0, rewrite_words / j.source.word_count), 3) if j.source.word_count else None
        j.billing.fee_paid += fee  # earlier estimates on this job stay counted (and refundable)
        j.quote = bound_quote(
            settings,
            run.selection,
            run.source_sha256,
            j.source.word_count,
            run.engine or priced_engine(settings),
            run.guideline_sha256,
            guide_words,
            passages,
            fee_paid=j.billing.fee_paid,
            estimate_id=run.id,
        )
        j.selection = run.selection
        state.transition(j, JobStatus.QUOTED, f"Estimate ready ({credits.tokens(fee)} charged)")
        return j, w

    rt.store.update_job_and_wallet(job_id, finish)


def _estimate_failed(rt: Runtime, job_id: str, run_id: str, owner: str, code: str, message: str, detail: str, retryable: bool) -> None:
    settings = rt.settings
    retry_again = False

    def fail(j: Job, w: Wallet) -> tuple[Job, Wallet] | None:
        nonlocal retry_again
        run = j.estimate
        if run is None or run.id != run_id or run.status != "RUNNING" or run.lease_owner != owner:
            return None
        run.lease_until, run.lease_owner = None, ""
        if retryable and run.attempts + 1 < settings.stage_max_attempts:
            run.attempts += 1
            retry_again = True
            return j, w
        if run.held:
            credits.settle(w, held=run.fee_cap, charge=0, job_id=j.id, note="AI estimate could not run, so it was not charged")
        run.status, run.message = "FAILED", message
        j.events.append(JobEvent(label=f"Estimate failed: {code}"))
        j.failure_detail = f"estimate {detail}"[:500]
        return j, w

    result = rt.store.update_job_and_wallet(job_id, fail)
    log(logger, logging.WARNING, "estimate failed", code=code, retryable=retryable, willRetry=retry_again)
    if result and retry_again and result[0].estimate:
        attempts = result[0].estimate.attempts
        rt.queue.enqueue(job_id, f"{job_id}-e{run_id}-a{attempts}", delay_sec=min(300, 10 * 2**attempts))


def _select_targets(ctx: StageContext, model: DocumentModel) -> list[Target]:
    if _deep(ctx):
        return _redraft_targets(ctx, model)
    saved = ctx.get_json("analysis.json")
    result = AnalysisResult.model_validate(saved["result"])
    scores: dict[str, float] = saved["scores"]
    model_scores: dict[str, float] = saved.get("modelScores", {})
    preserve = set(saved.get("preserve", []))  # the lead judged these must not be rewritten
    risks: dict[str, str] = saved.get("risks", {})
    hits: dict[str, list[dict]] = saved.get("hits", {})
    flagged = {f.block_id for f in result.findings}
    findings: dict[str, list[str]] = {}
    for f in result.findings:
        findings.setdefault(f.block_id, []).append(f"{f.reason}: {f.explanation}")
    for bid, measured in hits.items():  # the measurements behind the confirmed findings
        findings.setdefault(bid, []).extend(f"PaperAid measured {h['measures']}: {h['value']} (threshold {h['threshold']})" for h in measured)
    prose = [b for b in model.blocks if b.kind in ("paragraph", "list_item")]
    by_position = {b.id: i for i, b in enumerate(prose)}

    def priority(b) -> float:
        return -(0.5 * scores.get(b.id, 0) + 0.5 * model_scores.get(b.id, scores.get(b.id, 0)))

    chosen = set(ctx.job.selection.only_blocks)
    if chosen:  # "Fix selected": the student chose these passages; the AI Check's findings on them guide the rewrite
        for bid in chosen:
            notes = [*ctx.job.fix_notes.get(bid, []), *ctx.job.fix_notes.get("*", [])]  # "*": a request for every chosen passage
            findings.setdefault(bid, []).extend(n for n in notes if n not in findings.get(bid, []))
        candidates = [b for b in prose if b.editable and b.id in chosen]
    else:
        candidates = sorted((b for b in prose if b.editable and b.id in flagged and b.id not in preserve), key=priority)
    share = 1.0 if chosen else 0.25 if ctx.job.selection.intensity == "LIGHT" else 0.5
    cap = sum(b.words for b in candidates) if chosen else max(150, share * result.analysed_words)
    targets, used = [], 0
    for block in candidates:
        if used + block.words > cap and targets:
            continue
        i = by_position[block.id]
        masked, _ = protect.mask(block.masked or "")
        targets.append(
            Target(
                id=block.id,
                section=block.section,
                masked=masked,
                before=prose[i - 1].text[-400:] if i > 0 else "",
                after=prose[i + 1].text[:400] if i + 1 < len(prose) else "",
                findings=findings.get(block.id, []),
                risk=risks.get(block.id, ""),
            )
        )
        used += block.words
    return targets


def _redraft_targets(ctx: StageContext, model: DocumentModel) -> list[Target]:
    """Deep Redraft works on every paragraph group (the plan may still leave a group alone),
    except a group holding a passage the lead said must not be rewritten."""
    saved = ctx.get_json("analysis.json")
    result = AnalysisResult.model_validate(saved["result"])
    preserve = set(saved.get("preserve", []))
    risks: dict[str, str] = saved.get("risks", {})
    findings: dict[str, list[str]] = {}
    for f in result.findings:
        findings.setdefault(f.block_id, []).append(f"{f.reason}: {f.explanation}")
    prose = [b for b in model.blocks if b.kind in ("paragraph", "list_item")]
    position = {b.id: i for i, b in enumerate(prose)}
    targets = []
    for group in paragraph_groups.groups(model):
        if preserve & set(group.block_ids):
            continue
        first, last = position[group.block_ids[0]], position[group.block_ids[-1]]
        targets.append(
            Target(
                id=group.id,
                section=group.section,
                masked=group.masked,
                before=prose[first - 1].text[-400:] if first > 0 else "",
                after=prose[last + 1].text[:400] if last + 1 < len(prose) else "",
                findings=[f for bid in group.block_ids for f in findings.get(bid, [])],
                risk=" ".join(risks[bid] for bid in group.block_ids if bid in risks),
            )
        )
    return targets


def stage_planning(ctx: StageContext) -> None:
    model = ctx.document()
    saved = _estimate_artifacts(ctx)
    if saved is not None:  # exactly the passages and draft plan the estimate priced
        targets = [Target(**t) for t in saved["targets"]]
        draft: dict[str, PlanItem] | None = {k: PlanItem.model_validate(v) for k, v in saved["draft"].items()}
    else:
        targets, draft = _select_targets(ctx, model), None
    plan = ctx.ai().negotiate_plan(targets, model.outline(), _brief(ctx), draft) if targets else None
    ctx.put_json(
        "plan.json",
        {
            "targets": [t.__dict__ for t in targets],
            "draft": {k: v.model_dump() for k, v in (plan.draft if plan else {}).items()},
            "critique": {k: v.model_dump() for k, v in (plan.critique if plan else {}).items()},
            "critiqueOverall": plan.critique_overall if plan else "",
            "final": {k: v.model_dump() for k, v in (plan.final if plan else {}).items()},
        },
    )


def _planned_targets(ctx: StageContext) -> list[Target]:
    """The passages the final plan says to rewrite, each carrying its agreed instruction."""
    saved = ctx.get_json("plan.json")
    final = {k: PlanItem.model_validate(v) for k, v in saved["final"].items()}
    targets = []
    for raw in saved["targets"]:
        item = final.get(raw["id"])
        # The student's own request (Ask for changes) reaches the writer in their words, and a passage
        # they asked to change is always rewritten (owner request 2026-09-29).
        asked = [n for n in [*ctx.job.fix_notes.get(raw["id"], []), *ctx.job.fix_notes.get("*", [])] if n.startswith("The student asks:")]
        if (item and item.action == "rewrite") or asked:
            instruction = " ".join([item.instruction if item and item.action == "rewrite" else "", *asked]).strip()
            targets.append(Target(**{**raw, "instruction": instruction, "preserve": item.preserve if item else ""}))
    return targets


def stage_refining(ctx: StageContext) -> None:
    model = ctx.document()
    targets = _planned_targets(ctx)
    runner = ctx.ai()
    revisions = runner.refine(targets, model.outline(), _brief(ctx)) if targets else []
    ctx.put_json("revisions.json", [r.__dict__ for r in revisions])
    if runner.budget_reached:
        ctx.update(lambda j: _add_warnings(j, [BUDGET_WARNING]))


BUDGET_WARNING = "This job reached the most it may spend on AI before every passage was finished, so those passages keep your original wording."


def stage_redrafting(ctx: StageContext) -> None:
    model = ctx.document()
    targets = _planned_targets(ctx)
    runner = ctx.ai()
    revisions = runner.redraft(targets, model.outline(), _brief(ctx)) if targets else []
    ctx.put_json("revisions.json", [r.__dict__ for r in revisions])
    if runner.budget_reached:
        ctx.update(lambda j: _add_warnings(j, [BUDGET_WARNING]))


def stage_auditing(ctx: StageContext) -> None:
    settings = ctx.rt.settings
    model = ctx.document()
    blocks = model.by_id()
    deep = _deep(ctx)
    groups = {g.id: g for g in paragraph_groups.groups(model)} if deep else {}
    revisions = [Revision(**r) for r in ctx.get_json("revisions.json")]
    targets = {t.id: t for t in _planned_targets(ctx)}
    instructions = {tid: t.instruction for tid, t in targets.items()}
    brief = _brief(ctx)
    runner = ctx.ai()
    missing = [r for r in revisions if NOT_RETURNED in r.problems]
    changed = [r for r in revisions if r.revised != r.original]
    # The writer returned the passage untouched: it found no safe improvement. Reported as kept.
    unchanged = [r for r in revisions if r.revised == r.original and NOT_RETURNED not in r.problems]

    # Stage 8–9: code has already rechecked every rewrite (check_rewrite); the lead now reviews
    # each one with PaperAid's post-scan, its neighbours and the passages linked to it.
    review = runner.review(changed, instructions, brief, _review_context(model, targets, changed, groups)) if changed else ReviewOutcome()
    fix = runner.redraft_fix if deep else runner.repair
    failed = {r.id: (r.problems or review.issues.get(r.id, [])) for r in changed if r.problems or review.issues.get(r.id)}
    reviewer_notes, risk = dict(review.warnings), dict(review.risk)
    notes: dict[str, str] = {}
    for _ in runner.audit_rounds(settings.repair_attempts, start=1):  # the review above was round 0
        if not failed:
            break
        try:
            repaired = fix([(r, failed[r.id]) for r in changed if r.id in failed], instructions, brief)
            clean = [r for r in repaired if r.revised != r.original and not r.problems]
            # A repair is reviewed again, with the same context: fixing one problem must not create another.
            second = runner.review(clean, instructions, brief, _review_context(model, targets, clean, groups)) if clean else ReviewOutcome()
        except PermanentStageError as exc:
            if exc.code != "BUDGET_EXCEEDED":
                raise
            break  # out of budget for repairs: the failed passages simply keep their original wording
        by_id = {r.id: r for r in repaired}
        changed = [by_id.get(r.id, r) for r in changed]
        reviewer_notes.update(second.warnings)
        risk.update(second.risk)
        failed = {r.id: (r.problems or second.issues.get(r.id, [])) for r in repaired if r.problems or second.issues.get(r.id) or r.revised == r.original}

    accepted = [r for r in changed if r.id not in failed]
    kept = [r for r in changed if r.id in failed] + missing + unchanged
    for r in accepted:
        if r.id in reviewer_notes:
            notes[r.id] = f"Reviewer note: {reviewer_notes[r.id]}"
    ctx.put_json("review.json", {"risk": {r.id: risk[r.id] for r in accepted if r.id in risk}})
    for r in kept:
        issues = failed.get(r.id, [])
        notes[r.id] = "Kept your original: " + (
            "the rewrite could not be verified to keep every figure, citation and meaning exactly."
            if issues
            else "we could not produce a safe improvement for this passage."
        )
    # Owner decision 2026-09-27: verified rewrites are always delivered; passages that could not be
    # verified keep the student's wording and the job is PARTIAL. It never fails for that reason.

    shown = changed + missing + unchanged
    kept_ids = {r.id for r in kept}
    source = ctx.rt.files.get(ctx.job.source.path)  # type: ignore[union-attr]
    if deep:
        rewrites = [(groups[r.id].block_ids, paragraph_groups.to_docx(groups[r.id], r.revised), groups[r.id].xmap) for r in accepted]
        ctx.put_bytes("refined.docx", apply_group_rewrites(source, rewrites) if rewrites else source)

        def readable(r: Revision, text: str) -> str:
            return "\n\n".join(groups[r.id].readable(p) for p in groups[r.id].paragraphs(text))

        def section_of(r: Revision) -> str:
            return groups[r.id].section
    else:
        originals = {r.id: protect.mask(blocks[r.id].masked or "")[1] for r in shown}
        patch = {r.id: protect.unmask(r.revised, originals[r.id]) for r in accepted}
        ctx.put_bytes("refined.docx", apply_revisions(source, patch) if patch else source)

        def readable(r: Revision, text: str) -> str:
            return blocks[r.id].readable(protect.unmask(text, originals[r.id]))

        def section_of(r: Revision) -> str:
            return blocks[r.id].section

    changes = [
        ChangedBlock(
            block_id=r.id,
            section=section_of(r),
            before=readable(r, r.original),
            after=readable(r, r.revised),
            kept=r.id in kept_ids,
            note=notes.get(r.id),
            reason=instructions.get(r.id),
        )
        for r in shown
    ]
    prose = [b for b in model.blocks if b.kind in ("paragraph", "list_item")]
    ctx.put_json("changes_full.json", [c.model_dump() for c in changes])  # every word, for the change report
    ctx.put_json("accepted.json", {"deep": deep, "revised": {r.id: r.revised for r in accepted}})  # for the student's own choices
    changes, trimmed = _fit_record(changes)
    refinement = RefinementResult(
        trimmed=trimmed,
        mode="REDRAFT" if deep else "REFINE",
        targeted_blocks=len(revisions),
        refined_blocks=len(accepted),
        kept_original=len(kept),
        untouched_blocks=(len(groups) if deep else len(prose)) - len(accepted),
        changes=changes,
        method=_method(ctx, "redraft" if deep else "refinement"),
    )
    warnings = []
    if kept and accepted:
        warnings.append(f"{len(kept)} of {len(shown)} passages kept their original wording because we couldn't produce a rewrite we could verify kept every figure, citation and meaning.")
    elif kept:
        warnings.append(f"None of the {len(shown)} flagged passages could be improved in a way we could verify, so your wording is unchanged. You are charged only for the analysis.")
    if not shown:
        warnings.append("No passages needed refinement under the selected intensity, so your wording is unchanged.")
    if runner.budget_reached:
        warnings.append(BUDGET_WARNING)
    noted = sum(1 for r in accepted if r.id in reviewer_notes)
    if noted:
        done = "redrafted" if deep else "refined"
        warnings.append(f"{noted} {done} passage{'s have' if noted > 1 else ' has'} a reviewer note in the change report: worth a look before you submit.")

    def save(j: Job) -> Job:
        j.refinement = refinement
        if kept:
            j.outcome = "PARTIAL"
        return _add_warnings(j, warnings)

    ctx.update(save)


def with_logo(rt, job: Job, data: bytes, block_map: dict[str, str] | None = None) -> tuple[bytes, FormattingRule | None]:
    """The student's institution logo on the first page, when they chose one: the same step for the
    finished file and for "Download with my choices" (Codex audit 56c4f83 M14)."""
    if job.selection.logo == "NONE" or job.logo is None or job.selection.formatting == "NONE":
        return data, None
    where = "top left" if job.selection.logo == "LEFT" else "top centre"
    return add_logo(data, rt.files.get(job.logo.path), job.selection.logo, block_map), FormattingRule(label="Logo", value=f"{job.logo.name}, {where} of the first page")


def stage_formatting(ctx: StageContext) -> None:
    job = ctx.job
    base = ctx.get_bytes("refined.docx") if ctx.has("refined.docx") else ctx.rt.files.get(job.source.path)  # type: ignore[union-attr]
    if job.selection.formatting == "TEMPLATE_FORMAT":
        approved = _format_from_guide(ctx, base)
        if approved is None:  # the rules were not approved by both reviewers: none are applied
            _skip_template(ctx)
            return
        formatted, result, partial = approved
    else:
        formatted, result = apply_formatting(base, with_custom(PRESETS[job.selection.preset], job.selection.custom), read_docx(base))
        partial = False
    formatted, logo_rule = with_logo(ctx.rt, job, formatted)
    if logo_rule is not None:
        result = result.model_copy(update={"rules": [*result.rules, logo_rule]})
    ctx.put_bytes("formatted.docx", formatted)

    def save(j: Job) -> Job:
        j.formatting = result
        if partial:
            j.outcome = "PARTIAL"
        return _add_warnings(j, result.warnings)

    ctx.update(save)


TEMPLATE_SKIPPED = (
    "PaperAid could not confirm your university's formatting rules, so they were not applied: your paper keeps its own layout. "
    "You were not charged for university template formatting."
)


def _skip_template(ctx: StageContext) -> None:
    """Unapproved university rules (owner decision 2026-09-29): the rest of the job is delivered
    without them and that part is refunded. A job that asked only for the template has nothing else
    to deliver, so it fails without charge."""
    selection = ctx.job.selection
    if selection.services() == [ServiceId.TEMPLATE_FORMAT]:  # the academic review needs a writing service
        raise PermanentStageError(
            "TEMPLATE_NOT_APPROVED", "PaperAid could not confirm your university's formatting rules, so none were applied and nothing was charged.", "template rules not approved"
        )

    def save(j: Job) -> Job:
        j.delivery = {**j.delivery, "TEMPLATE_FORMAT": 0.0}
        j.outcome = "PARTIAL"
        return _add_warnings(j, [TEMPLATE_SKIPPED])

    ctx.update(save)


def _format_from_guide(ctx: StageContext, base: bytes) -> tuple[bytes, FormattingResult, bool] | None:
    """The algorithm applied to formatting rules: lead drafts rules from the guide, writer
    critiques, lead finalises; code applies them (wording cannot change); lead reviews what was
    applied; writer fixes the rules; code re-applies — for a bounded number of rounds. None when an
    engine requiring both approvals ends without them."""
    guide = ctx.get_json("guide.json")["text"]
    runner = ctx.ai()
    label = f"Your guide ({ctx.job.guideline.name})" if ctx.job.guideline else "Your guide"
    answer = runner.negotiate_spec(guide)
    trail = answer.pop("_trail")
    reviews: list[list[dict[str, str]]] = []
    unresolved: list[dict[str, str]] = []
    rounds = ctx.rt.settings.repair_attempts
    for round_number in runner.audit_rounds(rounds + 1):
        spec, evidence, notes, checks = to_spec(answer, label, guide)
        formatted, result = apply_formatting(base, spec, read_docx(base))
        applied = {"spec": {k: v for k, v in answer.items() if k not in ("evidence",)}, "rulesApplied": [f"{r.label}: {r.value}" for r in result.rules]}
        problems = runner.review_spec(guide, applied)
        reviews.append(problems)
        if not problems:
            break
        if round_number == rounds:
            unresolved = problems
            break
        try:
            answer = runner.fix_spec(guide, answer, problems)
        except PermanentStageError as exc:
            if exc.code != "BUDGET_EXCEEDED":
                raise
            unresolved = problems
            break
    ctx.put_json("spec.json", {"final": answer, "trail": trail, "reviews": reviews})
    if unresolved and runner._engine.require_dual_approval:
        return None
    warnings = notes + checks + [f"Check this rule yourself: {p.get('field', '')} — {p.get('problem', '')}" for p in unresolved]
    warnings += [w for w in result.warnings if w not in warnings]
    result = result.model_copy(update={"evidence": evidence, "warnings": warnings, "method": _method(ctx, "formatting")})
    return formatted, result, bool(unresolved or checks)


def stage_converting(ctx: StageContext) -> None:
    """LaTeX from the finished Word file (refined or redrafted, then formatted, when chosen)."""
    base = next((ctx.get_bytes(n) for n in ("formatted.docx", "refined.docx") if ctx.has(n)), None) or ctx.rt.files.get(ctx.job.source.path)  # type: ignore[union-attr]
    archive, result, compiled, problem = latex.package(base)
    ctx.put_bytes("latex.zip", archive)
    summary = LatexResult(compiled=compiled, equations=result.equations, equations_converted=result.equations_converted, figures=result.figures, warnings=result.warnings)
    warnings = [f"LaTeX: {w}" for w in result.warnings]
    if not compiled:
        warnings.append(f"The LaTeX was not compiled on our server ({problem}). Your .tex project is included; compile it yourself, for example in Overleaf.")

    def save(j: Job) -> Job:
        j.latex = summary
        if not compiled or result.omitted:  # anything left out of main.tex makes it a partial result
            j.outcome = "PARTIAL"
        return _add_warnings(j, warnings)

    ctx.update(save)


def stage_exporting(ctx: StageContext) -> None:
    job = ctx.job
    base_name = PurePosixPath(job.source.name).stem[:120] if job.source else "paper"  # display only
    outputs: list[StoredOutput] = []

    def output(key: str, label: str, suffix: str, data: bytes, ext: str = "docx", content_type: str = DOCX_TYPE) -> None:
        ctx.assert_owner()
        path = f"{ctx.prefix}/output/{ctx.owner}/{key}.{ext}"
        ctx.rt.files.put(path, data, content_type)
        outputs.append(StoredOutput(id=key, label=label, name=f"{base_name} – {suffix}.{ext}", size_bytes=len(data), path=path, content_type=content_type))

    final = ctx.get_bytes("formatted.docx") if ctx.has("formatted.docx") else ctx.get_bytes("refined.docx") if ctx.has("refined.docx") else None
    if final is not None:
        refined, formatted = job.refinement is not None, job.formatting is not None
        done = "Redrafted" if job.refinement is not None and job.refinement.mode == "REDRAFT" else "Refined"
        label = f"{done} and formatted paper (Word)" if refined and formatted else f"{done} paper (Word)" if refined else "Formatted paper (Word)"
        output("paper", label, done.lower() if refined else "formatted", final)

    after = None
    if job.analysis:
        if job.refinement and job.refinement.refined_blocks:
            if ctx.ai()._engine.ai_check_peer_model:
                after, coverage_warning = _analyse(ctx, read_docx(ctx.get_bytes("refined.docx")), "analysis_after.json")
                if coverage_warning:
                    ctx.update(lambda j: _add_warnings(j, [coverage_warning]))
            else:
                after = _analysis_after(ctx, job.analysis.method)
        shown = after or job.analysis  # the passages named are those of the paper the score describes
        paper = read_docx(ctx.get_bytes("refined.docx")) if after is not None and ctx.has("refined.docx") else ctx.document()
        report = writing_report(
            job.source.name if job.source else "", utcnow(), job.analysis, after, job.paper_checks, job.research, _passage_labels(paper, shown.disagreement_blocks),
            show_score=ctx.rt.settings.show_ai_score,
        )
        output("writing-report", "Writing report (Word)", "writing report", report)
    elif job.research is not None:  # a source check on its own
        output("source-report", "Source check report (Word)", "source check", source_report(job.source.name if job.source else "", utcnow(), job.research))
    if job.refinement:
        full = job.refinement
        if ctx.has("changes_full.json"):  # the record may hold shortened passages; the report has every word
            full = job.refinement.model_copy(update={"changes": [ChangedBlock.model_validate(c) for c in ctx.get_json("changes_full.json")]})
        output("change-report", "Change report (Word)", "changes", change_report(job.source.name if job.source else "", utcnow(), full))
    if final is not None and job.refinement is not None and job.formatting is None:
        # The same paper with Academic formatting applied, so the student can choose at download.
        done = "Redrafted" if job.refinement.mode == "REDRAFT" else "Refined"
        formatted, _ = apply_formatting(final, PRESETS["apa7"], read_docx(final))
        output("paper-apa", f"{done} paper with academic formatting, APA 7 (Word)", f"{done.lower()}, APA 7", formatted)
    if job.latex is not None and ctx.has("latex.zip"):
        label = "LaTeX project with PDF (.zip)" if job.latex.compiled else "LaTeX project (.zip)"
        output("latex", label, "LaTeX", ctx.get_bytes("latex.zip"), "zip", "application/zip")

    def save(j: Job) -> Job:
        j.outputs = outputs
        j.analysis_after = after
        j.outcome = j.outcome or "FULL"
        return j

    ctx.update(save)


RECORD_TEXT_BYTES = 300_000  # before/after text kept in the job record (Firestore holds 1 MiB per document)


def _clip(text: str, max_bytes: int) -> str:
    if len(text.encode("utf-8")) <= max_bytes:
        return text
    return text.encode("utf-8")[: max(0, max_bytes - 40)].decode("utf-8", errors="ignore").rsplit(" ", 1)[0] + " … (full text in the change report)"


def _fit_record(changes: list[ChangedBlock]) -> tuple[list[ChangedBlock], bool]:
    """Keep the record's change text within RECORD_TEXT_BYTES, shortening long passages evenly
    (Codex audit #9). Returns (changes, whether anything was shortened)."""
    total = sum(len(c.before.encode("utf-8")) + len(c.after.encode("utf-8")) for c in changes)
    if total <= RECORD_TEXT_BYTES:
        return changes, False
    share = RECORD_TEXT_BYTES / total
    return [
        c.model_copy(update={"before": _clip(c.before, int(len(c.before.encode("utf-8")) * share)), "after": _clip(c.after, int(len(c.after.encode("utf-8")) * share))})
        for c in changes
    ], True


def _passage_labels(model: DocumentModel, block_ids: list[str]) -> list[str]:
    """Passages a student can find in their own paper: the section and the opening words, never an id."""
    blocks = model.by_id()
    return [f"{b.section or 'Body'}: “{' '.join(b.text.split()[:12])}…”" for bid in block_ids if (b := blocks.get(bid)) is not None]


def _analysis_after(ctx: StageContext, method: str) -> AnalysisResult:
    """The after-refinement band, by the same method as the before band: PaperAid's signals on the
    refined paper, blended with the lead's judgement: its original judgement for untouched
    passages (their rejected false positives stay rejected) and its review of each rewrite."""
    saved = ctx.get_json("analysis.json")
    if ctx.job.refinement is not None and ctx.job.refinement.mode == "REDRAFT":
        return _redraft_after(ctx, method, saved)
    refined_ids = {c.block_id for c in (ctx.job.refinement.changes if ctx.job.refinement else []) if not c.kept}
    review_risk: dict[str, str] = ctx.get_json("review.json")["risk"] if ctx.has("review.json") else {}
    rejected: dict[str, list[str]] = saved.get("rejected", {})
    found = signals.scan(read_docx(ctx.get_bytes("refined.docx")))
    for s in found.blocks:
        if s.block.id not in refined_ids and s.block.id in rejected:
            s.hits = [h for h in s.hits if h.rule not in rejected[s.block.id]]
            s.rescore()
    scores = {bid: v for bid, v in saved.get("modelScores", {}).items() if bid not in refined_ids}
    scores.update({bid: signals.MODEL_SCORE[band] for bid, band in review_risk.items() if bid in refined_ids})
    result = signals.aggregate(found.blocks, found.excluded_words, method, scores)
    if ctx.job.analysis is not None and ctx.job.analysis.coverage_complete is False:
        result = result.model_copy(update={"coverage_complete": False, "percent": None, "confidence": "LOW"})
    return result


def _redraft_after(ctx: StageContext, method: str, saved: dict[str, Any]) -> AnalysisResult:
    """After a Deep Redraft, paragraphs move and merge, so passages are matched by their text: an
    unchanged paragraph keeps the lead's original judgement (and its rejected false positives
    stay rejected); a rewritten one takes the lead's review of its group."""
    before = {b.text: b.id for b in ctx.document().blocks if b.kind in ("paragraph", "list_item")}
    review_risk: dict[str, str] = ctx.get_json("review.json")["risk"] if ctx.has("review.json") else {}
    group_sections = {c.section for c in (ctx.job.refinement.changes if ctx.job.refinement else []) if not c.kept}
    section_risk = max((signals.MODEL_SCORE[band] for band in review_risk.values()), default=None)
    rejected: dict[str, list[str]] = saved.get("rejected", {})
    model_scores: dict[str, float] = saved.get("modelScores", {})
    found = signals.scan(read_docx(ctx.get_bytes("refined.docx")))
    scores: dict[str, float] = {}
    for s in found.blocks:
        original = before.get(s.block.text)
        if original is not None:
            if original in rejected:
                s.hits = [h for h in s.hits if h.rule not in rejected[original]]
                s.rescore()
            if original in model_scores:
                scores[s.block.id] = model_scores[original]
        elif s.block.section in group_sections and section_risk is not None:
            scores[s.block.id] = section_risk
    result = signals.aggregate(found.blocks, found.excluded_words, method, scores)
    if ctx.job.analysis is not None and ctx.job.analysis.coverage_complete is False:
        result = result.model_copy(update={"coverage_complete": False, "percent": None, "confidence": "LOW"})
    return result


def _review_context(model: DocumentModel, targets: dict[str, Target], revisions: list[Revision], groups: dict[str, Any] | None = None) -> dict[str, dict[str, Any]]:
    """For each rewrite: its neighbours, up to two passages elsewhere that share its key terms
    (objectives, methods, results or conclusions it relates to), and PaperAid's post-scan. For a
    Deep Redraft group, "elsewhere" means outside the group."""
    blocks = model.by_id()
    groups = groups or {}
    prose = [b for b in model.blocks if b.kind in ("paragraph", "list_item")]
    phrases = {b.id: signals.phrases(b.masked or b.text) for b in prose}
    linkable = ("introduction", "methods", "results", "discussion", "conclusion", "abstract")
    context: dict[str, dict[str, Any]] = {}
    for r in revisions:
        target = targets.get(r.id)
        members = set(groups[r.id].block_ids) if r.id in groups else {r.id}
        section = groups[r.id].section if r.id in groups else blocks[r.id].section
        keys = {w for w in signals.words_of(r.original) if len(w) >= 7 and w not in signals.STOPWORDS}
        scored = []
        for b in prose:
            if b.id in members or b.section == section or signals.section_type(b.section) not in linkable:
                continue
            overlap = len(keys & set(signals.words_of(b.text)))
            if overlap >= 2:
                scored.append((overlap, b))
        linked = [{"section": b.section, "text": b.text[:500]} for _, b in sorted(scored, key=lambda item: -item[0])[:2]]
        elsewhere = set().union(*(p for bid, p in phrases.items() if bid not in members))
        context[r.id] = {
            "context": {"before": target.before if target else "", "after": target.after if target else ""},
            "linked": linked,
            "postScan": signals.post_scan(r.original, r.revised, section, elsewhere),
        }
    return context


STAGES = {
    Stage.EXTRACTING: stage_extracting,
    Stage.ANALYSING: stage_analysing,
    Stage.RESEARCHING: stage_researching,
    Stage.PLANNING: stage_planning,
    Stage.REFINING: stage_refining,
    Stage.REDRAFTING: stage_redrafting,
    Stage.AUDITING: stage_auditing,
    Stage.FORMATTING: stage_formatting,
    Stage.CONVERTING: stage_converting,
    Stage.EXPORTING: stage_exporting,
}


# --- the step runner -----------------------------------------------------------------------


def work_stage(stage: Stage):
    """A work step's stage (concept notes, coursework, funding proposals): never another service's."""
    return work_pipeline.STAGES[stage]


def run_step(rt: Runtime, job_id: str) -> None:
    """One queued task: a job's next stage, or a piece of Data Lab data work (`dop_` ids, Codex audit
    finding 13: the worker, not the public API, reads files and runs analyses)."""
    if job_id.startswith("dop_"):
        from app.datalab.service import run_op

        run_op(rt, job_id)
        return
    token = job_id_var.set(job_id)
    try:
        _run_step(rt, job_id)
    finally:
        job_id_var.reset(token)


def _run_step(rt: Runtime, job_id: str) -> None:
    now = utcnow()
    current = rt.store.get(job_id)
    estimating = bool(current and current.status == JobStatus.DRAFT and current.estimate and current.estimate.status == "RUNNING")
    if not processing_enabled(rt):  # emergency pause: leave the work waiting, look again in a minute
        if current and (estimating or current.status in (JobStatus.QUEUED, JobStatus.PROCESSING)):
            rt.queue.enqueue(job_id, task_name(current, f"-p{int(now.timestamp()) // 60}"), delay_sec=60)
        return
    if estimating:
        _run_estimate_task(rt, job_id)
        return

    def claim(j: Job) -> Job | None:
        if j.status not in (JobStatus.QUEUED, JobStatus.PROCESSING):
            return None  # finished, cancelled or failed: duplicate delivery is harmless
        if j.lease_until and j.lease_until > now:
            return None  # another worker holds this job
        if j.status == JobStatus.QUEUED:
            state.transition(j, JobStatus.PROCESSING, "Processing started")
        j.stage = next((s for s in j.pipeline if s not in j.completed_stages), None)
        j.lease_until = now + LEASE
        j.lease_owner = secrets.token_hex(12)
        return j

    job = rt.store.update(job_id, claim)
    if job is None:
        return
    stage = job.stage
    if stage is None:  # every stage done (a crash between the last stage and completion)
        _finish(rt, job_id, job.lease_owner)
        return

    started = utcnow()
    attempt = job.attempts
    since = job.ready_at or job.queued_at  # when its turn in the queue began
    queued_ms = int((started - since).total_seconds() * 1000) if since else 0
    ctx = StageContext(rt, job)
    if job.selection.datalab != "NONE":
        from app.datalab import pipeline as datalab_pipeline  # Data Lab imports the job service, which the worker's module must not import first
        from app.datalab import qual

        run = (qual.STAGES if job.selection.datalab == "THEMES" else datalab_pipeline.STAGES)[stage]
    elif job.selection.work != "NONE":
        run = work_stage(stage)
    elif job.selection.proposal == "REVIEW":
        run = proposal_review.STAGES.get(stage) or STAGES[stage]
    elif job.selection.proposal != "NONE":
        run = proposal_pipeline.STAGES[stage]
    else:
        run = STAGES[stage]
    def timing(outcome: str, code: str = "") -> StageTiming:
        return StageTiming(stage=stage, attempt=attempt, started_at=started, ended_at=utcnow(), outcome=outcome, code=code, queued_ms=max(0, queued_ms))

    try:
        run(ctx)
    except StageContinues:
        _continue_later(rt, job_id, stage, ctx.owner, timing("CONTINUED"))
        return
    except CapacityWait as exc:  # no Gemini capacity free: pause, keep everything done, come back shortly
        try:
            ctx.assert_owner()
        except StageContinues:
            return
        _wait_for_capacity(rt, job_id, stage, ctx.owner, exc.reason, timing("WAITING", "CAPACITY"))
        return
    except StageError as exc:
        try:
            ctx.assert_owner()
        except StageContinues:
            return
        from app import notify

        notify.provider_problem(rt, exc.code, exc.detail)  # a key or a provider balance the owner must fix
        _handle_failure(rt, job_id, stage, ctx.owner, exc.code, exc.user_message, exc.detail, exc.retryable, timing("RETRY" if exc.retryable else "FAILED", exc.code))
        return
    except Exception as exc:  # unexpected: classify as retryable so a transient bug can recover
        try:
            ctx.assert_owner()
        except StageContinues:
            return
        logger.exception("stage crashed", extra={"fields": {"stage": stage.value}})
        _handle_failure(rt, job_id, stage, ctx.owner, "INTERNAL", GENERIC_FAILURE, f"{type(exc).__name__}: {exc}", True, timing("RETRY", "INTERNAL"))
        return

    def complete(j: Job, w: Wallet) -> tuple[Job, Wallet] | None:
        if j.status != JobStatus.PROCESSING or j.stage != stage or j.lease_owner != ctx.owner:
            return None  # the stage finished the job itself (a work step publishes and settles in one transaction), or it was stopped
        if stage not in j.completed_stages:
            j.completed_stages.append(stage)
        j.attempts = 0
        j.lease_until = None
        j.lease_owner = ""
        j.timings = [*j.timings, timing("DONE")][-80:]
        j.activity = None
        j.ready_at = utcnow()
        j.stage = next((s for s in j.pipeline if s not in j.completed_stages), None)
        if j.stage is None:
            state.transition(j, JobStatus.COMPLETED, "Completed with warnings" if j.outcome == "PARTIAL" else "Completed")
            settle_completed(j, w)
        return j, w

    result = rt.store.update_job_and_wallet(job_id, complete)
    if result is None:
        # A step that completed itself (a work, proposal or Data Lab publication): its last stage's timing is added
        # here, or the reports would show the job without its final stage (Codex audit through ea0599e, finding 12).
        done = timing("DONE")

        def stamp(j: Job) -> Job | None:
            if j.status != JobStatus.COMPLETED or any(t.stage == stage and t.outcome == "DONE" and t.started_at == done.started_at for t in j.timings):
                return None
            j.timings = [*j.timings, done][-80:]
            j.activity = None
            return j

        rt.store.update(job_id, stamp)
        _notify(rt, job_id)
        return
    job = result[0]
    if job.status == JobStatus.COMPLETED:
        _notify(rt, job_id)
    log(logger, logging.INFO, "stage complete", stage=stage.value, durationMs=int((utcnow() - started).total_seconds() * 1000))
    if job.status == JobStatus.PROCESSING:
        rt.queue.enqueue(job_id, task_name(job))


def _continue_later(rt: Runtime, job_id: str, stage: Stage, owner: str, timing: StageTiming | None = None) -> None:
    """Release the lease and deliver the same stage again; its finished calls replay from the cache."""

    def release(j: Job) -> Job | None:
        if j.status != JobStatus.PROCESSING or j.stage != stage or j.lease_owner != owner:
            return None  # cancelled or failed meanwhile: stop here
        j.lease_until = None
        j.lease_owner = ""
        if timing is not None:
            j.timings = [*j.timings, timing][-80:]
        j.ready_at = utcnow()
        j.events.append(JobEvent(label=f"Continuing {stage.value.lower()} in a new task"))
        return j

    job = rt.store.update(job_id, release)
    if job is not None:
        rt.queue.enqueue(job_id, task_name(job, f"-c{len(job.events)}"))


CAPACITY_BUSY = ("PaperAid is very busy right now, so this could not finish in time. Nothing was charged and what was done is "
                 "saved. Please continue it in a little while.")


def _wait_for_capacity(rt: Runtime, job_id: str, stage: Stage, owner: str, reason: str, timing: StageTiming) -> None:
    """No Gemini capacity was free (speed plan 2026-10-08): the stage keeps what it has done (its finished calls replay
    from the cache), releases its lease and is delivered again after a short wait. These pauses never use up the
    stage's retries for provider failures; after `capacity_max_waits` of them (about two hours) the job stops, uncharged."""
    settings = rt.settings
    retry_again = False

    def pause(j: Job, w: Wallet) -> tuple[Job, Wallet] | None:
        nonlocal retry_again
        if j.status != JobStatus.PROCESSING or j.stage != stage or j.lease_owner != owner:
            return None  # cancelled, failed or finished meanwhile
        j.lease_until, j.lease_owner = None, ""
        j.timings = [*j.timings, timing][-80:]
        j.capacity_waits += 1
        if j.capacity_waits > settings.capacity_max_waits:
            # retryable: the student can resume it, and its finished calls are reused (Codex audit, finding 10)
            j.failure = JobFailure(code="CAPACITY_BUSY", user_message=CAPACITY_BUSY, retryable=True)
            j.failure_detail = f"stage={stage.value} capacity waits exhausted: {reason}"[:500]
            state.transition(j, JobStatus.FAILED, "Failed: CAPACITY_BUSY")
            refund_job(j, w, "Job failed, so nothing was charged")
            return j, w
        if j.activity is None or j.activity.kind != "WAITING":
            j.events.append(JobEvent(label=f"Waiting for capacity during {stage.value.lower()}"))
        j.activity = Activity(kind="WAITING", note=reason)
        j.ready_at = utcnow() + timedelta(seconds=delay)  # due then: the pause itself is not time in the queue
        retry_again = True
        return j, w

    delay = settings.capacity_retry_sec + random.randint(0, max(1, settings.capacity_retry_sec // 2))
    result = rt.store.update_job_and_wallet(job_id, pause)
    log(logger, logging.INFO, "stage paused for capacity", stage=stage.value, reason=reason, willRetry=retry_again)
    if result and retry_again:
        job = result[0]
        rt.queue.enqueue(job_id, task_name(job, f"-w{job.capacity_waits}"), delay_sec=delay)
    elif result:
        _notify(rt, job_id)


def _finish(rt: Runtime, job_id: str, owner: str) -> None:
    def done(j: Job, w: Wallet) -> tuple[Job, Wallet] | None:
        if j.status != JobStatus.PROCESSING or j.lease_owner != owner:
            return None
        j.lease_until = None
        j.lease_owner = ""
        state.transition(j, JobStatus.COMPLETED, "Completed")
        settle_completed(j, w)
        return j, w

    rt.store.update_job_and_wallet(job_id, done)
    _notify(rt, job_id)


def _notify(rt: Runtime, job_id: str) -> None:
    """Tell the person their work is ready, or that it stopped (app.notify sends each outcome once)."""
    from app import notify

    job = rt.store.get(job_id)
    if job is not None:
        notify.after_job(rt, job)


# Provider problems (Google slow, busy or unreachable) are retried sooner than other failures, within the same number
# of attempts (speed plan 2026-10-08): 15, 30, 60, 120 then 240 seconds instead of 20 doubling to 300.
PROVIDER_CODES = ("VERTEX_", "PROVIDER_UNAVAILABLE")


def _retry_delay(code: str, attempts: int) -> int:
    return min(240, 15 * 2 ** (attempts - 1)) if code.startswith(PROVIDER_CODES) else min(300, 10 * 2**attempts)


def _handle_failure(rt: Runtime, job_id: str, stage: Stage, owner: str, code: str, message: str, detail: str, retryable: bool,
                    timing: StageTiming | None = None) -> None:
    settings = rt.settings
    retry_again = False

    def fail(j: Job, w: Wallet) -> tuple[Job, Wallet] | None:
        nonlocal retry_again
        if j.status != JobStatus.PROCESSING or j.stage != stage or j.lease_owner != owner:
            return None  # already finished (an error after the stage completed and settled it) or stopped: never refunded twice or after delivery
        j.lease_until = None
        j.lease_owner = ""
        if timing is not None:
            j.timings = [*j.timings, timing][-80:]
        if retryable and j.attempts + 1 < settings.stage_max_attempts:
            j.attempts += 1
            j.events.append(JobEvent(label=f"Retrying {stage.value.lower()} after {code}"))
            j.activity = Activity(kind="RETRYING", note="PROVIDER" if code.startswith(PROVIDER_CODES) else "OTHER")
            j.ready_at = utcnow() + timedelta(seconds=_retry_delay(code, j.attempts))  # due then: the backoff is not queue time
            retry_again = True
            return j, w
        from app.ai.providers import UNAVAILABLE, UNAVAILABLE_FINAL

        final = UNAVAILABLE_FINAL if message == UNAVAILABLE else message  # the retries are used up: say it stopped
        j.failure = JobFailure(code=code, user_message=final, retryable=retryable)
        j.failure_detail = f"stage={stage.value} {detail}"[:500]
        state.transition(j, JobStatus.FAILED, f"Failed: {code}")
        refund_job(j, w, "Job failed, so nothing was charged")
        return j, w

    result = rt.store.update_job_and_wallet(job_id, fail)
    job = result[0] if result else None
    log(logger, logging.WARNING, "stage failed", stage=stage.value, code=code, retryable=retryable, willRetry=retry_again)
    if job and retry_again:
        delay = _retry_delay(code, job.attempts)
        rt.queue.enqueue(job_id, task_name(job, f"-a{job.attempts}"), delay_sec=delay)
    elif job is not None:
        _notify(rt, job_id)


def _set(j: Job, **fields: Any) -> Job:
    for key, value in fields.items():
        setattr(j, key, value)
    return j


def _add_warnings(j: Job, warnings: list[str]) -> Job:
    j.warnings = list(dict.fromkeys(j.warnings + warnings))
    return j


def _method(ctx: StageContext, kind: str) -> str:
    """How the work was done, as students see it. Model names stay internal (owner decision
    2026-09-25); admins see the exact models and costs on each job."""
    if kind == "analysis":
        return "PaperAid writing-pattern signals and AI analysis"
    if kind == "formatting":
        return "Rules read from your guide and checked by PaperAid's AI, applied by PaperAid's formatter"
    if kind == "redraft":
        return "Planned, redrafted section by section and independently reviewed by PaperAid's AI"
    return "Planned, rewritten and independently reviewed by PaperAid's AI"
