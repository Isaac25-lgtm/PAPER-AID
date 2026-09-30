"""A work as a Word document: the render profile the page checks use (rulebook §17: the same layout
for measuring and for the download), headings and text with citations and figures filled in by
code, the funding tables rendered from the Results Model and budget (never written by a model),
the reference list in the required style, and, where it applies, the last-page note."""

import io
import re

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
from docx.shared import Inches, Pt

from app.formatting.apply import _set_font
from app.proposals import evidence as ev
from app.proposals.export import _footer_numbers
from app.proposals.models import EvidenceItem
from app.works import budget as budget_engine
from app.works import numbers
from app.works import results as results_engine
from app.works.models import Budget, ResolvedSpec, ResultsModel, WorkDocument

KIND_LABELS = {"FUNDING_CONCEPT": "Concept Note", "PROJECT_CONCEPT": "Project Concept Note", "NGO_PROJECT": "Project Proposal", "RESEARCH_GRANT": "Research Grant Proposal"}
# Where each table goes: after the section with this key (or at the end when the key is absent).
TABLES_AFTER = {"logframe": ("expected_results", "goal_objectives"), "workplan": ("implementation", "timeline", "timeline_budget"), "mel": ("mel",),
                "budget": ("budget_narrative", "timeline_budget")}


class Profile:
    """Font, size, spacing and margins: the call's or brief's instructions where it gives them."""

    def __init__(self, spec: ResolvedSpec):
        coursework = spec.kind == "COURSEWORK"
        self.font, self.size, self.spacing, self.margin = "Times New Roman", 12.0, 1.5 if coursework else 1.0, 1.0
        text = " ".join(r.value + " " + r.quote for r in spec.requirements if r.key == "format").lower()
        for name in ("times new roman", "arial", "calibri", "cambria", "garamond", "georgia", "helvetica", "trebuchet ms", "verdana"):
            if name in text:
                self.font = name.title().replace("Ms", "MS")
        size = re.search(r"\b(9|10|10\.5|11|11\.5|12|13|14)\s*(?:pt|point)", text)
        if size:
            self.size = float(size.group(1))
        if "double" in text:
            self.spacing = 2.0
        elif "1.5" in text or "one and a half" in text:
            self.spacing = 1.5
        elif "single" in text:
            self.spacing = 1.0
        margin = re.search(r"(\d(?:\.\d+)?)\s*(?:inch|in\b|\")", text) or re.search(r"(\d(?:\.\d+)?)\s*cm", text)
        if margin:
            value = float(margin.group(1))
            self.margin = value / 2.54 if "cm" in margin.group(0) else value


def _setup(doc, profile: Profile) -> None:
    normal = doc.styles["Normal"]
    _set_font(normal, profile.font, profile.size)
    normal.paragraph_format.line_spacing = profile.spacing
    normal.paragraph_format.space_after = Pt(6 if profile.spacing == 1.0 else 0)
    for level, size in ((1, profile.size + 2), (2, profile.size), (3, profile.size)):
        style = doc.styles[f"Heading {level}"]
        _set_font(style, profile.font, size)
        style.font.bold, style.font.italic = True, False
        style.font.color.rgb = None
        style.paragraph_format.space_before, style.paragraph_format.space_after = Pt(12), Pt(6)
    section = doc.sections[0]
    section.top_margin = section.bottom_margin = section.left_margin = section.right_margin = Inches(profile.margin)


def _table(doc, rows: list[list[str]], caption: str) -> None:
    if len(rows) < 2:
        return
    title = doc.add_paragraph()
    title.add_run(caption).bold = True
    grid = doc.add_table(rows=len(rows), cols=len(rows[0]))
    grid.style = "Table Grid"
    for r, row in enumerate(rows):
        for c, value in enumerate(row):
            cell = grid.cell(r, c)
            cell.text = value
            for paragraph in cell.paragraphs:
                paragraph.paragraph_format.line_spacing = 1.0
                for run in paragraph.runs:
                    run.font.size = Pt(9)
                    run.bold = r == 0
    doc.add_paragraph()


def _budget_tables(budget: Budget) -> tuple[list[list[str]], list[list[str]]]:
    t = budget_engine.totals(budget)
    cur = budget.currency
    summary = [["Category", "Amount"], *[[k, budget_engine.money(v, cur)] for k, v in sorted(t.by_category.items())], ["Total", budget_engine.money(t.total, cur)]]
    detail = [["Line", "Description", "Quantity", "Unit", "Unit cost", "Total", "Year", "Activities"]]
    for li in budget.lines:
        detail.append([li.id, li.description, f"{li.quantity:g}", li.unit, budget_engine.money(li.unit_cost, cur), budget_engine.money(budget_engine.line_total(li), cur),
                       str(li.year), ", ".join(li.activity_ids) or ("Support" if li.support else "")])
    return summary, detail


def build(document: WorkDocument, spec: ResolvedSpec, results: ResultsModel | None, budget: Budget | None, library: dict[str, EvidenceItem],
          tokens: dict[str, tuple[str, str]], draft: bool) -> bytes:
    profile = Profile(spec)
    doc = Document()
    _setup(doc, profile)
    title = doc.add_paragraph()
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    title.add_run(document.title).bold = True
    label = KIND_LABELS.get(document.variant, "")
    if label:
        sub = doc.add_paragraph(label)
        sub.alignment = WD_ALIGN_PARAGRAPH.CENTER
    if document.exploratory:
        note = doc.add_paragraph()
        note.alignment = WD_ALIGN_PARAGRAPH.CENTER
        note.add_run("Exploratory draft: not every eligibility criterion is met, so this is not ready to submit.").italic = True
    elif draft and document.status == "NOT_READY":
        note = doc.add_paragraph()
        note.alignment = WD_ALIGN_PARAGRAPH.CENTER
        note.add_run("Draft: some requirements still need your attention (see PaperAid's checklist).").italic = True
    _footer_numbers(doc.sections[0], "decimal")
    citer = ev.Citer(library, spec.citation_style)
    tables: dict[str, list[tuple[list[list[str]], str]]] = {}
    for key, _, rows, caption in generated_tables(document, spec, results, budget):
        tables.setdefault(key, []).append((rows, caption))
    for s in document.sections:
        doc.add_heading(s.heading, level=1 if not spec.fields else 2)
        for paragraph in s.paragraphs:
            text = numbers.render(citer.render(paragraph), tokens)[0]
            p = doc.add_paragraph(text)
            p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        if s.field_id:
            field = next((f for f in spec.fields if f.id == s.field_id), None)
            rendered = " ".join(numbers.render(citer.render(p), tokens)[0] for p in s.paragraphs)
            if field is not None:
                limit = f"{field.max_characters:,} characters" if field.max_characters else f"{field.max_words:,} words"
                count = f"{len(rendered):,} characters" if field.max_characters else f"{len(rendered.split()):,} words"
                doc.add_paragraph().add_run(f"{count} (limit {limit})").italic = True
        if s.table:
            _table(doc, [[numbers.render(citer.render(c), tokens)[0] for c in row] for row in s.table], numbers.render(citer.render(s.table_caption), tokens)[0] or s.heading)
        for rows, caption in tables.pop(s.key, []):
            _table(doc, rows, caption)
    for rows, caption in [t for group in tables.values() for t in group]:  # tables whose section is absent
        _table(doc, rows, caption)
    cited = [i for i in document.cited if i in library]
    if cited:
        doc.add_heading("Reference List" if spec.citation_style == "HARVARD" else "References", level=1)
        for entry in ev.reference_list([library[i].source for i in cited], spec.citation_style):
            p = doc.add_paragraph(entry)
            p.paragraph_format.left_indent = Inches(0.5)
            p.paragraph_format.first_line_indent = Inches(-0.5)
    if document.ai_note:  # on a page of its own at the end (owner decision 2026-09-30)
        doc.add_paragraph().add_run().add_break(WD_BREAK.PAGE)
        doc.add_paragraph(document.ai_note)
    out = io.BytesIO()
    doc.save(out)
    return out.getvalue()


def generated_tables(document: WorkDocument, spec: ResolvedSpec, results: ResultsModel | None, budget: Budget | None) -> list[tuple[str, str, list[list[str]], str]]:
    """The tables code renders from the Results Model and budget, as (the section they follow, kind,
    rows, caption): the Word file and the length checks use the same list."""
    out: list[tuple[str, str, list[list[str]], str]] = []
    if results is not None and spec.kind == "FUNDING_PROPOSAL":
        if document.variant == "NGO_PROJECT":
            out.append((_after("logframe", document), "logframe", results_engine.logframe(results), "Logframe"))
        out.append((_after("workplan", document), "workplan", results_engine.workplan(results, spec.duration_months), "Workplan"))
        out.append((_after("mel", document), "mel", results_engine.mel_table(results), "Monitoring and evaluation indicators"))
    if budget is not None and budget.lines and (spec.kind == "FUNDING_PROPOSAL" or any(li.unit_cost for li in budget.lines)):
        summary, detail = _budget_tables(budget)
        key = _after("budget", document)
        out.append((key, "budget", summary, "Budget summary"))
        if spec.kind == "FUNDING_PROPOSAL":
            out.append((key, "budget", detail, "Detailed budget"))
    return out


def _after(table: str, document: WorkDocument) -> str:
    keys = {s.key for s in document.sections}
    return next((k for k in TABLES_AFTER[table] if k in keys), "")
