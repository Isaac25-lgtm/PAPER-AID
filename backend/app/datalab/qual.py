"""Qualitative Data Lab (owner decision 2026-10-04): transcripts and open answers analysed thematically.

Before a transcript is stored, the names the researcher lists are replaced with the codes they give,
and every email address, phone number and national ID number with a marker; the original stays on
their device. The paid analysis then runs in three stages, like the quantitative report:

DRAFTING: the analyst codes the transcripts in batches, each code with quotes; code keeps a quote only
if it appears word for word in its transcript (whitespace and quotation marks aside), so no quote is
ever invented. The writer groups the codes into themes and writes them up, citing quotes only by
reference (⟦Q:n⟧): code places each exact quote and its transcript's label, and code alone counts in
how many transcripts a theme appears. Code checks the draft and the writer repairs it (at most twice).

AUDITING: the whole report is assembled (question, data, method, themes with their quotes, limitations,
codebook) and the one accountable final reviewer (Sol) reads exactly it and must pass every rule;
objections are repaired and reviewed again, at most twice; anything else fails without charge.

EXPORTING: the approved report itself is published as Word, with the codebook as Excel, only if the
transcripts are still the ones it was written from."""

import hashlib
import io
import json
import re
from typing import TYPE_CHECKING, Any

import xlsxwriter
from pydantic import BaseModel

from app.ai.orchestration import REVIEW_REPAIRS, AIRunner, check_content
from app.core.errors import PermanentStageError, RetryableStageError
from app.datalab import report
from app.datalab.models import Cell, DataProject, ReportVersion, ResultTable
from app.datalab.report import ReportDocument, ReportSection
from app.jobs import state
from app.jobs.models import Camel, Job, JobStatus, Stage, Wallet, utcnow
from app.pricing.billing import settle_completed
from app.works.ai import RULE_VERDICTS, RuleVerdict, _enum, _list, _obj

if TYPE_CHECKING:
    from app.jobs.pipeline import StageContext

INPUT = "qual_input.json"
ANONYMISATION_VERSION = 1
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
BATCH_WORDS = 9_000  # transcript words one coding call reads
QUOTE_WORDS = (4, 80)
QUOTE_TOKEN = re.compile(r"⟦Q:(\d+)⟧")
DIGIT = re.compile(r"\d")
RAW_QUOTE = re.compile(r"[\"“][^\"”]{40,}[\"”]")  # a long passage in quotation marks: quotes come only by reference
SUBSTANTIVE = 8
RULES = ["Q1", "Q2", "Q3", "Q4", "Q5", "Q6"]
NOT_FINISHED = "PaperAid couldn't finish an analysis it could stand behind this time. Nothing was charged; please try again."
CHANGED = "Your transcripts changed while the analysis was being written, so it wasn't delivered. Nothing was charged; please start it again."

_S, _STRS = {"type": "string"}, {"type": "array", "items": {"type": "string"}}
CODE_SCHEMA = _obj({"codes": _list(_obj({"code": _S, "description": _S, "quotes": _list(_obj({"document": _S, "text": _S}))}))})
THEMES_SCHEMA = _obj({"themes": _list(_obj({"name": _S, "definition": _S, "codes": _STRS, "paragraphs": _STRS})), "summary": _STRS, "limitations": _STRS,
                      "withheld": _STRS})
REVIEW_SCHEMA = _obj({"verdict": _enum("PASS", "REPAIR"), "rules": RULE_VERDICTS, "issues": _STRS, "suggestions": _STRS})


# --- preparing a transcript (before it is stored) -----------------------------------------------------------

EMAIL = re.compile(r"[^@\s]+@[^@\s]+\.[a-z]{2,}", re.I)
NATIONAL_ID = re.compile(r"\bC[MF][A-Z0-9]{12}\b", re.I)
# A phone number in any common layout: +256 772 123 456, 0772 123456, 0772-123-456, (0772) 123 456,
# 256772123456. Only a run that starts as a phone number does (+, 00, 0 or 256) and has 9 to 13 digits,
# so years, dates and figures stay (Codex audit 2026-10-04, finding 1: spaced numbers got through).
# Fixed lengths for Uganda and local numbers prevent the following year or another
# phone from becoming part of the match. Separators never consume a new line.
_SEP = r"[ \t()-]*"  # no dots: a run of decimals ("0.25 0.30 0.45") is not a phone number (Claude's audit 2026-10-05)
PHONE_RUN = re.compile(
    rf"(?<![\w+])(?:\(?\+?256{_SEP}(?:\d{_SEP}){{8}}\d|"
    rf"\(?00256{_SEP}(?:\d{_SEP}){{8}}\d|"
    rf"\(?0{_SEP}(?:\d{_SEP}){{8}}\d|"
    rf"\(?\+\d(?:{_SEP}\d){{8,12}})(?!\w)\)?"
)
NAME_WORDS = re.compile(r"[^\W\d_][\w'’.-]*")


def _phone(match: re.Match[str]) -> str:
    run = match.group()
    digits = re.sub(r"\D", "", run)
    if digits.startswith("00"):
        digits = digits[2:]  # international dialling prefix is not part of the number
    starts = run.lstrip("(").startswith(("+", "0")) or digits.startswith("256")
    return "[phone]" if starts and 9 <= len(digits) <= 13 else run


def _identifiers(text: str) -> tuple[str, int]:
    count = 0
    text, n = EMAIL.subn("[email]", text)
    count += n
    text, n = NATIONAL_ID.subn("[ID number]", text)
    count += n
    replaced = PHONE_RUN.sub(_phone, text)
    count += replaced.count("[phone]") - text.count("[phone]")
    return replaced, count


def _name_pattern(name: str) -> re.Pattern[str]:
    # whole words, any case, a possessive ("Agnes's", "Agnes’") included in the match
    return re.compile(rf"(?<!\w){re.escape(name.strip())}(?:['’]s?)?(?!\w)", re.I)


def check_replacements(replacements: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """The researcher's name = code pairs, refused when a code would itself identify someone: empty, too
    long, containing a listed name, or an email, phone or ID number (Codex audit 2026-10-04, finding 1)."""
    from app.core.errors import AppError

    pairs = [(" ".join(n.split()), " ".join(c.split())) for n, c in replacements if n.strip()]
    for name, code in pairs:
        if len(name) < 2:
            raise AppError(f"\"{name}\" is too short to replace safely: list the full name.", code="INVALID_REPLACEMENT")
        if not code or len(code) > 40:
            raise AppError(f"Give \"{name}\" a short code of up to 40 characters, such as Participant A.", code="INVALID_REPLACEMENT")
        name_words = {w.lower() for other, _ in pairs for w in NAME_WORDS.findall(other) if len(w) >= 3}
        if name_words & {w.lower() for w in NAME_WORDS.findall(code)} or _identifiers(code)[1]:  # "Agnes A." still names Agnes
            raise AppError(f"The code for \"{name}\" would itself identify someone. Use a code such as Participant A.", code="INVALID_REPLACEMENT")
    return pairs


def pseudonymise(text: str, replacements: list[tuple[str, str]]) -> tuple[str, int]:
    """The text with each listed name replaced by its code (whole words, any case, possessives too) and
    every email address, phone number and national ID number by a marker; and how many replacements."""
    count = 0
    for name, code in sorted(replacements, key=lambda r: -len(r[0])):  # longer names first: "Agnes Akello" before "Agnes"
        if not name.strip():
            continue
        text, n = _name_pattern(name).subn(code.strip() or "[name]", text)
        count += n
    text, n = _identifiers(text)
    return text, count + n


def leaks(text: str, names: list[str]) -> bool:
    """Whether a listed name, email, phone or ID number is still in the text: checked again before anything
    is stored or sent to a model."""
    return any(_name_pattern(n).search(text) for n in names if n.strip()) or _identifiers(text)[1] > 0


def clean(text: str) -> str:
    """Identifiers removed from text bound for a model (transcripts stored before the wider patterns)."""
    return _identifiers(text)[0]


def _locate(quote: str, source: str) -> str | None:
    """The quote as it stands in its transcript: found ignoring case, typographic quotes and spacing, and
    returned with the transcript's own characters, never the model's (Codex audit 2026-10-04, finding 8)."""
    fold = {"“": '"', "”": '"', "‘": "'", "’": "'"}
    chars: list[str] = []
    where: list[int] = []
    space = False
    for i, ch in enumerate(source):
        if ch.isspace():
            space = bool(chars)
            continue
        if space:
            chars.append(" ")
            where.append(i)
            space = False
        normalised = fold.get(ch, ch).lower()
        chars.extend(normalised)
        where.extend([i] * len(normalised))
    needle = " ".join("".join(fold.get(c, c) for c in quote).lower().split())
    at = "".join(chars).find(needle)
    if not needle or at < 0:
        return None
    return " ".join(source[where[at]:where[at + len(needle) - 1] + 1].split())


# --- the frozen input and the model calls ------------------------------------------------------------------------


class QualDoc(Camel):
    id: str
    label: str
    path: str
    sha256: str
    words: int
    anonymisation_version: int = 0


class QualInput(Camel):
    project_id: str
    title: str
    question: str
    documents: list[QualDoc]


class _Quote(BaseModel):
    document: str
    text: str


class _Code(BaseModel):
    code: str
    description: str
    quotes: list[_Quote]


class Coded(BaseModel):
    codes: list[_Code]


class _Theme(BaseModel):
    name: str
    definition: str
    codes: list[str]
    paragraphs: list[str]


class Themes(BaseModel):
    themes: list[_Theme]
    summary: list[str]
    limitations: list[str]
    withheld: list[str] = []  # quotes the writer leaves out because they would identify a participant


class Review(BaseModel):
    verdict: str
    rules: list[RuleVerdict]
    issues: list[str]
    suggestions: list[str] = []


class QualRunner(AIRunner):
    def code(self, payload: dict[str, Any]) -> Coded:
        answer = self._call("q_code", payload, CODE_SCHEMA, Coded)
        if answer is None:
            raise RetryableStageError("OUTPUT_TRUNCATED", "PaperAid's analyst was cut off. It will try again.", "answer did not fit on q_code")
        return answer

    def themes(self, payload: dict[str, Any]) -> dict[str, Any]:
        answer = self._call("q_themes", payload, THEMES_SCHEMA, Themes)
        if answer is None:
            raise RetryableStageError("OUTPUT_TRUNCATED", "PaperAid's writer was cut off. It will try again.", "answer did not fit on q_themes")
        return answer.model_dump()

    def final_review(self, payload: dict[str, Any]) -> Review | None:
        from app.datalab.pipeline import check_review_size

        check_review_size(payload)
        try:
            return self._call("q_review", payload, REVIEW_SCHEMA, Review)
        except PermanentStageError as exc:
            if exc.code != "BUDGET_EXCEEDED":
                raise
            self.budget_reached = True
            return None


def _input(ctx: "StageContext") -> QualInput:
    check_content(ctx.job.quote.engine if ctx.job.quote else None)
    inp = QualInput.model_validate(ctx.get_json(INPUT))
    if any(d.anonymisation_version != ANONYMISATION_VERSION for d in inp.documents):
        raise PermanentStageError("TRANSCRIPTS_NEED_REUPLOAD", "Please remove and add your older transcripts again so their labels and contact details can be protected. Nothing was charged.")
    return inp


def _runner(ctx: "StageContext") -> QualRunner:
    runner = ctx.ai(QualRunner)
    assert isinstance(runner, QualRunner)
    return runner


def _texts(ctx: "StageContext", inp: QualInput) -> dict[str, str]:
    out = {}
    for doc in inp.documents:
        data = ctx.rt.files.get(doc.path)
        if hashlib.sha256(data).hexdigest() != doc.sha256:
            raise PermanentStageError("DATA_CHANGED", CHANGED, f"transcript {doc.id} changed")
        out[doc.id] = clean(data.decode("utf-8"))
    return out


def _batches(inp: QualInput, texts: dict[str, str]) -> list[list[dict[str, str]]]:
    """Transcripts packed into calls of at most BATCH_WORDS; a longer transcript in parts, split between paragraphs."""
    pieces: list[dict[str, str]] = []
    for doc in inp.documents:
        from app.works.pipeline import _chunks

        paragraphs = [c for p in texts[doc.id].split("\n") if p.strip() for c in _chunks(p, BATCH_WORDS)]  # one long paragraph is cut too
        part: list[str] = []
        words = 0
        for p in paragraphs:
            n = len(p.split())
            if part and words + n > BATCH_WORDS:
                pieces.append({"id": doc.id, "label": doc.label, "text": "\n".join(part)})
                part, words = [], 0
            part.append(p)
            words += n
        if part:
            pieces.append({"id": doc.id, "label": doc.label, "text": "\n".join(part)})
    batches: list[list[dict[str, str]]] = [[]]
    size = 0
    for piece in pieces:
        n = len(piece["text"].split())
        if batches[-1] and size + n > BATCH_WORDS:
            batches.append([])
            size = 0
        batches[-1].append(piece)
        size += n
    return batches


# --- DRAFTING ---------------------------------------------------------------------------------------------------


def verified_quotes(coded: Coded, batch: list[dict[str, str]], texts: dict[str, str]) -> tuple[list[dict[str, Any]], int]:
    """Each code with only its quotes found word for word in their own transcript; and how many were dropped."""
    ids = {piece["id"] for piece in batch}
    out, dropped = [], 0
    for code in coded.codes:
        kept = []
        for q in code.quotes:
            words = len(q.text.split())
            found = _locate(q.text, texts[q.document]) if q.document in ids and QUOTE_WORDS[0] <= words <= QUOTE_WORDS[1] else None
            if found:
                kept.append({"document": q.document, "text": found})
            else:
                dropped += 1
        if kept and code.code.strip():
            out.append({"code": code.code.strip()[:80], "description": code.description.strip()[:300], "quotes": kept})
    return out, dropped


def merge_codes(found: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[int, dict[str, str]]]:
    """Codes of the same name merged, every quote numbered once (Q1, Q2 ...)."""
    by_name: dict[str, dict[str, Any]] = {}
    quotes: dict[int, dict[str, str]] = {}
    seen: dict[tuple[str, str], int] = {}
    for code in found:
        key = code["code"].lower()
        entry = by_name.setdefault(key, {"code": code["code"], "description": code["description"], "quotes": []})
        for q in code["quotes"]:
            ident = (q["document"], q["text"].lower())
            if ident not in seen:
                seen[ident] = len(quotes) + 1
                quotes[seen[ident]] = q
            if seen[ident] not in entry["quotes"]:
                entry["quotes"].append(seen[ident])
    return list(by_name.values()), quotes


def withhold(draft: dict[str, Any], codes: list[dict[str, Any]], quotes: dict[int, dict[str, str]]) -> tuple[list[dict[str, Any]], dict[int, dict[str, str]]]:
    """The codes and quotes without those the writer withheld (a quote that would identify a participant):
    a withheld quote is in neither the report nor the codebook, and a code left without quotes goes too."""
    out = {int(n) for ref in draft.get("withheld", []) for n in re.findall(r"\d+", str(ref))}
    kept = {n: q for n, q in quotes.items() if n not in out}
    trimmed = [{**c, "quotes": [n for n in c["quotes"] if n in kept]} for c in codes]
    return [c for c in trimmed if c["quotes"]], kept


def problems(draft: dict[str, Any], codes: list[dict[str, Any]], quotes: dict[int, dict[str, str]]) -> list[str]:
    """What code finds wrong with the themes, each as an instruction to the writer."""
    issues = []
    names = {c["code"].lower() for c in codes}
    if not draft.get("themes"):
        issues.append("Build at least one theme from the codes.")
    for part in ("summary", "limitations"):
        if not any(len(QUOTE_TOKEN.sub("x", p).split()) >= SUBSTANTIVE for p in draft.get(part, []) if isinstance(p, str)):
            issues.append(f"Write the {part}: it is empty or too short to say anything.")
    for theme in draft.get("themes", []):
        name = theme.get("name", "") or "a theme"
        unknown = [c for c in theme.get("codes", []) if c.lower() not in names]
        if unknown:
            issues.append(f"In \"{name}\": these codes don't exist: {', '.join(unknown[:5])}. Use only the codes given.")
        text = " ".join(theme.get("paragraphs", []))
        cited = {int(n) for n in QUOTE_TOKEN.findall(text)}
        if cited - set(quotes):
            issues.append(f"In \"{name}\": quotes {', '.join(f'⟦Q:{n}⟧' for n in sorted(cited - set(quotes)))} don't exist. Cite only the quotes given.")
        if len(cited & set(quotes)) < 2:
            issues.append(f"In \"{name}\": support the theme with at least two quotes, cited as ⟦Q:n⟧.")
        if len(QUOTE_TOKEN.sub("x", text).split()) < 3 * SUBSTANTIVE:
            issues.append(f"In \"{name}\": describe the theme more fully; it is too short.")
    for where, text in _texts_of(draft):
        bare = QUOTE_TOKEN.sub("", text)
        if DIGIT.search(bare):
            issues.append(f"In the {where}: don't write numbers or counts; PaperAid's code says in how many transcripts each theme appears.")
        if RAW_QUOTE.search(bare):
            issues.append(f"In the {where}: a long passage is quoted directly. Cite quotes only as ⟦Q:n⟧, so they are reproduced exactly.")
    return list(dict.fromkeys(issues))


def _texts_of(draft: dict[str, Any]) -> list[tuple[str, str]]:
    out = [(f"theme \"{t.get('name', '')}\"", p) for t in draft.get("themes", []) for p in [t.get("definition", ""), *t.get("paragraphs", [])] if isinstance(p, str)]
    return out + [(part, p) for part in ("summary", "limitations") for p in draft.get(part, []) if isinstance(p, str)]


def _payload(inp: QualInput, codes: list[dict[str, Any]], quotes: dict[int, dict[str, str]]) -> dict[str, Any]:
    labels = {d.id: d.label for d in inp.documents}
    return {"title": inp.title, "question": inp.question, "documents": [{"label": d.label, "words": d.words} for d in inp.documents],
            "codes": [{"code": c["code"], "description": c["description"],
                       "quotes": [{"ref": f"⟦Q:{n}⟧", "document": labels[quotes[n]["document"]], "text": quotes[n]["text"]} for n in c["quotes"]]} for c in codes]}


def stage_drafting(ctx: "StageContext") -> None:
    inp = _input(ctx)
    runner = _runner(ctx)
    texts = _texts(ctx, inp)
    found: list[dict[str, Any]] = []
    dropped = 0
    for batch in _batches(inp, texts):
        coded = runner.code({"question": inp.question, "documents": batch})
        kept, lost = verified_quotes(coded, batch, texts)
        found += kept
        dropped += lost
    codes, quotes = merge_codes(found)
    if not quotes:
        raise PermanentStageError("NO_CODES", "PaperAid found nothing in these transcripts it could quote exactly, so nothing was charged. Check they are the "
                                  "transcripts of your study.", f"no verified quotes ({dropped} dropped)")
    payload = _payload(inp, codes, quotes)
    draft = runner.themes(payload)
    rounds = [{"round": 0, "problems": []}]
    for round_ in range(1, REVIEW_REPAIRS + 2):
        found_problems = problems(draft, *withhold(draft, codes, quotes))
        rounds[-1]["problems"] = found_problems
        if not found_problems:
            break
        if round_ > REVIEW_REPAIRS:
            ctx.put_json("qual_rounds.json", rounds)
            raise PermanentStageError("DOCUMENT_NOT_APPROVED", NOT_FINISHED, "code checks still failing: " + "; ".join(found_problems)[:300])
        draft = runner.themes({**payload, "draft": draft, "critique": found_problems})
        rounds.append({"round": round_, "problems": []})
    ctx.put_json("qual_rounds.json", rounds)
    ctx.put_json("qual_draft.json", {"draft": draft, "codes": codes, "quotes": {str(k): v for k, v in quotes.items()}, "dropped": dropped})


# --- the report, as delivered ----------------------------------------------------------------------------------


def _in_documents(theme: dict[str, Any], codes: list[dict[str, Any]], quotes: dict[int, dict[str, str]]) -> set[str]:
    chosen = {c.lower() for c in theme.get("codes", [])}
    cited = {int(n) for n in QUOTE_TOKEN.findall(" ".join(theme.get("paragraphs", [])))}
    refs = {n for c in codes if c["code"].lower() in chosen for n in c["quotes"]} | cited
    return {quotes[n]["document"] for n in refs if n in quotes}


def assemble(inp: QualInput, draft: dict[str, Any], codes: list[dict[str, Any]], quotes: dict[int, dict[str, str]]) -> ReportDocument:
    labels = {d.id: d.label for d in inp.documents}
    total = len(inp.documents)

    def place(text: str) -> str:
        return QUOTE_TOKEN.sub(lambda m: f"“{quotes[int(m.group(1))]['text']}” ({labels[quotes[int(m.group(1))]['document']]})" if int(m.group(1)) in quotes else "",
                               text)

    sections = [
        ReportSection(key="summary", heading="Summary", paragraphs=[place(p) for p in draft.get("summary", [])]),
        ReportSection(key="question", heading="Research question", paragraphs=[inp.question or "Not stated."]),
        ReportSection(key="data", heading="The data", paragraphs=[
            f"{total} transcript{'s' if total != 1 else ''} ({sum(d.words for d in inp.documents):,} words). Names the researcher listed, and any email address, "
            "phone number or ID number, were replaced before the transcripts were stored or analysed."],
            tables=[ResultTable(title="Transcripts analysed", columns=["Transcript", "Words"],
                                rows=[[Cell(text=d.label), Cell(text=f"{d.words:,}", value=d.words)] for d in inp.documents])]),
        ReportSection(key="method", heading="Method", paragraphs=[
            "The transcripts were coded inductively, passage by passage, and the codes grouped into themes that answer the research question (thematic "
            "analysis). PaperAid proposed the codes and themes, kept a quote only if it appears word for word in its transcript, and "
            "counted in how many transcripts each theme appears. The whole report was checked against the transcripts before delivery. The researcher remains "
            "responsible for the interpretation, as in any qualitative study."]),
        ReportSection(key="themes", heading="Themes", paragraphs=[]),
    ]
    for n, theme in enumerate(draft.get("themes", []), start=1):
        present = _in_documents(theme, codes, quotes)
        sections.append(ReportSection(key=f"theme_{n}", heading=f"{n}. {theme.get('name', '')}", level=2,
                                      paragraphs=[theme.get("definition", ""), f"Found in {len(present)} of {total} transcripts.",
                                                  *(place(p) for p in theme.get("paragraphs", []))]))
    sections.append(ReportSection(key="limitations", heading="Limitations", paragraphs=[place(p) for p in draft.get("limitations", [])]))
    theme_of = {c.lower(): t.get("name", "") for t in draft.get("themes", []) for c in t.get("codes", [])}
    codebook = ResultTable(title="Codebook", columns=["Code", "Description", "Theme", "Transcripts", "Quotes"], rows=[
        [Cell(text=c["code"]), Cell(text=c["description"]), Cell(text=theme_of.get(c["code"].lower(), "Not in a theme")),
         Cell(text=str(len({quotes[n]["document"] for n in c["quotes"]}))), Cell(text=str(len(c["quotes"])))] for c in codes])
    rows = workbook_rows(inp, draft, codes, quotes)["Quotes"][1]
    quoted = ResultTable(title="Quotations", columns=["Ref", "Quote", "Transcript", "Code"], rows=[[Cell(text=str(c)) for c in r] for r in rows])
    appendices = [ReportSection(key="appendix_codebook", heading="Appendix A. Codebook", tables=[codebook]),
                  ReportSection(key="appendix_quotes", heading="Appendix B. Quotations", tables=[quoted],
                                paragraphs=["Every quotation in the codebook, as it stands in its transcript."])]
    document = ReportDocument(title=inp.title or "Qualitative analysis", subtitle=f"Qualitative analysis · {utcnow():%d %B %Y}", sections=sections, appendices=appendices)
    document.words = sum(len(p.split()) for s in sections for p in s.paragraphs)
    return document


def workbook_rows(inp: QualInput, draft: dict[str, Any], codes: list[dict[str, Any]], quotes: dict[int, dict[str, str]]) -> dict[str, Any]:
    """The codebook workbook's sheets as rows: the same rows the report's appendices show the reviewer."""
    labels = {d.id: d.label for d in inp.documents}
    theme_of = {c.lower(): t.get("name", "") for t in draft.get("themes", []) for c in t.get("codes", [])}
    return {
        "Themes": (["Theme", "Definition", "Codes", "Transcripts"],
                   [[t.get("name", ""), t.get("definition", ""), "; ".join(t.get("codes", [])), len(_in_documents(t, codes, quotes))] for t in draft.get("themes", [])]),
        "Codebook": (["Code", "Description", "Theme", "Transcripts", "Quotes"],
                     [[c["code"], c["description"], theme_of.get(c["code"].lower(), ""), len({quotes[n]["document"] for n in c["quotes"]}), len(c["quotes"])] for c in codes]),
        "Quotes": (["Ref", "Quote", "Transcript", "Code"],
                   [[f"Q{n}", quotes[n]["text"], labels[quotes[n]["document"]], c["code"]] for c in codes for n in c["quotes"]]),
    }


def codebook_workbook(sheets: dict[str, Any]) -> bytes:
    """The workbook from approved rows only (Codex audit 2026-10-04, finding 2: it held quotes no review saw)."""
    buffer = io.BytesIO()
    book = xlsxwriter.Workbook(buffer, {"in_memory": True, "strings_to_formulas": False, "strings_to_urls": False})
    head = book.add_format({"bold": True, "font_color": "white", "bg_color": "#0F633E", "border": 1})
    wrap = book.add_format({"text_wrap": True, "valign": "top", "border": 1})
    for name, (columns, rows) in sheets.items():
        ws = book.add_worksheet(name)
        ws.write_row(0, 0, columns, head)
        ws.set_column(0, 0, 40)
        ws.set_column(1, 1, 60)
        ws.set_column(2, len(columns) - 1, 18)
        for r, row in enumerate(rows, start=1):
            for c, value in enumerate(row):
                ws.write(r, c, value, wrap)
    book.close()
    return buffer.getvalue()


# --- AUDITING ---------------------------------------------------------------------------------------------------


def _review(runner: QualRunner, inp: QualInput, document: ReportDocument, codes: list[dict[str, Any]], previous: list[str]) -> Review | None:
    from app.datalab.pipeline import document_parts

    base: dict[str, Any] = {"question": inp.question, "codes": [{"code": c["code"], "description": c["description"], "quotes": len(c["quotes"])} for c in codes],
                            "rules": RULES, **({"previousIssues": previous} if previous else {})}
    parts, manifest = document_parts(document, None, base)  # long sections and the quotations appendix split within the bound
    base["manifest"] = manifest
    verdicts: dict[str, RuleVerdict] = {}
    issues: list[str] = []
    suggestions: list[str] = []
    passed = True
    for n, part in enumerate(parts, start=1):
        answer = runner.final_review({**base, "part": f"{n} of {len(parts)}", "document": {"title": document.title, "sections": part}})
        if answer is None or not set(RULES) <= {r.rule for r in answer.rules}:
            return None
        passed = passed and answer.verdict == "PASS"
        issues += answer.issues
        suggestions += answer.suggestions
        for r in answer.rules:
            if r.rule in RULES and (r.rule not in verdicts or verdicts[r.rule].status == "PASS"):
                verdicts[r.rule] = r
    return Review(verdict="PASS" if passed else "REPAIR", rules=[verdicts[r] for r in RULES], issues=list(dict.fromkeys(issues)),
                  suggestions=list(dict.fromkeys(suggestions)))


def _saved(ctx: "StageContext") -> tuple[dict[str, Any], list[dict[str, Any]], dict[int, dict[str, str]]]:
    saved = ctx.get_json("qual_draft.json")
    return saved["draft"], saved["codes"], {int(k): v for k, v in saved["quotes"].items()}


def stage_auditing(ctx: "StageContext") -> None:
    inp = _input(ctx)
    runner = _runner(ctx)
    draft, codes, quotes = _saved(ctx)
    payload = _payload(inp, codes, quotes)
    seen: list[dict[str, Any]] = []
    previous: list[str] = []
    for round_ in runner.audit_rounds(REVIEW_REPAIRS + 1):
        shipped_codes, shipped = withhold(draft, codes, quotes)
        document = assemble(inp, draft, shipped_codes, shipped)
        review = _review(runner, inp, document, shipped_codes, previous)
        if review is None:
            ctx.put_json("qual_review.json", seen)
            raise PermanentStageError("DOCUMENT_NOT_APPROVED", NOT_FINISHED, "final review not completed (missing verdict, cut off or spend cap)")
        not_passed = [f"{r.rule}: {r.note}" for r in review.rules if r.status != "PASS"]
        seen.append({"round": round_, "verdict": review.verdict, "failed": not_passed, "issues": review.issues, "suggestions": review.suggestions})
        objections = list(dict.fromkeys([*review.issues, *not_passed]))
        if review.verdict == "PASS" and not objections:
            data = document.model_dump(mode="json", by_alias=True)
            sheets = workbook_rows(inp, draft, shipped_codes, shipped)
            ctx.put_json("qual_review.json", seen)
            ctx.put_json("qual_approved.json", {"draft": draft, "document": data, "workbook": sheets,
                                                "sha": hashlib.sha256(json.dumps([data, sheets], sort_keys=True).encode()).hexdigest()})
            return
        if round_ == REVIEW_REPAIRS or runner.budget_reached:
            break
        repaired = runner.themes({**payload, "draft": draft, "critique": objections})
        if problems(repaired, *withhold(repaired, codes, quotes)):
            repaired = runner.themes({**payload, "draft": repaired, "critique": problems(repaired, *withhold(repaired, codes, quotes))})
            if problems(repaired, *withhold(repaired, codes, quotes)):
                break
        draft, previous = repaired, objections
    ctx.put_json("qual_review.json", seen)
    last = seen[-1] if seen else {"issues": [], "failed": []}
    raise PermanentStageError("DOCUMENT_NOT_APPROVED", NOT_FINISHED, "final reviewer still objecting: " + "; ".join(last["issues"] + last["failed"])[:300])


# --- EXPORTING ----------------------------------------------------------------------------------------------------


def stage_exporting(ctx: "StageContext") -> None:
    inp = _input(ctx)
    approved = ctx.get_json("qual_approved.json")
    data, sheets = approved["document"], approved["workbook"]
    if hashlib.sha256(json.dumps([data, sheets], sort_keys=True).encode()).hexdigest() != approved["sha"]:
        raise PermanentStageError("DOCUMENT_NOT_APPROVED", NOT_FINISHED, "approved document does not match its hash")
    document = ReportDocument.model_validate(data)
    project = ctx.rt.store.get_datalab(inp.project_id)
    if project is None or project.deleting:
        raise PermanentStageError("DATALAB_DELETED", "This project was deleted before the analysis was finished, so nothing was charged.", "project gone at export")
    if {(d.id, d.sha256) for d in project.documents} != {(d.id, d.sha256) for d in inp.documents}:
        raise PermanentStageError("DATA_CHANGED", CHANGED, "transcripts changed")
    files = ctx.rt.files
    job_id = ctx.job.id
    prefix = f"{project.storage_prefix()}/reports/{job_id}"
    files.put(prefix + ".json", document.model_dump_json(by_alias=True).encode(), "application/json")
    files.put(prefix + ".docx", report.to_docx(document, lambda path: None), DOCX)
    files.put(prefix + ".xlsx", codebook_workbook(sheets), XLSX)
    gone = False

    def finish(j: Job, w: Wallet, p: DataProject | None) -> tuple[Job, Wallet, DataProject] | None:
        nonlocal gone
        gone = p is None or p.deleting
        if p is None or p.deleting or j.status != JobStatus.PROCESSING or j.stage != Stage.EXPORTING:
            return None
        if not any(r.job_id == job_id for r in p.reports):
            version = len(p.reports) + 1
            p.reports.append(ReportVersion(version=version, path=prefix + ".json", docx=prefix + ".docx", workbook=prefix + ".xlsx", job_id=job_id,
                                           analyses=[d.id for d in inp.documents], kind="THEMES"))
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
        raise PermanentStageError("DATALAB_DELETED", "This project was deleted before the analysis was finished, so nothing was charged.", "project deleting at export")


STAGES = {Stage.DRAFTING: stage_drafting, Stage.AUDITING: stage_auditing, Stage.EXPORTING: stage_exporting}
