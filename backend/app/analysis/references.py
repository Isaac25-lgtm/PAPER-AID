"""Reference verification (master context §36-37, §114, §116): does each work in the paper's
reference list exist as written? No AI: each entry is matched against registered bibliographic
records (Crossref, by DOI or by bibliographic search), comparing title, first author and year.

Deliberately careful wording: a reference PaperAid cannot find is "could not verify", never
"fabricated" (books, local reports and grey literature are often not registered anywhere), and a
verified reference only means the work exists; whether it supports a claim is the source check's
question. Retractions come from Crossref's registered notices and OpenAlex."""

import re
from concurrent.futures import ThreadPoolExecutor
from difflib import SequenceMatcher

from app.analysis import fetch
from app.documents.model import DocumentModel
from app.jobs.models import ReferenceCheck, ReferenceVerification, utcnow

MAX_REFERENCES = 60
WORKERS = 6
DOI = re.compile(r"\b(10\.\d{4,9}/[^\s\"<>]+[^\s\"<>.,;)\]])", re.I)
YEAR_WORD = re.compile(r"(?:1[5-9]|20)\d{2}[a-z]?")  # one normalised word that is a year ("2016" or "2016a")
NUMBERING = re.compile(r"^\s*(?:\[\d+\]|\d+[.)])\s*")


def _norm(text: str) -> str:
    return " ".join(re.findall(r"\w+", text.casefold()))


def _similar(a: str, b: str) -> float:
    a, b = _norm(a), _norm(b)
    if not a or not b:
        return 0.0
    if a in b or b in a:  # a subtitle omitted on one side
        return 0.95 if min(len(a), len(b)) > 20 else 0.8
    return SequenceMatcher(None, a, b).ratio()


UNAVAILABLE = "PaperAid could not reach the registry of published works just now, so this reference was not checked. Check it yourself or try again later."


def _title_span(words: list[str], title: str) -> tuple[float, int, int]:
    """Where a registered title sits in a reference, in any style (owner, 2026-11-17, after PaperAid Pro): the best
    fuzzy match of the title against windows of the reference's words, as (score, first word, end word). A subtitle
    left out on one side still matches its main title."""
    best = (0.0, 0, 0)
    for candidate in {title, title.split(":")[0]}:
        target = _norm(candidate)
        size = len(target.split())
        if not target or not words or size < 2:
            continue
        for start in range(0, max(1, len(words) - size + 1)):
            for width in (size - 1, size, size + 1, size + 2):
                if width < 1:
                    continue
                window = " ".join(words[start:start + width])
                score = 1.0 if window == target else SequenceMatcher(None, window, target).ratio()
                if score > best[0]:
                    best = (score, start, start + width)
    return best


def _first_author_ok(before_title: list[str], first: str) -> bool | None:
    """The reference's first listed author is the registered first author: the surname of "Surname, I.", or an
    organisation's whole name (Codex audit 56c4f83 M22: never a later author). Leading initials are skipped, as in
    IEEE's "J. Smith". None when either side names no author."""
    registered = _norm(first.split(",")[0]) if "," in first else _norm(first)
    names = list(before_title)
    while names and len(names[0]) == 1:
        names.pop(0)
    if not names or not registered:
        return None
    family = registered.split()
    if names[:len(family)] == family:
        return True
    return "," not in first and (registered in " ".join(names[:len(family) + 3]))  # an organisation written a little differently


def _read(entry: str, record: dict[str, str]) -> tuple[float, str, bool | None]:
    """How a reference reads against one registered record, in any referencing style: (title score, the year it
    gives, whether its first author is the registered one). Authors come before the title in APA, Harvard,
    Vancouver, IEEE, MLA and Chicago; the year is read only outside the title, so a year inside a title never
    counts as the publication year."""
    words = _norm(NUMBERING.sub("", entry)).split()
    score, start, end = _title_span(words, record.get("title", ""))
    if score < 0.6:
        start = end = 0
    outside = words[:start] + words[end:]
    years = [w[:4] for w in outside if YEAR_WORD.fullmatch(w)]
    first = (record.get("authors") or "").split(";")[0].strip()
    return score, years[0] if years else "", _first_author_ok(words[:start], first) if score >= 0.6 else None


def _rank(entry: str, record: dict[str, str]) -> float:
    score, year, author = _read(entry, record)
    registered = record.get("year", "")
    year_ok = None if not (year and registered) else year == registered
    return score + sum(0.1 for ok in (year_ok, author) if ok) - sum(0.2 for ok in (year_ok, author) if ok is False)


def verify(entry: str) -> ReferenceCheck:
    doi_match = DOI.search(entry)
    candidates: list[dict[str, str]] = []
    if doi_match:
        found, record = fetch.crossref_lookup(doi_match.group(1).rstrip(".").lower())
        if found == "UNAVAILABLE":
            return ReferenceCheck(entry=entry, status="NOT_VERIFIED", doi=doi_match.group(1), note=UNAVAILABLE)
        if found == "NOT_FOUND" or not record or not record.get("title"):
            return ReferenceCheck(entry=entry, status="NOT_VERIFIED", doi=doi_match.group(1), note="This DOI is not registered. Check it is typed correctly.")
        candidates = [record]
    if not candidates:
        searched = fetch.crossref_search(entry, rows=5)
        if searched is None:
            return ReferenceCheck(entry=entry, status="NOT_VERIFIED", note=UNAVAILABLE)
        candidates = [r for r in searched if r.get("title")]
    best = max(candidates, key=lambda r: _rank(entry, r), default=None)
    best_score, year, author = _read(entry, best) if best else (0.0, "", None)
    if best is None or best_score < 0.6:
        return ReferenceCheck(entry=entry, status="NOT_VERIFIED", note="No registered record matches this reference. It may be a book, report or source that is not registered, so check it yourself.")
    first = best["authors"].split(";")[0].strip()
    differences = []
    if year and best["year"] and year != best["year"]:
        differences.append(f"the registered year is {best['year']}, not {year}")
    if author is False:
        differences.append(f"the registered first author is {first}")
    if best_score < 0.85:
        differences.append(f"the registered title is “{best['title']}”")
    if doi_match and not differences and author is True and year and best["year"]:
        status = "VERIFIED"
    elif not differences:
        status = "PROBABLE"
    else:
        status = "MISMATCH"
    retracted = bool(best.get("retracted"))
    if best.get("doi") and not retracted:
        retracted = fetch.openalex_retracted(best["doi"]) is True
    note = "Details differ: " + "; ".join(differences) + "." if differences else ""
    if retracted:
        note = ("This work has been retracted. " + note).strip()
    return ReferenceCheck(
        entry=entry, status=status, doi=best.get("doi", ""), matched_title=best["title"], matched_year=best["year"], retracted=retracted, note=note
    )


def verify_all(model: DocumentModel) -> ReferenceVerification | None:
    entries = [b.text.strip() for b in model.blocks if b.kind == "reference" and len(b.text.split()) >= 4]
    if not entries:
        return None
    chosen = entries[:MAX_REFERENCES]
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        items = list(pool.map(verify, chosen))
    return ReferenceVerification(items=items, checked=len(items), total=len(entries), retrieved_on=utcnow().date().isoformat())
