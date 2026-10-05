"""The analysis report step (owner decision 2026-10-03). DRAFTING: the writer interprets the computed
results through number tokens; code checks the draft (every required part present and substantive,
the wording rules) and the writer repairs what code finds (at most two rounds). AUDITING: the whole
document is assembled by code (every section, table, note and appendix, numbers filled in) and the
one accountable final reviewer (Sol) reads exactly that, in parts with a manifest when it is long,
and must give an explicit PASS on every rule (Codex audit, finding 5). Objections are repaired and
the reassembled document reviewed again, at most twice; a review that is missing, cut off, refused
or unaffordable is "not reviewed", never approval, and the step fails without charge. EXPORTING:
the approved document itself (not a rebuild) is published, completed and settled in one
transaction, only if the data, the analyses and, for Chapter Four, the proposal's plan and Chapter
Three are still what it was written from."""

import hashlib
import json
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel

from app.ai.orchestration import FINAL_PART_WORDS, REVIEW_REPAIRS, AIRunner, check_content
from app.core.errors import PermanentStageError, RetryableStageError
from app.datalab import narrative, report
from app.datalab.models import DataProject, ReportVersion
from app.datalab.report import ReportDocument, ReportSection
from app.datalab.service import INPUT, ReportInput, still_current
from app.jobs import state
from app.jobs.models import Job, JobStatus, Stage, Wallet, utcnow
from app.pricing.billing import settle_completed
from app.works.ai import RULE_VERDICTS, RuleVerdict, _enum, _list, _obj

if TYPE_CHECKING:
    from app.jobs.pipeline import StageContext

DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
_S, _STRS = {"type": "string"}, {"type": "array", "items": {"type": "string"}}
REPORT_SCHEMA = _obj({"summary": _STRS, "findings": _list(_obj({"id": _S, "paragraphs": _STRS})), "keyFindings": _STRS, "limitations": _STRS, "conclusions": _STRS})
CHAPTER_SCHEMA = _obj({"introduction": _STRS, "findings": _list(_obj({"id": _S, "paragraphs": _STRS})), "summary": _STRS})
REVIEW_SCHEMA = _obj({"verdict": _enum("PASS", "REPAIR"), "rules": RULE_VERDICTS, "issues": _STRS, "suggestions": _STRS})
RULES = {"REPORT": ["R1", "R2", "R3", "R4", "R5", "R6", "R7", "R8"], "CHAPTER_FOUR": ["R1", "R2", "R3", "R4", "R5", "R6", "R7", "R8", "R9"]}
NOT_FINISHED = "PaperAid couldn't finish a report it could stand behind this time. Nothing was charged; please try again."
CHANGED = "Your data, its settings or your proposal changed while the report was being written, so it wasn't delivered. Nothing was charged; please start it again."


class _Finding(BaseModel):
    id: str
    paragraphs: list[str]


class Draft(BaseModel):
    summary: list[str]
    findings: list[_Finding]
    keyFindings: list[str]  # noqa: N815
    limitations: list[str]
    conclusions: list[str]


class ChapterDraft(BaseModel):
    introduction: list[str]
    findings: list[_Finding]
    summary: list[str]


class Review(BaseModel):
    verdict: str
    rules: list[RuleVerdict]
    issues: list[str]
    suggestions: list[str] = []


class DataRunner(AIRunner):
    def report(self, payload: dict[str, Any]) -> Draft:
        answer = self._call("d_report", payload, REPORT_SCHEMA, Draft)
        if answer is None:
            raise RetryableStageError("OUTPUT_TRUNCATED", "PaperAid's writer was cut off. It will try again.", "answer did not fit on d_report")
        return answer

    def chapter(self, payload: dict[str, Any]) -> ChapterDraft:
        answer = self._call("d_chapter4", payload, CHAPTER_SCHEMA, ChapterDraft)
        if answer is None:
            raise RetryableStageError("OUTPUT_TRUNCATED", "PaperAid's writer was cut off. It will try again.", "answer did not fit on d_chapter4")
        return answer

    def write(self, chapter: bool, payload: dict[str, Any]) -> dict[str, Any]:
        """A report's narrative, or Chapter Four's (the same rules, its own parts)."""
        return (self.chapter(payload) if chapter else self.report(payload)).model_dump()

    def final_review(self, payload: dict[str, Any]) -> Review | None:
        check_review_size(payload)
        try:
            return self._call("d_report_review", payload, REVIEW_SCHEMA, Review)
        except PermanentStageError as exc:
            if exc.code != "BUDGET_EXCEEDED":
                raise
            self.budget_reached = True
            return None


def _input(ctx: "StageContext") -> ReportInput:
    check_content(ctx.job.quote.engine if ctx.job.quote else None)
    return ReportInput.model_validate(ctx.get_json(INPUT))


def _runner(ctx: "StageContext") -> DataRunner:
    runner = ctx.ai(DataRunner)
    assert isinstance(runner, DataRunner)
    return runner


def _context(inp: ReportInput) -> tuple[dict[str, tuple[str, str]], dict[str, str], dict[str, Any]]:
    general = {"records": (f"{inp.rows:,}", "the records in the dataset"), "variables": (f"{inp.columns:,}", "the variables in the dataset"),
               "analyses": (f"{len(inp.analyses):,}", "the analyses reported"), "alpha": (f"{inp.alpha:g}".lstrip("0") or "0", "the significance level"),
               "ci": ("95%", "the confidence level of every interval")}
    values, prefixes = narrative.tokens(inp.analyses, general)
    dataset = {"source": inp.source_name, "records": "⟦N:records⟧", "variables": "⟦N:variables⟧", "version": inp.version,
               "changes": [s.description for s in inp.cleaning]}
    chapter = inp.mode == "CHAPTER_FOUR"
    return values, prefixes, narrative.payload(inp.title, inp.purpose, dataset, inp.alpha, inp.analyses, prefixes, values,
                                               inp.objectives if chapter else None, inp.objective_of,
                                               [p.model_dump() for p in inp.chapter_three] if chapter else None, inp.missing_objectives if chapter else None)


def stage_drafting(ctx: "StageContext") -> None:
    inp = _input(ctx)
    runner = _runner(ctx)
    values, prefixes, payload = _context(inp)
    chapter = inp.mode == "CHAPTER_FOUR"
    draft = runner.write(chapter, payload)
    rounds = [{"round": 0, "problems": []}]
    for round_ in range(1, REVIEW_REPAIRS + 2):
        found = narrative.problems(draft, inp.analyses, prefixes, values, inp.alpha, inp.mode)
        rounds[-1]["problems"] = found
        if not found:
            break
        if round_ > REVIEW_REPAIRS:
            ctx.put_json("report_rounds.json", rounds)
            raise PermanentStageError("DOCUMENT_NOT_APPROVED", NOT_FINISHED, "code checks still failing: " + "; ".join(found)[:300])
        draft = runner.write(chapter, {**payload, "draft": draft, "critique": found})
        rounds.append({"round": round_, "problems": []})
    ctx.put_json("report_rounds.json", rounds)
    ctx.put_json("draft.json", draft)


def assemble(inp: ReportInput, draft: dict[str, Any], values: dict[str, tuple[str, str]]) -> ReportDocument:
    """The whole deliverable, as it will be downloaded."""
    def fill(text: str) -> str:
        return narrative.fill(text, values)

    if inp.mode == "CHAPTER_FOUR":
        return report.build_chapter(inp.title, inp.rows, inp.version, inp.cleaning, inp.objectives, inp.objective_of, inp.analyses, inp.charts, draft, fill,
                                    inp.missing_objectives)
    return report.build(inp.title, inp.source_name, inp.sheet, inp.version, inp.rows, inp.columns, inp.alpha, inp.threshold, inp.cleaning, inp.variables,
                        inp.analyses, inp.charts, draft, fill, inp.released)


def _rendered(section: ReportSection, written: set[str] | None = None) -> dict[str, Any]:
    """A section as the reviewer reads it: its text, its tables cell by cell, its notes. With `written`
    (the writer's text as filled in), each paragraph and bullet says who wrote it: the writer, whom a
    repair can change, or PaperAid's code (live check 2026-10-04)."""
    def by(texts: list[str]) -> list[Any]:
        return texts if written is None else [{"by": "WRITER" if t in written else "CODE", "text": t} for t in texts]

    return {"key": section.key, "heading": section.heading, "paragraphs": by(section.paragraphs), "bullets": by(section.bullets),
            "tables": [{"title": t.title, "columns": t.columns, "rows": [[c.text for c in r] for r in t.rows], "notes": t.notes} for t in section.tables],
            "figure": bool(section.chart), "notes": section.notes}


def _words(entry: Any) -> int:
    return len(json.dumps(entry, ensure_ascii=False).split())


def check_review_size(payload: Any) -> None:
    if _words(payload) > FINAL_PART_WORDS:
        raise PermanentStageError("REVIEW_INPUT_TOO_LARGE",
                                  "PaperAid could not fit this document and its supporting evidence into a complete review. Nothing was charged. Please use fewer analyses or shorter supporting material.",
                                  f"review request exceeds {FINAL_PART_WORDS} words")


def split_rendered(entry: dict[str, Any], limit: int) -> list[dict[str, Any]]:
    """A rendered section longer than `limit` words in consecutive pieces within it: paragraphs and bullets
    cut at sentence ends, tables by rows with their columns repeated (Codex audit 2026-10-04, finding 7:
    one 20,000-word section was a single review part)."""
    from app.works.pipeline import _chunks

    if _words(entry) <= limit:
        return [entry]
    shell = {k: v for k, v in entry.items() if k not in ("paragraphs", "bullets", "tables", "notes")}
    room = max(60, limit - _words(shell) - 12)
    pieces: list[dict[str, Any]] = [{"paragraphs": [], "bullets": [], "tables": [], "notes": []}]

    def add(kind: str, item: Any) -> None:
        if _words(pieces[-1]) > 8 and _words(pieces[-1]) + _words(item) > room:
            pieces.append({"paragraphs": [], "bullets": [], "tables": [], "notes": []})
        pieces[-1][kind].append(item)

    def text_items(kind: str) -> None:
        for item in entry.get(kind, []):
            text = item["text"] if isinstance(item, dict) else item
            for chunk in _chunks(text, max(20, room // 2)):
                add(kind, {**item, "text": chunk} if isinstance(item, dict) else chunk)

    text_items("paragraphs")
    text_items("bullets")
    for table in entry.get("tables", []):
        head = {k: v for k, v in table.items() if k != "rows"}
        rows: list[list[str]] = []
        for row in table["rows"]:
            cells = [_chunks(c, max(10, room // (2 * max(1, len(row))))) for c in row]  # a cell longer than a piece continues on further rows
            for i in range(max(len(c) for c in cells)):
                rows.append([c[i] if i < len(c) else "" for c in cells])
        part = {**head, "rows": []}
        for row in rows:
            if part["rows"] and _words(part) + _words(row) > room:
                add("tables", part)
                part = {**head, "title": f"{head.get('title', '')} (continued)", "rows": []}
            part["rows"].append(row)
        add("tables", part)
    for note in entry.get("notes", []):
        for chunk in _chunks(note, max(20, room // 2)):
            add("notes", chunk)
    return [{**shell, "heading": entry["heading"] if n == 0 else f"{entry['heading']} (continued, piece {n + 1} of {len(pieces)})", **piece}
            for n, piece in enumerate(pieces)]


def bounded_parts(entries: list[dict[str, Any]], repeated: Any) -> tuple[list[list[dict[str, Any]]], list[dict[str, Any]]]:
    """Sections in review parts of at most FINAL_PART_WORDS each, counting what every part repeats (the
    inputs and the manifest); the manifest names the part each section is in."""
    reserve = 100  # document title, subtitle, part labels and JSON envelope
    bound = FINAL_PART_WORDS - _words(repeated) - 12 * len(entries) - reserve
    for _ in range(16):  # the manifest grows as long sections are split
        if bound < 80:
            check_review_size({"context": repeated, "document": entries})
            raise PermanentStageError("REVIEW_INPUT_TOO_LARGE", "PaperAid could not fit the complete evidence into its review. Nothing was charged. Please use fewer analyses or shorter supporting material.")
        parts: list[list[dict[str, Any]]] = [[]]
        words = 0
        for entry in entries:
            for piece in split_rendered(entry, bound):
                size = _words(piece)
                if parts[-1] and words + size > bound:
                    parts.append([])
                    words = 0
                parts[-1].append(piece)
                words += size
        manifest = [{"key": e["key"], "heading": e["heading"], "part": n} for n, part in enumerate(parts, start=1) for e in part]
        over = max(_words(part) for part in parts) + _words(repeated) + _words(manifest) + reserve - FINAL_PART_WORDS
        if over <= 0:
            return parts, manifest
        bound -= over + 50
    raise PermanentStageError("REVIEW_INPUT_TOO_LARGE", "PaperAid could not fit the complete evidence into its review. Nothing was charged. Please use fewer analyses or shorter supporting material.")


def document_parts(document: ReportDocument, written: set[str] | None = None, repeated: Any = None) -> tuple[list[list[dict[str, Any]]], list[dict[str, Any]]]:
    """The document in bounded parts (every section and appendix, in order) and the manifest of the whole."""
    return bounded_parts([_rendered(s, written) for s in document.sections + document.appendices], repeated or {})


def _dataset(inp: ReportInput) -> dict[str, Any]:
    """The facts PaperAid's code states about the data, so the reviewer can check that text against them."""
    return {"file": inp.source_name, "sheet": inp.sheet, "records": inp.rows, "variables": inp.columns, "version": inp.version,
            "preparation": [{"step": s.description, "how": "applied automatically" if s.automatic else "confirmed by the researcher"} for s in inp.cleaning],
            "columns": [{"name": v.title(), "type": v.kind, "withValue": v.valid, "missing": v.missing, "setAside": v.excluded} for v in inp.variables],
            "includedByResearcher": inp.released}


def _written(draft: dict[str, Any], values: dict[str, tuple[str, str]]) -> set[str]:
    """Every paragraph and bullet of the writer's draft, as it prints."""
    texts = [t for key in ("summary", "keyFindings", "limitations", "conclusions", "introduction") for t in draft.get(key, [])]
    texts += [t for f in draft.get("findings", []) for t in f.get("paragraphs", [])]
    return {narrative.fill(t, values) for t in texts}


def _review(runner: DataRunner, inp: ReportInput, document: ReportDocument, analyses: list[dict[str, Any]], previous: list[str],
            written: set[str]) -> Review | None:
    """Sol's review of the exact document, part by part. A rule passes only with an explicit PASS in
    every part; any missing verdict, cut-off or unaffordable part: None (not reviewed)."""
    rules = RULES[inp.mode]
    base: dict[str, Any] = {"mode": inp.mode, "significanceLevel": inp.alpha, "dataset": _dataset(inp), "analyses": analyses, "rules": rules,
                            **({"previousIssues": previous} if previous else {})}
    if inp.mode == "CHAPTER_FOUR":
        base["objectives"] = [{"number": n, "objective": text} for n, text in enumerate(inp.objectives, start=1)]
        base["chapterThree"] = [p.model_dump() for p in inp.chapter_three]
    parts, manifest = document_parts(document, written, base)
    base["manifest"] = manifest
    verdicts: dict[str, RuleVerdict] = {}
    issues: list[str] = []
    suggestions: list[str] = []
    passed = True
    for n, part in enumerate(parts, start=1):
        answer = runner.final_review({**base, "part": f"{n} of {len(parts)}", "document": {"title": document.title, "subtitle": document.subtitle, "sections": part}})
        if answer is None or not set(rules) <= {r.rule for r in answer.rules}:
            return None
        passed = passed and answer.verdict == "PASS"
        issues += answer.issues
        suggestions += answer.suggestions
        for r in answer.rules:
            if r.rule in rules and (r.rule not in verdicts or verdicts[r.rule].status == "PASS"):
                verdicts[r.rule] = r  # a FAIL (or anything but PASS) in any part stands
    return Review(verdict="PASS" if passed else "REPAIR", rules=[verdicts[r] for r in rules], issues=list(dict.fromkeys(issues)),
                  suggestions=list(dict.fromkeys(suggestions)))


def stage_auditing(ctx: "StageContext") -> None:
    inp = _input(ctx)
    runner = _runner(ctx)
    values, prefixes, payload = _context(inp)
    chapter = inp.mode == "CHAPTER_FOUR"
    draft = ctx.get_json("draft.json")
    analyses = [{"ref": prefixes[r.id], "title": r.title, "question": r.record.question, "method": r.record.method, "status": r.status, "warnings": r.warnings,
                 "numbers": {k.split(".", 1)[1]: v for k, (v, _m) in values.items() if k.startswith(prefixes[r.id] + ".")},
                 "record": r.record.model_dump(mode="json", by_alias=True)} for r in inp.analyses]
    seen: list[dict[str, Any]] = []
    previous: list[str] = []
    for round_ in range(REVIEW_REPAIRS + 1):
        document = assemble(inp, draft, values)
        review = _review(runner, inp, document, analyses, previous, _written(draft, values))
        if review is None:
            ctx.put_json("report_review.json", seen)
            raise PermanentStageError("DOCUMENT_NOT_APPROVED", NOT_FINISHED, "final review not completed (missing verdict, cut off or spend cap)")
        not_passed = [f"{r.rule}: {r.note}" for r in review.rules if r.status != "PASS"]  # NOT_APPLICABLE is not approval
        seen.append({"round": round_, "verdict": review.verdict, "failed": not_passed, "issues": review.issues, "suggestions": review.suggestions})
        objections = list(dict.fromkeys([*review.issues, *not_passed]))
        if review.verdict == "PASS" and not objections:
            data = document.model_dump(mode="json", by_alias=True)
            ctx.put_json("report_review.json", seen)
            ctx.put_json("approved.json", {"draft": draft, "document": data, "sha": hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest(),
                                           "suggestions": review.suggestions})
            return
        if round_ == REVIEW_REPAIRS or runner.budget_reached:
            break
        repaired = runner.write(chapter, {**payload, "draft": draft, "critique": objections})
        code = narrative.problems(repaired, inp.analyses, prefixes, values, inp.alpha, inp.mode)
        if code:  # a repair that breaks a code rule is not shown to the reviewer
            repaired = runner.write(chapter, {**payload, "draft": repaired, "critique": code})
            if narrative.problems(repaired, inp.analyses, prefixes, values, inp.alpha, inp.mode):
                break
        draft, previous = repaired, objections
    ctx.put_json("report_review.json", seen)
    last = seen[-1] if seen else {"issues": [], "failed": []}
    raise PermanentStageError("DOCUMENT_NOT_APPROVED", NOT_FINISHED, "final reviewer still objecting: " + "; ".join(last["issues"] + last["failed"])[:300])


def stage_exporting(ctx: "StageContext") -> None:
    inp = _input(ctx)
    approved = ctx.get_json("approved.json")
    data = approved["document"]
    if hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest() != approved["sha"]:
        raise PermanentStageError("DOCUMENT_NOT_APPROVED", NOT_FINISHED, "approved document does not match its hash")
    document = ReportDocument.model_validate(data)  # exactly what the reviewer approved: never rebuilt
    project = ctx.rt.store.get_datalab(inp.project_id)
    if project is None or project.deleting:
        raise PermanentStageError("DATALAB_DELETED", "This project was deleted before the report was finished, so nothing was charged.", "project gone at export")
    changed = still_current(ctx.rt, inp)
    if changed:
        raise PermanentStageError("DATA_CHANGED", CHANGED, f"not current at export: {changed}")
    files = ctx.rt.files

    def chart_bytes(path: str) -> bytes | None:
        return files.get(path) if path and files.exists(path) else None

    docx = report.to_docx(document, chart_bytes)
    job_id = ctx.job.id
    doc_path = f"{project.storage_prefix()}/reports/{job_id}.json"
    docx_path = f"{project.storage_prefix()}/reports/{job_id}.docx"
    files.put(doc_path, document.model_dump_json(by_alias=True).encode(), "application/json")
    files.put(docx_path, docx, DOCX)
    gone = False

    def finish(j: Job, w: Wallet, p: DataProject | None) -> tuple[Job, Wallet, DataProject] | None:
        nonlocal gone
        gone = p is None or p.deleting
        if p is None or p.deleting:
            return None
        if j.status != JobStatus.PROCESSING or j.stage != Stage.EXPORTING:
            return None
        if not any(r.job_id == job_id for r in p.reports):
            version = len(p.reports) + 1
            p.reports.append(ReportVersion(version=version, path=doc_path, docx=docx_path, job_id=job_id, analyses=[r.id for r in inp.analyses], kind=inp.mode))
            p.report_current = version
        p.updated_at = utcnow()
        j.outcome = j.outcome or "FULL"
        if Stage.EXPORTING not in j.completed_stages:
            j.completed_stages.append(Stage.EXPORTING)
        j.attempts, j.lease_until, j.stage = 0, None, None
        state.transition(j, JobStatus.COMPLETED, "Completed")
        settle_completed(j, w)
        return j, w, p

    ctx.rt.store.update_job_wallet_and_datalab(job_id, inp.project_id, finish)
    if gone:
        raise PermanentStageError("DATALAB_DELETED", "This project was deleted before the report was finished, so nothing was charged.", "project deleting at export")


STAGES = {Stage.DRAFTING: stage_drafting, Stage.AUDITING: stage_auditing, Stage.EXPORTING: stage_exporting}
