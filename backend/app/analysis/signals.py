"""Deterministic writing-pattern signals and the versioned AI-likeness aggregation (signals-v2).

Code measures; GPT-6 Sol judges. Each passage is measured (sentence rhythm, openings,
transitions, hedging, specificity, vocabulary variety), then the document as a whole (repeated
phrasing across paragraphs, paragraph openers, transition density, paragraph rhythm, style shifts
between sections, punctuation). The rules and thresholds live in `app/analysis/rules.py`.

The hits go to Sol as a compact evidence bundle; Sol confirms or rejects each one in context.
Everything here is deterministic (no set or hash ordering reaches the output): the estimate and
the job must send the lead identical requests, so the job replays the estimate's paid answers.
The displayed band is computed here from passage-level results (blended with Sol's per-passage
judgement when it is available), so it is reproducible. No hit is proof of AI use.
"""

import re
import statistics
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from app.analysis.rules import RULES, RULESET_VERSION, SECTION_FACTOR, SEVERITY_WEIGHT
from app.documents.model import PROSE_KINDS, Block, DocumentModel
from app.jobs.models import AnalysisResult, Finding

ALGORITHM_VERSION = RULESET_VERSION
MIN_BLOCK_WORDS = 25

STOCK_PHRASES = [
    "it is important to note", "it is worth noting", "plays a crucial role", "plays a vital role", "plays a significant role",
    "plays a key role", "plays a pivotal role", "in today's fast-paced world", "in today's digital age", "in today's world",
    "in today's society", "in the modern era", "has become an integral part", "a significant part of", "delve into", "delves into",
    "tapestry", "in the realm of", "a testament to", "navigate the complexities", "shed light on", "sheds light on", "pave the way",
    "a myriad of", "multifaceted", "holistic approach", "ever-evolving", "cannot be overstated", "underscores the importance",
    "highlights the significance", "it goes without saying", "at the end of the day", "last but not least",
    "further research is needed in this area", "this essay will", "in this day and age",
]
IMPORTANCE = re.compile(
    r"\b(?:plays? an? (?:crucial|vital|key|significant|pivotal|important|critical) role|is (?:crucial|vital|essential|paramount|critical|pivotal)"
    r"|of (?:paramount|utmost|great|critical) importance|cannot be overstated)\b",
    re.I,
)
ADDITIVE = re.compile(r"^(?:furthermore|moreover|additionally|in addition|also|besides|what is more)\b", re.I)
CONNECTIVE = re.compile(
    r"^(furthermore|moreover|additionally|in addition|also|besides|however|therefore|thus|hence|consequently|as a result|overall"
    r"|notably|importantly|ultimately|similarly|likewise|nevertheless|nonetheless|indeed|in contrast|on the other hand"
    r"|in conclusion|to conclude|in summary)\b",
    re.I,
)
HEDGES = re.compile(r"\b(could|may|might|possibly|perhaps|arguably|somewhat|to some extent|tend to|tends to|seem to|seems to|it could be argued)\b", re.I)
VAGUE = re.compile(
    r"\b(studies have shown|research has shown|research shows|many researchers|several studies|many studies|it is widely believed"
    r"|experts agree|scholars argue|it has been argued)\b",
    re.I,
)
SUMMARY_OPENER = re.compile(r"^(in conclusion|to conclude|in summary|to sum up|overall)\b", re.I)
HAS_CITATION = re.compile(r"⟦[XP]\d+⟧|\([^()]*\b(19|20)\d{2}\b[^()]*\)|\[\d+\]")
SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z⟦\"“(])")
TOKENS = re.compile(r"⟦[XP]\d+⟧")
WORD = re.compile(r"[A-Za-z][A-Za-z'’-]*")
NUMBER = re.compile(r"\d")
MONTHS = re.compile(r"\b(January|February|March|April|May|June|July|August|September|October|November|December)\b")
STOPWORDS = frozenset(
    "a an the and or but if of to in on at by for with from as is are was were be been being this that these those it its their "
    "they them we our us i my you your he she his her which who whom whose what when where why how not no than then there here "
    "also can could may might will would should must do does did has have had into over under about between through during "
    "such more most other some any each all both either neither very much many few one two three so because while".split()
)

# Section types by heading. Order matters: the first match wins ("Discussion of findings" is discussion).
SECTION_TYPES = [
    ("abstract", re.compile(r"\babstract\b|\bexecutive summary\b", re.I)),
    ("methods", re.compile(r"\bmethod|\bmaterials\b|\bresearch design\b|\bstudy design\b|\bsampling\b|\bdata collection\b|\bparticipants\b|\bprocedure", re.I)),
    ("discussion", re.compile(r"\bdiscussion\b", re.I)),
    ("conclusion", re.compile(r"\bconclu|\brecommendation|\bimplications\b|\bsummary\b", re.I)),
    ("results", re.compile(r"\bresults?\b|\bfindings\b|\banalysis\b", re.I)),
    ("literature", re.compile(r"\bliterature\b|\btheoretical\b|\bconceptual framework\b|\brelated work\b", re.I)),
    ("introduction", re.compile(r"\bintroduction\b|\bbackground\b|\bproblem\b|\bobjectives?\b|\bresearch questions?\b", re.I)),
]


def section_type(section: str) -> str:
    return next((kind for kind, pattern in SECTION_TYPES if pattern.search(section or "")), "body")


@dataclass
class Hit:
    rule: str
    severity: str  # minor | moderate | major
    value: float
    excerpt: str


@dataclass
class BlockSignals:
    block: Block
    kind: str  # section type
    hits: list[Hit] = field(default_factory=list)
    score: float = 0.0
    findings: list[Finding] = field(default_factory=list)

    def rescore(self) -> None:
        """Findings and score from the hits: one finding per reason (its strongest hit), each
        weighted by severity and by how that reason is read in this kind of section."""
        strongest: dict[str, Hit] = {}
        for hit in self.hits:
            rule = RULES[hit.rule]
            if not rule.finding:
                continue
            best = strongest.get(rule.reason)
            if best is None or SEVERITY_WEIGHT[hit.severity] > SEVERITY_WEIGHT[best.severity]:
                strongest[rule.reason] = hit
        self.findings = []
        total = 0.0
        for n, (reason, hit) in enumerate(strongest.items(), start=1):
            rule = RULES[hit.rule]
            total += SEVERITY_WEIGHT[hit.severity] * SECTION_FACTOR.get(self.kind, {}).get(reason, 1.0)
            self.findings.append(
                Finding(
                    id=f"{self.block.id}-{n}",
                    block_id=self.block.id,
                    section=self.block.section or "Body",
                    reason=reason,  # type: ignore[arg-type]
                    severity=hit.severity,  # type: ignore[arg-type]
                    excerpt=_excerpt(hit.excerpt),
                    explanation=rule.explanation,
                    suggestion=rule.suggestion,
                )
            )
        self.score = min(1.0, total / 2.2)

    def evidence(self) -> list[dict[str, Any]]:
        """This passage's hits as the lead model sees them."""
        return [
            {"rule": h.rule, "measures": RULES[h.rule].measures, "value": round(h.value, 2), "threshold": RULES[h.rule].threshold, "severity": h.severity}
            for h in self.hits
        ]


@dataclass
class DocSignal:
    """A document-level measurement: shown to the lead model, never a verdict on its own."""

    rule: str
    value: float
    passages: list[str] = field(default_factory=list)
    note: str = ""


@dataclass
class Scan:
    blocks: list[BlockSignals]
    document: list[DocSignal]
    excluded_words: int
    sections: list[dict[str, Any]]

    def evidence(self) -> dict[str, Any]:
        """The compact evidence bundle for the lead model: the document's shape and its
        document-level signals. Passage-level hits travel with each passage."""
        return {
            "rulesetVersion": RULESET_VERSION,
            "sections": self.sections,
            "documentSignals": [
                {"rule": d.rule, "measures": RULES[d.rule].measures, "value": round(d.value, 2), "threshold": RULES[d.rule].threshold, "passages": d.passages[:12], "note": d.note}
                for d in self.document
            ],
        }


# --- measurements ---------------------------------------------------------------------------


def sentences(text: str) -> list[str]:
    return [s.strip() for s in SENTENCE_SPLIT.split(text) if s.strip()]


def words_of(text: str) -> list[str]:
    return [w.lower().replace("’", "'") for w in WORD.findall(TOKENS.sub(" ", text))]


def mattr(words: list[str], window: int = 40) -> float:
    """Moving-average type/token ratio: vocabulary variety that does not depend on length."""
    if not words:
        return 1.0
    if len(words) <= window:
        return len(set(words)) / len(words)
    counts = Counter(words[:window])
    ratios = [len(counts) / window]
    for i in range(window, len(words)):
        counts[words[i]] += 1
        old = words[i - window]
        counts[old] -= 1
        if counts[old] == 0:
            del counts[old]
        ratios.append(len(counts) / window)
    return sum(ratios) / len(ratios)


def specifics_per_100(text: str) -> float:
    """Numbers, citations and other locked items, dates and proper names per 100 words."""
    visible = TOKENS.sub(" ", text)
    words = WORD.findall(visible)
    if not words:
        return 0.0
    count = len(TOKENS.findall(text)) + len(re.findall(r"\d+(?:[.,]\d+)?", visible)) + len(MONTHS.findall(visible))
    for sentence in sentences(visible):
        for word in WORD.findall(sentence)[1:]:  # a capital at the start of a sentence says nothing
            if word[0].isupper() and word.lower() not in STOPWORDS:
                count += 1
    return 100 * count / len(words)


def _excerpt(text: str, limit: int = 280) -> str:
    text = TOKENS.sub("…", text).strip()
    return text if len(text) <= limit else text[: limit - 1].rsplit(" ", 1)[0] + "…"


def analysable(model: DocumentModel) -> list[Block]:
    return [b for b in model.blocks if b.kind in PROSE_KINDS and b.words >= MIN_BLOCK_WORDS]


def _opening(sentence: str, n: int = 2) -> str:
    return " ".join(words_of(sentence)[:n])


def block_signals(block: Block, kind: str | None = None) -> BlockSignals:
    """Passage-level measurements."""
    text = block.masked or block.text
    lowered = text.lower().replace("’", "'")
    sents = sentences(text)
    result = BlockSignals(block, kind or section_type(block.section))

    def hit(rule: str, severity: str, value: float, excerpt: str) -> None:
        result.hits.append(Hit(rule, severity, float(value), excerpt))

    stock = [p for p in STOCK_PHRASES if p in lowered]
    if stock:
        sentence = next((s for s in sents if any(p in s.lower().replace("’", "'") for p in stock)), text)
        hit("GEN_STOCK_PHRASE", "major" if len(stock) >= 2 else "moderate", len(stock), sentence)

    importance = IMPORTANCE.findall(text)
    if len(importance) >= RULES["GEN_IMPORTANCE"].threshold:
        hit("GEN_IMPORTANCE", "moderate" if len(importance) >= 3 else "minor", len(importance), next((s for s in sents if IMPORTANCE.search(s)), text))

    additive = [s for s in sents if ADDITIVE.match(s)]
    if len(additive) >= RULES["TRANS_STACKED"].threshold or re.search(r"\bhowever, it can also\b", lowered):
        hit("TRANS_STACKED", "moderate" if len(additive) >= 3 else "minor", len(additive), " … ".join(additive[:3]) or text)

    openings = Counter(_opening(s) for s in sents if len(words_of(s)) >= 3)
    repeated, count = openings.most_common(1)[0] if openings else ("", 0)
    if repeated and count >= RULES["OPENINGS_REPEATED"].threshold:
        hit("OPENINGS_REPEATED", "minor", count, " … ".join(s for s in sents if _opening(s) == repeated)[:280])

    for s in sents:
        hedges = len(HEDGES.findall(s))
        if hedges >= RULES["HEDGE_STACKED"].threshold:
            hit("HEDGE_STACKED", "moderate", hedges, s)
            break

    for s in sents:
        if VAGUE.search(s) and not HAS_CITATION.search(s):
            hit("VAGUE_ATTRIBUTION", "moderate", 1, s)
            break

    words = words_of(text)
    if len(words) >= 80 and result.kind in ("introduction", "literature", "discussion", "conclusion", "body"):
        density = specifics_per_100(text)
        if density < RULES["SPECIFICITY_LOW"].threshold:
            hit("SPECIFICITY_LOW", "minor", density, sents[0] if sents else text)

    if sents and SUMMARY_OPENER.match(sents[0]) and (stock or not HAS_CITATION.search(text)) and not NUMBER.search(TOKENS.sub(" ", text)):
        hit("SUMMARY_UNSUPPORTED", "major" if stock else "minor", 1, sents[0])

    lengths = [len(s.split()) for s in sents]
    if len(lengths) >= 5 and statistics.mean(lengths) > 8:  # fewer sentences are too few to call a rhythm
        variation = statistics.pstdev(lengths) / statistics.mean(lengths)
        if variation < RULES["RHYTHM_UNIFORM"].threshold:
            hit("RHYTHM_UNIFORM", "moderate" if variation < 0.15 and len(lengths) >= 7 else "minor", variation, sents[0])

    if len(words) >= 80:
        variety = mattr(words)
        if variety < RULES["VOCAB_NARROW"].threshold:
            hit("VOCAB_NARROW", "minor", variety, sents[0] if sents else text)

    result.rescore()
    return result


# --- document-level measurements --------------------------------------------------------------


def _content_ngrams(words: list[str], n: int = 5, topic: frozenset[str] = frozenset()) -> set[str]:
    """Five-word phrases with at least two content words. A phrase made only of the paper's topic
    vocabulary (words in its title and headings) is the paper's subject, not a template."""
    grams = set()
    for i in range(len(words) - n + 1):
        gram = words[i : i + n]
        content = [w for w in gram if w not in STOPWORDS]
        if len(content) >= 2 and not all(w in topic for w in content):
            grams.add(" ".join(gram))
    return grams


def _document_signals(blocks: list[BlockSignals], topic: frozenset[str] = frozenset()) -> list[DocSignal]:
    """Measurements across passages. The ones that are findings also add hits to the passages
    they concern (and rescore them)."""
    found: list[DocSignal] = []
    total_words = sum(b.block.words for b in blocks) or 1

    # Repeated five-word phrasing across different paragraphs (the first use is not flagged).
    grams = {b.block.id: _content_ngrams(words_of(b.block.masked or b.block.text), topic=topic) for b in blocks}
    seen: dict[str, list[str]] = {}
    for b in blocks:
        for gram in grams[b.block.id]:
            seen.setdefault(gram, []).append(b.block.id)
    repeated = {g: ids for g, ids in seen.items() if len(ids) >= RULES["NGRAM_REPEATED"].threshold}
    if repeated:
        flagged: set[str] = set()
        for b in blocks:
            mine = [(g, ids) for g, ids in repeated.items() if b.block.id in ids[1:]]
            if mine:
                gram, ids = min(mine, key=lambda item: (-len(item[1]), item[0]))  # ties broken by text: deterministic
                text = b.block.masked or b.block.text
                sentence = next((s for s in sentences(text) if gram in " ".join(words_of(s))), text)
                b.hits.append(Hit("NGRAM_REPEATED", "minor", len(ids), sentence))
                flagged.add(b.block.id)
        top = sorted(repeated.items(), key=lambda item: (-len(item[1]), item[0]))[:5]
        found.append(DocSignal("NGRAM_REPEATED", len(repeated), sorted(flagged), "most repeated: " + "; ".join(f'"{g}" ×{len(ids)}' for g, ids in top)))

    # Paragraphs opening with the same connective.
    openers: dict[str, list[BlockSignals]] = {}
    for b in blocks:
        first = sentences(b.block.masked or b.block.text)[:1]
        match = CONNECTIVE.match(first[0]) if first else None
        if match:
            openers.setdefault(match.group(1).lower(), []).append(b)
    for word, users in openers.items():
        if len(users) >= RULES["TRANS_PARA_OPENER"].threshold:
            for b in users[2:]:
                b.hits.append(Hit("TRANS_PARA_OPENER", "minor", len(users), sentences(b.block.masked or b.block.text)[0]))
            found.append(DocSignal("TRANS_PARA_OPENER", len(users), [b.block.id for b in users], f'"{word}" opens {len(users)} paragraphs'))

    # Sentence-opening connectives per 1,000 words (information for the lead model).
    opening = {b.block.id: sum(1 for s in sentences(b.block.masked or b.block.text) if CONNECTIVE.match(s)) for b in blocks}
    density = 1000 * sum(opening.values()) / total_words
    if density > RULES["TRANS_DENSITY"].threshold:
        found.append(DocSignal("TRANS_DENSITY", density, [bid for bid, n in sorted(opening.items(), key=lambda i: -i[1]) if n]))

    # Paragraph rhythm and style shifts, section by section (in reading order).
    sections: dict[str, list[BlockSignals]] = {}
    for b in blocks:
        sections.setdefault(b.block.section or "Body", []).append(b)
    for name, members in sections.items():
        sizes = [m.block.words for m in members]
        if len(sizes) >= 4 and statistics.pstdev(sizes) / statistics.mean(sizes) < RULES["PARA_RHYTHM"].threshold:
            found.append(DocSignal("PARA_RHYTHM", statistics.pstdev(sizes) / statistics.mean(sizes), [m.block.id for m in members], f'section "{name}"'))

    profiles = []
    for name, members in sections.items():
        text = " ".join(m.block.masked or m.block.text for m in members)
        words = words_of(text)
        lengths = [len(s.split()) for s in sentences(text)]
        if len(words) >= 150 and lengths:
            profiles.append((name, members, statistics.mean(lengths), mattr(words)))
    for (_, _, before_len, before_var), (name, members, after_len, after_var) in zip(profiles, profiles[1:], strict=False):
        ratio = max(before_len, after_len) / max(1.0, min(before_len, after_len))
        if ratio >= RULES["STYLE_SHIFT"].threshold and abs(before_var - after_var) >= 0.08:
            first = members[0]
            first.hits.append(Hit("STYLE_SHIFT", "minor", ratio, sentences(first.block.masked or first.block.text)[0]))
            found.append(DocSignal("STYLE_SHIFT", ratio, [first.block.id], f'section "{name}": sentence length ×{ratio:.1f}, vocabulary variety {before_var:.2f} → {after_var:.2f}'))

    # Punctuation profile: information only (an em dash is not an AI marker).
    joined = " ".join(b.block.text for b in blocks)
    per_k = lambda n: round(1000 * n / total_words, 1)  # noqa: E731
    found.append(
        DocSignal("PUNCTUATION_PROFILE", 0, [], f"em dashes {per_k(joined.count('—'))}, semicolons {per_k(joined.count(';'))}, colons {per_k(joined.count(':'))} per 1,000 words")
    )

    for b in blocks:
        b.rescore()
    return found


def scan(model: DocumentModel) -> Scan:
    blocks = analysable(model)
    measured = [block_signals(b) for b in blocks]
    topic = frozenset(w for line in model.outline() for w in words_of(line) if w not in STOPWORDS)
    document = _document_signals(measured, topic)
    words: dict[str, int] = {}
    for b in blocks:
        words[b.section or "Body"] = words.get(b.section or "Body", 0) + b.words
    sections = [{"heading": name, "type": section_type(name), "words": n} for name, n in words.items()]
    return Scan(measured, document, model.word_count - sum(b.words for b in blocks), sections)


def phrases(text: str) -> set[str]:
    """The five-word phrases the repetition rule compares."""
    return _content_ngrams(words_of(text))


def post_scan(original: str, revised: str, section: str, elsewhere: set[str]) -> dict[str, Any]:
    """For the final review: the passage's hits before and after the rewrite, and any phrasing
    the rewrite introduced that already appears elsewhere (`elsewhere`: the other passages'
    phrases)."""
    kind = section_type(section)
    before = block_signals(Block(id="before", kind="paragraph", section=section, text=original, masked=original), kind)
    after = block_signals(Block(id="after", kind="paragraph", section=section, text=revised, masked=revised), kind)
    new = (phrases(revised) - phrases(original)) & elsewhere
    return {
        "signalsBefore": sorted({h.rule for h in before.hits}),
        "signalsAfter": sorted({h.rule for h in after.hits}),
        "newRepeatedPhrasing": sorted(new)[:5],
    }


# --- aggregation ------------------------------------------------------------------------------


# The lead model's band for a passage, as a score on the same 0–1 scale as the signals.
MODEL_SCORE = {"low": 0.1, "moderate": 0.45, "high": 0.85}


def band_for(score: float) -> str:
    return "LOW" if score < 0.15 else "MODERATE" if score < 0.32 else "HIGH"


def aggregate(signals: list[BlockSignals], excluded_words: int, method: str, model_scores: dict[str, float] | None = None) -> AnalysisResult:
    """Word-weighted mean of passage scores → band. Model scores, when present, are blended 50/50."""
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
    result = scan(model)
    return aggregate(result.blocks, result.excluded_words, method), result.blocks
