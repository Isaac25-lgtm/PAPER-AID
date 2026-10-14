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
FIGURE = re.compile(r"(?<![\w.])[-+−]?\d{1,3}(?:,\d{3})+(?:\.\d+)?%?|(?<![\w.])[-+−]?\d+(?:\.\d+)?%?")
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


DATED_AFTER = 10  # years between a source and the day its finding was gathered


def dated(item: EvidenceItem) -> str:
    """What a writer and a reviewer are told about a finding from an old source, with the finding: a figure from it is
    that year's figure. A 2003 paper was cited for what malaria "accounts for" today (round of 11 October 2026). Said
    in words, never enforced by code: an old source is often the right one for a theory or a history."""
    year = re.fullmatch(r"(?:19|20)\d{2}", item.source.year or "")
    gathered = re.match(r"(?:19|20)\d{2}", item.retrieved_on or "")
    if not year or not gathered or int(gathered.group(0)) - int(year.group(0)) <= DATED_AFTER:
        return ""
    if not re.search(r"\d", re.sub(r"\b(?:19|20)\d{2}\b", "", item.statement)):
        return ""  # no figure to go out of date: a method or a theory is not "as of 2015" (quality round, 2026-10-11)
    return (f"Published in {year.group(0)}. A figure or a description of the situation from it is given as that time's, with its year "
            f"(“in {year.group(0)}, ...”), never as the present position; for the present, use a recent finding or say none was found.")


def dedupe(items: Iterable[EvidenceItem]) -> list[EvidenceItem]:
    """One entry per id; a usable copy wins over one that could not be confirmed."""
    kept: dict[str, EvidenceItem] = {}
    retracted: set[str] = set()
    for item in items:
        if item.source.retracted:
            retracted.add(item.source.doi or item.source.url)
        if item.id not in kept or (item.usable and not kept[item.id].usable):
            kept[item.id] = item
    return [item.model_copy(update={"source": item.source.model_copy(update={"retracted": True})})
            if (item.source.doi or item.source.url) in retracted else item for item in kept.values()]


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


def _initials(author: str) -> str:
    return "".join(re.findall(r"[^\W\d_]", author.partition(",")[2])).casefold()


def _same_authorship(a: EvidenceSource, b: EvidenceSource) -> bool:
    """Both records name the same people, as far as each goes: the same surnames in the same order (one list may stop
    short of the other) and initials that agree (one may give fewer). With no people on either side, the same body.
    A record that names people and one that names none are not shown to be the same work."""
    one, other = clean_authors(a.authors), clean_authors(b.authors)
    if not one and not other:
        return bool(a.organisation.strip()) and clean_text(a.organisation).casefold() == clean_text(b.organisation).casefold()
    if not one or not other:
        return False
    for x, y in zip(one, other, strict=False):
        first, second = _initials(x), _initials(y)
        if _surname(x).casefold() != _surname(y).casefold() or not (first.startswith(second) or second.startswith(first)):
            return False
    return True


def _same_work(a: EvidenceSource, b: EvidenceSource) -> bool:
    """Two records of one work: the same DOI or address, or one work reached by two addresses (its DOI and a page
    that carries none). Two registrations are two works whatever their titles. Without that proof everything the
    records say must agree: a title long enough to tell works apart ("Introduction" is not), the year, who wrote it
    (`_same_authorship`: "Smith, J." and "Smith, R." are two people), and the journal, volume and pages wherever both
    give them. Where identity is not shown, the records stay two entries (Codex's audits of 1a3b1e7, 458e65b and
    6e513af)."""
    if _key(a) == _key(b):
        return True
    if a.doi and b.doi:
        return False
    title = _title_key(a)
    if len(title) < 25 or title != _title_key(b) or a.year != b.year or not _same_authorship(a, b):
        return False
    for one, other in ((clean_container(a.container), clean_container(b.container)), (a.volume, b.volume), (clean_pages(a.pages), clean_pages(b.pages))):
        if one.strip() and other.strip() and one.strip().casefold() != other.strip().casefold():
            return False
    return True


def works(sources: Iterable[EvidenceSource]) -> list[list[EvidenceSource]]:
    """The distinct works among these sources, each with every record of it; the record that carries a DOI first.

    Every DOI is a work of its own. A record without one joins a work only when it is the same work as every record
    already in it, and only when that is the one work it could be: a record that fits two works (two papers under
    different DOIs with one title, year and author) is listed on its own and never joins them into one (Codex's
    re-audit of 458e65b, finding 1). The result does not depend on the order the sources come in."""
    unique: dict[str, EvidenceSource] = {}
    for source in sources:
        unique.setdefault(_key(source), source)
    ordered = sorted(unique.values(), key=lambda s: (not s.doi, not s.authors, _key(s)))  # registered works first, then records that name an author; never the order given
    groups: list[list[EvidenceSource]] = []
    for source in ordered:
        fits = [] if source.doi else [g for g in groups if all(_same_work(known, source) for known in g)]
        if len(fits) == 1:
            fits[0].append(source)
        else:
            groups.append([source])
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
        text = CITATION.sub(one, self._without_typed_names(text))
        return re.sub(r"\s+([.,;:])", r"\1", text).strip()

    def _without_typed_names(self, text: str) -> str:
        """A narrative token prints its author's name. A writer who also typed that name just before the token
        got it twice: "As Mann Mann (2003) observes", "The Centers for Disease Control and Prevention Centers for
        Disease Control and Prevention (2012) notes" (independent audit, 2026-10-12). Only the exact name this very
        token will print, standing immediately before it, is taken out; nothing else in the sentence is touched."""
        out, last = [], 0
        for match in re.finditer(r"⟦(E[0-9a-f]{6})\|n⟧", text):
            item = self.library.get(match.group(1))
            before = text[last:match.start()]
            if item is not None:
                labels = {author_label(item.source, self.style, first, True) for first in (True, False)}
                # a body's name typed without the abbreviation it prints with: "Critical Appraisal Skills Programme (CASP UK)"
                labels |= {re.sub(r"\s*\([^()]*\)$", "", label) for label in labels}
                for label in sorted(labels, key=len, reverse=True):
                    typed = re.search(r"(?<![\w])" + re.escape(label) + r"\s*$", before) if label and not label.startswith("“") else None
                    if typed:
                        before = before[:typed.start()]
                        break
            out.append(before)
            out.append(match.group(0))
            last = match.end()
        out.append(text[last:])
        return "".join(out)


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
    if source.preprint:
        title += " [Preprint]."
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
    if source.preprint:
        title += " [Preprint]."
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


def reference_entries(sources: Iterable[EvidenceSource], style: CitationStyle = "APA7",
                      among: Iterable[EvidenceSource] | None = None) -> list[tuple[str, list[EvidenceSource]]]:
    """The reference list with, beside each entry, the records of the work it stands for: alphabetical, one entry for
    each distinct work (`works`). Works cited alike carry their letters, told apart among `among` when the list is
    part of a larger document (a chapter of a proposal) and otherwise among these sources."""
    sources = list(sources)
    letters = year_letters(sources if among is None else [*sources, *among], style)
    entries = [(reference(group[0], style, letters.get(_key(group[0]), "")), group) for group in works(sources)]
    return sorted(entries, key=lambda e: e[0].lower().lstrip("“\"'"))


def reference_list(sources: Iterable[EvidenceSource], style: CitationStyle = "APA7", among: Iterable[EvidenceSource] | None = None) -> list[str]:
    return [entry for entry, _ in reference_entries(sources, style, among)]


def same_source(a: EvidenceSource, b: EvidenceSource) -> bool:
    """The two records are one source (its DOI, else its address)."""
    return _key(a) == _key(b)


# --- the checks ---------------------------------------------------------------------------------


def cited_ids(text: str) -> list[str]:
    return [m.group(1) for m in TOKEN.finditer(text)]


def source_context(item: EvidenceItem, status: bool = False) -> dict[str, str]:
    """Recorded provenance, not a certificate of suitability. Source kinds come from metadata, not model guesses."""
    out = {"sourceKind": "PREPRINT" if item.source.preprint else item.source.kind, "metadataOrigin": item.source.metadata, "access": item.access,
           "retrievedOn": item.retrieved_on, "sourceTitle": item.source.title, "sourceUrl": item.source.url}
    if status:
        out["retractionStatus"] = ("KNOWN_RETRACTED" if item.source.retracted else "NOT_KNOWN_RETRACTED" if item.source.retraction_checked
                                   else "NOT_APPLICABLE" if item.source.kind not in ("ARTICLE", "BOOK") else "NOT_CHECKED")
    return out


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


def _quantity_key(value: str) -> str:
    """Equivalent decimal spelling, preserving sign and percent units. No rounding."""
    percent = "%" if value.endswith("%") else ""
    raw = value.removesuffix("%").replace("−", "-").lstrip("+")
    sign = "-" if raw.startswith("-") else ""
    whole, _, fraction = raw.lstrip("-").partition(".")
    whole, fraction = whole.lstrip("0") or "0", fraction.rstrip("0")
    return sign + whole + ("." + fraction if fraction else "") + percent


def _plain_figure(figure: str) -> bool:
    """Years, small counts and section numbers are not statistics that need a source."""
    value = figure.rstrip("%")
    if value.startswith(("-", "−")):
        return False
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
    quantities = {_quantity_key(f) for f in known}
    missing = sorted(f for f in _figures(REFERENCE.sub(" ", ANY_TOKEN.sub(" ", paragraph)))
                     if not _plain_figure(f) and _quantity_key(f) not in quantities)
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
# A ratio (whose value of no difference is 1), its interval with its stated level, and its p-value, in one sentence:
# "OR = 1.27; 95% CI: 0.56–2.89; p = 0.043".
_RATIO = re.compile(
    r"\b(?:a?OR|RR|HR|PR|odds ratios?|risk ratios?|hazard ratios?|prevalence ratios?|relative risks?)\b[^.;!?]{0,60}?\d+(?:\.\d+)?[^!?]{0,40}?"
    r"(?:(?P<level>\d{2}(?:\.\d+)?)\s*%\s*)?(?:CI|confidence interval)(?:\s+(?:of|from|was|is))?\W{0,4}(?P<low>\d+(?:\.\d+)?)\s*(?:[-–—]|to|,)\s*(?P<high>\d+(?:\.\d+)?)"
    r"[^!?]{0,40}?\bp\s*(?:-?\s*value)?\s*(?P<op>[<=])\s*(?P<p>0?\.\d+)", re.I)
_SIGNIFICANT = re.compile(r"\bsignifican(?:t|tly|ce)\b", re.I)
_CLAUSE = re.compile(r";|\b(?:and|while|whereas|but|although|though)\b", re.I)
# Where a new clause certainly begins: a semicolon, a contrast, or "and" after a comma. A bare "and" may only join
# two nouns ("between education and uptake").
_BREAK = re.compile(r";|\b(?:whereas|while|although|though|but)\b|,\s*and\b", re.I)
_JOINED = re.compile(r"\bbetween\b[^,;()]{1,80}?\band\b", re.I)
_OPENER = re.compile(r"\s*(?:although|though|because|since|while|as|if|when|where|given)\b[^,]*,", re.I)
# Three kinds of word decide what code may conclude about a claim, and only when they stand in the claim's own
# clause: another clause's "no" says nothing about it ("there is no electricity in the district, and no study has
# ..."). A denial or a doubt of a significance claim makes it sound; a reporting verb does not ("the study suggests
# a significant association" still calls it significant). For a claim that research is absent, any of the three
# leaves code unable to say whose claim it is or whether it is made at all, and then the sentence is neither flagged
# nor passed over: it is given to the reviewer to read (Codex's audits of 458e65b, finding 3, and 6e513af, finding 2).
_NEGATION = re.compile(r"\b(?:not|no|never|neither|nor|cannot|without|hardly|scarcely|non|lacked|lacks?|fail\w*)\b|n['’]t\b", re.I)
_DOUBT = re.compile(r"\b(?:inconsistent|misleading|mistaken|wrong|false|untrue|incorrect|inaccurate|contradict\w*|unsupported|unjustified|doubt\w*|questionable|caution\w*)\b", re.I)
_CONDITIONAL = re.compile(r"\s*(?:if|unless|whether|were|had|should|suppose|supposing|assume|assuming|imagine|hypothetically)\b", re.I)
_QUOTATION = re.compile(r'“[^”]*”|"[^"]*"|‘[^’]*’')
_REPORTING = re.compile(r"\b(?:claim\w*|argu\w*|assert\w*|contend\w*|suggest\w*|impl(?:y|ies|ied)|say|says|said|saying|state|states|stated|stating|wrote|writes?|conclud\w*"
                        r"|believ\w*|maintain\w*)\b|\bthat\s*$", re.I)
_AFFIRMS = re.compile(r"(?:yes|y|true|sig\.?|significant|✓|✔|\*{1,3})", re.I)
GAP_NOTE = "PaperAid's code could not tell whether this sentence claims that no research exists on its topic, or reports, denies or questions such a claim: “{}”"
RATIO_NOTE = ("PaperAid's code could not tell whether this sentence calls a result significant whose reported {}% interval ({}–{}) includes 1 while its p-value is below "
              "0.05, or says that it is not: “{}”")


def _significance(clause: str) -> str:
    """What a short text (a table cell, a heading) says about significance: "PLAIN", "DENIED" or ""."""
    if not _SIGNIFICANT.search(clause):
        return ""
    return "DENIED" if _NEGATION.search(clause) or _DOUBT.search(clause) else "PLAIN"


def _said_of(lead: str, tail: str) -> str:
    """What the words around one result say of it. `lead` runs from the result before it (or the sentence's start)
    up to it; `tail` from it to the next result (or the sentence's end).

    "PLAIN": it is called significant, whoever is said to have found so. "DENIED": the word is negated or doubted
    ("not significant", "should not be described as significant"). "UNSURE": the word is there but code cannot tie
    it to this result (another clause begins between them) or cannot tell a denial from an unrelated "no". "": the
    result is not called anything."""
    words = list(_SIGNIFICANT.finditer(lead))
    if words:
        word = words[-1]
        between = _JOINED.sub(" ", lead[word.end():])
        if _CLAUSE.search(between):
            return "UNSURE"  # "age was significant and education showed (OR ...)": the word belongs to another clause
        before = _BREAK.split(lead[:word.start()])[-1]
        return "DENIED" if _NEGATION.search(before) or _DOUBT.search(before) else "PLAIN"
    first = _SIGNIFICANT.search(_BREAK.split(tail)[0])
    if first:
        before = _BREAK.split(tail)[0][:first.start()]
        if _CLAUSE.search(_JOINED.sub(" ", before)):
            return "UNSURE"
        return "DENIED" if _NEGATION.search(before) or _DOUBT.search(before) else "PLAIN"
    return ""


def _called_significant(text: str) -> bool:
    return _significance(text) == "PLAIN"


def _quoted(text: str, at: int) -> bool:
    before = text[:at]
    return before.count("“") > before.count("”") or before.count('"') % 2 == 1 or before.count("‘") > before.count("’")


def _conditional_or_question(sentence: str) -> bool:
    """Code cannot treat a condition or a question as an assertion. The reviewer reads its full context."""
    return bool(_CONDITIONAL.match(sentence)) or sentence.rstrip().endswith("?")


def gap_findings(paragraph: str) -> tuple[list[str], list[str]]:
    """(problems, sentences for the reviewer) about claims that research on a topic does not exist. A problem is the
    plain assertion, in the writer's own voice. A sentence is for the reviewer when the claim's own clause negates,
    doubts or reports it, or the claim stands inside a quotation: code neither flags nor passes over what it cannot
    judge. A hedged claim ("remains largely unstudied") is the wording asked for, and is neither."""
    problems: list[str] = []
    notes: list[str] = []
    for sentence in sentences(paragraph):
        for found in ABSOLUTE_GAP.finditer(sentence):
            lead = sentence[:found.start()]
            if _HEDGED.search(lead):
                continue
            opener = _OPENER.match(lead)  # "Although the district is not remote, ...": that clause ends at its comma
            own = _CLAUSE.split(lead[opener.end():] if opener else lead)[-1]
            if (_conditional_or_question(sentence) or _quoted(sentence, found.start()) or _NEGATION.search(own)
                    or _DOUBT.search(own) or _REPORTING.search(own)):
                notes.append(GAP_NOTE.format(sentence.strip()[:400]))
            else:
                problems.append(f"“{found.group(0)}” claims that nothing has been studied or is known. State the gap as what the sources found do not show (for example "
                                "“the studies found did not examine ...” or “published evidence on ... is limited”), never that no study exists.")
            break
    return problems[:1], list(dict.fromkeys(notes))


def gap_problems(paragraph: str) -> list[str]:
    return gap_findings(paragraph)[0]


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


def statistic_findings(paragraph: str) -> tuple[list[str], list[str]]:
    """(problems, sentences for the reviewer) about a ratio whose own 95% interval includes 1 while its p-value is
    below 0.05. The two do not agree, whoever reported them (the audit of 2026-10-10 found one copied faithfully
    from a publisher's abstract). A problem: the words that lead to the result, or follow it, plainly call it
    significant (`_said_of`), whoever they say found so; never another result's words in the same sentence. For the
    reviewer: the word is negated or doubted, which is usually a sound sentence and sometimes is not ("among women
    with no schooling the association was significant"), or cannot be tied to this result. Code corrects no figure."""
    problems: list[str] = []
    notes: list[str] = []
    for sentence in sentences(paragraph):
        every = list(_RATIO.finditer(sentence))
        for m in _disagreeing(sentence):
            n = next(i for i, other in enumerate(every) if other.start() == m.start())
            start = every[n - 1].end() if n else 0
            end = every[n + 1].start() if n + 1 < len(every) else len(sentence)
            lead, tail = sentence[start:m.start()], sentence[m.end():end]
            said = _said_of(lead, tail)
            words = list(_SIGNIFICANT.finditer(lead))
            after = _SIGNIFICANT.search(_BREAK.split(tail)[0]) if not words else None
            at = None
            if words:
                at = start + words[-1].start()
            elif after:
                at = m.end() + after.start()
            # Quotation marks and a criticism AFTER the figures also change whose claim this is. An unrelated
            # negative word can make this uncertain, never automatically sound: the reviewer must decide.
            if said == "PLAIN" and (_conditional_or_question(sentence) or (at is not None and _quoted(sentence, at))
                                    or _NEGATION.search(tail) or _DOUBT.search(tail)):
                said = "UNSURE"
            if said == "PLAIN":
                problems.append(f"The {m.group('level')}% interval reported ({m.group('low')}–{m.group('high')}) includes 1 while the p-value ({m.group('op')} {m.group('p')}) is below 0.05: "
                                "these do not agree. Do not call this result significant; say what the source reports and that its interval includes 1, or leave the result out.")
            elif said:  # denied, or not tied to this result: the reviewer reads it
                notes.append(RATIO_NOTE.format(m.group("level"), m.group("low"), m.group("high"), sentence.strip()[:400]))
    return problems, list(dict.fromkeys(notes))


def statistic_problems(paragraph: str) -> list[str]:
    return statistic_findings(paragraph)[0]


def for_the_reviewer(texts: Iterable[str], gaps: bool = True, library: dict[str, EvidenceItem] | None = None) -> list[str]:
    """The sentences of these texts (a section's paragraphs, caption and cells) that code could not judge, each to be
    read by the reviewer. They are not problems: nothing is repaired or withheld because of one. With the `library`,
    an exact provision of a law that code could not take out by itself is among them."""
    notes: list[str] = []
    for text in texts:
        notes += statistic_findings(text)[1] + (gap_findings(text)[1] if gaps else [])
        if library is not None:
            notes += provision_findings(text, library)[1]
    return list(dict.fromkeys(notes))


# An exact provision of a law ("Section 13(5)(2c) of the Education Act 2008"). A report about a law can number its
# provisions wrongly, and the one PaperAid cited had (independent audit, 2026-10-12: the duty is in section 6(2)(c)).
# A quote check proves only that the report says so. So a provision's number is printed only when a source cited for
# it is the law itself; otherwise the law is named without the number and the point stays with the source that
# reports it. Code never supplies or corrects a number.
_PART = r"(?:(?:sub-?)?sections?|articles?|regulations?|clauses?|rules?|ss?\.|art\.)"
_NUMBER = r"\d+[A-Za-z]?(?:\s*[\(\[]\s*\w+\s*[\)\]])*"
PROVISION = re.compile(rf"\b{_PART}\s+{_NUMBER}", re.I)
INSTRUMENT = re.compile(r"\b((?:[A-Z][\w'’&-]*,?\s+(?:(?:of|and|for|on|the)\s+)?){0,6}(?:Act|Constitution|Regulations?|Statute|Ordinance|Decree|Convention|Charter|Code))\b")
_LABELLED = re.compile(rf"\b{_PART}\s+{_NUMBER}(?:\s*,\s*(?:sub-?sections?|paragraphs?)\s+{_NUMBER})?\s+of\s+(the\s+)?", re.I)
_BRACKETED = re.compile(rf"\s*\(\s*{_PART}\s+\d[^()]*(?:\([^()]*\)[^()]*)*\)", re.I)
LAW_SITES = re.compile(r"(?:^|\.)(?:ulii\.org|kenyalaw\.org|saflii\.org|tanzlii\.org|laws\.africa|africanlii\.org|legislation\.gov\.uk|parliament\.go\.ug"
                       r"|constituteproject\.org|treaties\.un\.org|ohchr\.org)$")


def _is_the_law(instrument: str, source: EvidenceSource) -> bool:
    """A conservative candidate for the named instrument, never a host-wide certification.
    A legal publisher also carries judgments and commentary; a report can name an Act in its title.
    The verified passage and provision still have to match below, and meaning remains a review judgement."""
    from urllib.parse import urlsplit

    host = (urlsplit(source.url).hostname or "").casefold().rstrip(".")
    if source.kind == "ARTICLE" or re.search(r"\b(?:brief|commentary|analysis|summary|study|review|judgment|judgement)\b", source.title, re.I):
        return False
    if not (LAW_SITES.search(host) or host.endswith((".go.ug", ".gov.uk", ".gov"))):
        return False
    title = set(re.findall(r"[^\W\d_]+", clean_title(source.title).casefold()))
    words = [w for w in re.findall(r"[^\W\d_]+", instrument.casefold()) if w not in ("the", "of", "and", "for", "on")]
    return bool(words) and all(w in title for w in words)


def _provision_key(text: str) -> str:
    text = re.sub(r"^(?:sub-?)?sections?|^ss?\.", "section", text, flags=re.I)
    text = re.sub(r"^articles?|^art\.", "article", text, flags=re.I)
    return re.sub(r"\W", "", text.casefold())


def _unproved_provision(sentence: str, paragraph: str, library: dict[str, EvidenceItem]) -> tuple[str, str] | None:
    """(the provision, the instrument) when the sentence gives an exact provision of a named law and none of the
    sources cited for it provides a matching verified provision of that law. Every provision is checked;
    an earlier supported number cannot vouch for a later one, and an uncited assertion remains unconfirmed."""
    provisions, instruments = list(PROVISION.finditer(sentence)), list(INSTRUMENT.finditer(sentence))
    if not provisions or not instruments:
        return None
    # A citation in a neighbouring sentence must not vouch for this sentence's provision.
    ids = [i for i in dict.fromkeys(cited_ids(sentence)) if i in library]
    for provision in provisions:
        earlier = [m for m in instruments if m.end() <= provision.start()]
        following = next((m for m in instruments if m.start() >= provision.end()), None)
        # "Section 6 of the Education Act" points forward; "Education Act (Section 6)"
        # points back. Do not attach the latter to a different law later in the sentence.
        instrument = following if following and re.match(r"\s+of\b", sentence[provision.end():], re.I) else earlier[-1] if earlier else following
        if instrument is None:
            continue
        years = re.findall(r"\b(?:19|20)\d{2}\b", sentence[instrument.start():instrument.end() + 8])
        if any(library[i].usable and _is_the_law(instrument.group(1), library[i].source)
               and (not years or all(y in library[i].source.title for y in years))
               and any(_provision_key(p.group()) == _provision_key(provision.group()) for p in PROVISION.finditer(library[i].passage)) for i in ids):
            continue
        return provision.group(0), instrument.group(1).strip()
    return None


def _without_label(sentence: str) -> str:
    def named(match: re.Match[str]) -> str:
        the = match.group(1) or ""
        return (the.capitalize() if match.start() == 0 else the) if the else ""

    return _BRACKETED.sub("", _LABELLED.sub(named, sentence))


def provision_findings(paragraph: str, library: dict[str, EvidenceItem]) -> tuple[list[str], list[str]]:
    """(problems, sentences for the reviewer). A problem where the number can be taken out and the sentence still
    names the law ("Section 6 of the Education Act" becomes "the Education Act"); a sentence for the reviewer where it
    is written some other way, which code leaves exactly as it is."""
    problems, notes = [], []
    for sentence in sentences(paragraph):
        found = _unproved_provision(sentence, paragraph, library)
        if not found:
            continue
        if (_conditional_or_question(sentence) or _quoted(sentence, PROVISION.search(sentence).start())
                or re.search(r"\b(?:according to|claims?|reported|reports|stated|states|argues?|asserts?)\b", sentence, re.I)
                or _DOUBT.search(sentence) or _NEGATION.search(sentence)):
            notes.append(f"Read this legal claim against its cited passage: its exact provision of the {found[1]} is not confirmed from the named law's own text: “{sentence.strip()}”")
        elif _without_label(sentence) != sentence:
            problems.append(f"“{found[0]}” gives an exact provision of the {found[1]} without a verified matching passage in that law itself (it may be on the word of a source that is not the law itself). "
                            "Cite the named law's verified provision, or explicitly attribute the account to its secondary source without asserting the unconfirmed number. Removing a number does not verify the legal meaning.")
        else:
            notes.append(f"PaperAid's code could not confirm this provision of the {found[1]} from the law itself; its cited source is a report about the law: “{sentence.strip()[:400]}”")
    return list(dict.fromkeys(problems)), list(dict.fromkeys(notes))


def provision_problems(paragraph: str, library: dict[str, EvidenceItem]) -> list[str]:
    return provision_findings(paragraph, library)[0]


_NEVER_A_NAME = re.compile(r"(?:The|A|An|In|Within|Under|Across|At|On|By|For|From|This|These|That|Those|Its|Their|Such|Each|Every|Some|Most|Many|All|Both|With|Without)\s")


def drop_provisions(paragraph: str, library: dict[str, EvidenceItem]) -> str:
    """The last line of defence: a provision's number that the repairs left, on the word of a source that is not the
    law, is taken out and the law still named. The same paragraph when there is nothing to take out."""
    out, changed = [], False
    for sentence in sentences(paragraph):
        if (provision_findings(sentence, library)[0] and cited_ids(sentence)
                and (plain := _without_label(sentence)) != sentence):
            # Keep the account explicitly attributed. Removing a wrong number must not transform
            # a secondary source's account into PaperAid's own certification of a legal duty.
            # The sentence's first letter is lowered only for a word that is never a name ("The", "In", "Under"):
            # "Uganda's Education Act" and "UNESCO" keep their capitals, after a colon.
            reports = "The cited sources report" if len(set(cited_ids(sentence))) > 1 else "The cited source reports"
            sentence = f"{reports} that {plain[0].lower()}{plain[1:]}" if _NEVER_A_NAME.match(plain) else f"{reports}: {plain}"
            changed = True
        out.append(sentence)
    return " ".join(out) if changed else paragraph


def row_text(header: list[str], row: list[str]) -> str:
    """A table row read with its headings, as a reader takes it in: "OR = 1.27; 95% CI = 0.56–2.89; p = 0.043"."""
    return "; ".join(f"{h.strip()} = {c.strip()}" if h.strip() else c.strip() for h, c in zip([*header, *[""] * len(row)], row, strict=False) if c.strip())


def row_overclaims(header: list[str], row: list[str]) -> list[int]:
    """The cells of a row that call its result significant while the row, read with its headings, reports a ratio
    whose 95% interval includes 1 at p below 0.05 (a statistic spread across columns). A cell says so in its own
    words ("Significant"), or by its answer under a heading that asks ("Statistically significant?": "Yes")."""
    if not _disagreeing(row_text(header, row)):
        return []
    headings = [*header, *[""] * len(row)]
    return [n for n, cell in enumerate(row) if not _RATIO.search(cell) and (
        _called_significant(cell) or (_called_significant(headings[n]) and bool(_AFFIRMS.fullmatch(cell.strip()))))]


COPIED_RUN = 10  # words in a row


def _word_spans(text: str) -> list[tuple[str, int, int]]:
    """The words of a text with where each stands; citation and number tokens are not words and break a run."""
    blanked = ANY_TOKEN.sub(lambda m: "\x00" * len(m.group(0)), text)
    return [(m.group(0).casefold(), m.start(), m.end()) for m in re.finditer(r"[^\W_]+(?:['’][^\W_]+)*|\x00+", blanked)]


def _copied_run(sentence: str, passages: list[str], quoted: list[tuple[int, int]] | None = None) -> tuple[int, int, int] | None:
    """The longest run of a source's own words in the sentence, outside quotation marks: (words, start, end) in the
    sentence, or None when no run reaches COPIED_RUN."""
    spans = _word_spans(sentence)
    quoted = [(m.start(), m.end()) for m in _QUOTATION.finditer(sentence)] if quoted is None else quoted
    # Quoted words BREAK a match; they are excluded before choosing the longest run. Otherwise a long quotation
    # hides a shorter unquoted passage, and adding quotation marks makes the check falsely report no problem.
    mine = ["\x00" if any(low <= start < high for low, high in quoted) else word for word, start, _ in spans]
    best: tuple[int, int, int] | None = None
    for passage in passages:
        theirs = [w for w, _, _ in _word_spans(passage)]
        previous = [0] * (len(theirs) + 1)
        for i, word in enumerate(mine, start=1):
            current = [0] * (len(theirs) + 1)
            for j, other in enumerate(theirs, start=1):
                if word == other and not word.startswith("\x00"):
                    current[j] = previous[j - 1] + 1
                    if current[j] >= COPIED_RUN and (best is None or current[j] > best[0]):
                        best = (current[j], spans[i - current[j]][1], spans[i - 1][2])
            previous = current
    return best


def _copy_sentences(paragraph: str) -> Iterable[tuple[int, str, list[tuple[int, int]]]]:
    """Sentence-local quote positions, including quotations that span a sentence boundary."""
    quoted = [(m.start(), m.end()) for m in _QUOTATION.finditer(paragraph)]
    offset = 0
    for sentence in sentences(paragraph):
        start = paragraph.find(sentence, offset)
        end = start + len(sentence)
        yield start, sentence, [(max(0, low - start), min(len(sentence), high - start)) for low, high in quoted if low < end and high > start]
        offset = end


def _passages_for(sentence: str, paragraph: str, library: dict[str, EvidenceItem]) -> list[str]:
    ids = cited_ids(sentence) or cited_ids(paragraph)
    return [library[i].passage for i in dict.fromkeys(ids) if i in library and library[i].passage]


def copied_problems(paragraph: str, library: dict[str, EvidenceItem]) -> list[str]:
    """Sentences that carry COPIED_RUN or more words in a row from the passage of a source they cite, outside
    quotation marks. A citation does not make a source's own wording the student's: it is paraphrased or quoted
    (the quality round of 2026-10-11 found runs of 22 words, in 20 of one coursework's 57 sentences)."""
    problems = []
    for _, sentence, quoted in _copy_sentences(paragraph):
        found = _copied_run(sentence, _passages_for(sentence, paragraph, library), quoted)
        if found:
            opening = " ".join(sentence[found[1]:found[2]].split()[:6])
            problems.append(f"A sentence carries {found[0]} words in a row from its source's own wording (“{opening} ...”). Say it in your own words, or keep the exact "
                            "words short and inside quotation marks.")
    return problems


def quote_copied(paragraph: str, library: dict[str, EvidenceItem]) -> str:
    """The last line of defence for copied wording: what the repair rounds left is marked as the quotation it is,
    so nothing printed passes a source's words off as the student's. Nothing else changes; the same paragraph when
    there is nothing to mark."""
    mark: list[tuple[int, int]] = []
    for start, sentence, quoted in _copy_sentences(paragraph):
        passages = _passages_for(sentence, paragraph, library)
        while (found := _copied_run(sentence, passages, quoted)) is not None:
            mark.append((start + found[1], start + found[2]))
            quoted.append((found[1], found[2]))  # each iteration excludes its run: no arbitrary three-run limit
    for low, high in sorted(mark, reverse=True):  # original offsets and all unrelated whitespace stay intact
        paragraph = f"{paragraph[:low]}“{paragraph[low:high]}”{paragraph[high:]}"
    return paragraph


def repeated_sentences(texts: list[tuple[str, list[str]]]) -> dict[str, list[str]]:
    """By section key, the sentences (ten words or more) that an earlier section has already said word for word.
    `texts`: each section's key and paragraphs, in the document's order."""
    seen: dict[str, str] = {}
    found: dict[str, list[str]] = {}
    for key, paragraphs in texts:
        for paragraph in paragraphs:
            for sentence in sentences(paragraph):
                words = [w for w, _, _ in _word_spans(sentence) if not w.startswith("\x00")]
                if len(words) < 10:
                    continue
                same = " ".join(words)
                if same in seen and seen[same] != key:
                    found.setdefault(key, []).append(f"This sentence was already said, word for word, in an earlier section: “{sentence.strip()[:160]}”. Say it once, "
                                                     "and here say something that takes the argument further.")
                seen.setdefault(same, key)
    return {key: list(dict.fromkeys(problems))[:3] for key, problems in found.items()}


_NUMBERED = re.compile(r"\s*(?:table|figure|fig\.)\s*\d+(?:\.\d+)*\s*[:.–—-]\s*", re.I)


def caption_text(caption: str) -> str:
    """A table's or figure's caption without a number of its own. Code numbers them, once, in the order they print:
    a writer's "Table 3.1: Work Plan" printed as "Table 3.1: Table 3.1: Work Plan" (independent audit, 2026-10-12)."""
    return _NUMBERED.sub("", caption, count=1) if _NUMBERED.match(caption) else caption


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
