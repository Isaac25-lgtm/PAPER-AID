"""Wallet operations: the only code that moves credits. Each function changes a Wallet and appends
one ledger entry. They run inside a store transaction together with the job they concern, so the
job's `billing` record and the wallet always change together; that record is what makes every
operation happen at most once per job generation."""

import secrets
from typing import Literal

from app.core.errors import AppError
from app.jobs.models import LedgerEntry, Wallet, utcnow

MAX_ENTRIES = 300
Kind = Literal["TOP_UP", "HOLD", "CHARGE", "RELEASE", "REFUND"]


def tokens(ugx: int) -> str:
    """A UGX amount as students see it: credits, to one decimal (owner decisions 2026-09-28; called
    credits since 2026-10-01)."""
    from app.core.config import get_settings

    value = ugx / get_settings().ugx_per_token
    text = f"{value:,.1f}".rstrip("0").rstrip(".")
    return f"{text} credit" if text == "1" else f"{text} credits"


class InsufficientCredits(AppError):
    def __init__(self, needed: int, available: int):
        super().__init__(
            f"You need {tokens(needed)} for this, and your balance is {tokens(available)}. Buy credits to continue.",
            code="INSUFFICIENT_CREDITS",
            status=402,
        )
        self.needed = needed


def _record(w: Wallet, kind: Kind, amount: int, job_id: str | None, note: str) -> Wallet:
    w.entries = (w.entries + [LedgerEntry(id=f"le_{secrets.token_hex(6)}", kind=kind, amount=amount, job_id=job_id, note=note, available_after=w.available, held_after=w.held)])[-MAX_ENTRIES:]
    w.updated_at = utcnow()
    return w


def top_up(w: Wallet, amount: int, note: str) -> Wallet:
    if amount <= 0:
        raise AppError("Enter an amount above zero.", code="INVALID_AMOUNT")
    w.available += amount
    return _record(w, "TOP_UP", amount, None, note)


def grant(w: Wallet, amount: int, note: str, op_id: str, actor: str) -> Wallet:
    """A manual grant, at most once per operation id: every grant's id is kept for good in
    `grant_ops` (the display ledger keeps only recent entries), so replaying an old request adds
    nothing (Codex audit, ledger durability)."""
    if w.closing:
        raise AppError("This account is being deleted, so no credits can be added.", code="ACCOUNT_CLOSING", status=409)
    if op_id in w.grant_ops or any(e.op_id == op_id for e in w.entries):
        return w
    top_up(w, amount, note)
    w.entries[-1].op_id, w.entries[-1].actor = op_id, actor
    w.grant_ops = [*w.grant_ops, op_id]
    return w


def hold(w: Wallet, amount: int, job_id: str, note: str) -> Wallet:
    if amount < 0:
        raise ValueError("negative hold")
    if w.available < amount:
        raise InsufficientCredits(amount, w.available)
    w.available -= amount
    w.held += amount
    return _record(w, "HOLD", amount, job_id, note)


def reserve(w: Wallet, key: str, amount: int, note: str) -> Wallet:
    """Set credits aside for a document before any of its paid work runs (one Start): available to
    held, under `key`. A key reserved again is first returned, so it never holds twice."""
    release_reservation(w, key, "Earlier reservation returned")
    if amount <= 0:
        return w
    if w.available < amount:
        raise InsufficientCredits(amount, w.available)
    w.available -= amount
    w.held += amount
    w.reservations = {**w.reservations, key: amount}
    return _record(w, "HOLD", amount, None, note)


def release_reservation(w: Wallet, key: str, note: str) -> int:
    """Return what `key` reserved to the balance (0 when nothing was)."""
    amount = w.reservations.get(key, 0)
    if not amount:
        return 0
    w.reservations = {k: v for k, v in w.reservations.items() if k != key}
    w.held -= amount
    w.available += amount
    _record(w, "RELEASE", amount, None, note)
    return amount


def settle(w: Wallet, held: int, charge: int, job_id: str, note: str) -> Wallet:
    """Charge part of a hold and release the rest."""
    if not 0 <= charge <= held <= w.held:
        raise ValueError(f"invalid settlement charge={charge} held={held} wallet_held={w.held}")
    w.held -= held
    if charge:
        _record(w, "CHARGE", charge, job_id, note)
    w.available += held - charge
    if held - charge:
        _record(w, "RELEASE", held - charge, job_id, "Unused hold returned to your balance")
    return w


def refund(w: Wallet, amount: int, job_id: str, note: str) -> Wallet:
    if amount <= 0:
        return w
    w.available += amount
    return _record(w, "REFUND", amount, job_id, note)
