"""Backend for the browser test (web/scripts/e2e.mjs) — never for real use.

Runs the real app on :8000 with both AI roles answered by tests.fake_models, dummy keys and its
own data folder (backend/.data_e2e), so browser-test jobs never mix with real ones and no provider
is called. Usage: cd backend && .venv/Scripts/python -m tests.serve_e2e"""

import json
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
            "GEMINI_API_KEY": "gm-e2e",
            "VERTEX_PROJECT": "paperaid",
            "FLOOD_CLIENT_RATE": "100000", "FLOOD_INSTANCE_RATE": "100000", "AI_CHECK_ENABLED": "true",  # the journeys run from one address  # the Gemini workflow, as in production; the stand-in answers every stage
            # Every work service on, with test prices, so the browser journeys can run them.
            "WORKS_ENABLED": '["CONCEPT_NOTE","COURSEWORK","FUNDING_PROPOSAL"]', "WORKS_PUBLIC": "true",
            "DATALAB_ENABLED": "true",
            "MODEL_PRICES": '{"fake:gpt-6-sol":[0,0,0],"fake:gpt-6-luna":[0,0,0],"fake:claude-sonnet-5-5":[0,0,0],"fake:claude-opus-5-5":[0,0,0],"fake:gemini-3.8-flash":[0,0,0],"fake:gemini-3.5-flash-lite":[0,0,0],"fake:gemini-3.1-pro-preview":[0,0,0]}',
            "ADMIN_EMAILS": '["demo@paperaid.app"]',
            "ENV": "local",
            "CREDITS_ENABLED": "true",  # the browser journey covers credits, whatever the local .env says
            "QUOTES_PER_HOUR": "500",  # several journeys run against one server within the hour
            "SUBMITS_PER_HOUR": "500",
        }
    )
    from app.core.config import Settings, get_settings

    # Test prices for the work services, in the browser-test backend only (the product has none until the owner sets them).
    work_tokens = {"WORK_READ": 1, "CN_PLAN": 2, "CN_BRIEF": 3, "CN_STANDARD": 4, "CN_EXTENDED": 6, "CW_PLAN": 2, "CW_1500": 4, "CW_3000": 6, "CW_5000": 8, "CW_8000": 11,
                   "FP_PLAN": 3, "FP_COMPACT": 8, "FP_STANDARD": 12, "FP_COMPREHENSIVE": 18, "WORK_REVISE": 2,
                   "DL_SMALL": 3, "DL_STANDARD": 5, "DL_LARGE": 8, "QL_SMALL": 4, "QL_STANDARD": 7, "QL_LARGE": 12}
    os.environ["FIXED_TOKENS"] = json.dumps({**Settings(_env_file=None).fixed_tokens, **work_tokens})
    get_settings.cache_clear()
    # Even a later accidental bypass of the stand-in must never become a paid Vertex call.
    from anthropic.resources.messages import Messages
    from google.genai.models import Models
    from openai.resources.responses import Responses

    from app.ai import costs, orchestration
    from app.main import create_app
    from tests.fake_models import FakeModels

    def no_vertex_call(*args, **kwargs):
        raise AssertionError("Browser-test backend cannot call Vertex")

    Models.generate_content = no_vertex_call
    Messages.create = no_vertex_call
    Responses.create = no_vertex_call

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
    app = create_app()
    # The journeys' signed-in accounts have accepted the current terms (the sign-up journey accepts them itself).
    import hashlib

    from app.runtime import get_runtime

    rt = get_runtime()
    for email in ("demo@paperaid.app", "someone.else@example.com"):
        uid = "u_" + hashlib.sha256(email.encode()).hexdigest()[:20]
        rt.store.update_wallet(uid, email, lambda w: w.model_copy(update={"terms_version": rt.settings.terms_version}))
    uvicorn.run(app, host="127.0.0.1", port=int(os.environ.get("PAPERAID_E2E_PORT", "8000")))


if __name__ == "__main__":
    main()
