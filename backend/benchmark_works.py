r"""Measures what the work services really cost, so the owner can set their token prices (B8). PAID:
it runs real work steps with the configured models on cases the owner supplies, in a throwaway local
data folder, with credits off (nothing charged to anyone). Prints numbers only, never text.

Each case is a JSON file in the folder:
    {"kind": "COURSEWORK", "variant": "ESSAY", "mode": "", "title": "...", "description": "the question",
     "answers": {"word_limit": "2000", "level": "LATER_UG", "ai_policy": "NOT_MENTIONED"},
     "experience": "", "sources": [{"role": "BRIEF", "file": "brief.pdf"}],
     "results": {...Results Model with the applicant's targets...}, "budget": {...lines with quantities and costs...}}
A funding proposal is drafted only when the case gives its Results Model and budget: PaperAid never
supplies an applicant's targets or costs, and neither does this tool.

    .venv\Scripts\python.exe benchmark_works.py CASES_FOLDER --budget-usd 25
"""

import argparse
import json
import os
import statistics
import sys
import tempfile
import time
from pathlib import Path

STEPS = ("READ", "PLAN", "DRAFT")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("cases", type=Path)
    parser.add_argument("--budget-usd", type=float, required=True, help="stop once this much has been spent in total")
    parser.add_argument("--margin", type=float, default=2.0, help="price = measured worst spend x this")
    args = parser.parse_args()
    if not all(os.environ.get(k) for k in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GEMINI_API_KEY")):
        print("Set OPENAI_API_KEY, ANTHROPIC_API_KEY and GEMINI_API_KEY first.", file=sys.stderr)
        return 1
    data = Path(tempfile.mkdtemp(prefix="paperaid-bench-"))
    os.environ.update({"DATA_DIR": str(data), "CREDITS_ENABLED": "false", "PRICING_MODE": "cost", "QUOTES_PER_HOUR": "1000", "SUBMITS_PER_HOUR": "1000",
                       "WORKS_ENABLED": '["CONCEPT_NOTE","COURSEWORK","FUNDING_PROPOSAL"]', "UPLOADS_PER_HOUR": "1000", "LOG_LEVEL": "ERROR"})
    from fastapi.testclient import TestClient

    from app.main import create_app
    from app.runtime import get_runtime

    headers = {"Authorization": "Dev benchmark@paperaid.app"}
    rows: list[dict] = []
    spent = 0.0
    with TestClient(create_app()) as client:
        rt = get_runtime()

        def wait(job_id: str) -> dict:
            while True:
                job = client.get(f"/api/jobs/{job_id}", headers=headers).json()
                if job["status"] in ("COMPLETED", "FAILED", "CANCELLED"):
                    return job
                time.sleep(2)

        def run(work_id: str, step: str, case: str) -> bool:
            nonlocal spent
            quoted = client.post(f"/api/works/{work_id}/steps", headers=headers, json={"step": step, "note": ""})
            if quoted.status_code != 200:
                rows.append({"case": case, "step": step, "refused": quoted.json().get("code")})
                return False
            body = quoted.json()
            client.post(f"/api/works/{work_id}/steps/{body['job']['id']}/submit", headers=headers, json={"quoteId": body["quote"]["id"]})
            job = wait(body["job"]["id"])
            stored = rt.store.get(body["job"]["id"])
            spent += stored.cost_usd
            rows.append({"case": case, "step": step, "band": stored.selection.work_band, "status": job["status"], "failure": (job.get("failure") or {}).get("code"),
                         "spendUsd": round(stored.cost_usd, 4), "capUsd": round(stored.budget_usd, 4), "calls": len(stored.model_calls),
                         "byRole": {c.role: round(sum(x.cost_usd for x in stored.model_calls if x.role == c.role), 4) for c in stored.model_calls}})
            return job["status"] == "COMPLETED"

        for path in sorted(args.cases.glob("*.json")):
            if spent >= args.budget_usd:
                print(f"Stopped at the budget: {spent:.2f} USD spent.", file=sys.stderr)
                break
            case = json.loads(path.read_text(encoding="utf-8"))
            inputs = {"title": case["title"], "description": case.get("description", ""), "answers": case.get("answers", {}), "experience": case.get("experience", "")}
            work = client.post("/api/works", headers=headers, json={"kind": case["kind"], "variant": case["variant"], "mode": case.get("mode", ""), "inputs": inputs}).json()
            for source in case.get("sources", []):
                file = path.parent / source["file"]
                client.post(f"/api/works/{work['id']}/sources", headers=headers, data={"role": source["role"]}, files={"file": (file.name, file.read_bytes())})
            if case.get("sources") and not run(work["id"], "READ", path.stem):
                continue
            work = client.get(f"/api/works/{work['id']}", headers=headers).json()
            confirm = {q["id"]: "yes" for q in work["spec"]["questions"] if q["id"].startswith(("confirm:", "eligible:"))}
            work = client.post(f"/api/works/{work['id']}/answers", headers=headers, json={"answers": confirm, "skipRest": True, "baseVersion": work["specVersion"]}).json()
            work = client.post(f"/api/works/{work['id']}/spec/confirm", headers=headers, json={"baseVersion": work["specVersion"]}).json()
            if not run(work["id"], "PLAN", path.stem):
                continue
            work = client.get(f"/api/works/{work['id']}", headers=headers).json()
            client.post(f"/api/works/{work['id']}/plan/approve", headers=headers, json={"baseVersion": work["planVersion"]})
            if case["kind"] == "FUNDING_PROPOSAL":
                if "results" not in case or "budget" not in case:
                    rows.append({"case": path.stem, "step": "DRAFT", "refused": "the case gives no Results Model or budget"})
                    continue
                work = client.get(f"/api/works/{work['id']}", headers=headers).json()
                work = client.post(f"/api/works/{work['id']}/results", headers=headers, json={"results": case["results"], "baseVersion": work["resultsVersion"]}).json()
                work = client.post(f"/api/works/{work['id']}/results/approve", headers=headers, json={"baseVersion": work["resultsVersion"]}).json()
                client.post(f"/api/works/{work['id']}/budget", headers=headers, json={"budget": case["budget"], "baseVersion": work["budgetVersion"]})
            run(work["id"], "DRAFT", path.stem)

    by_band: dict[str, list[float]] = {}
    for r in rows:
        if r.get("status") == "COMPLETED":
            by_band.setdefault(r["band"], []).append(r["spendUsd"])
    rate = float(os.environ.get("UGX_PER_USD", "4000"))
    suggestions = {
        band: {"n": len(v), "medianUsd": round(statistics.median(v), 4), "maxUsd": round(max(v), 4),
               "tokensAtMargin": round(max(v) * args.margin * rate / 1000, 1)}
        for band, v in sorted(by_band.items())
    }
    print(json.dumps({"spentUsd": round(spent, 2), "rows": rows, "byBand": suggestions,
                      "note": "tokensAtMargin = the worst measured spend x margin, in tokens. A few cases estimate cost; they do not establish quality."}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
