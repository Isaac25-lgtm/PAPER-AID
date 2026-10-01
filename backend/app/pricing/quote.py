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
from app.ai.orchestration import BATCH_WORDS, FINAL_PART_WORDS, PROMPTS, REVIEW_REPAIRS, STEPS, current_engine, model_for_engine
from app.analysis import research
from app.core.config import Settings
from app.jobs.models import BoundQuote, Engine, Passage, QuoteLine, ServiceSelection, utcnow

PRICING_VERSION = "credits-v1"  # actual AI spend × multiplier, quoted as a ceiling
FIXED_VERSION = "fixed-v1"  # fixed prices by page band (owner decision 2026-09-28)
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


def _step_usd(settings: Settings, task: str, payload_chars: float, words: float, engine: Engine | None = None) -> float:
    """Projected cost of one algorithm step over a payload, batched as the runner batches it, with
    the model and prompt version of the engine being priced (F9: an older engine's own prompts)."""
    engine = engine or current_engine(settings)
    step = STEPS[task]
    provider, _, model = model_for_engine(engine, task).partition(":")
    batches = max(1, math.ceil(words / BATCH_WORDS))
    per_batch = len(PROMPTS[engine.prompts.get(task, step.prompt)]) + payload_chars / batches
    return batches * costs.estimate_usd(provider, model, int(per_batch), step.max_tokens, settings.model_prices, engine.price_table)


# --- projections (USD of provider spend) ------------------------------------------------------


def _batches_for(words: float) -> int:
    return max(1, math.ceil(words / BATCH_WORDS))


def analysis_usd(settings: Settings, words: int, engine: Engine | None = None) -> float:
    e = engine or current_engine(settings)
    passages = max(1, words // 120)
    payload = words * CHARS_PER_WORD + (ITEM_OVERHEAD + SIGNAL_CHARS) * passages + BUNDLE_CHARS * _batches_for(words)
    usd = _step_usd(settings, "analyse", payload, words, e)
    if e.ai_check_peer_model:
        usd += _step_usd(settings, "analyse_peer", payload, words, e)
    # explicit coverage re-asks each checker once for the passages it skipped: at worst all of them
    return usd * (2 if e.explicit_coverage else 1)


ANCHOR_CHARS = 4000  # the objectives passages sent with every academic-review batch


def academic_usd(settings: Settings, words: int, engine: Engine | None = None) -> float:
    """The lead's academic, evidence and methodology review over every passage."""
    e = engine or current_engine(settings)
    passages = max(1, words // 120)
    payload = words * CHARS_PER_WORD + ITEM_OVERHEAD * passages + (ANCHOR_CHARS + BUNDLE_CHARS) * _batches_for(words)
    return _step_usd(settings, "academic", payload, words, e)


def estimate_scan_usd(settings: Settings, words: int, selection: ServiceSelection, engine: Engine | None = None) -> float:
    """The most the paid estimate can cost: the lead's analysis of the whole paper plus its draft
    plan for the share of the paper the service may change (a quarter or a half for refinement,
    all of it for Deep Redraft)."""
    e = engine or current_engine(settings)
    share = 1.0 if selection.writing == "REDRAFT" else 0.25 if selection.intensity == "LIGHT" else 0.5
    planned_words = max(150, share * words)
    plan = _step_usd(settings, "plan", planned_words * CHARS_PER_WORD * 1.4 + BRIEF_CHARS * _batches_for(planned_words), planned_words, e)
    return analysis_usd(settings, words, e) + plan


def refinement_usd(settings: Settings, passages: list[Passage], deep: bool = False, engine: Engine | None = None) -> float:
    """The rest of the refinement once the draft plan exists: critique and final plan over every
    planned passage, then rewrite, review, one fix round and a second review of the rewrites."""
    e = engine or current_engine(settings)
    if not passages:
        return 0.0
    all_chars = sum(p.chars + p.instruction_chars + ITEM_OVERHEAD for p in passages)
    all_words = sum(p.words for p in passages)
    rewrites = [p for p in passages if p.rewrite]
    rw_chars = sum(p.chars for p in rewrites)
    rw_words = sum(p.words for p in rewrites)
    brief = BRIEF_CHARS * _batches_for(all_words)
    usd = _step_usd(settings, "critique", all_chars + brief, all_words, e)
    if e.require_dual_approval and e.frontier_guidance:
        usd += _step_usd(settings, "guide", all_chars + brief, all_words, e)
    usd += _step_usd(settings, "finalise", all_chars + 250 * len(passages) + brief, all_words, e)
    if rewrites:
        n = len(rewrites)
        review_words = 2 * rw_words + n * REVIEW_CONTEXT_CHARS / CHARS_PER_WORD  # context counts toward batch size
        review_chars = 2 * rw_chars + n * (200 + ITEM_OVERHEAD + REVIEW_CONTEXT_CHARS) + BRIEF_CHARS * _batches_for(review_words)
        write, fix = ("redraft", "redraft_fix") if deep else ("refine", "repair")
        usd += _step_usd(settings, write, rw_chars + n * (800 + 200 + ITEM_OVERHEAD) + BRIEF_CHARS * _batches_for(rw_words), rw_words, e)
        rounds = settings.repair_attempts
        usd += (rounds + 1) * _step_usd(settings, "review", review_chars, review_words, e)
        if e.require_dual_approval and not e.single_reviewer:
            usd += (rounds + 1) * _step_usd(settings, "review_peer", review_chars, review_words, e)
        usd += rounds * _step_usd(settings, fix, 2 * rw_chars + n * (400 + ITEM_OVERHEAD) + BRIEF_CHARS * _batches_for(rw_words), rw_words, e)
    return usd


def source_check_usd(settings: Settings, words: int, engine: Engine | None = None) -> float:
    """The source check at its worst: finding the claims, every allowed search for every claim
    (each search's fee plus the pages it reads), and the writer's check of the evidence."""
    e = engine or current_engine(settings)
    claims = research.claims_for(words, settings.research_max_claims)
    if not claims:
        return 0.0
    usd = _step_usd(settings, "claims", words * CHARS_PER_WORD + ITEM_OVERHEAD * max(1, words // 120), words, e)
    provider, _, model = model_for_engine(e, "research").partition(":")
    searches = settings.research_max_searches
    per_claim = costs.estimate_usd(provider, model, 1500 + costs.SEARCH_INPUT_TOKENS_WORST * 4 * searches, STEPS["research"].max_tokens, settings.model_prices)
    usd += claims * (per_claim + costs.search_fee_usd(provider, searches))
    usd += _step_usd(settings, "verify", claims * 3200, claims * 450, e)
    return usd


def template_usd(settings: Settings, guide_words: int, engine: Engine | None = None) -> float:
    """University template rules: draft, critique and final rules, then every review and fix
    round allowed (the worst case)."""
    e = engine or current_engine(settings)
    guide = guide_words * CHARS_PER_WORD
    rounds = settings.repair_attempts
    usd = _step_usd(settings, "spec_plan", guide, 0, e)
    usd += _step_usd(settings, "spec_critique", guide + 4000, 0, e)
    if e.require_dual_approval and e.frontier_guidance:
        usd += _step_usd(settings, "spec_guide", guide + 4000, 0, e)
    usd += _step_usd(settings, "spec_finalise", guide + 8000, 0, e)
    usd += (rounds + 1) * _step_usd(settings, "spec_review", guide + 3000, 0, e)
    if e.require_dual_approval and not e.single_reviewer:
        usd += (rounds + 1) * _step_usd(settings, "spec_review_peer", guide + 3000, 0, e)
    usd += rounds * _step_usd(settings, "spec_fix", guide + 6000, 0, e)
    return usd


EVIDENCE_ITEM_CHARS = 420  # one evidence item as the models see it (statement, scope, source label, id)
PLAN_CHARS = 9000  # an approved plan with its alignment table
LIBRARY_ITEMS = 60  # evidence already in a project, as the planning steps see it


def proposal_usd(settings: Settings, step: str, words: int, engine: Engine | None = None) -> float:
    """A proposal step at its worst: every planned research need read in the scholarly index and
    also searched on the web, every finding checked, the plan or briefs negotiated, and (for a
    chapter) drafting, every review and fix round, and the readiness assessment. `words` is the
    chapter's target length."""
    e = engine or current_engine(settings)
    chapter = 0 if step == "PLAN" else 4 if step == "CONCEPT" else int(step[-1])
    needs = settings.proposal_needs.get(chapter, 6)
    searches = settings.research_max_searches
    provider, _, model = model_for_engine(e, "p_search").partition(":")
    usd = _step_usd(settings, "p_needs", PLAN_CHARS + LIBRARY_ITEMS * 200, 0, e)
    per_need = _step_usd(settings, "p_extract", settings.proposal_works_per_need * 3200, 0, e)
    per_need += costs.estimate_usd(provider, model, 1500 + costs.SEARCH_INPUT_TOKENS_WORST * 4 * searches, STEPS["p_search"].max_tokens, settings.model_prices)
    per_need += costs.search_fee_usd(provider, searches)
    usd += needs * per_need
    found = needs * 3
    usd += _step_usd(settings, "verify", found * 1600, found * 250, e)
    evidence_chars = (found + LIBRARY_ITEMS) * EVIDENCE_ITEM_CHARS
    first = "p_plan" if chapter == 0 else "p_brief"
    base = PLAN_CHARS + evidence_chars + (0 if chapter == 0 else 5000)
    usd += _step_usd(settings, first, base, 0, e) + _step_usd(settings, "p_critique", base + 10000, 0, e) + _step_usd(settings, "p_finalise", base + 20000, 0, e)
    if e.require_dual_approval and e.frontier_guidance:
        usd += _step_usd(settings, "p_guide", base + 10000, 0, e)
    if chapter == 0:
        if e.single_reviewer:  # the final review, and up to two targeted repairs each reviewed again
            usd += (REVIEW_REPAIRS + 1) * _step_usd(settings, "p_plan_review", base + 20000, 0, e) + REVIEW_REPAIRS * _step_usd(settings, "p_finalise", base + 24000, 0, e)
        elif e.require_dual_approval:
            usd += _step_usd(settings, "p_plan_review", base + 20000, 0, e) + _step_usd(settings, "p_plan_review_peer", base + 20000, 0, e)
        return usd
    batches = _batches_for(words)
    draft_input = batches * (PLAN_CHARS + BRIEF_CHARS) + found * EVIDENCE_ITEM_CHARS * 2 + words * 2
    usd += _step_usd(settings, "p_draft", draft_input, words, e)
    rounds = settings.repair_attempts
    review_input = batches * (PLAN_CHARS + 6000) + words * CHARS_PER_WORD * 2 + found * EVIDENCE_ITEM_CHARS * 2
    usd += (rounds + 1) * _step_usd(settings, "p_review", review_input, words * 2, e)
    if e.require_dual_approval and not e.single_reviewer:  # plus one review by both of any section code cleaned after the rounds
        usd += (rounds + 2) * _step_usd(settings, "p_review_peer", review_input, words * 2, e) + _step_usd(settings, "p_review", review_input, words * 2, e)
    elif e.require_dual_approval:  # one final reviewer: plus its review of any section code cleaned after the rounds
        usd += _step_usd(settings, "p_review", review_input, words * 2, e)
    usd += rounds * _step_usd(settings, "p_fix", draft_input + words * CHARS_PER_WORD, words, e)
    usd += _step_usd(settings, "p_readiness", PLAN_CHARS + words * CHARS_PER_WORD + 2 * 2500 * 12 + 4000, 0, e)
    return usd


SPEC_CHARS = 9000  # a resolved specification as the models see it
WORK_STUDENT_CHARS = 6000  # the student's own description, answers and experience


def work_usd(settings: Settings, step: str, kind: str, words: int, engine: Engine) -> float:
    """A work step at its worst (owner decision 2026-09-30): every research need read in the student's
    readings and the scholarly index and searched on the web, every finding checked; the plan drafted,
    reviewed and redrafted (for funding also the Results Model); the draft written, then every audit
    round (integrity, evaluation and repair), the whole-document review and its repair, and two
    compression rounds. `words` is the target length (READ: the documents' words; REVISE: the
    revised text)."""
    e = engine
    base = SPEC_CHARS + WORK_STUDENT_CHARS
    if step == "READ":  # every part of every document, in calls of at most READ_CHARS (works.pipeline.read_parts)
        from app.works.pipeline import READ_CHARS, READ_OVERLAP

        chars = words * CHARS_PER_WORD
        calls = max(1, math.ceil(chars / (READ_CHARS - READ_OVERLAP)))
        return calls * _step_usd(settings, "w_read", chars / calls + READ_OVERLAP + 4000, 0, e)
    usd = 0.0
    if step in ("PLAN", "DRAFT"):
        needs = 5 if step == "PLAN" else 8
        provider, _, model = model_for_engine(e, "w_search").partition(":")
        searches = settings.research_max_searches
        per_need = 2 * _step_usd(settings, "w_extract", settings.proposal_works_per_need * 3200, 0, e)
        per_need += costs.estimate_usd(provider, model, 1500 + costs.SEARCH_INPUT_TOKENS_WORST * 4 * searches, STEPS["w_search"].max_tokens, settings.model_prices, e.price_table)
        per_need += costs.search_fee_usd(provider, searches)
        found = needs * 3
        usd += _step_usd(settings, "w_needs", base + LIBRARY_ITEMS * 200, 0, e) + needs * per_need + _step_usd(settings, "w_verify", found * 1600, found * 250, e)
    evidence_chars = (8 * 3 + LIBRARY_ITEMS) * EVIDENCE_ITEM_CHARS
    if step == "PLAN":
        plan_chars = base + evidence_chars + 6000
        drafts, reviews = (REVIEW_REPAIRS + 1, REVIEW_REPAIRS + 1) if e.single_reviewer else (2, 1)
        usd += drafts * _step_usd(settings, "w_plan", plan_chars, 0, e) + reviews * _step_usd(settings, "w_plan_review", plan_chars + 8000, 0, e)
        if kind == "FUNDING_PROPOSAL":
            usd += drafts * _step_usd(settings, "w_results", plan_chars + 12000, 0, e) + reviews * _step_usd(settings, "w_results_review", plan_chars + 20000, 0, e)
        return usd
    batches = _batches_for(words)
    section_input = batches * (base + BRIEF_CHARS) + evidence_chars * 2 + words * 2
    review_input = batches * (base + 4000) + words * CHARS_PER_WORD * 2
    rounds = settings.repair_attempts
    if step == "DRAFT":
        usd += _step_usd(settings, "w_draft", section_input, words, e)
    else:  # REVISE: the requested changes first
        usd += _step_usd(settings, "w_repair", section_input + words * CHARS_PER_WORD, words, e)
    audits = REVIEW_REPAIRS + 1 if e.single_reviewer else 2
    for _ in range(audits):  # the audit, and the audit again after each of the final review's repairs
        usd += (rounds + 1) * (_step_usd(settings, "w_integrity", review_input, words * 2, e) + _step_usd(settings, "w_evaluate", review_input, words * 2, e))
        usd += rounds * _step_usd(settings, "w_repair", section_input + words * CHARS_PER_WORD, words, e)
        if e.roles.get("ADJUDICATOR"):
            usd += (rounds + 1) * _step_usd(settings, "w_adjudicate", review_input, words, e)
    if e.single_reviewer:
        # The final review of the whole deliverable (tables, references and notes included), in parts of
        # at most FINAL_PART_WORDS, after every change; up to two targeted repairs; compression and a
        # check of what it changed before each final review.
        parts = max(1, math.ceil(words * 1.3 / FINAL_PART_WORDS)) + (1 if words * 1.3 > FINAL_PART_WORDS else 0)  # a long section split across parts can add one
        final_chars = base + words * CHARS_PER_WORD * 1.5 / parts + 9000
        usd += (REVIEW_REPAIRS + 1) * parts * _step_usd(settings, "w_final", final_chars, 0, e) + REVIEW_REPAIRS * _step_usd(settings, "w_repair", section_input, words, e)
        usd += (REVIEW_REPAIRS + 1) * 2 * _step_usd(settings, "w_compress", section_input + words * CHARS_PER_WORD, words, e)
        usd += (REVIEW_REPAIRS + 1) * (_step_usd(settings, "w_integrity", review_input, words * 2, e) + _step_usd(settings, "w_evaluate", review_input, words * 2, e))
        return usd
    usd += 2 * _step_usd(settings, "w_final", base + words * CHARS_PER_WORD * 1.2 + 6000, 0, e) + _step_usd(settings, "w_repair", section_input, words, e)
    usd += 2 * _step_usd(settings, "w_compress", section_input + words * CHARS_PER_WORD, words, e)
    # What compression or withholding changed is reviewed again, as it will be published (Codex audit 2026-09-30 #2).
    usd += _step_usd(settings, "w_integrity", review_input, words * 2, e) + _step_usd(settings, "w_evaluate", review_input, words * 2, e)
    return usd


def revise_usd(settings: Settings, words: int, engine: Engine | None = None) -> float:
    """Sections revised from supervisor comments at their worst: the first fix, every review and
    further fix round, and the chapter's readiness check again. `words` is the revised text."""
    e = engine or current_engine(settings)
    batches = _batches_for(words)
    fix_input = batches * (PLAN_CHARS + BRIEF_CHARS) + LIBRARY_ITEMS * EVIDENCE_ITEM_CHARS + words * CHARS_PER_WORD * 2
    rounds = settings.repair_attempts
    usd = (rounds + 1) * _step_usd(settings, "p_fix", fix_input, words, e)
    review_input = batches * (PLAN_CHARS + 6000) + words * CHARS_PER_WORD * 2 + LIBRARY_ITEMS * EVIDENCE_ITEM_CHARS
    usd += (rounds + 1) * _step_usd(settings, "p_review", review_input, words * 2, e)
    if e.require_dual_approval and not e.single_reviewer:  # plus one review by both of any section code cleaned after the rounds
        usd += (rounds + 2) * _step_usd(settings, "p_review_peer", review_input, words * 2, e) + _step_usd(settings, "p_review", review_input, words * 2, e)
    elif e.require_dual_approval:  # one final reviewer: plus its review of any section code cleaned after the rounds
        usd += _step_usd(settings, "p_review", review_input, words * 2, e)
    usd += _step_usd(settings, "p_readiness", PLAN_CHARS + 12000 * CHARS_PER_WORD + 2 * 2500 * 12 + 4000, 0, e)
    return usd


def profile_usd(settings: Settings, guide_words: int, engine: Engine | None = None) -> float:
    """An institution profile: the lead drafts it from the whole guide, the writer critiques it and
    the lead finalises it (each call reads the guide)."""
    e = engine or current_engine(settings)
    guide = guide_words * CHARS_PER_WORD + 12000
    usd = _step_usd(settings, "p_profile", guide, 0, e) + _step_usd(settings, "p_profile_critique", guide + 8000, 0, e) + _step_usd(settings, "p_profile_finalise", guide + 12000, 0, e)
    if e.require_dual_approval and e.frontier_guidance:
        usd += _step_usd(settings, "p_profile_guide", guide + 8000, 0, e)
    if e.require_dual_approval:  # the approval of the finished profile (both reviewers on older engines)
        usd += _step_usd(settings, "p_profile_review", guide + 16000, 0, e)
        if not e.single_reviewer:
            usd += _step_usd(settings, "p_profile_review_peer", guide + 16000, 0, e)
        else:  # up to two targeted repairs, each reviewed again
            usd += REVIEW_REPAIRS * (_step_usd(settings, "p_profile_finalise", guide + 16000, 0, e) + _step_usd(settings, "p_profile_review", guide + 16000, 0, e))
    return usd


def proposal_review_usd(settings: Settings, words: int, engine: Engine | None = None) -> float:
    """The lead's audit of an uploaded proposal: one call over the whole text."""
    e = engine or current_engine(settings)
    return _step_usd(settings, "p_audit", words * CHARS_PER_WORD + 150 * max(1, words // 120) + 12000, 0, e)


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
    ai_ugx: int  # the AI part of the price
    fixed_ugx: int
    budget_usd: float  # the provider-spend cap: the worst-case projection with the safety margin


def band_factor(settings: Settings, words: int) -> float:
    """Each fixed price covers up to `band_pages` pages; each further band adds `band_step` of it."""
    pages = max(1, math.ceil(words / settings.words_per_page))
    return 1 + settings.band_step * (math.ceil(pages / settings.band_pages) - 1)


def fixed_price(settings: Settings, key: str, words: int | None) -> int:
    """A service's fixed price in UGX (students see it in tokens). `words` None: not banded."""
    factor = band_factor(settings, words) if words is not None else 1.0
    return round_up(settings.fixed_tokens[key] * factor * settings.ugx_per_token)


def worst_passages(words: int, share: float) -> list[Passage]:
    """Without an estimate: the most a refinement may rewrite, as 150-word passages."""
    target = max(150, int(words * share))
    count = max(1, target // 150)
    return [Passage(chars=int(150 * CHARS_PER_WORD), words=150, rewrite=True) for _ in range(count)]


def price(
    settings: Settings,
    selection: ServiceSelection,
    words: int,
    guide_words: int = 0,
    passages: list[Passage] | None = None,
    fee_paid: int = 0,
    scope_words: int | None = None,
    engine: Engine | None = None,
    part: float = 1.0,
    cap: int | None = None,
    note: str = "",
) -> Priced:
    """Quote lines for a selection. Under the fixed policy each AI service has its price by page
    band; under the cost policy (refinement priced from its estimate's `passages`) each is its
    worst-case AI cost as a ceiling. Either way the job's spend cap is the worst-case projection,
    so quality is never cut to fit a price."""
    fixed_mode = settings.pricing_mode == "fixed"
    e = engine or current_engine(settings)
    label_note = f": {note}" if note else ""  # the engine the run will execute with (its routes and prompts)
    services: list[tuple[str, str, float, int | None]] = []  # (key, label, worst-case USD, banded words)
    if selection.writing == "AI_CHECK":
        services.append(("AI_CHECK", "Writing check", analysis_usd(settings, words, e), words))
    elif selection.writing in ("REFINE", "REDRAFT"):
        deep = selection.writing == "REDRAFT"
        light = selection.intensity == "LIGHT" and not deep
        share = 1.0 if deep or selection.only_blocks else 0.25 if light else 0.5
        scope = scope_words or words  # "Fix selected": the chosen passages, not the whole paper
        planned = passages or worst_passages(scope, share)
        usd = refinement_usd(settings, planned, deep=deep, engine=e) + (0 if passages else analysis_usd(settings, words, e))
        if e.ai_check_peer_model:
            usd += analysis_usd(settings, words, e)  # the finished paper is independently checked again
        key = "REDRAFT" if deep else "REFINE_LIGHT" if light else "REFINE"
        label = "Deep redraft" if deep else f"Check + Refine, {'light' if light else 'standard'}"
        services.append((key, label, usd, scope))
    if selection.academic and selection.writing in ("AI_CHECK", "REFINE", "REDRAFT"):
        services.append(("ACADEMIC", "Academic, evidence and method review", academic_usd(settings, words, e), words))
    if selection.source_check:
        services.append(("SOURCE_CHECK", "Source check with live search", source_check_usd(settings, words, e), words))
    if selection.proposal == "REVIEW":
        services.append(("REVIEW", "Proposal review", proposal_review_usd(settings, words, e), words))
    elif selection.proposal == "PROFILE":
        services.append(("PROFILE", "Your institution's guide, read into a profile", profile_usd(settings, guide_words, e), None))
    elif selection.proposal.startswith("REVISE_"):
        banded = scope_words or words
        services.append(("REVISE", f"Chapter {selection.proposal[-1]} revised from your supervisor's comments", revise_usd(settings, banded, e), banded))
    elif selection.proposal != "NONE":
        label = {"PLAN": "Proposal plan", "CONCEPT": "Concept paper"}.get(selection.proposal, f"Chapter {selection.proposal[-1]}")
        if selection.finish:  # "Finish chapter": the sections still to write, priced at `part`, their share
            label += ": the sections still to write"
        services.append((selection.proposal, label, proposal_usd(settings, selection.proposal, words, e), None))
    if selection.formatting == "TEMPLATE_FORMAT":
        services.append(("TEMPLATE_FORMAT", "University template formatting", template_usd(settings, guide_words, e), words))
    if selection.work != "NONE":
        banded = words if selection.work == "REVISE" else None
        usd = work_usd(settings, selection.work, selection.work_kind, words, e)
        ceiling = settings.work_budget_cap_usd.get(selection.work_kind)
        services.append((selection.work_band, WORK_LABELS.get(selection.work_band, selection.work_band) + label_note, min(usd, ceiling) if ceiling else usd, banded))

    if selection.bundled:
        services = _bundled(settings, selection, services, fixed_mode)
    lines: list[QuoteLine] = []
    if fee_paid:
        lines.append(QuoteLine(label="AI estimate (already paid, counts toward this job)", amount=fee_paid))
    ai = 0
    plan_key = _plan_key(selection) if selection.bundled else None
    for key, label, usd, banded in services:
        if key.endswith(":BUNDLED"):  # read or plan within one Start: charged with the document
            lines.append(QuoteLine(label=label, amount=0, service=key.split(":")[0]))
            continue
        amount = fixed_price(settings, key, banded) if fixed_mode else with_margin(usd, settings)
        if plan_key and key not in BUNDLE_FREE and fixed_mode and plan_key in settings.fixed_tokens:
            amount += fixed_price(settings, plan_key, None)
            label += ", plan included"
        if part < 1.0 and selection.finish:
            amount = round_up(amount * part)
        if cap is not None and selection.finish:  # what the chapter has not yet cost (Codex review #3)
            amount = min(amount, cap)
        lines.append(QuoteLine(label=label if fixed_mode else f"{label} (up to)", amount=amount, service=key))
        ai += amount
    fixed = 0
    if selection.formatting == "FORMAT":
        fixed = format_ugx(settings, words)
        lines.append(QuoteLine(label="Academic formatting", amount=fixed, service="FORMAT"))
    if selection.latex:
        conversion = latex_ugx(settings, words)
        lines.append(QuoteLine(label="LaTeX conversion", amount=conversion, service="LATEX"))
        fixed += conversion
    budget = sum(usd for _, _, usd, _ in services) * (1 + settings.quote_safety_margin)
    return Priced(lines=lines, ai_ugx=ai, fixed_ugx=fixed, budget_usd=budget)


BUNDLE_FREE = {"WORK_READ", "CW_PLAN", "CN_PLAN", "FP_PLAN", "PLAN"}


def _bundled(settings: Settings, selection: ServiceSelection, services: list[tuple[str, str, float, int | None]], fixed_mode: bool) -> list[tuple[str, str, float, int | None]]:
    """One Start, one charge (owner decision 2026-10-01): reading the student's documents and the plan
    cost nothing on their own (their spend cap stays real); the first document carries the plan's
    price, so a document that fails returns everything that was charged."""
    out = []
    for key, label, usd, banded in services:
        if key in BUNDLE_FREE:
            out.append((f"{key}:BUNDLED", label + " (part of your document)", usd, banded))
        else:
            out.append((key, label, usd, banded))
    return out


def _plan_key(selection: ServiceSelection) -> str | None:
    """The plan whose price a bundled first document carries."""
    if selection.work == "DRAFT" and selection.work_band:
        return selection.work_band.split("_")[0] + "_PLAN"
    if selection.proposal in ("CHAPTER_1", "CONCEPT"):
        return "PLAN"
    return None


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
    scope_words: int | None = None,
    part: float = 1.0,
    cap: int | None = None,
    note: str = "",
) -> BoundQuote:
    """A quote bound to the exact files, selection and engine it priced, with the rate and
    multiplier frozen. `fee_paid` is every estimate already charged on the job: it counts toward the
    quote, so accepting holds only the rest."""
    priced = price(settings, selection, words, guide_words, passages, fee_paid, scope_words, engine=engine, part=part, cap=cap, note=note)
    return BoundQuote(
        id=f"quote_{secrets.token_hex(6)}",
        lines=priced.lines,
        amount=sum(line.amount for line in priced.lines),
        paid=fee_paid,
        pricing_version=FIXED_VERSION if settings.pricing_mode == "fixed" else PRICING_VERSION,
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
        budget_usd=priced.budget_usd if settings.pricing_mode == "fixed" else 0.0,
    )


WORK_LABELS = {
    "WORK_READ": "Reading your documents", "WORK_REVISE": "Your requested changes",
    "CN_PLAN": "Concept note plan", "CN_BRIEF": "Concept note, brief", "CN_STANDARD": "Concept note, standard", "CN_EXTENDED": "Concept note, extended",
    "CW_PLAN": "Coursework plan", "CW_1500": "Coursework draft, up to 1,500 words", "CW_3000": "Coursework draft, up to 3,000 words",
    "CW_5000": "Coursework draft, up to 5,000 words", "CW_8000": "Coursework draft, up to 8,000 words",
    "FP_PLAN": "Funding proposal plan and Results Model", "FP_COMPACT": "Funding proposal, compact", "FP_STANDARD": "Funding proposal, standard",
    "FP_COMPREHENSIVE": "Funding proposal, comprehensive",
}
# Every token price a work service needs (owner sets them from the benchmark; none are invented).
WORK_PRICE_KEYS: dict[str, tuple[str, ...]] = {
    "CONCEPT_NOTE": ("WORK_READ", "CN_PLAN", "CN_BRIEF", "CN_STANDARD", "CN_EXTENDED", "WORK_REVISE"),
    "COURSEWORK": ("WORK_READ", "CW_PLAN", "CW_1500", "CW_3000", "CW_5000", "CW_8000", "WORK_REVISE"),
    "FUNDING_PROPOSAL": ("WORK_READ", "FP_PLAN", "FP_COMPACT", "FP_STANDARD", "FP_COMPREHENSIVE", "WORK_REVISE"),
}


def work_prices_set(settings: Settings, service: str) -> bool:
    """A work service can be offered only with every one of its prices (the cost policy needs none)."""
    if settings.pricing_mode != "fixed":
        return True
    return all(settings.fixed_tokens.get(key, 0) > 0 for key in WORK_PRICE_KEYS.get(service, ("",)))


def needs_estimate(selection: ServiceSelection, settings: Settings) -> bool:
    """Under the cost policy, refinement and Deep Redraft are priced from an AI scan. Under fixed
    prices only Deep Redraft runs one, uncharged, to show how much of the paper it would change."""
    if settings.pricing_mode == "fixed":
        return selection.writing == "REDRAFT"
    return selection.writing in ("REFINE", "REDRAFT")


def estimate_charged(settings: Settings) -> bool:
    return settings.credits_enabled and settings.pricing_mode == "cost"
