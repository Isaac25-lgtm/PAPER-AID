# PaperAid: independent academic audit review and implementation handoff

**For Claude and the owner — 12 October 2026**

## 1. Verdict and scope

The independent audit identifies substantial academic-quality problems. Adopt its demand for traceable claims,
coherent methods, feasible schedules and honest readiness. Its assertion that several underlying contracts are
absent is too broad: existing code already implements evidence verification, chapter completeness, budget sums,
number tokens and an objective-to-method matrix. Extend these mechanisms instead of rebuilding them.

Keep the current pipeline, bounded repair loops, existing reviewers, task queue, credits, lease ownership and
checkpoint recovery for this work. Do not enable WORKFLOW 2 or FINAL_EDITOR as part of an academic-quality patch.
This recommendation preserves the orchestration; it does not claim stricter validation has no effect on delivery
rate, cost or time. Previously accepted defective work may need a repair, more user information or a draft label.

Reviewed material:

- `PaperAid_Independent_Academic_Audit_11Oct2026 (1).md` in Downloads.
- The ZIP's 21 DOCX documents: 14 first pass, seven second pass. Extracted paragraphs, headings, references,
  tables and image counts; inspected targeted academic, methods, funding and citation passages.
- Current repository HEAD `6f728f6`, relevant proposal/works models, evidence, sampling, framework, review,
  budget, Results Model and export code, plus local synthetic trial inputs.
- Targeted primary-source checks, including the Gulu University/publisher article metadata, the ASA statement,
  and the original Busoga referral study. The Education Act's old ESC PDF address returned 404 and direct ULII
  retrieval returned 403; search-index extracts support the concern but a full statutory extract must still be
  captured before certifying the exact legal repair.

This is not an exhaustive independent verification of every reference, a page-by-page Word/PDF layout review,
or a new live performance trial. No paid calls, tests, production changes or application-code edits were made
for this report. Document findings are separated below from confirmed code mechanisms and unresolved provenance.

## 2. Corrections to the independent audit's diagnosis

### A. An unfinished proposal export does not prove the completeness gate is absent

D20 has only Chapters One and Two, but its cover explicitly says it is not complete for submission. D13 is a
Chapter One draft. `proposals/export.final_blockers` already requires all three chapters, required sections,
chapter approval and applicable integrity checks for a complete export. Draft exports intentionally allow less.

Check the exact API route, `final` flag, selected action and job outcome before declaring a false completion.
A completed Chapter One job is not a completed three-chapter proposal. The owner's established Start flow delivers
Chapter One first. Do not require Chapters Two and Three at that first Start or reject every useful chapter draft.

Strengthen the visible scope: "Chapter One ready for review; proposal 1 of 3 chapters written", and put a
missing-chapter checklist in an incomplete export. Preserve the existing complete-export blocker.

### B. Several precise figures and organisational histories came from the test inputs

`backend/.trial/trial_quality.py` explicitly supplies the 2,400, 1,350 and 9,800 populations and their purported
registry names. It also supplies the applicant registration histories, the Kasenyi cooperative's 2014 registration,
and funding amounts of USD 85,000, 60,000 and 50,000. `trial_prop2.py` supplies 3,600, 5,200 and 6,100 and their
registry descriptions. These synthetic test inputs explain their appearance; they are not evidence that the
writer invented those particular numbers or histories.

They also do not authenticate the purported registers. Production needs to retain USER_SUPPLIED provenance and
distinguish an applicant's statement from independent verification. `_student_figures_only` already prevents a
model-picked sample-population number from replacing the user's entered number. Eligibility and frame scope still
need stronger checks: a register of all pupils is not automatically a frame of P5–P7 pupils.

### C. An evidence registry exists; support of every final sentence is still not guaranteed

`EvidenceItem` stores an ID, statement, source passage, scope, access level, source identity, retrieval date,
verification and support decision. An unverified or unchecked finding is not usable. The research stage verifies
passages and support, and section reviewers receive cited evidence. This is more than finding a nearby URL.

The remaining weakness is the transformation from a verified finding into the final sentence. A supported passage
can be misattributed, overgeneralised, made causal or assigned to the wrong measure. The numeric guard recognises
allowed numbers, not their full statistical or legal meaning. The works final whole-document review does not
currently receive the evidence passages alongside every part. Fix those gaps using the existing registry.

### D. Budget arithmetic and basic timing checks exist

`works/budget.py` computes line/category totals, ceiling and request reconciliation. `results.py` checks activity
dates against project duration and builds the workplan from the Results Model. The gaps are missing applicant
figures, narrative that misrepresents a ceiling as a reconciled request, cohort dependencies, follow-up timing and
resource feasibility. Rendering a Gantt from plausible month ranges does not prove the project is feasible.

### E. Do not overcorrect the statistics or framework

D21 may legitimately model binary adoption while describing an intensity count. It needs a declared primary
outcome and exact objective mapping; a separate count regression is required only if an objective seeks inference
about that count. Do not automatically add several regressions or convert all continuous variables into categories.

The current diagram explicitly says its arrows show associations, not proven causes. Arrows alone are not proof
of a causal claim. Its generic "intervening" category and arrow onto an association do conflate distinct roles,
however: mediator, moderator and adjustment covariate are not interchangeable.

## 3. Findings to act on, ranked by consequence

| Priority | Confirmed concern | Practical consequence | Recommended response |
|---|---|---|---|
| High | D12 repeats the compound Education Act section label `13(5)(2c)` from a secondary source | A precise legal proposition may be wrong despite matching a retrieved passage | Require primary-law support for exact statutory labels and operative meaning; otherwise remove the specificity or mark the proposition unverified |
| High | D21 models/measurements and multi-stage sampling are underspecified; D11 conflates adherence and viral suppression; D14 changes outcome families | A polished methodology may not answer its objectives defensibly | Extend the existing alignment matrix and review it before writing; refuse false methodological certainty, not all drafts |
| High | D19's narrative requires setup, consecutive six-month cycles and late post-placement follow-up within 12 months | Activities can fit individual Gantt ranges while the promised programme cannot finish | Model cohorts and dependencies explicitly; validate the dates and generate narrative from the same schedule |
| High | Draft funding budgets lack quantities/costs while narrative presents headline requests confidently | A grant ceiling may be mistaken for a validated budget | Keep marked draft downloads, distinguish ceiling from request, and require reconciliation for submission readiness |
| High | D21 cites the Kule study as `gu.ac.ug` with journal name as work title | The source is real but its scholarly identity is wrong | Resolve the underlying publication's canonical author/title/DOI; do not treat a university hosting page as its author |
| High, specialist judgement | Patient transport, minors, clinical records and engineering installations require safeguards beyond fluent prose | A document can imply safety or feasibility not established by its evidence | Add focused domain review requirements; unresolved material safety assumptions block submission readiness |
| Medium | D16 says a single statistical test can verify an effect and makes other sweeping methods claims | Learners receive incorrect methodological teaching | Improve existing writer/reviewer instructions and source suitability; treat semantic concerns as review findings |
| Medium | D15 prints `Mann Mann`, `Kim Kim` and repeated corporate names | Citation-token rendering can create grammar defects after writing | Fix the narrative citation boundary deterministically and expose final rendered wording to validation |
| Medium | D21 prints `Table 3.1: Table 3.1: ...` in caption and list | Export adds numbering to an already numbered caption | Code owns numbering once; use one canonical unnumbered caption for every export/list/preview |
| Medium | Nonlocal results and scoped search failures become categorical local assurances or novelty claims | Evidence strength, population and search limits are concealed | Carry scope and search coverage into existing reviews; describe proposed outcomes as aims, not guarantees |
| Medium | Basic coursework uses unnecessarily advanced language and inconsistent source types | The answer is less useful at the student's level | Add a compact level/source policy to existing planning and review; preserve essential technical precision |

The archive supports these output concerns. It does not establish that every citation is false, every listed N
was invented, every complete-export endpoint is broken, or every project needs an advanced statistical model.

## 4. Implementation work packages

### Package 1 — Citation and caption rendering

**Files:** `proposals/evidence.py`, `proposals/export.py`, relevant `works/export.py` / `render.py`, new prompt
versions only where writing instructions need clarification; shared regression fixtures.

- A narrative token renders the complete author/year citation. Writers must not put a second author label beside it.
- Before rendering, detect the exact adjacent duplicate author label for a narrative token. Use the canonical
  citation object; no fuzzy removal of arbitrary names. Preserve parenthetical citations, unrelated repeated names,
  quotations, group authors and APA 6 first-citation behaviour.
- Validate rendered citation grammar against the exact token/metadata combination, rather than globally deleting
  repeated words. Reproduce `As Mann ⟦E...|n⟧ observes` → `As Mann (2003) observes`.
- Store caption text without its generated number. Use the same caption formatter in the list of tables, body,
  preview, DOCX and PDF. A caption containing a conflicting number is a finding, not a silent renumbering guess.
- Run checks before approval on the text the reviewer will actually see; do not make semantic edits after approval.

**Impact:** no extra AI calls or network requests expected. Only local text/export work. No orchestration change.

### Package 2 — Source identity and consequential-claim evidence

**Files:** `analysis/fetch.py`, `metadata.py`, `proposals/models.py` / `pipeline.py` / `evidence.py`, `works/pipeline.py`,
new versions of affected research/writer/reviewer prompts, existing source caches and tests.

- Extend existing source/evidence objects; do not introduce a competing registry or another database.
- Resolve DOI, publisher or institution publication metadata for hosted articles. Where a citation page identifies
  a book, use authors from bibliographic/title-page records, not the university or publisher merely hosting it.
- For the Gulu example, test DOI `10.1080/23311886.2025.2588856`, the actual title and Kule and coauthors. A bare
  domain and journal-only title cannot satisfy scholarly author/title identity. Do not ban all university domains:
  an institution can legitimately author its own policy or report.
- Add optional source type, locator and provenance fields. A locator can be abstract/section/table/page; never
  fabricate a page number. Existing records without the field remain readable and are marked unknown.
- Classify consequential claims: statutory authority, empirical statistic, user-owned local fact, measured outcome,
  and ordinary explanatory material. An abstract can support a claim without full-text retrieval when it states it
  directly. Do not fetch a full paper for every generic sentence.
- For legislation, separate the secondary report's interpretation from the primary statutory text. Verify the
  instrument, version, exact provision and meaning. An inaccessible authority is NOT_CHECKED, not confirmation.
  Do not globally substitute `6(2)(c)` wherever `13(5)(2c)` appears without checking the proposition and version.
- Preserve the material claim's cited evidence IDs and scope beside its paragraph. Pass the cited evidence to the
  existing section evaluator and, compactly, the existing final reviewer. Add a stable material-claim mapping only
  as a versioned extension, never infer semantic support from number occurrence or matching DOI alone.
- Rank sources by the claim: official law/statistics for legal/national indicators; primary/review studies for
  empirical conclusions; appropriate textbooks/course material for basic concepts; news for explicitly reported
  news, not proof of a clinical or methodological conclusion.
- Reuse public metadata caches and bounded retrieval. Use the existing safe URL handling, retries, research deadline,
  capacity limiter and checkpoints. Do not introduce a second unrestricted Google-search loop.

**Impact:** no new LLM stage proposed. Input tokens increase where reviewers receive more evidence. Metadata and
primary-source misses add bounded network time; cached identities add little. Long final reviews may require an
extra part, therefore an extra existing review call. Measure and price this explicitly. Every actual outgoing
payload, including history and evidence, must still fit the existing bound.

### Package 3 — Input provenance and honest completion scope

**Files:** `proposals/models.py`, `service.py`, `pipeline.py`, `export.py`; works models/service/export; workspace
presentation; price/input fingerprints and admin field classification where fields are added.

- Persist origin for local N, applicant histories, budgets and other owner-owned facts: USER_SUPPLIED,
  SOURCE_VERIFIED, PROVISIONAL or UNKNOWN. A named registry typed by a user is USER_SUPPLIED, not SOURCE_VERIFIED.
- Carry source date, scope, eligible population and attached reference where available. Private administrative
  lists stay private; never search student records or registry contents on the web.
- Do not make a public official registry attachment compulsory at Start. A draft can use an explicitly attributed
  user figure. Verification/confirmation belongs in the existing needs-input workspace where appropriate.
- If the plan narrows the population (all pupils → P5–P7), request the eligible N or a scope confirmation; do not
  quietly reuse the original universe or invent a smaller one. Limit inference to the frame actually sampled.
- Keep separate scopes for a paid step and the whole artifact. A Chapter One job can complete; the full proposal
  remains incomplete. Use the current rulebook/profile to determine required sections, not a global heading list.
- Preserve existing status values initially. Add structured issue/reason codes and document banners rather than
  replacing enums across jobs, payments and UI. Draft export must prominently list missing chapters/essential input;
  complete export must still enforce its blockers. User confirmation does not waive a known contradiction.
- Separate "writing checked" from "ready to submit". A READY_WITH_WARNINGS writing draft with applicant-owned
  gaps must still receive a draft banner in Word/PDF, even though the current exporter mainly adds that banner
  for NOT_READY. Derive submission readiness from applicable requirements; do not change whether a completed
  paid step is charged/refunded just by relabelling its artifact.

**Impact:** no extra model calls for provenance or status rendering. Changes to public fields require compatibility
tests. This changes readiness behaviour and presentation, not the job graph. It should preserve two-page Start
and internal plans. Do not restore a mandatory plan-approval screen.

### Package 4 — Methods crosswalk and sampling validity

**Files:** existing `AlignmentRow`, `Variables`, `SampleSize` in `proposals/models.py`; `sampling.py`, `decisions.py`,
`rulebook.py` / versioned rulebook data, proposal planning/review/section payloads, framework and export.

- Extend the current alignment row with outcome ID/type, unit, operational definition, instrument/source,
  observation period, predictors, adjustment rationale, estimator and diagnostics. Use stable variable IDs shared
  by objectives, methods and figures. Keep the free-text rationale for judgement that cannot be mechanised.
- The existing planner/finaliser populates the new contract once. The existing plan reviewer assesses it. Writers
  consume it; they do not independently choose different outcome families in Chapter Three.
- Code validates stated structural contradictions: unmapped objectives, undefined outcome IDs, binary models
  attached to a declared count outcome without a justified transformation, or undeclared category thresholds.
  Statistical appropriateness is not proved merely by passing a schema.
- D21 may keep binary adoption as primary and intensity as secondary descriptive information. Define the practice
  list, binary rule, unit and primary inference. If intensity is itself an inferential objective, review a suitable
  model. Continuous predictors do not require categorisation just because a generic Chi-square sentence was written.
- D11 must distinguish pill-taking measure from viral suppression, measurement windows, discordance and recruitment
  coverage. Do not auto-select a clinical cutoff or consent exception; defer those to an approved protocol.
- D12 must reconcile school-level feeding, pupil attendance windows/denominators and clustering. D14 must specify
  each objective's disposal/segregation/recycling outcome and corresponding model explicitly.
- Separate the base sample calculation from the sampling design. Assess eligible N, frame coverage, selection units,
  cluster/stratum allocation, response assumptions, design effect and weighting. Label unresolved assumptions.
- Do not silently apply a stock design effect or non-response percentage. Add adjustments only when supplied or
  explicitly confirmed, with code-calculated steps. Do not present a prevalence-precision formula as proof of
  regression power; analytical power may require specialist review or an author-stated rationale.
- Confirm feasibility and participant protections in the existing plan/section reviews. Unknown facts must not
  block a useful Chapter One unnecessarily, but they must not become definitive sample or ethics statements.

**Impact:** this is a research-planning/schema and calculation behaviour change. It is NOT a replacement LLM
algorithm, but it needs its own versioned rollout. More review input/output tokens and possibly more bounded
repairs initially. Do not promise a zero-minute effect. It may ultimately reduce repeated failed chapters.

### Package 5 — Framework roles and cross-chapter consistency

- Replace the overloaded generic intervening role with an explicit proposed role: predictor, outcome, adjustment
  covariate, mediator, moderator or exploratory factor, plus rationale and linked analysis. Preserve legacy fields
  for old plans; do not reinterpret already approved studies silently.
- Without a justified mediation/moderation plan, render additional factors neutrally. Do not draw an arrow onto an
  association as though effect modification has been specified. The current association-not-causation legend is good.
- Freeze the framework data with the plan version used for each chapter and exported artifact. A change marks
  dependent text stale; regenerating an old version must not silently use the new design.
- Keep the UCU structure and the owner's objective-count decisions. Institution rules govern structure; they do not
  establish that an estimator, causal claim or clinical procedure is valid.

**Impact:** drawing/consistency checks need no extra AI call. Role selection is part of Package 4's existing planning
and review. Adds a versioned plan schema, not new agents or a new approval route.

### Package 6 — Funding schedules, budgets and domain safeguards

**Files:** `works/models.py`, `results.py`, `budget.py`, `numbers.py`, planning/final Results Model review payloads,
export/service and versioned rules/prompts.

- Keep the current budget engine. Clearly distinguish grant ceiling, applicant proposed request and reconciled total.
  If costs are missing, summary figures remain unknown and the headline must not imply line-item validation.
- Add a nonempty-budget check when a budget is required: `all(...)` over an empty line list must not certify budget
  completeness. Distinguish unknown cost from legitimate zero-cost/in-kind lines instead of relying on truthiness.
- Continue allowing draft downloads with visible gaps. A checked writing draft is not yet a funder-ready costed
  proposal. Reconcile request, currency, costs and funder constraints before submission readiness.
- Extend activities with cohort/phase IDs, duration, predecessor IDs, allowable overlap and follow-up window. Use
  relative project months; detect cycles, invalid dependencies and a required finish beyond the funded period.
- Generate Gantt, narrative timing and indicator measurement windows from this one schedule. Do not independently
  describe "two consecutive six-month cohorts" while drawing arbitrary overlapping months.
- For D19, present feasible choices: permitted cohort overlap, fewer/shorter cohorts with revised objectives, or
  an extended project/follow-up funded outside the original term. Do not alter the user's 12-month period silently.
- Capacity checks can use supplied seats, staff-hours, placement sites, equipment throughput and verified costs.
  Code cannot invent cooperative capacity, refrigeration specifications or safe transport procedures to pass.
- Use existing Results Model/final reviews for health, safeguarding and engineering concerns. Require an explicit
  specialist review status when a material assumption cannot be resolved by evidence. Do not describe ordinary
  motorcycle travel as a universally safe obstetric-emergency pathway. Do not invent HMIS tools or approval.

**Impact:** this changes the funding plan's feasibility model, not worker/queue mechanics. Deterministic date/budget
checks add no AI calls. Additional structured output and corrections can increase existing planning time. Specialist
confirmation may add human waiting time that must be visible and distinct from slow generation.

### Package 7 — Academic wording, evidence scope and teaching level

- Add compact reviewer instructions for statistical inference: a statistical test is not proof an effect exists;
  report the design, uncertainty, effect measure and limitations. Avoid equating random sampling with randomisation.
- Treat terms such as "proves", "never", "eliminates" and "causes" as context-sensitive review candidates. Do not
  revive the destructive blanket regex stripping fixed on 12 October. Preserve quotations, denials and conditions.
- Keep local study-gap language bounded by the actual search and supplied evidence. Search dates, queries and
  scope can be retained internally without claiming an exhaustive systematic review. Nearby-region papers must
  keep their populations and limits; they are neither proof of local uptake nor proof no local research exists.
- For basic coursework, use the student's level, direct answers and ordinary examples. Explain essential technical
  terms. Do not delete "ontology" automatically when the assignment actually asks about research paradigms.
- Give background, problem, justification and significance distinct purposes in the existing briefs. Repetition
  checking should detect duplicated claims with judgement, not forbid a necessary premise appearing in two places.

**Impact:** existing prompts/reviews only. Better instructions may reduce repairs; semantic checks can also uncover
more problems. Measure net time, not just first-draft word count. No general speed guarantee follows from this patch.

## 5. Stability rules for every package

1. Do not change job states, lease owners, attempt-scoped paths, wallet holds/refunds, continuation or queue limits.
   Keep all current idempotency and transaction guarantees. These changes belong in quality contracts and rendering.
2. Released prompts/rulebooks remain immutable. New versions are frozen at pricing. Optional fields have safe legacy
   defaults and a contract/version marker; a missing legacy field is UNKNOWN, never newly invented verification.
3. Bind methods, provenance, schedule and quality-policy changes to frozen input/plan/spec versions. The writer,
   reviewer and exporter must consume the same snapshot. Editing inputs while a step runs retains current stale-input
   protection. Changed methodology marks affected sections stale.
4. Reuse stable paragraph/evidence/variable/activity IDs. Quality defects should identify the exact object and a
   feasible repair. Do not issue a generic "not perfect" rejection or change approved user facts without a proposal.
5. No unbounded retry, per-sentence LLM call or full-text crawl. No extra frontier reviewer. Respect per-call and
   stage deadlines, shared Vertex capacity, quoted budgets and final request-size bounds.
6. Keep a single consistent rendered deliverable for review, preview, Word/PDF and subsequent revisions. Re-run code
   checks after any permitted correction; changed substantive wording needs approval before publication.
7. Do not install every new semantic gate as a hard blocker at once. Validate on fixtures, run shadow measurements,
   then enforce proven contradictions for newly priced work. Critical unresolved safety/substantiation still prevents
   a submission-ready label. Do not use a shadow mode to advertise known bad output as verified.
8. Record defect counts, unavailable-source outcomes, repairs, approval model/fallback, input/output tokens, capacity
   waits and total latency. Keep student text and private source material out of general logs and admin summaries.
   Store detailed claims, excerpts and search traces in the existing artifact file store, not in oversized Firestore
   job records. Keep only bounded metadata, IDs, hashes and outcomes in the job document.
9. Verify current and frozen jobs, revisions, figures updates, worker recovery, account deletion, retention and
   rollbacks. Metadata additions need the repository's admin-field classification and storage-size checks.

## 6. What is and is not an algorithm revision

| Proposal | Classification | Added time/cost |
|---|---|---|
| Exact citation/caption fixes and draft scope labels | Rendering/presentation correction | No extra model calls expected |
| Source identity/provenance and primary-law lookup | Evidence-quality extension in current research | Bounded network time on misses; no new paid stage |
| Evidence passages in final reviewer parts | Review-payload extension | More input tokens; possibly extra parts/calls for long documents |
| Structured outcome/sampling crosswalk | Research-planning and validation behaviour change | Larger existing calls; repairs/user clarification can add time |
| Cohort/dependency feasibility | Funding-planning behaviour change | Larger structured plan; deterministic checking plus possible repairs |
| One frontier editor directly rewrites and approves once, removing current loops | LLM orchestration/approval algorithm revision | Unknown until controlled trials; savings and quality are unproven |
| Extra per-claim verifier, specialist agent or second premium veto | New AI stages | Additional calls, spend and queues; not recommended now |

Do NOT silently adopt Step 6 of the independent audit as a "small fix". The live path uses bounded review/repair/
review; the direct-editor path exists separately and is disabled. Removing the loops changes approval semantics,
cache/checkpoint inputs, pricing and recovery. If the owner later chooses it, evaluate it as a separate project
with code-applied corrections, evidence checks, final approval semantics, cost measurement and rollback.

No credible estimate of extra minutes can be supplied from a static audit. Measure p50/p95 generation, model time,
retrieval time, capacity waiting, repair rounds and user waiting separately for matched workloads. A fuller review
can increase tokens without adding a stage, and a stronger check can increase failures before repairs improve.

## 7. Test and acceptance plan for Claude

First create reproducible fixtures from the actual defects, with exact synthetic inputs, immutable source snippets,
metadata, request routes, engine version, delivered DOCX and readiness. Mask all user-sensitive content. The same
fixture and evidence snapshot must be used before/after; changing sources is a separate retrieval experiment.

**Offline release tests:**

- D15 narrative token with a preceding identical person/group label; no duplicates in preview, Word or PDF.
- D21 numbered/un-numbered/conflicting caption; a single valid caption in body and list; references remain intact.
- Gulu publication with its DOI and four authors; genuine corporate reports remain valid; university/book publisher
  not substituted for known personal authors; unavailable metadata stays unresolved rather than guessed.
- D12 secondary source repeating the bad statutory label; primary-source confirmation required. A quoted criticism
  of that label must not be stripped or rewritten as an endorsed legal claim.
- No population input: no invented registry or exact N. Supplied synthetic N: USER_SUPPLIED, never SOURCE_VERIFIED.
  All-pupils frame narrowed to P5–P7: prompt a scope correction rather than calculate from the wrong denominator.
- D13/D20: Chapter One/two draft exports allowed and visibly incomplete; complete-export requests refused until the
  current rulebook's required chapters/sections and approvals exist. Completed child jobs do not mark the project done.
- D11: adherence and viral suppression separate; recruitment coverage and age-specific protections unresolved until
  specified. No fabricated threshold, tool validation, consent waiver or ethics approval.
- D21: binary primary with descriptive count accepted when explicitly mapped; a count inferential objective attached
  only to an unexplained binary model flagged. D14 outcome mappings consistent across objectives and Chapter Three.
- Clustered school/household designs: scope, stages, response/design assumptions and analysis handling present, or
  unresolved status shown. Do not hardcode one universal estimator, design effect or sample inflation percentage.
- D19 schedule: setup + consecutive cycles + follow-up cannot silently fit an impossible term; valid permitted
  overlaps pass; missing/cyclic dependencies and unfunded follow-up are named.
- Required funding budget empty/incomplete: draft, not reconciled request. User quantities/costs reconcile in code;
  legitimate zero-cost/in-kind items handled deliberately; unknown figures never converted to zero or invented.
- Conceptual role/diagram labels match the frozen methods contract; old versions remain stable after plan revision.
- Meaningful negative controls: conditional statements, quoted errors, qualitative studies, descriptive coursework,
  genuine organisation authors, appropriate university teaching sources and valid association-only frameworks.

Run affected backend tests, full suite, web tests/typecheck/build and relevant fake-model browser journeys. Test
each key regression with its fix reverted. Do not claim fake models establish real academic judgement.

**Real-model validation, only after paid-call approval:**

Prioritise D12, D14, D19, D20 and D21, and include D11 for clinical outcome/consent issues and D15/D16 for coursework.
Rerun the refused Chapter Three. Measure the exact final Quality Control section, not just successful API responses.
Read Word and PDF, evidence passages, chosen methods, final objections and status. Record costs of failed jobs too.

Then re-score all 21 outputs with a consistent rubric. Only five archive pairs are matched before/after; the Gulu
skills and Mbale CSA second-pass files are new cases in this archive. More words/references do not prove improvement.

Use small concurrency trials before a larger workload. Do not infer 100-user capacity from a handful of successful
jobs. No change to Gemini slot limits is justified by this academic audit alone.

## 8. Recommended delivery order

1. Capture fixtures and provenance; classify each issue as confirmed output defect, confirmed code gap, intentional
   draft behaviour or needing source verification. Preserve existing tests and approval rules.
2. Ship rendering corrections and clearer draft scope/status after their gate. These have the lowest runtime risk.
3. Add source identity, claim provenance and targeted final-review evidence with bounded payloads and retrieval.
4. Add the methods contract and framework roles as a separate versioned research-quality patch.
5. Add cohort/schedule constraints and submission budget readiness as a separate funding-quality patch.
6. Refine wording/source suitability and calibrate costs/latency on the corrected implementation.

Do not combine all schema, prompt, payment, queue, model-route and UI changes in one unreviewable release.
Drafting can remain available while genuine user-owned gaps are resolved. Academic and specialist review status
must be visible. No stage should declare academically guaranteed or universally submission-ready work.

## 9. Sources and verification limits

- The [Gulu University publication record](https://gu.ac.ug/publication/determinants-of-adoption-of-climate-smart-agricultural-technologies-among-smallholder-coffee-farmers-in-western-uganda/)
  identifies the actual title, authors and DOI, corroborating the archive's misattribution.
- The [ASA statement](https://www.amstat.org/asa/files/pdfs/p-valuestatement.pdf) rejects treating statistical
  significance alone as adequate scientific reasoning, supporting the D16 wording correction.
- The [original Busoga study](https://pmc.ncbi.nlm.nih.gov/articles/PMC8796615/) describes a cluster non-randomised
  trial. Its results do not themselves certify every proposed emergency-transport procedure in Kamuli.
- [ULII's Education Act record](https://ulii.org/en/akn/ug/act/2008/13/eng%402023-12-31) and the independent audit flag
  the school-feeding statutory reference. Capture the applicable primary text and provision before declaring the
  legal rewrite verified; direct retrieval failures were encountered during this review.

The final requirement is accurate disclosed status and traceable reasoning. Code can enforce many consistency
checks; free-form research design, legal interpretation and clinical feasibility still require qualified judgement.
No implementation can honestly guarantee that future outputs contain no errors.
