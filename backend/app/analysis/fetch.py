"""Reads a public web page (or a journal article's abstract) so the source check can confirm that a
quoted passage is really there.

Only the URLs a web search returned are ever fetched, plus OpenAlex (a free, open scholarly index)
for the abstract of an article whose URL carries a DOI; publishers often block automated reading
of the article page itself. Guards: http(s) only; the host must resolve to public addresses
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
from urllib.parse import quote, urljoin, urlsplit

import httpx
from pypdf import PdfReader
from pypdf.errors import PdfReadError

logger = logging.getLogger("paperaid.fetch")

MAX_BYTES = 3_000_000
TIMEOUT_SEC = 15
MAX_REDIRECTS = 3
HEADERS = {"User-Agent": "PaperAid-SourceCheck/1.0 (+https://paperaid-ca172.web.app)", "Accept": "text/html,application/pdf,application/json,text/plain;q=0.8"}
TAGS = re.compile(r"<(script|style|noscript|svg|head)\b.*?</\1\s*>", re.I | re.S)
MARKUP = re.compile(r"<[^>]+>")
DOI = re.compile(r"\b(10\.\d{4,9}/[^\s?#&]+)")


def _public(host: str) -> bool:
    try:
        infos = socket.getaddrinfo(host, None)
    except (socket.gaierror, UnicodeError):
        return False
    for info in infos:
        address = ipaddress.ip_address(info[4][0])
        if address.is_private or address.is_loopback or address.is_link_local or address.is_reserved or address.is_multicast or address.is_unspecified:
            return False
    return bool(infos)


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
    current = url
    try:
        with httpx.Client(timeout=TIMEOUT_SEC, headers=HEADERS, follow_redirects=False) as client:
            for _ in range(MAX_REDIRECTS + 1):
                parts = urlsplit(current)
                if parts.scheme not in ("http", "https") or not parts.hostname or not _public(parts.hostname):
                    return None
                with client.stream("GET", current) as response:
                    if response.is_redirect and "location" in response.headers:
                        current = urljoin(current, response.headers["location"])
                        continue
                    if response.status_code != 200:
                        return None
                    body = b""
                    for chunk in response.iter_bytes():
                        body += chunk
                        if len(body) > MAX_BYTES:
                            break
                    return body[:MAX_BYTES], response.headers.get("content-type", "").lower()
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
        index = json.loads(got[0]).get("abstract_inverted_index") or {}
    except (ValueError, AttributeError):
        return None
    positions = [(p, word) for word, places in index.items() for p in places]
    return " ".join(word for _, word in sorted(positions)) or None
