"""Regressions for the four confirmed findings on b14b50f. No real model calls."""

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.ai.orchestration import STEPS
from app.proposals import evidence, service
from app.proposals.models import ChapterDocument, ChapterSection, EvidenceItem, EvidenceSource

RATIO = "(OR = 1.27; 95% CI: 0.56–2.89; p = 0.043)"


@pytest.mark.parametrize("sentence", [
    "If no study has examined caregivers in Mukono District, this survey would be the first to do so.",
    "Were it true that this relationship has never been studied, a scoping review would be the right first step.",
    "Is it the case that no study has examined this question?",
    f"If the authors had called this result significant {RATIO}, the claim would not survive a reading of its interval.",
    f"The abstract's description of the association as “significant” {RATIO} is contradicted by its own interval.",
    f"Okello's claim of a “statistically significant” effect {RATIO} cannot stand, because the interval includes 1.",
    f'The phrase "a significant association {RATIO}" is not supported by those figures.',
    f"The association was significant {RATIO}, but this conclusion is unsupported.",
])
def test_uncertain_claims_survive_and_reach_the_reviewer(sentence):
    assert evidence.gap_problems(sentence) == []
    assert evidence.statistic_problems(sentence) == []
    assert evidence.strip_overclaims(sentence) == sentence
    notes = evidence.for_the_reviewer([sentence])
    assert len(notes) == 1 and sentence in notes[0]


@pytest.mark.parametrize("sentence", [
    "No study has examined caregivers in Mukono District.",
    "There is no electricity in the district, and no study has examined vaccine uptake.",
    f"Education showed a significant association with uptake {RATIO}.",
    f"The study suggests a significant association between education and uptake {RATIO}.",
])
def test_plain_overclaims_are_still_blocked(sentence):
    assert evidence.gap_problems(sentence) or evidence.statistic_problems(sentence)
    assert evidence.strip_overclaims(sentence) == ""


def test_new_reviewer_prompts_do_not_grant_automatic_approval_for_attribution():
    folder = Path(__file__).parents[1] / "app" / "ai" / "prompts"
    registered = json.loads((folder / "released.json").read_text(encoding="utf-8"))
    assert STEPS["p_review"].prompt == STEPS["p_review_peer"].prompt == "p-review-v8"
    assert STEPS["w_evaluate"].prompt == "w-evaluate-v6"
    for key in ("p-review-v8", "w-evaluate-v4", "w-evaluate-v5", "w-evaluate-v6"):
        text = (folder / f"{key}.md").read_text(encoding="utf-8")
        assert "Attribution or quotation alone does not make a claim sound" in text
        assert "never automatically pass or fail" in text
        assert "it is sound and you say nothing" not in text
        assert hashlib.sha256(text.encode()).hexdigest() == registered[key]
    # Frozen engines still have the exact earlier prompt bytes available.
    for key in ("p-review-v6", "w-evaluate-v3"):
        assert hashlib.sha256((folder / f"{key}.md").read_text(encoding="utf-8").encode()).hexdigest() == registered[key]


def _library(passage):
    item = EvidenceItem(
        id="E0a1b2c", chapter=1, need="Context", statement="A supported finding", passage=passage,
        verified=True, support="SUPPORTED", retrieved_on="2026-10-12",
        source=EvidenceSource(url="https://example.org/study", title="A sufficiently long title for a study", year="2024",
                              authors=["Smith, J.", "Jones, A.", "Brown, B."]),
    )
    return {item.id: item}


FIRST = "the investigator measures the outcome and the exposures in the study participants at the same time"
SECOND = "participants are selected based on the inclusion and exclusion criteria set for the study"
PASSAGE = f"In a cross-sectional study, {FIRST}. Unlike in cohort studies, the {SECOND}."


@pytest.mark.parametrize("quotes", [None, ("“", "”"), ('"', '"'), ("‘", "’")])
def test_a_quoted_run_never_hides_another_unquoted_run(quotes):
    library = _library(PASSAGE)
    first = f"{quotes[0]}{FIRST}{quotes[1]}" if quotes else FIRST
    sentence = f"Here {first}, and {SECOND} ⟦E0a1b2c⟧."
    assert evidence.copied_problems(sentence, library)
    marked = evidence.quote_copied(sentence, library)
    assert f"“{SECOND}”" in marked
    assert (f"{quotes[0]}{FIRST}{quotes[1]}" if quotes else f"“{FIRST}”") in marked
    assert evidence.copied_problems(marked, library) == []
    assert evidence.quote_copied(marked, library) == marked


def test_quoting_covers_every_run_and_preserves_surrounding_whitespace():
    library = _library(PASSAGE)
    sentence = "Here " + "; separately, ".join([FIRST] * 6) + " ⟦E0a1b2c⟧."
    paragraph = "An introduction.\n\n" + sentence + "  A conclusion."
    marked = evidence.quote_copied(paragraph, library)
    assert marked.count(f"“{FIRST}”") == 6
    assert marked.startswith("An introduction.\n\n") and marked.endswith("  A conclusion.")
    assert evidence.copied_problems(marked, library) == []


def test_a_quotation_across_sentence_boundaries_remains_quoted():
    passage = "Caregivers live far from facilities and face substantial transport costs during routine visits. Household education influences timely vaccination decisions within the study population."
    library = _library(passage)
    paragraph = f"“{passage}” ⟦E0a1b2c⟧."
    assert evidence.copied_problems(paragraph, library) == []
    assert evidence.quote_copied(paragraph, library) == paragraph


@pytest.mark.parametrize("style", ["APA6", "APA7"])
def test_historical_citations_are_independent_of_current_earlier_chapters(monkeypatch, style):
    library = _library(PASSAGE)

    def document(number, text, cited):
        return ChapterDocument(
            number=number, title=f"Chapter {number}", plan_version=1, words=10, cited=cited,
            sections=[ChapterSection(key="background", number=f"{number}.1", heading="Background", paragraphs=[text])],
        )

    states = {n: SimpleNamespace(number=n, current=1) for n in (1, 2, 3)}
    documents = {1: document(1, "No citation here.", []), 2: document(2, "Prior work supports this ⟦E0a1b2c⟧.", ["E0a1b2c"]), 3: None}
    project = SimpleNamespace(chapter=lambda n: states[n], citation=style, plan=None)
    monkeypatch.setattr(service, "_owned", lambda rt, user, project_id: project)
    monkeypatch.setattr(service, "_chapter_doc", lambda rt, stored, version=None: documents[stored.number])
    monkeypatch.setattr(service, "_citer", lambda rt, p, scope: evidence.Citer(library, p.citation, scope))
    before = service.chapter(None, None, "test", 2, version=1)
    documents[1] = document(1, "This now cites it ⟦E0a1b2c⟧.", ["E0a1b2c"])
    after = service.chapter(None, None, "test", 2, version=1)
    assert before.sections == after.sections and before.references == after.references
    expected = "(Smith, Jones, & Brown, 2024)" if style == "APA6" else "(Smith et al., 2024)"
    assert expected in after.sections[0].paragraphs[0]
    # The current view still follows the combined proposal's citation order.
    current = service.chapter(None, None, "test", 2)
    assert "(Smith et al., 2024)" in current.sections[0].paragraphs[0]
