"""From the cells as read to a typed table and a description of every variable. Types are decided
conservatively (decision 2026-10-03): a column becomes numbers only when every value is a number
and none is written with a leading zero; dates only from real Excel dates or unambiguous ISO
dates; everything else stays text exactly as written. Nothing is changed silently (Codex audit,
finding 10): a column is converted only when every value converts faithfully (a mix of dates and
date-times stays whole; a whole number too long to store exactly stays text, flagged), otherwise it
keeps its values as written. Flags say what needs the researcher's attention: likely personal
identifiers and coordinates (both left out by default), possible survey-design columns (asked, never
assumed)."""

import json
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from app.datalab.engine.ingest import Table
from app.datalab.models import Flag, Kind, Level, Variable

NUMBER = re.compile(r"^[+-]?(\d+(\.\d*)?|\.\d+)([eE][+-]?\d+)?$")
LEADING_ZERO = re.compile(r"^0\d")
DECIMAL_COMMA = re.compile(r"^[+-]?(\d{1,3}(\.\d{3})+|\d+)(,\d+)?$")  # 1,5  1.234,5  12,75
THOUSANDS_DOT = re.compile(r"^[+-]?\d{1,3}(\.\d{3})+$")  # 1.234: a thousand and more, or one and a bit, depending on where it was written
ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}([ T]\d{2}:\d{2}(:\d{2})?)?$")
# Columns that may identify people or places: one rule set, read here and by the browser before a CSV
# is uploaded (identifiers.json, owner decision 2026-10-04).
RULES = json.loads((Path(__file__).parent / "identifiers.json").read_text(encoding="utf-8"))
EMAIL = re.compile(RULES["values"]["EMAIL"], re.I)
PHONE = re.compile(RULES["values"]["PHONE"], re.I)  # Ugandan mobile numbers
NIN = re.compile(RULES["values"]["NIN"], re.I)  # Ugandan national ID numbers
PERSONAL_NAMES = re.compile(RULES["headers"]["PERSONAL"], re.I)
NOT_PERSONAL = re.compile(RULES["except"]["PERSONAL"], re.I)  # district_name, school name: places and organisations
LOCATION_NAMES = re.compile(RULES["headers"]["LOCATION"], re.I)
SURVEY_NAMES = re.compile(r"^(weight|wt|wgt|pweight|sweight|sampling ?weight|survey ?weight|final ?weight|v005|hv005|mv005|cluster|psu|v001|v021|hv021|"
                          r"strata|stratum|v022|hv022|v023|hv023)$", re.I)
ID_NAMES = re.compile(r"(^|[\s_])(id|code|serial|record|no|number|key)$", re.I)
EXACT = 2**53  # beyond this a whole number can't be stored exactly as a number


def infer(table: Table) -> tuple[pd.DataFrame, list[Variable]]:
    """The typed table (numbers as floats, dates as datetimes, text as strings, missing as NA) and
    a profile of each column."""
    data: dict[str, pd.Series] = {}
    variables: list[Variable] = []
    for index, name in enumerate(table.columns):
        values = [row[index] for row in table.rows]
        series, stored, flags = _typed(values, european=table.delimiter == ";")
        data[name] = series
        variables.append(describe(name, series, stored, flags))
    return pd.DataFrame(data), variables


def _typed(values: list[Any], european: bool = False) -> tuple[pd.Series, str, list[Flag]]:
    """One column's values typed, with one vectorised pass per check (a 20 MB file is profiled in
    seconds, not minutes: measured 2026-10-04). Numbers written the European way (a decimal comma, or
    in a semicolon file dots between thousands) stay text, flagged, until the researcher confirms."""
    column = pd.Series(values, dtype=object)
    present = column[column.notna()]
    flags: list[Flag] = []
    if present.empty:
        return pd.Series([None] * len(values), dtype="string"), "text", flags
    kinds = present.map(type)
    types = set(kinds.unique())
    datelike = {t for t in types if issubclass(t, date)}
    numlike = {t for t in types if t in (int, float)}  # bool is never here: the reader writes TRUE/FALSE as text
    has_text = str in types
    others = types - datelike - numlike - {str}
    raw = present[kinds.isin([str])]
    # every check runs on the distinct values only (a survey column holds a handful), then maps back
    distinct = pd.Series(pd.unique(raw), dtype=object) if has_text else pd.Series([], dtype=object)
    text = distinct.str.strip()
    if not numlike and not others and (datelike or text.head(20).str.fullmatch(ISO_DATE.pattern).all()):
        if text.str.fullmatch(ISO_DATE.pattern).all():
            dates = _dates(values)
            if dates is not None:
                return dates, "date", flags
    if not datelike and not others and (not has_text or text.str.fullmatch(NUMBER.pattern).all()):
        if has_text and text.str.match(LEADING_ZERO.pattern).any():
            flags.append("LEADING_ZEROS")  # "00123" is a code, not the number 123
        elif european and has_text and not numlike and text.str.fullmatch(THOUSANDS_DOT.pattern).all():
            flags.append("DECIMAL_COMMA")  # 1.234 in a semicolon file: never read either way without asking
        elif any(_too_long(v) for v in text[text.str.len() > 15]) or any(_too_long(v) for v in present[kinds.isin([int])]):
            flags.append("LONG_NUMBER")  # 9007199254740993 would become ...992 as a number: kept exactly, as text
        else:
            numbers = pd.Series(np.nan, index=column.index, dtype="float64")
            if has_text:
                numbers[raw.index] = raw.map(dict(zip(distinct, pd.to_numeric(text).astype("float64"), strict=True))).astype("float64")
            plain = present[~kinds.isin([str])]
            numbers[plain.index] = plain.astype("float64")
            return numbers.reset_index(drop=True), "number", flags
    if (has_text and not flags and not numlike and not datelike and not others and text.str.contains(",", regex=False).any()
            and text.str.fullmatch(DECIMAL_COMMA.pattern).all() and not text.str.match(LEADING_ZERO.pattern).any()):
        flags.append("DECIMAL_COMMA")
    if has_text and (numlike or datelike):
        flags.append("MIXED")
    out = [None if v is None or (isinstance(v, float) and np.isnan(v)) else _as_text(v) for v in values]
    return pd.Series(out, dtype="string"), "text", flags


def _dates(values: list[Any]) -> pd.Series | None:
    """Dates and date-times as datetimes when every one converts (2026-10-01 and 2026-10-02 12:00 in
    one column included); None when any would be lost."""
    parsed = []
    for v in values:
        if v is None:
            parsed.append(pd.NaT)
            continue
        try:
            parsed.append(pd.Timestamp(v.strip() if isinstance(v, str) else v))
        except ValueError:
            return None
    return pd.Series(pd.to_datetime(parsed), dtype="datetime64[ns]")


def _too_long(value: Any) -> bool:
    if isinstance(value, int):
        return abs(value) > EXACT
    if isinstance(value, str):
        text = value.strip().lstrip("+-")
        return text.isdigit() and int(text) > EXACT
    return False


def _as_text(value: Any) -> str:
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return str(value)


def describe(name: str, series: pd.Series, stored: str, flags: list[Flag] | None = None, label: str = "", kind: Kind | None = None,
             excluded: bool | None = None) -> Variable:
    """A column's profile: its kind (unless the researcher set it), counts, levels or summary, and flags."""
    flags = list(flags or [])
    valid = int(series.notna().sum())
    missing = int(len(series) - valid)
    distinct = int(series.dropna().nunique())
    text_values = series.dropna().astype(str).str.strip() if stored == "text" else pd.Series([], dtype="string")
    if (PERSONAL_NAMES.search(name) and not NOT_PERSONAL.search(name)) or (stored == "text" and valid and (_share(text_values, EMAIL) > 0.5 or _share(text_values, PHONE) > 0.5 or _share(text_values, NIN) > 0.5)):
        flags.append("PERSONAL")
    if LOCATION_NAMES.search(name):
        flags.append("LOCATION")
    if SURVEY_NAMES.match(name.strip()):
        flags.append("SURVEY_DESIGN")
    if valid >= 20 and distinct == valid and (stored == "text" or ID_NAMES.search(name)) and "PERSONAL" not in flags:
        flags.append("RECORD_ID")
    if kind is None:
        kind = _kind(series, stored, distinct, valid, flags)
    if stored == "number" and kind == "NUMERIC" and 2 < distinct <= 7 and (series.dropna() % 1 == 0).all():
        flags.append("FEW_VALUES")
    levels: list[Level] = []
    summary: dict[str, float] = {}
    # Levels for categories, for text, and for numbers with few values (codes the researcher may treat as categories).
    if kind in ("CATEGORICAL", "BINARY") or (stored == "text" and kind != "IDENTIFIER") or (stored == "number" and distinct <= 50):
        if stored == "number":  # counted first, then only the distinct values formatted
            raw = series.dropna().value_counts()
            counts = raw.groupby(raw.index.map(lambda v: f"{v:g}")).sum().sort_values(ascending=False, kind="stable")
        else:
            counts = series.dropna().astype(str).str.strip().value_counts()
        levels = [Level(value=str(v), count=int(c)) for v, c in counts.head(50).items()]
    if stored == "number" and valid:
        x = series.dropna().astype(float)
        summary = {"min": float(x.min()), "q1": float(x.quantile(0.25)), "median": float(x.median()), "mean": float(x.mean()), "q3": float(x.quantile(0.75)),
                   "max": float(x.max())}
        if valid > 1:
            summary["sd"] = float(x.std(ddof=1))
    if excluded is None:  # names, phone numbers and exact coordinates stay out until the researcher includes them (Codex audit, finding 3)
        excluded = "PERSONAL" in flags or "LOCATION" in flags
    return Variable(name=name, label=label, kind=kind, stored=stored, valid=valid, missing=missing, distinct=distinct, levels=levels, summary=summary,
                    flags=list(dict.fromkeys(flags)), excluded=excluded)


def _kind(series: pd.Series, stored: str, distinct: int, valid: int, flags: list[Flag]) -> Kind:
    if "RECORD_ID" in flags or "LEADING_ZEROS" in flags and distinct > 50:
        return "IDENTIFIER"
    if stored == "date":
        return "DATE"
    if distinct == 2:
        return "BINARY"
    if stored == "number":
        return "NUMERIC"
    if distinct <= 10 or distinct <= 50 and distinct / valid <= 0.5:
        return "CATEGORICAL"
    return "TEXT"


SAMPLE = 5_000  # values checked for a pattern: enough to tell whether most of a column matches


def _share(values: pd.Series, pattern: re.Pattern[str]) -> float:
    if values.empty:
        return 0.0
    sample = values.iloc[:: max(1, len(values) // SAMPLE)]
    return float(sample.str.match(pattern.pattern, flags=pattern.flags).mean())
