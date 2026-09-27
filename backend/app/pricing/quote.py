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
from app.core.config import Settings
from app.jobs.models import BoundQuote, Engine, Passage, QuoteLine, ServiceSelection, utcnow

PRICING_VERSION = "credits-v1"
CHARS_PER_WORD = 6.5  # prose plus JSON framing, measured on the fixture papers
ITEM_OVERHEAD = 160  # ids, keys and instructions around each passage in a payload


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


def analysis_usd(settings: Settings, words: int) -> float:
    return _step_usd(settings, "analyse", words * CHARS_PER_WORD + ITEM_OVERHEAD * max(1, words // 120), words)


def estimate_scan_usd(settings: Settings, words: int, intensity: str) -> float:
    """The most the refinement estimate can cost: the lead's analysis of the whole paper plus
    its draft plan for the share of the paper that intensity allows."""
    share = 0.25 if intensity == "LIGHT" else 0.5
    planned_words = max(150, share * words)
    plan = _step_usd(settings, "plan", planned_words * CHARS_PER_WORD * 1.4, planned_words)
    return analysis_usd(settings, words) + plan


def refinement_usd(settings: Settings, passages: list[Passage]) -> float:
    """The rest of the refinement once the draft plan exists: critique and final plan over every
    planned passage, then rewrite, review, one fix round and a second review of the rewrites."""
    if not passages:
        return 0.0
    all_chars = sum(p.chars + p.instruction_chars + ITEM_OVERHEAD for p in passages)
    all_words = sum(p.words for p in passages)
    rewrites = [p for p in passages if p.rewrite]
    rw_chars = sum(p.chars for p in rewrites)
    rw_words = sum(p.words for p in rewrites)
    usd = _step_usd(settings, "critique", all_chars, all_words)
    usd += _step_usd(settings, "finalise", all_chars + 250 * len(passages), all_words)
    if rewrites:
        n = len(rewrites)
        usd += _step_usd(settings, "refine", rw_chars + n * (800 + 200 + ITEM_OVERHEAD), rw_words)
        usd += _step_usd(settings, "review", 2 * rw_chars + n * (200 + ITEM_OVERHEAD), 2 * rw_words)
        usd += _step_usd(settings, "repair", 2 * rw_chars + n * (400 + ITEM_OVERHEAD), rw_words)
        usd += _step_usd(settings, "review", 2 * rw_chars + n * (200 + ITEM_OVERHEAD), 2 * rw_words)
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


# --- quote lines ------------------------------------------------------------------------------


def format_ugx(settings: Settings, words: int) -> int:
    return max(settings.format_min_ugx, math.ceil(words / 300) * settings.format_ugx_per_300_words)


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
    elif selection.writing == "REFINE":
        light = selection.intensity == "LIGHT"
        amount = with_margin(refinement_usd(settings, passages or []), settings)
        lines.append(QuoteLine(label=f"Check + Refine, {'light' if light else 'standard'} (up to)", amount=amount))
        ai += amount
    fixed = 0
    if selection.formatting == "FORMAT":
        fixed = format_ugx(settings, words)
        lines.append(QuoteLine(label="Academic formatting", amount=fixed))
    elif selection.formatting == "TEMPLATE_FORMAT":
        amount = with_margin(template_usd(settings, guide_words), settings)
        lines.append(QuoteLine(label="University template formatting (up to)", amount=amount))
        ai += amount
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
    )


def needs_estimate(selection: ServiceSelection) -> bool:
    """Only refinement needs a paid AI scan to size the work; everything else is priced from length."""
    return selection.writing == "REFINE"
