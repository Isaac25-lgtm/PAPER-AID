"""Fixed prices by page band (owner decision 2026-09-28): the price is known before anything runs,
no refinement estimate is needed, the job's AI spend is capped at the worst case (never at the
price), and a partial result is charged only for what was delivered."""

from app.core.config import Settings
from app.jobs.models import ServiceSelection
from app.pricing.quote import band_factor, price
from tests.test_api import STUDENT, wait

REFINE = {"writing": "REFINE", "intensity": "STANDARD", "formatting": "NONE", "latex": False}


def _settings() -> Settings:
    return Settings(_env_file=None, pricing_mode="fixed")


def test_prices_come_from_the_table_by_page_band():
    s = _settings()
    assert band_factor(s, 2500) == 1 and band_factor(s, 2600) == 1.75 and band_factor(s, 10_000) == 3.25
    lines = price(s, ServiceSelection(writing="AI_CHECK"), 2500).lines
    assert [(line.service, line.amount) for line in lines] == [("AI_CHECK", 2000), ("ACADEMIC", 1000)]
    refine = price(s, ServiceSelection(writing="REFINE"), 5000).lines
    assert refine[0].service == "REFINE" and refine[0].amount == 7000  # 4 tokens × 1.75 for 11-20 pages
    chapter = price(s, ServiceSelection(proposal="CHAPTER_2"), 2000).lines
    assert chapter[0].amount == 7000  # proposal steps are not banded


def test_the_spend_cap_is_the_worst_case_never_the_price():
    s = _settings()
    priced = price(s, ServiceSelection(writing="REFINE"), 2500)
    assert priced.budget_usd > (priced.ai_ugx / s.ugx_per_usd / s.price_multiplier)  # quality is never cut to fit the price


def test_refinement_is_priced_at_once_and_charged_the_fixed_price(fixed_client):
    job_id = fixed_client.post("/api/jobs", headers=STUDENT).json()["id"]
    from tests.conftest import fixture_bytes

    fixed_client.post(f"/api/jobs/{job_id}/files/source", headers=STUDENT, files={"file": ("essay.docx", fixture_bytes("simple_essay.docx"), "application/octet-stream")})
    response = fixed_client.post(f"/api/jobs/{job_id}/quote", headers=STUDENT, json={"selection": REFINE}).json()
    quote = response["quote"]
    assert quote is not None and response["estimate"] is None  # no estimate step
    assert quote["pricingVersion"] == "fixed-v1" and quote["amount"] == 5000  # 4 + 1 tokens
    fixed_client.post(f"/api/jobs/{job_id}/submit", headers=STUDENT, json={"quoteId": quote["id"]})
    job = wait(fixed_client, job_id, timeout=120)
    assert job["status"] == "COMPLETED"
    r = job["refinement"]
    expected_refine = 4000 if job["outcome"] == "FULL" else -(-4000 * max(0.25, r["refinedBlocks"] / r["targetedBlocks"]) // 100) * 100
    assert job["billing"]["charged"] == expected_refine + 1000


def test_deep_redraft_previews_free(fixed_client):
    from tests.conftest import fixture_bytes

    job_id = fixed_client.post("/api/jobs", headers=STUDENT).json()["id"]
    fixed_client.post(f"/api/jobs/{job_id}/files/source", headers=STUDENT, files={"file": ("essay.docx", fixture_bytes("simple_essay.docx"), "application/octet-stream")})
    selection = {**REFINE, "writing": "REDRAFT"}
    first = fixed_client.post(f"/api/jobs/{job_id}/quote", headers=STUDENT, json={"selection": selection}).json()
    assert first["estimateFeeCap"] == 0
    wallet_before = fixed_client.get("/api/wallet", headers=STUDENT).json()["available"]
    fixed_client.post(f"/api/jobs/{job_id}/quote", headers=STUDENT, json={"selection": selection, "startEstimate": True})
    for _ in range(300):
        job = fixed_client.get(f"/api/jobs/{job_id}", headers=STUDENT).json()
        if job["estimate"]["status"] != "RUNNING":
            break
        import time

        time.sleep(0.2)
    assert job["estimate"]["status"] == "READY" and job["estimate"]["intervention"] is not None
    assert job["quote"]["lines"][0]["service"] == "REDRAFT" and job["quote"]["lines"][0]["amount"] == 7000
    assert fixed_client.get("/api/wallet", headers=STUDENT).json()["available"] == wallet_before  # the preview cost nothing


def test_fix_selected_is_priced_by_the_chosen_passages(fixed_client):
    from tests.test_workspace import AI_CHECK, _run

    check = _run(fixed_client, AI_CHECK, name="dissertation_long.docx")
    finding = next(f for f in check["analysis"]["findings"] + check["analysis"]["review"] if f["safe"])
    draft = fixed_client.post(f"/api/jobs/{check['id']}/fix", headers=STUDENT, json={"findingIds": [finding["id"]]}).json()
    quote = fixed_client.post(f"/api/jobs/{draft['id']}/quote", headers=STUDENT, json={"selection": draft["selection"]}).json()["quote"]
    assert [line["service"] for line in quote["lines"]] == ["REFINE"]  # the check's review is reused, not paid again
    assert quote["amount"] == 4000  # one passage: the first band, however long the paper
