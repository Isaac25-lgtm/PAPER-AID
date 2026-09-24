# PaperAid

Students upload a paper, choose a service and see a server-calculated price. PaperAid processes the job in the background and returns finished Word files.

**Beta services:**
- **AI Check** — writing-pattern report;
- **Check + Refine** — refines flagged passages with citations and numbers locked, then runs an independent accuracy audit;
- **Academic Formatting** — APA 7 or Harvard, with wording verified unchanged.

## Run it on this computer

Double-click **`start-paperaid.bat`**. The first run installs everything, which takes a few minutes. Two windows open, one for the backend and one for the website, and your browser opens **http://localhost:5000**. Close both windows to stop PaperAid.

You need Python 3.12+ and Node.js 20+.

Manual equivalent, in two terminals:

```bash
cd backend && python -m venv .venv && .venv/Scripts/pip install -e ".[dev]" && .venv/Scripts/python -m uvicorn app.main:app --port 8000
cd web && npm install && npm run dev
```

### Trying it out

- **Sign in:** until the Firebase project is connected, the sign-in page offers a clearly labelled local test sign-in (this computer only): any email with an 8+ character password. Emails listed in `ADMIN_EMAILS` in `backend/.env` get the admin pages. Google sign-in appears once Firebase is connected.
- **Upload a paper:** use your own `.docx`, or one of the synthetic papers in `backend/tests/fixtures/generated/`. `dissertation_long.docx` (a 16,000-word dissertation) and `citation_fields.docx` (Zotero-style citations) are good tests.
- **Download results:** you get the refined and/or formatted Word file, a writing report and a change report.
- **Admin console** (`/admin`): every job with its timeline, costs and failures, plus retry, cancel and a pause switch for all processing.
- **Your data:** local jobs and files live in `backend/.data/`. Delete that folder to start fresh.

### AI providers

PaperAid has no stand-in AI. Until both keys are in `backend/.env`, AI Check, Check + Refine and University templates show as **Not set up** and cannot be quoted or run; APA/Harvard formatting, which uses no AI, still works.

```
OPENAI_API_KEY=sk-...        # GPT-6 Sol: analyses, plans, reviews
ANTHROPIC_API_KEY=sk-ant-... # Claude Opus 5.5: critiques, rewrites, fixes
```

Both keys are needed: every service runs the fixed lead/writer loop described in `docs/decisions.md` ("The permanent algorithm"). University templates use the same loop over the formatting rules found in the uploaded guide.

Then restart the backend. Set a monthly spending limit in each provider's console first.

## Tests

```bash
cd backend && .venv/Scripts/python -m pytest -q           # 166 tests: file safety, document integrity, API, races, AI path
cd backend && .venv/Scripts/python -m ruff check app tests
cd web && npm test                                         # frontend unit tests
cd web && npm run build                                    # typecheck + production build
cd backend && .venv/Scripts/python -m tests.serve_e2e      # browser-test backend: test stand-ins for the AI, own data folder
cd web && node scripts/e2e.mjs out                         # full browser journey (web on :5000 + the browser-test backend)
cd web && node scripts/screenshots.mjs out                 # every page at phone and desktop widths
```

## How it fits together

```
web/                 React + TypeScript + Vite (port 5000; /api proxied to :8000)
  src/lib/api-source.ts     the one data layer: every screen talks to the API through it
  src/features/             marketing, auth, upload, jobs, results, account, admin
backend/app/
  api/routes.py             thin HTTP layer
  jobs/service.py           business rules: drafts, quotes bound to the exact file, submit, cancel, delete, admin
  jobs/state.py             the job state machine (the only place statuses change)
  jobs/pipeline.py          the worker: one stage per queue task, leases, checkpoints, retries
  documents/                upload validation, DOCX/PDF reading, locked segments, selective patching
  analysis/signals.py       writing-pattern signals and the versioned AI-likeness band
  ai/                       provider adapters (Anthropic, OpenAI), prompts, costs, orchestration
  formatting/               FormattingSpec presets and the deterministic formatter
  reports/                  Word writing and change reports
  integrations/             local vs Firestore / Cloud Storage / Cloud Tasks implementations
backend/tests/fixtures/     generator for 28 synthetic test documents (including hostile ones)
docs/decisions.md           owner decisions that refine the master specification
docs/deployment.md          step-by-step Google Cloud + Firebase production setup
```

Production runs the same code on Firebase Hosting, two Cloud Run services (a public API and an internal worker), Firestore, Cloud Storage and Cloud Tasks. See `docs/deployment.md`.
