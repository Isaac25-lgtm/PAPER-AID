"""Codex's review of the four-model release (2026-09-30): each finding with its correct outcome."""

import io

import pytest
from docx import Document

from app.latex.convert import Result
from app.proposals import service as proposals
from app.runtime import get_runtime
from tests.conftest import fixture_bytes
from tests.test_api import STUDENT, get_quote, wait
from tests.test_audit_20260928 import _chapter_ready
from tests.test_finish_chapter import _chapter_price
from tests.test_profiles import _guide
from tests.test_proposals import _create, _run

# --- #1: writing-pattern feedback only (owner decision 2026-09-30) -----------------------------------


def _writing_report(client):
    job_id = client.post("/api/jobs", headers=STUDENT).json()["id"]
    client.post(f"/api/jobs/{job_id}/files/source", headers=STUDENT, files={"file": ("simple_essay.docx", fixture_bytes("simple_essay.docx"), "application/octet-stream")})
    priced = get_quote(client, job_id, {"writing": "AI_CHECK", "academic": False})
    assert [line["label"].startswith("Writing check") for line in priced["lines"]] == [True]
    client.post(f"/api/jobs/{job_id}/submit", headers=STUDENT, json={"quoteId": priced["id"]})
    wait(client, job_id)
    report = Document(io.BytesIO(client.get(f"/api/jobs/{job_id}/outputs/writing-report", headers=STUDENT).content))
    return "\n".join(p.text for p in report.paragraphs)


def test_students_get_writing_feedback_and_no_ai_score(client):
    assert client.get("/api/config").json()["aiScore"] is False
    text = _writing_report(client)
    assert "Writing patterns" in text and "does not detect AI" in text
    assert "AI-likeness" not in text and "Low (confidence" not in text


def test_the_score_returns_only_when_switched_on(client, monkeypatch):
    monkeypatch.setattr(get_runtime().settings, "show_ai_score", True)
    assert client.get("/api/config").json()["aiScore"] is True
    assert "Estimated AI-likeness" in _writing_report(client)


# --- #2: a step runs only on the guide and structure it was priced on ------------------------------


def _with_guide(client, text="research proposal"):
    pid = _create(client)["id"]
    assert client.post(f"/api/projects/{pid}/guide", headers=STUDENT, files={"file": ("guide.docx", _guide(text), "application/octet-stream")}).status_code == 200
    return pid


def test_a_profile_priced_on_one_guide_cannot_run_on_another(client):
    pid = _with_guide(client)
    quoted = client.post(f"/api/projects/{pid}/steps", headers=STUDENT, json={"step": "PROFILE"}).json()
    replaced = client.post(f"/api/projects/{pid}/guide", headers=STUDENT, files={"file": ("guide B.docx", _guide("research proposal, second edition"), "application/octet-stream")})
    assert replaced.status_code == 200
    late = client.post(f"/api/projects/{pid}/steps/{quoted['job']['id']}/submit", headers=STUDENT, json={"quoteId": quoted["quote"]["id"]})
    assert late.status_code == 409 and late.json()["code"] == "QUOTE_MISMATCH"


def test_a_plan_priced_before_a_guide_arrived_cannot_run_until_the_student_chooses(client):
    pid = _create(client)["id"]
    quoted = client.post(f"/api/projects/{pid}/steps", headers=STUDENT, json={"step": "PLAN"}).json()
    client.post(f"/api/projects/{pid}/guide", headers=STUDENT, files={"file": ("guide.docx", _guide(), "application/octet-stream")})
    late = client.post(f"/api/projects/{pid}/steps/{quoted['job']['id']}/submit", headers=STUDENT, json={"quoteId": quoted["quote"]["id"]})
    assert late.status_code == 409 and late.json()["code"] == "QUOTE_MISMATCH"


def test_a_guide_replaced_while_its_profile_is_read_saves_nothing_and_costs_nothing(fixed_client):
    pid = _with_guide(fixed_client)
    rt = get_runtime()

    def replaced_meanwhile(payload):  # the student uploads another guide while PaperAid reads the first
        rt.store.update_project(pid, lambda p: p.model_copy(update={"guide": p.guide.model_copy(update={"path": p.guide.path + ".b"})}))
        return fixed_client.models.default("p_profile", payload)

    fixed_client.models.overrides["p_profile"] = replaced_meanwhile
    job = _run(fixed_client, pid, "PROFILE")
    assert job["status"] == "FAILED" and job["failure"]["code"] == "INPUTS_CHANGED" and job["billing"]["charged"] == 0
    assert not fixed_client.get(f"/api/projects/{pid}", headers=STUDENT).json()["rulebook"].startswith("custom-")


# --- #3 and #4: finishes never cost more than one chapter; partial chapters are switched off by default ---


def _approve_only_first(client):
    """Both reviewers approve only the first section they are shown, every time."""

    def review(payload):
        keys = [s["key"] for s in payload["sections"]]
        return {"results": [{"key": k, "grade": "PASS" if i == 0 else "REPAIR", "issues": [] if i == 0 else ["Not yet."], "note": ""} for i, k in enumerate(keys)]}

    client.models.overrides["p_review"] = review
    client.models.overrides["p_review_peer"] = review


def test_many_finishes_together_never_cost_more_than_one_chapter(fixed_client, monkeypatch):
    monkeypatch.setattr(get_runtime().settings, "partial_chapters", True)
    pid = _chapter_ready(fixed_client)
    full = _chapter_price(fixed_client, pid)
    _approve_only_first(fixed_client)
    charged = [_run(fixed_client, pid, "CHAPTER_1")["billing"]["charged"]]
    for _ in range(20):  # one section per finish until none is missing
        chapter = fixed_client.get(f"/api/projects/{pid}/chapters/1", headers=STUDENT).json()
        if not chapter["missing"]:
            break
        job = _run(fixed_client, pid, "COMPLETE_1")
        assert job["status"] == "COMPLETED", job.get("failure")
        charged.append(job["billing"]["charged"])
    assert fixed_client.get(f"/api/projects/{pid}/chapters/1", headers=STUDENT).json()["missing"] == []
    assert len(charged) > 3 and sum(charged) <= full  # every rounding is inside the cap


def test_without_the_switch_a_new_chapter_is_all_or_nothing(fixed_client):
    pid = _chapter_ready(fixed_client)
    _approve_only_first(fixed_client)
    job = _run(fixed_client, pid, "CHAPTER_1")
    assert job["status"] == "FAILED" and job["failure"]["code"] == "DOCUMENT_NOT_APPROVED" and job["billing"]["charged"] == 0


# --- #5: a complete proposal's LaTeX is never offered with content left out --------------------------


def test_a_complete_latex_export_with_content_left_out_is_refused(client, monkeypatch):
    pid = _create(client)["id"]
    monkeypatch.setattr(proposals, "_export", lambda rt, user, p, final: (b"docx", "Proposal.docx"))
    monkeypatch.setattr(proposals, "latex_project", lambda data: (b"PK-zip", Result(tex="", omitted=2)))
    refused = client.get(f"/api/projects/{pid}/export.zip?final=true", headers=STUDENT)
    assert refused.status_code == 400 and refused.json()["code"] == "LATEX_INCOMPLETE"
    draft = client.get(f"/api/projects/{pid}/export.zip", headers=STUDENT)
    assert draft.status_code == 200 and "incomplete" in draft.headers["content-disposition"]


# --- #6: a finish is written, fixed and reviewed with the chapter's approved sections -------------------


def test_a_finish_sees_the_approved_sections(fixed_client, monkeypatch):
    monkeypatch.setattr(get_runtime().settings, "partial_chapters", True)
    pid = _chapter_ready(fixed_client)
    _approve_only_first(fixed_client)
    _run(fixed_client, pid, "CHAPTER_1")
    for task in ("p_review", "p_review_peer"):
        fixed_client.models.overrides.pop(task)
    start = len(fixed_client.models.tasks)
    assert _run(fixed_client, pid, "COMPLETE_1")["status"] == "COMPLETED"
    sent = dict(zip(fixed_client.models.tasks[start:], fixed_client.models.requests[start:], strict=True))
    for task in ("p_brief", "p_draft", "p_review", "p_review_peer"):
        assert '"approvedSections": [{' in sent[task], task


@pytest.mark.parametrize("step", ["PLAN", "CHAPTER_1"])
def test_other_steps_carry_no_finish_context(client, step):
    pid = _chapter_ready(client) if step == "CHAPTER_1" else _create(client)["id"]
    start = len(client.models.tasks)
    _run(client, pid, step)
    assert all("approvedSections" not in r for r in client.models.requests[start:])
