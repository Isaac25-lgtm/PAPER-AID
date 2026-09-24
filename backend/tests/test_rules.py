import pytest

from app.ai.costs import ensure_within_budget
from app.analysis import signals
from app.core.config import Settings
from app.core.errors import Conflict, PermanentStageError
from app.documents import protect
from app.documents.docx_io import read_docx
from app.formatting.apply import apply_formatting
from app.formatting.presets import PRESETS
from app.jobs import state
from app.jobs.models import Job, JobFailure, JobStatus, ServiceSelection, Stage, utcnow
from app.pricing import credits
from app.pricing.quote import Passage, format_ugx, price, round_up, to_ugx
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


PRICING = Settings(openai_api_key="sk-test", anthropic_api_key="sk-test")


def test_price_is_ai_cost_times_the_multiplier_in_ugx():
    # $1 of AI spend at 2x and UGX 4,000 per dollar is UGX 8,000; always rounded up to the next 100
    assert to_ugx(1.0, PRICING) == 8000
    assert to_ugx(0.00001, PRICING) == 100 and round_up(0) == 0


def test_apa_harvard_is_the_one_fixed_price():
    assert format_ugx(PRICING, 300) == 2000  # the minimum
    assert format_ugx(PRICING, 30_000) == 10_000  # UGX 100 per 300 words
    assert price(PRICING, ServiceSelection(formatting="FORMAT"), 30_000).fixed_ugx == 10_000


def test_quotes_are_ceilings_that_grow_with_the_work():
    short = price(PRICING, ServiceSelection(writing="AI_CHECK"), 1_000).ai_ugx
    long = price(PRICING, ServiceSelection(writing="AI_CHECK"), 20_000).ai_ugx
    assert 0 < short < long and short % 100 == 0
    few = [Passage(chars=600, words=100, rewrite=True)] * 3
    many = [Passage(chars=600, words=100, rewrite=True)] * 30
    refine = ServiceSelection(writing="REFINE")
    assert price(PRICING, refine, 5_000, passages=few).ai_ugx < price(PRICING, refine, 5_000, passages=many).ai_ugx
    left_alone = [Passage(chars=600, words=100, rewrite=False)] * 3
    assert price(PRICING, refine, 5_000, passages=left_alone).ai_ugx < price(PRICING, refine, 5_000, passages=few).ai_ugx
    paid = price(PRICING, refine, 5_000, passages=few, fee_paid=700)
    assert paid.lines[0].amount == 700 and "already paid" in paid.lines[0].label


def test_the_ledger_never_goes_negative_and_settles_exactly():
    from app.jobs.models import Wallet

    w = credits.top_up(Wallet(uid="u", email="u@x.com"), 10_000, "Test credits")
    credits.hold(w, 8_000, "job_a", "hold")
    with pytest.raises(credits.InsufficientCredits):
        credits.hold(w, 8_000, "job_b", "second tab")  # only 2,000 left available
    credits.settle(w, held=8_000, charge=3_100, job_id="job_a", note="charge")
    assert (w.available, w.held) == (6_900, 0)
    assert [e.kind for e in w.entries] == ["TOP_UP", "HOLD", "CHARGE", "RELEASE"]
    with pytest.raises(ValueError):
        credits.settle(w, held=100, charge=200, job_id="job_a", note="more than held")


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


def test_budget_guard():
    ensure_within_budget(0.1, 0.1, 0.5)
    with pytest.raises(PermanentStageError) as err:
        ensure_within_budget(0.45, 0.1, 0.5)
    assert err.value.code == "BUDGET_EXCEEDED"
