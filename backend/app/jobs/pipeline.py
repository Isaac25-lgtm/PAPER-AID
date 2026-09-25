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
import secrets
from datetime import timedelta
from pathlib import PurePosixPath
from typing import Any, Literal

from app.ai.orchestration import NOT_RETURNED, AIRunner, PlanItem, Revision, Target
from app.analysis import signals
from app.core.errors import InvalidDocument, PermanentStageError, StageError
from app.core.logging import job_id as job_id_var
from app.core.logging import log
from app.documents import protect
from app.documents.docx_io import apply_revisions, read_docx
from app.documents.intake import inspect_upload
from app.documents.model import DocumentModel
from app.formatting.apply import apply_formatting
from app.formatting.guideline import MAX_GUIDE_WORDS, to_spec
from app.formatting.presets import PRESETS
from app.jobs import state
from app.jobs.models import (
    AnalysisResult,
    Billing,
    BoundQuote,
    ChangedBlock,
    Finding,
    FormattingResult,
    Job,
    JobEvent,
    JobFailure,
    JobStatus,
    ModelCall,
    RefinementResult,
    Stage,
    StoredOutput,
    Wallet,
    utcnow,
)
from app.jobs.service import DOCX_TYPE, processing_enabled, task_name
from app.pricing import credits
from app.pricing.billing import refund_job, settle_completed
from app.pricing.quote import PRICING_VERSION, Passage, price, to_ugx
from app.reports.builder import change_report, writing_report
from app.runtime import Runtime

logger = logging.getLogger("paperaid.worker")
LEASE = timedelta(minutes=25)
# A stage stops starting new model calls after this long and hands the rest to a fresh delivery,
# which replays finished calls from the response cache. Keeps every delivery inside the lease
# and the 30-minute task deadline, however many batches a long paper needs.
STAGE_WORK_LIMIT = timedelta(minutes=20)
GENERIC_FAILURE = "Something went wrong while processing your paper. Our team has been notified."
ESTIMATE_FAILURE = "We couldn't estimate this paper right now. Your credits were returned; please try again shortly."
REFINE_STAGES = (Stage.PLANNING, Stage.REFINING, Stage.AUDITING)


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
                if j.status != JobStatus.DRAFT or j.estimate is None or j.estimate.id != run_id or j.estimate.status != "RUNNING":
                    return None
                j.estimate.lease_until = now + LEASE
                return j
            if j.status != JobStatus.PROCESSING or j.stage != stage:
                return None
            j.lease_until = now + LEASE
            return j

        if self.rt.store.update(self.job.id, renew) is None:
            raise StageContinues()
        self._paid_calls += 1

    # artifacts -------------------------------------------------------------------------
    def put_json(self, name: str, data: Any) -> None:
        self.rt.files.put(f"{self.prefix}/internal/{name}", json.dumps(data, ensure_ascii=False).encode(), "application/json")

    def get_json(self, name: str) -> Any:
        return json.loads(self.rt.files.get(f"{self.prefix}/internal/{name}"))

    def has(self, name: str) -> bool:
        return self.rt.files.exists(f"{self.prefix}/internal/{name}")

    def put_bytes(self, name: str, data: bytes) -> None:
        self.rt.files.put(f"{self.prefix}/internal/{name}", data, DOCX_TYPE)

    def get_bytes(self, name: str) -> bytes:
        return self.rt.files.get(f"{self.prefix}/internal/{name}")

    def document(self) -> DocumentModel:
        return DocumentModel.model_validate(self.get_json("document.json"))

    def update(self, mutate) -> Job:
        updated = self.rt.store.update(self.job.id, mutate)
        assert updated is not None
        self.job = updated
        return updated

    def ai(self) -> AIRunner:
        def record(call: ModelCall) -> None:
            def add(j: Job) -> Job:
                j.model_calls = (j.model_calls + [call])[-200:]
                j.cost_usd = round(j.cost_usd + call.cost_usd, 6)
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
                return current.estimate_cost_usd - estimate.cost_base_usd
            return current.cost_usd - current.estimate_cost_usd

        budget = estimate.budget_usd if estimate is not None else self.job.budget_usd
        return AIRunner(self.rt.settings, record, spent, budget, cache=_ResponseCache(self), heartbeat=self.heartbeat, phase=self.phase)


class _ResponseCache:
    """Saved model responses for this job, keyed by request fingerprint (see app.ai.orchestration)."""

    def __init__(self, ctx: StageContext):
        self._ctx = ctx

    def get(self, key: str) -> str | None:
        name = f"calls/{key}.json"
        return self._ctx.get_bytes(name).decode("utf-8") if self._ctx.has(name) else None

    def put(self, key: str, text: str) -> None:
        self._ctx.rt.files.put(f"{self._ctx.prefix}/internal/calls/{key}.json", text.encode("utf-8"), "application/json")


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


def stage_analysing(ctx: StageContext) -> None:
    result, coverage_warning = _analyse(ctx, ctx.document())

    def save(j: Job) -> Job:
        j.analysis = result
        if coverage_warning:
            j.outcome = "PARTIAL"
            _add_warnings(j, [coverage_warning])
        return j

    ctx.update(save)


def _analyse(ctx: StageContext, model: DocumentModel) -> tuple[AnalysisResult, str | None]:
    """PaperAid's signals plus the lead's judgement; saves analysis.json. The estimate runs this
    too (without showing the result), so the job replays the lead's answer from the cache."""
    runner = ctx.ai()
    result, block_signals = signals.analyse(model, method=_method(ctx, "analysis"))
    model_results = runner.analyse([(s.block.id, s.block.masked or s.block.text) for s in block_signals], model.outline())
    submitted, covered = len(block_signals), len(model_results)
    lead = ctx.rt.settings.lead_model.split(":")[-1]
    coverage_warning = None
    if covered < submitted:
        coverage_warning = (
            f"{lead} could assess only {covered} of {submitted} passages; the rest were scored on PaperAid's writing-pattern signals alone."
            if covered
            else f"{lead} could not assess this paper, so every passage was scored on PaperAid's writing-pattern signals alone."
        )
        method = f"PaperAid writing-pattern signals + analysis by {lead} ({covered} of {submitted} passages)" if covered else "PaperAid writing-pattern signals only"
        result = result.model_copy(update={"method": method})
    if model_results:
        scores = {bid: {"low": 0.1, "moderate": 0.45, "high": 0.85}.get(r.riskBand, 0.3) for bid, r in model_results.items()}
        for s in block_signals:
            item = model_results.get(s.block.id)
            if item and item.reasons and not s.findings:
                s.findings.append(
                    Finding(
                        id=f"{s.block.id}-m",
                        block_id=s.block.id,
                        section=s.block.section or "Body",
                        reason=item.reasons[0],  # type: ignore[arg-type]
                        severity="major" if item.riskBand == "high" else "moderate",
                        excerpt=item.excerpt[:280],
                        explanation=item.explanation,
                        suggestion=item.suggestion,
                    )
                )
            elif item and s.findings:
                s.findings[0].explanation, s.findings[0].suggestion = item.explanation, item.suggestion
        excluded = model.word_count - sum(s.block.words for s in block_signals)
        result = signals.aggregate(block_signals, excluded, result.method, scores)
    ctx.put_json("analysis.json", {"result": result.model_dump(), "scores": {s.block.id: s.score for s in block_signals}})
    return result, coverage_warning


# --- the refinement estimate ---------------------------------------------------------------


def run_estimate(ctx: StageContext) -> tuple[list[Passage], int]:
    """The paid scan that sizes a refinement: extraction, the lead's analysis and its draft plan,
    exactly the first calls the job itself will make (and then replay from the cache). Nothing is
    shown to the student except the resulting quote."""
    run = ctx.job.estimate
    assert run is not None
    model = _extract(ctx, run.source_sha256, run.guideline_sha256, run.selection.formatting)
    _analyse(ctx, model)
    targets = _select_targets(ctx, model)
    draft = ctx.ai().draft_plan(targets, model.outline()) if targets else {}
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
        return j

    job = rt.store.update(job_id, claim)
    if job is None or job.estimate is None:
        return
    run_id = job.estimate.id
    ctx = StageContext(rt, job, phase="estimate")
    try:
        passages, guide_words = run_estimate(ctx)
    except StageContinues:

        def release(j: Job) -> Job | None:
            if j.estimate is None or j.estimate.id != run_id or j.estimate.status != "RUNNING":
                return None
            j.estimate.lease_until = None
            return j

        released = rt.store.update(job_id, release)
        if released is not None:  # named by progress (paid calls so far), so every hand-off is a distinct task
            rt.queue.enqueue(job_id, f"{job_id}-e{run_id}-c{len(released.model_calls)}")
        return
    except StageError as exc:
        _estimate_failed(rt, job_id, run_id, exc.code, exc.user_message, exc.detail, exc.retryable)
        return
    except Exception as exc:  # unexpected: classify as retryable so a transient bug can recover
        logger.exception("estimate crashed")
        _estimate_failed(rt, job_id, run_id, "INTERNAL", ESTIMATE_FAILURE, f"{type(exc).__name__}: {exc}", True)
        return
    _finish_estimate(rt, job_id, run_id, passages, guide_words)


def _finish_estimate(rt: Runtime, job_id: str, run_id: str, passages: list[Passage], guide_words: int) -> None:
    settings = rt.settings
    now = utcnow()

    def finish(j: Job, w: Wallet) -> tuple[Job, Wallet] | None:
        run = j.estimate
        if j.status != JobStatus.DRAFT or run is None or run.id != run_id or run.status != "RUNNING" or j.source is None:
            return None
        fee = min(run.fee_cap, to_ugx(j.estimate_cost_usd - run.cost_base_usd, settings)) if run.held else 0
        priced = price(settings, run.selection, j.source.word_count, guide_words, passages, fee_paid=fee)
        if run.held:
            credits.settle(w, held=run.fee_cap, charge=fee, job_id=j.id, note="AI estimate")
        run.status, run.fee, run.lease_until = "READY", fee, None
        j.billing = Billing(fee_paid=fee)
        j.quote = BoundQuote(
            id=f"quote_{secrets.token_hex(6)}",
            lines=priced.lines,
            amount=sum(line.amount for line in priced.lines),
            paid=fee,
            pricing_version=PRICING_VERSION,
            expires_at=now + timedelta(minutes=settings.quote_ttl_minutes),
            selection=run.selection,
            source_sha256=run.source_sha256,
            guideline_sha256=run.guideline_sha256,
            word_count=j.source.word_count,
            fixed_ugx=priced.fixed_ugx,
            ugx_per_usd=settings.ugx_per_usd,
            multiplier=settings.price_multiplier,
        )
        j.selection = run.selection
        state.transition(j, JobStatus.QUOTED, f"Estimate ready (UGX {fee:,} charged)")
        return j, w

    rt.store.update_job_and_wallet(job_id, finish)


def _estimate_failed(rt: Runtime, job_id: str, run_id: str, code: str, message: str, detail: str, retryable: bool) -> None:
    settings = rt.settings
    retry_again = False

    def fail(j: Job, w: Wallet) -> tuple[Job, Wallet] | None:
        nonlocal retry_again
        run = j.estimate
        if run is None or run.id != run_id or run.status != "RUNNING":
            return None
        run.lease_until = None
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
    saved = ctx.get_json("analysis.json")
    result = AnalysisResult.model_validate(saved["result"])
    scores: dict[str, float] = saved["scores"]
    flagged = {f.block_id for f in result.findings}
    findings: dict[str, list[str]] = {}
    for f in result.findings:
        findings.setdefault(f.block_id, []).append(f"{f.reason}: {f.explanation}")
    prose = [b for b in model.blocks if b.kind in ("paragraph", "list_item")]
    by_position = {b.id: i for i, b in enumerate(prose)}
    candidates = sorted((b for b in prose if b.editable and b.id in flagged), key=lambda b: -scores.get(b.id, 0))
    share = 0.25 if ctx.job.selection.intensity == "LIGHT" else 0.5
    cap = max(150, share * result.analysed_words)
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
            )
        )
        used += block.words
    return targets


def stage_planning(ctx: StageContext) -> None:
    model = ctx.document()
    targets = _select_targets(ctx, model)
    plan = ctx.ai().negotiate_plan(targets, model.outline()) if targets else None
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
        if item and item.action == "rewrite":
            targets.append(Target(**{**raw, "instruction": item.instruction, "preserve": item.preserve}))
    return targets


def stage_refining(ctx: StageContext) -> None:
    model = ctx.document()
    targets = _planned_targets(ctx)
    revisions = ctx.ai().refine(targets, model.outline()) if targets else []
    ctx.put_json("revisions.json", [r.__dict__ for r in revisions])


def stage_auditing(ctx: StageContext) -> None:
    settings = ctx.rt.settings
    model = ctx.document()
    blocks = model.by_id()
    revisions = [Revision(**r) for r in ctx.get_json("revisions.json")]
    instructions = {t.id: t.instruction for t in _planned_targets(ctx)}
    runner = ctx.ai()
    missing = [r for r in revisions if NOT_RETURNED in r.problems]
    changed = [r for r in revisions if r.revised != r.original]

    verdicts = runner.review(changed, instructions) if changed else {}
    failed = {r.id: (r.problems or verdicts.get(r.id, [])) for r in changed if r.problems or verdicts.get(r.id)}
    notes: dict[str, str] = {}
    for _ in range(settings.repair_attempts):
        if not failed:
            break
        try:
            repaired = runner.repair([(r, failed[r.id]) for r in changed if r.id in failed], instructions)
            clean = [r for r in repaired if r.revised != r.original and not r.problems]
            second = runner.review(clean, instructions) if clean else {}
        except PermanentStageError as exc:
            if exc.code != "BUDGET_EXCEEDED":
                raise
            break  # out of budget for repairs: the failed passages simply keep their original wording
        by_id = {r.id: r for r in repaired}
        changed = [by_id.get(r.id, r) for r in changed]
        failed = {r.id: (r.problems or second.get(r.id, [])) for r in repaired if r.problems or second.get(r.id) or r.revised == r.original}

    accepted = [r for r in changed if r.id not in failed]
    kept = [r for r in changed if r.id in failed] + missing
    for r in kept:
        issues = failed.get(r.id, [])
        notes[r.id] = "Kept your original: " + (
            "the rewrite could not be verified to keep every figure, citation and meaning exactly."
            if issues
            else "we could not produce a safe improvement for this passage."
        )
    attempted = len(changed) + len(missing)
    if attempted >= 3 and len(kept) / attempted > settings.max_failed_share:
        raise PermanentStageError(
            "QUALITY_CHECK_FAILED",
            "Our accuracy check could not verify enough of the changes, so we stopped rather than give you an altered paper. You have not been charged.",
            f"kept={len(kept)} attempted={attempted}",
        )

    shown = changed + missing
    kept_ids = {r.id for r in kept}
    originals = {r.id: protect.mask(blocks[r.id].masked or "")[1] for r in shown}
    source = ctx.rt.files.get(ctx.job.source.path)  # type: ignore[union-attr]
    patch = {r.id: protect.unmask(r.revised, originals[r.id]) for r in accepted}
    ctx.put_bytes("refined.docx", apply_revisions(source, patch) if patch else source)

    def readable(r: Revision, text: str) -> str:
        return blocks[r.id].readable(protect.unmask(text, originals[r.id]))

    changes = [
        ChangedBlock(
            block_id=r.id,
            section=blocks[r.id].section,
            before=readable(r, r.original),
            after=readable(r, r.revised),
            kept=r.id in kept_ids,
            note=notes.get(r.id),
            reason=instructions.get(r.id),
        )
        for r in shown
    ]
    prose = [b for b in model.blocks if b.kind in ("paragraph", "list_item")]
    refinement = RefinementResult(
        targeted_blocks=len(revisions),
        refined_blocks=len(accepted),
        kept_original=len(kept),
        untouched_blocks=len(prose) - len(accepted),
        changes=changes,
        method=_method(ctx, "refinement"),
    )
    warnings = []
    if kept:
        warnings.append(f"{len(kept)} passage(s) kept their original wording because we couldn't produce a rewrite we could verify kept every figure, citation and meaning.")
    if not shown:
        warnings.append("No passages needed refinement under the selected intensity, so your wording is unchanged.")

    def save(j: Job) -> Job:
        j.refinement = refinement
        if kept:
            j.outcome = "PARTIAL"
        return _add_warnings(j, warnings)

    ctx.update(save)


def stage_formatting(ctx: StageContext) -> None:
    job = ctx.job
    base = ctx.get_bytes("refined.docx") if ctx.has("refined.docx") else ctx.rt.files.get(job.source.path)  # type: ignore[union-attr]
    if job.selection.formatting == "TEMPLATE_FORMAT":
        formatted, result, partial = _format_from_guide(ctx, base)
    else:
        formatted, result = apply_formatting(base, PRESETS[job.selection.preset], read_docx(base))
        partial = False
    ctx.put_bytes("formatted.docx", formatted)

    def save(j: Job) -> Job:
        j.formatting = result
        if partial:
            j.outcome = "PARTIAL"
        return _add_warnings(j, result.warnings)

    ctx.update(save)


def _format_from_guide(ctx: StageContext, base: bytes) -> tuple[bytes, FormattingResult, bool]:
    """The algorithm applied to formatting rules: lead drafts rules from the guide, writer
    critiques, lead finalises; code applies them (wording cannot change); lead reviews what was
    applied; writer fixes the rules; code re-applies — for a bounded number of rounds."""
    guide = ctx.get_json("guide.json")["text"]
    runner = ctx.ai()
    label = f"Your guide ({ctx.job.guideline.name})" if ctx.job.guideline else "Your guide"
    answer = runner.negotiate_spec(guide)
    trail = answer.pop("_trail")
    reviews: list[list[dict[str, str]]] = []
    unresolved: list[dict[str, str]] = []
    rounds = ctx.rt.settings.repair_attempts
    for round_number in range(rounds + 1):
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
    warnings = notes + checks + [f"Check this rule yourself: {p.get('field', '')} — {p.get('problem', '')}" for p in unresolved]
    warnings += [w for w in result.warnings if w not in warnings]
    result = result.model_copy(update={"evidence": evidence, "warnings": warnings, "method": _method(ctx, "formatting")})
    return formatted, result, bool(unresolved or checks)


def stage_exporting(ctx: StageContext) -> None:
    job = ctx.job
    base_name = PurePosixPath(job.source.name).stem[:120] if job.source else "paper"  # display only
    outputs: list[StoredOutput] = []

    def output(key: str, label: str, suffix: str, data: bytes) -> None:
        path = f"{ctx.prefix}/output/{key}.docx"
        ctx.rt.files.put(path, data, DOCX_TYPE)
        outputs.append(StoredOutput(id=key, label=label, name=f"{base_name} – {suffix}.docx", size_bytes=len(data), path=path, content_type=DOCX_TYPE))

    final = ctx.get_bytes("formatted.docx") if ctx.has("formatted.docx") else ctx.get_bytes("refined.docx") if ctx.has("refined.docx") else None
    if final is not None:
        refined, formatted = job.refinement is not None, job.formatting is not None
        label = "Refined and formatted paper (Word)" if refined and formatted else "Refined paper (Word)" if refined else "Formatted paper (Word)"
        output("paper", label, "refined" if refined else "formatted", final)

    after = None
    if job.analysis:
        if job.refinement and job.refinement.refined_blocks:
            after, _ = signals.analyse(read_docx(ctx.get_bytes("refined.docx")), method=job.analysis.method)
        output("writing-report", "Writing report (Word)", "writing report", writing_report(job.source.name if job.source else "", utcnow(), job.analysis, after))
    if job.refinement:
        output("change-report", "Change report (Word)", "changes", change_report(job.source.name if job.source else "", utcnow(), job.refinement))

    def save(j: Job) -> Job:
        j.outputs = outputs
        j.analysis_after = after
        j.outcome = j.outcome or "FULL"
        return j

    ctx.update(save)


STAGES = {
    Stage.EXTRACTING: stage_extracting,
    Stage.ANALYSING: stage_analysing,
    Stage.PLANNING: stage_planning,
    Stage.REFINING: stage_refining,
    Stage.AUDITING: stage_auditing,
    Stage.FORMATTING: stage_formatting,
    Stage.EXPORTING: stage_exporting,
}


# --- the step runner -----------------------------------------------------------------------


def run_step(rt: Runtime, job_id: str) -> None:
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
        return j

    job = rt.store.update(job_id, claim)
    if job is None:
        return
    stage = job.stage
    if stage is None:  # every stage done (a crash between the last stage and completion)
        _finish(rt, job_id)
        return

    started = utcnow()
    ctx = StageContext(rt, job)
    try:
        STAGES[stage](ctx)
    except StageContinues:
        _continue_later(rt, job_id, stage)
        return
    except StageError as exc:
        _handle_failure(rt, job_id, stage, exc.code, exc.user_message, exc.detail, exc.retryable)
        return
    except Exception as exc:  # unexpected: classify as retryable so a transient bug can recover
        logger.exception("stage crashed", extra={"fields": {"stage": stage.value}})
        _handle_failure(rt, job_id, stage, "INTERNAL", GENERIC_FAILURE, f"{type(exc).__name__}: {exc}", True)
        return

    def complete(j: Job, w: Wallet) -> tuple[Job, Wallet]:
        if stage not in j.completed_stages:
            j.completed_stages.append(stage)
        j.attempts = 0
        j.lease_until = None
        j.stage = next((s for s in j.pipeline if s not in j.completed_stages), None)
        if j.stage is None:
            state.transition(j, JobStatus.COMPLETED, "Completed with warnings" if j.outcome == "PARTIAL" else "Completed")
            settle_completed(j, w)
        return j, w

    result = rt.store.update_job_and_wallet(job_id, complete)
    assert result is not None
    job = result[0]
    log(logger, logging.INFO, "stage complete", stage=stage.value, durationMs=int((utcnow() - started).total_seconds() * 1000))
    if job.status == JobStatus.PROCESSING:
        rt.queue.enqueue(job_id, task_name(job))


def _continue_later(rt: Runtime, job_id: str, stage: Stage) -> None:
    """Release the lease and deliver the same stage again; its finished calls replay from the cache."""

    def release(j: Job) -> Job | None:
        if j.status != JobStatus.PROCESSING or j.stage != stage:
            return None  # cancelled or failed meanwhile: stop here
        j.lease_until = None
        j.events.append(JobEvent(label=f"Continuing {stage.value.lower()} in a new task"))
        return j

    job = rt.store.update(job_id, release)
    if job is not None:
        rt.queue.enqueue(job_id, task_name(job, f"-c{len(job.events)}"))


def _finish(rt: Runtime, job_id: str) -> None:
    def done(j: Job, w: Wallet) -> tuple[Job, Wallet] | None:
        if j.status != JobStatus.PROCESSING:
            return None
        j.lease_until = None
        state.transition(j, JobStatus.COMPLETED, "Completed")
        settle_completed(j, w)
        return j, w

    rt.store.update_job_and_wallet(job_id, done)


def _handle_failure(rt: Runtime, job_id: str, stage: Stage, code: str, message: str, detail: str, retryable: bool) -> None:
    settings = rt.settings
    retry_again = False

    def fail(j: Job, w: Wallet) -> tuple[Job, Wallet]:
        nonlocal retry_again
        j.lease_until = None
        if retryable and j.attempts + 1 < settings.stage_max_attempts:
            j.attempts += 1
            j.events.append(JobEvent(label=f"Retrying {stage.value.lower()} after {code}"))
            retry_again = True
            return j, w
        j.failure = JobFailure(code=code, user_message=message, retryable=retryable)
        j.failure_detail = f"stage={stage.value} {detail}"[:500]
        state.transition(j, JobStatus.FAILED, f"Failed: {code}")
        refund_job(j, w, "Job failed, so nothing was charged")
        return j, w

    result = rt.store.update_job_and_wallet(job_id, fail)
    job = result[0] if result else None
    log(logger, logging.WARNING, "stage failed", stage=stage.value, code=code, retryable=retryable, willRetry=retry_again)
    if job and retry_again:
        delay = min(300, 10 * 2**job.attempts)
        rt.queue.enqueue(job_id, task_name(job, f"-a{job.attempts}"), delay_sec=delay)


def _set(j: Job, **fields: Any) -> Job:
    for key, value in fields.items():
        setattr(j, key, value)
    return j


def _add_warnings(j: Job, warnings: list[str]) -> Job:
    j.warnings = list(dict.fromkeys(j.warnings + warnings))
    return j


def _method(ctx: StageContext, kind: str) -> str:
    settings = ctx.rt.settings
    lead, writer = settings.lead_model.split(":")[-1], settings.writer_model.split(":")[-1]
    if kind == "analysis":
        return f"PaperAid writing-pattern signals + analysis by {lead}"
    if kind == "formatting":
        return f"Rules drafted and reviewed by {lead}, critiqued and fixed by {writer}, applied by PaperAid's formatter"
    return f"Plan drafted and finalised by {lead}, critiqued by {writer}; rewritten by {writer}; reviewed by {lead}"
