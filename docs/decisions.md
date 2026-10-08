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

A further live run with this fix completed and was delivered, but as "Not ready": 1,259 words against a 1,500-word limit (CW-007, well under at 85%). Each section was only a little short, so no section check flagged it, while the document fell below the length check. The final loop now treats a document below that threshold (`UNDER_LENGTH`, shared with the validator) as PaperAid's to repair: the sections furthest under their planned length are developed with their evidence toward the planned total, within the same at-most-two repair rounds and their price.

### 2026-10-01 — Codex's audit of c6ba362: all 5 findings fixed

1. **A Results Model is approved only if code finds none of PaperAid's own defects:** the checks on what the model writes (FP-014, 018, 019, 022, 024, 036 and the budget-line mapping FP-037/038, when active and blocking) are objections like Sol's, go to the repair, and an unresolved one leaves the model kept, unapproved and uncharged. The applicant's own figures (baselines, targets, their dates, quantities, costs) are never part of it. Codex's re-check added: an indicator field the writer supplies (unit, means of verification, frequency, responsible role) and a model with costed activities but no budget lines are PaperAid's defects too.
2. **A new draft still well under its length after the repairs fails without charge** (DOCUMENT_NOT_READY, CW-007 in the detail), like every other PaperAid-owned blocking defect. A revision is not refused for it: the student's own requests may have shortened it.
3. **Final-review repairs are aimed:** a blank location names no section; an objection without a usable location goes to one section, the largest planned, never the whole document; a funder priority found unaddressed becomes a repair instruction instead of only a later failure.
4. **Target dates are the applicant's,** like baselines and targets: whatever the model writes there is cleared, so an edit to them never needs a new review.
5. **Every final-review part is within FINAL_PART_WORDS,** front matter, tables, references and notes counted: long paragraphs are cut at sentence ends, long tables by rows (header repeated; a single row too long for one part continues on further rows, each cell cut in step), and what follows the sections takes further parts when it does not fit.

### 2026-10-01 — Proposal Chapter One refused over "6–24 months": figure-check false alarms fixed

Live project prj_18519f00596d (job_d6b68ac4da3a) failed DOCUMENT_NOT_APPROVED, "5 of 11 sections approved", for no fault of the writing. The text that holds the student's own figures was built with JSON's default escaping, which wrote the dash in "6–24" as a code that hid the 24, so every sentence about children aged 6–24 months was flagged as an untraceable figure: withheld (leaving a bare "1." where objective 1 had been) and raised to the reviewer every round, until the sections ran out of repairs. "Section 1.9" was also read as the statistic 1.9. Fixed: the student's text is kept as written in proposals and works (any figure after a dash or symbol: "15–49", "≥18"); numbers after Section, Chapter, Table, Figure, Appendix and similar are references, not figures; a withheld numbered sentence takes its list marker with it; and a refused chapter's record names the unapproved sections and the first reason for each (admin only, never logged).

### 2026-10-01 — One Start: two pages, then the document (owner decision, with Codex's review)

Students never see, edit or approve a plan, and never see a price screen. Supersedes, for new work, the earlier decisions that the student confirms requirements, edits and approves the plan, and sees a quote (2026-09-29, 2026-09-30); works and proposals set up before keep their earlier pages until written.
- **Flow.** New (every service, grouped, coursework first) → page 1 (what the task is, with the brief or call; uploads are read at once, no charge of their own) → page 2 (what PaperAid found, with its quotes, and only the questions this document needs; required ones say "* Required" in words, with the reason beside the field; optional ones folded under "More details") → Start → progress (plain steps, an estimate per service, safe to close, "Request stop") → the workspace. Coursework gets an optional cover block (name, registration number, course, lecturer, institution, date), printed under the title and never sent to a model; a brief silent on AI keeps the last-page note on unless the student unticks it; a banned brief keeps it always.
- **The plan stays internal and is never approved in the student's name otherwise (Codex).** `POST /works/{id}/start` and `/projects/{id}/start` plan; the worker continues to the draft (Chapter One, or the concept paper) only when PaperAid's own final review approved the plan (and, for funding, the Results Model) and code finds none of PaperAid's own defects. Otherwise it stops: "We couldn't finish this one ... You were not charged", with Try again (which continues from where it stopped). Runs at most once per plan. A proposal's assumed sample-size settings are recorded as acknowledged because page 2 states them.
- **Credits.** Students see credits (renamed from tokens), with the balance and anything reserved in the top bar; no price line on Start. Each service can have a minimum balance (`MIN_CREDITS`, in credits; empty until the owner sets prices); Start is refused before any AI runs when the balance is below the minimum or the document's price. One charge: started with Start, the read and plan steps cost nothing on their own (their spend cap stays real) and the first document carries the plan's price (`ServiceSelection.bundled`), so a document that fails returns everything. Changes keep their own charge.
- **Funding: drafted with marked gaps.** Figures only the applicant gives (baselines, targets, quantities, unit costs, the amount) never stop a one-Start draft: they print as "[target to be added]" / "[to be added]" in text and tables, never as a zero, and their checks (FP-026, FP-027, FP-039–FP-048, CN-022) are the AUTHOR's, so the document is "Needs your input" rather than failed. Each indicator rule now checks its own field (`validators-v3`): unit, source, frequency and owner stay PaperAid's. The workspace's "Needs your input" saves the figures and `POST /works/{id}/figures` rebuilds the same text as a new version with code only, no AI and no charge.
- **Workspace.** The document as it reads on paper on the left (changed paragraphs and marked gaps highlighted on screen only); on the right: Needs your input, Ask for changes (the student's words, which part, and an optional Word or PDF for context, whose text goes to the writer with the request), what PaperAid checked (in plain words, never a mark), versions; Download Word and PDF always in the header. Proposals get one tab per chapter, "Continue to Chapter Two", and "More tools" for the earlier full proposal page (supervisor comments, evidence, details).
- **Look.** Top bar Dashboard · New ▾ · Your work · credits · Buy; PaperAid green throughout, the strongest colour only for the main action; cards with clear borders, hover and keyboard focus; the dashboard shows the student's work first. The conceptual framework is a drawn figure (grouped factors, the outcome, intervening factors dashed, arrows meaning "association examined", not cause) in the app and the Word file, with its words as the image's alternative text (`render-v3`).
- **Not built yet:** reading a university's own guide during Start (page 1 says the standard structure is used and the guide can be added afterwards); a PDF-page preview (the preview is the document's text laid out as a page; the downloads are the exact files); live counts on the progress screen.

### 2026-10-01 — Codex's verification of the one-Start release, and two owner requests

1. **No AI before the credits are there; the price reserved at Start.** Reading a brief needs the balance (and minimum) the document will take. Start reserves the document's price on the wallet (`Wallet.reservations`, keyed by the work or proposal); the document's own step turns it into its hold in the same transaction that starts it; a plan that fails, is cancelled or is stopped, a Start that does not go through, or a deleted work or proposal returns it.
2. **A failed read says so** on page 2, with "Try reading again" or "Continue without them", instead of waiting for ever.
3. **The proposal workspace shows what the complete proposal still needs**, each with its action there: approve a chapter, add the supervisor and submission date (asked when needed, not at Start).
4. **Adding figures adds only figures**: anything else changed since the document was written is refused ("ask for changes"); versions are checked again at publication; every check that depends on figures (results, budget, staffing, timeline, tables, numbers) is worked out again; a numbers-only save keeps the Results Model approved.
5. **New work never enters the earlier plan pages**: their creation links open the Start pages; a new proposal's "More tools" has no plan tab.
6. **Assumed sample-size settings need the student's own tick** beside Start; without it, PaperAid stops and asks, with "Use the standard settings and continue".
7. **A lost Start response never makes a second proposal**: the new proposal's id is kept in the address and Start is retried on it.
8. **PDF on Windows**: the compiler keeps the system variables MiKTeX needs and reports its stderr instead of "unknown error". Public copy says credits, and no longer promises a price before work runs.
- **Owner: the coursework word limit is not demanded.** PaperAid suggests: the usual limits in a list, "Enter my own", or left empty for the usual length for the level (said so in the document).
- **Owner: failures point to the exact issue.** Live, a tester's seven-word question was refused three times by a twelve-word minimum for "the assignment question" that page 2 never showed. A question of four words or more now counts; page 2 never hides a question the server still needs, and a refused Start points to the field. Failure messages name what could not be met: the requirement a draft missed, the proposal sections not finished, and the reasons a plan was not good enough.

### 2026-10-01 — Codex's second verification: a continuation that survives a stopped worker

1. **The plan's next step is durable.** Publishing a one-Start plan records it on the work or proposal (`auto_next`); the transaction that submits the draft (or first chapter) clears it, and so does a stop. A stop returns the reservation first and clears the record second, so a half-finished stop is simply repeated. Maintenance (`resume_continuations`, part of the reconcile run) finishes any continuation still pending two minutes after its plan completed; every part of it can be repeated safely, and it runs only while still pending.
2. **One reservation per Start attempt.** A second Start that loses the race returns only what it reserved (`work:<id>:<attempt>`); the document's hold, a failed or stopped plan, and deletion take every reservation of the item.
3. **Page 1 never creates a second work**: it reuses the work it created and does not upload a file twice; page 2 treats "not read, nothing reading" as a state to act on (Read my documents), never a spinner; "Continue without them" only for coursework, since a funding call is required.
4. **Reading before a document is started is capped**: besides the balance check, reads for works never started are limited per student per day (`FREE_READS_PER_DAY`, 5). Reserving the document's price at reading time was considered and not done: it would lock credits on forms students abandon.
5. **Adding figures re-measures length**: the rebuilt document is page-counted (when rendering is on) and the word and page limits checked again before the version is published.
- **Copy**: the pricing and home pages describe today's product: credits reserved at Start and charged only for what is delivered, nothing charged during testing.
- **Older work, once written, opens in the workspace** without a reload (it stayed on its earlier page after the draft).

### 2026-10-01 — Live reliability run: plans within the evidence, patience for provider outages

Six real coursework jobs on the released one-Start flow: 4 delivered (Ready with warnings, 1,287–2,297 words), 2 stopped without charge at the plan, both because the final review found claims stronger than the confirmed evidence and two repairs did not clear them. `w-plan-v2`: claims in the position and briefs stay within the evidence's population, place, dates and strength (an unsettled point is something a section will examine), and a repair changes only what the critique raised. A rerun of three hit a Google (Gemini) outage (503); both questions that reached drafting had passed their plans, including one that had failed before. Stages now wait about ten minutes for an outage (`STAGE_MAX_ATTEMPTS` 6, backoff to five minutes; completed calls replay from the job's cache) and a step that used up its retries says it could not finish ("You were not charged. Please try again in a few minutes.") instead of "We'll keep trying".

### 2026-10-02 — Codex's audit of 9239dd0

1. **Page 1 keeps one work in line with the page.** Continue, pressed again, updates the saved work's details, removes files taken off the page, adds new ones once each and replaces a changed pasted call. The saved work's id is in the address (`?draft=`), so a reload, or "Change my documents" from page 2, reopens page 1 on that same work with its documents listed.
2. **Start is one transaction.** The step's submission, marking the work or proposal started, and reserving the document's price happen together or not at all (`submit(..., reservation=)`, `submit_step(..., start=True)`). A balance that changes after the check, or a submission that fails, leaves nothing "starting" and nothing set aside. A proposal continuing after the sample-size tick records the pending step before reserving, so an interruption is finished by maintenance and the chapter holds its own price.
3. **A document added for context is kept in file storage**, never in the work or project record, and removed with its request. The writer gets its first 1,000 words, and the change box says so before it is added.
4. **A funding call that cannot be read can be replaced**: page 2 offers "Change my documents" beside "Try reading again".
5. **Reads have a firm daily ceiling**: besides the friendly limit on works read but not started (`FREE_READS_PER_DAY`), an atomic daily counter of reads of new works refuses beyond twice that allowance, whatever happens to the works.
6. **Prompts say the plan is internal**: `w-plan-v3` and `w-results-v2` no longer tell the model that the student edits and approves the plan or Results Model first.
- **Release record**: `820f862` and `9239dd0` were deployed on 2026-10-01 without being pushed or logged. Both are now in the release log, and this release is pushed.

### 2026-10-02 — Owner: PaperAid is for researchers, not university students only

Public wording addresses researchers and students: the home page says "For researchers and students", the link preview "Built for researchers and students", and guides are "your institution's guide" rather than "your university's". Service names (University templates) and the coursework service's own wording (brief, lecturer) are unchanged.
- **Wording that matches the product (same day, owner: "fix all the wrong wording").** The public pages describe all five sections (Coursework, Research Proposals, Funding, Paper Check, Academic Formatting; `PUBLIC_SECTIONS`), with their availability badges from the server. No public or New-page copy promises an estimate first or a plan the student approves for new work: one Start writes once PaperAid's own checks pass, credits are reserved at Start and charged only for what is delivered. "Results Model" and "checked by code" are no longer in student copy (what, not how). Paper Check keeps its price and estimate wording, which its flow still has; earlier plan pages keep theirs for work set up before one Start; "AI detection — coming soon" stays.

### 2026-10-02 — Codex's second look at the 9239dd0 fixes

1. **A proposal resumed after the sample-size tick reserves nothing.** The plan is done, so the first chapter starts at once and holds its own price in its own transaction. Only one Start marks the step pending (a second one, or one after the plan was approved, is refused with "already working on this"). A continuation whose document was started at the same moment by another (the request and maintenance) returns quietly instead of stopping the work, for works and proposals.
2. **A pasted call reopened on page 1 is the pasted call, not a file in the list**: the page says it is saved; pasting again replaces it, leaving the box empty keeps it. The browser journey checks that exactly one call remains.
3. **The firm read counter is per UTC day** (a calendar day, not a rolling 24 hours); the friendly limit counts the last 24 hours. Both are stated in the code.

### 2026-10-03 — Data Lab, Chapter Four from data, and Uganda maps (owner, after Claude's and Codex's reviews of the Research, Data Lab, Spatial Lab and Reports specification)

The specification is a roadmap, not one release. Funding working end to end comes first, then the shared analysis engine, Data Lab, Chapter Four in Research proposals, Uganda district maps, then the reliability work. Nothing is committed before Codex audits it.

1. **One engine, separate sections.** Reading files, data checks, cleaning, statistics, charts and exports are one engine (`app/datalab/engine/`). **Data Lab** is its own section with its own journey and its own analysis report (executive summary, dataset overview, data preparation, data quality, methods, results, key findings, limitations, conclusions; appendices: cleaning log, statistical output, data dictionary), exported as an Excel workbook with real charts and as Word and PDF. **Chapter Four** in Research proposals uses the same engine from the approved objectives and Chapter Three, and writes academic prose by objective; Chapter Five follows from it. The general **Reports** section (from documents) is later and separate.
2. **Infrastructure stays as it is.** No Postgres or PostGIS, no new queue. Datasets live in Storage (the original untouched, a Parquet copy for work), small metadata in Firestore, analysis runs in the worker. Uploads stay at 20 MB to start; processing limits (rows, columns, expanded size, memory, time) are measured and enforced; larger direct uploads come only when measured need requires them, with server validation before a file is usable.
3. **Code calculates, models explain.** Every number (counts, percentages, means, tests, intervals, effect sizes) comes from code; models see variable descriptions and computed results, never rows. Narrative may only use numbers from the result, checked after writing. p ≥ the set level is never "significant"; causal language only when the design and its assumptions support it; odds ratios are never "times more likely".
4. **First analyses, narrow and validated.** Descriptive tables; cross-tabulation with chi-square or Fisher's exact; two-group comparison (t-test or Mann–Whitney, chosen from the question and design, not swapped because a normality check failed); correlation (Pearson or Spearman). Effect sizes and confidence intervals where appropriate, with every test. Regression follows once these pass. A failed assumption is reported with its options, never silently switched. Charts only where they help. Every method is checked against reference values (R) including awkward and invalid cases.
5. **Every analysis keeps a visible record**: question, method and why, dataset version and cleaning applied, rows used of rows available and why others were left out, coding and reference categories, missing-value handling, significance level, assumption checks, library and version, date. Hidden by default ("How this was calculated"), always available, and in the report's methods appendix.
6. **Survey data are gated.** A column that may be a weight, cluster or stratum prompts a question about what it is; once a complex survey design is confirmed, unsupported statistical analysis is refused (inspection, variable descriptions and data quality still work). Weighted analysis is enabled only after it matches reference results.
7. **Cleaning is conservative and reversible.** The original is never changed; every transformation makes a derived version and records what changed. Automatic fixes follow explicit rules per column type (never converting identifiers such as "00123"); anything that changes a value, merges categories or excludes rows is a short confirmation in the workspace with a recommended answer.
8. **Privacy across every output.** Small counts (below 5 by default) are suppressed together with the cells that would reveal them, in tables, charts, map labels, narrative and Excel alike. Likely identifier columns are flagged and excluded by default. Exact household or patient points are not exported by default; releasing them is a recorded decision.
9. **Pricing.** Fixed tiers, the tier's price reserved at Start, charged for what is delivered, never raised during a run; no price before Start (the balance and reserved credits show in the top bar, the charge and any refund on the receipt). Tier sizes are set from measurement; prices from total delivery cost (failed runs, compute, storage and support included), at most 3x.
10. **Maps use the best boundary file on the evidence** (source, licence, year, codes, valid shapes, join coverage), the original kept untouched.

### 2026-10-04 — What the 2026-10-03 plan built (awaiting Codex's audit; nothing committed)

**Funding proposals.** The live funding run stopped because the final review kept moving the target: each repair round was judged by a fresh reviewer who raised new, non-blocking points. Fixed by new prompt versions (released prompts unchanged): `w-plan-v4` and `w-results-v3` (facts only the applicant can give are never invented; no claims about page limits; measurable indicators), `w-plan-review-v2` and `w-results-review-v2`. Reviews now separate blocking `issues` from `suggestions` (kept for admins, never a reason to refuse), and a repair round's review receives the previous round's issues (`previousIssues`) so it judges whether they were resolved. A template that names several required sections in one heading now gives each its own locked section (`templates-v2`, part of the engine hash; older funding engines without it are refused as changed). A live rerun after the audit confirms the fix.

**Data Lab as built.** Engine in `app/datalab/engine/` (ingest, profile, clean, stats, disclosure, charts, maps), checked against R reference values. The checks, cleaning and analyses are free; the analysis report (Word, PDF, Excel workbook) uses fixed tiers DL_SMALL / DL_STANDARD / DL_LARGE, which **have no prices yet**: until the owner sets them the report shows as not available. The report is drafted from computed results only (number tokens filled by code), reviewed by the final reviewer, and a report the review does not approve fails without charge.

**Chapter Four.** A proposal opens a Data Lab project carrying its approved objectives; each analysis is tied to an objective, and the chapter (4.1 Introduction, one section per objective, other results, summary) is written from those results with tables and figures numbered 4.n.

**Maps.** The GeoJSON (2020, 146 districts with region codes) was chosen over the shapefile, which mixed cities into districts, had a null feature, invalid and overlapping shapes and no codes. Simplified, Kabale's shape repaired, lakes drawn from the same source; licence not stated in the files. Names are matched after tidying with a short alias list; fuzzy matches are only suggestions the person confirms. Sub-regions: see the corrections below (they are in the parish layer).

**Resume from the last good step.** Starting a work, proposal or Data Lab report again after a retryable failure requeues the failed step itself (same quote, same engine) instead of a new paid step; the claim happens in the same transaction, and admin retry shares the code.

**Messages.** "Your work is ready" and "it stopped" by email (SendGrid) and SMS (Africa's Talking), each only when its keys are in Secret Manager; with neither, settings offer nothing. Each outcome is sent once, names the service and links to it, never paper text or titles. The person chooses in Settings; a phone number is kept only with consent and removed with the account.

**Reliability.** `/admin/reliability`: per service, completion, where jobs stop, time, AI cost against charges, admin retries; numbers and codes only.

**Daily canary.** `/tasks/canary` (scheduled daily) runs a writing check on a short fixed paper from a dedicated account, paid from that account's credits and refused above `CANARY_BUDGET_USD`. Every paragraph carries the date, so answers are never replayed from the cache. It alerts (log, and email to `ALERT_EMAIL` when email is set up) when the previous run failed, finished with warnings or is stuck, or when a run cannot start. Its runs are kept out of the reliability figures and listed on their own. Off until `CANARY_ENABLED`, `CANARY_UID` and `CANARY_EMAIL` are set (the account must be a tester while the tester list is in use).

**Waiting on the owner:** Data Lab report prices; SendGrid and Africa's Talking keys and a verified sender; the canary account and alert address; the payment provider; data protection registration.

**Corrections (2026-10-04, later the same day).** The sub-region list *is* in the owner's files: the UBOS parish layer's `F15Regions` field (15 sub-regions; Bugisu and Sebei combined). The Uganda boundary files are UBOS's, and the owner states PaperAid may use them in any way.

### 2026-10-04 — Codex's audit of the Data Lab set fixed; Uganda maps in full; privacy protections (owner: build every phase, after Codex reviewed the plan)

Codex confirmed the tests passed but found 13 defects in the Data Lab set and reviewed the privacy and spatial plan. The owner asked for all phases at once, tested, committed and published.

**Codex's 13 findings, fixed.**
1. *Files and races:* every version, profile, analysis, chart and export is written under a name of its own before the record names it; old files are deleted only after the record changed; a daily sweep removes files no record names once two hours old. Data work runs one piece at a time per project.
2. *Small counts:* totals are part of the table (a row, its total and the column of totals each a line), zeros included; every hidden small count is audited by linear programming until the range it could take is at least the threshold wide; one neutral mark (–) for every hidden entry. In a 2×2 table with hidden counts the test's numbers are withheld (they would reveal them). Counts in running text, the quality and cleaning tables say "fewer than N". A brute-force test confirms no hidden count can be narrowed on random tables.
3. *Coordinates* are left out by default like names; including a flagged column is a recorded decision (who, when) named in the report's methods. The report workbook holds no records; the cleaned data is a separate file for the researcher, with a cover saying what it holds.
4. *Out-of-date results:* every analysis has a fingerprint of the data and every setting it used (variables, threshold, significance level, survey answers, rules, map layers); a mismatch marks it out of date, kept out of reports and workbooks; settings can't change while a report is written, and the fingerprints are checked again before publishing.
5. *Final review:* the whole document is assembled first and the final reviewer reads exactly it (in parts with a manifest when long); every rule needs an explicit PASS (`d-report-review-v2`, rules R1–R8, R9 for Chapter Four); required sections must have real content; the approved document itself is exported, never rebuilt.
6. *Chapter Four:* the approved plan and Chapter Three are read at Start, frozen with the job and checked again at publication; Chapter Three's methods reach the writer and the reviewer (`d-chapter4-v2`); objectives follow the proposal, a changed objective's analyses must be linked again; an objective with no analysis stops Start until the student confirms, and the chapter then says so.
7. *Admin retry* claims the project, work or Data Lab project in the same transaction as student resume.
8. *Record size:* long cleaning details live in file storage; a project record is refused above 800 KB.
9. *Inputs:* checked before anything reads them; constant groups and any non-finite result are "can't be estimated", with the reason.
10. *Import:* a mix of dates and date-times is kept; whole numbers beyond 2^53 stay exact, as text (LONG_NUMBER); a workbook with formulas whose results Excel never saved is refused with the reason.
11. *Messages:* the message a job owes is recorded on the job in the same transaction as its outcome (`state.transition`); each channel's delivery is recorded; failed sends are retried with growing waits by the reconcile task.
12. *Canary:* the day is claimed atomically (a scheduler retry returns that day's run); `?rerun=true` is a deliberate extra run with its own text.
13. *Worker:* reading files, cleaning, analyses and the cleaned-data file run in the worker (`dop_` tasks through the same queue). Measured on files at the upload limit (2026-10-04): 200,000×12 rows read in 1.5 s and profiled in 5 s; 20,000×300 profiled in 7.5 s (after making profiling vectorised); analyses under 1 s, charts about 1 s, a map 2–8 s; peak traced memory under 200 MiB on the 2 GiB worker. A piece of data work longer than 10 minutes is treated as stopped.

**Uganda maps in full.** Levels: districts (2020, 146), subcounties (2021, 2,181 after joining the pieces of split features; always matched with their district), sub-regions (15) and regions (4) made from districts. Sub-regions are assigned to 2020 districts by area overlap on full shapes in Arc 1960 / UTM 36N: 145 districts at 90% or more; Kalangala (86% Central I, 14% Greater Kampala) confirmed by the owner as Central I. Data can be records (counted, or a number averaged) or area totals (the count, or a rate per 1,000 of a population column; an area appearing twice is refused). A region, a sub-region or a filter on the districts zooms the map, with neighbours in grey. Every map: "Boundaries: Uganda Bureau of Statistics (UBOS), year", and "Boundaries are shown for analysis and imply no position on any border." Released layer files are frozen by hash (`app/datalab/geo/released.json`).

**Filters on any variable** (every analysis): a category's values, a range of numbers or dates (a date's upper bound includes the whole day), up to five combined; missing values never match and are counted apart; columns that identify people or places can't be filters. Subtraction rule: a filter keeps at least the threshold and leaves out none or at least the threshold. Results released together (a report, the report workbook) are checked as a set: two whose filtered records differ by fewer than the threshold are refused with the pair named. *Known limit:* the set check compares filters, not the complete-case differences missing values create.

**Privacy.** Countries fail closed: only Uganda is open; data from any other country (or one not listed) is refused at upload with the reason (`app/datalab/countries.json`), and maps follow the same list. Terms (version 2026-10-04, plain wording until the lawyer's replaces it as a new version): accepted at sign-up and recorded on the account, asked again before any paid step or Data Lab upload. Every upload carries two confirmations (the right to use the data; identifiers removed or left to PaperAid), recorded with their wording version, the terms version and the time. Identifier rules are one file read by the server and the browser (`app/datalab/engine/identifiers.json`, with exceptions for place and organisation names); a CSV is scanned in full in the browser and ticked columns are removed before it is sent, named in the cleaning record; Excel files are checked after upload and flagged columns left out. Decimal commas: a column written 1,5 or 1.234,5 (or, in a semicolon file, 1.234) stays as written until the researcher confirms reading it as numbers, with a preview.

**Proposals.** The default rulebook is "the standard guide" everywhere people see it. The title page prints the student's own institution (a new field), else the one in their uploaded guide, else (projects from before) what it printed. Where an uploaded guide departs a lot from the standard guide (a core section missing, objectives, page range, formatting), each point is put to the student: keep the guide's, or take the standard guide's (a new profile); Start waits until every point is answered.

**Private mode: measured, not built.** Chrome emulating a mid-range Android phone (4× slower CPU, 4G) ran the real engine in Pyodide: 50 MB to download; about 5½ minutes before the first analysis (start 48 s, packages 132 s, importing the engine 148 s); a 20 MB CSV read, profiled and checked in about 2½ minutes; analyses 0.5–7 s; a map 63 s; Word and Excel 4–5 s; about 840 MB of memory; results identical to the server's (R's reference t = −1.860813). Every target failed (≤ 35 MB, ≤ 10 s). Private mode and the paid private report stay unbuilt; the owner decides between a lighter browser engine, laptops only, or processing on the server without keeping anything.

**Other countries.** `scripts/import_boundaries.py` imports a pinned, licence-checked geoBoundaries layer and registers it FROZEN (`app/datalab/geo/registry.json`): Kenya's counties (2020, public domain) and Rwanda's districts (2012, CC BY 4.0) are imported. Any chapter structure in uploaded guides is a separate release (Codex).

**Still waiting on the owner:** Data Lab report prices; SendGrid and Africa's Talking keys; the canary account and alert address; the payment provider; legal advice (terms wording, data processing agreement, privacy policy, Uganda's transfers abroad, each other country) and Uganda PDPO registration; a decision on private mode.

## 2026-10-04 — Data Lab in two sections, interviews analysed, and what the live check found (owner: "divide it into quantitative and qualitative ... on one page")

**Two sections, one page each.** Data Lab opens on Quantitative data (a survey or records: describe, compare, relate, correlate, maps, filters, report and workbook) and Qualitative data (interviews, focus groups, open answers). A project is one page: numbered sections that fold away (your data, checks, analyses and maps, the report or Chapter Four) instead of step tabs. The New page offers "Analyse numbers", "Map my data" (opens the map analysis) and "Analyse interviews"; the public pages list every analysis, maps of Uganda included.

**Qualitative analysis** (`app/datalab/qual.py`, prompts `q-code-v1`, `q-themes-v1`, `q-review-v1`). Each transcript (text, Word or text PDF, or pasted) is kept only after the names the researcher lists, and any phone number, email or ID number, are replaced; the researcher confirms consent and the data's country (Uganda only, as for datasets). The analyst codes the transcripts with quotes; code keeps a quote only if it is in its transcript word for word; the writer groups codes into themes that answer the research question, citing quotes by reference, and code places every quote and counts "Found in X of Y transcripts"; the final reviewer reads the assembled report (rules Q1–Q6), with repair at most twice. Delivered: a report (Word, PDF) with a codebook appendix, and the codebook in Excel (themes, codes, quotes). No codes or an unapproved report: nothing charged. Prices QL_SMALL / QL_STANDARD / QL_LARGE (by words and transcripts) are the owner's to set; until then the analysis shows as not available yet.

**Live check (real models, 2026-10-04).** Passed: AI check with source check, refine (light) with formatting, redraft, formatting only, the qualitative analysis (three themes), Data Lab analyses, map and filters. Fixed:
1. *Data Lab reports and Chapter Four could never be approved.* The reviewer objected to text PaperAid's code writes (the dataset paragraph read "no variable was left out of the analysis" as "all were analysed"; the statistical-output appendix and the Chapter Four introduction were called unsupported because the reviewer was not given the records they come from), and the writer cannot repair code's text. The dataset paragraph now names the variables the analyses used; the reviewer (`d-report-review-v3`) is told which paragraphs code wrote and given the dataset facts and each analysis's full record; an analysis the researcher chose with a method Chapter Three did not name passes R9 when the text says so.
2. *Funding proposals without the applicant's figures could never be approved.* The reviewer failed FP-028 (targets plausible against baselines) because the applicant had not yet given baselines and targets, which One Start drafts as gaps; while every indicator's baseline or target is a gap, a FAIL on FP-028 is not an objection (code knows; the prompt already called it not applicable). The run's other objections (an output worded as an activity, raised only in the last round on unchanged text; baseline timing) remain to be re-checked live.
3. *An empty provider balance looked like an outage.* OpenAI's "no credits remaining" (429) was retried for 14 minutes and the student told to try again; Anthropic's "credit balance is too low" (400) said the document could not be processed. Both now stop the step as a configuration fault (refunded) and raise an operations alert once a day.
Stopped when the OpenAI balance ran out (about 10:42 UTC): coursework, concept note, academic concept paper, research proposal, and the re-runs of fixes 1 and 2. To be run again once credit is added. PaperAid's recorded spend since 25 September is $10.94 on the live site (Sol $2.98) and about $2.20 for this check.

## 2026-10-04 — Codex's audit of 8ebecb4..6373ceb: all 13 findings fixed, with a regression test each (`tests/test_audit_20261004.py`)

1. *Transcript identifiers:* phone numbers in any common layout (+256 772 123 456, 0772 123456, 0772-123-456, (0772) 123 456, 256772123456; only runs that start like a phone number and hold 9 to 13 digits, so years and figures stay); names with possessives; the label and the file name pseudonymised like the text; a replacement code that contains a word of a listed name, or a contact detail, is refused; the text, label and name are checked again before storage; transcripts are cleaned again before any model call.
2. *Quotations the reviewer never saw:* every quotation that ships is in the reviewed report (Appendix B. Quotations, each with its reference); the Excel codebook is built only from the rows approved with the report (both in the approved hash). A quote that would identify someone is withheld by the writer (`q-themes-v2` "withheld"; `q-review-v2` names the quote to withhold) and then appears nowhere.
3. *Small denominators:* a rate map protects the populations like the counts; an area is hidden (count, population, rate) when either is unsafe. Also found: a hidden row's place in a value-ordered table hinted at its value; hidden rows now follow the shown ones by name (maps and category summaries).
4. *Released together:* every analysis records the rows it actually used (after missing values, unmatched places and other regions were left out) as a compressed bitmap; the release check compares those rows (filters only for analyses from before).
5. *Funding:* review issues name their rule and statements (`w-results-review-v3`); while the applicant's figures are gaps, objections tied to the figure rules (FP-028 and the student-figure rules) don't block, and genuine defects still do. After a repair the reviewer gets its earlier classifications, each statement's hash and the list of changed statements; a classification reversed on unchanged wording counts only with its reason. Saving figures marks FP-028 for the applicant to check (NEEDS_REVIEW), never as approved.
6. *Worker ownership:* each claim of a data operation has an attempt token; only that attempt commits or fails it, and a superseded attempt deletes only its own files, never the shared upload.
7. *Model-input bounds:* a transcript paragraph longer than a coding batch is cut at sentence ends; a report section longer than a review part is split (paragraphs, bullets, table rows, cells), and the bound counts what every part repeats (dataset facts, records, the manifest) and settles as the manifest grows.
8. *Quotations as written:* a quote is found ignoring case, typographic quotes and spacing, and exported with the transcript's own characters.
9. *Concurrent uploads:* the transcript count and word limits are checked again inside the transaction; only the rejected attempt's file is deleted.
10. *Totals maps:* records used are the rows; the summed total is stated apart (only when nothing is hidden).
11. *Messages:* alerts claim with a unique token; a job's outstanding channels and retry time are decided inside the claim and only the lease holder records results.
12. *Reports:* a request naming a removed analysis is refused (UNKNOWN_ANALYSES); the page drops removed or out-of-date analyses from its choice.
13. *Provider problems:* estimates raise the same daily alert as steps (`notify.provider_problem`); messages no longer claim the team was notified, only what happened ("PaperAid recorded the problem", "isn't available right now").

**Not yet verified with real models** (the OpenAI balance is empty): the new prompt versions `q-themes-v2`, `q-review-v2`, `w-results-review-v3`, `d-report-review-v3`.

## 2026-10-04 — Calm academic redesign, after Jenni (owner: "the appearance has to be Jenni"; decisions: indigo-blue accent, left sidebar, live demo instead of video)

Jenni's public site, sign-in and help-doc app screenshots were measured in a browser (type, colours, spacing, radii, shadows, motion) and PaperAid took their discipline, not their assets: the logo, exact colours, wording and images stay PaperAid's (no pixel copy, to avoid passing off).
- **Foundations** (`styles/globals.css`): an indigo-blue accent (#3f4be3, close to Jenni's but PaperAid's own) on white and neutral greys (#f9fafb, #e5e7eb, text #101828 / #4a5565 / #6a7282); corners 8 px for controls and 12 px for cards; hairline borders and near-invisible shadows; large headings at weight 500; section labels as small uppercase text in the accent, never pills. Buttons 36 px (48 px in the hero) with a faint inner highlight. A new mark: a page whose path forms a P, with a small spark.
- **App shell**: a left sidebar (New, Home, Your work, then the sections: Coursework & funding, Research proposals, Data Lab, Paper Check, Academic formatting; Credits, Settings, the account at the foot) and a slim top bar with the balance. On phones the sidebar is a drawer. Documents sit on white, without the grey frame or sheet shadow; tinted icon tiles became neutral outlines; one main button per screen.
- **Public pages**: Jenni's order with PaperAid's content and only true claims (no university logos, user counts or invented results): a centred hero, the live product demo (no video: Jenni has none either), the sections, three steps with large faint numbers, features alternating text and illustrations made of product elements with placeholder lines, what PaperAid never does, who it's for, pricing, an FAQ, a calm final call to action and a dark footer. Sections fade and rise once as they come into view (reduced motion honoured).

**Follow-ups the same evening (owner):** the dashboard leads with a greeting and a row of quick-start buttons, then only the four latest pieces of work ("Continue working", with "See all"); the empty top bar is hidden on wide screens while credits are off. On the home page "What PaperAid does" comes before "How it works"; the research section is "Academic research and coursework" (concept paper and proposal through Chapter Four's results); Geospatial analysis has its own section with an example Uganda district map (UBOS boundaries, shading illustrative); funding is "Funding concept notes and proposals". **Credits are equated to no currency anywhere a student or visitor reads (PaperAid is international):** "One credit is UGX …" and "mobile money" are gone from the public pages and the Credits page; the ledger stays in UGX internally and admins still see it.

**Live home page (owner, 2026-10-05):** every feature illustration is a short live loop with a ghost cursor, built from the product's own elements and example content: a chapter written with a confirmed source, then Chapter Four's table; a comparison run, explained and added to the report; maps of several countries cycling (Uganda by UBOS district; Kenya's 47 counties from geoBoundaries, public domain; Tanzania, Nigeria, Ghana, South Africa, India and Brazil from Natural Earth, public domain), each captioned honestly ("PaperAid maps Uganda today; more countries are being added"); the call's requirements checked and the applicant's own figure added without AI; a passage marked, redrafted and formatted. The hero demo rotates four topics with real citations (social media, malaria bed nets, machine learning in hospitals, drought and yields). Loops run only on screen; reduced motion shows one finished frame.

## 2026-10-05 — Second audit fixes (owner: implement locally, test without paid model calls, hand over to Claude)

This supersedes the earlier rule that an unexplained classification reversal keeps the previous classification.

- **Final approval:** Sol's latest classification is never replaced by an earlier pass. A reversal on unchanged wording must explain the actual before/after classifications. Otherwise the review is NOT_REVIEWED (REVIEW_CLARIFICATION); the same candidate is sent to Sol for clarification within the existing three total review rounds, with no additional writer repair for clarification. Exhausted, unavailable or unaffordable clarification never approves. New released prompt: `w-results-review-v4`; older prompts are unchanged.
- **Transcript privacy:** phone matching protects adjacent numbers and years; Unicode quotation lookup maps each normalised character to its original source position. New transcripts and frozen transcript inputs record anonymisation version 1. Older records lack this evidence: remove and re-add them with the participant-name replacements before analysing. Start refuses before a hold, and the worker refuses an older frozen input before model calls. No originals or replacement-name dictionaries are saved.
- **Row identity:** filters retain original indexes through complete-case and map selection. Analysis fingerprints now include rowIdentity version 1: older analyses are out of date and must be rerun before inclusion in a new report or workbook. Previously generated reports are not deleted.
- **Review bounds:** document sections are split with allowance for repeated evidence, the complete manifest and the request envelope. Both Data Lab final-review entry points check the actual JSON request against 7,000 words before any provider call. Inseparable supporting evidence that cannot fit stops with REVIEW_INPUT_TOO_LARGE and no delivered-report charge. Evidence is not silently shortened or reviewed out of context; automatically partitioning that shared evidence remains a possible later enhancement.
- **Messages:** an SMS is accepted only when the expected recipient's response reports statusCode 100, 101 or 102. Invalid numbers, unsupported recipients and opt-outs are terminal failures, while temporary problems retain bounded retry. Sender/account/balance faults raise an owner alert. Accepted means provider acceptance, not confirmed handset delivery. Permanent failure of one channel does not stop retry of another.
- **Public demonstration:** the research illustration links the actual RTS,S Clinical Trials Partnership (2015) trial, PMID 25913272, with a claim supported by its abstract. The sample results table is explicitly illustrative and makes no claim that its hardcoded numbers were calculated by the live engine.
- **Regression proof:** the shared-upload test requires an existing upload, passes it to the superseded worker's cleanup, and checks that the shared upload remains while the late attempt's own artifact is removed. The unconditional `or True` is gone.

Implementation and tests are local. This entry does not record a commit, deployment or real-provider verification. Claude's handoff contains the final test results and release considerations.

**Claude's audit of these fixes (2026-10-05):** all seven reproductions fixed; full backend suite 893 passed; Data Lab, One Start and main browser journeys passed. One follow-up fixed: dots no longer count as phone-number separators, so a run of decimals ("0.25 0.30 0.45") is no longer read as a phone number. Real-model checks of `w-results-review-v4` and real SMS sending wait for credit.
## 2026-10-06 — Local Vertex Gemini architecture (owner's explicit phase instructions)

Add an ADC-backed `vertex:*` provider with the official Google Gen AI SDK. Preserve `openai:*`,
`anthropic:*` and `google:*` exactly as separate provider routes. Production/default routes remain
the current ones. No deployment, production changes, commit, push or billable model requests in
this phase. The target model account is project `paperaid`, location `global`; this does not move
Firebase, Firestore, Storage, Tasks or Cloud Run out of the existing project `paperaid-ca172`.

Central logical roles and capabilities select models for NEW engines only; concrete IDs, optional
fallback chains, capability declarations, project/location and verified rate records are frozen
in the quote. Task overrides opt in selected tasks, or `PAPERAID_GEMINI_ROUTING_ENABLED` opts in
the central task classifications. Both mechanisms default off. Gemini 3.8 Flash is the only
configured/confirmed model. Routine/writer/reasoner/reviewer/search bindings use that model;
multimodal, image, audio, live and embeddings roles remain unconfigured. A supported model
capability does not imply PaperAid has implemented its service adapter.

Vertex prices are UNVERIFIED until configured with rates and an explicit verification source.
Unverified pricing blocks both quotes and AIRunner calls; no copied Developer API rates and no
customer billing guesses. Additional billable units have explicit USD/unit rates. Fallbacks
are Vertex-only, capability-compatible and no more expensive in any configured dimension.
No fallback after a billed response, refusal, invalid schema or authentication failure.

Grounded JSON uses Google's Google Search tool and retains source URLs, queries, citation
segments and Search Suggestions privately. Missing metadata/unsupported requests fail clearly.
Google Search has no equivalent to OpenAI's exact max_tool_calls: post-response query checks
can refuse an excessive result but cannot prevent provider overrun. Search defaults off and
is explicitly blocked in production until combined structured/grounded behavior, redirect
sources, suggestions display and query-budget handling are verified. Deterministic operations
remain outside the LLM. See `docs/Vertex_Local_Phase_20261006.md` for the implementation report.

## 2026-10-06 — Local verified Vertex pricing phase (owner's explicit instructions)

This entry supersedes the preceding phase's UNVERIFIED status for **Vertex Gemini 3.8 Flash,
Standard, Global only**. Official pricing was checked at
https://cloud.google.com/gemini-enterprise-agent-platform/generative-ai/pricing on 2026-10-06.
No actual environment file, production route, Cloud Run setting, IAM role or secret was changed.
No additional model request, grounding request, commit, push or deployment was made.

- Published USD per million tokens through 2026-12-31: input 0.75, output including thinking
  3.75, cached input 0.075. Beginning 2027-01-01: input 1.50, output including thinking 7.50,
  cached input 0.15. Rates and source/effective-date/scope metadata live in
  `app/ai/vertex_pricing.py`. We do not backdate this newly verified schedule before 2026-10-06.
- The source describes introductory rates as 50% credits back on eligible net spend.
  Reconcile the net rate with the Google billing statement before customer billing. The
  separate $300 Cloud promotional credit is never subtracted from PaperAid model unit prices.
- Selection uses the UTC date at quote creation, including in a process with cached Settings.
  Each engine freezes one flat price record; neither that record nor the legacy price tables
  is rewritten on the January transition. An uncached model call outside its frozen rate's
  period stops before the SDK with VERTEX_PRICE_PERIOD_CHANGED and needs a new quote.
- Visible response and thinking token counts are stored separately; output_tokens remains
  their combined billable quantity. Decimal arithmetic prices that quantity exactly once and
  prices cached reads at the discounted input rate. Per-call cost retains precision at the
  existing float boundary; job totals still follow the established six-decimal rounding.
  Explicit Vertex cache creation/storage is not implemented/priced and fails closed.
- Gemini 3 Search metadata records 5,000 free queries/month aggregated across Gemini 3 models,
  then USD 14/1,000 individual queries, not requests. Repeated returned queries are counted.
  Google Search-provided input is informational, not added to paid input tokens. There is no
  billing-wide allowance counter or reconciliation, so this metadata never becomes a flat
  fee or per-student free allowance: customer grounding pricing remains gated. Search remains
  off by default and blocked in production.
- Text-only Vertex quoting can now use verified prices without legacy provider keys.
  Quotes that require Vertex grounding remain unavailable. Routing still defaults off;
  settings alone are not evidence of ADC, IAM or live job readiness. Unverified models and
  wrong endpoint locations remain unavailable. Explicit VERTEX_PRICES={} disables the registry.

See `docs/Vertex_Pricing_Phase_20261006.md` for tests, files and the handoff for the next offline phase.

## 2026-10-07 — Vertex infrastructure only; no function/model strategy approved

Owner's instructions began 2026-10-06 and supersede any implication that the earlier migration's
Gemini role bindings/task classifications were approved for use. Keep those assignments in
place for the owner's decision; report them explicitly rather than silently removing them.
Automatic routing remains off and task overrides empty by default. No final model or thinking
level is assigned to a PaperAid function. No mapping-strategy tests in this phase.

Complete a provider-level explicit-model generation interface with request sampling, schema,
thinking, media, tools/grounding and safety parameters. Preserve namespaces and the existing
structured wrappers; provider task labels do not determine model choice or capability needs.
Forward the caller's system instruction exactly, including grounded requests, rather than
adding the previous adapter's grounding instruction. Existing PaperAid prompts are unchanged.
Tools are declarations only: caller handles any later turn, never automatic execution.
Models/capabilities are declared outside the provider; unsupported requests fail clearly.
Clients are reused safely across concurrent starts and closed at process exit.

No workflow, academic methodology, deterministic analysis, pricing/credits, formatting,
citations, customer-facing behavior, actual environment configuration, production, IAM,
commit/push or paid model call changed. Source/test changes are local and uncommitted.
See `docs/Vertex_Infrastructure_Phase_20261007.md` for all 20 requested report items,
the retained assignments with locations, Cloud Run requirements and the 156 passing offline
provider/schema/usage tests. Model/function strategy awaits the owner.

## 2026-10-07 — PaperAid's AI runs on Gemini through Vertex AI (owner: "finish the Gemini integration", Claude's final pass over Codex's three phases)

The owner's prompt authorised the whole integration: review Codex's work, complete it, test it with
real calls, grant the worker's access, deploy and verify production. Architecture and operations:
`docs/Gemini_Vertex_Handoff_20261007.md`.

- **New jobs use the Gemini workflow** (`GEMINI_WORKFLOW`, on): intake (3.5 Flash-Lite), planner,
  research, execution, first audit, fix and final sign-off (3.8 Flash), premium audit (3.1 Pro
  Preview), and a second check (Flash-Lite) so the AI check keeps two independent assessors. Thinking
  levels per stage are settings. The premium audit approves each deliverable; every re-review after a
  repair is the lighter final sign-off, shown the earlier findings (`signoff-v1`). This supersedes,
  for new jobs, "Sol alone approves" (2026-09-30); frozen older jobs keep their quoted roles.
- **Kept from Codex:** the separate `vertex:` provider over ADC and google-genai, response JSON schemas
  validated again locally, usage normalisation (thinking billed once, search-tool input free), the
  error classification, the dated verified price records, freezing everything into the quote.
- **Changed from Codex:** logical roles replaced by the owner's stages; routing on for new engines;
  `VERTEX_PROJECT`/`VERTEX_LOCATION` instead of `GOOGLE_CLOUD_PROJECT` (Firebase pinned to
  `GCP_PROJECT`); grounding enabled and priced at $0.014 a query; grounding redirect links resolved
  to their pages (live: with a JSON answer Vertex returns no source list); extra queries charged, not
  failed; a search Google declines (RECITATION) finds nothing instead of failing the step; thinking
  room added to every output limit (Gemini counts thinking against it); Pro's long-context tier
  priced; a timeout counts against the cap at its estimate; the premium audit falls back to 3.8 Flash
  when the preview model is rate-limited (seen live); release scripts replaced by `release.sh`.
- **Not used:** `gemini-3.5-pro` answers in Vertex but has no published price.
- **Access:** custom role `paperaidVertexInference` (`aiplatform.endpoints.predict`,
  `serviceusage.services.use`) in project `paperaid` for the worker's service account only.

## 2026-10-07 — Codex's audit of the Gemini integration: eight findings fixed; terms re-accepted; no provider names (owner)

- All eight findings confirmed and fixed (details and tests: handoff §8, `tests/test_audit_20261007.py`):
  search spend reserved at 3 queries per allowed search and capped after an overrun; billing-unknown
  calls reserve their estimate apart from confirmed cost; usage recorded and the raw answer saved
  before bounded link resolution; every priced quote carries its content fingerprint so an older
  image refuses it; sign-off history per part, not doubled, bounded; links found in decoded JSON;
  provenance limited to what was shown; transcripts disclosed in the terms.
- Owner: no AI provider or model names anywhere students look (terms, privacy summary). Admin views
  keep the model of each call.
- Owner: accepting the terms carries on the step that asked for them; "Not now" stops it. Terms
  version `2026-10-07`, so everyone accepts once more.
- Rollback is controlled: pause processing, switch traffic, resume (`release.sh` prints the steps).

## 2026-10-07 — Coursework graphs, one repair limit, capacity for 20 students (owner: "a student can't sit for over 40 minutes")

- A coursework question asking for graphs or numerical illustrations is answered with a graph PaperAid
  draws from the writer's data and an illustrative worked-example table, both labelled by code
  ("(illustrative values)"); prompts `w-draft-v2`, `w-repair-v3`.
- One repair limit per draft across section checks and the final review; stop when the final review
  repeats itself; targeted part repairs; parallel integrity and evaluation; lighter thinking for research
  (LOW), checks and sign-off (MEDIUM); a visible checking/repairing round; retries reuse checked sources.
- Twenty steps at once (queue and worker), throttled Gemini calls retried within seconds.

## 2026-10-07 — The AI checker is hidden; live-test fixes (owner: "first hide AI checker")

- The "Check for AI" step is hidden until a validated detector (for example ZeroGPT's API) is integrated:
  `AI_CHECK_ENABLED` (default off) makes `AI_CHECK` "soon", so it is neither offered nor accepted by the
  server. Paper Check stays open and starts at Redraft (light, standard, deep), with Ask for changes,
  Check my sources and Format; while the check is hidden it takes Word files only (a PDF could only be
  checked). A redraft still reads the paper internally to choose what to change.
- Live tests on real Gemini (synthetic content) found and fixed: a whole-chapter "Ask for changes"
  request is answered by revising the sections it concerns (it was left open and called a supervisor's
  comment); an institution profile's final review is told which values PaperAid filled from the standard
  profile (`from_standard`, prompt `p-profile-review-v2`) and a guide's "no more than four objectives"
  is kept; each Vertex call's timeout follows its own token allowance (up to 290 seconds), so a
  HIGH-thinking step is no longer cut off at 180 seconds and retried.
- The admin job page shows each AI call's step, workflow stage, thinking level, fallback (for example a
  premium review answered by Flash while Pro was busy), error and any reserved amount.


## 2026-10-07 — Codex's review of the Gemini release: eleven findings fixed

All eleven confirmed in the code and fixed, each with a regression test (tests named after the finding):
1. The Google SDK retried timed-out and disconnected requests on its own (whatever status codes it was
   given), so one call could be sent up to four times, each possibly billed and unrecorded. The SDK now
   never retries; PaperAid retries only 429 and 503 (neither billed), at most four attempts.
2. A parallel check's spending reservation is released only after the call's cost (or unknown billing) is
   saved.
3. A revision keeps the graph and the illustrative example of the sections it does not change; a
   compressed or repaired example keeps its label.
4. Worked examples and drawn graphs belong to coursework only; their numbers may be used only in the
   example and in sentences about it, never in a factual claim.
5. A failed step's research is reused only when every research input (question, files, specification,
   plan, notes, private words) and the engine are the same.
6. A whole-chapter request is applied when every section it names (found by code) was revised; one met
   only in part stays open.
7. The final review stops early only for the same objections in the same place saying much the same, not
   for a different weakness under the same rule.
8. Every final-review request, with all it repeats (specification, rules, context, manifest) and room
   for earlier findings, fits FINAL_PART_WORDS.
9. An answer without usable usage reserves the part of its estimate its counts do not cover.
10. Older engines' OpenAI/Anthropic routes run only with `LEGACY_PROVIDERS` on (owner: Gemini only); off,
    a retried or resumed older job is refused before any spend. Production had 5 expired quotes and 4
    failed jobs on older engines.
11. The daily canary keeps its AI check while the check is hidden from students (its own account only).


## 2026-10-07 — Codex's third review: eleven more findings fixed by Codex, checked and completed by Claude

Codex fixed all eleven findings of its review of 6eaa1ee in the working tree; Claude reviewed every change,
fixed four gaps, added one regression test per finding (`backend/tests/test_codex_20261007b.py`) and ran the
full suite and the five browser journeys.
- Worker ownership (`lease_owner`, attempt-scoped artifacts); Data Lab disclosure-v3 (counts, missing-value notes,
  cleaning notes and reviewer inputs protected, including by subtraction; an analysis that uses or leaves out
  fewer people than the threshold is not shared); whole-request bound for final reviews; locations keep section
  numbers; a chapter request is applied only when every section it targets changed; total deadlines for source
  pages and throttle retries; stale browser responses ignored; explicit graph removal; protected large CSV
  exports; distinct legend limits.
- Claude's corrections: the results page and research reuse read attempt-scoped files (they read the old shared
  paths: every new result would have opened as the uploaded paper with no changes); a worked example's numbers
  are allowed in sentences that open as hypotheticals ("Suppose…", "In this example…"), not in none (the
  economics coursework could not be explained); "the figure" meaning a number is not a missing exhibit; source
  pages get 10 s per network step within 30 s (3 s per step lost slow academic sites); the review manifest lists
  each section once with the parts it spans (listing every piece made further splitting grow the request); the
  sign-off's history room is proportional; the new job fields are classified for support views.
- Owner decision pending: an analysis leaving out 1-4 people (for example a few missing values) is now withheld
  under the "leave out none or at least the threshold" rule. Real datasets with a few blanks will see more
  "cannot be shared" results.

## 2026-10-08 — Four follow-up corrections (local; awaiting Claude's tests)

The owner asked Codex to implement the four confirmed remaining findings. Testing remains with Claude.
- Worked-example prose requires explicit hypothetical framing. "For example", "For illustration" and
  "To illustrate" no longer exempt a factual sentence from numeric evidence checks. New prompts are
  `w-draft-v4` and `w-repair-v5`; released older prompts stay intact.
- Graph removal must target the graph itself. Instructions preserving the graph win over conflicting
  removal wording; deleting a paragraph, table or graph caption does not remove the graph.
- Data Lab's review manifest lists each original section once, with the range of parts it spans.
  Exact request-size checks remain; genuinely oversized repeated context still fails safely.
- Work and proposal pages reset on route-ID changes, reject responses older than the latest displayed
  response or server record, and invalidate pending refreshes after a saved change. Slow polling may
  still display useful progress while a newer request is pending.
- Regression cases now include the unnamed "Use future tense throughout" request (partial and complete
  revisions), long report/Chapter Four reviews, and deliberately reversed page responses in both unit
  tests and a local synthetic browser journey. These additions have not been executed by Codex.

No deployment, commit, push or paid model request was performed for these corrections. Strict Data Lab
disclosure is unchanged. Handoff: `docs/Codex_Handoff_20261008_Four_Fixes.md`.


## 2026-10-08 — Research proposals follow the UCU handbook to the letter (standard guide v2); the owner's objective cap

The handbook takes precedence, with one deliberate exception set by the owner.
- **Owner's rule (overrides the handbook's two to five):** Bachelor's, Postgraduate Diploma and Master's proposals
  take **three** specific objectives, **four only when the student asks** (a choice on the Start page). PhD follows the
  handbook (two to five). Concept papers: the handbook's three to five within the same cap. Research questions avoid
  the past tense unless the study is about past events (flagged for review, never blocked).
- **Handbook fixes (rulebook `ucu-2018-v2`, the new default; v1 stays for proposals under way):** the general (main)
  objective is stated under Objectives of the Study with the specific objectives (§5.3.3; no separate Purpose
  section); a primary research question precedes the specific questions (vetting form, p. 51); hypotheses are stated
  as null and alternative (§5.3.4); a short Chapter One conclusion (§5.3); a PhD states its original contribution.
- **Code, not the writer, places the approved statements** (Codex review): the general objective, specific objectives,
  primary question and specific questions (or hypothesis pairs, or propositions) are copied word for word from the
  approved plan after drafting and after every repair; the writer adds only an introduction. Code checks them on the
  delivered chapter; a missing or altered one blocks a complete export. The plan review repairs plans that break the
  count, primary-question or hypothesis-pair rules (prompt `p-plan-v3`). A proposal's length for its level is checked
  on Chapter Three (warning). Uploaded faculty guides get the same code placement for new profiles.
- **The reviewer is told the placed statements are the approved plan** (live run 2026-10-08): with the brief "one short
  introduction only", the final review asked to remove the placed objectives and questions, which code puts back, so
  Chapter One could never be approved. The v2 briefs now describe both parts (the writer's introduction, then the
  placed statements, never to be changed or removed); a faculty guide's own brief gets the same note added by code. The
  writer's introduction (up to two paragraphs) is kept, including one that opens "To address these gaps, the study's
  objectives ..."; a line that lists or repeats an approved statement, or a bare "To ..." objective, is dropped.

## 2026-10-08 — A simpler proposal Start, guide alignment after Chapter One, the conceptual framework reworked

The owner approved Codex's recommendations on the proposal Start page, the institution guide and the conceptual framework.
- **Start page.** One line: "PaperAid writes to the standard research structure." Only the student's name is required.
  Where the study takes place and who it studies are optional ("Leave blank for PaperAid to suggest this from your
  topic"); the design defaults to "Recommend an approach" (no guess from title keywords), with an optional "design your
  supervisor requires" carried in the notes; registration number and faculty are optional (a blank one prints no line
  and no longer blocks the complete proposal; supervisor and date still do). No sample-size tick: standard settings never
  stop a proposal; the chapter says where they were assumed and Chapter Three asks the student to confirm them
  (`C3-ASSUMED`, NEEDS_REVIEW). A consent given on the earlier page is still recorded as before.
- **Proposed, until confirmed.** What the student left blank and PaperAid proposed (`ProjectView.proposed`: study area,
  population, design) shows in a "Confirm your study setting" card beside the chapter. Confirming or correcting it
  (`POST /projects/{id}/setting`) is the student's own edit: the plan stays approved, and a corrected value marks the
  sections built on it for review. The design is changed in the plan (More tools).
- **Align with my institution's guidelines.** A guide can be uploaded and read after chapters exist. Reading it
  restructures every written chapter by code (`pipeline.align_document`), each as a new version with the earlier one
  kept: the guide's order, numbering and headings; the approved statements placed again under their new numbers;
  sections the guide drops left out (named in `C{n}-ALIGNED`); sections it adds left to write ("Write the sections your
  guide adds", the finish step, priced as their share); sections whose requirement differs listed (`to_align`) and
  revised on the student's request, priced before it starts. Written chapters keep their citation style. A chapter
  changed while the guide is read fails the step without charge.
- **Conceptual framework.** Black and white by default (muted green or blue on request; a style change only redraws
  it). Every variable is drawn: the old silent limit of 10/3/6 is gone, the layout adapts. A qualitative study gets a
  concept framework (the phenomenon and the areas the objectives explore, joined by plain lines claiming no cause).
  One drawing, caption and note serve the app, the Word file, the PDF and a separate download. The variables are
  edited from the workspace (rename, reorder, move between groups, remove, add; `POST /projects/{id}/framework`): the
  plan stays approved and the sections built on them are marked for review. Edits in plain language through a model,
  and checking the framework against a guide's figure rules, are not built.
- **Fixes found in testing.** A chapter being written showed as "Applying your changes" on the chapter before it: the
  page now opens the chapter being written with the same progress view as Chapter One (and why it stopped, if it
  failed). One web search Google left hanging failed a whole research stage (live Chapter Two, three times): a lost
  search now finds nothing and research goes on; repeated losses still stop the stage. Chapter views are sent in
  camelCase like every other view (a table's own caption and the "needs review" badge were never shown).
- **Old AI keys removed** (owner instruction): the OpenAI, Anthropic and Gemini API keys were unbound from both
  services and deleted from Secret Manager. Revoking them at OpenAI and Anthropic is the owner's.
- **Codex's audit of 29343c2, fixed the same day.** (1) A section the guide asks for differently stays unresolved
  until a revision changes it and passes review: the chapter cannot be approved (`CHAPTER_NOT_ALIGNED`) and the complete
  proposal is blocked meanwhile. (2) A guide's Chapter One sections are matched to their role by key or heading
  (purpose, objectives, questions; `profile.role`), so "Study aims" carries the objectives over and the approved
  statements are placed by code there; a purpose section holds the general objective; two sections with one role are
  refused for the student to check (`GUIDE_AMBIGUOUS`, not charged); a role section the earlier structure lacked is
  placed by code when aligning, never left for a model. (3) Writing the sections a guide adds follows the current
  approved plan, so it works after a confirmed setting or framework edit (sections from changed decisions stay flagged
  and block the complete proposal). (4) A guide profile keeps the standard guide's safeguards it does not replace: the
  owner's objective cap when the guide sets no number, the concept paper's three to five, the primary question and the
  hypothesis pairs. (5) A plan changed while the guide is read aligns nothing (`INPUTS_CHANGED`, not charged).
  (6) Chapter Three's assumed sample-size settings can be confirmed where it asks (`POST /projects/{id}/sampling`).
- **Testers:** attanborney458@gmail.com added (owner, 2026-10-08).

## 2026-10-08 — Speed and rate limits, without touching the work's integrity

The owner asked for faster jobs that never overload Gemini and never weaken the work ("it has to still be perfect, it
has to be grounded"). Plan agreed with Codex's two critiques. Evidence: Google's answers varied from 3 s to over 100 s
for the same task, hung searches waited 3 minutes and then restarted whole stages, research ran one topic at a time,
and nothing kept many jobs from calling Gemini at once.
- **Integrity first (owner):** models, thinking levels, prompts, research coverage, verification, reviews, repair
  rounds and approval are unchanged. Research is never cut short by time, and a search Google loses is asked once
  more straight away and never skipped (the tolerance of two skipped searches added earlier today is removed); lost
  twice, the stage retries as before. Lower thinking for research planning is not adopted.
- **One shared limit on Gemini calls** (`app/jobs/capacity.py`, `capacity_*` settings): every call of a job stage holds
  a slot of its resource (Vertex project, location and model; a web-search call is its own resource) while it runs, so
  all workers together never exceed it (Flash 12, Pro 4, searches 6 to start, as settings). Slots live in Firestore
  (`capacity/{resource}/slots/{n}`), are taken in a transaction and freed only by the request that holds them; a
  holder that vanished frees its slot when its time is up. A call waits up to 30 s; then the stage pauses
  (`CapacityWait`): it keeps everything done, its lease is released and it is delivered again in about 20-30 s. Pauses
  never use up provider-failure retries; after `capacity_max_waits` (about two hours) the job stops uncharged
  (`CAPACITY_BUSY`). If the limiter cannot be reached, calls pause too: nothing bypasses it. The existing cap of three
  active jobs per student, with two research topics at a time, bounds any one student to six calls.
- **Research two topics at a time** (`research_parallel`), results kept in topic order, every call under the limit; each
  topic answered in full is saved and read back by a retry (`checkpointed`).
- **Shorter waits:** a search or abstract reading gets 75 s (never below the token-rate rule for its allowance) instead
  of 180-290 s; retries after provider problems wait 15, 30, 60, 120, 240 s instead of 20 rising to 300. A lost call
  keeps its unknown-cost reservation.
- **Measured:** every call records its size and slot wait; every stage run its time, outcome and queue wait (admin
  page); `speed_report.py` gives per-task times, timeouts, refusals and first-try and eventual completion.
- **Students see** the topic in progress, waiting for capacity, and a provider retry with nothing lost.
- **Not done, and why:** buying reserved Google capacity (after measurement), more servers or CPU (they wait on
  Google), sending duplicate copies of slow calls (double billing), backup models (changes quality and price), lower
  thinking or fewer research topics (quality), automatic limit adjustment (after the fixed limits are observed), a
  large paid load test (needs the owner's spending cap; a small live check instead).
- **Load test on real Gemini (2026-10-08, local backend with the limiter, synthetic topics, $32.15 of a $60 cap):**
  1 at once: plan and Chapter One in 18 min. 3 at once: proposal 16 min, coursework essay 11, concept paper 12; no
  timeouts or refusals. 10 at once (limits as released): all 10 finished, proposal 23-28 min, essay 13-14, concept paper
  20-29; 10 timeouts, all recovered; slot waits small (searches, at most 32 s). 20 at once (search limit tried at 10):
  19 of 20 finished in 20-41 min, 32 timeouts and 2 refusals (both on the Pro reviewer), 151 capacity pauses (at most 12
  for one job), none failed for capacity. Quality held: every Chapter One had its 11 sections and passed its code
  checks. The slowdown under load is Google answering more slowly, most of all the Pro review model, not waiting for a
  slot. More searches at once brought more timeouts (about 10% at a limit of 10, about 4% at 6): the released limits
  stay (Flash 12, Pro 4, searches 6). The test ran the in-memory limiter; the Firestore one was checked in production.
- **A bug the load test found:** a concept paper with hypotheses was refused (not charged) because the reviewer asked to
  remove the placed sub-headings "Primary Research Question" and "Research Hypotheses". Every section whose statements
  code places now tells the writer and reviewer that the sub-headings and statements are the approved plan (`PLACED`,
  always added), for Chapter One, the concept paper and any guide.
- **A coursework draft cut too far (a tester's job, 2026-10-08):** a 1,000-word essay over its limit was compressed to
  809 words and then refused for being well under it (not charged; the rerun completed). A compressed section is now
  accepted only at 90% of its target or more (`COMPRESS_FLOOR`); cut further, its earlier text stays and it is asked
  again, up to three passes, and only if every pass overshoots is the closest attempt used.
- **Testers:** oboireedison@gmail.com added (owner, 2026-10-08).

## 2026-10-08 — Coursework: the question and the question paper are pasted (no uploads); nothing about AI unless the student asks

A tester typed "Solve this assignment for me?" as the question and uploaded the real question paper as a "set reading";
PaperAid wrote an essay it then refused for not answering that sentence (11 minutes, not charged). The owner's decision:
- **No files on the coursework Start page.** "Your question" (typed or pasted) and "More context (optional)": everything
  from the question paper, pasted, saved as the brief (`BRIEF`, "The question paper (pasted)"). The Brief, Marking rubric
  and Set readings uploads are gone from the page; the reading and rubric code stays for works that have them and can be
  shown again. Works that came with a data file (an Excel sheet to analyse) are an open question for later.
- **A request to PaperAid is never the question** (`resolve.is_request`: "Solve this assignment for me?", "Answer the
  questions below"): it is left out of the parts to answer, and when nothing else gives a question the student is asked
  for it before any work starts.
- **Nothing about AI is asked or printed** (replacing the decision of 2026-09-30): the question about the brief's AI rule
  is never asked; the last-page note is added only when the student asks for it (`ai_note_asked`; a disclosure statement
  where the assignment asks for one). An assignment whose own text bans AI tools is told to the student on screen
  ("Your assignment says AI tools are not allowed. Check your institution's rules before you submit this."), in the
  workspace, the price notice and the checks, never in the document (owner agreed to this safeguard). `validators-v4`.
- **A coursework plan the reviewer could never approve (a tester's work, 2026-10-08):** the skeleton attaches a marking
  criterion that names no section to every body section; the final reviewer asked for "Theme 1: S1 to S3 only, Theme 2:
  S4 to S6"; code let the writer add criteria but never remove them, so the plan was refused after two repairs (not
  charged). For coursework the writer's choice of criteria per section now stands (`_criteria`), and code only returns a
  criterion left out everywhere to the sections it was planned for. Other works keep the skeleton's criteria.

## 2026-10-08 — Codex's audit through ea0599e: fourteen findings fixed; a search that never answers no longer holds a work

Codex audited the speed release and the two coursework commits and found fourteen defects; each is fixed with the case
that showed it (`tests/test_codex_20261008_audit3.py`). Nothing about models, thinking, prompts, verification, reviews
or approval changed.
- **Research budget (1, 2):** two topics running together each reserve their possible cost, so the second could be told
  the budget was spent when nothing yet was. A call now waits for the calls under way to be recorded when it would fit
  on what is really spent (`AIRunner._settled`). A topic already saved is read back even when nothing more may be spent.
- **Academic alignment (3 to 7):** reading a guide again keeps a section still to revise (`to_align`); a section code
  placed from the plan during alignment carries the plan's stamp, so a changed plan marks it; a revision keeps what the
  chapter still lacks and has cost (`missing`, `full_price`, `paid`); a guide's own objective count is enforced
  (`objectives_enforced`); a guide with research questions and hypotheses as two sections is accepted.
- **Queue and limiter (8 to 11):** a retry and a capacity pause record when the job will next run (`ready_at`); a job
  stopped while waiting for a slot sends nothing; a job stopped for capacity can be resumed with a fresh allowance
  (`capacity_waits` reset); the paid estimate waits for capacity too; `CAPACITY_BUSY` can be tried again; the allowance
  is about two hours (`capacity_max_waits` 130). Every call takes a slot of its model and a search also one of the
  model's search slots, so the two no longer add up past the model's limit.
- **Reporting and drawing (12 to 14):** "completed first try" leaves out jobs that had any lost call; several topics'
  errors are settled by the most serious one, never hidden by a wait for capacity; every arrow of the conceptual
  framework ends on a dependent variable's box (`arrow_ends`). A compression asked again is told what its last attempt
  did (`lastAttempt`); a coursework writer's explicit "no criteria here" is honoured.
- **A search that never answers (owner, 2026-10-08: "fix everything"; amends "never skipped" above).** A tester's essay
  plan waited eighteen minutes because one web search of five timed out eight times while the other four topics had
  their verified sources. A topic the search service leaves unanswered (timeout, connection lost, unavailable) still
  fails its stage and is retried, but after two runs (four tries, about seven minutes) the work goes on without that one
  topic (`LOST_TOPIC_RUNS`, `checkpointed`). It is never dropped silently: the job carries the warning, and the
  document's checks show "Every research topic was searched: needs review" with the topic named (`research_gaps`,
  `W-RESEARCH`, `C{n}-RESEARCH`), so the document reads "Ready with warnings". Too many requests is never treated as a
  lost search; nothing is written from a source that was not found and verified.
