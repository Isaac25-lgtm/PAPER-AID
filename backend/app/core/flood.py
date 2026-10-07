"""A flood guard in front of the public API (owner, 2026-10-07: "an attack can hit my database a thousand
times per second"). It refuses excess requests before any sign-in check or database read.

Two token buckets per API instance: one per client address and one for the instance as a whole, so
an attacker who fakes addresses still cannot push more than the instance's ceiling through. Sign-in,
App Check and the per-student hourly limits on paid actions (`_rate_limit`) still apply behind it.
"""

import threading
import time
from dataclasses import dataclass, field


@dataclass
class Bucket:
    rate: float  # tokens added per second
    burst: float  # the most a bucket holds
    tokens: float = field(default=0.0)
    updated: float = field(default_factory=time.monotonic)

    def take(self, now: float) -> bool:
        self.tokens = min(self.burst, self.tokens + (now - self.updated) * self.rate)
        self.updated = now
        if self.tokens < 1:
            return False
        self.tokens -= 1
        return True


class FloodGuard:
    def __init__(self, per_client_rate: float, per_client_burst: float, instance_rate: float, instance_burst: float, max_clients: int = 20_000):
        self._per_client = (per_client_rate, per_client_burst)
        self._instance = Bucket(instance_rate, instance_burst, tokens=instance_burst)
        self._clients: dict[str, Bucket] = {}
        self._max_clients = max_clients
        self._lock = threading.Lock()

    def allow(self, client: str) -> bool:
        now = time.monotonic()
        with self._lock:
            bucket = self._clients.get(client)
            if bucket is None:
                if len(self._clients) >= self._max_clients:  # forget the quietest half rather than grow without bound
                    for key in sorted(self._clients, key=lambda k: self._clients[k].updated)[: self._max_clients // 2]:
                        del self._clients[key]
                bucket = self._clients[client] = Bucket(*self._per_client, tokens=self._per_client[1])
            return bucket.take(now) and self._instance.take(now)


def client_address(forwarded_for: str | None, peer: str | None) -> str:
    """The original client as Firebase Hosting forwards it: the left-most X-Forwarded-For entry. A client can
    fake that entry to dodge its own bucket, but not the instance's ceiling, which every request meets."""
    hops = [h.strip() for h in (forwarded_for or "").split(",") if h.strip()]
    return hops[0] if hops else (peer or "unknown")
