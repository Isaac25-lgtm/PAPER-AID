"""Phase 3 (owner decision 2026-09-29): three sections. Source check and LaTeX are steps inside them,
so a paper's sources can be checked on their own from its results, and a proposal downloads as LaTeX."""

import io
import zipfile

from docx import Document

from tests.conftest import fixture_bytes
from tests.test_api import STUDENT, get_quote, wait
from tests.test_audit_20260928 import _chapter_ready
from tests.test_audit_20260928 import _run as run_step


def test_a_source_check_runs_on_its_own_with_its_own_report(client):
    job_id = client.post("/api/jobs", headers=STUDENT).json()["id"]
    client.post(f"/api/jobs/{job_id}/files/source", headers=STUDENT, files={"file": ("simple_essay.docx", fixture_bytes("simple_essay.docx"), "application/octet-stream")})
    priced = get_quote(client, job_id, {"writing": "NONE", "sourceCheck": True})
    assert [line["service"] for line in priced["lines"]] == ["SOURCE_CHECK"]  # no second AI Check to pay for
    client.post(f"/api/jobs/{job_id}/submit", headers=STUDENT, json={"quoteId": priced["id"]})
    job = wait(client, job_id, timeout=120)
    assert job["status"] == "COMPLETED" and job["research"] is not None and job["analysis"] is None
    assert "analyse" not in client.models.tasks
    report = Document(io.BytesIO(client.get(f"/api/jobs/{job_id}/outputs/source-report", headers=STUDENT).content))
    text = "\n".join(p.text for p in report.paragraphs)
    assert "Source check" in text and "second AI" not in text


def test_a_proposal_downloads_as_a_latex_project(client):
    pid = _chapter_ready(client)
    assert run_step(client, pid, "CHAPTER_1")["status"] == "COMPLETED"
    response = client.get(f"/api/projects/{pid}/export.zip", headers=STUDENT)
    assert response.status_code == 200 and response.headers["content-type"] == "application/zip"
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        assert "main.tex" in archive.namelist() and "main.pdf" not in archive.namelist()  # converted by code, not compiled
        assert "\\section" in archive.read("main.tex").decode("utf-8")
