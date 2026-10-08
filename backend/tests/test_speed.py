"""Speed and rate limits (plan of 2026-10-08, Codex-reviewed): the shared limit on Gemini calls, pausing for capacity
without losing work or retries, research topics worked on side by side with their results in a fixed order and saved
as they finish, stage timings and what the student sees. Nothing here changes what is written or checked."""

import threading
import time

import pytest

from app.core.errors import CapacityWait, LimiterUnavailable
from app.integrations.store import LocalJobStore
from app.jobs import capacity
from tests.test_api import STUDENT
from tests.test_proposals import _create, _run


class _Settings:
    vertex_project, vertex_location = "paperaid", "global"
    capacity_default, capacity_limits, capacity_search, capacity_wait_sec = 3, {"pro": 1}, 2, 0.2


def test_the_shared_limit_is_never_exceeded_however_many_calls_ask_at_once(tmp_path):
    store = LocalJobStore(tmp_path)
    take = capacity.gate(store, _Settings(), "job_a", sleep=lambda s: time.sleep(0.01))
    held, most, lock, refused = [0], [0], threading.Lock(), [0]

    def call():
        try:
            release, _ = take("flash", False)
        except CapacityWait:
            with lock:
                refused[0] += 1
            return
        with lock:
            held[0] += 1
            most[0] = max(most[0], held[0])
        time.sleep(0.05)
        with lock:
            held[0] -= 1
        release()

    threads = [threading.Thread(target=call) for _ in range(12)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert most[0] <= 3 and most[0] >= 2  # never more than the limit, and the limit is used
    assert capacity.slots_for(_Settings(), "pro", False) == 1 and capacity.slots_for(_Settings(), "flash", True) == 2  # per model; searches apart


def test_a_slot_is_freed_only_by_the_request_that_holds_it(tmp_path):
    store = LocalJobStore(tmp_path)
    first = store.take_slot("r", 1, "late-request", ttl_sec=0.01)
    time.sleep(0.02)  # its time is up: another request takes the slot over
    second = store.take_slot("r", 1, "new-request", ttl_sec=60)
    assert first == second == 0
    store.release_slot("r", 0, "late-request")  # the late request finishing must not free its successor's slot
    assert store.take_slot("r", 1, "third", ttl_sec=60) is None
    store.release_slot("r", 0, "new-request")
    assert store.take_slot("r", 1, "third", ttl_sec=60) == 0


def test_when_the_limiter_cannot_be_reached_calls_pause_and_never_bypass_it():
    class Down:
        def take_slot(self, *args):
            raise LimiterUnavailable("ServiceUnavailable")

    take = capacity.gate(Down(), _Settings(), "job_a")  # type: ignore[arg-type]
    with pytest.raises(CapacityWait):
        take("flash", False)


def test_a_full_limit_pauses_the_call_after_its_wait():
    class Full:
        def take_slot(self, *args):
            return None

    take = capacity.gate(Full(), _Settings(), "job_a", sleep=lambda s: None)  # type: ignore[arg-type]
    started = time.monotonic()
    with pytest.raises(CapacityWait):
        take("flash", False)
    assert time.monotonic() - started >= 0.2


def _quick_pauses(monkeypatch, **changes):
    from app.runtime import get_runtime

    settings = get_runtime().settings
    monkeypatch.setattr(settings, "capacity_retry_sec", 0)
    for name, value in changes.items():
        monkeypatch.setattr(settings, name, value)


def test_a_stage_paused_for_capacity_keeps_its_work_and_its_retries(client, monkeypatch):
    from app.runtime import get_runtime
    from tests.fake_models import FakeModels

    _quick_pauses(monkeypatch)
    paused = {"n": 0}

    def needs(payload):
        if paused["n"] < 2:  # the first two times, no capacity is free
            paused["n"] += 1
            raise CapacityWait("every slot is in use")
        return FakeModels().default("p_needs", payload)

    client.models.overrides["p_needs"] = needs
    project = _create(client)
    job = _run(client, project["id"], "PLAN")
    assert job["status"] == "COMPLETED", job.get("failure")
    stored = get_runtime().store.get(job["id"])
    assert stored.capacity_waits == 2
    assert sum(1 for e in stored.events if e.label.startswith("Waiting for capacity")) == 1  # said once, not every pause
    assert not any(e.label.startswith("Retrying") for e in stored.events)  # no provider-failure retry was used
    outcomes = [t.outcome for t in stored.timings]
    assert outcomes.count("WAITING") == 2 and outcomes[-1] == "DONE" and stored.activity is None
    assert all(c.prompt_chars > 0 for c in stored.model_calls)


def test_a_job_that_never_gets_capacity_stops_uncharged(client, monkeypatch):
    from app.runtime import get_runtime

    _quick_pauses(monkeypatch, capacity_max_waits=1)

    def busy(payload):
        raise CapacityWait("every slot is in use")

    client.models.overrides["p_needs"] = busy
    project = _create(client)
    job = _run(client, project["id"], "PLAN")
    assert job["status"] == "FAILED" and job["failure"]["code"] == "CAPACITY_BUSY"
    stored = get_runtime().store.get(job["id"])
    assert stored.payment_status.value in ("NOT_REQUIRED", "REFUNDED") and stored.billing.charged == 0


def test_research_topics_side_by_side_keep_the_order_of_one_at_a_time():
    import random

    from app.proposals.pipeline import research_topics

    class Ctx:
        def __init__(self):
            self.seen = []

        def activity(self, kind, done=0, total=0, note=""):
            self.seen.append((kind, done, total))

    def answer(n):
        time.sleep(random.random() / 50)  # topics finish in any order
        return [f"{n}-a", f"{n}-b"]

    topics = list(range(8))
    one, two = Ctx(), Ctx()
    assert research_topics(two, topics, answer, 2) == research_topics(one, topics, answer, 1)  # type: ignore[arg-type]
    assert two.seen[0] == ("SOURCES", 0, 8) and two.seen[-1] == ("SOURCES", 8, 8)


def test_an_error_in_one_topic_waits_for_the_others_to_finish():
    from app.proposals.pipeline import research_topics

    finished = []

    class Ctx:
        def activity(self, *args, **kwargs):
            pass

    def answer(n):
        if n == 0:
            raise CapacityWait("every slot is in use")
        time.sleep(0.02)
        finished.append(n)
        return []

    with pytest.raises(CapacityWait):
        research_topics(Ctx(), [0, 1, 2], answer, 2)  # type: ignore[arg-type]
    assert sorted(finished) == [1, 2]  # every paid answer was kept before the stage paused


def test_a_topic_answered_in_full_is_saved_and_read_back_on_a_retry():
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
    calls = {"n": 0}

    def search():
        calls["n"] += 1
        return [item]

    ctx = Ctx()
    assert checkpointed(ctx, Runner(), Need(), search)[0].id == "E1"
    assert checkpointed(ctx, Runner(), Need(), search)[0].id == "E1" and calls["n"] == 1  # the retry read it back


def test_a_search_gets_a_shorter_time_limit_never_below_what_its_answer_needs():
    from app.ai.vertex import RESEARCH_CALL_TASKS, call_timeout

    assert "p_search" in RESEARCH_CALL_TASKS and "p_draft" not in RESEARCH_CALL_TASKS
    assert call_timeout(2000, 75) == 75 and call_timeout(12000, 75) == 130  # the token-rate rule wins for a long allowance


def test_the_speed_report_reads_what_jobs_record(client):
    from app.runtime import get_runtime
    from speed_report import report

    project = _create(client)
    job = _run(client, project["id"], "PLAN")
    stored = get_runtime().store.get(job["id"])
    out = report([stored.model_dump(mode="json", by_alias=True)])
    assert out["jobs"]["PLAN"]["completedFirstTry"] == 1 and any(k.startswith("p_needs") for k in out["calls"])
    assert client.get(f"/api/jobs/{job['id']}", headers=STUDENT).json().get("activity") is None
