"""Rendered page counts (Workstream H, rulebook SH-005): the Word file PaperAid delivers, converted
to PDF by LibreOffice (headless, offline, in a temporary folder) and its pages counted. Used only
when `render_pages` is on and the worker image was built with LibreOffice. LibreOffice lays pages
out slightly differently from Word, so a count passes only with a 5% margin, and the student is
told to confirm it in Word (Codex review 2026-09-30 #7)."""

import io
import logging
import shutil
import subprocess
import tempfile
from pathlib import Path

from pypdf import PdfReader
from pypdf.errors import PdfReadError

from app.core.logging import log

logger = logging.getLogger("paperaid.render")
TIMEOUT_SEC = 120


def executable() -> str | None:
    return shutil.which("soffice") or shutil.which("libreoffice")


def page_count(docx: bytes) -> float | None:
    """The document's pages, or None when it could not be rendered (the check then stays "Needs review")."""
    exe = executable()
    if exe is None:
        return None
    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp)
        source = folder / "document.docx"
        source.write_bytes(docx)
        profile = (folder / "profile").as_uri()
        try:
            run = subprocess.run(
                [exe, f"-env:UserInstallation={profile}", "--headless", "--norestore", "--convert-to", "pdf", "--outdir", str(folder), str(source)],
                capture_output=True, timeout=TIMEOUT_SEC, check=False,
            )
        except subprocess.TimeoutExpired:
            log(logger, logging.WARNING, "page render timed out")
            return None
        pdf = folder / "document.pdf"
        if run.returncode != 0 or not pdf.exists():
            log(logger, logging.WARNING, "page render failed", code=run.returncode)
            return None
        try:
            return float(len(PdfReader(io.BytesIO(pdf.read_bytes())).pages))
        except PdfReadError:
            return None
