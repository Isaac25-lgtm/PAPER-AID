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
    whole = max(1, settings.capacity_limits.get(model, settings.capacity_default))
    return max(1, min(whole, settings.capacity_search)) if searching else whole


def gate(store: JobStore, settings: Settings, owner: str, sleep: Callable[[float], None] = time.sleep) -> Gate:
    """A gate for one job stage: take(model, searching) waits for a slot and returns (release, milliseconds waited),
    or raises CapacityWait when none frees in time or the limiter cannot be reached."""

    def take(model: str, searching: bool) -> tuple[Release, int]:
        # Every call holds a slot of its model: the model's limit covers searches too. A search also holds one of the
        # model's (fewer) search slots (Codex audit through ea0599e, finding 11: the two pools added up).
        wanted = [(resource(settings, model, False), slots_for(settings, model, False))]
        if searching:
            wanted.append((resource(settings, model, True), slots_for(settings, model, True)))
        holder = f"{owner}:{secrets.token_hex(6)}"  # this request's own identity
        started = time.monotonic()
        held: list[tuple[str, int]] = []

        def release() -> None:
            for name, slot in reversed(held):
                try:
                    store.release_slot(name, slot, holder)
                except LimiterUnavailable as exc:  # it frees itself when its time is up
                    log(logger, logging.WARNING, "slot not released", error=str(exc))
            held.clear()

        while True:
            try:
                for name, slots in wanted[len(held):]:
                    slot = store.take_slot(name, slots, holder, CALL_LIMIT_SEC + HOLD_MARGIN_SEC)
                    if slot is None:
                        break
                    held.append((name, slot))
            except LimiterUnavailable as exc:
                release()
                log(logger, logging.WARNING, "limiter unavailable", error=str(exc))
                raise CapacityWait("the limiter could not be reached") from exc
            if len(held) == len(wanted):
                return release, int((time.monotonic() - started) * 1000)
            release()  # never wait holding one of the two: another call could be waiting for it
            if time.monotonic() - started >= settings.capacity_wait_sec:
                raise CapacityWait("every slot is in use")
            sleep(1 + random.random())  # spread the waiters out

    return take
