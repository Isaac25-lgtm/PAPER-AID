"""Regressions for the four remaining release-2fe13d6 findings. Synthetic inputs; no paid calls."""

from types import SimpleNamespace

import pytest

from app.datalab import pipeline as datalab
from app.datalab.report import ReportDocument, ReportSection
from app.proposals.ai import SectionText, Table
from app.works import pipeline
from tests.test_codex_20261007b import WORKED, _inp


@pytest.mark.parametrize("opener", ["For example,", "For illustration,", "To illustrate,", "In the example of Kenya,"])
def test_a_factual_example_cannot_borrow_the_tables_numbers(opener):
    text = SectionText(key="k", table=Table.model_validate(WORKED),
                       paragraphs=[f"{opener} district officials recorded 900 cases."])
    assert not pipeline._strip(_inp(), text, {}, "").paragraphs
    section = SimpleNamespace(max_words=0, min_words=0, words=0, field_id="")
    assert any("900" in p for p in pipeline._checks(_inp(), section, text, {}, "", {}))


@pytest.mark.parametrize("opener", ["Suppose", "Assume", "Imagine", "Hypothetically,", "In this example,", "In the worked example,"])
def test_a_clearly_hypothetical_example_can_explain_its_numbers(opener):
    text = SectionText(key="k", table=Table.model_validate(WORKED), paragraphs=[f"{opener} the price falls from 900 to 860 dollars."])
    assert pipeline._strip(_inp(), text, {}, "").paragraphs == text.paragraphs
    assert not pipeline._strip(_inp("FUNDING_PROPOSAL"), text, {}, "").paragraphs


@pytest.mark.parametrize("instruction", [
    "Remove the last paragraph but keep the graph",
    "Remove the second sentence; the graph stays",
    "Delete the table, not the graph",
    "Do not remove the graph; shorten the conclusion",
    "Don't delete the chart",
    "The diagram must not be removed",
    "Do not write this section without a chart",
    "Remove the graph's caption",
    "Remove the graph caption",
])
def test_removing_other_content_or_preserving_a_graph_never_removes_it(instruction):
    assert not pipeline._remove_figure_requested([instruction])


@pytest.mark.parametrize("instruction", ["Remove the graph", "Delete the existing chart", "Write it without a chart", "The diagram should be removed"])
def test_explicit_graph_removal_still_works(instruction):
    assert pipeline._remove_figure_requested([instruction])


def test_preservation_wins_across_multiple_instructions():
    assert not pipeline._remove_figure_requested(["Remove the graph", "Keep the graph"])


@pytest.mark.parametrize("mode", ["REPORT", "CHAPTER_FOUR"])
def test_a_long_datalab_review_fits_without_growing_its_manifest(monkeypatch, mode):
    monkeypatch.setattr(datalab, "FINAL_PART_WORDS", 900)
    monkeypatch.setattr(datalab, "_dataset", lambda inp: {"records": 100})
    body = " ".join(f"word{i}" for i in range(12000))
    appendix = " ".join(f"appendix{i}" for i in range(300))
    document = ReportDocument(title="Synthetic report", subtitle="Results", sections=[
        ReportSection(key="results", heading="Results", paragraphs=[body]),
    ], appendices=[ReportSection(key="appendix", heading="Appendix", paragraphs=[appendix])])
    inp = SimpleNamespace(mode=mode, alpha=0.05, objectives=["Assess the outcome"],
                          chapter_three=[SimpleNamespace(model_dump=lambda: {"methods": "method " * 80})])
    sent = []

    def review(payload):
        datalab.check_review_size(payload)
        sent.append(payload)
        return datalab.Review(verdict="PASS", rules=[datalab.RuleVerdict(rule=r, status="PASS", note="Checked") for r in payload["rules"]], issues=[])

    answer = datalab._review(SimpleNamespace(final_review=review), inp, document,
                            [{"record": "context " * 280}], [], set())
    assert answer is not None and answer.verdict == "PASS"
    assert len(sent) > 10 and all(datalab._words(p) <= 900 for p in sent)
    assert all(len(p["manifest"]) == 2 for p in sent)
    for payload in sent:
        assert {m["key"] for m in payload["manifest"]} == {"results", "appendix"}
    # Every word of the reviewed document survives splitting, in order and exactly once.
    restored = {"results": [], "appendix": []}
    for payload in sent:
        for section in payload["document"]["sections"]:
            restored[section["key"]].extend(p["text"] for p in section["paragraphs"])
    assert " ".join(restored["results"]) == body
    assert " ".join(restored["appendix"]) == appendix
    assert "-" in sent[0]["manifest"][0]["part"]


def test_an_unfit_repeated_context_is_refused_before_review(monkeypatch):
    monkeypatch.setattr(datalab, "FINAL_PART_WORDS", 900)
    with pytest.raises(datalab.PermanentStageError):
        datalab.bounded_parts([], {"context": "word " * 950})
