# PaperAid — working rules for coding agents

The authoritative product spec is `PaperAid_Master_Product_Architecture_and_Implementation_Specification.md`. Most of its per-requirement "Implementation / Guardrails / Acceptance" paragraphs are repeated boilerplate. Read the section intros, the "Required outcomes" lists and Appendices A–K instead. Owner decisions that refine the spec are in `docs/decisions.md`. They win over the spec where the two differ.

## Product in one line
Students upload a paper, choose a service, see a server-calculated quote, and later download a finished result. PaperAid is job-based, not a chatbot. Positioning: "paper-ready" (clarity, correct formatting, reviewable output). Never market it as beating AI detectors.

## Fixed architecture
- React + TypeScript + Vite (`web/`, dev server on **port 5000**), hosted on Firebase Hosting.
- Firebase Auth, Firestore (metadata only), Storage (files), App Check.
- One Python FastAPI backend (`backend/`), deployed to Cloud Run as two services from one image: a public `api` and an internal `worker`. Background work runs through Cloud Tasks, one pipeline stage per task.
- Region `europe-west1`. Secrets live in Secret Manager only. Model SDKs are called only from the backend.
- Never add: Redis, Postgres, Kubernetes, Kafka/RabbitMQ, microservices, LangChain/LangGraph, Redux.

## Code rules
- Simple code stays simple. No manager/factory/repository layers with one implementation. Interfaces exist only where there are real alternatives: `JobStore`/`FileStore`/`TaskQueue` (local vs Google Cloud) and `Provider` (Anthropic, OpenAI).
- One source of truth for each business rule: pricing (`app/pricing`), state transitions (`app/jobs/state.py`), authorization (`app/core/auth.py`, `app/jobs/service.py`) and cost ceilings (`app/ai/costs.py`) live in the backend. The browser only displays server results.
- No `any` and no blanket `except`/`catch`. Catch an error only where you classify it, recover from it, or translate it at a boundary.
- Never log paper text, prompts containing paper text, secrets or signed URLs.
- Hide unfinished services through config. Never ship a control that only partly works.
- No placeholders in the product: no stand-in AI, fake results, invented prices or fake sign-in. What can't really work yet is shown as unavailable. Test stand-ins live only in `backend/tests/`.
- The roadmap for the intelligence layer is `PaperAid_Revised_AI_Algorithm_Claude_Context_and_Research_Architecture.md`, as amended by "Revised AI algorithm adopted" in `docs/decisions.md` (the amendments win).
- New runs use four models (owner decision 2026-09-29, superseding the original two-model routing): Luna and Sonnet independently assess every eligible passage; Luna drafts plans and performs routine work; Sonnet critiques, writes and repairs; Opus gives guidance and Sol finalises plans; both Sol and Opus must approve delivered rewritten wording. Repairs are bounded and reviewed again. Frozen older jobs keep their quoted roles. Routing is shared by execution and pricing in `app/ai/orchestration.py`.
- Code measures, models judge: writing signals are versioned rules in `app/analysis/rules.py` (signals-v2); both checkers confirm or reject them in context. Omission is not LOW. Incomplete coverage has no overall percentage; a low-against-high disagreement is shown as uncertainty and lowers confidence; thresholds remain uncalibrated. Approved text is delivered exactly as approved. Nothing is rewritten only because a threshold was crossed. Citation checks (`app/analysis/paper_checks.py`) are separate from AI-likeness. Model inputs stay deterministic so paid estimate answers replay.
- Released prompts never change (`app/ai/prompts/released.json`, enforced by a test): add the next version and point `STEPS` at it. Each job runs with the engine it was priced with.
- Keep the app runnable after every change: `cd web && npm run dev` must keep working.

## Domain vocabulary
- Job `status`: DRAFT → QUOTED → (AWAITING_PAYMENT) → QUEUED → PROCESSING → COMPLETED | FAILED | CANCELLED.
- `stage`, used only while PROCESSING: EXTRACTING, ANALYSING, RESEARCHING (source check, proposal research), PLANNING, REFINING, REDRAFTING, DRAFTING (proposal chapters), AUDITING, FORMATTING, CONVERTING (LaTeX), EXPORTING.
- `paymentStatus` is separate: NOT_REQUIRED, PENDING (credits held), PAID, FAILED, REFUNDED.
- Students see **tokens** (owner decision 2026-09-28): 1 token = `ugx_per_token` (UGX 1,000), shown to one decimal; UGX appears only where tokens are bought. The ledger stays in exact UGX. Prices are fixed per service and page band (`pricing_mode="fixed"`, `fixed_tokens`, version `fixed-v1`); the quote's `budget_usd` caps what the job may spend, and settlement charges each line by what was delivered, never more than quoted. `pricing_mode="cost"` (actual AI spend × `price_multiplier`) remains for tests. Rules: `app/pricing/` (`quote.py` formulas, `credits.py` ledger and `tokens()` wording, `billing.py` hold/settle/refund). Balances only move inside `update_job_and_wallet` (or, for proposal steps, `update_job_wallet_and_project`) transactions.
- Student-facing text says what PaperAid does, never how (owner decision 2026-09-28): no model roles, advisers, second AIs, algorithms, or the institution's manual and section numbers. Those stay in code, prompts, the rulebook and admin views.
- A COMPLETED job with `outcome: "PARTIAL"` must show its warnings. It is never presented as a clean success.
- Research proposals (`app/proposals/`, owner decision 2026-09-28): a persistent **project** (plan, chapter versions, evidence library) whose paid steps are ordinary jobs linked by `projectId`. The rulebook is data (`app/proposals/rulebooks/ucu-2018-v1.json`, from the UCU manual). Approved decisions have ids and hashes (`decisions.py`); a changed decision marks the sections built on it for review. Writers cite only by evidence token; code renders APA 6/7 and removes any citation or figure it cannot trace (`evidence.py`). Sample sizes come from `sampling.py` and the student's own figures, never a model. Readiness is a checklist (PASS / NEEDS_REVIEW / MISSING / NOT_APPLICABLE / BLOCKED, each CODE / AI / AUTHOR), never a mark.
- Students get writing-pattern feedback only (owner decision 2026-09-30, after a real-model pilot scored 10 human and 10 AI-written papers alike): passages marked as generic, formulaic or repetitive with reasons and suggestions, and nothing that claims to detect AI or judge authorship. The AI-likeness percentage and band are still computed (word-weighted, rounded down into their band) and kept for admins and calibration; `SHOW_AI_SCORE` shows them again only once a validated detector exists.
- One screen from upload to final draft (owner decision 2026-09-29): uploading opens the paper on its job page with only the next step beside it (Check for AI, Redraft or Format); options appear only for the step chosen; results, Redraft, Ask for changes (the student's own words reach the writer), Check my sources and Format continue from the same paper (`POST /jobs/{id}/continue`). Chapters and the concept paper take Ask for changes too.
- Three sections (owner decision 2026-09-29): Paper Check (check → redraft light/standard/deep → review changes → finish), Research Proposals, Academic Formatting. Source check, university templates and LaTeX are steps or finishing choices inside them, never jobs of their own (`SECTIONS` in `web/src/lib/services.ts`); older `?service=` links open their section.
- Billing guards (owner decision 2026-09-29): an AI Check that cannot produce a complete result is not charged (`delivery["AI_CHECK"] = 0`); a paper with nothing scorable is refused before pricing (`NOT_SCORABLE`); unapproved university rules are skipped and that line refunded; with `PARTIAL_CHAPTERS` on (off by default, owner decision 2026-09-30) a new chapter delivers only approved sections, charged by their share, and "Finish chapter" (API step `COMPLETE_n`, stored as the chapter step with `finish=True` so older releases can read it) writes the rest, capped at what the chapter has not yet cost (`ChapterDocument.full_price`/`paid`). A proposal step runs and publishes only on the guide and structure it was priced on.

## Commands
- Everything: `start-paperaid.bat`. Backend on :8000, web on http://localhost:5000.
- Backend tests: `cd backend && .venv/Scripts/python -m pytest -q`; lint: `.venv/Scripts/python -m ruff check app tests`.
- Web: `cd web && npm test` (unit tests), `npm run build` (typecheck + build); `node scripts/e2e.mjs out` (and `node scripts/e2e-proposal.mjs out [proposal.docx]`) runs the browser journey against web on :5000 and the browser-test backend (`cd backend && .venv/Scripts/python -m tests.serve_e2e`).
- Test documents: `backend/tests/fixtures/generate.py` regenerates the 28 fixtures; `manifest.json` records what each must do.
- Read-only tools: `backend/inspect_ai_score.py JOB_ID` (one job's scoring), `backend/cost_report.py [--local DIR] --since DATE` (AI spend against price, failed and abandoned work included). `backend/calibrate.py FOLDER --budget-usd N` makes paid calls: it compares score formulas on labelled papers (a development half chooses, a test half reports).
- Load test: `cd backend && .venv/Scripts/python -m tests.load_test --students 40` against a dev-auth backend (no AI is called).
- On Windows, give pytest a short `--basetemp` (for example `C:/Users/USER/AppData/Local/Temp/pt`): long temp paths pass the 260-character limit.
