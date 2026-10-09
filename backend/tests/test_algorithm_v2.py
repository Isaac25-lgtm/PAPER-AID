"""The algorithm revision of 2026-10-09 (owner, with Codex's plan): each change with the case that shows it.
Synthetic inputs and stand-in models only; nothing here makes a paid call."""

import threading
import time

import pytest

from app.ai import orchestration
from app.ai.orchestration import AIRunner
from app.core.errors import PermanentStageError
from tests.test_ai import ScriptedProvider, real_settings
from tests.test_api import STUDENT

PASSAGE = [{"id": "b1", "text": "A short paragraph of about twenty words that needs a quick look from the lead model before pricing.", "signals": []}]

# --- A call waits for the budget before it takes a slot of the shared limit ------------------------------------------


class _Priced(ScriptedProvider):
    name = "openai"


def _gated(monkeypatch, heartbeat=None, budget=5.0):
    scripted = _Priced({"analyse": [{"blocks": []}, {"blocks": []}]})
    monkeypatch.setattr(orchestration, "provider_for", lambda ref, settings: (scripted, "gpt-6-sol"))
    events: list[str] = []

    def gate(model, searching):
        events.append("taken")
        return (lambda: events.append("released")), 0

    runner = AIRunner(real_settings(), lambda c: None, lambda: 0.0, budget, heartbeat=heartbeat, gate=gate)
    return runner, scripted, events


def test_a_call_waiting_for_the_budget_holds_no_slot(monkeypatch):
    runner, scripted, events = _gated(monkeypatch)
    runner._inflight = 4.99  # a call alongside holds nearly the whole cap at its estimate; nothing is really spent
    def call():
        try:
            runner.analyse(PASSAGE, [], {})
        except PermanentStageError:
            pass  # the second assessor has no price in this stand-in: only the first call matters here

    thread = threading.Thread(target=call)
    thread.start()
    time.sleep(0.3)
    assert events == [] and scripted.calls == []  # it waits for the other call to be recorded, with no slot taken
    with runner._inflight_lock:  # the other call is recorded at its real cost
        runner._inflight = 0.0
        runner._inflight_lock.notify_all()
    thread.join(timeout=10)
    assert events[:2] == ["taken", "released"] and scripted.calls[:1] == ["analyse"]


def test_a_job_stopped_during_the_budget_wait_sends_nothing_and_frees_its_slot(monkeypatch):
    stopped = {"now": False}

    def heartbeat():
        if stopped["now"]:
            raise PermanentStageError("JOB_STOPPED", "Stopped.", "test: stopped while waiting")

    runner, scripted, events = _gated(monkeypatch, heartbeat=heartbeat)
    runner._inflight = 4.99
    failure: list[BaseException] = []

    def call():
        try:
            runner.analyse(PASSAGE, [], {})
        except PermanentStageError as exc:
            failure.append(exc)

    thread = threading.Thread(target=call)
    thread.start()
    time.sleep(0.3)
    stopped["now"] = True
    with runner._inflight_lock:
        runner._inflight = 0.0
        runner._inflight_lock.notify_all()
    thread.join(timeout=10)
    assert failure and failure[0].code == "JOB_STOPPED"
    assert scripted.calls == [] and events == ["taken", "released"]  # checked again after the wait: nothing was sent


def test_part_of_the_cap_can_be_kept_for_the_final_review(monkeypatch):
    runner, scripted, _ = _gated(monkeypatch, budget=4.0)
    runner.hold_back(3.9995, frozenset({"review"}))
    assert runner._cap("review") == 4.0 and runner._cap("analyse") == pytest.approx(0.0005)
    with pytest.raises(PermanentStageError) as err:  # another step may not spend what is kept for the review
        runner.analyse(PASSAGE, [], {})
    assert err.value.code == "BUDGET_EXCEEDED" and scripted.calls == []


# --- Workflow 2: frozen into the engine; topic planning has its own stage ---------------------------------------------


def test_the_workflow_is_frozen_into_each_engine(monkeypatch):
    from app.ai.orchestration import current_engine
    from app.core.config import Settings

    monkeypatch.setenv("VERTEX_PROJECT", "paperaid")
    old = current_engine(Settings())
    assert old.workflow == 1 and old.prompts["w_needs"] == "w-needs-v1" and old.vertex_stages["w_needs"] == "planner"
    monkeypatch.setenv("WORKFLOW", "2")
    new = current_engine(Settings())
    assert new.workflow == 2 and new.prompts["w_needs"] == "w-needs-v2" and new.prompts["p_needs"] == "p-needs-v2"
    assert new.vertex_stages["w_needs"] == "topics" and new.vertex_thinking["topics"] == "MEDIUM"
    assert new.vertex_thinking["planner"] == "HIGH"  # plans keep their own level


# --- The index: a key, a pool of candidates, and what a search came to -------------------------------------------------


@pytest.mark.parametrize("response, outcome", [
    (None, "UNAVAILABLE"),
    ((429, b"", "", {"x-ratelimit-remaining-usd": "0"}), "ALLOWANCE_USED"),
    ((429, b"", "", {"x-ratelimit-remaining-usd": "0.4"}), "RATE_LIMITED"),
    ((403, b"", "", {}), "ACCESS_DENIED"),
    ((503, b"", "", {}), "UNAVAILABLE"),
    ((200, b"not json", "application/json", {}), "INVALID"),
    ((200, b'{"results": []}', "application/json", {}), "NO_RESULTS"),
])
def test_an_index_search_says_what_it_came_to(monkeypatch, response, outcome):
    from app.analysis import fetch

    monkeypatch.setattr(fetch, "_request", lambda url, redirects=3: response)
    assert fetch.openalex_find("malaria vaccine uptake", 2015, 50) == (outcome, [])


def test_the_index_key_goes_only_to_the_index_and_no_redirect_is_followed(monkeypatch):
    from app.analysis import fetch

    seen = []
    monkeypatch.setattr(fetch, "_request", lambda url, redirects=3: seen.append((url, redirects)) or (200, b'{"results": []}', "", {}))
    monkeypatch.setattr(fetch, "_openalex_key", "")
    fetch.set_openalex_key(" test-key ")
    fetch.openalex_find("malaria", 2015, 50)
    fetch.openalex_retracted("10.1000/x")
    assert all(url.startswith("https://api.openalex.org/") and url.endswith("api_key=test-key") and redirects == 0 for url, redirects in seen) and len(seen) == 2
    monkeypatch.setattr(fetch, "_fetch", lambda url: seen.append((url, None)) or (404, b"", ""))
    fetch.crossref_lookup("10.1000/x")
    assert "test-key" not in seen[-1][0]  # another service never sees it


def test_candidates_are_ranked_for_the_need_not_only_by_the_index():
    from app.analysis import research

    def work(n, title, abstract, **more):
        return {"doi": f"10.1/{n}", "title": title, "abstract": abstract, **more}

    works = [
        work(1, "Vaccine hesitancy in European adults", "A survey of hesitancy among adults in Europe."),
        work(2, "Malaria vaccine uptake among caregivers in Uganda", "Uptake of the malaria vaccine among caregivers in Mukono, Uganda."),
        work(3, "Malaria vaccine uptake among caregivers in Uganda", "A retracted copy.", retracted="yes"),
        {"doi": "10.1/2", "title": "Malaria vaccine uptake among caregivers in Uganda (repeat)", "abstract": "The same work again."},
        work(5, "Caregivers and vaccines", "Caregivers in Uganda and uptake of vaccines."),
    ]
    ranked = research.rank_works(works, "What determines malaria vaccine uptake among caregivers in Uganda?", "malaria vaccine uptake caregivers", 3)
    assert [w["doi"] for w in ranked] == ["10.1/2", "10.1/5", "10.1/1"]  # the local study first; the retracted work and the repeat left out


# --- Workflow 2: how each topic is answered ---------------------------------------------------------------------------


@pytest.fixture
def v2(tmp_path, monkeypatch):
    from tests.conftest import _client

    monkeypatch.setenv("WORKFLOW", "2")
    monkeypatch.setenv("WORKS_ENABLED", '["CONCEPT_NOTE","COURSEWORK","FUNDING_PROPOSAL"]')
    yield from _client(tmp_path, monkeypatch, "cost")


def _need(n, category, essential=False, covered=(), broader=""):
    return {"id": f"n{n}", "need": f"Evidence need number {n} about maternal health", "category": category, "essential": essential,
            "query": f"maternal health topic {n}", "broader": broader, "coveredBy": list(covered)}


def _plan(client, needs):
    from app.runtime import get_runtime
    from tests.test_works import _coursework, _run

    client.models.overrides["w_needs"] = lambda payload: {"needs": needs}
    work = _coursework(client)
    _, job = _run(client, work["id"], "PLAN")
    return work, job, get_runtime().store.get(job["id"])


def test_a_scholarly_topic_is_read_from_a_ranked_pool_and_never_searched_on_the_web_when_the_index_answers(v2):
    work, job, stored = _plan(v2, [_need(1, "STUDY"), _need(2, "METHOD")])
    assert job["status"] == "COMPLETED", job.get("failure")
    assert "w_search" not in v2.models.tasks and v2.models.tasks.count("w_extract") == 2
    assert [(t.category, t.index, t.web, t.verified) for t in stored.topics] == [("STUDY", "FOUND", "NOT_USED", 1), ("METHOD", "FOUND", "NOT_USED", 1)]


def test_the_index_is_asked_for_a_pool_and_the_reader_gets_only_the_best_few(v2, monkeypatch):
    from app.analysis import fetch
    from tests.fake_models import WORK

    asked = []

    def find(query, from_year, limit):
        asked.append(limit)
        return "FOUND", [{**WORK, "doi": f"10.1/{n}", "title": f"{WORK['title']} {n}"} for n in range(limit)]

    monkeypatch.setattr(fetch, "openalex_find", find)
    read = []
    real = v2.models.default
    v2.models.overrides["w_extract"] = lambda payload: read.append(len(payload["works"])) or real("w_extract", payload)
    _, job, stored = _plan(v2, [_need(1, "STUDY")])
    assert job["status"] == "COMPLETED" and asked == [50] and read == [8]
    assert (stored.topics[0].candidates, stored.topics[0].kept) == (50, 8)


def test_an_official_figure_goes_to_the_web_and_the_reason_is_recorded(v2):
    _, job, stored = _plan(v2, [_need(1, "STATISTIC"), _need(2, "POLICY")])
    assert job["status"] == "COMPLETED", job.get("failure")
    assert v2.models.tasks.count("w_search") == 2 and "w_extract" not in v2.models.tasks
    assert [(t.index, t.web, t.reason) for t in stored.topics] == [("NOT_TRIED", "FOUND", "OFFICIAL_SOURCE")] * 2


def test_an_optional_scholarly_topic_the_index_cannot_answer_is_not_sent_to_the_web(v2):
    v2.models.works = []  # the index has nothing
    _, job, stored = _plan(v2, [_need(1, "STUDY", broader="maternal health"), _need(2, "STATISTIC")])
    assert job["status"] == "COMPLETED", job.get("failure")
    assert v2.models.tasks.count("w_search") == 1  # only the official figure
    assert v2.models.searched[:2] == ["maternal health topic 1", "maternal health"]  # the broader query was tried once
    assert (stored.topics[0].index, stored.topics[0].web) == ("NO_RESULTS", "NOT_USED")


def test_an_essential_topic_the_index_cannot_answer_is_searched_on_the_web(v2):
    v2.models.works = []
    _, job, stored = _plan(v2, [_need(1, "STUDY", essential=True)])
    assert job["status"] == "COMPLETED", job.get("failure")
    assert (stored.topics[0].index, stored.topics[0].web, stored.topics[0].reason, stored.topics[0].essential) == ("NO_RESULTS", "FOUND", "INDEX_EMPTY", True)


def test_an_index_that_cannot_be_asked_is_not_mistaken_for_no_evidence(v2, monkeypatch):
    from app.analysis import fetch

    monkeypatch.setattr(fetch, "openalex_find", lambda query, from_year, limit: ("ALLOWANCE_USED", []))
    _, job, stored = _plan(v2, [_need(1, "STUDY")])  # optional, yet the web is tried: the index never answered
    assert job["status"] == "COMPLETED", job.get("failure")
    assert (stored.topics[0].index, stored.topics[0].web, stored.topics[0].reason) == ("ALLOWANCE_USED", "FOUND", "INDEX_FAILED")


def test_a_step_stops_without_charge_when_an_essential_topic_has_no_evidence(v2):
    v2.models.works = []
    v2.models.opened = []  # the web search opens nothing either
    _, job, stored = _plan(v2, [_need(1, "STUDY", essential=True), _need(2, "STUDY")])
    assert job["status"] == "FAILED" and job["failure"]["code"] == "EVIDENCE_MISSING"
    assert "Evidence need number 1" in job["failure"]["userMessage"] and "Nothing was charged" in job["failure"]["userMessage"]
    assert job["paymentStatus"] in ("REFUNDED", "NOT_REQUIRED")
    assert "w_plan" not in v2.models.tasks  # stopped in research, before anything was written


def test_saved_evidence_is_not_searched_for_again(v2):
    from tests.test_works import _run, _work

    work, job, _ = _plan(v2, [_need(1, "STUDY")])
    assert job["status"] == "COMPLETED", job.get("failure")
    work = _work(v2, work["id"])
    work = v2.post(f"/api/works/{work['id']}/plan/approve", headers=STUDENT, json={"baseVersion": work["planVersion"]}).json()
    library = []

    def needs(payload):
        library.extend(e["id"] for e in payload["library"])
        return {"needs": [_need(1, "STUDY", covered=library[:1]), _need(2, "STUDY", covered=["Enot0real"]), _need(3, "STATISTIC")]}

    v2.models.overrides["w_needs"] = needs
    before = (v2.models.tasks.count("w_extract"), v2.models.tasks.count("w_search"))
    from app.runtime import get_runtime

    _, drafted = _run(v2, work["id"], "DRAFT")
    assert drafted["status"] == "COMPLETED", drafted.get("failure")
    assert library and (v2.models.tasks.count("w_extract"), v2.models.tasks.count("w_search")) == (before[0] + 1, before[1] + 1)
    topics = get_runtime().store.get(drafted["id"]).topics
    assert [(t.category, t.covered) for t in topics] == [("STUDY", False), ("STATISTIC", False), ("STUDY", True)]  # an unknown id is not coverage
