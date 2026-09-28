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
YEAR = re.compile(r"\((?:19|20)\d{2}[a-z]?\)|\b(?:19|20)\d{2}[a-z]?\b")
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


def _same_author(surname: str, first: str) -> bool:
    """The reference's first author is the registered first author (Codex audit 56c4f83 M22): the
    surname of "Surname, I." or, for an organisation, its whole name. Never a later author, and never
    the journal's name."""
    registered = _norm(first.split(",")[0]) if "," in first else _norm(first)
    given = _norm(surname)
    return bool(given and registered) and (given == registered or ("," not in first and (given in registered or registered in given)))


def _parts(entry: str) -> tuple[str, str, str]:
    """(first author's surname, year, title) as best they can be read from an author-date entry."""
    body = NUMBERING.sub("", entry)
    year_match = YEAR.search(body)
    year = re.sub(r"\D", "", year_match.group(0))[:4] if year_match else ""
    surname = re.split(r"[,.(&]", body, maxsplit=1)[0].strip()
    after = body[year_match.end() :] if year_match else body
    after = after.lstrip(" ).,:")
    title = re.split(r"(?<=[a-z0-9?!])\.\s+(?=[A-Z])", after, maxsplit=1)[0]
    return surname, year, title.strip(" .")


def verify(entry: str) -> ReferenceCheck:
    surname, year, title = _parts(entry)
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
        searched = fetch.crossref_search(entry)
        if searched is None:
            return ReferenceCheck(entry=entry, status="NOT_VERIFIED", note=UNAVAILABLE)
        candidates = searched
    best, best_score = None, 0.0
    for record in candidates:
        score = _similar(title, record["title"]) if title else 0.0
        if score > best_score:
            best, best_score = record, score
    if best is None or best_score < 0.6:
        return ReferenceCheck(entry=entry, status="NOT_VERIFIED", note="No registered record matches this reference. It may be a book, report or source that is not registered, so check it yourself.")
    first = best["authors"].split(";")[0].strip()
    author_known = bool(surname and first)  # both sides name a first author: otherwise it cannot be confirmed
    author_ok = not author_known or _same_author(surname, first)
    year_ok = not year or not best["year"] or year == best["year"]
    differences = []
    if not year_ok:
        differences.append(f"the registered year is {best['year']}, not {year}")
    if not author_ok:
        differences.append(f"the registered first author is {first}")
    if best_score < 0.85:
        differences.append(f"the registered title is “{best['title']}”")
    if doi_match and not differences and author_known and year and best["year"]:
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
