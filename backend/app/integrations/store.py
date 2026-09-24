"""Job metadata storage. `LocalJobStore` (JSON files) runs everything on one machine;
`FirestoreJobStore` is the production implementation. Both give the same guarantees the job
engine relies on: atomic read-modify-write per job, and owner-scoped listing."""

import json
import threading
import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Protocol

from app.jobs.models import Job, JobStatus

Mutator = Callable[[Job], Job | None]


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


def _dump(job: Job) -> str:
    return job.model_dump_json(by_alias=True)


class LocalJobStore:
    def __init__(self, root: Path):
        self._dir = root / "jobs"
        self._dir.mkdir(parents=True, exist_ok=True)
        self._flags_path = root / "flags.json"
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


class FirestoreJobStore:
    """Production store: jobs/{jobId} documents, transactions for every update."""

    def __init__(self, project: str | None):
        from google.cloud import firestore

        self._fs = firestore
        self._db = firestore.Client(project=project)
        self._jobs = self._db.collection("jobs")

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
