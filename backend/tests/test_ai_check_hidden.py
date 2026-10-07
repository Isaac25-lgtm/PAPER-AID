"""The AI checker is hidden by default (owner decision 2026-10-07) until a validated detector is
integrated: the "Check for AI" step is not offered and the server refuses it, while Paper Check's
redraft, source check and formatting stay open."""

from app.core.config import Settings
from app.jobs.service import availability
from tests.test_api import STUDENT, fixture_bytes


def test_the_check_is_hidden_by_default_and_paper_check_stays_open():
    offered = availability(Settings(_env_file=None, vertex_project="paperaid"))
    assert offered["AI_CHECK"] == "soon"
    assert offered["REFINE"] == offered["REDRAFT"] == offered["FORMAT"] == offered["SOURCE_CHECK"] == "available"
    assert availability(Settings(_env_file=None, vertex_project="paperaid", ai_check_enabled=True))["AI_CHECK"] == "available"


def test_a_hidden_check_is_refused_and_a_redraft_still_quotes(client, monkeypatch):
    from app.runtime import get_runtime

    monkeypatch.setattr(get_runtime().settings, "ai_check_enabled", False)
    job_id = client.post("/api/jobs", headers=STUDENT).json()["id"]
    client.post(f"/api/jobs/{job_id}/files/source", headers=STUDENT, files={"file": ("essay.docx", fixture_bytes("simple_essay.docx"), "application/octet-stream")})
    assert client.get("/api/config", headers=STUDENT).json()["availability"]["AI_CHECK"] == "soon"
    refused = client.post(f"/api/jobs/{job_id}/quote", headers=STUDENT, json={"selection": {"writing": "AI_CHECK"}})
    assert refused.status_code == 400 and refused.json()["code"] == "SERVICE_UNAVAILABLE"
    redraft = client.post(f"/api/jobs/{job_id}/quote", headers=STUDENT, json={"selection": {"writing": "REDRAFT"}})
    assert redraft.status_code == 200, redraft.json()
