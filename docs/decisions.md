# Decisions

Short, dated records of owner decisions that refine the master specification. Where one of these differs from the spec, it wins.

## 2026-09-23 — Positioning: "paper-ready"
Lead with clarity, correct formatting and a reviewable Word file. The AI Check is a self-check. Drop the mockup's "68% → 12%" hero and its "originality" framing. The terms of service require the uploaded work to be the student's own.

## 2026-09-23 — AI score display
Show passage-level findings plus an estimated band (Low / Moderate / High) with a confidence level. Don't show a numeric percentage until the score passes a separate validation gate.

## 2026-09-23 — Partial refinement results
Paragraphs that still fail audit after bounded repair keep their original text. If the job otherwise succeeds, it ends COMPLETED with `outcome: PARTIAL`, and the warnings are shown prominently. If a large share of the targeted paragraphs fails, the job fails.

## 2026-09-23 — Beta scope
AI Check, Check + Refine and Academic Formatting are enabled. University Template Formatting, Deep Redraft and LaTeX appear as "coming soon" and can't be selected.

## 2026-09-23 — Input matrix (beta)
DOCX is accepted by every service. A text-based PDF is accepted for AI Check only. Scanned PDFs and macro-enabled or encrypted files are rejected.

## 2026-09-23 — Payments
Superseded on 2026-09-24 by "Prepaid credits". (Originally: payments off and jobs recorded BETA_BYPASS.)

## 2026-09-23 — Region and source control
Google Cloud region is `europe-west1`, because Cloud Tasks isn't offered in `africa-south1`. The code stays local for now and will be committed later.

## 2026-09-24 — Uploads go through the API
Browsers upload to `POST /api/jobs/{id}/files/{source|guideline}` rather than directly to Cloud Storage. The server validates every file before storing it, and Firestore and Storage rules can then deny all client access. Uploads are capped at 20 MB, well within Cloud Run's request limit.

## 2026-09-24 — Local mode needs no accounts
Locally, the backend accepts a developer sign-in header, stores data in `backend/.data/`, and runs the queue as a bounded thread pool. Production refuses to start with any of these local settings. (The mock AI provider that used to live here was removed on 2026-09-24; see "No placeholders".)

## 2026-09-24 — Output format
Outputs are a clean Word file plus a separate change report. A tracked-changes Word file stays an experiment until it is proven on real documents.

## 2026-09-24 — The permanent algorithm (owner decision; replaces "Default models")
Two fixed roles, set by `LEAD_MODEL` (GPT-6 Sol, `openai:gpt-6-sol`) and `WRITER_MODEL` (Claude Opus 5.5, `anthropic:claude-opus-5-5`). Every paid AI service runs the same loop:
1. **Lead analyses** the paper and marks the passages it believes read as AI-generated.
2. **Lead drafts** a plan: for each passage, rewrite or leave, what to change, and what must be preserved.
3. **Writer critiques** the plan, passage by passage.
4. **Lead finalises** the plan, taking the critique into account. A passage missing from the final plan keeps its draft instruction.
5. **Writer rewrites** only the passages the final plan says to rewrite, following each agreed instruction.
6. **Lead reviews** each revision once, against the original and its instruction.
7. **Writer fixes** what the lead flags, then the lead reviews again. There are at most 2 fix rounds. A passage that still fails keeps its original wording.

Deterministic checks run on every rewrite regardless of the models: protected citations, quotes and links appear exactly once, numbers are unchanged, and no citation is added. AI Check is step 1 only. APA/Harvard presets are pure code.

**University templates follow the same loop, applied to formatting rules.** The lead drafts rules from the uploaded guide, quoting the sentence each rule came from. The writer critiques the rules and the lead finalises them. PaperAid's formatter applies them, and it cannot change wording (the body-text fingerprint is verified). The lead reviews the applied rules against the guide, the writer fixes them, and the result is re-applied, for at most 2 rounds. Rules still disputed at the end become "Check this rule yourself" warnings, and the job completes as PARTIAL. Contradictions in the guide are always reported.

Without both API keys the AI services are unavailable; nothing stands in for the models.

## 2026-09-24 — Fixes from the external review (Codex)
- A draft is created on the first upload, never when the page opens.
- Every upload is stored as its own immutable file. Attaching a file and submitting a job are checked atomically, so neither can overwrite the other.
- Production downloads return a signed link that the browser opens directly.
- Production requires an explicit `SERVICE_ROLE`, and worker endpoints verify the Cloud Tasks identity token.
- Model usage is recorded before parsing. Responses are cached per request, so retries don't pay twice. A response cut off by the output limit splits its batch instead of retrying the same request.
- Maintenance jobs page through all jobs, not just the newest 500.
- Live job status survives temporary errors; only a 404 means "not found".

## 2026-09-24 — Second review round (Codex)
- Upload objects are unique per attempt (`source-<hash>-<random>`), not per content. A replaced object can never become current again, so cleanup only ever deletes files no job points at.
- Model answers are cached only after passing schema validation, and an unusable cached answer is ignored. A retry never replays a bad response.
- The browser journey fails on any error response the current step doesn't expect, not only on failed steps.
- Tests for the submit/upload races inject the competing change inside the transaction. Each one was confirmed to fail with its fix removed.

## 2026-09-24 — Third review round (Codex): the algorithm is enforced, not assumed
- The writer critiques the whole draft plan, "leave" decisions included, and the final plan can only cover passages the writer saw.
- A planned passage the writer never returned is kept original, listed in the changes, and makes the job PARTIAL.
- If GPT-6 Sol could not assess every passage, the job is PARTIAL, a warning says how many it covered, and the method says so.
- Guides are limited to 15,000 words at upload, so every model step sees the whole guide.
- The rules gained paper size (A4 or Letter) and an "unsupported" list. Any guide rule the formatter cannot apply becomes a "Not applied automatically" warning and the job is PARTIAL. Evidence quotes must appear in the guide or the rule is flagged. Contradictions found by the deterministic reader are kept even if the final answer omits them.
- OpenAI refusal content ends the step as a refusal instead of being retried. GPT-6 Sol is priced at its published standard rate ($2 / $10 / $0.20 per million tokens).
- Every paid call renews the stage lease. After 20 minutes a stage hands the rest to a new delivery, which replays finished calls from the response cache, so no delivery outlives the lease or the 30-minute task deadline.
- A quote is saved only if the files it priced are still the job's files. Removing a guide on the page removes it on the server and clears the quote.

## 2026-09-24 — No placeholders (owner decision)
The product never simulates work it cannot do. The mock AI provider and its rule engine are removed from the app; without both API keys, AI Check, Check + Refine and University templates are shown as "Not set up" and cannot be quoted or run, and a job that somehow runs without keys fails with "AI not configured". The fake "Continue with Google" button is gone: local mode shows a labelled local test sign-in, and Google sign-in appears only once Firebase is connected. Test stand-ins for the models live only in `backend/tests/` (`fake_models.py`, `fake_writer.py`); the browser test runs the app through `tests/serve_e2e.py` with its own data folder. Still to replace: the fixed price table and job budget settings, which the prepaid-credit model (price = actual AI cost × 2) replaces next.

## 2026-09-24 — Prepaid credits (owner decision; supersedes the fixed price table, BETA_BYPASS and public "from" prices)
- **Credits, not tokens.** Students hold a UGX balance (dollar equivalent shown). Mobile-money top-ups come with the payment aggregator, from UGX 5,000; until then an admin adds credits (clearly marked as test credits in local mode). Credits never expire and can't be cashed out.
- **Price = actual AI cost × 2**, converted at 4,000 UGX per USD (market ~3,907 on 2026-09-23, rounded up; review monthly). Every amount rounds up to the next UGX 100.
- **A quote is a ceiling**: the AI work projected call by call with the same estimate the budget guard uses, plus a 20% margin. Accepting holds the ceiling; completion charges the actual cost × 2 (never more) and returns the rest. The job's provider-spend cap is the quote's AI part ÷ rate ÷ 2, so the margin holds even in the worst case.
- **Refinement needs a paid AI estimate first**: GPT-6 Sol's analysis and draft plan, the exact first calls of the job, which then replays them from the response cache. The student sees the estimate's maximum and starts it with a click; it is charged at actual cost × 2 and counts toward the job. It is kept if the student doesn't go ahead, and not charged if it fails. AI Check and University templates are priced from length (paper, guide) with no scan. APA/Harvard formatting uses no AI: UGX 100 per 300 words (about a page), minimum UGX 2,000.
- **No estimate or quote without credits.**
- **Failures:** a failed job returns everything, the estimate included. A partial refinement is charged in proportion to the planned passages actually delivered. Cancelling before the job starts returns the hold. An admin cancel or retry is handled the same way (a retry needs a new hold).
- **Integrity:** a job and its owner's wallet change in one transaction (Firestore transaction / one local lock), and the job's billing record makes every hold, charge and refund happen once.

## 2026-09-25 — Live on Firebase (testing mode)
PaperAid is deployed to project `paperaid-ca172` (https://paperaid-ca172.web.app): Firebase Hosting and Auth (email with verification, and Google), App Check with reCAPTCHA Enterprise, Cloud Run `paperaid-api` and `paperaid-worker` in europe-west1, Firestore, the `paperaid-ca172-papers` bucket, the `paper-jobs` queue and the reconcile/cleanup schedules. Credits are off (`CREDITS_ENABLED=false`: nothing charged). The AI keys are not set yet, so the AI services show "Not set up"; missing keys no longer stop production from starting, since the services are simply unavailable. APA/Harvard formatting works end to end (verified with a throwaway account, then deleted).

