"""Deterministic writing-pattern signals and the versioned AI-likeness aggregation.

This is the part of the estimate that needs no model: formulaic phrasing, stacked transitions,
hedging, vague claims, unsupported summaries and uniform sentence rhythm. When a model is
configured it adds its own per-block judgement, but the displayed band is always computed
here, from block-level results, so it is reproducible.
"""

import re
import statistics
from dataclasses import dataclass, field

from app.documents.model import PROSE_KINDS, Block, DocumentModel
from app.jobs.models import AnalysisResult, Finding

ALGORITHM_VERSION = "signals-v1"
MIN_BLOCK_WORDS = 25

FORMULAIC = [
    "it is important to note", "it is worth noting", "plays a crucial role", "plays a vital role", "plays a significant role",
    "plays a key role", "in today's fast-paced world", "in today's digital age", "in today's world", "in today's society",
    "in the modern era", "has become an integral part", "a significant part of", "delve into", "delves into", "tapestry",
    "in the realm of", "a testament to", "navigate the complexities", "shed light on", "sheds light on", "pave the way",
    "a myriad of", "multifaceted", "holistic approach", "ever-evolving", "cannot be overstated", "underscores the importance",
    "highlights the significance", "it goes without saying", "at the end of the day", "last but not least",
    "further research is needed in this area", "this essay will", "in this day and age",
]
ADDITIVE = re.compile(r"^(furthermore|moreover|additionally|in addition|also|besides)\b", re.I)
HEDGES = re.compile(r"\b(could|may|might|possibly|perhaps|arguably|somewhat|to some extent|tend to|tends to|seem to|seems to|it could be argued)\b", re.I)
VAGUE = re.compile(r"\b(studies have shown|research has shown|research shows|many researchers|several studies|many studies|it is widely believed|experts agree|scholars argue|it has been argued)\b", re.I)
SUMMARY_OPENER = re.compile(r"^(in conclusion|to conclude|in summary|to sum up|overall)\b", re.I)
HAS_CITATION = re.compile(r"⟦[XP]\d+⟧|\([^()]*\b(19|20)\d{2}\b[^()]*\)|\[\d+\]")
SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z⟦\"“(])")

EXPLAIN = {
    "GENERIC_PHRASING": (
        "Stock phrases like this appear in thousands of papers and say little about your study.",
        "Replace it with something only your paper can say — a finding, a figure or a specific example.",
    ),
    "FORMULAIC_TRANSITIONS": (
        "Several sentences in a row start with an additive transition, which makes the paragraph read like a list.",
        "Connect ideas by their logic — cause, contrast or consequence — rather than stacking 'also' words.",
    ),
    "OVER_HEDGING": (
        "Several hedges in one sentence make your point hard to find.",
        "State what your evidence shows, then give one clear limitation.",
    ),
    "LOW_SPECIFICITY": (
        "The claim refers to studies or experts without naming them.",
        "Name the studies and give their key figures, with a citation.",
    ),
    "UNSUPPORTED_SUMMARY": (
        "This summary is not tied to specific findings from your paper.",
        "Summarise your main findings and what they mean for your setting.",
    ),
    "UNIFORM_STRUCTURE": (
        "The sentences in this paragraph are very similar in length and shape, which reads as mechanical.",
        "Vary sentence length and structure; lead with your strongest point.",
    ),
}
SEVERITY_WEIGHT = {"minor": 0.35, "moderate": 0.65, "major": 1.0}


@dataclass
class BlockSignals:
    block: Block
    score: float = 0.0
    findings: list[Finding] = field(default_factory=list)


def sentences(text: str) -> list[str]:
    return [s.strip() for s in SENTENCE_SPLIT.split(text) if s.strip()]


def _excerpt(text: str, limit: int = 280) -> str:
    text = re.sub(r"⟦[XP]\d+⟧", "…", text).strip()
    return text if len(text) <= limit else text[: limit - 1].rsplit(" ", 1)[0] + "…"


def analysable(model: DocumentModel) -> list[Block]:
    return [b for b in model.blocks if b.kind in PROSE_KINDS and b.words >= MIN_BLOCK_WORDS]


def block_signals(block: Block) -> BlockSignals:
    text = block.masked or block.text
    lowered = text.lower().replace("’", "'")
    sents = sentences(text)
    result = BlockSignals(block)
    raw = []

    def add(reason: str, severity: str, excerpt: str) -> None:
        explanation, suggestion = EXPLAIN[reason]
        n = len(result.findings) + 1
        result.findings.append(
            Finding(
                id=f"{block.id}-{n}",
                block_id=block.id,
                section=block.section or "Body",
                reason=reason,  # type: ignore[arg-type]
                severity=severity,  # type: ignore[arg-type]
                excerpt=_excerpt(excerpt),
                explanation=explanation,
                suggestion=suggestion,
            )
        )
        raw.append(SEVERITY_WEIGHT[severity])

    phrase_hits = [p for p in FORMULAIC if p in lowered]
    if phrase_hits:
        hit_sentence = next((s for s in sents if any(p in s.lower().replace("’", "'") for p in phrase_hits)), text)
        add("GENERIC_PHRASING", "major" if len(phrase_hits) >= 2 else "moderate", hit_sentence)

    additive = [s for s in sents if ADDITIVE.match(s)]
    if len(additive) >= 2 or re.search(r"\bhowever, it can also\b", lowered):
        add("FORMULAIC_TRANSITIONS", "moderate" if len(additive) >= 3 else "minor", " … ".join(additive[:3]) or text)

    for s in sents:
        if len(HEDGES.findall(s)) >= 3:
            add("OVER_HEDGING", "moderate", s)
            break

    for s in sents:
        if VAGUE.search(s) and not HAS_CITATION.search(s):
            add("LOW_SPECIFICITY", "moderate", s)
            break

    if sents and SUMMARY_OPENER.match(sents[0]) and (phrase_hits or not HAS_CITATION.search(text)):
        add("UNSUPPORTED_SUMMARY", "major" if phrase_hits else "minor", sents[0])

    lengths = [len(s.split()) for s in sents]
    if len(lengths) >= 4 and statistics.mean(lengths) > 8:
        variation = statistics.pstdev(lengths) / statistics.mean(lengths)
        if variation < 0.22:
            add("UNIFORM_STRUCTURE", "minor", sents[0])

    result.score = min(1.0, sum(raw) / 2.2)
    return result


def band_for(score: float) -> str:
    return "LOW" if score < 0.15 else "MODERATE" if score < 0.32 else "HIGH"


def aggregate(signals: list[BlockSignals], excluded_words: int, method: str, model_scores: dict[str, float] | None = None) -> AnalysisResult:
    """Word-weighted mean of block scores → band. Model scores, when present, are blended 50/50."""
    total_words = sum(s.block.words for s in signals)
    if total_words == 0:
        score = 0.0
    else:
        def combined(s: BlockSignals) -> float:
            if model_scores and s.block.id in model_scores:
                return 0.5 * s.score + 0.5 * model_scores[s.block.id]
            return s.score

        score = sum(combined(s) * s.block.words for s in signals) / total_words
    findings = sorted((f for s in signals for f in s.findings), key=lambda f: (f.block_id, -SEVERITY_WEIGHT[f.severity]))
    # Without a validated calibration set, confidence never goes above MEDIUM.
    confidence = "LOW" if total_words < 600 else "MEDIUM"
    return AnalysisResult(
        band=band_for(score),  # type: ignore[arg-type]
        confidence=confidence,  # type: ignore[arg-type]
        analysed_words=total_words,
        excluded_words=excluded_words,
        findings=findings[:60],
        algorithm_version=ALGORITHM_VERSION,
        method=method,
    )


def analyse(model: DocumentModel, method: str = "PaperAid writing-pattern signals") -> tuple[AnalysisResult, list[BlockSignals]]:
    blocks = analysable(model)
    excluded = model.word_count - sum(b.words for b in blocks)
    signals = [block_signals(b) for b in blocks]
    return aggregate(signals, excluded, method), signals
