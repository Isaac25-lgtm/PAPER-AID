"""Works: calls, eligibility, forms, conflicts, closed reading lists, revisions, deletion, prices and
the model layer (rulebook v1.0 §28 golden cases, on the test stand-ins)."""

import json

import pytest

from tests.conftest import _client
from tests.fake_models import ABSTRACT
from tests.test_api import STUDENT, wait
from tests.test_works import QUESTION, _coursework, _run, _work

CALL = """Call for concept notes: Safer Motherhood Fund 2027.
Concept notes must not exceed 1,500 words. The funding ceiling is USD 50,000.
Eligibility: Registered non-governmental organisations based in Uganda
Priority: Maternal and newborn health in rural districts
Priority: Community health systems
Box: Project summary (900 characters)
Box: Problem and need (2000 characters)
"""


@pytest.fixture
def works_client(tmp_path, monkeypatch):
    monkeypatch.setenv("WORKS_ENABLED", '["CONCEPT_NOTE","COURSEWORK","FUNDING_PROPOSAL"]')
    yield from _client(tmp_path, monkeypatch, "cost")


def _concept(client, variant="FUNDING_CONCEPT", answers=None):
    body = {"kind": "CONCEPT_NOTE", "variant": variant, "mode": "STANDARD",
            "inputs": {"title": "Safer deliveries in Kamuli", "description": "Too many mothers in Kamuli deliver at home without skilled care.",
                       "answers": {"problem": "Home deliveries in Kamuli.", "intervention": "Village health teams and referral transport.", **(answers or {})}}}
    created = client.post("/api/works", headers=STUDENT, json=body)
    assert created.status_code == 200, created.json()
    return created.json()


def _answer(client, work, answers, skip=True):
    response = client.post(f"/api/works/{work['id']}/answers", headers=STUDENT, json={"answers": answers, "skipRest": skip, "baseVersion": work["specVersion"]})
    assert response.status_code == 200, response.json()
    return response.json()


def test_a_call_with_eligibility_and_form_boxes_makes_an_exploratory_form_draft(works_client):
    """Golden cases CN-4 (character-limited portal) and CN-6 (failed eligibility)."""
    client = works_client
    work = _concept(client)
    work = client.post(f"/api/works/{work['id']}/sources/text", headers=STUDENT, json={"role": "CALL", "name": "Call", "text": CALL}).json()
    _, job = _run(client, work["id"], "READ")
    assert job["status"] == "COMPLETED", job.get("failure")
    work = _work(client, work["id"])
    spec = work["spec"]
    assert spec["ceiling"] == 50000 and [f["maxCharacters"] for f in spec["fields"]] == [900, 2000] and spec["flags"]["form_mode"]
    eligible = next(q for q in spec["questions"] if q["id"].startswith("eligible:"))
    assert spec["gate"] == "BLOCK"
    work = _answer(client, work, {eligible["id"]: "no", "confirm:all": "yes"})
    assert any("exploratory" in b for b in work["spec"]["blockers"])
    work = _answer(client, work, {"exploratory": "yes"})
    assert work["spec"]["gate"] == "PASS" and work["spec"]["exploratory"], work["spec"]["blockers"]
    work = client.post(f"/api/works/{work['id']}/spec/confirm", headers=STUDENT, json={"baseVersion": work["specVersion"]}).json()
    _, job = _run(client, work["id"], "PLAN")
    work = _work(client, work["id"])
    assert [s["fieldId"] for s in work["plan"]["sections"]] == ["field1", "field2"]  # planned box by box
    work = client.post(f"/api/works/{work['id']}/plan/approve", headers=STUDENT, json={"baseVersion": work["planVersion"]}).json()
    quote, job = _run(client, work["id"], "DRAFT")
    assert "exploratory" in quote["notice"] and "exploratory draft" in quote["quote"]["lines"][0]["label"]
    assert job["status"] == "COMPLETED", (job.get("failure"), job.get("warnings"))
    doc = client.get(f"/api/works/{work['id']}/document", headers=STUDENT).json()
    assert doc["status"] == "NOT_READY" and doc["exploratory"]
    assert all(len(" ".join(s["paragraphs"])) <= limit for s, limit in zip(doc["sections"], [900, 2000], strict=True))
    boxes = {i["id"]: i for i in doc["readiness"]}
    assert boxes["CN-039"]["status"] == "PASS" and boxes["CN-042"]["status"] == "BLOCKED"


def test_project_concept_note_ends_with_the_decision_requested(works_client):
    client = works_client
    work = _concept(client, "PROJECT_CONCEPT", {"decision": "Approve a six-month pilot."})
    work = _answer(client, work, {})
    client.post(f"/api/works/{work['id']}/spec/confirm", headers=STUDENT, json={"baseVersion": work["specVersion"]})
    _run(client, work["id"], "PLAN")
    work = _work(client, work["id"])
    assert work["plan"]["sections"][-1]["key"] == "decision" and work["spec"]["targetWords"] == 1500


def test_two_documents_that_disagree_must_be_settled_and_an_addendum_wins(works_client):
    """Rulebook §3 example C and golden case: conflicting external instructions pause locking."""
    client = works_client
    work = client.post("/api/works", headers=STUDENT, json={"kind": "COURSEWORK", "variant": "ESSAY", "inputs": {"title": "CHWs", "description": QUESTION}}).json()
    client.post(f"/api/works/{work['id']}/sources/text", headers=STUDENT, json={"role": "BRIEF", "name": "Brief", "text": f"{QUESTION} Your essay must not exceed 1,500 words."})
    work = client.post(f"/api/works/{work['id']}/sources/text", headers=STUDENT, json={"role": "RUBRIC", "name": "Rubric", "text": "Essays must not exceed 2,000 words."}).json()
    _run(client, work["id"], "READ")
    work = _work(client, work["id"])
    conflict = next(q for q in work["spec"]["questions"] if q["id"] == "conflict:limit.words")
    assert work["spec"]["gate"] == "BLOCK" and len(conflict["choices"]) == 2
    brief_limit = next(r for r in work["spec"]["requirements"] if r["key"] == "limit.words" and r["number"] == 1500)
    work = _answer(client, work, {"conflict:limit.words": brief_limit["id"], "confirm:all": "yes"})
    assert work["spec"]["limits"][0]["max"] == 1500 and work["spec"]["conflicts"][0]["chosen"] == brief_limit["id"]

    funding = _concept(client)
    client.post(f"/api/works/{funding['id']}/sources/text", headers=STUDENT, json={"role": "CALL", "name": "Call", "text": "Concept notes must not exceed 1,500 words."})
    funding = client.post(f"/api/works/{funding['id']}/sources/text", headers=STUDENT, json={"role": "ADDENDUM", "name": "Addendum", "text": "Concept notes must not exceed 2,000 words."}).json()
    _run(client, funding["id"], "READ")
    funding = _work(client, funding["id"])
    assert not funding["spec"]["conflicts"] and funding["spec"]["limits"][0]["max"] == 2000  # the addendum amends the call


def test_a_closed_reading_list_is_the_only_source(works_client):
    client = works_client
    work = client.post("/api/works", headers=STUDENT, json={"kind": "COURSEWORK", "variant": "ESSAY", "inputs": {"title": "Vaccine uptake", "description": QUESTION}}).json()
    client.post(f"/api/works/{work['id']}/sources/text", headers=STUDENT, json={"role": "BRIEF", "name": "Brief", "text": f"{QUESTION} Use only the set readings."})
    work = client.post(f"/api/works/{work['id']}/sources/text", headers=STUDENT, json={"role": "READING", "name": "Reading 1", "text": "Vaccine uptake in Mukono\n" + ABSTRACT}).json()
    _run(client, work["id"], "READ")
    work = _work(client, work["id"])
    assert work["spec"]["sourcePolicy"] == "CLOSED"
    work = _answer(client, work, {"word_limit": "1500", "level": "LATER_UG", "confirm:all": "yes"})
    client.post(f"/api/works/{work['id']}/spec/confirm", headers=STUDENT, json={"baseVersion": work["specVersion"]})
    searched_before = len(client.models.searched)
    _run(client, work["id"], "PLAN")
    work = _work(client, work["id"])
    client.post(f"/api/works/{work['id']}/plan/approve", headers=STUDENT, json={"baseVersion": work["planVersion"]})
    _, job = _run(client, work["id"], "DRAFT")
    assert job["status"] == "COMPLETED", (job.get("failure"), job.get("warnings"))
    assert len(client.models.searched) == searched_before  # no scholarly index or web search
    doc = client.get(f"/api/works/{work['id']}/document", headers=STUDENT).json()
    assert doc["references"] and all("Mugisha" in r for r in doc["references"])
    assert next(i for i in doc["readiness"] if i["id"] == "CW-049")["status"] == "PASS"


def test_ask_for_changes_revises_only_the_chosen_section(works_client):
    client = works_client
    work = _coursework(client)
    _run(client, work["id"], "PLAN")
    work = _work(client, work["id"])
    client.post(f"/api/works/{work['id']}/plan/approve", headers=STUDENT, json={"baseVersion": work["planVersion"]})
    _run(client, work["id"], "DRAFT")
    before = client.get(f"/api/works/{work['id']}/document", headers=STUDENT).json()
    work = client.post(f"/api/works/{work['id']}/requests", headers=STUDENT, json={"instruction": "Say more about supervision.", "sections": ["conclusion"]}).json()
    _, job = _run(client, work["id"], "REVISE")
    assert job["status"] == "COMPLETED", job.get("failure")
    work = _work(client, work["id"])
    assert work["current"] == 2 and work["requests"][0]["status"] == "APPLIED"
    after = client.get(f"/api/works/{work['id']}/document", headers=STUDENT).json()
    changed = [a["key"] for a, b in zip(after["sections"], before["sections"], strict=True) if a["paragraphs"] != b["paragraphs"]]
    assert changed == ["conclusion"]


def test_a_stale_edit_is_refused(works_client):
    client = works_client
    work = _coursework(client)
    _run(client, work["id"], "PLAN")
    work = _work(client, work["id"])
    stale = client.post(f"/api/works/{work['id']}/plan", headers=STUDENT, json={"plan": work["plan"], "baseVersion": work["planVersion"] - 1})
    assert stale.status_code == 409 and stale.json()["code"] == "VERSION_CHANGED"
    locked = {**work["plan"], "sections": [s for s in work["plan"]["sections"] if s["key"] != "introduction"]}
    refused = client.post(f"/api/works/{work['id']}/plan", headers=STUDENT, json={"plan": locked, "baseVersion": work["planVersion"]})
    assert refused.status_code == 400 and refused.json()["code"] == "SECTION_REQUIRED"


def test_deleting_an_account_erases_its_works_and_their_steps(works_client):
    from app.runtime import get_runtime

    client = works_client
    work = _coursework(client)
    _run(client, work["id"], "PLAN")
    rt = get_runtime()
    stored = rt.store.get_work(work["id"])
    jobs, prefix = stored.jobs, stored.storage_prefix()
    assert jobs and rt.files.exists(stored.spec_path)
    rt.store.update_wallet(stored.owner_uid, "student@example.com", lambda w: w.model_copy(update={"available": 0}))  # nothing left to refund
    deleted = client.delete("/api/me", headers=STUDENT)
    assert deleted.status_code == 204, deleted.json()
    assert rt.store.get_work(work["id"]) is None and all(rt.store.get(j) is None for j in jobs)
    assert not rt.files.exists(stored.spec_path) and prefix.startswith("works/")


def test_work_services_are_offered_only_when_switched_on_priced_and_to_testers():
    """A work service shows as coming soon until it is switched on and every price is set; while
    testing is limited to invited testers, the work services are too."""
    from app.core.config import Settings
    from app.jobs.service import User, availability

    keys = {"vertex_project": "paperaid", "pricing_mode": "fixed", "works_public": True}  # the Gemini workflow's Vertex target, not a local .env
    assert availability(Settings(works_enabled=[], **keys))["COURSEWORK"] == "soon"
    unpriced = {k: v for k, v in Settings().fixed_tokens.items() if k != "CW_1500"}
    assert availability(Settings(fixed_tokens=unpriced, works_enabled=["COURSEWORK"], **keys))["COURSEWORK"] == "soon"
    settings = Settings(works_enabled=["COURSEWORK"], **keys)
    assert availability(settings)["COURSEWORK"] == "available" and availability(settings)["FUNDING_PROPOSAL"] == "soon"
    someone, tester = User(uid="u1", email="someone@example.com", is_admin=False), User(uid="u2", email="Tester@example.com", is_admin=False)
    pilot = {**keys, "works_public": False}
    testing = Settings(works_enabled=["COURSEWORK"], tester_emails=["tester@example.com"], **pilot)
    assert availability(testing, someone)["COURSEWORK"] == "invite_only" and availability(testing, tester)["COURSEWORK"] == "available"
    # The pilot fails closed: an empty tester list opens the work services to no one but admins.
    empty = Settings(works_enabled=["COURSEWORK"], tester_emails=[], **pilot)
    assert availability(empty, someone)["COURSEWORK"] == "invite_only" and availability(empty, None)["COURSEWORK"] == "invite_only"
    assert availability(empty, User(uid="a", email="admin@example.com", is_admin=True))["COURSEWORK"] == "available"


def test_a_quote_freezes_roles_tier_price_table_and_content(works_client):
    from app.ai import costs
    from app.runtime import get_runtime

    client = works_client
    work = _coursework(client)
    quoted = client.post(f"/api/works/{work['id']}/steps", headers=STUDENT, json={"step": "PLAN"}).json()
    job = get_runtime().store.get(quoted["job"]["id"])
    engine = job.quote.engine
    assert engine.tier == "STANDARD" and engine.roles["WRITER"] == "google:gemini-3.8-flash" and engine.price_table == costs.table_in_force()
    assert engine.content["prompt:w-draft-v1"] and engine.content["rules:coursework-v1"] and engine.content["validators"] == "validators-v3"
    assert job.selection.work == "PLAN" and job.selection.work_band == "CW_PLAN" and job.work_id == work["id"]


def test_the_january_price_rise_never_changes_a_quoted_steps_projection():
    from app.ai import costs, orchestration
    from app.core.config import Settings
    from app.pricing.quote import work_usd

    # The direct Gemini API's dated tables, for works priced before the Gemini workflow (Vertex: test_vertex_pricing).
    settings = Settings(openai_api_key="k", anthropic_api_key="k", gemini_api_key="k", gemini_workflow=False)
    engine = orchestration.work_engine(settings, "COURSEWORK").model_copy(update={"price_table": "2026-09"})
    later = engine.model_copy(update={"price_table": "2027-01"})
    assert work_usd(settings, "DRAFT", "COURSEWORK", 2000, later) > work_usd(settings, "DRAFT", "COURSEWORK", 2000, engine)
    assert costs.price_for("google", "gemini-3.8-flash", table="2026-09") == (0.75, 3.75, 0.75)


def test_gemini_answers_blocks_and_errors_are_classified(monkeypatch):
    import httpx

    from app.ai.providers import GeminiProvider
    from app.core.config import Settings
    from app.core.errors import PermanentStageError, RetryableStageError

    calls = []

    def reply(status, body):
        def post(url, json=None, headers=None, timeout=None):  # noqa: A002 - httpx's own keyword
            calls.append((url, headers))
            return httpx.Response(status, json=body)

        return post

    provider = GeminiProvider(Settings(gemini_api_key="secret"))
    usage = {"promptTokenCount": 120, "candidatesTokenCount": 30, "thoughtsTokenCount": 50, "cachedContentTokenCount": 20}
    monkeypatch.setattr(httpx, "post", reply(200, {"candidates": [{"content": {"parts": [{"text": '{"a": 1}'}]}, "finishReason": "STOP"}], "usageMetadata": usage}))
    result = provider.json("w_draft", "gemini-3.8-flash", "system", {"x": 1}, {"type": "object"}, 1000)
    assert json.loads(result.text) == {"a": 1} and result.usage.output_tokens == 80 and result.usage.input_tokens == 100 and result.usage.cached_tokens == 20
    assert calls[0][1] == {"x-goog-api-key": "secret"} and "gemini-3.8-flash:generateContent" in calls[0][0]
    monkeypatch.setattr(httpx, "post", reply(200, {"candidates": [{"content": {"parts": []}, "finishReason": "SAFETY"}], "usageMetadata": usage}))
    assert provider.json("w_draft", "gemini-3.8-flash", "s", {}, {}, 10).stop == "refusal"
    monkeypatch.setattr(httpx, "post", reply(200, {"candidates": [{"content": {"parts": [{"text": "{"}]}, "finishReason": "MAX_TOKENS"}], "usageMetadata": usage}))
    assert provider.json("w_draft", "gemini-3.8-flash", "s", {}, {}, 10).stop == "max_tokens"
    monkeypatch.setattr(httpx, "post", reply(429, {}))
    with pytest.raises(RetryableStageError):
        provider.json("w_draft", "gemini-3.8-flash", "s", {}, {}, 10)
    monkeypatch.setattr(httpx, "post", reply(403, {}))  # an expired key or an empty prepaid balance: fails, credits back
    with pytest.raises(PermanentStageError):
        provider.json("w_draft", "gemini-3.8-flash", "s", {}, {}, 10)


def test_changing_the_writer_is_a_settings_change_for_new_quotes_only(works_client, monkeypatch):
    from app.core.config import get_settings
    from app.runtime import get_runtime

    client = works_client
    work = _coursework(client)
    first = client.post(f"/api/works/{work['id']}/steps", headers=STUDENT, json={"step": "PLAN"}).json()
    get_settings().role_models["WRITER"] = "anthropic:claude-sonnet-5-5"
    get_runtime().settings.role_models["WRITER"] = "anthropic:claude-sonnet-5-5"
    second = client.post(f"/api/works/{work['id']}/steps", headers=STUDENT, json={"step": "PLAN"}).json()
    rt = get_runtime()
    assert rt.store.get(first["job"]["id"]).quote.engine.roles["WRITER"] == "google:gemini-3.8-flash"
    assert rt.store.get(second["job"]["id"]).quote.engine.roles["WRITER"] == "anthropic:claude-sonnet-5-5"
    client.post(f"/api/works/{work['id']}/steps/{second['job']['id']}/submit", headers=STUDENT, json={"quoteId": second["quote"]["id"]})
    assert wait(client, second["job"]["id"], timeout=120)["status"] == "COMPLETED"


def test_a_failed_plans_research_is_reused_only_for_the_same_question(works_client):
    """Codex review 2026-10-07, finding 5: a PLAN has no plan to compare, so a retry after the question
    changed reused the old topic's sources."""
    from app.core.errors import PermanentStageError

    client = works_client
    work = _coursework(client)

    def refused(payload):
        raise PermanentStageError("MODEL_REFUSED", "Refused.", "test: plan refused after research")

    client.models.overrides["w_plan"] = refused
    _, failed = _run(client, work["id"], "PLAN")
    assert failed["status"] == "FAILED"
    researched = client.models.tasks.count("w_needs")
    _, again = _run(client, work["id"], "PLAN")  # the same question: its checked sources are reused
    assert again["status"] == "FAILED" and client.models.tasks.count("w_needs") == researched

    work = _work(client, work["id"])
    changed = client.post(f"/api/works/{work['id']}/details", headers=STUDENT, json={
        "inputs": {**work["inputs"], "description": "Discuss how school feeding programmes affect pupils' attendance in rural primary schools."},
        "baseVersion": work["specVersion"]})
    assert changed.status_code == 200, changed.json()
    work = changed.json()
    if work["specStatus"] != "CONFIRMED":
        work = client.post(f"/api/works/{work['id']}/answers", headers=STUDENT, json={"answers": {}, "skipRest": True, "baseVersion": work["specVersion"]}).json()
        work = client.post(f"/api/works/{work['id']}/spec/confirm", headers=STUDENT, json={"baseVersion": work["specVersion"]}).json()
    del client.models.overrides["w_plan"]
    _, planned = _run(client, work["id"], "PLAN")
    assert planned["status"] == "COMPLETED", planned.get("failure")
    assert client.models.tasks.count("w_needs") > researched  # a new question is researched again
