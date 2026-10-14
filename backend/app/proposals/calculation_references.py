"""Bibliographic attribution for the named formulas implemented by sampling.py.

Identity metadata checked 2026-10-13: Crossref for Krejcie/Morgan, Wiley's catalogue
for Cochran, and the scanned book's Google Books record for Yamane. These are
references to code's mathematical method, never fabricated verified evidence items.
Freeze the chosen record in a step/document; older documents keep their old rendering.
"""

import re

from app.proposals.evidence import Citer
from app.proposals.models import EvidenceSource

_SOURCES = {
    "KREJCIE_MORGAN": dict(url="https://doi.org/10.1177/001316447003000308", doi="10.1177/001316447003000308",
                         title="Determining sample size for research activities", authors=["Krejcie, R. V.", "Morgan, D. W."], year="1970",
                         container="Educational and Psychological Measurement", volume="30", issue="3", pages="607–610", kind="ARTICLE", metadata="CROSSREF"),
    "COCHRAN": dict(url="https://www.wiley-vch.de/en/areas-interest/mathematics-statistics/sampling-techniques-978-0-471-16240-7",
                    title="Sampling techniques (3rd ed.)", authors=["Cochran, W. G."], year="1977", container="John Wiley & Sons", kind="BOOK", metadata="PAGE"),
    "YAMANE": dict(url="https://books.google.com/books/about/Statistics.html?id=Wr7rAAAAMAAJ", title="Statistics: An introductory analysis (2nd ed.)",
                   authors=["Yamane, T."], year="1967", container="Harper & Row", kind="BOOK", metadata="PAGE"),
}


def source(method: str) -> EvidenceSource | None:
    return EvidenceSource.model_validate(_SOURCES[method]) if method in _SOURCES else None


def _mention(reference: EvidenceSource) -> re.Pattern[str]:
    names = [re.escape(a.partition(",")[0]) for a in reference.authors]
    return re.compile(r"\b" + r"\s+(?:and|&)\s+".join(names) + r"(?:['’]s)?\b", re.I)


def has_mention(texts: list[str], reference: EvidenceSource | None) -> bool:
    return reference is not None and any(_mention(reference).search(t) for t in texts)


def render(text: str, reference: EvidenceSource | None, citer: Citer) -> str:
    """Add the year to an already-written attribution; no new empirical assertion."""
    if reference is None:
        return text
    match = _mention(reference).search(text)
    if match is None or re.match(r"\s*\((?:19|20)\d{2}", text[match.end():]):
        return text
    label = citer.cite([reference], narrative=True)
    year = label[label.rfind(" ("):]
    return text[:match.end()] + year + text[match.end():]
