"""Every Firestore query the service issues must have a composite index in firestore.indexes.json.
A missing one fails only in production (local runs use the file store), so it is checked here."""

import json
from pathlib import Path

import pytest
from google.cloud import firestore

from app.core.config import Settings
from app.integrations.store import FirestoreJobStore
from app.jobs import service
from app.runtime import Runtime

INDEXES = json.loads((Path(__file__).parents[2] / "firestore.indexes.json").read_text(encoding="utf8"))["indexes"]


class _Query:
    """Records the shape of each query that runs: its filtered fields and its sort order."""

    def __init__(self, shapes: list, filters: tuple = (), order: tuple | None = None):
        self._shapes, self._filters, self._order = shapes, filters, order

    def where(self, filter):
        return _Query(self._shapes, self._filters + (filter.field_path,), self._order)

    def order_by(self, field, direction):
        return _Query(self._shapes, self._filters, (field, direction))

    def limit(self, _):
        return self

    def start_after(self, _):
        return self

    def select(self, _):
        return self

    def stream(self):
        self._shapes.append((frozenset(self._filters), self._order))
        return iter([])


class _Store(FirestoreJobStore):
    def __init__(self, shapes: list):  # no client: only the query builder is exercised
        self._fs = firestore
        self._jobs = _Query(shapes)

    def delete_wallet(self, uid: str) -> None:
        pass

    def get_flag(self, name: str, default: bool) -> bool:
        return default

    def update_wallet(self, uid, email, mutate):
        from app.jobs.models import Wallet

        return mutate(Wallet(uid=uid, email=email))


def _indexed(filters: frozenset, order: tuple) -> bool:
    field, direction = order
    want = "DESCENDING" if direction == firestore.Query.DESCENDING else "ASCENDING"
    for index in INDEXES:
        *equalities, last = index["fields"]
        if {f["fieldPath"] for f in equalities} == filters and last["fieldPath"] == field and last.get("order") == want:
            return True
    return False


@pytest.fixture
def shapes():
    recorded: list = []
    rt = Runtime(Settings(_env_file=None), _Store(recorded), files=None)  # type: ignore[arg-type]
    user = service.User(uid="u1", email="a@b.co", is_admin=False)
    service.delete_account(rt, user)
    for status in (None, "COMPLETED", "DRAFT"):
        for svc in (None, "REFINE"):
            service.list_jobs(rt, user, status, svc, None, 20)
            service.admin_list(rt, status, svc, None, None, 20)
    service.admin_list(rt, None, None, "someone@example.com", None, 20)
    service.admin_summary(rt)
    service.reconcile(rt)
    service.cleanup_expired(rt)
    return recorded


def test_every_sorted_job_query_has_an_index(shapes):
    sorted_queries = {(f, o) for f, o in shapes if o is not None and f}  # sort alone uses the built-in index
    assert sorted_queries, "no queries were recorded"
    missing = [(sorted(f), o[0]) for f, o in sorted_queries if not _indexed(f, o)]
    assert missing == []


def test_account_deletion_query_is_covered(shapes):
    assert (frozenset({"ownerUid"}), ("createdAt", firestore.Query.DESCENDING)) in shapes
