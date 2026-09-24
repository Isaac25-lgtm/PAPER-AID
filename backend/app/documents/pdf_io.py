"""Text-based PDF reading. PDFs are analysed but never patched: PaperAid cannot promise a
faithful PDF round-trip, so PDF uploads support AI Check only."""

import io
import re

from pypdf import PdfReader
from pypdf.errors import PdfReadError

from app.core.errors import InvalidDocument
from app.documents.model import Block, DocumentModel

MIN_CHARS_PER_PAGE = 150


def read_pdf(data: bytes, max_pages: int) -> DocumentModel:
    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            raise InvalidDocument(
                "This PDF is password-protected. Remove the password or upload the Word file instead.", code="ENCRYPTED"
            )
        pages = reader.pages
        if len(pages) > max_pages:
            raise InvalidDocument(f"This PDF has more than {max_pages} pages. Split it or upload the relevant chapters.", code="TOO_MANY_PAGES")
        texts = [page.extract_text() or "" for page in pages]
    except PdfReadError as exc:
        raise InvalidDocument("We couldn't read this PDF. It may be damaged — try exporting it again.", code="INVALID_CONTAINER") from exc

    if not pages or sum(len(t.strip()) for t in texts) / len(pages) < MIN_CHARS_PER_PAGE:
        raise InvalidDocument(
            "We couldn't find readable text in this PDF — it looks like a scanned document. "
            "Upload the original Word file, or a PDF exported from Word or Google Docs.",
            code="SCANNED_PDF",
        )

    blocks: list[Block] = []
    section = ""
    counter = 0
    for text in texts:
        for chunk in _paragraphs(text):
            counter += 1
            is_heading = len(chunk.split()) <= 10 and not chunk.endswith((".", ",", ";")) and chunk[:1].isupper()
            if is_heading:
                section = chunk
            blocks.append(
                Block(id=f"b{counter:05d}", kind="heading" if is_heading else "paragraph", level=1 if is_heading else None, section=section, text=chunk)
            )
    return DocumentModel(format="PDF", blocks=blocks, page_count=len(pages))


def _paragraphs(page_text: str) -> list[str]:
    """Rebuild paragraphs from PDF lines: blank lines split, wrapped lines join."""
    paragraphs, current = [], []
    for line in page_text.splitlines():
        stripped = line.strip()
        if not stripped:
            if current:
                paragraphs.append(" ".join(current))
                current = []
            continue
        short_line = len(stripped.split()) <= 10 and not stripped.endswith((".", ","))
        if short_line and not current:
            paragraphs.append(stripped)
            continue
        current.append(stripped)
        if stripped.endswith(".") and len(" ".join(current).split()) > 120:
            paragraphs.append(" ".join(current))
            current = []
    if current:
        paragraphs.append(" ".join(current))
    return [re.sub(r"(\w)- (\w)", r"\1\2", p) for p in paragraphs if p]
