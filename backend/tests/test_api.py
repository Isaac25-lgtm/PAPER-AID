import io
import json
import logging
import re
import time

from tests.conftest import fixture_bytes, grant, internal

STUDENT = {"Authorization": "Dev student@example.com"}
OTHER = {"Authorization": "Dev other@example.com"}
ADMIN = {"Authorization": "Dev demo@paperaid.app"}
REFINE_FORMAT = {"writing": "REFINE", "intensity": "STANDARD", "formatting": "FORMAT", "preset": "apa7", "latex": False}


def enable_score() -> None:
    """Opt a score-specific regression into the internal calibration display."""
    from app.runtime import get_runtime

    get_runtime().settings.show_ai_score = True


def start_job(client, name="simple_essay.docx", selection=None, headers=STUDENT):
    job_id = client.post("/api/jobs", headers=headers).json()["id"]
    upload = client.post(f"/api/jobs/{job_id}/files/source", headers=headers, files={"file": (name, fixture_bytes(name), "application/octet-stream")})
    assert upload.status_code == 200, upload.json()
    return job_id, get_quote(client, job_id, selection or REFINE_FORMAT, headers)


def get_quote(client, job_id, selection, headers=STUDENT, timeout=120):
    """A quote, waiting for the refinement estimate when the selection needs one."""
    response = client.post(f"/api/jobs/{job_id}/quote", headers=headers, json={"selection": selection, "startEstimate": True})
    body = response.json()
    assert response.status_code == 200, body
    if body.get("quote"):
        return body["quote"]
    deadline = time.time() + timeout
    while time.time() < deadline:
        job = client.get(f"/api/jobs/{job_id}", headers=headers).json()
        if job["estimate"]["status"] == "READY":
            return job["quote"]
        assert job["estimate"]["status"] == "RUNNING", job["estimate"]
        time.sleep(0.2)
    raise AssertionError("estimate did not finish")


def wait(client, job_id, headers=STUDENT, timeout=60):
    deadline = time.time() + timeout
    while time.time() < deadline:
        job = client.get(f"/api/jobs/{job_id}", headers=headers).json()
        if job["status"] in ("COMPLETED", "FAILED", "CANCELLED"):
            return job
        time.sleep(0.3)
    raise AssertionError("job did not finish")


def test_requests_without_identity_are_rejected(client):
    assert client.post("/api/jobs").status_code == 401
    assert client.get("/api/jobs").status_code == 401
    assert client.get("/api/admin/summary", headers=STUDENT).status_code == 403


def test_full_job_produces_downloadable_outputs(client):
    job_id, quote = start_job(client)
    assert client.post(f"/api/jobs/{job_id}/submit", headers=STUDENT, json={"quoteId": quote["id"]}).status_code == 200
    job = wait(client, job_id)
    assert job["status"] == "COMPLETED" and job["paymentStatus"] == "PAID" and job["billing"]["state"] == "SETTLED"
    assert {o["id"] for o in job["outputs"]} == {"paper", "writing-report", "change-report"}
    download = client.get(f"/api/jobs/{job_id}/outputs/paper", headers=STUDENT)
    assert download.status_code == 200 and download.content[:2] == b"PK"


def test_other_users_cannot_see_or_touch_a_job(client):
    job_id, quote = start_job(client)
    for response in (
        client.get(f"/api/jobs/{job_id}", headers=OTHER),
        client.post(f"/api/jobs/{job_id}/submit", headers=OTHER, json={"quoteId": quote["id"]}),
        client.post(f"/api/jobs/{job_id}/cancel", headers=OTHER),
        client.get(f"/api/jobs/{job_id}/outputs/paper", headers=OTHER),
    ):
        assert response.status_code == 404
    assert client.get("/api/jobs", headers=OTHER).json()["items"] == []


def test_double_submit_creates_one_job(client):
    job_id, quote = start_job(client)
    first = client.post(f"/api/jobs/{job_id}/submit", headers=STUDENT, json={"quoteId": quote["id"]}).json()
    second = client.post(f"/api/jobs/{job_id}/submit", headers=STUDENT, json={"quoteId": quote["id"]}).json()
    assert first["id"] == second["id"]
    job = wait(client, job_id)
    admin = client.get(f"/api/admin/jobs/{job_id}", headers=ADMIN).json()
    assert [e["label"] for e in admin["events"]].count("Processing started") == 1
    assert job["status"] == "COMPLETED"


def test_replacing_the_file_invalidates_the_quote(client):
    job_id, quote = start_job(client)
    client.post(f"/api/jobs/{job_id}/files/source", headers=STUDENT, files={"file": ("x.docx", fixture_bytes("fake_headings.docx"), "application/octet-stream")})
    response = client.post(f"/api/jobs/{job_id}/submit", headers=STUDENT, json={"quoteId": quote["id"]})
    assert response.status_code == 409 and response.json()["code"] == "QUOTE_MISMATCH"


def test_client_cannot_choose_the_price(client):
    job_id, quote = start_job(client)
    response = client.post(f"/api/jobs/{job_id}/quote", headers=STUDENT, json={"selection": REFINE_FORMAT, "amount": 1})
    assert response.json()["quote"]["amount"] == quote["amount"] > 1


def test_pdf_is_ai_check_only_and_bad_files_are_rejected(client):
    job_id = client.post("/api/jobs", headers=STUDENT).json()["id"]
    client.post(f"/api/jobs/{job_id}/files/source", headers=STUDENT, files={"file": ("p.pdf", fixture_bytes("text_based.pdf"), "application/pdf")})
    refused = client.post(f"/api/jobs/{job_id}/quote", headers=STUDENT, json={"selection": REFINE_FORMAT})
    assert refused.json()["code"] == "PDF_AI_CHECK_ONLY"
    bad = client.post(f"/api/jobs/{job_id}/files/source", headers=STUDENT, files={"file": ("m.docx", fixture_bytes("macro_renamed.docx"), "application/octet-stream")})
    assert bad.status_code == 422 and bad.json()["code"] == "MACRO_ENABLED"


def test_duplicate_delivery_after_completion_does_nothing(client):
    from app.jobs.pipeline import run_step
    from app.runtime import get_runtime

    job_id, quote = start_job(client, selection={"writing": "AI_CHECK"})
    client.post(f"/api/jobs/{job_id}/submit", headers=STUDENT, json={"quoteId": quote["id"]})
    wait(client, job_id)
    rt = get_runtime()
    # COMPLETED is published before the "ready" message is sent, which writes the job's notice: compare
    # only once that is settled, or the snapshot races the worker (the flaky failure of 2026-10-06).
    deadline = time.time() + 10
    while (before := rt.store.get(job_id)).notice is not None and (before.notice.lease_until or (before.notice.pending and not before.notice.attempts)) and time.time() < deadline:
        time.sleep(0.05)
    run_step(rt, job_id)
    assert rt.store.get(job_id) == before


def test_cancel_queued_job_and_reject_cancelling_completed(client):
    from app.runtime import get_runtime

    job_id, quote = start_job(client)
    get_runtime().store.set_flag("processing_enabled", False)  # hold the job in the queue
    client.post(f"/api/jobs/{job_id}/submit", headers=STUDENT, json={"quoteId": quote["id"]})
    assert client.get("/api/wallet", headers=STUDENT).json()["held"] > 0
    cancelled = client.post(f"/api/jobs/{job_id}/cancel", headers=STUDENT).json()
    assert cancelled["status"] == "CANCELLED" and cancelled["billing"]["state"] == "RELEASED"
    assert client.get("/api/wallet", headers=STUDENT).json()["held"] == 0  # the whole hold came back
    get_runtime().store.set_flag("processing_enabled", True)
    job_id, quote = start_job(client, selection={"writing": "AI_CHECK"})
    client.post(f"/api/jobs/{job_id}/submit", headers=STUDENT, json={"quoteId": quote["id"]})
    wait(client, job_id)
    assert client.post(f"/api/jobs/{job_id}/cancel", headers=STUDENT).status_code == 409


def test_active_job_cap(client):
    from app.runtime import get_runtime

    get_runtime().store.set_flag("processing_enabled", False)
    for _ in range(3):
        job_id, quote = start_job(client, selection={"writing": "AI_CHECK"})
        assert client.post(f"/api/jobs/{job_id}/submit", headers=STUDENT, json={"quoteId": quote["id"]}).status_code == 200
    job_id, quote = start_job(client, selection={"writing": "AI_CHECK"})
    response = client.post(f"/api/jobs/{job_id}/submit", headers=STUDENT, json={"quoteId": quote["id"]})
    assert response.status_code == 429 and response.json()["code"] == "ACTIVE_JOB_LIMIT"


def test_admin_retry_resumes_a_retryable_failure(client):
    from app.jobs import state
    from app.jobs.models import JobFailure, JobStatus
    from app.runtime import get_runtime

    rt = get_runtime()
    rt.store.set_flag("processing_enabled", False)
    job_id, quote = start_job(client, selection={"writing": "AI_CHECK"})
    client.post(f"/api/jobs/{job_id}/submit", headers=STUDENT, json={"quoteId": quote["id"]})

    def fail(j):
        j.failure = JobFailure(code="PROVIDER_UNAVAILABLE", user_message="delayed", retryable=True)
        return state.transition(j, JobStatus.FAILED)

    rt.store.update(job_id, fail)
    rt.store.set_flag("processing_enabled", True)
    assert client.post(f"/api/admin/jobs/{job_id}/retry", headers=STUDENT).status_code == 403
    retried = client.post(f"/api/admin/jobs/{job_id}/retry", headers=ADMIN).json()
    assert retried["adminActions"][0]["actor"] == "demo@paperaid.app"
    assert wait(client, job_id)["status"] == "COMPLETED"


def test_logs_never_contain_paper_text(client, caplog):
    caplog.set_level(logging.DEBUG)
    job_id, quote = start_job(client)
    client.post(f"/api/jobs/{job_id}/submit", headers=STUDENT, json={"quoteId": quote["id"]})
    wait(client, job_id)
    from app.documents.docx_io import read_docx

    sentences = [b.text[:60] for b in read_docx(fixture_bytes("simple_essay.docx")).blocks if b.kind == "paragraph"]
    logged = "\n".join(record.getMessage() + str(getattr(record, "fields", "")) for record in caplog.records)
    assert not any(s in logged for s in sentences)


def test_deleting_a_job_removes_its_files(client):
    from app.runtime import get_runtime

    job_id, quote = start_job(client, selection={"writing": "AI_CHECK"})
    client.post(f"/api/jobs/{job_id}/submit", headers=STUDENT, json={"quoteId": quote["id"]})
    wait(client, job_id)
    rt = get_runtime()
    prefix = rt.store.get(job_id).storage_prefix()
    assert client.delete(f"/api/jobs/{job_id}", headers=STUDENT).status_code == 204
    assert client.delete(f"/api/jobs/{job_id}", headers=STUDENT).status_code == 204  # idempotent
    assert not rt.files.exists(f"{prefix}/input/source.docx")
    assert client.get(f"/api/jobs/{job_id}", headers=STUDENT).status_code == 404


# --- regressions for the external review findings ------------------------------------------


def _input_objects(rt, job_id):
    prefix = rt.files.local_path(f"{rt.store.get(job_id).storage_prefix()}/input")
    return sorted(p.name for p in prefix.iterdir()) if prefix.exists() else []


def test_upload_after_submit_is_rejected_and_leaves_the_job_intact(client):
    from app.runtime import get_runtime

    rt = get_runtime()
    job_id, quote = start_job(client)
    rt.store.set_flag("processing_enabled", False)
    client.post(f"/api/jobs/{job_id}/submit", headers=STUDENT, json={"quoteId": quote["id"]})
    late = client.post(f"/api/jobs/{job_id}/files/source", headers=STUDENT, files={"file": ("new.docx", fixture_bytes("fake_headings.docx"), "application/octet-stream")})
    assert late.status_code == 409 and late.json()["code"] in ("ALREADY_SUBMITTED", "CONFLICT")
    job = rt.store.get(job_id)
    assert job.status == "QUEUED" and job.quote is not None and job.quote.id == quote["id"]
    assert len(_input_objects(rt, job_id)) == 1  # the late file was not left behind


def test_each_upload_is_immutable_and_replacements_clean_up(client):
    from app.runtime import get_runtime

    rt = get_runtime()
    job_id = client.post("/api/jobs", headers=STUDENT).json()["id"]
    for name in ("simple_essay.docx", "fake_headings.docx"):
        client.post(f"/api/jobs/{job_id}/files/source", headers=STUDENT, files={"file": (name, fixture_bytes(name), "application/octet-stream")})
    objects = _input_objects(rt, job_id)
    assert len(objects) == 1 and objects[0].startswith("source-") and rt.store.get(job_id).source.path.endswith(objects[0])


def test_submit_rechecks_the_file_inside_the_transaction(client, monkeypatch):
    """The competing upload lands after submit has read the job and passed its early checks, just
    before submit's own transaction runs — only the recheck inside the transaction can catch it."""
    from app.runtime import get_runtime

    rt = get_runtime()
    job_id, quote = start_job(client)
    original_update = rt.store.update_job_and_wallet
    injected = []

    def racing_update(target_id, mutate):
        if not injected:
            injected.append(True)

            def concurrent_upload(j):
                j.source = j.source.model_copy(update={"sha256": "0" * 64, "path": j.source.path + ".new"})
                return j

            rt.store.update(target_id, concurrent_upload)
        return original_update(target_id, mutate)

    monkeypatch.setattr(rt.store, "update_job_and_wallet", racing_update)
    response = client.post(f"/api/jobs/{job_id}/submit", headers=STUDENT, json={"quoteId": quote["id"]})
    assert injected, "submit never reached its transaction"
    assert response.status_code == 409 and rt.store.get(job_id).status == "QUOTED"


def test_maintenance_sees_every_page(client, monkeypatch):
    from app.jobs import service
    from app.runtime import get_runtime

    rt = get_runtime()
    rt.store.set_flag("processing_enabled", False)
    monkeypatch.setattr(service, "PAGE_SIZE", 2)
    ids = []
    for i in range(5):
        headers = {"Authorization": f"Dev many{i}@example.com"}
        grant(f"many{i}@example.com", 100_000)
        job_id, quote = start_job(client, selection={"writing": "AI_CHECK"}, headers=headers)
        client.post(f"/api/jobs/{job_id}/submit", headers=headers, json={"quoteId": quote["id"]})
        ids.append(job_id)
    assert {j.id for j in service.every_job(rt, None, {service.JobStatus.QUEUED})} >= set(ids)
    assert service.reconcile(rt) >= 5
    assert service.admin_summary(rt).queued >= 5


def test_production_downloads_return_a_signed_link(client, monkeypatch):
    from app.runtime import get_runtime

    rt = get_runtime()
    job_id, quote = start_job(client, selection={"writing": "AI_CHECK"})
    client.post(f"/api/jobs/{job_id}/submit", headers=STUDENT, json={"quoteId": quote["id"]})
    wait(client, job_id)
    monkeypatch.setattr(rt.files, "local_path", lambda path: None)
    monkeypatch.setattr(rt.files, "signed_url", lambda path, name: "https://storage.example/signed")
    response = client.get(f"/api/jobs/{job_id}/outputs/writing-report", headers=STUDENT)
    assert response.status_code == 200 and response.json() == {"url": "https://storage.example/signed"}


def test_production_requires_an_explicit_service_role():
    import pytest

    from app.main import resolve_role

    for bad in (None, "all", "both"):
        with pytest.raises(RuntimeError):
            resolve_role("production", bad)
    assert resolve_role("production", "worker") == "worker"
    assert resolve_role("local", None) == "all"


def test_task_endpoints_verify_the_caller_identity(monkeypatch):
    from types import SimpleNamespace

    import pytest
    from google.oauth2 import id_token

    from app.api.routes import _require_task_caller
    from app.core.config import Settings
    from app.core.errors import Forbidden

    settings = Settings.model_construct(env="production", worker_url="https://worker", tasks_invoker_email="tasks@p.iam.gserviceaccount.com")
    rt = SimpleNamespace(settings=settings)

    def request(headers):
        return SimpleNamespace(headers=headers)

    with pytest.raises(Forbidden):
        _require_task_caller(request({"x-cloudtasks-queuename": "paper-jobs"}), rt)  # a header alone proves nothing
    monkeypatch.setattr(id_token, "verify_oauth2_token", lambda token, req, audience: {"email": "someone@evil.com", "email_verified": True})
    with pytest.raises(Forbidden):
        _require_task_caller(request({"authorization": "Bearer t"}), rt)
    seen = {}

    def verify(token, req, audience):
        seen["audience"] = audience
        return {"email": "tasks@p.iam.gserviceaccount.com", "email_verified": True}

    monkeypatch.setattr(id_token, "verify_oauth2_token", verify)
    _require_task_caller(request({"authorization": "Bearer t"}), rt)
    assert seen["audience"] == "https://worker"


def test_reuploading_identical_bytes_never_deletes_the_current_file(client):
    from app.runtime import get_runtime

    rt = get_runtime()
    job_id = client.post("/api/jobs", headers=STUDENT).json()["id"]
    for name in ("simple_essay.docx", "fake_headings.docx", "simple_essay.docx"):
        client.post(f"/api/jobs/{job_id}/files/source", headers=STUDENT, files={"file": (name, fixture_bytes(name), "application/octet-stream")})
    current = rt.store.get(job_id).source.path
    assert rt.files.exists(current)  # the same bytes as the first upload, yet its own object
    assert _input_objects(rt, job_id) == [current.rsplit("/", 1)[1]]


def test_a_rejected_late_upload_removes_only_its_own_file(client, monkeypatch):
    from app.jobs import service
    from app.runtime import get_runtime

    rt = get_runtime()
    job_id, quote = start_job(client)
    current = rt.store.get(job_id).source.path
    original_update = rt.store.update

    def submitted_meanwhile(target_id, mutate):  # the job is submitted between the upload's checks and its attach
        def submit(j):
            j.status = service.JobStatus.QUEUED
            return j

        original_update(target_id, submit)
        return original_update(target_id, mutate)

    monkeypatch.setattr(rt.store, "update", submitted_meanwhile)
    late = client.post(f"/api/jobs/{job_id}/files/source", headers=STUDENT, files={"file": ("x.docx", fixture_bytes("simple_essay.docx"), "application/octet-stream")})
    assert late.status_code == 409 and late.json()["code"] == "ALREADY_SUBMITTED"
    assert rt.files.exists(current) and _input_objects(rt, job_id) == [current.rsplit("/", 1)[1]]


def test_local_queue_suppresses_duplicates_only_while_pending():
    import threading

    from app.core.config import Settings
    from app.integrations.queue import LocalQueue

    started, release, runs = threading.Event(), threading.Event(), []

    def runner(job_id):
        runs.append(job_id)
        started.set()
        release.wait(5)

    queue = LocalQueue(runner, 2, Settings())
    queue.enqueue("job_a", "job_a-g0-s0")
    assert started.wait(5)
    queue.enqueue("job_a", "job_a-g0-s0")  # duplicate delivery while the first is running: dropped
    release.set()
    queue._pool.shutdown(wait=True)
    assert runs == ["job_a"]
    assert queue._seen == set()  # forgotten once run, so memory does not grow

    queue = LocalQueue(lambda job_id: runs.append(job_id), 1, Settings())
    queue.enqueue("job_a", "job_a-g0-s0")
    queue._pool.shutdown(wait=True)
    assert runs == ["job_a", "job_a"]  # the same name is usable again after it ran


# --- the permanent algorithm: planning stage and university templates ---------------------

TEMPLATE = {"writing": "NONE", "formatting": "TEMPLATE_FORMAT"}


def _upload(client, job_id, role, name):
    return client.post(f"/api/jobs/{job_id}/files/{role}", headers=STUDENT, files={"file": (name, fixture_bytes(name), "application/octet-stream")})


def test_refinement_agrees_a_plan_before_rewriting(client):
    from app.runtime import get_runtime

    job_id, quote = start_job(client)
    client.post(f"/api/jobs/{job_id}/submit", headers=STUDENT, json={"quoteId": quote["id"]})
    job = wait(client, job_id)
    assert job["status"] == "COMPLETED"
    rt = get_runtime()
    plan = internal(rt, rt.store.get(job_id), "plan.json")
    assert plan["final"] and all(item["action"] == "rewrite" for item in plan["final"].values())
    assert all(c["reason"] for c in job["refinement"]["changes"])  # each change says why it was made


def test_templates_need_a_guide_and_only_accept_known_roles(client):
    job_id = client.post("/api/jobs", headers=STUDENT).json()["id"]
    _upload(client, job_id, "source", "simple_essay.docx")
    response = client.post(f"/api/jobs/{job_id}/quote", headers=STUDENT, json={"selection": TEMPLATE})
    assert response.status_code == 400 and response.json()["code"] == "NO_GUIDELINE"
    assert _upload(client, job_id, "secret", "simple_essay.docx").status_code == 404


def test_university_template_job_applies_the_rules_from_the_guide(client):
    job_id = client.post("/api/jobs", headers=STUDENT).json()["id"]
    assert _upload(client, job_id, "source", "simple_essay.docx").status_code == 200
    assert _upload(client, job_id, "guideline", "guideline_university.docx").status_code == 200
    quote = get_quote(client, job_id, TEMPLATE)
    assert client.post(f"/api/jobs/{job_id}/submit", headers=STUDENT, json={"quoteId": quote["id"]}).status_code == 200
    job = wait(client, job_id)
    assert job["status"] == "COMPLETED", job
    formatting = job["formatting"]
    rules = {r["label"]: r["value"] for r in formatting["rules"]}
    assert formatting["bodyTextUnchanged"] is True
    assert any("Times New Roman" in v for v in rules.values()) and "3.0 cm left" in rules["Page"], rules
    assert formatting["evidence"] and formatting["method"]
    assert any("contradictory" in w for w in job["warnings"])  # 1.5 spacing vs "double-spaced throughout"
    # "Tables shall be captioned above..." cannot be applied automatically, so it is not a clean success
    assert job["outcome"] == "PARTIAL" and any("Not applied automatically" in w for w in job["warnings"])


def test_replacing_the_guide_invalidates_the_quote(client):
    job_id = client.post("/api/jobs", headers=STUDENT).json()["id"]
    _upload(client, job_id, "source", "simple_essay.docx")
    _upload(client, job_id, "guideline", "guideline_university.docx")
    quote = get_quote(client, job_id, TEMPLATE)
    _upload(client, job_id, "guideline", "guideline_university.docx")
    response = client.post(f"/api/jobs/{job_id}/submit", headers=STUDENT, json={"quoteId": quote["id"]})
    assert response.status_code == 409 and response.json()["code"] == "QUOTE_MISMATCH"



# --- fixes from the third external review (Codex) ------------------------------------------


def _analyse_all(payload):
    return {
        "blocks": [
            {
                "id": b["id"], "riskBand": "moderate", "reasons": ["GENERIC_PHRASING"], "explanation": "Reads generically.", "suggestion": "Be specific.",
                "excerpt": b["text"][:60], "confirmed": [s["rule"] for s in b["signals"]], "rejected": [], "preserve": False, "risk": "",
            }
            for b in payload["blocks"]
        ]
    }


def _submit(client, selection, name="simple_essay.docx", timeout=60):
    job_id, quote = start_job(client, name=name, selection=selection)
    assert client.post(f"/api/jobs/{job_id}/submit", headers=STUDENT, json={"quoteId": quote["id"]}).status_code == 200
    return job_id, wait(client, job_id, timeout=timeout)


def test_a_passage_the_writer_never_returned_is_kept_and_reported(real_client):
    models = real_client.models
    models.overrides["analyse"] = _analyse_all
    dropped = []

    def refine_all_but_one(payload):  # the writer silently omits one passage, once
        answer = models.default("refine", payload)
        if not dropped:
            dropped.append(answer["blocks"].pop()["id"])
        return answer

    models.overrides["refine"] = refine_all_but_one
    _, job = _submit(real_client, REFINE_FORMAT)
    assert job["status"] == "COMPLETED" and job["outcome"] == "PARTIAL"
    kept = {c["blockId"] for c in job["refinement"]["changes"] if c["kept"]}
    assert set(dropped) <= kept and job["refinement"]["keptOriginal"] >= len(dropped)
    assert any("kept their original wording" in w for w in job["warnings"])


def test_explicit_low_judgments_are_a_complete_analysis(real_client):
    real_client.models.overrides["analyse"] = _judge_all(lambda b: {"rejected": [s["rule"] for s in b["signals"]]})
    _, job = _submit(real_client, {"writing": "AI_CHECK"})
    assert job["status"] == "COMPLETED" and job["outcome"] == "FULL"
    assert job["analysis"]["coverageComplete"] is True
    assert not any("could not assess" in w for w in job["warnings"])


def test_missing_lead_analysis_is_disclosed(real_client):
    real_client.models.truncate.add("analyse")  # every answer cut off, even one passage at a time
    _, job = _submit(real_client, {"writing": "AI_CHECK"})
    assert job["status"] == "COMPLETED" and job["outcome"] == "PARTIAL"
    assert job["analysis"]["method"] == "PaperAid writing-pattern signals only"
    assert any("could not assess this paper" in w for w in job["warnings"])


def test_real_mode_runs_every_step_of_the_algorithm_in_order(real_client):
    real_client.models.overrides["analyse"] = _analyse_all
    _, job = _submit(real_client, REFINE_FORMAT)
    assert job["status"] == "COMPLETED", job
    tasks = list(dict.fromkeys(real_client.models.tasks))
    # the free estimate analyses and drafts the plan; the paid job adds the academic review, replays both from the cache, then refines;
    # one accountable final reviewer approves the rewrites, and Opus's optional guidance is off (owner decision 2026-09-30)
    assert tasks == ["analyse", "analyse_peer", "plan", "academic", "critique", "finalise", "refine", "review", "analyse_after", "analyse_after_peer"]


def test_a_long_stage_continues_in_a_new_delivery_without_paying_twice(real_client, monkeypatch):
    from datetime import timedelta

    from app.jobs import pipeline

    monkeypatch.setattr(pipeline, "STAGE_WORK_LIMIT", timedelta(0))  # hand off after every paid call
    real_client.models.overrides["analyse"] = _analyse_all
    # Handing off after every call makes this long paper run about 70 deliveries, each re-preparing its
    # stage (about 2 s in the estimate and the re-analysis) before one call: about 110 s on a laptop.
    # The deadline allows for that (Codex audit 2026-09-30: 60 s timed out on slower machines).
    job_id, job = _submit(real_client, REFINE_FORMAT, name="dissertation_long.docx", timeout=400)
    assert job["status"] == "COMPLETED", job
    admin = real_client.get(f"/api/admin/jobs/{job_id}", headers=ADMIN).json()
    assert sum(e["label"].startswith("Continuing") for e in admin["events"]) >= 10  # it really continued, many times
    requests = real_client.models.requests
    assert len(requests) == len(set(requests))  # a continuation replays finished calls from the cache, never re-sends them


def test_guides_too_long_for_the_models_are_refused_at_upload(client):
    import io

    from docx import Document

    doc = Document()
    for _ in range(170):
        doc.add_paragraph("Body text shall be double spaced and justified throughout the thesis. " * 10)
    buffer = io.BytesIO()
    doc.save(buffer)
    job_id = client.post("/api/jobs", headers=STUDENT).json()["id"]
    response = client.post(f"/api/jobs/{job_id}/files/guideline", headers=STUDENT, files={"file": ("handbook.docx", buffer.getvalue(), "application/octet-stream")})
    assert response.status_code == 422 and "15,000 words" in response.json()["message"]


def test_removing_the_guide_removes_it_on_the_server(client):
    from app.runtime import get_runtime

    job_id = client.post("/api/jobs", headers=STUDENT).json()["id"]
    _upload(client, job_id, "source", "simple_essay.docx")
    _upload(client, job_id, "guideline", "guideline_university.docx")
    assert client.post(f"/api/jobs/{job_id}/quote", headers=STUDENT, json={"selection": TEMPLATE}).status_code == 200
    rt = get_runtime()
    guide_path = rt.store.get(job_id).guideline.path
    assert client.delete(f"/api/jobs/{job_id}/files/guideline", headers=STUDENT).status_code == 204
    job = rt.store.get(job_id)
    assert job.guideline is None and job.quote is None and job.status == "DRAFT" and not rt.files.exists(guide_path)
    assert client.post(f"/api/jobs/{job_id}/quote", headers=STUDENT, json={"selection": TEMPLATE}).json()["code"] == "NO_GUIDELINE"
    assert client.delete(f"/api/jobs/{job_id}/files/guideline", headers=OTHER).status_code == 404


def test_a_quote_is_not_saved_for_files_that_changed_while_pricing(client, monkeypatch):
    from app.jobs import service
    from app.runtime import get_runtime

    job_id = client.post("/api/jobs", headers=STUDENT).json()["id"]
    _upload(client, job_id, "source", "simple_essay.docx")
    original = service._rate_limit

    def upload_meanwhile(*args, **kwargs):
        _upload(client, job_id, "source", "fake_headings.docx")  # lands between reading the job and saving the quote
        return original(*args, **kwargs)

    monkeypatch.setattr(service, "_rate_limit", upload_meanwhile)
    response = client.post(f"/api/jobs/{job_id}/quote", headers=STUDENT, json={"selection": {"formatting": "FORMAT", "preset": "apa7"}})
    assert response.status_code == 409 and response.json()["code"] == "FILES_CHANGED"
    assert get_runtime().store.get(job_id).quote is None


def test_without_the_ai_provider_the_ai_services_cannot_be_quoted_or_run(client, monkeypatch):
    from app.runtime import get_runtime

    settings = get_runtime().settings
    monkeypatch.setattr(settings, "vertex_project", None)  # the Gemini workflow's Vertex target is not set up
    config = client.get("/api/config").json()["availability"]
    assert config["AI_CHECK"] == config["REFINE"] == config["TEMPLATE_FORMAT"] == "not_configured"
    assert config["FORMAT"] == "available"  # APA/Harvard formatting needs no AI
    job_id = client.post("/api/jobs", headers=STUDENT).json()["id"]
    _upload(client, job_id, "source", "simple_essay.docx")
    response = client.post(f"/api/jobs/{job_id}/quote", headers=STUDENT, json={"selection": REFINE_FORMAT})
    assert response.status_code == 400 and response.json()["code"] == "SERVICE_UNAVAILABLE"


def test_an_old_ai_quote_cannot_be_submitted_after_the_ai_provider_is_removed(client, monkeypatch):
    from app.runtime import get_runtime

    job_id, quote = start_job(client)
    monkeypatch.setattr(get_runtime().settings, "vertex_project", None)
    response = client.post(f"/api/jobs/{job_id}/submit", headers=STUDENT, json={"quoteId": quote["id"]})
    assert response.status_code == 400 and response.json()["code"] == "SERVICE_UNAVAILABLE"
    assert get_runtime().store.get(job_id).status == "QUOTED"


# --- prepaid credits (owner decision 2026-09-24) -----------------------------------------------

REAL_PRICES = {"fake:gpt-6-sol": (2.0, 10.0, 0.2), "fake:gpt-6-luna": (0.1, 0.5, 0.01), "fake:claude-sonnet-5-5": (2.0, 10.0, 0.2), "fake:claude-opus-5-5": (4.0, 20.0, 0.2),
               # the Gemini workflow's models at their published Vertex rates
               "fake:gemini-3.8-flash": (0.75, 3.75, 0.075), "fake:gemini-3.5-flash-lite": (0.30, 2.50, 0.03), "fake:gemini-3.1-pro-preview": (2.0, 12.0, 0.2)}


def _priced_models(client, monkeypatch, tokens=(2000, 800)):
    """Give the stand-in models real prices and token usage, so every call costs money."""
    from app.runtime import get_runtime

    monkeypatch.setattr(get_runtime().settings, "model_prices", REAL_PRICES)
    client.models.tokens = tokens


def _wallet(client, headers=STUDENT):
    return client.get("/api/wallet", headers=headers).json()


def test_no_estimate_or_quote_without_credits(client):
    headers = {"Authorization": "Dev broke@example.com"}
    job_id = client.post("/api/jobs", headers=headers).json()["id"]
    client.post(f"/api/jobs/{job_id}/files/source", headers=headers, files={"file": ("e.docx", fixture_bytes("simple_essay.docx"), "application/octet-stream")})
    for selection in (REFINE_FORMAT, {"writing": "AI_CHECK"}, {"formatting": "FORMAT", "preset": "apa7"}):
        response = client.post(f"/api/jobs/{job_id}/quote", headers=headers, json={"selection": selection, "startEstimate": True})
        assert response.status_code == 402 and response.json()["code"] == "INSUFFICIENT_CREDITS"


def test_refinement_estimate_is_charged_once_and_counts_toward_the_job(client, monkeypatch):
    _priced_models(client, monkeypatch)
    start = _wallet(client)["available"]
    job_id, quote = start_job(client)
    job = client.get(f"/api/jobs/{job_id}", headers=STUDENT).json()
    fee = job["estimate"]["fee"]
    assert 0 < fee <= job["estimate"]["feeCap"] and quote["paid"] == fee and quote["amount"] > fee
    assert _wallet(client)["available"] == start - fee  # the scan's hold was settled at its real cost
    assert any("already paid" in line["label"] for line in quote["lines"])

    client.post(f"/api/jobs/{job_id}/submit", headers=STUDENT, json={"quoteId": quote["id"]})
    job = wait(client, job_id)
    billing = job["billing"]
    assert job["status"] == "COMPLETED" and billing["state"] == "SETTLED" and job["paymentStatus"] == "PAID"
    assert 0 < billing["charged"] <= quote["amount"] - fee  # never more than the quote
    assert _wallet(client)["held"] == 0
    assert _wallet(client)["available"] == start - fee - billing["charged"]
    # the analysis and draft plan the estimate paid for were replayed from the cache, not re-sent
    assert client.models.tasks.count("analyse") == 1 and client.models.tasks.count("plan") == 1


def test_a_failed_job_returns_everything_including_the_estimate(client, monkeypatch):
    _priced_models(client, monkeypatch)
    start = _wallet(client)["available"]
    job_id, quote = start_job(client)
    client.models.refuse.add("critique")  # the writer declines once the job itself runs
    client.post(f"/api/jobs/{job_id}/submit", headers=STUDENT, json={"quoteId": quote["id"]})
    job = wait(client, job_id)
    assert job["status"] == "FAILED" and job["paymentStatus"] == "REFUNDED"
    assert job["billing"]["refunded"] == quote["paid"] > 0
    wallet = _wallet(client)
    assert (wallet["available"], wallet["held"]) == (start, 0)
    assert {e["kind"] for e in wallet["entries"]} >= {"HOLD", "CHARGE", "RELEASE", "REFUND"}


def test_a_failed_estimate_is_not_charged(client, monkeypatch):
    _priced_models(client, monkeypatch)
    start = _wallet(client)["available"]
    client.models.refuse.add("plan")
    job_id = client.post("/api/jobs", headers=STUDENT).json()["id"]
    _upload(client, job_id, "source", "simple_essay.docx")
    preview = client.post(f"/api/jobs/{job_id}/quote", headers=STUDENT, json={"selection": REFINE_FORMAT}).json()
    assert preview["estimateFeeCap"] > 0 and preview["estimate"] is None  # shown first; nothing held or run yet
    assert _wallet(client)["held"] == 0
    body = client.post(f"/api/jobs/{job_id}/quote", headers=STUDENT, json={"selection": REFINE_FORMAT, "startEstimate": True}).json()
    assert body["estimate"]["status"] == "RUNNING" and body["quote"] is None
    deadline = time.time() + 20
    while client.get(f"/api/jobs/{job_id}", headers=STUDENT).json()["estimate"]["status"] == "RUNNING" and time.time() < deadline:
        time.sleep(0.2)
    job = client.get(f"/api/jobs/{job_id}", headers=STUDENT).json()
    assert job["estimate"]["status"] == "FAILED" and job["estimate"]["message"] and job["quote"] is None
    assert (_wallet(client)["available"], _wallet(client)["held"]) == (start, 0)


def test_submit_needs_enough_credit_for_the_whole_quote(client):
    headers = {"Authorization": "Dev small@example.com"}
    grant("small@example.com", 1_000)
    job_id, quote = start_job(client, selection={"formatting": "FORMAT", "preset": "apa7"}, headers=headers)
    assert quote["amount"] >= 2_000  # the APA/Harvard minimum
    response = client.post(f"/api/jobs/{job_id}/submit", headers=headers, json={"quoteId": quote["id"]})
    assert response.status_code == 402 and response.json()["code"] == "INSUFFICIENT_CREDITS"
    job = client.get(f"/api/jobs/{job_id}", headers=headers).json()
    assert job["status"] == "QUOTED" and _wallet(client, headers)["held"] == 0


def test_formatting_only_is_charged_its_fixed_price(client):
    start = _wallet(client)["available"]
    job_id, quote = start_job(client, selection={"formatting": "FORMAT", "preset": "apa7"})
    client.post(f"/api/jobs/{job_id}/submit", headers=STUDENT, json={"quoteId": quote["id"]})
    job = wait(client, job_id)
    assert job["billing"]["charged"] == quote["amount"] == 2_000
    assert _wallet(client)["available"] == start - 2_000


def test_only_admins_grant_credits_and_only_to_known_accounts(client):
    client.get("/api/wallet", headers=STUDENT)
    before = _wallet(client)["available"]
    granted = client.post("/api/admin/credits", headers=ADMIN, json={"email": "student@example.com", "amount": 5_000, "note": "", "opId": "grant-test-1"}).json()
    assert granted["available"] == before + 5_000
    assert client.post("/api/admin/credits", headers=STUDENT, json={"email": "student@example.com", "amount": 5_000, "opId": "grant-test-2"}).status_code == 403
    assert client.post("/api/admin/credits", headers=ADMIN, json={"email": "nobody@example.com", "amount": 5_000, "opId": "grant-test-3"}).status_code == 404
    assert _wallet(client)["testCredits"] is True and _wallet(client)["entries"][0]["kind"] == "TOP_UP"


def test_files_are_pinned_while_an_estimate_runs(client, monkeypatch):
    from app.runtime import get_runtime

    get_runtime().store.set_flag("processing_enabled", False)  # keep the estimate running
    job_id = client.post("/api/jobs", headers=STUDENT).json()["id"]
    _upload(client, job_id, "source", "simple_essay.docx")
    client.post(f"/api/jobs/{job_id}/quote", headers=STUDENT, json={"selection": REFINE_FORMAT, "startEstimate": True})
    assert _upload(client, job_id, "source", "fake_headings.docx").json()["code"] == "ESTIMATE_RUNNING"
    assert client.post(f"/api/jobs/{job_id}/cancel", headers=STUDENT).json()["code"] == "ESTIMATE_RUNNING"
    assert client.delete(f"/api/jobs/{job_id}", headers=STUDENT).json()["code"] == "ESTIMATE_RUNNING"


def test_testing_mode_runs_every_service_without_credits(client, monkeypatch):
    """Owner decision 2026-09-25: with credits switched off, nothing needs a balance and nothing is charged."""
    from app.runtime import get_runtime

    monkeypatch.setattr(get_runtime().settings, "credits_enabled", False)
    _priced_models(client, monkeypatch)
    headers = {"Authorization": "Dev colleague@example.com"}  # no credits at all
    assert client.get("/api/config").json()["creditsEnabled"] is False
    assert client.post("/api/me/terms", headers=headers, json={"version": client.get("/api/config").json()["termsVersion"]}).status_code == 204
    job_id, quote = start_job(client, headers=headers)
    assert quote["amount"] > 0 and quote["paid"] == 0  # the price is still shown
    client.post(f"/api/jobs/{job_id}/submit", headers=headers, json={"quoteId": quote["id"]})
    job = wait(client, job_id, headers=headers)
    assert job["status"] == "COMPLETED" and job["paymentStatus"] == "NOT_REQUIRED" and job["billing"]["state"] == "NONE"
    wallet = _wallet(client, headers)
    assert (wallet["available"], wallet["held"], wallet["entries"]) == (0, 0, [])


def test_ai_services_are_invite_only_while_a_tester_list_is_set(client, monkeypatch):
    """Owner decision 2026-09-25: a public link must not spend the AI budget during testing."""
    from app.runtime import get_runtime

    monkeypatch.setattr(get_runtime().settings, "tester_emails", ["student@example.com"])
    outsider = {"Authorization": "Dev stranger@example.com"}
    grant("stranger@example.com", 100_000)
    assert client.get("/api/config").json()["availability"]["REFINE"] == "invite_only"  # anonymous visitor
    assert client.get("/api/config", headers=outsider).json()["availability"]["AI_CHECK"] == "invite_only"
    tester_view = client.get("/api/config", headers=STUDENT).json()["availability"]
    assert tester_view["REFINE"] == "available" and tester_view["FORMAT"] == "available"
    assert client.get("/api/config", headers=ADMIN).json()["availability"]["REFINE"] == "available"
    assert client.get("/api/config", headers={"Authorization": "Dev not-an-email"}).status_code == 200  # bad credential = anonymous
    job_id = client.post("/api/jobs", headers=outsider).json()["id"]
    _upload_as = client.post(f"/api/jobs/{job_id}/files/source", headers=outsider, files={"file": ("e.docx", fixture_bytes("simple_essay.docx"), "application/octet-stream")})
    assert _upload_as.status_code == 200
    refused = client.post(f"/api/jobs/{job_id}/quote", headers=outsider, json={"selection": {"writing": "AI_CHECK"}})
    assert refused.status_code == 400 and refused.json()["code"] == "SERVICE_UNAVAILABLE"
    allowed = client.post(f"/api/jobs/{job_id}/quote", headers=outsider, json={"selection": {"formatting": "FORMAT", "preset": "apa7"}})
    assert allowed.status_code == 200  # formatting uses no AI, so it stays open to everyone


# --- partial results (owner decision 2026-09-27) ------------------------------------------------


def _review_failing(ids_to_fail):
    def review(payload):
        return {
            "results": [
                {"id": p["id"], "grade": "REPAIR" if p["id"] in ids_to_fail else "PASS", "issues": ["MEANING_DRIFT"] if p["id"] in ids_to_fail else [], "note": "", "riskBand": "low"}
                for p in payload["pairs"]
            ]
        }

    return review


def test_verified_rewrites_are_delivered_when_others_fail(client):
    seen = []

    def review(payload):
        ids = [p["id"] for p in payload["pairs"]]
        seen.append(ids)
        return _review_failing(set(ids[: max(1, len(ids) // 2)]))(payload)  # reject half, every round

    client.models.overrides["review"] = review
    _, job = _submit(client, REFINE_FORMAT)
    r = job["refinement"]
    assert job["status"] == "COMPLETED" and job["outcome"] == "PARTIAL"
    assert r["refinedBlocks"] >= 1 and r["keptOriginal"] >= 1  # good work kept, doubtful work reverted
    assert any("kept their original wording" in w for w in job["warnings"])


def test_nothing_verified_still_completes_with_the_original_wording(client):
    client.models.overrides["review"] = lambda payload: _review_failing({p["id"] for p in payload["pairs"]})(payload)
    _, job = _submit(client, REFINE_FORMAT)
    assert job["status"] == "COMPLETED" and job["outcome"] == "PARTIAL"
    assert job["refinement"]["refinedBlocks"] == 0
    assert any("None of the" in w for w in job["warnings"])


def test_unchanged_writer_responses_count_as_kept(client):
    client.models.overrides["refine"] = lambda payload: {"blocks": [{"id": b["id"], "text": b["text"]} for b in payload["blocks"]]}
    _, job = _submit(client, REFINE_FORMAT)
    r = job["refinement"]
    assert r["refinedBlocks"] == 0 and r["keptOriginal"] == r["targetedBlocks"] > 0
    assert "No passages needed refinement" not in " ".join(job["warnings"])


def test_admins_never_receive_paper_text_and_expiry_purges_it(client):
    """Codex audit finding 1: the privacy page promises support can't see papers."""
    from datetime import timedelta

    from app.jobs import service
    from app.jobs.models import utcnow
    from app.runtime import get_runtime

    job_id, job = _submit(client, REFINE_FORMAT)
    assert job["refinement"]["changes"] and job["refinement"]["changes"][0]["before"]  # the student sees their passages
    admin = client.get(f"/api/admin/jobs/{job_id}", headers=ADMIN).json()["job"]
    assert all(c["before"] == c["after"] == "" for c in admin["refinement"]["changes"])
    assert all(f["excerpt"] == "" for f in admin["analysis"]["findings"])
    rt = get_runtime()
    rt.store.update(job_id, lambda j: j.model_copy(update={"expires_at": utcnow() - timedelta(days=1)}))
    assert service.cleanup_expired(rt) == 1
    expired = client.get(f"/api/jobs/{job_id}", headers=STUDENT).json()
    assert all(c["before"] == "" for c in expired["refinement"]["changes"])
    assert all(f["excerpt"] == "" for f in expired["analysis"]["findings"])



# --- money lifecycle (Codex audit, 2026-09-27) ------------------------------------------------


def _expire_quote(job_id):
    from datetime import timedelta

    from app.jobs.models import utcnow
    from app.runtime import get_runtime

    def expire(j):
        j.quote.expires_at = utcnow() - timedelta(minutes=1)
        return j

    get_runtime().store.update(job_id, expire)


def test_an_expired_quote_is_repriced_from_the_finished_estimate_and_keeps_its_fee(client, monkeypatch):
    _priced_models(client, monkeypatch)
    start = _wallet(client)["available"]
    job_id, quote = start_job(client)
    fee = quote["paid"]
    assert fee > 0
    _expire_quote(job_id)
    calls = len(client.models.tasks)
    again = client.post(f"/api/jobs/{job_id}/quote", headers=STUDENT, json={"selection": REFINE_FORMAT, "startEstimate": True}).json()
    assert again["quote"]["id"] != quote["id"] and again["quote"]["paid"] == fee
    assert len(client.models.tasks) == calls  # repriced from the saved result: no new scan, no new fee
    assert _wallet(client)["available"] == start - fee

    client.models.refuse.add("critique")
    client.post(f"/api/jobs/{job_id}/submit", headers=STUDENT, json={"quoteId": again["quote"]["id"]})
    job = wait(client, job_id)
    assert job["status"] == "FAILED" and job["billing"]["refunded"] == fee
    assert (_wallet(client)["available"], _wallet(client)["held"]) == (start, 0)


def test_a_second_estimate_keeps_the_first_fee_on_the_job(client, monkeypatch):
    _priced_models(client, monkeypatch)
    start = _wallet(client)["available"]
    job_id, first = start_job(client)
    light = {**REFINE_FORMAT, "intensity": "LIGHT"}
    second = get_quote(client, job_id, light)
    job = client.get(f"/api/jobs/{job_id}", headers=STUDENT).json()
    assert second["paid"] == first["paid"] + job["estimate"]["fee"] == job["billing"]["feePaid"]
    assert _wallet(client)["available"] == start - second["paid"]


def test_the_job_runs_with_the_engine_it_was_priced_with(client, monkeypatch):
    """A deploy that changes a prompt between estimate and submit must not re-bill the estimate's calls."""
    from app.ai import orchestration
    from app.jobs.models import Stage

    job_id, quote = start_job(client)
    monkeypatch.setitem(orchestration.PROMPTS, "plan-v0-test", "An updated planning prompt.")
    monkeypatch.setitem(orchestration.STEPS, "plan", orchestration.Step("lead", Stage.PLANNING, "plan-v0-test", 12000))
    client.post(f"/api/jobs/{job_id}/submit", headers=STUDENT, json={"quoteId": quote["id"]})
    assert wait(client, job_id)["status"] == "COMPLETED"
    assert client.models.tasks.count("plan") == 1 and client.models.tasks.count("analyse") == 1


def test_released_prompts_never_change():
    """Runs pin prompt versions (see Engine), so a released prompt file is frozen: change a prompt by
    adding the next version and pointing STEPS at it. New prompts are added to released.json."""
    import hashlib
    from pathlib import Path

    from app.ai.orchestration import STEPS

    folder = Path(__file__).parents[1] / "app" / "ai" / "prompts"
    released = json.loads((folder / "released.json").read_text(encoding="utf-8"))
    current = {p.stem: hashlib.sha256(p.read_text(encoding="utf-8").replace("\r\n", "\n").encode()).hexdigest() for p in folder.glob("*.md")}
    assert {name: current.get(name) for name in released} == released  # none edited or deleted
    assert {step.prompt for step in STEPS.values()} <= set(released)


def test_admin_retry_follows_the_current_credit_mode(client, monkeypatch):
    from app.jobs import state
    from app.jobs.models import JobFailure, JobStatus
    from app.pricing.billing import refund_job
    from app.runtime import get_runtime

    rt = get_runtime()
    start = _wallet(client)["available"]
    rt.store.set_flag("processing_enabled", False)
    job_id, quote = start_job(client, selection={"formatting": "FORMAT", "preset": "apa7"})
    client.post(f"/api/jobs/{job_id}/submit", headers=STUDENT, json={"quoteId": quote["id"]})

    def fail(j, w):
        refund_job(j, w, "failed")
        j.failure = JobFailure(code="PROVIDER_UNAVAILABLE", user_message="delayed", retryable=True)
        return state.transition(j, JobStatus.FAILED), w

    rt.store.update_job_and_wallet(job_id, fail)
    rt.store.set_flag("processing_enabled", True)
    monkeypatch.setattr(rt.settings, "credits_enabled", False)
    client.post(f"/api/admin/jobs/{job_id}/retry", headers=ADMIN)
    job = wait(client, job_id)
    assert job["status"] == "COMPLETED" and job["paymentStatus"] == "NOT_REQUIRED" and job["billing"]["state"] == "NONE"
    assert (_wallet(client)["available"], _wallet(client)["held"]) == (start, 0)


def test_no_work_can_start_on_a_job_being_deleted(client, monkeypatch):
    """The race Codex reproduced: an estimate started between deletion's check and its delete."""
    from app.jobs import service

    job_id = client.post("/api/jobs", headers=STUDENT).json()["id"]
    _upload(client, job_id, "source", "simple_essay.docx")
    original = service._erase
    raced = []

    def estimate_meanwhile(rt, job):
        raced.append(client.post(f"/api/jobs/{job_id}/quote", headers=STUDENT, json={"selection": REFINE_FORMAT, "startEstimate": True}))
        raced.append(_upload(client, job_id, "source", "fake_headings.docx"))
        original(rt, job)

    monkeypatch.setattr(service, "_erase", estimate_meanwhile)
    assert client.delete(f"/api/jobs/{job_id}", headers=STUDENT).status_code == 204
    assert all(r.status_code == 409 for r in raced), [r.json() for r in raced]
    assert _wallet(client)["held"] == 0


def test_account_deletion_touches_nothing_while_a_job_runs(client):
    from app.runtime import get_runtime

    rt = get_runtime()
    headers = {"Authorization": "Dev leaving@example.com"}
    grant("leaving@example.com", 50_000)
    done, quote = start_job(client, selection={"formatting": "FORMAT", "preset": "apa7"}, headers=headers)
    client.post(f"/api/jobs/{done}/submit", headers=headers, json={"quoteId": quote["id"]})
    wait(client, done, headers=headers)
    rt.store.set_flag("processing_enabled", False)
    running, quote = start_job(client, selection={"formatting": "FORMAT", "preset": "apa7"}, headers=headers)
    client.post(f"/api/jobs/{running}/submit", headers=headers, json={"quoteId": quote["id"]})
    response = client.delete("/api/me", headers=headers)
    assert response.status_code == 409 and response.json()["code"] == "JOB_ACTIVE"
    kept = rt.store.get(done)
    assert kept is not None and not kept.deleting  # the claim on the finished job was released


def test_repeating_a_grant_request_adds_credits_once(client):
    client.get("/api/wallet", headers=STUDENT)
    before = _wallet(client)["available"]
    body = {"email": "student@example.com", "amount": 5_000, "note": "refund", "opId": "op-refund-0001"}
    first = client.post("/api/admin/credits", headers=ADMIN, json=body).json()
    repeat = client.post("/api/admin/credits", headers=ADMIN, json=body).json()
    assert first["available"] == repeat["available"] == before + 5_000
    other = client.post("/api/admin/credits", headers=ADMIN, json={**body, "opId": "op-refund-0002"}).json()
    assert other["available"] == before + 10_000
    entry = next(e for e in _wallet(client)["entries"] if e.get("opId") == "op-refund-0001")
    assert entry["actor"] == "demo@paperaid.app"


def test_local_job_and_wallet_change_survives_a_failed_write(tmp_path, monkeypatch):
    """Codex #7: the wallet was written and the job write failed, so a retry held twice."""
    import pytest

    from app.integrations.store import LocalJobStore
    from app.jobs.models import Job, JobStatus, utcnow
    from app.pricing import credits

    store = LocalJobStore(tmp_path)
    store.create(Job(id="job_abc123", status=JobStatus.QUOTED, owner_uid="u1", owner_email="a@b.co", expires_at=utcnow()))
    store.update_wallet("u1", "a@b.co", lambda w: credits.top_up(w, 10_000, "test"))

    def hold_once(j, w):
        if j.billing.state == "HELD":
            return j, w  # already done: the operation is idempotent through the job record
        credits.hold(w, 2_000, j.id, "hold")
        j.billing.held, j.billing.state = 2_000, "HELD"
        return j, w

    original, calls = store._write, []

    def failing_write(job):
        calls.append(job.id)
        if len(calls) == 1:
            raise OSError("disk full")
        original(job)

    monkeypatch.setattr(store, "_write", failing_write)
    with pytest.raises(OSError):
        store.update_job_and_wallet("job_abc123", hold_once)
    job, wallet = store.update_job_and_wallet("job_abc123", hold_once)  # the retry sees the finished change
    assert job.billing.held == wallet.held == 2_000 and wallet.available == 8_000
    assert LocalJobStore(tmp_path).get("job_abc123").billing.state == "HELD"


def test_unfinished_drafts_are_listed_for_resuming(client):
    job_id, quote = start_job(client, selection={"formatting": "FORMAT", "preset": "apa7"})
    client.post("/api/jobs", headers=STUDENT)  # an empty draft (no paper) is not worth resuming
    drafts = client.get("/api/jobs?status=DRAFT", headers=STUDENT).json()["items"]
    assert [d["id"] for d in drafts] == [job_id] and drafts[0]["quote"]["id"] == quote["id"]
    assert job_id not in [j["id"] for j in client.get("/api/jobs", headers=STUDENT).json()["items"]]
    assert client.get("/api/jobs?status=DRAFT", headers=OTHER).json()["items"] == []


# --- phase 3: the revised analysis and refinement algorithm (owner decision 2026-09-27) ----------


def _judge_all(judgement):
    """A lead analysis that returns every passage, with `judgement(passage)` as its answer fields."""

    def analyse(payload):
        base = {"riskBand": "low", "reasons": [], "explanation": "", "suggestion": "", "excerpt": "", "confirmed": [], "rejected": [], "preserve": False, "risk": ""}
        return {"blocks": [{**base, "id": b["id"], **judgement(b)} for b in payload["blocks"]]}

    return analyse


def test_both_checkers_can_reject_every_signal_as_a_false_positive(real_client):
    enable_score()
    real_client.models.overrides["analyse"] = _judge_all(lambda b: {"rejected": [s["rule"] for s in b["signals"]]})
    real_client.models.overrides["analyse_peer"] = real_client.models.overrides["analyse"]
    _, job = _submit(real_client, {"writing": "AI_CHECK"})
    assert job["analysis"]["findings"] == [] and job["analysis"]["band"] == "LOW"


def test_signals_reach_the_lead_as_an_evidence_bundle(real_client):
    _, job = _submit(real_client, {"writing": "AI_CHECK"})
    sent = json.loads(next(r for r in real_client.models.requests if r.startswith("analyse"))[len("analyse") :])
    assert sent["document"]["rulesetVersion"] == "signals-v2" and sent["document"]["sections"]
    assert any(b["signals"] for b in sent["blocks"]) and all("sectionType" in b for b in sent["blocks"])
    assert job["analysis"]["algorithmVersion"] == "signals-v2"


def test_passages_the_lead_marks_to_preserve_are_never_rewritten(real_client):
    real_client.models.overrides["analyse"] = _judge_all(lambda b: {"riskBand": "high", "reasons": ["GENERIC_PHRASING"], "confirmed": [s["rule"] for s in b["signals"]], "preserve": True})
    _, job = _submit(real_client, REFINE_FORMAT)
    assert job["status"] == "COMPLETED" and job["refinement"]["refinedBlocks"] == 0
    assert "plan" not in real_client.models.tasks and "refine" not in real_client.models.tasks


def test_the_chosen_style_reaches_every_planning_and_writing_step(real_client):
    real_client.models.overrides["analyse"] = _analyse_all
    _, job = _submit(real_client, {**REFINE_FORMAT, "style": "CONCISE_ACADEMIC"})
    assert job["selection"]["style"] == "CONCISE_ACADEMIC"
    for task in ("plan", "critique", "finalise", "refine", "review"):
        sent = next(r for r in real_client.models.requests if r.startswith(task + "{"))
        assert "Concise academic" in sent, task


def test_a_different_style_needs_its_own_quote(client):
    job_id, quote = start_job(client)
    other = get_quote(client, job_id, {**REFINE_FORMAT, "style": "TECHNICAL"})
    assert other["id"] != quote["id"]
    client.post(f"/api/jobs/{job_id}/submit", headers=STUDENT, json={"quoteId": other["id"]})
    assert wait(client, job_id)["selection"]["style"] == "TECHNICAL"


def test_the_reviewer_sees_the_post_scan_and_linked_passages_and_its_warnings_reach_the_student(real_client):
    models = real_client.models
    models.overrides["analyse"] = _analyse_all

    def review(payload):
        return {"results": [{"id": p["id"], "grade": "PASS_WITH_WARNINGS", "issues": [], "note": "Still rests on a general claim only you can support.", "riskBand": "low"} for p in payload["pairs"]]}

    models.overrides["review"] = review
    _, job = _submit(real_client, REFINE_FORMAT, name="dissertation_long.docx")
    sent = json.loads(next(r for r in models.requests if r.startswith("review"))[len("review") :])
    pair = sent["pairs"][0]
    assert {"signalsBefore", "signalsAfter", "newRepeatedPhrasing"} <= set(pair["postScan"]) and "before" in pair["context"]
    assert any(p["linked"] for p in sent["pairs"])  # passages elsewhere that share key terms
    assert any("reviewer note" in w for w in job["warnings"])  # delivered, but never as an unqualified success
    delivered = [c for c in job["refinement"]["changes"] if not c["kept"]]
    assert delivered and all(c["note"].startswith("Reviewer note:") for c in delivered)


def test_the_after_band_uses_both_checkers_judgments_of_the_finished_paper(real_client):
    enable_score()
    models = real_client.models
    models.overrides["analyse"] = _analyse_all
    order = ["LOW", "MODERATE", "HIGH"]
    bands = []
    for risk in ("low", "high"):
        models.overrides["analyse_after"] = _judge_all(lambda b, risk=risk: {"riskBand": risk})
        models.overrides["analyse_after_peer"] = models.overrides["analyse_after"]
        _, job = _submit(real_client, REFINE_FORMAT)
        bands.append(order.index(job["analysisAfter"]["band"]))
    assert bands[1] > bands[0]


def test_paper_checks_are_reported_and_hidden_from_admins(client):
    job_id, quote = start_job(client, name="citations_in_text.docx", selection={"writing": "AI_CHECK"})
    client.post(f"/api/jobs/{job_id}/submit", headers=STUDENT, json={"quoteId": quote["id"]})
    job = wait(client, job_id)
    assert job["paperChecks"]["citationsFound"] >= 3 and job["paperChecks"]["items"][0]["kind"] == "NO_REFERENCE_LIST"
    admin = client.get(f"/api/admin/jobs/{job_id}", headers=ADMIN).json()["job"]
    assert all(i["item"] == "" and i["detail"] == "" for i in admin["paperChecks"]["items"])


# --- phase 4: source check with live search (owner decision 2026-09-27) ---------------------------

SOURCE_CHECK = {"writing": "AI_CHECK", "sourceCheck": True}


def _claims_paper() -> bytes:
    import io

    from docx import Document

    d = Document()
    d.add_heading("Mobile Money and Savings in Lira", 0)
    d.add_paragraph("Achola Grace, Reg. No. 2020/HD06/1234")
    d.add_heading("1. Introduction", 1)
    d.add_paragraph(
        "By 2022, Uganda had more than 30 million registered mobile money accounts (Bank of Uganda, 2022). Traders in secondary cities "
        "use these accounts every day, yet few studies ask whether market vendors keep balances on them for longer than a week."
    )
    d.add_paragraph(
        "In 2016, researchers in Kenya estimated that access to mobile money lifted about two percent of households out of poverty. "
        "The same work found larger effects for households headed by women, which makes the question relevant to Lira's markets."
    )
    d.add_heading("4. Results", 1)
    d.add_paragraph(
        "In 2024, of the 214 vendors we surveyed, 187 had an active mobile money account and only 41 kept money on it for more than a month. "
        "Women were more likely than men to keep a balance, and most balances were below the amount needed to restock."
    )
    out = io.BytesIO()
    d.save(out)
    return out.getvalue()


def _source_check_job(client, selection=SOURCE_CHECK, headers=STUDENT):
    job_id = client.post("/api/jobs", headers=headers).json()["id"]
    client.post(f"/api/jobs/{job_id}/files/source", headers=headers, files={"file": ("claims.docx", _claims_paper(), "application/octet-stream")})
    quote = get_quote(client, job_id, selection, headers)
    assert client.post(f"/api/jobs/{job_id}/submit", headers=headers, json={"quoteId": quote["id"]}).status_code == 200
    return job_id, quote, wait(client, job_id, headers)


def test_source_check_is_priced_and_checks_public_claims_with_real_sources(client):
    job_id, quote, job = _source_check_job(client)
    assert any(line["label"].startswith("Source check") for line in quote["lines"])
    research = job["research"]
    assert job["status"] == "COMPLETED" and research["checked"] == research["candidates"] >= 1
    claim = research["claims"][0]
    assert claim["support"] == "SUPPORTED" and claim["sources"][0]["url"] == "https://stats.example.org/report-2022"
    assert claim["sources"][0]["access"] == "FULL_TEXT" and research["retrievedOn"]
    calls = client.get(f"/api/admin/jobs/{job_id}", headers=ADMIN).json()["modelCalls"]
    assert any(c["searchCalls"] for c in calls if c["promptVersion"] == "research-v1")


def test_the_search_never_receives_the_paper_or_its_own_results(client):
    _, _, job = _source_check_job(client)
    researched = [json.loads(r[len("research") :]) for r in client.models.requests if r.startswith("research{")]
    assert researched and all(set(p) == {"claim", "query", "citedInPaper"} for p in researched)
    assert not any("214" in p["claim"] or "187" in p["claim"] or "Achola" in p["query"] for p in researched)
    assert all(c["section"] != "4. Results" for c in job["research"]["claims"])


def test_a_source_the_search_did_not_open_is_never_shown(client):
    client.models.opened = ["https://somewhere-else.example.org/"]  # the answer's URL was not among the pages opened
    _, _, job = _source_check_job(client)
    assert all(c["support"] == "NOT_FOUND" and c["sources"] == [] for c in job["research"]["claims"])


def test_when_the_second_check_disagrees_the_claim_is_uncertain(client):
    client.models.overrides["verify"] = lambda p: {"results": [{"id": c["id"], "support": "CONTRADICTED", "note": "Different year."} for c in p["claims"]]}
    _, _, job = _source_check_job(client)
    claim = job["research"]["claims"][0]
    assert claim["support"] == "UNCERTAIN" and "Second check: Different year." in claim["note"]


def test_contradicted_claims_are_flagged_but_the_paper_is_not_changed(client):
    client.models.overrides["verify"] = lambda p: {"results": [{"id": c["id"], "support": "CONTRADICTED", "note": "Incompatible."} for c in p["claims"]]}

    def research(payload):
        answer = client.models.default("research", payload)
        answer["support"] = "CONTRADICTED"
        answer["sources"][0]["supports"] = "CONTRADICTED"
        return answer

    client.models.overrides["research"] = research
    _, _, job = _source_check_job(client, {**REFINE_FORMAT, "sourceCheck": True})
    assert any("contradicted" in w for w in job["warnings"])
    assert all(c["support"] == "CONTRADICTED" for c in job["research"]["claims"])


def test_research_that_runs_out_of_budget_is_a_partial_result(client, monkeypatch):
    from app.ai import costs

    _priced_models(client, monkeypatch)
    job_id = client.post("/api/jobs", headers=STUDENT).json()["id"]
    client.post(f"/api/jobs/{job_id}/files/source", headers=STUDENT, files={"file": ("claims.docx", _claims_paper(), "application/octet-stream")})
    quote = get_quote(client, job_id, SOURCE_CHECK)
    monkeypatch.setattr(costs, "SEARCH_INPUT_TOKENS_WORST", 10**9)  # after pricing: every search now looks unaffordable
    client.post(f"/api/jobs/{job_id}/submit", headers=STUDENT, json={"quoteId": quote["id"]})
    job = wait(client, job_id)
    assert job["status"] == "COMPLETED" and job["outcome"] == "PARTIAL"
    assert job["research"]["checked"] == 0 and any("could not be checked" in w for w in job["warnings"])


def test_source_check_rules_and_privacy(client):
    job_id = client.post("/api/jobs", headers=STUDENT).json()["id"]
    client.post(f"/api/jobs/{job_id}/files/source", headers=STUDENT, files={"file": ("c.docx", _claims_paper(), "application/octet-stream")})
    alone = client.post(f"/api/jobs/{job_id}/quote", headers=STUDENT, json={"selection": {"formatting": "FORMAT", "preset": "apa7", "sourceCheck": True}})
    assert alone.status_code == 200 and {line["service"] for line in alone.json()["quote"]["lines"]} == {"SOURCE_CHECK", "FORMAT"}
    job_id, _, job = _source_check_job(client)
    admin = client.get(f"/api/admin/jobs/{job_id}", headers=ADMIN).json()["job"]
    assert all(c["claim"] == "" and c["note"] == "" for c in admin["research"]["claims"])


def test_the_word_report_carries_the_source_check(client):
    import io

    from docx import Document

    job_id, _, _ = _source_check_job(client)
    report = client.get(f"/api/jobs/{job_id}/outputs/writing-report", headers=STUDENT)
    text = "\n".join(p.text for p in Document(io.BytesIO(report.content)).paragraphs)
    assert "Source check" in text and "https://stats.example.org/report-2022" in text and "not that no evidence exists" in text


# --- phase 7: Deep Redraft (owner decision 2026-09-27) --------------------------------------------

REDRAFT = {"writing": "REDRAFT", "style": "STANDARD_ACADEMIC"}


def _field_count(data: bytes) -> int:
    from app.documents.docx_io import read_docx

    return sum(len(b.locked) for b in read_docx(data).blocks)


def test_deep_redraft_restructures_groups_and_keeps_every_citation_field(client):
    from tests.conftest import fixture_bytes

    job_id, quote = start_job(client, name="citation_fields.docx", selection=REDRAFT)
    assert any(line["label"] == "Deep redraft (up to)" for line in quote["lines"]) and quote["paid"] >= 0
    client.post(f"/api/jobs/{job_id}/submit", headers=STUDENT, json={"quoteId": quote["id"]})
    job = wait(client, job_id)
    assert job["status"] == "COMPLETED" and job["pipeline"] == ["EXTRACTING", "ANALYSING", "PLANNING", "REDRAFTING", "AUDITING", "EXPORTING"]
    assert job["refinement"]["mode"] == "REDRAFT" and job["refinement"]["refinedBlocks"] == 1
    paper = client.get(f"/api/jobs/{job_id}/outputs/paper", headers=STUDENT).content
    from app.documents.docx_io import read_docx

    before = [b for b in read_docx(fixture_bytes("citation_fields.docx")).blocks if b.kind == "paragraph"]
    after = [b for b in read_docx(paper).blocks if b.kind == "paragraph"]
    assert len(after) == len(before) - 1  # the writer merged two paragraphs
    assert _field_count(paper) == _field_count(fixture_bytes("citation_fields.docx")) == 4  # the Word citation fields moved, not retyped
    assert any(o["label"] == "Redrafted paper (Word)" for o in job["outputs"])
    assert "Standard academic" in next(r for r in client.models.requests if r.startswith("redraft{"))


def test_a_redraft_that_loses_a_citation_keeps_the_students_text(client):
    def drop_first_token(paragraphs):
        return [re.sub(r"⟦X\d+⟧", "", paragraphs[0], count=1), *paragraphs[1:]]

    client.models.overrides["redraft"] = lambda p: {"groups": [{"id": g["id"], "paragraphs": drop_first_token(g["paragraphs"])} for g in p["groups"]]}
    # the fix makes the same mistake, so the group is never verified
    client.models.overrides["redraft_fix"] = lambda p: {"groups": [{"id": g["id"], "paragraphs": drop_first_token(g["original"])} for g in p["groups"]]}
    job_id, quote = start_job(client, name="citation_fields.docx", selection=REDRAFT)
    client.post(f"/api/jobs/{job_id}/submit", headers=STUDENT, json={"quoteId": quote["id"]})
    job = wait(client, job_id)
    assert job["status"] == "COMPLETED" and job["outcome"] == "PARTIAL" and job["refinement"]["keptOriginal"] == 1
    paper = client.get(f"/api/jobs/{job_id}/outputs/paper", headers=STUDENT).content
    assert _field_count(paper) == 4


def test_a_citation_may_move_to_another_paragraph_of_its_group(client):
    def move_token(payload):
        answer = {"groups": []}
        for g in payload["groups"]:
            paragraphs = list(g["paragraphs"])
            last = paragraphs[-1]
            token = re.search(r"⟦X\d+⟧", last)
            if token and len(paragraphs) > 1:
                paragraphs[-1] = last.replace(token.group(0), "", 1)
                paragraphs[0] = paragraphs[0].rstrip(".") + " " + token.group(0) + "."
            answer["groups"].append({"id": g["id"], "paragraphs": paragraphs})
        return answer

    client.models.overrides["redraft"] = move_token
    job_id, quote = start_job(client, name="citation_fields.docx", selection=REDRAFT)
    client.post(f"/api/jobs/{job_id}/submit", headers=STUDENT, json={"quoteId": quote["id"]})
    job = wait(client, job_id)
    assert job["outcome"] == "FULL" and job["refinement"]["refinedBlocks"] == 1
    assert _field_count(client.get(f"/api/jobs/{job_id}/outputs/paper", headers=STUDENT).content) == 4


def test_deep_redraft_needs_an_estimate_and_never_touches_preserved_passages(real_client):
    def preserve_all(payload):
        return {
            "blocks": [
                {"id": b["id"], "riskBand": "low", "reasons": [], "explanation": "", "suggestion": "", "excerpt": "", "confirmed": [], "rejected": [], "preserve": True, "risk": ""}
                for b in payload["blocks"]
            ]
        }

    real_client.models.overrides["analyse"] = preserve_all
    job_id = real_client.post("/api/jobs", headers=STUDENT).json()["id"]
    _upload(real_client, job_id, "source", "simple_essay.docx")
    preview = real_client.post(f"/api/jobs/{job_id}/quote", headers=STUDENT, json={"selection": REDRAFT}).json()
    assert preview["estimateFeeCap"] > 0 and preview["quote"] is None  # sized by a paid estimate first
    quote = get_quote(real_client, job_id, REDRAFT)
    real_client.post(f"/api/jobs/{job_id}/submit", headers=STUDENT, json={"quoteId": quote["id"]})
    job = wait(real_client, job_id)
    assert job["refinement"]["refinedBlocks"] == 0 and "redraft" not in real_client.models.tasks


def test_latex_conversion_is_a_fixed_price_job_with_a_downloadable_project(client):
    import zipfile

    job_id, quote = start_job(client, name="equation.docx", selection={"latex": True})
    assert [line["label"] for line in quote["lines"]] == ["LaTeX conversion"] and quote["amount"] == 3000
    client.post(f"/api/jobs/{job_id}/submit", headers=STUDENT, json={"quoteId": quote["id"]})
    job = wait(client, job_id)
    assert job["pipeline"] == ["EXTRACTING", "CONVERTING", "EXPORTING"] and job["latex"]["equationsConverted"] == 1
    assert job["billing"]["charged"] == 3000
    download = client.get(f"/api/jobs/{job_id}/outputs/latex", headers=STUDENT)
    names = zipfile.ZipFile(io.BytesIO(download.content)).namelist()
    assert "main.tex" in names and ("main.pdf" in names) == job["latex"]["compiled"]
    assert job["outcome"] == ("FULL" if job["latex"]["compiled"] else "PARTIAL")


def test_latex_follows_the_refined_paper(client):
    import zipfile

    job_id, quote = start_job(client, selection={**REFINE_FORMAT, "latex": True})
    client.post(f"/api/jobs/{job_id}/submit", headers=STUDENT, json={"quoteId": quote["id"]})
    job = wait(client, job_id)
    refined = next(c["after"] for c in job["refinement"]["changes"] if not c["kept"])
    tex = zipfile.ZipFile(io.BytesIO(client.get(f"/api/jobs/{job_id}/outputs/latex", headers=STUDENT).content)).read("main.tex").decode()
    assert refined.split(".")[0][:40] in tex


def test_an_invented_quotation_is_never_evidence(client):
    """Codex audit #4: a passage not found on the source page cannot make a claim supported."""
    from tests.fake_models import SOURCE_URL

    client.models.pages[SOURCE_URL] = "<p>This real page is about something else entirely.</p>"
    _, _, job = _source_check_job(client)
    claim = job["research"]["claims"][0]
    assert claim["support"] == "UNCERTAIN" and claim["sources"][0]["verified"] is False
    assert "could not find the quoted passage on the source page" in claim["note"]
    assert not any(r.startswith("verify{") for r in client.models.requests)  # nothing unconfirmed goes to the second check


def test_a_confirmed_quotation_is_marked_verified(client):
    _, _, job = _source_check_job(client)
    assert job["research"]["claims"][0]["sources"][0]["verified"] is True


def test_results_of_a_search_that_broke_privacy_rules_are_discarded(client):
    """Codex audit #3: the queries the model actually sent are checked, not only the suggested one."""
    client.models.sent_queries = ["Achola Grace mobile money savings"]  # a front-matter name
    _, _, job = _source_check_job(client)
    assert all(c["support"] == "NOT_FOUND" and c["sources"] == [] for c in job["research"]["claims"])
    assert "privacy rules" in job["research"]["claims"][0]["note"]


def test_no_admin_view_or_expired_record_carries_the_papers_words(real_client):
    """Codex audit #5, as an allowlist check: no 6-word run of the paper appears anywhere in what
    support can see, including the plan's instructions ("why") and section headings."""
    from app.documents.docx_io import read_docx
    from app.jobs import service
    from app.runtime import get_runtime
    from tests.conftest import fixture_bytes

    def quoting(payload):  # a plan whose instructions quote the paper, as a real one may
        return {"blocks": [{"id": p["id"], "action": "rewrite", "instruction": f"Rework: {p['text'][:120]}", "preserve": p["text"][:60]} for p in payload["passages"]]}

    real_client.models.overrides["analyse"] = _analyse_all
    real_client.models.overrides["plan"] = quoting
    job_id, job = _submit(real_client, {**REFINE_FORMAT, "sourceCheck": True})
    words = [w for b in read_docx(fixture_bytes("simple_essay.docx")).blocks for w in [b.text.split()] if len(w) >= 6]
    runs = {" ".join(ws[i : i + 6]) for ws in words for i in range(len(ws) - 5)}
    admin = json.dumps(real_client.get(f"/api/admin/jobs/{job_id}", headers=ADMIN).json())
    assert not [r for r in runs if r in admin]
    rt = get_runtime()
    expired = service.without_paper_text(rt.store.get(job_id).view()).model_dump_json(by_alias=True)
    assert not [r for r in runs if r in expired]


def test_running_out_of_budget_mid_review_delivers_what_was_verified(real_client, monkeypatch):
    """Codex audit #10: the budget ran out on the second review batch and the whole job failed."""
    from app.ai import orchestration
    from app.core.errors import PermanentStageError

    monkeypatch.setattr(orchestration, "BATCH_WORDS", 60)  # one passage per batch

    models = real_client.models
    models.overrides["analyse"] = _analyse_all
    reviews = []

    def review(payload):
        reviews.append(len(payload["pairs"]))
        if len(reviews) >= 2:
            raise PermanentStageError("BUDGET_EXCEEDED", "budget", "spend cap reached")
        return models.default("review", payload)

    models.overrides["review"] = review
    _, job = _submit(real_client, REFINE_FORMAT, name="dissertation_long.docx", timeout=180)
    assert len(reviews) >= 2, "the paper must need more than one review batch"
    assert job["status"] == "COMPLETED" and job["outcome"] == "PARTIAL"
    assert job["refinement"]["refinedBlocks"] >= 1 and job["refinement"]["keptOriginal"] >= 1
    assert any("most it may spend" in w for w in job["warnings"])


def test_expired_drafts_lose_their_files_and_paper_text(client):
    """Codex audit #11: retention cleanup skipped abandoned drafts and quotes."""
    from datetime import timedelta

    from app.jobs import service
    from app.jobs.models import utcnow
    from app.runtime import get_runtime

    rt = get_runtime()
    job_id, _ = start_job(client, selection={"formatting": "FORMAT", "preset": "apa7"})  # quoted, never submitted
    path = rt.store.get(job_id).source.path
    assert rt.files.exists(path)
    rt.store.update(job_id, lambda j: j.model_copy(update={"expires_at": utcnow() - timedelta(days=1)}))
    assert service.cleanup_expired(rt) >= 1
    assert not rt.files.exists(path) and rt.store.get(job_id).files_deleted
    assert job_id not in [d["id"] for d in client.get("/api/jobs?status=DRAFT", headers=STUDENT).json()["items"]]


def test_nothing_new_can_start_while_an_account_is_being_deleted(client, monkeypatch):
    """Codex audit #2: a job submitted during deletion left a hold on a deleted wallet."""
    from app.jobs import service
    from app.runtime import get_runtime

    rt = get_runtime()
    monkeypatch.setattr(rt.settings, "credits_enabled", False)  # testing mode: a balance does not block deletion
    headers = {"Authorization": "Dev leaving2@example.com"}
    first, _ = start_job(client, selection={"formatting": "FORMAT", "preset": "apa7"}, headers=headers)
    attempts = []
    original = service._erase

    def meanwhile(rt_, job):
        if not attempts:
            attempts.append(client.post("/api/jobs", headers=headers))
        original(rt_, job)

    monkeypatch.setattr(service, "_erase", meanwhile)
    assert client.delete("/api/me", headers=headers).status_code == 204
    assert attempts[0].status_code == 409 and attempts[0].json()["code"] == "ACCOUNT_CLOSING"
    assert rt.store.get(first) is None  # the job is gone
    assert not [w for w in rt.store.find_wallets("leaving2@example.com", 5) if w.email == "leaving2@example.com"]


def test_an_account_holding_credit_is_not_deleted_while_credits_are_on(client):
    headers = {"Authorization": "Dev rich@example.com"}
    grant("rich@example.com", 7_000)
    response = client.delete("/api/me", headers=headers)
    assert response.status_code == 409 and response.json()["code"] == "ACCOUNT_HAS_CREDIT"
    assert client.post("/api/jobs", headers=headers).status_code == 200  # nothing was closed


def test_an_old_grant_replayed_after_300_later_entries_adds_nothing(client):
    """Codex audit: the display ledger keeps 300 entries, so grant ids must be kept elsewhere."""
    client.get("/api/wallet", headers=STUDENT)
    body = {"email": "student@example.com", "amount": 1000, "note": "", "opId": "op-first-grant"}
    after_first = client.post("/api/admin/credits", headers=ADMIN, json=body).json()["available"]
    for n in range(301):
        client.post("/api/admin/credits", headers=ADMIN, json={**body, "amount": 1, "opId": f"op-filler-{n:04d}"})
    replay = client.post("/api/admin/credits", headers=ADMIN, json=body).json()["available"]
    assert replay == after_first + 301


def test_a_rule_change_after_the_estimate_never_repeats_its_paid_calls(client, monkeypatch):
    """Codex audit #7: a changed signal threshold made the job pay for analysis and planning again."""
    from dataclasses import replace

    from app.analysis import rules

    job_id, quote = start_job(client)
    assert client.models.tasks.count("analyse") == 1 and client.models.tasks.count("plan") == 1
    monkeypatch.setitem(rules.RULES, "RHYTHM_UNIFORM", replace(rules.RULES["RHYTHM_UNIFORM"], threshold=0.9))  # a deploy changes a rule
    client.post(f"/api/jobs/{job_id}/submit", headers=STUDENT, json={"quoteId": quote["id"]})
    assert wait(client, job_id)["status"] == "COMPLETED"
    assert client.models.tasks.count("analyse") == 1 and client.models.tasks.count("plan") == 1


def test_a_maximum_length_paper_keeps_its_record_within_firestores_limit(client):
    """Codex audit #9: full before/after text of a long paper could exceed Firestore's 1 MiB."""
    import zipfile  # noqa: F401

    from docx import Document as WordDocument

    from app.integrations.store import MAX_RECORD_BYTES
    from app.runtime import get_runtime

    doc = WordDocument()
    sentence = "Η πρόσβαση στο διαδίκτυο παραμένει περιορισμένη για πολλούς φοιτητές στις αγροτικές περιοχές της χώρας. "  # 2-byte letters
    words = 0
    n = 0
    while words < 24_500:
        if n % 6 == 0:
            doc.add_heading(f"Ενότητα {n // 6 + 1}", 1)
        doc.add_paragraph(sentence * 8)
        words += 8 * len(sentence.split())
        n += 1
    out = io.BytesIO()
    doc.save(out)
    job_id = client.post("/api/jobs", headers=STUDENT).json()["id"]
    client.post(f"/api/jobs/{job_id}/files/source", headers=STUDENT, files={"file": ("big.docx", out.getvalue(), "application/octet-stream")})
    quote = get_quote(client, job_id, {"writing": "REDRAFT"})
    client.post(f"/api/jobs/{job_id}/submit", headers=STUDENT, json={"quoteId": quote["id"]})
    job = wait(client, job_id, timeout=600)
    record = get_runtime().store.get(job_id).model_dump_json(by_alias=True).encode()
    assert job["status"] == "COMPLETED" and job["refinement"]["refinedBlocks"] > 0  # a non-Latin paper can be redrafted
    assert job["refinement"]["trimmed"] is True
    assert len(record) < MAX_RECORD_BYTES
    report = client.get(f"/api/jobs/{job_id}/outputs/change-report", headers=STUDENT).content
    text = "\n".join(p.text for p in WordDocument(io.BytesIO(report)).paragraphs)
    assert "full text in the change report" not in text  # the report has every word


def test_a_source_that_cannot_be_opened_is_found_but_not_confirmed(client):
    """Publishers often block automated reading: that is reported as unconfirmed, not as a bad quotation."""
    from tests.fake_models import SOURCE_URL

    del client.models.pages[SOURCE_URL]  # the page cannot be opened
    _, _, job = _source_check_job(client)
    claim = job["research"]["claims"][0]
    assert claim["support"] == "UNCONFIRMED" and claim["sources"][0]["readable"] is False
    assert "Open the links to check them yourself" in claim["note"]


def test_a_blocked_article_is_confirmed_from_its_abstract(client):
    from tests.fake_models import SOURCE_URL

    del client.models.pages[SOURCE_URL]
    client.models.abstracts[SOURCE_URL] = "Background. The report gives the figure for 2022. Methods follow."
    _, _, job = _source_check_job(client)
    source = job["research"]["claims"][0]["sources"][0]
    assert job["research"]["claims"][0]["support"] == "SUPPORTED" and source["verified"] and source["access"] == "ABSTRACT"


# --- Codex verification round 2 (2026-09-27): interleavings that must stay safe -------------------


def test_a_draft_paused_before_its_write_cannot_outlive_account_deletion(client, monkeypatch):
    """Reproduction A: the draft request passes its checks, the account is deleted, then the write runs."""
    from app.runtime import get_runtime

    rt = get_runtime()
    monkeypatch.setattr(rt.settings, "credits_enabled", False)
    headers = {"Authorization": "Dev latedraft@example.com"}
    client.get("/api/wallet", headers=headers)
    original = type(rt.store).create_if_open
    deleted = []

    def delete_first(store, job):
        if not deleted:
            deleted.append(client.delete("/api/me", headers=headers).status_code)
        return original(store, job)

    monkeypatch.setattr(type(rt.store), "create_if_open", delete_first)
    response = client.post("/api/jobs", headers=headers)
    assert deleted == [204] and response.status_code == 409 and response.json()["code"] == "ACCOUNT_CLOSING"
    uid = "u_" + __import__("hashlib").sha256(b"latedraft@example.com").hexdigest()[:20]
    assert rt.store.list(uid, None, None, None, 10)[0] == []


def test_a_grant_whose_wallet_was_already_found_cannot_reopen_a_deleted_account(client, monkeypatch):
    """Reproduction B: the grant selected the wallet, the account was deleted, then the grant ran."""
    from app.runtime import get_runtime

    rt = get_runtime()
    headers = {"Authorization": "Dev lategrant@example.com"}
    client.get("/api/wallet", headers=headers)  # an open, empty wallet the admin can find
    original = type(rt.store).update_wallet
    state = {"deleting": False, "done": False}

    def delete_before_the_grant(store, uid, email, mutate):
        if not state["done"] and not state["deleting"] and email == "lategrant@example.com":
            state["deleting"] = True
            assert client.delete("/api/me", headers=headers).status_code == 204
            state["done"] = True
        return original(store, uid, email, mutate)

    monkeypatch.setattr(type(rt.store), "update_wallet", delete_before_the_grant)
    body = {"email": "lategrant@example.com", "amount": 1000, "note": "", "opId": "op-late-grant-1"}
    response = client.post("/api/admin/credits", headers=ADMIN, json=body)
    assert state["done"] and response.status_code == 409 and response.json()["code"] == "ACCOUNT_CLOSING"
    uid = "u_" + __import__("hashlib").sha256(b"lategrant@example.com").hexdigest()[:20]
    wallet = rt.store.get_wallet(uid)
    assert wallet is not None and wallet.closing and wallet.available == 0 and wallet.email == ""


def test_a_submission_racing_retention_cleanup_never_loses_its_files(client, monkeypatch):
    """#11 round 2: cleanup selected an expired quote, the student submitted, then files were deleted."""
    from datetime import timedelta

    from app.jobs import service
    from app.jobs.models import JobStatus, utcnow
    from app.runtime import get_runtime

    rt = get_runtime()
    rt.store.set_flag("processing_enabled", False)
    job_id, quote = start_job(client, selection={"formatting": "FORMAT", "preset": "apa7"})
    rt.store.update(job_id, lambda j: j.model_copy(update={"expires_at": utcnow() - timedelta(minutes=1)}))  # quote still valid
    original = type(rt.files).delete_prefix
    submitted = []

    def submit_first(files, prefix):
        if not submitted:
            submitted.append(client.post(f"/api/jobs/{job_id}/submit", headers=STUDENT, json={"quoteId": quote["id"]}))
        return original(files, prefix)

    monkeypatch.setattr(type(rt.files), "delete_prefix", submit_first)
    service.cleanup_expired(rt)
    job = rt.store.get(job_id)
    assert submitted[0].status_code == 409  # the claim came first
    assert job.status == JobStatus.QUOTED and job.billing.state != "HELD" and job.files_deleted


def test_a_submission_that_wins_the_race_keeps_its_files(client, monkeypatch):
    from datetime import timedelta

    from app.jobs import service
    from app.jobs.models import JobStatus, utcnow
    from app.runtime import get_runtime

    rt = get_runtime()
    rt.store.set_flag("processing_enabled", False)
    job_id, quote = start_job(client, selection={"formatting": "FORMAT", "preset": "apa7"})
    rt.store.update(job_id, lambda j: j.model_copy(update={"expires_at": utcnow() - timedelta(minutes=1)}))
    assert client.post(f"/api/jobs/{job_id}/submit", headers=STUDENT, json={"quoteId": quote["id"]}).status_code == 200
    service.cleanup_expired(rt)
    job = rt.store.get(job_id)
    assert job.status == JobStatus.QUEUED and not job.files_deleted and rt.files.exists(job.source.path)


def test_only_the_services_list_skips_app_check(monkeypatch):
    """A fresh App Check attestation (reCAPTCHA) takes seconds after an hour away. Only the harmless
    services list may answer without it; every action and every read of the user's data needs it."""
    import pytest
    from firebase_admin import app_check
    from firebase_admin import auth as fb_auth
    from starlette.requests import Request

    from app.core import auth
    from app.core.config import Settings
    from app.core.errors import Unauthorized

    settings = Settings(_env_file=None, auth_mode="firebase", require_app_check=True)
    monkeypatch.setattr(auth, "_firebase", lambda settings: None)
    monkeypatch.setattr(fb_auth, "verify_id_token", lambda token, check_revoked: {"uid": "u1", "email": "a@b.co", "email_verified": True})

    def no_attestation(token):
        raise ValueError("no App Check token")

    monkeypatch.setattr(app_check, "verify_token", no_attestation)
    request = Request({"type": "http", "headers": [(b"authorization", b"Bearer id-token")]})
    with pytest.raises(Unauthorized):
        auth.current_user(request, settings)
    user = auth.optional_user(request, settings)
    assert user is not None and user.uid == "u1"
