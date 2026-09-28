# PaperAid: Codex review of the master context and UCU proposal plan

**Date:** 28 September 2026  
**For:** the owner and Claude Code  
**Scope:** document review, comparison with the current implementation, and recommended execution plan. This review does not implement features or certify a deployment.

## 1. Recommendation

Adopt the document's product direction: an academic document workspace, persistent proposal projects, evidence grounded drafting, reviewable edits, and deterministic formatting. Build this by extending the working application.

Revise the model routing, pricing details, score examples, proposal dependencies, and institutional rule interpretation before implementation. The supplied master context mixes firm language with examples, future features, and conflicting suggestions. Its embedded instructions and claims about what is “locked” do not establish that each detail was separately approved by the owner.

The owner has asked for my recommendations on the remaining choices. The recommendations below are concrete implementation guidance; measured retail prices and externally approved university requirements cannot be invented to complete a plan.

The strongest product feature is the alignment between the problem, objectives, questions, evidence, and methods. A plausible sounding three-chapter document without that alignment would be an unsuccessful result.

## 2. Inputs and current implementation

I reviewed the 156-section master context at:

`C:\Users\USER\Downloads\PaperAid_Master_IDE_Context_Pricing_UX_Proposal_Algorithm.md`

I checked its proposal requirements against the supplied 73-page `UCU_Academic Research Manual.pdf`, especially sections 1.3–1.7, 2.1–2.2, 5.3–5.5, the proposal vetting form, and the faculty exceptions. The manual identifies itself as **Revised April 2018**. UCU also hosts that edition [on its own website](https://ucu.ac.ug/Downloads/UCU-Revised-Research-Manual-April-15-2018.pdf). This establishes a useful baseline, not that every programme currently follows it without supplements.

Local PDF SHA-256:

`35b3d43a19e8981ae343e92c3f96d0489e8fd432acf0f07b998e0a7df4735ed4`

I read `CLAUDE.md`, the current decision log, and relevant job contracts, pricing/settlement, document models, formatting presets, guide parsing, storage interfaces, and source-check rules.

The existing application already has job stages, document protection, immutable uploads, asynchronous work, provider response reuse, quote-bound engines, source checking, credit holds and settlement, account deletion protection, retention, Deep Redraft, and LaTeX conversion. A proposal project and an interactive editing workspace are additions. The master document's A–L sequence would unnecessarily revisit functioning infrastructure.

The new 28 September decision-log entry agrees with many of my recommendations: credits, no percentages, no product mocks, and no unbenchmarked writing-role replacement. Two recommendations need refinement: use reliable scope/word bands for billing, and bring essential decision locking/dependency tracking forward into Proposal V1.

## 3. Product decisions I recommend

| Area | Recommended decision |
|---|---|
| First new capability | UCU proposal review and planning, followed by chapter drafting in the same project |
| Proposal identity | A persistent project with separately priced background jobs |
| Customer money | UGX credits; retain the existing UGX 5,000 minimum top-up unless a later commercial decision changes it |
| Retail pricing | Fixed prices by service and defined scope, based on measured complete costs |
| Long document pricing | Word/scope bands; page counts are institutional formatting checks |
| Current writing engine | Keep Sol leading and Opus writing/critiquing while alternatives are evaluated |
| Cheaper models | Introduce narrowly bounded tasks only after task-specific evaluation; deterministic operations remain code |
| AI-likeness display | Band and confidence with reasons; no invented percentage |
| Proposal readiness | Evidence-backed checklist and unresolved items; no automatic university mark |
| V1 consistency | Approved research decisions, versions, dependency invalidation, and alignment matrix |
| V1 editing | Reviewable section/block revisions; preserve the original Word document on imported work |
| Primary export | DOCX; rendered PDF only when a dependable renderer is available |
| Faculty variations | Apply documented, versioned overrides; expose unresolved conflicts |
| Unsupported information | Ask the author, omit unsupported optional material, or mark the result incomplete in the application |

Fixed retail pricing improves predictability. It does not require replacing the credit ledger, renaming credits to tokens, or changing the working engine at the same time.

## 4. UCU rules: what the PDF actually supports

The page references below are **printed page numbers**. For numbered body pages, add seven to find the physical PDF page. For example, printed page 10 is PDF page 17.

| Requirement | Source | How PaperAid should handle it |
|---|---|---|
| General introduction, literature review, methodology | §2.1, pp. 7–9 | Standard UCU proposal structure; allow documented disciplinary variations |
| Background, problem, purpose/objectives, questions/hypotheses, scope, justification, significance, framework | §2.1, p. 7 | Check presence separately from quality and alignment |
| Evaluative literature organised around objectives/questions and identifying a gap | §2.1, pp. 7–8 | Assess synthesis and support; a list of studies is insufficient |
| Design, area, information sources, sampling, variables where relevant, instruments, quality control, analysis, ethics, constraints | §2.1, p. 8 | Apply each rule according to the research type |
| Work plan/timeline; budget optional | §2.1, p. 9 | Require the work plan for the standard applicable structure; do not require every student to invent a budget |
| Secondary-data work and other special formats may differ | §2.1 note, p. 9; §7.4, pp. 64–65 | Do not force surveys, independent/dependent variables, or field sampling into every project |
| Title, declaration, approval, contents and relevant lists | §2.2, p. 9 | Collect genuine author/programme/supervisor details; do not create a signature or claim actual approval |
| Title page includes candidate name/number, programme, proposed supervisor, submission date | §2.2, p. 9 | Author input; missing information blocks a complete submission export |
| Chapter numbering is optional; sections can run continuously | §2.2, p. 9 | Do not flag unnumbered chapters or continuous sections as violations |
| Reference list, followed by appendices where needed | §2.2, pp. 9–10 | Build from sources actually used and retain relevant instruments |
| Future tense for a proposal | §2.2, p. 10 | Apply to planned work; preserve appropriate tense for established facts and published studies. That contextual treatment is PaperAid's interpretation, not a verbatim exception in the manual |
| Trebuchet MS 12, double spacing, one-inch margins, bottom-centred numbering | §2.2, p. 10 | Deterministic UCU layout profile |
| Bachelor 10–20 pages; master's/PGD 15–30; PhD 25–45 | §2.2, p. 10 | Level-specific checks. Report estimated versus rendered page count honestly |
| General body-length discussion excludes preliminaries, references and appendices and estimates approximately 250 words/page | §1.7, pp. 5–6 | Context for an approximate body-length check; obtain a faculty clarification if proposal counting is disputed |
| Concept paper maximum five pages, 3–5 objectives/questions, 5–8 annotated sources | §1.4, pp. 3–4 | Separate concept-paper profile, not full-proposal requirements |
| General research-document guidance suggests 2–5 specific objectives/questions/hypotheses | §5.3, pp. 19–22 | Guidance with document scope attached; do not enforce concept-paper counts on every proposal |
| Proposal rubric asks for at least 30 quality references; freshness depends on faculty/topic | §7.3.1, pp. 50–52 | A traceable proposal-review criterion; identify its School of Research & Postgraduate Studies scope and flag uncertain applicability to a programme |
| APA is the baseline, with communicated faculty alternatives | §1.6, p. 5 | Citation style is part of the selected institutional profile |
| APA appendix explicitly uses the sixth edition | §7.2, p. 44 | Do not silently call the existing APA 7 preset an exact implementation of the 2018 UCU appendix |
| Faculty-specific and non-empirical formats exist | front matter p. i; §7.4, pp. 64–65 | Initial support boundaries must be explicit; complex exceptions need their documented profile |

### Details that must not become misleading rules

The manual's proposal assessment table gives **20, 15 and 15 marks, totalling 50** (p. 50). Following pages label those sections with percent signs. Treat this as an ambiguity in the source, not a basis for an invented 91% readiness score. Use the criteria as a checklist.

The “majority within ten years” question appears in the final research-document assessment material (p. 42). The proposal rubric instead says freshness depends on faculty and research (p. 51). Do not impose a universal ten-year exclusion on proposals or remove foundational theory.

The report title-length, abstract and past-tense requirements belong to the research-report sections (pp. 13–14). They should not automatically be applied to a proposal. The supplied manual also has inconsistent abstract limits in different sections. Preserve scope and record conflicts.

The manual's April 2018 APA appendix and the current application's APA 7 formatting preset differ. Recommend a distinct UCU-2018 citation/layout profile, with a visible APA 7 override only when selected or supported by faculty guidance. Layout formatting alone is not a complete citation-style transformation.

## 5. Highest-priority gaps in the master context

### P0: missing research decisions can turn into invented methods

A topic alone does not establish a population size, sampling frame, feasible recruitment process, validated instrument, ethics approval, or correct analysis method. A writer can produce convincing but unusable Chapter Three text by supplying those details itself.

**Fix:** progressive author questions, an explicit proposed/approved decision state, sourced methodological recommendations, and a required alignment matrix. Deterministic sample-size calculations need approved assumptions, the appropriate method, and recorded inputs. Qualitative/theoretical studies must have their own relevant justification. Never apply one default sample-size formula to every study.

No model may invent completed data collection, pilot results, reliability coefficients, permissions or ethics approval. An ethics plan and actual institutional approval are different facts.

### P0: decision locking cannot wait until V2

If the author changes Objective 2 after Chapter Two is generated, Chapter Three can keep its old variables and analysis. Version history alone records the inconsistency without preventing it.

**Fix:** V1 must store approved objectives, questions, study area, population, design and analysis decisions with stable identifiers. Each generated section records its dependencies. Changing an approved decision creates a new version and marks affected downstream sections as needing review. A full supervisor-feedback extraction interface can wait.

A background job publishes against its input project version. If the author edits meanwhile, retain the generated artifact as a separate candidate; do not overwrite the newer draft.

### P0: fixed prices require a different settlement policy

The current `settle_completed` calculates actual provider spend multiplied by the quote's rate/multiplier. Merely changing the quote table would still charge variable prices. Old and new jobs may complete after a deployment.

**Fix:** freeze a billing-policy version in every accepted quote. Existing jobs keep their existing rules. A new successful fixed-price action charges its disclosed fixed price; unused internal provider budget does not automatically become a customer refund. Failed actions refund according to the disclosed policy, and partial delivery has an explicit fair refund rule. Keep actual-cost accounting separately.

Preserve already-paid estimate credit and cached analysis without counting either twice. A fixed price should include any required preflight: if an estimate fee is charged separately, disclose it before work and state exactly how it reduces the accepted price. Do not charge an undisclosed investigation merely to reveal a price.

### P0: a persistent project needs retention and deletion semantics

The current privacy screen says files are deleted after the configured job retention period, currently 30 days. A months-long project cannot rely on chapter-job artifacts that independently expire.

**Fix:** project-owned canonical sections, evidence and versions with a displayed expiry; short-lived execution artifacts under job retention. For V1, recommend 30 days of project inactivity before expiry, with an advance notice and explicit export/archive controls. Renew on genuine author activity, not automatic polling. This remains a retention-policy change that must be represented in the privacy text and cleanup code before release.

Account closure, authorization and deletion must cover projects, sources and versions as well as jobs. Ensure every new write checks the account tombstone and any project cleanup/deletion claim.

### P1: evidence verification is not reference existence

A DOI lookup proves bibliographic identity, not that a cited article supports a sentence. A blocked publisher page is not proof that a claim is false. An abstract can only substantiate what it actually says.

**Fix:** keep bibliographic status, access status and claim-support verdict separate. Store actual retrieved passages, locators, scope and retrieval time. Use the existing “Found, not confirmed” distinction. A limited search cannot justify “no previous research exists.” Report search scope and remaining uncertainty.

Do not generate extra references simply to meet a count. Distinct citations should resolve to distinct works; mirrors do not create independent corroboration. Crossref absence alone does not establish fabrication, particularly for books, local reports, or works registered elsewhere. [Crossref exposes deposited metadata](https://www.crossref.org/documentation/retrieve-metadata/rest-api/), not a universal full-text truth test.

### P1: a cheaper writer is an experiment, not a demonstrated replacement

The document's low-cost model prices make experimentation worthwhile. They do not establish equal academic quality or a 50–70% reduction in complete job cost.

**Fix:** retain the current engine as the reference. Compare alternatives on meaning, citations, quantities, methods, unsupported additions, coherence, repairs, latency and complete billed cost. Include human Ugandan academic work, non-native English, difficult Word structures, multiple study designs and non-Latin text. Use a held-out set and a human reviewer; one model's approval is insufficient proof of equivalence.

Self-reported model confidence is not a calibrated routing score. Deterministic operations use code. Model-based claim triage is a judgment task and needs evidence that it does not drop important claims. Freeze any accepted routing policy in a new engine version.

### P1: a browser editor must preserve Word content

DOCX converted to editable HTML and reconstructed can lose fields, bookmarks, notes, equations, headers and objects even if its visible paragraphs look right.

**Fix:** for imported work, keep the original OOXML authoritative and patch supported blocks with version/hash checks. Start with a reading view, findings, preview/accept/dismiss and revision history. Make complex protected content read-only. PDF is analysis input initially; do not promise lossless editable-PDF round trips.

Generated proposals can use a controlled section editor and deterministic DOCX renderer. They do not need the same fidelity strategy as an arbitrary imported dissertation.

### P1: metadata records and logs must remain bounded

The proposed schema could put large chapters, evidence and revision histories into Firestore records. The current wallet also retains grant operation IDs indefinitely in a growing list.

**Fix:** place large document/evidence artifacts in private storage and keep bounded metadata/manifests in records. Use durable append-only transaction/idempotency records for new billing work, with compact wallet totals and paginated history, rather than unbounded embedded history. Preserve the existing local journal's crash guarantees when a transaction gains project state.

## 6. Pricing and model economics

Keep the UGX credit balance and a clear price for each action. A second retail unit adds conversion work for students and contradicts the existing terminology decision. Provider token accounting remains internal.

Measure full costs: model input/output and reasoning, searches, source retrieval, retries, repairs, rendering, storage and compute. Review the expensive tail of each service, not only its mean. Restrict supported scope when a price cannot cover that tail. The proposed retail amounts are starting hypotheses, not measured prices.

Use words and an explicit service scope for uploaded documents. Page count changes with font, spacing, tables and renderer. Proposal project prices can distinguish planning, a defined chapter draft, a targeted revision and a final review. Reusing evidence or restarting a successful checkpoint must not silently rebill a completed action.

Define one paid action per job. Do not hold a full-project balance for weeks. Two tabs accepting actions must reserve against the same wallet transaction; duplicate requests need stable operation IDs. Recovery must reconcile abandoned holds and unfinished jobs. Publishing a result, recording its charge and updating the project must have recoverable atomic semantics.

Current standard input/output prices per million tokens checked on 28 September 2026:

| Model | Input USD | Output USD | Source |
|---|---:|---:|---|
| GPT-6 Luna | 0.10 | 0.50 | [OpenAI model page](https://developers.openai.com/api/docs/models/gpt-6-luna) |
| GPT-6 Sol | 2.00 | 10.00 | [OpenAI model page](https://developers.openai.com/api/docs/models/gpt-6-sol) |
| Claude Sonnet 5 | 2.00 | 10.00 | [Anthropic pricing](https://platform.claude.com/docs/en/about-claude/pricing) |
| Claude Opus 5.5 | 4.00 | 20.00 | [Anthropic pricing](https://platform.claude.com/docs/en/about-claude/pricing) |

These are base token rates, not job prices. Cache operations, tools, context length and processing choices affect bills. Some older indexed Sonnet documentation describes an increase to $3/$15; the current pricing page and [release notes](https://platform.claude.com/docs/en/release-notes/overview) say the $2/$10 rate became standard. Use the current rate card when freezing a quote, not an old search excerpt.

Optimize evidence reuse, irrelevant context and duplicate work before changing the writer. Evaluate each smaller-model substitution independently. OpenAI's [optimization guidance](https://developers.openai.com/api/docs/guides/model-optimization) also emphasizes measuring behavior across model changes.

## 7. Recommended execution sequence

### Milestone 1 — UCU rulebook and proposal review

Create a curated, versioned rulebook from the manual. Each rule includes a stable ID, source edition/hash, section and page, applicability, required/recommended status, validation method and conflict handling. Label PaperAid interpretations separately from the manual's exact requirements.

Split concept-paper, proposal and final-report rules. Keep imported faculty instructions as candidate overrides until confirmed. Unknown programme applicability becomes a visible review item.

Run the rulebook against genuine existing proposals with permission. Deliver a real compliance report with section locations and actionable findings before generating an entire proposal. This is the first usable increment of Proposal V1.

**Gate:** an absent required section is found; an allowed faculty variation is not falsely rejected; APA 6/7 differences and unresolved rules are visible; no fake marks or citations appear.

### Milestone 2 — Project state and approved plan

Add a project with canonical research decisions, source library, version manifests and child jobs. Reuse the existing backend, storage, authentication and queue.

Start intake with topic, institution/programme, level, area and any concept/draft. Ask subsequent questions only when needed to resolve decisions. Produce a proposed plan, evidence gaps and objective-to-method matrix. Author approval establishes the baseline.

Record project/rulebook/engine versions, dependencies and accepted decisions from the first version. Store large content outside metadata records. Apply retention and closure rules now.

**Gate:** reopening on Android or Windows shows the same saved state; two editors cannot overwrite each other silently; changing an objective invalidates affected sections; a closed account cannot start a project action.

### Milestone 3 — Evidence library and Chapter One

Plan public research needs before searching. Collect and deduplicate sources, retrieve their actual supporting passages, and separate found references from confirmed claims. Reuse the current source-check safety controls without sending names, student identifiers or unpublished findings to public searches.

Draft the introduction from approved decisions and verified evidence. Critique, audit and repair within bounded work. Deliver a section revision with its evidence links and unresolved author questions.

**Gate:** every introduced external factual claim has traceable support or is withheld; a blocked source is labelled accurately; the model cannot change approved objectives or fabricate local statistics.

### Milestone 4 — Chapters Two and Three

Organise literature by approved objectives/themes and critically synthesize differences, limitations and relevance. Build references from verified metadata. Cover conceptual/theoretical frameworks in V1; a sophisticated diagram editor can wait, but required framework content cannot.

For methodology, use approved design decisions and a complete objective-to-data-to-analysis mapping. Explain limitations and planned ethics safeguards without pretending approvals or fieldwork already happened. Ask for missing feasibility details instead of filling them with defaults.

**Gate:** sample size and assumptions are reproducible; each objective has an appropriate method; qualitative and secondary-data examples work; a changed population marks sampling and analysis for review.

### Milestone 5 — Audit, export and pricing readiness

Check the whole project for structural, citation, evidence and cross-chapter consistency. Publish a checklist with PASS, NEEDS REVIEW, MISSING, NOT APPLICABLE and BLOCKED outcomes, showing why and where. A model-reviewed item should be distinguishable from a deterministic check or an author-confirmed fact.

Generate DOCX using the selected UCU profile. Verify actual font availability, page numbers, headings, contents fields and protected content. If a reliable renderer is unavailable, page count and TOC pagination remain clearly pending Word verification. Do not label an estimated page count as a measured compliance pass.

Permit export of an explicitly incomplete draft where safe. Complete submission export requires essential author information and blocking academic checks to be resolved. Keep unresolved issues in the application/report, not fabricated prose or bracketed filler in the proposal.

Measure live complete costs and set retail prices before enabling paid proposal jobs. Missing keys keep AI actions unavailable; automated tests use fakes only in tests.

**Gate:** real Word review, mobile/desktop continuity, retry/crash recovery, duplicate-submit billing, account deletion, retention and real-model evaluations pass. This review itself has not run those new-feature gates.

### Milestone 6 — Interactive review workspace and richer feedback

Apply preview/accept/dismiss/undo interactions to existing AI Check and refinement results. Keep scope, current version, accepted edits and quote boundaries clear.

Then add supervisor-feedback extraction, a richer dependency preview, framework diagram editing, and additional institution profiles. Basic dependency tracking and decision approval are already present from V1.

## 8. Implementation guidance for Claude Code

1. Extend the functioning job engine and stores; do not rebuild the master document's infrastructure stages.
2. Add a small proposal domain: rulebook, project state, evidence references, alignment checks and section revisions. Avoid a generic agent framework or a new service fleet.
3. Preserve job status, processing stage, checkpoints and payment status as separate concepts. Project state is also separate from a chapter job's status.
4. Every action runs against a frozen project version, source/rulebook versions, engine and billing policy. An old accepted job must survive new deployments without repricing or changing its algorithm.
5. Keep provider usage records private and content-free in support/admin views. Progress and coverage counts must come from real work, including limitations on how many references or claims were checked.
6. Test invariants, not just happy paths: concurrent edits, dependency invalidation, stale results, hold/refund retries, deletion races, source privacy, incomplete methods and profile exceptions.
7. Keep the existing invitation and credits-off testing controls until live evidence, export and cost gates pass.
8. Update working rules, decision history and customer wording together when the new pricing or project-retention policy is implemented. Historical entries remain history; current instructions must not contradict the running application.

## 9. Summary for the owner

The document has a strong product direction and useful engineering ideas. The UCU PDF is sufficient to begin a carefully scoped proposal module, and it provides more specific rules than a generic academic-writing prompt.

My recommended first delivery is **a real UCU proposal review, a persistent approved plan, and traceable chapter drafting**. Keep approved research decisions and version dependencies in the first release. Use UGX credits and measured fixed prices, preserve the existing writing engine while alternatives are evaluated, and keep scores honest.

Success means an author can understand and defend the proposal's decisions, sources and methods, reopen it on another device, revise it safely, and download an intact Word document. Completing model calls alone does not establish that outcome.
