# PaperAid code audit — 56c4f83

Date: 2026-09-28. Auditor: Codex. Range: `655cda5..56c4f83` (15 commits, 92 changed files). Local HEAD matched `56c4f83`.

## 1. Verdict and verification

**Do not deploy this revision as-is or enable paid public use.** The ordinary journeys work, but new paths break privacy, revision correctness and the promise to charge only for delivered work. The seven suspected leads in the handoff all have substance; several require broader fixes than the handoff suggests.

| Severity | VERIFIED | SUSPECTED | Total |
| --- | ---: | ---: | ---: |
| Critical | 0 | 0 | 0 |
| High | 8 | 0 | 8 |
| Medium | 18 | 2 | 20 |
| Low | 1 | 0 | 1 |
| **Total** | **27** | **2** | **29** |

VERIFIED means I reproduced the faulty behavior with isolated tests or the browser. SUSPECTED means the code establishes a risk, but I did not reproduce its full production impact. Separate findings below identify their category, location, failure, evidence and recommended fix.

### Checks actually run

| Check | Result |
| --- | --- |
| Existing backend suite | **369 passed, 9 skipped, 1 failed**, 453.07 seconds |
| Backend Ruff, application and existing tests | Passed |
| New audit diagnostics | **26 passed**, 34.71 seconds: 25 reproduce defects; one confirms reference queries are not logged by the application fetch client |
| Frontend unit tests | **5 passed** |
| TypeScript typecheck | Passed |
| Vite production build into a separate audit directory | Passed, 2,081 modules |
| Main browser journey | Passed, no page errors, including immediate PDF upload and replacing a Word file |
| Proposal browser journey | Passed, including auto Chapter One, supervisor feedback, revision, comparison, concept paper, and institution guide |
| Proposal recovery browser journey | Passed: stale plan edit refused, failed project load shown with retry, refused monitoring shown with recovery |
| New browser diagnostics | Two defects reproduced: Deep Redraft rejection preview and selecting an unloaded chapter version |

The backend failure was `tests/test_proposal_v2.py:174`, `test_the_proposal_downloads_as_a_pdf`: expected HTTP 200/PDF, received HTTP 400. A minimal `article` also failed before typesetting under this sandbox's MiKTeX account. MiKTeX's log reported a Windows error during its file-name-database refresh. **This is an environment-limited PDF verification failure, not proof that the Linux production converter is broken.** It still means I cannot report an entirely passing backend suite or certify PDF delivery here.

The browser servers ran on **127.0.0.1:5001 and :8001**, with test providers, dummy keys, and a separate `.ae56` data directory. Owner data and the ordinary localhost ports were not used. Two preliminary browser attempts were invalidated by the audit setup: relocating a script changed its fixture-relative path, and concurrent journeys changed the same test wallet while the main journey checked its balance. Correcting the fixture path and running the main journey after the other journeys finished produced the passes above. Those setup failures are not application findings.

### Audit boundaries

- No application source was edited, no deployment or push was performed, and no real model calls were made.
- Added only this report and diagnostic artifacts. Synthetic test records and build/browser outputs were isolated from owner data.
- Firestore transaction behavior was inspected in code; these reproductions use the local store. No live Firestore, Cloud Tasks, GCS lifecycle, IAM, Firebase sign-in or App Check certification is implied.
- Real Word pagination/rendering, paid model quality and production PDF compilation remain unverified.
- Existing owner files, including the untracked UCU manual and earlier verification report, were preserved.

## 2. Findings — high severity

### H01 — Workspace fix instructions bypass the admin and retention sanitizer

**HIGH · privacy · VERIFIED**

**Location:** `backend/app/jobs/service.py:847`; `backend/app/jobs/workspace.py:179`.

`fix_draft` stores the findings' explanations and suggestions in `fix_notes`. These can quote or paraphrase a private paper. `without_paper_text` sanitizes the older fields but leaves `fix_notes` intact. Both admin responses and retention cleanup use this helper.

**Failure:** A fix draft contains `PRIVATE author sentence and confidential fix instruction`. `GET /api/admin/jobs/{id}` returns it under `job.fixNotes`, and the retention sanitizer preserves the same text.

**Evidence:** `test_admin_view_exposes_fix_notes` passed by reproducing that disclosure.

**Fix:** Empty `fix_notes` on admin/expired views. Prefer constructing an explicit support DTO rather than copying a full job and clearing known fields. Add a test that introduces every paper-bearing field, including future fields, and checks the actual admin route and persisted expired record.

### H02 — Actual account deletion leaves the durable ledger behind

**HIGH · privacy · VERIFIED**

**Location:** `backend/app/jobs/service.py:773`; `backend/app/integrations/store.py:253`, `:473`.

The account deletion route writes a closed wallet tombstone with `entries=[]`, but never calls the code that deletes durable ledger records. Clearing the display list does not erase the local JSONL file or the Firestore ledger subcollection.

**Failure:** After successful `DELETE /api/me`, the wallet is closed and the account is deleted, yet `store.ledger(uid, ...)` still contains its financial activity and grant metadata.

**Evidence:** `test_account_deletion_retains_durable_history`. The existing deletion test in `test_ledger.py` calls `store.delete_wallet` directly; it does **not** exercise the account deletion workflow.

**Fix:** Erase ledger history as an explicit resumable account-deletion step while retaining whatever minimal closing tombstone is needed to reject late requests. Do not simply remove the tombstone and reopen the upload/grant race. Test the public deletion route on both store implementations.

### H03 — A guide upload arriving after project deletion recreates a private orphan

**HIGH · privacy · VERIFIED**

**Location:** `backend/app/proposals/service.py:521`, especially `:531`; `backend/app/jobs/service.py:1060`.

Guide upload checks ownership, parses the document, writes its extracted text, then updates the project. If project deletion finishes before that write, the upload recreates a file under `projects/`, then fails because its project is gone. There is no cleanup on the failed attachment. This prefix deliberately has no fixed-age bucket backstop.

**Failure:** Delete the project exactly before `files.put` for its guide. Upload returns 404, the project is absent, but the file still contains the private guide text.

**Evidence:** `test_late_guide_upload_leaves_private_file_after_deletion` injects deletion at that boundary using the same deletion service the API calls.

**Fix:** Give uploads unique attempt paths, claim/attach against a live project atomically, and clean up every failed attachment. Ensure deletion accounts for in-flight uploads; a cleanup design must also survive a process crash between writing and attaching. A bounded orphan-cleanup process is useful for project objects outside the bucket TTL.

### H04 — The project-prefix change has no migration for existing projects

**HIGH · privacy/correctness · VERIFIED**

**Location:** `backend/app/proposals/models.py:292`; `backend/app/jobs/service.py:1086`; `docs/deployment.md:27`.

New project files moved from `users/{uid}/projects/{id}` to `projects/{uid}/{id}`. Existing records retain absolute chapter/evidence paths under the old prefix. Deletion uses only the new computed prefix, and the documented bucket policy still deletes everything old under `users/` after 31 days.

**Failure:** An existing project still reads its legacy chapter successfully. Project deletion returns 204 but leaves that chapter file behind. Separately, renewing such a project cannot protect its old objects from the `users/` lifecycle rule.

**Evidence:** `test_legacy_project_prefix_is_not_erased` seeds the old stored-path shape and exercises real read/delete routes. The renewal/lifecycle consequence follows from the documented policy; it was not tested against a real bucket.

**Fix:** Migrate files and all persisted references for existing projects before applying the new prefix policy. Make deletion handle both prefixes and referenced legacy objects until migration is complete. Include custom profiles/evidence and interrupted migrations; verify the deployed lifecycle separately.

### H05 — A revision that delivers no replacement marks feedback applied and charges 75%

**HIGH · money/correctness · VERIFIED**

**Location:** `backend/app/proposals/pipeline.py:485`, `:717`; `backend/app/pricing/billing.py:36`.

`_merge` knows which sections fell back to earlier text, but export marks every frozen comment ID `APPLIED` anyway. Proposal partial settlement then uses a flat 75% share, irrespective of what replacement text was delivered.

**Failure:** Every fix response for the selected problem section is empty. The old wording is kept, the job is PARTIAL, the supervisor comment is marked APPLIED, and the student is charged **1,500 UGX of a 2,000 UGX quote**. The response report can then claim the comment was answered in the new version.

**Evidence:** `test_empty_revision_marks_comment_applied_and_charges` runs the full worker pipeline with fixed pricing.

**Fix:** Persist per-section revision outcomes and link comments only to successfully delivered and checked changes. Leave unresolved comments OPEN with a reason. Settle from actual delivered outcomes; define an explicit owner-approved review-only fee if that should cost anything. A blanket 75% discount does not implement proportional delivery.

### H06 — Revising one section clears review failures in untouched sections

**HIGH · correctness · VERIFIED**

**Location:** `backend/app/proposals/pipeline.py:522`, `:488`, `:607`; `backend/app/proposals/export.py:56`.

`_merge` constructs a new chapter without its base warnings/readiness. `_readiness` then declares every section reviewed if the current revision's sections were reviewed. An untouched section's earlier missing review is forgotten. The whole-chapter readiness model does not retain enough section-level provenance to establish the new claim.

**Failure:** The base chapter has an unreviewed background and `C1-REVIEWED=NEEDS_REVIEW`. Revise only the problem statement. The new background is unchanged, its warning disappears, and `C1-REVIEWED` becomes PASS. This can remove the review blocker used by complete export.

**Evidence:** `test_revision_erases_untouched_review_failure` runs the revision pipeline.

**Fix:** Carry untouched sections' review coverage, warnings and integrity results forward. Recompute the chapter summary from coverage of **all final sections**, with content hashes for what was actually reviewed. Preserve unresolved findings unless new work explicitly resolves them.

### H07 — A stale revision quote makes an older chapter current again

**HIGH · correctness · VERIFIED**

**Location:** `backend/app/proposals/service.py:415`, `:550`; `backend/app/proposals/pipeline.py:495`, `:706`.

A revision quote freezes a base chapter path. Submit atomically checks ownership, deletion, plan version and the active-job claim, but not the chapter version/current path or feedback snapshot. Choosing or producing another chapter version does not necessarily change the plan version.

**Failure:** Quote a revision against version 1; select version 2 containing a newer background; submit the old quote. The revision uses version 1 and publishes a new current version containing its old untouched background. Version 2 remains in history, but its work has been silently displaced.

**Evidence:** `test_revision_from_stale_quote_replaces_newer_background`.

**Fix:** Freeze and atomically check the base chapter version/path/hash at submission. Refuse stale quotes with a clear reprice message. Define publication behavior if the student changes the current version during processing: retain a candidate rather than overwrite that newer selection.

### H08 — A small fix draft can be expanded without changing its page-band price

**HIGH · money · VERIFIED**

**Location:** `backend/app/jobs/service.py:389`, `:453`; `backend/app/jobs/workspace.py:178`; `backend/app/pricing/quote.py:274`.

`scope_words` is copied from the initial fix selection. Later quote requests can replace `only_blocks` with any syntactically valid block IDs, while the old stored scope still determines price and the rewrite projection. Replacing the source also does not clear the fix scope/notes.

**Failure:** Create a real 4,500-word document with 30 editable 150-word paragraphs. Use the actual fix endpoint for one paragraph, creating a 150-word draft. Expand `onlyBlocks` to all 30 valid IDs. The quote remains **4,000 UGX**, while the normal 4,500-word price is **7,000 UGX**. The larger selection is saved for execution.

**Evidence:** `test_fix_scope_can_be_expanded_without_repricing_words` uses actual DOCX parsing, actual findings, the fix route and both quote requests; it does not rely on nonexistent block IDs.

**Fix:** Derive scope from the exact current document and selected editable blocks each time, or prohibit changes to the frozen fix scope. Validate membership as well as ID syntax. Source replacement must reset fix metadata or require a new ordinary draft. Freeze the validated selection/scope in the quote.

## 3. Findings — medium severity

### M09 — Moving a comment after quoting makes the wrong section appear addressed

**MEDIUM · correctness · VERIFIED**

**Location:** `backend/app/proposals/service.py:622`; `backend/app/proposals/pipeline.py:717`.

Only comment IDs are checked at publication, not their placement/version. **Failure:** Quote a problem-statement revision, move its comment to the background, then submit. The problem is revised, the background stays unchanged, and the background comment becomes APPLIED. `test_reassigned_feedback_marked_applied_to_unchanged_section` reproduces it.

**Fix:** Snapshot/hash the comment text and target sections, validate them at acceptance, and mark applied only if the current comment still matches that snapshot. Changes during processing should leave the changed comment OPEN.

### M10 — Standalone local wallet writes can record a transaction that never committed

**MEDIUM · money/auditability · VERIFIED**

**Location:** `backend/app/integrations/store.py:204`, `:222`.

`_write_wallet` appends ledger entries before replacing the wallet JSON. Standalone `update_wallet` has no journal enclosing both writes. **Failure:** Interrupt the wallet replacement after a 5,000 UGX top-up is appended. Wallet balance remains 1,000 UGX, but history records the uncommitted top-up. `test_local_wallet_failure_leaves_phantom_ledger_entry` injects this exact filesystem failure.

**Fix:** Journal wallet-only transactions too, recovering a complete commit or a complete rollback. Make JSONL recovery tolerate an interrupted final line. Deduplicating identical ledger IDs cannot repair a phantom transaction whose wallet update never committed. Firestore's transaction is not shown to share this local failure.

### M11 — Timestamp-only ledger cursors skip entries at page boundaries

**MEDIUM · money/history · VERIFIED**

**Location:** `backend/app/jobs/service.py:799`; `backend/app/integrations/store.py:258`, `:485`; `backend/app/api/routes.py:91`.

History pages use `at < before`. Local sorting has an ID tie-break, but the cursor has only the timestamp; Firestore has the same strict timestamp filter. **Failure:** Insert 60 entries sharing a timestamp. Page one returns 50; page two excludes the remaining 10. `test_ledger_cursor_loses_entries_with_equal_times` exercises the HTTP history API.

**Fix:** Order and paginate by `(at, id)` with an opaque compound cursor, consistently in both stores and the browser. Update the API's 40-character cursor limit. Normalize timestamp representation or store native timestamps so string formatting differences do not affect ordering.

### M12 — Existing wallet entries are never migrated into durable history

**MEDIUM · money/migration · VERIFIED**

**Location:** `backend/app/integrations/store.py:63`, `:204`, `:426`.

New durable records are selected relative to the wallet's existing display-entry IDs. Legacy display entries therefore never count as new, even on the next wallet update. **Failure:** Seed an old wallet with a committed top-up and no ledger file. Both immediately and after an ordinary wallet update, history is empty. `test_existing_wallet_history_is_not_backfilled` reproduces it.

**Fix:** Backfill the retained legacy entries idempotently before presenting complete history. Record a migration version. Entries already lost to the old 300-entry cap cannot be reconstructed from this code; disclose the historical cutoff or recover them from a trustworthy existing source.

### M13 — Expired-project cleanup stops behind a page full of refused items

**MEDIUM · privacy/retention · VERIFIED**

**Location:** `backend/app/jobs/service.py:1094`; `backend/app/integrations/store.py:328`.

Cleanup repeatedly requests the first page and filters already-seen IDs locally. When that page is full of projects it could not erase, the filtered batch is empty and cleanup stops, without advancing to later projects. **Failure:** At page size 1, the first expired project has a queued step and the second is deletable; zero projects are erased. At the production page size, the same failure requires a first page filled with refused items.

**Evidence:** `test_cleanup_stops_behind_one_blocked_page`. The existing pagination test covers deletion shifting later items into page one, not refused items remaining in it.

**Fix:** Add a stable expiry/ID cursor or enumerate all eligible IDs once, independently of deletion success. Keep the atomic renewed-project check. Test blocked/renewed items at page boundaries as well as successful deletion.

### M14 — Downloading workspace choices drops the institution logo

**MEDIUM · output/UX · VERIFIED**

**Location:** `backend/app/jobs/workspace.py:91`; compare `backend/app/jobs/pipeline.py:914`.

Rebuild applies the formatter/custom layout but does not re-add the uploaded logo. **Failure:** The normal finished file contains one inline logo; `paper-reviewed` contains none. `test_workspace_rebuild_loses_uploaded_logo` runs a real refine-and-format job, then downloads both DOCX files.

**Fix:** Share the code that applies the final selected layout and logo between the worker and rebuild. Test both logo positions, ordinary refinement and Deep Redraft. Preserve original document images as well as the uploaded logo.

### M15 — Browser-edited research gaps can claim unconfirmed evidence

**MEDIUM · correctness · VERIFIED**

**Location:** `backend/app/proposals/service.py:184`; compare `backend/app/proposals/pipeline.py:298`.

Only the model-produced plan goes through `_confirmed_gap`; browser saves do not. **Failure:** Save a research gap with `E999999` and `not-an-id`, then approve the plan. Both IDs survive. The editor's source count can consequently claim confirmed support it does not have.

**Evidence:** `test_browser_plan_accepts_unconfirmed_gap_evidence` exercises save and approval.

**Fix:** Validate against the project's usable evidence at every plan-ingestion boundary, including browser saves and candidate acceptance. Reject invalid selections or remove them with an explicit warning. Keep validity and missing support visible when a gap cannot be supported yet.

### M16 — Malformed profile numbers escape the NOT_A_GUIDE boundary

**MEDIUM · correctness/resilience · VERIFIED**

**Location:** `backend/app/proposals/profile.py:83`, `:111`, `:124`; `backend/app/proposals/ai.py:275`; `backend/app/proposals/pipeline.py:239`.

The local profile response wrapper accepts an arbitrary object, then `build` directly calls `float`/`int`. **Failure:** A model profile with `formatting.sizePt="twelve"` raises ordinary `ValueError`, not `NotAGuide`. The pipeline only classifies `NotAGuide`; this falls through its generic stage error path and retries can replay the same cached malformed object.

**Evidence:** `test_profile_numeric_error_is_not_classified_as_not_a_guide` reproduces the validator exception. I did not count this as a demonstrated series of extra paid calls.

**Fix:** Use typed nested local response models before caching, then validate finite/bounded values and structure. Translate unusable profiles once into the agreed domain failure. Cover strings, nulls, NaN/infinity, malformed chapter keys and empty structures; catch specific validation failures rather than every exception.

### M17 — One missing custom rulebook breaks the project list

**MEDIUM · availability · VERIFIED**

**Location:** `backend/app/proposals/rulebook.py:34`; `backend/app/proposals/service.py:115`.

Missing profile storage propagates from `rulebook.load` into project view construction and list construction. **Failure:** Open a project using a custom book, remove that book, clear the cache as a restart would, then fetch the project or list. Both raise `FileNotFoundError` locally; the handoff's precise prediction of `ValueError` was incorrect, but the 500 behavior is real. A warm cache can hide it until restart or another instance serves the request.

**Evidence:** `test_missing_custom_rulebook_breaks_project_and_list`.

**Fix:** Return a recoverable missing-profile state for the affected project without breaking unrelated projects. Let the student restore/rebuild the guide where allowed. Do not silently mark the default profile as if the uploaded guide was read. Bound/invalidate the rulebook cache when profiles are deleted.

### M18 — Version comparison ignores tables, captions and heading-only changes

**MEDIUM · correctness/UX · VERIFIED**

**Location:** `backend/app/proposals/service.py:716`.

The comparison determines whether a section changed from paragraph arrays and diffs only that prose. **Failure:** Change a work-plan cell from month 1 to month 6 and change its caption, keeping paragraphs unchanged. The API says `changed=0`. `test_table_only_revision_is_invisible_in_comparison` reproduces it.

**Fix:** Compare the section's visible heading, numbering, prose, caption and table cells, and return/render those differences. Snapshot framework data with versions if figures are included in version comparison. Avoid telling students nothing changed when a material schedule or budget changed.

### M19 — The Word List of Tables exposes raw evidence tokens

**MEDIUM · output correctness · VERIFIED**

**Location:** `backend/app/proposals/export.py:215`, `:251`.

Body captions use `Citer.render`, but preliminary List of Tables entries use raw captions. **Failure:** A caption citing `⟦E00000b⟧` prints a proper APA citation in the chapter and the raw internal token in the List of Tables. `test_list_of_tables_leaks_unrendered_evidence_tokens` inspects the generated DOCX.

**Fix:** Render all delivered text through the same evidence/citation boundary, including preliminary lists. Use an appropriate separate rendering state so preliminary summaries do not incorrectly consume APA 6 first-use rules for the body. Check the complete DOCX for unresolved tokens.

### M20 — A truncated PNG produces a server exception instead of upload rejection

**MEDIUM · input validation/UX · VERIFIED**

**Location:** `backend/app/jobs/service.py:294`.

The exception list omits `python-docx`'s `UnexpectedEndOfFileError`. **Failure:** Upload only the eight-byte PNG signature. The parser raises that exception out of the route instead of returning the classified invalid-logo response. `test_truncated_png_is_an_unhandled_server_exception` reproduces it.

**Fix:** Classify the actual image-parser failures and return the normal invalid-image response. Extend validation tests to truncated signatures and malformed image headers, not only an obviously wrong file. Keep the existing 2 MB/type constraints.

### M21 — New feedback/guide routes lack quotas and parse uploads on the API event loop

**MEDIUM · security/resource control · VERIFIED for quota omission**

**Location:** `backend/app/api/projects.py:172`, `:190`; `backend/app/proposals/service.py:521`, `:590`.

These routes have auth and ownership checks, but no operation-specific per-user limit. The async upload handlers also call synchronous document/PDF parsers directly after reading the file, blocking their serving event loop for parsing duration. Size/comment caps bound some inputs, not repeated CPU work or aggregate upload rate.

**Failure/evidence:** Set the per-user quote limit to 1, then add four feedback batches; all return 200. `test_feedback_add_has_no_per_user_quota` confirms the missing rate gate. Event-loop blocking is established by the handler call chain; I did not perform a hostile load test or claim demonstrated production exhaustion.

**Fix:** Add explicit feedback, guide, rebuild and export quotas where needed. Run CPU/blocking parsing in the thread pool or worker with bounded concurrency. Check account/project state before costly parsing and again before mutation. Preserve legitimate editing use; a quote-rate setting is not a substitute for an upload policy.

### M22 — A second author can be verified as the reference's first author

**MEDIUM · correctness · VERIFIED**

**Location:** `backend/app/analysis/references.py:69`.

The documented first-author check searches the normalized surname anywhere in the author list or journal/container. **Failure:** Crossref lists Ojakaa first and Jarvis second. A reference naming only Jarvis as its author, with the correct title/year/DOI, is labeled VERIFIED. `test_reference_verification_accepts_second_author_as_first` reproduces it.

**Fix:** Compare a structured first-author identity, with explicit organizational-author rules. Do not treat journal/container membership or an arbitrary substring match as author agreement. Missing metadata should lower certainty rather than certify a match.

### M23 — An unavailable DOI lookup is stated as proof the DOI is unregistered

**MEDIUM · correctness/wording · VERIFIED**

**Location:** `backend/app/analysis/references.py:59`; `backend/app/analysis/fetch.py:81`, `:214`.

The fetch layer returns `None` for non-200 responses, timeouts and failed safety/read checks. Verification converts all such results into “This DOI is not registered.” **Failure:** A valid DOI's lookup is temporarily unavailable; the student is told to correct an allegedly unregistered DOI. `test_reference_service_outage_says_doi_not_registered` supplies the same unavailable result that the real fetch path returns.

**Fix:** Distinguish explicit not-found, service unavailable, invalid data and a successful registry response. Say “could not verify right now” for unavailable lookups and provide retry/check links. Apply the same distinction to bibliographic searches. The existing fake lookup test assumes absence means unregistered and therefore misses this case.

### M24 — Incomplete academic review is labeled FULL

**MEDIUM · correctness/consistency · VERIFIED**

**Location:** `backend/app/jobs/pipeline.py:251`; `backend/app/pricing/billing.py:35`; `web/src/features/jobs/job-page.tsx:201`.

Academic review reaching budget adds a warning, but unlike incomplete AI-likeness analysis it does not set PARTIAL. **Failure:** Inject the real academic-coverage warning at the review boundary. The complete worker pipeline returns `outcome=FULL` even though it says some sections were not reviewed. `test_incomplete_academic_review_is_labelled_full` reproduces the status; settlement does discount the academic line to 50%, so this finding is not an allegation of full charging for that line.

**Fix:** Store coverage explicitly and mark incomplete services/job outcomes accurately. Drive the result heading and settlement from that data, rather than matching warning text. Keep a usable partial result while making its coverage limits clear.

### M25 — Rejecting a Deep Redraft group hides original paragraphs in the preview

**MEDIUM · UX/correctness · VERIFIED**

**Location:** `web/src/features/results/workspace.tsx:78`, `:143`.

Extra paragraphs in a redrafted group are always hidden before rejection is considered. **Failure:** Reject a two-paragraph group. The paper preview shows the first original paragraph but not the second; the side panel's combined before-text can misleadingly look correct.

**Evidence:** `docs/codex_audit_browser_56c4f83.mjs` reproduces this in Chromium using synthetic route responses against the real UI.

**Fix:** Keep the group's identity on every member and hide later paragraphs only while its rewrite is accepted. When rejected, render all original blocks in their original order. Test the preview and the rebuilt DOCX together, including groups with more than two paragraphs.

### M26 — Failed chapter loads leave an old preview with an active version-selection button

**MEDIUM · UX/correctness · VERIFIED**

**Location:** `web/src/features/proposals/project-page.tsx:50`, `:78`, `:161`.

Changing the version does not clear the old `chapter`; a failed request sets an error but leaves it visible. Selection buttons use the dropdown version, not the version actually loaded.

**Failure/evidence:** Load version 1, choose version 2, return HTTP 503 for version 2. The selector says 2 and the preview still shows version 1. Clicking “Use this version” posts version 2. The browser diagnostic captures that exact request.

**Fix:** Track loading/error state by project/chapter/version, clear stale content, and disable selection/approval until the selected version is successfully loaded. Clear recovered errors and provide a retry. This extends the earlier project-load fix to chapter-level loading.

### M27 — Synchronous PDF compilation has no aggregate capacity bound

**MEDIUM · security/availability · SUSPECTED production impact**

**Location:** `backend/app/proposals/service.py:352`; `backend/app/api/projects.py:154`; `backend/app/latex/package.py:20`.

The PDF route runs a compiler for up to 90 seconds inside an API request. It has a per-user `pdf` counter using `quotes_per_hour`, but no queue, shared compiler-concurrency limit or cached result. The counter is a separate action: it does not literally consume the same quote counter. Because the endpoint is synchronous, FastAPI uses its thread pool; it is **not** the async-event-loop parser issue in M21.

**Concrete risk:** Many signed-in users request repeated proposal PDFs, occupying API threads and spawning compilers while normal API traffic shares the instance. I did not reproduce production exhaustion, and the local compiler failed before useful resource measurements.

**Fix:** Cache by project/version/citation/title-page/layout inputs and enforce a small compiler concurrency bound. Move cache misses through the existing worker queue if measured load warrants it. Benchmark normal request latency under concurrent PDF work and add an explicit PDF quota.

### M28 — Frozen engines do not freeze newly added steps or legacy selection defaults

**MEDIUM · consistency/money · SUSPECTED upgrade impact**

**Location:** `backend/app/ai/orchestration.py:499`; `backend/app/jobs/models.py:93`; `backend/app/jobs/pipeline.py:241`.

`_prompt_for` explicitly falls back to today's prompt when a task is absent from the quote's engine. The new `academic=True` default also applies when deserializing old selections that have no academic field.

**Concrete risk:** A queued/estimated job saved before this feature gains an academic review after upgrade, using a prompt absent from its frozen engine and an old quote projection that did not price it. The quote's monetary ceiling still limits the student's charge; the issues are executing unpriced/new work and consuming budget intended for the frozen workflow. I did not run a full before/after deployment with a legacy queued job.

**Fix:** Persist an execution-policy/version or exact task set with the quote, migrate old selections to their historical defaults, and require a frozen prompt for every executed task. Fail/reprice at a controlled boundary rather than silently adopting a new task. Keep the already-correct p-plan-v1/v2 schema selection.

## 4. Low-severity finding

### L29 — The load-test runner ignores student-task exceptions

**LOW · tests · VERIFIED**

**Location:** `backend/tests/load_test.py:89`.

The executor's futures are never consumed. A task exception outside `Recorder.call` disappears from the recorded failure list. **Failure:** Record one successful request, then raise a malformed-response error in the student task. `main()` returns 0 and prints normal latency results without reporting the exception. `test_load_script_reports_success_when_student_future_crashes` reproduces it.

**Fix:** Keep the futures and consume `future.result()`/`as_completed`, recording failures with student/stage identifiers. Check the expected number of completed journeys and required responses. This runner is a preliminary API exercise; it does not establish production queue, Firestore, upload-parser or PDF capacity.

## 5. Handoff leads a–g

| Lead | Verdict | Evidence and scope |
| --- | --- | --- |
| a. Rebuild misses logo | **Confirmed** | M14; actual before/after DOCX files inspected |
| b. Empty revision still marks comments APPLIED | **Confirmed, broader money defect** | H05; unchanged wording, false APPLIED, 75% charge; M09 adds comment-placement races |
| c. Browser research-gap IDs unchecked | **Confirmed** | M15; save and approval accept unknown IDs |
| d. Profile numeric conversions bypass NOT_A_GUIDE | **Confirmed** | M16; ordinary ValueError; no claim that every retry makes a paid call |
| e. Missing rulebook crashes views | **Confirmed with corrected exception** | M17; local FileNotFoundError, project GET and entire project list fail after cache clear |
| f. Quotas absent; PDF synchronously in API | **Confirmed code paths; production overload suspected** | M21/M27; async parsing and sync PDF execution are different mechanisms; the PDF counter uses the same setting but a separate action key |
| g. Old wallet entries absent from durable history | **Confirmed** | M12; persisted legacy wallet remains absent from history even after update |

## 6. Previous 16 findings — regression matrix

The direct fixes in `7cd6a5a` are largely present and their normal-path tests pass. That is different from confirming the guarantees survive every new path.

| Earlier # | Guarantee | Result in this audit |
| --- | --- | --- |
| 1 | DNS rebinding/private-address guard | **Direct fix holds.** Fetch pins a validated address, preserves Host/SNI and disables environment proxies; existing regression tests pass. Real HTTPS/production network behavior not exercised. |
| 2 | Preserve later-section headers/footers | **Holds in tests.** Section references/text are checked and populated containers are preserved. Real Word check remains necessary. |
| 3 | Renewable projects survive object-age lifecycle | **Fixed for new paths; migration gap H04.** Existing project objects remain under the old TTL prefix unless explicitly migrated. Live bucket configuration not independently checked. |
| 4 | Submit, project claim and money are atomic | **Direct fix holds.** Triple-store transaction and competing deletion tests pass. New revision inputs are insufficiently checked: H07/M09. |
| 5 | Renewed projects survive cleanup | **The original renewal race is fixed.** Separate pagination guarantee is incomplete when refused rows fill a page: M13. |
| 6 | Delete all private project/child-job material | **Normal child-job fix holds.** New upload race H03 and legacy-object gap H04 prevent a complete deletion guarantee. |
| 7 | Evidence checks/rendering cover tables and captions | **Body fix holds.** New List of Tables output bypasses rendering: M19. |
| 8 | Complete export rejects empty/unreviewed chapters | **Direct empty/integrity checks hold.** H06 supplies a false whole-chapter review PASS, weakening the review gate via revision. |
| 9 | Dirty plan editor cannot overwrite concurrent edits | **Holds.** Recovery browser journey refuses stale save and shows the conflict. |
| 10 | Missing review cannot yield a clean reviewed result | **Normal chapter fix holds.** Untouched chapter coverage is lost through revision H06; new academic service has a related outcome defect M24. |
| 11 | At most two repair rounds; last text reviewed | **Holds on ordinary chapter path.** Existing test passes. REVISE's initial rewrite plus two further repairs is explicitly authorized by the newer decision; it is not an unauthorized third repair. |
| 12 | Objective membership changes invalidate dependent sections | **Holds in focused tests.** Whole-set hashes and missing per-objective sections are checked. |
| 13 | Population/sample numbers must be explicit author inputs | **Holds.** Year in notes is refused; explicit fields accepted; browser sample calculation passes. |
| 14 | APA 6 first use follows reading order | **Holds in both narrative/parenthetical tests.** M19 needs a fix that preserves that ordered state. |
| 15 | Load/progress errors are visible and recoverable | **Project/progress fixes hold in browser.** New chapter-version loading has a related stale-content defect M26. |
| 16 | Reviewer warnings reach the student | **Normal-path fix holds.** New reviewer notes are retained; untouched base warnings are erased during revision H06. |

Therefore I cannot confirm that all 16 guarantees remain fully covered by the new system, even though their original reproduction tests mostly pass.

## 7. Code versus documented decisions

1. **Support metadata only, and paper text expires:** H01 conflicts with the privacy decision at `docs/decisions.md:136` and the sanitizer's stated allowlist. New private fields must not be automatically inherited by support views.
2. **Ledger complete, atomic and deleted with account:** H02 and M10–M12 contradict Operations (`docs/decisions.md:204`). A correct `delete_wallet` method is not sufficient if the real account flow does not call it.
3. **Charge in proportion to delivered work:** H05 conflicts with `docs/decisions.md:188`, `CLAUDE.md` and the student FAQ. A PARTIAL proposal is currently charged 75% by outcome, even with no delivered replacement.
4. **Only selected passages; selected scope governs price:** H08 breaks the workspace decision at `docs/decisions.md:190` and the fixed-band pricing contract.
5. **Supervisor comments identify the version that answered them:** H05/M09 violate `docs/decisions.md:195`. “Earlier version kept” and “APPLIED” cannot both establish successful correction.
6. **Whole final text reviewed; every other section carried forward:** H06/H07 break review provenance/current-version expectations. Carrying over text alone does not carry over its warnings or prove it reviewed.
7. **Research gap rests only on confirmed IDs:** M15 conflicts with `docs/decisions.md:197`.
8. **Pages through every expired project:** M13 conflicts with the cleanup function's own contract; H03/H04 undermine deletion/lifecycle claims.
9. **Every job uses its priced engine:** M28 is an upgrade-risk exception to `CLAUDE.md`. Existing frozen prompts and the PLAN_SCHEMA v1/v2 switch are good; fallback for missing tasks remains a gap.
10. **No partly working controls:** M14/M18/M25/M26 violate the intent of `CLAUDE.md` even though happy-path browser journeys pass.

### Decisions that are intentionally different from earlier specs

- **Tokens**, fixed prices, default academic review and automatic Chapter One are the newer owner decisions. I did not treat their conflict with earlier “credits/cost mode” wording as an implementation defect.
- The owner explicitly kept the original lead/writer models. No model replacement or per-step routing was proposed or applied.
- Source Check, Concept, Profile and Revision prices are still described as awaiting confirmation in the newer decision entries. Resolve those retail values before enabling paid public use; passing a pricing-formula test does not establish price approval or sustainable margins.
- The concept-paper checklist estimates pages from prose words and reports out-of-range length/reference counts as NEEDS_REVIEW. It does not enforce an actual five-page Word result. The UI's unconditional “at most five pages” should be softened to a target or backed by a measured export gate. Tables, annotations and title material affect pagination. This is a remaining acceptance limitation, not a reproduced Word-pagination finding.
- A small wording inconsistency remains: `backend/app/proposals/review.py:234` labels a downloaded checklist result “AI judgement,” while the new student-wording decision asks to describe what PaperAid does. Use the same plain wording in downloads as in the web checklist. Required institution names on a proposal's cover are not the same as exposing an internal manual name in the app.

## 8. Test gaps and misleading proofs

- **Account deletion:** test the actual `DELETE /api/me` flow, durable entries, interrupted deletion and the retained account lock. Directly calling `delete_wallet` proves only that method.
- **Revision delivery:** empty/omitted responses, kept original text, remaining reviewer warnings, zero delivered replacements and per-comment status/charge. Check the response report, not just the chapter status.
- **Revision concurrency:** quoted base version changes, current-version changes while running, feedback relocation/deletion while running and changed guide/profile inputs. Check the atomic transaction and publication boundary.
- **Legacy migration:** projects using the old prefix, wallet display entries without history, existing selections/engines, interrupted migration and retry. Creating only new objects cannot establish upgrade safety.
- **Ledger:** tied timestamps, compound cursor traversal without gaps, wallet-only filesystem failures and incomplete JSONL records. Verify histories reconcile with balances, not just entry count.
- **Retention:** first-page projects refused by the deletion gate; late private file writes after successful deletion; expiry redaction of fix notes.
- **Profile validation:** malformed numeric/structural responses before cache save, missing storage, stale cached book, and preserving other project rows when one is damaged. Happy valid fake profiles do not prove the error boundary.
- **Workspace:** real grouped redraft preview after rejection; logo/custom layout in choice downloads; replacing a fix draft's source and expanding its selection with valid IDs.
- **Exports:** captions, preliminary lists, table cells and all Word body text should contain no unresolved internal evidence token. Table/heading-only comparisons need assertions on differences.
- **Reference verification:** unavailable versus absent registry answers, first-author versus coauthor agreement, organizational names, missing metadata, malformed registry records and private/unpublished bibliographic entries.
- **Resource use:** current load test exercises dev-auth metadata/upload/quote paths. It does not measure production Firestore, worker backlog, paid models, feedback/guide parser interference or concurrent PDF compilers. Consume futures and validate completed journeys before trusting its exit status.
- **Browser tests:** happy-path tests did not cover H05/H06, M18, M25 or M26. The latest frontend unit suite has only five tests; successful typecheck/build does not prove these state transitions.
- **Mutations:** I did not independently repeat the claimed remove-fix/restore-fix mutation checks for the previous 16. I ran their available tests and added boundary reproductions. A test's name or the previous handoff is not evidence of mutation sensitivity.

## 9. What I checked and found correct

- Fixed-price page-band arithmetic and explicit per-service quote lines work for normal inputs. Quotes freeze price/policy metadata; `budget_usd` is separate from the retail charge. The free fixed-price Deep Redraft estimate path works in the browser.
- Settlement caps the charge by the held amount; billing state guards normal settle/refund retries. I did **not** find a reproduced above-quote or repeated-settlement charge in this revision. Wrong delivered-share semantics and underpriced scope are separate findings.
- Local paired/triple transaction journaling exists, and Firestore writes the new ledger entries inside the relevant transaction. M10 is specifically the unjournaled standalone local path.
- Uploaded source attempts retain unique storage names and late attachments are rejected/cleaned. Draft creation happens on upload; immediate PDF and replacement journeys passed. These patterns should be reused by new guide uploads.
- New routes retain authentication/ownership gates; production dev sign-in is refused. The findings do not allege unrestricted cross-account chapter or file access.
- Normal workspace dismiss/restore, fix creation, ordinary change rejection and rebuilding are functional without calling AI from the workspace. Main journey and existing workspace tests cover them; H08/M14/M25 cover missing boundaries.
- APA/Harvard, professional/report presets and normal custom font/layout/logo application have working tests and browser coverage. Header/footer protection is improved.
- References and paper checks are kept separate from claim support and AI-likeness. Registered-work verification does not inherently prove a claim. In the tested fetch path, reference queries were **not** logged: application fetch uses the silenced `httpx` logger, whereas `httpx2` messages seen in tests are the test client. I dismissed that suspected logging leak after checking the actual client.
- Normal proposed chapter evidence checks include table cells/captions; quoted passages are independently checked against text/abstracts. Required sections/integrity/review flags gate complete export. M19 and H06 are specific gaps beyond these working normal checks.
- Code-owned sample calculations and explicit student numeric inputs survive the earlier fixes. The browser calculated 343 from the student's figure and Chapter Three used it.
- Objective/group decision hashes, stale plan save checks, and candidate-plan preservation protect concurrent plan edits. Original recovery UI cases passed.
- Lead/writer step assignments follow the approved roles. Released-prompt immutability tests passed. The p-plan-v1/v2 schema choice uses the frozen prompt version. Ordinary repairs remain limited and their last text reviewed.
- Concept-paper state is represented as number 4 without treating it as Chapter Four in the main proposal export; older project records gain its state. Independent concept download and its normal checklist pass with test models.
- Guide extraction and default/custom profile selection work in the valid case; written chapters prevent ordinary guide/profile changes. That does not establish malformed-response or missing-file resilience.
- Main job/proposal browser journeys, service chooser, token wording, automatic Chapter One, framework drawing and ordinary feedback assignment work. CI now runs the web unit tests.
- HTML now has `no-cache`, while hashed assets remain immutable. This helps fresh navigation after releases; it does not guarantee an already-open old tab retains all removed old chunks. No live hosting assertion was made in this audit.

## 10. Recommended repair order and retest gates

1. Close private-data holes H01–H04, including migrations and actual deletion workflows. Keep account/project closing gates while adding cleanup.
2. Fix revision outcome/provenance/quote snapshot behavior H05–H07 and M09, then scoped pricing H08. Add per-section delivery data before adjusting charges.
3. Repair durable-history atomicity, migration and pagination M10–M13. Reconcile synthetic histories with balances after fault injection.
4. Repair profile/input boundaries, output rendering and stale browser state. Share final formatting code so logo/custom layout cannot drift between downloads.
5. Add bounded parsing/PDF execution and meaningful load-test completion checks. Verify upgrade behavior for legacy quotes/engines.
6. Rerun ordinary and negative journeys with fixed pricing and both store implementations. Then run the real deployment/Word/provider gates with owner-authorized credentials. Keep test fakes isolated; do not use them to label production quality verified.

## 11. Reproduction artifacts and cleanup

- `docs/codex_audit_reproductions_56c4f83.py`: isolated pytest diagnostics. **Most tests intentionally assert broken behavior; passing them means reproduction, not a fix.** The `test_reference_query_is_not_logged_by_real_fetch_client` test is the positive privacy check.
- `docs/codex_audit_browser_56c4f83.mjs`: synthetic browser responses through the real UI; asserts the two reproduced display defects. Requires the test-provider backend/local-sign-in stack, not a live Firebase session.

Backend reproduction command, from `backend/`, using a **fresh short** basetemp:

```powershell
$env:OPENAI_API_KEY='sk-test-audit'
$env:ANTHROPIC_API_KEY='sk-test-audit'
$env:PYTHONIOENCODING='utf-8'
.\.venv\Scripts\python.exe -m pytest -q ../docs/codex_audit_reproductions_56c4f83.py --basetemp=.audit-new -p no:cacheprovider
```

The fixture replaces providers and network lookups. The explicit dummy keys prevent any real key in an owner `.env` from being used by these diagnostics.

For the browser artifact, use the repository's test-only backend and local-sign-in Vite app. It defaults to `http://127.0.0.1:5000`; set `PAPERAID_AUDIT_BASE` for an isolated alternate port. Do not run the repository test launcher against owner data: it uses its own `.data_e2e` folder and clears that test folder at startup.

Temporary audit servers, pytest folders, build directories and adapted journey copies were isolated. Cleanup status is recorded after the final workspace check below. Do not delete the preexisting untracked owner files or earlier audits as part of this cleanup.
