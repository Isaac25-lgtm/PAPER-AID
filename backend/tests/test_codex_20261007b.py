# ruff: noqa: F811
"""Codex's second review of 2026-10-07 (code at 6eaa1ee) and its fixes: one regression per finding, each
reproducing the original case. No paid model calls."""

from types import SimpleNamespace

import httpx
import pytest

from app.ai import orchestration, vertex
from app.analysis import fetch
from app.core.errors import PermanentStageError, RetryableStageError
from app.jobs import pipeline as jobs_pipeline
from app.jobs.models import JobStatus, Stage
from app.proposals.ai import Figure, SectionText, Table
from app.works import pipeline
from app.works.ai import Final, FinalRule
from tests.test_api import STUDENT, start_job, wait

WORKED = {"caption": "Worked example", "illustrative": True,
          "rows": [["Case", "Price ($)", "Quantity"], ["Before", "900", "250"], ["After", "860", "205"]]}
FIGURE = {"caption": "Demand", "x_axis": "Quantity", "y_axis": "Price",
          "series": [{"label": "D1", "points": [{"x": 100, "y": 1200}, {"x": 400, "y": 600}]},
                     {"label": "D2", "points": [{"x": 60, "y": 1200}, {"x": 340, "y": 600}]}]}


def _inp(kind="COURSEWORK"):
    return SimpleNamespace(spec=SimpleNamespace(kind=kind, source_policy="OPEN", fields=[]))


# --- 1. a worked example's numbers never support a factual claim ------------------------------------------


def test_an_examples_numbers_support_only_its_cells_and_sentences_framed_as_hypothetical():
    text = SectionText(key="k", table=Table.model_validate(WORKED), paragraphs=[
        "Suppose the price falls from 900 to 860 dollars. District officials recorded 900 cases, as shown in the table. "
        "If officials recorded 900 cases, that matters. In this example, quantity falls from 250 to 205."])
    kept = pipeline._strip(_inp(), text, {}, "")
    assert kept.paragraphs == ["Suppose the price falls from 900 to 860 dollars. In this example, quantity falls from 250 to 205."]
    assert kept.table.rows == WORKED["rows"]
    section = SimpleNamespace(max_words=0, min_words=0, words=0, field_id="")
    assert [p for p in pipeline._checks(_inp(), section, text, {}, "", {}) if "900" in p]  # the table and "if" sentences
    framed = text.model_copy(update={"paragraphs": [kept.paragraphs[0]]})
    assert not [p for p in pipeline._checks(_inp(), section, framed, {}, "", {}) if "900" in p or "250" in p]
    assert not pipeline._strip(_inp("FUNDING_PROPOSAL"), text, {}, "").paragraphs  # never outside coursework


def test_the_figure_meaning_a_number_is_not_a_missing_exhibit():
    section = SimpleNamespace(max_words=0, min_words=0, words=0, field_id="")
    plain = SectionText(key="k", table=Table(caption="", rows=[]), paragraphs=["The figure reported by the ministry is cited above."])
    assert not [p for p in pipeline._checks(_inp(), section, plain, {}, "", {}) if "refers to a figure" in p]
    missing = plain.model_copy(update={"paragraphs": ["Figure 1 shows the shift in demand."]})
    assert [p for p in pipeline._checks(_inp(), section, missing, {}, "", {}) if "refers to a figure" in p]


# --- 2. an expired worker can never change its replacement's job -------------------------------------------


def test_a_stale_attempt_can_neither_write_fail_nor_finish_its_replacements_stage(client):
    from app.runtime import get_runtime

    rt = get_runtime()
    job_id, _ = start_job(client, selection={"writing": "NONE", "formatting": "FORMAT"})
    rt.store.update(job_id, lambda j: j.model_copy(update={"status": JobStatus.PROCESSING, "stage": Stage.FORMATTING, "lease_owner": "attempt-b"}))
    current = rt.store.get(job_id)
    stale = jobs_pipeline.StageContext(rt, current.model_copy(update={"lease_owner": "attempt-a"}))
    with pytest.raises(jobs_pipeline.StageContinues):
        stale.put_json("document.json", {"stale": True})
    jobs_pipeline._handle_failure(rt, job_id, Stage.FORMATTING, "attempt-a", "INTERNAL", "x", "stale", False)
    jobs_pipeline._finish(rt, job_id, "attempt-a")
    after = rt.store.get(job_id)
    assert after.status == JobStatus.PROCESSING and after.lease_owner == "attempt-b" and after.failure is None
    assert "document.json" not in after.artifact_paths
    owner = jobs_pipeline.StageContext(rt, after)
    owner.put_json("document.json", {"current": True})
    path = rt.store.get(job_id).artifact_paths["document.json"]
    assert "/attempts/attempt-b/" in path and owner.get_json("document.json") == {"current": True}


def test_a_finished_jobs_workspace_reads_the_attempts_own_artifacts(client):
    """The workspace read internal files by their shared path: after attempt-scoped artifacts it would have
    shown every new result as the uploaded paper without its changes."""
    from app.jobs import workspace
    from app.runtime import get_runtime

    rt = get_runtime()
    job_id, quote = start_job(client)
    client.post(f"/api/jobs/{job_id}/submit", headers=STUDENT, json={"quoteId": quote["id"]})
    job = wait(client, job_id, timeout=120)
    assert job["status"] == "COMPLETED", job
    stored = rt.store.get(job_id)
    assert any("/attempts/" in p for p in stored.artifact_paths.values())
    assert workspace._internal(rt, stored, "document.json") is not None
    doc = client.get(f"/api/jobs/{job_id}/document", headers=STUDENT).json()
    assert doc["changes"], "the refined changes come from the attempt's own artifact"


# --- 3. no small count escapes through details or subtraction -----------------------------------------------






# --- 4. no final-review request above the bound, ever ---------------------------------------------------


def test_a_final_review_request_over_the_bound_is_never_sent():
    from tests.test_vertex import SCHEMA, Answer, flat, runner

    ai, records = runner(flat())
    huge = {"part": "1 of 1", "document": {"sections": [{"text": ["word " * (orchestration.FINAL_PART_WORDS + 10)]}]}}
    with pytest.raises(PermanentStageError, match="REVIEW_REQUEST_TOO_LARGE"):
        ai._call("w_final", huge, SCHEMA, Answer)
    assert records == []


# --- 5. different places are different places ---------------------------------------------------------------


def test_the_same_objection_in_another_section_is_not_a_repeat():
    rules = [{"id": "CW-008", "severity": "BLOCKING"}]

    def review(where):
        return pipeline._blocking(Final(rules=[FinalRule(rule="CW-008", status="FAIL", note="Missing evidence.", where=where)], coverage=[], priorities=[]), rules)

    assert not pipeline._repeats(review("s2"), review("s1"))
    assert not pipeline._repeats(review("Section 1.2"), review("Section 1.1"))
    assert pipeline._repeats(review("Section 1.1"), review("Section 1.1"))


# --- 7. slow sources and slow retries end on time -------------------------------------------------------------


def test_a_page_that_drips_its_answer_is_abandoned_at_the_total_deadline(monkeypatch):
    clock = [0.0]
    monkeypatch.setattr(fetch.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(fetch, "_pinned", lambda url: (url, {}, {}))

    class Slow:
        status_code, is_redirect, headers = 200, False, {"content-type": "text/html"}

        def iter_bytes(self):
            while True:
                clock[0] += 5  # five seconds a chunk: each read in time, the whole never
                yield b"x"

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr(httpx.Client, "stream", lambda self, *a, **k: Slow())
    assert fetch._fetch("https://slow.example/page") is None
    assert clock[0] <= fetch.TOTAL_SEC + 5


def test_throttled_retries_stop_at_their_window(monkeypatch):
    from google.genai import errors

    from tests.test_vertex import MODEL, SCHEMA, settings

    clock = [0.0]
    calls = []

    def generate(**kw):
        calls.append(kw["config"].http_options.timeout)
        clock[0] += 70  # each 503 came after a long wait
        raise errors.APIError(503, {})

    monkeypatch.setattr(vertex.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(vertex, "_vertex_client", lambda *a: SimpleNamespace(models=SimpleNamespace(generate_content=generate)))
    monkeypatch.setattr(vertex, "_pause", lambda s: clock.__setitem__(0, clock[0] + s))
    with pytest.raises(RetryableStageError):
        vertex.VertexGeminiProvider(settings()).json("plan", MODEL, "s", {}, SCHEMA, 1000)
    assert len(calls) < vertex.THROTTLE_ATTEMPTS and calls[-1] < calls[0]  # later attempts get only what is left


# --- 9. a graph is removed only when the student asks ---------------------------------------------------------


def test_a_graph_is_removed_only_on_an_explicit_request():
    assert pipeline._remove_figure_requested(["Please remove the graph from this section."])
    assert pipeline._remove_figure_requested(["Write it without a chart."])
    assert not pipeline._remove_figure_requested(["Keep the graph and do not remove it; shorten the text."])
    assert not pipeline._remove_figure_requested(["Make the conclusion stronger."])
    old = SectionText(key="k", paragraphs=["x"], table=Table(caption="", rows=[]), figure=Figure.model_validate(FIGURE))
    new = SectionText(key="k", paragraphs=["y"], table=Table(caption="", rows=[]))
    assert pipeline._kept(old, new).figure is not None and pipeline._kept(old, new, remove_figure=True).figure is None


# --- 10. a large export is safe to open in a spreadsheet ------------------------------------------------------




# --- 11. legends never repeat a limit -----------------------------------------------------------------------


