"""Import one country's boundaries for Data Lab maps (owner decision 2026-10-04, reviewed by Codex). Admin
only, never during a job: PaperAid never fetches boundaries while someone waits for a map.

    python scripts/import_boundaries.py KEN ADM1 [--out DIR] [--upload BUCKET] [--register]

It reads geoBoundaries' open release metadata, pins the exact commit the files come from, and refuses
the layer unless its licence allows commercial use (public domain, CC0, PDDL, CC BY 3.0/4.0, CC BY 3.0
IGO; ODbL is refused for now, and so is anything non-commercial or for humanitarian use only). It checks
the shapes (valid or repaired and counted, none empty, WGS 84, the unit count the metadata gives, unique
codes and names), keeps the full version for later spatial work, simplifies a copy for drawing, and
names both by their content's hash. `--upload` puts them in Cloud Storage (boundaries/ISO/LEVEL/);
`--register` adds the layer to app/datalab/geo/registry.json, always FROZEN: a country is opened only
by a reviewed change to that file citing its legal clearance."""

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

import geopandas as gpd
import httpx
import shapely
from shapely.validation import make_valid

API = "https://www.geoboundaries.org/api/current/gbOpen/{iso}/{level}/"
ALLOWED = ("public domain", "cc0", "pddl", "public domain dedication", "creative commons attribution 4.0", "cc by 4.0", "creative commons attribution 3.0",
           "cc by 3.0")
REFUSED = ("odbl", "open database", "noncommercial", "non-commercial", "humanitarian", "share alike", "sharealike", "nc ")
REGISTRY = Path(__file__).resolve().parents[1] / "app" / "datalab" / "geo" / "registry.json"


def licence_ok(text: str) -> bool:
    t = text.lower()
    return not any(r in t for r in REFUSED) and any(a in t for a in ALLOWED)


def _sha(data: bytes) -> str:
    return hashlib.sha256(data.replace(b"\r\n", b"\n")).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("iso")
    parser.add_argument("level", choices=["ADM1", "ADM2", "ADM3", "ADM4"])
    parser.add_argument("--out", default=str(Path(__file__).resolve().parents[1] / ".boundaries"))
    parser.add_argument("--upload", help="Cloud Storage bucket for boundaries/ISO/LEVEL/")
    parser.add_argument("--register", action="store_true")
    parser.add_argument("--level-name", default="", help="what the country calls these areas, when the source doesn't say (e.g. Districts)")
    args = parser.parse_args()
    iso, level = args.iso.upper(), args.level
    meta = httpx.get(API.format(iso=iso, level=level), timeout=60, follow_redirects=True).json()
    licence = str(meta.get("boundaryLicense", ""))
    if not licence_ok(licence):
        print(f"REFUSED: licence {licence!r} doesn't allow PaperAid's use", file=sys.stderr)
        return 2
    url = meta["gjDownloadURL"]
    commit = re.search(r"/raw/([0-9a-f]{6,40})/", url)
    if commit is None:
        print("REFUSED: the download isn't pinned to a release commit", file=sys.stderr)
        return 2
    raw = httpx.get(url, timeout=300, follow_redirects=True).content
    folder = Path(args.out) / iso / level
    folder.mkdir(parents=True, exist_ok=True)
    source = folder / "source.geojson"
    source.write_bytes(raw)
    gdf = gpd.read_file(source)
    problems = []
    if gdf.crs is None or gdf.crs.to_epsg() != 4326:
        problems.append(f"not WGS 84 ({gdf.crs})")
    if len(gdf) != int(meta["admUnitCount"]):
        problems.append(f"{len(gdf)} units, the metadata says {meta['admUnitCount']}")
    if gdf.geometry.isna().any() or gdf.geometry.is_empty.any():
        problems.append("empty shapes")
    if not gdf["shapeID"].is_unique:
        problems.append("repeated codes")
    if not gdf["shapeName"].is_unique:
        problems.append("repeated names: " + ", ".join(sorted(gdf.loc[gdf["shapeName"].duplicated(), "shapeName"]))[:200])
    repaired = int((~gdf.is_valid).sum())
    gdf["geometry"] = gdf.geometry.apply(lambda g: g if g.is_valid else make_valid(g))
    if problems:
        print("REFUSED: " + "; ".join(problems), file=sys.stderr)
        return 2
    full = gpd.GeoDataFrame({"area": gdf["shapeName"], "code": gdf["shapeID"]}, geometry=gdf.geometry, crs=4326)
    simple = full.copy()
    simple["geometry"] = shapely.set_precision(simple.geometry.simplify(0.001, preserve_topology=True).values, 1e-5)
    simple["geometry"] = simple.geometry.apply(lambda g: g if g.is_valid else make_valid(g))
    full_bytes, simple_bytes = full.to_json(drop_id=True).encode(), simple.to_json(drop_id=True).encode()
    full_sha, simple_sha = _sha(full_bytes), _sha(simple_bytes)
    (folder / f"{full_sha[:16]}.full.geojson").write_bytes(full_bytes)
    (folder / f"{simple_sha[:16]}.geojson").write_bytes(simple_bytes)
    level_name = args.level_name or str(meta.get("boundaryCanonical") or "")
    if not level_name or level_name.lower() == "unknown":
        print("REFUSED: the source doesn't say what these areas are called: give --level-name", file=sys.stderr)
        return 2
    entry = {"iso3": iso, "level": level, "levelName": level_name, "source": f"geoBoundaries gbOpen ({meta.get('boundarySource', '')})",
             "release": commit.group(1), "year": meta.get("boundaryYearRepresented"), "licence": licence,
             "attribution": f"geoBoundaries (Runfola et al.); {meta.get('boundarySource', '')}", "units": len(full), "repaired": repaired,
             "nameField": "area", "codeField": "code", "sha256": simple_sha, "fullSha256": full_sha,
             "path": f"boundaries/{iso}/{level}/{simple_sha[:16]}.geojson", "fullPath": f"boundaries/{iso}/{level}/{full_sha[:16]}.full.geojson",
             "status": "FROZEN", "frozenReason": "DATA_PROTECTION"}
    if args.upload:
        from google.cloud import storage

        bucket = storage.Client().bucket(args.upload)
        for path, data in ((entry["path"], simple_bytes), (entry["fullPath"], full_bytes)):
            bucket.blob(path).upload_from_string(data, content_type="application/geo+json")
    if args.register:
        registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
        registry["layers"] = [x for x in registry["layers"] if not (x["iso3"] == iso and x["level"] == level)] + [entry]
        REGISTRY.write_text(json.dumps(registry, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(entry, indent=2, ensure_ascii=False))
    print(f"{len(full)} units; drawing copy {len(simple_bytes) / 1e6:.2f} MB", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
