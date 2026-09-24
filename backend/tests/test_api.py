import json
import logging
import time

from tests.conftest import fixture_bytes

STUDENT = {"Authorization": "Dev student@example.com"}
OTHER = {"Authorization": "Dev other@example.com"}
ADMIN = {"Authorization": "Dev demo@paperaid.app"}
REFINE_FORMAT = {"writing": "REFINE", "intensity": "STANDARD", "formatting": "FORMAT", "preset": "apa7", "latex": False}


def start_job(client, name="simple_essay.docx", selection=None, headers=STUDENT):
    job_id = client.post("/api/jobs", headers=headers).json()["id"]
    upload = client.post(f"/api/jobs/{job_id}/files/source", headers=headers, files={"file": (name, fixture_bytes(name), "application/octet-stream")})
    assert upload.status_code == 200, upload.json()
    quote = client.post(f"/api/jobs/{job_id}/quote", headers=headers, json={"selection": selection or REFINE_FORMAT}).json()
    return job_id, quote


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
    assert job["status"] == "COMPLETED" and job["paymentStatus"] == "BETA_BYPASS"
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
    assert response.json()["amount"] == quote["amount"] > 1


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
    before = rt.store.get(job_id)
    run_step(rt, job_id)
    assert rt.store.get(job_id) == before


def test_cancel_queued_job_and_reject_cancelling_completed(client):
    from app.runtime import get_runtime

    get_runtime().store.set_flag("processing_enabled", False)  # hold jobs in the queue
    job_id, quote = start_job(client)
    client.post(f"/api/jobs/{job_id}/submit", headers=STUDENT, json={"quoteId": quote["id"]})
    cancelled = client.post(f"/api/jobs/{job_id}/cancel", headers=STUDENT).json()
    assert cancelled["status"] == "CANCELLED"
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
    rt.store.set_flag("processing_enabled", False)
    job_id, quote = start_job(client)
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
    original_update = rt.store.update
    injected = []

    def racing_update(target_id, mutate):
        if not injected:
            injected.append(True)

            def concurrent_upload(j):
                j.source = j.source.model_copy(update={"sha256": "0" * 64, "path": j.source.path + ".new"})
                return j

            original_update(target_id, concurrent_upload)
        return original_update(target_id, mutate)

    monkeypatch.setattr(rt.store, "update", racing_update)
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
    plan = json.loads(rt.files.get(f"{rt.store.get(job_id).storage_prefix()}/internal/plan.json"))
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
    quote = client.post(f"/api/jobs/{job_id}/quote", headers=STUDENT, json={"selection": TEMPLATE}).json()
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
    quote = client.post(f"/api/jobs/{job_id}/quote", headers=STUDENT, json={"selection": TEMPLATE}).json()
    _upload(client, job_id, "guideline", "guideline_university.docx")
    response = client.post(f"/api/jobs/{job_id}/submit", headers=STUDENT, json={"quoteId": quote["id"]})
    assert response.status_code == 409 and response.json()["code"] == "QUOTE_MISMATCH"



# --- fixes from the third external review (Codex) ------------------------------------------


def _analyse_all(payload):
    return {
        "blocks": [
            {"id": b["id"], "riskBand": "moderate", "reasons": ["GENERIC_PHRASING"], "explanation": "Reads generically.", "suggestion": "Be specific.", "excerpt": b["text"][:60]}
            for b in payload["blocks"]
        ]
    }


def _submit(client, selection, name="simple_essay.docx"):
    job_id, quote = start_job(client, name=name, selection=selection)
    assert client.post(f"/api/jobs/{job_id}/submit", headers=STUDENT, json={"quoteId": quote["id"]}).status_code == 200
    return job_id, wait(client, job_id)


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


def test_missing_lead_analysis_is_disclosed(real_client):
    real_client.models.overrides["analyse"] = lambda payload: {"blocks": []}  # e.g. every answer cut off
    _, job = _submit(real_client, {"writing": "AI_CHECK"})
    assert job["status"] == "COMPLETED" and job["outcome"] == "PARTIAL"
    assert job["analysis"]["method"] == "PaperAid writing-pattern signals only"
    assert any("could not assess this paper" in w for w in job["warnings"])


def test_real_mode_runs_every_step_of_the_algorithm_in_order(real_client):
    real_client.models.overrides["analyse"] = _analyse_all
    _, job = _submit(real_client, REFINE_FORMAT)
    assert job["status"] == "COMPLETED", job
    tasks = list(dict.fromkeys(real_client.models.tasks))
    assert tasks == ["analyse", "plan", "critique", "finalise", "refine", "review"]


def test_a_long_stage_continues_in_a_new_delivery_without_paying_twice(real_client, monkeypatch):
    from datetime import timedelta

    from app.jobs import pipeline

    monkeypatch.setattr(pipeline, "STAGE_WORK_LIMIT", timedelta(0))  # hand off after every paid call
    real_client.models.overrides["analyse"] = _analyse_all
    job_id, job = _submit(real_client, REFINE_FORMAT, name="dissertation_long.docx")
    assert job["status"] == "COMPLETED", job
    admin = real_client.get(f"/api/admin/jobs/{job_id}", headers=ADMIN).json()
    assert any(e["label"].startswith("Continuing") for e in admin["events"])
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
    original = service.quote_lines

    def upload_meanwhile(selection, words):
        _upload(client, job_id, "source", "fake_headings.docx")  # lands between reading the job and saving the quote
        return original(selection, words)

    monkeypatch.setattr(service, "quote_lines", upload_meanwhile)
    response = client.post(f"/api/jobs/{job_id}/quote", headers=STUDENT, json={"selection": REFINE_FORMAT})
    assert response.status_code == 409 and response.json()["code"] == "FILES_CHANGED"
    assert get_runtime().store.get(job_id).quote is None


def test_without_ai_keys_the_ai_services_cannot_be_quoted_or_run(client, monkeypatch):
    from app.runtime import get_runtime

    settings = get_runtime().settings
    monkeypatch.setattr(settings, "openai_api_key", None)
    config = client.get("/api/config").json()["availability"]
    assert config["AI_CHECK"] == config["REFINE"] == config["TEMPLATE_FORMAT"] == "not_configured"
    assert config["FORMAT"] == "available"  # APA/Harvard formatting needs no AI
    job_id = client.post("/api/jobs", headers=STUDENT).json()["id"]
    _upload(client, job_id, "source", "simple_essay.docx")
    response = client.post(f"/api/jobs/{job_id}/quote", headers=STUDENT, json={"selection": REFINE_FORMAT})
    assert response.status_code == 400 and response.json()["code"] == "SERVICE_UNAVAILABLE"


def test_an_old_ai_quote_cannot_be_submitted_after_keys_are_removed(client, monkeypatch):
    from app.runtime import get_runtime

    job_id, quote = start_job(client)
    monkeypatch.setattr(get_runtime().settings, "openai_api_key", None)
    response = client.post(f"/api/jobs/{job_id}/submit", headers=STUDENT, json={"quoteId": quote["id"]})
    assert response.status_code == 400 and response.json()["code"] == "SERVICE_UNAVAILABLE"
    assert get_runtime().store.get(job_id).status == "QUOTED"
