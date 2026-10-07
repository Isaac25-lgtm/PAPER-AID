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
| research | `gemini-3.8-flash` + Google Search | LOW | source check, proposal and works research, evidence extraction |
| execution | `gemini-3.8-flash` | MEDIUM | rewrites, redrafts, chapters, works drafts, Data Lab reports, qualitative coding and themes |
| first audit | `gemini-3.8-flash` | MEDIUM | AI check, academic review, evidence verification, integrity, section evaluation, readiness, plan critiques |
| second check | `gemini-3.5-flash-lite` | MEDIUM | the AI check's independent second assessor |
| premium audit | `gemini-3.1-pro-preview` | HIGH | the approval review of every deliverable; review of an uploaded proposal; premium-tier section evaluation |
| fix | `gemini-3.8-flash` | MEDIUM | targeted repairs of what an audit named |
| final sign-off | `gemini-3.8-flash` | MEDIUM | every re-review after a repair |

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

Rollback is a controlled operation (Codex audit 2026-10-07, finding 4):
1. Pause processing (admin console, or `POST /api/admin/processing {"enabled": false}`) and let
   running stages finish.
2. `gcloud run services update-traffic SERVICE --project paperaid-ca172 --region europe-west1
   --to-revisions=PREVIOUS=100` for the worker and the API.
3. Resume processing.

Every quote freezes the fingerprint of every prompt and rule file it runs (`priced_engine`). An older
image reads a Gemini-priced engine without its Vertex routes, but its own prompts differ, so it refuses
the job before any call (ENGINE_CHANGED: failed, not charged) rather than running it on other models.
Jobs priced on `50dd7a7` itself (Paper Check before this fix carried no fingerprint) must not be left
queued if you roll back further than `50dd7a7`: pause first, then cancel them.

Live check of the deployed identity (a few cents; synthetic text only):
```bash
gcloud run jobs deploy paperaid-vertex-check --project paperaid-ca172 --region europe-west1 \
  --image IMAGE@DIGEST --service-account paperaid-worker@paperaid-ca172.iam.gserviceaccount.com \
  --set-env-vars VERTEX_PROJECT=paperaid,VERTEX_LOCATION=global \
  --command python --args=-m,app.ai.vertex_check,--allow-paid-calls
gcloud run jobs execute paperaid-vertex-check --project paperaid-ca172 --region europe-west1 --wait
gcloud run jobs delete paperaid-vertex-check --project paperaid-ca172 --region europe-west1 --quiet
```

## 7. Released and verified (2026-10-07)

| | |
|---|---|
| Commit | `50dd7a7` (the integration is `66f9452`) |
| Image | `europe-west1-docker.pkg.dev/paperaid-ca172/paperaid/backend:release-50dd7a7`, `sha256:c6e405141097bb43cc86090d748b1585938aa2aabb844354a549111856b3b261` |
| Worker | `paperaid-worker-00045-sv2` (was `00044-7rz`), service account `paperaid-worker@…` |
| API | `paperaid-api-00044-66x` (was `00043-f4p`), service account `paperaid-api@…` |
| Settings added | `VERTEX_PROJECT=paperaid`, `VERTEX_LOCATION=global` (both services); nothing else changed |
| IAM added | `projects/paperaid/roles/paperaidVertexInference` → worker service account |

**Tests.** Backend 1,112 passed (lint clean); web unit tests 10 passed, typecheck and production build
pass; browser journeys (main, One Start, proposal, works, Data Lab) pass on the Gemini workflow.

**Live runs on Vertex** (local API and pipelines, real calls, test documents, credits off):

| Service | Result | Time | Cost |
|---|---|---|---|
| Paper Check: AI check + academic review + source check | completed; links resolved to real pages | 63 s | $0.04 |
| Paper Check: light rewrite + formatting | completed; Pro approved first time | 7 min | $0.32 |
| Coursework (1,500 words), One Start | plan and document approved by Pro; 16 evidence citations, 14 sources | 19 min | $0.99 |
| Research proposal, One Start → Chapter One | plan approved; chapter: Pro audit → fix → Flash sign-off → readiness | 28 min | $1.39 |
| Funding proposal (compact), One Start | plan: Pro audit → repair → sign-off; Results Model and document approved by Pro | 26 min | $1.37 |
| Data Lab quantitative report | Pro audit → repair → sign-off; Pro rate-limited 4 times first | 9 min | $0.13 |
| Data Lab qualitative themes | approved by Pro | 49 s | $0.04 |

The first proposal run failed Chapter One on a Google `RECITATION` stop in one search; fixed
(`SEARCH_DECLINED`) and re-run. **Production check** (Cloud Run job, deployed image, worker service
account): all nine stages and one grounded search succeeded, $0.075. The temporary job was deleted.

**Known limitations.** The premium auditor is a preview model on shared capacity (fallback covers it);
Gemini wrote a 1,500-word essay about 10% short (PaperAid flagged it "ready with warnings");
web research is the largest cost of a research step (thinking plus $0.014 a query); whether Google's
50% introductory credit-back applies while the $300 credit pays the bill shows only on the invoice.

## 8. Codex's audit of the integration, fixed (2026-10-07)

| # | Finding | Fix |
|---|---|---|
| 1 | Grounding has no hard query cap, so one call could spend past the job's cap | Spend is reserved for 3 queries per allowed search (`SEARCH_RESERVE_FACTOR`; live calls ran 2 to 3). A call that runs more is charged as run; the job then buys nothing more (`budget_reached`, next call refused). The student is never charged above the quote. |
| 2 | Only timeouts reserved spend | A request that may have been billed although its answer was lost (timeout, connection broken after sending, unreadable answer) records `reservedUsd` = its estimate and `pricingStatus: UNKNOWN_BILLING`; the job's cap counts reservations (`Job.reservedUsd`), kept apart from confirmed cost. Connection refused or an HTTP error is never billed by Google. |
| 3 | Link resolution unbounded and before the cost was saved | The call's usage is recorded first, the raw answer is saved (`…-raw`), then at most 20 links are resolved, 8 at a time, 5 s each, 25 s in total. A retry after a crash resolves the saved answer again and never buys it twice. |
| 4 | A rollback could run Gemini-priced jobs on the old models | Every priced quote carries its content fingerprint; controlled rollback procedure above. |
| 5 | Sign-off history mixed document parts and bypassed the size bound | Earlier answers are kept per document part; a pipeline that passes its own findings (`previousIssues`) gets no second copy; history is at most 1,200 words and keeps a review part within `FINAL_PART_WORDS`. |
| 6 | Links escaped as `\/` in valid JSON were missed | Links are found in the decoded answer. |
| 7 | A resolvable link was treated as returned by this search | A link counts only if a search ran, it resolves, and it was not in the request; `grounding.provenance` says whether the sources came from Google's metadata or from resolved answer links. The quotation checks still decide. |
| 8 | Terms said the AI never sees individual records; transcripts are sent | Terms and privacy summary now say: numbers, only calculated results; transcripts, the passages analysed after listed names and contact details are replaced. Terms version `2026-10-07`: everyone accepts again, and the step they were taking carries on as soon as they do. |

Tests: `backend/tests/test_audit_20261007.py`, one regression per finding.

## 9. Coursework that took 44 minutes and failed, fixed (2026-10-07)

A live coursework draft (an economics question asking for "graphical and numerical illustrations") ran
43 minutes 42 seconds and failed. Seventy-two AI requests: 21 integrity checks, 21 section evaluations,
12 repairs and 3 final reviews. Two causes:
1. **It asked for something PaperAid could not make.** The writer could not draw a graph, and the guard
   against invented statistics emptied the worked example cell by cell. The final reviewer rightly failed
   the draft every round. Now the writer gives a graph as data (`figure`: caption, axes, labelled lines of
   points) and PaperAid's code draws it (Word: matplotlib; the app: an SVG chart); a worked example is a
   table marked `illustrative`. Both are labelled "(illustrative values)" by code, and only their own
   numbers count as allowed in that section. Prompts `w-draft-v2` and `w-repair-v3`; the answer format with
   figures applies only to steps priced on them. The final reviewer reads a figure as its data.
2. **Nested loops.** Each final-review round re-ran the whole section repair loop. Now one repair limit
   (repair_attempts + 1) covers the section checks and the final review together; after a final-review
   repair, the repaired sections get one check and go to the sign-off; the loop stops when the final
   review repeats the same blocking objections; a missing part of the question is repaired in the section
   the reviewer named (or the plan's main one), not in every section mapped to it; integrity and evaluation
   run at the same time; research thinks LOW, checks and the sign-off MEDIUM.

Also: the progress screen shows "Checking each section / Fixing what the checks found / Final check of
the whole document · round N"; a retry of a failed step on the same approved plan reuses that attempt's
checked sources instead of researching again.

**Capacity for many students at once.** Twenty steps run at the same time (queue `paper-jobs`
`maxConcurrentDispatches` 20, worker `--max-instances` 20, one step per instance); more wait in the queue.
A Gemini call throttled (429) or briefly unavailable (503) retries itself within seconds with jitter
(`THROTTLE_RETRY`), before the step's own retry; Google bills neither. The premium audit falls back to
3.8 Flash when the preview Pro model stays busy.

## 10. Every section tested live on Gemini, and what that fixed (2026-10-07)

Owner-authorised live runs on real Gemini (Vertex, `paperaid`/`global`) through PaperAid's real API and
pipelines, with synthetic content only, credits off and throwaway data folders (driver kept outside the
repository). Costs are actual Vertex spend.

| Flow | Result | Time | Cost |
|---|---|---|---|
| Coursework essay (economics, graphs asked for) | Delivered: Figure 1 drawn by code, illustrative table | ~11 min | $0.61 |
| Coursework report, brief bans AI (2,000 words) | Delivered; the "AI-assisted third party" last-page note present | 24 min | $0.53 |
| Funding concept note | Plan and draft approved | ~10 min | $0.44 |
| Funding proposal, standard (18 months) | 13 sections, 5,234 words; Results Model approved; indicator targets left as applicant gaps (FP-027) | 34 min | $1.22 |
| Academic concept note | Plan, then concept paper (Pro review → fix → Flash sign-off) | 14.5 min | $0.80 |
| Research proposal: plan + Chapters 1, 2, 3 | All FULL | 48 min | $2.08 |
| Revise Chapter 1 from a request | Two sections revised | 5 min | $0.30 |
| Data Lab quantitative report | 13 sections, 6 tables, 4 charts | 2 min | $0.14 |
| Data Lab qualitative themes | 3 themes, codebook | 2.4 min | $0.17 |
| Chapter Four from data (the proposal above) | By objective, 6 tables, 6 figures, approved first time | 2 min | $0.13 |
| Paper Check redraft with source check | FULL; redraft, writing report, changes, APA copy | | $0.21 |
| Paper Check "Ask for changes" on the result | FULL (10 passages; planner timed out 3× at the old 180 s first) | 34 min | $0.43 |
| Paper Check light refine | FULL | 2.6 min | $0.17 |
| Paper Check AI check (before it was hidden) | FULL | 0.8 min | $0.05 |
| University template + LaTeX | PARTIAL, correctly: the test guide contradicts itself, so the warnings say what was assumed | 1.6 min | $0.08 |
| Proposal review (uploaded proposal) | FULL; the thin test proposal's missing sections reported | <1 min | $0.11 |
| Institution profile from a guide | Failed twice (see fix 2), then approved first time after the fix | 13 min | $0.24 |

Fixed from these runs (tests in brackets):
1. **A whole-chapter "Ask for changes" stayed open.** A request with no section picked covers every section;
   it is now answered when the sections it concerns are revised, and the note no longer calls the student's
   own request a supervisor's comment (`test_proposal_v2.py`).
2. **An institution profile could never be approved.** Code fills what a guide does not give from the
   standard profile (other levels' page ranges, the concept paper's layout, preliminary pages, words per
   page); the final reviewer rejected those three rounds running and no repair could change them. The
   profile now lists them (`from_standard`) and review prompt `p-profile-review-v2` judges them only where
   the guide states something different. A guide's maximum alone ("no more than four objectives", "must not
   exceed 25 pages") is kept instead of falling back to the standard range; margins the profile cannot hold
   (different per side, in cm) are told to the student in the institution notes; the never-used preliminary
   pages are not shown to the reviewer (`test_profiles.py`). The second live run failed on exactly those
   three; the third was approved first time.
3. **HIGH-thinking calls were cut off at 180 seconds.** Thinking counts against the output limit, and a
   HIGH call thinking to its 32k room at Flash's measured 145–165 tokens a second needs about four minutes;
   the Paper Check planner timed out three times in a row (each possibly billed) before succeeding in 132
   seconds with 20.8k thinking tokens. Each call's timeout now follows its own allowance
   (`vertex.call_timeout`: 30 s + tokens/120 a second, at least `PROVIDER_TIMEOUT_SEC`, at most 290 s so it
   stays inside the stage's hand-over margin) (`test_vertex.py`).
4. **The admin job page** shows each call's step, workflow stage, thinking level, fallback, error and
   reserved amount, so a premium review answered by Flash while Pro was busy is visible.
5. **The AI checker is hidden** (owner decision): `AI_CHECK_ENABLED` off; Paper Check starts at Redraft and
   takes Word files (`test_ai_check_hidden.py`).

Observed, no change needed: Google returned 503 for 3.8 Flash across all jobs for about four minutes
(08:40–08:44 UTC); every job retried and finished. The preview Pro model was busy several times; the premium
audit fell back to 3.8 Flash at HIGH as designed. A dropped connection after sending reserves the call's
estimate (unknown billing) and the stage retries.
Suggested, not built: Data Lab headings use a variable's name until the researcher gives it a label
(for example "knowledge_score by completed"); prompting for labels before a report would read better.


## 11. Codex's review of release 5c33697: eleven findings fixed (2026-10-07)

Each finding was confirmed in the code before it was fixed; every fix has a regression test, and the
tests for findings 1, 3 and 8 were run against the old code and failed there.

| # | Finding | Fix | Where |
|---|---|---|---|
| 1 | The SDK resent timed-out/disconnected requests (up to 4 sends, possibly billed, unrecorded) | `NO_SDK_RETRY`; PaperAid retries only 429/503 (`THROTTLE_ATTEMPTS` 4, 2/4/8 s + jitter) | `vertex.py` |
| 2 | Parallel checks: a reservation released before the cost was saved | released in `finally`, after the record | `orchestration.py` `_call` |
| 3 | Revisions dropped graphs and example labels; compression dropped the label | the revision rebuilds sections as delivered; `_kept` keeps the label | `works/pipeline.py` |
| 4 | Example numbers allowed anywhere in the section, for any work | coursework only; only in the example and sentences about it (`ABOUT_EXAMPLE`) | `works/pipeline.py`, `evidence.strip_unsupported` |
| 5 | Research reused after the question changed | all research inputs and the engine compared (`RESEARCH_INPUTS`) | `works/pipeline.py` |
| 6 | A whole-chapter request closed when any section changed | the sections it names (`feedback.named`) must all change | `proposals/` |
| 7 | "Repeated" objections compared rule ids only | same id, place and wording (`_repeats`) | `works/pipeline.py` |
| 8 | Review parts bounded the document only | the whole request measured (`payload_words`), history room kept | `works/pipeline.py`, `orchestration._history` |
| 9 | No reservation for an answer without usage | the unmetered part of the estimate reserved | `orchestration.py` |
| 10 | Older engines could still call OpenAI/Anthropic | `LEGACY_PROVIDERS` (off): refused before spend, `ENGINE_RETIRED` | `config.py`, `orchestration.py` |
| 11 | The canary asks for the hidden AI check | the check stays open to the canary account only | `jobs/service.py` |

Owner question answered in passing: there is no access-request flow. Anyone can sign up; AI services show
"invited testers" to emails not in `TESTER_EMAILS` (live: three), and nobody is notified. A "Request
access" button with an admin approval would be new work.


## 12. Codex's third review (code at 6eaa1ee): fixed by Codex, completed by Claude (2026-10-07)

| # | Finding | Codex's fix | Claude's check |
|---|---|---|---|
| 1 | Example numbers accepted in factual sentences ("…as shown in the table") | No keyword exemption; prompts `w-draft-v3`, `w-repair-v4` | Corrected: sentences opening as hypotheticals may use them (`HYPOTHETICAL`), otherwise the worked example could not be explained |
| 2 | A stale worker could fail, finish or overwrite its replacement | `lease_owner` on every heartbeat, update, completion, failure and publication; attempt-scoped artifacts | Corrected: the results page (`workspace._internal_path`) and research reuse read the attempt's files |
| 3 | Small counts leaked through "Records used", notes and subtraction | disclosure-v3 across report, workbook, notes, reviewer inputs; fail-closed analyses | Correct; owner decision on fail-closed noted in decisions.md |
| 4 | Final-review requests could exceed the bound | whole-request measure; hard refusal in the runner (`REVIEW_REQUEST_TOO_LARGE`) | Corrected: one manifest entry per section (it grew with each split, so splitting could never fit); proportional history room |
| 5 | s1/s2 and 1.1/1.2 read as the same place | locations keep identifiers | Correct |
| 6 | A chapter-wide instruction closed after one section changed | every targeted section must change | Correct (a request naming no section now needs every section revised; the student can mark it done) |
| 7 | Source reading and throttle retries had no total deadline | deadlines | Corrected: 10 s per network step within 30 s total (3 s per step was too short) |
| 8 | Old preview responses replaced the selected version | stale responses ignored | Correct; covered by the browser journeys |
| 9 | A graph could not be removed on request | explicit removal; references to a missing figure flagged | Corrected: "the figure" meaning a number is not flagged |
| 10 | Large CSV exports lacked formula protection | protected in chunks | Correct |
| 11 | Legend limits could still read the same | precision up to 12 places; one value for constant data | Correct |

Also classified the new job fields (`lease_owner`, `artifact_paths`) for support views. Tests: one regression per
finding in `tests/test_codex_20261007b.py` (the results-page test fails without Claude's path fix); tests that read
the old artifact paths now use `tests.conftest.internal`; final-review tests now bound the whole request at 900
words (about 460 words of each request are repeated context, so their former 120-400 limits could not fit).
Deployment: the worker is deployed before the API (release.sh); a job claimed by the previous revision has no owner
token and is taken over normally once its lease expires.
