"""Cleaning, conservatively (decision 2026-10-03). The only automatic change is trimming spaces
around category labels. Everything that changes a value, merges categories or removes rows is a
proposal with a plain question, applied only when the researcher confirms it, and every applied
change makes a new version with its record. Identifiers, free text and dates are never touched."""

import re
import secrets

import numpy as np
import pandas as pd

from app.datalab.models import CleaningStep, Variable

# Text that only means "no answer here". "Unknown" and "Don't know" are real answers and are kept.
MISSING_TOKENS = {"n/a", "na", "n.a.", "none", "null", "nil", "missing", "-", "--", ".", "?", "#n/a", "nan"}
SENTINELS = (-9.0, -99.0, -999.0, -9999.0)
SYNONYMS = {"m": "male", "f": "female", "y": "yes", "n": "no"}
AGE = re.compile(r"(^|[\s_])age($|[\s_(])|^age", re.I)


def _id() -> str:
    return f"cs_{secrets.token_hex(4)}"


LISTED = 5  # values named in a description or question; the full list is in the step itself
LABEL = 40  # characters of a value named there


def _quoted(values: list[str]) -> str:
    shown = ", ".join(repr(v if len(v) <= LABEL else v[: LABEL - 1] + "…") for v in values[:LISTED])
    return shown + (f" and {len(values) - LISTED:,} more" if len(values) > LISTED else "")


def proposals(frame: pd.DataFrame, variables: list[Variable], threshold: int = 5) -> list[CleaningStep]:
    """What PaperAid would change, each with its question. TRIM steps are automatic. Counts below the
    disclosure threshold are written "fewer than N" (they reach the report's cleaning log), and long
    lists of values are shortened in the text (Codex audit, finding 8)."""
    out: list[CleaningStep] = []

    def few(n: int) -> str:
        return f"{n:,}" if n == 0 or n >= threshold else f"fewer than {threshold}"
    for var in variables:
        if "DECIMAL_COMMA" in var.flags and var.stored == "text" and var.name in frame and "RECORD_ID" not in var.flags:
            values = frame[var.name].dropna().astype(str).str.strip()
            examples = list(dict.fromkeys(values))[:3]
            shown = ", ".join(f"\"{v}\" → {_european(v):g}" for v in examples)
            out.append(CleaningStep(id=_id(), kind="DECIMAL_COMMA", column=var.name, affected=len(values),
                                    description=f"Read \"{var.title()}\" as numbers written with a decimal comma and dots between thousands ({shown}).",
                                    question=f"\"{var.title()}\" looks like numbers written the European way: {shown}. Read them as numbers like this?"))
            continue
        if var.kind in ("IDENTIFIER", "DATE") or "PERSONAL" in var.flags or var.name not in frame:
            continue
        col = frame[var.name]
        categories = var.kind in ("CATEGORICAL", "BINARY")
        if var.stored == "text":
            values = col.dropna().astype(str)
            padded = int((values != values.str.strip()).sum())
            if padded and categories:
                out.append(CleaningStep(id=_id(), kind="TRIM", column=var.name, automatic=True, affected=padded,
                                        description=f"Removed spaces before or after {few(padded)} values of \"{var.title()}\"."))
            stripped = values.str.strip()
            tokens = sorted({v for v in stripped.unique() if v.lower() in MISSING_TOKENS})
            rest = stripped[~stripped.isin(tokens)]
            numeric_after = bool(len(rest)) and bool(rest.map(_is_number).all())
            if tokens and (categories or numeric_after):  # free text keeps its words, unless they only mark a missing number
                n = int(stripped.isin(tokens).sum())
                out.append(CleaningStep(id=_id(), kind="SET_MISSING", column=var.name, params={"values": tokens}, affected=n,
                                        description=f"Treat {_quoted(tokens)} in \"{var.title()}\" as missing ({few(n)} values)"
                                                    + (", so it can be analysed as numbers." if numeric_after else "."),
                                        question=f"\"{var.title()}\" has {few(n)} values written as {_quoted(tokens)}. Treat them as missing?"))
            merge = _variants(rest) if categories else {}
            if merge:
                n = int(stripped.isin(list(merge)).sum())
                targets = sorted(set(merge.values()))
                pairs = "; ".join(f"{_quoted(sorted(v for v in merge if merge[v] == target))} → {_quoted([target])}" for target in targets[:LISTED])
                if len(targets) > LISTED:
                    pairs += f"; and {len(targets) - LISTED:,} more categories"
                out.append(CleaningStep(id=_id(), kind="MERGE_LEVELS", column=var.name, params={"mapping": merge}, affected=n,
                                        description=f"Merge spellings of the same category in \"{var.title()}\": {pairs}.",
                                        question=f"\"{var.title()}\" spells the same category in different ways ({pairs}). Merge them?"))
        elif var.stored == "number":
            x = col.dropna()
            if AGE.search(var.name):
                bad = x[(x < 0) | (x > 120)]
                if len(bad):
                    out.append(CleaningStep(id=_id(), kind="OUT_OF_RANGE", column=var.name, params={"low": 0.0, "high": 120.0}, affected=int(len(bad)),
                                            description=f"Treat {few(len(bad))} ages below 0 or above 120 in \"{var.title()}\" as missing.",
                                            question=f"\"{var.title()}\" has {few(len(bad))} values below 0 or above 120, which can't be ages. Treat them as missing?"))
            sentinels = [s for s in SENTINELS if (x == s).any()]
            if sentinels and (x[~x.isin(sentinels)] >= 0).all():
                n = int(x.isin(sentinels).sum())
                codes = ", ".join(f"{s:g}" for s in sentinels)
                out.append(CleaningStep(id=_id(), kind="SET_MISSING", column=var.name, params={"numbers": [f"{s:g}" for s in sentinels]}, affected=n,
                                        description=f"Treat {codes} in \"{var.title()}\" as missing-value codes ({few(n)} values).",
                                        question=f"\"{var.title()}\" is never negative except for {few(n)} values of {codes}, which are usually codes for a missing answer. "
                                                 "Treat them as missing?"))
    duplicates = int(frame.duplicated(keep="first").sum())
    if duplicates:
        out.append(CleaningStep(id=_id(), kind="DUPLICATES", affected=duplicates,
                                description=f"Remove {few(duplicates)} rows that repeat another row exactly.",
                                question=f"{few(duplicates).capitalize()} rows repeat another row in every column. Remove the repeats, keeping the first of each?"))
    return out


def _european(value: str) -> float:
    """1.234,5 → 1234.5; 1,5 → 1.5; 1.234 → 1234 (the researcher confirmed this reading)."""
    return float(value.strip().replace(".", "").replace(",", "."))


def _is_number(value: str) -> bool:
    try:
        float(value)
    except ValueError:
        return False
    return True


def _variants(values: pd.Series) -> dict[str, str]:
    """Spellings that differ only in capitals, inner spaces or a standard abbreviation (M/F, Y/N)
    when the full word is also there: each mapped to the most common spelling of its group."""
    counts = values.value_counts()
    groups: dict[str, list[str]] = {}
    present = {" ".join(v.lower().split()) for v in counts.index}
    for value in counts.index:
        key = " ".join(value.lower().split())
        if key in SYNONYMS and SYNONYMS[key] in present:
            key = SYNONYMS[key]
        groups.setdefault(key, []).append(value)
    mapping: dict[str, str] = {}
    for spellings in groups.values():
        if len(spellings) > 1:
            target = max(spellings, key=lambda v: (counts[v], v))
            mapping.update({v: target for v in spellings if v != target})
    return mapping


def apply(frame: pd.DataFrame, step: CleaningStep) -> tuple[pd.DataFrame, int]:
    """The frame after one step, and how many cells or rows it changed. The input is not modified."""
    out = frame.copy()
    if step.kind == "DUPLICATES":
        keep = ~out.duplicated(keep="first")
        return out[keep].reset_index(drop=True), int((~keep).sum())
    col = out[step.column]
    if step.kind == "TRIM":
        stripped = col.astype("string").str.strip()
        changed = int((stripped != col.astype("string")).fillna(False).sum())
        out[step.column] = stripped
        return out, changed
    if step.kind == "MERGE_LEVELS":
        mapping = step.params.get("mapping", {})
        assert isinstance(mapping, dict)
        stripped = col.astype("string").str.strip()
        changed = int(stripped.isin(list(mapping)).sum())
        out[step.column] = stripped.replace(mapping)
        return out, changed
    if step.kind == "SET_MISSING":
        if "numbers" in step.params:
            codes = [float(v) for v in step.params["numbers"]]  # type: ignore[union-attr]
            hit = col.isin(codes)
            out[step.column] = col.mask(hit, np.nan)
            return out, int(hit.sum())
        tokens = step.params.get("values", [])
        assert isinstance(tokens, list)
        stripped = col.astype("string").str.strip()
        hit = stripped.isin(tokens).fillna(False)
        out[step.column] = col.mask(hit, pd.NA)
        rest = out[step.column].dropna().astype(str).str.strip()
        if len(rest) and rest.map(_is_number).all() and not rest.str.match(r"^0\d").any():
            out[step.column] = pd.to_numeric(out[step.column], errors="coerce").astype("float64")
        return out, int(hit.sum())
    if step.kind == "DECIMAL_COMMA":  # the original values stay in the earlier version
        present = col.notna()
        out[step.column] = col.astype("string").map(lambda v: _european(v) if isinstance(v, str) else np.nan, na_action="ignore").astype("float64")
        return out, int(present.sum())
    if step.kind == "OUT_OF_RANGE":
        low, high = float(step.params["low"]), float(step.params["high"])  # type: ignore[arg-type]
        hit = (col < low) | (col > high)
        out[step.column] = col.mask(hit, np.nan)
        return out, int(hit.sum())
    raise ValueError(f"unknown cleaning step {step.kind}")
