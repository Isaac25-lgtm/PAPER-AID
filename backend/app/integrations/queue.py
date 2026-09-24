"""The job queue. Production uses Cloud Tasks (OIDC-authenticated delivery to the internal
worker). Locally, a bounded thread pool runs the same `run_step` function — it refuses to
start in production. Task names are deterministic so duplicate enqueues are harmless."""

import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Protocol

from app.core.config import Settings


class TaskQueue(Protocol):
    def enqueue(self, job_id: str, task_name: str, delay_sec: float = 0) -> None: ...


class LocalQueue:
    def __init__(self, runner: Callable[[str], None], concurrency: int, settings: Settings):
        if settings.env == "production":
            raise RuntimeError("The local queue must never run in production.")
        self._runner = runner
        self._pool = ThreadPoolExecutor(max_workers=concurrency, thread_name_prefix="job-worker")
        self._seen: set[str] = set()
        self._lock = threading.Lock()

    def enqueue(self, job_id: str, task_name: str, delay_sec: float = 0) -> None:
        with self._lock:
            if task_name in self._seen:
                return
            self._seen.add(task_name)
        def run() -> None:
            try:
                self._runner(job_id)
            finally:
                with self._lock:
                    self._seen.discard(task_name)  # names are only needed while a task is pending

        if delay_sec > 0:
            timer = threading.Timer(delay_sec, lambda: self._pool.submit(run))
            timer.daemon = True
            timer.start()
        else:
            self._pool.submit(run)

    def shutdown(self) -> None:
        self._pool.shutdown(wait=False, cancel_futures=True)


class CloudTasksQueue:
    def __init__(self, settings: Settings):
        from google.api_core.exceptions import AlreadyExists
        from google.cloud import tasks_v2

        self._tasks = tasks_v2
        self._already_exists = AlreadyExists
        self._client = tasks_v2.CloudTasksClient()
        self._parent = self._client.queue_path(settings.gcp_project, settings.tasks_location, settings.tasks_queue)
        self._worker_url = f"{settings.worker_url}/tasks/run-step"
        self._invoker = settings.tasks_invoker_email

    def enqueue(self, job_id: str, task_name: str, delay_sec: float = 0) -> None:
        import json
        from datetime import UTC, datetime, timedelta

        from google.protobuf import timestamp_pb2

        task: dict = {
            "name": f"{self._parent}/tasks/{task_name}",
            "http_request": {
                "http_method": self._tasks.HttpMethod.POST,
                "url": self._worker_url,
                "headers": {"Content-Type": "application/json"},
                "body": json.dumps({"jobId": job_id}).encode(),
                "oidc_token": {"service_account_email": self._invoker, "audience": self._worker_url.rsplit("/tasks", 1)[0]},
            },
            "dispatch_deadline": {"seconds": 1800},
        }
        if delay_sec > 0:
            ts = timestamp_pb2.Timestamp()
            ts.FromDatetime(datetime.now(UTC) + timedelta(seconds=delay_sec))
            task["schedule_time"] = ts
        try:
            self._client.create_task(parent=self._parent, task=task)
        except self._already_exists:
            pass  # same deterministic name: this step is already queued
