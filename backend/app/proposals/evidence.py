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
from app.analysis.metadata import clean_authors, clean_container, clean_pages, clean_text, clean_title
from app.proposals.models import EvidenceItem, EvidenceSource

# Proposals use APA 6 or 7; coursework and funding works may also use Harvard (rulebook v1.0 CW-056).
CitationStyle = Literal["APA6", "APA7", "HARVARD"]

TOKEN = re.compile(r"⟦(E[0-9a-f]{6})(\|n)?⟧")
# A narrative token, or a run of parenthetical ones. A writer's comma, semicolon or "and" between two tokens is part of the
# run: it printed as "(Opok et al., 2026), (Opok et al., 2026)" (audit of the trial documents, 2026-10-10).
CITATION = re.compile(r"⟦(?P<narrative>E[0-9a-f]{6})\|n⟧|\s*⟦E[0-9a-f]{6}⟧(?:\s*(?:[,;]|and\b|&)?\s*⟦E[0-9a-f]{6}⟧)*")
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
    authors = clean_authors(source.authors)
    if not authors:
        return clean_text(source.organisation or source.container) or f"“{_short_title(clean_title(source.title))}”"
    names = [_surname(a) for a in authors]
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
        # one work reached by two addresses prints once
        parts = sorted(dict.fromkeys(f"{self._label(s, False)}{sep}{_year(s)}" for s in unique.values()), key=str.lower)
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


def _ended(title: str) -> str:
    """A title with its closing stop: one full stop, and none added after a question or exclamation mark."""
    title = title.rstrip(". ")
    return title if title.endswith(("?", "!")) else f"{title}."


def _authors_apa(authors: list[str], style: CitationStyle) -> str:
    limit = 7 if style == "APA6" else 20
    if len(authors) == 1:
        return authors[0]
    if len(authors) <= limit:
        return ", ".join(authors[:-1]) + ", & " + authors[-1]
    return ", ".join(authors[: limit - 1]) + ", … " + authors[-1]


def _harvard(source: EvidenceSource) -> str:
    """Harvard (Cite Them Right): Surname, I. (Year) Title. Journal, volume(issue), pp. pages. Available at: link."""
    names = clean_authors(source.authors)
    who = (", ".join(names[:-1]) + " and " + names[-1]) if len(names) > 1 else (names[0] if names else clean_text(source.organisation))
    title = _ended(clean_title(source.title))
    head = f"{who} ({_year(source)}) {title}" if who else f"{title.rstrip('.')} ({_year(source)})."
    link = f"https://doi.org/{source.doi}" if source.doi else ("" if source.url.startswith("reading:") else source.url)
    if source.kind == "ARTICLE":
        volume = source.volume + (f"({source.issue})" if source.issue else "")
        journal = clean_container(source.container)  # volume and pages belong to a journal: without one they are not printed
        tail = ", ".join(p for p in (journal, volume, f"pp. {clean_pages(source.pages)}" if source.pages else "") if p) if journal else ""
        head = f"{head} {tail}." if tail else head
    elif source.container and clean_text(source.container) != who:
        head = f"{head} {clean_text(source.container)}."
    return f"{head} Available at: {link}." if link else head


def reference(source: EvidenceSource, style: CitationStyle = "APA7") -> str:
    """One reference-list entry, built only from the source's recorded details."""
    if style == "HARVARD":
        return _harvard(source)
    authors = clean_authors(source.authors)
    who = _authors_apa(authors, style) if authors else clean_text(source.organisation)
    title = _ended(clean_title(source.title))
    if who:
        head = f"{who}{'' if who.endswith('.') else '.'} ({_year(source)}). {title}"
    else:
        head = f"{title} ({_year(source)})."
    if source.doi:
        link = f"doi:{source.doi}" if style == "APA6" else f"https://doi.org/{source.doi}"
    elif source.url.startswith("reading:"):  # one of the student's own readings: no web address
        link = ""
    else:
        link = f"Retrieved from {source.url}" if style == "APA6" else source.url
    if source.kind == "ARTICLE":
        volume = source.volume + (f"({source.issue})" if source.issue else "")
        journal = clean_container(source.container)  # volume and pages belong to a journal: without one they are not printed
        tail = ", ".join(p for p in (journal, volume, clean_pages(source.pages)) if p) if journal else ""
        return f"{head} {tail + '. ' if tail else ''}{link}".strip()
    site = clean_text(source.container) if source.container and clean_text(source.container) != who else ""
    return f"{head} {site + '. ' if site else ''}{link}".strip()


def reference_list(sources: Iterable[EvidenceSource], style: CitationStyle = "APA7") -> list[str]:
    """Alphabetical, one entry per distinct source (DOI, else URL)."""
    unique: dict[str, EvidenceSource] = {}
    for s in sources:
        unique.setdefault(_key(s), s)
    # one work reached by two addresses (its DOI and a page that carries none) is listed once: the entry with a DOI
    works: dict[tuple[str, str], EvidenceSource] = {}
    for s in unique.values():
        same = (re.sub(r"[^a-z0-9]", "", clean_title(s.title).casefold()), s.year)
        if same not in works or (s.doi and not works[same].doi):
            works[same] = s
    return sorted((reference(s, style) for s in works.values()), key=lambda r: r.lower().lstrip("“\"'"))


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
# A numbered sub-heading line placed by code ("1.4.1 General Objective"): its number is the document's own.
SUBHEADING = re.compile(r"^\d{1,2}(?:\.\d{1,2}){1,2} [A-Z][A-Za-z ]{2,60}$")


def figure_problems(paragraph: str, library: dict[str, EvidenceItem], allowed_text: str) -> list[str]:
    """Figures must come from the evidence cited in the same paragraph, or from the student's
    own inputs and plan (`allowed_text`). References to the document's own sections, tables and
    figures are not figures."""
    if SUBHEADING.match(paragraph.strip()):
        return []
    cited = [library[i] for i in cited_ids(paragraph) if i in library]
    known = _figures(allowed_text)
    for item in cited:
        known |= _figures(item.passage) | _figures(item.statement)
    missing = sorted(f for f in _figures(REFERENCE.sub(" ", ANY_TOKEN.sub(" ", paragraph))) if not _plain_figure(f) and f not in known)
    return [f"The figure {f} is not in the evidence cited in this paragraph or in your plan." for f in missing]


# A claim that nothing has been studied. A search that found nothing proves only that: the audit of 2026-10-10 found a
# registered study and a dissertation on a topic a proposal called "uninvestigated" and "completely lacking". Each
# alternative names research or evidence itself, so "electricity is completely lacking" is not one.
_KIND = r"(?:prior\s+|previous\s+|existing\s+|known\s+|published\s+|empirical\s+)?"
ABSOLUTE_GAP = re.compile(
    r"\b(?:uninvestigated|unexplored|unstudied|unresearched"
    r"|(?:has|have|had)\s+(?:never|not yet|yet to)\s+(?:been\s+|be\s+)?(?:studied|investigated|examined|researched|explored)"
    rf"|no\s+{_KIND}(?:study|studies|research|evidence|literature|data)\s+(?:has|have|exists?|is available|are available)"
    rf"|there\s+(?:is|are|exists?)\s+no\s+{_KIND}(?:study|studies|research|literature)\s+(?:on|about|into|that|which|examining|addressing|available|regarding|concerning|to date)"
    r"|(?:remains?|remained)\s+(?:undocumented|unknown|unexamined)"
    r"|(?:evidence|research|studies|data|literature|knowledge|information)\b[^.;!?]{0,80}?\b(?:completely|entirely|totally|wholly|altogether)\s+(?:lacking|absent|missing|unknown))\b", re.I)
_HEDGED = re.compile(r"\b(?:largely|relatively|comparatively|mostly|somewhat|partly|little)\s+$", re.I)  # "remains largely unexplored" is a limit, not an absolute
# "OR = 1.27; 95% CI: 0.56–2.89; p = 0.043": a ratio, its interval and its p-value in one sentence.
_RATIO = re.compile(
    r"\b(?:a?OR|RR|HR|PR|odds ratios?|risk ratios?|hazard ratios?|prevalence ratios?)\b[^.;!?]{0,60}?\d+(?:\.\d+)?[^!?]{0,40}?"
    r"(?:CI|confidence interval)(?:\s+(?:of|from|was|is))?\W{0,4}(\d+(?:\.\d+)?)\s*(?:[-–—]|to|,)\s*(\d+(?:\.\d+)?)[^!?]{0,40}?\bp\s*(?:-?\s*value)?\s*([<=])\s*(0?\.\d+)", re.I)
_SIGNIFICANT = re.compile(r"\bsignifican(?:t|tly|ce)\b", re.I)
_DENIED = re.compile(r"(?:\b(?:not|no|never|without|lacked|lacks?|failed to reach|fails to reach)\b[\s\w-]{0,25}|\bnon-?)$", re.I)


def _called_significant(sentence: str) -> bool:
    """The sentence says its result is significant ("not statistically significant" and "no significant" do not)."""
    return any(not _DENIED.search(sentence[max(0, m.start() - 45):m.start()]) for m in _SIGNIFICANT.finditer(sentence))


def gap_problems(paragraph: str) -> list[str]:
    """A statement that a topic has never been studied, or that evidence is wholly absent."""
    for found in ABSOLUTE_GAP.finditer(paragraph):
        if _HEDGED.search(paragraph[:found.start()]):
            continue
        return [f"“{found.group(0)}” claims that nothing has been studied or is known. State the gap as what the sources found do not show (for example "
                "“the studies found did not examine ...” or “published evidence on ... is limited”), never that no study exists."]
    return []


def statistic_problems(paragraph: str) -> list[str]:
    """A ratio whose reported interval includes 1 while its p-value is below 0.05, called significant. The two do not
    agree, whoever reported them (the audit of 2026-10-10 found one such result copied faithfully from a publisher's
    abstract): it is told as the source reports it, never as a significant association. Code corrects no figure."""
    problems = []
    for sentence in sentences(paragraph):
        for found in _RATIO.finditer(sentence):
            low, high, p = float(found.group(1)), float(found.group(2)), float(found.group(4))
            below = p < 0.05 or (found.group(3) == "<" and p <= 0.05)
            if low <= 1 <= high and below and _called_significant(sentence):
                problems.append(f"The interval reported ({found.group(1)}–{found.group(2)}) includes 1 while the p-value ({found.group(3)} {found.group(4)}) is below 0.05: these do not agree. "
                                "Do not call this result significant; say what the source reports and that its interval includes 1, or leave the result out.")
    return problems


def strip_overclaims(paragraph: str, gaps: bool = True) -> str:
    """The last line of defence for the two checks above, as `strip_unsupported` is for citations and figures: a
    sentence the repair rounds left making either claim is withheld whole, before the final review reads the section.
    Returns the paragraph exactly as it was when nothing is removed."""
    parts = sentences(paragraph)
    kept = [s for s in parts if not (statistic_problems(s) or (gaps and gap_problems(s)))]
    return paragraph if len(kept) == len(parts) else " ".join(kept).strip()


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
