"""Load test: many simulated students using the API at once, with latency percentiles per request.

    python -m tests.load_test --base http://127.0.0.1:8000 --students 40 --rounds 3 [--submit]

Each student opens the config, creates a draft, uploads a fixture paper, gets a formatting quote
and lists their jobs; with --submit it also starts the formatting job, which is code only (no AI is
ever called, so a run costs nothing). It needs a backend with dev sign-in (local, or the
browser-test backend `python -m tests.serve_e2e`); production sign-in and App Check are not
simulated. --submit needs credits off (CREDITS_ENABLED=false) or tokens on the load accounts, or
every submit is refused with 402. The local backend keeps its store in files behind one lock, so
its latencies are an upper bound, not a prediction for Cloud Run and Firestore. Failures are
printed; the exit code is 1 on any failure."""

import argparse
import statistics
import threading
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed

import httpx

from tests.conftest import fixture_bytes

FORMAT = {"writing": "NONE", "formatting": "FORMAT", "preset": "apa7", "latex": False}


class Recorder:
    def __init__(self) -> None:
        self.times: dict[str, list[float]] = defaultdict(list)
        self.failures: list[str] = []
        self._lock = threading.Lock()

    def call(self, client: httpx.Client, name: str, method: str, url: str, **kwargs) -> httpx.Response | None:
        start = time.perf_counter()
        try:
            response = client.request(method, url, **kwargs)
        except httpx.HTTPError as exc:  # a timeout or refused connection is a result to report
            with self._lock:
                self.failures.append(f"{name}: {type(exc).__name__}")
            return None
        elapsed = time.perf_counter() - start
        with self._lock:
            self.times[name].append(elapsed)
            if response.status_code >= 400:
                self.failures.append(f"{name}: HTTP {response.status_code} {response.text[:120]}")
        return response


def student(base: str, n: int, rounds: int, submit: bool, rec: Recorder) -> None:
    headers = {"Authorization": f"Dev load{n}@example.com"}
    paper = fixture_bytes("simple_essay.docx")
    with httpx.Client(base_url=base, headers=headers, timeout=60) as client:
        rec.call(client, "config", "GET", "/api/config")
        for _ in range(rounds):
            draft = rec.call(client, "create draft", "POST", "/api/jobs")
            if draft is None or draft.status_code != 200:
                continue
            job_id = draft.json()["id"]
            files = {"file": ("essay.docx", paper, "application/octet-stream")}
            if (up := rec.call(client, "upload", "POST", f"/api/jobs/{job_id}/files/source", files=files)) is None or up.status_code != 200:
                continue
            quoted = rec.call(client, "quote", "POST", f"/api/jobs/{job_id}/quote", json={"selection": FORMAT})
            if submit and quoted is not None and quoted.status_code == 200 and quoted.json().get("quote"):
                rec.call(client, "submit", "POST", f"/api/jobs/{job_id}/submit", json={"quoteId": quoted.json()["quote"]["id"]})
            rec.call(client, "list jobs", "GET", "/api/jobs")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--base", default="http://127.0.0.1:8000")  # not "localhost": Windows tries IPv6 first (~200 ms a connection)
    parser.add_argument("--students", type=int, default=20)
    parser.add_argument("--rounds", type=int, default=2)
    parser.add_argument("--submit", action="store_true", help="also start each formatting job (code only)")
    args = parser.parse_args()
    rec = Recorder()
    start = time.perf_counter()
    with ThreadPoolExecutor(max_workers=args.students) as pool:
        futures = {pool.submit(student, args.base, n, args.rounds, args.submit, rec): n for n in range(args.students)}
        for future in as_completed(futures):
            error = future.exception()  # a journey that crashed outside a request is a failure too (Codex audit 56c4f83 L29)
            if error is not None:
                rec.failures.append(f"student {futures[future]}: {type(error).__name__}: {error}")
    total = time.perf_counter() - start
    requests = sum(len(t) for t in rec.times.values())
    print(f"{args.students} students x {args.rounds} rounds: {requests} requests in {total:.1f}s ({requests / total:.1f}/s)")
    print(f"{'request':<14}{'n':>6}{'p50 ms':>10}{'p95 ms':>10}{'max ms':>10}")
    for name, times in rec.times.items():
        ordered = sorted(times)
        p95 = ordered[min(len(ordered) - 1, int(len(ordered) * 0.95))]
        print(f"{name:<14}{len(times):>6}{statistics.median(times) * 1000:>10.0f}{p95 * 1000:>10.0f}{ordered[-1] * 1000:>10.0f}")
    if rec.failures:
        print(f"\n{len(rec.failures)} failures, for example:")
        for failure in list(dict.fromkeys(rec.failures))[:10]:
            print(" ", failure)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
