# PaperAid code audit — 28 September 2026

**For the owner and Claude Code. Reviewed repository HEAD: `655cda5`, including Proposal V1 in `7910545`.**

## Verdict

**I would not approve this code for a production release yet.** The established tests and ordinary browser journeys pass, but additional adversarial cases expose data loss, a source-fetch security bypass, project lifecycle races and proposal safeguards that do not cover everything delivered.

This was an audit. I did not edit application code, deploy, change keys, change Google Cloud permissions, change App Check settings, or delete the owner's jobs. The test runs used separate data folders and test-only models. The browser stack ran on ports **5001/8001**, leaving the owner's 5000/8000 stack alone. Verification refreshed a generated TypeScript build cache; that file was already modified before this audit.

### Verification completed

| Check | Result |
| --- | --- |
| Existing backend suite, isolated Windows temp directory | **306 passed, 9 skipped** |
| Backend Ruff | Pass |
| Frontend unit tests | **5 passed** |
| Frontend `npm run typecheck` | Pass |
| Vite production build to an isolated output directory | Pass |
| Existing general browser journey | Pass, with its strict response/error checks |
| Existing proposal browser journey, including uploaded proposal review | Pass |
| Additional backend audit diagnostics | **13 cases reproduced** |
| Additional browser diagnostics | Concurrent edit lost; initial project error hidden; blocked progress polling silently stopped |

The nine backend skips concern the unavailable local LaTeX engine. The initial ordinary pytest invocation failed to create Windows' shared pytest temp folder; rerunning with a new directory inside this workspace resolved that environment problem. Initial browser attempts also exposed mistakes in my test setup: nonexistent fixture names, shared-data interference between simultaneous journeys, and the normal hourly submit limit after repeated runs. The final journeys ran sequentially on fresh test data, with a valid fixture and increased **test-only** rate limits.

The additional diagnostics deliberately assert the faulty behavior, so **passing them means reproducing a defect**, not proving a fix. They are kept outside normal acceptance tests. Claude should turn them into assertions of the correct behavior when fixing the code.

## Ranked findings

P1 means fix before production use of the affected feature. P2 means a material correctness or recovery issue. Each location is relative to the repository; line numbers refer to the audited HEAD.

### 1. P1 — Source fetching can bypass the private-address guard through a second DNS lookup

**Location:** `backend/app/analysis/fetch.py:37`, `:62`.

`_public()` resolves a hostname and checks its addresses. The subsequent HTTP request uses the hostname again, allowing another DNS lookup. The connection is not bound to an address that passed the check.

**Reproduction:** A test hostname resolved to a public address for `_public()`, then to `127.0.0.1` for the actual HTTP connection. `_get()` read a local endpoint's response. This used a real local socket, not a mocked HTTP response, and contacted no external or cloud endpoint.

**Fix:** Bind each connection to a validated address while preserving the correct Host header and TLS verification; apply the same treatment after every redirect. Explicitly handle proxy behavior too. Keep the public-address checks. Add a rebinding regression case with a local server.

### 2. P1 — Formatting erases custom headers or footers in later sections

**Location:** `backend/app/formatting/apply.py:189`–`:204`.

Only the first section's chosen header/footer is checked for existing text. If it is empty, the formatter adds page numbers and sets every later section's corresponding container to `is_linked_to_previous=True`. That discards a later section's distinct content.

**Reproduction:** A two-section DOCX had an empty first header and a custom second header. APA formatting removed the custom header, while `body_text_unchanged` remained true and no preservation warning was emitted. The body fingerprint does not include header/footer text.

**Fix:** Inspect each section independently. Preserve custom containers and their linkage; insert page numbering only where safe, or report what must be done manually. Extend preservation checks to the document parts the formatter changes.

This affects the existing formatting service, not only Proposal V1.

### 3. P1 — The documented bucket lifecycle contradicts renewable proposal retention

**Location:** `docs/deployment.md:26`–`:33`; `docs/decisions.md:166`; proposal artifacts under `users/{uid}/projects/{id}/`.

The deployment guide applies a bucket-wide deletion rule at object age 31 days. The approved project policy is 30 days **after the student's last genuine action**, and those actions extend project metadata without rewriting all existing chapter and evidence objects.

**Failure example:** A chapter created on day 0 belongs to a project edited on day 29. The UI promises retention until roughly day 59, but the chapter becomes eligible for bucket deletion on day 31. Exports or later chapter consistency checks then lose their inputs.

Google documents that lifecycle `age` is measured from object creation time. [Cloud Storage lifecycle documentation](https://docs.cloud.google.com/storage/docs/lifecycle#age).

**Fix:** Separate renewable project artifacts from files governed by fixed-age deletion, through separate buckets or safely scoped object prefixes. Initially use the application's transactional project cleanup for renewable artifacts; any storage backstop must follow the same renewal policy. Correct the deployment guide and inspect the live bucket's actual rule before enabling proposals. **I did not verify or change the live bucket policy.**

### 4. P1 — Project deletion can win after the project claim but before paid submission

**Location:** `backend/app/proposals/service.py:378`–`:403`; `backend/app/jobs/service.py:442`–`:487`, `:896`–`:910`.

Claiming the project and accepting the job/holding credit are separate transactions. Project deletion ignores the unexpired QUOTED claim: it only treats ACTIVE job statuses as running. The later wallet/job transaction does not revalidate the project.

**Reproduction:** Injected project deletion exactly before submission's `update_job_and_wallet`. Deletion returned 204. Submission then returned 200, leaving a **QUEUED job with HELD credit and no project**.

**Fix:** Make project reservation, paid acceptance and deletion exclusion a single atomic invariant. Firestore can transact over project, job and wallet together; local storage needs equivalent locking and crash recovery. A reservation generation must also fence a request that resumes after the 120-second claim timeout. Revalidate ownership, deleting state, plan version and reservation at acceptance. Ensure admin retries respect the same project reservation.

This can waste provider spend even if the later export fails and refunds the student.

### 5. P1 — Cleanup deletes a project that was renewed after the expiry query

**Location:** `backend/app/jobs/service.py:896`–`:917`.

The expiry query returns candidate projects, but the deletion transaction does not check the current `expires_at` again. It checks only whether the recorded step is active.

**Reproduction:** Collected an expired project, then successfully saved its details to renew it for another 30 days. Cleanup used the earlier listing and erased the newly renewed project.

**Fix:** Pass the cleanup cutoff into the atomic deletion claim and recheck the current expiry there. User deletion and expiry deletion need distinct predicates. Keep interrupted deletion resumable. Also paginate expiry candidates rather than treating the first 500 as the entire collection.

### 6. P1 — Deleting a project retains private proposal material in child jobs

**Location:** `backend/app/jobs/service.py:909`; `backend/app/proposals/service.py:336`–`:369`.

Project deletion removes the project prefix and record. Frozen inputs and paid-call caches live under separate `users/{uid}/jobs/{jobId}/internal/` prefixes and remain. These can contain the study inputs, personal-name filters, approved plan and generated proposal wording.

**Reproduction:** Completed a plan, deleted the project successfully, then read exactly the same `internal/proposal_input.json`, including the private name, from its retained child job. The job record also remained.

**Fix:** Delete or redact every associated child job's private artifacts as part of project erasure, with a resumable deletion claim. Find them by project ID, not just the project's last-100-job list. Retain only deliberately chosen financial/operational metadata where necessary. Apply the same process to expiry cleanup.

### 7. P1 — Tables and captions bypass proposal evidence checks and citation rendering

**Location:** `backend/app/proposals/pipeline.py:350`–`:360`, `:403`–`:438`; `backend/app/proposals/export.py:188`–`:197`.

The deterministic checks and final stripping inspect only paragraphs. Table rows and captions are copied through. They also bypass the citation renderer and cited-source collection.

**Reproduction:** The writer returned a work-plan table containing `73% ⟦E999999⟧` and a caption containing `Smith (2019)`. The job finished **FULL**, and the invented percentage and unresolved token appeared in the downloaded Word table.

**Fix:** Validate all delivered text: paragraph text, table cells and captions. Render tokens and collect references from all those fields. Recheck repairs on the same complete text surface. An invalid table must be repaired, withheld or explicitly marked incomplete, never declared checked.

### 8. P1 — The complete-export gate accepts empty approved chapters

**Location:** `backend/app/proposals/export.py:27`–`:45`; `backend/app/proposals/service.py:217`–`:229`.

The final gate requires chapter objects, approval and non-stale dependency hashes. It does not require nonempty content, required sections, or resolution of blocking readiness failures. Chapter approval has no structural gate either.

**Reproduction:** Three approved chapter objects with zero sections and a CODE readiness item marked MISSING produced no final blockers. `build(..., draft=False)` created an unstamped complete document.

**Fix:** Derive required structure from the project's rulebook and study type, and enforce it before final export. Distinguish hard structural/integrity blockers from advisory AI judgments and programme-dependent recommendations. Do **not** turn the recommended 30-reference count into a universal hard blocker. Approval should not make missing required content complete.

### 9. P1 — A dirty editor silently adopts a newer version number and overwrites concurrent work

**Location:** `web/src/features/proposals/plan-editor.tsx:54`–`:62`, `:87`.

When the editor is dirty, it keeps its old local plan as intended. However, saving sends the **latest prop's** `project.planVersion`, rather than the version from which the dirty draft was derived. This defeats the backend's otherwise correct optimistic concurrency check.

**Browser reproduction:** Edited the title locally, accepted a new plan step, saved a different problem statement through another request, and let the finished step refresh the project. Saving the local title then also overwrote the newer problem with the old one; the server accepted it because the editor supplied the newer version number.

**Fix:** Capture a base version with the editor's source plan and retain it while dirty. When a newer server version arrives, preserve the local draft and show a conflict/reload/merge choice. Never update the base version independently of the draft content.

### 10. P1 — An unreviewed chapter can finish FULL when the review budget runs out

**Location:** `backend/app/proposals/pipeline.py:388`–`:420`, `:485`–`:490`.

A missing review becomes an issue only when `runner.budget_reached` is false. Once the budget is exhausted, missing reviews are omitted from unresolved issues. If the paragraph checks pass, no warning or PARTIAL outcome is set.

**Reproduction:** Made the review return no grades with `budget_reached=True`. The chapter finished **FULL**, with no warnings. Deterministic token/number checks cannot establish whether the prose preserves source meaning or obeys the plan.

**Fix:** Track review coverage explicitly. Budget exhaustion must leave unreviewed sections identified as such, with PARTIAL status and actionable warnings. Separate mechanical trace checks from semantic review. Withhold claims that require an absent review; do not describe all delivered prose as independently checked.

### 11. P1 — Proposal repairs run one extra round and the final fix is not reviewed

**Location:** `backend/app/proposals/pipeline.py:382`–`:401`; `backend/app/pricing/quote.py:162`–`:166`.

The loop allows `repair_attempts + 1` iterations and fixes on every iteration, including the last. With the configured limit of two repairs, that permits three fixes. The third fixed output has no subsequent review. Pricing budgets for two fixes.

**Reproduction:** The orchestration sequence was `review → fix → review → fix → review → fix`. Identical requests may be served from cache; the defect is the extra permitted repair and absent final assessment. Changed repair outputs can incur the additional provider cost.

**Fix:** Allow at most two repair calls and assess the last changed output before publication. Keep the loop, quote projection and stored review coverage aligned. Preserve unresolved concerns rather than assuming the last fix resolved them.

### 12. P1 — Adding an objective does not invalidate sections covering the full objective set

**Location:** `backend/app/proposals/decisions.py:47`–`:99`.

Staleness compares only decision IDs recorded when a section was written. New objective/question/alignment IDs were not in that earlier stamp, so their addition is invisible to the comparison.

**Reproduction:** Added a fourth valid objective, question and alignment row. `changed()` correctly reported `O4`, but the chapter section containing the original three objectives was still considered current. Chapter Two can likewise omit the newly required empirical review without a stale warning.

**Fix:** Hash relevant set membership as well as each row's content. Revalidate expected chapter sections after changes to objective count and study type. Keep unaffected per-objective reviews current, while flagging sections that describe the complete set and identifying new required sections.

### 13. P1 — A year in the student's notes is accepted as an author-supplied population size

**Location:** `backend/app/proposals/pipeline.py:285`–`:297`.

`_student_figures_only()` treats any matching number anywhere in the input JSON as provenance for population N or a stated sample. Matching digits do not identify what the student said the number means.

**Reproduction:** The only supplied number was “The study will be undertaken in 2026.” A model-proposed population of **2,026** survived the guard instead of being removed and asked about.

**Fix:** Bind these values to explicit author-owned population/sample fields and provenance, or require the author to confirm a specifically extracted interpretation. Free-text years, ages, programme codes and unrelated counts must not silently satisfy N or n. Calculate sample size only from those confirmed values.

### 14. P2 — APA 6 first-use author rendering follows replacement order, not reading order

**Location:** `backend/app/proposals/evidence.py:104`–`:114`.

`Citer.render()` replaces all parenthetical runs before narrative tokens. A later parenthetical citation marks the source seen before an earlier narrative citation is processed.

**Reproduction:** A paragraph starting with the first narrative citation of a three-author work rendered `Okello et al. (2022)`, while the later parenthetical citation rendered the full three names. The first-use forms are reversed.

**Fix:** Render left to right with a single ordered traversal, preserving grouped citations and cross-chapter first-use state. Add narrative-first and parenthetical-first tests for the same work in one paragraph.

### 15. P2 — Proposal loading and progress errors can leave the UI silently stuck

**Locations:** `web/src/features/proposals/project-page.tsx:232`, `:259`; `web/src/features/proposals/shared.tsx:83`; `web/src/lib/api-source.ts:94`.

The initial project loader stores an error but returns the skeleton before rendering it. Separately, StepProgress omits the `onBlocked` callback even though `watchJob` stops after a 401/403.

**Browser reproductions:** A project GET returning 503 left a skeleton without the server error. A progress GET returning 403 stopped further polling and left “Queued” visible without an error. The second case applies to temporary attestation problems as well as authentication loss.

**Fix:** Render a recoverable initial-load error before the loading return, with an explicit retry. Wire the blocked callback into proposal progress and estimate progress, show the server message, and offer a controlled restart of monitoring. Do not keep a stopped watcher looking like live progress.

### 16. P2 — Proposal reviewer warnings are discarded

**Location:** `backend/app/proposals/pipeline.py:392`–`:413`.

The reviewer can return PASS_WITH_WARNINGS with a note for the author, but the pipeline considers issues only for REPAIR and never copies the warning note into the chapter or job. The independent assessment's caution is lost.

**Reproduction:** Every reviewed section returned PASS_WITH_WARNINGS with a specific author-confirmation note. Both chapter and job warnings were empty, and the note was absent from the chapter response.

**Fix:** Preserve those notes with section locations and show them in the chapter and job result. Store grade/coverage separately from mechanical validation. A reviewed warning need not make otherwise valid content unusable, but it must reach the student.

## What holds up in this review

- Production separates API and worker routes and requires a Google-verified worker identity; the public config's App Check exception is narrowly scoped. Its available-service response is still calculated by the server.
- No runtime mock provider or rule-based imitation of paid AI was found. Missing keys are refused; test stand-ins remain in the test harness.
- Wallet/job transitions share transactions or local crash-recoverable writes. The existing cases for grant replay, repeated submit, refunds, account closing and retention/submission races pass. The new proposal-project transaction boundary is the additional problem in finding 4.
- Upload names are unique per attempt. Existing tests cover identical reuploads and cleanup of late uploads. DOCX intake checks container expansion, unsafe paths, macros and encryption.
- Existing refinement preserves locked Word elements and reviews repairs before accepting them. Deep Redraft's grouping respects document barriers and bookmark ranges. Its ordinary browser journey passes.
- Evidence quotations are checked independently against source text/abstracts. Bibliographic metadata and evidence-token rendering are useful foundations. They do not establish support for arbitrary new prose or the unchecked table surface in finding 7.
- Frozen engine/prompt metadata and validated answer caches support reuse of estimate work. Nothing in this audit required changing the approved lead/writer roles or pricing policy.

## Release sequence I recommend

1. Fix source-fetch binding and DOCX header/footer preservation. They also affect established services.
2. Reconcile bucket lifecycle with renewable project retention; fix project acceptance, cleanup and deletion invariants.
3. Fix the dirty-editor base version, added-objective dependencies and author-figure provenance.
4. Validate every delivered proposal field; fix review coverage, repair bounds and final structural gating.
5. Fix citation reading order and visible UI recovery, then turn these reproductions into correctness regression tests.
6. Rerun the established checks and both browser journeys. Run a genuinely independent Sol/Opus proposal on the approved real models, inspect its output in Word, and verify Cloud Run/Tasks, App Check and the live bucket lifecycle against the candidate release.

Claude's reported live run with Sol in both roles does not verify the approved Sol/Opus path. I made no real paid model calls. Local success also does not certify live IAM, real browser attestation or Word rendering.

Keep the existing App Check TTL while evaluating the warming change; a longer TTL is not a fix for missing error handling. Add the frontend unit tests to CI (the current web job builds but does not run them). Before paid public launch, address durable financial history beyond the wallet's 300 display entries and measure resource use under representative concurrent uploads/jobs. These are follow-up release gates, not additional reproduced findings above.

## Reproduction artifacts

- `docs/codex_audit_reproductions_20260928.py`: 13 isolated backend cases for findings 1, 2, 4–8, 10–14 and 16. Run explicitly from `backend` with a **new, nonexistent** `--basetemp` directory and `-p no:cacheprovider`. Pytest clears its base directory, so never point it at owner data. All model calls in these cases use `tests.fake_models`.
- `web/scripts/codex-audit-proposal-ui-20260928.mjs`: real-browser cases for findings 9 and 15, intended for the isolated test-only stack on 5001/8001. It uses synthetic project content and simulated failure responses. It is an audit diagnostic, not a production script.

Finding 3 is a deployment-policy conflict grounded in the checked-in configuration and Google's documented semantics; no live bucket experiment was performed. Findings and suggested fixes are recommendations for the owner, not automatically approved product-decision changes.

## Temporary audit files and cleanup

Both isolated test servers have been stopped. I removed my temporary launcher, Vite configuration and copied journey scripts. Automatic approval review rejected the recursive removal of my temporary test/build directories with the message **“blocked by policy”**; it supplied no more specific reason. I did not bypass that rejection. These directories contain isolated test data and output, not the owner's application data:

```text
backend/.codex_audit_tmp_20260928/
backend/.codex_browser_clean_20260928/
backend/.codex_browser_data_20260928/
backend/.codex_browser_final_20260928/
backend/.codex_final_checked_20260928/
backend/.codex_final_repros_20260928/
backend/.codex_repro_tmp_20260928/
backend/.codex_repro_verified_20260928/
backend/.codex_small_repros_20260928/
backend/.codex_warning_repro_20260928/
web/codex_audit_build_20260928/
web/codex_browser_proposal_20260928/
web/codex_browser_regular_20260928/
```

Keep the report and two reproduction artifacts listed above. The preexisting UCU manual, earlier verification report and owner data were left alone. No application source code was changed.
