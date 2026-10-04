"""Charts, only where they help (decision 2026-10-03), drawn from the result's own (masked) table:
a count hidden in the table is never drawn either. Individual records are never plotted: a
relationship between two numbers is shown as binned density, with bins of fewer records than the
threshold left out. PNG at 200 dpi, PaperAid green, for the workspace, Word, PDF and Excel."""

import io
import math

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from app.datalab.models import AnalysisResult  # noqa: E402

GREEN, MID, LIGHT, GREY = "#0f633e", "#3f9a6c", "#9fd3b6", "#6b7280"
SERIES = [GREEN, "#7fb89a", "#c58b2c", "#4f6d8a", "#a35d6a", "#8a8f3c"]


def _figure(width: float = 6.4, height: float = 3.6):
    fig, ax = plt.subplots(figsize=(width, height), dpi=200)
    ax.spines[["top", "right"]].set_visible(False)
    ax.tick_params(colors="#374151", labelsize=8)
    for spine in ("left", "bottom"):
        ax.spines[spine].set_color("#9ca3af")
    return fig, ax


def _png(fig) -> bytes:
    buffer = io.BytesIO()
    fig.tight_layout()
    fig.savefig(buffer, format="png", dpi=200)
    plt.close(fig)
    return buffer.getvalue()


def _short(text: str, n: int = 28) -> str:
    return text if len(text) <= n else text[: n - 1] + "…"


def for_result(result: AnalysisResult, frame: pd.DataFrame | None = None, threshold: int = 5) -> bytes | None:
    """The chart that helps explain this result, or None when a table says it all."""
    if result.status == "NOT_ESTIMABLE" or not result.tables:
        return None
    kind, s = result.spec.kind, result.statistics
    if kind == "DESCRIBE" and "mean" in s and frame is not None:
        return _histogram(frame[result.spec.variables[0]].dropna().astype(float), result.title, threshold)
    if kind == "DESCRIBE":
        return _bars(result)
    if kind == "CROSSTAB":
        return _grouped(result)
    if kind == "COMPARE_TWO" and "mean1" in s:
        return _means(result)
    if kind == "CORRELATE" and frame is not None:
        data = frame[result.spec.variables].dropna().astype(float)
        return _density(data.iloc[:, 0], data.iloc[:, 1], result, threshold)
    return None


def _bars(result: AnalysisResult) -> bytes | None:
    table = result.tables[0]
    rows = [r for r in table.rows if r[0].text != "Total" and not r[2].suppressed and r[2].value is not None]
    if len(rows) < 2 or len(rows) > 15:
        return None
    labels = [_short(r[0].text) for r in rows]
    values = [float(r[2].value) for r in rows]  # type: ignore[arg-type]
    fig, ax = _figure(6.4, max(2.4, 0.38 * len(rows) + 1))
    ax.barh(labels[::-1], values[::-1], color=GREEN)
    ax.set_xlabel("Percent of records", fontsize=8)
    for i, v in enumerate(values[::-1]):
        ax.text(v + 0.5, i, f"{v:.1f}%", va="center", fontsize=7, color="#374151")
    ax.set_xlim(0, max(values) * 1.18)
    ax.set_title(result.title, fontsize=9, loc="left", color="#111827")
    return _png(fig)


def _histogram(x: pd.Series, title: str, threshold: int) -> bytes | None:
    if len(x) < 2 or x.nunique() < 3:
        return None
    bins = np.histogram_bin_edges(x, bins="sturges")
    counts, edges = np.histogram(x, bins=bins)
    shown = np.where((counts > 0) & (counts < threshold), 0, counts)  # bins with too few records are left out
    fig, ax = _figure()
    ax.bar(edges[:-1], shown, width=np.diff(edges), align="edge", color=GREEN, edgecolor="white", linewidth=0.6)
    ax.set_ylabel("Records", fontsize=8)
    ax.set_title(title, fontsize=9, loc="left", color="#111827")
    if (shown != counts).any():
        ax.text(0.99, 0.97, f"Bars of fewer than {threshold} records not shown", transform=ax.transAxes, ha="right", va="top", fontsize=6.5, color=GREY)
    return _png(fig)


def _grouped(result: AnalysisResult) -> bytes | None:
    table = result.tables[0]
    body = [r for r in table.rows if r[0].text != "Total"]
    columns = table.columns[1:-1]
    if len(body) > 10 or len(columns) > 6:
        return None
    fig, ax = _figure(6.4, max(2.6, 0.45 * len(body) + 1.2))
    height = 0.8 / len(columns)
    y = np.arange(len(body))
    for j, col in enumerate(columns):
        values = []
        for row in body:
            cell = row[j + 1]
            total = row[-1].value or 0
            values.append(0.0 if cell.suppressed or cell.value is None or not total else 100 * float(cell.value) / float(total))
        ax.barh(y + j * height, values, height=height, color=SERIES[j % len(SERIES)], label=_short(col, 20))
    ax.set_yticks(y + height * (len(columns) - 1) / 2, [_short(r[0].text) for r in body])
    ax.invert_yaxis()
    ax.set_xlabel("Percent of row", fontsize=8)
    ax.legend(fontsize=7, frameon=False, loc="lower right")
    ax.set_title(result.title, fontsize=9, loc="left", color="#111827")
    return _png(fig)


def _means(result: AnalysisResult) -> bytes | None:
    s = result.statistics
    if not all(k in s for k in ("mean1", "mean2", "sd1", "sd2", "n1", "n2")):
        return None
    labels = [_short(r[0].text, 20) for r in result.tables[0].rows]
    from scipy import stats as st

    means, half = [], []
    for m, sd, n in ((s["mean1"], s["sd1"], s["n1"]), (s["mean2"], s["sd2"], s["n2"])):
        means.append(m)
        half.append(st.t.ppf(0.975, n - 1) * sd / math.sqrt(n))
    fig, ax = _figure(5.2, 3.2)
    ax.errorbar(labels, means, yerr=half, fmt="o", color=GREEN, ecolor=MID, capsize=6, markersize=7, linewidth=1.6)
    ax.set_ylabel("Mean with 95% CI", fontsize=8)
    ax.set_xlim(-0.6, 1.6)
    ax.set_title(result.title, fontsize=9, loc="left", color="#111827")
    return _png(fig)


def _density(x: pd.Series, y: pd.Series, result: AnalysisResult, threshold: int) -> bytes | None:
    if len(x) < 2 * threshold:
        return None
    fig, ax = _figure(5.6, 4.0)
    hb = ax.hexbin(x, y, gridsize=18, mincnt=threshold, cmap="Greens", linewidths=0.2)
    cbar = fig.colorbar(hb, ax=ax)
    cbar.set_label("Records", fontsize=7)
    cbar.ax.tick_params(labelsize=7)
    names = result.spec.variables
    ax.set_xlabel(_short(names[0], 40), fontsize=8)
    ax.set_ylabel(_short(names[1], 40), fontsize=8)
    ax.set_title(result.title, fontsize=9, loc="left", color="#111827")
    ax.text(0.99, 0.01, f"Areas with fewer than {threshold} records not shown", transform=ax.transAxes, ha="right", va="bottom", fontsize=6.5, color=GREY)
    return _png(fig)
