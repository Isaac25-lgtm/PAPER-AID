"""Reads a public web page (or a journal article's abstract) so the source check can confirm that a
quoted passage is really there.

Only the URLs a web search returned are ever fetched, plus OpenAlex (a free, open scholarly index)
for the abstract of an article whose URL carries a DOI; publishers often block automated reading
of the article page itself. Proposal research also searches OpenAlex by query and reads a DOI's
registered details from Crossref; only the search query or the DOI is sent. Guards: http(s) only; the host must resolve to public addresses
(private, loopback, link-local and reserved ranges are refused, on every redirect); at most 3
redirects, 15 seconds and 3 MB; HTML, PDF and JSON only. Nothing from the student's paper is ever
sent. What is read is untrusted text: it is only searched for the quotation, never followed.
"""

import html
import io
import ipaddress
import json
import logging
import re
import socket
import time
from typing import Literal
from urllib.parse import quote, urljoin, urlsplit, urlunsplit

import httpx
from pypdf import PdfReader
from pypdf.errors import PdfReadError

logger = logging.getLogger("paperaid.fetch")

MAX_BYTES = 3_000_000
TIMEOUT_SEC = 10  # each network step (connect, each read)
TOTAL_SEC = 30  # the whole fetch: redirects, headers and body (Codex review 2026-10-07)
MAX_REDIRECTS = 3
HEADERS = {"User-Agent": "PaperAid-SourceCheck/1.0 (+https://paperaid-ca172.web.app)", "Accept": "text/html,application/pdf,application/json,text/plain;q=0.8"}
TAGS = re.compile(r"<(script|style|noscript|svg|head)\b.*?</\1\s*>", re.I | re.S)
MARKUP = re.compile(r"<[^>]+>")
DOI = re.compile(r"\b(10\.\d{4,9}/[^\s?#&]+)")


def _public_address(host: str) -> str | None:
    """One validated public IP for a host, resolved once, or None when any address it resolves to
    is private, loopback, link-local, reserved, multicast or unspecified. The connection is then made
    to this exact address (Codex audit 2026-09-28 #1): resolving again at connect time let a host
    pass the check with a public address and connect to a private one (DNS rebinding)."""
    try:
        infos = socket.getaddrinfo(host, None)
    except (socket.gaierror, UnicodeError):
        return None
    addresses = [ipaddress.ip_address(info[4][0]) for info in infos]
    for address in addresses:
        if address.is_private or address.is_loopback or address.is_link_local or address.is_reserved or address.is_multicast or address.is_unspecified:
            return None
    return str(addresses[0]) if addresses else None


def _pinned(url: str) -> tuple[str, dict[str, str], dict[str, str]] | None:
    """(URL addressed to the validated IP, Host header, TLS server name) for a public http(s) URL.
    TLS still verifies the certificate against the real host name."""
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        return None
    address = _public_address(parts.hostname)
    if address is None:
        return None
    ip = f"[{address}]" if ":" in address else address
    netloc = f"{ip}:{parts.port}" if parts.port else ip
    host = f"{parts.hostname}:{parts.port}" if parts.port else parts.hostname
    return urlunsplit((parts.scheme, netloc, parts.path or "/", parts.query, "")), {"Host": host}, {"sni_hostname": parts.hostname}


def _text(body: bytes, content_type: str) -> str | None:
    if "pdf" in content_type or body[:5] == b"%PDF-":
        try:
            reader = PdfReader(io.BytesIO(body))
            return " ".join((page.extract_text() or "") for page in reader.pages[:60])
        except (PdfReadError, ValueError, KeyError, OSError):
            return None
    if "html" in content_type or "text" in content_type:
        page = body.decode("utf-8", errors="replace")
        return html.unescape(MARKUP.sub(" ", TAGS.sub(" ", page)))
    return None


def _get(url: str) -> tuple[bytes, str] | None:
    """(body, content type) of a public URL, or None when it cannot be read safely."""
    got = _fetch(url)
    return (got[1], got[2]) if got and got[0] == 200 else None


def _fetch(url: str) -> tuple[int, bytes, str] | None:
    """(status, body, content type) of a public URL's final response, or None when it could not be
    reached safely (then nothing is known about it)."""
    current = url
    deadline = time.monotonic() + TOTAL_SEC
    try:
        # trust_env=False: an environment proxy would resolve the host itself, bypassing the pinning.
        with httpx.Client(timeout=TIMEOUT_SEC, headers=HEADERS, follow_redirects=False, trust_env=False) as client:
            for _ in range(MAX_REDIRECTS + 1):  # every hop is resolved, validated and pinned again
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return None
                pinned = _pinned(current)
                if pinned is None:
                    return None
                target, host, tls = pinned
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return None
                with client.stream("GET", target, headers=host, extensions=tls, timeout=min(TIMEOUT_SEC, remaining)) as response:
                    if response.is_redirect and "location" in response.headers:
                        current = urljoin(current, response.headers["location"])
                        continue
                    if response.status_code != 200:
                        return response.status_code, b"", ""
                    body = b""
                    for chunk in response.iter_bytes():
                        if time.monotonic() >= deadline:
                            return None
                        body += chunk
                        if len(body) > MAX_BYTES:
                            break
                    return 200, body[:MAX_BYTES], response.headers.get("content-type", "").lower()
    except httpx.HTTPError as exc:
        logger.info("source page could not be read", extra={"fields": {"error": type(exc).__name__}})
        return None
    return None


def page_text(url: str) -> str | None:
    """The page's visible text, or None when it cannot be read (then its quotation is unconfirmed)."""
    got = _get(url)
    return _text(*got) if got else None


def abstract_text(url: str) -> str | None:
    """The abstract of the article a URL points to, from OpenAlex, when the URL carries a DOI."""
    match = DOI.search(url)
    if not match:
        return None
    got = _get(f"https://api.openalex.org/works/doi:{quote(match.group(1).rstrip('.'), safe='/')}")
    if not got:
        return None
    try:
        return _abstract(json.loads(got[0]).get("abstract_inverted_index") or {})
    except (ValueError, AttributeError):
        return None


def _abstract(index: dict[str, list[int]]) -> str | None:
    positions = [(p, word) for word, places in index.items() for p in places]
    return " ".join(word for _, word in sorted(positions)) or None


def doi_in(url: str) -> str:
    match = DOI.search(url)
    return match.group(1).rstrip(".").lower() if match else ""


PMCID = re.compile(r"\b(PMC\d{4,10})\b", re.I)
PMID = re.compile(r"pubmed\.ncbi\.nlm\.nih\.gov/(\d{4,10})")


def resolve_doi(url: str) -> str:
    """The DOI of the article a URL points to: in the URL itself, or (for PubMed Central and
    PubMed pages, which carry none) looked up in OpenAlex by PMCID or PMID. Empty when unknown."""
    doi = doi_in(url)
    if doi:
        return doi
    pmcid, pmid = PMCID.search(url), PMID.search(url)
    key = f"pmcid:{pmcid.group(1).upper()}" if pmcid else f"pmid:{pmid.group(1)}" if pmid else ""
    if not key:
        return ""
    data = _json(f"https://api.openalex.org/works/{key}")
    return ((data or {}).get("doi") or "").removeprefix("https://doi.org/").lower()


def _json(url: str) -> dict | None:
    got = _get(url)
    if not got:
        return None
    try:
        data = json.loads(got[0])
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def _surname_initials(family: str, given: str) -> str:
    initials = " ".join(f"{part[0]}." for part in re.split(r"[\s.-]+", given) if part[:1].isalpha())
    return f"{family.strip()}, {initials}".strip().rstrip(",")


def openalex_search(query: str, from_year: int, limit: int) -> list[dict[str, str]]:
    """Scholarly works matching a query (OpenAlex, free and open), newest research first, each
    with its abstract and bibliographic details. Only works that have an abstract are returned:
    PaperAid confirms every quoted passage against it. The query is the only thing sent."""
    params = f"search={quote(query)}&filter=from_publication_date:{from_year}-01-01,has_abstract:true&per-page={limit}&sort=relevance_score:desc"
    data = _json(f"https://api.openalex.org/works?{params}")
    works = []
    for item in (data or {}).get("results", [])[:limit]:
        abstract = _abstract(item.get("abstract_inverted_index") or {})
        title = item.get("display_name") or ""
        if not abstract or not title:
            continue
        authors = []
        for authorship in item.get("authorships") or []:
            name = ((authorship.get("author") or {}).get("display_name") or "").strip()
            if name:
                given, _, family = name.rpartition(" ")
                authors.append(_surname_initials(family, given) if given else family)
        location = item.get("primary_location") or {}
        biblio = item.get("biblio") or {}
        pages = "–".join(p for p in (biblio.get("first_page"), biblio.get("last_page")) if p)
        doi = (item.get("doi") or "").removeprefix("https://doi.org/").lower()
        works.append(
            {
                "doi": doi,
                "url": f"https://doi.org/{doi}" if doi else (location.get("landing_page_url") or item.get("id") or ""),
                "title": title,
                "authors": "; ".join(authors[:20]),
                "year": str(item.get("publication_year") or ""),
                "container": ((location.get("source") or {}).get("display_name") or ""),
                "volume": str(biblio.get("volume") or ""),
                "issue": str(biblio.get("issue") or ""),
                "pages": pages,
                "type": item.get("type") or "",
                "abstract": abstract,
            }
        )
    return works


def crossref_work(doi: str) -> dict[str, str] | None:
    """A DOI's registered bibliographic record (Crossref): the reference list is built from this,
    never from what a model says about the source."""
    data = _json(f"https://api.crossref.org/works/{quote(doi, safe='/')}")
    message = (data or {}).get("message")
    if not isinstance(message, dict):
        return None
    return _crossref_record(message, doi)


Lookup = Literal["FOUND", "NOT_FOUND", "UNAVAILABLE"]


def crossref_lookup(doi: str) -> tuple[Lookup, dict[str, str] | None]:
    """A DOI's registered record, telling "not registered" (Crossref answers 404) apart from "could
    not be checked" (no answer, an error, or unreadable data) (Codex audit 56c4f83 M23)."""
    got = _fetch(f"https://api.crossref.org/works/{quote(doi, safe='/')}")
    if got is None or got[0] not in (200, 404):
        return "UNAVAILABLE", None
    if got[0] == 404:
        return "NOT_FOUND", None
    try:
        message = json.loads(got[1]).get("message")
    except (ValueError, AttributeError):
        return "UNAVAILABLE", None
    return ("FOUND", _crossref_record(message, doi)) if isinstance(message, dict) else ("UNAVAILABLE", None)


RETRACTION = {"retraction", "withdrawal", "removal"}


def _crossref_record(message: dict, doi: str = "") -> dict[str, str]:
    authors = [_surname_initials(a.get("family", ""), a.get("given", "")) if a.get("family") else a.get("name", "") for a in message.get("author") or []]
    parts = ((message.get("issued") or {}).get("date-parts") or [[None]])[0]
    # A retraction or withdrawal notice registered against this work (Crossref, with Retraction Watch data).
    updates = [u.get("type", "").lower() for u in message.get("updated-by") or [] if isinstance(u, dict)]
    return {
        "doi": (doi or message.get("DOI") or "").lower(),
        "title": " ".join((message.get("title") or [""])[0].split()),
        "authors": "; ".join(a for a in authors if a),
        "year": str(parts[0]) if parts and parts[0] else "",
        "container": (message.get("container-title") or [""])[0],
        "volume": str(message.get("volume") or ""),
        "issue": str(message.get("issue") or ""),
        "pages": str(message.get("page") or "").replace("-", "–"),
        "type": message.get("type") or "",
        "retracted": "yes" if RETRACTION & set(updates) else "",
    }


def crossref_search(bibliographic: str, rows: int = 3) -> list[dict[str, str]] | None:
    """Registered works matching a reference as written (Crossref's bibliographic search), or None
    when the search could not run. Only the reference text is sent: public data, never the paper."""
    data = _json(f"https://api.crossref.org/works?query.bibliographic={quote(bibliographic[:300])}&rows={rows}")
    if data is None:
        return None
    items = (data.get("message") or {}).get("items") or []
    return [_crossref_record(i) for i in items if isinstance(i, dict)]


def openalex_retracted(doi: str) -> bool | None:
    """OpenAlex's retraction flag for a DOI; None when the work is unknown to it."""
    data = _json(f"https://api.openalex.org/works/doi:{quote(doi, safe='/')}")
    return None if data is None else bool(data.get("is_retracted"))
