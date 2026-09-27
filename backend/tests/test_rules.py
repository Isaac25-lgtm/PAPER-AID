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
    assert formulaic.algorithm_version == "signals-v2"


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


# --- signals-v2 (owner decision 2026-09-27: signals guide review, they are not the target) --------


def test_every_rule_is_well_formed_and_no_section_is_exempt():
    from typing import get_args

    from app.analysis.rules import RULES, SECTION_FACTOR
    from app.jobs.models import ReasonCode

    assert all(rule.reason in get_args(ReasonCode) for rule in RULES.values())
    assert all(rule.explanation and rule.suggestion for rule in RULES.values() if rule.finding)
    assert min(f for factors in SECTION_FACTOR.values() for f in factors.values()) >= 0.5  # interpretation, never exemption


def _paragraph(section, text):
    from app.documents.model import Block

    return Block(id="b1", kind="paragraph", section=section, text=text, masked=text, editable=True)


UNIFORM = " ".join(f"The participants in group {n} completed the same survey form on the same day." for n in "ABCDEFG")


def test_section_type_changes_how_a_signal_counts_but_never_hides_it():
    intro = signals.block_signals(_paragraph("1. Introduction", UNIFORM))
    methods = signals.block_signals(_paragraph("3. Methodology", UNIFORM))
    assert {h.rule for h in intro.hits} == {h.rule for h in methods.hits} and intro.hits
    assert 0 < methods.score < intro.score


def test_an_em_dash_or_a_transition_word_alone_is_not_a_finding():
    text = "However, the results were mixed — some schools improved while others did not. " "We interviewed 12 teachers in Gulu in March 2024 (Okello, 2021)."
    assert signals.block_signals(_paragraph("Results", text)).findings == []


def test_repeated_phrasing_is_measured_across_paragraphs_but_the_paper_topic_is_not():
    from app.documents.model import Block, DocumentModel

    template = "it is important to note that the programme had clear effects on local learners"
    blocks = [Block(id="h1", kind="heading", level=1, text="Mobile money use among traders", section="")]
    for i in range(4):
        text = f"In district {i}, {template}. Mobile money use among traders rose in district {i} as the survey showed for every market we visited there."
        blocks.append(Block(id=f"p{i}", kind="paragraph", section="Mobile money use among traders", text=text, masked=text, editable=True))
    found = signals.scan(DocumentModel(format="DOCX", blocks=blocks))
    repeated = [b.block.id for b in found.blocks if any(h.rule == "NGRAM_REPEATED" for h in b.hits)]
    assert repeated == ["p1", "p2", "p3"]  # the first use is not flagged
    note = next(d.note for d in found.document if d.rule == "NGRAM_REPEATED")
    assert "clear effects on local learners" in note and "mobile money use among traders" not in note


def test_post_scan_reports_signals_before_and_after_and_new_repetition():
    before = "Furthermore, it is important to note that costs rose. Moreover, fees rose. Additionally, rents rose."
    after = "Costs rose, and so did fees and rents across the whole of the region."
    elsewhere = signals.phrases("Prices went up across the whole of the region in every month.")
    result = signals.post_scan(before, after, "Results", elsewhere)
    assert "TRANS_STACKED" in result["signalsBefore"] and result["signalsAfter"] == []
    assert "across the whole of the" in " ".join(result["newRepeatedPhrasing"])


def test_paper_checks_separate_confirmed_possible_and_undetermined():
    from app.analysis import paper_checks
    from app.documents.model import Block, DocumentModel

    paragraphs = ["Costs shaped habits (Okello, 2021; Nansubuga & Mugisha, 2019). Kato (2018) disagreed, as did (Byaruhanga, 2017)."]
    references = ["Okello, J. (2021). Data costs.", "Nansubuga, R., & Mugisha, P. (2019). Title.", "Kato, S. (2019). Another.", "Ssemwogerere, A. (2015). Never cited.", "Pamphlet with no author or date"]
    blocks = [Block(id=f"p{i}", kind="paragraph", text=t) for i, t in enumerate(paragraphs)] + [Block(id=f"r{i}", kind="reference", text=t) for i, t in enumerate(references)]
    items = {(i.kind, i.certainty, i.item) for i in paper_checks.check(DocumentModel(format="DOCX", blocks=blocks)).items}
    assert ("CITED_NOT_LISTED", "CONFIRMED", "(Byaruhanga, 2017)") in items
    assert ("CITED_NOT_LISTED", "POSSIBLE", "Kato (2018)") in items  # the list has Kato (2019): a different year
    assert ("LISTED_NOT_CITED", "CONFIRMED", "Ssemwogerere, A. (2015). Never cited.") in items
    assert ("UNREADABLE_REFERENCE", "UNDETERMINED", "Pamphlet with no author or date") in items
    assert not any(i[2].startswith("(Okello") or i[2].startswith("(Nansubuga") for i in items)


def test_paper_checks_make_no_claim_without_a_reference_list():
    from app.analysis import paper_checks

    result = paper_checks.check(read_docx(fixture_bytes("citations_in_text.docx")))
    assert [(i.kind, i.certainty) for i in result.items] == [("NO_REFERENCE_LIST", "UNDETERMINED")]


def test_every_style_forbids_new_facts_and_stronger_claims():
    from typing import get_args

    from app.ai.styles import writing_brief
    from app.jobs.models import WritingStyle

    for style in get_args(WritingStyle):
        brief = writing_brief(style, "LIGHT")
        assert "no new facts" in brief["style"] and "stronger" in brief["style"] and brief["intervention"].startswith("Light")


def test_the_scan_is_identical_across_processes():
    """The estimate and the job must send the lead identical requests (so the job replays the
    estimate's paid answers from the cache); Python's per-process hash seed must not leak in."""
    import os
    import subprocess
    import sys

    code = (
        "import json;from app.analysis import signals;from app.documents.docx_io import read_docx;from tests.conftest import fixture_bytes;"
        "s=signals.scan(read_docx(fixture_bytes('dissertation_long.docx')));"
        "print(json.dumps([s.evidence(),[b.evidence() for b in s.blocks],[f.model_dump() for b in s.blocks for f in b.findings]],sort_keys=True))"
    )
    outputs = {
        subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True, env={**os.environ, "PYTHONHASHSEED": seed}).stdout
        for seed in ("1", "2", "3")
    }
    assert len(outputs) == 1


# --- source check: code-enforced research rules (phase 4) -------------------------------------


def _research_doc():
    from app.documents.model import Block, DocumentModel

    return DocumentModel(
        format="DOCX",
        blocks=[
            Block(id="t", kind="title", text="Mobile Money in Lira"),
            Block(id="a", kind="paragraph", text="Achola Grace, Reg. No. 2020/HD06/1234"),
            Block(id="h1", kind="heading", level=1, text="1. Introduction", section="1. Introduction"),
            Block(id="p1", kind="paragraph", section="1. Introduction", text="By 2022, Uganda had more than 30 million mobile money accounts."),
            Block(id="h2", kind="heading", level=1, text="4. Results", section="4. Results"),
            Block(id="p2", kind="paragraph", section="4. Results", text="Of the 214 vendors, 187 (87%) had an active account."),
        ],
    )


def test_no_search_can_carry_the_papers_own_results_contact_details_or_front_matter_names():
    from app.analysis import research

    model = _research_doc()
    own, names = research.own_numbers(model), research.front_matter_names(model)
    assert research.safe_to_search("By 2022, Uganda had more than 30 million accounts.", "Uganda mobile money accounts 2022", own, names)
    assert not research.safe_to_search("187 vendors had an account.", "vendors mobile money 187", own, names)  # own finding
    assert not research.safe_to_search("A claim.", "Achola mobile money thesis", own, names)  # the student's name
    assert not research.safe_to_search("A claim.", "contact achola@example.com", own, names)
    assert not research.safe_to_search("A claim.", "x" * 200, own, names)  # an overlong query is not "minimal"


def test_only_urls_the_search_opened_are_accepted():
    from app.analysis import research

    opened = ["https://www.ucc.co.ug/report/?utm_source=openai", "https://fred.stlouisfed.org/data/UGA"]
    assert research.opened("https://WWW.UCC.co.ug/report", opened)
    assert research.opened("https://fred.stlouisfed.org/data/UGA/#top", opened)
    assert not research.opened("https://invented.example.org/report", opened)


def test_disagreeing_checks_make_a_claim_uncertain_never_stronger():
    from app.analysis.research import combine

    assert combine("SUPPORTED", "SUPPORTED") == "SUPPORTED"
    assert combine("SUPPORTED", "PARTLY_SUPPORTED") == combine("PARTLY_SUPPORTED", "SUPPORTED") == "PARTLY_SUPPORTED"
    assert combine("SUPPORTED", "CONTRADICTED") == combine("CONTRADICTED", "PARTLY_SUPPORTED") == "UNCERTAIN"
    assert combine("SUPPORTED", None) == "UNCERTAIN"  # a search alone never confirms a claim
    assert combine("NOT_FOUND", "SUPPORTED") == "NOT_FOUND"


def test_claims_are_quoted_from_the_paper_and_scale_with_length():
    from app.analysis.research import claims_for, verbatim

    assert verbatim("Uganda had more than 30 million", "By 2022, Uganda had  more than 30 million accounts.")
    assert not verbatim("Uganda had over 30 million", "By 2022, Uganda had more than 30 million accounts.")
    assert (claims_for(300, 10), claims_for(2000, 10), claims_for(20000, 10)) == (3, 8, 10)


def test_private_names_and_the_papers_own_work_never_reach_a_search():
    """Codex audit #3: the claim is checked too (the searching model sees it), and first-person
    reports of the paper's own work are never searched."""
    from app.analysis import research

    model = _research_doc()
    own, names = research.own_numbers(model), research.front_matter_names(model)
    assert not research.safe_to_search("Achola Grace found that traders save little.", "traders savings Uganda", own, names)
    assert not research.safe_to_search("Our interviews revealed that vendors distrust agents.", "vendors distrust mobile money agents", own, names)
    assert not research.safe_to_search("This study shows that balances are small.", "mobile money balances", own, names)
    assert research.safe_to_search("In the US, adoption rose after 2020.", "US mobile payments adoption 2020", own, names)
    assert not research.query_safe("Achola mobile money", own, names) and research.query_safe("mobile money Uganda 2022", own, names)


def test_a_quotation_must_really_be_on_the_page():
    from app.analysis.research import quote_found

    page = "<p>At the close of December 2022,\nregistered mobile money subscriptions equalled 36.8 million.</p>"
    assert quote_found("At the close of December 2022, registered mobile money subscriptions equalled 36.8 million", page)
    assert not quote_found("At the close of December 2022, registered mobile money subscriptions equalled 40 million", page)
    assert not quote_found("An invented passage that never appears on the source page at all", page)


def test_organisations_particles_and_openers_are_matched_not_flagged():
    """Codex audit #13: "World Health Organization (2021)" produced two false CONFIRMED errors."""
    from app.analysis import paper_checks
    from app.documents.model import Block, DocumentModel

    paragraphs = [
        "World Health Organization (2021) reported rising rates. As Kato (2019) noted, costs matter. Others agree (WHO, 2021; van der Berg, 2018).",
        "Earlier, Suri and Jack (2016) found gains (see Okello, 2021). Nobody (ibid.) disagrees.",
    ]
    references = ["World Health Organization (WHO). (2021). Global report. Geneva.", "Kato, S. (2019). Costs.", "van der Berg, J. (2018). Study.", "Suri, T., & Jack, W. (2016). Title.", "Okello, J. (2021). Phones."]
    blocks = [Block(id=f"p{i}", kind="paragraph", text=t) for i, t in enumerate(paragraphs)] + [Block(id=f"r{i}", kind="reference", text=t) for i, t in enumerate(references)]
    items = paper_checks.check(DocumentModel(format="DOCX", blocks=blocks)).items
    assert items == []  # every citation matched; "(ibid.)" has no year, so it is not a citation to check


def test_an_unmatched_organisation_is_only_ever_a_possible_mismatch():
    from app.analysis import paper_checks
    from app.documents.model import Block, DocumentModel

    blocks = [Block(id="p", kind="paragraph", text="Uganda Bureau of Statistics (2020) reported the census."), Block(id="r", kind="reference", text="Kato, S. (2019). Costs.")]
    certainties = {i.certainty for i in paper_checks.check(DocumentModel(format="DOCX", blocks=blocks)).items if i.kind == "CITED_NOT_LISTED"}
    assert certainties == {"POSSIBLE"}
