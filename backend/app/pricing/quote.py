"""The one pricing formula (owner decision 2026-09-24). The browser only displays what this returns.

There is no price list. A job is charged its actual AI spend × `price_multiplier`, converted to
UGX at `ugx_per_usd`, and never more than its quote. A quote is therefore a ceiling: the AI work
the job is expected to need, projected call by call with the same cost estimate the budget guard
uses before every paid call, plus `quote_safety_margin`. APA/Harvard formatting uses no AI and is
the one fixed price: `format_ugx_per_300_words` (about a page), with a minimum.

Every amount is rounded up to the next UGX 100.
"""

import math
import secrets
from dataclasses import dataclass
from datetime import timedelta

from app.ai import costs
from app.ai.orchestration import BATCH_WORDS, PROMPTS, STEPS
from app.analysis import research
from app.core.config import Settings
from app.jobs.models import BoundQuote, Engine, Passage, QuoteLine, ServiceSelection, utcnow

PRICING_VERSION = "credits-v1"
CHARS_PER_WORD = 6.5  # prose plus JSON framing, measured on the fixture papers
ITEM_OVERHEAD = 160  # ids, keys and instructions around each passage in a payload
SIGNAL_CHARS = 250  # PaperAid's measurements travelling with each passage to the analysis
BUNDLE_CHARS = 2500  # the document-level evidence bundle, sent with every analysis batch
BRIEF_CHARS = 800  # the student's style and intervention level, sent with every planning/writing batch
REVIEW_CONTEXT_CHARS = 1600  # neighbours, linked passages and the post-scan sent with each reviewed rewrite


def round_up(ugx: float) -> int:
    return int(math.ceil(max(0.0, ugx) / 100.0) * 100)


def to_ugx(usd: float, settings: Settings) -> int:
    """What the student pays for `usd` of AI spend."""
    return round_up(usd * settings.price_multiplier * settings.ugx_per_usd)


def ai_cap_usd(ugx: int, settings: Settings) -> float:
    """The provider spend a UGX amount can pay for while keeping the margin."""
    return ugx / settings.ugx_per_usd / settings.price_multiplier


def _step_usd(settings: Settings, task: str, payload_chars: float, words: float) -> float:
    """Projected cost of one algorithm step over a payload, batched as the runner batches it."""
    step = STEPS[task]
    ref = settings.lead_model if step.role == "lead" else settings.writer_model
    provider, _, model = ref.partition(":")
    batches = max(1, math.ceil(words / BATCH_WORDS))
    per_batch = len(PROMPTS[step.prompt]) + payload_chars / batches
    return batches * costs.estimate_usd(provider, model, int(per_batch), step.max_tokens, settings.model_prices)


# --- projections (USD of provider spend) ------------------------------------------------------


def _batches_for(words: float) -> int:
    return max(1, math.ceil(words / BATCH_WORDS))


def analysis_usd(settings: Settings, words: int) -> float:
    passages = max(1, words // 120)
    payload = words * CHARS_PER_WORD + (ITEM_OVERHEAD + SIGNAL_CHARS) * passages + BUNDLE_CHARS * _batches_for(words)
    return _step_usd(settings, "analyse", payload, words)


def estimate_scan_usd(settings: Settings, words: int, selection: ServiceSelection) -> float:
    """The most the paid estimate can cost: the lead's analysis of the whole paper plus its draft
    plan for the share of the paper the service may change (a quarter or a half for refinement,
    all of it for Deep Redraft)."""
    share = 1.0 if selection.writing == "REDRAFT" else 0.25 if selection.intensity == "LIGHT" else 0.5
    planned_words = max(150, share * words)
    plan = _step_usd(settings, "plan", planned_words * CHARS_PER_WORD * 1.4 + BRIEF_CHARS * _batches_for(planned_words), planned_words)
    return analysis_usd(settings, words) + plan


def refinement_usd(settings: Settings, passages: list[Passage], deep: bool = False) -> float:
    """The rest of the refinement once the draft plan exists: critique and final plan over every
    planned passage, then rewrite, review, one fix round and a second review of the rewrites."""
    if not passages:
        return 0.0
    all_chars = sum(p.chars + p.instruction_chars + ITEM_OVERHEAD for p in passages)
    all_words = sum(p.words for p in passages)
    rewrites = [p for p in passages if p.rewrite]
    rw_chars = sum(p.chars for p in rewrites)
    rw_words = sum(p.words for p in rewrites)
    brief = BRIEF_CHARS * _batches_for(all_words)
    usd = _step_usd(settings, "critique", all_chars + brief, all_words)
    usd += _step_usd(settings, "finalise", all_chars + 250 * len(passages) + brief, all_words)
    if rewrites:
        n = len(rewrites)
        review_words = 2 * rw_words + n * REVIEW_CONTEXT_CHARS / CHARS_PER_WORD  # context counts toward batch size
        review_chars = 2 * rw_chars + n * (200 + ITEM_OVERHEAD + REVIEW_CONTEXT_CHARS) + BRIEF_CHARS * _batches_for(review_words)
        write, fix = ("redraft", "redraft_fix") if deep else ("refine", "repair")
        usd += _step_usd(settings, write, rw_chars + n * (800 + 200 + ITEM_OVERHEAD) + BRIEF_CHARS * _batches_for(rw_words), rw_words)
        usd += _step_usd(settings, "review", review_chars, review_words)
        usd += _step_usd(settings, fix, 2 * rw_chars + n * (400 + ITEM_OVERHEAD) + BRIEF_CHARS * _batches_for(rw_words), rw_words)
        usd += _step_usd(settings, "review", review_chars, review_words)
    return usd


def source_check_usd(settings: Settings, words: int) -> float:
    """The source check at its worst: finding the claims, every allowed search for every claim
    (each search's fee plus the pages it reads), and the writer's check of the evidence."""
    claims = research.claims_for(words, settings.research_max_claims)
    if not claims:
        return 0.0
    usd = _step_usd(settings, "claims", words * CHARS_PER_WORD + ITEM_OVERHEAD * max(1, words // 120), words)
    provider, _, model = settings.lead_model.partition(":")
    searches = settings.research_max_searches
    per_claim = costs.estimate_usd(provider, model, 1500 + costs.SEARCH_INPUT_TOKENS_WORST * 4 * searches, STEPS["research"].max_tokens, settings.model_prices)
    usd += claims * (per_claim + costs.search_fee_usd(provider, searches))
    usd += _step_usd(settings, "verify", claims * 3200, claims * 450)
    return usd


def template_usd(settings: Settings, guide_words: int) -> float:
    """University template rules: draft, critique and final rules, then every review and fix
    round allowed (the worst case)."""
    guide = guide_words * CHARS_PER_WORD
    rounds = settings.repair_attempts
    usd = _step_usd(settings, "spec_plan", guide, 0)
    usd += _step_usd(settings, "spec_critique", guide + 4000, 0)
    usd += _step_usd(settings, "spec_finalise", guide + 8000, 0)
    usd += (rounds + 1) * _step_usd(settings, "spec_review", guide + 3000, 0)
    usd += rounds * _step_usd(settings, "spec_fix", guide + 6000, 0)
    return usd


EVIDENCE_ITEM_CHARS = 420  # one evidence item as the models see it (statement, scope, source label, id)
PLAN_CHARS = 9000  # an approved plan with its alignment table
LIBRARY_ITEMS = 60  # evidence already in a project, as the planning steps see it


def proposal_usd(settings: Settings, step: str, words: int) -> float:
    """A proposal step at its worst: every planned research need read in the scholarly index and
    also searched on the web, every finding checked, the plan or briefs negotiated, and (for a
    chapter) drafting, every review and fix round, and the readiness assessment. `words` is the
    chapter's target length."""
    chapter = 0 if step == "PLAN" else int(step[-1])
    needs = settings.proposal_needs.get(chapter, 6)
    searches = settings.research_max_searches
    provider, _, model = settings.lead_model.partition(":")
    usd = _step_usd(settings, "p_needs", PLAN_CHARS + LIBRARY_ITEMS * 200, 0)
    per_need = _step_usd(settings, "p_extract", settings.proposal_works_per_need * 3200, 0)
    per_need += costs.estimate_usd(provider, model, 1500 + costs.SEARCH_INPUT_TOKENS_WORST * 4 * searches, STEPS["p_search"].max_tokens, settings.model_prices)
    per_need += costs.search_fee_usd(provider, searches)
    usd += needs * per_need
    found = needs * 3
    usd += _step_usd(settings, "verify", found * 1600, found * 250)
    evidence_chars = (found + LIBRARY_ITEMS) * EVIDENCE_ITEM_CHARS
    first = "p_plan" if chapter == 0 else "p_brief"
    base = PLAN_CHARS + evidence_chars + (0 if chapter == 0 else 5000)
    usd += _step_usd(settings, first, base, 0) + _step_usd(settings, "p_critique", base + 10000, 0) + _step_usd(settings, "p_finalise", base + 20000, 0)
    if chapter == 0:
        return usd
    batches = _batches_for(words)
    draft_input = batches * (PLAN_CHARS + BRIEF_CHARS) + found * EVIDENCE_ITEM_CHARS * 2 + words * 2
    usd += _step_usd(settings, "p_draft", draft_input, words)
    rounds = settings.repair_attempts
    review_input = batches * (PLAN_CHARS + 6000) + words * CHARS_PER_WORD * 2 + found * EVIDENCE_ITEM_CHARS * 2
    usd += (rounds + 1) * _step_usd(settings, "p_review", review_input, words * 2)
    usd += rounds * _step_usd(settings, "p_fix", draft_input + words * CHARS_PER_WORD, words)
    usd += _step_usd(settings, "p_readiness", PLAN_CHARS + words * CHARS_PER_WORD + 2 * 2500 * 12 + 4000, 0)
    return usd


def proposal_review_usd(settings: Settings, words: int) -> float:
    """The lead's audit of an uploaded proposal: one call over the whole text."""
    return _step_usd(settings, "p_audit", words * CHARS_PER_WORD + 150 * max(1, words // 120) + 12000, 0)


# --- quote lines ------------------------------------------------------------------------------


def format_ugx(settings: Settings, words: int) -> int:
    return max(settings.format_min_ugx, math.ceil(words / 300) * settings.format_ugx_per_300_words)


def latex_ugx(settings: Settings, words: int) -> int:
    return max(settings.latex_min_ugx, math.ceil(words / 300) * settings.latex_ugx_per_300_words)


def with_margin(ugx_usd: float, settings: Settings) -> int:
    return to_ugx(ugx_usd * (1 + settings.quote_safety_margin), settings)


@dataclass(frozen=True)
class Priced:
    lines: list[QuoteLine]
    ai_ugx: int  # the AI part of the ceiling; its USD equivalent is the job's spend cap
    fixed_ugx: int


def price(
    settings: Settings,
    selection: ServiceSelection,
    words: int,
    guide_words: int = 0,
    passages: list[Passage] | None = None,
    fee_paid: int = 0,
) -> Priced:
    """Quote lines for a selection. Refinement needs `passages` from its estimate."""
    lines: list[QuoteLine] = []
    ai = 0
    if fee_paid:
        lines.append(QuoteLine(label="AI estimate (already paid, counts toward this job)", amount=fee_paid))
    if selection.writing == "AI_CHECK":
        amount = with_margin(analysis_usd(settings, words), settings)
        lines.append(QuoteLine(label="AI Check (up to)", amount=amount))
        ai += amount
    elif selection.writing == "REDRAFT":
        amount = with_margin(refinement_usd(settings, passages or [], deep=True), settings)
        lines.append(QuoteLine(label="Deep redraft (up to)", amount=amount))
        ai += amount
    elif selection.writing == "REFINE":
        light = selection.intensity == "LIGHT"
        amount = with_margin(refinement_usd(settings, passages or []), settings)
        lines.append(QuoteLine(label=f"Check + Refine, {'light' if light else 'standard'} (up to)", amount=amount))
        ai += amount
    if selection.source_check:
        amount = with_margin(source_check_usd(settings, words), settings)
        lines.append(QuoteLine(label="Source check with live search (up to)", amount=amount))
        ai += amount
    if selection.proposal == "REVIEW":
        amount = with_margin(proposal_review_usd(settings, words), settings)
        lines.append(QuoteLine(label="Proposal review against the UCU manual (up to)", amount=amount))
        ai += amount
    elif selection.proposal != "NONE":
        label = "Proposal plan with research (up to)" if selection.proposal == "PLAN" else f"Chapter {selection.proposal[-1]} with research, review and readiness check (up to)"
        amount = with_margin(proposal_usd(settings, selection.proposal, words), settings)
        lines.append(QuoteLine(label=label, amount=amount))
        ai += amount
    fixed = 0
    if selection.formatting == "FORMAT":
        fixed = format_ugx(settings, words)
        lines.append(QuoteLine(label="Academic formatting", amount=fixed))
    elif selection.formatting == "TEMPLATE_FORMAT":
        amount = with_margin(template_usd(settings, guide_words), settings)
        lines.append(QuoteLine(label="University template formatting (up to)", amount=amount))
        ai += amount
    if selection.latex:
        conversion = latex_ugx(settings, words)
        lines.append(QuoteLine(label="LaTeX conversion", amount=conversion))
        fixed += conversion
    return Priced(lines=lines, ai_ugx=ai, fixed_ugx=fixed)


def bound_quote(
    settings: Settings,
    selection: ServiceSelection,
    source_sha256: str,
    words: int,
    engine: Engine,
    guideline_sha256: str | None = None,
    guide_words: int = 0,
    passages: list[Passage] | None = None,
    fee_paid: int = 0,
    estimate_id: str | None = None,
) -> BoundQuote:
    """A quote bound to the exact files, selection and engine it priced, with the rate and
    multiplier frozen. `fee_paid` is every estimate already charged on the job: it counts toward the
    quote, so accepting holds only the rest."""
    priced = price(settings, selection, words, guide_words, passages, fee_paid)
    return BoundQuote(
        id=f"quote_{secrets.token_hex(6)}",
        lines=priced.lines,
        amount=sum(line.amount for line in priced.lines),
        paid=fee_paid,
        pricing_version=PRICING_VERSION,
        expires_at=utcnow() + timedelta(minutes=settings.quote_ttl_minutes),
        selection=selection,
        source_sha256=source_sha256,
        guideline_sha256=guideline_sha256,
        word_count=words,
        fixed_ugx=priced.fixed_ugx,
        ugx_per_usd=settings.ugx_per_usd,
        multiplier=settings.price_multiplier,
        engine=engine,
        estimate_id=estimate_id,
    )


def needs_estimate(selection: ServiceSelection) -> bool:
    """Refinement and Deep Redraft need a paid AI scan to size the work; everything else is priced from length."""
    return selection.writing in ("REFINE", "REDRAFT")
