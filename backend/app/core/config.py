from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.ai.gemini import CONFIRMED_MODELS, GeminiModel, Thinking, VertexPrice
from app.ai.vertex_pricing import VERIFIED_VERTEX_PRICES


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
    # The "Check for AI" step itself (owner decision 2026-10-07): hidden until a validated detector is
    # integrated. Paper Check stays open and starts at Redraft; a redraft still reads the paper the same
    # way internally to choose what to change.
    ai_check_enabled: bool = False
    model_prices: dict[str, tuple[float, float, float]] = {}  # "provider:model" → USD per 1M (input, output, cached input)
    anthropic_api_key: SecretStr | None = None
    openai_api_key: SecretStr | None = None
    gemini_api_key: SecretStr | None = None  # Secret Manager GEMINI_API_KEY (paid tier), for roles on google:*

    # The Gemini workflow (owner decision 2026-10-07): every NEW engine routes each AI step to a stage
    # of app.ai.gemini, executed on Vertex AI in its own project. Engines frozen before keep their
    # openai:/anthropic:/google: routes; the settings above serve them (and GEMINI_WORKFLOW=false).
    gemini_workflow: bool = True
    # The OpenAI, Anthropic and Gemini-API routes of engines priced before 2026-10-07 (owner, 2026-10-07: "we
    # are only going to use Gemini"). Off: such a route is refused before any spend (ENGINE_RETIRED, nothing
    # charged; the student starts again on Gemini) and counts as not configured; finished results and their
    # downloads are untouched. On: those engines run as priced, with their keys (Codex review, finding 10).
    legacy_providers: bool = False
    # Vertex inference, quota and billing live in their own project. Never GOOGLE_CLOUD_PROJECT: Google
    # libraries (Firebase among them) read that one, and the application's resources stay in gcp_project.
    vertex_project: str | None = None
    vertex_location: str | None = "global"
    intake_model: str = "gemini-3.5-flash-lite"  # classifies and extracts requirements and claims
    intake_thinking: Thinking = "LOW"
    planner_model: str = "gemini-3.8-flash"  # plans, briefs, evidence needs, rule specs
    planner_thinking: Thinking = "HIGH"
    research_model: str = "gemini-3.8-flash"  # grounded search and evidence extraction
    research_thinking: Thinking = "LOW"  # live 2026-10-07: MEDIUM spent 3,000-12,000 thinking tokens a search
    execution_model: str = "gemini-3.8-flash"  # writes: rewrites, drafts, chapters, reports, themes
    execution_thinking: Thinking = "MEDIUM"
    first_audit_model: str = "gemini-3.8-flash"  # independent checks: AI check, integrity, sections, critiques
    first_audit_thinking: Thinking = "MEDIUM"  # live 2026-10-07: HIGH made each section check 35-85 s
    second_check_model: str = "gemini-3.5-flash-lite"  # the AI check's second, independent assessor
    second_check_thinking: Thinking = "MEDIUM"
    premium_audit_model: str = "gemini-3.1-pro-preview"  # the approval review of every deliverable (first round)
    premium_audit_thinking: Thinking = "HIGH"
    fix_model: str = "gemini-3.8-flash"  # targeted repairs of what an audit named
    fix_thinking: Thinking = "MEDIUM"
    final_signoff_model: str = "gemini-3.8-flash"  # re-review after a repair: were the findings resolved?
    final_signoff_thinking: Thinking = "MEDIUM"  # it checks named findings; the premium audit keeps HIGH
    # A stage's fallback stages, used only when its model is unavailable, rate-limited or timing out, and
    # only if they cost no more in any billing dimension. The premium auditor is a preview model on shared
    # capacity: a live run was rate-limited four times in five minutes, so its review goes to the first
    # auditor's model rather than failing the job after its retries. GEMINI_FALLBACKS={} turns this off.
    gemini_fallbacks: dict[str, list[str]] = {"premium_audit": ["first_audit"]}
    paperaid_gemini_models: dict[str, GeminiModel] = CONFIRMED_MODELS
    vertex_prices: dict[str, VertexPrice] = VERIFIED_VERTEX_PRICES
    model_unit_prices: dict[str, float] = {}  # derived from vertex_prices: "vertex:model:unit" → USD per unit
    model_long_prices: dict[str, tuple[int, float, float, float]] = {}  # derived: long-context tier (threshold, in, out, cached)
    vertex_search_enabled: bool = True  # Google Search grounding; false shows the searching services as not set up

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
    # Data Lab (owner decision 2026-10-03): switched on here once its tier prices (DL_SMALL, DL_STANDARD,
    # DL_LARGE) are set; open to testers and admins like the work services while `works_public` is off.
    # Processing limits are measured, not promised: raised only from measured runs.
    datalab_enabled: bool = False
    datalab_max_rows: int = 200_000
    datalab_max_columns: int = 300
    datalab_max_cells: int = 6_000_000
    datalab_max_expanded_bytes: int = 120 * 1024 * 1024  # what an .xlsx may unpack to
    datalab_analyses_per_hour: int = 120  # computed by code, never billed: a fair-use limit
    datalab_report_cap_usd: float = 6.0
    datalab_qual_cap_usd: float = 8.0  # a qualitative analysis's most AI spend
    datalab_qual_max_documents: int = 40
    datalab_qual_max_words: int = 150_000  # all transcripts together
    # "Your work is ready" messages (owner roadmap 2026-10-03): off until the keys are set in Secret Manager.
    app_url: str = "http://localhost:5000"  # links in messages
    sendgrid_api_key: str = ""
    notify_from: str = ""  # a sender address SendGrid has verified
    africastalking_username: str = ""
    africastalking_api_key: str = ""
    sms_sender: str = ""  # an approved sender ID, or empty for the shared one
    # The daily canary (owner roadmap 2026-10-03): a writing check on a fixed paper from a dedicated
    # account, paid from that account's credits. Off until the account is set up.
    # The terms people accept (owner decision 2026-10-04): a new version is asked for again before the
    # next paid step or Data Lab upload. The lawyer's wording replaces the plain one under a new version.
    terms_version: str = "2026-10-07"  # qualitative transcripts disclosed (Codex audit 2026-10-07, finding 8)
    canary_enabled: bool = False
    canary_uid: str = ""
    canary_email: str = ""
    canary_budget_usd: float = 0.5  # a run whose quote allows more AI spend than this is not started
    alert_email: str = ""  # where the canary's alerts go (email needs the SendGrid settings)
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
    # The flood guard in front of the public API, per instance (requests per second, and the burst allowed).
    flood_client_rate: float = 10.0
    flood_client_burst: float = 40.0
    flood_instance_rate: float = 150.0
    flood_instance_burst: float = 300.0
    quotes_per_hour: int = 40
    submits_per_hour: int = 10
    uploads_per_hour: int = 20  # feedback, guides, rebuilt downloads and PDFs, per student (Codex audit 56c4f83 M21)
    max_upload_bytes: int = 20 * 1024 * 1024
    max_words: int = 25_000
    max_pdf_pages: int = 150
    retention_days: int = 30
    quote_ttl_minutes: int = 30
    # A provider outage often lasts minutes: with backoff (20 s doubling, at most 5 min) six attempts wait
    # about ten minutes before a stage fails; completed AI calls replay from the job's cache (live 2026-10-01).
    stage_max_attempts: int = 6
    repair_attempts: int = 2
    research_max_claims: int = 10  # source check: most claims checked in one paper
    research_max_searches: int = 2  # source check: most web searches per claim
    # Proposal projects: research needs planned per step (0 = the plan, then each chapter), scholarly
    # works read per need, and the longest proposal the review service accepts.
    proposal_needs: dict[int, int] = {0: 6, 1: 8, 2: 12, 3: 5, 4: 4}  # 4: the concept paper
    proposal_works_per_need: int = 6
    # Speed and rate limits (plan of 2026-10-08, Codex-reviewed). One shared limit on Gemini calls in flight across
    # every worker, per Vertex project, location and model (a web-search call is its own resource): a call waits
    # for a slot, and a stage that waits too long pauses and is delivered again, never sending more than the
    # limit. The limiter failing pauses work; it is never bypassed.
    capacity_gate: bool = True
    capacity_default: int = 12  # calls in flight at once for a model not listed below
    capacity_limits: dict[str, int] = {"gemini-3.1-pro-preview": 4}
    capacity_search: int = 6  # web-search calls in flight at once, per model
    capacity_wait_sec: float = 30  # how long a call waits for a slot before its stage pauses
    capacity_retry_sec: int = 20  # how long a paused stage waits before it is delivered again
    capacity_max_waits: int = 360  # pauses allowed for one job (about two hours) before it stops, uncharged
    research_parallel: int = 2  # research needs worked on at the same time inside one stage (each call takes a slot)
    research_call_floor_sec: float = 75  # time limit for a search or abstract reading (never below the token-rate rule)
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
    # The least balance (in credits) a student needs to start each service (owner decision 2026-10-01:
    # "below a certain number of credits you cannot do coursework..."). Set with the final prices;
    # 0 or absent: only the job's own price is checked. Keys: COURSEWORK, PROPOSAL, CONCEPT_PAPER,
    # CONCEPT_NOTE, FUNDING_PROPOSAL.
    min_credits: dict[str, float] = {}
    # Reading a student's documents is free (part of the document's price); reads for work that was then
    # never started are capped per student per day, so they cannot run up AI cost (Codex audit 2026-10-01).
    free_reads_per_day: int = 5
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
        from app.ai.orchestration import STEPS, current_engine, model_for_engine
        from app.core.errors import StageError

        try:
            engine = current_engine(self)
            unused = set()
            if not self.frontier_guidance:
                unused.update({"guide", "spec_guide", "p_guide", "p_profile_guide"})
            if self.single_reviewer:
                unused.update({"review_peer", "spec_review_peer", "p_plan_review_peer", "p_review_peer", "p_profile_review_peer"})
            return all(self.provider_configured(model_for_engine(engine, task)) for task, step in STEPS.items()
                       if step.role in ("lead", "writer") and task not in unused)
        except StageError:
            return False

    @property
    def roles_configured(self) -> bool:
        """Every provider a configured work role needs has its key."""
        from app.ai.orchestration import STEPS, WORK_ROLES, current_engine, freeze_vertex, model_for_engine
        from app.core.errors import StageError

        try:
            base = current_engine(self)
            # Availability needs model routes, not content hashes (which require disk reads).
            for tier in set(self.service_tiers.values()) | {"STANDARD"}:
                engine = freeze_vertex(self, base.model_copy(deep=True, update={"roles": dict(self.role_models), "tier": tier}))
                if not all(self.provider_configured(model_for_engine(engine, task)) for task, step in STEPS.items()
                           if step.role in WORK_ROLES and (step.role != "ADJUDICATOR" or self.role_models.get("ADJUDICATOR"))):
                    return False
            return True
        except StageError:
            return False

    @property
    def search_configured(self) -> bool:
        """Whether the web research steps of a job priced now can run: on Vertex they need grounding."""
        from app.ai.gemini import SEARCH_TASKS
        from app.ai.orchestration import current_engine, model_for_engine
        from app.core.errors import StageError

        try:
            engine = current_engine(self)
            return all(self.vertex_search_enabled or not model_for_engine(engine, task).startswith("vertex:") for task in SEARCH_TASKS)
        except StageError:
            return False

    def provider_configured(self, ref: str) -> bool:
        provider, _, model = ref.partition(":")
        if provider == "vertex":
            # ADC is resolved lazily by the worker; the API never fetches credentials for availability.
            # Unverified rates close availability as well as quoting.
            price = self.vertex_prices.get(model)
            price = price.at() if price else None
            return bool(self.vertex_project and self.vertex_location and model in self.paperaid_gemini_models
                        and price and price.status == "VERIFIED" and price.covers()
                        and (not price.location or price.location == self.vertex_location))
        key = {"openai": self.openai_api_key, "anthropic": self.anthropic_api_key, "google": self.gemini_api_key}.get(provider)
        return self.legacy_providers and key is not None and bool(key.get_secret_value().strip())

    @model_validator(mode="after")
    def _vertex_configuration(self) -> "Settings":
        from app.ai.gemini import STAGES

        if any(stage not in STAGES or any(f not in STAGES for f in fallbacks) for stage, fallbacks in self.gemini_fallbacks.items()):
            raise ValueError("GEMINI_FALLBACKS must name Gemini workflow stages")
        token_prices = {k: v for k, v in self.model_prices.items() if not k.startswith("vertex:")}
        unit_prices = {k: v for k, v in self.model_unit_prices.items() if not k.startswith("vertex:")}
        long_prices: dict[str, tuple[int, float, float, float]] = {}
        for model, price in self.vertex_prices.items():
            price = price.at()
            if price.status == "VERIFIED" and (not price.location or price.location == self.vertex_location):
                token_prices["vertex:" + model] = (price.input, price.output, price.cached)
                unit_prices.update({f"vertex:{model}:{unit}": value for unit, value in price.units.items()})
                if price.grounding is not None:
                    # Every query at the rate above the shared free allowance: never assume a job gets free queries.
                    unit_prices.setdefault(f"vertex:{model}:google_search_query", price.grounding.per_query_usd)
                if price.long_context_tokens:
                    long_prices["vertex:" + model] = (price.long_context_tokens, price.long_input, price.long_output, price.long_cached)
        self.model_prices, self.model_unit_prices, self.model_long_prices = token_prices, unit_prices, long_prices
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
