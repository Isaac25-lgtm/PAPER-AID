"""The shared limit on Gemini calls (speed plan of 2026-10-08, Codex-reviewed).

Every Gemini call a job stage makes holds one slot of its resource (Vertex project, location and model, a web-search
call counting as a resource of its own) for as long as it runs, so all workers together never send more calls at
once than the limit. A call waits briefly for a free slot; if none frees, the stage pauses (CapacityWait) and is
delivered again a little later with everything it has done kept. If the limiter cannot be reached, calls do not go
ahead: the stage pauses the same way. A slot is released only by the request that took it; one whose holder
vanished frees itself when its time is up."""

import logging
import random
import secrets
import time
from collections.abc import Callable

from app.core.config import Settings
from app.core.errors import CapacityWait, LimiterUnavailable
from app.core.logging import log
from app.integrations.store import JobStore

logger = logging.getLogger("paperaid.capacity")

HOLD_MARGIN_SEC = 60  # a slot outlives its call's longest time limit by this much before another may take it
CALL_LIMIT_SEC = 290  # the longest a single Gemini call may run (app.ai.vertex.CALL_SECONDS_CAP)

Release = Callable[[], None]
Gate = Callable[[str, bool], tuple[Release, int]]


def resource(settings: Settings, model: str, searching: bool) -> str:
    return f"{settings.vertex_project}:{settings.vertex_location}:{model}{':search' if searching else ''}"


def slots_for(settings: Settings, model: str, searching: bool) -> int:
    return max(1, settings.capacity_search if searching else settings.capacity_limits.get(model, settings.capacity_default))


def gate(store: JobStore, settings: Settings, owner: str, sleep: Callable[[float], None] = time.sleep) -> Gate:
    """A gate for one job stage: take(model, searching) waits for a slot and returns (release, milliseconds waited),
    or raises CapacityWait when none frees in time or the limiter cannot be reached."""

    def take(model: str, searching: bool) -> tuple[Release, int]:
        name, slots = resource(settings, model, searching), slots_for(settings, model, searching)
        holder = f"{owner}:{secrets.token_hex(6)}"  # this request's own identity
        started = time.monotonic()
        while True:
            try:
                slot = store.take_slot(name, slots, holder, CALL_LIMIT_SEC + HOLD_MARGIN_SEC)
            except LimiterUnavailable as exc:
                log(logger, logging.WARNING, "limiter unavailable", error=str(exc))
                raise CapacityWait("the limiter could not be reached") from exc
            if slot is not None:
                waited = int((time.monotonic() - started) * 1000)

                def release(slot: int = slot) -> None:
                    try:
                        store.release_slot(name, slot, holder)
                    except LimiterUnavailable as exc:  # it frees itself when its time is up
                        log(logger, logging.WARNING, "slot not released", error=str(exc))

                return release, waited
            if time.monotonic() - started >= settings.capacity_wait_sec:
                raise CapacityWait("every slot is in use")
            sleep(1 + random.random())  # spread the waiters out

    return take
