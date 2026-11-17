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
    monkeypatch.setattr(fetch, "crossref_lookup", lambda doi: ("FOUND", state["works"][doi]) if doi in state["works"] else ("NOT_FOUND", None))
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


# --- every referencing style (owner, 2026-11-17, after PaperAid Pro): the title is found in the entry, the first author
# is read before it and the year outside it, whatever the style.

STYLES = {
    "Vancouver": "1. Ojakaa DI, Jarvis JD. Acceptance of a malaria vaccine by caregivers of sick children in Kenya. Malar J. 2014;13(1):172.",
    "IEEE": "[3] D. I. Ojakaa and J. D. Jarvis, \u201cAcceptance of a malaria vaccine by caregivers of sick children in Kenya,\u201d Malaria Journal, vol. 13, no. 1, 2014.",
    "MLA": "Ojakaa, David I., and Jane D. Jarvis. \u201cAcceptance of a Malaria Vaccine by Caregivers of Sick Children in Kenya.\u201d Malaria Journal, vol. 13, no. 1, 2014.",
    "Harvard": "Ojakaa, D.I. and Jarvis, J.D. (2014) \u2018Acceptance of a malaria vaccine by caregivers of sick children in Kenya\u2019, Malaria Journal, 13(1).",
}


@pytest.mark.parametrize("style", STYLES)
def test_a_reference_in_any_style_is_matched(lookups, style):
    lookups["found"] = [RECORD]
    assert references.verify(STYLES[style]).status == "PROBABLE"
    lookups["works"][RECORD["doi"]] = RECORD
    assert references.verify(STYLES[style] + " doi:" + RECORD["doi"]).status == "VERIFIED"


def test_a_wrong_year_or_author_is_found_in_any_style(lookups):
    lookups["found"] = [RECORD]
    wrong_year = references.verify(STYLES["Vancouver"].replace("2014", "2016"))
    assert wrong_year.status == "MISMATCH" and "registered year is 2014, not 2016" in wrong_year.note
    wrong_author = references.verify(STYLES["IEEE"].replace("D. I. Ojakaa and J. D. Jarvis", "J. D. Jarvis"))
    assert wrong_author.status == "MISMATCH" and "registered first author is Ojakaa" in wrong_author.note


def test_a_year_inside_a_title_is_not_the_publication_year(lookups):
    record = {**RECORD, "title": "Uganda Vision 2040 and maternal health services", "year": "2018", "authors": "Okello, P."}
    lookups["found"] = [record]
    check = references.verify("Okello, P. (2018). Uganda Vision 2040 and maternal health services. Kampala: Fountain.")
    assert check.status == "PROBABLE", check.note


def test_the_best_of_several_registered_records_is_chosen(lookups):
    decoy = {**RECORD, "doi": "10.1000/other", "title": "Acceptance of a malaria vaccine by caregivers in Ghana", "authors": "Mensah, K.", "year": "2019"}
    lookups["found"] = [decoy, RECORD]
    check = references.verify(ENTRY)
    assert check.status == "PROBABLE" and check.doi == RECORD["doi"]
