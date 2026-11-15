"""Data Lab removed (owner, 2026-11-15; its last code is tagged `datalab-last`), and a stored Word file is read
again only through the bounded parser (production readiness audit, 2026-11-15)."""

import io

from docx import Document

from app.documents import intake


def test_data_lab_is_gone_from_the_api_and_the_catalogue(client):
    assert client.get("/api/datalab").status_code == 404
    assert client.post("/api/datalab", json={}).status_code in (404, 405)
    config = client.get("/api/config").json()
    assert "DATALAB" not in str(config) and "DATALAB_QUAL" not in str(config)
    routes = {getattr(r, "path", "") for r in client.app.routes}
    assert not any("datalab" in path for path in routes)


def test_no_data_lab_service_or_steps_remain():
    from app.ai import gemini, orchestration
    from app.jobs.models import ServiceId

    assert "DATALAB" not in {s.value for s in ServiceId}
    gone = {"d_report", "d_report_review", "d_chapter4", "q_code", "q_themes", "q_review"}
    assert not gone & set(orchestration.STEPS)
    assert not gone & set(gemini.TASK_STAGES)


def _docx(words: int) -> bytes:
    doc = Document()
    doc.add_paragraph(" ".join(["word"] * words))
    out = io.BytesIO()
    doc.save(out)
    return out.getvalue()


def test_a_stored_file_is_read_again_only_by_the_bounded_parser(monkeypatch):
    """The preview, the rebuild, a passage's price and the worker read an accepted file through the child process."""
    from app.jobs import pipeline, service, workspace

    calls = []
    real = intake._isolated_docx

    def counted(data, max_words):
        calls.append(max_words)
        return real(data, max_words)

    monkeypatch.setattr(intake, "_isolated_docx", counted)
    accepted = type("Accepted", (), {"format": "DOCX", "word_count": 400, "page_estimate": 2})()
    model = intake.read_stored(_docx(400), accepted, 25_000, 50)
    assert calls == [25_000] and model.word_count >= 400
    for module in (workspace, service):
        assert module.read_stored is intake.read_stored
        assert "read_docx(rt.files.get" not in open(module.__file__, encoding="utf-8").read()
    assert "read_stored_docx" not in open(pipeline.__file__, encoding="utf-8").read()


FORMAT_ONLY = {"writing": "NONE", "formatting": "FORMAT", "preset": "apa7", "latex": False}
STUDENT = {"Authorization": "Dev student@example.com"}


def _job_with(client, words):
    job_id = client.post("/api/jobs", headers=STUDENT).json()["id"]
    sentence = "Community health workers improve maternal care in rural districts. "
    upload = client.post(f"/api/jobs/{job_id}/files/source", headers=STUDENT,
                         files={"file": ("paper.docx", _docx_text(sentence * (words // 9)), "application/octet-stream")})
    assert upload.status_code == 200, upload.json()
    return job_id


def _docx_text(text: str) -> bytes:
    doc = Document()
    doc.add_heading("A paper", level=1)
    for i in range(0, len(text), 600):
        doc.add_paragraph(text[i:i + 600])
    out = io.BytesIO()
    doc.save(out)
    return out.getvalue()


def test_lowering_the_word_limit_never_locks_an_accepted_file_but_holds_new_quotes_to_it(client, monkeypatch):
    """Codex audit, 2026-11-15: a 300-word file accepted under the limit stays readable after the limit drops to 100;
    a new quote and a hold on it meet today's limit; the worker checks a priced file at the limit it was accepted at."""
    from app.runtime import get_runtime

    job_id = _job_with(client, 300)
    rt = get_runtime()
    monkeypatch.setattr(rt.settings, "max_words", 100)
    preview = client.get(f"/api/jobs/{job_id}/document", headers=STUDENT)
    assert preview.status_code == 200 and preview.json()["blocks"]
    quote = client.post(f"/api/jobs/{job_id}/quote", headers=STUDENT, json={"selection": FORMAT_ONLY})
    assert quote.status_code >= 400 and quote.json()["code"] == "DOCUMENT_TOO_LONG"
    # the reader the worker uses keeps the accepted size as its floor
    job = rt.store.get(job_id)
    model = intake.read_stored(rt.files.get(job.source.path), job.source, 100, rt.settings.max_pdf_pages)
    assert model.word_count == job.source.word_count > 100


def test_a_new_upload_meets_todays_limit(client, monkeypatch):
    from app.runtime import get_runtime

    monkeypatch.setattr(get_runtime().settings, "max_words", 100)
    job_id = client.post("/api/jobs", headers=STUDENT).json()["id"]
    sentence = "Community health workers improve maternal care in rural districts. "
    upload = client.post(f"/api/jobs/{job_id}/files/source", headers=STUDENT,
                         files={"file": ("paper.docx", _docx_text(sentence * 35), "application/octet-stream")})
    assert upload.status_code >= 400 and upload.json()["code"] == "DOCUMENT_TOO_LONG"
