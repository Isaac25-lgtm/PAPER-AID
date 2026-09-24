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


class InsufficientCredits(AppError):
    def __init__(self, needed: int, available: int):
        super().__init__(
            f"You need UGX {needed:,} of credit for this, and your balance is UGX {available:,}. Top up to continue.",
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


def hold(w: Wallet, amount: int, job_id: str, note: str) -> Wallet:
    if amount < 0:
        raise ValueError("negative hold")
    if w.available < amount:
        raise InsufficientCredits(amount, w.available)
    w.available -= amount
    w.held += amount
    return _record(w, "HOLD", amount, job_id, note)


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
