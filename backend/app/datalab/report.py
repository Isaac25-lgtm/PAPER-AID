"""The Data Lab analysis report (decision 2026-10-03): executive summary, key findings, the dataset,
data preparation, data quality, methods, results, limitations and conclusions, with the cleaning
log, the statistical output and the data dictionary as appendices. Code writes every factual part
and every table; the narrative supplies only the interpretation. The whole document is assembled
before the final review, and the reviewed document is exactly what is exported (Codex audit,
finding 5): nothing is added or substituted afterwards. The Word file is built from this one
document, and the PDF from the Word file."""

import io
from datetime import UTC, datetime
from typing import Any

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Inches, Pt, RGBColor
from pydantic import Field

from app.datalab.engine.disclosure import few
from app.datalab.models import AnalysisResult, CleaningStep, ResultTable, Variable
from app.jobs.models import Camel

GREEN = RGBColor(0x0F, 0x63, 0x3E)


class ReportSection(Camel):
    key: str
    heading: str
    paragraphs: list[str] = []
    bullets: list[str] = []
    tables: list[ResultTable] = []
    chart: str = ""  # path of a PNG in the project's storage
    notes: list[str] = []
    level: int = 1


class ReportDocument(Camel):
    title: str
    subtitle: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    sections: list[ReportSection]
    appendices: list[ReportSection] = []
    words: int = 0
    numbered: bool = True  # a report numbers its sections; a chapter's headings carry their own numbers (4.1 ...)
    table_prefix: str = ""  # "4." in Chapter Four: Table 4.1, Figure 4.1


def _kind_label(var: Variable) -> str:
    return {"NUMERIC": "Number", "CATEGORICAL": "Category", "BINARY": "Two categories", "DATE": "Date", "TEXT": "Free text", "IDENTIFIER": "Identifier"}[var.kind]


def build(title: str, source_name: str, sheet: str | None, version: int, rows: int, columns: int, alpha: float, threshold: int,
          cleaning: list[CleaningStep], variables: list[Variable], analyses: list[AnalysisResult], charts: dict[str, str], narrative: dict[str, Any],
          fill, released: list[str] | None = None) -> ReportDocument:
    """`narrative` is the draft (tokens still in it); `fill` turns tokens into numbers."""
    findings = {f["id"]: f["paragraphs"] for f in narrative.get("findings", [])}
    used = [v for v in variables if not v.excluded]
    left_out = [v for v in variables if v.excluded]
    # Said by code, so the reviewer never has to ask for it: which variables the analyses read (live check 2026-10-04).
    title_of = {v.name: v.title() for v in variables}
    read = list(dict.fromkeys(title_of.get(n, n) for r in analyses for n in r.spec.names()))
    sections = [
        ReportSection(key="summary", heading="Executive summary", paragraphs=[fill(p) for p in narrative.get("summary", [])]),
        ReportSection(key="key_findings", heading="Key findings", bullets=[fill(p) for p in narrative.get("keyFindings", [])]),
        ReportSection(key="dataset", heading="The dataset", paragraphs=[
            f"The analysis used \"{source_name}\"" + (f" (sheet \"{sheet}\")" if sheet else "") + f": {rows:,} records and {columns:,} variables, "
            f"in version {version} of the data after the preparation described below. The original file was kept unchanged.",
            *([f"The analyses in this report use {len(read)} of the {columns:,} variables: " + ", ".join(f"\"{t}\"" for t in read) + "."] if read else []),
            *([f"{len(left_out)} variable{'s were' if len(left_out) != 1 else ' was'} set aside, because {'they' if len(left_out) != 1 else 'it'} may identify "
               "people or places, and no analysis used " + ("them" if len(left_out) != 1 else "it") + ": " + ", ".join(f"\"{v.title()}\"" for v in left_out) + "."]
              if left_out else []),
            *([f"The researcher chose to include {', '.join(chr(34) + n + chr(34) for n in released)}, which may identify people or places."] if released else []),
        ]),
        ReportSection(key="preparation", heading="Data preparation", bullets=[
            f"{s.description.rstrip('.')} ({'applied automatically' if s.automatic else 'confirmed by the researcher'})." for s in cleaning
        ] or [], paragraphs=[] if cleaning else ["No changes were made to the data as uploaded."]),
        ReportSection(key="quality", heading="Data quality", paragraphs=[_quality_text(used, threshold)], tables=[_quality_table(used, threshold)]),
        ReportSection(key="methods", heading="Methods", paragraphs=[
            f"Each analysis below answers one question, with the method chosen for that question. Records missing a value for a variable in an "
            f"analysis were left out of that analysis (complete cases). Tests are two-sided, at a significance level of {alpha:g}. "
            f"Counts below {threshold} are hidden (–), together with any number that would reveal them, so that no one can be identified.",
            *[f"{n}. {a.record.question} {a.record.method}. {a.record.why}" for n, a in enumerate(analyses, start=1)],
            "All numbers were calculated by PaperAid's code (" + ", ".join(analyses[0].record.software if analyses else []) + ").",
        ]),
    ]
    for n, result in enumerate(analyses, start=1):
        sections.append(ReportSection(key=f"result_{result.id}", heading=f"{n}. {result.title}", level=2,
                                      paragraphs=[fill(p) for p in findings.get(result.id, [])],
                                      tables=result.tables, chart=charts.get(result.id, ""), notes=result.warnings))
    sections.insert(6, ReportSection(key="results", heading="Results", paragraphs=[]))
    sections += [
        ReportSection(key="limitations", heading="Limitations", paragraphs=[fill(p) for p in narrative.get("limitations", [])]),
        ReportSection(key="conclusions", heading="Conclusions", paragraphs=[fill(p) for p in narrative.get("conclusions", [])]),
    ]
    appendices = [
        ReportSection(key="appendix_cleaning", heading="Appendix A. Cleaning log", tables=[_cleaning_table(cleaning, threshold)] if cleaning else [],
                      paragraphs=[] if cleaning else ["No changes were made to the data as uploaded."]),
        ReportSection(key="appendix_output", heading="Appendix B. Statistical output", paragraphs=[], bullets=[]),
        ReportSection(key="appendix_dictionary", heading="Appendix C. Data dictionary", tables=[_dictionary_table(variables)]),
    ]
    output = appendices[1]
    for n, result in enumerate(analyses, start=1):
        r = result.record
        output.bullets.append(f"{n}. {result.title}. Method: {r.method}. Records used: {r.rows_used:,} of {r.rows_available:,}. "
                              + " ".join(r.left_out) + (" " + " ".join(r.coding) if r.coding else "") + (" Checks: " + " ".join(r.assumptions) if r.assumptions else "")
                              + f" Significance level {r.alpha:g}. Data version {r.dataset_version}. Calculated {r.calculated_at:%d %B %Y}.")
    document = ReportDocument(title=title or "Analysis report", subtitle=f"Analysis report · {datetime.now(UTC):%d %B %Y}", sections=sections, appendices=appendices)
    document.words = sum(len(p.split()) for s in sections + appendices for p in s.paragraphs + s.bullets)
    return document


def build_chapter(project_title: str, rows: int, version: int, cleaning: list[CleaningStep], objectives: list[str], objective_of: dict[str, int],
                  analyses: list[AnalysisResult], charts: dict[str, str], narrative: dict[str, Any], fill, missing: list[int] | None = None) -> ReportDocument:
    """Chapter Four of a research report (owner decision 2026-10-03): the results, one section per
    specific objective, each analysis with its table and figure; then the summary of the results. An
    objective with no analysis keeps its section and says so (Codex audit, finding 6)."""
    findings = {f["id"]: f["paragraphs"] for f in narrative.get("findings", [])}
    preparation = (" Before the analysis, " + "; ".join(s.description.rstrip(".").lower()[:1] + s.description.rstrip(".")[1:] for s in cleaning) + ".") if cleaning else ""
    sections = [ReportSection(key="introduction", heading="4.1 Introduction", paragraphs=[*(fill(p) for p in narrative.get("introduction", [])),
                f"The analysis used {rows:,} records (version {version} of the data).{preparation} Records missing a value for a variable in an analysis were "
                "left out of that analysis."])]
    number = 1

    def add(result: AnalysisResult) -> None:
        sections.append(ReportSection(key=f"result_{result.id}", heading=result.title, level=3, paragraphs=[fill(p) for p in findings.get(result.id, [])],
                                      tables=result.tables, chart=charts.get(result.id, ""), notes=result.warnings))

    for n, objective in enumerate(objectives, start=1):
        mine = [r for r in analyses if objective_of.get(r.id) == n]
        if not mine and n not in (missing or []):
            continue
        number += 1
        sections.append(ReportSection(key=f"objective_{n}", heading=f"4.{number} Objective {n}: {objective.rstrip('.')}", level=2,
                                      paragraphs=[] if mine else ["No analysis of the data was reported for this objective."]))
        for result in mine:
            add(result)
    others = [r for r in analyses if r.id not in objective_of]
    if others:
        number += 1
        sections.append(ReportSection(key="other_results", heading=f"4.{number} Other results", level=2))
        for result in others:
            add(result)
    number += 1
    sections.append(ReportSection(key="summary", heading=f"4.{number} Summary of the results", level=2, paragraphs=[fill(p) for p in narrative.get("summary", [])]))
    document = ReportDocument(title="Chapter Four: Results", subtitle=project_title.removeprefix("Chapter Four: "), sections=sections, numbered=False, table_prefix="4.")
    document.words = sum(len(p.split()) for s in sections for p in s.paragraphs)
    return document


def _quality_text(variables: list[Variable], threshold: int) -> str:
    missing = [v for v in variables if v.missing]
    if not missing:
        return f"Each of the {len(variables)} variables available for analysis has a value in every record."
    worst = max(missing, key=lambda v: v.missing / max(1, v.valid + v.missing))
    share = 100 * worst.missing / max(1, worst.valid + worst.missing)
    how_many = f"missing in {share:.1f}% of records" if worst.missing >= threshold else f"missing in {few(worst.missing, threshold)} records"
    return (f"{len(missing)} of the {len(variables)} variables available for analysis have missing values; the most is \"{worst.title()}\", {how_many}. "
            "The table lists each variable's type and its missing values.")


def _quality_table(variables: list[Variable], threshold: int) -> ResultTable:
    """Missing values per variable; a small count is "fewer than N" (with the total known, the records
    with a value would reveal it, so they aren't listed)."""
    from app.datalab.models import Cell

    rows = []
    for v in variables:
        total = v.valid + v.missing
        small = 0 < v.missing < threshold
        rows.append([Cell(text=v.title()), Cell(text=_kind_label(v)),
                     Cell(text=few(v.missing, threshold) if small else (f"{v.missing:,} ({100 * v.missing / total:.1f}%)" if total else "0"),
                          value=None if small else v.missing, count=True, suppressed=small)])
    return ResultTable(title="Variables and missing values", columns=["Variable", "Type", "Missing"], rows=rows)


def _cleaning_table(steps: list[CleaningStep], threshold: int) -> ResultTable:
    from app.datalab.models import Cell

    rows = [[Cell(text=str(n)), Cell(text=s.description), Cell(text=few(s.affected, threshold), value=s.affected if s.affected == 0 or s.affected >= threshold else None),
             Cell(text="Automatic" if s.automatic else "Confirmed"),
             Cell(text=f"{s.decided_at:%d %b %Y}" if s.decided_at else "")] for n, s in enumerate(steps, start=1)]
    return ResultTable(title="Changes made to the data", columns=["Step", "Change", "Values or rows changed", "How", "Date"], rows=rows)


def _dictionary_table(variables: list[Variable]) -> ResultTable:
    from app.datalab.models import Cell

    notes = {"PERSONAL": "may identify people (left out)", "RECORD_ID": "unique record code", "SURVEY_DESIGN": "survey design column", "LOCATION": "coordinates",
             "FEW_VALUES": "few values", "LEADING_ZEROS": "code with leading zeros", "MIXED": "mixed numbers and text"}
    rows = [[Cell(text=v.name), Cell(text=v.label or ""), Cell(text=_kind_label(v)), Cell(text=f"{v.distinct:,}", value=v.distinct),
             Cell(text=", ".join(notes[f] for f in v.flags))] for v in variables]
    return ResultTable(title="Variables", columns=["Column", "Label", "Type", "Different values", "Notes"], rows=rows)


# --- Word ------------------------------------------------------------------------------------------------------


def to_docx(document: ReportDocument, chart_bytes) -> bytes:
    """`chart_bytes(path)` returns a chart's PNG (or None)."""
    doc = Document()
    style = doc.styles["Normal"]
    style.font.name, style.font.size = "Calibri", Pt(11)
    for section in doc.sections:
        section.left_margin = section.right_margin = Inches(1)
        _page_numbers(section)
    heading = doc.add_paragraph()
    run = heading.add_run(document.title)
    run.bold, run.font.size, run.font.color.rgb = True, Pt(22), GREEN
    sub = doc.add_paragraph(document.subtitle)
    sub.runs[0].font.color.rgb = RGBColor(0x4B, 0x55, 0x63)
    table_no = figure_no = 0
    number = 0
    for part in document.sections:
        if part.level == 1:
            number += 1
        numbered = document.numbered and part.level == 1
        doc.add_heading(f"{number}. {part.heading}" if numbered else part.heading, level=min(part.level, 3))
        for text in part.paragraphs:
            doc.add_paragraph(text)
        for text in part.bullets:
            doc.add_paragraph(text, style="List Bullet")
        for table in part.tables:
            table_no += 1
            _table(doc, table, f"Table {document.table_prefix}{table_no}. {table.title}")
        if part.chart:
            png = chart_bytes(part.chart)
            if png:
                figure_no += 1
                doc.add_picture(io.BytesIO(png), width=Inches(5.8))
                doc.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER
                caption = doc.add_paragraph(f"Figure {document.table_prefix}{figure_no}. {part.heading.split('. ', 1)[-1] if document.numbered else part.heading}")
                caption.runs[0].italic = True
        for note in part.notes:
            p = doc.add_paragraph(f"Note: {note}")
            p.runs[0].italic = True
    for part in document.appendices:
        doc.add_page_break()
        doc.add_heading(part.heading, level=1)
        for text in part.paragraphs:
            doc.add_paragraph(text)
        for text in part.bullets:
            doc.add_paragraph(text, style="List Bullet")
        for table in part.tables:
            _table(doc, table, table.title)
    buffer = io.BytesIO()
    doc.save(buffer)
    return buffer.getvalue()


def _table(doc, table: ResultTable, caption: str) -> None:
    cap = doc.add_paragraph(caption)
    cap.runs[0].bold = True
    t = doc.add_table(rows=1, cols=len(table.columns))
    t.style = "Light Grid Accent 1"
    for i, name in enumerate(table.columns):
        t.rows[0].cells[i].text = name
    for row in table.rows:
        cells = t.add_row().cells
        for i, cell in enumerate(row[: len(table.columns)]):
            cells[i].text = cell.text
    for note in table.notes:
        p = doc.add_paragraph(note)
        p.runs[0].font.size = Pt(9)


def _page_numbers(section) -> None:
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn

    paragraph = section.footer.paragraphs[0]
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = paragraph.add_run()
    for kind, text in (("begin", None), (None, "PAGE"), ("end", None)):
        if kind:
            el = OxmlElement("w:fldChar")
            el.set(qn("w:fldCharType"), kind)
        else:
            el = OxmlElement("w:instrText")
            el.set(qn("xml:space"), "preserve")
            el.text = text
        run._r.append(el)
