"""Data Lab removed (owner, 2026-11-15; its last code is tagged `datalab-last`), and a stored Word file is read
again only through the bounded parser (production readiness audit, 2026-11-15)."""

import io

import pytest
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


@pytest.mark.parametrize("caller", ["preview", "rebuild", "passage_price"])
def test_a_stored_word_file_is_read_again_only_by_the_bounded_parser(monkeypatch, caller):
    """The three places a stored Word file is read again use `read_stored_docx`, which is the child process."""
    from app.jobs import service, workspace

    calls = []
    real = intake._isolated_docx

    def counted(data, max_words):
        calls.append(max_words)
        return real(data, max_words)

    monkeypatch.setattr(intake, "_isolated_docx", counted)
    model = intake.read_stored_docx(_docx(400), 25_000)
    assert calls == [25_000] and model.word_count >= 400
    # the callers use that function, never the in-process reader
    module = workspace if caller in ("preview", "rebuild") else service
    assert module.read_stored_docx is intake.read_stored_docx
    assert "read_docx(rt.files.get" not in open(module.__file__, encoding="utf-8").read()


def test_a_stored_word_file_over_the_limit_is_refused_in_the_child():
    with pytest.raises(intake.InvalidDocument) as err:
        intake.read_stored_docx(_docx(300), 100)
    assert err.value.code == "DOCUMENT_TOO_LONG"
