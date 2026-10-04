"""Build the Uganda layers Data Lab maps use (owner decisions 2026-10-03 and 2026-10-04), from the
owner's UBOS files (the owner states PaperAid may use them in any way, 2026-10-04). Each released
layer file is frozen (app/datalab/geo/released.json): a new build writes a new file name.

    python scripts/build_uganda_districts.py districts PATH/TO/UGANDA_DISTRICT.json [PATH/TO/UGA_water_areas_dcw.shp]
    python scripts/build_uganda_districts.py subcounties PATH/TO/Uganda-Subcounties-2021.shp
    python scripts/build_uganda_districts.py subregions PATH/TO/UGANDA_DISTRICT.json PATH/TO/uganda_parishes_cleaned_attached.shp

Districts: UGANDA_DISTRICT.json (146 districts, 2020, WGS84, with a region code), chosen over the
shapefile in the same delivery (it mixes cities with districts, has a feature with no name or
shape, nine invalid shapes, no codes and 63 km² of overlaps). Kabale's invalid shape repaired,
outlines simplified to about 100 m.

Subcounties: Uganda-Subcounties-2021.shp (2,190 features). Pieces of one subcounty (the same object
id) are joined, the feature with no name or shape is dropped, invalid shapes are repaired, two
district spellings are brought to the district layer's (LUWERO → LUWEERO, NAMUTUNMBA → NAMUTUMBA),
outlines simplified to about 100 m. A subcounty is always named with its district: names repeat.

Sub-regions: the parish layer (2016) carries the 15 sub-regions. Each 2020 district is assigned the
sub-region covering most of its area, measured on full shapes in a projected system (Arc 1960 / UTM
36N); a district at least 90% inside one sub-region is assigned, any other is listed for the owner
to confirm and is left out of sub-region maps and filters until then. UBOS gives Bugisu and Sebei
as one sub-region; it is kept so ("Bugisu–Sebei"). The original files are never changed."""

import hashlib
import json
import re
import sys
from pathlib import Path

import geopandas as gpd
import shapely
from shapely.validation import make_valid

OUT = Path(__file__).resolve().parents[1] / "app" / "datalab" / "geo"
REGIONS = {"1": "Central", "2": "Eastern", "3": "Northern", "4": "Western"}
SOURCE = "Uganda Bureau of Statistics (UBOS)"
LICENCE = "UBOS. PaperAid's owner states PaperAid may use these files in any way (2026-10-04)."
SPELLINGS = {"LUWERO": "LUWEERO", "NAMUTUNMBA": "NAMUTUMBA"}
SUBREGIONS = {"ACHOLI": "Acholi", "ANKOLE": "Ankole", "BUGISU_SEBEI": "Bugisu–Sebei", "BUKEDI": "Bukedi", "BUNYORO": "Bunyoro", "BUSOGA": "Busoga",
              "CENTRAL I": "Central I", "CENTRAL II": "Central II", "GREATER KAMPALA": "Greater Kampala", "KARAMOJA": "Karamoja", "KIGEZI": "Kigezi",
              "LANGO": "Lango", "TESO": "Teso", "TORO": "Toro", "WEST NILE": "West Nile"}
ASSIGN_SHARE = 0.9


def _tidy(name: str) -> str:
    return " ".join(re.sub(r"[-_.,/]+", " ", str(name)).upper().split())


def _valid(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    gdf["geometry"] = gdf.geometry.apply(lambda g: g if g.is_valid else make_valid(g))
    return gdf


def districts(source: Path) -> None:
    data = source.read_bytes()
    gdf = _valid(gpd.read_file(source))
    assert len(gdf) == 146 and gdf.crs.to_epsg() == 4326, (len(gdf), gdf.crs)
    gdf["geometry"] = gdf.geometry.simplify(0.001, preserve_topology=True)
    assert gdf.is_valid.all()
    out = gpd.GeoDataFrame({"district": gdf["District"].str.strip().str.upper(), "region": gdf["RCode"].map(REGIONS)}, geometry=gdf.geometry, crs=4326)
    assert out["region"].notna().all() and out["district"].is_unique
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "uganda_districts_2020.geojson").write_text(out.to_json(drop_id=True, to_wgs84=True), encoding="utf-8")
    _meta("uganda_districts_2020", {"name": "Uganda districts, 2020 (146)", "source": f"{SOURCE}: UGANDA_DISTRICT.json", "year": 2020,
                                    "sourceSha256": hashlib.sha256(data).hexdigest(), "features": len(out), "crs": "EPSG:4326 (WGS 84)", "regions": REGIONS,
                                    "simplified": "outlines simplified to about 100 m; Kabale's invalid shape repaired", "licence": LICENCE})
    print(f"{len(out)} districts, {(OUT / 'uganda_districts_2020.geojson').stat().st_size / 1e6:.2f} MB")


def water(source: Path) -> None:
    lakes = gpd.read_file(source).to_crs(4326)
    lakes = lakes[(lakes["HYC_DESCRI"] == "Perennial/Permanent") & (lakes.to_crs(32636).area > 5e6)]
    lakes = gpd.GeoDataFrame({"name": lakes["NAME"].where(lakes["NAME"] != "UNK", "")}, geometry=lakes.geometry.simplify(0.001, preserve_topology=True), crs=4326)
    (OUT / "uganda_water_dcw.geojson").write_text(lakes.to_json(drop_id=True), encoding="utf-8")
    print(f"{len(lakes)} lakes")


def subcounties(source: Path) -> None:
    raw = source.read_bytes() if source.suffix == ".json" else b"".join(p.read_bytes() for p in sorted(source.parent.glob(source.stem + ".*")) if p.suffix in (".shp", ".dbf"))
    gdf = gpd.read_file(source)
    gdf = gdf[gdf.geometry.notna() & gdf["Subcounty"].notna() & gdf["District"].notna()].copy()
    gdf = _valid(gdf)
    gdf["district"] = gdf["District"].map(_tidy).replace(SPELLINGS)
    gdf["subcounty"] = gdf["Subcounty"].map(_tidy)
    joined = gdf.dissolve(by=["district", "subcounty"], as_index=False)[["district", "subcounty", "geometry"]]
    known = set(json.loads((OUT / "uganda_districts_2020.geojson").read_text(encoding="utf-8"))["features"][i]["properties"]["district"]
                for i in range(146))
    assert set(joined["district"]) <= {_tidy(d) for d in known}, sorted(set(joined["district"]) - {_tidy(d) for d in known})
    by_tidy = {_tidy(d): d for d in known}
    joined["district"] = joined["district"].map(by_tidy)
    out = joined.to_crs(4326)
    out["geometry"] = shapely.set_precision(out.geometry.simplify(0.001, preserve_topology=True).values, 1e-5)  # about 100 m outlines, 1 m coordinates
    out["geometry"] = out.geometry.apply(lambda g: g if g.is_valid else make_valid(g))
    assert out.is_valid.all() and not out.duplicated(["district", "subcounty"]).any()
    (OUT / "uganda_subcounties_2021.geojson").write_text(out.to_json(drop_id=True, to_wgs84=True), encoding="utf-8")
    _meta("uganda_subcounties_2021", {"name": f"Uganda subcounties, 2021 ({len(out):,})", "source": f"{SOURCE}: Uganda-Subcounties-2021.shp", "year": 2021,
                                      "sourceSha256": hashlib.sha256(raw).hexdigest(), "features": len(out), "crs": "EPSG:4326 (WGS 84)",
                                      "simplified": "pieces of one subcounty joined; the feature with no name or shape dropped; invalid shapes repaired; "
                                                    "LUWERO and NAMUTUNMBA spelled as in the district layer; outlines simplified to about 100 m",
                                      "licence": LICENCE})
    print(f"{len(out)} subcounties, {(OUT / 'uganda_subcounties_2021.geojson').stat().st_size / 1e6:.2f} MB")


def subregions(district_source: Path, parish_source: Path) -> None:
    """The district → sub-region crosswalk, measured on full shapes in the parish layer's projected system."""
    parishes = _valid(gpd.read_file(parish_source))
    crs = parishes.crs
    labelled = parishes[parishes["F15Regions"].notna()]
    regions = _valid(labelled.dissolve(by="F15Regions", as_index=False)[["F15Regions", "geometry"]])
    full = _valid(gpd.read_file(district_source)).to_crs(crs)
    out: dict[str, dict] = {}
    for _, d in full.iterrows():
        name = d["District"].strip().upper()
        shares = {}
        for _, r in regions.iterrows():
            overlap = d.geometry.intersection(r.geometry).area
            if overlap > 0:
                shares[SUBREGIONS[r["F15Regions"]]] = overlap
        covered = sum(shares.values())
        ranked = sorted(((n, a / covered) for n, a in shares.items()), key=lambda x: -x[1]) if covered else []
        top, share = ranked[0] if ranked else ("", 0.0)
        out[name] = {"subregion": top if share >= ASSIGN_SHARE else "", "share": round(share, 4),
                     "status": "ASSIGNED" if share >= ASSIGN_SHARE else "TO_CONFIRM",
                     "shares": {n: round(s, 4) for n, s in ranked if s >= 0.005}}
    doc = {"name": "Uganda sub-regions (15) by 2020 district", "source": f"{SOURCE}: uganda_parishes_cleaned_attached.shp (2016 parishes, F15Regions) "
           "and UGANDA_DISTRICT.json (2020)", "method": f"each district takes the sub-region covering at least {ASSIGN_SHARE:.0%} of its area (full shapes, "
           f"{crs.to_string()}); others wait for the owner's confirmation", "licence": LICENCE, "subregions": sorted(SUBREGIONS.values()), "districts": out}
    (OUT / "uganda_subregions.json").write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    pending = sorted(n for n, v in out.items() if v["status"] != "ASSIGNED")
    print(f"{len(out) - len(pending)} districts assigned; to confirm: {pending}")


def _meta(stem: str, meta: dict) -> None:
    (OUT / f"{stem}.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    command, *paths = sys.argv[1:]
    if command == "districts":
        districts(Path(paths[0]))
        if len(paths) > 1:
            water(Path(paths[1]))
    elif command == "subcounties":
        subcounties(Path(paths[0]))
    elif command == "subregions":
        subregions(Path(paths[0]), Path(paths[1]))
    else:
        raise SystemExit("commands: districts, subcounties, subregions")
