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


# --- Workflow 2: the final editor reviews, corrects and decides --------------------------------------------------------


def _draft(client, edit=None, resolve=None, flag=None):
    """A coursework drafted on workflow 2: (work, the draft's job, the stored document)."""
    from app.runtime import get_runtime
    from app.works import service
    from tests.test_works import _coursework, _run, _work

    work = _coursework(client)
    _, planned = _run(client, work["id"], "PLAN")
    assert planned["status"] == "COMPLETED", planned.get("failure")
    work = _work(client, work["id"])
    work = client.post(f"/api/works/{work['id']}/plan/approve", headers=STUDENT, json={"baseVersion": work["planVersion"]}).json()
    for task, answer in (("w_edit", edit), ("w_resolve", resolve), ("w_flag", flag)):
        if answer is not None:
            client.models.overrides[task] = answer
    _, job = _run(client, work["id"], "DRAFT")
    rt = get_runtime()
    return work, job, service._doc(rt, rt.store.get_work(work["id"]))


def _verdicts(payload, **more):
    from tests import fake_works

    return {**fake_works.answer("w_edit", payload), **more}


def _correct(payload, text, kind="WORDING", action="REPLACE", paragraph=None, section=None):
    target = payload["editable"][0]
    return {"section": section or target["key"], "paragraph": paragraph or target["paragraphs"][0]["id"], "action": action, "text": text, "kind": kind, "reason": "Test."}


def test_a_sound_draft_is_reviewed_once_by_the_final_editor_and_by_nothing_else(v2):
    _, job, document = _draft(v2)
    assert job["status"] == "COMPLETED", job.get("failure")
    tasks = v2.models.tasks
    assert tasks.count("w_edit") == 1 and not {"w_final", "w_repair", "w_flag", "w_resolve", "w_plan_review"} & set(tasks)
    approval = document.approval
    assert approval.reviewer == "vertex:gemini-3.1-pro-preview" and approval.corrections == 0 and not approval.resolved
    assert approval.reviewed_sha256 == approval.accepted_sha256  # nothing changed between what it read and what was delivered


def test_the_editor_is_given_the_text_it_may_correct_with_ids_tokens_evidence_and_every_rule(v2):
    seen = {}

    def edit(payload):
        seen.update(payload)
        return _verdicts(payload)

    _, job, _ = _draft(v2, edit=edit)
    assert job["status"] == "COMPLETED", job.get("failure")
    section = seen["editable"][0]
    assert section["paragraphs"][0]["id"] == "p1" and section["wordsNow"] > 0 and "words" in section
    assert all(e["token"].startswith("\u27e6E") and e["sourceWords"] for e in seen["evidence"]) and seen["evidence"]
    assert any(r.get("sections") for r in seen["rules"]) and any("sections" not in r for r in seen["rules"])  # section rules and document rules
    assert {"document", "coverage", "numberTokens", "findings", "length"} <= seen.keys()


def test_a_wording_correction_is_applied_by_paragraph_and_needs_no_second_look(v2):
    marker = "This sentence was sharpened by the final editor."

    def edit(payload):
        first = payload["editable"][0]["paragraphs"][0]
        return _verdicts(payload, corrections=[_correct(payload, first["text"] + " " + marker)])

    work, job, document = _draft(v2, edit=edit)
    assert job["status"] == "COMPLETED", job.get("failure")
    assert marker in document.sections[0].paragraphs[0] and sum(marker in p for s in document.sections for p in s.paragraphs) == 1
    assert "w_flag" not in v2.models.tasks and "w_resolve" not in v2.models.tasks
    assert document.approval.corrections == 1 and document.approval.substantive == 0
    assert document.approval.reviewed_sha256 != document.approval.accepted_sha256
    shown = v2.get(f"/api/works/{work['id']}/document", headers=STUDENT).json()
    assert "approval" not in shown and marker in " ".join(p for sec in shown["sections"] for p in sec["paragraphs"])  # the student sees the text, never the record


def test_a_corrected_claim_is_checked_and_a_supported_one_stands(v2):
    checked = []

    def edit(payload):
        first = payload["editable"][0]["paragraphs"][0]
        return _verdicts(payload, corrections=[_correct(payload, first["text"] + " The association is modest.", kind="CLAIM")])

    def flag(payload):
        checked.extend(payload["corrections"])
        return {"results": [{"id": c["id"], "supported": True, "problem": ""} for c in payload["corrections"]]}

    _, job, document = _draft(v2, edit=edit, flag=flag)
    assert job["status"] == "COMPLETED", job.get("failure")
    assert len(checked) == 1 and checked[0]["before"] and checked[0]["after"].endswith("The association is modest.")
    assert "w_resolve" not in v2.models.tasks and document.approval.substantive == 1 and document.approval.flagged == 0


def test_a_flagged_claim_goes_back_to_the_editor_once_and_the_check_never_rewrites(v2):
    asked = {}

    def edit(payload):
        first = payload["editable"][0]["paragraphs"][0]
        return _verdicts(payload, corrections=[_correct(payload, first["text"] + " Distance causes low uptake everywhere.", kind="CLAIM")])

    def resolve(payload):
        asked.update(payload)
        flagged = payload["flagged"][0]
        target = next(p for e in payload["editable"] for p in e["paragraphs"] if p["id"] == flagged["paragraph"])
        return _verdicts(payload, corrections=[_correct(payload, target["text"].replace(" Distance causes low uptake everywhere.", " Distance is associated with lower uptake."),
                                                        kind="CLAIM", paragraph=flagged["paragraph"])])

    _, job, document = _draft(v2, edit=edit, resolve=resolve,
                              flag=lambda payload: {"results": [{"id": c["id"], "supported": False, "problem": "The source shows an association in one district."} for c in payload["corrections"]]})
    assert job["status"] == "COMPLETED", job.get("failure")
    text = " ".join(p for s in document.sections for p in s.paragraphs)
    assert "is associated with lower uptake" in text and "causes low uptake everywhere" not in text
    assert v2.models.tasks.count("w_resolve") == 1 and v2.models.tasks.count("w_flag") == 1  # one resolution, and it is not checked again
    assert asked["flagged"][0]["problem"].startswith("The source shows") and "findings" not in asked
    assert document.approval.flagged == 1 and document.approval.resolved and "w_repair" not in v2.models.tasks


def test_wording_the_editor_cannot_trace_is_sent_back_and_never_released_if_it_stays(v2):
    untraceable = " A recent survey found that 87 percent of clinics lack supplies (Smith, 2020)."
    checks = {}

    def edit(payload):
        first = payload["editable"][0]["paragraphs"][0]
        return _verdicts(payload, corrections=[_correct(payload, first["text"] + untraceable)])

    def resolve(payload):
        checks.update({"checks": payload["checks"]})
        return _verdicts(payload)  # it leaves the sentence in

    _, job, document = _draft(v2, edit=edit, resolve=resolve)
    assert "cannot be traced" in str(checks["checks"])  # code found it and told the editor which paragraph
    assert job["status"] == "FAILED" and job["failure"]["code"] == "DOCUMENT_NOT_APPROVED" and document is None
    assert job["paymentStatus"] in ("REFUNDED", "NOT_REQUIRED")


def test_a_correction_that_names_its_section_by_heading_is_applied_to_that_section(v2):
    """Real-model trial 2026-10-09: on its second look the editor named sections by the headings it had been given,
    every such correction was refused, and three of six drafts stopped. Sections are now given by key, and a heading
    still names its section."""
    seen = {}

    def edit(payload):
        target = payload["editable"][0]
        seen["editable"], seen["length"] = target, payload["length"]
        return _verdicts(payload, corrections=[_correct(payload, "The essay first sets out the question and the argument it will make about maternal health.", section=f"  {target['heading'].upper()} ")])

    _, job, document = _draft(v2, edit=edit)
    assert job["status"] == "COMPLETED", job.get("failure")
    section = next(s for s in document.sections if s.key == seen["editable"]["key"])
    assert section.paragraphs[0] == "The essay first sets out the question and the argument it will make about maternal health."
    assert document.approval.refused == 0 and document.approval.corrections == 1
    assert seen["length"]["minimum"] == 1276 and seen["length"]["limit"] == 1500  # the editor is told how short is too short


def test_what_the_editor_is_sent_back_names_sections_by_key(v2):
    seen = {}

    def edit(payload):
        return _verdicts(payload, corrections=[_correct(payload, "Malaria kills 73% of children in the district, as Smith (2019) showed.", kind="CLAIM", action="INSERT_AFTER")])

    def resolve(payload):
        seen.update(payload)
        target = payload["editable"][0]
        return _verdicts(payload, corrections=[{"section": target["key"], "paragraph": "p2", "action": "DELETE", "text": "", "kind": "CLAIM", "reason": "Test."}])

    _, job, document = _draft(v2, edit=edit, resolve=resolve, flag=lambda p: {"results": [{"id": c["id"], "supported": False, "problem": "No source gives this."} for c in p["corrections"]]})
    assert job["status"] == "COMPLETED", job.get("failure")
    key = seen["editable"][0]["key"]
    assert [(f["section"], f["paragraph"]) for f in seen["flagged"]] == [(key, "p2")] and seen["flagged"][0]["heading"]
    assert [c["section"] for c in seen["checks"]] == [key] and "73%" not in " ".join(p for s in document.sections for p in s.paragraphs)


def test_a_draft_well_under_its_limit_is_developed_by_the_writer_before_the_editor_reads_it(v2):
    """Real-model trial 2026-10-09: drafts of 1,244 words for 1,500 went to the editor, which corrects and does not
    write, and stopped as well under their limit."""
    from tests import fake_works

    order = []

    def short_draft(payload):
        answer = fake_works.draft(payload)
        for s in answer["sections"]:
            words = " ".join(s["paragraphs"]).split()
            s["paragraphs"] = [" ".join(words[: int(len(words) * 0.7)]).rstrip(".,;") + "."]
        return answer

    def repair(payload):
        order.append("writer")
        out = []
        for s in payload["sections"]:
            assert any("well short" in i for i in s["issues"])
            out.append({"key": s["key"], "paragraphs": fake_works._text({"key": s["key"], "heading": s["heading"], "words": s["words"], "evidence": s["evidence"]}, []),
                        "table": {"caption": "", "rows": []}})
        return {"sections": out}

    v2.models.overrides["w_draft"] = short_draft
    v2.models.overrides["w_repair"] = repair
    _, job, document = _draft(v2, edit=lambda payload: order.append("editor") or _verdicts(payload))
    assert job["status"] == "COMPLETED", job.get("failure")
    assert order == ["writer", "editor"] and 1275 <= document.words <= 1500  # one development, then the one review


def test_a_correction_that_names_an_unknown_place_is_refused_never_guessed_at():
    from app.proposals.ai import Correction, SectionText, Table
    from app.proposals.pipeline import apply_corrections as _apply_corrections

    def section(key, *paragraphs):
        return SectionText(key=key, paragraphs=list(paragraphs), table=Table(caption="T", rows=[["a"]]))

    current = {"intro": section("intro", "One.", "Two.", "Three."), "body": section("body", "Kept.")}

    def c(section_key, paragraph, action, text="", kind="WORDING"):
        return Correction(section=section_key, paragraph=paragraph, action=action, text=text, kind=kind)

    applied, refused = _apply_corrections(current, [
        c("intro", "p2", "REPLACE", "Two,  rewritten."), c("intro", "p2", "REPLACE", "Again."), c("intro", "p1", "INSERT_AFTER", "New."),
        c("intro", "p3", "DELETE"), c("intro", "p9", "REPLACE", "Nowhere."), c("body", "p1", "REPLACE", "Not allowed."),
        c("intro", "p1", "REMOVE_TABLE"), c("intro", "p1", "REPLACE", ""),
    ], ["intro"])
    assert current["intro"].paragraphs == ["One.", "New.", "Two, rewritten."] and current["intro"].table.rows == []
    assert current["body"].paragraphs == ["Kept."] and current["body"].table.rows == [["a"]]  # a section this step may not change
    assert [(a["action"], a["paragraph"]) for a in applied] == [("REPLACE", "p3"), ("INSERT_AFTER", "p2"), ("DELETE", ""), ("REMOVE_TABLE", "p1")]
    assert len(refused["intro"]) == 3 and len(refused[""]) == 1  # corrected twice, no such paragraph, no text; and the other section


def test_a_blocker_the_editor_cannot_settle_stops_the_draft_without_any_repair_round(v2):
    def edit(payload):
        answer = _verdicts(payload)
        answer["coverage"] = [{**c, "answered": False, "where": ""} for c in answer["coverage"]]
        answer["blockers"] = [{"where": "", "issue": "The question asks for a comparison the evidence cannot support."}]
        return answer

    _, job, document = _draft(v2, edit=edit)
    assert job["status"] == "FAILED" and job["failure"]["code"] == "DOCUMENT_NOT_READY" and document is None
    assert v2.models.tasks.count("w_edit") == 1 and "w_repair" not in v2.models.tasks and "w_final" not in v2.models.tasks


def test_when_the_final_editor_cannot_answer_the_draft_waits_and_nothing_else_approves(v2, monkeypatch):
    from app.core.errors import RetryableStageError
    from app.runtime import get_runtime

    get_runtime().settings.review_wait_sec = 1
    calls = {"n": 0}

    def edit(payload):
        calls["n"] += 1
        if calls["n"] <= 2:
            raise RetryableStageError("PROVIDER_UNAVAILABLE", "Unavailable.", "test: the premium model is down")
        return _verdicts(payload)

    _, job, document = _draft(v2, edit=edit)
    assert job["status"] == "COMPLETED", job.get("failure")
    stored = get_runtime().store.get(job["id"])
    assert calls["n"] == 3 and stored.capacity_waits == 2 and stored.attempts == 0  # two waits, no retry of the stage used up
    assert [t.code for t in stored.timings if t.outcome == "WAITING"] == ["REVIEW", "REVIEW"]
    assert v2.models.tasks.count("w_draft") == 1 and "w_final" not in v2.models.tasks  # the draft was kept; no stand-in approved
    assert document.approval.reviewer == "vertex:gemini-3.1-pro-preview"


def test_a_coursework_plan_is_decided_by_code_and_says_so(v2):
    from app.runtime import get_runtime
    from tests.test_works import _coursework, _run

    work = _coursework(v2)
    _, job = _run(v2, work["id"], "PLAN")
    assert job["status"] == "COMPLETED", job.get("failure")
    assert "w_plan_review" not in v2.models.tasks and v2.models.tasks.count("w_plan") == 1
    review = get_runtime().store.get_work(work["id"]).plan_review
    assert (review.outcome, review.reason) == ("APPROVED", "CODE_CHECKS")  # not recorded as a reviewer's approval


def test_the_final_review_s_share_of_the_cap_is_kept_from_every_other_step(monkeypatch):
    from app.ai.orchestration import EDITOR_TASKS

    runner, _, _ = _gated(monkeypatch, budget=4.0)
    monkeypatch.setattr(AIRunner, "worst_cost", lambda self, task, chars: 0.6)
    runner.keep_for_editor(12_000)
    assert runner._held == pytest.approx(1.8) and runner._held_for == EDITOR_TASKS
    assert runner._cap("w_edit") == 4.0 and runner._cap("w_search") == pytest.approx(2.2)
    monkeypatch.setattr(AIRunner, "worst_cost", lambda self, task, chars: 5.0)
    runner.keep_for_editor(12_000)
    assert runner._held == 2.0  # never more than half the cap


def test_workflow_1_drafts_are_reviewed_as_they_were_priced(tmp_path, monkeypatch):
    from tests.conftest import _client

    monkeypatch.setenv("WORKS_ENABLED", '["CONCEPT_NOTE","COURSEWORK","FUNDING_PROPOSAL"]')
    for client in _client(tmp_path, monkeypatch, "cost"):
        _, job, document = _draft(client)
        assert job["status"] == "COMPLETED", job.get("failure")
        assert "w_final" in client.models.tasks and "w_plan_review" in client.models.tasks and "w_edit" not in client.models.tasks
        assert document.approval is None


def test_asking_for_changes_is_approved_by_the_final_editor_too(v2):
    from app.runtime import get_runtime
    from app.works import service
    from tests.test_works import _run, _work

    work, job, document = _draft(v2)
    assert job["status"] == "COMPLETED", job.get("failure")
    work = _work(v2, work["id"])
    key = document.sections[0].key
    asked = v2.post(f"/api/works/{work['id']}/requests", headers=STUDENT, json={"instruction": "Say more about rural clinics.", "sections": [key]})
    assert asked.status_code == 200, asked.json()
    before = v2.models.tasks.count("w_edit")
    seen = {}
    v2.models.overrides["w_edit"] = lambda payload: seen.update(payload) or _verdicts(payload)
    _, revised = _run(v2, work["id"], "REVISE")
    assert revised["status"] == "COMPLETED", revised.get("failure")
    assert v2.models.tasks.count("w_edit") == before + 1 and "w_final" not in v2.models.tasks
    assert [e["key"] for e in seen["editable"]] == [key]  # only the section the student asked about may be corrected
    rt = get_runtime()
    latest = service._doc(rt, rt.store.get_work(work["id"]))
    assert latest.approval is not None and latest.revised == [key]


def test_the_built_word_file_is_read_back_before_a_draft_can_complete(v2, monkeypatch):
    from app.works import export

    _, job, document = _draft(v2)
    assert job["status"] == "COMPLETED", job.get("failure")  # the real file carries every heading and paragraph
    real = export.build

    def without_a_paragraph(*args, **kwargs):
        import io

        from docx import Document

        built = Document(io.BytesIO(real(*args, **kwargs)))
        body = [p for p in built.paragraphs if len(p.text.split()) > 8][0]
        body._element.getparent().remove(body._element)
        out = io.BytesIO()
        built.save(out)
        return out.getvalue()

    monkeypatch.setattr(export, "build", without_a_paragraph)
    _, job, document = _draft(v2)
    assert job["status"] == "FAILED" and job["failure"]["code"] == "EXPORT_FAILED" and document is None


# --- Workflow 2: proposal chapters -------------------------------------------------------------------------------------


def _chapter_one(client, **answers):
    """A proposal planned and approved, so Chapter One is written: (project id, the chapter's job, the stored chapter)."""
    from app.proposals import service
    from app.runtime import get_runtime
    from tests.test_api import wait
    from tests.test_proposals import _create, _run

    pid = _create(client)["id"]
    planned = _run(client, pid, "PLAN")
    assert planned["status"] == "COMPLETED", planned.get("failure")
    client.models.overrides.update(answers)
    project = client.get(f"/api/projects/{pid}", headers=STUDENT).json()
    saved = client.post(f"/api/projects/{pid}/plan", headers=STUDENT, json={"plan": project["plan"], "baseVersion": project["planVersion"]}).json()
    acknowledge = ["SAMPLING"] if saved["plan"].get("samplingAssumed") else []
    approved = client.post(f"/api/projects/{pid}/plan/approve", headers=STUDENT, json={"baseVersion": saved["planVersion"], "acknowledge": acknowledge})
    assert approved.status_code == 200, approved.json()
    job = wait(client, approved.json()["activeJob"])
    rt = get_runtime()
    return pid, job, service._chapter_doc(rt, rt.store.get_project(pid).chapter(1))


def _passes(payload, corrections=None):
    """Every section passed, with `corrections` ({section key: [correction]})."""
    return {"results": [{"key": s["key"], "grade": "PASS", "issues": [], "note": "", "corrections": (corrections or {}).get(s["key"], [])} for s in payload["sections"]]}


def _change(section, text, kind="WORDING", action="REPLACE", paragraph=0):
    return {"paragraph": section["paragraphs"][paragraph]["id"], "action": action, "text": text, "kind": kind, "reason": "Test."}


def _section(payload, key):
    return next((s for s in payload["sections"] if s["key"] == key), None)


def test_a_sound_chapter_is_reviewed_once_by_the_final_editor_and_by_no_other(v2):
    _, job, chapter = _chapter_one(v2)
    assert job["status"] == "COMPLETED", job.get("failure")
    tasks = v2.models.tasks
    assert "p_edit" in tasks and not {"p_review", "p_review_peer", "p_fix", "p_flag", "p_resolve"} & set(tasks)
    approval = chapter.approval
    assert approval.reviewer == "vertex:gemini-3.1-pro-preview" and approval.corrections == 0 and not approval.resolved
    assert approval.reviewed_sha256 == approval.accepted_sha256 and all(s.reviewed for s in chapter.sections)
    shown = v2.get(f"/api/projects/{_}/chapters/1", headers=STUDENT).json()
    assert "approval" not in shown  # the record is for admins and audits, never the student's page


def test_a_chapter_correction_is_applied_by_paragraph_and_the_plan_s_statements_stay_word_for_word(v2):
    from app.proposals.models import ProposalPlan
    from app.proposals.pipeline import plan_statements

    def edit(payload):
        corrections = {}
        if (background := _section(payload, "background")):
            corrections["background"] = [_change(background, "The study will follow the plan the student approved.", paragraph=1)]
        if (objectives := _section(payload, "objectives")):
            corrections["objectives"] = [_change(objectives, "To do something else entirely.", kind="CLAIM", paragraph=len(objectives["paragraphs"]) - 1)]
        return _passes(payload, corrections)

    pid, job, chapter = _chapter_one(v2, p_edit=edit)
    assert job["status"] == "COMPLETED", job.get("failure")
    sections = {s.key: s for s in chapter.sections}
    assert sections["background"].paragraphs[1] == "The study will follow the plan the student approved."
    plan = ProposalPlan.model_validate(v2.get(f"/api/projects/{pid}", headers=STUDENT).json()["plan"])
    statements = plan_statements(plan, "objectives", sections["objectives"].number)
    assert sections["objectives"].paragraphs[-len(statements):] == statements  # put back by code, whatever the editor changed
    assert "p_flag" not in v2.models.tasks and "p_resolve" not in v2.models.tasks  # an undone correction is not in the text: nothing to check
    assert chapter.approval.corrections == 1 and chapter.approval.reviewed_sha256 != chapter.approval.accepted_sha256


def test_a_flagged_chapter_claim_goes_back_to_the_editor_once_for_that_section_only(v2):
    seen = {}

    def edit(payload):
        background = _section(payload, "background")
        if background is None:
            return _passes(payload)
        token = f"⟦{background['evidence'][0]['id']}⟧"
        return _passes(payload, {"background": [_change(background, f"Distance causes lower uptake among every caregiver in the country. {token}", kind="CLAIM")]})

    def flag(payload):
        seen["flag"] = payload
        return {"results": [{"id": c["id"], "supported": False, "problem": "The source shows an association among rural caregivers, not a cause for all."} for c in payload["corrections"]]}

    def resolve(payload):
        seen["resolve"] = payload
        background = _section(payload, "background")
        token = f"⟦{background['evidence'][0]['id']}⟧"
        return _passes(payload, {"background": [_change(background, f"Distance was associated with lower uptake among rural caregivers. {token}", kind="CLAIM")]})

    _, job, chapter = _chapter_one(v2, p_edit=edit, p_flag=flag, p_resolve=resolve)
    assert job["status"] == "COMPLETED", job.get("failure")
    tasks = v2.models.tasks
    assert tasks.count("p_flag") == 1 and tasks.count("p_resolve") == 1 and "p_fix" not in tasks and "p_review" not in tasks
    correction = seen["flag"]["corrections"][0]
    assert correction["after"].startswith("Distance causes") and correction["evidence"][0]["sourceWords"]  # checked against the source's own words
    assert [s["key"] for s in seen["resolve"]["sections"]] == ["background"]
    assert seen["resolve"]["sections"][0]["flagged"] == [{"paragraph": "p1", "problem": "The source shows an association among rural caregivers, not a cause for all."}]
    background = next(s for s in chapter.sections if s.key == "background")
    assert background.paragraphs[0].startswith("Distance was associated with lower uptake among rural caregivers.")
    approval = chapter.approval
    assert (approval.flagged, approval.resolved, approval.substantive) == (1, True, 2)


def test_chapter_wording_code_cannot_trace_after_the_editor_s_last_look_is_never_released(v2):
    def edit(payload):
        background = _section(payload, "background")
        if background is None:
            return _passes(payload)
        return _passes(payload, {"background": [_change(background, "Malaria kills 73% of children in the district, as Smith (2019) showed.", kind="CLAIM", action="INSERT_AFTER")]})

    seen = {}

    def resolve(payload):
        seen.update(payload)
        return _passes(payload)  # the editor leaves it

    pid, job, chapter = _chapter_one(v2, p_edit=edit, p_resolve=resolve)
    assert job["status"] == "FAILED" and job["failure"]["code"] == "DOCUMENT_NOT_APPROVED" and job["billing"]["charged"] == 0
    assert chapter is None and "p_fix" not in v2.models.tasks
    checks = seen["sections"][0]["paperaidChecks"]
    assert [s["key"] for s in seen["sections"]] == ["background"] and any(c.startswith("Paragraph p2 carries") for c in checks)


def test_a_section_the_editor_does_not_pass_is_not_delivered(v2):
    def edit(payload):
        answer = _passes(payload)
        for result in answer["results"]:
            if result["key"] == "problem":
                result.update(grade="REPAIR", issues=["The size of the problem in the study area is not given, and only the student can give it."])
        return answer

    _, job, chapter = _chapter_one(v2, p_edit=edit)
    assert job["status"] == "FAILED" and job["failure"]["code"] == "DOCUMENT_NOT_APPROVED" and chapter is None
    assert v2.models.tasks.count("p_resolve") == 0 and "p_fix" not in v2.models.tasks  # nothing flagged or found: no second look, no writer


def test_when_the_final_editor_cannot_answer_a_chapter_waits_with_its_draft_kept(v2):
    from app.core.errors import RetryableStageError
    from app.runtime import get_runtime

    get_runtime().settings.review_wait_sec = 1
    calls = {"n": 0}

    def edit(payload):
        calls["n"] += 1
        if calls["n"] <= 2:
            raise RetryableStageError("VERTEX_MODEL_UNAVAILABLE", "Unavailable.", "test: the premium model is down")
        return _passes(payload)

    _, job, chapter = _chapter_one(v2, p_edit=edit)
    assert job["status"] == "COMPLETED", job.get("failure")
    stored = get_runtime().store.get(job["id"])
    assert stored.capacity_waits == 2 and stored.attempts == 0 and [t.code for t in stored.timings if t.outcome == "WAITING"] == ["REVIEW", "REVIEW"]
    assert [t.outcome for t in stored.timings if t.stage == "DRAFTING"] == ["DONE"]  # written once: the waits kept the draft
    assert "p_review" not in v2.models.tasks and chapter.approval is not None


def test_a_chapter_revision_is_approved_by_the_final_editor_and_its_rewrite_is_paid_for_once(v2):
    from app.core.errors import RetryableStageError
    from app.proposals import service
    from app.runtime import get_runtime
    from tests.test_api import wait

    pid, job, _ = _chapter_one(v2)
    assert job["status"] == "COMPLETED", job.get("failure")
    added = v2.post(f"/api/projects/{pid}/chapters/1/request", headers=STUDENT, json={"instruction": "Show the size of the problem.", "sections": ["problem"]})
    assert added.status_code == 200, added.json()
    get_runtime().settings.review_wait_sec = 1
    calls = {"n": 0}
    seen = {}

    def edit(payload):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RetryableStageError("PROVIDER_UNAVAILABLE", "Unavailable.", "test: the premium model is down")
        seen.update(payload)
        return _passes(payload)

    v2.models.overrides["p_edit"] = edit
    quoted = v2.post(f"/api/projects/{pid}/steps", headers=STUDENT, json={"step": "REVISE_1", "comments": [added.json()["feedback"][0]["id"]]}).json()
    v2.post(f"/api/projects/{pid}/steps/{quoted['job']['id']}/submit", headers=STUDENT, json={"quoteId": quoted["quote"]["id"]})
    revised = wait(v2, quoted["job"]["id"])
    assert revised["status"] == "COMPLETED", revised.get("failure")
    assert v2.models.tasks.count("p_fix") == 1 and "p_review" not in v2.models.tasks  # the rewrite was kept through the wait
    assert [s["key"] for s in seen["sections"]] == ["problem"]
    rt = get_runtime()
    latest = service._chapter_doc(rt, rt.store.get_project(pid).chapter(1))
    assert latest.revised == ["problem"] and latest.approval is not None
    assert any("supervisor's comment" in p for s in latest.sections if s.key == "problem" for p in s.paragraphs)


def test_a_proposal_s_scholarly_topic_is_read_from_the_index_and_not_searched_on_the_web(v2):
    from app.runtime import get_runtime
    from tests.test_proposals import _create, _run

    v2.models.overrides["p_needs"] = lambda payload: {"needs": [_need(1, "STUDY"), _need(2, "STATISTIC")]}
    job = _run(v2, _create(v2)["id"], "PLAN")
    assert job["status"] == "COMPLETED", job.get("failure")
    topics = get_runtime().store.get(job["id"]).topics
    assert [(t.category, t.index, t.web) for t in topics] == [("STUDY", "FOUND", "NOT_USED"), ("STATISTIC", "NOT_TRIED", "FOUND")]
    assert (v2.models.tasks.count("p_extract"), v2.models.tasks.count("p_search")) == (1, 1)


def test_workflow_1_chapters_are_reviewed_as_they_were_priced(client):
    _, job, chapter = _chapter_one(client)
    assert job["status"] == "COMPLETED", job.get("failure")
    assert "p_review" in client.models.tasks and "p_edit" not in client.models.tasks and chapter.approval is None


def test_a_chapter_s_final_review_keeps_its_share_of_the_cap(v2, monkeypatch):
    held = []
    keep = orchestration.AIRunner.keep_for_editor
    monkeypatch.setattr(orchestration.AIRunner, "keep_for_editor", lambda self, chars, service="w": (held.append((service, chars)), keep(self, chars, service))[1])
    _, job, _ = _chapter_one(v2)
    assert job["status"] == "COMPLETED", job.get("failure")
    assert held and {service for service, _ in held} == {"p"} and all(chars > 0 for _, chars in held)  # every stage of the chapter, never the plan

