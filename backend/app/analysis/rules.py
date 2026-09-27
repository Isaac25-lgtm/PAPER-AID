"""The writing-signal rules (signals-v2), in one versioned place.

Each rule measures something ordinary code can count. A rule hit is never proof of AI use: it is
evidence for GPT-6 Sol's review, which confirms or rejects it in context (owner decision
2026-09-27: signals guide review, they are not the target). Thresholds are provisional until
calibrated on a held-out set of genuinely human writing.

`scope` says where a rule is measured: in one passage, or across the document. `finding` says whether a hit
becomes a finding for the student; information-only rules are shown to Sol and never scored.
A hit's severity (minor, moderate, major) sets how much it counts.
"""

from dataclasses import dataclass
from typing import Literal

from app.jobs.models import ReasonCode

RULESET_VERSION = "signals-v2"


@dataclass(frozen=True)
class Rule:
    id: str
    reason: ReasonCode
    scope: Literal["passage", "document"]
    measures: str  # what the number means, as shown to the lead model
    threshold: float
    finding: bool  # False: information for the lead model only, never scored or shown as a finding
    explanation: str  # for the student
    suggestion: str


RULES: dict[str, Rule] = {
    r.id: r
    for r in [
        Rule(
            "GEN_STOCK_PHRASE", "GENERIC_PHRASING", "passage", "stock academic phrases found in the passage", 1, True,
            "Stock phrases like this appear in thousands of papers and say little about your study.",
            "Replace it with something only your paper can say: a finding, a figure or a specific example.",
        ),
        Rule(
            "GEN_IMPORTANCE", "GENERIC_PHRASING", "passage", "claims of importance without saying why (crucial/vital/essential role…)", 2, True,
            "The passage says several times that something matters without showing why.",
            "Say what the effect or consequence is, using what your paper already shows.",
        ),
        Rule(
            "TRANS_STACKED", "FORMULAIC_TRANSITIONS", "passage", "sentences opening with an additive connective (furthermore, moreover…)", 2, True,
            "Several sentences start with an additive transition, which makes the paragraph read like a list.",
            "Connect ideas by their logic (cause, contrast or consequence) rather than stacking 'also' words.",
        ),
        Rule(
            "TRANS_PARA_OPENER", "FORMULAIC_TRANSITIONS", "document", "paragraphs opening with the same connective", 3, True,
            "Many paragraphs open with the same connective, which reads as a template.",
            "Open each paragraph with its own point rather than a stock connective.",
        ),
        Rule(
            "TRANS_DENSITY", "FORMULAIC_TRANSITIONS", "document", "sentence-opening connectives per 1,000 words", 10, False,
            "", "",
        ),
        Rule(
            "RHYTHM_UNIFORM", "UNIFORM_STRUCTURE", "passage", "variation in sentence length (standard deviation ÷ mean)", 0.22, True,
            "The sentences in this paragraph are very similar in length and shape, which reads as mechanical.",
            "Vary sentence length and structure; lead with your strongest point.",
        ),
        Rule(
            "OPENINGS_REPEATED", "UNIFORM_STRUCTURE", "passage", "sentences starting with the same two words", 3, True,
            "Several sentences start the same way.",
            "Vary how sentences begin so each one leads with what is new in it.",
        ),
        Rule(
            "PARA_RHYTHM", "UNIFORM_STRUCTURE", "document", "variation in paragraph length within a section (standard deviation ÷ mean)", 0.12, False,
            "", "",
        ),
        Rule(
            "HEDGE_STACKED", "OVER_HEDGING", "passage", "hedges in a single sentence (may, might, possibly…)", 3, True,
            "Several hedges in one sentence make your point hard to find.",
            "State what your evidence shows, then give one clear limitation.",
        ),
        Rule(
            "VAGUE_ATTRIBUTION", "LOW_SPECIFICITY", "passage", "claims attributed to unnamed studies or experts, with no citation", 1, True,
            "The claim refers to studies or experts without naming them.",
            "Name the studies and give their key figures, with a citation.",
        ),
        Rule(
            "SPECIFICITY_LOW", "LOW_SPECIFICITY", "passage", "specific details per 100 words (numbers, citations, names, dates)", 0.4, True,
            "This passage stays general: it has no figures, names, dates or citations.",
            "Anchor it in your own material: a result, a setting or a source you already use.",
        ),
        Rule(
            "SUMMARY_UNSUPPORTED", "UNSUPPORTED_SUMMARY", "passage", "summary openers with no citation, figure or finding", 1, True,
            "This summary is not tied to specific findings from your paper.",
            "Summarise your main findings and what they mean for your setting.",
        ),
        Rule(
            "NGRAM_REPEATED", "REPETITION", "document", "five-word phrases (not just the paper's topic terms) repeated across different paragraphs", 3, True,
            "This wording repeats phrasing used elsewhere in your paper.",
            "Say it once where it matters most, and refer back to it more briefly elsewhere.",
        ),
        Rule(
            "VOCAB_NARROW", "REPETITION", "passage", "vocabulary variety (moving-average type/token ratio, 40-word window)", 0.62, True,
            "The passage repeats the same words closely together.",
            "Vary the wording where it doesn't change a technical term.",
        ),
        Rule(
            "STYLE_SHIFT", "STYLE_SHIFT", "document", "change in sentence length and vocabulary between neighbouring sections", 1.6, True,
            "The writing style changes noticeably from the previous section.",
            "Read the two sections together and make the voice consistent.",
        ),
        Rule(
            "SPELLING_MIXED", "STYLE_SHIFT", "document", "British and American spellings both used", 1, False,
            "", "",
        ),
        Rule(
            "PUNCTUATION_PROFILE", "UNIFORM_STRUCTURE", "document", "em dashes, semicolons and colons per 1,000 words (information only)", 0, False,
            "", "",
        ),
    ]
}

SEVERITY_WEIGHT = {"minor": 0.35, "moderate": 0.65, "major": 1.0}

# How a signal is read in each kind of section. Interpretation, never exemption: no factor is
# below 0.5, so a methods paragraph can still be flagged, just on stronger evidence.
SECTION_FACTOR: dict[str, dict[str, float]] = {
    "methods": {"UNIFORM_STRUCTURE": 0.5, "REPETITION": 0.5, "LOW_SPECIFICITY": 0.6, "OVER_HEDGING": 0.7},
    "results": {"UNIFORM_STRUCTURE": 0.5, "REPETITION": 0.5},
    "abstract": {"UNSUPPORTED_SUMMARY": 0.5, "LOW_SPECIFICITY": 0.7},
    "literature": {"LOW_SPECIFICITY": 1.0},
}
