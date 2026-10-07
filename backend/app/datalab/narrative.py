"""The report's narrative is written from the computed results only (decision 2026-10-03): every
number enters as a token ⟦N:a1.mean⟧ that code fills in from the result, so the text and the tables
can never disagree, and a hidden (small) count has no token to use. Code then checks what wording
rules code can check: no stray digits, no causal claims, no "times more likely", no significance
claimed where p is not below the level. The final reviewer judges the rest."""

import math
import re
from typing import Any

from app.datalab.engine.stats import p_text
from app.datalab.models import AnalysisResult
from app.works.numbers import NUMBER_TOKEN

CAUSAL = re.compile(r"\b(caus(e|es|ed|ing)|lead(s)? to|led to|driv(e|es|en|ing)|drove|result(s|ed)? in|effects? (?!size)(of|on)|impact(s|ed)? (of|on)|"
                    r"contribut(e|es|ed|ing) to|because of)\b", re.I)
TIMES_LIKELY = re.compile(r"\btimes (more|less|as) likely\b", re.I)
SIGNIFICANT = re.compile(r"\b(?<!not )(?<!no )(statistically )?significant(ly)?\b", re.I)
TREND = re.compile(r"\b(trend(ed|ing)? (toward|towards)|approach(ed|ing)? significance|marginally significant|borderline significan)", re.I)
DIGIT = re.compile(r"\d")
SUBSTANTIVE = 8  # words: a required part shorter than this is empty or a placeholder (Codex audit, finding 5)
REQUIRED = {"REPORT": ("summary", "keyFindings", "limitations", "conclusions"), "CHAPTER_FOUR": ("introduction", "summary")}

MEANINGS = {
    "n": "the number of records analysed", "mean": "the mean", "sd": "the standard deviation", "median": "the median", "q1": "the lower quartile",
    "q3": "the upper quartile", "min": "the smallest value", "max": "the largest value", "mean_low": "the lower 95% limit of the mean",
    "mean_high": "the upper 95% limit of the mean", "chi2": "the chi-square statistic", "df": "the degrees of freedom",
    "p": "the p-value, printed with its sign (\"= .043\" or \"< .001\"): write \"p ⟦N:...⟧\"", "fisher_p": "Fisher's exact p-value, printed with its sign",
    "cramers_v": "Cramér's V", "odds_ratio": "the odds ratio", "or_low": "the lower 95% limit of the odds ratio", "or_high": "the upper 95% limit of the odds ratio",
    "t": "the t statistic", "diff": "the difference in means (first group minus second)", "diff_low": "the lower 95% limit of the difference",
    "diff_high": "the upper 95% limit of the difference", "hedges_g": "Hedges' g", "mean1": "the first group's mean", "sd1": "the first group's standard deviation",
    "mean2": "the second group's mean", "sd2": "the second group's standard deviation", "n1": "the first group's records", "n2": "the second group's records",
    "median1": "the first group's median", "q1_1": "the first group's lower quartile", "q3_1": "the first group's upper quartile", "median2": "the second group's median",
    "q1_2": "the second group's lower quartile", "q3_2": "the second group's upper quartile", "w": "the W (rank-sum) statistic",
    "rank_biserial": "the rank-biserial correlation", "r": "the correlation coefficient", "r_low": "its lower 95% limit", "r_high": "its upper 95% limit",
}
COUNTS = {"n", "n1", "n2"}
TWO = {"cramers_v", "odds_ratio", "or_low", "or_high", "hedges_g", "rank_biserial", "r", "r_low", "r_high", "chi2", "t"}


def _safe(key: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "_", key).strip("_") or "x"


def prints(key: str, value: float) -> str:
    base = key.split(":")[0]
    if base in ("p", "fisher_p"):
        return p_text(value)
    if base in COUNTS or base == "count":
        return f"{int(round(value)):,}"
    if base in ("pct", "rowpct", "low", "high"):
        return f"{value:.1f}%"
    if base == "df":
        return f"{int(value)}" if float(value).is_integer() else f"{value:.1f}"
    if base == "w":
        return f"{value:,.1f}"
    if base in TWO:
        return f"{value:.2f}"
    return f"{value:,.2f}"


def _meaning(key: str, result: AnalysisResult) -> str:
    if ":" in key:
        kind, _, rest = key.partition(":")
        if "|" in rest:
            row, col = rest.split("|", 1)
            return {"count": f"the records with \"{row}\" and \"{col}\"", "rowpct": f"the percent of \"{row}\" records that are \"{col}\""}.get(kind, key)
        return {"count": f"the records answering \"{rest}\"", "pct": f"the percent answering \"{rest}\"", "low": f"the lower 95% limit of that percent (\"{rest}\")",
                "high": f"the upper 95% limit of that percent (\"{rest}\")"}.get(kind, key)
    return MEANINGS.get(key, key)


def tokens(analyses: list[AnalysisResult], general: dict[str, tuple[str, str]]) -> tuple[dict[str, tuple[str, str]], dict[str, str]]:
    """Every token available: path → (how it prints, what it means); and analysis id → its prefix (a1, a2 ...)."""
    out = dict(general)
    prefixes: dict[str, str] = {}
    for n, result in enumerate(analyses, start=1):
        prefix = f"a{n}"
        prefixes[result.id] = prefix
        used: set[str] = set()
        for key, value in result.statistics.items():
            if value is None or (isinstance(value, float) and (math.isnan(value) or math.isinf(value))):
                continue
            name = _safe(key)
            while name in used:
                name += "_"
            used.add(name)
            out[f"{prefix}.{name}"] = (prints(key, float(value)), _meaning(key, result))
    return out, prefixes


def fill(text: str, values: dict[str, tuple[str, str]]) -> str:
    return NUMBER_TOKEN.sub(lambda m: values[m.group(1)][0] if m.group(1) in values else m.group(0), text)


def _substantive(texts: Any) -> bool:
    return isinstance(texts, list) and any(isinstance(t, str) and len(NUMBER_TOKEN.sub("x", t).split()) >= SUBSTANTIVE for t in texts)


def problems(draft: dict[str, Any], analyses: list[AnalysisResult], prefixes: dict[str, str], values: dict[str, tuple[str, str]], alpha: float,
             mode: str = "REPORT") -> list[str]:
    """What code finds wrong with a draft, each as an instruction to the writer: every required part
    and every analysis's findings must have real content, then the wording rules."""
    issues: list[str] = []
    for part in REQUIRED.get(mode, ()):
        if not _substantive(draft.get(part)):
            issues.append(f"Write the {part}: it is empty or too short to say anything.")
    parts: list[tuple[str, str, AnalysisResult | None]] = []
    for name, value in draft.items():  # every narrative part (a report's or a chapter's), then the findings
        if name != "findings" and isinstance(value, list):
            parts += [(name, p, None) for p in value if isinstance(p, str)]
    by_id = {r.id: r for r in analyses}
    written = {f["id"] for f in draft.get("findings", [])}
    for missing in [r.id for r in analyses if r.id not in written]:
        issues.append(f"Write the findings for analysis {prefixes[missing]} ({by_id[missing].title}).")
    for finding in draft.get("findings", []):
        result = by_id.get(finding["id"])
        if result is None:
            issues.append(f"There is no analysis with id {finding['id']}: write findings only for the analyses given.")
            continue
        if not _substantive(finding.get("paragraphs")):
            issues.append(f"Write the findings for analysis {prefixes[result.id]} ({result.title}): they are empty or too short.")
        parts += [(f"findings for {prefixes[result.id]}", p, result) for p in finding.get("paragraphs", [])]
    for where, text, result in parts:
        unknown = sorted({m.group(1) for m in NUMBER_TOKEN.finditer(text)} - set(values))
        if unknown:
            issues.append(f"In the {where}: these tokens don't exist: {', '.join(unknown)}. Use only the tokens given.")
        bare = NUMBER_TOKEN.sub("", text)
        if DIGIT.search(bare):
            issues.append(f"In the {where}: a number is written as digits (\"{_around(bare, DIGIT)}\"). Every number must be a token.")
        if CAUSAL.search(bare):
            issues.append(f"In the {where}: \"{_around(bare, CAUSAL)}\" states a cause; these analyses show associations or differences only.")
        if TIMES_LIKELY.search(bare):
            issues.append(f"In the {where}: an odds ratio is not \"times more likely\"; describe it as odds.")
        if result is not None and result.statistics.get("p", 0.0) >= alpha:
            if SIGNIFICANT.search(bare) and not re.search(r"\b(not|no|nor|without)\b[^.]{0,40}significan", bare, re.I):
                issues.append(f"In the {where}: p is not below the significance level, so the result must not be called significant.")
            if TREND.search(bare):
                issues.append(f"In the {where}: a result above the significance level must not be described as a trend or near significance.")
    return list(dict.fromkeys(issues))


def _around(text: str, pattern: re.Pattern[str]) -> str:
    m = pattern.search(text)
    if m is None:
        return ""
    return text[max(0, m.start() - 30): m.end() + 30].strip()


def payload(title: str, purpose: str, dataset: dict[str, Any], alpha: float, analyses: list[AnalysisResult], prefixes: dict[str, str],
             values: dict[str, tuple[str, str]], objectives: list[str] | None = None, objective_of: dict[str, int] | None = None,
             chapter_three: list[dict[str, str]] | None = None, missing: list[int] | None = None, threshold: int = 5) -> dict[str, Any]:
    """What the writer sees: results and tokens, never rows."""
    from app.datalab.engine.disclosure import records_used

    items = []
    for result in analyses:
        prefix = prefixes[result.id]
        items.append({
            "id": result.id, "ref": prefix, "title": result.title, "question": result.record.question, "method": result.record.method, "why": result.record.why,
            "status": result.status, "warnings": result.warnings,
            "rowsUsed": records_used(result.record.rows_used, result.record.rows_available, threshold),
            "rowsAvailable": "hidden to protect privacy" if 0 < result.record.rows_available < threshold else result.record.rows_available,
            "leftOut": result.record.left_out, "coding": result.record.coding, "sentencesFromCode": result.sentences,
            "tokens": [{"token": f"⟦N:{k}⟧", "means": m, "prints": v} for k, (v, m) in values.items() if k.startswith(prefix + ".")],
            **({"objective": (objective_of or {}).get(result.id)} if objectives else {}),
        })
    general = [{"token": f"⟦N:{k}⟧", "means": m, "prints": v} for k, (v, m) in values.items() if "." not in k]
    out = {"title": title, "purpose": purpose, "dataset": dataset, "significanceLevel": alpha, "generalTokens": general, "analyses": items}
    if objectives:
        out["objectives"] = [{"number": n, "objective": text} for n, text in enumerate(objectives, start=1)]
        out["chapterThree"] = chapter_three or []
        out["missingObjectives"] = missing or []
    return out
