"""Reference verification (master context §36-37): each reference matched against registered
records by DOI or bibliographic search. Unfound is "could not verify", never "fabricated"."""

import pytest

from app.analysis import fetch, references
from tests.test_api import ADMIN, STUDENT, start_job, wait

RECORD = {
    "doi": "10.1186/1475-2875-13-172", "title": "Acceptance of a malaria vaccine by caregivers of sick children in Kenya",
    "authors": "Ojakaa, D. I.; Jarvis, J. D.", "year": "2014", "container": "Malaria Journal", "volume": "13", "issue": "1", "pages": "", "type": "journal-article", "retracted": "",
}
ENTRY = "Ojakaa, D. I., & Jarvis, J. D. (2014). Acceptance of a malaria vaccine by caregivers of sick children in Kenya. Malaria Journal, 13(1)."


@pytest.fixture
def lookups(monkeypatch):
    state = {"works": {}, "found": [], "retracted": set()}
    monkeypatch.setattr(fetch, "crossref_work", lambda doi: state["works"].get(doi))
    monkeypatch.setattr(fetch, "crossref_search", lambda text, rows=3: state["found"])
    monkeypatch.setattr(fetch, "openalex_retracted", lambda doi: doi in state["retracted"])
    return state


def test_a_doi_that_matches_is_verified(lookups):
    lookups["works"][RECORD["doi"]] = RECORD
    check = references.verify(ENTRY + " https://doi.org/10.1186/1475-2875-13-172")
    assert check.status == "VERIFIED" and check.doi == RECORD["doi"] and not check.retracted


def test_a_search_match_is_probable_and_a_wrong_year_is_a_mismatch(lookups):
    lookups["found"] = [RECORD]
    assert references.verify(ENTRY).status == "PROBABLE"
    wrong = references.verify(ENTRY.replace("2014", "2019"))
    assert wrong.status == "MISMATCH" and "registered year is 2014" in wrong.note


def test_an_unknown_reference_is_could_not_verify_never_fabricated(lookups):
    check = references.verify("Namara, P. (2021). District health office annual report. Mukono District Local Government.")
    assert check.status == "NOT_VERIFIED" and "fabricat" not in check.note.lower() and "check it yourself" in check.note


def test_an_unregistered_doi_says_so(lookups):
    check = references.verify(ENTRY + " doi:10.9999/not-a-real-doi")
    assert check.status == "NOT_VERIFIED" and "DOI is not registered" in check.note


def test_retractions_are_flagged(lookups):
    lookups["found"] = [RECORD]
    lookups["retracted"].add(RECORD["doi"])
    check = references.verify(ENTRY)
    assert check.retracted and check.note.startswith("This work has been retracted")
    lookups["retracted"].clear()
    lookups["found"] = [{**RECORD, "retracted": "yes"}]  # a notice registered with Crossref
    assert references.verify(ENTRY).retracted


def test_an_ai_check_verifies_the_reference_list_and_admins_never_see_it(client):
    first = {**RECORD, "doi": "10.1000/j000", "title": "Title of study number 0 on learning outcomes", "authors": "Author0, A. B.; Writer, C.", "year": "2000"}
    client.models.crossref["10.1000/j000"] = first  # the fixture's first reference carries this DOI
    job_id, quote = start_job(client, "references_heavy.docx", {"writing": "AI_CHECK", "formatting": "NONE", "latex": False})
    client.post(f"/api/jobs/{job_id}/submit", headers=STUDENT, json={"quoteId": quote["id"]})
    job = wait(client, job_id, timeout=120)
    verification = job["references"]
    assert verification["checked"] == 45 and verification["total"] == 45
    assert verification["items"][0]["status"] == "VERIFIED"  # DOI registered, title, author and year agree
    assert verification["items"][1]["status"] == "NOT_VERIFIED"  # its DOI is not registered and {i["status"] for i in verification["items"]} <= {"VERIFIED", "PROBABLE", "MISMATCH", "NOT_VERIFIED"}
    admin = client.get(f"/api/admin/jobs/{job_id}", headers=ADMIN).json()
    assert all(i["entry"] == "" for i in admin["job"]["references"]["items"])
