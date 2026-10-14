"""Coursework, proposals/thesis and funding: resource, recovery and financial boundaries.
All documents/identities are synthetic and providers are stand-ins.
"""

import io
import json
import logging
import sys
import threading
from concurrent.futures import ThreadPoolExecutor

import pandas as pd
import pytest

from app.core.errors import InvalidDocument
from tests.conftest import fixture_bytes
from tests.test_api import STUDENT


@pytest.mark.parametrize("headers", [{}, {"Authorization": "Bearer invalid"}, {"Authorization": "Dev invalid"}])
def test_upload_is_authenticated_before_multipart_parsing(client, monkeypatch, headers):
    from starlette.formparsers import MultiPartParser

    async def forbidden(*args, **kwargs):
        raise AssertionError("Unauthenticated body reached the multipart parser")
    monkeypatch.setattr(MultiPartParser, "parse", forbidden)
    response = client.post("/api/projects/missing/guideline", headers=headers, files={"file": ("guide.pdf", b"x" * 2048)})
    assert response.status_code == 401


@pytest.mark.parametrize("declared", [None, "1", "999999999"])
def test_request_bytes_are_bounded_even_without_an_honest_length(client, declared):
    from app.runtime import get_runtime

    get_runtime().settings.max_upload_bytes = 100
    # JSON bodies have the same transport ceiling. The streaming count does not trust headers.
    headers = {**STUDENT, "Content-Type": "application/json"}
    if declared is not None:
        headers["Content-Length"] = declared
    response = client.post("/api/projects", headers=headers, content=b"x" * (1024 * 1024 + 101))
    assert response.status_code == 413 and response.json()["code"] == "FILE_TOO_LARGE"


def test_paper_upload_uses_shared_quota(client):
    from app.runtime import get_runtime

    get_runtime().settings.uploads_per_hour = 1
    job = client.post("/api/jobs", headers=STUDENT).json()["id"]
    file = {"file": ("paper.docx", fixture_bytes("simple_essay.docx"))}
    assert client.post(f"/api/jobs/{job}/files/source", headers=STUDENT, files=file).status_code == 200
    assert client.post(f"/api/jobs/{job}/files/source", headers=STUDENT, files=file).status_code == 429


def test_pdf_word_limit_stops_before_later_pages(monkeypatch):
    from app.documents import pdf_io

    seen = []
    class Page:
        def extract_text(self):
            seen.append(True)
            return "synthetic academic wording " * 100
    class Reader:
        is_encrypted = False
        pages = [Page(), Page(), Page()]
        def __init__(self, stream):
            pass
    monkeypatch.setattr(pdf_io, "PdfReader", Reader)
    with pytest.raises(InvalidDocument) as failure:
        pdf_io._read_pdf(b"synthetic", 150, 100)
    assert failure.value.code == "DOCUMENT_TOO_LONG" and len(seen) == 1


def test_compressed_pdf_stream_is_refused_before_large_expansion():
    from pypdf import PdfWriter
    from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

    from app.documents.pdf_io import read_pdf

    writer = PdfWriter()
    page = writer.add_blank_page(width=600, height=800)
    font = DictionaryObject({NameObject("/Type"): NameObject("/Font"), NameObject("/Subtype"): NameObject("/Type1"), NameObject("/BaseFont"): NameObject("/Helvetica")})
    page[NameObject("/Resources")] = DictionaryObject({NameObject("/Font"): DictionaryObject({NameObject("/F1"): writer._add_object(font)})})
    stream = DecodedStreamObject()
    stream.set_data(b"BT /F1 12 Tf (" + b"x" * (9 * 1024 * 1024) + b") Tj ET")
    page[NameObject("/Contents")] = writer._add_object(stream.flate_encode())
    output = io.BytesIO()
    writer.write(output)
    with pytest.raises(InvalidDocument):
        read_pdf(output.getvalue(), 150)


def test_log_diagnostics_do_not_include_exception_or_nested_inputs():
    from app.core.logging import JsonFormatter

    try:
        raise ValueError("PRIVATE_SENTINEL")
    except ValueError:
        record = logging.LogRecord("paperaid.worker", logging.ERROR, "test.py", 1, "stage crashed %s", ("PRIVATE_SENTINEL",), sys.exc_info())
    record.fields = {"nested": [{"text": "PRIVATE_SENTINEL", "access_token": "PRIVATE_SENTINEL", "count": 3}],
                     "detail": "PRIVATE_SENTINEL", "problem": "PRIVATE_SENTINEL", "response": {"message": "PRIVATE_SENTINEL"}}
    rendered = JsonFormatter().format(record)
    assert "PRIVATE_SENTINEL" not in rendered
    result = json.loads(rendered)
    assert result["exceptionType"] == "ValueError" and result["frames"] and result["nested"] == [{"count": 3}]


def test_admin_failure_diagnostics_cannot_repeat_student_text(client):
    from app.jobs.models import JobFailure, JobStatus
    from app.runtime import get_runtime
    from tests.test_api import ADMIN

    job_id = client.post("/api/jobs", headers=STUDENT).json()["id"]
    def failed(j):
        j.status = JobStatus.FAILED
        j.failure = JobFailure(code="INTERNAL", user_message="PRIVATE_SENTINEL", retryable=True)
        j.failure_detail = "PRIVATE_SENTINEL"
        return j
    get_runtime().store.update(job_id, failed)
    admin = client.get(f"/api/admin/jobs/{job_id}", headers=ADMIN)
    assert admin.status_code == 200 and "PRIVATE_SENTINEL" not in admin.text
    assert "PRIVATE_SENTINEL" in client.get(f"/api/jobs/{job_id}", headers=STUDENT).text


def test_cross_tab_rejects_actual_cardinality_before_allocating(monkeypatch):
    from app.datalab.engine import stats
    from app.datalab.models import AnalysisSpec, Variable

    frame = pd.DataFrame({"a": [f"a{i}" for i in range(100)], "b": [f"b{i}" for i in range(100)]})
    variables = {name: Variable(name=name, kind="CATEGORICAL", stored="text", valid=100, missing=0, distinct=2) for name in frame.columns}
    def forbidden(*a, **kw):
        raise AssertionError("Dense grid was allocated before the limit")
    monkeypatch.setattr(pd, "crosstab", forbidden)
    result = stats.run(stats.Context(frame, variables, 1), AnalysisSpec(kind="CROSSTAB", variables=["a", "b"]))
    assert result.status == "NOT_ESTIMABLE"


def test_simultaneous_last_slot_submits_are_admitted_atomically(client, monkeypatch):
    from app.runtime import get_runtime

    rt = get_runtime()
    rt.settings.max_active_jobs_per_user = 3
    monkeypatch.setattr(rt.queue, "enqueue", lambda *a, **kw: None)
    jobs = []
    for _ in range(4):
        job = client.post("/api/jobs", headers=STUDENT).json()["id"]
        client.post(f"/api/jobs/{job}/files/source", headers=STUDENT, files={"file": ("paper.docx", fixture_bytes("simple_essay.docx"))})
        quoted = client.post(f"/api/jobs/{job}/quote", headers=STUDENT, json={"selection": {"formatting": "FORMAT", "preset": "apa7"}})
        assert quoted.status_code == 200
        jobs.append((job, quoted.json()["quote"]["id"]))
    original = rt.store.count_active
    barrier, lock, calls = threading.Barrier(4), threading.Lock(), 0
    def simultaneous(uid):
        nonlocal calls
        value = original(uid)
        with lock:
            calls += 1
            first = calls <= 4
        if first:
            barrier.wait(timeout=15)
        return value
    monkeypatch.setattr(rt.store, "count_active", simultaneous)
    def submit(item):
        job, quote = item
        return client.post(f"/api/jobs/{job}/submit", headers=STUDENT, json={"quoteId": quote}).status_code
    with ThreadPoolExecutor(max_workers=4) as pool:
        statuses = list(pool.map(submit, jobs))
    assert sorted(statuses) == [200, 200, 200, 429]


def _running_context(client, owner="attempt-a"):
    from app.jobs.models import JobStatus, Stage
    from app.jobs.pipeline import StageContext
    from app.runtime import get_runtime

    rt = get_runtime()
    rt.settings.gemini_workflow = False
    rt.settings.model_prices = {**rt.settings.model_prices, "fake:gpt-6-luna": (1, 2, .1)}
    job_id = client.post("/api/jobs", headers=STUDENT).json()["id"]
    def running(j):
        j.status, j.stage, j.lease_owner, j.budget_usd = JobStatus.PROCESSING, Stage.PLANNING, owner, 1.0
        return j
    job = rt.store.update(job_id, running)
    return StageContext(rt, job)


def _answer_provider(monkeypatch, before=None):
    from app.ai import orchestration
    from app.ai.providers import ModelResult, Usage

    class Provider:
        name = "fake"
        calls = 0
        def json(self, *a, **kw):
            self.calls += 1
            if before:
                before()
            return ModelResult(text='{"ok":true}', usage=Usage(100, 100, 0, 1), provider="fake", model="gpt-6-luna")
    provider = Provider()
    monkeypatch.setattr(orchestration, "provider_for", lambda *a: (provider, "gpt-6-luna"))
    return provider


def _ask(runner):
    from pydantic import BaseModel

    class Answer(BaseModel):
        ok: bool
    # A manual StageContext has no priced WorkStepInput. Supply its otherwise frozen work
    # roles explicitly; actual work jobs obtain these from their quote's work_engine.
    runner._engine.roles = dict(runner.settings.role_models)
    return runner._call("w_read", {"synthetic": "test"}, {"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"]}, Answer)


def test_provider_is_called_only_after_its_allowance_is_durable(client, monkeypatch):
    ctx = _running_context(client)
    def before():
        j = ctx.rt.store.get(ctx.job.id)
        assert len(j.pending_calls) == 1 and j.reserved_usd > 0
    provider = _answer_provider(monkeypatch, before)
    assert _ask(ctx.ai()).ok
    job = ctx.rt.store.get(ctx.job.id)
    assert provider.calls == 1 and not job.pending_calls and job.reserved_usd == 0 and job.cost_usd > 0
    assert job.model_calls[-1].call_id
    assert "pendingCalls" not in job.view().model_dump(by_alias=True)


def test_lost_record_keeps_allowance_and_cannot_replay_past_the_cap(client, monkeypatch):
    from app.core.errors import PermanentStageError

    class HardStop(BaseException):
        pass
    ctx = _running_context(client)
    provider = _answer_provider(monkeypatch)
    runner = ctx.ai()
    def lost(call):
        raise HardStop()
    runner._record = lost
    with pytest.raises(HardStop):
        _ask(runner)
    pending = ctx.rt.store.get(ctx.job.id)
    assert provider.calls == 1 and len(pending.pending_calls) == 1 and pending.reserved_usd > 0 and pending.cost_usd == 0
    ctx.rt.store.update(pending.id, lambda j: j.model_copy(update={"budget_usd": pending.reserved_usd * 1.5, "lease_owner": "replacement"}))
    from app.jobs.pipeline import StageContext
    replacement = StageContext(ctx.rt, ctx.rt.store.get(pending.id))
    with pytest.raises(PermanentStageError) as failure:
        _ask(replacement.ai())
    assert failure.value.code == "BUDGET_EXCEEDED" and provider.calls == 1


def test_parallel_calls_settle_without_double_counting_live_allowances(client, monkeypatch):
    ctx = _running_context(client)
    barrier = threading.Barrier(2)
    provider = _answer_provider(monkeypatch, lambda: barrier.wait(timeout=10))
    runner = ctx.ai()
    answers = runner.together(lambda: _ask(runner), lambda: _ask(runner))
    assert all(a.ok for a in answers) and provider.calls == 2
    j = ctx.rt.store.get(ctx.job.id)
    assert not j.pending_calls and j.reserved_usd == 0 and len(j.model_calls) == 2


def test_daily_budget_admits_and_settles_in_the_same_unit_as_the_job(client):
    from app.core.errors import RetryableStageError
    from app.jobs.models import ModelCall, Stage, utcnow

    a, b = _running_context(client), _running_context(client)
    a.rt.settings.daily_ai_budget_usd = 1
    first, second = a.ai(), b.ai()
    call_id = first._reserve_call("artificial-a", .75, 1)
    with pytest.raises(RetryableStageError) as failure:
        second._reserve_call("artificial-b", .75, 1)
    assert failure.value.code == "DAILY_SPEND_LIMIT" and not a.rt.store.get(b.job.id).pending_calls
    call = ModelCall(call_id=call_id, stage=Stage.PLANNING, provider="fake", model="gpt-6-luna", prompt_version="test", input_tokens=100,
                     output_tokens=100, cached_tokens=0, latency_ms=1, cost_usd=.1)
    first._record(call)
    first._record(call)  # idempotent callback
    assert len(a.rt.store.get(a.job.id).model_calls) == 1
    second._reserve_call("artificial-b", .75, 1)
    ledger = json.loads((a.rt.settings.data_dir / "ai-spend" / f"{utcnow().date().isoformat()}.json").read_text())
    assert ledger == {"spent": .1, "reserved": .75}


def test_stale_worker_cannot_reserve_a_new_call(client, monkeypatch):
    from app.jobs.pipeline import StageContinues

    ctx = _running_context(client)
    provider = _answer_provider(monkeypatch)
    ctx.rt.store.update(ctx.job.id, lambda j: j.model_copy(update={"lease_owner": "replacement"}))
    with pytest.raises(StageContinues):
        _ask(ctx.ai())
    assert provider.calls == 0 and not ctx.rt.store.get(ctx.job.id).pending_calls


def test_two_people_racing_the_daily_allowance_cannot_both_take_the_last_slot(client):
    from app.core.errors import RetryableStageError

    a, b = _running_context(client), _running_context(client)
    a.rt.settings.daily_ai_budget_usd = 1
    barrier = threading.Barrier(2)
    def reserve(ctx):
        barrier.wait(timeout=10)
        try:
            ctx.ai()._reserve_call("synthetic", .75, 1)
            return "ADMITTED"
        except RetryableStageError as exc:
            return exc.code
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(reserve, (a, b))) == ["ADMITTED", "DAILY_SPEND_LIMIT"]
    assert sum(a.rt.store.get(c.job.id).reserved_usd for c in (a, b)) == .75


def test_replaced_attempt_can_record_its_own_usage_without_disrupting_replacement(client):
    from app.jobs.models import ModelCall, Stage

    ctx = _running_context(client)
    ctx.rt.settings.daily_ai_budget_usd = 1
    runner = ctx.ai()
    call_id = runner._reserve_call("synthetic", .5, 1)
    ctx.rt.store.update(ctx.job.id, lambda j: j.model_copy(update={"lease_owner": "replacement", "stage": Stage.DRAFTING}))
    call = ModelCall(call_id=call_id, phase="job", stage=Stage.PLANNING, provider="fake", model="gpt-6-luna", prompt_version="test",
                     input_tokens=100, output_tokens=100, cached_tokens=0, latency_ms=1, cost_usd=.1)
    runner._record(call)
    runner._record(call)
    job = ctx.rt.store.get(ctx.job.id)
    assert job.lease_owner == "replacement" and job.stage == Stage.DRAFTING and job.status == "PROCESSING"
    assert job.cost_usd == .1 and job.reserved_usd == 0 and not job.pending_calls and len(job.model_calls) == 1


def test_fractional_call_allowances_do_not_leave_a_phantom_reserve(client):
    from app.jobs.models import ModelCall, Stage

    ctx = _running_context(client)
    ctx.rt.settings.daily_ai_budget_usd = 1
    runner = ctx.ai()
    for _ in range(10):
        call_id = runner._reserve_call("synthetic", .0000017, 1)
        pending = ctx.rt.store.get(ctx.job.id).pending_calls[call_id]
        assert pending.amount == .000002
        runner._record(ModelCall(call_id=call_id, phase="job", stage=Stage.PLANNING, provider="fake", model="gpt-6-luna", prompt_version="test",
                                 input_tokens=1, output_tokens=1, cached_tokens=0, latency_ms=1, cost_usd=.000001))
    job = ctx.rt.store.get(ctx.job.id)
    assert job.reserved_usd == 0 and not job.pending_calls


def test_retracted_index_record_is_not_sent_to_the_reader(monkeypatch):
    from app.analysis import fetch
    from app.jobs.models import TopicRoute
    from app.proposals.pipeline import _from_index

    monkeypatch.setattr(fetch, "openalex_find", lambda *a: ("FOUND", [{"doi": "10.1000/a", "retracted": "yes"}]))
    class Runner:
        def extract(self, *a):
            raise AssertionError("Retracted work was sent for extraction")
    assert _from_index(Runner(), "synthetic need", "query", 1, "2026-10-13", 6, None, TopicRoute()) == []


@pytest.mark.parametrize("style", ["APA6", "APA7", "HARVARD"])
def test_preprints_are_labelled_and_retracted_evidence_is_unusable(style):
    from app.proposals.evidence import reference, source_context
    from app.proposals.models import EvidenceItem, EvidenceSource

    source = EvidenceSource(url="https://example.org/a", title="Synthetic study", authors=["Test, A."], year="2026", preprint=True, retracted=True)
    item = EvidenceItem(id="Etest", chapter=1, need="synthetic", statement="A finding.", passage="A finding.", verified=True,
                        support="SUPPORTED", source=source, retrieved_on="2026-10-13")
    assert not item.usable and "[Preprint]" in reference(source, style)
    assert source_context(item)["sourceKind"] == "PREPRINT"


def test_daily_call_allowance_recovers_after_failure_between_ledger_and_job(client, monkeypatch):
    from app.integrations.store import LocalJobStore

    ctx = _running_context(client)
    ctx.rt.settings.daily_ai_budget_usd = 1
    store = ctx.rt.store
    original_write = store._write

    def fail_after_ledger(job):
        raise OSError("Simulated local disk interruption")
    monkeypatch.setattr(store, "_write", fail_after_ledger)
    with pytest.raises(OSError):
        ctx.ai()._reserve_call("synthetic", .5, 1)
    monkeypatch.setattr(store, "_write", original_write)
    recovered = LocalJobStore(ctx.rt.settings.data_dir)
    job = recovered.get(ctx.job.id)
    assert job.reserved_usd == .5 and len(job.pending_calls) == 1
    ledger = json.loads(next((ctx.rt.settings.data_dir / "ai-spend").glob("*.json")).read_text())
    assert ledger == {"spent": 0, "reserved": .5} and not store._journal.exists()


def test_accounting_failure_frees_live_waiters_but_keeps_durable_allowance(client, monkeypatch):
    from app.ai import costs

    ctx = _running_context(client)
    provider = _answer_provider(monkeypatch)
    runner = ctx.ai()
    monkeypatch.setattr(costs, "cost_usd", lambda *a, **kw: (_ for _ in ()).throw(ValueError("Simulated accounting failure")))
    with pytest.raises(ValueError):
        _ask(runner)
    assert provider.calls == 1 and ctx.rt.store.get(ctx.job.id).reserved_usd > 0
    assert runner._inflight == runner._durable_inflight == 0


def test_parser_timeout_releases_its_slot_and_does_not_print_private_output(monkeypatch):
    import subprocess

    from app.documents import intake, pdf_io

    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired("synthetic parser", 25, output=b"PRIVATE_SENTINEL", stderr=b"PRIVATE_SENTINEL")
    monkeypatch.setattr(subprocess, "run", timeout)
    for parse in (lambda: pdf_io.read_pdf(b"synthetic", 20), lambda: intake._isolated_docx(b"synthetic", 200)):
        with pytest.raises(InvalidDocument) as failure:
            parse()
        assert "PRIVATE_SENTINEL" not in str(failure.value)
        assert pdf_io._PARSER_SLOT.acquire(blocking=False)
        pdf_io._PARSER_SLOT.release()


def test_research_pdf_uses_the_bounded_reader(monkeypatch):
    from app.analysis import fetch

    seen = []
    monkeypatch.setattr(fetch, "source_pdf_text", lambda body: seen.append(body) or "Exact scholarly passage")
    assert fetch._text(b"%PDF-synthetic", "application/pdf") == "Exact scholarly passage"
    assert seen == [b"%PDF-synthetic"]


def test_retraction_decision_is_reused_during_export_without_another_lookup(monkeypatch):
    from types import SimpleNamespace

    from app.analysis import fetch
    from app.jobs.models import Stage, utcnow
    from app.proposals.models import EvidenceItem, EvidenceSource
    from app.proposals.pipeline import _library

    item = EvidenceItem(id="E1", chapter=1, need="synthetic", statement="A finding.", passage="A finding.", verified=True,
                        support="SUPPORTED", source=EvidenceSource(url="https://example.org/a", title="Study", doi="10.1000/test"),
                        retrieved_on="2026-01-01")
    def forbidden(*a):
        raise AssertionError("Export issued another retraction lookup")
    monkeypatch.setattr(fetch, "openalex_retracted", forbidden)
    artifacts = {"evidence.json": [item.model_dump(mode="json")],
                 "retractions.json": {"day": utcnow().date().isoformat(), "dois": {"10.1000/test": True}}}
    ctx = SimpleNamespace(rt=SimpleNamespace(files=None), job=SimpleNamespace(stage=Stage.EXPORTING), has=lambda n: n in artifacts,
                          get_json=lambda n: artifacts[n])
    current = _library(ctx, SimpleNamespace(evidence_files=[], academic_policy=2))["E1"]
    assert not current.usable and current.source.retracted and current.source.retraction_checked
    legacy = _library(ctx, SimpleNamespace(evidence_files=[], academic_policy=1))["E1"]
    assert legacy.usable and not legacy.source.retracted


def test_provenance_version_keeps_historical_model_payloads_unchanged():
    from app.proposals.models import EvidenceItem, EvidenceSource
    from app.proposals.pipeline import _for_model

    item = EvidenceItem(id="E1", chapter=1, need="synthetic", statement="A finding.", passage="A finding.", verified=True,
                        support="SUPPORTED", source=EvidenceSource(url="https://example.org/a", title="Study", doi="10.1000/test", kind="ARTICLE"), retrieved_on="2026-01-01")
    old = _for_model([item], provenance=1)
    new = _for_model([item], provenance=2)
    assert "retractionStatus" not in old[0] and new[0]["retractionStatus"] == "NOT_CHECKED"


def test_upload_concurrency_rejects_before_reading_the_body():
    import asyncio

    from app.core.config import Settings
    from app.core.uploads import UploadGuard

    async def exercise():
        release, started = asyncio.Event(), asyncio.Event()
        async def application(scope, receive, send):
            started.set()
            await release.wait()
        settings = Settings(auth_mode="dev", upload_concurrency=1)
        guard = UploadGuard(application, settings)
        scope = {"type": "http", "path": "/api/projects/x/guideline", "method": "POST", "query_string": b"",
                 "headers": [(b"authorization", b"Dev student@example.com"), (b"content-type", b"multipart/form-data; boundary=x")]}
        async def unread():
            raise AssertionError("Busy request body was consumed")
        output = []
        async def send(message):
            output.append(message)
        first = asyncio.create_task(guard(dict(scope), unread, send))
        await started.wait()
        await guard(dict(scope), unread, send)
        release.set()
        await first
        assert output[0]["status"] == 429 and not guard.slots.locked()
    asyncio.run(exercise())


@pytest.mark.parametrize("printed,supplied", [("0.50", "0.5"), ("0.050", "0.05"), ("400.0", "400"), ("-0.50", "-0.5"), ("50.0%", "50%")])
def test_equivalent_decimal_spellings_retain_the_supplied_quantity(printed, supplied):
    from app.proposals import evidence

    text = f"The supplied assumption is {printed}."
    assert evidence.figure_problems(text, {}, supplied) == []
    assert evidence.strip_unsupported(text, {}, set(), supplied) == text


@pytest.mark.parametrize("printed,supplied", [("-0.50", "0.5"), ("0.50%", "0.5"), ("0.50", "50%"), ("0.70", "0.5")])
def test_numeric_matching_never_changes_sign_units_or_the_value(printed, supplied):
    from app.proposals import evidence

    text = f"The observed value is {printed}."
    assert evidence.figure_problems(text, {}, supplied)
    assert evidence.strip_unsupported(text, {}, set(), supplied) == ""


def _chapter_three_input(policy):
    from app.proposals.models import ProposalInputs, ProposalPlan, SampleSize, StepInput
    from app.proposals.rulebook import DEFAULT
    from tests.fake_models import PLAN

    plan = ProposalPlan.model_validate(PLAN)
    plan.sample_size = SampleSize(method="KREJCIE_MORGAN", population=400, population_source="Synthetic roster", margin=.05, proportion=.5, confidence=95)
    return StepInput(project_id="prj_synthetic", step="CHAPTER", chapter=3, plan_version=1, rulebook=DEFAULT,
                     inputs=ProposalInputs(topic="Synthetic research question for a controlled regression", level="MASTERS"), plan=plan, academic_policy=policy)


def test_unverified_brief_threshold_cannot_become_a_mandatory_repair_target():
    from app.proposals.pipeline import _section_items

    input_ = _chapter_three_input(3)
    unreliable = "Cronbach's alpha will be tested with a coefficient threshold of 0.70 considered acceptable."
    safe = "Content validity and internal consistency reliability will be assessed before fieldwork."
    briefs = {"quality": {"points": [safe, unreliable], "evidence": []}}
    current = next(i for i in _section_items(input_, {}, briefs) if i["key"] == "quality")
    assert current["points"] == [safe] and "reliability" in current["requirement"].lower()
    historical = next(i for i in _section_items(_chapter_three_input(2), {}, briefs) if i["key"] == "quality")
    assert historical["points"] == [safe, unreliable]


def test_calculator_values_remain_distinct_from_empirical_claims_in_review_context():
    from app.proposals.pipeline import _common, _section_items
    from app.proposals.sampling import calculate

    input_ = _chapter_three_input(3)
    point = "The calculation uses population proportion 0.50 and a 0.05 margin of error for the provisional population of 400."
    brief = {"sampling": {"points": [point], "evidence": []}}
    item = next(i for i in _section_items(input_, {}, brief) if i["key"] == "sampling")
    assert item["points"] == [point]
    context = _common(input_, calculate(input_.plan.sample_size).steps)
    assert "not observed study findings" in context["sampleCalculationBasis"] and "197" in context["sampleSize"]
    assert "sampleCalculationBasis" not in _common(_chapter_three_input(2), context["sampleSize"])
