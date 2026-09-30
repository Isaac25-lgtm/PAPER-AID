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
    ai_check_model: str = "openai:gpt-6-luna"  # writing-pattern reviewer, owner decision 2026-09-29
    ai_check_peer_model: str | None = "anthropic:claude-sonnet-5-5"
    routine_model: str | None = "openai:gpt-6-luna"
    drafting_model: str | None = "anthropic:claude-sonnet-5-5"
    require_dual_approval: bool = True  # nothing generated is delivered without approval (older engines: by both reviewers)
    # One accountable final reviewer (owner decision 2026-09-30, superseding the dual veto): Sol alone
    # approves generated wording, after bounded targeted repair and re-review; no second automatic veto.
    single_reviewer: bool = True
    # Opus's advisory guidance before a plan is finalised: optional, off by default, never a veto.
    frontier_guidance: bool = False
    # A new chapter delivers its approved sections and "Finish chapter" writes the rest. Off until a
    # rollback to 1d573b6 (which cannot protect a partly written chapter) is no longer needed (owner, 2026-09-30).
    partial_chapters: bool = False
    # The AI-likeness percentage and band. Off: a real-model pilot scored 10 human and 10 AI-written papers
    # alike (6% each), so students get writing-pattern feedback only until a validated detector exists
    # (owner decision 2026-09-30). The score is still computed and kept for admins and calibration.
    show_ai_score: bool = False
    model_prices: dict[str, tuple[float, float, float]] = {}  # "provider:model" → USD per 1M (input, output, cached input)
    anthropic_api_key: SecretStr | None = None
    openai_api_key: SecretStr | None = None
    gemini_api_key: SecretStr | None = None  # Secret Manager GEMINI_API_KEY (paid tier), for roles on google:*

    # Works (concept notes, coursework, funding proposals; owner decisions 2026-09-30). Each role is a
    # "provider:model" in configuration, so changing API in January is a settings change; a quote
    # freezes the roles, the tier and the dated price table it was priced with.
    role_models: dict[str, str] = {
        "ANALYST": "openai:gpt-6-luna",  # reads documents, extracts requirements, plans research, classifies
        "WRITER": "google:gemini-3.8-flash",  # plans, drafts and repairs
        "INTEGRITY": "openai:gpt-6-luna",  # checks meaning is kept and nothing is invented; checks evidence
        "EVALUATOR_STANDARD": "anthropic:claude-sonnet-5-5",  # judges each section against its rules (a check, not the release decision)
        "EVALUATOR_PREMIUM": "anthropic:claude-sonnet-5-5",  # was Opus: Opus now only advises (owner decision 2026-09-30)
        "FINAL": "openai:gpt-6-sol",  # the one accountable final reviewer of plans, Results Models and documents
        "ADJUDICATOR": "",  # none configured: an unresolved disagreement becomes "Needs review"
    }
    # Which reviewers run behind each service's price. Students never choose or see a tier.
    service_tiers: dict[str, str] = {"CONCEPT_NOTE": "STANDARD", "COURSEWORK": "STANDARD", "FUNDING_PROPOSAL": "PREMIUM"}
    # The most one step of each service may spend on providers (USD), whatever its band's projection;
    # past it the step stops escalating and what is left is marked for review, never overspent (B5).
    # Above every band's worst case, so each band runs on its own projection (2026-09-30).
    work_budget_cap_usd: dict[str, float] = {"CONCEPT_NOTE": 8.0, "COURSEWORK": 15.0, "FUNDING_PROPOSAL": 40.0}
    # New services are switched on here, one by one, once their token prices are set (owner).
    works_enabled: list[str] = []
    # While false, the work services are open only to the invited testers and admins, even when the
    # tester list is empty: the pilot fails closed (Codex audit 2026-09-30, second round).
    works_public: bool = False
    # Rendered page counts with LibreOffice in the worker (Workstream H). Off: page limits are
    # estimated from words and shown as "Needs review".
    render_pages: bool = False
    provider_timeout_sec: float = 180
    writer_effort: Literal["low", "medium", "high", "xhigh", "max"] = "medium"

    # Product rules
    payments_enabled: bool = False
    processing_enabled: bool = True
    queue_concurrency: int = 5
    max_active_jobs_per_user: int = 3
    quotes_per_hour: int = 40
    submits_per_hour: int = 10
    uploads_per_hour: int = 20  # feedback, guides, rebuilt downloads and PDFs, per student (Codex audit 56c4f83 M21)
    max_upload_bytes: int = 20 * 1024 * 1024
    max_words: int = 25_000
    max_pdf_pages: int = 150
    retention_days: int = 30
    quote_ttl_minutes: int = 30
    stage_max_attempts: int = 4
    repair_attempts: int = 2
    research_max_claims: int = 10  # source check: most claims checked in one paper
    research_max_searches: int = 2  # source check: most web searches per claim
    # Proposal projects: research needs planned per step (0 = the plan, then each chapter), scholarly
    # works read per need, and the longest proposal the review service accepts.
    proposal_needs: dict[int, int] = {0: 6, 1: 8, 2: 12, 3: 5, 4: 4}  # 4: the concept paper
    proposal_works_per_need: int = 6
    proposal_review_max_words: int = 20000

    # Invited testers (owner decision 2026-09-25): while set, only these emails (and admins) may use
    # the AI services, so a public link can't spend the AI budget. Empty = open to every user.
    tester_emails: list[str] = []

    # Credits and pricing (owner decisions, 2026-09-24; see docs/decisions.md "Prepaid credits").
    # A job costs its actual AI spend × price_multiplier, converted at ugx_per_usd and never more
    # than its quote; quotes add quote_safety_margin on top of the projected AI spend.
    # Off = testing mode (owner decision 2026-09-25): no balance needed, nothing held or charged;
    # prices are still calculated and shown as "not charged while testing".
    credits_enabled: bool = True
    price_multiplier: float = 2.0
    ugx_per_usd: float = 4000  # market was ~3,907 on 2026-09-23; rounded up as a buffer. Review monthly.
    quote_safety_margin: float = 0.2
    format_ugx_per_300_words: int = 100  # APA/Harvard formatting uses no AI
    format_min_ugx: int = 2000
    latex_ugx_per_300_words: int = 150  # LaTeX conversion uses no AI (owner decision 2026-09-27)
    latex_min_ugx: int = 3000
    min_top_up_ugx: int = 10000  # 10 tokens (owner's master context)
    # Students see tokens, not money (owner decision 2026-09-28); the ledger stays in UGX.
    ugx_per_token: int = 1000
    # Fixed prices by page band (owner decision 2026-09-28, from the master context's table). Each
    # price covers up to `band_pages` pages; each further band adds `band_step` of it. "cost" is
    # the earlier policy (actual AI spend × multiplier, quoted as a ceiling after an estimate).
    pricing_mode: Literal["fixed", "cost"] = "fixed"
    fixed_tokens: dict[str, float] = {
        "AI_CHECK": 2, "ACADEMIC": 1, "REFINE_LIGHT": 3, "REFINE": 4, "REDRAFT": 7,
        "SOURCE_CHECK": 3,  # not in the owner's table: to be confirmed
        "TEMPLATE_FORMAT": 3, "PLAN": 2, "CHAPTER_1": 5, "CHAPTER_2": 7, "CHAPTER_3": 5, "REVIEW": 2,
        "REVISE": 2,  # a chapter revised from supervisor comments, per band of revised text: to be confirmed
        "CONCEPT": 2,  # the concept paper (at most five pages): to be confirmed
        "PROFILE": 2,  # an institution profile from the student's guide: to be confirmed
        # Works, for testing (owner, 2026-09-30): the worst-case projection x 2, rounded; to be
        # confirmed against real spend before students pay.
        "WORK_READ": 1, "WORK_REVISE": 17,
        "CW_PLAN": 3, "CW_1500": 20, "CW_3000": 35, "CW_5000": 60, "CW_8000": 90,
        "CN_PLAN": 3, "CN_BRIEF": 20, "CN_STANDARD": 34, "CN_EXTENDED": 44,
        "FP_PLAN": 7, "FP_COMPACT": 57, "FP_STANDARD": 122, "FP_COMPREHENSIVE": 247,
    }
    band_pages: int = 10
    band_step: float = 0.75
    words_per_page: int = 250

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
        # Missing AI keys are not unsafe: the AI services show as "Not set up" and cannot run
        # (owner decision 2026-09-25: go live with formatting first, add the keys later).
        if problems:
            raise ValueError("Unsafe production configuration: " + "; ".join(problems))
        return self


    @property
    def ai_configured(self) -> bool:
        return all(key is not None and key.get_secret_value().strip() for key in (self.openai_api_key, self.anthropic_api_key))

    @property
    def roles_configured(self) -> bool:
        """Every provider a configured work role needs has its key."""
        keys = {"openai": self.openai_api_key, "anthropic": self.anthropic_api_key, "google": self.gemini_api_key}
        for ref in self.role_models.values():
            if not ref:
                continue
            key = keys.get(ref.partition(":")[0])
            if key is None or not key.get_secret_value().strip():
                return False
        return True


@lru_cache
def get_settings() -> Settings:
    return Settings()
