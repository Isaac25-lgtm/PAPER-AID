"""Backend for the browser test (web/scripts/e2e.mjs) — never for real use.

Runs the real app on :8000 with both AI roles answered by tests.fake_models, dummy keys and its
own data folder (backend/.data_e2e), so browser-test jobs never mix with real ones and no provider
is called. Usage: cd backend && .venv/Scripts/python -m tests.serve_e2e"""

import os
import shutil
from pathlib import Path

import uvicorn

DATA = Path(__file__).resolve().parents[1] / ".data_e2e"


def main() -> None:
    shutil.rmtree(DATA, ignore_errors=True)  # every browser-test run starts empty
    os.environ.update(
        {
            "DATA_DIR": str(DATA),
            "OPENAI_API_KEY": "sk-e2e",
            "ANTHROPIC_API_KEY": "sk-e2e",
            "MODEL_PRICES": '{"fake:gpt-6-sol":[0,0,0],"fake:claude-opus-5-5":[0,0,0]}',
            "ADMIN_EMAILS": '["demo@paperaid.app"]',
            "ENV": "local",
        }
    )
    from app.ai import orchestration
    from app.main import create_app
    from tests.fake_models import FakeModels

    models = FakeModels()
    orchestration.provider_for = lambda ref, settings: (models, ref.split(":")[-1])
    uvicorn.run(create_app(), host="127.0.0.1", port=8000)


if __name__ == "__main__":
    main()
