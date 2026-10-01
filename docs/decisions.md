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

## 2026-09-27 — Codex verification, round 2 (four remaining gaps fixed)
- **Quotations are confirmed word for word.** Only typography, case, spacing and line-end hyphenation may differ; a changed negation or figure, or fragments stitched from different parts of a page, are not confirmed. A marked omission ("…") is allowed when every part is on the page in order.
- **A closed account stays closed.** Deletion leaves a tombstone wallet (no email, balance or history), and draft creation checks the account and writes in one atomic step, so a request already past its checks can neither leave a draft behind nor recreate an open wallet through a late credit grant.
- **Retention claims before it deletes.** Cleanup atomically claims an expired job (refused while work runs, an estimate runs, credits are held or the job is being deleted); a claimed job accepts no submission, upload, estimate, quote or retry, and an interrupted cleanup resumes from the claim.
- **Bookmarks, comments and permission ranges keep their exact scope.** Paragraphs holding them are never part of a Deep Redraft group (refinement keeps whole-paragraph ranges around the rewritten text).

## 2026-09-28 — Master context adopted with Claude's recommendations (owner decision)
`PaperAid_Master_IDE_Context_Pricing_UX_Proposal_Algorithm.md` (the owner's master context) is adopted as product direction, with these rulings where it conflicts with earlier decisions or with itself:
- **Models:** the permanent algorithm stays for writing and review (Sol leads, Opus writes, at most 2 fix rounds). GPT-6 Luna may take mechanical steps only (claim triage, finding classification, finding explanations), introduced as a new engine version. Luna, Sonnet or a risk router take over writing only after they match the current engine on a fixed benchmark set of documents.
- **Money:** fixed prices by service and page band replace "AI cost × 2" as the customer price, still settled through the existing hold → settle ledger and never above the quote. The unit stays **credits** (UGX), not "tokens". Exact prices come from measured costs before credits are switched on.
- **AI score:** band (Low / Moderate / High) plus a confidence level; no percentage until the score passes validation (unchanged).
- **No mock flows:** new screens are built against the real backend; unfinished services are hidden through config.
- **Build order:** Proposal V1 first — the UCU Academic Research Manual (revised April 2018, `UCU_Academic Research Manual.pdf`) as the baseline rulebook, a persistent proposal project, plan first, Chapters One to Three, an evidence library, a readiness audit, versions and DOCX export. Then the interactive AI Check workspace. Proposal V2 (supervisor feedback with dependency updates, locked decisions, framework diagrams, other institutions' manuals) comes after.
- **Soon:** Crossref DOI lookup for reference existence (separate from claim support), including retraction notices.

## 2026-09-28 — Proposal V1: merged plan (Claude's recommendations + Codex's review, owner decision "execute")
Codex's review (`docs/Codex_Master_Context_Review_and_UCU_Proposal_Plan_20260928.md`) is adopted on top of the entry above. Where they differ, this entry wins:
- **Build order:** (1) UCU rulebook and review of an uploaded proposal; (2) persistent project with an approved plan, stable decision ids, an objective-to-method alignment matrix and dependency tracking; (3) evidence library and Chapter One; (4) Chapters Two and Three; (5) whole-project audit and Word export; (6) interactive review workspace and supervisor feedback (later).
- **Decisions are locked in V1:** every approved decision (objectives, questions, area, population, design, sampling, variables, alignment rows…) has a stable id and a content hash; each generated section records the hashes it was written from, and a section whose decisions changed shows "needs review". Plan edits carry the version they started from, so two tabs cannot overwrite each other silently. A job publishes against its input version; a plan produced while the student edited is kept as a candidate, never over their draft.
- **The author owns the facts:** PaperAid asks rather than invents population sizes, sample assumptions, instruments, statistics, pilot results or approvals. Sample sizes are calculated by code from approved assumptions (Yamane, Cochran, Krejcie & Morgan, census; saturation or an author-stated number for qualitative work). Chapter Three cannot start while a required fact is missing. Ethics text describes planned safeguards, never approval already obtained.
- **Readiness:** a checklist with PASS / NEEDS_REVIEW / MISSING / NOT_APPLICABLE / BLOCKED, each marked as a code check, an AI judgement or an author-confirmed fact. No marks or percentages (the manual's 20/15/15 table is used as questions only).
- **Rule scope:** proposal, concept-paper and final-report rules are kept apart; 2–5 objectives and 30 quality references are recommendations with their source, not hard rules; faculty variations win when documented.
- **Citation style:** the manual's appendix uses APA 6. A project chooses "APA 6 (UCU 2018 manual)" (default) or APA 7; citations are stored as evidence tokens and rendered in the chosen style, so switching needs no AI.
- **Retention:** a project expires 30 days after the student's last genuine action (edits, approvals, submissions, downloads — not page views); the expiry date is shown. Account deletion and cleanup cover projects.
- **Pricing:** proposal jobs use the current credits-v1 policy while credits are off; fixed retail prices (with a frozen billing-policy version per quote) come after live costs are measured. Proposal features stay invite-only until the live gates pass.

## 2026-09-28 — Codex's full audit of 655cda5: all 16 findings verified and fixed
Report: `docs/Codex_Full_Code_Audit_20260928_655cda5.md`; regressions in `backend/tests/test_audit_20260928.py` and `web/scripts/e2e-proposal-recovery.mjs`.
- **Fetching** connects only to the address it validated (resolved once, pinned, TLS checked against the real host, no environment proxy, every redirect re-checked).
- **Formatting** never relinks a later section's own header or footer, and fails rather than change one.
- **Storage:** project files live under `projects/`; the bucket's 31-day backstop applies to `users/` (job files) only. The live bucket rule must be updated at the next deploy.
- **Proposal steps** are accepted in one transaction with the project (job, wallet and project together); deletion is refused while a step is queued or running, and expiry rechecks the date inside its claim. Deleting a project erases every job run for it.
- **Every delivered text is checked** (paragraphs, table cells, captions); a section is never passed unreviewed (budget or not); at most two fixes, and the last text is always reviewed; reviewer notes reach the student.
- **Complete export** requires every section the current plan needs and no code-level integrity failure; AI judgements and the 30-reference recommendation stay advisory.
- **Decisions:** sections covering every objective depend on the whole set, so adding an objective marks them; missing sections are shown for review.
- **Student figures:** a population size or stated sample comes only from the explicit fields the student fills in (population size, its source, expected participants).
- **APA 6** first citations follow reading order. **The web** keeps a plan draft's version with its content and shows conflicts; load errors and refused monitoring are shown with a retry.

## 2026-09-28 — Owner decisions: simpler experience, tokens, automatic Chapter One
- **New job starts with the job.** `/app/new` first asks "What would you like PaperAid to do?" (every service with what it does, what you get and what it accepts); the upload form opens set up for the chosen job. Every service also has its own top-bar link (AI Check, Refine, Formatting, Proposals) so a student can switch from anywhere.
- **Students see what PaperAid does, never how.** No lead/writer, advisers, second AIs, critiques or algorithms in the interface or messages, and no institution manual, committee or section numbers; progress reads "Researching your topic", "Planning", "Writing", "Checking and polishing". Readiness items no longer show whether code or the AI settled them (kept in the data); only facts from the student's own details are marked. This supersedes the "basis" display in the Codex review entry.
- **Tokens replace money amounts.** 1 token = UGX 1,000 (owner's master context), shown to one decimal; minimum purchase 10 tokens (UGX 10,000). The ledger, holds and settlement stay in UGX; admins grant tokens. This supersedes "the unit stays credits".
- **Chapter One follows the plan automatically.** The plan's price shows the plan and Chapter One together; starting the plan is the student's go-ahead for Chapter One, which starts (with its own hold) when the plan is first approved. If it cannot start (not enough tokens, a missing figure) the student is told why and starts it themselves.

## 2026-09-28 — Pending work built: review workspace, reference checks, fixed prices, formatting options (owner: "work on everything pending")
- **Fixed prices (`fixed-v1`, the default `pricing_mode`).** Each service has a token price per page band (`fixed_tokens`; a band is 10 pages of 250 words; each band adds `band_step` 75%). A quote freezes its price version; `budget_usd` on the quote is the worst-case spend cap the job may use. Settlement charges each line in proportion to what was delivered (`delivered_share`), never more than quoted. Deep Redraft's estimate is free under fixed prices. Source check's price (3 tokens a band) is still to be confirmed by the owner. `pricing_mode="cost"` keeps the old actual-cost × 2 rule (used by most tests).
- **Academic review** is a lead-model step (`academic`, prompt `academic-v1`) in ANALYSING: evidence, method and argument findings with a category and a "safe to fix" flag, priced as its own line (on by default, the student can turn it off). Formatting findings (headings typed as text, skipped levels, caption numbering) and a "protected in your paper" summary come from code (`app/analysis/structure.py`).
- **Review workspace.** The student reads the paper beside its findings, dismisses or restores them, and "Fix selected" / "Fix all safe issues" open a new priced refinement draft limited to those passages (`only_blocks`, with the findings as notes). After a refinement each change can be kept or rejected; "Download with my choices" rebuilds the Word file by code from the original. No AI runs in the workspace itself.
- **Reference verification** (`app/analysis/references.py`): each reference-list entry is looked up on Crossref (by DOI, otherwise a bibliographic search) with OpenAlex's retraction flag: VERIFIED, PROBABLE, MISMATCH or NOT_VERIFIED. The wording is "could not verify", never "fabricated". This is separate from the source check (claim support) and from AI-likeness.
- **Formatting options.** Professional and report layouts for non-academic documents; the student may override font, size, line spacing, margins and alignment on top of a style; an institution logo (PNG/JPEG, ≤ 2 MB, validated) is placed top centre or left on the first page, sized 3.5 cm wide, with the text fingerprint checked unchanged.

## 2026-09-28 — Proposals V2 built (owner: "work on everything pending")
- **Supervisor feedback.** Comments are pasted, or read from a marked-up Word file (each Word comment with the heading it sits under) or PDF notes; code places each on a section (a section number, a heading, or the words it uses) and the student confirms. A priced revision step (`REVISE_n`) sends only those sections through the writer's fix step with the comments as the issues, then the lead's review and at most two further fixes; every other section is carried over unchanged into a new version, and each comment records the version that answered it. A Word "response to the supervisor's comments" table is built by code. No new AI step.
- **Version comparison** of any two chapter versions, section by section and word by word, citations as they print. **Conceptual framework** figure drawn by code from the plan's variables (web boxes and a Word figure). **"Ready?"** screen: what blocks the complete download, in one place.
- **Research-gap builder** (`p-plan-v2`, `p-finalise-v2`): the plan carries a research gap (known, missing, contribution) resting only on confirmed evidence ids (code drops any other); it is a tracked decision, so changing it flags the problem statement, justification and the literature review's gap section.
- **Concept paper** (UCU manual §1.4): its own document in the project (stored as number 4), written from the approved plan with the manual's section lengths, at most five pages and five to eight annotated references (each annotation is the confirmed finding from that source); exported on its own. Price 2 tokens, to be confirmed.
- **PDF** of the proposal for reading and sharing: the Word export converted to LaTeX and compiled offline (the image already has TeX Live). Word stays the file to submit.
- **Institution profiles** from the student's own research guide, before any chapter is written: a priced step (lead drafts the profile, writer critiques, lead finalises: `p_profile`, `p_profile_critique`, `p_profile_finalise`) whose answer code validates into a rulebook of the default's shape, filling what the guide leaves out from the default and listing it for the supervisor. The title page and layout follow that institution. Price 2 tokens, to be confirmed. Students see "the standard proposal structure", never the UCU name.
- **Revision price** 2 tokens per band of revised text, to be confirmed.

## 2026-09-28 — Operations
- **Credit history is complete:** each ledger entry is also written as its own record in the wallet's transaction (Firestore subcollection `wallets/{uid}/ledger`), so history survives the wallet's 300-entry display cap; the credits page pages through it. It is deleted with the account.
- **Load test:** `python -m tests.load_test` (concurrent students through draft, upload, quote and code-only jobs; no AI). Use 127.0.0.1, not localhost, on Windows.
- **CI** runs the web unit tests.

## 2026-09-28 — Models stay as they are (owner decision)
"Go with the original models; we will revise the model politics later." GPT-6 Sol leads and Claude Opus 5.5 writes for every step. The Luna benchmark and any per-step model routing are not pending work until the owner reopens it; this supersedes the Luna line in "Master context adopted".

## 2026-09-28 — Codex's audit of 56c4f83: all 29 findings verified and fixed
Report: `docs/Codex_Full_Code_Audit_20260928_56c4f83.md`; regressions in `backend/tests/test_audit_56c4f83.py` and `web/scripts/e2e-audit-56c4f83.mjs`. Decisions taken while fixing (owner may revise):
- **Revision billing:** a revision is charged by the share of its targeted sections that changed and passed the final review; a revision resolving nothing fails and costs nothing. Unresolved comments stay open. A comment is marked revised only if its sections were resolved and it was not moved or edited after pricing. A revision quote is bound to the chapter version and comments it priced.
- **Incomplete academic review** is a partial result, charged at half its line (recorded in the job's `delivery`, no longer read from warning text).
- **Hourly limits:** feedback, guide uploads, "Download with my choices" and PDFs share `uploads_per_hour` = 20 per student.
- **PDF:** cached per content (chapter versions, plan, details, citation style, date) and at most 2 compiles at once per API instance; a busy instance says so (503).
- **Upgrades:** a step missing from a job's priced engine is refused (the job fails without charge, "start it again"); the academic review runs only for jobs priced with it.
- **Migrations** run in the scheduled cleanup: old projects move out of `users/`, and wallets' earlier entries are copied into the complete history (entries older than the 300-entry display cap were never kept and cannot be recovered).
- **Every Job field is classified** as paper-bearing (emptied for support and expiry) or support metadata; a test fails until a new field is classified.

## 2026-09-29 — One screen from upload to final draft, with a percentage (owner decision)
The owner compared PaperAid's AI Check with Grammarly and asked for the same kind of flow:
- **Upload first, nothing else.** Choosing a job and uploading opens the paper on its own page at once, with only the next step beside it: **Check for AI** (with the academic question and its price), or Redraft / Format for those jobs. The long options form is gone from the upload page (it stays only for the proposal review).
- **Results on the same screen:** the paper and highlighted issues on the left; a compact Estimated AI-likeness **percentage** and its band at the top of the right panel, followed by explanations and Strong/Moderate/Weak counts with Next →. Confidence, analysed/excluded word counts and disclaimers sit behind the information button. This supersedes the earlier position above the paper and explanations under passages. The percentage is a weighted writing-pattern score on a 0–100 scale, rounded down so it sits in its band; it is not a percentage of AI-authored words or a promise that fresh model checks will agree. Older original and refined scores are recovered from saved analysis when it is sufficient, without new paid calls.
- **Then Redraft**, and only then the options (how much, writing style, academic review, source check, formatting with APA/Harvard/university guide, custom layout, logo, LaTeX), with the price.
- **After a draft the window stays:** download, keep or undo each change, **Ask for changes** (the student's instruction, for passages they click or the whole paper, sent to the writer in their words and always rewritten), and **Format the finished paper**. Each is a priced job continued from the same paper (`POST /jobs/{id}/continue`).
- **Proposals:** every chapter and the concept paper have **Ask for changes** (text plus sections); the concept paper can now be revised (`REVISE_4`). The student's own requests are kept apart from supervisor comments in the response report.

### 2026-09-29 — Completing the interrupted fixes
- Selected passages are mapped through formatting and logos by their paragraph identity, so identical wording cannot select the wrong occurrence. A continuation uses the current keep/undo choices, and reviewed downloads are published only if those choices still match.
- Explicit selections include every editable requested passage, including short passages excluded from the AI score. Up to 3,000 passages can be requested, with one saved copy of the instruction. Invalid selections are refused.
- A chapter's student request is quoted by its exact comment ID, can be cancelled, and is offered only on the current chapter version. Abandoned requests do not join later supervisor revisions.
- Every guide attempt belongs to the project's guide directory; deletion removes current, replaced and legacy flat guide copies. Upload failures remove their copy, and the fixed-age storage rule remains a backstop for hard interruptions.
- Missing institution profiles expose the standard-structure recovery action even after chapters have been written.

## 2026-09-29 — Four-model routing and approval (owner reopens the model policy)

The owner requested Luna and Sonnet for the working steps, with Sol and Opus reserved for guidance and approval before generated wording is released. The later request supersedes the earlier Luna-only checking choice and the 2026-09-28 original-models-only decision.

- **Checking:** Luna and Sonnet independently assess every eligible body passage. Neither sees the other's answer. Code combines the two band scores equally within the existing 50% model / 50% signal blend. The percentage remains a writing-pattern index, not an AI-authorship probability. Missing responses do not imply LOW; an incomplete check has no overall percentage. Disagreement identifies passages and lowers confidence; it does not become forced consensus.
- **Working steps:** Luna drafts plans and does routine analysis/research; Sonnet critiques, writes and repairs. Opus supplies plan guidance; Sol finalises the instructions. Repairs are bounded by the existing maximum and reviewed again.
- **Release:** Sol and Opus independently review the same changed text. Either rejection, missing review or substantive issue prevents that wording from being delivered. Previous approval cannot approve a later repair. Uploaded papers retain original wording where a rewrite cannot be approved, with warnings. Chapter revisions retain the previous section. A new proposal chapter has no previous wording, so a missing/rejected section prevents release and the job is refunded. A proposal plan also receives both final approvals. Changing wording after approval for evidence cleanup prevents release.
- **Formatting:** university rules receive both frontier reviews; unresolved rules prevent release. Deterministic APA/Harvard formatting and LaTeX conversion do not add AI wording and retain their existing code checks. Check reports can be generated by the checking service; the frontier approval requirement applies to rewritten/generated academic text.
- **Compatibility and billing:** each quote freezes the model routes, approval policy and prompt versions. Older jobs keep their quoted algorithm and cached request shapes. Estimates replay the original paid calls; the finished paper's separate checking calls are recorded separately. Provider budgets project all required models and review/repair rounds. Customer fixed prices are unchanged.
- **Verified prices:** [GPT-6 Luna](https://developers.openai.com/api/docs/models/gpt-6-luna): $0.10 input / $0.50 output / $0.01 cached input per million tokens. [Sonnet 5.5](https://www.anthropic.com/claude-sonnet-5-5): $2 / $10 / $0.20 respectively. These are standard token rates; task costs and quality must be measured on PaperAid's papers.
- **Calibration remains pending:** existing rule thresholds have no labelled held-out validation. Model agreement alone cannot establish authorship accuracy. Job `job_8a5808635e3e` still needs its saved cloud analysis to diagnose its LOW result; the read-only helper is `backend/inspect_ai_score.py`.

The routing above began as Codex's interpretation. The owner confirmed it, with the refinements below, by approving the joint Claude–Codex plan on 2026-09-29.

### 2026-09-29 — Agreed plan (Claude audit, Codex amendments, owner go-ahead)

- **Checking:** both checkers assess every eligible passage. A checker that skips passages is asked again once, for those passages only, within the job's spending limit (Phase 2). Every difference between the checkers is kept internally; only low against high is shown to the student as uncertainty. Such passages lower confidence to at most MEDIUM, and to LOW when they cover 15% or more of the analysed words (provisional, uncalibrated).
- **Rejected rewrites:** the student's original wording (uploaded papers) or the previous approved section (chapter revisions) is kept, with a clear warning. New chapters stay fail-closed with no charge in this release; partly written chapters and a "Finish chapter" step are a later milestone.
- **Approved text is delivered exactly:** evidence cleanup that removes nothing leaves the text untouched. When cleanup does remove a sentence, it happens before the final approval and both reviewers approve the cleaned wording; a final code check refuses any change after that.
- **Billing (Phase 2):** an AI Check that cannot produce its complete result is not charged; other delivered parts of the job still are. A paper with no passage long enough to score is refused before it is priced.
- **University rules not approved (Phase 2):** approved work is delivered without them, that part is refunded, and the student is told the university formatting was not applied.
- **Institution profiles (Phase 2):** need both approvals; if rejected, the student is offered the standard structure and confirms it before continuing.
- **Prices:** unchanged for controlled testing. Public prices are decided after measuring actual costs, including failed, refunded and abandoned work, at the median and the expensive end. Opus guidance stays on until its value is measured.
- **Score formula:** unchanged until a calibration on human, AI-written and mixed papers (including Ugandan academic writing, technical papers and different English styles), with weights chosen on a development set and confirmed on separate papers. The percentage stays a writing-pattern score.
- **Prompts:** every prompt describes the model's real role; changes are new versions, including for prompts that were never deployed.
- **Navigation (Phase 3):** three sections: Paper Check (upload → check → redraft → review changes → finish, with source check as an option, university templates as formatting choices and LaTeX as an export), Research Proposals, and Academic Formatting (APA/Harvard without AI; a university guide uses AI and is priced as such).
- **Implemented (owner: "do all phases"):** Phases 1-3 and 6 are built and tested. Partial chapters and "Finish chapter" were moved into this release at the owner's instruction, with Codex's conditions: sections are weighed by planned length; the draft and its finish never cost more than one chapter; a finish is bound to the version it was priced on (a second tab cannot buy it) and refused if the plan changed; an incomplete chapter cannot be approved or exported as complete. An uploaded guide must be read, or the standard structure chosen (which removes the guide), before a plan or chapter is written. A source check may run on its own from a paper's results; a complete proposal also downloads as LaTeX (converted by code, free). Not built: re-checking only changed passages after a rewrite, because each checker also sees whole-document context that any rewrite changes.
- **2026-09-30 — owner decisions after Codex's review:** (1) students get writing-pattern feedback only: no AI-likeness percentage or band and no wording that claims to detect AI, until a validated detector exists (`SHOW_AI_SCORE`, off); (2) partial chapters and "Finish chapter" ship behind `PARTIAL_CHAPTERS`, off, because the release before this one cannot protect a partly written chapter after a rollback. Codex's other findings are fixed: a step is bound to the guide and structure it was priced on; a chapter's finishes are capped at what it has not yet cost; a complete proposal's LaTeX is refused if anything was left out; a finish is written, fixed and reviewed with the chapter's approved sections; an over-long plan field is never cut mid-sentence (the step fails without charge instead); the cost report uses each quote's own exchange rate. Post-release follow-up (Codex audit of `5277491`): with `SHOW_AI_SCORE` off, student job and document responses omit the percentage, band and confidence (admin views keep them); guide uploads and structure changes are refused while a proposal step runs, and a step publishes only on the guide it was priced on (`StepInput.guide_sha256`); a complete proposal's PDF is refused if conversion omitted content and a draft PDF says it is incomplete; a finish sees every approved section's heading and an excerpt, with more text from the sections beside the missing ones.
- **Phase 4 finding (2026-09-29, real models):** on 10 human and 10 AI-written papers the check rated both groups the same (mean 6% each on the current formula; nothing MODERATE or HIGH), so no reweighting can make the percentage detect AI writing. Details and costs: `docs/Four_Model_Algorithm_20260929.md`. The owner decides how the score is presented or replaced before release.
- **Diagnosis of `job_8a5808635e3e`:** the checker judged 42 of 83 passages and 41 omitted passages counted as LOW; the rule score was about 0.5%. With the same judgements on every passage it would still be about 11% (LOW). The formula, not the omissions, dominates; whether the paper should have scored higher is not established.

## 2026-09-30 — Works: concept notes, coursework and funding proposals (rulebook v1.0)

Owner decisions:
- **New sections:** Coursework and Funding (funding concept note, project concept note, funding proposal); an academic concept note under Research Proposals, built on the UCU concept paper. Each work service is switched on in `WORKS_ENABLED` once its token prices are set (`WORK_PRICE_KEYS`); none are invented, so an unpriced service shows as coming soon.
- **AI checker:** stays "coming soon" (shown in Paper Check); the writing check stays live as feedback.
- **Payment:** students buy tokens and spend them per action (a fixed price per service and length band, charged in full when delivered, nothing when a step cannot deliver). The review tier behind each price (STANDARD or PREMIUM, `service_tiers`) is internal; students never choose or see it. Subscriptions later.
- **Models:** roles are configuration (`role_models`): analyst and integrity checker GPT-6 Luna, writer Gemini 3.8 Flash (Gemini API, paid tier, `GEMINI_API_KEY` in Secret Manager), standard evaluator Claude Sonnet 5.5, premium evaluator Claude Opus 5.5, no adjudicator (an unresolved disagreement is shown as "needs review"). Changing API in January 2027 is a settings change for new quotes. Gemini's prices double on 1 January 2027 (`costs.PRICE_TABLES`); each quote freezes the table in force.
- **Coursework and AI rules (amends CW-047):** when a brief bans generative AI, PaperAid still drafts; the last page of the Word document says "This document was drafted by an AI-assisted third party.", the student is told before buying, and PaperAid cannot leave the note out. When the policy is unknown the note is on by default and the student may untick it; when AI is allowed with disclosure a disclosure statement is added. There is never a detector-evasion step (CW-073).

Rulebook v1.0 amendments (they win over the rulebook):
1. The rulebook defines what must be true; the worker → evaluator → repair design decides which model does each step (replaces §0 and directive 18, "routing unchanged").
2. Readiness is the existing checklist (PASS / NEEDS_REVIEW / MISSING / NOT_APPLICABLE / BLOCKED, each CODE / AI / AUTHOR) with a severity; code works out Not ready, Ready with warnings or Ready. No second DRAFT or NEEDS_REVIEW status (§21).
3. Appendix A2 is the Results Model; §12.6 is superseded.
4. A model's own confidence decides nothing (§5.1): a requirement locks only when code finds its quote in the document and nothing conflicts; anything else is confirmed by the student, and high-stakes items are always confirmed.
5. Quality rules are judged together, one evaluation per section with the rules that apply to it, never one call per rule.
6. Page compliance comes only from a rendered count (`RENDER_PAGES`, LibreOffice in the worker when built with `WITH_LIBREOFFICE=true`, 5% margin, the Word download authoritative); until then a page limit shows "Needs review" and the work is not Ready.
7. Storage: one record per work in its own `works` collection; requirement sets and document versions are immutable files; rules are one data file per service (`app/rules/data`).
8. The new services are priced by length mode or word band; all budget arithmetic is code; figures from the budget, Results Model, call or the student's answers enter the text only as number tokens that code fills.
9. Source list: S22 and S38 are secondary; the gaps in its numbering are intentional.

Codex's review of the plan, adopted: nothing the student must settle is left to be discovered after they pay (steps are priced only when their inputs are in place; a step whose own output breaks a blocking rule after its bounded repairs fails without charge; an exploratory draft is labelled at the quote); an untraceable citation fails its section and a sentence that still cannot be traced is withheld whole; quotes freeze roles, tier, price table and the hashes of every prompt, rule file, validator set and render profile; number tokens have stable ids, units and currency and an unknown one fails the section; edits carry their base version; semantic rules are judged even on low-risk sections; a concept-note project never starts or prices Chapter One; `AIRunner`'s recording, cache, heartbeat, budget and validation are reused. Rollback: a tolerant release (the new records readable, work steps failing with a refund, works deleted with their accounts and expiring, concept projects safe) is released first and is the rollback point; it was checked against records written by the full release.


### 2026-09-30 — Codex's audit of the works build: all 11 findings fixed

1. **Publication and settlement are one transaction.** A work step's export publishes, completes and settles in `update_job_wallet_and_work`, so a published result can never be refunded and a refunded step is never published (also when an older release takes the step over). A failure handler never touches a job that is no longer processing. A proposal export retried after its publication committed now settles instead of being refused.
2. **Checks run on the exact published text.** After the whole-document review, compression and withheld sentences, every section that changed is reviewed again (no repair), then the whole document is reviewed again; a result that no longer passes a blocking rule fails without charge.
3. **A paid plan can always be approved.** Code places every part of the question the writer left unplanned; planning and approval use the same test (`_plan_problems`, now including the hard word limit), and a plan that still fails it fails the step without charge.
4. **Revisions deliver and charge only what passed.** A requested change that does not pass its review is not delivered (that section stays exactly as it was); the step is charged for the share of requested sections changed (`delivery`, outcome PARTIAL); a request stays open unless every section it asked about, or every targeted section for a whole-document request, was revised.
5. **Limits count their scope (rulebook §6.2).** Each section's text and its own table always count; the reference list and the tables code renders count when the limit's scope names them; when the instructions do not say, a total over the limit with them shows "Needs review". Compression shrinks by what the whole scope is over.
6. **Table cells and captions** are withheld like sentences when they carry an untraceable citation or figure.
7. **Long documents are read in full:** every instruction document in overlapping parts across as many calls as needed (priced accordingly); a set reading is read for its details, and evidence is looked for in its most relevant parts from anywhere in it.
8. **Search privacy:** each step freezes private words (the student's email name, every titled name in their details and documents, names inside their account of their experience, minus the topic's own words); proposed and sent queries and the need's text are checked.
9. **Frozen content is enforced:** before any paid call or rule, a work step checks the running prompts, rule files, validator set and render profile against its quote's hashes; a changed release fails it without charge.
10. **A quote verifies its value:** a requirement is verified only when its number (figures, "50k", words, years for a duration), a limit's unit, a referencing style or a currency appears in its own quote; otherwise the student confirms it.
11. **The preview shows each section's table**, as the Word file does.

### 2026-09-30 — Works on for invited testers (owner: "I need coursework live")

- Coursework, funding and project concept notes and funding proposals are on (`WORKS_ENABLED`) for the invited testers only (the work services now follow `TESTER_EMAILS` like every AI service). Credits stay off while testing, so nothing is charged. Only AI detection stays "coming soon".
- Testing prices (worst-case projection × 2): read 1; plan 3 (coursework, concept note) or 7 (funding); coursework 20 / 35 / 60 / 90 for up to 1,500 / 3,000 / 5,000 / 8,000 words; concept note 20 / 34 / 44; funding proposal 57 / 122 / 247; changes 17. To be set from real spend before students pay.
- Real-model pilot (Gemini writer, Luna, Sonnet or Opus reviewers), actual spend: coursework plan $0.10, 1,500-word draft $0.32 (7.6 min), changes $0.04; concept note read $0.001, plan $0.15, standard draft $0.47 (10 min); funding plan $0.35, compact draft $1.66 (18 min). Actual spend is about a fifth of the worst-case projection or less.
- Before public launch: credits on, a way to buy tokens (interim: mobile money confirmed by an admin; later a payment gateway), then the tester list removed.

### 2026-09-30 — Codex's second audit of the works build: all 12 findings fixed

1. **Requirement values:** a figure is read whole with its scale ("USD 50k" is 50,000, never 50; "1,500" never 1 or 500), and a limit's number must sit next to its unit ("a 5-page limit" is never 50 pages beside "50 applicants").
2. **Word file before charging:** a writer's uneven table rows are padded (never cut), the Word writer tolerates uneven rows, and the Word file is built once before a step can complete, so an export fault fails the step without charge.
3. **Revisions that change nothing:** a requested section the writer did not return, or returned unchanged, is not revised, charged or closed; if none changed, the step fails without charge.
4. **Stale verdicts:** each review round clears the earlier verdicts of the sections it re-reviews, so repaired text is reviewed afresh or reported as not reviewed.
5. **Sampling:** for a method that calculates a sample (Yamane, Cochran, Krejcie & Morgan), missing settings take the standard values and the plan asks the student to confirm them before approval; qualitative methods are filled quietly.
6. **Required headings:** matching ignores generic words ("proposed", "indicative", "statement"...), then uses equivalents and the section's purpose; a renamed section's brief names the call's heading.
7. **Pilot fails closed:** the work services are open only to listed testers and admins, even with an empty list, until `WORKS_PUBLIC=true` opens them for launch.
8. **Uncertain limits:** when the instructions do not say whether references and tables count and they would exceed the limit, the item shows "Needs review" at warning level (new validator status WARN): visible, not blocking. The same applies to sections where untraceable sentences were withheld.
9. **Missing documents:** a READ step with any stored document missing fails without charge and names it; nothing is marked read.
10. **Private names:** capitalised names in the student's own account are private even when the topic names them; only countries and regions stay searchable.
11. **Form boxes** count their table text.
12. **Hard limits** keep every finding: an estimated page count no longer hides a word-limit failure.

## 2026-09-30 — One accountable final reviewer (owner decision; supersedes the dual veto of 2026-09-29)

Live cases behind it: the owner's proposal plan `prj_c704b0c370f7` failed twice with DOCUMENT_NOT_APPROVED because Sol, the first reviewer, raised fixable objections and plans had no repair after review (Opus, the second reviewer, was never reached). The owner's coursework `wrk_64b3b916e144` never reached AI: the word-limit box was a number field, so "3,000 words" was lost in the browser and the question stayed open.

- **Sol alone approves generated wording**: proposal plans, chapters and profiles, works plans, Results Models and documents, Paper Check rewrites. No second automatic veto. Sonnet, Gemini and Luna plan, draft, check integrity and repair. Sol never approves what it finalised: proposal-plan, profile and template-spec finalisation moved to Sonnet. Opus's guidance is optional (`FRONTIER_GUIDANCE`), off by default, never a veto; the works premium evaluator is Sonnet.
- **Rejection leads to repair**: a targeted repair of exactly what was raised, then review again, at most two repairs (`REVIEW_REPAIRS`).
- **What is delivered when review does not approve**: a proposal or works plan (or Results Model) still objected to, or not reviewed, is kept with the exact objections shown, marked unapproved, charged nothing (delivery share 0), never starts Chapter One by itself, and can be approved only with the student's recorded, versioned acknowledgment. A generated document with an unresolved PaperAid-owned blocking defect, or whose final review is missing, cut off, refused or unaffordable, fails without charge (REVIEW_UNAVAILABLE, SPEND_CAP, DOCUMENT_NOT_READY).
- **The works final review** is on the exact deliverable (paragraphs, section tables and captions, generated funding tables, rendered citations and figures, references, required notes), requires a verdict for every document rule, question part and funder priority, and runs in parts of at most 7,000 words with a manifest of the whole. After any repair, withholding or compression the whole deliverable is reviewed again. The Word file built from the approved content before completion is stored and every download serves exactly it.
- **Hand-typed citations in plans** are converted by code only when they match exactly one confirmed source by author and year; any other is sent to the repair by name. No source is invented.
- **Sampling**: standard settings PaperAid substitutes for a calculated sample (Yamane, Cochran, Krejcie & Morgan) need the student's explicit acknowledgment, stored with the plan version and text hash, before the plan can be approved.
- **Reasons**: readiness items and failures carry REVIEW_OBJECTION, REVIEW_UNAVAILABLE, SPEND_CAP, CODE_RULE, STUDENT_INFO_MISSING or PAGE_COUNT_UNMEASURED, with a next action for the student.
- **Page limits**: LibreOffice renders the delivered Word file in the worker (`RENDER_PAGES=true`, image built with `cloudbuild.yaml`, which also proves rendering in the image); a page-limited work is never "Ready" from an estimate.
- **Coursework questions**: number answers are saved as the number they give ("3,000 words", "2 years" for a duration) or refused with the reason; "My brief gives no word limit" is an answer and never an invented limit; each answer is saved as it is given; the page says exactly why Confirm is unavailable.
- **Frozen older jobs**: `Engine.single_reviewer` is False on every engine priced before this decision; they keep both reviewers, their prompts (the content check now hashes every released prompt, so a superseded prompt version still verifies) and their prices. Credits stay off, the work services stay tester-only (fail-closed), AI detection and PARTIAL_CHAPTERS stay off.
- **Measured on the real models (pilot 2026-10-01, capped at USD 20; USD 3.28 in the recorded run and about USD 1.20 in an earlier run whose log was lost):** coursework 1,500 words: plan USD 0.04, draft USD 0.22 (was 0.32), Ready with warnings; coursework 5,000 words: plan 0.08, draft 0.55, 4,273 words, Ready with warnings; the owner's proposal topic replayed: plan 0.23, approved by Sol (it had failed twice live), Chapter One 0.49, all 11 sections; concept note with a 2-page call: plan 0.18 (Sol's objections kept: separate subheadings, a provisional budget split, unsupported applicant claims), draft 0.31, Not ready only because the page count was not measured on the machine without LibreOffice; funding proposal: plan 0.27 (Results Model objections kept: monitoring and evaluation indicators), draft 0.89 (was 1.66 with Opus reviewing each section). Sol's final review cost 0.02–0.04 a draft; Opus was not used. Every Word download was identical on repeat; every PDF converted after the workplan's "■" was mapped for LaTeX. A budget that did not match the amount requested now stops the draft quote before payment (FP-048 compares the student's answered amount).

### 2026-10-01 — Codex's audit of the one-final-reviewer release: all 7 findings fixed

1. **No approval despite an objection:** a works plan is approved only with a PASS verdict, a verdict on every rule it was asked to judge, no failed rule, no issue and no code problem; a Results Model also needs every goal, outcome and output classified at its real level (code's level, not the model's "stated as"). A missing verdict or classification is "not reviewed".
2. **Proposal steps publish, complete and settle in one transaction** (`update_job_wallet_and_project`), as works do: a published result is never refunded by a later failure.
3. **Older works steps are refused, not run on changed validators:** `validators-v2` and `render-v2`; a step priced on the earlier versions fails its content check before any paid call and is refunded.
4. **Each final-review part must be complete on its own** (every rule, question part and priority); a section longer than one part is split across parts; the projection allows for the extra part.
5. **An edit replaces the earlier review:** editing a reviewed plan, or a Results Model beyond the applicant's own baselines and targets, marks it "not reviewed (edited)", and approving needs the student's confirmation.
6. **One layout for the review and the Word file** (`app.works.export.layout`): title and labels, headings, paragraphs, form-box counts, printing tables, references and the note, in order; only the not-ready label is added afterwards, from the review's result.
7. **Institution profiles get the repair loop:** an objection is repaired and reviewed again, at most twice; a profile still not approved is never used and the step fails without charge.

### 2026-10-01 — Works repairs get the section's evidence

The live check after the OpenAI top-up: plan approved by Sol every time; of three 1,500-word coursework drafts, two failed without charge (DOCUMENT_NOT_READY: Sol found "critically evaluate the effectiveness" unanswered and the evaluation unsupported after both repairs) and one completed (1,348 words, Ready with warnings, Word identical on repeat, PDF converted). Cause: every works repair (a section's own, the final review's and a student's revision) received the text and the objection but none of the evidence the section was drafted with, so an objection asking for support could not be met honestly. Repairs now get the section's brief, rules, question parts and assigned evidence (`_repair_items`), under prompt `w-repair-v2` (critically evaluate = weigh what works, what does not, for whom, with what limits, and judge; a point the evidence does not settle is stated as a limit). Pricing already counted the evidence in repair inputs, so prices are unchanged. Each final-review round is also kept in the job's internal files (`final_review.json`: verdicts, repairs asked for, text) for admin diagnosis; it is never logged.
