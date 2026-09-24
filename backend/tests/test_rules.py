import pytest

from app.ai.costs import ensure_within_budget, job_budget
from app.analysis import signals
from app.core.errors import Conflict, PermanentStageError
from app.documents import protect
from app.documents.docx_io import read_docx
from app.formatting.apply import apply_formatting
from app.formatting.presets import PRESETS
from app.jobs import state
from app.jobs.models import Job, JobFailure, JobStatus, ServiceSelection, Stage, utcnow
from app.pricing.quote import quote_lines
from tests import fake_writer as rules
from tests.conftest import fixture_bytes, manifest

DOCX_ACCEPTED = [e["file"] for e in manifest() if e["expect"] == "accept" and e["file"].endswith(".docx")]


@pytest.mark.parametrize("name", DOCX_ACCEPTED)
def test_rule_engine_never_breaks_preservation(name):
    for block in read_docx(fixture_bytes(name)).blocks:
        if block.editable:
            masked, _ = protect.mask(block.masked or "")
            assert protect.check_rewrite(masked, rules.rewrite(masked)) == []


def test_rule_engine_removes_filler():
    out = rules.rewrite("It is important to note that social media plays a crucial role in learning in today's digital age.")
    assert out == "Social media shapes learning."


@pytest.mark.parametrize("name", DOCX_ACCEPTED)
@pytest.mark.parametrize("preset", ["apa7", "harvard"])
def test_formatting_never_changes_wording(name, preset):
    data = fixture_bytes(name)
    formatted, result = apply_formatting(data, PRESETS[preset], read_docx(data))
    assert result.body_text_unchanged
    assert read_docx(formatted).word_count == read_docx(data).word_count


def test_harvard_adds_schema_ordered_roman_prelims():
    data = fixture_bytes("dissertation_long.docx")
    formatted, result = apply_formatting(data, PRESETS["harvard"], read_docx(data))
    assert any(r.label == "Preliminary pages" for r in result.rules)
    import io

    from docx import Document

    for sect in Document(io.BytesIO(formatted)).element.body.iter("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}sectPr"):
        tags = [child.tag.split("}")[1] for child in sect]
        if "pgNumType" in tags and "docGrid" in tags:
            assert tags.index("pgNumType") < tags.index("docGrid")


def test_references_do_not_count_toward_the_estimate():
    model = read_docx(fixture_bytes("references_heavy.docx"))
    result, _ = signals.analyse(model)
    assert result.excluded_words > result.analysed_words


def test_formulaic_text_scores_higher_than_plain_text():
    plain, _ = signals.analyse(read_docx(fixture_bytes("hyperlinks.docx")))
    formulaic, _ = signals.analyse(read_docx(fixture_bytes("simple_essay.docx")))
    order = ["LOW", "MODERATE", "HIGH"]
    assert order.index(formulaic.band) >= order.index(plain.band)
    assert formulaic.algorithm_version == "signals-v1"


def test_quotes_are_deterministic_and_ordered():
    refine = ServiceSelection(writing="REFINE")
    assert quote_lines(refine, 4312)[0].amount == 7500
    assert quote_lines(ServiceSelection(writing="AI_CHECK"), 300)[0].amount == 2000
    assert quote_lines(ServiceSelection(writing="REDRAFT"), 4312)[0].amount > quote_lines(refine, 4312)[0].amount
    assert all(line.amount % 500 == 0 for line in quote_lines(ServiceSelection(writing="REFINE", formatting="FORMAT"), 12345))


def _job(status: JobStatus) -> Job:
    return Job(id="job_abc", status=status, owner_uid="u", owner_email="u@x.com", expires_at=utcnow(), pipeline=[Stage.EXTRACTING])


def test_state_machine_rejects_illegal_transitions():
    with pytest.raises(Conflict):
        state.transition(_job(JobStatus.COMPLETED), JobStatus.QUEUED)
    with pytest.raises(Conflict):
        state.transition(_job(JobStatus.PROCESSING), JobStatus.COMPLETED)  # stages not done
    with pytest.raises(Conflict):
        state.transition(_job(JobStatus.PROCESSING), JobStatus.FAILED)  # no recorded reason
    job = _job(JobStatus.PROCESSING)
    job.failure = JobFailure(code="X", user_message="y", retryable=False)
    assert state.transition(job, JobStatus.FAILED).status == JobStatus.FAILED
    for current, targets in state.ALLOWED.items():
        for target in JobStatus:
            assert state.can_transition(current, target) == (target in targets)


def test_budget_guard_and_budget():
    assert job_budget(7500, 3700, 0.35, 0.4, 5.0) == pytest.approx(0.7094, rel=1e-3)
    assert job_budget(100_000_000, 3700, 0.35, 0.4, 5.0) == 5.0
    ensure_within_budget(0.1, 0.1, 0.5)
    with pytest.raises(PermanentStageError) as err:
        ensure_within_budget(0.45, 0.1, 0.5)
    assert err.value.code == "BUDGET_EXCEEDED"
