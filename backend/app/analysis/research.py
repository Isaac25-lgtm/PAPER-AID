"""The code-enforced rules of the source check (phase 4 of the revised algorithm).

What the models may do is set by prompts; what must never happen is enforced here:
- Data minimisation: the searching step only ever receives a claim and a search query that
  passed these checks, never the paper. A claim built on the paper's own unpublished results, or
  a query carrying contact details or names from the front matter, is dropped before any search.
- A source is accepted only if its URL is among the search's results (no invented URLs), and its
  quotation counts only when PaperAid finds it on the page itself (`quote_found`); an unconfirmed
  quotation can never make a claim supported or contradicted.
- The queries the search actually sent are checked after the fact too; results from a search that
  broke these rules are discarded.
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
# The paper reporting its own, unpublished work: never searched.
OWN_WORK = re.compile(
    r"\b(?:[Ww]e|[Oo]ur|us)\b"  # case-aware, so "US" (the country) is not the author speaking
    r"|\b(?i:(?:this|the present|the current) (?:study|research|paper|thesis|dissertation|survey|project))\b"
    r"|\b(?i:(?:the|these) (?:respondents|participants|interviewees|informants))\b"
)


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


def _words(text: str) -> set[str]:
    return {w.lower() for w in re.findall(r"[A-Za-z'’-]+", text)}


def query_safe(query: str, own: set[str], names: set[str]) -> bool:
    """A search query (suggested, or actually sent by the model) that carries nothing private."""
    if not query.strip() or len(query) > MAX_QUERY_CHARS or CONTACT.search(query) or OWN_WORK.search(query):
        return False
    if {n.replace(",", "") for n in NUMBER.findall(query)} & own:
        return False
    return not (_words(query) & names)


def safe_to_search(claim: str, query: str, own: set[str], names: set[str]) -> bool:
    """Both the claim (which the searching model sees) and its query must be free of private names,
    contact details, the paper's own result figures and its own unpublished work."""
    if not claim.strip() or len(claim) > MAX_CLAIM_CHARS or CONTACT.search(claim) or OWN_WORK.search(claim):
        return False
    if {n.replace(",", "") for n in NUMBER.findall(claim)} & own or _words(claim) & names:
        return False
    return query_safe(query, own, names)


ELLIPSIS = re.compile(r"\s*(?:\.\s?\.\s?\.|…|\[\s*(?:\.\.\.|…)\s*\])\s*")


def _norm_words(text: str) -> list[str]:
    """Words for comparison: case-folded, in any script, with typography and line-end hyphenation
    undone. Every word and number is kept, so "not", "did" and figures always count."""
    text = re.sub(r"(\w)-\s*\n\s*(\w)", r"\1\2", text)  # a word hyphenated across a PDF line is one word
    return re.findall(r"\w+|%", text.casefold())


def quote_found(passage: str, page: str) -> bool:
    """The quotation appears on the page as one contiguous passage, word for word (Codex audit #4,
    second round: a fuzzy match accepted "did improve" for "did not improve"). Only typography,
    case, spacing and line-end hyphenation may differ. A quotation shortened with an ellipsis must
    have every part, each at least four words, on the page in the same order. Anything less is
    not a confirmed quotation."""
    parts = [_norm_words(p) for p in ELLIPSIS.split(passage) if p.strip()]
    if not parts or any(len(p) < 4 for p in parts):
        return False  # too short to confirm anything
    page_text = " " + " ".join(_norm_words(page)) + " "
    position = 0
    for part in parts:
        found = page_text.find(" " + " ".join(part) + " ", position)
        if found < 0:
            return False
        position = found + 1
    return True


def rank_works(works: list[dict[str, str]], need: str, query: str, keep: int) -> list[dict[str, str]]:
    """The works of an index search most likely to answer a need, best first (algorithm revision 2026-10-09). The
    index's own order (its relevance) is the base. A work gains for carrying the need's and the query's words in its
    title and abstract, and for naming the places and groups the need names, so local evidence is not displaced by a
    better-known study of somewhere else. Age costs nothing: a foundational work stays. Retracted works and repeats
    of one work are left out."""
    wanted = {w for w in _words(need + " " + query) if len(w) > 3} - signals.STOPWORDS
    named = {w.lower() for w in re.findall(r"(?<!^)(?<![.?!]\s)\b[A-Z][a-z'’-]{2,}", need)} - signals.STOPWORDS
    seen: set[str] = set()
    scored: list[tuple[float, int, dict[str, str]]] = []
    total = max(1, len(works))
    for position, work in enumerate(works):
        key = work.get("doi") or re.sub(r"[^a-z0-9]", "", work.get("title", "").casefold())
        if work.get("retracted") or not key or key in seen:
            continue
        seen.add(key)
        title, abstract = _words(work.get("title", "")), _words(work.get("abstract", ""))
        score = 1 - position / total
        if wanted:
            score += 1.5 * len(wanted & title) / len(wanted) + len(wanted & abstract) / len(wanted)
        if named:
            score += 0.75 * len(named & (title | abstract)) / len(named)
        scored.append((-score, position, work))
    return [work for _, _, work in sorted(scored, key=lambda s: s[:2])[:keep]]


def about(need: str, query: str, text: str) -> bool:
    """Whether a piece of saved evidence can be about a need at all (Codex audit of fd74ff3, finding 5): its words
    carry at least half of the search's own (two at least) and, when the need names places or groups, one of them.
    A check of subject, never of support: a model's word that evidence covers a need is not taken alone."""
    have = _words(text)
    asked = {w for w in _words(query) if len(w) > 3} - signals.STOPWORDS
    named = {w.lower() for w in re.findall(r"(?<!^)(?<![.?!]\s)\b[A-Z][a-z'’-]{2,}", need)} - signals.STOPWORDS
    enough = len(asked & have) >= max(min(2, len(asked)), -(-len(asked) // 2))
    return bool(asked) and enough and (not named or bool(named & have))


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
