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
- The AI flow is fixed (see "The permanent algorithm" in `docs/decisions.md`): the lead model (GPT-6 Sol) analyses, plans, finalises and reviews; the writer (Claude Opus 5.5) critiques, rewrites and fixes; there are at most 2 fix rounds. University templates run the same loop over formatting rules. The step-to-role map is `STEPS` in `app/ai/orchestration.py`. Don't add a step or swap roles without an owner decision.
- Keep the app runnable after every change: `cd web && npm run dev` must keep working.

## Domain vocabulary
- Job `status`: DRAFT → QUOTED → (AWAITING_PAYMENT) → QUEUED → PROCESSING → COMPLETED | FAILED | CANCELLED.
- `stage`, used only while PROCESSING: EXTRACTING, ANALYSING, PLANNING, REFINING, REDRAFTING, FORMATTING, AUDITING, EXPORTING.
- `paymentStatus` is separate: NOT_REQUIRED, BETA_BYPASS, PENDING, PAID, FAILED, REFUNDED.
- A COMPLETED job with `outcome: "PARTIAL"` must show its warnings. It is never presented as a clean success.
- The AI score is labelled "Estimated AI-likeness" and shown as a band (Low/Moderate/High) with a confidence level. No percentage is shown until the score passes validation.

## Commands
- Everything: `start-paperaid.bat`. Backend on :8000, web on http://localhost:5000.
- Backend tests: `cd backend && .venv/Scripts/python -m pytest -q`; lint: `.venv/Scripts/python -m ruff check app tests`.
- Web: `cd web && npm test` (unit tests), `npm run build` (typecheck + build); `node scripts/e2e.mjs out` runs the browser journey against web on :5000 and the browser-test backend (`cd backend && .venv/Scripts/python -m tests.serve_e2e`).
- Test documents: `backend/tests/fixtures/generate.py` regenerates the 28 fixtures; `manifest.json` records what each must do.
