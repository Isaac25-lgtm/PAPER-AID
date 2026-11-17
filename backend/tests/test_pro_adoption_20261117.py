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


def test_codex_cases_small_counts_currency_and_an_unrelated_bare_number():
    """Codex audit 2026-11-17, P1: each of these passed before."""
    days = _library("Mothers waited 12 days for a referral.")
    assert evidence.figure_problems("They waited 12 months ⟦E000001⟧.", days, "", units=True)  # 12 is a small count only when bare
    money = _library("A visit cost UGX 12 in 1990.")
    assert evidence.figure_problems("A visit cost USD 12 ⟦E000001⟧.", money, "", units=True)
    versioned = _library("Mothers waited 14 days. Version 14 of the guideline applies.")
    assert evidence.figure_problems("They waited 14 months ⟦E000001⟧.", versioned, "", units=True)  # a bare 14 elsewhere never overrides
    per_cent = _library("Uptake rose to 12 per cent in the district.")
    assert evidence.figure_problems("Uptake rose to 12% ⟦E000001⟧.", per_cent, "", units=True) == []
    assert evidence.figure_problems("Uptake rose to 12 percent ⟦E000001⟧.", _library("Uptake rose to 12%."), "", units=True) == []
    assert evidence.figure_problems("The study ran for 3 years ⟦E000001⟧.", days, "", units=True)  # an unsourced duration
    assert evidence.figure_problems("Three of the 5 districts took part ⟦E000001⟧.", days, "", units=True) == []  # a bare small count
    assert evidence.figure_problems("They waited 12 months ⟦E000001⟧.", days, "") == []  # steps priced before keep their check


def test_the_exported_text_is_withheld_on_its_units_too():
    days = _library("Mothers waited 12 days for a referral.")
    paragraph = "Referral is slow. They waited 12 months ⟦E000001⟧."
    assert evidence.strip_unsupported(paragraph, days, {"E000001"}, "") == paragraph  # older steps unchanged
    assert evidence.strip_unsupported(paragraph, days, {"E000001"}, "", units=True) == "Referral is slow."


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


def test_the_appearance_is_kept_with_the_account_apart_from_the_wallet(client):
    from app.runtime import get_runtime

    first = client.get("/api/me/preferences", headers=STUDENT).json()
    assert first["appearance"] is None and first["termsAccepted"] is True and first["termsVersion"]
    assert client.post("/api/me/preferences", headers=STUDENT, json={"appearance": "dark"}).json() == {"appearance": "dark"}
    assert client.get("/api/me/preferences", headers=STUDENT).json()["appearance"] == "dark"
    assert client.post("/api/me/preferences", headers=STUDENT, json={"appearance": "purple"}).status_code == 422
    # an older release rewriting the whole wallet (a rollout or a rollback) never drops it: it is not in the wallet
    rt = get_runtime()
    uid = client.get("/api/me", headers=STUDENT).json()["uid"]
    rt.store.update_wallet(uid, "student@example.com", lambda w: w.model_copy())
    assert client.get("/api/me/preferences", headers=STUDENT).json()["appearance"] == "dark"


def _finish(client, selection=None):
    from tests.test_api import start_job, wait

    job_id, quote = start_job(client, selection=selection or FORMAT_ONLY)
    client.post(f"/api/jobs/{job_id}/submit", headers=STUDENT, json={"quoteId": quote["id"]})
    assert wait(client, job_id)["status"] == "COMPLETED"
    return job_id


def test_finished_work_is_in_the_inbox_until_it_is_read(client):
    assert client.get("/api/me/inbox", headers=STUDENT).json() == {"items": [], "unread": 0}
    job_id = _finish(client)
    inbox = client.get("/api/me/inbox", headers=STUDENT).json()
    assert inbox["unread"] == 1
    item = inbox["items"][0]
    assert item["outcome"] == "READY" and item["title"] == "Your paper is ready" and item["to"] == f"/app/jobs/{job_id}"
    assert client.post("/api/me/inbox/read", headers=STUDENT, json={"through": item["at"]}).status_code == 204
    after = client.get("/api/me/inbox", headers=STUDENT).json()
    assert after["unread"] == 0 and len(after["items"]) == 1
    other = client.get("/api/me/inbox", headers={"Authorization": "Dev someone@example.com"}).json()
    assert other == {"items": [], "unread": 0}  # never another person's work


def test_codex_the_inbox_reads_notices_newest_first_and_marks_read_only_what_was_shown(client):
    """Codex audit 2026-11-17: an older job that finished last was left out; opening the bell marked unseen notices read."""
    from datetime import timedelta

    from app.jobs.models import utcnow
    from app.runtime import get_runtime

    rt = get_runtime()
    older, newer = _finish(client), _finish(client)
    later = utcnow() + timedelta(seconds=5)
    rt.store.update(older, lambda j: j.model_copy(update={"notice": j.notice.model_copy(update={"at": later})}))  # created first, finished last
    shown = client.get("/api/me/inbox", headers=STUDENT).json()["items"]
    assert [i["id"] for i in shown] == [older, newer]
    # the bell shows only the newer notice, then the older one arrives: reading through the newer leaves the older unread
    first_at = next(i["at"] for i in shown if i["id"] == newer)
    client.post("/api/me/inbox/read", headers=STUDENT, json={"through": first_at})
    unread = {i["id"]: i["unread"] for i in client.get("/api/me/inbox", headers=STUDENT).json()["items"]}
    assert unread == {older: True, newer: False}


def test_an_account_on_older_terms_is_asked_before_using_the_app(client):
    from app.runtime import get_runtime

    rt = get_runtime()
    new = {"Authorization": "Dev new@example.com"}
    uid = client.get("/api/me", headers=new).json()["uid"]
    rt.store.update_wallet(uid, "new@example.com", lambda w: w.model_copy(update={"terms_version": "2026-10-07"}))
    assert client.get("/api/me/preferences", headers=new).json()["termsAccepted"] is False
    assert client.post("/api/me/terms", headers=new, json={"version": rt.settings.terms_version}).status_code == 204
    assert client.get("/api/me/preferences", headers=new).json()["termsAccepted"] is True


def test_a_security_policy_report_is_logged_with_its_rule_and_host_only(client, caplog):
    """Codex audit 2026-11-17: the report-only policy needs somewhere to report, so it can be enforced on evidence."""
    import logging

    caplog.set_level(logging.WARNING, logger="paperaid.csp")
    report = {"csp-report": {"effective-directive": "script-src-elem", "blocked-uri": "https://evil.example/x.js?token=secret"}}
    assert client.post("/api/csp-report", json=report).status_code == 204  # no sign-in: browsers send it without one
    assert client.post("/api/csp-report", content=b"not json").status_code == 204
    logged = " ".join(f"{r.getMessage()} {r.__dict__}" for r in caplog.records)
    assert "script-src-elem" in logged and "evil.example" in logged and "secret" not in logged
