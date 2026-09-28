"""How a job's credits end: charged on completion, released and refunded on failure, released on
cancellation. Each function runs inside the store transaction that changes the job's status, so
the status and the money can never disagree, and the job's `billing.state` makes each one happen
at most once."""

from app.jobs.models import Job, PaymentStatus, Wallet
from app.pricing import credits
from app.pricing.quote import FIXED_VERSION, round_up


def hold_for_job(j: Job, w: Wallet) -> int:
    """Hold what accepting the quote can still cost: the quote minus the estimate already paid."""
    assert j.quote is not None
    amount = max(0, j.quote.amount - j.billing.fee_paid)
    credits.hold(w, amount, j.id, "Held for your job (the most it can cost)")
    j.billing.held, j.billing.state = amount, "HELD"
    j.payment_status = PaymentStatus.PENDING
    return amount


def delivered_share(j: Job, service: str) -> float:
    """How much of a service the student actually received (fixed prices, owner decision
    2026-09-28): a FULL result is charged in full; a PARTIAL one only for what was delivered."""
    if service in ("REFINE", "REFINE_LIGHT", "REDRAFT"):
        r = j.refinement
        if r is None or not r.targeted_blocks:
            return 0.25  # nothing needed rewriting: the analysis and plan were delivered
        return max(0.25, r.refined_blocks / r.targeted_blocks)
    if service == "SOURCE_CHECK":
        research = j.research
        return research.checked / research.candidates if research and research.candidates else 1.0
    if service == "ACADEMIC":
        return 0.5 if any("academic review reached" in w for w in j.warnings) else 1.0
    if service in ("PLAN", "CHAPTER_1", "CHAPTER_2", "CHAPTER_3"):
        return 1.0 if j.outcome != "PARTIAL" else 0.75
    return 1.0


def _fixed_charge(j: Job) -> int:
    q = j.quote
    assert q is not None
    total = 0
    for line in q.lines:
        if not line.service:  # an estimate already paid: never charged twice
            continue
        total += round_up(line.amount * min(1.0, delivered_share(j, line.service)))
    return total


def settle_completed(j: Job, w: Wallet) -> None:
    """Charge a completed job. Fixed prices: each line's price for what was delivered. The cost
    policy: its actual AI spend × the quote's multiplier (refinement scaled by the share of planned
    passages delivered), plus any fixed formatting price. Never more than what is held; the rest
    of the hold returns to the balance."""
    b, q = j.billing, j.quote
    if b.state != "HELD" or q is None:
        return
    if q.pricing_version == FIXED_VERSION:
        charge = min(b.held, _fixed_charge(j))
        credits.settle(w, held=b.held, charge=charge, job_id=j.id, note="PaperAid job")
        b.charged, b.held, b.state = charge, 0, "SETTLED"
        j.payment_status = PaymentStatus.PAID
        return
    share = 1.0
    if j.refinement and j.refinement.targeted_blocks:
        share = j.refinement.refined_blocks / j.refinement.targeted_blocks
    job_usd = (j.cost_usd - j.estimate_cost_usd) - j.refine_cost_usd * (1 - share)
    ai = min(max(0, q.amount - q.paid - q.fixed_ugx), round_up(job_usd * q.multiplier * q.ugx_per_usd))
    fee_due = q.paid if b.fee_paid == 0 else 0  # the estimate, if an earlier failure refunded it
    charge = min(b.held, ai + q.fixed_ugx + fee_due)
    credits.settle(w, held=b.held, charge=charge, job_id=j.id, note="PaperAid job")
    b.charged, b.fee_paid, b.held, b.state = charge - fee_due, b.fee_paid + fee_due, 0, "SETTLED"
    j.payment_status = PaymentStatus.PAID


def release_hold(j: Job, w: Wallet, reason: str) -> None:
    """Return the whole hold (the job never ran)."""
    b = j.billing
    if b.state == "HELD":
        credits.settle(w, held=b.held, charge=0, job_id=j.id, note=reason)
        b.held, b.state = 0, "RELEASED"
        j.payment_status = PaymentStatus.REFUNDED


def refund_job(j: Job, w: Wallet, reason: str) -> None:
    """A failed job, or one an admin stops: nothing is charged and the estimate is refunded too."""
    release_hold(j, w, reason)
    b = j.billing
    if b.fee_paid:
        credits.refund(w, b.fee_paid, j.id, "AI estimate refunded")
        b.refunded += b.fee_paid
        b.fee_paid = 0
    j.payment_status = PaymentStatus.REFUNDED
