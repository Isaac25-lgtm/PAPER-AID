"""Uganda maps in full and filters on any variable (owner decision 2026-10-04, after Codex's review):
subcounties named with their district, sub-regions and regions, records or totals, filters with the
subtraction rule, results released together checked as a set."""

import numpy as np
import pytest

from app.core.errors import AppError
from app.datalab.engine import filters, ingest, maps, profile, stats
from app.datalab.models import AnalysisSpec, Filter
from tests.test_datalab_engine import SLEEP_1, SLEEP_2

LIMITS = ingest.Limits(rows=10_000, columns=200, cells=1_000_000, expanded_bytes=50_000_000)


def _setup(columns: dict[str, list], threshold: int = 5):
    table = ingest.Table(columns=list(columns), rows=[list(r) for r in zip(*columns.values(), strict=True)])
    frame, variables = profile.infer(table)
    return frame, {v.name: v for v in variables}, threshold


def _ctx(frame, variables, threshold, spec: AnalysisSpec) -> stats.Context:
    kept, notes, words = filters.apply(frame, spec.filters, variables, threshold)
    return stats.Context(kept, variables, 1, threshold=threshold, available=len(frame), population=words, notes=notes)


# --- filters ---------------------------------------------------------------------------------------------


def test_a_filtered_analysis_matches_r_on_the_records_it_keeps():
    """Welch's t-test on R's sleep data, with a third group in the file that the filter leaves out."""
    frame, variables, t = _setup({"extra": SLEEP_1 + SLEEP_2 + [9.0] * 8, "group": ["1"] * 10 + ["2"] * 10 + ["3"] * 8})
    spec = AnalysisSpec(kind="COMPARE_TWO", variables=["extra", "group"], method="MEANS", filters=[Filter(variable="group", op="IN", values=["1", "2"])])
    r = stats.run(_ctx(frame, variables, t, spec), spec)
    assert r.statistics["t"] == pytest.approx(-1.860813, abs=1e-6) and r.statistics["df"] == pytest.approx(17.77647, abs=1e-5)
    assert r.record.rows_used == 20 and r.record.rows_available == 28 and r.record.filters == "group is 1 or 2"
    assert any("8 records are outside the filter (group is 1 or 2)" in x for x in r.record.left_out)
    assert "among records where group is 1 or 2" in r.record.question and r.title.endswith("(group is 1 or 2)")


def test_number_and_date_ranges_and_missing_values():
    days = [f"2026-10-{d:02d}" for d in range(1, 31)] * 2
    frame, variables, t = _setup({"age": [float(a) for a in range(60)], "seen": days, "note": ["x"] * 59 + [None]})
    keep, missing = filters.mask(frame, [Filter(variable="age", op="BETWEEN", low="10", high="19")], variables)
    assert int(keep.sum()) == 10 and missing == []
    keep, _ = filters.mask(frame, [Filter(variable="seen", op="BETWEEN", low="2026-10-05", high="2026-10-06")], variables)
    assert int(keep.sum()) == 4  # the upper day is included whole
    keep, missing = filters.mask(frame, [Filter(variable="note", op="NOT_IN", values=["y"])], variables)
    assert int(keep.sum()) == 59 and missing and "no value" in missing[0]  # a missing value never matches, even "is not"


def test_the_subtraction_rule_refuses_a_filter_that_isolates_a_few():
    frame, variables, t = _setup({"district": ["Gulu"] * 40 + ["Pader"] * 3, "score": list(range(43))})
    for values, code in ((["Pader"], "FILTER_TOO_NARROW"), (["Gulu"], "FILTER_TOO_NARROW"), (["Kampala"], "FILTER_EMPTY")):
        with pytest.raises(AppError) as exc:  # 3 kept; 3 left out; none kept
            filters.apply(frame, [Filter(variable="district", op="IN", values=values)], variables, t)
        assert exc.value.code == code
    kept, _, _ = filters.apply(frame, [Filter(variable="score", op="BETWEEN", low="10")], variables, t)
    assert len(kept) == 33


def test_columns_that_identify_people_or_places_cant_be_filters():
    frame, variables, t = _setup({"name": [f"P{i}" for i in range(30)], "lat": [0.3 + i / 100 for i in range(30)], "score": list(range(30))})
    for column in ("name", "lat"):
        with pytest.raises(AppError) as exc:
            filters.check([Filter(variable=column, op="IN", values=["x"])], variables)
        assert exc.value.code == "FILTER_NOT_ALLOWED"


def test_results_released_together_cant_differ_by_a_few_records():
    """Codex's case: 50 records, and the same 50 but one: each filter passes alone, the pair doesn't."""
    frame, variables, t = _setup({"group": ["a"] * 50 + ["b"] * 1 + ["c"] * 49, "score": list(range(100))})
    with pytest.raises(AppError) as exc:
        filters.overlaps(frame, {"x": [Filter(variable="group", op="IN", values=["a"])], "y": [Filter(variable="group", op="IN", values=["a", "b"])]},
                         {"x": "First", "y": "Second"}, variables, t)
    assert exc.value.code == "OVERLAPPING_RESULTS" and "First" in exc.value.message
    filters.overlaps(frame, {"x": [Filter(variable="group", op="IN", values=["a"])], "y": [Filter(variable="group", op="IN", values=["c"])]},
                     {"x": "First", "y": "Second"}, variables, t)  # different groups: fine


# --- maps ---------------------------------------------------------------------------------------------


def test_the_layers_cover_uganda_with_15_sub_regions():
    places = maps.places()
    assert len(places["subregions"]) == 15 and sum(len(s["districts"]) for s in places["subregions"]) == 146
    assert "Bugisu–Sebei" in [s["name"] for s in places["subregions"]] and "KALANGALA" in next(s for s in places["subregions"] if s["name"] == "Central I")["districts"]
    assert len(maps.subcounties()) == 2181


def test_a_subcounty_is_matched_only_within_its_district():
    names = maps._official_subcounties()
    shared = next(s for s in names["KAMPALA"].values() if any(s in other.values() for d, other in names.items() if d != "KAMPALA")) \
        if any(any(s in o.values() for d, o in names.items() if d != "KAMPALA") for s in names["KAMPALA"].values()) else None
    district_a, district_b = [d for d, subs in names.items() if any(maps.tidy(x) == "CENTRAL DIVISION" for x in subs.values())][:2]
    found, _, unmatched = maps.match_subcounties([(district_a, "Central Division"), (district_b, "Central Division"), ("GULU", "Central Division")], {})
    assert found[(district_a, "Central Division")] != found[(district_b, "Central Division")]  # the same name, two places
    assert ("Central Division|GULU" in unmatched) == (("GULU", "Central Division") not in found)
    assert shared is None or shared  # (names repeat across districts: that's why the district is required)


def _map(columns, spec: AnalysisSpec, threshold=5):
    frame, variables, t = _setup(columns, threshold)
    return maps.run(_ctx(frame, variables, t, spec), spec)


def test_records_mapped_by_sub_region_and_region():
    rows = {"district": ["Gulu"] * 12 + ["Pader"] * 9 + ["Kitgum"] * 8 + ["Mbarara"] * 15 + ["Kabale"] * 6}
    by_subregion, png = _map(rows, AnalysisSpec(kind="MAP", variables=["district"], method="COUNT", level="SUBREGION"))
    counts = {r[0].text: r[1].text for r in by_subregion.tables[0].rows}
    assert counts["Acholi"] == "29" and counts["Ankole"] == "15" and counts["Kigezi"] == "6" and png[:4] == b"\x89PNG"
    by_region, _ = _map(rows, AnalysisSpec(kind="MAP", variables=["district"], method="COUNT", level="REGION"))
    assert {r[0].text: r[1].text for r in by_region.tables[0].rows} == {"Northern": "29", "Western": "21"}
    acholi, _ = _map(rows, AnalysisSpec(kind="MAP", variables=["district"], method="COUNT", subregion="Acholi"))
    assert {r[0].text for r in acholi.tables[0].rows} == {"Gulu", "Pader", "Kitgum"}
    assert any("outside the Acholi sub-region" in x for x in acholi.record.left_out)


def test_totals_are_mapped_as_counts_or_rates_and_never_counted_as_records():
    rows = {"district": ["Gulu", "Pader", "Kitgum", "Lira"], "cases": [120, 3, 45, 60], "population": [300000, 200000, 150000, 400000]}
    counted, _ = _map(rows, AnalysisSpec(kind="MAP", variables=["district"], data_form="TOTALS", total="cases", method="COUNT"))
    table = {r[0].text: r[1].text for r in counted.tables[0].rows}
    assert table["Gulu"] == "120" and table["Pader"] == "–"  # 3 cases: hidden, with another so the total can't reveal it
    assert sum(1 for v in table.values() if v == "–") >= 2
    rated, _ = _map(rows, AnalysisSpec(kind="MAP", variables=["district"], data_form="TOTALS", total="cases", denominator="population", method="RATE"))
    gulu = next(r for r in rated.tables[0].rows if r[0].text == "Gulu")
    assert gulu[3].text == "0.40" and rated.tables[0].columns[-1] == "cases per 1,000"
    twice, _ = _map({"district": ["Gulu", "Gulu", "Pader"], "cases": [10, 12, 30]},
                    AnalysisSpec(kind="MAP", variables=["district"], data_form="TOTALS", total="cases"))
    assert twice.status == "NOT_ESTIMABLE" and "more than once" in twice.warnings[0]


def test_a_filter_on_the_districts_zooms_the_map_to_them():
    rows = {"district": ["Gulu"] * 12 + ["Pader"] * 9 + ["Kampala"] * 15, "score": list(range(36))}
    spec = AnalysisSpec(kind="MAP", variables=["district"], method="COUNT", filters=[Filter(variable="district", op="IN", values=["Gulu", "Pader"])])
    result, png = _map(rows, spec)
    assert {r[0].text for r in result.tables[0].rows} == {"Gulu", "Pader"} and result.title.endswith("(district is Gulu or Pader)")
    focus = maps._areas("DISTRICT")
    zoomed = focus[focus["area"].isin({"GULU", "PADER"})]
    assert len(maps._neighbours(focus, zoomed)) > 0 and png[:4] == b"\x89PNG"  # neighbours drawn in grey around them


def test_a_subcounty_map_counts_within_each_district():
    names = maps._official_subcounties()
    gulu = sorted(names["GULU"].values())[:2]
    rows = {"district": ["Gulu"] * 14, "subcounty": [gulu[0].title()] * 8 + [gulu[1].title()] * 6}
    result, png = _map(rows, AnalysisSpec(kind="MAP", variables=["district"], method="COUNT", level="SUBCOUNTY", subcounty="subcounty"))
    labels = {r[0].text for r in result.tables[0].rows}
    assert labels == {f"{gulu[0].title()} (Gulu)", f"{gulu[1].title()} (Gulu)"} and png[:4] == b"\x89PNG"
    assert np.isclose(result.statistics["n"], 14)
