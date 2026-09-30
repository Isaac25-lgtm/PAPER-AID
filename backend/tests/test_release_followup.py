"""Regressions for the four issues found after the four-model release."""

from types import SimpleNamespace

from app.latex.convert import Result
from app.proposals import pipeline
from app.proposals import service as proposals
from app.proposals.models import ChapterDocument, ChapterSection, GuideFile
from app.runtime import get_runtime
from tests.conftest import fixture_bytes
from tests.test_api import ADMIN, STUDENT, get_quote, wait
from tests.test_profiles import _guide
from tests.test_proposals import _create, _run


def test_student_api_omits_score_fields_but_admin_retains_them(client, monkeypatch):
    job_id = client.post("/api/jobs", headers=STUDENT).json()["id"]
    uploaded = client.post(f"/api/jobs/{job_id}/files/source", headers=STUDENT, files={"file": ("simple_essay.docx", fixture_bytes("simple_essay.docx"), "application/octet-stream")})
    assert uploaded.status_code == 200
    quoted = get_quote(client, job_id, {"writing": "AI_CHECK", "academic": False})
    client.post(f"/api/jobs/{job_id}/submit", headers=STUDENT, json={"quoteId": quoted["id"]})
    job = wait(client, job_id)
    assert job["status"] == "COMPLETED"
    for view in (job, client.get("/api/jobs", headers=STUDENT).json()["items"][0]):
        assert not {"percent", "band", "confidence"} & view["analysis"].keys()
        assert view["analysis"]["findings"] is not None
    document = client.get(f"/api/jobs/{job_id}/document", headers=STUDENT).json()
    assert "percent" not in document and "percentAfter" not in document
    admin = client.get(f"/api/admin/jobs/{job_id}", headers=ADMIN).json()["job"]["analysis"]
    assert {"percent", "band", "confidence"} <= admin.keys()
    monkeypatch.setattr(get_runtime().settings, "show_ai_score", True)
    assert {"percent", "band", "confidence"} <= client.get(f"/api/jobs/{job_id}", headers=STUDENT).json()["analysis"].keys()
    assert "percent" in client.get(f"/api/jobs/{job_id}/document", headers=STUDENT).json()


def test_guide_upload_is_refused_while_a_plan_runs_and_plan_completes(client):
    pid = _create(client)["id"]
    seen = []

    def try_upload(payload):
        reply = client.post(f"/api/projects/{pid}/guide", headers=STUDENT, files={"file": ("guide.docx", _guide(), "application/octet-stream")})
        seen.append((reply.status_code, reply.json()["code"]))
        return client.models.default("p_plan", payload)

    client.models.overrides["p_plan"] = try_upload
    job = _run(client, pid, "PLAN")
    assert job["status"] == "COMPLETED" and seen == [(409, "STEP_RUNNING")]
    assert client.get(f"/api/projects/{pid}", headers=STUDENT).json()["guideName"] is None


def test_publish_backstop_rejects_a_guide_added_during_a_plan(client):
    pid = _create(client)["id"]
    rt = get_runtime()

    def change_project(payload):
        guide = GuideFile(name="new guide", words=400, sha256="new-guide", path="users/test/guides/new.txt")
        rt.store.update_project(pid, lambda p: p.model_copy(update={"guide": guide}))
        return client.models.default("p_plan", payload)

    client.models.overrides["p_plan"] = change_project
    job = _run(client, pid, "PLAN")
    assert job["status"] == "FAILED" and job["failure"]["code"] == "INPUTS_CHANGED"
    assert job["billing"]["charged"] == 0
    assert client.get(f"/api/projects/{pid}", headers=STUDENT).json()["plan"] is None


def test_complete_pdf_refuses_omission_and_draft_is_labelled(client, monkeypatch):
    pid = _create(client)["id"]
    monkeypatch.setattr(proposals, "_export", lambda rt, user, p, final: (b"docx", "Proposal.docx"))
    monkeypatch.setattr(proposals, "to_latex", lambda data: Result(tex="", omitted=1))
    monkeypatch.setattr(proposals, "compile_pdf", lambda result: (b"%PDF-test", ""))
    refused = client.get(f"/api/projects/{pid}/export.pdf?final=true", headers=STUDENT)
    assert refused.status_code == 400 and refused.json()["code"] == "PDF_INCOMPLETE"
    draft = client.get(f"/api/projects/{pid}/export.pdf", headers=STUDENT)
    assert draft.status_code == 200 and "incomplete" in draft.headers["content-disposition"]
    cached = client.get(f"/api/projects/{pid}/export.pdf", headers=STUDENT)
    assert cached.status_code == 200 and "incomplete" in cached.headers["content-disposition"]
    assert client.get(f"/api/projects/{pid}/export.pdf?final=true", headers=STUDENT).json()["code"] == "PDF_INCOMPLETE"


def test_finish_context_keeps_every_heading_and_expands_neighbors(monkeypatch):
    planned = [SimpleNamespace(key=f"s{i}") for i in range(12)]
    monkeypatch.setattr(pipeline.rulebook, "sections", lambda *args: planned)
    sections = [
        ChapterSection(key=f"s{i}", number=f"1.{i}", heading=f"Heading {i}", paragraphs=[f"Unique{i} " * 300])
        for i in range(12) if i != 10
    ]
    base = ChapterDocument(number=1, title="Chapter One", plan_version=1, sections=sections, cited=[], words=3300, missing=["s10"])
    monkeypatch.setattr(pipeline, "_base_document", lambda ctx, inp: base)
    inp = SimpleNamespace(step="COMPLETE", plan=object(), rulebook="test", chapter=1, inputs=SimpleNamespace(level="MASTERS"), only=["s10"])
    rows = pipeline._finish_context(SimpleNamespace(), inp)["approvedSections"]
    assert [row["heading"] for row in rows] == [s.heading for s in sections]
    assert len(rows[-1]["text"]) > len(rows[0]["text"])  # s11 is next to the missing s10
    assert len(rows[-2]["text"]) > len(rows[0]["text"])  # s9 is next to the missing s10
    assert sum(len(row["number"]) + len(row["heading"]) + len(row["text"]) + 40 for row in rows) <= 9000
