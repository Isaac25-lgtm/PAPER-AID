"""The review workspace (owner request 2026-09-28): academic, evidence, methodology and formatting
findings beside AI-likeness; dismiss and undo; "Fix selected" as a new priced job on exactly those
passages; keeping or rejecting each refined change, and a Word file rebuilt from those choices."""

import io

from docx import Document

from tests.test_api import ADMIN, OTHER, STUDENT, get_quote, start_job, wait

AI_CHECK = {"writing": "AI_CHECK", "formatting": "NONE", "latex": False}


def _run(client, selection, name="simple_essay.docx"):
    job_id, quote = start_job(client, name, selection)
    assert client.post(f"/api/jobs/{job_id}/submit", headers=STUDENT, json={"quoteId": quote["id"]}).status_code == 200
    return wait(client, job_id, timeout=120)


def test_an_ai_check_reports_academic_findings_protected_content_and_the_document(client):
    job = _run(client, AI_CHECK)
    assert job["status"] == "COMPLETED"
    review = job["analysis"]["review"]
    assert any(f["category"] == "ACADEMIC" and f["reason"] == "VAGUE_WORDING" and f["safe"] for f in review)
    assert "academic" in client.models.tasks
    assert job["protected"]["numbers"] >= 0 and "citations" in job["protected"]
    assert any(line["label"].startswith("Academic, evidence and method review") for line in job["quote"]["lines"])
    document = client.get(f"/api/jobs/{job['id']}/document", headers=STUDENT).json()
    ids = {b["id"] for b in document["blocks"]}
    assert all(f["blockId"] in ids for f in job["analysis"]["findings"] + review)
    assert client.get(f"/api/jobs/{job['id']}/document", headers=OTHER).status_code == 404


def test_non_academic_work_skips_the_academic_review(client):
    job = _run(client, {**AI_CHECK, "academic": False})
    assert "academic" not in client.models.tasks
    assert not [f for f in job["analysis"]["review"] if f["category"] != "FORMATTING"]
    assert not any("Academic" in line["label"] for line in job["quote"]["lines"])


def test_a_finding_can_be_dismissed_and_restored(client):
    job = _run(client, AI_CHECK)
    finding = job["analysis"]["review"][0]["id"]
    url = f"/api/jobs/{job['id']}/findings/{finding}"
    assert client.post(url, headers=STUDENT, json={"dismissed": True}).json()["dismissed"] == [finding]
    assert client.post(url, headers=STUDENT, json={"dismissed": False}).json()["dismissed"] == []
    assert client.post(f"/api/jobs/{job['id']}/findings/nope", headers=STUDENT, json={"dismissed": True}).status_code == 404
    assert client.post(url, headers=OTHER, json={"dismissed": True}).status_code == 404


def test_fix_selected_refines_exactly_the_chosen_passages(client):
    check = _run(client, AI_CHECK)
    chosen = check["analysis"]["review"][0]
    draft = client.post(f"/api/jobs/{check['id']}/fix", headers=STUDENT, json={"findingIds": [chosen["id"]]}).json()
    assert draft["status"] == "DRAFT" and draft["selection"]["onlyBlocks"] == [chosen["blockId"]] and draft["sourceJob"] == check["id"]
    quote = get_quote(client, draft["id"], draft["selection"])
    assert client.post(f"/api/jobs/{draft['id']}/submit", headers=STUDENT, json={"quoteId": quote["id"]}).status_code == 200
    job = wait(client, draft["id"], timeout=120)
    assert job["status"] == "COMPLETED"
    assert {c["blockId"] for c in job["refinement"]["changes"]} == {chosen["blockId"]}


def test_fix_all_safe_issues_never_includes_evidence_or_method_findings(client):
    client.models.overrides["academic"] = lambda p: {
        "findings": [
            {"id": p["passages"][0]["id"], "category": "METHOD", "code": "OBJECTIVE_METHOD_MISMATCH", "severity": "major", "excerpt": "x", "explanation": "e", "suggestion": "s"},
        ]
    }
    check = _run(client, AI_CHECK)
    method = [f for f in check["analysis"]["review"] if f["category"] == "METHOD"]
    assert method and not method[0]["safe"]
    response = client.post(f"/api/jobs/{check['id']}/fix", headers=STUDENT, json={"safeOnly": True})
    if response.status_code == 200:  # only AI-like findings (all safe) were chosen
        safe_blocks = {f["blockId"] for f in check["analysis"]["findings"]}
        assert set(response.json()["selection"]["onlyBlocks"]) <= safe_blocks
    else:
        assert response.json()["code"] == "NOTHING_TO_FIX"


def test_a_rejected_change_keeps_the_students_wording_in_the_rebuilt_file(client):
    job = _run(client, {"writing": "REFINE", "intensity": "STANDARD", "formatting": "NONE", "latex": False})
    changed = [c for c in job["refinement"]["changes"] if not c["kept"] and c["before"] != c["after"]]
    assert len(changed) >= 1
    full = client.get(f"/api/jobs/{job['id']}/document", headers=STUDENT).json()["changes"]
    assert {c["blockId"] for c in full} >= {c["blockId"] for c in changed}  # the same camelCase contract as the job
    target = changed[0]
    assert any(o["id"] == "paper-apa" for o in job["outputs"])  # the academic-formatting option at download
    updated = client.post(f"/api/jobs/{job['id']}/changes/{target['blockId']}", headers=STUDENT, json={"accepted": False}).json()
    assert updated["rejectedChanges"] == [target["blockId"]]
    rebuilt = client.post(f"/api/jobs/{job['id']}/rebuild", headers=STUDENT).json()
    assert any(o["id"] == "paper-reviewed" for o in rebuilt["outputs"])
    data = client.get(f"/api/jobs/{job['id']}/outputs/paper-reviewed", headers=STUDENT).content
    text = "\n".join(p.text for p in Document(io.BytesIO(data)).paragraphs)
    assert target["before"].split(".")[0] in text
    for other in changed[1:]:
        assert other["after"].split(".")[0] in text  # the other changes are still there


def test_deep_redraft_quote_says_how_much_will_change(client):
    job_id, _ = start_job(client, "simple_essay.docx", {"writing": "REDRAFT", "formatting": "NONE", "latex": False})
    job = client.get(f"/api/jobs/{job_id}", headers=STUDENT).json()
    assert 0 < job["estimate"]["intervention"] <= 1


def test_admin_views_never_show_review_text(client):
    job = _run(client, AI_CHECK)
    admin = client.get(f"/api/admin/jobs/{job['id']}", headers=ADMIN).json()
    assert admin["job"]["analysis"]["review"] and all(f["excerpt"] == "" and f["explanation"] == "" for f in admin["job"]["analysis"]["review"])
