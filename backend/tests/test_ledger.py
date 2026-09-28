"""The credit history is complete: the wallet keeps its recent entries for display, and every entry
is also written as its own record in the same transaction, so nothing is lost past the cap."""

import hashlib

from app.pricing import credits
from app.pricing.credits import MAX_ENTRIES
from tests.test_api import STUDENT, start_job, wait

UID = "u_" + hashlib.sha256(b"student@example.com").hexdigest()[:20]


def test_the_history_keeps_every_entry_beyond_the_wallets_cap(client):
    from app.runtime import get_runtime

    rt = get_runtime()
    for n in range(MAX_ENTRIES + 20):
        rt.store.update_wallet(UID, "student@example.com", lambda w, n=n: credits.top_up(w, 1000, f"test {n}"))
    assert len(rt.store.get_wallet(UID).entries) == MAX_ENTRIES
    seen, before, pages = [], None, 0
    while True:
        page = client.get("/api/wallet/history", headers=STUDENT, params={"before": before} if before else {}).json()
        seen += page["entries"]
        pages += 1
        if not page["next"]:
            break
        before = page["next"]
    notes = [e["note"] for e in seen if e["note"].startswith("test ")]
    assert len(notes) == MAX_ENTRIES + 20 == len(set(notes)) and pages >= 7
    assert notes[0] == f"test {MAX_ENTRIES + 19}" and notes[-1] == "test 0"  # newest first


def test_a_jobs_hold_and_charge_reach_the_history(client):
    job_id, quote = start_job(client, selection={"formatting": "FORMAT", "preset": "apa7"})
    client.post(f"/api/jobs/{job_id}/submit", headers=STUDENT, json={"quoteId": quote["id"]})
    assert wait(client, job_id)["status"] == "COMPLETED"
    kinds = {e["kind"] for e in client.get("/api/wallet/history", headers=STUDENT).json()["entries"] if e["jobId"] == job_id}
    assert {"HOLD", "CHARGE"} <= kinds


def test_deleting_the_account_removes_the_history(client):
    from app.runtime import get_runtime

    rt = get_runtime()
    rt.store.update_wallet(UID, "student@example.com", lambda w: credits.top_up(w, 1000, "before deletion"))
    assert rt.store.ledger(UID, None, 10)
    rt.store.delete_wallet(UID)
    assert rt.store.ledger(UID, None, 10) == []
