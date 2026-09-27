"""The code-enforced rules of the source check (phase 4 of the revised algorithm).

What the models may do is set by prompts; what must never happen is enforced here:
- Data minimisation: the searching step only ever receives a claim and a search query that
  passed these checks, never the paper. A claim built on the paper's own unpublished results, or
  a query carrying contact details or names from the front matter, is dropped before any search.
- A source is accepted only if its URL is one the search actually opened (no invented URLs).
- Verdicts combine cautiously: when the searching model and the checking model disagree, the
  claim is UNCERTAIN, never quietly promoted.
- "Not found" means a limited search found no support; it is never presented as "no research
  exists" (Codex review, 2026-09-27).
"""

import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from app.analysis import signals
from app.documents.model import DocumentModel

MAX_CLAIM_CHARS = 400
MAX_QUERY_CHARS = 150
CONTACT = re.compile(r"@|https?://|www\.|\+?\d[\d\s-]{8,}\d")
NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")
OWN_DATA_SECTIONS = ("methods", "results")


def claims_for(words: int, cap: int) -> int:
    """How many claims a paper of this length gets checked: 3, plus one per 400 words, up to `cap`."""
    return max(0, min(cap, 3 + words // 400))


def own_numbers(model: DocumentModel) -> set[str]:
    """Figures from the paper's own methods and results: its unpublished findings."""
    found: set[str] = set()
    for block in model.blocks:
        if block.kind in ("paragraph", "list_item", "table_cell", "caption") and signals.section_type(block.section) in OWN_DATA_SECTIONS:
            found.update(n.replace(",", "") for n in NUMBER.findall(block.text) if len(n.replace(",", "")) >= 2)
    return found


def front_matter_names(model: DocumentModel) -> set[str]:
    """Capitalised words that appear before the first heading other than in the title: author,
    supervisor, student number and institution lines. None of them may reach a search."""
    names: set[str] = set()
    for block in model.blocks[:12]:  # front matter is short lines at the top of the paper
        if block.kind == "heading":
            break
        if block.kind == "title" or block.words > 25:
            continue
        names.update(w.lower() for w in re.findall(r"\b[A-Z][a-z'’-]+", block.text))
    return names - signals.STOPWORDS


def safe_to_search(claim: str, query: str, own: set[str], names: set[str]) -> bool:
    if not claim.strip() or not query.strip() or len(query) > MAX_QUERY_CHARS or len(claim) > MAX_CLAIM_CHARS:
        return False
    if CONTACT.search(query) or CONTACT.search(claim):
        return False
    figures = {n.replace(",", "") for n in NUMBER.findall(claim + " " + query)}
    if figures & own:  # the paper's own finding: not something the web can confirm, and unpublished
        return False
    query_words = {w.lower() for w in re.findall(r"[A-Za-z'’-]+", query)}
    return not (query_words & names)


def verbatim(claim: str, text: str) -> bool:
    """The claim must be quoted from the passage (ignoring spacing and quote styles)."""

    def norm(value: str) -> str:
        return re.sub(r"\s+", " ", value.replace("’", "'").replace("“", '"').replace("”", '"')).strip().lower()

    return bool(claim.strip()) and norm(claim) in norm(text)


def normalise_url(url: str) -> str:
    """Scheme and host in lower case, no fragment, no tracking parameters, no trailing slash."""
    parts = urlsplit(url.strip())
    query = urlencode([(k, v) for k, v in parse_qsl(parts.query) if not k.lower().startswith("utm_")])
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path.rstrip("/"), query, ""))


def opened(url: str, sources: list[str]) -> bool:
    target = normalise_url(url)
    return bool(target) and any(normalise_url(s) == target for s in sources)


def combine(searched: str, checked: str | None) -> str:
    """The final support level from the searching model's verdict and the checking model's."""
    if searched == "NOT_FOUND":
        return "NOT_FOUND"
    if checked is None:  # the check did not happen: the search alone is not enough to confirm
        return "UNCERTAIN"
    if searched == checked:
        return searched
    if {searched, checked} == {"SUPPORTED", "PARTLY_SUPPORTED"}:
        return "PARTLY_SUPPORTED"
    return "UNCERTAIN"
