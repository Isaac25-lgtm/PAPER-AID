"""Text-based PDF reading. PDFs are analysed but never patched: PaperAid cannot promise a
faithful PDF round-trip, so PDF uploads support AI Check only."""

import io
import json
import re
import subprocess
import sys
import threading

from pypdf import PdfReader
from pypdf.errors import PyPdfError

from app.core.errors import InvalidDocument, LimitExceeded
from app.documents.model import Block, DocumentModel

MIN_CHARS_PER_PAGE = 150
MAX_PAGE_CHARS = 2_000_000
MAX_TOTAL_CHARS = 8_000_000
PDF_TIMEOUT_SEC = 25
_PARSER_SLOT = threading.BoundedSemaphore(1)


def read_pdf(data: bytes, max_pages: int, max_words: int = 25_000) -> DocumentModel:
    """Untrusted PDF parsing runs in a bounded child, never on the API's Python heap.
    One child per process also prevents parallel uploads exhausting a 1 GiB API instance.
    """
    if not _PARSER_SLOT.acquire(timeout=5):
        raise LimitExceeded("Another document is being read. Please try your upload again shortly.", code="PDF_READER_BUSY")
    try:
        try:
            result = subprocess.run([sys.executable, "-m", "app.documents.pdf_io", "--worker", str(max_pages), str(max_words)],
                                    input=data, capture_output=True, timeout=PDF_TIMEOUT_SEC, check=False)
        except subprocess.TimeoutExpired as exc:
            # subprocess.run kills and waits for the child before raising. Its stderr is private.
            raise InvalidDocument("This PDF is too complex to read safely. Export it again or upload the Word file.", code="PDF_RESOURCE_LIMIT") from exc
        if result.returncode != 0:
            raise InvalidDocument("We couldn't read this PDF safely. Export it again or upload the Word file.", code="INVALID_CONTAINER")
        answer = json.loads(result.stdout)
        if "error" in answer:
            raise InvalidDocument(answer["message"], code=answer["error"])
        return DocumentModel.model_validate(answer)
    finally:
        _PARSER_SLOT.release()


def _read_pdf(data: bytes, max_pages: int, max_words: int) -> DocumentModel:
    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            raise InvalidDocument(
                "This PDF is password-protected. Remove the password or upload the Word file instead.", code="ENCRYPTED"
            )
        pages = reader.pages
        if len(pages) > max_pages:
            raise InvalidDocument(f"This PDF has more than {max_pages} pages. Split it or upload the relevant chapters.", code="TOO_MANY_PAGES")
        texts, chars, words = [], 0, 0
        for page in pages:
            text = page.extract_text() or ""
            chars += len(text)
            if len(text) > MAX_PAGE_CHARS or chars > MAX_TOTAL_CHARS:
                raise InvalidDocument("This PDF expands to too much text to read safely. Upload the relevant pages or the Word file.", code="PDF_RESOURCE_LIMIT")
            words += len(text.split())
            if words > max_words:
                raise InvalidDocument(f"This document is longer than the {max_words:,}-word limit. Upload the chapters you need separately.", code="DOCUMENT_TOO_LONG")
            texts.append(text)
    except (PyPdfError, RecursionError, ValueError, KeyError, IndexError, TypeError, OverflowError, MemoryError) as exc:
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


def _worker() -> None:
    _worker_limits()
    # Modern pypdf bounds decompression itself. The child is separately memory/time bounded
    # for other encodings and older versions; no shared process-global decoder is changed.
    import pypdf

    if hasattr(pypdf, "apply_configuration"):
        pypdf.apply_configuration(zlib_maximum_output_length=8 * 1024 * 1024)
    try:
        doc = _read_pdf(sys.stdin.buffer.read(), int(sys.argv[2]), int(sys.argv[3]))
    except InvalidDocument as exc:
        sys.stdout.write(json.dumps({"error": exc.code, "message": exc.message}))
    else:
        sys.stdout.write(doc.model_dump_json())


def _worker_limits() -> None:
    # JSON and exact source passages must not inherit Windows' legacy console encoding.
    sys.stdout.reconfigure(encoding="utf-8")
    if sys.platform != "win32":
        import resource

        resource.setrlimit(resource.RLIMIT_AS, (384 * 1024 * 1024, 384 * 1024 * 1024))
        resource.setrlimit(resource.RLIMIT_CPU, (15, 17))


def source_pdf_text(data: bytes) -> str | None:
    """Fetched research PDFs are untrusted too; preserve their original extracted wording.
    The worker reads two research topics at once: a source waits for the reader as long as one reading
    can take, rather than being dropped as unreadable because another PDF was being read."""
    if not _PARSER_SLOT.acquire(timeout=PDF_TIMEOUT_SEC + 5):
        return None
    try:
        try:
            result = subprocess.run([sys.executable, "-m", "app.documents.pdf_io", "--source-worker"], input=data,
                                    capture_output=True, timeout=PDF_TIMEOUT_SEC, check=False)
            return result.stdout.decode("utf-8") if result.returncode == 0 else None
        except (subprocess.TimeoutExpired, UnicodeError, OSError):
            return None
    finally:
        _PARSER_SLOT.release()


def _source_worker() -> None:
    _worker_limits()
    import pypdf

    pypdf.apply_configuration(zlib_maximum_output_length=8 * 1024 * 1024)
    reader = PdfReader(io.BytesIO(sys.stdin.buffer.read()))
    parts, size = [], 0
    for page in reader.pages[:60]:
        text = page.extract_text() or ""
        size += len(text)
        if len(text) > MAX_PAGE_CHARS or size > MAX_TOTAL_CHARS:
            raise ValueError("Source PDF text exceeded the reader resource limit")
        parts.append(text)
    sys.stdout.write(" ".join(parts))


if __name__ == "__main__" and len(sys.argv) == 4 and sys.argv[1] == "--worker":
    _worker()
elif __name__ == "__main__" and len(sys.argv) == 2 and sys.argv[1] == "--source-worker":
    _source_worker()
