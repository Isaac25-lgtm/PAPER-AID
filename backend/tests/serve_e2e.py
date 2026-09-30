"""Backend for the browser test (web/scripts/e2e.mjs) — never for real use.

Runs the real app on :8000 with both AI roles answered by tests.fake_models, dummy keys and its
own data folder (backend/.data_e2e), so browser-test jobs never mix with real ones and no provider
is called. Usage: cd backend && .venv/Scripts/python -m tests.serve_e2e"""

import os
import shutil
import tempfile
from pathlib import Path

import uvicorn

DEFAULT_DATA = (Path(__file__).resolve().parents[1] / ".data_e2e").resolve()
DATA = Path(os.environ.get("PAPERAID_E2E_DATA_DIR", str(DEFAULT_DATA))).resolve()


def main() -> None:
    if DATA != DEFAULT_DATA and not (DATA.is_relative_to(Path(tempfile.gettempdir()).resolve()) and DATA.name == ".data_e2e"):
        raise ValueError("Browser-test data must be the default directory or a .data_e2e directory under the system temporary directory")
    shutil.rmtree(DATA, ignore_errors=True)  # every browser-test run starts empty
    os.environ.update(
        {
            "DATA_DIR": str(DATA),
            "OPENAI_API_KEY": "sk-e2e",
            "ANTHROPIC_API_KEY": "sk-e2e",
            "MODEL_PRICES": '{"fake:gpt-6-sol":[0,0,0],"fake:gpt-6-luna":[0,0,0],"fake:claude-sonnet-5-5":[0,0,0],"fake:claude-opus-5-5":[0,0,0]}',
            "ADMIN_EMAILS": '["demo@paperaid.app"]',
            "ENV": "local",
            "CREDITS_ENABLED": "true",  # the browser journey covers credits, whatever the local .env says
            "QUOTES_PER_HOUR": "500",  # several journeys run against one server within the hour
            "SUBMITS_PER_HOUR": "500",
        }
    )
    from app.ai import costs, orchestration
    from app.main import create_app
    from tests.fake_models import FakeModels

    models = FakeModels()
    orchestration.provider_for = lambda ref, settings: (models, ref.split(":")[-1])
    costs.SEARCH_FEE_USD["fake"] = 0.01
    from app.analysis import fetch

    fetch.page_text = lambda url: fetch._text(models.pages[url].encode(), "text/html") if url in models.pages else None
    fetch.abstract_text = lambda url: models.abstracts.get(url)
    fetch.openalex_search = lambda query, from_year, limit: [dict(w) for w in models.works][:limit]
    fetch.crossref_work = lambda doi: models.crossref.get(doi)
    fetch.crossref_lookup = lambda doi: ("FOUND", models.crossref[doi]) if doi in models.crossref else ("NOT_FOUND", None)
    fetch.crossref_search = lambda text, rows=3: [dict(r) for r in models.crossref_found]
    fetch.openalex_retracted = lambda doi: doi in models.retracted
    fetch.resolve_doi = lambda url: models.dois.get(url, fetch.doi_in(url))
    uvicorn.run(create_app(), host="127.0.0.1", port=int(os.environ.get("PAPERAID_E2E_PORT", "8000")))


if __name__ == "__main__":
    main()
