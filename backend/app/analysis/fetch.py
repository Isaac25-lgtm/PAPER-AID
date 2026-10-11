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

from app.analysis.metadata import clean_authors, clean_container, clean_text, clean_title, distinct_people, is_organisation

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
    got = _request(url)
    return got[:3] if got else None


def _request(url: str, redirects: int = MAX_REDIRECTS) -> tuple[int, bytes, str, dict[str, str]] | None:
    """`_fetch` with the final response's headers (lower-case names) and a chosen number of redirects."""
    current = url
    deadline = time.monotonic() + TOTAL_SEC
    try:
        # trust_env=False: an environment proxy would resolve the host itself, bypassing the pinning.
        with httpx.Client(timeout=TIMEOUT_SEC, headers=HEADERS, follow_redirects=False, trust_env=False) as client:
            for _ in range(redirects + 1):  # every hop is resolved, validated and pinned again
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
                    headers = {k.lower(): v for k, v in response.headers.items()}
                    if response.status_code != 200:
                        return response.status_code, b"", "", headers
                    body = b""
                    for chunk in response.iter_bytes():
                        if time.monotonic() >= deadline:
                            return None
                        body += chunk
                        if len(body) > MAX_BYTES:
                            break
                    return 200, body[:MAX_BYTES], headers.get("content-type", "").lower(), headers
    except httpx.HTTPError as exc:
        logger.info("source page could not be read", extra={"fields": {"error": type(exc).__name__}})
        return None
    return None


def page_text(url: str) -> str | None:
    """The page's visible text, or None when it cannot be read (then its quotation is unconfirmed)."""
    got = _get(url)
    return _text(*got) if got else None


_META = re.compile(r"<meta\b[^>]*>", re.I)
_ATTR = re.compile(r"""\b(name|property|content)\s*=\s*(?:"([^"]*)"|'([^']*)')""", re.I)


def page_meta(url: str) -> dict[str, str]:
    """The article a web page presents, as the page itself declares it for indexing (the `citation_*` tags that
    journals, PubMed Central and institutional repositories carry): title, authors ("; " between them), year,
    journal, volume, issue, pages and DOI. Empty when the page declares none or cannot be read. The page is the
    publisher's own statement of who wrote the work, so a source is never cited by its host's name when the page
    names its authors (audit of the trial documents, 2026-10-10: a paper cited as "National Library of Medicine
    (PMC), 2023" was by three named authors, 2025)."""
    got = _get(url)
    if not got or "html" not in got[1].lower():
        return {}
    found: dict[str, list[str]] = {}
    for tag in _META.findall(got[0][:600_000].decode("utf-8", errors="replace")):
        attrs = {m.group(1).lower(): m.group(2) if m.group(2) is not None else m.group(3) for m in _ATTR.finditer(tag)}
        key, value = (attrs.get("name") or attrs.get("property") or "").lower(), clean_text(attrs.get("content") or "")
        if key.startswith("citation_") and value:
            found.setdefault(key, []).append(value)
    if not found.get("citation_title"):
        return {}

    def first(*keys: str) -> str:
        return next((found[k][0] for k in keys if found.get(k)), "")

    authors = []
    for name in found.get("citation_author", []):
        if is_organisation(name):
            authors.append(name)
            continue
        family, comma, given = name.partition(",")
        if not comma:
            given, _, family = name.rpartition(" ")
        authors.append(_surname_initials(family, given) if given.strip() else family.strip())
    year = re.search(r"\b(?:19|20)\d{2}\b", first("citation_publication_date", "citation_date", "citation_online_date", "citation_year"))
    pages = "–".join(p for p in (first("citation_firstpage"), first("citation_lastpage")) if p)
    doi = DOI.search(first("citation_doi"))
    return {"title": clean_title(first("citation_title")), "authors": "; ".join(clean_authors(authors)[:20]), "year": year.group(0) if year else "",
            "container": first("citation_journal_title", "citation_conference_title", "citation_dissertation_institution", "citation_publisher"),
            "volume": first("citation_volume"), "issue": first("citation_issue"), "pages": pages, "doi": doi.group(1).rstrip(".").lower() if doi else ""}


def abstract_text(url: str) -> str | None:
    """The abstract of the article a URL points to, from OpenAlex, when the URL carries a DOI."""
    match = DOI.search(url)
    if not match:
        return None
    data = _openalex_json(f"/works/doi:{quote(match.group(1).rstrip('.'), safe='/')}")
    return _abstract(data.get("abstract_inverted_index") or {}) if data else None


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
    data = _openalex_json(f"/works/{key}")
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
    initials = " ".join(f"{part[0].upper()}." for part in re.split(r"[\s.-]+", given) if part[:1].isalpha())
    return f"{family.strip()}, {initials}".strip().rstrip(",")


OPENALEX = "https://api.openalex.org"
_openalex_key = ""  # set once at start-up (app.runtime); sent only to api.openalex.org, never logged
# What a search of the index came to (algorithm revision 2026-10-09): "no results" is not "could not be asked".
IndexOutcome = Literal["FOUND", "NO_RESULTS", "RATE_LIMITED", "ALLOWANCE_USED", "UNAVAILABLE", "ACCESS_DENIED", "INVALID"]


def set_openalex_key(key: str) -> None:
    global _openalex_key
    _openalex_key = key.strip()


def _openalex(path: str) -> tuple[int, bytes, str, dict[str, str]] | None:
    """One request to OpenAlex, with PaperAid's key when it has one. No redirect is followed, so the key can only
    ever reach api.openalex.org."""
    url = OPENALEX + path
    if _openalex_key:
        url += ("&" if "?" in path else "?") + "api_key=" + quote(_openalex_key, safe="")
    return _request(url, redirects=0)


def _openalex_json(path: str) -> dict | None:
    got = _openalex(path)
    if not got or got[0] != 200:
        return None
    try:
        data = json.loads(got[1])
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def openalex_find(query: str, from_year: int | None, limit: int) -> tuple[IndexOutcome, list[dict[str, str]]]:
    """Scholarly works matching a query (OpenAlex), most relevant first, each with its abstract and bibliographic
    details, and what the search came to. Only works that have an abstract are returned: PaperAid confirms every
    quoted passage against it. The query is the only thing sent."""
    since = f"from_publication_date:{from_year}-01-01," if from_year else ""  # None: any year (a theory's or a method's own source)
    params = f"search={quote(query)}&filter={since}has_abstract:true&per-page={limit}&sort=relevance_score:desc"
    got = _openalex(f"/works?{params}")
    if got is None:
        return "UNAVAILABLE", []
    status, body, _, headers = got
    if status == 429:
        # The day's allowance used up reads 0 remaining; otherwise it is the per-second limit.
        spent = headers.get("x-ratelimit-remaining-usd", "") in ("0", "0.0", "0.00", "0.000") or headers.get("x-ratelimit-remaining", "") == "0"
        return ("ALLOWANCE_USED" if spent else "RATE_LIMITED"), []
    if status in (401, 403):
        return "ACCESS_DENIED", []
    if status != 200:
        return "UNAVAILABLE", []
    try:
        data = json.loads(body)
    except ValueError:
        return "INVALID", []
    if not isinstance(data, dict) or not isinstance(data.get("results"), list):
        return "INVALID", []
    works = _openalex_works(data["results"][:limit])
    return ("FOUND" if works else "NO_RESULTS"), works


def openalex_search(query: str, from_year: int, limit: int) -> list[dict[str, str]]:
    return openalex_find(query, from_year, limit)[1]


def _openalex_works(results: list) -> list[dict[str, str]]:
    works = []
    for item in results:
        if not isinstance(item, dict):
            continue
        abstract = _abstract(item.get("abstract_inverted_index") or {})
        title = item.get("display_name") or ""
        if not abstract or not title:
            continue
        if (item.get("language") or "en") != "en":
            continue  # the student, and PaperAid's checks, read English: a work in another language is not offered as a source
        authors = []
        for name in distinct_people([((a.get("author") or {}).get("display_name") or "").strip() for a in item.get("authorships") or []]):
            if name:
                given, _, family = name.rpartition(" ")
                authors.append(name if is_organisation(name) else _surname_initials(family, given) if given else family)
        location = item.get("primary_location") or {}
        source = location.get("source") or {}
        biblio = item.get("biblio") or {}
        pages = "–".join(p for p in (biblio.get("first_page"), biblio.get("last_page")) if p)
        doi = (item.get("doi") or "").removeprefix("https://doi.org/").lower()
        works.append(
            {
                "doi": doi,
                "url": f"https://doi.org/{doi}" if doi else (location.get("landing_page_url") or item.get("id") or ""),
                "title": clean_title(title),
                "authors": "; ".join(clean_authors(authors)[:20]),
                "year": str(item.get("publication_year") or ""),
                "container": "" if source.get("type") == "repository" else clean_container(source.get("display_name") or ""),
                "volume": str(biblio.get("volume") or ""),
                "issue": str(biblio.get("issue") or ""),
                "pages": pages,
                "type": item.get("type") or "",
                "abstract": abstract,
                "retracted": "yes" if item.get("is_retracted") else "",
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
    people = [a for a in message.get("author") or [] if isinstance(a, dict)]
    kept = set(distinct_people([f"{a.get('given', '')} {a.get('family', '')}".strip() or a.get("name", "") for a in people]))
    authors = clean_authors([_surname_initials(a.get("family", ""), a.get("given", "")) if a.get("family") else a.get("name", "") for a in people
                             if (f"{a.get('given', '')} {a.get('family', '')}".strip() or a.get("name", "")) in kept])
    parts = ((message.get("issued") or {}).get("date-parts") or [[None]])[0]
    # A retraction or withdrawal notice registered against this work (Crossref, with Retraction Watch data).
    updates = [u.get("type", "").lower() for u in message.get("updated-by") or [] if isinstance(u, dict)]
    return {
        "doi": (doi or message.get("DOI") or "").lower(),
        "title": clean_title((message.get("title") or [""])[0]),
        "authors": "; ".join(a for a in authors if a),
        "year": str(parts[0]) if parts and parts[0] else "",
        "container": clean_container((message.get("container-title") or [""])[0]),
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
    data = _openalex_json(f"/works/doi:{quote(doi, safe='/')}")
    return None if data is None else bool(data.get("is_retracted"))
