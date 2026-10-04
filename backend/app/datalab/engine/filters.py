"""Filters (owner decision 2026-10-04, reviewed by Codex): any analysis can be limited to the records
that match conditions on any variable (a category's values, a range of numbers or dates), several
combined. Applied before anything is counted, so every table, chart and map, and every protection of
small counts, works on the filtered records.

Guards: a variable left out of analysis, or flagged as identifying people or giving their location,
can't be a filter. A filter must keep at least the disclosure threshold of records and leave out
either none or at least that many: otherwise a filtered result compared with the unfiltered one would
reveal a few people by subtraction. Results released together (a report, the report workbook) are
also checked as a set (`overlaps`). Missing values never match a condition and are counted apart."""

from datetime import timedelta

import pandas as pd

from app.core.errors import AppError
from app.datalab.engine.disclosure import few
from app.datalab.models import Filter, Variable

MAX_FILTERS = 5


def _text(series: pd.Series) -> pd.Series:
    return series.astype("string").str.strip() if series.dtype != "float64" else series.map(lambda v: f"{v:g}" if pd.notna(v) else pd.NA)


def check(filters: list[Filter], variables: dict[str, Variable]) -> None:
    """Refuse a filter that can't be used, before any work starts."""
    if len(filters) > MAX_FILTERS:
        raise AppError(f"Use up to {MAX_FILTERS} filters at a time.", code="TOO_MANY_FILTERS")
    for f in filters:
        var = variables.get(f.variable)
        if var is None:
            raise AppError("Filter on a variable in the dataset.", code="UNKNOWN_VARIABLE")
        if var.excluded or "PERSONAL" in var.flags or "LOCATION" in var.flags:
            raise AppError(f"\"{var.title()}\" may identify people or places, so it can't be used to choose records.", code="FILTER_NOT_ALLOWED")
        if f.op in ("IN", "NOT_IN") and not f.values:
            raise AppError(f"Choose at least one value of \"{var.title()}\".", code="FILTER_INCOMPLETE")
        if f.op == "BETWEEN":
            if var.stored not in ("number", "date"):
                raise AppError(f"\"{var.title()}\" isn't a number or a date, so it has no range.", code="FILTER_INCOMPLETE")
            if not f.low and not f.high:
                raise AppError(f"Give a lower or an upper limit for \"{var.title()}\".", code="FILTER_INCOMPLETE")
            for bound in (f.low, f.high):
                if bound and _bound(var, bound) is None:
                    raise AppError(f"\"{bound}\" isn't a {'date (YYYY-MM-DD)' if var.stored == 'date' else 'number'}.", code="FILTER_INCOMPLETE")


def _bound(var: Variable, text: str):
    try:
        return pd.Timestamp(text) if var.stored == "date" else float(text)
    except ValueError:
        return None


def describe(filters: list[Filter], variables: dict[str, Variable]) -> str:
    """The filter in words: "sex is Female; age from 18 to 35"."""
    parts = []
    for f in filters:
        name = variables[f.variable].title() if f.variable in variables else f.variable
        if f.op == "IN":
            parts.append(f"{name} is {' or '.join(f.values[:6])}{' …' if len(f.values) > 6 else ''}")
        elif f.op == "NOT_IN":
            parts.append(f"{name} is not {' or '.join(f.values[:6])}{' …' if len(f.values) > 6 else ''}")
        elif f.low and f.high:
            parts.append(f"{name} from {f.low} to {f.high}")
        elif f.low:
            parts.append(f"{name} from {f.low}")
        else:
            parts.append(f"{name} up to {f.high}")
    return "; ".join(parts)


def mask(frame: pd.DataFrame, filters: list[Filter], variables: dict[str, Variable]) -> tuple[pd.Series, list[str]]:
    """Which records match every condition, and the records left out for having no value."""
    keep = pd.Series(True, index=frame.index)
    notes = []
    for f in filters:
        var = variables[f.variable]
        col = frame[f.variable]
        present = col.notna()
        if f.op in ("IN", "NOT_IN"):
            hit = _text(col).isin(f.values).fillna(False).astype(bool)
            match = hit if f.op == "IN" else ~hit
        else:
            match = pd.Series(True, index=frame.index)
            low, high = _bound(var, f.low) if f.low else None, _bound(var, f.high) if f.high else None
            if low is not None:
                match &= (col >= low).fillna(False).astype(bool)
            if high is not None:
                whole_day = var.stored == "date" and len(f.high.strip()) == 10
                match &= (col < high + timedelta(days=1) if whole_day else col <= high).fillna(False).astype(bool)
        keep &= match & present
        notes.append((var, int((~present).sum())))
    return keep, [f"{few(n, 5).capitalize()} records have no value for \"{v.title()}\", so no filter could include them." for v, n in notes if n]


def apply(frame: pd.DataFrame, filters: list[Filter], variables: dict[str, Variable], threshold: int) -> tuple[pd.DataFrame, list[str], str]:
    """The records an analysis uses, the notes for its record, and the filter in words. Refused when the
    result would identify people: fewer records than the threshold kept, or fewer than the threshold
    (but some) left out."""
    if not filters:
        return frame, [], ""
    check(filters, variables)
    keep, missing_notes = mask(frame, filters, variables)
    kept, dropped = int(keep.sum()), int((~keep).sum())
    words = describe(filters, variables)
    if kept == 0:
        raise AppError(f"No records match all of these conditions ({words}).", code="FILTER_EMPTY")
    if kept < threshold:
        raise AppError(f"Fewer than {threshold} records match ({words}): too few to show without identifying people. Widen the filter.",
                       code="FILTER_TOO_NARROW")
    if 0 < dropped < threshold:
        raise AppError(f"This filter leaves out fewer than {threshold} records ({words}). Compared with the whole data, it would reveal those few "
                       "people: widen it, or analyse without it.", code="FILTER_TOO_NARROW")
    notes = [f"{dropped:,} records are outside the filter ({words})." if dropped else "", *[n.replace("Fewer than 5", f"Fewer than {threshold}") for n in missing_notes]]
    return frame[keep].reset_index(drop=True), [n for n in notes if n], words


def overlaps(frame: pd.DataFrame, populations: dict[str, list[Filter]], titles: dict[str, str], variables: dict[str, Variable], threshold: int,
             used: dict[str, pd.Series] | None = None) -> None:
    """Results released together are checked as a set: two whose records differ by only a few (but
    some) would reveal those few by subtraction, so the release is refused with the pair named. `used`:
    the rows each analysis actually used, where recorded; otherwise its filter's rows."""
    masks = {}
    for analysis_id, filters in populations.items():
        if used and analysis_id in used:
            masks[analysis_id] = used[analysis_id]
        else:
            masks[analysis_id] = mask(frame, filters, variables)[0] if filters else pd.Series(True, index=frame.index)
    ids = list(masks)
    for i, a in enumerate(ids):
        for b in ids[i + 1:]:
            differ = int((masks[a] ^ masks[b]).sum())
            if 0 < differ < threshold:
                raise AppError(f"\"{titles[a]}\" and \"{titles[b]}\" cover almost the same records (they differ by fewer than {threshold}), so together "
                               "they could reveal those few people. Leave one out, or widen its filter.", code="OVERLAPPING_RESULTS")
