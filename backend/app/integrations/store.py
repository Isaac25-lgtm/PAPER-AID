"""Job and wallet storage. `LocalJobStore` (JSON files) runs everything on one machine;
`FirestoreJobStore` is the production implementation. Both give the same guarantees the job
engine relies on: atomic read-modify-write per job, a job and its owner's wallet changed in one
transaction (so credits can never be held twice or lost between them), and owner-scoped listing."""

from __future__ import annotations  # the stores define a `list` method, which shadows the builtin in annotations

import json
import threading
import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Protocol

from app.jobs.models import Job, JobStatus, Wallet

Mutator = Callable[[Job], Job | None]
WalletMutator = Callable[[Wallet], Wallet | None]
PairMutator = Callable[[Job, Wallet], tuple[Job, Wallet] | None]


class JobStore(Protocol):
    def create(self, job: Job) -> None: ...
    def get(self, job_id: str) -> Job | None: ...
    def update(self, job_id: str, mutate: Mutator) -> Job | None: ...
    def delete(self, job_id: str) -> None: ...
    def list(
        self, owner_uid: str | None, statuses: set[JobStatus] | None, service: str | None, cursor: str | None, limit: int
    ) -> tuple[list[Job], str | None]: ...
    def count_active(self, owner_uid: str) -> int: ...
    def hit(self, key: str, window_sec: int) -> int: ...
    def get_flag(self, name: str, default: bool) -> bool: ...
    def set_flag(self, name: str, value: bool) -> None: ...
    def get_wallet(self, uid: str) -> Wallet | None: ...
    def update_wallet(self, uid: str, email: str, mutate: WalletMutator) -> Wallet | None: ...
    def update_job_and_wallet(self, job_id: str, mutate: PairMutator) -> tuple[Job, Wallet] | None: ...
    def find_wallets(self, email_contains: str | None, limit: int) -> list[Wallet]: ...
    def delete_wallet(self, uid: str) -> None: ...


def _dump(job: Job) -> str:
    return job.model_dump_json(by_alias=True)


class LocalJobStore:
    def __init__(self, root: Path):
        self._dir = root / "jobs"
        self._dir.mkdir(parents=True, exist_ok=True)
        self._flags_path = root / "flags.json"
        self._wallets = root / "wallets"
        self._wallets.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._hits: dict[str, list[float]] = {}

    def _path(self, job_id: str) -> Path:
        if not job_id.replace("_", "").isalnum():
            raise ValueError("invalid job id")
        return self._dir / f"{job_id}.json"

    def _write(self, job: Job) -> None:
        self._dir.mkdir(parents=True, exist_ok=True)  # survives someone deleting .data while running
        tmp = self._path(job.id).with_suffix(".tmp")
        tmp.write_text(_dump(job), encoding="utf-8")
        tmp.replace(self._path(job.id))

    def create(self, job: Job) -> None:
        with self._lock:
            self._write(job)

    def get(self, job_id: str) -> Job | None:
        path = self._path(job_id)
        with self._lock:
            return Job.model_validate_json(path.read_text(encoding="utf-8")) if path.exists() else None

    def update(self, job_id: str, mutate: Mutator) -> Job | None:
        with self._lock:
            job = self.get(job_id)
            if job is None:
                return None
            result = mutate(job)
            if result is not None:
                self._write(result)
            return result

    def delete(self, job_id: str) -> None:
        with self._lock:
            self._path(job_id).unlink(missing_ok=True)

    def _all(self) -> list[Job]:
        with self._lock:
            return [Job.model_validate_json(p.read_text(encoding="utf-8")) for p in self._dir.glob("*.json")]

    def list(self, owner_uid, statuses, service, cursor, limit):
        jobs = [
            j
            for j in self._all()
            if (owner_uid is None or j.owner_uid == owner_uid)
            and (statuses is None or j.status in statuses)
            and (service is None or service in j.services)
        ]
        jobs.sort(key=lambda j: j.created_at, reverse=True)
        start = int(cursor or 0)
        page = jobs[start : start + limit]
        return page, str(start + limit) if start + limit < len(jobs) else None

    def count_active(self, owner_uid: str) -> int:
        active = {JobStatus.AWAITING_PAYMENT, JobStatus.QUEUED, JobStatus.PROCESSING}
        return sum(1 for j in self._all() if j.owner_uid == owner_uid and j.status in active)

    def hit(self, key: str, window_sec: int) -> int:
        now = time.time()
        with self._lock:
            recent = [t for t in self._hits.get(key, []) if now - t < window_sec]
            recent.append(now)
            self._hits[key] = recent
            return len(recent)

    def get_flag(self, name: str, default: bool) -> bool:
        with self._lock:
            flags = json.loads(self._flags_path.read_text()) if self._flags_path.exists() else {}
            return bool(flags.get(name, default))

    def set_flag(self, name: str, value: bool) -> None:
        with self._lock:
            flags = json.loads(self._flags_path.read_text()) if self._flags_path.exists() else {}
            flags[name] = value
            self._flags_path.write_text(json.dumps(flags))

    # wallets: one file each, replaced atomically; every change runs under the same lock as jobs
    def _wallet_path(self, uid: str) -> Path:
        if not uid.replace("_", "").replace("-", "").isalnum():
            raise ValueError("invalid uid")
        return self._wallets / f"{uid}.json"

    def _write_wallet(self, wallet: Wallet) -> None:
        self._wallets.mkdir(parents=True, exist_ok=True)
        tmp = self._wallet_path(wallet.uid).with_suffix(".tmp")
        tmp.write_text(wallet.model_dump_json(by_alias=True), encoding="utf-8")
        tmp.replace(self._wallet_path(wallet.uid))

    def get_wallet(self, uid: str) -> Wallet | None:
        path = self._wallet_path(uid)
        with self._lock:
            return Wallet.model_validate_json(path.read_text(encoding="utf-8")) if path.exists() else None

    def update_wallet(self, uid: str, email: str, mutate: WalletMutator) -> Wallet | None:
        with self._lock:
            wallet = self.get_wallet(uid) or Wallet(uid=uid, email=email)
            result = mutate(wallet)
            if result is not None:
                self._write_wallet(result)
            return result

    def update_job_and_wallet(self, job_id: str, mutate: PairMutator) -> tuple[Job, Wallet] | None:
        with self._lock:
            job = self.get(job_id)
            if job is None:
                return None
            wallet = self.get_wallet(job.owner_uid) or Wallet(uid=job.owner_uid, email=job.owner_email)
            result = mutate(job, wallet)
            if result is not None:
                # wallet first: if the job write then failed, a restart reconciles from the job record
                self._write_wallet(result[1])
                self._write(result[0])
            return result

    def find_wallets(self, email_contains: str | None, limit: int) -> list[Wallet]:
        with self._lock:
            wallets = [Wallet.model_validate_json(p.read_text(encoding="utf-8")) for p in self._wallets.glob("*.json")]
        term = (email_contains or "").strip().lower()
        matches = [w for w in wallets if term in w.email.lower()]
        return sorted(matches, key=lambda w: w.updated_at, reverse=True)[:limit]

    def delete_wallet(self, uid: str) -> None:
        with self._lock:
            self._wallet_path(uid).unlink(missing_ok=True)


class FirestoreJobStore:
    """Production store: jobs/{jobId} documents, transactions for every update."""

    def __init__(self, project: str | None):
        from google.cloud import firestore

        self._fs = firestore
        self._db = firestore.Client(project=project)
        self._jobs = self._db.collection("jobs")
        self._wallets = self._db.collection("wallets")

    def create(self, job: Job) -> None:
        self._jobs.document(job.id).create(json.loads(_dump(job)))

    def get(self, job_id: str) -> Job | None:
        snap = self._jobs.document(job_id).get()
        return Job.model_validate(snap.to_dict()) if snap.exists else None

    def update(self, job_id: str, mutate: Mutator) -> Job | None:
        ref = self._jobs.document(job_id)

        @self._fs.transactional
        def run(transaction) -> Job | None:
            snap = ref.get(transaction=transaction)
            if not snap.exists:
                return None
            result = mutate(Job.model_validate(snap.to_dict()))
            if result is not None:
                transaction.set(ref, json.loads(_dump(result)))
            return result

        return run(self._db.transaction())

    def delete(self, job_id: str) -> None:
        self._jobs.document(job_id).delete()

    def list(self, owner_uid, statuses, service, cursor, limit):
        query = self._jobs
        if owner_uid:
            query = query.where(filter=self._fs.FieldFilter("ownerUid", "==", owner_uid))
        if statuses:
            query = query.where(filter=self._fs.FieldFilter("status", "in", [s.value for s in statuses][:30]))
        if service:
            query = query.where(filter=self._fs.FieldFilter("services", "array_contains", service))
        query = query.order_by("createdAt", direction=self._fs.Query.DESCENDING)
        if cursor:
            query = query.start_after({"createdAt": cursor})
        docs = list(query.limit(limit + 1).stream())
        jobs = [Job.model_validate(d.to_dict()) for d in docs[:limit]]
        next_cursor = docs[limit - 1].to_dict()["createdAt"] if len(docs) > limit else None
        return jobs, next_cursor

    def count_active(self, owner_uid: str) -> int:
        query = self._jobs.where(filter=self._fs.FieldFilter("ownerUid", "==", owner_uid)).where(
            filter=self._fs.FieldFilter("status", "in", ["AWAITING_PAYMENT", "QUEUED", "PROCESSING"])
        )
        return len(list(query.select([]).stream()))

    def hit(self, key: str, window_sec: int) -> int:
        bucket = int(time.time() // window_sec)
        ref = self._db.collection("rateLimits").document(f"{key}:{bucket}".replace("/", "_"))
        ref.set({"count": self._fs.Increment(1), "expiresAt": datetime.fromtimestamp((bucket + 2) * window_sec)}, merge=True)
        return int(ref.get().to_dict().get("count", 1))

    def get_flag(self, name: str, default: bool) -> bool:
        snap = self._db.collection("config").document("runtime").get()
        return bool((snap.to_dict() or {}).get(name, default)) if snap.exists else default

    def set_flag(self, name: str, value: bool) -> None:
        self._db.collection("config").document("runtime").set({name: value}, merge=True)

    def get_wallet(self, uid: str) -> Wallet | None:
        snap = self._wallets.document(uid).get()
        return Wallet.model_validate(snap.to_dict()) if snap.exists else None

    def update_wallet(self, uid: str, email: str, mutate: WalletMutator) -> Wallet | None:
        ref = self._wallets.document(uid)

        @self._fs.transactional
        def run(transaction) -> Wallet | None:
            snap = ref.get(transaction=transaction)
            wallet = Wallet.model_validate(snap.to_dict()) if snap.exists else Wallet(uid=uid, email=email)
            result = mutate(wallet)
            if result is not None:
                transaction.set(ref, json.loads(result.model_dump_json(by_alias=True)))
            return result

        return run(self._db.transaction())

    def update_job_and_wallet(self, job_id: str, mutate: PairMutator) -> tuple[Job, Wallet] | None:
        job_ref = self._jobs.document(job_id)

        @self._fs.transactional
        def run(transaction) -> tuple[Job, Wallet] | None:
            job_snap = job_ref.get(transaction=transaction)
            if not job_snap.exists:
                return None
            job = Job.model_validate(job_snap.to_dict())
            wallet_ref = self._wallets.document(job.owner_uid)
            wallet_snap = wallet_ref.get(transaction=transaction)  # every read before any write
            wallet = Wallet.model_validate(wallet_snap.to_dict()) if wallet_snap.exists else Wallet(uid=job.owner_uid, email=job.owner_email)
            result = mutate(job, wallet)
            if result is not None:
                transaction.set(job_ref, json.loads(_dump(result[0])))
                transaction.set(wallet_ref, json.loads(result[1].model_dump_json(by_alias=True)))
            return result

        return run(self._db.transaction())

    def find_wallets(self, email_contains: str | None, limit: int) -> list[Wallet]:
        # Firestore has no substring search; exact email match, or the most recently active wallets.
        term = (email_contains or "").strip().lower()
        query = self._wallets.where(filter=self._fs.FieldFilter("email", "==", term)) if term else self._wallets.order_by("updatedAt", direction=self._fs.Query.DESCENDING)
        return [Wallet.model_validate(d.to_dict()) for d in query.limit(limit).stream()]

    def delete_wallet(self, uid: str) -> None:
        self._wallets.document(uid).delete()
