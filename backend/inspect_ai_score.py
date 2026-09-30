r"""Read-only cloud diagnostic. Prints scoring metadata, never paper wording or credentials.

Run from a normal signed-in terminal: .venv\Scripts\python.exe inspect_ai_score.py job_8a5808635e3e
No AI calls, job changes, refunds or account changes are made.
"""

import argparse
import collections
import json
import re
import subprocess
import sys
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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("job_id")
    parser.add_argument("--project", default="paperaid-ca172")
    parser.add_argument("--bucket", default="paperaid-ca172-papers")
    args = parser.parse_args()
    if not re.fullmatch(r"job_[a-z0-9]+", args.job_id):
        parser.error("Invalid job ID")
    auth = subprocess.run(["gcloud.cmd", "auth", "print-access-token"], capture_output=True, text=True, check=False)
    if auth.returncode or not auth.stdout.strip():
        print("Google sign-in could not provide access. Run this in your normal signed-in terminal.", file=sys.stderr)
        return 1
    token = auth.stdout.strip()

    def get(url):
        request = Request(url, headers={"Authorization": "Bearer " + token})
        with urlopen(request, timeout=45) as response:
            return json.load(response)

    def file(name):
        return get(f"https://storage.googleapis.com/storage/v1/b/{quote(args.bucket, safe='')}/o/{quote(name, safe='')}?alt=media")

    try:
        record = get(f"https://firestore.googleapis.com/v1/projects/{quote(args.project, safe='')}/databases/(default)/documents/jobs/{args.job_id}")
        job = {k: decode(v) for k, v in record.get("fields", {}).items()}
        prefix = f"users/{job['ownerUid']}/jobs/{args.job_id}/internal/"
        saved, document = file(prefix + "analysis.json"), file(prefix + "document.json")
        scores, models = saved.get("scores", {}), saved.get("modelScores", {})
        weights = {b["id"]: len(b["text"].split()) for b in document.get("blocks", [])}
        eligible_words = sum(weights.get(bid, 0) for bid in scores)
        total = sum((0.5 * score + 0.5 * models[bid] if bid in models else score) * weights.get(bid, 0) for bid, score in scores.items())
        cached_bands = collections.Counter()
        explicit_ids = set()
        empty_responses = 0
        page_token = None
        while True:
            query = {"prefix": prefix + "calls/", "maxResults": 1000}
            if page_token:
                query["pageToken"] = page_token
            page = get(f"https://storage.googleapis.com/storage/v1/b/{quote(args.bucket, safe='')}/o?{urlencode(query)}")
            for item in page.get("items", []):
                answer = file(item["name"])
                blocks = answer.get("blocks") if isinstance(answer, dict) else None
                if blocks == []:
                    empty_responses += 1  # empty responses cannot be identified as analysis by shape alone
                for b in blocks or []:
                    if b.get("riskBand") in ("low", "moderate", "high"):
                        cached_bands[b["riskBand"]] += 1
                        explicit_ids.add(b["id"])
            page_token = page.get("nextPageToken")
            if not page_token:
                break
        result = job.get("analysis") or {}
        output = {
            "jobId": args.job_id, "status": job.get("status"), "writingService": job.get("selection", {}).get("writing"),
            "band": result.get("band"), "percent": result.get("percent"), "confidence": result.get("confidence"),
            "algorithmVersion": result.get("algorithmVersion"), "coverageComplete": result.get("coverageComplete"),
            "eligiblePassages": len(scores), "eligibleWords": eligible_words, "excludedWords": result.get("excludedWords"),
            "savedModelScores": len(models), "explicitCachedJudgmentIds": len(explicit_ids & set(scores)),
            "omittedPassages": len(set(scores) - explicit_ids),  # counted as LOW by engines before explicit coverage
            "cachedJudgmentBands": dict(cached_bands), "emptyCachedResponsesOfUnknownTask": empty_responses,
            "reconstructedPercent": int(100 * total / eligible_words + 1e-9) if eligible_words else None,
            "ruleScoreMean": sum(v * weights.get(bid, 0) for bid, v in scores.items()) / eligible_words if eligible_words else None,
            "findingCount": len(result.get("findings", [])),
            # inputTokens is uncached input only; cache writes and reads are listed beside it
            "analysisCalls": [
                {k: c.get(k) for k in ("provider", "model", "promptVersion", "phase", "inputTokens", "cacheWriteTokens", "cachedTokens", "outputTokens", "costUsd")}
                for c in job.get("modelCalls", [])
                if str(c.get("promptVersion", "")).startswith("analyse-")
            ],
            "callHistoryCapped": len(job.get("modelCalls", [])) >= 200,  # the job keeps its latest 200 calls only
        }
        print(json.dumps(output, indent=2))
        return 0
    except HTTPError as error:
        print(f"Cloud read returned HTTP {error.code}; check the signed-in account's read access and the bucket name.", file=sys.stderr)
    except (URLError, OSError):
        print("Cloud connection failed. Run from your normal terminal with network access.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
