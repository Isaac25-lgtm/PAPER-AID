"""Composition root: builds the store, file store and queue chosen in settings, once."""

from dataclasses import dataclass, field
from functools import lru_cache

from app.core.config import Settings, get_settings
from app.integrations.files import FileStore, GcsFileStore, LocalFileStore
from app.integrations.queue import CloudTasksQueue, LocalQueue, TaskQueue
from app.integrations.store import FirestoreJobStore, JobStore, LocalJobStore


@dataclass
class Runtime:
    settings: Settings
    store: JobStore
    files: FileStore
    queue: TaskQueue = field(init=False)


@lru_cache
def get_runtime() -> Runtime:
    from app.jobs.pipeline import run_step

    settings = get_settings()
    store: JobStore = FirestoreJobStore(settings.gcp_project) if settings.store_backend == "firestore" else LocalJobStore(settings.data_dir)
    files: FileStore = (
        GcsFileStore(settings.gcs_bucket or "", settings.gcp_project) if settings.storage_backend == "gcs" else LocalFileStore(settings.data_dir)
    )
    runtime = Runtime(settings, store, files)
    from app.proposals import rulebook

    rulebook.use_storage(files.get, files.exists)  # institution profiles built from students' guides
    from app.analysis import fetch

    fetch.set_openalex_key(settings.openalex_api_key.get_secret_value() if settings.openalex_api_key else "")
    runtime.queue = (
        CloudTasksQueue(settings)
        if settings.queue_backend == "cloud_tasks"
        else LocalQueue(lambda job_id: run_step(runtime, job_id), settings.queue_concurrency, settings)
    )
    return runtime
