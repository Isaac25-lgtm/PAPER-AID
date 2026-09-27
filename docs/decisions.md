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
The product never simulates work it cannot do. The mock AI provider and its rule engine are removed from the app; without both API keys, AI Check, Check + Refine and University templates are shown as "Not set up" and cannot be quoted or run, and a job that somehow runs without keys fails with "AI not configured". The fake "Continue with Google" button is gone: local mode shows a labelled local test sign-in, and Google sign-in appears only once Firebase is connected. Test stand-ins for the models live only in `backend/tests/` (`fake_models.py`, `fake_writer.py`); the browser test runs the app through `tests/serve_e2e.py` with its own data folder. The fixed price table and job budget settings it mentioned were replaced by prepaid credits (next entry).

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

## 2026-09-27 — Revised AI algorithm adopted (owner decision); amendments marked by status
Adopting the document as the roadmap is the owner's decision. Each amendment below is marked: **[owner]** restates an owner decision; **[proposed]** is a recommendation from Claude and Codex that the owner has not yet approved.

`PaperAid_Revised_AI_Algorithm_Claude_Context_and_Research_Architecture.md` is the roadmap for the intelligence layer. It extends "The permanent algorithm" rather than replacing it: code for mechanics, GPT-6 Sol for judgment, planning and QA, Claude for critique, writing and repair; one master plan; targeted paragraph edits; code rechecks after every write; bounded repair with re-review; checkpoints after each paid stage. Amendments that override the document where they differ:
- **[owner, 2026-09-24] No placeholders.** Missing information becomes a question to the student or an explicitly incomplete result, never text inside a delivered document. Writer output may never contain notes, flags or placeholders; the planner may not ask for them (enforced in `protect.check_rewrite` and the prompts).
- **[owner, 2026-09-23] Bands, not percentages.** Estimated AI-likeness stays Low/Moderate/High with a confidence level until validated on a labelled corpus.
- **[owner, 2026-09-27] The student authorises the scope.** Refinement preserves claims and meaning; substantive rewriting only in Deep Redraft, explicitly chosen. Unsupported claims in an uploaded paper become findings, not silent edits.
- **[owner, 2026-09-27] Partial, not failed.** Verified rewrites are always delivered; unverified passages keep the student's wording and the job is PARTIAL. This departs from the owner's 2026-09-23 rule that a job fails when a large share of passages fails; it was made after a live job discarded 4 good rewrites because 3 others failed.
- **[proposed] Research is claim-level.** Each important claim records the supporting passage, where it was read (full text, abstract or snippet), population/place/period, retrieval date and support level; a second model checks support. Search costs enter estimates, holds and billing; searches exclude private names and unpublished findings.
- **[proposed; the per-run freeze is implemented] Status, stage, checkpoint stay separate**, and each run freezes its prompts, models, rules and prices.
- **[proposed] Order:** finish billing/privacy fixes → per-run configuration freeze → signals-v2 and writing-style controls → proposal review with an approved rulebook → live research with evidence → sourced drafting → Deep Redraft and LaTeX.

## 2026-09-27 — Money lifecycle rules (from the Codex audit)
Engineering rules that implement the audit fixes the owner asked for; they matter once credits are on. Product policy **[proposed]**: an estimate fee counts toward any later quote on the same job, even for a different selection.
- **Estimate fees belong to the job.** Every estimate charged on a job stays on its billing record (`fee_paid`) and counts toward whichever quote follows, including a quote for a different selection; a failed job refunds all of them. A finished estimate is repriced from its saved result when its quote expires: no new scan and no new fee.
- **Each run is frozen when it is priced.** The estimate and the quote record the engine (both models and every step's prompt version); the job runs with its quote's engine, so a deploy between estimate and submit can't re-bill the estimate's calls. Released prompt files never change (`app/ai/prompts/released.json`, enforced by a test): a prompt changes by adding its next version.
- **Retries follow the current credit mode.** An admin retry holds credits only while credits are on; a job accepted in testing mode is never charged by a retry.
- **Deletion claims the job first.** Deleting a job (or an account) marks it `deleting` in a transaction that refuses while work runs or credits are held; nothing new can start on a claimed job.
- **Manual grants are idempotent.** Each grant carries an operation id; repeating it adds nothing. The entry records who made it.
- **Local mode is crash-safe too.** A paired job-and-wallet change is written to a journal first and replayed if interrupted.
- **Also recorded (owner decisions, 2026-09-25):** University templates are available (to invited testers while testing); model names are not shown to students (the privacy page still names OpenAI and Anthropic as processors); in testing mode (`CREDITS_ENABLED=false`) prices are shown but nothing is held or charged, and only `TESTER_EMAILS` and admins may use the AI services.

## 2026-09-27 — Build plan and prices (owner decision)
- **Order:** phase 3 (writing-signal scan v2, paper-quality checks, evidence bundle for Sol, post-rewrite scan in Sol's final review, writing styles) → phase 4 (live research for every AI service, claim-level evidence) → phase 7 (Deep Redraft and LaTeX). Proposal review (phase 5) and sourced drafting (phase 6) wait for the owner's proposal guideline. Each phase goes live to invited testers only after tests and real-model runs.
- **Writing styles:** Preserve my voice (default), Standard academic, Concise academic, Technical/scientific. The style is part of the priced selection. No style permits new facts, new technical detail or stronger claims.
- **Deep Redraft** is a separate job the student chooses; refinement never escalates into it (it may recommend it in the report). Priced like every AI service: actual AI cost × 2, sized by a paid estimate first.
- **LaTeX conversion** uses no AI: UGX 150 per 300 words, minimum UGX 3,000.
- **Partial, not failed** (confirmed): verified rewrites are delivered, the rest keep the student's wording, the job is PARTIAL with warnings. Supersedes the failure threshold in "Partial refinement results" (2026-09-23).
- **Signals guide review; they are not the target.** Meaning, citation integrity and useful edits come first. Sol decides whether a measured signal matters in context; nothing is rewritten only because a threshold was crossed. Section type changes interpretation, never exempts a section. Paper-quality findings (citations vs references) are reported separately from AI-likeness, with three outcomes: confirmed mismatch, possible mismatch, could not interpret.
- **Calibration:** thresholds are provisional until checked on a held-out set of genuinely human writing (the owner will gather pre-2022 papers with permission, including non-native English and technical work).

## 2026-09-27 — Source check (phase 4, built under the owner's approval of the build plan)
- **What it is:** an option on AI Check and Check + Refine ("Source check"). The lead picks the paper's important public factual claims (never the paper's own methods or results), searches the live web for each, and quotes the passage that bears on it with the source's date, scope (population, place, period) and how much was read (full text, abstract or snippet). The writer then checks each quoted passage against its claim without searching; if the two disagree the claim is UNCERTAIN. Results: Supported, Partly supported, Contradicted, Not found in this search, Uncertain. "Not found" never means "no evidence exists".
- **The paper is never changed by it**; contradicted claims are reported with a warning, and sources for uncited claims are offered for the student to read and choose.
- **Enforced in code, not prompts:** the searching step receives only the claim and a checked query (no paper text); a claim containing the paper's own result figures, or a query with contact details or front-matter names, is dropped before any search; only URLs the search actually opened are accepted.
- **Cost:** OpenAI web search is $10 per 1,000 searches plus the pages read as input (checked 2026-09-27). At most 10 claims per paper (3 + 1 per 400 words) and 2 searches per claim. Searches are counted in the job's hard spending ceiling; when the quoted allowance is spent, the remaining claims are reported as not checked and the job is PARTIAL. Measured: about $0.06–0.08 per claim; a 750-word paper with 4 claims cost $0.32 in total including AI Check.

## 2026-09-27 — Deep Redraft and LaTeX conversion (phase 7, built under the owner's approval of the build plan)
- **Deep Redraft** works on groups of consecutive ordinary paragraphs within one section (at most about 900 words each). The plan loop is the same as refinement at the "deep" level; the writer may reorder, merge and split paragraphs and rewrite sentences inside a group, never across sections; headings, lists, tables, captions, quotations and paragraphs with section breaks are never touched. Locked items are numbered across the whole group, so the same code checks apply (every citation, field and link once, every number unchanged, no notes), and Word fields move as their original XML. A group that cannot be verified keeps the student's text (PARTIAL). At the deep level the plan reworks every group whose wording, register, structure or flow can be improved without new facts, even when a deeper problem (missing evidence) remains for the student. Priced at AI cost × 2 after a paid estimate that plans the whole paper.
- **LaTeX conversion** is deterministic code (no AI), UGX 150 per 300 words, minimum UGX 3,000, on its own or after refining, redrafting or formatting. The download is a zip with main.tex, figures and a README, plus main.pdf when the server compiled it (offline TeX Live, no shell escape; the image build fails if its self-test does not compile). Citations stay as displayed and the reference list as written: **no BibTeX file**, because building one would mean guessing authors, titles and years. An equation or image the converter cannot express is left out with a comment where it was and listed as a warning (the job is PARTIAL); all text is escaped, so a student's words can never become LaTeX commands.

## 2026-09-27 — Fixes from Codex's audit of phases 3–7 (all 14 findings verified and fixed)
- **Source check evidence:** a quotation counts only when PaperAid finds it itself: on the source page (public http(s) pages only, private addresses refused, size and time limits), or for a journal article whose page is blocked, in its abstract from OpenAlex (via the DOI). A page that opened without the quotation makes the claim UNCERTAIN; sources PaperAid could not open at all make it UNCONFIRMED ("Found, not confirmed", links for the student to check). Unconfirmed passages never reach the second model. The claim text is privacy-checked as well as its query, the paper's own work ("we/our…", "this study…") is never searched, and results from any search whose actual query breaks the rules are discarded. Only search actions are billed, not page opens.
- **Spending:** output is capped to what the remaining budget can pay for, with input counted conservatively (2 characters per token plus request framing, billed as a cache write) and 20,000 tokens reserved per search. This is a conservative bound, not an exact count; a rare overshoot is absorbed by PaperAid and the student is never charged above the quote. A batched step that reaches the budget stops at a batch boundary and delivers what was verified (PARTIAL).
- **Estimates are reused, never repeated:** the job uses the analysis, passages and draft plan its estimate saved (by estimate id), so no change to PaperAid between estimate and submission can re-bill that work.
- **Privacy:** admin views and expired records keep an allowlist of support metadata only (ids, codes, counts, outcomes, public sources). Retention cleanup now covers abandoned drafts and unsubmitted quotes.
- **Deep Redraft:** never groups across a section break, image, equation, table or page break, even in an empty paragraph; a paragraph whose bookmark or comment range sits inside its text is never rewritten, and rebuilt ranges always enclose their text. Paragraphs in any script can be edited.
- **LaTeX:** link targets are limited to http, https and mailto and percent-encoded (no TeX injection); anything omitted makes the job PARTIAL.
- **Records:** a job record keeps at most ~300 KB of change text (the rest is in job storage and the change report), and any record over 900 KB is refused with a clear error.
- **Accounts and credits:** deleting an account claims it first (wallet `closing`), so no job, estimate, grant or retry can start meanwhile; every manual grant id is kept for good, so a replayed grant never adds twice.
- **[proposed, awaiting owner decision] Account deletion with a balance:** while credits are on, an account holding credit cannot be deleted until PaperAid refunds it (in testing mode it can). The estimate-fee carry-over to a different service (above) is also still **[proposed]**.
