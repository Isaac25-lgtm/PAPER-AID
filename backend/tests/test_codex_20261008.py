"""Regressions for the four remaining release-2fe13d6 findings. Synthetic inputs; no paid calls."""

from types import SimpleNamespace

import pytest

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




