from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Every limit, model name and backend choice lives here, read from env / .env."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    env: Literal["local", "production"] = "local"
    data_dir: Path = Path(".data")
    log_level: str = "INFO"

    # Backends: "local" runs everything on this machine; the cloud values are for Cloud Run.
    auth_mode: Literal["dev", "firebase"] = "dev"
    store_backend: Literal["local", "firestore"] = "local"
    storage_backend: Literal["local", "gcs"] = "local"
    queue_backend: Literal["local", "cloud_tasks"] = "local"
    admin_emails: list[str] = []  # dev auth only; production uses the `admin` custom claim
    require_app_check: bool = False
    allowed_origins: list[str] = ["http://localhost:5000"]

    # AI providers. The algorithm has two fixed roles (see app/ai/orchestration.py):
    #   lead   — analyses the paper, drafts and finalises the plan, reviews the result (GPT-6 Sol)
    #   writer — critiques the draft plan, writes the result, fixes what the review raises (Claude Opus 5.5)
    # Both keys are required. Without them the AI services are shown as not set up and cannot be
    # quoted or run; there is no stand-in.
    lead_model: str = "openai:gpt-6-sol"
    writer_model: str = "anthropic:claude-opus-5-5"
    model_prices: dict[str, tuple[float, float, float]] = {}  # "provider:model" → USD per 1M (input, output, cached input)
    anthropic_api_key: SecretStr | None = None
    openai_api_key: SecretStr | None = None
    provider_timeout_sec: float = 180
    writer_effort: Literal["low", "medium", "high", "xhigh", "max"] = "medium"

    # Product rules
    payments_enabled: bool = False
    processing_enabled: bool = True
    queue_concurrency: int = 5
    max_active_jobs_per_user: int = 3
    quotes_per_hour: int = 40
    submits_per_hour: int = 10
    max_upload_bytes: int = 20 * 1024 * 1024
    max_words: int = 25_000
    max_pdf_pages: int = 150
    retention_days: int = 30
    quote_ttl_minutes: int = 30
    stage_max_attempts: int = 4
    repair_attempts: int = 2
    max_failed_share: float = 0.3

    # Cost control
    ugx_per_usd: float = 3700
    job_budget_share: float = 0.6  # the plan/critique/final-plan/review loop makes ~7 model calls per job
    job_budget_cap_usd: float = 6.0
    job_budget_floor_usd: float = 1.50

    # Google Cloud (production only)
    gcp_project: str | None = None
    gcs_bucket: str | None = None
    tasks_location: str = "europe-west1"
    tasks_queue: str = "paper-jobs"
    worker_url: str | None = None
    tasks_invoker_email: str | None = None

    @model_validator(mode="after")
    def _fail_closed_in_production(self) -> "Settings":
        if self.env != "production":
            return self
        problems = []
        if self.auth_mode != "firebase":
            problems.append("AUTH_MODE must be firebase")
        if self.store_backend != "firestore" or self.storage_backend != "gcs" or self.queue_backend != "cloud_tasks":
            problems.append("production requires firestore, gcs and cloud_tasks backends")
        if not self.require_app_check:
            problems.append("REQUIRE_APP_CHECK must be true")
        if not (self.gcp_project and self.gcs_bucket and self.worker_url and self.tasks_invoker_email):
            problems.append("GCP_PROJECT, GCS_BUCKET, WORKER_URL and TASKS_INVOKER_EMAIL are required")
        if not self.ai_configured:
            problems.append("OPENAI_API_KEY and ANTHROPIC_API_KEY are required")
        if problems:
            raise ValueError("Unsafe production configuration: " + "; ".join(problems))
        return self


    @property
    def ai_configured(self) -> bool:
        return all(key is not None and key.get_secret_value().strip() for key in (self.openai_api_key, self.anthropic_api_key))


@lru_cache
def get_settings() -> Settings:
    return Settings()
