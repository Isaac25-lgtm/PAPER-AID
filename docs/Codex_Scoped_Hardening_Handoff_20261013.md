# PaperAid: scoped hardening and verification handoff to Claude

13 October 2026. Local candidate based on `97cd500` (application release `52a59c1`).

## Release status and owner decisions

These changes are **uncommitted and not deployed**. Do not describe them as live. The owner requested fixes and tests for coursework, academic research proposals/thesis and funding, then independent Claude verification and agreement before deployment. The owner approved up to **US$15 total** for synthetic real Vertex acceptance tests and explicitly chose to **keep the existing Flash fallback**. The writing algorithm remains workflow 1; the methods contract and partial chapters remain off. Existing released prompt files have not been edited; two new proposal prompt versions were added after a real regression was reproduced. No additional model stage was added.

The objective is better protection and reliability without rebuilding the writing/review process. No audit or finite test suite can certify perfect code, universal academic correctness or 100-user production capacity.

## Correction to the earlier audit

**Withdraw the broad PAI-001 finding.** Claude correctly pointed out that persistent academic chapters, work documents and datasets are outside the bucket's `users/` lifecycle prefix. They use `projects/`, `works/` and `datalab/`. Do not change the bucket lifecycle because of the withdrawn finding. The real, narrower defect was an expired transient Data Lab job input being read during resume. Dated correction notices were added to the older reports in `audit-output/2026-10-13`.

Also retain these earlier corrections: coursework/funding already had a retraction check; the old 29 failures were caused by Codex's global algorithm override; production aggregates mixed releases; local fake-load tests did not establish real Gemini/Firestore throughput.

## Changes made

### 1. Upload admission and request size

- New `backend/app/core/uploads.py`: authenticate multipart requests before parsing/spooling, then enforce the actual streamed byte count. Missing or dishonest Content-Length cannot bypass the cap. Partial parser files are closed on rejection.
- Multipart ceiling is the configured upload size plus 1 MiB envelope overhead. JSON/nonmultipart requests default to a 4 MiB ceiling. Existing 20 MiB file and word/page limits remain.
- Two multipart uploads per API process by default, configurable from one to four. Excess simultaneous uploads receive a retryable 429 before their bodies are read.
- `app/core/auth.py` caches only the fully verified identity within that request; optional verification does not weaken App Check.
- `app/jobs/service.py` applies the existing per-person upload counter to paper uploads too. This shared control also supports research guide uploads.
- `app/main.py` installs admission on API/all roles and disables OpenAPI, Swagger and ReDoc in production.

### 2. Untrusted document resource bounds

- `app/documents/pdf_io.py` and `intake.py`: uploaded Word/PDF parsing runs in a child process, one child per API process. Deadline 25 seconds; a busy reader returns 429 instead of allocating more children.
- Linux children have 384 MiB address-space and 15-second CPU limits. Windows has wall-clock/decoder limits, **not an OS memory ceiling**. The Linux image gate is still required.
- PDF extraction stops when the word limit is crossed and bounds page/total characters. The decoder bounds zlib expansion too. Crashes and parser faults are classified as invalid/too-complex documents, not raw internal errors.
- Research PDFs fetched from source websites use the same isolation while preserving their exact extracted wording and the existing first-60-pages scope (`app/analysis/fetch.py`). An unreadable source remains unreadable; no quote is manufactured.
- Child output is explicitly UTF-8. Windows fixture tests caught and fixed the initial encoding mistake.
- No new AI call. Process startup adds a small reading overhead; this is a safety change, not a turnaround-time optimization.

### 3. Durable provider-call accounting

- `app/jobs/models.py`: private `pending_calls`/`CallIntent`, and optional `ModelCall.call_id`. Historical jobs remain readable; student views do not expose pending intents.
- `app/jobs/pipeline.py`: reserve a unique call allowance **durably before** invoking the provider, under the attempt/stage ownership fence. A failed reservation makes no model call.
- `app/ai/orchestration.py`: account live durable allowances once, retain allowances for unknown outcomes, settle known costs, release local waiters even when accounting fails, and keep existing retries/fallback/cache rules.
- A crash after the SDK request but before its record cannot erase the allowance. A retry may purchase work again, but it must fit beside the retained allowance. This bounds uncounted replay; it does **not** promise exactly-once external inference.
- A replaced attempt cannot start another call or publish. It may settle only its own existing intent when its already-purchased response arrives, so the business cost is not hidden. Tests check the replacement's stage/owner remain unchanged and a repeated callback does not add cost twice.
- Existing unknown-billing reservations remain separate from confirmed spend. Do not clear them automatically to make a job fit.
- Real tests exposed a micro-dollar rounding residue after fully settled calls. New intents round the allowance upward once, then persist and release that same amount. The regression settles ten fractional allowances and requires no phantom reserve. The original trial ledger is retained unchanged.

### 4. Optional daily application spend ceiling

- `DAILY_AI_BUDGET_USD` defaults to unset. No production ceiling was selected or enabled by Codex.
- `integrations/store.py`: job and UTC-day allowance ledger change together. Local store uses its crash-replay journal; Firestore uses a transaction over the job and `ai_spend/{day}`.
- Concurrent admissions cannot both take the final allowance. Actual provider cost is still recorded when it exceeds an estimate; records are never discarded because an already-purchased call crossed the limit.
- The ledger holds aggregate amounts, no student content. Call intent records the admission day for correct settlement across midnight.
- This is an **application admission control**, not a hard Google billing-account limit. Grounding usage can exceed an estimate; other consumers of the Cloud project are outside this ledger. Configure at a quiet boundary and reconcile any earlier same-day activity before relying on it.
- A global daily Firestore document can become a contention point at high call throughput. Verify production transaction behaviour and capacity before enabling it broadly.

### 5. Per-person job admission

- `jobs/service.py`: repeat the active-job limit check inside the owner-wallet admission transaction, including resume/requeue. The existing outer check stays for a quick refusal.
- Local concurrency regression admits exactly three of four simultaneous submissions with a limit of three. Firestore submissions contend on the same owner wallet; its transaction retries must re-read the count.
- No second hold on a rejected admission. Real Firestore/emulator concurrency remains a Claude gate.

### 6. Diagnostics privacy

- `core/logging.py`: recursively remove content/secret fields, omit arbitrary objects, do not render interpolated arguments or third-party messages. Exceptions emit type and structural frames, not exception text/local values.
- `jobs/pipeline.py`: unexpected failures save the exception class, not its potentially private message.
- `jobs/service.py`: support/expired views remove student-specific failure wording. Admin failure detail contains code and attempt count; the owner's view keeps its useful explanation.
- Tests inject a private sentinel into nested logging inputs and failure messages and prove it is absent from admin/log output.
- Tradeoff: support receives less prose. Use codes, stages, call rows and frame locations for diagnosis.

### 7. Proposal source integrity and preprints

- `proposals/models.py`, `pipeline.py`, `evidence.py`: explicit retraction/check/preprint fields; known retractions are unusable, and index-flagged retractions are rejected before extraction. Retraction status survives deduplication.
- For **new academic policy version 2**, proposals re-check distinct library DOIs with at most three parallel lookups and reuse the day's results. Saved decisions are used during drafting/export without another lookup and retained in the reusable evidence library.
- Unavailable lookup is labelled unverified; it never becomes a fabricated clean result. Existing coursework/funding final checks remain.
- Preprints identified by registry/index status are labelled in APA 6, APA 7 and Harvard references and source context. This is not a universal preprint classifier for every website or proof of source suitability.
- New work inputs use `academic_policy=2`, new proposal inputs now use version 3 (the Chapter Three correction below); 0/1/2 remain accepted and retain their older payload behaviour. Frozen input bytes/hashes are not rewritten.
- Distinct DOI lookups add HTTP work and can add latency. No extra model stage/call. Measure this cost in real acceptance results.

### 8. Shared thesis/Chapter Four safety

- `datalab/engine/stats.py`: check the observed category cardinality before constructing a dense cross-tabulation. No statistical estimator changed.
- `datalab/service.py`: an expired transient input is not blindly read to resume an old report/theme job; the normal new-quote path is used instead.
- These are shared engine/recovery fixes, not a new standalone Data Lab project. Existing Chapter Four tests and the shared browser journey cover the connected path. A complete Chapter Five/discussion/conclusions generator is not established by these changes.

### 9. Reproducible build and candidate-image tests

- New `backend/constraints.txt`: exact resolved production/cloud/dev dependency closure from the tested local environment. `uvloop` and build-only `setuptools` were resolved from public package metadata and are not locally exercised.
- `Dockerfile`: pin Python base-image manifest digest and apply constraints during package installation/build isolation.
- `.github/workflows/ci.yml`: build the candidate with LibreOffice, run native rendering and dependency checks, then run the suite against `/srv/app` inside the image with provider calls blocked and synthetic tests mounted read-only.
- Docker is unavailable locally; **the new Linux image workflow has not been executed**. Do not claim its gate passes. Native apt packages are not hash-locked and this is not a package supply-chain certificate.

### 10. Chapter Three failure reproduced on real models and corrected

The first real Chapter Three stopped with 12 of 14 sections approved: Sampling and Quality Control were rejected. The saved responses prove a repeatable conflict, not merely a screenshot or a conjecture.

- Number provenance compared spellings literally: the approved proportion `0.5` did not accept `0.50`. Added exact decimal-equivalence matching while keeping percent units and signs distinct, with no rounding. The ordinary-small-count check still sees the original spelling. Negative values now retain their sign.
- The model's internal brief asserted that `0.70` was an acceptable reliability threshold without evidence. Reviewers then treated that point as mandatory, demanded a citation, and demanded it be restored when the writer removed it. New proposal policy 3 filters unsupported numeric brief points before drafting/review; the institution requirement stays. This does not waive a real criterion or fabricate evidence for it.
- New `p-review-v9` and `p-fix-v7` distinguish code-calculated sample assumptions from measured findings, and working brief suggestions from binding institutional requirements. An assumption is not a claim of observed prevalence. Contradictory calculations, invented populations and unsupported scientific standards still require repair.
- The same synthetic project then delivered Chapter Three with 1,584 words. The old failed run remains in the cost/reliability evidence; it was not charged or deleted to improve the figures.
- New regression cases cover decimal equality, sign/unit/value differences, the unsupported brief threshold, preservation of the institutional requirement, calculator context and older input payloads.
- `proposals/service.py` sets policy 3 only for newly frozen proposal inputs. `ai/orchestration.py` selects the new prompt versions for newly priced engines. `released.json` registers their hashes; old released prompt bytes and old engine bindings remain.

### 11. Research exports and calculation attribution

- The delivered research Word document contained a Unicode minus (`U+2212`) in the sample formula. Its PDF failed with that exact unsupported-character error. `latex/convert.py` now maps it to a safe mathematical minus; the image's LaTeX self-test includes the formula. The actual synthetic research document now compiles with zero omissions and no conversion warnings. This adds no model call.
- The generated Sampling section named Krejcie and Morgan but the bibliography omitted the method. New `proposals/calculation_references.py` supplies frozen bibliographic identity for the three formulas code implements. Primary records: [Krejcie and Morgan, DOI registration](https://api.crossref.org/works/10.1177/001316447003000308), [Cochran, Wiley catalogue](https://www.wiley-vch.de/en/areas-interest/mathematics-statistics/sampling-techniques-978-0-471-16240-7), [Yamane, Google Books record](https://books.google.com/books/about/Statistics.html?id=Wr7rAAAAMAAJ).
- This is method attribution, **not a new verified evidence item** and not confirmation of a student's population, instrument or scientific threshold. No invented passages or evidence tokens are added. The records are not sent as extra model context. Code adds a year only to an author attribution already present in the approved Sampling prose, and includes its matching reference.
- New chapter inputs freeze the method record; a delivered chapter retains it only when Sampling actually names that method. Preview and Word export use the same renderer; PDF uses the Word document. Revision/completion carry it with the Sampling section, and guide alignment removes it if that attribution disappears. Older input/document records default to no method record, preserving historical displays.
- Tests cover the three methods and three citation styles, no manufactured mention or duplicated year, preview/Word agreement, historical/legacy rendering, revision carry-over/removal, and storing a reference only for a named attribution.
- Real paid runs preceded this last metadata/export correction. A **separate offline renderer check on copies** of the real synthetic chapters verified the citation, bibliography and full PDF; it did not rewrite trial records or rerun a model. Files are `research-proposal-render-check-with-method-reference.*`.

## Verification evidence

All ordinary/backend/browser test processes block paid SDK boundaries. Logs, fixture outputs and real acceptance artifacts are under `audit-output/2026-10-13/`.

- First completed full candidate suite: **1,543 passed, 3 failed** (`hardening-gate.log`/XML). Do not call this one clean full gate.
- Failure 1: an old concurrency stand-in bypassed `AIRunner.__init__` and needed initialization of the new durable-live counter. Fixed the stand-in, preserving its waiting assertions.
- Failure 2: the full run collected the new provenance test before its final fixture correction. A web-type fixture is correctly NOT_APPLICABLE; the intended journal fixture now explicitly says ARTICLE. Current targeted test passes.
- Failure 3: the spending-stop regression timed out on a maximum-length paper with hundreds of stand-in calls. Its purpose is stopping at the second review batch, so it now uses a short paper with the existing forced-small batch size. It still requires two reviews and checks partial delivery, originals retained and the spending warning. Separate maximum-length tests remain.
- After those corrections, a clean full gate passed **1,547 tests** (`hardening-final-gate.log`/XML). This was before the late real Chapter Three and method/export fixes; it is not the complete final candidate's result.
- After the Chapter Three correction, **129 academic tests** and **163 proposal/workflow/one-Start tests** passed (`hardening-academic-repair.log`, `hardening-proposal-final.log`). These overlap other counts.
- The method-reference/decimal-calculation/fractional-allowance selection passed **15 tests**. The earlier broader new-test run had three malformed test fixtures (missing required Project/SectionText fields); corrected fixtures pass. Its 73 passing cases included the native PDF regressions. Retain that earlier failure log rather than claim it was clean.
- **Final full run:** **1,572 passed, 2 failed, 4 warnings**, in 33m31s (`hardening-complete-parallel.log`/XML). Both failures were test deadlines, not a wrong delivered result. Do not describe this log as a clean full pass.
- Failure A: the forced-continuation test used a maximum-length dissertation, forced a new delivery after every paid stand-in call, and timed out in its 120-second estimate helper before its separate 400-second job deadline. It now uses a short paper with forced 300-word batches, preserving **at least ten continuations and no duplicate provider requests**. Maximum-size document tests remain. No production time limit or algorithm was changed.
- Failure B: the proposal test's repeated repair/removal loop exceeded its 60-second helper deadline while four workers competed for the laptop. Its one explicit wait is now 120 seconds; it still asserts invented `73%` and hand-typed `Smith (2019)` are removed, the safe sentence remains, and removal happens before the final review.
- **Both final corrected tests pass together**, in 45.84s (`hardening-final-two.log`/XML). Thus all **1,574 collected tests have a passing result across the full run and these two reruns**. A single clean full run of the final candidate is still a Claude release gate. Do not add overlapping targeted counts to 1,574.
- The earlier sequential attempt (`hardening-complete-final.log`) was deliberately stopped to use the release's parallel setup; it is not a completed gate. The four warnings concern non-estimable constant statistical fixtures, not silently released infinite results.
- The immutable-prompt regression passes on the final registry. New registrations initially used raw Windows CRLF bytes; they now use the application's normalized UTF-8 convention. Existing registered hashes and prompt wording were unchanged. The real model calls used the same normalized prompt text throughout.
- **72 document/boundary tests pass** (`hardening-document-final.log`), and **88 accounting/AI/speed regressions pass** (`hardening-call-final.log`). These overlap the above; do not add the counts.
- Web: **20 unit tests**, typecheck and production build pass. Lint and `git diff --check` pass.
- Browser: **all five journeys pass**: Start, works/funding, proposal, main and shared Data Lab/Chapter Four. Main initially failed because its job counter read the wrong temporary folder; matching `PAPERAID_E2E_DATA_DIR` fixed the test setup. No application fix was needed for that failure.
- The abandoned first suite hit recursion in its pricing/upload injection hook after upload quota was added. The test now injects the replacement upload once; it was never a student-path recursion. Retain the incomplete log, do not count it as a full pass.

## Real acceptance results

Finished. The explicit runner is `backend/scripts/scoped_acceptance.py`, separate from pytest, with synthetic identities/data, local storage/queue/wallets and real ADC Vertex calls in project `paperaid`, location `global`. It read the existing OpenAlex key into memory without exposing it or modifying secrets. Application admissions were capped at US$6 within the owner's US$15 authorization. No production job, real student data or payment collection was involved.

**Recorded confirmed AI spend: US$5.109619.** Retained unknown-call allowance: **US$0.315754**, plus a **US$0.000001 rounding residue** from the old trial code. Conservative total **US$5.425374**, below both caps. This is application accounting, not a verified Google invoice. No further paid calls are needed for the remaining export checks, and none were made after the follow-up.

| Synthetic case | Delivered outcome | Recorded AI cost | Time / size | Local artificial credit settlement |
| --- | --- | --- | --- | --- |
| Coursework, compare qualitative/quantitative methods | READY_WITH_WARNINGS; Word and PDF | US$0.331206, plan plus draft | 8.43 min; 1,300 body words against a 1,500 target | UGX 23,000 charged; no remaining hold |
| Research plan and Chapters 1–3 | All three chapters delivered after repairing the Chapter Three defect; Word and PDF draft export | US$2.656509 including the failed first Chapter Three; US$0.315754 unknown allowance separately | Ch1 1,954 words, Ch2 2,313, repaired Ch3 1,584; Ch2 approximately 20–22 min and repaired Ch3 7.31 min | UGX 19,000 charged for delivered chapters; failed Chapter Three charged zero |
| Funding proposal | Draft delivered, **NOT_READY**, with missing author targets/budget and visible warnings; Word and PDF | US$2.121904 including call reading, plan and draft | 33.70 min; 2,604 words | UGX 64,000 charged under the existing draft-with-gaps policy; no remaining hold |

These outcomes do **not** establish a service success rate. It is one synthetic example per service, with a research rerun. Funding is not a submission-ready success. Research is a labelled draft, not an ethics/methodology approval or proof of a complete thesis.

### Real test identities, failures and reruns

- Coursework `wrk_834bd3b7dbfb`: plan `job_c3ab762956f1`, draft `job_fdae8f5d21b9`.
- Research `prj_44f47cc51162`: plan `job_739228be432e`, Chapter One `job_9134e9268e82`, Chapter Two `job_dc2e62025525`, failed Chapter Three `job_250e54ca002b`, repaired Chapter Three `job_db2f07660957`.
- Funding `wrk_d4ef967e7408`: read `job_8a7a3bfa3207`, plan `job_28ef6bc86c3e`, draft `job_e115c82c36b0`.
- The initial funding harness attempted Start before reading the required call, and then without confirming eligibility. Those preconditions were correctly refused. Follow-ups read and confirmed the **synthetic** call on the same work; no duplicate was created. These are harness omissions, not reported product failures.
- Chapter Two recovered from four Flash `p_brief` 429 responses. Funding recovered from three provider-unavailable responses. Flash fallback remained enabled as the owner chose. These tail delays remain commercially relevant.
- The failed first Chapter Three had a Pro timeout with unknown billing; its allowance is still present. Never delete that failure or reserve to improve the reported margin or success rate.
- All three synthetic wallets now have zero held credits and empty reservations. No synthetic jobs remain QUEUED, PROCESSING or AWAITING_PAYMENT; the runner drained its local worker executor and disabled further processing on this **test store only**.

### Academic review of the actual delivered files

- Coursework answered the comparison and included examples/limitations, but prose remains heavy, 17 references are excessive for a basic task, and the PICO example's comparator/claims deserve human rubric review. A code PASS is not a grade or certificate of every inference's strength.
- Research Chapter One visibly includes a General Objective, three Specific Objectives and a conceptual framework. Chapter Three's repaired numerical assumptions remain provisional; the population 400 was an explicitly synthetic roster, not actual Makerere enrolment. The code rounds the calculation upward to 197; the original plan rationale mentioned 196, so Claude should independently review whether the editable plan wording explains that rounding consistently. Do not silently rewrite an approved plan or treat one different rounding convention as invented source evidence.
- The method-reference omission and Unicode-minus PDF failure were discovered by reading/downloading the real output and fixed as described above. They were not inferred solely from a successful job status.
- Funding's empty author budget is shown as a gap, not a balanced USD 60,000 budget. Targets I1/I2/I3 need author input. An unresolved review concern about unemployment/training causation and secondary UBOS citation quality merits scrutiny. The current product charges for the delivered draft with author gaps; verify that its warning/price promise makes this clear before paid launch.
- Existing thesis/Chapter Four shared paths were tested with stand-ins/browser fixtures, **not a real-model thesis or a new Chapter Five generator** in this run.

### Files for Claude to inspect

`audit-output/2026-10-13/real-acceptance/`: `coursework.*`, `funding_proposal.*`, `research-proposal-repaired.*`, `chapter-one.json`, chapter artifacts/metadata, `followup-2-final.json`, and **`job-finances-final.json`**. The latter reads settlements from `job.billing`; do not use a fabricated top-level charged field. Original failed/partial outputs remain alongside corrected copies. Raw trial state is under `backend/.trial/h13-live`, never a release input or commit target.

## Financial feasibility: what is and is not proved

The fixed student quote/refund policy remains. Test balances are artificial, not a payment-provider test. Durable intents improve cost visibility and bound replay against application caps. They add one persistence admission per real provider request; quantify Firestore overhead at scale.

Do not infer commercial margin from successful-draft AI cost alone. Calculate total cohort spend divided by delivered/paid work, including failures, repairs, unknown billing, grounding, FX, infrastructure/storage, payment fees and support. Existing prices/minimum credits/payment selection still require owner approval. A handful of synthetic successes is insufficient to establish success rate or 100-user capacity.

**Paid-launch blocker: the current per-job AI allowances are not margin limits.** The unchanged algorithm can legally spend far more on AI than the student's fixed quote:

| Step | Student quote at the quote's UGX 4,000/USD | AI allowance on the actual test quote |
| --- | --- | --- |
| Coursework | US$5.75 | US$11.348249 |
| Research Chapter One | US$1.75 | US$8.533253 |
| Research Chapter Two | US$1.75 | US$10.012148 |
| Repaired Chapter Three | US$1.25 | US$5.754856 |
| Funding proposal draft | US$16.00 | US$36.097699 |

Observed coursework AI spend was about 5.8% of its price; funding about 13.3%, but delivered with gaps. Research successful-run AI was US$2.085136 / US$4.75 = **43.9%**. Including the failed chapter, **55.9%**; including the unknown allowance, **62.6%**. All exclude hosting, payment fees, source/API services and support. The real cohort therefore did not meet a 50% AI-spend target for research once failures were included.

Do not arbitrarily slash repair budgets or raise prices within this safety patch: both require measured calibration and owner approval. Before money is taken, Claude should design and independently verify a versioned pricing/allowance policy using cohort costs and delivery reliability. The new daily admission ceiling remains unset in production; it improves control only when deliberately configured and reconciled, and it does not guarantee per-document margin.

## Candidate source inventory

Changed files are visible in `git diff 97cd500`. Newly created source/test files that ordinary `git diff` does not include:

- `backend/app/core/uploads.py`
- `backend/app/proposals/calculation_references.py`
- `backend/app/ai/prompts/p-review-v9.md`, `p-fix-v7.md`
- `backend/constraints.txt`
- `backend/tests/test_scoped_hardening_20261013.py`, `test_calculation_references.py`
- `backend/scripts/scoped_acceptance.py` (explicit opt-in paid harness; not an automatic release test)
- `docs/Codex_Scoped_Hardening_Handoff_20261013.md`

Other pre-existing untracked audit/handoff files are not all part of this change. Inspect ownership/history before staging. No web product source was edited.

`audit-output/2026-10-13/candidate-manifest.json` records the base commit and file digests for the changed/new source, test and build files. The prompt integrity check compares normalized UTF-8 content, as the application does. The handoff document itself is not part of that source digest set.

## Required Claude verification before any deployment

1. Review `git diff 97cd500` and the new untracked source/test/constraints files listed here. Do not commit trial data, generated fixtures, screenshots, helper servers or old audit folders.
2. Review call-intent settlement, stale-attempt ownership, local journal replay, Firestore read-before-write transactions, owner-wallet active limits and the daily-ledger rollout boundary.
3. Rerun the complete backend suite on the final candidate, then web checks/journeys as the release gate requires. Do not globally override FINAL_EDITOR for workflow-2 tests.
4. Execute the Linux candidate-image CI gate; confirm parser CPU/memory limits on benign maximum-size and adversarial files, native exports and locked dependency resolution. No paid models in ordinary tests.
5. Read synthetic real acceptance documents, not just status flags. Verify task coverage, general/specific objectives, methods/framework alignment, citation/source scope, required funding sections and budgets. Distinguish legitimate rejection from code failure.
   - Include retained/unrevised sections and historical/final exports when a source's retraction status changes; this patch does not implement continuous post-publication monitoring of every reference.
   - Include an institution guide with numeric methodological requirements: distinguish a real guide requirement from an unsupported model brief suggestion. Do not waive source checks to make either case pass.
6. Review explicit limitations: no proof of universal academic quality, no full thesis Chapter Five, no real payment collection test and no measured 100-job Gemini/Firestore load.
7. Agree on any remaining code findings and owner policy choices before releasing. Keep Flash fallback and the current writing algorithm; don't enable methods contract, workflow 2 or partial chapters as part of this hardening patch.
8. Review rollout/rollback for the new call intents and daily ledger. Pause/drain processing before switching between a version that understands these fields and one that does not. Historical job compatibility alone does not make an active-worker rollback safe or preserve a daily ceiling on older code.

## Operating tasks still pending

Cloud backup/PITR and a restore rehearsal; alerting/uptime/canary scheduling; verified billing/expiry/payment method; administrator MFA; payment provider and final prices; production credit/reservation testing; real load and observed-tail turnaround targets. Calculation-heavy coursework still needs its separately validated design; this patch does not implement a general mathematical solver. These require separate implementation, operational work or owner choices and were not changed in this local task. Do not mark them fixed because tests passed.

No commit, push, deployment, IAM change, production environment change, service account creation or secret rotation was performed by Codex for this candidate.

## Copyable next instruction for Claude

> Audit the local candidate in `docs/Codex_Scoped_Hardening_Handoff_20261013.md`, `git diff 97cd500`, and its listed new untracked source/test files. Independently check the fixes, real synthetic documents and financial evidence. Run the complete final backend gate, Linux candidate-image gate and necessary Firestore concurrency/recovery checks without paid model calls. Codex recorded US$5.109619 confirmed AI spend plus US$0.315755 conservatively reserved within the owner's US$15 task-wide ceiling; do not assume a new US$15 allowance. Keep workflow 1, Flash fallback, methods contract off and partial chapters off. Report confirmed remaining defects and pricing/operating decisions for Codex and the owner to agree on. Do not commit, push or deploy until that review and release decision are complete. Do not stage `.trial`, audit outputs or unrelated old handoff files.
