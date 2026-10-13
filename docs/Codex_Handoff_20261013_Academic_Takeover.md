# PaperAid: local academic takeover and hardening

Written for the owner and Claude. Started 12 October; continued 13 October 2026.

## State

- Repository: `F:\MY FILES\DATA SCIENCE\PAPER AID`, branch `main`, base commit `b808f41`.
- These changes are local and uncommitted. Codex did not push, deploy, change cloud configuration, change production secrets or make a paid model call.
- Claude's unfinished changes were preserved. The takeover completes that patch and implements additional academic contracts from the earlier academic fix plan. It is broader than the original rendering-only patch.
- Scope: coursework, academic concept papers and research proposals. Claude's small shared funding fixes were retained; a full funding dependency/cohort redesign was deferred.
- This is a code and offline integration result. It does not establish that every real-model draft will be correct or finish quickly.

## 1. Claude's unfinished patch

### Citations and reference identity

`app/proposals/evidence.py` removes an exact author name typed immediately before its narrative citation token. It preserves different names, names elsewhere in the sentence, parenthetical citations and APA 6 first/subsequent citation behaviour. The audited Mann, Kim, CDC and CASP passages are replayed from the stored audit fixture.

`app/analysis/fetch.py` retains registered book subtitles and publisher details. `app/proposals/pipeline.py` resolves full registered titles without duplicating the subtitle, records books as BOOK where the registration identifies them, and uses their recorded publisher. A bare web address cannot become a group author. DOI/title/year matching is retained; code does not invent an author to fill a missing record.

### Captions, tables and incomplete drafts

- A numbered caption supplied by a writer is stripped of its leading label before code adds its own number.
- The proposal's list of tables and body use the same numbering, restarting the table count within each chapter.
- Proposal tables are padded to their widest row; longer rows are not cut. Legacy ragged tables can also export without losing extra cells.
- A draft's cover states which of the three chapters are written, which remain and which are partial.
- A checked works draft containing marked author-owned gaps receives a draft banner in its stored Word file, including after figures are saved or a legacy file is rebuilt.

### Retained small funding changes

An empty budget is not complete. Explicit in-kind lines are known at no charge to that budget; an unentered zero cost remains unknown. The UI allows the applicant to mark an in-kind line, and the figures-only update path permits it. Budget tokens/tables use the same calculation. The existing evaluator receives the printed schedule and an explanation when a headline request/ceiling is shown beside an uncosted budget. No dependency graph, scheduling agent or new funding stage was added.

## 2. Legal-source hardening

Claude's first version treated a legal host or matching title as proof of an exact provision. It also removed the number but left the legal duty stated in PaperAid's own voice. Both were insufficient.

The guard now requires a conservative candidate for the **named instrument**, the stated year where supplied, and a **usable verified passage containing that provision**. A legal host can carry commentary and judgments; its domain alone proves nothing. A neighbouring sentence's citation cannot vouch for this sentence. Every provision in a sentence is checked, so a confirmed first provision cannot excuse a second unconfirmed one.

- Clear unconfirmed precision goes to the existing repair loop.
- A last-resort removal of the number explicitly attributes the remaining account to the cited source. It does not certify the legal meaning.
- Uncited statements do not acquire invented attribution.
- Conditional sentences, quotations and criticism remain intact and are given to the reviewer in context.
- Changed prose is reviewed again before release. The new reviewer prompts explicitly distinguish a source's account from an established legal duty.

This is a guard using evidence PaperAid already has. It is not a comprehensive legal database or a new primary-law crawl. Jurisdiction, operative meaning and source suitability still require contextual review. Missing primary text is never replaced with a guessed section number.

## 3. Methods crosswalk for new proposal plans

Files: `app/proposals/models.py`, `methods.py`, `ai.py`, `pipeline.py`, `rulebook.py`, `decisions.py`; related proposal UI and API contracts.

New `p-plan-v6` plans include a version-1 `MethodsContract`:

- Stable measurement IDs (`V1` etc.), labels and roles: outcome, predictor, adjustment, mediator, moderator or exploratory factor.
- Measurement scale, operational definition, unit, instrument/source, observation period and rationale.
- One methods row per specific objective: outcome ID, predictor IDs, estimator, rationale, diagnostics and any justified transformation.
- Selection units, eligible population frame, recruitment and planned protections/unresolved permissions.

The same plan contract reaches the existing final plan reviewer, writers and chapter reviewers. Chapter Three is not asked to independently choose a different outcome family. The older free-text alignment and narrative rationale remain; passing the schema is **not** statistical certification.

Code rejects duplicate/undefined measurement IDs, duplicate or unmapped objectives, undefined predictors/outcomes, an outcome reused as its own predictor, an incompatible declared outcome/model family without a stated transformation, and duplicate legacy alignment rows. Transformations and unknown measurements are still proposals for review, not automatic approval. A missing methods object in a new final plan fails without charging; code does not silently downgrade it to a legacy plan.

The review guidance specifically covers the audit's difficult cases: primary binary adoption versus descriptive intensity, separate outcomes for separate objectives, continuous predictors, sampling coverage/clustering/weights, self-report versus biological outcomes and their windows, statistical uncertainty, recruitment bias and permissions for minors. It prohibits invented clinical cutoffs, validation, approval and consent exceptions. Scientific suitability and protocol choices remain human/model judgements within the existing bounded process.

The optional study-details editor exposes these measurements and analyses after generation. It does not add a mandatory Start page or require the student to review an internal plan before receiving Chapter One.

## 4. Sampling and input provenance

- A model may keep N or a stated qualitative sample only when it matches the user's explicitly entered figure, as before.
- For new policy inputs, a model cannot manufacture the population's registry/source when the student left that source blank.
- N is labelled USER_SUPPLIED or UNKNOWN; typing a registry name is not independent verification.
- Optional design effect and non-response rate are copied only from explicit inputs. No stock design effect or non-response allowance is applied.
- `sampling.calculate` retains the base formula, applies supplied adjustments in code with separate steps and requires their rationale. It refuses an adjusted recruitment target above the accessible population and an adjustment applied to a census or qualitative/stated sample. It does not present a prevalence-precision calculation as proof of regression power.
- The optional editor presents these assumptions and their source/rationale; blank values remain blank.

New typed plans using N need a `FRAME` acknowledgment before a **complete** proposal export. The student confirms the exact eligible frame, source and date after generation; the acknowledgment is bound to the plan version and a hash of the relevant facts. It is idempotent, owned, costs nothing, makes no model request and does not waive a methods contradiction. Changing the relevant facts or plan version invalidates it. Chapter One and draft downloads remain available.

The new route is `POST /api/projects/{id}/population-frame`, with `baseVersion`. The Chapter Three workspace offers the confirmation and distinguishes student confirmation from independent verification. Historical chapter checks do not borrow a confirmation from a different plan version.

## 5. Frameworks and version consistency

`ChapterDocument.frameworkPlan` is stored in the artifact file, not the job metadata. It captures the priced plan for the chapter's diagram. Rewriting an unrelated section retains the earlier framework snapshot; a framework revision uses its new snapshot. Word, chapter views and the framework PNG consume that snapshot where available. Legacy artifacts retain their fallback behaviour.

For typed plans:

- Diagram edges come from the objective crosswalk's predictor/outcome IDs, not arbitrary box order.
- Additional factors are labelled neutrally with their declared roles; no dashed arrow implies an unplanned moderation or mediation effect.
- Unlinked proposed factors are identified in the description rather than silently given an association.
- Framework editing retains stable IDs when measurements are renamed. New measurements remain undefined until their methods are supplied; removing a referenced outcome/predictor cannot silently disconnect the analysis.
- A methods change is part of the decision hashes and marks dependent sections stale. The legacy hash is unchanged when the optional fields are absent.
- The workspace explains that proposed changes are not yet in the downloaded framework until the section is revised.

Colour remains a presentation preference: MONO, GREEN or BLUE. A colour change does not change the study plan or use an AI model. The UCU/owner objective-count and placed-statement rules are retained.

## 6. Evidence in the live works final review

`app/works/pipeline.py::_final_review` now gives the existing final reviewer the actual cited passages, statements, scope, cautions, access and recorded source provenance for the sections shown in each part. A section-to-evidence mapping and the printed reference identify what each item supports. The reviewer no longer relies only on citation presence and extracted statements.

The existing whole-request limit still applies, including source passages and reserved history room. Actual outgoing payloads are measured before a call. No verified quotation is truncated to force a fit. Missing/unusable evidence or context that cannot fit produces an unavailable review, never assumed approval. The manifest remains one entry per section, including spans across parts.

This can add input tokens and, for a long document, review parts or existing repairs. It does not add a model stage, a per-claim agent or an unbounded loop. **No honest extra-minutes or cost estimate is available without a real-model trial.** A large single section with very extensive evidence may still be unable to fit; paragraph-level evidence partitioning is a potential later optimisation and must retain complete claim coverage.

## 7. Versioning and stability

New prompt versions are registered in `released.json`:

| Step | Version |
|---|---|
| Proposal plan | `p-plan-v6` |
| Plan finalise | `p-finalise-v5` |
| Plan review/peer | `p-plan-review-v4` |
| Chapter draft/fix | `p-draft-v6`, `p-fix-v6` |
| Chapter review/peer | `p-review-v8` |
| Works draft/repair | `w-draft-v10`, `w-repair-v10` |
| Works section evaluation | `w-evaluate-v6` |
| Works final review | `w-final-v3` |

The superseded uncommitted Claude prompt versions remain present. Previously committed prompt bytes were not edited. New steps freeze `academicPolicy=1` in their stored input; legacy inputs default to 0. Absent optional sampling fields do not change the old decision hash or old model payload. The frozen pricing day is also passed explicitly into proposal planning/briefing.

No job-state, wallet, pricing formula, queue/lease ownership, attempt path, continuation, capacity or provider retry implementation was changed. Prompt/input sizes change where described above, and new typed plans have additional readiness requirements. Workflow 2, FINAL_EDITOR and partial-chapter production switches were not enabled. No model routing/fallback policy was changed.

## 8. Offline verification

Final checks on the completed local code:

| Check | Result |
|---|---|
| Complete backend suite, partitioned by file into three isolated runs | **1,512 passed**: 505 + 503 + 504; no failures |
| Web unit tests | **20 passed** across five files |
| Web typecheck and production build | Passed |
| Local browser journeys | **All five passed**: main, one Start, works, proposal and Data Lab |
| Backend lint and whitespace checks | Passed |
| Previously registered prompts | All **149** prior registered texts retain their canonical loader hashes |

The first full backend run exposed eight compatibility failures: one current prompt-version assertion and seven checks using a minimal input stand-in without `academic_policy`. These were fixed, the affected files passed, and the complete suite above was rerun on the corrected code. The final suite produced four warnings from a deprecated Pydantic test access and deliberately non-estimable constant-data statistical fixtures; no failed tests were waived.

No real model calls were made. The browser journeys use local fake models and local test data. Logs and screenshots are retained under `backend/.trial/` with `codex_takeover` / `e2e-takeover-20261013` names. That folder and existing audit/build artifacts are untracked; **do not use a blanket `git add .`**. Stage the reviewed source, prompts, tests, fixture and documentation explicitly.

The new regression file is `backend/tests/test_academic_takeover.py`. It covers frozen schemas/hashes, methods contradictions and negative controls, explicit sampling assumptions/arithmetic, provenance, version invalidation, neutral/accurate diagram edges, snapshots, ragged tables, primary-law identity/passages, multiple provisions, quote/condition preservation, final-review evidence and size refusal, and owned/idempotent/unbilled frame confirmation.

Claude's `test_independent_audit.py` and its stored audit fixture were retained and strengthened. Tests whose scripted plan-finalise answers intentionally change only unrelated fields now retain the required methods object from the draft. Earlier assertions pinned to a superseded current prompt were updated; frozen old-prompt coverage remains.

The Data Lab browser script initially selected an invisible sidebar match after reaching Your work. Its locator was scoped to the main content, and the complete journey was rerun. The application route itself was working; the failed selector did not prove a production navigation fault.

## 9. Claude's next audit and real-model acceptance

Read the full working-tree diff against `b808f41`, including new files. Do not describe this work as already live. Look hardest at:

1. Methods/schema compatibility, strict missing-contract handling and the distinction between structural code checks and semantic judgement.
2. Frozen inputs, legacy hashes, revisions, frame acknowledgments and historical views.
3. Evidence request sizes/cost caps, including large cited-evidence sets and re-review history.
4. Framework IDs, declared edges, snapshots, renaming/removal and stale sections.
5. Legal identity/provision matching and retained attribution/uncertain clauses.
6. Shared works export/figures behaviour, especially zero-cost lines and marked gaps.

After review, obtain explicit approval for paid trials. Recommended matched cases: D11 clinical/adherence, D12 school feeding and legal attribution/clustering, D14 multiple waste outcomes, D21 adoption/intensity and framework alignment, and basic coursework D15/D16. Also test all three proposal chapters, academic concept papers, changes with an attachment, frame confirmation, diagrams and Word/PDF downloads on the **same candidate code**. Compare the delivered text and evidence, not just whether each Gemini stage responds. Record cost, failure reasons, repairs and p50/p95 time; a zero-failure stage probe is not an end-to-end quality trial.

## 10. Limits and decisions still open

- Offline fakes cannot establish clinical validity, appropriate analytical power, truthful source interpretations, full academic quality or real-model reliability.
- Exact full-text quote locators, a finer claim-to-passage map and stronger source-type policies remain extensions. Do not invent a page number or imply independent verification from a verified quote. The final review currently maps evidence to sections, not every clause.
- A source classification is metadata, not proof that it is suitable for a specific assignment. Primary-law retrieval was not expanded into a separate crawler.
- The existing live algorithm's standard-model fallback can still approve when Pro cannot answer. This takeover preserved that policy. A guaranteed frontier-only final decision requires its own explicit versioned policy change; the newer strict editor path remains off.
- Partial-chapter policy, calculation coursework, paid prices/payment integration, funding dependencies and the ten-minute/load target are not resolved by this patch.
- Existing approvals and the researcher's own confirmations are not a substitute for a supervisor/statistician or an ethics/protocol decision.

No paid launch or release approval is implied by this report.
