"""Explicitly authorized synthetic Vertex acceptance run; local stores, no deployment.

python -m scripts.scoped_acceptance --allow-paid-calls --budget-usd 15
The daily ledger enforces a conservative admission cap below the authorization, leaving
headroom for provider-reported search usage that exceeds the estimate. Never reset its data.
"""

import argparse
import hashlib
import io
import json
import os
import shutil
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx
from docx import Document

BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parent


def run(args) -> None:
    if not args.allow_paid_calls or not 0 < args.budget_usd <= 15:
        raise SystemExit("Requires explicit --allow-paid-calls and a budget between 0 and the authorized $15.")
    data = BACKEND / ".trial" / "h13-live"
    out = ROOT / "audit-output" / "2026-10-13" / "real-acceptance"
    data.mkdir(parents=True, exist_ok=True)
    out.mkdir(parents=True, exist_ok=True)
    today = time.strftime("%Y-%m-%d", time.gmtime())
    historical = sum(sum(json.loads(p.read_text()).get(k, 0) for k in ("spent", "reserved"))
                     for p in (data / "ai-spend").glob("*.json") if p.stem != today)
    cap = max(0, min(6, args.budget_usd - 3) - historical)
    if cap <= 0:
        raise SystemExit("No authorized admission budget remains; no request made.")
    # Process-local fixture settings, never gcloud/Cloud Run or production environment changes.
    os.environ.update({"ENV": "local", "AUTH_MODE": "dev", "STORE_BACKEND": "local", "STORAGE_BACKEND": "local", "QUEUE_BACKEND": "local",
                       "DATA_DIR": str(data), "VERTEX_PROJECT": "paperaid", "VERTEX_LOCATION": "global", "GEMINI_WORKFLOW": "true",
                       "WORKFLOW": "1", "FINAL_EDITOR": "false", "METHODS_CONTRACT": "false", "LEGACY_PROVIDERS": "false",
                       "CREDITS_ENABLED": "true", "PRICING_MODE": "fixed", "WORKS_ENABLED": '["COURSEWORK","CONCEPT_NOTE","FUNDING_PROPOSAL"]',
                       "WORKS_PUBLIC": "false", "TESTER_EMAILS": '["audit-cw@example.com","audit-fp@example.com","audit-rp@example.com"]',
                       "ADMIN_EMAILS": '[]', "SENDGRID_API_KEY": "", "AFRICASTALKING_API_KEY": "", "ALERT_EMAIL": "", "CANARY_ENABLED": "false",
                       "QUEUE_CONCURRENCY": "4", "DAILY_AI_BUDGET_USD": str(cap), "AI_CHECK_ENABLED": "false", "PARTIAL_CHAPTERS": "false",
                       "LOG_LEVEL": "WARNING"})
    from google.auth import default
    from google.auth.transport.requests import Request

    credentials, _ = default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    if getattr(credentials, "quota_project_id", None) != "paperaid":
        raise SystemExit("ADC quota project is not paperaid; no model request made.")
    credentials.refresh(Request())  # authentication only; no inference
    identity = httpx.get("https://www.googleapis.com/oauth2/v3/userinfo", headers={"Authorization": "Bearer " + credentials.token}, timeout=20)
    if identity.status_code != 200 or identity.json().get("email") != "omodingisaac123@gmail.com":
        raise SystemExit("ADC identity could not be verified as the authorized account; no model request made.")
    print(json.dumps({"authentication": "ADC", "account": identity.json()["email"], "project": "paperaid", "location": "global", "admissionCap": cap}), flush=True)

    # Read the already-authorized application secret into this process only. Never echo it,
    # write it to disk or change the active CLI account/project or a production setting.
    if not os.environ.get("OPENALEX_API_KEY"):
        executable = shutil.which("gcloud")
        if executable:
            secret = subprocess.run([executable, "secrets", "versions", "access", "latest", "--secret=OPENALEX_API_KEY",
                                     "--project=paperaid-ca172", "--account=omodingisaac111@gmail.com", "--quiet"],
                                    capture_output=True, timeout=30, check=False)
            if secret.returncode == 0:
                os.environ["OPENALEX_API_KEY"] = secret.stdout.decode().strip()
    if not os.environ.get("OPENALEX_API_KEY"):
        raise SystemExit("The production-equivalent scholarly-index key is unavailable; no model request made.")

    flags = data / "flags.json"
    if flags.exists() and not (args.resume_funding or args.resume_chapter_three):
        raise SystemExit("This acceptance directory has already been used; review its budget and results before any rerun.")

    from fastapi.testclient import TestClient

    from app.core.config import get_settings
    from app.main import create_app
    from app.pricing import credits
    from app.runtime import get_runtime

    get_settings.cache_clear()
    get_runtime.cache_clear()
    runtime = get_runtime()
    if args.preflight_only:
        print(json.dumps({"preflight": "ready", "realCalls": 0, "workflow": runtime.settings.workflow,
                          "creditsEnabledLocally": runtime.settings.credits_enabled, "scholarlyKeyConfigured": bool(runtime.settings.openalex_api_key)}))
        runtime.queue.shutdown()
        return
    try:
        lock_name = (f"followup-{args.funding_round}.lock" if args.resume_funding or args.resume_chapter_three else "run.lock")
        if args.resume_funding and (not args.resume_funding.startswith("wrk_") or not args.resume_funding[4:].isalnum()):
            raise SystemExit("Invalid synthetic funding ID; no request made.")
        if (args.resume_funding or args.resume_chapter_three) and (not flags.exists() or json.loads(flags.read_text()).get("processing_enabled", True)):
            raise SystemExit("The previous acceptance process has not finished; no request made.")
        descriptor = os.open(data / lock_name, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        raise SystemExit("An acceptance lock already exists; inspect the previous run before starting another.") from None
    with os.fdopen(descriptor, "w") as lock:
        lock.write(str(os.getpid()))
    if args.resume_funding:
        previous = runtime.store.get_work(args.resume_funding)
        if (previous is None or previous.kind != "FUNDING_PROPOSAL" or previous.auto
                or any((j := runtime.store.get(jid)) is None or j.selection.work != "READ" or j.status != "COMPLETED" for jid in previous.jobs)):
            raise SystemExit("Funding follow-up requires the original unstarted synthetic work; no request made.")
        runtime.store.set_flag("processing_enabled", True)
    if args.resume_chapter_three:
        previous = runtime.store.get_project(args.resume_chapter_three)
        if previous is None or previous.owner_email != "audit-rp@example.com" or previous.chapter(3).current:
            raise SystemExit("Chapter Three follow-up requires the original synthetic project with no delivered Chapter Three.")
        runtime.store.set_flag("processing_enabled", True)
    for email in ("audit-cw@example.com", "audit-fp@example.com", "audit-rp@example.com"):
        uid = "u_" + hashlib.sha256(email.encode()).hexdigest()[:20]
        def accept(w):
            if not w.entries:
                w = credits.top_up(w, 1_000_000, "Synthetic test balance, no payment")
            w.terms_version = runtime.settings.terms_version
            w.notify_email, w.notify_sms = False, False
            return w
        runtime.store.update_wallet(uid, email, accept)

    progress_lock = threading.Lock()

    def summary() -> dict:
        jobs = [json.loads(p.read_text(encoding="utf-8")) for p in (data / "jobs").glob("*.json")]
        return {"costUsd": round(sum(j.get("costUsd", 0) for j in jobs), 6), "reservedUsd": round(sum(j.get("reservedUsd", 0) for j in jobs), 6),
                "jobs": [{"id": j["id"], "workId": j.get("workId"), "projectId": j.get("projectId"), "status": j["status"],
                          "step": j.get("selection", {}).get("work") or j.get("selection", {}).get("proposal"),
                          "costUsd": j.get("costUsd", 0), "reservedUsd": j.get("reservedUsd", 0), "billing": j.get("billing"),
                          "quote": {k: (j.get("quote") or {}).get(k) for k in ("amount", "budgetUsd", "ugxPerUsd", "pricingVersion")},
                          "failure": j.get("failure"), "failureDetail": j.get("failureDetail"),
                          "calls": [{k: c.get(k) for k in ("task", "model", "inputTokens", "outputTokens", "thinkingTokens", "costUsd", "reservedUsd", "errorCode", "latencyMs")} for c in j.get("modelCalls", [])]}
                         for j in jobs]}

    def request(client, email, method, path, **kwargs):
        r = client.request(method, path, headers={"Authorization": "Dev " + email}, **kwargs)
        if r.status_code != 200:
            raise RuntimeError(f"{method} {path}: {r.status_code} {r.text[:500]}")
        return r

    def wait_view(client, email, path, ready):
        deadline, last = time.monotonic() + 5400, None
        while time.monotonic() < deadline:
            last = request(client, email, "GET", path).json()
            with progress_lock:
                target = out / "spend-and-progress.json"
                temporary = target.with_suffix(".tmp")
                temporary.write_text(json.dumps(summary(), indent=2), encoding="utf-8")
                temporary.replace(target)
            if ready(last) or last.get("autoFailure"):
                return last
            time.sleep(5)
        raise RuntimeError("Acceptance wait exceeded 90 minutes; inspect saved local jobs, do not start a duplicate.")

    def work(client, kind):
        email = "audit-cw@example.com" if kind == "COURSEWORK" else "audit-fp@example.com"
        begun = time.monotonic()
        if kind == "COURSEWORK":
            question = "Compare qualitative and quantitative research approaches, giving one suitable study question for each and discussing two limitations of each approach."
            body = {"kind": kind, "variant": "ESSAY", "inputs": {"title": "Comparing research approaches", "description": question}}
            answers = {"word_limit": "1500", "level": "LATER_UG", "citation_style": "APA7"}
        else:
            body = {"kind": kind, "variant": "NGO_PROJECT", "mode": "COMPACT",
                    "inputs": {"title": "Synthetic digital-skills programme in Gulu", "description": "A synthetic test application for a twelve-month digital-skills programme for out-of-school young adults."}}
            answers = {"applicant": "Synthetic Learning Access NGO (fictional test organisation)", "geography": "Gulu City, Uganda", "amount_requested": "60000",
                       "duration_months": "12", "currency": "USD", "problem": "For this test, the applicant reports limited access to structured digital-skills training.",
                       "intervention": "Two consecutive three-month basic digital-skills cohorts, with follow-up inside a twelve-month programme."}
        view = (request(client, email, "GET", f"/api/works/{args.resume_funding}").json() if args.resume_funding
                else request(client, email, "POST", "/api/works", json=body).json())
        wid = view["id"]
        if kind == "FUNDING_PROPOSAL" and not args.resume_funding:
            doc = Document()
            for line in ("Synthetic Education Access Fund — TEST CALL, not a real funder", "Registered NGOs are eligible.", "Required sections: Background; Proposed intervention; Results; Workplan; Monitoring and evaluation; Budget; Sustainability.",
                         "Maximum grant USD 60,000. Programme duration twelve months. Maximum 3,000 words including references.", "Applicant: fictional Synthetic Learning Access NGO, established in 2019. All applicant histories and figures are artificial test inputs."):
                doc.add_paragraph(line)
            blob = io.BytesIO()
            doc.save(blob)
            request(client, email, "POST", f"/api/works/{wid}/sources", files={"file": ("synthetic-call.docx", blob.getvalue())}, data={"role": "CALL"})
        if kind == "FUNDING_PROPOSAL":
            request(client, email, "POST", f"/api/works/{wid}/read")
            wait_view(client, email, f"/api/works/{wid}", lambda w: not w.get("activeJob"))
        view = request(client, email, "GET", f"/api/works/{wid}").json()
        if args.confirm_call and kind == "FUNDING_PROPOSAL":
            # The synthetic call has been read by this operator; the test applicant is
            # deliberately eligible. This exercises the same confirmations as page 2.
            answers["confirm:all"] = "yes"
            answers.update({q["id"]: "yes" for q in view["spec"]["questions"] if q["id"].startswith("eligible:")})
            answers["legal_entity"] = "Registered NGO, fictional registration supplied solely for this test"
        request(client, email, "POST", f"/api/works/{wid}/answers", json={"answers": answers, "skipRest": True, "baseVersion": view["specVersion"]})
        request(client, email, "POST", f"/api/works/{wid}/start")
        view = wait_view(client, email, f"/api/works/{wid}", lambda w: bool(w.get("documents")))
        result = {"kind": kind, "id": wid, "minutes": round((time.monotonic() - begun) / 60, 2), "failure": view.get("autoFailure")}
        if view.get("documents"):
            document = request(client, email, "GET", f"/api/works/{wid}/document").json()
            result.update(words=document.get("words"), status=document.get("status"), readiness=document.get("readiness"))
            for suffix, route in (("docx", "export"), ("pdf", "export.pdf")):
                r = client.get(f"/api/works/{wid}/{route}", headers={"Authorization": "Dev " + email})
                result[route] = r.status_code
                if r.status_code == 200:
                    (out / f"{kind.lower()}.{suffix}").write_bytes(r.content)
        (out / f"{kind.lower()}.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(json.dumps({k: v for k, v in result.items() if k != "readiness"}), flush=True)
        return result

    def proposal(client):
        email, begun = "audit-rp@example.com", time.monotonic()
        body = {"inputs": {"topic": "Factors associated with use of electronic library resources among undergraduate students at Makerere University",
                           "level": "MASTERS", "programme": "Master of Information Science", "studyArea": "Makerere University, Kampala, Uganda",
                           "population": "Undergraduate students enrolled at the university", "populationSize": 400,
                           "populationSource": "Synthetic audit roster of 400 students; this is not a real university population figure"},
                "titlePage": {"studentName": "Synthetic Audit Student"}, "citation": "APA7"}
        view = (request(client, email, "GET", f"/api/projects/{args.resume_chapter_three}").json() if args.resume_chapter_three
                else request(client, email, "POST", "/api/projects", json=body).json())
        pid = view["id"]
        if not args.resume_chapter_three:
            request(client, email, "POST", f"/api/projects/{pid}/start", json={"acceptSampling": True})
            view = wait_view(client, email, f"/api/projects/{pid}", lambda p: any(c["number"] == 1 and c.get("current") for c in p["chapters"]))
        result = {"kind": "RESEARCH_PROPOSAL", "id": pid, "chapters": {}, "failure": view.get("autoFailure")}
        for number in ((3,) if args.resume_chapter_three else (1, 2, 3)):
            if result["failure"]:
                break
            if number > 1:
                if number == 3 and view.get("samplingConsent") is False:
                    request(client, email, "POST", f"/api/projects/{pid}/sampling", json={"baseVersion": view["planVersion"]})
                quoted = request(client, email, "POST", f"/api/projects/{pid}/steps", json={"step": f"CHAPTER_{number}"}).json()
                request(client, email, "POST", f"/api/projects/{pid}/steps/{quoted['job']['id']}/submit", json={"quoteId": quoted["quote"]["id"]})
                view = wait_view(client, email, f"/api/projects/{pid}", lambda p, number=number, job_id=quoted["job"]["id"]:
                                 any(c["number"] == number and c.get("current") for c in p["chapters"]) or
                                 (not p.get("activeJob") and any(j.status.value == "FAILED" for j in [runtime.store.get(job_id)] if j)))
            state = next(c for c in view["chapters"] if c["number"] == number)
            if not state.get("current"):
                result["failure"] = f"Chapter {number} was not delivered"
                break
            chapter = request(client, email, "GET", f"/api/projects/{pid}/chapters/{number}").json()
            result["chapters"][str(number)] = {"words": chapter.get("words"), "readiness": chapter.get("readiness"), "references": chapter.get("references")}
            request(client, email, "POST", f"/api/projects/{pid}/chapters/{number}", json={"version": state["current"], "approved": True})
            print(json.dumps({"project": pid, "chapter": number, "words": chapter.get("words")}), flush=True)
        if result["chapters"]:
            r = request(client, email, "GET", f"/api/projects/{pid}/export")
            (out / ("research-proposal-repaired.docx" if args.resume_chapter_three else "research-proposal.docx")).write_bytes(r.content)
        result["minutes"] = round((time.monotonic() - begun) / 60, 2)
        (out / ("research-proposal-repaired.json" if args.resume_chapter_three else "research-proposal.json")).write_text(json.dumps(result, indent=2), encoding="utf-8")
        return result

    try:
        with TestClient(create_app()) as client:
            with ThreadPoolExecutor(max_workers=3) as pool:
                cases = ({**({"funding": lambda: work(client, "FUNDING_PROPOSAL")} if args.resume_funding else {}),
                          **({"chapter_three": lambda: proposal(client)} if args.resume_chapter_three else {})} if args.resume_funding or args.resume_chapter_three else {
                    "coursework": lambda: work(client, "COURSEWORK"), "funding": lambda: work(client, "FUNDING_PROPOSAL"), "proposal": lambda: proposal(client)}
                         )
                futures = {name: pool.submit(fn) for name, fn in cases.items()}
                results = {}
                for name, future in futures.items():
                    try:
                        results[name] = future.result()
                    except Exception as exc:
                        results[name] = {"failure": f"{type(exc).__name__}: {str(exc)[:700]}"}
    finally:
        # Fence unfinished synthetic attempts before waiting for the current SDK calls to end.
        # Never leave a paid local worker running after this script reports completion.
        from app.jobs.models import JobFailure, JobStatus
        from app.pricing.billing import refund_job

        runtime.store.set_flag("processing_enabled", False)
        for path in (data / "jobs").glob("*.json"):
            job = json.loads(path.read_text(encoding="utf-8"))
            if job["status"] not in ("QUEUED", "PROCESSING", "AWAITING_PAYMENT"):
                continue
            def stop(j, wallet):
                j.status, j.lease_owner = JobStatus.CANCELLED, ""
                j.failure = JobFailure(code="TEST_STOPPED", user_message="Synthetic acceptance run ended.", retryable=False)
                refund_job(j, wallet, "Synthetic acceptance stopped; no delivery")
                return j, wallet
            runtime.store.update_job_and_wallet(job["id"], stop)
        runtime.queue._pool.shutdown(wait=True, cancel_futures=True)

    if results:
        final = {"results": results, "spend": summary(), "authorizationUsd": args.budget_usd, "admissionCapUsd": cap,
                 "scope": "Synthetic local app, real Vertex; no production data or configuration changes"}
        (out / (f"followup-{args.funding_round}-final.json" if args.resume_funding or args.resume_chapter_three else "final.json")).write_text(json.dumps(final, indent=2), encoding="utf-8")
        print(json.dumps({"costUsd": final["spend"]["costUsd"], "reservedUsd": final["spend"]["reservedUsd"], "results": {k: v.get("failure") for k, v in results.items()}}), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--allow-paid-calls", action="store_true")
    parser.add_argument("--budget-usd", type=float, required=True)
    parser.add_argument("--preflight-only", action="store_true")
    parser.add_argument("--resume-funding", default="")
    parser.add_argument("--resume-chapter-three", default="")
    parser.add_argument("--funding-round", type=int, default=1)
    parser.add_argument("--confirm-call", action="store_true")
    run(parser.parse_args())
