"""The flood guard in front of the public API (owner, 2026-10-07): excess requests are refused before any
sign-in check or database read, per client address and per instance."""

import time

from app.core.flood import FloodGuard, client_address


def test_a_client_gets_its_burst_then_its_rate_and_others_are_unaffected():
    guard = FloodGuard(per_client_rate=5, per_client_burst=10, instance_rate=1000, instance_burst=1000)
    assert sum(guard.allow("1.1.1.1") for _ in range(30)) == 10  # the burst, then refused
    assert guard.allow("2.2.2.2")  # someone else is not affected
    time.sleep(0.45)
    assert guard.allow("1.1.1.1")  # it refills at its rate


def test_a_clock_read_a_tick_early_never_empties_a_bucket():
    """The release check 2026-10-07: a new client's bucket was stamped after `now` was read, and at a
    high rate the negative interval took every token, refusing a first request."""
    from app.core.flood import Bucket

    bucket = Bucket(rate=100_000, burst=40, tokens=40, updated=10.016)
    assert bucket.take(10.0) and bucket.tokens == 39 and bucket.updated == 10.016
    guard = FloodGuard(per_client_rate=100_000, per_client_burst=40, instance_rate=100_000, instance_burst=300)
    assert all(guard.allow(f"203.0.113.{i}") for i in range(200))


def test_faked_addresses_still_meet_the_instance_ceiling():
    guard = FloodGuard(per_client_rate=100, per_client_burst=100, instance_rate=1, instance_burst=50)
    allowed = sum(guard.allow(f"10.0.{i // 250}.{i % 250}") for i in range(1000))
    assert allowed == 50


def test_the_original_client_is_the_left_most_forwarded_address():
    assert client_address("203.0.113.9, 130.211.0.1", "169.254.1.1") == "203.0.113.9"
    assert client_address(None, "198.51.100.7") == "198.51.100.7"
    assert client_address("", None) == "unknown"


def test_the_api_refuses_a_flood_before_doing_any_work(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("FLOOD_CLIENT_RATE", "1")
    monkeypatch.setenv("FLOOD_CLIENT_BURST", "5")
    from fastapi.testclient import TestClient

    from app.core.config import get_settings
    from app.main import create_app
    from app.runtime import get_runtime

    get_settings.cache_clear()
    get_runtime.cache_clear()
    try:
        with TestClient(create_app()) as client:
            codes = [client.get("/api/config", headers={"X-Forwarded-For": "203.0.113.9"}).status_code for _ in range(20)]
            assert codes[:5] == [200] * 5 and codes.count(429) == 15
            refused = client.get("/api/config", headers={"X-Forwarded-For": "203.0.113.9"})
            assert refused.json()["code"] == "RATE_LIMITED" and refused.headers["Retry-After"] == "2"
            assert client.get("/api/config", headers={"X-Forwarded-For": "198.51.100.7"}).status_code == 200
    finally:
        get_settings.cache_clear()
        get_runtime.cache_clear()
