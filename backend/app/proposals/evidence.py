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


def _year(source: EvidenceSource, letter: str = "") -> str:
    """The year as cited, with the letter that tells two works of one author and year apart ("2026a", "n.d.-a")."""
    if not letter:
        return source.year or "n.d."
    return f"{source.year}{letter}" if source.year else f"n.d.-{letter}"


def _key(source: EvidenceSource) -> str:
    return source.doi or research.normalise_url(source.url)


def _title_key(source: EvidenceSource) -> str:
    return re.sub(r"[\W_]+", "", clean_title(source.title).casefold())  # letters and digits of any script


def _same_work(a: EvidenceSource, b: EvidenceSource) -> bool:
    """Two records of one work: the same DOI or address, or one work reached by two addresses (its DOI and a page
    that carries none). Two registrations are two works whatever their titles; without that proof the titles must be
    the same and long enough to tell works apart ("Introduction" is not), in the same year, and by the same first
    author where both name one (Codex's audit of 1a3b1e7, finding 1: a title and a year alone merged two papers)."""
    if _key(a) == _key(b):
        return True
    if a.doi and b.doi:
        return False
    title = _title_key(a)
    if len(title) < 25 or title != _title_key(b) or a.year != b.year:
        return False
    first_a, first_b = clean_authors(a.authors)[:1], clean_authors(b.authors)[:1]
    return not (first_a and first_b) or _surname(first_a[0]).casefold() == _surname(first_b[0]).casefold()


def works(sources: Iterable[EvidenceSource]) -> list[list[EvidenceSource]]:
    """The distinct works among these sources, each with every record of it; the record that carries a DOI first."""
    groups: list[list[EvidenceSource]] = []
    seen: set[str] = set()
    for source in sources:
        if _key(source) in seen:
            continue
        seen.add(_key(source))
        group = next((g for g in groups if any(_same_work(known, source) for known in g)), None)
        if group is None:
            groups.append([source])
        elif source.doi and not group[0].doi:
            group.insert(0, source)
        else:
            group.append(source)
    return groups


def year_letters(sources: Iterable[EvidenceSource], style: "CitationStyle" = "APA7") -> dict[str, str]:
    """Letters for the works of one document that would otherwise be cited alike (the same author label and year):
    "a", "b" ... in the order of their titles, as the reference list prints them. By source key; a work cited alone
    in its label and year has none."""
    alike: dict[tuple[str, str], list[list[EvidenceSource]]] = {}
    for group in works(sources):
        alike.setdefault((author_label(group[0], style).casefold(), _year(group[0])), []).append(group)
    letters: dict[str, str] = {}
    for groups in alike.values():
        if len(groups) > 1:
            for n, group in enumerate(sorted(groups, key=lambda g: (_title_key(g[0]), _key(g[0])))):
                letters.update({_key(source): chr(97 + min(n, 25)) for source in group})
    return letters


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

    def __init__(self, library: dict[str, EvidenceItem], style: CitationStyle, cited: Iterable[str] | None = None):
        """`cited`: the ids the document cites, so works it would cite alike are told apart by letter exactly as its
        reference list does (`reference_list` of the same sources). Without it no letter is given."""
        self.library, self.style, self.seen = library, style, set()
        self.letters = year_letters([library[i].source for i in cited if i in library], style) if cited is not None else {}

    def _when(self, source: EvidenceSource) -> str:
        return _year(source, self.letters.get(_key(source), ""))

    def _label(self, source: EvidenceSource, narrative: bool) -> str:
        first = _key(source) not in self.seen
        self.seen.add(_key(source))
        return author_label(source, self.style, first, narrative)

    def cite(self, sources: list[EvidenceSource], narrative: bool = False) -> str:
        if narrative and len(sources) == 1:
            return f"{self._label(sources[0], True)} ({self._when(sources[0])})"
        sep = " " if self.style == "HARVARD" else ", "  # Harvard: (Okello et al. 2022); APA: (Okello et al., 2022)
        parts = []
        for group in works(sources):  # one work reached by two addresses prints once; two works never merge
            parts.append(f"{self._label(group[0], False)}{sep}{self._when(group[0])}")
            self.seen.update(_key(s) for s in group)
        return "(" + "; ".join(sorted(parts, key=str.lower)) + ")"

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


def _harvard(source: EvidenceSource, letter: str = "") -> str:
    """Harvard (Cite Them Right): Surname, I. (Year) Title. Journal, volume(issue), pp. pages. Available at: link."""
    names = clean_authors(source.authors)
    who = (", ".join(names[:-1]) + " and " + names[-1]) if len(names) > 1 else (names[0] if names else clean_text(source.organisation))
    title = _ended(clean_title(source.title))
    head = f"{who} ({_year(source, letter)}) {title}" if who else f"{title.rstrip('.')} ({_year(source, letter)})."
    link = f"https://doi.org/{source.doi}" if source.doi else ("" if source.url.startswith("reading:") else source.url)
    if source.kind == "ARTICLE":
        volume = source.volume + (f"({source.issue})" if source.issue else "")
        journal = clean_container(source.container)  # volume and pages belong to a journal: without one they are not printed
        tail = ", ".join(p for p in (journal, volume, f"pp. {clean_pages(source.pages)}" if source.pages else "") if p) if journal else ""
        head = f"{head} {tail}." if tail else head
    elif source.container and clean_text(source.container) != who:
        head = f"{head} {clean_text(source.container)}."
    return f"{head} Available at: {link}." if link else head


def reference(source: EvidenceSource, style: CitationStyle = "APA7", letter: str = "") -> str:
    """One reference-list entry, built only from the source's recorded details. `letter`: see `year_letters`."""
    if style == "HARVARD":
        return _harvard(source, letter)
    authors = clean_authors(source.authors)
    who = _authors_apa(authors, style) if authors else clean_text(source.organisation)
    title = _ended(clean_title(source.title))
    if who:
        head = f"{who}{'' if who.endswith('.') else '.'} ({_year(source, letter)}). {title}"
    else:
        head = f"{title} ({_year(source, letter)})."
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
    """Alphabetical, one entry for each distinct work (`works`); works cited alike carry their letters."""
    sources = list(sources)
    letters = year_letters(sources, style)
    return sorted((reference(group[0], style, letters.get(_key(group[0]), "")) for group in works(sources)), key=lambda r: r.lower().lstrip("“\"'"))


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


# A claim that research on a topic does not exist. A search that found nothing proves only that: the audit of
# 2026-10-10 found a registered study and a dissertation on a topic a proposal called "uninvestigated" and "completely
# lacking". Every alternative names research itself (a study, the literature, published evidence), so a statement that
# a fact is not known ("the eligible population remains unknown", "data on stock-outs are missing") is never one
# (Codex's audit of 1a3b1e7, finding 5). Wording that only may be such a claim is left to the reviewer.
_KIND = r"(?:prior\s+|previous\s+|existing\s+|known\s+|published\s+|empirical\s+)?"
ABSOLUTE_GAP = re.compile(
    r"\b(?:uninvestigated|unstudied|unresearched"
    r"|(?:has|have|had)\s+(?:never|not yet|yet to)\s+(?:been\s+|be\s+)?(?:studied|investigated|researched)"
    rf"|no\s+{_KIND}(?:study|studies|research|evidence|literature)\s+(?:has|have|exists?|is available|are available)"
    rf"|there\s+(?:is|are|exists?)\s+no\s+{_KIND}(?:(?:study|studies|research|literature)\s+(?:on|about|into|that|which|examining|addressing|available|regarding|concerning|to date)"
    r"|evidence\s+(?:on|about|regarding|concerning))"
    r"|(?:evidence|research|studies|literature)\b[^.;!?]{0,80}?\b(?:completely|entirely|totally|wholly|altogether)\s+(?:lacking|absent|missing))\b", re.I)
_HEDGED = re.compile(r"\b(?:largely|relatively|comparatively|mostly|somewhat|partly|little)\s+$", re.I)  # "remains largely unstudied" is a limit, not an absolute
# The claim is someone else's, or is being denied: "it is sometimes claimed that no study has ...".
_REPORTED = re.compile(r"\b(?:claim\w*|argu\w*|assert\w*|contend\w*|impl(?:y|ies|ied)|not (?:true|correct|accurate|the case)|wrong|mistaken|incorrect"
                       r"|cannot (?:be said|conclude)|does not mean)\b[^.;!?]{0,80}$", re.I)
# A ratio (whose value of no difference is 1), its interval with its stated level, and its p-value, in one sentence:
# "OR = 1.27; 95% CI: 0.56–2.89; p = 0.043".
_RATIO = re.compile(
    r"\b(?:a?OR|RR|HR|PR|odds ratios?|risk ratios?|hazard ratios?|prevalence ratios?|relative risks?)\b[^.;!?]{0,60}?\d+(?:\.\d+)?[^!?]{0,40}?"
    r"(?:(?P<level>\d{2}(?:\.\d+)?)\s*%\s*)?(?:CI|confidence interval)(?:\s+(?:of|from|was|is))?\W{0,4}(?P<low>\d+(?:\.\d+)?)\s*(?:[-–—]|to|,)\s*(?P<high>\d+(?:\.\d+)?)"
    r"[^!?]{0,40}?\bp\s*(?:-?\s*value)?\s*(?P<op>[<=])\s*(?P<p>0?\.\d+)", re.I)
_SIGNIFICANT = re.compile(r"\bsignifican(?:t|tly|ce)\b", re.I)
_DENIED = re.compile(r"(?:\b(?:not|no|never|without|lacked|lacks?|failed to reach|fails to reach)\b[\s\w-]{0,25}|\bnon-?)$", re.I)
_CLAUSE = re.compile(r";|\b(?:and|while|whereas|but|although|though)\b", re.I)


def _called_significant(text: str) -> bool:
    """The words say a result is significant ("not statistically significant" and "no significant" do not)."""
    return any(not _DENIED.search(text[max(0, m.start() - 45):m.start()]) for m in _SIGNIFICANT.finditer(text))


def _quoted(text: str, at: int) -> bool:
    before = text[:at]
    return before.count("“") > before.count("”") or before.count('"') % 2 == 1


def gap_problems(paragraph: str) -> list[str]:
    """A statement, in the writer's own voice, that research on a topic does not exist."""
    for found in ABSOLUTE_GAP.finditer(paragraph):
        before = paragraph[:found.start()]
        if _HEDGED.search(before) or _REPORTED.search(before[-140:]) or _quoted(paragraph, found.start()):
            continue
        return [f"“{found.group(0)}” claims that nothing has been studied or is known. State the gap as what the sources found do not show (for example "
                "“the studies found did not examine ...” or “published evidence on ... is limited”), never that no study exists."]
    return []


def _disagreeing(sentence: str) -> list[re.Match[str]]:
    """Ratios in the sentence whose stated interval, at 95% or narrower, includes 1 while the p-value is below 0.05.
    Those cannot both hold. An interval at another level (a 99% interval can include 1 at p = 0.02), one whose level
    is not stated, and a difference or a coefficient (whose value of no difference is 0) are not judged by code
    (Codex's audit of 1a3b1e7, finding 2)."""
    found = []
    for m in _RATIO.finditer(sentence):
        p = float(m.group("p"))
        below = p < 0.05 or (m.group("op") == "<" and p <= 0.05)
        if m.group("level") and float(m.group("level")) <= 95 and float(m.group("low")) <= 1 <= float(m.group("high")) and below:
            found.append(m)
    return found


def statistic_problems(paragraph: str) -> list[str]:
    """A ratio called significant while its own 95% interval includes 1 and its p-value is below 0.05. The two do
    not agree, whoever reported them (the audit of 2026-10-10 found one copied faithfully from a publisher's
    abstract): it is told as the source reports it, never as a significant association. Code corrects no figure.
    The word must belong to that result: the clause that leads to it or the one that follows it, never another
    result's in the same sentence ("age was significant (...), whereas education was not (...)")."""
    problems = []
    for sentence in sentences(paragraph):
        every = list(_RATIO.finditer(sentence))
        for m in _disagreeing(sentence):
            n = next(i for i, other in enumerate(every) if other.start() == m.start())
            lead = _CLAUSE.split(sentence[every[n - 1].end() if n else 0:m.start()])[-1]
            tail = _CLAUSE.split(sentence[m.end():every[n + 1].start() if n + 1 < len(every) else len(sentence)])[0]
            if _called_significant(lead) or _called_significant(tail):
                problems.append(f"The {m.group('level')}% interval reported ({m.group('low')}–{m.group('high')}) includes 1 while the p-value ({m.group('op')} {m.group('p')}) is below 0.05: "
                                "these do not agree. Do not call this result significant; say what the source reports and that its interval includes 1, or leave the result out.")
    return problems


def row_text(header: list[str], row: list[str]) -> str:
    """A table row read with its headings, as a reader takes it in: "OR = 1.27; 95% CI = 0.56–2.89; p = 0.043"."""
    return "; ".join(f"{h.strip()} = {c.strip()}" if h.strip() else c.strip() for h, c in zip([*header, *[""] * len(row)], row, strict=False) if c.strip())


def row_overclaims(header: list[str], row: list[str]) -> list[int]:
    """The cells of a row that call its result significant while the row, read with its headings, reports a ratio
    whose 95% interval includes 1 at p below 0.05 (a statistic spread across columns)."""
    if not _disagreeing(row_text(header, row)):
        return []
    return [n for n, cell in enumerate(row) if _called_significant(cell) and not _RATIO.search(cell)]


def table_problems(rows: list[list[str]]) -> list[str]:
    """Rows (the first is the heading row) that are called significant against their own interval."""
    if len(rows) < 2:
        return []
    return [f"The row “{row[0][:60]}” is called significant while its 95% interval includes 1 and its p-value is below 0.05: these do not agree. Do not call it significant."
            for row in rows[1:] if row_overclaims(rows[0], row)]


def strip_table_overclaims(rows: list[list[str]]) -> list[list[str]]:
    """The rows with each cell that makes that claim emptied (a withheld cell stays as an empty cell). The same
    list when nothing is withheld."""
    if len(rows) < 2 or not any(row_overclaims(rows[0], row) for row in rows[1:]):
        return rows
    return [rows[0], *[["" if n in set(row_overclaims(rows[0], row)) else cell for n, cell in enumerate(row)] for row in rows[1:]]]


def cited_in(sections: Iterable[object]) -> list[str]:
    """The evidence ids a document's sections cite, in reading order: paragraphs, then a table's caption and cells."""
    out: list[str] = []
    for s in sections:
        table = getattr(s, "table", None) or []
        for text in [*getattr(s, "paragraphs", []), *([getattr(s, "table_caption", ""), *[c for row in table for c in row]] if table else [])]:
            out += [i for i in cited_ids(text) if i not in out]
    return out


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
