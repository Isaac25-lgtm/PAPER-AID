r"""Read-only cost report: what jobs cost PaperAid in AI spend against what students paid.

Counts every job with AI spend, including failed and refunded ones and estimates that were never
bought: those costs are PaperAid's too (Codex plan review 2026-09-29). Prints numbers only, never
paper text, names or credentials. No AI calls, job changes or refunds are made.

    .venv\Scripts\python.exe cost_report.py --since 2026-09-29            (the cloud, signed in with gcloud)
    .venv\Scripts\python.exe cost_report.py --local .data --since 2026-09-29   (a local data folder)
"""

import argparse
import json
import statistics
import subprocess
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen


def decode(value):
    if "mapValue" in value:
        return {k: decode(v) for k, v in value["mapValue"].get("fields", {}).items()}
    if "arrayValue" in value:
        return [decode(v) for v in value["arrayValue"].get("values", [])]
    if "integerValue" in value:
        return int(value["integerValue"])
    if "doubleValue" in value:
        return float(value["doubleValue"])
    return next(iter(value.values()), None)


def cloud_jobs(project: str):
    auth = subprocess.run(["gcloud.cmd", "auth", "print-access-token"], capture_output=True, text=True, check=False)
    if auth.returncode or not auth.stdout.strip():
        raise SystemExit("Google sign-in could not provide access. Run this in your normal signed-in terminal.")
    token = auth.stdout.strip()
    page_token = None
    while True:
        query = {"pageSize": 300, **({"pageToken": page_token} if page_token else {})}
        url = f"https://firestore.googleapis.com/v1/projects/{quote(project, safe='')}/databases/(default)/documents/jobs?{urlencode(query)}"
        with urlopen(Request(url, headers={"Authorization": "Bearer " + token}), timeout=60) as response:
            page = json.load(response)
        for doc in page.get("documents", []):
            yield {k: decode(v) for k, v in doc.get("fields", {}).items()}
        page_token = page.get("nextPageToken")
        if not page_token:
            return


def local_jobs(folder: Path):
    for path in sorted((folder / "jobs").glob("*.json")):
        yield json.loads(path.read_text(encoding="utf-8"))


def row(job: dict, default_rate: float) -> dict:
    quote_ = job.get("quote") or {}
    # each quote froze its own exchange rate: spend is compared with the price at that rate (Codex review #8)
    ugx_per_usd = float(quote_.get("ugxPerUsd") or 0) or default_rate
    billing = job.get("billing") or {}
    selection = job.get("selection") or {}
    services = [line.get("service") for line in quote_.get("lines", []) if line.get("service")]
    spend = float(job.get("costUsd") or 0)
    price = int(quote_.get("amount") or 0)
    charged = int(billing.get("charged") or 0)
    status = job.get("status")
    return {
        "id": job.get("id"),
        "created": str(job.get("createdAt", ""))[:19],
        "services": "+".join(services) or next((v for v in (selection.get("proposal"), selection.get("writing")) if v and v != "NONE"), "-"),
        "status": status,
        "outcome": job.get("outcome"),
        "failure": (job.get("failure") or {}).get("code"),
        "words": (job.get("source") or {}).get("wordCount"),
        "priceUgx": price,
        "chargedUgx": charged,
        "spendUsd": round(spend, 4),
        "spendUgx": round(spend * ugx_per_usd),
        "ugxPerUsd": ugx_per_usd,
        "estimateSpendUsd": round(float(job.get("estimateCostUsd") or 0), 4),
        # the spend as a share of what the job was priced at, and of what was actually charged
        "spendOfPrice": round(spend * ugx_per_usd / price, 3) if price else None,
        "spendOfCharge": round(spend * ugx_per_usd / charged, 3) if charged else None,
        "lostUgx": round(spend * ugx_per_usd) if status in ("FAILED", "CANCELLED") or (spend and not charged) else 0,
        # spend by who made each call (lead, writer, or a works role such as WRITER or EVALUATOR_PREMIUM), and by step
        "byRole": _sum(job, "role"),
        "byTask": _sum(job, "task"),
    }


def _sum(job: dict, key: str) -> dict:
    out: dict[str, float] = {}
    for call in job.get("modelCalls") or []:
        name = call.get(key) or "-"
        out[name] = round(out.get(name, 0.0) + float(call.get("costUsd") or 0), 6)
    return out


def summary(rows: list[dict]) -> dict:
    def spread(values):
        values = sorted(v for v in values if v is not None)
        if not values:
            return None
        p90 = values[min(len(values) - 1, int(round(0.9 * (len(values) - 1))))]
        return {"n": len(values), "median": round(statistics.median(values), 3), "p90": round(p90, 3), "max": round(values[-1], 3)}

    by_service: dict[str, list[dict]] = {}
    for r in rows:
        by_service.setdefault(r["services"], []).append(r)
    return {
        "jobs": len(rows),
        "spendUsd": round(sum(r["spendUsd"] for r in rows), 2),
        "chargedUgx": sum(r["chargedUgx"] for r in rows),
        "lostUgx": sum(r["lostUgx"] for r in rows),  # AI spend on jobs that brought in nothing
        "spendByRoleUsd": _merge(r["byRole"] for r in rows),
        "spendByTaskUsd": _merge(r["byTask"] for r in rows),
        "byService": {
            name: {
                "jobs": len(group),
                "failed": sum(1 for r in group if r["status"] == "FAILED"),
                "spendUsd": spread([r["spendUsd"] for r in group]),
                "spendOfPrice": spread([r["spendOfPrice"] for r in group]),
                "spendOfCharge": spread([r["spendOfCharge"] for r in group]),
            }
            for name, group in sorted(by_service.items())
        },
    }


def _merge(parts) -> dict:
    total: dict[str, float] = {}
    for part in parts:
        for name, usd in part.items():
            total[name] = round(total.get(name, 0.0) + usd, 4)
    return dict(sorted(total.items(), key=lambda kv: -kv[1]))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--since", default="", help="only jobs created on or after this date (YYYY-MM-DD)")
    parser.add_argument("--local", type=Path, help="a local data folder instead of the cloud")
    parser.add_argument("--project", default="paperaid-ca172")
    parser.add_argument("--ugx-per-usd", type=float, default=4000, help="only for jobs without a quote (each quote froze its own rate)")
    parser.add_argument("--rows", action="store_true", help="also print one line per job")
    args = parser.parse_args()
    try:
        jobs = list(local_jobs(args.local) if args.local else cloud_jobs(args.project))
    except HTTPError as error:
        print(f"Cloud read returned HTTP {error.code}; check the signed-in account's read access.", file=sys.stderr)
        return 1
    except (URLError, OSError):
        print("Cloud connection failed. Run from your normal terminal with network access.", file=sys.stderr)
        return 1
    rows = [row(j, args.ugx_per_usd) for j in jobs if str(j.get("createdAt", "")) >= args.since and float(j.get("costUsd") or 0) > 0]
    out = {"summary": summary(rows), **({"rows": rows} if args.rows else {})}
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
