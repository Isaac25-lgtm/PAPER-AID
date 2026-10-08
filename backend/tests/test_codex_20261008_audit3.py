"""Codex's audit through ea0599e (2026-10-08): fourteen findings, each with the case that showed it."""

import threading
import time

import pytest

from app.core.errors import CapacityWait, PermanentStageError
from app.proposals import profile, rulebook
from tests.fake_models import PLAN
from tests.test_api import STUDENT
from tests.test_profiles import _aligned, _answer
from tests.test_proposals import _create, _run

# --- 1: a reservation held by a call under way is not an exhausted budget ---------------------------------------------


def test_a_call_waits_for_the_calls_under_way_to_settle_before_it_says_the_budget_is_spent():
    from app.ai.orchestration import AIRunner

    runner = object.__new__(AIRunner)
    spent = {"usd": 0.0}
    runner._spent, runner._budget, runner._inflight, runner._inflight_lock = (lambda: spent["usd"]), 0.40, 0.25, threading.Condition()
    waited = {"done": False}

    def second_call():
        with runner._inflight_lock:
            runner._settled(0.25)  # 0.25 held + 0.25 does not fit in 0.40, but nothing is really spent yet
            waited["done"] = True

    thread = threading.Thread(target=second_call)
    thread.start()
    time.sleep(0.1)
    assert not waited["done"]  # it waits; it does not say the budget is exhausted
    with runner._inflight_lock:  # the first call is recorded at its real cost
        spent["usd"], runner._inflight = 0.01, 0.0
        runner._inflight_lock.notify_all()
    thread.join(timeout=5)
    assert waited["done"] and spent["usd"] + 0.25 <= runner._budget

    runner._inflight, spent["usd"] = 0.25, 0.30  # genuinely short of money: no waiting, the budget check decides
    with runner._inflight_lock:
        runner._settled(0.25)


def test_a_saved_research_topic_is_read_back_even_when_nothing_more_may_be_spent():
    from app.proposals.models import EvidenceItem, EvidenceSource
    from app.proposals.pipeline import checkpointed

    class Ctx:
        files: dict = {}

        def has(self, name):
            return name in self.files

        def get_json(self, name):
            return self.files[name]

        def put_json(self, name, value):
            self.files[name] = value

    class Runner:
        budget_reached = False

    class Need:
        need, query, kind = "Uptake", "malaria vaccine uptake", "WEB"

    item = EvidenceItem(id="E1", chapter=0, need="Uptake", statement="s", passage="p", source=EvidenceSource(url="https://x.org", title="t"), retrieved_on="2026-10-08")
    ctx, runner = Ctx(), Runner()
    checkpointed(ctx, runner, Need(), lambda: [item])
    runner.budget_reached = True
    assert [i.id for i in checkpointed(ctx, runner, Need(), lambda: [])] == ["E1"]


# --- 2, 3, 5: guide alignment --------------------------------------------------------------------------------------


def _chapter(to_align=(), missing=()):
    from app.proposals.models import ChapterDocument, ChapterSection

    return ChapterDocument(number=1, title="Introduction", plan_version=1, cited=[], words=10, to_align=list(to_align), missing=list(missing), full_price=9000, paid=4000,
                           sections=[ChapterSection(key="background", number="1.1", heading="Background to the Study", paragraphs=["Text."]),
                                     ChapterSection(key="problem", number="1.2", heading="Statement of the Problem", paragraphs=["Text."])])


def test_reading_a_guide_again_keeps_a_section_still_to_revise():
    from app.proposals.models import ProposalPlan
    from app.proposals.pipeline import align_document

    plan = ProposalPlan.model_validate(PLAN)
    aligned = align_document(_chapter(to_align=["background"]), rulebook.DEFAULT, rulebook.DEFAULT, "MASTERS", plan)  # the same briefs on both sides
    assert "background" in aligned.to_align and "problem" not in aligned.to_align


def test_a_section_placed_from_the_plan_is_marked_when_the_plan_changes(monkeypatch):
    from app.proposals import decisions
    from app.proposals.models import ProposalPlan
    from app.proposals.pipeline import align_document

    plan = ProposalPlan.model_validate(PLAN)
    real = rulebook.sections

    def with_purpose(rulebook_id, chapter, level, p):  # "guide": the standard structure with a section for the general objective
        out = real(rulebook.DEFAULT, chapter, level, p)
        if rulebook_id == "guide" and chapter == 1:
            out = [*out[:2], rulebook.SectionPlan("purpose", "1.2", "Aim of the Study", "The aim.", 100, from_plan="purpose"), *out[2:]]
        return out

    monkeypatch.setattr(rulebook, "sections", with_purpose)
    aligned = align_document(_chapter(), rulebook.DEFAULT, "guide", "MASTERS", plan)
    purpose = next(s for s in aligned.sections if s.key == "purpose")
    assert purpose.depends and not decisions.stale(aligned.model_copy(update={"sections": [purpose]}), plan)
    changed = plan.model_copy(update={"purpose": "To study something else entirely."})
    assert "1.2 Aim of the Study" in decisions.stale(aligned, changed)


def test_a_revision_keeps_what_the_chapter_still_lacks_and_has_cost():
    from app.proposals.pipeline import _merge

    base = _chapter(to_align=["background"], missing=["definitions"])
    revised = base.model_copy(update={"sections": [base.sections[0].model_copy(update={"paragraphs": ["Revised."]})]})
    merged, _ = _merge(base, revised, {"background"})
    assert merged.missing == ["definitions"] and (merged.full_price, merged.paid) == (9000, 4000) and merged.to_align == []


# --- 6, 7: guide profiles -------------------------------------------------------------------------------------------


def test_a_guides_own_objective_count_is_enforced(monkeypatch):
    from app.proposals.models import ProposalPlan

    book = profile.build({**_answer(), "objectives": {"min": 4, "max": 4}}, "guide.docx")
    assert book["objectives_enforced"] and "objectives_by_level" not in book
    monkeypatch.setattr(rulebook, "load", lambda rulebook_id: book)
    assert rulebook.enforced_counts("custom-x")
    three = ProposalPlan.model_validate(PLAN)
    assert any("takes 4 specific objectives" in p for p in rulebook.plan_problems("custom-x", three, "MASTERS"))


def test_a_guide_with_questions_and_hypotheses_as_two_sections_is_accepted():
    answer = _answer()
    base = [s for s in answer["chapters"][0]["sections"] if s["key"] != "questions"]
    extra = [{"key": "rq", "heading": "Research Questions", "brief": "x", "share": 0.05, "perObjective": False, "table": False},
             {"key": "hyp", "heading": "Research Hypotheses", "brief": "y", "share": 0.05, "perObjective": False, "table": False}]
    answer["chapters"][0]["sections"] = [*base, *extra]
    sections = {s["heading"]: s for s in profile.build(answer, "guide.docx")["chapters"][0]["sections"]}
    assert sections["Research Questions"].get("from_plan") == "questions" and "from_plan" not in sections["Research Hypotheses"]
    answer["chapters"][0]["sections"] = [*base, extra[0], {**extra[0], "key": "rq2", "heading": "Research Questions of the Study"}]
    with pytest.raises(profile.AmbiguousGuide):  # two sections for the same questions is still ambiguous
        profile.build(answer, "guide.docx")


# --- 9, 10, 11: capacity --------------------------------------------------------------------------------------------


def test_a_job_stopped_while_waiting_for_a_slot_sends_nothing(client, monkeypatch):
    from app.jobs import capacity
    from app.jobs.models import JobStatus
    from app.runtime import get_runtime
    from tests.test_api import wait

    project = _create(client)
    quoted = client.post(f"/api/projects/{project['id']}/steps", headers=STUDENT, json={"step": "PLAN"}).json()
    job_id = quoted["job"]["id"]
    stopped = {"done": False}

    def waiting_gate(store, settings, owner, sleep=time.sleep):
        def take(model, searching):
            if not stopped["done"]:  # the job is stopped while its first call waits for a slot
                stopped["done"] = True

                def stop(j):
                    j.status = JobStatus.FAILED
                    return j

                get_runtime().store.update(job_id, stop)
            return (lambda: None), 1500

        return take

    monkeypatch.setattr(capacity, "gate", waiting_gate)
    before = len(client.models.tasks)
    client.post(f"/api/projects/{project['id']}/steps/{job_id}/submit", headers=STUDENT, json={"quoteId": quoted["quote"]["id"]})
    assert wait(client, job_id, STUDENT)["status"] == "FAILED"
    time.sleep(0.5)
    assert stopped["done"] and len(client.models.tasks) == before  # no request reached the provider


def test_a_job_stopped_for_capacity_can_be_resumed_with_a_fresh_allowance(client, monkeypatch):
    from app.jobs.service import resumable
    from app.runtime import get_runtime

    settings = get_runtime().settings
    monkeypatch.setattr(settings, "capacity_retry_sec", 0)
    monkeypatch.setattr(settings, "capacity_max_waits", 1)

    def busy(payload):
        raise CapacityWait("every slot is in use")

    client.models.overrides["p_needs"] = busy
    project = _create(client)
    job = _run(client, project["id"], "PLAN")
    assert job["status"] == "FAILED" and job["failure"]["code"] == "CAPACITY_BUSY" and job["failure"]["retryable"]
    stored = get_runtime().store.get(job["id"])
    assert resumable(get_runtime(), stored) and stored.capacity_waits == 2
    assert settings.model_fields["capacity_max_waits"].default == 130  # about two hours of pauses, as the message says


def test_searches_count_within_their_models_limit():
    from app.integrations.store import LocalJobStore
    from app.jobs import capacity

    class S:
        vertex_project, vertex_location = "paperaid", "global"
        capacity_default, capacity_limits, capacity_search, capacity_wait_sec = 3, {}, 2, 0.05

    import tempfile
    from pathlib import Path

    take = capacity.gate(LocalJobStore(Path(tempfile.mkdtemp())), S(), "job", sleep=lambda s: None)
    first, _ = take("flash", True)
    take("flash", True)
    with pytest.raises(CapacityWait):
        take("flash", True)  # two searches at most
    take("flash", False)  # the third of the model's three slots
    with pytest.raises(CapacityWait):
        take("flash", False)  # searches and other calls share the model's limit
    first()
    take("flash", False)  # a finished search frees a slot of the model too


# --- 12: timings ------------------------------------------------------------------------------------------------------


def test_a_step_that_publishes_itself_still_records_its_last_stage(client):
    from app.runtime import get_runtime
    from speed_report import report

    project = _create(client)
    job = _run(client, project["id"], "PLAN")
    for _ in range(100):  # the last stage's record is written just after the step publishes itself
        stored = get_runtime().store.get(job["id"])
        done = [t.stage.value for t in stored.timings if t.outcome == "DONE"]
        if done[-1] == "EXPORTING":
            break
        time.sleep(0.05)
    assert done[-1] == "EXPORTING" and len(done) == len(stored.pipeline)  # every stage, the publishing one included
    record = stored.model_dump(mode="json", by_alias=True)
    assert report([record])["jobs"]["PLAN"]["completedFirstTry"] == 1
    record["modelCalls"][0]["errorCode"] = "VERTEX_TIMEOUT"  # a call lost and asked again is not a first-try completion
    assert report([record])["jobs"]["PLAN"]["completedFirstTry"] == 0


# --- 13: which error decides ----------------------------------------------------------------------------------------


def test_a_terminal_error_in_one_topic_is_not_hidden_by_a_wait_in_another():
    from app.proposals.pipeline import research_topics

    class Ctx:
        def activity(self, *args, **kwargs):
            pass

    def answer(n):
        if n == 0:
            raise CapacityWait("every slot is in use")
        if n == 1:
            raise PermanentStageError("MODEL_REFUSED", "refused", "refused")
        return []

    with pytest.raises(PermanentStageError):
        research_topics(Ctx(), [0, 1, 2], answer, 2)  # type: ignore[arg-type]


# --- 14: the framework's arrows -----------------------------------------------------------------------------------------


@pytest.mark.parametrize(("arrows", "boxes"), [(1, [(100, 180), (220, 300)]), (3, [(100, 180), (220, 300)]), (5, [(100, 150), (200, 400), (430, 470)]), (2, [(100, 300)])])
def test_every_arrow_ends_on_a_dependent_variables_box(arrows, boxes):
    from app.proposals.framework import arrow_ends

    ends = arrow_ends(arrows, boxes)
    assert len(ends) == arrows and all(any(top < y < bottom for top, bottom in boxes) for y in ends)
    assert ends == sorted(ends)  # in the order of the independent variables: no crossing for its own sake


def test_alignment_adds_a_section_then_a_revision_then_the_finish(client):
    """#5 end to end: a guide adds a section and asks an existing one differently; revising first must not lose the
    section still to write."""
    project_id, url = _aligned(client)
    chapter = client.get(f"{url}/chapters/1", headers=STUDENT).json()
    assert chapter["missing"] and chapter["toAlign"]
    asked = client.post(f"{url}/chapters/1/request", headers=STUDENT, json={"instruction": "Revise this section to my institution's guide.", "sections": chapter["toAlign"][:1]})
    before = {c["id"] for c in client.get(url, headers=STUDENT).json()["feedback"]} - {c["id"] for c in asked.json()["feedback"]}
    mine = next(c["id"] for c in asked.json()["feedback"] if c["id"] not in before and c["by"] == "STUDENT" and c["status"] == "OPEN")
    quoted = client.post(f"{url}/steps", headers=STUDENT, json={"step": "REVISE_1", "comments": [mine]}).json()
    client.post(f"{url}/steps/{quoted['job']['id']}/submit", headers=STUDENT, json={"quoteId": quoted["quote"]["id"]})
    from tests.test_api import wait

    assert wait(client, quoted["job"]["id"], STUDENT)["status"] == "COMPLETED"
    assert client.get(f"{url}/chapters/1", headers=STUDENT).json()["missing"] == chapter["missing"]  # still to write
    assert _run(client, project_id, "COMPLETE_1")["status"] == "COMPLETED"
    assert not client.get(f"{url}/chapters/1", headers=STUDENT).json()["missing"]
