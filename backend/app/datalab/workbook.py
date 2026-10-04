"""The workbooks (decision 2026-10-03), built by code with no AI. The report workbook is shareable:
README, the data dictionary, the cleaning log and one sheet per analysis (its table, how it was
calculated and a real Excel chart where the table supports one, the chart image otherwise), every
table from the result's protected table and every count in running text protected too. It holds no
individual records: since Codex's audit (finding 2) the cleaned data is a separate file for the
researcher alone (`cleaned`), which says on its cover what it is and leaves out the columns left out
of analysis (names, phone numbers, coordinates) unless the researcher included them."""

import io
import re
from datetime import UTC, datetime

import pandas as pd
import xlsxwriter

from app.datalab.models import AnalysisResult, CleaningStep, ResultTable, Variable

GREEN = "#0F633E"
EXCEL_MAX_ROWS = 1_048_575


def _sheet_name(n: int, title: str, used: set[str]) -> str:
    base = re.sub(r"[\[\]:*?/\\]", " ", f"{n} {title}")[:31].strip()
    name, k = base, 2
    while name.lower() in used:
        suffix = f" ({k})"
        name, k = base[: 31 - len(suffix)] + suffix, k + 1
    used.add(name.lower())
    return name


def build(title: str, source_name: str, version: int, rows: int, threshold: int, variables: list[Variable], cleaning: list[CleaningStep],
          analyses: list[AnalysisResult], chart_bytes) -> bytes:
    buffer = io.BytesIO()
    book = xlsxwriter.Workbook(buffer, {"in_memory": True, "strings_to_formulas": False, "strings_to_urls": False})
    head = book.add_format({"bold": True, "font_color": "white", "bg_color": GREEN, "border": 1, "text_wrap": True, "valign": "top"})
    cell = book.add_format({"border": 1, "text_wrap": True, "valign": "top"})
    number = book.add_format({"border": 1, "num_format": "#,##0.00"})
    whole = book.add_format({"border": 1, "num_format": "#,##0"})
    percent = book.add_format({"border": 1, "num_format": '0.0"%"'})
    title_fmt = book.add_format({"bold": True, "font_size": 14, "font_color": GREEN})
    note = book.add_format({"italic": True, "font_color": "#4B5563", "text_wrap": True})
    used: set[str] = set()

    readme = book.add_worksheet("README")
    used.add("readme")
    readme.set_column(0, 0, 28)
    readme.set_column(1, 1, 90)
    readme.write(0, 0, title or "Analysis", title_fmt)
    lines = [("Made", f"{datetime.now(UTC):%d %B %Y} by PaperAid Data Lab"), ("Source file", source_name), ("Data version", f"{version} ({rows:,} records)"),
             ("Analyses", str(len(analyses))), ("Small counts", f"Counts below {threshold} are hidden (–), with any number that would reveal them."),
             ("Personal identifiers", "This workbook holds no individual records. Columns that may identify people or places are left out of the analyses."),
             ("Numbers", "Every number was calculated by PaperAid's code; see each analysis sheet for how.")]
    for i, (k, v) in enumerate(lines, start=2):
        readme.write(i, 0, k, head)
        readme.write(i, 1, v, cell)

    _table_sheet(book, used, "Data dictionary", ["Column", "Label", "Type", "Missing", "Left out"],
                 [[v.name, v.label, v.kind.title(), _count(v.missing, threshold), "Yes" if v.excluded else ""] for v in variables], head, cell, whole)
    _table_sheet(book, used, "Cleaning log", ["Step", "Change", "Values or rows changed", "How", "Version made"],
                 [[n, s.description, _count(s.affected, threshold), "Automatic" if s.automatic else "Confirmed", s.version or ""]
                  for n, s in enumerate(cleaning, start=1)], head, cell, whole)

    for n, result in enumerate(analyses, start=1):
        ws = book.add_worksheet(_sheet_name(n, result.title, used))
        ws.set_column(0, 0, 34)
        ws.set_column(1, 12, 18)
        ws.write(0, 0, result.title, title_fmt)
        row = 2
        anchors: list[tuple[int, ResultTable]] = []
        for table in result.tables:
            ws.write(row, 0, table.title, book.add_format({"bold": True}))
            row += 1
            ws.write_row(row, 0, table.columns, head)
            anchors.append((row, table))
            for r in table.rows:
                row += 1
                for c, value in enumerate(r[: len(table.columns)]):
                    plain = _plain_number(value.text) if not value.suppressed else None
                    if plain is not None:  # a cell that is only a number (or a percentage) stays a number Excel can use
                        ws.write_number(row, c, plain, percent if value.text.endswith("%") else whole if plain.is_integer() else number)
                    else:
                        ws.write(row, c, value.text, cell)
            for text in table.notes:
                row += 1
                ws.write(row, 0, text, note)
            row += 2
        rec = result.record
        details = [("Question", rec.question), ("Method", rec.method), ("Why this method", rec.why), ("Records used", f"{rec.rows_used:,} of {rec.rows_available:,}"),
                   ("Left out", " ".join(rec.left_out) or "None"), ("Coding", " ".join(rec.coding) or "As in the data"), ("Missing values", rec.missing),
                   ("Checks", " ".join(rec.assumptions) or "None needed"), ("Significance level", f"{rec.alpha:g}"), ("Software", ", ".join(rec.software)),
                   ("Warnings", " ".join(result.warnings) or "None")]
        for k, v in details:
            ws.write(row, 0, k, head)
            ws.write(row, 1, v, cell)
            row += 1
        chart = _native_chart(book, ws, result, anchors)
        if chart is not None:
            ws.insert_chart(row + 1, 0, chart)
        elif result.chart:
            png = chart_bytes(result.chart)
            if png:
                ws.insert_image(row + 1, 0, "chart.png", {"image_data": io.BytesIO(png), "x_scale": 0.45, "y_scale": 0.45})

    book.close()
    return buffer.getvalue()


def _count(n: int, threshold: int) -> int | str:
    return n if n == 0 or n >= threshold else f"fewer than {threshold}"


def cleaned(title: str, source_name: str, version: int, data: pd.DataFrame, released: list[str]) -> bytes:
    """The researcher's cleaned data: a cover sheet saying what it is, then the records."""
    buffer = io.BytesIO()
    book = xlsxwriter.Workbook(buffer, {"in_memory": True, "constant_memory": True, "strings_to_formulas": False, "strings_to_urls": False})
    head = book.add_format({"bold": True, "font_color": "white", "bg_color": GREEN, "border": 1})
    wrap = book.add_format({"text_wrap": True, "valign": "top"})
    cover = book.add_worksheet("About this file")
    cover.set_column(0, 0, 100)
    lines = [f"{title or 'Data'}: cleaned data", f"From \"{source_name}\", data version {version}, made {datetime.now(UTC):%d %B %Y} by PaperAid Data Lab.",
             "This file holds individual records. Keep and share it only as your ethics approval and your participants' consent allow.",
             "Columns that may identify people or places (names, phone numbers, ID numbers, exact coordinates) are left out unless you included them."]
    if released:
        lines.append("You included these columns, which may identify people or places: " + ", ".join(released) + ".")
    for i, text in enumerate(lines):
        cover.write(i, 0, text, wrap)
    ws = book.add_worksheet("Cleaned data")
    columns = list(data.columns)
    ws.write_row(0, 0, columns, head)
    ws.freeze_panes(1, 0)
    for c, name in enumerate(columns):
        ws.set_column(c, c, max(10, min(30, len(name) + 2)))
    for r, record in enumerate(data.head(EXCEL_MAX_ROWS).itertuples(index=False), start=1):
        for c, value in enumerate(record):
            if value is None or (not isinstance(value, str) and pd.isna(value)):
                continue
            if isinstance(value, float):
                ws.write_number(r, c, value)
            else:
                ws.write_string(r, c, str(value))
    book.close()
    return buffer.getvalue()


def _plain_number(text: str) -> float | None:
    try:
        return float(text.replace(",", "").removesuffix("%"))
    except ValueError:
        return None


def _table_sheet(book, used: set[str], name: str, columns: list[str], rows: list[list], head, cell, whole) -> None:
    ws = book.add_worksheet(name)
    used.add(name.lower())
    ws.write_row(0, 0, columns, head)
    ws.freeze_panes(1, 0)
    for c in range(len(columns)):
        ws.set_column(c, c, 40 if c == 1 else 18)
    for r, values in enumerate(rows, start=1):
        for c, value in enumerate(values):
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                ws.write_number(r, c, value, whole)
            else:
                ws.write(r, c, value, cell)
    if rows:
        ws.autofilter(0, 0, len(rows), len(columns) - 1)


def _native_chart(book, ws, result: AnalysisResult, anchors: list[tuple[int, ResultTable]]):
    """A real Excel chart over the sheet's own cells: category percentages as bars. Other results
    use the image (Excel can't draw binned densities or intervals from a table)."""
    if result.spec.kind != "DESCRIBE" or not anchors or "mean" in result.statistics:
        return None
    header_row, table = anchors[0]
    body = [i for i, r in enumerate(table.rows) if r[0].text != "Total" and not r[2].suppressed and r[2].value is not None]
    if len(body) < 2 or len(body) > 15 or body != list(range(len(body))):
        return None
    sheet = ws.get_name()
    first, last = header_row + 1, header_row + len(body)
    chart = book.add_chart({"type": "bar"})
    chart.add_series({"name": "Percent", "categories": [sheet, first, 0, last, 0], "values": [sheet, first, 2, last, 2], "fill": {"color": GREEN},
                      "data_labels": {"value": True}})
    chart.set_title({"name": result.title})
    chart.set_legend({"none": True})
    chart.set_y_axis({"reverse": True})
    return chart
