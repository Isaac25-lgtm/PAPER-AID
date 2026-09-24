"""Security-sensitive validation of every upload, repeated on the server regardless of what the
browser checked. Runs before any file is stored for processing or sent to a model."""

import io
import math
import zipfile
from pathlib import PurePosixPath

from app.core.errors import InvalidDocument
from app.documents.docx_io import read_docx
from app.documents.model import DocumentModel
from app.documents.pdf_io import read_pdf

ZIP_MAGIC = b"PK\x03\x04"
OLE_MAGIC = bytes.fromhex("D0CF11E0A1B11AE1")
MAX_ENTRIES = 2000
MAX_UNCOMPRESSED = 80 * 1024 * 1024
MAX_ENTRY_RATIO = 200
MIN_WORDS = 50


def _reject(code: str, message: str) -> InvalidDocument:
    return InvalidDocument(message, code=code)


def _check_docx_archive(data: bytes) -> None:
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise _reject("INVALID_CONTAINER", "This isn't a valid Word document. Open it in Word and save it as .docx again.") from exc
    entries = archive.infolist()
    if len(entries) > MAX_ENTRIES:
        raise _reject("ARCHIVE_ENTRY_COUNT", "This Word file has an unusual internal structure and can't be processed safely.")
    total = 0
    for entry in entries:
        path = PurePosixPath(entry.filename)
        if entry.filename.startswith(("/", "\\")) or ".." in path.parts or ":" in entry.filename:
            raise _reject("UNSAFE_ARCHIVE_PATH", "This Word file contains unsafe internal paths and can't be processed.")
        if entry.flag_bits & 0x1:
            raise _reject("ENCRYPTED", "This Word file is password-protected. Remove the password and upload it again.")
        total += entry.file_size
        if entry.file_size > 1024 * 1024 and entry.file_size / max(entry.compress_size, 1) > MAX_ENTRY_RATIO:
            raise _reject("ARCHIVE_EXPANSION", "This Word file expands to an unsafe size and can't be processed.")
    if total > MAX_UNCOMPRESSED:
        raise _reject("ARCHIVE_EXPANSION", "This Word file is too large once unpacked. Remove large images and try again.")
    names = {e.filename for e in entries}
    if "[Content_Types].xml" not in names or "word/document.xml" not in names:
        raise _reject("INVALID_CONTAINER", "This isn't a valid Word document. Open it in Word and save it as .docx again.")
    content_types = archive.read("[Content_Types].xml")
    if b"macroEnabled" in content_types or any(n.lower().endswith("vbaproject.bin") for n in names):
        raise _reject("MACRO_ENABLED", "Macro-enabled Word files are not accepted. Save it as a normal .docx and try again.")


def inspect_upload(data: bytes, filename: str, max_bytes: int, max_words: int, max_pdf_pages: int, min_words: int = MIN_WORDS) -> DocumentModel:
    """Validate an uploaded paper and return its DocumentModel, or raise InvalidDocument."""
    ext = PurePosixPath(filename.lower()).suffix
    if not data:
        raise _reject("EMPTY_FILE", "This file is empty.")
    if len(data) > max_bytes:
        raise _reject("FILE_TOO_LARGE", f"This file is larger than {max_bytes // (1024 * 1024)} MB. Remove large images or split the document.")
    if ext in (".docm", ".dotm"):
        raise _reject("MACRO_ENABLED", "Macro-enabled Word files are not accepted. Save it as a normal .docx and try again.")
    if ext not in (".docx", ".pdf"):
        raise _reject("UNSUPPORTED_TYPE", "Upload a Word document (.docx) or a text-based PDF.")
    if data.startswith(OLE_MAGIC):
        raise _reject("ENCRYPTED", "This file is password-protected or in the old .doc format. Remove the password or save it as .docx.")

    if ext == ".docx":
        if not data.startswith(ZIP_MAGIC):
            raise _reject("INVALID_CONTAINER", "This isn't a valid Word document. Open it in Word and save it as .docx again.")
        _check_docx_archive(data)
        model = read_docx(data)
        model.page_count = max(1, math.ceil(model.word_count / 300))
    else:
        if b"%PDF-" not in data[:1024]:
            raise _reject("INVALID_CONTAINER", "This isn't a valid PDF file.")
        model = read_pdf(data, max_pdf_pages)

    if model.word_count < min_words:
        raise _reject("NO_TEXT", "We couldn't find enough text in this document to work with.")
    if model.word_count > max_words:
        raise _reject("DOCUMENT_TOO_LONG", f"This document is longer than the {max_words:,}-word limit. Upload the chapters you need separately.")
    return model
