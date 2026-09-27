"""Paper-quality checks: in-text citations against the reference list, and spelling conventions.

These are about the paper's integrity, not AI-likeness, and are reported separately (owner
decision 2026-09-27). Every result says how sure it is:
  CONFIRMED    both sides were read clearly and they do not match;
  POSSIBLE     probably a mismatch (a different year, a near-identical name);
  UNDETERMINED PaperAid could not read the citation or reference reliably, so it makes no claim.
Nothing here edits the paper, and uncertain metadata is never "fixed" by guessing. Citation
fields from reference managers are read from their visible text and left untouched.
"""

import re
from difflib import SequenceMatcher

from app.documents.model import DocumentModel
from app.jobs.models import PaperCheck, PaperChecks

METHOD = "PaperAid citation and reference checks (author and year matching)"
MAX_ITEMS = 40

YEAR = r"(?:1[89]\d{2}|20\d{2})[a-z]?|n\.d\."
PARENTHETICAL = re.compile(r"\(([^()]*?(?:\b(?:1[89]\d{2}|20\d{2})[a-z]?\b|n\.d\.)[^()]*)\)")
PARTICLES = {"van", "von", "der", "den", "de", "del", "della", "da", "di", "du", "le", "la", "dos", "das", "ter", "ten", "bin", "al", "el"}
JOINERS = {"of", "for", "on", "and", "the"}
# Words that can open a sentence before a narrative citation ("As Kato (2018) noted").
LEADING = {"as", "in", "the", "according", "to", "while", "however", "although", "since", "when", "both", "recently", "earlier", "later",
           "following", "like", "unlike", "by", "from", "and", "but", "yet", "also", "thus", "indeed", "similarly", "see", "for", "work"}
NAME_WORD = r"(?:[A-Z][\w'’-]+|" + "|".join(sorted(PARTICLES)) + ")"
# A narrative citation: a run of name words (an organisation's full name, or a surname with its
# particles), optionally "and"/"&" a second author or "et al.", then (year).
NARRATIVE = re.compile(rf"\b({NAME_WORD}(?:\s+(?:{NAME_WORD}|of|for|on|and|&))*?)(?:\s+et\s+al\.?)?\s+\(({YEAR})(?:,[^)]*)?\)")
PARTICLE_PREFIX = r"(?:(?:" + "|".join(sorted(PARTICLES)) + r")\s+)*"
CITED_PART = re.compile(rf"^(?:(?:see|e\.g\.|cf\.|as cited in)[,\s]+)*(?P<author>{PARTICLE_PREFIX}[A-Z][^,;()]*?)(?:,)?\s+(?P<years>(?:{YEAR})(?:\s*,\s*(?:{YEAR}))*)(?:\s*,\s*(?:p|pp)\..*)?$")
NUMERIC = re.compile(r"\[(\d+(?:\s*[,–-]\s*\d+)*)\]")
REF_YEAR = re.compile(rf"\(({YEAR})\)|\b({YEAR})\b")
REF_NUMBER = re.compile(r"^\s*(?:\[(\d+)\]|(\d+)\.)\s")
FIRST_NAME = re.compile(r"[A-Za-zÀ-ÿ][\w'’-]*")

SPELLING_PAIRS = [
    ("colour", "color"), ("behaviour", "behavior"), ("centre", "center"), ("organisation", "organization"), ("analyse", "analyze"),
    ("labour", "labor"), ("favour", "favor"), ("recognise", "recognize"), ("emphasise", "emphasize"), ("utilise", "utilize"),
    ("realise", "realize"), ("minimise", "minimize"), ("prioritise", "prioritize"), ("characterise", "characterize"), ("modelling", "modeling"),
]


def _words(text: str) -> list[str]:
    return [w.replace("’", "'") for w in FIRST_NAME.findall(text)]


def _surname(author: str) -> str:
    """The matching key of an author: the first name word after any sentence opener, skipping
    particles ("van der Berg" → "berg")."""
    words = _words(author)
    while words and words[0].lower() in LEADING and len(words) > 1:
        words = words[1:]
    return next((w.lower() for w in words if w.lower() not in PARTICLES and w.lower() not in JOINERS), "")


def _organisation(author: str) -> bool:
    """Three or more capitalised name words: probably an organisation, whose many written forms
    ("WHO", "World Health Organization") this checker cannot always match with certainty."""
    return sum(1 for w in _words(author) if w[:1].isupper() and w.lower() not in LEADING) >= 3


def _aliases(author: str) -> set[str]:
    """Every key a reference can be cited by: its first name word, an acronym given in brackets,
    and an organisation's initials ("World Health Organization" → "who")."""
    keys = {_surname(author)}
    keys.update(a.lower() for a in re.findall(r"\(([A-Z]{2,})\)", author))
    if _organisation(author):
        name = re.split(r"[.(]", author)[0]
        keys.add("".join(w[0] for w in _words(name) if w[:1].isupper() and w.lower() not in JOINERS).lower())
    return keys - {""}


def _citations(model: DocumentModel) -> tuple[list[tuple[str, str, str, bool]], list[str], list[int]]:
    """(key, year, as written, organisation-like) for each author–date citation; unreadable
    citation-like text; numbers cited in [n] style."""
    found: list[tuple[str, str, str, bool]] = []
    unreadable: list[str] = []
    numbers: list[int] = []
    for block in model.blocks:
        if block.kind in ("reference", "heading", "title"):
            continue
        text = block.text
        for match in PARENTHETICAL.finditer(text):
            for part in match.group(1).split(";"):
                part = part.strip()
                cited = CITED_PART.match(part)
                if re.match(r"(?i)(?:ibid|op\.? cit|loc\.? cit)", part):
                    unreadable.append(f"({part})")
                elif cited:
                    author = cited.group("author")
                    for year in re.split(r"\s*,\s*", cited.group("years")):
                        found.append((_surname(author), year, f"({part})", _organisation(author)))
                elif re.search(r"et al|&|\band\b", part):
                    unreadable.append(f"({part})")
                # anything else with a year in brackets ("conducted in 2019") is not a citation
        for match in NARRATIVE.finditer(text):
            key = _surname(match.group(1))
            if key:
                found.append((key, match.group(2), match.group(0), _organisation(match.group(1))))
        for match in NUMERIC.finditer(text):
            for piece in re.split(r"\s*,\s*", match.group(1)):
                bounds = re.split(r"\s*[–-]\s*", piece)
                if len(bounds) == 2 and bounds[0].isdigit() and bounds[1].isdigit() and int(bounds[1]) - int(bounds[0]) < 50:
                    numbers.extend(range(int(bounds[0]), int(bounds[1]) + 1))
                elif piece.isdigit():
                    numbers.append(int(piece))
    unique = list(dict.fromkeys(found))
    return unique, list(dict.fromkeys(unreadable)), sorted(set(numbers))


def _references(model: DocumentModel) -> tuple[list[tuple[set[str], str, str, bool]], list[str], list[int]]:
    """(keys, year, entry, organisation-like) for each readable reference; unreadable entries;
    entry numbers."""
    readable: list[tuple[set[str], str, str, bool]] = []
    unreadable: list[str] = []
    numbered: list[int] = []
    for block in model.blocks:
        if block.kind != "reference" or not block.text.strip():
            continue
        entry = block.text.strip()
        number = REF_NUMBER.match(entry)
        if number:
            numbered.append(int(number.group(1) or number.group(2)))
            entry_body = entry[number.end() :]
        else:
            entry_body = entry
        year = REF_YEAR.search(entry_body)
        author = entry_body[: year.start()] if year else entry_body
        keys = _aliases(author)
        if year and keys:
            readable.append((keys, year.group(1) or year.group(2), entry, _organisation(author)))
        else:
            unreadable.append(entry)
    return readable, unreadable, numbered


def _short(text: str, limit: int = 160) -> str:
    return text if len(text) <= limit else text[: limit - 1].rsplit(" ", 1)[0] + "…"


def _similar(a: str, b: str) -> bool:
    return a != b and SequenceMatcher(None, a, b).ratio() >= 0.8


def check(model: DocumentModel) -> PaperChecks:
    citations, unreadable_citations, numbers = _citations(model)
    references, unreadable_references, numbered = _references(model)
    reference_count = len(references) + len(unreadable_references)
    items: list[PaperCheck] = []
    style = "NUMERIC" if numbers and len(numbers) > len(citations) else "AUTHOR_DATE" if citations else "UNKNOWN"

    if style == "NUMERIC":
        if not reference_count:
            items.append(PaperCheck(kind="NO_REFERENCE_LIST", certainty="UNDETERMINED", item="", detail="Numbered citations were found, but no reference list, so they could not be checked."))
        elif len(numbered) < 0.7 * reference_count:
            items.append(PaperCheck(kind="UNREADABLE_REFERENCE", certainty="UNDETERMINED", item="", detail="Your citations are numbered, but the reference list isn't, so the numbers could not be matched."))
        else:
            for n in numbers:
                if n not in numbered:
                    items.append(PaperCheck(kind="CITED_NOT_LISTED", certainty="CONFIRMED", item=f"[{n}]", detail=f"[{n}] is cited, but the reference list has no entry {n}."))
            for n in numbered:
                if n not in numbers:
                    items.append(PaperCheck(kind="LISTED_NOT_CITED", certainty="CONFIRMED", item=f"[{n}]", detail=f"Reference {n} is never cited in the text."))
    elif citations:
        if not reference_count:
            items.append(PaperCheck(kind="NO_REFERENCE_LIST", certainty="UNDETERMINED", item="", detail="No reference list was found under a References or Bibliography heading, so citations could not be checked."))
        else:
            # Confirmed claims need both sides read well; otherwise a mismatch is only possible.
            reliable = len(references) >= 0.7 * reference_count and len(unreadable_citations) <= 0.2 * max(1, len(citations))
            listed = {(key, y) for keys, y, _, _ in references for key in keys}
            cited = {(s, y) for s, y, _, _ in citations}
            for surname, year, written, org in citations:
                if (surname, year) in listed:
                    continue
                near = [entry for keys, y, entry, _ in references if surname in keys or any(y == year and _similar(k, surname) for k in keys)]
                if near:
                    items.append(PaperCheck(kind="CITED_NOT_LISTED", certainty="POSSIBLE", item=written, detail=f"The closest reference is “{_short(near[0])}”. Check the name and year match."))
                else:
                    # An organisation can be written many ways, so a miss is only ever possible.
                    sure = reliable and not org
                    items.append(PaperCheck(kind="CITED_NOT_LISTED", certainty="CONFIRMED" if sure else "POSSIBLE", item=written, detail="This citation has no matching entry in your reference list."))
            for keys, year, entry, org in references:
                if any((key, year) in cited for key in keys):
                    continue
                near_cited = any(s in keys or (y == year and any(_similar(k, s) for k in keys)) for s, y in cited)
                items.append(
                    PaperCheck(
                        kind="LISTED_NOT_CITED",
                        certainty="POSSIBLE" if near_cited or org or not reliable else "CONFIRMED",
                        item=_short(entry),
                        detail="This reference is not cited in the text" + (" under this name and year." if near_cited else "."),
                    )
                )
    elif reference_count:
        items.append(
            PaperCheck(
                kind="UNREADABLE_CITATION",
                certainty="UNDETERMINED",
                item="",
                detail="No in-text citations were recognised, so your reference list could not be checked against the text. If your paper cites sources, check each one appears in the list.",
            )
        )
    for text in unreadable_citations[:10]:
        items.append(PaperCheck(kind="UNREADABLE_CITATION", certainty="UNDETERMINED", item=text, detail="PaperAid could not read this citation reliably, so it was not checked."))
    for entry in unreadable_references[:10]:
        items.append(PaperCheck(kind="UNREADABLE_REFERENCE", certainty="UNDETERMINED", item=_short(entry), detail="PaperAid could not find an author and year in this reference, so it was not checked."))

    prose = " ".join(b.text.lower() for b in model.blocks if b.kind not in ("reference",))
    british = [uk for uk, us in SPELLING_PAIRS if re.search(rf"\b{uk}", prose)]
    american = [us for uk, us in SPELLING_PAIRS if re.search(rf"\b{us}", prose)]
    if british and american:
        items.append(
            PaperCheck(
                kind="SPELLING_MIXED",
                certainty="CONFIRMED",
                item="",
                detail=f"British spellings ({', '.join(british[:3])}) and American spellings ({', '.join(american[:3])}) are both used. Choose one convention.",
            )
        )

    order = {"CONFIRMED": 0, "POSSIBLE": 1, "UNDETERMINED": 2}
    items.sort(key=lambda i: order[i.certainty])
    return PaperChecks(
        citations_found=len(citations) + len(numbers),
        references_found=reference_count,
        style=style,  # type: ignore[arg-type]
        items=items[:MAX_ITEMS],
        method=METHOD,
    )
