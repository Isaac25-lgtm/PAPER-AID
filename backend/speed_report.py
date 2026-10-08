r"""Read-only speed report (speed plan 2026-10-08): where jobs spend their time, from the records every job keeps.

Per task and model: how many calls, their time (median, 90th percentile, slowest), how long they waited for a slot
under the shared limit, and how many timed out or were refused for too many requests. Per stage: how long it ran and
waited in the queue. Per kind of job: completion at the first try and in the end (provider outages included), and
the time to a result. Prints numbers only, never paper text, names or credentials. Changes nothing.

    .venv\Scripts\python.exe speed_report.py --since 2026-10-08              (the cloud, signed in with gcloud)
    .venv\Scripts\python.exe speed_report.py --local .data --since 2026-10-08
"""

import argparse
import json
import statistics
from datetime import datetime
from pathlib import Path

from cost_report import cloud_jobs, local_jobs


def _spread(values: list[float]) -> dict | None:
    values = sorted(values)
    if not values:
        return None
    p90 = values[min(len(values) - 1, int(round(0.9 * (len(values) - 1))))]
    return {"n": len(values), "median": round(statistics.median(values), 1), "p90": round(p90, 1), "max": round(values[-1], 1)}


def _seconds(start: str, end: str) -> float:
    return (datetime.fromisoformat(str(end).replace("Z", "+00:00")) - datetime.fromisoformat(str(start).replace("Z", "+00:00"))).total_seconds()


def report(jobs: list[dict]) -> dict:
    calls: dict[str, dict[str, list]] = {}
    stages: dict[str, dict[str, list]] = {}
    kinds: dict[str, dict[str, list]] = {}
    for job in jobs:
        for call in job.get("modelCalls") or []:
            group = calls.setdefault(f"{call.get('task') or '-'} · {call.get('model') or '-'}", {"time": [], "waited": [], "timeouts": [], "busy": []})
            group["time"].append(float(call.get("latencyMs") or 0) / 1000)
            group["waited"].append(float(call.get("queuedMs") or 0) / 1000)
            code = call.get("errorCode") or ""
            group["timeouts"].append(code in ("VERTEX_TIMEOUT", "VERTEX_CONNECTION_LOST"))
            group["busy"].append(code == "VERTEX_RATE_LIMIT")
        for timing in job.get("timings") or []:
            group = stages.setdefault(timing.get("stage") or "-", {"ran": [], "queued": [], "outcomes": []})
            group["ran"].append(_seconds(timing["startedAt"], timing["endedAt"]))
            group["queued"].append(float(timing.get("queuedMs") or 0) / 1000)
            group["outcomes"].append(timing.get("outcome") or "")
        selection = job.get("selection") or {}
        kind = next((v for v in (selection.get("proposal"), selection.get("work"), selection.get("datalab"), selection.get("writing")) if v and v != "NONE"), "-")
        if job.get("status") not in ("COMPLETED", "FAILED", "CANCELLED"):
            continue
        group = kinds.setdefault(kind, {"first": [], "eventual": [], "minutes": []})
        # first try: no stage was retried or paused, and no call was lost and asked again (Codex audit, finding 12)
        retried = (any(t.get("outcome") in ("RETRY", "WAITING") for t in job.get("timings") or [])
                   or any(c.get("errorCode") for c in job.get("modelCalls") or []))
        group["eventual"].append(job.get("status") == "COMPLETED")
        group["first"].append(job.get("status") == "COMPLETED" and not retried)
        if job.get("status") == "COMPLETED" and job.get("queuedAt") and job.get("completedAt"):
            group["minutes"].append(_seconds(job["queuedAt"], job["completedAt"]) / 60)
    return {
        "calls": {name: {"seconds": _spread(g["time"]), "waitedForSlot": _spread([w for w in g["waited"] if w > 0]),
                         "timeouts": sum(g["timeouts"]), "tooManyRequests": sum(g["busy"])} for name, g in sorted(calls.items())},
        "stages": {name: {"ranSeconds": _spread(g["ran"]), "queuedSeconds": _spread(g["queued"]),
                          "outcomes": {o: g["outcomes"].count(o) for o in sorted(set(g["outcomes"]))}} for name, g in sorted(stages.items())},
        "jobs": {name: {"finished": len(g["eventual"]), "completedFirstTry": sum(g["first"]), "completedInTheEnd": sum(g["eventual"]),
                        "minutesToResult": _spread(g["minutes"])} for name, g in sorted(kinds.items())},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--since", required=True, help="first day to include, YYYY-MM-DD")
    parser.add_argument("--local", type=Path, help="a local data folder instead of the cloud")
    parser.add_argument("--project", default="paperaid-ca172")
    args = parser.parse_args()
    jobs = [j for j in (local_jobs(args.local) if args.local else cloud_jobs(args.project)) if str(j.get("createdAt", "")) >= args.since]
    print(json.dumps(report(jobs), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
