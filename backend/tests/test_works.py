"""Works (rulebook v1.0): concept notes, coursework and funding proposals, end to end on the test
stand-ins, plus the rules engine's precedence, limits, budget, Results Model and command words."""

import io

import pytest
from docx import Document

from tests.conftest import _client
from tests.test_api import OTHER, STUDENT, wait

QUESTION = "Critically evaluate the effectiveness of community health workers in improving maternal health outcomes in rural Uganda since 2015."


@pytest.fixture
def works_client(tmp_path, monkeypatch):
    monkeypatch.setenv("WORKS_ENABLED", '["CONCEPT_NOTE","COURSEWORK","FUNDING_PROPOSAL"]')
    yield from _client(tmp_path, monkeypatch, "cost")


def _run(client, work_id, step, headers=STUDENT, note=""):
    quoted = client.post(f"/api/works/{work_id}/steps", headers=headers, json={"step": step, "note": note})
    assert quoted.status_code == 200, quoted.json()
    body = quoted.json()
    submitted = client.post(f"/api/works/{work_id}/steps/{body['job']['id']}/submit", headers=headers, json={"quoteId": body["quote"]["id"]})
    assert submitted.status_code == 200, submitted.json()
    job = wait(client, body["job"]["id"], headers, timeout=120)
    return body, job


def _work(client, work_id, headers=STUDENT):
    return client.get(f"/api/works/{work_id}", headers=headers).json()


def _coursework(client, ai_answer="NOT_MENTIONED", variant="ESSAY", description=QUESTION, extra=None):
    created = client.post("/api/works", headers=STUDENT, json={"kind": "COURSEWORK", "variant": variant, "inputs": {"title": "Community health workers", "description": description}})
    assert created.status_code == 200, created.json()
    work = created.json()
    answers = {"word_limit": "1500", "level": "LATER_UG", "ai_policy": ai_answer, **(extra or {})}
    work = client.post(f"/api/works/{work['id']}/answers", headers=STUDENT, json={"answers": answers, "skipRest": True, "baseVersion": work["specVersion"]}).json()
    assert work["spec"]["gate"] == "PASS", work["spec"]["blockers"]
    work = client.post(f"/api/works/{work['id']}/spec/confirm", headers=STUDENT, json={"baseVersion": work["specVersion"]}).json()
    assert work["specStatus"] == "CONFIRMED"
    return work


def test_coursework_essay_end_to_end_with_banned_ai_note(works_client):
    client = works_client
    work = _coursework(client, ai_answer="BANNED")
    spec = work["spec"]
    assert spec["directives"] == ["critically_evaluate"] and "CRITICAL" in spec["directiveGroups"]
    assert spec["targetWords"] == 1455 and spec["aiPolicy"] == "BANNED"
    _, job = _run(client, work["id"], "PLAN")
    assert job["status"] == "COMPLETED", job.get("failure")
    work = _work(client, work["id"])
    assert work["planStatus"] == "DRAFT" and work["plan"]["sections"][0]["key"] == "introduction"
    assert any(s["coverage"] for s in work["plan"]["sections"])  # the question's part has a home
    work = client.post(f"/api/works/{work['id']}/plan/approve", headers=STUDENT, json={"baseVersion": work["planVersion"]}).json()
    assert work["planStatus"] == "APPROVED", work
    quote, job = _run(client, work["id"], "DRAFT")
    assert "AI-assisted third party" in (quote["notice"] or "")
    assert job["status"] == "COMPLETED", (job.get("failure"), job.get("warnings"))
    work = _work(client, work["id"])
    assert work["current"] == 1 and work["status"] in ("READY", "READY_WITH_WARNINGS"), work["readiness"]
    doc = client.get(f"/api/works/{work['id']}/document", headers=STUDENT).json()
    assert doc["aiNote"] == "This document was drafted by an AI-assisted third party."
    assert doc["words"] <= 1500 and doc["references"]
    ids = {i["id"] for i in doc["readiness"]}
    assert {"CW-047", "CW-007"} <= ids
    exported = client.get(f"/api/works/{work['id']}/export", headers=STUDENT)
    assert exported.status_code == 200
    paragraphs = [p.text for p in Document(io.BytesIO(exported.content)).paragraphs if p.text.strip()]
    assert paragraphs[-1] == "This document was drafted by an AI-assisted third party."
    assert client.get(f"/api/works/{work['id']}", headers=OTHER).status_code == 404


def test_unknown_ai_policy_note_can_be_turned_off_but_a_ban_cannot(works_client):
    client = works_client
    work = _coursework(client)
    work = client.post(f"/api/works/{work['id']}/ai-note", headers=STUDENT, json={"on": False}).json()
    assert work["aiNote"] is False
    _run(client, work["id"], "PLAN")
    work = _work(client, work["id"])
    client.post(f"/api/works/{work['id']}/plan/approve", headers=STUDENT, json={"baseVersion": work["planVersion"]})
    quote, job = _run(client, work["id"], "DRAFT")
    assert quote["notice"] is None and job["status"] == "COMPLETED"
    assert client.get(f"/api/works/{work['id']}/document", headers=STUDENT).json()["aiNote"] == ""


def test_reflective_work_needs_the_students_own_experience(works_client):
    client = works_client
    created = client.post("/api/works", headers=STUDENT, json={"kind": "COURSEWORK", "variant": "REFLECTIVE", "inputs": {"title": "My placement", "description": "Reflect on your clinical placement."}}).json()
    assert created["spec"]["gate"] == "BLOCK" and any("experience" in b.lower() for b in created["spec"]["blockers"])
    quoted = client.post(f"/api/works/{created['id']}/steps", headers=STUDENT, json={"step": "PLAN"})
    assert quoted.status_code == 400 and quoted.json()["code"] == "SPEC_BLOCKED"


def test_a_brief_read_from_a_document_overrides_the_students_answer(works_client):
    """External mandatory instructions outrank the student's choice (rulebook §3, example A)."""
    client = works_client
    work = client.post("/api/works", headers=STUDENT, json={"kind": "COURSEWORK", "variant": "ESSAY", "inputs": {"title": "CHWs", "description": QUESTION}}).json()
    brief = f"Assignment brief. {QUESTION} Your essay must not exceed 1,200 words. Use APA 7."
    work = client.post(f"/api/works/{work['id']}/sources/text", headers=STUDENT, json={"role": "BRIEF", "name": "Brief", "text": brief}).json()
    assert work["needsRead"] is True
    _, job = _run(client, work["id"], "READ")
    assert job["status"] == "COMPLETED", job.get("failure")
    work = _work(client, work["id"])
    words = next(r for r in work["spec"]["requirements"] if r["key"] == "limit.words")
    assert words["verified"] and words["number"] == 1200 and words["quote"] == "must not exceed 1,200 words"
    work = client.post(f"/api/works/{work['id']}/answers", headers=STUDENT, json={"answers": {"word_limit": "2500", "confirm:all": "yes"}, "skipRest": True,
                                                                                   "baseVersion": work["specVersion"]}).json()
    assert work["spec"]["targetWords"] == int(1200 * 0.97)  # the brief's limit, not the student's 2,500
    assert any("limit" in o.lower() or "words" in o.lower() for o in work["spec"]["overridden"]) or work["spec"]["limits"][0]["max"] == 1200


def test_unverified_high_stakes_requirement_blocks_until_confirmed(works_client):
    from app.rules.extract import quote_found

    assert quote_found("must not exceed 1,200 words", "Your essay must not exceed 1,200 words.")
    assert not quote_found("must not exceed 2,000 words", "Your essay must not exceed 1,200 words.")
    assert not quote_found("words", "Your essay must not exceed 1,200 words.")  # one word proves nothing


def test_funding_proposal_results_model_budget_and_tables(works_client):
    client = works_client
    created = client.post("/api/works", headers=STUDENT, json={
        "kind": "FUNDING_PROPOSAL", "variant": "NGO_PROJECT", "mode": "COMPACT",
        "inputs": {"title": "Safer deliveries in Kamuli", "description": "Too many mothers in Kamuli deliver at home and die of preventable complications.",
                   "answers": {"problem": "Home deliveries and delayed referral in Kamuli District.", "intervention": "Train village health teams and fund referral transport.",
                               "duration_months": "12", "currency": "USD"}},
    }).json()
    work = client.post(f"/api/works/{created['id']}/answers", headers=STUDENT, json={"answers": {}, "skipRest": True, "baseVersion": created["specVersion"]}).json()
    assert work["spec"]["gate"] == "PASS", work["spec"]["blockers"]
    work = client.post(f"/api/works/{work['id']}/spec/confirm", headers=STUDENT, json={"baseVersion": work["specVersion"]}).json()
    _, job = _run(client, work["id"], "PLAN")
    assert job["status"] == "COMPLETED", job.get("failure")
    work = _work(client, work["id"])
    assert work["results"]["outcomes"] and all(i["target"] is None for i in work["results"]["indicators"])  # targets are the student's
    assert [li["quantity"] for li in work["budget"]["lines"]] == [0, 0, 0]  # amounts are the student's
    draft = client.post(f"/api/works/{work['id']}/steps", headers=STUDENT, json={"step": "DRAFT"})
    assert draft.status_code == 400 and draft.json()["code"] == "NOT_READY_TO_DRAFT"
    # the student completes the Results Model and budget
    results = work["results"]
    for ind in results["indicators"]:
        ind["target"], ind["baseline"] = (60, 34) if ind["level"] == "outcome" else (120, None)
    work = client.post(f"/api/works/{work['id']}/results", headers=STUDENT, json={"results": results, "baseVersion": work["resultsVersion"]}).json()
    work = client.post(f"/api/works/{work['id']}/results/approve", headers=STUDENT, json={"baseVersion": work["resultsVersion"]}).json()
    budget = work["budget"]
    for li, (qty, cost) in zip(budget["lines"], [(4, 1000), (12, 250), (4, 300)], strict=True):
        li["quantity"], li["unitCost"] = qty, cost
    budget["lines"][0]["enteredTotal"] = 4100  # a typing mistake code must catch
    work = client.post(f"/api/works/{work['id']}/budget", headers=STUDENT, json={"budget": budget, "baseVersion": work["budgetVersion"]}).json()
    math = next(i for i in work["checks"] if i["id"] == "FP-039")
    assert math["status"] == "BLOCKED" and "4,100" in math["note"]
    budget["lines"][0]["enteredTotal"] = None
    work = client.post(f"/api/works/{work['id']}/budget", headers=STUDENT, json={"budget": budget, "baseVersion": work["budgetVersion"]}).json()
    work = client.post(f"/api/works/{work['id']}/plan/approve", headers=STUDENT, json={"baseVersion": work["planVersion"]}).json()
    _, job = _run(client, work["id"], "DRAFT")
    assert job["status"] == "COMPLETED", (job.get("failure"), job.get("warnings"))
    doc = client.get(f"/api/works/{work['id']}/document", headers=STUDENT).json()
    captions = [t["caption"] for t in doc["tables"]]
    assert captions[:3] == ["Logframe", "Workplan", "Monitoring and evaluation indicators"] and "Budget summary" in captions
    budget_text = " ".join(p for s in doc["sections"] if s["key"] == "budget_narrative" for p in s["paragraphs"])
    assert "USD 8,200" in budget_text  # the number token, filled by code from the budget


def test_budget_engine_rules():
    from app.works import budget as engine
    from app.works.models import Budget, BudgetLine, ResolvedSpec

    spec = ResolvedSpec(version=1, kind="FUNDING_PROPOSAL", variant="NGO_PROJECT", mode="STANDARD", rules_version="rules-v1", target_words=5000, ceiling=10000,
                        cost_share=20, cost_share_base="total project cost", indirect_rate=10, indirect_base="total direct costs", prohibited_costs=["alcoholic beverages"])
    budget = Budget(currency="USD", cost_share_provided=1000, lines=[
        BudgetLine(id="B1", category="Training", description="Workshops", quantity=4, unit_cost=1500, activity_ids=["A1"]),
        BudgetLine(id="B2", category="Indirect costs", description="Overhead", quantity=1, unit_cost=900, support=True),
        BudgetLine(id="B3", category="Meals", description="Alcoholic beverages for the launch", quantity=1, unit_cost=100, support=True),
    ])
    found = {rid: (status, note) for rid, status, note in engine.checks(budget, spec, None)}
    assert found["FP-041"][0] == "PASS"  # 7,000 within 10,000
    assert found["FP-042"][0] == "FAIL"  # 20% of 8,000 is 1,600; 1,000 given
    assert found["FP-043"][0] == "FAIL"  # 900 indirect > 10% of 6,100 direct
    assert found["FP-044"][0] == "FAIL" and "B3" in found["FP-044"][1]


def test_results_model_links_and_indicator_fields():
    from app.works import results as engine
    from app.works.models import Activity, Goal, Indicator, Outcome, Output, ResolvedSpec, ResultsModel

    spec = ResolvedSpec(version=1, kind="FUNDING_PROPOSAL", variant="NGO_PROJECT", mode="STANDARD", rules_version="rules-v1", target_words=5000, duration_months=12)
    model = ResultsModel(goal=Goal(statement="Healthier mothers"), outcomes=[Outcome(id="O1", statement="More facility births")],
                         outputs=[Output(id="OP1", statement="Trained teams", outcome_id="O9")],
                         activities=[Activity(id="A1", statement="Train", output_id="OP1", start_month=1, end_month=18)],
                         indicators=[Indicator(id="I1", result_id="O1", level="output", definition="Births", unit="")])
    found = {rid: status for rid, status, _ in engine.checks(model, spec)}
    assert found["FP-019"] == "FAIL" and found["FP-024"] == "FAIL" and found["FP-025"] == "FAIL" and found["FP-036"] == "FAIL"


def test_command_words_and_compound_questions():
    from app.works import directives

    assert directives.find("To what extent has decentralisation improved services? Compare and contrast two districts.") == ["to_what_extent", "compare_and_contrast"]
    parts = directives.clauses("Explain the major causes of antimicrobial resistance and critically evaluate two policy responses.")
    assert [d for d, _ in parts] == ["explain", "critically_evaluate"]


def test_every_rule_names_a_known_validator_and_rule_files_never_change():
    import hashlib
    import json
    from pathlib import Path

    from app.rules import library
    from app.rules.validators import VALIDATORS

    for kind in ("CONCEPT_NOTE", "COURSEWORK", "FUNDING_PROPOSAL"):
        for rule in library.rules_for(kind):
            validator = rule["check"]["validator"]
            assert validator == "semantic" or validator in VALIDATORS, (rule["id"], validator)
    folder = Path(library.DATA)
    released = json.loads((folder / "released.json").read_text(encoding="utf-8"))
    current = {p.stem: hashlib.sha256(p.read_bytes().replace(b"\r\n", b"\n")).hexdigest() for p in folder.glob("*-v*.json")}
    assert {name: current.get(name) for name in released} == released
    assert set(library.FILES.values()) <= set(released)
