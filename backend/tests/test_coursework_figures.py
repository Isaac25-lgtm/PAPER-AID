"""Coursework that asks for graphs and worked numbers (2026-10-07). A live economics question ("Use graphical and
numerical illustrations") failed after 44 minutes: PaperAid could not draw, and its guard against invented
statistics emptied the worked example cell by cell. The writer now gives a graph as data that code draws, and
a worked example is an illustrative table that code labels; both reach the student, the Word file and the
final review. Also: one repair limit for the whole draft, and the loop stops when objections repeat."""

import io

import pytest
from docx import Document

from app.proposals.ai import Figure, SectionText, Table
from app.works import pipeline
from tests import fake_works
from tests.test_api import STUDENT
from tests.test_one_start import _coursework, _done, _settled

H = STUDENT
FIGURE = {"caption": "Demand for the iPhone before and after a fall in Samsung's price", "x_axis": "Quantity (thousands)", "y_axis": "Price ($)",
          "series": [{"label": "Demand before (D1)", "points": [{"x": 100, "y": 1200}, {"x": 400, "y": 600}]},
                     {"label": "Demand after (D2)", "points": [{"x": 60, "y": 1200}, {"x": 340, "y": 600}]},
                     {"label": "Supply (S)", "points": [{"x": 100, "y": 600}, {"x": 400, "y": 1200}]}]}
WORKED = {"caption": "Worked example", "illustrative": True,
          "rows": [["Case", "Price ($)", "Quantity (thousands)"], ["Before", "900", "250"], ["After", "860", "205"]]}


@pytest.fixture
def works_client(tmp_path, monkeypatch):
    monkeypatch.setenv("WORKS_ENABLED", '["CONCEPT_NOTE","COURSEWORK","FUNDING_PROPOSAL"]')
    from tests.conftest import _client

    yield from _client(tmp_path, monkeypatch, "fixed")


def test_a_figure_is_checked_by_code():
    good = Figure.model_validate(FIGURE)
    assert pipeline._figure_problems(good) == [] and pipeline._figure_problems(None) == []
    flat = good.model_copy(update={"series": [good.series[0].model_copy(update={"points": good.series[0].points[:1]})]})
    assert pipeline._figure_problems(flat)
    assert pipeline._figure_problems(good.model_copy(update={"x_axis": ""}))
    assert pipeline._figure_problems(good.model_copy(update={"series": good.series * 3}))  # more than six lines


def test_an_illustrative_worked_example_is_kept_and_a_sourced_looking_table_is_not():
    text = SectionText(key="k", paragraphs=["Suppose the price falls from 900 to 860 dollars, so quantity falls from 250 to 205 thousand."],
                       table=Table.model_validate(WORKED))
    kept = pipeline._strip(_inp(), text, {}, "")
    assert kept.table.rows == text.table.rows and kept.paragraphs == text.paragraphs
    plain = text.model_copy(update={"table": text.table.model_copy(update={"illustrative": False})})
    stripped = pipeline._strip(_inp(), plain, {}, "")
    assert stripped.table.rows[1][1] == "" and not stripped.paragraphs  # unsupported figures are still withheld


def test_a_graph_survives_a_rewrite_that_leaves_it_out():
    with_figure = SectionText(key="k", paragraphs=["x"], table=Table(caption="", rows=[]), figure=Figure.model_validate(FIGURE))
    shorter = SectionText(key="k", paragraphs=["y"], table=Table(caption="", rows=[]))
    assert pipeline._kept(with_figure, shorter).figure == with_figure.figure
    replaced = shorter.model_copy(update={"figure": Figure.model_validate({**FIGURE, "caption": "New"})})
    assert pipeline._kept(with_figure, replaced).figure.caption == "New"


def test_a_coursework_question_asking_for_graphs_and_numbers_is_answered_drawn_and_labelled(works_client):
    from app.runtime import get_runtime

    client = works_client

    def draft(payload):
        answer = fake_works.answer("w_draft", payload)
        first = answer["sections"][1] if len(answer["sections"]) > 1 else answer["sections"][0]
        first["figure"] = FIGURE
        first["table"] = WORKED
        first["paragraphs"].append("Suppose the price falls from 900 to 860 dollars, so quantity demanded falls from 250 to 205 thousand.")
        return answer

    client.models.overrides["w_draft"] = draft
    work = _coursework(client)
    assert client.post(f"/api/works/{work['id']}/start", headers=H).status_code == 200
    work = _settled(client, f"/api/works/{work['id']}", _done)
    assert work["documents"] and not work["autoFailure"], work["autoFailure"]
    view = client.get(f"/api/works/{work['id']}/document", headers=H).json()
    drawn = [s for s in view["sections"] if s.get("figure")]
    assert drawn and drawn[0]["figure"]["caption"].endswith("(illustrative values)") and len(drawn[0]["figure"]["series"]) == 3
    worked = [s for s in view["sections"] if s.get("table")]
    assert worked and worked[0]["tableCaption"].endswith("(illustrative values)") and worked[0]["table"][1] == ["Before", "900", "250"]
    word = client.get(f"/api/works/{work['id']}/export", headers=H)
    doc = Document(io.BytesIO(word.content))
    assert len(doc.inline_shapes) == 1 and any(p.text.startswith("Figure 1.") for p in doc.paragraphs)
    # The final reviewer read the graph as its data, in the section it belongs to.
    review = next(r for t, r in zip(client.models.tasks, client.models.requests, strict=True) if t == "w_final")
    assert "Figure (drawn by PaperAid from this data)" in review and "Demand after (D2)" in review
    jobs = [get_runtime().store.get(j) for j in work["jobs"]]
    assert all(j.status == "COMPLETED" for j in jobs)


def test_one_repair_limit_for_the_whole_draft_and_no_round_that_only_repeats(works_client):
    """The section checks and the final review share the draft's repairs; the same objections after a
    repair end the loop (live 2026-10-07: 12 repairs, 21 evaluations, 44 minutes)."""
    client = works_client
    calls = {"w_repair": 0, "w_final": 0}

    def final(payload):
        calls["w_final"] += 1
        return {"rules": [{"rule": r["rule"], "status": "PASS", "note": "Met.", "where": ""} for r in payload["rules"]],
                "coverage": [{"id": c["id"], "answered": False, "where": ""} for c in payload["coverage"]],
                "priorities": [{"priority": p, "addressed": True, "where": ""} for p in payload["priorities"]]}

    def repair(payload):
        calls["w_repair"] += 1
        return fake_works.repair(payload)

    client.models.overrides["w_final"] = final
    client.models.overrides["w_repair"] = repair
    work = _coursework(client)
    client.post(f"/api/works/{work['id']}/start", headers=H)
    work = _settled(client, f"/api/works/{work['id']}", _done)
    assert work["autoFailure"] and not work["documents"]
    assert calls["w_final"] == 2  # the objection repeated after one repair: no third round
    from app.runtime import get_runtime

    assert 1 <= calls["w_repair"] <= get_runtime().settings.repair_attempts + 1  # one limit for the whole draft


def _inp():
    from types import SimpleNamespace

    return SimpleNamespace()


def test_a_retry_after_a_failed_draft_reuses_its_checked_sources(works_client):
    """Codex 2026-10-07: a retry researched everything again (about 7 minutes). The same step on the same
    approved plan starts from the failed attempt's checked sources."""
    client = works_client
    objecting = {"on": True}

    def final(payload):
        return {"rules": [{"rule": r["rule"], "status": "PASS", "note": "Met.", "where": ""} for r in payload["rules"]],
                "coverage": [{"id": c["id"], "answered": not objecting["on"], "where": ""} for c in payload["coverage"]],
                "priorities": [{"priority": p, "addressed": True, "where": ""} for p in payload["priorities"]]}

    client.models.overrides["w_final"] = final
    work = _coursework(client)
    client.post(f"/api/works/{work['id']}/start", headers=H)
    work = _settled(client, f"/api/works/{work['id']}", _done)
    assert work["autoFailure"]
    searched_before = client.models.tasks.count("w_needs")
    objecting["on"] = False
    assert client.post(f"/api/works/{work['id']}/start", headers=H).status_code == 200
    work = _settled(client, f"/api/works/{work['id']}", lambda w: bool(w["documents"]) or (bool(w["autoFailure"]) and w["jobs"][-1] != w["jobs"][-2]))
    assert work["documents"], work["autoFailure"]
    assert client.models.tasks.count("w_needs") == searched_before  # no new research for the retry
