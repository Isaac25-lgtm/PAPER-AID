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

from pydantic import ValidationError

from app.core.errors import PermanentStageError
from app.jobs.models import Job, JobStatus, LedgerEntry, Wallet
from app.proposals.models import Project
from app.works.models import Work

Mutator = Callable[[Job], Job | None]
WalletMutator = Callable[[Wallet], Wallet | None]
PairMutator = Callable[[Job, Wallet], tuple[Job, Wallet] | None]
ProjectMutator = Callable[[Project], Project | None]
# A proposal step's job, its owner's wallet and its project, changed as one unit (Codex audit #4).
TripleMutator = Callable[[Job, Wallet, Project | None], tuple[Job, Wallet, Project] | None]
WorkMutator = Callable[[Work], Work | None]
# A work step's job, its owner's wallet and its work, changed as one unit.
WorkTripleMutator = Callable[[Job, Wallet, Work | None], tuple[Job, Wallet, Work] | None]


class JobStore(Protocol):
    def create(self, job: Job) -> None: ...
    def create_if_open(self, job: Job) -> bool: ...
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
    def ledger(self, uid: str, before: str | None, limit: int) -> list[LedgerEntry]: ...
    def backfill_ledger(self, uid: str) -> bool: ...
    def all_wallet_ids(self) -> list[str]: ...
    def delete_ledger(self, uid: str) -> None: ...
    # proposal projects: one record each, changed only by atomic read-modify-write
    def create_project_if_open(self, project: Project) -> bool: ...
    def get_project(self, project_id: str) -> Project | None: ...
    def update_project(self, project_id: str, mutate: ProjectMutator) -> Project | None: ...
    def update_job_wallet_and_project(self, job_id: str, project_id: str, mutate: TripleMutator) -> tuple[Job, Wallet, Project] | None: ...
    def list_projects(self, owner_uid: str) -> list[Project]: ...
    def expired_project_ids(self, before: datetime) -> list[str]: ...
    def delete_project(self, project_id: str) -> None: ...
    def all_projects(self) -> list[Project]: ...
    def pending_projects(self) -> list[Project]: ...  # one-Start proposals whose plan's next step is still to happen
    # works (concept notes, coursework, funding proposals): their own collection, same guarantees
    def create_work_if_open(self, work: Work) -> bool: ...
    def get_work(self, work_id: str) -> Work | None: ...
    def update_work(self, work_id: str, mutate: WorkMutator) -> Work | None: ...
    def update_job_wallet_and_work(self, job_id: str, work_id: str, mutate: WorkTripleMutator) -> tuple[Job, Wallet, Work] | None: ...
    def list_works(self, owner_uid: str) -> list[Work]: ...
    def expired_work_ids(self, before: datetime) -> list[str]: ...
    def delete_work(self, work_id: str) -> None: ...
    def pending_works(self) -> list[Work]: ...  # one-Start works whose plan's next step is still to happen


# Firestore stores at most 1 MiB per document. Job records are kept well under that (long change
# text is trimmed in the pipeline; full text lives in job storage); this guard turns any record
# that still grows too large into a clear error instead of an obscure write failure.
MAX_RECORD_BYTES = 900_000


def _new_entries(seen: set[str], wallet: Wallet) -> list[LedgerEntry]:
    """Entries a transaction added. The wallet keeps only its recent entries for display; each new
    entry is also written as its own record, in the same transaction, so the history is complete."""
    return [e for e in wallet.entries if e.id not in seen]


def _entry_json(entry: LedgerEntry) -> dict:
    return json.loads(entry.model_dump_json(by_alias=True))


def cursor_of(entry: LedgerEntry) -> str:
    """A history page cursor: the entry's time and id, so entries sharing a time are never skipped
    (Codex audit 56c4f83 M11)."""
    return f"{_entry_json(entry)['at']}|{entry.id}"


def _after_cursor(entry: LedgerEntry, before: str | None) -> bool:
    if before is None:
        return True
    at, _, entry_id = before.partition("|")
    key = (_entry_json(entry)["at"], entry.id)
    return key < (at, entry_id or "\uffff")


def _dump(job: Job | Project | Work) -> str:
    data = job.model_dump_json(by_alias=True)
    size = len(data.encode("utf-8"))
    if size > MAX_RECORD_BYTES:
        raise PermanentStageError("RECORD_TOO_LARGE", "This job's results were too large to save. Our team has been notified.", f"job record {size} bytes")
    return data


class LocalJobStore:
    def __init__(self, root: Path):
        self._dir = root / "jobs"
        self._dir.mkdir(parents=True, exist_ok=True)
        self._flags_path = root / "flags.json"
        self._wallets = root / "wallets"
        self._wallets.mkdir(parents=True, exist_ok=True)
        # A job and its wallet are two files. Their paired change is first written, whole, to this
        # journal; it is removed only after both files are replaced. A leftover journal (a crash or
        # a failed write in between) is applied before anything is read again, so the two files
        # can never be seen disagreeing.
        self._journal = root / "pending-pair.json"
        self._projects = root / "projects"
        self._projects.mkdir(parents=True, exist_ok=True)
        self._works = root / "works"
        self._works.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._hits: dict[str, list[float]] = {}
        with self._lock:
            self._recover()

    def _recover(self) -> None:
        if not self._journal.exists():
            return
        pending = json.loads(self._journal.read_text(encoding="utf-8"))
        self._write_wallet(Wallet.model_validate(pending["wallet"]))
        if pending.get("job"):  # a wallet-only change has no job (Codex audit 56c4f83 M10)
            self._write(Job.model_validate(pending["job"]))
        if pending.get("project"):
            self._write_project(Project.model_validate(pending["project"]))
        if pending.get("work"):
            self._write_work(Work.model_validate(pending["work"]))
        self._journal.unlink()

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

    def create_if_open(self, job: Job) -> bool:
        """Create the job unless its owner's account is closing or closed, as one atomic step."""
        with self._lock:
            wallet = self.get_wallet(job.owner_uid)
            if wallet is not None and wallet.closing:
                return False
            self._write(job)
            return True

    def get(self, job_id: str) -> Job | None:
        path = self._path(job_id)
        with self._lock:
            self._recover()
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
            self._recover()
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

    def _ledger_path(self, uid: str) -> Path:
        return self._wallet_path(uid).with_suffix(".ledger.jsonl")

    def _write_wallet(self, wallet: Wallet) -> None:
        self._wallets.mkdir(parents=True, exist_ok=True)
        path = self._wallet_path(wallet.uid)
        seen = {e.id for e in Wallet.model_validate_json(path.read_text(encoding="utf-8")).entries} if path.exists() else set()
        new = _new_entries(seen, wallet)
        if new:  # appended before the wallet is replaced; a repeat after a crash is removed on reading
            self._append_ledger(wallet.uid, new)
        tmp = self._wallet_path(wallet.uid).with_suffix(".tmp")
        tmp.write_text(wallet.model_dump_json(by_alias=True), encoding="utf-8")
        tmp.replace(self._wallet_path(wallet.uid))

    def get_wallet(self, uid: str) -> Wallet | None:
        path = self._wallet_path(uid)
        with self._lock:
            self._recover()
            return Wallet.model_validate_json(path.read_text(encoding="utf-8")) if path.exists() else None

    def update_wallet(self, uid: str, email: str, mutate: WalletMutator) -> Wallet | None:
        with self._lock:
            wallet = self.get_wallet(uid) or Wallet(uid=uid, email=email)
            result = mutate(wallet)
            if result is not None:  # through the journal, like paired changes: a crash replays it whole
                tmp = self._journal.with_suffix(".tmp")
                tmp.write_text(json.dumps({"wallet": json.loads(result.model_dump_json(by_alias=True))}), encoding="utf-8")
                tmp.replace(self._journal)
                self._recover()
            return result

    def update_job_and_wallet(self, job_id: str, mutate: PairMutator) -> tuple[Job, Wallet] | None:
        with self._lock:
            job = self.get(job_id)
            if job is None:
                return None
            wallet = self.get_wallet(job.owner_uid) or Wallet(uid=job.owner_uid, email=job.owner_email)
            result = mutate(job, wallet)
            if result is not None:
                tmp = self._journal.with_suffix(".tmp")
                pair = {"job": json.loads(_dump(result[0])), "wallet": json.loads(result[1].model_dump_json(by_alias=True))}
                tmp.write_text(json.dumps(pair), encoding="utf-8")
                tmp.replace(self._journal)  # the change is now durable as one unit
                self._recover()
            return result

    def find_wallets(self, email_contains: str | None, limit: int) -> list[Wallet]:
        with self._lock:
            self._recover()
            wallets = [Wallet.model_validate_json(p.read_text(encoding="utf-8")) for p in self._wallets.glob("*.json")]
        term = (email_contains or "").strip().lower()
        matches = [w for w in wallets if term in w.email.lower() and not w.closing]
        return sorted(matches, key=lambda w: w.updated_at, reverse=True)[:limit]

    def delete_wallet(self, uid: str) -> None:
        with self._lock:
            self._wallet_path(uid).unlink(missing_ok=True)
            self._ledger_path(uid).unlink(missing_ok=True)

    def delete_ledger(self, uid: str) -> None:
        with self._lock:
            self._ledger_path(uid).unlink(missing_ok=True)

    def _append_ledger(self, uid: str, entries: list[LedgerEntry]) -> None:
        """Append history lines, first cutting off a line a crash left half-written (its change is
        replayed whole from the journal), so a new line never joins a torn one (Codex re-check M10)."""
        path = self._ledger_path(uid)
        if path.exists():
            data = path.read_bytes()
            if data and not data.endswith(b"\n"):
                path.write_bytes(data[: data.rfind(b"\n") + 1])
        with path.open("a", encoding="utf-8") as ledger:
            ledger.writelines(json.dumps(_entry_json(e)) + "\n" for e in entries)

    def _read_ledger(self, uid: str) -> dict[str, LedgerEntry]:
        path = self._ledger_path(uid)
        entries: dict[str, LedgerEntry] = {}
        for line in path.read_text(encoding="utf-8").splitlines() if path.exists() else []:
            try:
                entry = LedgerEntry.model_validate_json(line)
            except ValidationError:
                continue  # a torn line; its change was replayed from the journal
            entries[entry.id] = entry
        return entries

    def ledger(self, uid: str, before: str | None, limit: int) -> list[LedgerEntry]:
        with self._lock:
            entries = self._read_ledger(uid)
        ordered = sorted(entries.values(), key=lambda e: (_entry_json(e)["at"], e.id), reverse=True)
        return [e for e in ordered if _after_cursor(e, before)][:limit]

    def backfill_ledger(self, uid: str) -> bool:
        with self._lock:
            wallet = self.get_wallet(uid)
            if wallet is None or wallet.ledger_backfilled:
                return False
            known = set(self._read_ledger(uid))
            self._append_ledger(uid, [e for e in wallet.entries if e.id not in known])
            wallet.ledger_backfilled = True
            self._write_wallet(wallet)
            return True

    def all_wallet_ids(self) -> list[str]:
        with self._lock:
            return [p.stem for p in self._wallets.glob("*.json")]

    # projects: one file each, replaced atomically under the same lock
    def _project_path(self, project_id: str) -> Path:
        if not project_id.replace("_", "").isalnum():
            raise ValueError("invalid project id")
        return self._projects / f"{project_id}.json"

    def _write_project(self, project: Project) -> None:
        self._projects.mkdir(parents=True, exist_ok=True)
        tmp = self._project_path(project.id).with_suffix(".tmp")
        tmp.write_text(_dump(project), encoding="utf-8")
        tmp.replace(self._project_path(project.id))

    def create_project_if_open(self, project: Project) -> bool:
        with self._lock:
            wallet = self.get_wallet(project.owner_uid)
            if wallet is not None and wallet.closing:
                return False
            self._write_project(project)
            return True

    def get_project(self, project_id: str) -> Project | None:
        path = self._project_path(project_id)
        with self._lock:
            return Project.model_validate_json(path.read_text(encoding="utf-8")) if path.exists() else None

    def update_project(self, project_id: str, mutate: ProjectMutator) -> Project | None:
        with self._lock:
            project = self.get_project(project_id)
            if project is None:
                return None
            result = mutate(project)
            if result is not None:
                self._write_project(result)
            return result

    def update_job_wallet_and_project(self, job_id: str, project_id: str, mutate: TripleMutator) -> tuple[Job, Wallet, Project] | None:
        with self._lock:
            job = self.get(job_id)
            if job is None:
                return None
            wallet = self.get_wallet(job.owner_uid) or Wallet(uid=job.owner_uid, email=job.owner_email)
            result = mutate(job, wallet, self.get_project(project_id))
            if result is not None:
                tmp = self._journal.with_suffix(".tmp")
                triple = {
                    "job": json.loads(_dump(result[0])),
                    "wallet": json.loads(result[1].model_dump_json(by_alias=True)),
                    "project": json.loads(_dump(result[2])),
                }
                tmp.write_text(json.dumps(triple), encoding="utf-8")
                tmp.replace(self._journal)  # durable as one unit, applied (or re-applied) by _recover
                self._recover()
            return result

    def list_projects(self, owner_uid: str) -> list[Project]:
        with self._lock:
            found = [Project.model_validate_json(p.read_text(encoding="utf-8")) for p in self._projects.glob("*.json")]
        return sorted((p for p in found if p.owner_uid == owner_uid), key=lambda p: p.updated_at, reverse=True)

    def expired_project_ids(self, before: datetime) -> list[str]:
        with self._lock:
            found = [Project.model_validate_json(p.read_text(encoding="utf-8")) for p in self._projects.glob("*.json")]
        return [p.id for p in sorted((p for p in found if p.expires_at < before), key=lambda p: (p.expires_at, p.id))]

    def delete_project(self, project_id: str) -> None:
        with self._lock:
            self._project_path(project_id).unlink(missing_ok=True)

    def all_projects(self) -> list[Project]:
        with self._lock:
            return [Project.model_validate_json(p.read_text(encoding="utf-8")) for p in self._projects.glob("*.json")]

    def pending_projects(self) -> list[Project]:
        return [p for p in self.all_projects() if p.auto_next]

    # works: one file each in their own directory, replaced atomically under the same lock
    def _work_path(self, work_id: str) -> Path:
        if not work_id.replace("_", "").isalnum():
            raise ValueError("invalid work id")
        return self._works / f"{work_id}.json"

    def _write_work(self, work: Work) -> None:
        self._works.mkdir(parents=True, exist_ok=True)
        tmp = self._work_path(work.id).with_suffix(".tmp")
        tmp.write_text(_dump(work), encoding="utf-8")
        tmp.replace(self._work_path(work.id))

    def _all_works(self) -> list[Work]:
        with self._lock:
            return [Work.model_validate_json(p.read_text(encoding="utf-8")) for p in self._works.glob("*.json")]

    def create_work_if_open(self, work: Work) -> bool:
        with self._lock:
            wallet = self.get_wallet(work.owner_uid)
            if wallet is not None and wallet.closing:
                return False
            self._write_work(work)
            return True

    def get_work(self, work_id: str) -> Work | None:
        path = self._work_path(work_id)
        with self._lock:
            return Work.model_validate_json(path.read_text(encoding="utf-8")) if path.exists() else None

    def update_work(self, work_id: str, mutate: WorkMutator) -> Work | None:
        with self._lock:
            work = self.get_work(work_id)
            if work is None:
                return None
            result = mutate(work)
            if result is not None:
                self._write_work(result)
            return result

    def update_job_wallet_and_work(self, job_id: str, work_id: str, mutate: WorkTripleMutator) -> tuple[Job, Wallet, Work] | None:
        with self._lock:
            job = self.get(job_id)
            if job is None:
                return None
            wallet = self.get_wallet(job.owner_uid) or Wallet(uid=job.owner_uid, email=job.owner_email)
            result = mutate(job, wallet, self.get_work(work_id))
            if result is not None:
                tmp = self._journal.with_suffix(".tmp")
                triple = {"job": json.loads(_dump(result[0])), "wallet": json.loads(result[1].model_dump_json(by_alias=True)), "work": json.loads(_dump(result[2]))}
                tmp.write_text(json.dumps(triple), encoding="utf-8")
                tmp.replace(self._journal)  # durable as one unit, applied (or re-applied) by _recover
                self._recover()
            return result

    def list_works(self, owner_uid: str) -> list[Work]:
        return sorted((w for w in self._all_works() if w.owner_uid == owner_uid), key=lambda w: w.updated_at, reverse=True)

    def pending_works(self) -> list[Work]:
        return [w for w in self._all_works() if w.auto_next]

    def expired_work_ids(self, before: datetime) -> list[str]:
        return [w.id for w in sorted((w for w in self._all_works() if w.expires_at < before), key=lambda w: (w.expires_at, w.id))]

    def delete_work(self, work_id: str) -> None:
        with self._lock:
            self._work_path(work_id).unlink(missing_ok=True)


class FirestoreJobStore:
    """Production store: jobs/{jobId} documents, transactions for every update."""

    def __init__(self, project: str | None):
        from google.cloud import firestore

        self._fs = firestore
        self._db = firestore.Client(project=project)
        self._jobs = self._db.collection("jobs")
        self._wallets = self._db.collection("wallets")
        self._projects = self._db.collection("projects")
        self._works = self._db.collection("works")

    def create(self, job: Job) -> None:
        self._jobs.document(job.id).create(json.loads(_dump(job)))

    def create_if_open(self, job: Job) -> bool:
        """Create the job unless its owner's account is closing or closed, in one transaction: a
        deletion that closes the account in between makes this transaction retry and refuse."""
        wallet_ref, job_ref = self._wallets.document(job.owner_uid), self._jobs.document(job.id)

        @self._fs.transactional
        def run(transaction) -> bool:
            snap = wallet_ref.get(transaction=transaction)
            if snap.exists and Wallet.model_validate(snap.to_dict()).closing:
                return False
            transaction.create(job_ref, json.loads(_dump(job)))
            return True

        return run(self._db.transaction())

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
            seen = {e.id for e in wallet.entries}
            result = mutate(wallet)
            if result is not None:
                transaction.set(ref, json.loads(result.model_dump_json(by_alias=True)))
                for entry in _new_entries(seen, result):
                    transaction.set(ref.collection("ledger").document(entry.id), _entry_json(entry))
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
            seen = {e.id for e in wallet.entries}
            result = mutate(job, wallet)
            if result is not None:
                transaction.set(job_ref, json.loads(_dump(result[0])))
                transaction.set(wallet_ref, json.loads(result[1].model_dump_json(by_alias=True)))
                for entry in _new_entries(seen, result[1]):
                    transaction.set(wallet_ref.collection("ledger").document(entry.id), _entry_json(entry))
            return result

        return run(self._db.transaction())

    def find_wallets(self, email_contains: str | None, limit: int) -> list[Wallet]:
        # Firestore has no substring search; exact email match, or the most recently active wallets.
        term = (email_contains or "").strip().lower()
        query = self._wallets.where(filter=self._fs.FieldFilter("email", "==", term)) if term else self._wallets.order_by("updatedAt", direction=self._fs.Query.DESCENDING)
        found = [Wallet.model_validate(d.to_dict()) for d in query.limit(limit).stream()]
        return [w for w in found if not w.closing]  # closed-account tombstones are never offered to admins

    def delete_wallet(self, uid: str) -> None:
        self.delete_ledger(uid)
        self._wallets.document(uid).delete()

    def delete_ledger(self, uid: str) -> None:
        ledger = self._wallets.document(uid).collection("ledger")
        while True:  # in batches: a subcollection is not deleted with its parent
            docs = list(ledger.limit(400).stream())
            if not docs:
                return
            batch = self._db.batch()
            for doc in docs:
                batch.delete(doc.reference)
            batch.commit()

    def ledger(self, uid: str, before: str | None, limit: int) -> list[LedgerEntry]:
        descending = self._fs.Query.DESCENDING
        query = self._wallets.document(uid).collection("ledger").order_by("at", direction=descending).order_by("id", direction=descending)
        if before:
            at, _, entry_id = before.partition("|")
            query = query.start_after({"at": at, "id": entry_id})
        return [LedgerEntry.model_validate(d.to_dict()) for d in query.limit(limit).stream()]

    def backfill_ledger(self, uid: str) -> bool:
        ref = self._wallets.document(uid)

        @self._fs.transactional
        def run(transaction) -> bool:
            snap = ref.get(transaction=transaction)
            if not snap.exists:
                return False
            wallet = Wallet.model_validate(snap.to_dict())
            if wallet.ledger_backfilled:
                return False
            for entry in wallet.entries:  # set by id: repeating it changes nothing
                transaction.set(ref.collection("ledger").document(entry.id), _entry_json(entry))
            transaction.update(ref, {"ledgerBackfilled": True})
            return True

        return run(self._db.transaction())

    def all_wallet_ids(self) -> list[str]:
        return [d.id for d in self._wallets.select([]).stream()]

    def create_project_if_open(self, project: Project) -> bool:
        """Like `create_if_open`: the account check and the write are one transaction."""
        wallet_ref, project_ref = self._wallets.document(project.owner_uid), self._projects.document(project.id)

        @self._fs.transactional
        def run(transaction) -> bool:
            snap = wallet_ref.get(transaction=transaction)
            if snap.exists and Wallet.model_validate(snap.to_dict()).closing:
                return False
            transaction.create(project_ref, json.loads(_dump(project)))
            return True

        return run(self._db.transaction())

    def get_project(self, project_id: str) -> Project | None:
        snap = self._projects.document(project_id).get()
        return Project.model_validate(snap.to_dict()) if snap.exists else None

    def update_project(self, project_id: str, mutate: ProjectMutator) -> Project | None:
        ref = self._projects.document(project_id)

        @self._fs.transactional
        def run(transaction) -> Project | None:
            snap = ref.get(transaction=transaction)
            if not snap.exists:
                return None
            result = mutate(Project.model_validate(snap.to_dict()))
            if result is not None:
                transaction.set(ref, json.loads(_dump(result)))
            return result

        return run(self._db.transaction())

    def update_job_wallet_and_project(self, job_id: str, project_id: str, mutate: TripleMutator) -> tuple[Job, Wallet, Project] | None:
        job_ref, project_ref = self._jobs.document(job_id), self._projects.document(project_id)

        @self._fs.transactional
        def run(transaction) -> tuple[Job, Wallet, Project] | None:
            job_snap = job_ref.get(transaction=transaction)
            if not job_snap.exists:
                return None
            job = Job.model_validate(job_snap.to_dict())
            wallet_ref = self._wallets.document(job.owner_uid)
            wallet_snap = wallet_ref.get(transaction=transaction)  # every read before any write
            project_snap = project_ref.get(transaction=transaction)
            wallet = Wallet.model_validate(wallet_snap.to_dict()) if wallet_snap.exists else Wallet(uid=job.owner_uid, email=job.owner_email)
            project = Project.model_validate(project_snap.to_dict()) if project_snap.exists else None
            seen = {e.id for e in wallet.entries}
            result = mutate(job, wallet, project)
            if result is not None:
                transaction.set(job_ref, json.loads(_dump(result[0])))
                transaction.set(wallet_ref, json.loads(result[1].model_dump_json(by_alias=True)))
                transaction.set(project_ref, json.loads(_dump(result[2])))
                for entry in _new_entries(seen, result[1]):
                    transaction.set(wallet_ref.collection("ledger").document(entry.id), _entry_json(entry))
            return result

        return run(self._db.transaction())

    def all_projects(self) -> list[Project]:
        # Only the maintenance migration uses this; a student has few projects and there are few in all.
        return [Project.model_validate(d.to_dict()) for d in self._projects.stream()]

    def pending_projects(self) -> list[Project]:
        # A single-field range filter: no composite index; only records with a pending step match.
        return [Project.model_validate(d.to_dict()) for d in self._projects.where(filter=self._fs.FieldFilter("autoNext", ">", "")).stream()]

    def list_projects(self, owner_uid: str) -> list[Project]:
        # An equality filter alone needs no composite index; a student has only a few projects.
        docs = self._projects.where(filter=self._fs.FieldFilter("ownerUid", "==", owner_uid)).stream()
        return sorted((Project.model_validate(d.to_dict()) for d in docs), key=lambda p: p.updated_at, reverse=True)

    def expired_project_ids(self, before: datetime) -> list[str]:
        # A single-field range filter uses Firestore's automatic index. Timestamps are stored as
        # UTC ISO strings of one format, so string order is time order. The stream pages itself.
        iso = before.isoformat().replace("+00:00", "Z")
        return [d.id for d in self._projects.where(filter=self._fs.FieldFilter("expiresAt", "<", iso)).select([]).stream()]

    def delete_project(self, project_id: str) -> None:
        self._projects.document(project_id).delete()

    def create_work_if_open(self, work: Work) -> bool:
        wallet_ref, work_ref = self._wallets.document(work.owner_uid), self._works.document(work.id)

        @self._fs.transactional
        def run(transaction) -> bool:
            snap = wallet_ref.get(transaction=transaction)
            if snap.exists and Wallet.model_validate(snap.to_dict()).closing:
                return False
            transaction.create(work_ref, json.loads(_dump(work)))
            return True

        return run(self._db.transaction())

    def get_work(self, work_id: str) -> Work | None:
        snap = self._works.document(work_id).get()
        return Work.model_validate(snap.to_dict()) if snap.exists else None

    def update_work(self, work_id: str, mutate: WorkMutator) -> Work | None:
        ref = self._works.document(work_id)

        @self._fs.transactional
        def run(transaction) -> Work | None:
            snap = ref.get(transaction=transaction)
            if not snap.exists:
                return None
            result = mutate(Work.model_validate(snap.to_dict()))
            if result is not None:
                transaction.set(ref, json.loads(_dump(result)))
            return result

        return run(self._db.transaction())

    def update_job_wallet_and_work(self, job_id: str, work_id: str, mutate: WorkTripleMutator) -> tuple[Job, Wallet, Work] | None:
        job_ref, work_ref = self._jobs.document(job_id), self._works.document(work_id)

        @self._fs.transactional
        def run(transaction) -> tuple[Job, Wallet, Work] | None:
            job_snap = job_ref.get(transaction=transaction)
            if not job_snap.exists:
                return None
            job = Job.model_validate(job_snap.to_dict())
            wallet_ref = self._wallets.document(job.owner_uid)
            wallet_snap = wallet_ref.get(transaction=transaction)  # every read before any write
            work_snap = work_ref.get(transaction=transaction)
            wallet = Wallet.model_validate(wallet_snap.to_dict()) if wallet_snap.exists else Wallet(uid=job.owner_uid, email=job.owner_email)
            work = Work.model_validate(work_snap.to_dict()) if work_snap.exists else None
            seen = {e.id for e in wallet.entries}
            result = mutate(job, wallet, work)
            if result is not None:
                transaction.set(job_ref, json.loads(_dump(result[0])))
                transaction.set(wallet_ref, json.loads(result[1].model_dump_json(by_alias=True)))
                transaction.set(work_ref, json.loads(_dump(result[2])))
                for entry in _new_entries(seen, result[1]):
                    transaction.set(wallet_ref.collection("ledger").document(entry.id), _entry_json(entry))
            return result

        return run(self._db.transaction())

    def list_works(self, owner_uid: str) -> list[Work]:
        docs = self._works.where(filter=self._fs.FieldFilter("ownerUid", "==", owner_uid)).stream()
        return sorted((Work.model_validate(d.to_dict()) for d in docs), key=lambda w: w.updated_at, reverse=True)

    def pending_works(self) -> list[Work]:
        return [Work.model_validate(d.to_dict()) for d in self._works.where(filter=self._fs.FieldFilter("autoNext", ">", "")).stream()]

    def expired_work_ids(self, before: datetime) -> list[str]:
        iso = before.isoformat().replace("+00:00", "Z")
        return [d.id for d in self._works.where(filter=self._fs.FieldFilter("expiresAt", "<", iso)).select([]).stream()]

    def delete_work(self, work_id: str) -> None:
        self._works.document(work_id).delete()
