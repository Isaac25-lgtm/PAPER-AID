"""The evidence library and the rules that keep a written proposal honest.

The writer never types a citation. It cites evidence by token (⟦E1a2b3c⟧, or ⟦E1a2b3c|n⟧ for a
narrative citation) and code renders APA 7 in-text citations and the reference list from the
source's registered details. So a reference can only exist if PaperAid read the source and
confirmed the quoted passage itself. Code also refuses, before release:
- a citation of anything not usable in the library, or a citation typed by hand;
- a figure in a paragraph that neither the cited evidence nor the student's own plan contains;
- the planned study described in the past tense (the manual: proposals use the future tense).
"""

import hashlib
import re
from collections.abc import Callable, Iterable
from typing import Literal

from app.analysis import research
from app.proposals.models import EvidenceItem, EvidenceSource

# Proposals use APA 6 or 7; coursework and funding works may also use Harvard (rulebook v1.0 CW-056).
CitationStyle = Literal["APA6", "APA7", "HARVARD"]

TOKEN = re.compile(r"⟦(E[0-9a-f]{6})(\|n)?⟧")
CITATION = re.compile(r"⟦(?P<narrative>E[0-9a-f]{6})\|n⟧|(?:\s*⟦E[0-9a-f]{6}⟧)+")  # a narrative token, or a run of parenthetical ones
ANY_TOKEN = re.compile(r"⟦[^⟧]*⟧")
TYPED_CITATION = re.compile(r"\([A-Z][^()]{0,80}?,\s*(?:19|20)\d{2}[a-z]?(?:,\s*p+\.\s*\d+)?\)|\b[A-Z][A-Za-z'’-]+(?:\s+et\s+al\.)?\s+\((?:19|20)\d{2}[a-z]?\)")
FIGURE = re.compile(r"(?<![\w.])\d{1,3}(?:,\d{3})+(?:\.\d+)?%?|(?<![\w.])\d+(?:\.\d+)?%?")
PAST_TENSE = re.compile(
    r"\b(?:this|the present|the current|the proposed) (?:study|research) (?:was|were|found|used|employed|collected|showed|revealed|established|adopted)\b"
    r"|\bdata (?:was|were) (?:collected|analysed|analyzed|gathered|obtained|coded|entered)\b"
    r"|\b(?:respondents|participants|interviewees) were (?:selected|sampled|interviewed|recruited|asked)\b"
    r"|\bthe researcher (?:used|collected|administered|obtained|sought|selected|interviewed)\b",
    re.I,
)


def evidence_id(source_key: str, passage: str) -> str:
    """Stable across jobs, so the same finding from the same source is one library entry."""
    words = " ".join(research._norm_words(passage))
    return "E" + hashlib.sha256(f"{source_key.lower()}|{words}".encode()).hexdigest()[:6]


def dedupe(items: Iterable[EvidenceItem]) -> list[EvidenceItem]:
    """One entry per id; a usable copy wins over one that could not be confirmed."""
    kept: dict[str, EvidenceItem] = {}
    for item in items:
        if item.id not in kept or (item.usable and not kept[item.id].usable):
            kept[item.id] = item
    return list(kept.values())


# --- APA rendering (6th edition, as in the UCU 2018 manual's appendix, or 7th) -------------------


def _surname(author: str) -> str:
    return author.split(",")[0].strip()


def _short_title(title: str) -> str:
    words = title.split()
    return " ".join(words[:5]) + ("…" if len(words) > 5 else "")


def _year(source: EvidenceSource) -> str:
    return source.year or "n.d."


def _key(source: EvidenceSource) -> str:
    return source.doi or research.normalise_url(source.url)


def author_label(source: EvidenceSource, style: CitationStyle = "APA7", first: bool = False, narrative: bool = False) -> str:
    """The author part of an in-text citation. APA 7: three or more authors are "et al." from the
    first citation. APA 6: three to five authors are all named the first time, then "et al."; six
    or more are "et al." throughout."""
    if not source.authors:
        return source.organisation or source.container or f"“{_short_title(source.title)}”"
    names = [_surname(a) for a in source.authors]
    joiner = " and " if narrative or style == "HARVARD" else " & "
    if len(names) == 1:
        return names[0]
    if len(names) == 2:
        return f"{names[0]}{joiner}{names[1]}"
    if style == "APA6" and first and len(names) <= 5:
        return ", ".join(names[:-1]) + f",{joiner}{names[-1]}"
    return f"{names[0]} et al."


class Citer:
    """Renders citation tokens in reading order, remembering first citations (APA 6 names three
    to five authors in full the first time)."""

    def __init__(self, library: dict[str, EvidenceItem], style: CitationStyle):
        self.library, self.style, self.seen = library, style, set()

    def _label(self, source: EvidenceSource, narrative: bool) -> str:
        first = _key(source) not in self.seen
        self.seen.add(_key(source))
        return author_label(source, self.style, first, narrative)

    def cite(self, sources: list[EvidenceSource], narrative: bool = False) -> str:
        if narrative and len(sources) == 1:
            return f"{self._label(sources[0], True)} ({_year(sources[0])})"
        unique = {_key(s): s for s in sources}
        sep = " " if self.style == "HARVARD" else ", "  # Harvard: (Okello et al. 2022); APA: (Okello et al., 2022)
        parts = sorted((f"{self._label(s, False)}{sep}{_year(s)}" for s in unique.values()), key=str.lower)
        return "(" + "; ".join(parts) + ")"

    def render(self, text: str) -> str:
        """Replace citation tokens with in-text citations; consecutive tokens become one
        parenthetical citation. Callers check first (`citation_problems`): an unknown token here is
        a programming error, not student-facing."""

        def one(match: re.Match[str]) -> str:
            if match.group("narrative"):
                return self.cite([self.library[match.group("narrative")].source], narrative=True)
            return " " + self.cite([self.library[i].source for i, _ in TOKEN.findall(match.group(0))])

        # One pass in reading order, so APA 6's "first citation" is the first in the text (Codex
        # audit 2026-09-28 #14: narrative citations used to be rendered after every parenthetical one).
        text = CITATION.sub(one, text)
        return re.sub(r"\s+([.,;:])", r"\1", text).strip()


def _authors_apa(authors: list[str], style: CitationStyle) -> str:
    limit = 7 if style == "APA6" else 20
    if len(authors) == 1:
        return authors[0]
    if len(authors) <= limit:
        return ", ".join(authors[:-1]) + ", & " + authors[-1]
    return ", ".join(authors[: limit - 1]) + ", … " + authors[-1]


def _harvard(source: EvidenceSource) -> str:
    """Harvard (Cite Them Right): Surname, I. (Year) Title. Journal, volume(issue), pp. pages. Available at: link."""
    names = source.authors
    who = (", ".join(names[:-1]) + " and " + names[-1]) if len(names) > 1 else (names[0] if names else source.organisation or "")
    title = source.title.strip().rstrip(".")
    head = f"{who} ({_year(source)}) {title}." if who else f"{title} ({_year(source)})."
    link = f"https://doi.org/{source.doi}" if source.doi else ("" if source.url.startswith("reading:") else source.url)
    if source.kind == "ARTICLE":
        volume = source.volume + (f"({source.issue})" if source.issue else "")
        tail = ", ".join(p for p in (source.container, volume, f"pp. {source.pages}" if source.pages else "") if p)
        head = f"{head} {tail}." if tail else head
    elif source.container and source.container != who:
        head = f"{head} {source.container}."
    return f"{head} Available at: {link}." if link else head


def reference(source: EvidenceSource, style: CitationStyle = "APA7") -> str:
    """One reference-list entry, built only from the source's recorded details."""
    if style == "HARVARD":
        return _harvard(source)
    who = _authors_apa(source.authors, style) if source.authors else (source.organisation or "")
    title = source.title.strip().rstrip(".")
    if who:
        head = f"{who}{'' if who.endswith('.') else '.'} ({_year(source)}). {title}."
    else:
        head = f"{title}. ({_year(source)})."
    if source.doi:
        link = f"doi:{source.doi}" if style == "APA6" else f"https://doi.org/{source.doi}"
    elif source.url.startswith("reading:"):  # one of the student's own readings: no web address
        link = ""
    else:
        link = f"Retrieved from {source.url}" if style == "APA6" else source.url
    if source.kind == "ARTICLE":
        volume = source.volume + (f"({source.issue})" if source.issue else "")
        tail = ", ".join(p for p in (source.container, volume, source.pages) if p)
        return f"{head} {tail + '. ' if tail else ''}{link}".strip()
    site = source.container if source.container and source.container != who else ""
    return f"{head} {site + '. ' if site else ''}{link}".strip()


def reference_list(sources: Iterable[EvidenceSource], style: CitationStyle = "APA7") -> list[str]:
    """Alphabetical, one entry per distinct source (DOI, else URL)."""
    unique: dict[str, EvidenceSource] = {}
    for s in sources:
        unique.setdefault(_key(s), s)
    return sorted((reference(s, style) for s in unique.values()), key=lambda r: r.lower().lstrip("“\"'"))


# --- the checks ---------------------------------------------------------------------------------


def cited_ids(text: str) -> list[str]:
    return [m.group(1) for m in TOKEN.finditer(text)]


def citation_problems(text: str, usable: set[str]) -> list[str]:
    problems = []
    for token in ANY_TOKEN.findall(text):
        match = TOKEN.fullmatch(token)
        if match is None:
            problems.append(f"{token} is not a valid citation token.")
        elif match.group(1) not in usable:
            problems.append(f"{token} cites evidence that is not in the confirmed evidence library.")
    for typed in TYPED_CITATION.findall(ANY_TOKEN.sub(" ", text)):
        problems.append(f"'{typed}' is a citation typed by hand; cite only with evidence tokens.")
    return problems


def _figures(text: str) -> set[str]:
    return {f.replace(",", "") for f in FIGURE.findall(text)}


def _plain_figure(figure: str) -> bool:
    """Years, small counts and section numbers are not statistics that need a source."""
    value = figure.rstrip("%")
    if figure.endswith("%"):
        return False
    try:
        number = float(value)
    except ValueError:
        return True
    if "." not in value and 1900 <= number <= 2100:
        return True
    return number <= 12 and number == int(number)


# "Section 1.9", "Table 3.2", "Figure 1.1", "Chapter 2": numbers that point inside the document, not
# statistics (a "Section 1.9" cross-reference was refused as an unsupported figure, live 2026-10-01).
REFERENCE = re.compile(r"\b(?:sections?|sub-?sections?|chapters?|tables?|figures?|appendix|appendices|annex(?:es)?|equations?|objectives?|"
                       r"questions?|hypothes[ie]s|steps?|phases?|pages?|items?|§)\s*(?:\d+(?:\.\d+)*|[A-Z])(?:\s*(?:and|to|–|-)\s*\d+(?:\.\d+)*)?",
                       re.IGNORECASE)
LIST_MARKER = re.compile(r"\(?(?:\d{1,2}|[a-z]|[ivx]{1,4})[.)]")


def figure_problems(paragraph: str, library: dict[str, EvidenceItem], allowed_text: str) -> list[str]:
    """Figures must come from the evidence cited in the same paragraph, or from the student's
    own inputs and plan (`allowed_text`). References to the document's own sections, tables and
    figures are not figures."""
    cited = [library[i] for i in cited_ids(paragraph) if i in library]
    known = _figures(allowed_text)
    for item in cited:
        known |= _figures(item.passage) | _figures(item.statement)
    missing = sorted(f for f in _figures(REFERENCE.sub(" ", ANY_TOKEN.sub(" ", paragraph))) if not _plain_figure(f) and f not in known)
    return [f"The figure {f} is not in the evidence cited in this paragraph or in your plan." for f in missing]


def tense_problems(paragraph: str) -> list[str]:
    return [f"'{m.group(0)}' describes the planned study in the past tense; a proposal uses the future tense." for m in PAST_TENSE.finditer(paragraph)]


def sentences(paragraph: str) -> list[str]:
    return re.split(r"(?<=[.!?])\s+(?=[A-Z⟦])", paragraph)


def strip_unsupported(paragraph: str, library: dict[str, EvidenceItem], usable: set[str], allowed_text: str,
                      also_allowed: Callable[[str], str] | None = None) -> str:
    """The last line of defence after the fix rounds: remove each sentence that still carries an
    invalid citation or an unsupported figure. Never adds anything, and returns the paragraph exactly
    as it was when nothing is removed: its spacing and line breaks are part of the approved text.
    `also_allowed` gives a sentence figures of its own to use (a coursework sentence about its worked example)."""
    kept = []
    removed = False
    for sentence in sentences(paragraph):
        if citation_problems(sentence, usable):
            removed = True
            continue
        context = sentence if cited_ids(sentence) else sentence + " " + " ".join(f"⟦{i}⟧" for i in cited_ids(paragraph))
        if figure_problems(context, library, allowed_text + (" " + also_allowed(sentence) if also_allowed else "")):
            removed = True
            if kept and LIST_MARKER.fullmatch(kept[-1]):
                kept.pop()  # "1." whose objective was withheld is never left behind on its own
            continue
        kept.append(sentence)
    return " ".join(kept).strip() if removed else paragraph
