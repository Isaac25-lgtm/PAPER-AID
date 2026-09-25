import json
import subprocess
import sys
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures" / "generated"


def pytest_sessionstart(session: pytest.Session) -> None:
    """Generate the test documents before collection: several test modules parametrize over the
    manifest at import time, and a fresh checkout (CI) does not have them yet."""
    if not (FIXTURES / "manifest.json").exists():
        subprocess.run([sys.executable, str(FIXTURES.parent / "generate.py")], check=True, capture_output=True)


def fixture_bytes(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


def manifest() -> list[dict]:
    return json.loads((FIXTURES / "manifest.json").read_text())


@pytest.fixture
def client(tmp_path, monkeypatch):
    """A fresh app on an isolated data directory with the local queue. Both AI roles are answered
    by tests.fake_models (dummy keys, no network); `client.models` lets a test script any step."""
    from app.ai import orchestration
    from tests.fake_models import FakeModels

    models = FakeModels()
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.setenv("MODEL_PRICES", '{"fake:gpt-6-sol":[0,0,0],"fake:claude-opus-5-5":[0,0,0]}')
    monkeypatch.setenv("ADMIN_EMAILS", '["demo@paperaid.app"]')
    monkeypatch.setattr(orchestration, "provider_for", lambda ref, settings: (models, ref.split(":")[-1]))
    for c in _app_client(tmp_path, monkeypatch):
        c.models = models
        for email in TEST_ACCOUNTS:
            grant(email, 1_000_000)
        yield c


TEST_ACCOUNTS = ("student@example.com", "other@example.com", "demo@paperaid.app")


def grant(email: str, amount: int) -> None:
    """Test credits straight into a wallet (the admin endpoint is tested separately)."""
    import hashlib

    from app.pricing import credits
    from app.runtime import get_runtime

    uid = "u_" + hashlib.sha256(email.encode()).hexdigest()[:20]
    get_runtime().store.update_wallet(uid, email, lambda w: credits.top_up(w, amount, "Test credits"))


def _app_client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("CREDITS_ENABLED", "true")  # tests never inherit the owner's local testing mode
    monkeypatch.setenv("QUOTES_PER_HOUR", "500")
    monkeypatch.setenv("SUBMITS_PER_HOUR", "500")
    from app.core.config import get_settings
    from app.runtime import get_runtime

    get_settings.cache_clear()
    get_runtime.cache_clear()
    from fastapi.testclient import TestClient

    from app.main import create_app

    with TestClient(create_app()) as c:
        yield c
    get_settings.cache_clear()
    get_runtime.cache_clear()


@pytest.fixture
def real_client(client):
    """Kept for readability in tests about the model steps: every client runs the full algorithm."""
    return client
