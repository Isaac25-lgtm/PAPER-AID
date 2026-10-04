"""Reading a dataset: CSV or Excel (.xlsx), as values only. Formulas are never run (Excel's saved
results are read), macro-enabled and old binary workbooks are refused, and the size limits are
checked before a whole file is held in memory (decision 2026-10-03: limits are measured, not
promised). Every cell is kept as read; types are decided afterwards (`profile.infer`), so an
identifier such as "00123" is never turned into a number here."""

import csv
import io
import zipfile
from dataclasses import dataclass, field
from datetime import date, datetime, time
from typing import Any

from app.core.errors import AppError


@dataclass(frozen=True)
class Limits:
    rows: int
    columns: int
    cells: int
    expanded_bytes: int  # an .xlsx is a zip: what it may unpack to


@dataclass
class Table:
    """A sheet or CSV as read: the header row's names (made unique) and the rows below it."""

    columns: list[str]
    rows: list[list[Any]]
    sheet: str | None = None
    sheets: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    delimiter: str = ""  # a CSV's separator: with ";" a value like 1.234 may mean a thousand and more


def read(data: bytes, filename: str, sheet: str | None, limits: Limits) -> Table:
    name = filename.lower()
    if name.endswith((".xlsm", ".xlsb", ".xltm")):
        raise AppError("Macro-enabled workbooks can't be opened. Save it as an ordinary Excel workbook (.xlsx) or as CSV.", code="DATA_MACROS")
    if name.endswith(".xls"):
        raise AppError("This is an older Excel file (.xls). Save it as .xlsx or CSV, then upload it again.", code="DATA_OLD_EXCEL")
    if name.endswith(".xlsx"):
        return _xlsx(data, sheet, limits)
    if name.endswith((".csv", ".txt", ".tsv")):
        return _csv(data, limits)
    raise AppError("Upload a CSV file or an Excel workbook (.xlsx).", code="DATA_FORMAT")


def _csv(data: bytes, limits: Limits) -> Table:
    text = None
    for encoding in ("utf-8-sig", "cp1252"):
        try:
            text = data.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        raise AppError("PaperAid couldn't read the characters in this file. Save it as CSV (UTF-8) and upload it again.", code="DATA_ENCODING")
    if "\x00" in text[:10000]:
        raise AppError("This doesn't look like a text CSV file. Save it as CSV and upload it again.", code="DATA_FORMAT")
    sample = text[:20000]
    try:
        delimiter = csv.Sniffer().sniff(sample, delimiters=",;\t|").delimiter
    except csv.Error:
        delimiter = ","
    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    rows: list[list[Any]] = []
    header: list[str] | None = None
    for number, row in enumerate(reader, start=1):
        if header is None:
            if not any(c.strip() for c in row):
                continue  # blank lines above the header
            header = row
            _check_width(len(header), limits)
            continue
        if not any(c.strip() for c in row):
            continue
        if len(row) > len(header):
            if any(c.strip() for c in row[len(header):]):
                raise AppError(f"Row {number} has more values than there are column names. Check the separators in that row, then upload it again.", code="DATA_SHAPE")
            row = row[: len(header)]
        rows.append([c if c.strip() else None for c in row] + [None] * (len(header) - len(row)))
        _check_size(len(rows), len(header), limits)
    if header is None or not rows:
        raise AppError("The file has no rows of data under its column names.", code="DATA_EMPTY")
    return Table(columns=_names(header), rows=rows, delimiter=delimiter)


def sheet_names(data: bytes) -> list[str]:
    from openpyxl import load_workbook

    workbook = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    try:
        return [ws.title for ws in workbook.worksheets]
    finally:
        workbook.close()


def _xlsx(data: bytes, sheet: str | None, limits: Limits) -> Table:
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise AppError("This Excel file is damaged or isn't really an .xlsx file.", code="DATA_FORMAT") from exc
    with archive:
        if any(i.filename.lower().endswith("vbaproject.bin") for i in archive.infolist()):
            raise AppError("This workbook contains macros. Save it as an ordinary Excel workbook (.xlsx) or as CSV.", code="DATA_MACROS")
        if sum(i.file_size for i in archive.infolist()) > limits.expanded_bytes:
            raise AppError("This workbook is too large to analyse here. Upload the sheet you need as CSV, or a smaller extract.", code="DATA_TOO_LARGE")
    from openpyxl import load_workbook
    from openpyxl.utils.exceptions import InvalidFileException

    try:
        workbook = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    except (InvalidFileException, KeyError, OSError) as exc:
        raise AppError("This Excel file couldn't be opened. Save it again as .xlsx, or as CSV.", code="DATA_FORMAT") from exc
    try:
        names = [ws.title for ws in workbook.worksheets]
        chosen = sheet if sheet in names else None
        if chosen is None:
            if sheet is not None:
                raise AppError(f"The workbook has no sheet called \"{sheet}\".", code="DATA_SHEET")
            chosen = names[0]
        ws = workbook[chosen]
        unsaved = _unsaved_formulas(data, chosen)
        if unsaved:
            raise AppError(f"{unsaved:,} cell{'s' if unsaved != 1 else ''} in sheet \"{chosen}\" {'have' if unsaved != 1 else 'has'} formulas whose results Excel hasn't saved, so their values can't be read. Open the file "
                           "in Excel, save it, and upload it again.", code="DATA_FORMULAS")
        header: list[Any] | None = None
        rows: list[list[Any]] = []
        for values in ws.iter_rows(values_only=True):
            cells = [_cell(v) for v in values]
            if header is None:
                if not any(c is not None for c in cells):
                    continue
                header = cells
                while header and header[-1] is None:
                    header.pop()
                _check_width(len(header), limits)
                continue
            if not any(c is not None for c in cells):
                continue
            if len(cells) > len(header) and any(c is not None for c in cells[len(header):]):
                raise AppError(f"Sheet \"{chosen}\" has values to the right of its last column name. Give every column a name, then upload it again.", code="DATA_SHAPE")
            cells = cells[: len(header)] + [None] * (len(header) - len(cells))
            rows.append(cells)
            _check_size(len(rows), len(header), limits)
    finally:
        workbook.close()
    if header is None or not rows:
        raise AppError(f"Sheet \"{chosen}\" has no rows of data under its column names.", code="DATA_EMPTY")
    notes = [f"This workbook has {len(names)} sheets; PaperAid read \"{chosen}\"."] if len(names) > 1 else []
    return Table(columns=_names([str(h) if h is not None else "" for h in header]), rows=rows, sheet=chosen, sheets=names, notes=notes)


def _unsaved_formulas(data: bytes, sheet: str) -> int:
    """Formula cells with no saved result (a workbook written by a program that never calculated it):
    read as values they would be blank, so they are counted and the file refused (Codex audit, finding 10)."""
    from openpyxl import load_workbook

    values = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    formulas = load_workbook(io.BytesIO(data), read_only=True, data_only=False)
    try:
        count = 0
        for saved, written in zip(values[sheet].iter_rows(values_only=True), formulas[sheet].iter_rows(values_only=True), strict=False):
            count += sum(1 for v, f in zip(saved, written, strict=False) if v is None and isinstance(f, str) and f.startswith("="))
        return count
    finally:
        values.close()
        formulas.close()


def _cell(value: Any) -> Any:
    """A cell's value as read: numbers stay numbers, dates stay dates, text is kept as written
    (blank text is empty)."""
    if value is None:
        return None
    if isinstance(value, str):
        return value if value.strip() else None
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, (int, float, datetime, date)):
        return value
    if isinstance(value, time):
        return value.isoformat()
    return str(value)


def _names(header: list[str]) -> list[str]:
    """Column names as given, trimmed; a blank name becomes "Column N" and a repeated one gets
    " (2)", so every column can be told apart."""
    out: list[str] = []
    seen: set[str] = set()
    for n, raw in enumerate(header, start=1):
        name = " ".join(str(raw).split())[:120] or f"Column {n}"
        base, k = name, 2
        while name.lower() in seen:
            name, k = f"{base} ({k})", k + 1
        seen.add(name.lower())
        out.append(name)
    return out


def _check_width(columns: int, limits: Limits) -> None:
    if columns > limits.columns:
        raise AppError(f"This file has {columns:,} columns; PaperAid analyses up to {limits.columns:,}. Remove the columns you don't need and upload it again.",
                       code="DATA_TOO_WIDE")


def _check_size(rows: int, columns: int, limits: Limits) -> None:
    if rows > limits.rows:
        raise AppError(f"This file has more than {limits.rows:,} rows, the most PaperAid analyses at a time. Upload an extract with the rows you need.", code="DATA_TOO_LONG")
    if rows * columns > limits.cells:
        raise AppError(f"This file has more than {limits.cells:,} cells, the most PaperAid analyses at a time. Remove columns or rows you don't need.", code="DATA_TOO_LARGE")
