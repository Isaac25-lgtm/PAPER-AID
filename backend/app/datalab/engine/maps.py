"""Uganda maps (owner decisions 2026-10-03 and 2026-10-04), drawn by code from UBOS's layers
(app/datalab/geo, built by scripts/build_uganda_districts.py; released layer files never change).

Levels: districts (2020), subcounties (2021, always named with their district: names repeat), and
the 15 sub-regions and 4 regions made from districts. A dataset's place names are matched exactly
after tidying (case, "District", hyphens and spaces) and through a list of known spellings; a near
miss is only suggested, never applied, until the researcher confirms it; unmatched records are
always reported, never dropped silently.

Data comes as records (one row per person or event: counted, or a number averaged) or as totals
(one row per area already holding its count: mapped as the count, or as a rate per 1,000 of a
population column). Every count goes through the same protection as every table: a small one is
hidden, with any that would reveal it, in the table and on the map alike (hatched, never coloured),
and an average or rate is hidden with its count. The legend's classes come only from what is shown.

A filter or a region narrows what is mapped and zooms the map to it, with the neighbouring areas in
grey for context. Every map carries a title, a legend, a north arrow, a scale bar measured in a
projected system (UTM 36N), the boundaries' source and year, and a note that boundaries imply no
position on any border."""

import difflib
import hashlib
import io
import json
import re
import secrets
from collections.abc import Callable
from functools import cache
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.patches import Patch  # noqa: E402

from app.datalab.engine import disclosure  # noqa: E402
from app.datalab.engine.stats import Context, _complete, _record, _text_values, labelled  # noqa: E402
from app.datalab.models import AnalysisResult, AnalysisSpec, Cell, ResultTable  # noqa: E402

GEO = Path(__file__).resolve().parents[1] / "geo"
LAYER = "uganda_districts_2020"
SUBCOUNTY_LAYER = "uganda_subcounties_2021"
REGIONS = ("Central", "Eastern", "Northern", "Western")
UTM36N = 32636
# Alternative spellings of the same district in common use, mapped to the layer's official names. A city
# (Fort Portal, Gulu City ...) is never mapped to a district here: the researcher confirms any such choice.
ALIASES = {"LUWERO": "LUWEERO", "SEMBABULE": "SSEMBABULE", "KASANDA": "KASSANDA", "BUKOMANSIBI": "BUKOMANSIMBI"}
GREENS = ["#e5f2ea", "#b9dcc6", "#82c19d", "#3f9a6c", "#0f633e"]
AREAS = {"DISTRICT": ("District", "districts"), "SUBCOUNTY": ("Subcounty", "subcounties"), "SUBREGION": ("Sub-region", "sub-regions"),
         "REGION": ("Region", "regions")}
BORDERS = "Boundaries are shown for analysis and imply no position on any border."


@cache
def districts():
    import geopandas as gpd

    return gpd.read_file(GEO / f"{LAYER}.geojson")


@cache
def subcounties():
    import geopandas as gpd

    return gpd.read_file(GEO / f"{SUBCOUNTY_LAYER}.geojson")


@cache
def lakes():
    import geopandas as gpd

    path = GEO / "uganda_water_dcw.geojson"
    return gpd.read_file(path) if path.exists() else None


@cache
def layer_info(stem: str = LAYER) -> dict:
    return json.loads((GEO / f"{stem}.json").read_text(encoding="utf-8"))


@cache
def subregion_of() -> dict[str, str]:
    """District → sub-region, for the districts assigned or confirmed (scripts/build_uganda_districts.py)."""
    table = json.loads((GEO / "uganda_subregions.json").read_text(encoding="utf-8"))["districts"]
    return {d: v["subregion"] for d, v in table.items() if v["subregion"] and v["status"] in ("ASSIGNED", "CONFIRMED")}


@cache
def _region_of() -> dict[str, str]:
    return dict(zip(districts()["district"], districts()["region"], strict=True))


@cache
def subregions() -> list[str]:
    return sorted(set(subregion_of().values()))


@cache
def layer_sha() -> str:
    """Every map data file: part of every map's fingerprint, so a new layer makes old maps out of date."""
    digest = hashlib.sha256()
    for name in (f"{LAYER}.geojson", f"{SUBCOUNTY_LAYER}.geojson", "uganda_subregions.json"):
        digest.update((GEO / name).read_bytes().replace(b"\r\n", b"\n"))  # the same on every checkout, whatever its line endings
    return digest.hexdigest()[:16]


def tidy(name: str) -> str:
    text = re.sub(r"\b(district|local government|dlg|lg|sub ?county|town council)\b", " ", str(name), flags=re.I)
    return " ".join(re.sub(r"[-_.,/]+", " ", text).upper().split())


@cache
def _official() -> dict[str, str]:
    """Tidied official name → the layer's name (MADI-OKOLLO and MADI OKOLLO are the same)."""
    return {tidy(n): n for n in districts()["district"]}


@cache
def _official_subcounties() -> dict[str, dict[str, str]]:
    out: dict[str, dict[str, str]] = {}
    for d, s in zip(subcounties()["district"], subcounties()["subcounty"], strict=True):
        out.setdefault(d, {})[tidy(s)] = s
    return out


def match(values: list[str], confirmed: dict[str, str]) -> tuple[dict[str, str], dict[str, str], list[str]]:
    """Each value → its district (exact after tidying, known spellings, or the researcher's
    confirmed choice); near misses suggested; the rest unmatched."""
    official = _official()
    names = set(official.values())
    matched: dict[str, str] = {}
    suggested: dict[str, str] = {}
    unmatched: list[str] = []
    for value in values:
        if value in confirmed and confirmed[value] in names:
            matched[value] = confirmed[value]
            continue
        key = tidy(value)
        key = tidy(ALIASES.get(key, key))
        if key in official:
            matched[value] = official[key]
            continue
        close = difflib.get_close_matches(key, list(official), n=1, cutoff=0.8)
        if close:
            suggested[value] = official[close[0]]
        unmatched.append(value)
    return matched, suggested, unmatched


def match_subcounties(pairs: list[tuple[str, str]], confirmed: dict[str, str]) -> tuple[dict[tuple[str, str], str], dict[str, str], list[str]]:
    """Each (district, subcounty) pair → the subcounty's key in the layer ("SUBCOUNTY|DISTRICT"), always
    within its own district: a subcounty name alone never matches. A confirmed choice is keyed
    "subcounty|district" as the data writes them."""
    by_district = _official_subcounties()
    matched: dict[tuple[str, str], str] = {}
    suggested: dict[str, str] = {}
    unmatched: list[str] = []
    for district, subcounty in pairs:
        label = f"{subcounty}|{district}"
        own = by_district.get(district, {})
        chosen = confirmed.get(label)
        if chosen is not None and chosen in own.values():
            matched[(district, subcounty)] = f"{chosen}|{district}"
            continue
        key = tidy(subcounty)
        if key in own:
            matched[(district, subcounty)] = f"{own[key]}|{district}"
            continue
        close = difflib.get_close_matches(key, list(own), n=1, cutoff=0.8)
        if close:
            suggested[label] = own[close[0]]
        unmatched.append(label)
    return matched, suggested, unmatched


@cache
def _areas(level: str):
    """The polygons drawn at a level, keyed "area"; each with its region and sub-region."""
    import geopandas as gpd

    base = districts().copy()
    base["subregion"] = base["district"].map(subregion_of())
    if level == "DISTRICT":
        return base.assign(area=base["district"])
    if level == "SUBCOUNTY":
        layer = subcounties().merge(base[["district", "region", "subregion"]], on="district")
        return layer.assign(area=layer["subcounty"] + "|" + layer["district"])
    column = "subregion" if level == "SUBREGION" else "region"
    joined = base.dropna(subset=[column]).dissolve(by=column, as_index=False, aggfunc="first")
    return gpd.GeoDataFrame({"area": joined[column], "region": joined["region"], "subregion": joined["subregion"] if level == "SUBREGION" else None},
                            geometry=joined.geometry, crs=base.crs)


def area_label(level: str, key: str) -> str:
    if level == "SUBCOUNTY":
        subcounty, district = key.split("|", 1)
        return f"{subcounty.title()} ({district.title()})"
    return key.title() if level == "DISTRICT" else key


def _breaks(values: np.ndarray, k: int = 5) -> list[float]:
    qs = np.unique(np.quantile(values, np.linspace(0, 1, k + 1)))
    return [float(q) for q in qs] if len(qs) > 1 else [float(values.min()), float(values.max())]


def _legend_numbers(breaks: list[float], whole: bool) -> Callable[[float], str]:
    """Choose enough precision that distinct class boundaries never print as the same number."""
    for places in range(0 if whole else 1, 13):
        if len({f"{b:,.{places}f}" for b in breaks}) == len(breaks):
            return lambda v: f"{v:,.{places}f}"
    return lambda v: repr(v)


def _nice(km: float) -> float:
    for step in (500, 200, 100, 50, 20, 10, 5, 2, 1):
        if step <= km:
            return float(step)
    return 1.0


def run(ctx: Context, spec: AnalysisSpec) -> tuple[AnalysisResult, bytes | None]:
    """The map and its table. `ctx.frame` is already limited to the analysis's filter."""
    district_var = ctx.variables[spec.variables[0]]
    value_var = ctx.variables[spec.variables[1]] if len(spec.variables) > 1 else None
    totals = spec.data_form == "TOTALS"
    measure = spec.method or ("MEAN" if value_var is not None and not totals else "COUNT")
    singular, plural = AREAS[spec.level]
    total_var = ctx.variables.get(spec.total)
    denominator_var = ctx.variables.get(spec.denominator)
    if totals:
        label = f"{total_var.title() if total_var else 'Total'} per 1,000" if measure == "RATE" else (total_var.title() if total_var else "Total")
    else:
        label = f"Average {value_var.title()}" if measure == "MEAN" and value_var else "Records"
    where = f", {spec.subregion} sub-region" if spec.subregion else f", {spec.region} region" if spec.region else ""
    title = f"{label} by {singular.lower()}{where}"
    names = [district_var.name] + ([spec.subcounty] if spec.level == "SUBCOUNTY" and spec.subcounty in ctx.variables else [])
    names += [v.name for v in (value_var, total_var, denominator_var) if v is not None]
    data, left_out = _complete(ctx, list(dict.fromkeys(names)))
    if len(data) == 0:
        return _empty(ctx, spec, title, "There are no records with a place" + (" and a value" if value_var or total_var else "") + ".", left_out), None

    # place each record (or area total) in its area
    raw = _text_values(data[district_var.name])
    matched, suggested, unmatched = match(sorted(raw.unique()), spec.aliases)
    if unmatched:
        rows_unmatched = int(raw.isin(unmatched).sum())
        left_out.append(f"{disclosure.few(rows_unmatched, ctx.threshold).capitalize()} records have district names that don't match Uganda's 2020 districts: "
                        + ", ".join(f'"{u}"' for u in unmatched[:12]) + ("…" if len(unmatched) > 12 else "") + ".")
    data = data.assign(_district=raw.map(matched)).dropna(subset=["_district"])
    if spec.level == "SUBCOUNTY":
        sub = _text_values(data[spec.subcounty])
        pairs = sorted(set(zip(data["_district"], sub, strict=True)))
        found, sub_suggested, sub_unmatched = match_subcounties(pairs, spec.aliases)
        suggested.update(sub_suggested)
        unmatched += sub_unmatched
        keys = [found.get((d, s)) for d, s in zip(data["_district"], sub, strict=True)]
        missing = sum(1 for k in keys if k is None)
        if missing:
            left_out.append(f"{disclosure.few(missing, ctx.threshold).capitalize()} records have subcounty names that don't match a subcounty of their "
                            "district (2021).")
        data = data.assign(_area=keys).dropna(subset=["_area"])
    elif spec.level == "DISTRICT":
        data = data.assign(_area=data["_district"])
    else:
        group = subregion_of() if spec.level == "SUBREGION" else _region_of()
        data = data.assign(_area=data["_district"].map(group)).dropna(subset=["_area"])

    # the area mapped: a region, a sub-region, or the districts a filter keeps (zoomed, with neighbours for context)
    layer = _areas(spec.level)
    focus = layer
    if spec.region or spec.subregion:
        inside = {d for d, r in _region_of().items() if r == spec.region} if spec.region else {d for d, s in subregion_of().items() if s == spec.subregion}
        outside = int((~data["_district"].isin(inside)).sum())
        if outside:
            left_out.append(f"{disclosure.few(outside, ctx.threshold).capitalize()} records are in districts outside the {spec.subregion or spec.region} "
                            f"{'sub-region' if spec.subregion else 'region'}.")
        data = data[data["_district"].isin(inside)]
        focus = layer[layer["region"] == spec.region] if spec.region else layer[layer["subregion"] == spec.subregion]
    kept = [f for f in spec.filters if f.variable == district_var.name and f.op == "IN"]
    if kept:
        chosen = {matched[v] for f in kept for v in f.values if v in matched}
        if spec.level == "DISTRICT":
            focus = focus[focus["area"].isin(chosen)]
        elif spec.level == "SUBCOUNTY":
            focus = focus[focus["district"].isin(chosen)]
        else:
            group = subregion_of() if spec.level == "SUBREGION" else _region_of()
            focus = focus[focus["area"].isin({group.get(d) for d in chosen})]
    ctx.used = data.index  # after unmatched places and other regions were left out
    placed = pd.to_numeric(data[total_var.name], errors="coerce").sum() if totals else len(data)  # area totals count what they hold, not their rows
    if placed < ctx.threshold:
        result = _empty(ctx, spec, title, f"Fewer than {ctx.threshold} records can be placed on the map, too few to show without identifying people.", left_out)
        result.matches, result.unmatched = suggested, unmatched
        return result, None

    # the measure per area, protected
    grouped = data.groupby("_area")
    populations = None
    if totals:
        values_total = pd.to_numeric(data[total_var.name], errors="coerce")
        if (values_total < 0).any() or (values_total % 1 != 0).any():
            return _empty(ctx, spec, title, f"\"{total_var.title()}\" should hold counts (whole numbers, never negative) to be mapped as totals.", left_out), None
        unit = data["_area"] if spec.level == "SUBCOUNTY" else data["_district"]
        repeated = sorted(set(unit[unit.duplicated()]))
        if repeated:
            named = ", ".join(area_label("SUBCOUNTY" if spec.level == "SUBCOUNTY" else "DISTRICT", r) for r in repeated[:8])
            return _empty(ctx, spec, title, f"Each row should hold one area's total, but {named}{' …' if len(repeated) > 8 else ''} appear more than once. If "
                          "each row is one record, map the data as records instead.", left_out), None
        counts = grouped[total_var.name].sum().astype(int)
        if measure == "RATE":
            populations = grouped[denominator_var.name].sum()
            if (populations <= 0).any():
                return _empty(ctx, spec, title, f"\"{denominator_var.title()}\" must be above zero in every area to give a rate.", left_out), None
            values = 1000 * counts / populations
        else:
            values = counts.astype(float)
    else:
        counts = grouped.size()
        values = grouped[value_var.name].mean() if measure == "MEAN" and value_var is not None else counts.astype(float)
    guard = disclosure.protect([int(c) for c in counts], ctx.threshold, row_totals=True, column_totals=False)
    hidden = dict(zip(counts.index, (bool(h) for h in guard.cells[0]), strict=True))
    if populations is not None:
        # a small denominator identifies people as surely as a small count (Codex audit 2026-10-04, finding 3): the
        # populations are protected the same way, and an area is hidden (count, population and rate) when either is.
        # Hiding more entries only widens what anyone could work out, so both protections still hold.
        shield = disclosure.protect([round(float(v)) for v in populations], ctx.threshold, row_totals=True, column_totals=False)
        hidden = {a: hidden[a] or bool(h) for a, h in zip(counts.index, shield.cells[0], strict=True)}
    shown = {a: float(values[a]) for a in values.index if not hidden[a]}

    table_rows = []
    stats: dict[str, float] = {"n": float(counts.sum()) if totals else float(len(data)), "areas": float(len(counts)), "areas_shown": float(len(shown))}
    # shown areas by value, hidden ones after them by name: a hidden row's place in the order would hint at its value
    for a in sorted(values.index, key=lambda x: (hidden[x], -values[x] if not hidden[x] else 0, x)):
        n = int(counts[a])
        count_cell = Cell(text=disclosure.HIDDEN, count=True, suppressed=True) if hidden[a] else Cell(text=f"{n:,}", value=n, count=True)
        row = [Cell(text=area_label(spec.level, a)), count_cell]
        if populations is not None:
            row += [Cell(text=disclosure.HIDDEN, count=True, suppressed=True) if hidden[a] else Cell(text=f"{float(populations[a]):,.0f}", value=float(populations[a]), count=True),
                    Cell(text=disclosure.HIDDEN, suppressed=True) if hidden[a] else Cell(text=f"{values[a]:,.2f}", value=float(values[a]))]
        elif measure == "MEAN":
            row.append(Cell(text=disclosure.HIDDEN, suppressed=True) if hidden[a] else Cell(text=f"{values[a]:,.2f}", value=float(values[a])))
        table_rows.append(row)
    if shown:
        top = max(shown, key=lambda d: shown[d])
        low = min(shown, key=lambda d: shown[d])
        stats.update({"max": shown[top], "min": shown[low], "median": float(np.median(list(shown.values())))})
    if populations is not None:
        columns = [singular, total_var.title(), denominator_var.title(), label]
    elif totals:
        columns = [singular, label]
    else:
        columns = [singular, "Records", label] if measure == "MEAN" else [singular, "Records"]
    notes = [disclosure.note(ctx.threshold)] if any(hidden.values()) else []
    table = ResultTable(title=title, columns=columns, rows=table_rows, notes=notes)
    sentences = []
    whole = measure == "COUNT"
    if shown:
        fmt = (lambda v: f"{int(v):,}") if whole else (lambda v: f"{v:,.2f}")
        sentences.append(f"{len(shown)} {plural} are mapped. The highest {label.lower()} was in {area_label(spec.level, top)} ({fmt(shown[top])}) "
                         f"and the lowest in {area_label(spec.level, low)} ({fmt(shown[low])}).")
    if measure == "COUNT":
        sentences.append("These are counts, not rates: areas with larger populations may simply have more.")
    warnings = []
    if unmatched:
        warnings.append(f"{len(unmatched)} place name{'s' if len(unmatched) != 1 else ''} in your data couldn't be matched"
                        + (": confirm the suggested matches to include them." if suggested else "; check their spelling."))
    info = layer_info(SUBCOUNTY_LAYER if spec.level == "SUBCOUNTY" else LAYER)
    coding = [f"Places matched to {info['name']} ({info['source']})."]
    if spec.level in ("SUBREGION", "REGION"):
        coding.append(f"Districts grouped into {plural} as UBOS defines them.")
    coding += [f'"{k}" treated as {v.title()} (you confirmed).' for k, v in spec.aliases.items()]
    if totals:
        method = (f"{total_var.title()} per 1,000 {denominator_var.title()}" if populations is not None else f"Total of {total_var.title()}") + f" per {singular.lower()}"
    else:
        method = f"Mean of {value_var.title()} per {singular.lower()}" if measure == "MEAN" and value_var else f"Count of records per {singular.lower()}"
    if totals:  # the rows are areas' totals: the rows used are the rows, the total is said apart (Codex audit 2026-10-04, finding 10)
        coding.append(f"Each row holds one area's total; together the rows used hold {int(counts.sum()):,} in \"{total_var.title()}\"."
                      if not any(hidden.values()) else f"Each row holds one area's total of \"{total_var.title()}\".")
    record = _record(ctx, spec, method + ", shown as a choropleth map in five quantile classes", f"A map shows how the measure varies across {plural}.",
                     len(data), left_out, coding)
    result = AnalysisResult(id=f"an_{secrets.token_hex(4)}", spec=spec, status="VALID_WITH_WARNINGS" if warnings else "VALID", title=title, tables=[table],
                            statistics=stats, sentences=sentences, warnings=warnings, record=record, matches=suggested, unmatched=unmatched)
    labelled(ctx, result)
    context = _neighbours(layer, focus) if len(focus) < len(layer) else None
    return result, draw(focus, shown, {a for a, h in hidden.items() if h}, result.title, label, info, whole=whole, context=context)


def _neighbours(layer, focus):
    """The areas touching the area mapped, drawn in grey around it for context."""
    outline = focus.union_all()
    return layer[~layer["area"].isin(focus["area"]) & layer.intersects(outline.buffer(1e-6))]


def _empty(ctx: Context, spec: AnalysisSpec, title: str, reason: str, left_out: list[str]) -> AnalysisResult:
    return labelled(ctx, AnalysisResult(id=f"an_{secrets.token_hex(4)}", spec=spec, status="NOT_ESTIMABLE", title=title, warnings=[reason],
                                        record=_record(ctx, spec, "Not calculated", reason, 0, left_out)))


def draw(layer, values: dict[str, float], hidden: set[str], title: str, label: str, info: dict, whole: bool = False, context=None) -> bytes:
    projected = layer.to_crs(UTM36N)
    minx, miny, maxx, maxy = projected.total_bounds
    height = min(9.0, max(4.0, 6.0 * (maxy - miny) / max(1.0, maxx - minx)))
    fig, ax = plt.subplots(figsize=(8.4, height), dpi=200)  # the legend sits to the right of the map
    ax.set_axis_off()
    data = np.array(list(values.values())) if values else np.array([0.0])
    breaks = _breaks(data)  # from the areas shown only: a hidden value never sets a class
    colours = GREENS[-(len(breaks) - 1):] if len(breaks) - 1 < len(GREENS) else GREENS

    def colour(v: float) -> str:
        i = int(np.searchsorted(breaks[1:-1], v, side="right"))
        return colours[min(i, len(colours) - 1)]

    pad = (maxx - minx) * 0.04
    if context is not None and len(context):
        for geometry in context.to_crs(UTM36N).geometry:
            ax.add_patch(matplotlib.patches.PathPatch(_path(geometry), facecolor="#fafafa", edgecolor="#d1d5db", linewidth=0.4, linestyle="--"))
    for key, geometry in zip(projected["area"], projected.geometry, strict=True):
        if key in values:
            face, hatch = colour(values[key]), None
        elif key in hidden:
            face, hatch = "#e5e7eb", "////"
        else:
            face, hatch = "#f3f4f6", None
        ax.add_patch(matplotlib.patches.PathPatch(_path(geometry), facecolor=face, edgecolor="white", linewidth=0.4, hatch=hatch))
    water = lakes()
    if water is not None:  # lakes over the areas, so lakeside areas' water reads as water
        area = water.to_crs(UTM36N).clip(projected.union_all().envelope.buffer(pad * 3))
        for geometry in area.geometry:
            if geometry is not None and not geometry.is_empty and geometry.geom_type in ("Polygon", "MultiPolygon"):
                ax.add_patch(matplotlib.patches.PathPatch(_path(geometry), facecolor="#dbeafe", edgecolor="#bfdbfe", linewidth=0.3))
    ax.set_xlim(minx - pad, maxx + pad)
    ax.set_ylim(miny - pad * 3, maxy + pad)
    ax.set_aspect("equal")
    ax.set_title(title, fontsize=11, loc="left", color="#111827")
    shown_as = _legend_numbers(breaks, whole)
    handles = [Patch(facecolor=colours[i], edgecolor="none",
                     label=(shown_as(breaks[i]) if breaks[i] == breaks[i + 1]
                            else f"{shown_as(breaks[i])} – {shown_as(breaks[i + 1])}"))
               for i in range(len(breaks) - 1)] if values else []
    if hidden:
        handles.append(Patch(facecolor="#e5e7eb", hatch="////", edgecolor="#9ca3af", label="Hidden to protect privacy"))
    handles.append(Patch(facecolor="#f3f4f6", edgecolor="#d1d5db", label="No data"))
    if context is not None and len(context):
        handles.append(Patch(facecolor="#fafafa", edgecolor="#d1d5db", linestyle="--", label="Outside the area mapped"))
    if water is not None:
        handles.append(Patch(facecolor="#dbeafe", edgecolor="#bfdbfe", label="Lakes"))
    ax.legend(handles=handles, title=label, loc="lower left", bbox_to_anchor=(1.0, 0.02), fontsize=7.5, title_fontsize=8, frameon=False, alignment="left")
    # north arrow and scale bar (metres in UTM zone 36N)
    ax.annotate("N", xy=(0.93, 0.95), xytext=(0.93, 0.86), xycoords="axes fraction", ha="center", fontsize=9, fontweight="bold",
                arrowprops={"arrowstyle": "-|>", "color": "#111827", "lw": 1.2})
    width_km = _nice((maxx - minx) / 1000 / 4)
    x0, y0 = maxx - width_km * 1000 - pad, miny - pad * 2
    ax.plot([x0, x0 + width_km * 1000], [y0, y0], color="#111827", lw=2)
    ax.text(x0 + width_km * 500, y0 + pad * 0.5, f"{width_km:g} km", ha="center", fontsize=7)
    fig.text(0.02, 0.005, f"Boundaries: Uganda Bureau of Statistics (UBOS), {info.get('year', '')}. {BORDERS} Lakes: Digital Chart of the World.",
             fontsize=6, color="#6b7280")
    buffer = io.BytesIO()
    fig.savefig(buffer, format="png", dpi=200, bbox_inches="tight")
    plt.close(fig)
    return buffer.getvalue()


def _path(geometry):
    from matplotlib.path import Path as MPath

    polygons = geometry.geoms if geometry.geom_type in ("MultiPolygon", "GeometryCollection") else [geometry]
    vertices: list[tuple[float, float]] = []
    codes: list[int] = []
    for polygon in polygons:
        if polygon.geom_type != "Polygon":
            continue
        for ring in [polygon.exterior, *polygon.interiors]:
            coords = list(ring.coords)
            vertices += coords
            codes += [MPath.MOVETO] + [MPath.LINETO] * (len(coords) - 2) + [MPath.CLOSEPOLY]
    return MPath(vertices or [(0, 0), (0, 0)], codes or [MPath.MOVETO, MPath.LINETO])


def available_districts(region: str = "") -> list[str]:
    layer = districts()
    return sorted(layer.loc[layer["region"] == region, "district"] if region else layer["district"])


def places() -> dict:
    """What the map step offers: the regions, and the sub-regions with their districts."""
    by_subregion: dict[str, list[str]] = {}
    for d, s in subregion_of().items():
        by_subregion.setdefault(s, []).append(d)
    return {"regions": list(REGIONS), "subregions": [{"name": s, "districts": sorted(by_subregion[s])} for s in subregions()]}


__all__ = ["REGIONS", "available_districts", "match", "match_subcounties", "places", "run", "tidy"]
