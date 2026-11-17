"""What PaperAid adopted from PaperAid Pro (owner, 2026-11-17): figures keep their units, for steps priced from then."""

from app.proposals import evidence
from app.proposals.models import EvidenceItem, EvidenceSource


def _library(passage: str) -> dict[str, EvidenceItem]:
    source = EvidenceSource(url="https://example.org/a", title="District health report", year="2024")
    return {"E000001": EvidenceItem(id="E000001", chapter=1, need="n", statement="s", passage=passage, scope="", access="ABSTRACT",
                                    verified=True, support="SUPPORTED", source=source, retrieved_on="2026-11-17")}


def test_a_figure_in_another_unit_than_its_source_is_a_finding_for_new_steps():
    library = _library("Mothers waited 14 days on average for a referral.")
    paragraph = "Mothers waited 14 months for a referral ⟦E000001⟧."
    assert evidence.figure_problems(paragraph, library, "") == []  # steps priced before keep their check
    found = evidence.figure_problems(paragraph, library, "", units=True)
    assert found and "14 months" in found[0] and "14 days" in found[0]


def test_the_same_unit_a_bare_source_number_and_currency_spellings_pass():
    days = _library("Mothers waited 14 days on average for a referral.")
    assert evidence.figure_problems("They waited 14 days ⟦E000001⟧.", days, "", units=True) == []
    bare = _library("The average wait was 14 in the district's records.")
    assert evidence.figure_problems("They waited 14 days ⟦E000001⟧.", bare, "", units=True) == []  # the source gives no unit to contradict
    money = _library("Each visit cost UGX 25,000 in transport.")
    assert evidence.figure_problems("A visit cost USh 25,000 ⟦E000001⟧.", money, "", units=True) == []


def test_a_different_currency_is_a_finding():
    money = _library("Each visit cost UGX 25,000 in transport.")
    found = evidence.figure_problems("A visit cost USD 25,000 ⟦E000001⟧.", money, "", units=True)
    assert found and "usd" in found[0]


def test_new_steps_are_priced_with_the_unit_check():
    from app.proposals.models import StepInput
    from app.works.models import WorkStepInput

    assert 4 in StepInput.model_fields["academic_policy"].annotation.__args__
    assert 3 in WorkStepInput.model_fields["academic_policy"].annotation.__args__
    for path, value in (("app/proposals/service.py", "academic_policy=4"), ("app/works/service.py", "academic_policy=3")):
        assert value in open(path, encoding="utf-8").read()


# --- night mode kept with the account, and in-app notifications ------------------------------------------------------

STUDENT = {"Authorization": "Dev student@example.com"}
FORMAT_ONLY = {"writing": "NONE", "formatting": "FORMAT", "preset": "apa7", "latex": False}


def test_the_appearance_is_kept_with_the_account(client):
    assert client.get("/api/me/preferences", headers=STUDENT).json() == {"appearance": None, "termsAccepted": True}  # test accounts accepted
    assert client.put("/api/me/preferences", headers=STUDENT, json={"appearance": "dark"}).json() == {"appearance": "dark"}
    assert client.get("/api/me/preferences", headers=STUDENT).json()["appearance"] == "dark"
    assert client.put("/api/me/preferences", headers=STUDENT, json={"appearance": "purple"}).status_code == 422


def test_finished_work_is_in_the_inbox_until_it_is_read(client):
    from tests.test_api import start_job, wait

    assert client.get("/api/me/inbox", headers=STUDENT).json() == {"items": [], "unread": 0}
    job_id, quote = start_job(client, selection=FORMAT_ONLY)
    client.post(f"/api/jobs/{job_id}/submit", headers=STUDENT, json={"quoteId": quote["id"]})
    assert wait(client, job_id)["status"] == "COMPLETED"
    inbox = client.get("/api/me/inbox", headers=STUDENT).json()
    assert inbox["unread"] == 1
    item = inbox["items"][0]
    assert item["outcome"] == "READY" and item["title"] == "Your paper is ready" and item["to"] == f"/api/jobs/{job_id}".replace("/api", "/app")
    assert client.post("/api/me/inbox/read", headers=STUDENT).status_code == 204
    after = client.get("/api/me/inbox", headers=STUDENT).json()
    assert after["unread"] == 0 and len(after["items"]) == 1
    other = client.get("/api/me/inbox", headers={"Authorization": "Dev someone@example.com"}).json()
    assert other == {"items": [], "unread": 0}  # never another person's work


def test_an_account_on_older_terms_is_asked_before_using_the_app(client):
    from app.runtime import get_runtime

    rt = get_runtime()
    new = {"Authorization": "Dev new@example.com"}
    uid = client.get("/api/me", headers=new).json()["uid"]
    rt.store.update_wallet(uid, "new@example.com", lambda w: w.model_copy(update={"terms_version": "2026-10-07"}))
    assert client.get("/api/me/preferences", headers=new).json()["termsAccepted"] is False
    assert client.post("/api/me/terms", headers=new, json={"version": rt.settings.terms_version}).status_code == 204
    assert client.get("/api/me/preferences", headers=new).json()["termsAccepted"] is True
