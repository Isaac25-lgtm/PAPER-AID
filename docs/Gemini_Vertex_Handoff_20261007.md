# PaperAid on Gemini (Vertex AI): architecture and operations, 2026-10-07

This is the current state of PaperAid's AI layer. It supersedes the three local phase reports
(`Vertex_Local_Phase_20261006.md`, `Vertex_Pricing_Phase_20261006.md`,
`Vertex_Infrastructure_Phase_20261007.md`), which remain as history.

## 1. Where things run

| | Project | Region / location | Notes |
|---|---|---|---|
| Website (Firebase Hosting), Firebase Auth, App Check | `paperaid-ca172` | — | Firebase is initialised with `projectId=GCP_PROJECT` (`app/core/auth.py`), never inferred |
| Cloud Run `paperaid-api`, `paperaid-worker` | `paperaid-ca172` | `europe-west1` | one image, two services |
| Firestore, Cloud Storage, Cloud Tasks | `paperaid-ca172` | `europe-west1` | every client is built with `GCP_PROJECT` |
| Vertex AI inference, its quota and its billing | `paperaid` | `global` | `VERTEX_PROJECT`, `VERTEX_LOCATION` |

`GOOGLE_CLOUD_PROJECT` is never used for Vertex: Google libraries read it, and setting it to
`paperaid` could move Firebase's token checks to the wrong project.

**Identity.** Only the worker calls models. It authenticates with its attached service account
through Application Default Credentials; there is no key file, no `GOOGLE_APPLICATION_CREDENTIALS`
and no developer credential in the image (the image copies `app/` only).

| Principal | Where | Role | Permissions |
|---|---|---|---|
| `paperaid-worker@paperaid-ca172.iam.gserviceaccount.com` | project `paperaid` | `projects/paperaid/roles/paperaidVertexInference` (custom) | `aiplatform.endpoints.predict`, `serviceusage.services.use` |
| `paperaid-api@paperaid-ca172.iam.gserviceaccount.com` | — | none in `paperaid` | the API prices and queues; it never calls a model |

The custom role is narrower than the predefined pair (`roles/aiplatform.user` +
`roles/serviceusage.serviceUsageConsumer`), which would also allow creating and managing Vertex
resources. `serviceusage.services.use` is needed because the client bills its quota to `paperaid`.

## 2. The AI workflow

PaperAid's pipelines (Paper Check, research proposals, works, Data Lab) decide what happens; the
workflow only decides which model executes each step. Every step in `STEPS` belongs to one stage
(`TASK_STAGES` in `app/ai/gemini.py`):

| Stage | Model | Thinking | Steps |
|---|---|---|---|
| intake | `gemini-3.5-flash-lite` | LOW | reading a brief (`w_read`), finding a paper's checkable claims (`claims`) |
| planner | `gemini-3.8-flash` | HIGH | plans, briefs, evidence needs, results models, formatting and institution specs |
| research | `gemini-3.8-flash` + Google Search | MEDIUM | source check, proposal and works research, evidence extraction |
| execution | `gemini-3.8-flash` | MEDIUM | rewrites, redrafts, chapters, works drafts, Data Lab reports, qualitative coding and themes |
| first audit | `gemini-3.8-flash` | HIGH | AI check, academic review, evidence verification, integrity, section evaluation, readiness, plan critiques |
| second check | `gemini-3.5-flash-lite` | MEDIUM | the AI check's independent second assessor |
| premium audit | `gemini-3.1-pro-preview` | HIGH | the approval review of every deliverable; review of an uploaded proposal; premium-tier section evaluation |
| fix | `gemini-3.8-flash` | MEDIUM | targeted repairs of what an audit named |
| final sign-off | `gemini-3.8-flash` | HIGH | every re-review after a repair |

**Audit → repair → sign-off.** Every approval review runs in PaperAid's bounded loop
(`REVIEW_REPAIRS = 2`). `AIRunner.audit_rounds` numbers the rounds: round 0 is the premium audit; each
later round is the final sign-off, which receives every earlier answer as `previousAudit` and the
`signoff-v1` instructions: confirm each earlier finding is resolved, that the repair broke nothing and
removed nothing required, and that the task is still met, in the same answer format (so PaperAid's
code still gets a verdict for every rule). It does not redo the full audit. A repair touches only
what was named; code checks still win over any model.

**Changes from the proposed baseline, and why.**
- *Second check stage.* The AI check has always used two independent assessors per passage, and
  PaperAid combines their answers. Two calls to the same model would be one view twice, so the
  second runs on Flash-Lite. Cost: about $0.01 per page; quality: genuine independence.
- *Premium auditor.* `gemini-3.5-pro` answers in Vertex but has no published price, so it cannot be
  priced and is not used. `gemini-3.1-pro-preview` is the strongest priced Pro; it stays configurable.
- *Premium-audit fallback.* The preview model runs on shared capacity: in the live run it was
  rate-limited four times in five minutes. A job retries a stage 6 times (about 10 minutes), so under
  load a Pro outage could fail and refund jobs. When Pro is rate-limited, unavailable or times out,
  that review goes to `gemini-3.8-flash` (HIGH) at once, recorded as the premium audit with
  `fallbackAttempt: 1`. `GEMINI_FALLBACKS={}` turns this off.
- *Thinking room.* Gemini counts thinking against the output limit (measured: 111 thinking tokens
  filled a 120-token limit). Each step keeps its visible allowance plus room for its level
  (LOW 6,000, MEDIUM 16,000, HIGH 32,000 tokens; `THINKING_ROOM`), since a live academic review at
  HIGH used 30,721 thinking tokens. Only tokens used are billed; the room raises the spend cap only.

**Configuration** (all optional; defaults above): `INTAKE_MODEL`, `PLANNER_MODEL`, `RESEARCH_MODEL`,
`EXECUTION_MODEL`, `FIRST_AUDIT_MODEL`, `SECOND_CHECK_MODEL`, `PREMIUM_AUDIT_MODEL`, `FIX_MODEL`,
`FINAL_SIGNOFF_MODEL`, the matching `*_THINKING` (MINIMAL, LOW, MEDIUM, HIGH),
`GEMINI_FALLBACKS`, `VERTEX_SEARCH_ENABLED`. A model must be in the verified registry
(`CONFIRMED_MODELS`: capabilities, limits, thinking levels from its model card) and have a published
price (`app/ai/vertex_pricing.py`), or pricing refuses it. Model IDs appear nowhere else.

**Frozen per quote.** `freeze_vertex` resolves the routes, thinking levels, capabilities, the price
record in force, the Vertex project and location, and the versions of the added instructions, into the
quote's engine. A job always runs as priced; changing a setting affects new quotes only.

## 3. Grounding (Google Search)

Live finding (2026-10-07): with a structured JSON answer, Vertex returns the queries it ran but no
source list and no citation segments; the sources are the grounding redirect links the model writes
into its answer. Google issues those links, and one the model invented does not resolve (404).
PaperAid therefore:
1. tells the model to run at most N queries and to give each URL exactly as the search provided it
   (`vertex-search-v1`, added to the step's released prompt);
2. resolves each redirect link to the page it stands for, reading only the `Location` header, and
   rewrites the answer with the real addresses; only resolved pages count as sources the search opened;
3. hands the answer to the existing source rules (`research.opened`, quotations confirmed on the page
   by PaperAid itself, the second model's check). A link that does not resolve is dropped by them.

Google gives no hard cap on queries: extra queries are charged, never a failure. A search Google
declines (a safety stop, or `RECITATION`: it will not repeat a page word for word) finds nothing for
that need or claim, and the step continues (`SEARCH_DECLINED`). Search Suggestions are kept in the
answer metadata but not displayed: Google's terms make displaying them optional below one million
grounded prompts a day. `VERTEX_SEARCH_ENABLED=false` switches grounding off and shows Source Check,
research proposals and works as not set up.

## 4. Pricing

Source: Google's Vertex AI pricing page, Standard tier, global endpoint (checked 2026-10-06/07).

| Model | Input / 1M | Cached input / 1M | Output incl. thinking / 1M | Valid |
|---|---|---|---|---|
| gemini-3.8-flash | $0.75 | $0.075 | $3.75 | to 2026-12-31 (introductory, given as 50% credits back) |
| gemini-3.8-flash | $1.50 | $0.15 | $7.50 | from 2027-01-01 |
| gemini-3.5-flash-lite | $0.30 | $0.03 | $2.50 | from 2026-10-06 |
| gemini-3.1-pro-preview | $2.00 ($4.00 above 200K input) | $0.20 ($0.40) | $12.00 ($18.00) | from 2026-10-06 |
| Google Search grounding | $0.014 per query | | | 5,000 free a month are shared by the whole account, so PaperAid never assumes them |

Thinking is billed once, inside output. Search-provided input is not charged. A Pro request above
200K input tokens is billed entirely at the long-context rates; the estimate picks the tier on the
worst-case token count. A quote freezes one flat record; a job whose frozen period has ended is
refused before any new call and must be quoted again. A call Google may have billed after PaperAid
stopped waiting (a timeout) counts against the job's cap at its estimate; failed requests are not
billed by Google. The $300 Google Cloud credit pays Google's invoice for project `paperaid`; it is not
a rate and appears nowhere in PaperAid's prices.

## 5. Older jobs and the earlier algorithm

Engines priced before this release have no Vertex routes and run exactly as they were priced, on
`openai:`, `anthropic:` and `google:` (Gemini API) with their own prompts and price tables. Their
adapters and the `OPENAI_API_KEY`, `ANTHROPIC_API_KEY` and `GEMINI_API_KEY` secrets therefore stay
until every such job has finished or expired. `GEMINI_WORKFLOW=false` routes new jobs through the
earlier algorithm again (it needs those keys). Nothing in the earlier routing can take over a new
job while the workflow is on: every step of a new engine has a frozen Vertex route.

## 6. Release and rollback

`./release.sh` (Git Bash, repository root, on `main` with a clean backend/web tree):
1. lint, the full backend suite, web unit tests, typecheck and a production build;
2. builds the image from `git archive HEAD` (never the working tree) with `backend/cloudbuild.yaml`
   (LibreOffice and the in-image rendering self-test);
3. deploys the worker, then the API, by digest, adding only `VERTEX_PROJECT=paperaid` and
   `VERTEX_LOCATION=global`; every other setting, secret and identity is kept;
4. prints the new and previous revisions and the rollback commands.

Rollback: `gcloud run services update-traffic SERVICE --project paperaid-ca172 --region europe-west1
--to-revisions=PREVIOUS=100` for the worker and the API. A job quoted on the new release keeps its
Vertex engine and still runs after a rollback only if the older revision understands it; quote
afresh after rolling back.

Live check of the deployed identity (a few cents; synthetic text only):
```bash
gcloud run jobs deploy paperaid-vertex-check --project paperaid-ca172 --region europe-west1 \
  --image IMAGE@DIGEST --service-account paperaid-worker@paperaid-ca172.iam.gserviceaccount.com \
  --set-env-vars VERTEX_PROJECT=paperaid,VERTEX_LOCATION=global \
  --command python --args=-m,app.ai.vertex_check,--allow-paid-calls
gcloud run jobs execute paperaid-vertex-check --project paperaid-ca172 --region europe-west1 --wait
gcloud run jobs delete paperaid-vertex-check --project paperaid-ca172 --region europe-west1 --quiet
```
