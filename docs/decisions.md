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
- **Revision billing:** a revision is charged by the share of its targeted sections that actually got new text; one that changes nothing fails and costs nothing. A comment is marked revised only if its sections were delivered and it was not moved or edited after pricing. A revision quote is bound to the chapter version and comments it priced.
- **Incomplete academic review** is a partial result, charged at half its line (recorded in the job's `delivery`, no longer read from warning text).
- **Hourly limits:** feedback, guide uploads, "Download with my choices" and PDFs share `uploads_per_hour` = 20 per student.
- **PDF:** cached per content (chapter versions, plan, details, citation style, date) and at most 2 compiles at once per API instance; a busy instance says so (503).
- **Upgrades:** a step missing from a job's priced engine is refused (the job fails without charge, "start it again"); the academic review runs only for jobs priced with it.
- **Migrations** run in the scheduled cleanup: old projects move out of `users/`, and wallets' earlier entries are copied into the complete history (entries older than the 300-entry display cap were never kept and cannot be recovered).
- **Every Job field is classified** as paper-bearing (emptied for support and expiry) or support metadata; a test fails until a new field is classified.

## 2026-09-29 — One screen from upload to final draft, with a percentage (owner decision)
The owner compared PaperAid's AI Check with Grammarly and asked for the same kind of flow:
- **Upload first, nothing else.** Choosing a job and uploading opens the paper on its own page at once, with only the next step beside it: **Check for AI** (with the academic question and its price), or Redraft / Format for those jobs. The long options form is gone from the upload page (it stays only for the proposal review).
- **Results on the same screen:** Estimated AI-likeness as a **percentage** with its band, confidence and disclaimers above the paper (this supersedes "band only, no percentage"); passages marked in the paper with labels (strong/moderate/weak AI patterns, or the academic category), the explanation under the passage, and the report on the right grouped Strong/Moderate/Weak with Next →. The percentage is the word-weighted score the band comes from, rounded down so it always sits in its band.
- **Then Redraft**, and only then the options (how much, writing style, academic review, source check, formatting with APA/Harvard/university guide, custom layout, logo, LaTeX), with the price.
- **After a draft the window stays:** download, keep or undo each change, **Ask for changes** (the student's instruction, for passages they click or the whole paper, sent to the writer in their words and always rewritten), and **Format the finished paper**. Each is a priced job continued from the same paper (`POST /jobs/{id}/continue`).
- **Proposals:** every chapter and the concept paper have **Ask for changes** (text plus sections); the concept paper can now be revised (`REVISE_4`). The student's own requests are kept apart from supervisor comments in the response report.
