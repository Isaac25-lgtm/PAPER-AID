"""The first analyses (decision 2026-10-03), every number computed here and checked against R:

- DESCRIBE: a number's mean (with its 95% interval), SD, median, quartiles and range; a category's
  counts and percentages, each with a Wilson 95% interval (R: prop.test(correct = FALSE)).
- CROSSTAB: counts and row percentages, Pearson's chi-square without continuity correction
  (R: chisq.test(correct = FALSE)), or Fisher's exact test for a 2×2 table with an expected count
  below 5 (R: fisher.test), which answers the same question; Cramér's V, and for a 2×2 table the
  odds ratio with Woolf's 95% interval.
- COMPARE_TWO: chosen by the question, never swapped on a failed check. MEANS: Welch's t-test
  (R: t.test) with the difference in means, its 95% interval and Hedges' g. DISTRIBUTIONS: the
  Wilcoxon rank-sum (Mann–Whitney) test (R: wilcox.test, exact below 50 per group without ties,
  otherwise normal with continuity correction) with the medians and the rank-biserial correlation.
- CORRELATE: Pearson's r with its Fisher-z 95% interval (R: cor.test), or Spearman's rho with the
  t approximation (R: cor.test(method = "spearman", exact = FALSE)).

Missing values are left out per analysis (complete cases), and the record says how many and why."""

import math
import platform
import secrets
from collections.abc import Callable

import numpy as np
import pandas as pd
import scipy
from scipy import stats as st

from app.datalab.engine import disclosure
from app.datalab.models import AnalysisResult, AnalysisSpec, CalculationRecord, Cell, Estimate, ResultTable, Variable


class Context:
    """What every analysis needs: the data version (already limited to its filter's records), the
    variables as the researcher set them, the significance level, the disclosure threshold, the
    cleaning applied and, with a filter, how many records there were before it and the filter in words."""

    def __init__(self, frame: pd.DataFrame, variables: dict[str, Variable], version: int, alpha: float = 0.05, threshold: int = 5,
                 cleaning: list[str] | None = None, available: int | None = None, population: str = "", notes: list[str] | None = None):
        self.frame, self.variables, self.version, self.alpha, self.threshold = frame, variables, version, alpha, threshold
        self.cleaning = cleaning or []
        self.available = len(frame) if available is None else available
        self.population = population
        self.notes = notes or []
        self.used: pd.Index | None = None  # the rows the analysis actually used: its filter's, less those with a missing value or no place


def software() -> list[str]:
    return [f"Python {platform.python_version()}", f"pandas {pd.__version__}", f"NumPy {np.__version__}", f"SciPy {scipy.__version__}"]


NEEDS = {"DESCRIBE": 1, "CROSSTAB": 2, "COMPARE_TWO": 2, "CORRELATE": 2}


def run(ctx: Context, spec: AnalysisSpec) -> AnalysisResult:
    for name in spec.variables:
        var = ctx.variables.get(name)
        if var is None:
            raise ValueError(f"unknown variable {name}")
    if len(spec.variables) != NEEDS[spec.kind]:
        raise ValueError(f"{spec.kind} needs {NEEDS[spec.kind]} variables")
    handlers: dict[str, Callable[[Context, AnalysisSpec], AnalysisResult]] = {
        "DESCRIBE": describe, "CROSSTAB": crosstab, "COMPARE_TWO": compare_two, "CORRELATE": correlate}
    return labelled(ctx, finite(ctx, spec, handlers[spec.kind](ctx, spec)))


def labelled(ctx: Context, result: AnalysisResult) -> AnalysisResult:
    """A filtered result says whose records it describes, in its title and every table's."""
    if not ctx.population:
        return result
    suffix = f" ({ctx.population[:90]}{'…' if len(ctx.population) > 90 else ''})"
    result.title += suffix
    for table in result.tables:
        table.title += suffix
    return result


def finite(ctx: Context, spec: AnalysisSpec, result: AnalysisResult) -> AnalysisResult:
    """A result with a number that isn't finite (every value the same, a zero spread) is not
    estimable, with the reason, never VALID with an infinite statistic (Codex audit, finding 9)."""
    numbers = list(result.statistics.values()) + [x for e in result.estimates for x in (e.value, e.low, e.high) if x is not None]
    if result.status == "NOT_ESTIMABLE" or all(math.isfinite(float(x)) for x in numbers):
        return result
    return _not_estimable(ctx, spec, result.title, "These values can't give a result: for example, every record in a group has the same value, so there is no "
                          "spread to compare.", result.record.rows_used, result.record.left_out)


# --- helpers -------------------------------------------------------------------------------------


def _id() -> str:
    return f"an_{secrets.token_hex(4)}"


def _fmt(x: float, digits: int = 2) -> str:
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return "–"
    return f"{x:,.{digits}f}"


def p_text(p: float) -> str:
    """APA style: exact to three decimals, "< .001" below that, without a leading zero."""
    if p < 0.001:
        return "< .001"
    return "= " + f"{p:.3f}".lstrip("0")


def _complete(ctx: Context, names: list[str]) -> tuple[pd.DataFrame, list[str]]:
    """The rows with a value for every variable, and why the others were left out."""
    frame = ctx.frame[names]
    keep = frame.notna().all(axis=1)
    left_out = []
    for name in names:
        n = int(ctx.frame[name].isna().sum())
        if n:
            shown = ("A protected number of" if disclosure.count_hidden(n, len(ctx.frame), ctx.threshold)
                     else disclosure.few(n, ctx.threshold).capitalize())
            left_out.append(f"{shown} records have no value for \"{ctx.variables[name].title()}\".")
    ctx.used = frame.index[keep]
    return frame[keep], left_out


def _record(ctx: Context, spec: AnalysisSpec, method: str, why: str, used: int, left_out: list[str], coding: list[str] | None = None,
            assumptions: list[str] | None = None) -> CalculationRecord:
    return CalculationRecord(question=spec.question or _default_question(ctx, spec), method=method, why=why, dataset_version=ctx.version,
                             cleaning=list(ctx.cleaning), rows_used=used, rows_available=ctx.available, left_out=[*ctx.notes, *left_out], coding=coding or [],
                             alpha=ctx.alpha, assumptions=assumptions or [], software=software(), filters=ctx.population)


def _default_question(ctx: Context, spec: AnalysisSpec) -> str:
    names = [ctx.variables[n].title() for n in spec.variables]
    among = f", among records where {ctx.population}" if ctx.population else ""
    if spec.kind == "DESCRIBE":
        return f"What does \"{names[0]}\" look like{among}?"
    if spec.kind == "CROSSTAB":
        return f"Is \"{names[0]}\" associated with \"{names[1]}\"{among}?"
    if spec.kind == "COMPARE_TWO":
        return f"Does \"{names[0]}\" differ between the groups of \"{names[1]}\"{among}?"
    if spec.kind == "MAP":
        areas = {"DISTRICT": "districts", "SUBCOUNTY": "subcounties", "SUBREGION": "sub-regions", "REGION": "regions"}[spec.level]
        if spec.data_form == "TOTALS":
            total = ctx.variables[spec.total].title() if spec.total in ctx.variables else "the total"
            measure = f"\"{total}\" per 1,000" if spec.method == "RATE" else f"\"{total}\""
        else:
            measure = f"the average \"{names[1]}\"" if len(names) > 1 else "the number of records"
        return f"How does {measure} vary across {areas}{among}?"
    return f"Do \"{names[0]}\" and \"{names[1]}\" go together{among}?"


def _not_estimable(ctx: Context, spec: AnalysisSpec, title: str, reason: str, used: int = 0, left_out: list[str] | None = None) -> AnalysisResult:
    return AnalysisResult(id=_id(), spec=spec, status="NOT_ESTIMABLE", title=title, warnings=[reason],
                          record=_record(ctx, spec, "Not calculated", reason, used, left_out or []))


def wilson(count: int, n: int, z: float = 1.959963984540054) -> tuple[float, float]:
    """Wilson score interval for a proportion, without continuity correction."""
    if n == 0:
        return (math.nan, math.nan)
    p = count / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return (centre - half, centre + half)


def _text_values(series: pd.Series) -> pd.Series:
    return series.astype(str).str.strip() if series.dtype != "float64" else series.map(lambda v: f"{v:g}")


# --- DESCRIBE ------------------------------------------------------------------------------------


def describe(ctx: Context, spec: AnalysisSpec) -> AnalysisResult:
    var = ctx.variables[spec.variables[0]]
    data, left_out = _complete(ctx, [var.name])
    x = data[var.name]
    title = f"Summary of {var.title()}"
    if len(x) == 0:
        return _not_estimable(ctx, spec, title, f"\"{var.title()}\" has no values to describe.", 0, left_out)
    if var.kind == "NUMERIC" and var.stored == "number":
        return _describe_number(ctx, spec, var, x.astype(float), left_out, title)
    return _describe_categories(ctx, spec, var, _text_values(x), left_out, title)


def _describe_number(ctx: Context, spec: AnalysisSpec, var: Variable, x: pd.Series, left_out: list[str], title: str) -> AnalysisResult:
    n = len(x)
    if n < ctx.threshold:
        return _not_estimable(ctx, spec, title, f"Fewer than {ctx.threshold} records have a value for \"{var.title()}\", too few to summarise without identifying people.",
                              n, left_out)
    mean, sd = float(x.mean()), float(x.std(ddof=1)) if n > 1 else math.nan
    q1, median, q3 = (float(x.quantile(q)) for q in (0.25, 0.5, 0.75))
    se = sd / math.sqrt(n)
    t = st.t.ppf(0.975, n - 1)
    low, high = mean - t * se, mean + t * se
    stats = {"n": n, "mean": mean, "sd": sd, "median": median, "q1": q1, "q3": q3, "min": float(x.min()), "max": float(x.max()), "mean_low": low, "mean_high": high}
    rows = [[Cell(text="Records"), Cell(text=f"{n:,}", value=n)], [Cell(text="Mean (95% CI)"), Cell(text=f"{_fmt(mean)} ({_fmt(low)} to {_fmt(high)})", value=mean)],
            [Cell(text="Standard deviation"), Cell(text=_fmt(sd), value=sd)], [Cell(text="Median (IQR)"), Cell(text=f"{_fmt(median)} ({_fmt(q1)} to {_fmt(q3)})", value=median)],
            [Cell(text="Range"), Cell(text=f"{_fmt(stats['min'])} to {_fmt(stats['max'])}", value=None)]]
    table = ResultTable(title=title, columns=["Statistic", var.title()], rows=rows)
    skew = float(st.skew(x, bias=False)) if n > 2 else 0.0
    assumptions = [f"Skewness {skew:.2f}" + ("; the distribution is noticeably skewed, so the median and IQR describe a typical value better than the mean." if abs(skew) > 1 else ".")]
    sentences = [f"The mean {var.title()} was {_fmt(mean)} (SD {_fmt(sd)}; 95% CI {_fmt(low)} to {_fmt(high)}), and the median was {_fmt(median)} (IQR {_fmt(q1)} to {_fmt(q3)}), "
                 f"from {n:,} records."]
    if abs(skew) > 1:
        sentences.append("The values are skewed, so the median is the better summary of a typical value.")
    record = _record(ctx, spec, "Mean with a t-based 95% confidence interval; median and quartiles (R's default, type 7)",
                     "A summary of one numeric variable.", n, left_out, assumptions=assumptions)
    return AnalysisResult(id=_id(), spec=spec, status="VALID", title=title, tables=[table], statistics=stats,
                          estimates=[Estimate(name="Mean", value=mean, low=low, high=high)], sentences=sentences, record=record)


def _describe_categories(ctx: Context, spec: AnalysisSpec, var: Variable, x: pd.Series, left_out: list[str], title: str) -> AnalysisResult:
    counts = x.value_counts()
    order = _level_order(var, list(counts.index))
    values = [int(counts.get(level, 0)) for level in order]
    n = int(sum(values))
    if n < ctx.threshold:
        return _not_estimable(ctx, spec, title, f"Fewer than {ctx.threshold} records have a value for \"{var.title()}\", too few to show without identifying people.",
                              n, left_out)
    hidden = list(disclosure.protect(np.array(values), ctx.threshold, row_totals=True, column_totals=False).cells[0])
    # hidden categories after the shown ones, by name: in the most-common-first order a hidden row's place would hint at its count
    keep = sorted(range(len(order)), key=lambda i: (bool(hidden[i]), order[i] if hidden[i] else "", i))
    order, values, hidden = [order[i] for i in keep], [values[i] for i in keep], [hidden[i] for i in keep]
    rows, stats = [], {"n": n}
    for i, (level, count) in enumerate(zip(order, values, strict=True)):
        low, high = wilson(count, n)
        pct = 100 * count / n
        if hidden[i]:
            rows.append([Cell(text=level), Cell(text=disclosure.HIDDEN, count=True, suppressed=True), Cell(text=disclosure.HIDDEN, suppressed=True),
                         Cell(text=disclosure.HIDDEN, suppressed=True)])
            continue
        rows.append([Cell(text=level), Cell(text=f"{count:,}", value=count, count=True), Cell(text=f"{pct:.1f}%", value=pct),
                     Cell(text=f"{100 * low:.1f}% to {100 * high:.1f}%", value=None)])
        stats[f"count:{level}"], stats[f"pct:{level}"], stats[f"low:{level}"], stats[f"high:{level}"] = count, pct, 100 * low, 100 * high
    rows.append([Cell(text="Total"), Cell(text=f"{n:,}", value=n, count=True), Cell(text="100.0%", value=100.0), Cell(text="")])
    notes = [disclosure.note(ctx.threshold)] if any(hidden) else []
    table = ResultTable(title=title, columns=[var.title(), "Count", "Percent", "95% CI"], rows=rows, notes=notes)
    shown_levels = [(level, values[i]) for i, level in enumerate(order) if not hidden[i]]
    sentences = []
    if shown_levels:
        top, top_n = max(shown_levels, key=lambda t: t[1])
        sentences.append(f"Of {n:,} records, the most common {var.title()} was \"{top}\" ({top_n:,}; {100 * top_n / n:.1f}%).")
    record = _record(ctx, spec, "Counts and percentages of valid answers, with Wilson 95% confidence intervals", "A summary of one categorical variable.", n, left_out)
    return AnalysisResult(id=_id(), spec=spec, status="VALID", title=title, tables=[table], statistics=stats, sentences=sentences, record=record)


def _level_order(var: Variable, present: list[str]) -> list[str]:
    """Categories in the order the profile lists them (most common first), then any others."""
    known = [lv.value for lv in var.levels if lv.value in present]
    return known + sorted(v for v in present if v not in known)


# --- CROSSTAB ------------------------------------------------------------------------------------


def crosstab(ctx: Context, spec: AnalysisSpec) -> AnalysisResult:
    if len(spec.variables) != 2:
        raise ValueError("a cross-tabulation needs two variables")
    rv, cv = (ctx.variables[n] for n in spec.variables)
    title = f"{rv.title()} by {cv.title()}"
    data, left_out = _complete(ctx, [rv.name, cv.name])
    rows_x, cols_x = _text_values(data[rv.name]), _text_values(data[cv.name])
    table = pd.crosstab(rows_x, cols_x)
    table = table.loc[_level_order(rv, list(table.index)), _level_order(cv, list(table.columns))]
    if table.shape[0] < 2 or table.shape[1] < 2:
        return _not_estimable(ctx, spec, title, "Each variable needs at least two categories with records to be compared.", len(data), left_out)
    if table.shape[0] > 20 or table.shape[1] > 20:
        return _not_estimable(ctx, spec, title, "One of these variables has more than 20 categories; group them first.", len(data), left_out)
    observed = table.to_numpy()
    n = int(observed.sum())
    if n < ctx.threshold:
        return _not_estimable(ctx, spec, title, f"Fewer than {ctx.threshold} records have values for both variables, too few to show without identifying people.",
                              n, left_out)
    chi2, p, dof, expected = st.chi2_contingency(observed, correction=False)
    small = float((expected < 5).mean())
    warnings: list[str] = []
    assumptions = [f"{small * 100:.0f}% of expected counts are below 5 (smallest {expected.min():.2f})."]
    stats: dict[str, float] = {"n": n, "chi2": float(chi2), "df": float(dof), "p": float(p)}
    method = "Pearson's chi-square test of independence (no continuity correction)"
    why = "Both variables are categories; the question is whether they are associated."
    k = min(observed.shape) - 1
    v = math.sqrt(chi2 / (n * k)) if n and k else math.nan
    stats["cramers_v"] = v
    estimates = [Estimate(name="Cramér's V", value=v, note="0 = no association, 1 = complete association")]
    test_line = f"χ²({dof}, N = {n:,}) = {chi2:.2f}, p {p_text(p)}"
    status = "VALID"
    if observed.shape == (2, 2):
        if (expected < 5).any():
            odds, p_exact = st.fisher_exact(observed)
            stats["p"], stats["fisher_p"] = float(p_exact), float(p_exact)
            method = "Fisher's exact test (two-sided)"
            why = "A 2×2 table with an expected count below 5, where the chi-square approximation is unreliable; the exact test answers the same question."
            test_line = f"Fisher's exact test, p {p_text(p_exact)}"
        a, b, c, d = (float(x) for x in observed.ravel())
        corrected = 0 in (a, b, c, d)
        if corrected:
            a, b, c, d = a + 0.5, b + 0.5, c + 0.5, d + 0.5
        odds_ratio = (a * d) / (b * c)
        se = math.sqrt(1 / a + 1 / b + 1 / c + 1 / d)
        low, high = math.exp(math.log(odds_ratio) - 1.959963984540054 * se), math.exp(math.log(odds_ratio) + 1.959963984540054 * se)
        stats.update({"odds_ratio": odds_ratio, "or_low": low, "or_high": high})
        estimates.append(Estimate(name="Odds ratio", value=odds_ratio, low=low, high=high,
                                  note=f"Odds of \"{table.columns[0]}\" in \"{table.index[0]}\" relative to \"{table.index[1]}\"" + (" (0.5 added to each cell because one was zero)" if corrected else "")))
    elif small > 0.2:
        status = "VALID_WITH_WARNINGS"
        warnings.append("More than a fifth of the expected counts are below 5, so the chi-square p-value may be unreliable. Grouping small categories together "
                        "would make it dependable.")
    guard = disclosure.protect(observed, ctx.threshold)
    hidden = guard.cells
    if guard.any and observed.shape == (2, 2):
        # In a 2×2 table the test's numbers (chi-square, Cramér's V, the odds ratio) with the totals
        # would let a hidden count be worked out: they are withheld, and so is anything built on them.
        for key in ("chi2", "df", "p", "fisher_p", "cramers_v", "odds_ratio", "or_low", "or_high"):
            stats.pop(key, None)
        estimates = []
        status = "VALID_WITH_WARNINGS"
        warnings.append("The test results aren't shown: this table has hidden counts, and in a table of two rows and two columns the test's numbers would "
                        "reveal them. Grouping or collecting more records would let it be tested.")
    out_rows = []
    row_totals = observed.sum(axis=1)
    for i, level in enumerate(table.index):
        cells = [Cell(text=str(level))]
        for j in range(observed.shape[1]):
            count = int(observed[i, j])
            if hidden[i, j]:
                cells.append(Cell(text=disclosure.HIDDEN, count=True, suppressed=True))
            elif guard.rows[i]:  # a percentage of a hidden total would reveal it: the count alone
                cells.append(Cell(text=f"{count:,}", value=count, count=True))
                stats[f"count:{level}|{table.columns[j]}"] = count
            else:
                pct = 100 * count / row_totals[i] if row_totals[i] else 0.0
                cells.append(Cell(text=f"{count:,} ({pct:.1f}%)", value=count, count=True))
                stats[f"count:{level}|{table.columns[j]}"], stats[f"rowpct:{level}|{table.columns[j]}"] = count, pct
        cells.append(Cell(text=disclosure.HIDDEN, count=True, suppressed=True) if guard.rows[i]
                     else Cell(text=f"{int(row_totals[i]):,}", value=float(row_totals[i]), count=True))
        out_rows.append(cells)
    col_totals = observed.sum(axis=0)
    out_rows.append([Cell(text="Total"),
                     *[Cell(text=disclosure.HIDDEN, count=True, suppressed=True) if guard.columns[j] else Cell(text=f"{int(t):,}", value=float(t), count=True)
                       for j, t in enumerate(col_totals)],
                     Cell(text=disclosure.HIDDEN, count=True, suppressed=True) if guard.total else Cell(text=f"{n:,}", value=n, count=True)])
    notes = ["Percentages are of each row's total."]
    if guard.any:
        notes.append(disclosure.note(ctx.threshold))
    result_table = ResultTable(title=title, columns=[rv.title(), *[str(c) for c in table.columns], "Total"], rows=out_rows, notes=notes)
    sentences = []
    if "p" in stats:
        significant = stats["p"] < ctx.alpha
        sentences.append(f"{test_line}. " + (f"\"{rv.title()}\" and \"{cv.title()}\" were associated" if significant else
                                             f"There was no statistically significant association between \"{rv.title()}\" and \"{cv.title()}\"")
                         + f" (Cramér's V = {v:.2f}).")
    if "odds_ratio" in stats:
        sentences.append(f"The odds ratio was {stats['odds_ratio']:.2f} (95% CI {stats['or_low']:.2f} to {stats['or_high']:.2f}).")
    sentences.append("This shows an association, not that one causes the other.")
    coding = [f"Rows: \"{rv.title()}\" ({', '.join(map(str, table.index))}); columns: \"{cv.title()}\" ({', '.join(map(str, table.columns))})."]
    record = _record(ctx, spec, method, why, n, left_out, coding, assumptions)
    return AnalysisResult(id=_id(), spec=spec, status=status, title=title, tables=[result_table], statistics=stats, estimates=estimates, sentences=sentences,
                          warnings=warnings, record=record)


# --- COMPARE_TWO ---------------------------------------------------------------------------------


def compare_two(ctx: Context, spec: AnalysisSpec) -> AnalysisResult:
    if len(spec.variables) != 2:
        raise ValueError("a comparison needs an outcome and a grouping variable")
    yv, gv = (ctx.variables[n] for n in spec.variables)
    title = f"{yv.title()} by {gv.title()}"
    if yv.stored != "number":
        return _not_estimable(ctx, spec, title, f"\"{yv.title()}\" isn't stored as numbers, so its values can't be compared this way.")
    data, left_out = _complete(ctx, [yv.name, gv.name])
    groups_x = _text_values(data[gv.name])
    levels = spec.groups or _level_order(gv, list(groups_x.unique()))
    if len(levels) != 2:
        return _not_estimable(ctx, spec, title, f"\"{gv.title()}\" has {len(levels)} groups; choose the two to compare.", len(data), left_out)
    a = data.loc[groups_x == levels[0], yv.name].astype(float)
    b = data.loc[groups_x == levels[1], yv.name].astype(float)
    if spec.groups and len(groups_x.unique()) > 2:
        left_out.append(f"{disclosure.few(int((~groups_x.isin(levels)).sum()), ctx.threshold).capitalize()} records in other groups of \"{gv.title()}\" were not "
                        "part of this comparison.")
    used = len(a) + len(b)
    if min(len(a), len(b)) < ctx.threshold:
        return _not_estimable(ctx, spec, title, f"Each group needs at least {ctx.threshold} records to be compared without identifying people.", used, left_out)
    method_kind = spec.method or "MEANS"
    assumptions = []
    for level, values in ((levels[0], a), (levels[1], b)):
        if 3 <= len(values) <= 5000:
            w, p_norm = st.shapiro(values)
            assumptions.append(f"\"{level}\": Shapiro–Wilk W = {w:.3f}, p {p_text(p_norm)} (n = {len(values):,}).")
    coding = [f"\"{gv.title()}\": \"{levels[0]}\" compared with \"{levels[1]}\" (differences are {levels[0]} minus {levels[1]})."]
    warnings: list[str] = []
    stats: dict[str, float] = {"n1": len(a), "n2": len(b)}
    if method_kind == "MEANS":
        res = st.ttest_ind(a, b, equal_var=False)
        v1, v2 = a.var(ddof=1) / len(a), b.var(ddof=1) / len(b)
        df = (v1 + v2) ** 2 / (v1**2 / (len(a) - 1) + v2**2 / (len(b) - 1))
        diff = float(a.mean() - b.mean())
        se = math.sqrt(v1 + v2)
        tcrit = st.t.ppf(0.975, df)
        low, high = diff - tcrit * se, diff + tcrit * se
        pooled = math.sqrt(((len(a) - 1) * a.var(ddof=1) + (len(b) - 1) * b.var(ddof=1)) / (len(a) + len(b) - 2))
        d = diff / pooled if pooled else math.nan
        correction = 1 - 3 / (4 * (len(a) + len(b)) - 9)
        g = d * correction
        g_se = math.sqrt((len(a) + len(b)) / (len(a) * len(b)) + g * g / (2 * (len(a) + len(b))))
        stats.update({"mean1": float(a.mean()), "sd1": float(a.std(ddof=1)), "mean2": float(b.mean()), "sd2": float(b.std(ddof=1)), "t": float(res.statistic), "df": float(df),
                      "p": float(res.pvalue), "diff": diff, "diff_low": low, "diff_high": high, "hedges_g": g})
        estimates = [Estimate(name="Difference in means", value=diff, low=low, high=high), Estimate(name="Hedges' g", value=g, low=g - 1.959963984540054 * g_se,
                                                                                                  high=g + 1.959963984540054 * g_se, note="approximate interval")]
        method = "Welch's t-test (unequal variances), two-sided"
        why = "The question is whether the average (mean) differs between two independent groups; Welch's test does not assume equal variances."
        small_skewed = [lvl for lvl, vals in ((levels[0], a), (levels[1], b)) if len(vals) < 30 and 3 <= len(vals) and st.shapiro(vals)[1] < 0.05]
        if small_skewed:
            warnings.append("A group with fewer than 30 records doesn't look normally distributed, so the t-test's p-value may be inaccurate. If the question is about typical "
                            "values rather than averages, comparing the distributions answers that instead.")
        rows = [[Cell(text=str(levels[0])), Cell(text=f"{len(a):,}", value=len(a)), Cell(text=f"{_fmt(stats['mean1'])} ({_fmt(stats['sd1'])})", value=stats["mean1"])],
                [Cell(text=str(levels[1])), Cell(text=f"{len(b):,}", value=len(b)), Cell(text=f"{_fmt(stats['mean2'])} ({_fmt(stats['sd2'])})", value=stats["mean2"])]]
        table = ResultTable(title=title, columns=[gv.title(), "Records", f"Mean (SD) of {yv.title()}"], rows=rows,
                            notes=[f"Difference {_fmt(diff)} (95% CI {_fmt(low)} to {_fmt(high)}); t({df:.1f}) = {res.statistic:.2f}, p {p_text(res.pvalue)}; Hedges' g = {g:.2f}."])
        significant = res.pvalue < ctx.alpha
        sentences = [f"The mean {yv.title()} was {_fmt(stats['mean1'])} in \"{levels[0]}\" and {_fmt(stats['mean2'])} in \"{levels[1]}\", a difference of {_fmt(diff)} "
                     f"(95% CI {_fmt(low)} to {_fmt(high)}; t({df:.1f}) = {res.statistic:.2f}, p {p_text(res.pvalue)}; Hedges' g = {g:.2f})."
                     + ("" if significant else " The difference was not statistically significant.")]
    else:
        ties = len(pd.concat([a, b]).unique()) < used
        exact = not ties and len(a) < 50 and len(b) < 50
        res = st.mannwhitneyu(a, b, alternative="two-sided", use_continuity=True, method="exact" if exact else "asymptotic")
        u = float(res.statistic)
        r = 2 * u / (len(a) * len(b)) - 1
        stats.update({"median1": float(a.median()), "q1_1": float(a.quantile(0.25)), "q3_1": float(a.quantile(0.75)), "median2": float(b.median()),
                      "q1_2": float(b.quantile(0.25)), "q3_2": float(b.quantile(0.75)), "w": u, "p": float(res.pvalue), "rank_biserial": r})
        estimates = [Estimate(name="Rank-biserial correlation", value=r, note=f"positive: values tend to be higher in \"{levels[0]}\"")]
        method = "Wilcoxon rank-sum (Mann–Whitney) test, two-sided" + (" (exact)" if exact else " (normal approximation with continuity correction)")
        why = "The question is whether values tend to be higher in one of two independent groups, comparing whole distributions rather than means."
        rows = [[Cell(text=str(levels[0])), Cell(text=f"{len(a):,}", value=len(a)), Cell(text=f"{_fmt(stats['median1'])} ({_fmt(stats['q1_1'])} to {_fmt(stats['q3_1'])})",
                                                                                  value=stats["median1"])],
                [Cell(text=str(levels[1])), Cell(text=f"{len(b):,}", value=len(b)), Cell(text=f"{_fmt(stats['median2'])} ({_fmt(stats['q1_2'])} to {_fmt(stats['q3_2'])})",
                                                                                  value=stats["median2"])]]
        table = ResultTable(title=title, columns=[gv.title(), "Records", f"Median (IQR) of {yv.title()}"], rows=rows,
                            notes=[f"W = {u:,.1f}, p {p_text(res.pvalue)}; rank-biserial correlation = {r:.2f}."])
        significant = res.pvalue < ctx.alpha
        sentences = [f"The median {yv.title()} was {_fmt(stats['median1'])} in \"{levels[0]}\" and {_fmt(stats['median2'])} in \"{levels[1]}\" "
                     f"(W = {u:,.1f}, p {p_text(res.pvalue)}; rank-biserial correlation = {r:.2f})."
                     + (" Values tended to differ between the groups." if significant else " The difference was not statistically significant.")]
    sentences.append("This compares the groups; it does not show what caused any difference.")
    record = _record(ctx, spec, method, why, used, left_out, coding, assumptions)
    return AnalysisResult(id=_id(), spec=spec, status="VALID_WITH_WARNINGS" if warnings else "VALID", title=title, tables=[table], statistics=stats,
                          estimates=estimates, sentences=sentences, warnings=warnings, record=record)


# --- CORRELATE -----------------------------------------------------------------------------------


def correlate(ctx: Context, spec: AnalysisSpec) -> AnalysisResult:
    if len(spec.variables) != 2:
        raise ValueError("a correlation needs two variables")
    xv, yv = (ctx.variables[n] for n in spec.variables)
    title = f"{xv.title()} and {yv.title()}"
    if xv.stored != "number" or yv.stored != "number":
        return _not_estimable(ctx, spec, title, "Both variables need to be numbers to be correlated.")
    data, left_out = _complete(ctx, [xv.name, yv.name])
    n = len(data)
    if n < max(ctx.threshold, 4):
        return _not_estimable(ctx, spec, title, f"At least {max(ctx.threshold, 4)} records need values for both variables.", n, left_out)
    x, y = data[xv.name].astype(float), data[yv.name].astype(float)
    if x.nunique() < 2 or y.nunique() < 2:
        return _not_estimable(ctx, spec, title, "One of the variables has the same value in every record, so it can't vary with the other.", n, left_out)
    method_kind = spec.method or "PEARSON"
    z = 1.959963984540054
    if method_kind == "PEARSON":
        r, p = st.pearsonr(x, y)
        if abs(r) > 1 - 1e-12:  # a perfect straight line: the interval is the value itself
            r = 1.0 if r > 0 else -1.0
            low = high = r
        else:
            fz, se = math.atanh(r), 1 / math.sqrt(n - 3)
            low, high = math.tanh(fz - z * se), math.tanh(fz + z * se)
        name, symbol = "Pearson's r", "r"
        method = "Pearson's product-moment correlation, two-sided, with a Fisher-z 95% confidence interval"
        why = "The question is whether the two measures rise and fall together in a straight line."
        note = ""
    else:
        r, p = st.spearmanr(x, y)
        if abs(r) > 1 - 1e-12:
            r = 1.0 if r > 0 else -1.0
            low = high = r
        else:
            se = math.sqrt((1 + r * r / 2) / (n - 3))
            low, high = math.tanh(math.atanh(r) - z * se), math.tanh(math.atanh(r) + z * se)
        name, symbol = "Spearman's rho", "rho"
        method = "Spearman's rank correlation, two-sided (t approximation), with an approximate (Bonett–Wright) 95% confidence interval"
        why = "The question is whether higher values of one tend to go with higher (or lower) values of the other, not necessarily in a straight line."
        note = "approximate interval"
    r, p = float(r), float(p)
    stats = {"n": n, "r": r, "p": p, "r_low": low, "r_high": high}
    strength = "very weak" if abs(r) < 0.1 else "weak" if abs(r) < 0.3 else "moderate" if abs(r) < 0.5 else "strong"
    direction = "positive" if r > 0 else "negative"
    significant = p < ctx.alpha
    sentences = [f"There was a {strength} {direction} correlation between \"{xv.title()}\" and \"{yv.title()}\" ({symbol} = {r:.2f}, 95% CI {low:.2f} to {high:.2f}, "
                 f"p {p_text(p)}, n = {n:,})." + ("" if significant else " It was not statistically significant."), "A correlation does not show that one causes the other."]
    table = ResultTable(title=title, columns=["Statistic", "Value"], rows=[[Cell(text="Records"), Cell(text=f"{n:,}", value=n)],
                                                                          [Cell(text=name), Cell(text=f"{r:.2f}", value=r)],
                                                                          [Cell(text="95% CI"), Cell(text=f"{low:.2f} to {high:.2f}")],
                                                                          [Cell(text="p"), Cell(text=p_text(p).replace("= ", ""), value=p)]])
    record = _record(ctx, spec, method, why, n, left_out)
    return AnalysisResult(id=_id(), spec=spec, status="VALID", title=title, tables=[table], statistics=stats,
                          estimates=[Estimate(name=name, value=r, low=low, high=high, note=note)], sentences=sentences, record=record)
