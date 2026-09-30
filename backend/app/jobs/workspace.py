"""The review workspace (owner request 2026-09-28, master context §9-15): the student reads their
paper next to the findings, dismisses what does not apply, asks PaperAid to fix chosen passages,
and after refinement keeps or rejects each change before downloading. No AI runs here: fixing is a
new, priced job, and a download with the student's choices is rebuilt by code from the original
Word file, so every other part of it stays exactly as it was."""

import hashlib
import json
import logging
import re
import secrets
from datetime import timedelta
from typing import Any

from app.analysis import signals
from app.core.errors import AppError, Conflict, NotFound
from app.core.logging import log
from app.documents import groups as paragraph_groups
from app.documents import protect
from app.documents.docx_io import apply_group_rewrites, apply_revisions, read_docx
from app.documents.intake import inspect_upload
from app.documents.model import DocumentModel
from app.documents.pdf_io import read_pdf
from app.formatting.apply import apply_formatting
from app.formatting.guideline import to_spec
from app.formatting.presets import PRESETS, with_custom
from app.jobs.models import ChangedBlock, Job, JobEvent, JobStatus, JobView, ServiceSelection, StoredFile, StoredOutput, utcnow
from app.jobs.pipeline import StageContext, _analysis_after, with_logo
from app.jobs.service import ACCOUNT_CLOSING, DOCX_TYPE, User, _owned, _rate_limit
from app.runtime import Runtime

logger = logging.getLogger("paperaid.workspace")
FINDING_ID = re.compile(r"^[A-Za-z0-9_-]{1,40}$")
MAX_DISMISSED = 500


def _readable(rt: Runtime, job: Job) -> Job:
    if job.files_deleted or job.expires_at < utcnow():
        raise AppError("This paper's files were deleted under our retention policy.", code="FILES_EXPIRED", status=410)
    return job


def _internal(rt: Runtime, job: Job, name: str) -> Any:
    path = f"{job.storage_prefix()}/internal/{name}"
    return json.loads(rt.files.get(path)) if rt.files.exists(path) else None


def document(rt: Runtime, user: User, job_id: str) -> dict[str, Any]:
    """The paper as PaperAid read it (paragraph by paragraph), and for a refined job every change
    in full, so the workspace can show the whole document beside its findings."""
    job = _readable(rt, _owned(rt, user, job_id))
    raw = _internal(rt, job, "document.json")
    if raw is not None:
        model = DocumentModel.model_validate(raw)
    elif job.source is not None:  # not processed yet: the paper as uploaded, so it shows at once
        data = rt.files.get(job.source.path)
        model = read_docx(data) if job.source.format == "DOCX" else read_pdf(data, rt.settings.max_pdf_pages)
    else:
        raise NotFound("Upload your paper first.")
    blocks = [{"id": b.id, "kind": b.kind, "level": b.level, "section": b.section, "text": b.text} for b in model.blocks if b.text.strip()]
    groups = {g.id: g.block_ids for g in paragraph_groups.groups(model)} if job.refinement and job.refinement.mode == "REDRAFT" else {}
    changes = [ChangedBlock.model_validate(c).model_dump(by_alias=True) for c in _internal(rt, job, "changes_full.json") or []]
    result = {"blocks": blocks, "groups": groups, "changes": changes}
    if not rt.settings.show_ai_score:
        return result
    percent = job.analysis.percent if job.analysis else None
    if job.analysis is not None and job.analysis.coverage_complete is not False and percent is None and raw is not None:
        percent = _saved_percent(rt, job, model)
    percent_after = job.analysis_after.percent if job.analysis_after else None
    if job.analysis_after is not None and job.analysis_after.coverage_complete is not False and percent_after is None:
        if job.refinement is not None and job.refinement.refined_blocks == 0:
            percent_after = percent
        elif (
            job.analysis_after.algorithm_version == signals.ALGORITHM_VERSION
            and raw is not None and _internal(rt, job, "analysis.json") is not None
            and rt.files.exists(f"{job.storage_prefix()}/internal/refined.docx")
        ):
            percent_after = _analysis_after(StageContext(rt, job), job.analysis_after.method).percent
    return {**result, "percent": percent, "percentAfter": percent_after}


def _saved_percent(rt: Runtime, job: Job, model: DocumentModel) -> int | None:
    """The percentage for an analysis made before it was recorded: the same word-weighted blend of
    PaperAid's signal scores and the lead's judgements, from the scores the analysis saved."""
    saved = _internal(rt, job, "analysis.json")
    if not saved or "scores" not in saved:
        return None
    words = {b.id: b.words for b in model.blocks}
    model_scores = saved.get("modelScores") or {}
    total = sum(words.get(bid, 0) for bid in saved["scores"])
    if not total:
        return 0 if job.analysis is not None and job.analysis.analysed_words == 0 else None
    score = sum((0.5 * s + 0.5 * model_scores[bid] if bid in model_scores else s) * words.get(bid, 0) for bid, s in saved["scores"].items()) / total
    return int(max(0.0, min(1.0, score)) * 100 + 1e-9)


def set_finding(rt: Runtime, user: User, job_id: str, finding_id: str, dismissed: bool) -> JobView:
    """Dismiss a finding, or undo that. Only the student's view changes; the report keeps it."""
    job = _owned(rt, user, job_id)
    known = {f.id for f in (job.analysis.findings + job.analysis.review if job.analysis else [])}
    if not FINDING_ID.match(finding_id) or finding_id not in known:
        raise NotFound("We couldn't find that finding.")

    def apply(j: Job) -> Job:
        rest = [f for f in j.dismissed if f != finding_id]
        j.dismissed = (rest + [finding_id])[-MAX_DISMISSED:] if dismissed else rest
        return j

    updated = rt.store.update(job.id, apply)
    assert updated is not None
    return updated.view()


def set_change(rt: Runtime, user: User, job_id: str, change_id: str, accepted: bool) -> JobView:
    """Keep a refined passage, or keep the student's own wording for it instead."""
    job = _owned(rt, user, job_id)
    if job.refinement is None or not any(c.block_id == change_id and not c.kept for c in job.refinement.changes):
        raise NotFound("We couldn't find that change.")

    def apply(j: Job) -> Job:
        rest = [c for c in j.rejected_changes if c != change_id]
        j.rejected_changes = rest if accepted else rest + [change_id]
        j.outputs = [o for o in j.outputs if o.id != "paper-reviewed"]  # it no longer matches the choices
        return j

    updated = rt.store.update(job.id, apply)
    assert updated is not None
    return updated.view()


def rebuild(rt: Runtime, user: User, job_id: str) -> JobView:
    """A Word file with only the changes the student kept: rebuilt from the original file by code
    (the same patching the job used), then formatted again when the job included formatting."""
    job = _readable(rt, _owned(rt, user, job_id))
    _rate_limit(rt, user, "rebuild", rt.settings.uploads_per_hour)  # each rebuild re-reads and re-formats the paper (M21)
    if job.status != JobStatus.COMPLETED or job.refinement is None or job.source is None:
        raise Conflict("Only a finished refinement can be rebuilt.", code="NOT_REFINED")
    built = _with_choices(rt, job)
    if built is None:
        raise Conflict("This job was refined before choices could be made. Its downloads are unchanged.", code="NO_CHOICES")
    paper, kept, total = built
    path = f"{job.storage_prefix()}/output/paper-reviewed-{secrets.token_hex(6)}.docx"
    rt.files.put(path, paper, DOCX_TYPE)
    stem = job.source.name.rsplit(".", 1)[0][:120]
    output = StoredOutput(
        id="paper-reviewed",
        label=f"Your choices: {kept} of {total} changes kept (Word)",
        name=f"{stem} – your choices.docx",
        size_bytes=len(paper),
        path=path,
        content_type=DOCX_TYPE,
    )
    choices = sorted(job.rejected_changes)

    def save(j: Job) -> Job | None:
        if sorted(j.rejected_changes) != choices:
            return None  # the choices changed while this was built: never offer a file that no longer matches them
        j.outputs = [o for o in j.outputs if o.id != "paper-reviewed"] + [output]
        return j

    updated = rt.store.update(job.id, save)
    if updated is None:
        rt.files.delete(path)
        raise Conflict("Your choices changed while the file was being made. Download again.", code="CHOICES_CHANGED")
    return updated.view()


def _with_choices(rt: Runtime, job: Job, block_map: dict[str, str] | None = None) -> tuple[bytes, int, int] | None:
    """The finished paper with exactly the changes the student keeps now (formatting and logo
    applied as the job chose), or None for a job refined before choices were recorded."""
    assert job.source is not None
    saved = _internal(rt, job, "accepted.json")
    raw = _internal(rt, job, "document.json")
    if job.refinement is None:  # a formatting-only result uses the same layout operations and mapping
        saved = {"revised": {}, "deep": False}
        raw = raw or read_docx(rt.files.get(job.source.path)).model_dump()
    if saved is None or raw is None:
        return None
    model = DocumentModel.model_validate(raw)
    if block_map is not None:
        if saved["deep"]:
            raise AppError("Choose the whole redrafted paper, or upload its Word file to select individual passages.", code="INVALID_SELECTION")
        block_map.update({b.id: b.id for b in model.blocks})
    kept = {bid: text for bid, text in saved["revised"].items() if bid not in set(job.rejected_changes)}
    source = rt.files.get(job.source.path)
    if saved["deep"]:
        groups = {g.id: g for g in paragraph_groups.groups(model)}
        rewrites = [(groups[gid].block_ids, paragraph_groups.to_docx(groups[gid], text), groups[gid].xmap) for gid, text in kept.items() if gid in groups]
        paper = apply_group_rewrites(source, rewrites) if rewrites else source
    else:
        blocks = model.by_id()
        patch = {bid: protect.unmask(text, protect.mask(blocks[bid].masked or "")[1]) for bid, text in kept.items() if bid in blocks}
        paper = apply_revisions(source, patch) if patch else source
    if job.selection.formatting == "FORMAT":
        paper, _ = apply_formatting(paper, with_custom(PRESETS[job.selection.preset], job.selection.custom), read_docx(paper), block_map)
    elif job.selection.formatting == "TEMPLATE_FORMAT":
        spec_saved, guide = _internal(rt, job, "spec.json"), _internal(rt, job, "guide.json")
        if spec_saved and guide:
            spec, _, _, _ = to_spec(spec_saved["final"], "Your guide", guide["text"])
            paper, _ = apply_formatting(paper, spec, read_docx(paper), block_map)
        elif block_map is not None:
            raise Conflict("This older layout cannot safely map passages. Choose the whole paper or upload its Word file.", code="NO_CHOICES")
    paper, _ = with_logo(rt, job, paper, block_map)
    return paper, len(kept), len(saved["revised"])


def continue_from(rt: Runtime, user: User, job_id: str, origin: str, instruction: str, blocks: list[str]) -> JobView:
    """The next step on the same screen: a new draft of this paper, as uploaded ("original") or as
    PaperAid finished it ("result"), priced and started like any job. With an instruction, the
    student's own request is what the writer follows for the chosen passages (or the whole paper)."""
    job = _readable(rt, _owned(rt, user, job_id))
    if job.status != JobStatus.COMPLETED or job.source is None:
        raise Conflict("Wait for this job to finish first.", code="NOT_FINISHED")
    block_map: dict[str, str] = {}
    picked = list(dict.fromkeys(blocks))
    if origin == "result":
        output = next((o for o in job.outputs if o.id == "paper"), None)
        if output is None or output.content_type != DOCX_TYPE:
            raise AppError("There is no finished Word file to continue from.", code="NO_RESULT")
        # the student's current keep/undo choices, built now, so rejected wording never comes back
        built = _with_choices(rt, job, block_map if picked else None)
        data, name = (built[0] if built else rt.files.get(output.path)), output.name
    else:
        data, name = rt.files.get(job.source.path), job.source.name
    instruction = " ".join(instruction.split())[:1000]
    _rate_limit(rt, user, "draft", rt.settings.quotes_per_hour)
    model = inspect_upload(data, name, rt.settings.max_upload_bytes, rt.settings.max_words, rt.settings.max_pdf_pages)
    selection = ServiceSelection(writing="REFINE" if model.format == "DOCX" else "AI_CHECK", style=job.selection.style)
    notes: dict[str, list[str]] = {}
    if instruction:
        if model.format != "DOCX":
            raise AppError("Changes need the Word file. Upload the .docx version of this paper.", code="PDF_AI_CHECK_ONLY")
        editable = [b.id for b in model.blocks if b.editable and b.kind in ("paragraph", "list_item")]
        if origin == "result" and picked:
            if any(b not in block_map for b in picked):
                raise AppError("Some of the passages you picked can't be identified in this result. Pick them again.", code="INVALID_SELECTION")
            picked = [block_map[b] for b in picked]
        if any(b not in set(editable) for b in picked):
            raise AppError("Some of the passages you picked can't be changed here. Pick them again.", code="INVALID_SELECTION")
        if len(picked or editable) > 3000:
            raise AppError("This paper has too many passages to change at once. Pick the passages to change.", code="TOO_LONG")
        chosen = picked or editable  # nothing picked: the whole paper, every passage
        selection = selection.model_copy(update={"academic": False, "only_blocks": chosen})
        # The selection defines its scope; keep one copy even when many individual passages were picked.
        notes = {"*": [f"The student asks: {instruction}"]}
    now = utcnow()
    new = Job(
        id=f"job_{secrets.token_hex(6)}",
        status=JobStatus.DRAFT,
        owner_uid=user.uid,
        owner_email=user.email,
        created_at=now,
        expires_at=now + timedelta(days=rt.settings.retention_days),
        selection=selection,
        source_job=job.id,
        fix_notes=notes,
        events=[JobEvent(at=now, label=f"Draft continued from {job.id} ({'finished paper' if origin == 'result' else 'original paper'})")],
    )
    digest = hashlib.sha256(data).hexdigest()
    ext = "docx" if model.format == "DOCX" else "pdf"
    path = f"{new.storage_prefix()}/input/source-{digest[:12]}-{secrets.token_hex(4)}.{ext}"
    rt.files.put(path, data, DOCX_TYPE if ext == "docx" else "application/pdf")
    new.source = StoredFile(
        name=name, format=model.format, size_bytes=len(data), word_count=model.word_count, page_estimate=model.page_count or 1,
        heading_count=model.heading_count, path=path, sha256=digest, scorable_words=sum(b.words for b in signals.analysable(model)),
    )
    if not rt.store.create_if_open(new):
        rt.files.delete_prefix(new.storage_prefix())
        raise Conflict(ACCOUNT_CLOSING, code="ACCOUNT_CLOSING")
    log(logger, logging.INFO, "draft continued", jobId=new.id, fromJob=job.id, origin=origin, instructed=bool(instruction))
    return new.view()


def fix_draft(rt: Runtime, user: User, job_id: str, finding_ids: list[str], safe_only: bool) -> JobView:
    """"Fix selected" / "Fix all safe issues": a new refinement draft of the same paper for exactly
    the passages those findings are in. It is priced and started like any job."""
    job = _readable(rt, _owned(rt, user, job_id))
    if job.analysis is None or job.source is None:
        raise Conflict("Check your writing first.", code="NO_ANALYSIS")
    if job.source.format != "DOCX":
        raise AppError("Fixing passages needs the Word file. Upload the .docx version of this paper.", code="PDF_AI_CHECK_ONLY")
    raw = _internal(rt, job, "document.json")
    if raw is None:
        raise Conflict("This paper has not been read yet.", code="NO_ANALYSIS")
    model = DocumentModel.model_validate(raw)
    editable = {b.id: b for b in model.blocks if b.editable and b.kind in ("paragraph", "list_item")}
    findings = [f for f in job.analysis.findings + job.analysis.review if f.id not in set(job.dismissed)]
    chosen = [f for f in findings if f.safe] if safe_only else [f for f in findings if f.id in set(finding_ids)]
    blocks = sorted({f.block_id for f in chosen if f.block_id in editable})
    if not blocks:
        raise AppError("None of the chosen findings is in a passage PaperAid can rewrite. Figures, tables and headings are fixed by you.", code="NOTHING_TO_FIX")
    _rate_limit(rt, user, "draft", rt.settings.quotes_per_hour)
    data = rt.files.get(job.source.path)
    now = utcnow()
    new = Job(
        id=f"job_{secrets.token_hex(6)}",
        status=JobStatus.DRAFT,
        owner_uid=user.uid,
        owner_email=user.email,
        created_at=now,
        expires_at=now + timedelta(days=rt.settings.retention_days),
        # The AI Check already reviewed the paper: its findings travel with the draft, so no second review is paid for.
        selection=ServiceSelection(writing="REFINE", style=job.selection.style, academic=False, only_blocks=blocks[:300]),
        source_job=job.id,
        scope_words=sum(editable[b].words for b in blocks[:300]),
        fix_notes={b: [f"{f.reason}: {f.explanation} {f.suggestion}".strip() for f in chosen if f.block_id == b][:6] for b in blocks[:300]},
        events=[JobEvent(at=now, label=f"Draft created to fix {len(blocks)} passages from {job.id}")],
    )
    digest = hashlib.sha256(data).hexdigest()
    path = f"{new.storage_prefix()}/input/source-{digest[:12]}-{secrets.token_hex(4)}.docx"
    rt.files.put(path, data, DOCX_TYPE)
    new.source = StoredFile(**{**job.source.model_dump(), "path": path})
    if not rt.store.create_if_open(new):
        rt.files.delete_prefix(new.storage_prefix())
        raise Conflict(ACCOUNT_CLOSING, code="ACCOUNT_CLOSING")
    log(logger, logging.INFO, "fix draft created", jobId=new.id, fromJob=job.id, passages=len(blocks))
    return new.view()
