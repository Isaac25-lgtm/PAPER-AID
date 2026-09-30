# PaperAid Final Implementation-Grade Rulebook Specification
## Concept Notes, Funding Proposals, and Academic Coursework

**Version:** 1.0  
**Status:** Final implementation contract for IDE handoff  
**Date:** 28 September 2026  
**Applies to:** PaperAid Concept Note, Funding Proposal, and Coursework services  
**Does not replace:** the existing PaperAid Academic Proposal/UCU rulebook, AI Checker architecture, model-routing architecture, token-wallet architecture, or future Dissertation/Data Analysis specification.

---

## 0. Executive implementation decision

PaperAid will implement three new rule-driven services:

1. **Concept Note**
   - Research Concept Note
   - Project Concept Note
   - Funding Concept Note
2. **Funding Proposal**
   - NGO / development-project proposal
   - Research-grant variant
   - Compact / Standard / Comprehensive planning modes
   - Form-based/field-limited application mode
3. **Academic Coursework**
   - Essay
   - Academic Report
   - Case Study
   - Literature Review
   - Short Research Paper
   - Reflective Assignment

The system-level workflow is fixed as:

```text
EXTERNAL REQUIREMENTS
(call / assignment brief / rubric / template / institution rule)
        ↓
REQUIREMENT EXTRACTION
(quote + source location + confidence)
        ↓
RESOLVED SPECIFICATION
        ↓
PLAN
(scoring-aware word budget)
        ↓
RESEARCH / EVIDENCE WHEN REQUIRED
        ↓
DRAFT
        ↓
DETERMINISTIC VALIDATION
        ↓
SEMANTIC / SENIOR AUDIT
        ↓
TARGETED REPAIR
        ↓
RENDERED COMPLIANCE
(words + pages + characters + fields)
        ↓
FINAL
```

The existing PaperAid LLM politics remain unchanged in principle: inexpensive worker models handle routine generation; PaperAid code handles deterministic rules; stronger models audit difficult academic, methodological, evidentiary, or semantic issues; repairs are targeted rather than whole-document rewrites.

This document defines **what must be true**, not which provider must be used for every step.

# 1. Product principles

The rule system may be sophisticated, but the user experience must remain simple.

The ordinary user should experience:

```text
Get Started
  ↓
Choose service
  ↓
Upload instructions/document OR enter a topic
  ↓
PaperAid understands the task
  ↓
PaperAid shows a plan
  ↓
User adjusts permitted items
  ↓
PaperAid drafts/checks
  ↓
PaperAid validates its own work
  ↓
Final document
```

The user must not be forced to understand model routing, prompt engineering, source ranking, rule precedence, evidence graphs, raw API tokens, or validator internals.

### 1.1 Locked design principles

1. External instructions outrank PaperAid defaults.
2. PaperAid plans internally in **words**, not pages.
3. Page compliance is verified only after final formatting/rendering.
4. Word, page, character, and field limits are separate constraint types.
5. Rule **class** and rule-failure **severity** are separate concepts.
6. Every externally extracted rule stores its exact supporting quote, location, confidence, version/date where possible, and source document.
7. Low-confidence extracted rules never become silently locked.
8. Published scoring criteria influence planning depth and word allocation, but are not mechanically converted 1:1 into word percentages.
9. Funding applications use a structured **Results Model** as the source of truth for objectives/outcomes/outputs/activities/indicators/timing/budget mapping.
10. Formal Theory of Change sections are conditional; internal intervention logic is always modeled.
11. Logframes, results tables, workplans, and M&E indicator tables are rendered from structured project state rather than independently authored.
12. PaperAid-added references must be bibliographically verified before final use.
13. Specific numerical claims require source text or structured data that actually supports the number.
14. User-supplied figures and facts are never silently altered.
15. Coursework first parses the assignment and rubric before drafting.
16. “Critical analysis” is a directive/quality mode, not a coursework document type.
17. Explicit institutional/assignment restrictions on generative AI must be obeyed.
18. Generated coursework must not run a detector-evasion or “make undetectable” pass.
19. Validators live in code; rule definitions live in data.
20. Job-specific extracted requirements belong to the job requirement set, not permanent base rulebooks.

# 2. Core terminology and enums

## 2.1 Rule class

Allowed values:

```text
REQUIRED
CONDITIONAL
DEFAULT
QUALITY
```

- **REQUIRED** — must be satisfied whenever applicable.
- **CONDITIONAL** — required only when `applies_if` resolves true.
- **DEFAULT** — PaperAid fallback when no stronger instruction exists.
- **QUALITY** — quality/reasoning standard used for assessment and refinement.

## 2.2 Severity

```text
BLOCKING
WARNING
INFO
```

- **BLOCKING:** READY status cannot be issued.
- **WARNING:** work can continue/export if the workflow allows, but the issue remains visible and should be repaired where practical.
- **INFO:** advisory or transparency message.

## 2.3 Validation type

```text
DETERMINISTIC
SEMANTIC
HYBRID
```

## 2.4 Rule stages

```text
INTAKE
PLAN
DRAFT
FINAL
RENDER
```

A rule may run at more than one stage.

## 2.5 Requirement authority

From highest to lowest:

```text
1. EXTERNAL_MANDATORY
   donor call / official template / assignment brief / rubric / institution policy / addendum

2. USER_EXPLICIT
   user choice that does not conflict with higher authority

3. DOCUMENT_VARIANT
   funding-concept / research-concept / essay / report / etc.

4. PAPERAID_BASELINE
   document-type fallback

5. QUALITY_GUIDANCE
   non-mandatory quality standard

6. MODEL_PREFERENCE
   stylistic preference only
```

No lower authority may override a higher one.

# 3. Exact override and conflict-resolution algorithm

The IDE should implement this logic centrally. Do not duplicate it across services.

```pseudo
INPUTS:
    shared_rules
    base_document_rules
    variant_rules
    dated_profile_hints
    external_extracted_requirements
    user_choices

FOR each requirement_key:
    candidates = all applicable rules for that key
    candidates = candidates where applies_if == true

    order candidates by authority:
        EXTERNAL_MANDATORY
        USER_EXPLICIT
        DOCUMENT_VARIANT
        PAPERAID_BASELINE
        QUALITY_GUIDANCE
        MODEL_PREFERENCE

    IF two or more EXTERNAL_MANDATORY candidates conflict:
        inspect explicit source precedence:
            addendum > base call when the addendum explicitly modifies it
            official submission template > generic PaperAid default
            later official clarification > earlier generic instruction where clearly applicable
        IF still unresolved:
            create REQUIREMENT_CONFLICT
            pause locking of that key
            ask user or require manual resolution

    ELSE IF EXTERNAL_MANDATORY exists:
        external candidate wins

    ELSE IF USER_EXPLICIT exists and value is within allowed range:
        user choice wins

    ELSE:
        highest applicable candidate wins

    persist:
        winning rule
        overridden candidates
        authority trail
        source provenance
```

### 3.1 Examples

**Example A — word count**
- PaperAid coursework default: 2,000 words.
- User selects: 2,500 words.
- Assignment brief says: 1,500 words ±10%.
- Resolved requirement: 1,500 words with the brief's tolerance, because external mandatory instructions override both user and PaperAid defaults.

**Example B — funding proposal length**
- PaperAid recommends Standard, 5,500 narrative words.
- Donor requires maximum 10 rendered pages, single-spaced, 12 pt.
- PaperAid uses 5,500 only as an initial planning estimate, renders in donor format, then compresses until the actual output is ≤10 pages.

**Example C — conflicting official documents**
- Call text: maximum 10 pages.
- official addendum: maximum 12 pages.
- If addendum explicitly amends the call, 12 wins and both sources remain in provenance.
- If not clearly amendatory, create conflict and ask.

### 3.2 User choices that are always subordinate to external rules

Users may not override:
- eligibility;
- deadline;
- hard page/word/character cap;
- donor funding ceiling;
- cost-share requirement;
- prohibited costs;
- mandatory section/template field;
- institution-mandated citation style;
- explicit AI-use prohibition;
- evidence integrity requirements.

# 4. Rule schema

Use an implementation schema equivalent to:

```json
{
  "id": "FP-041",
  "scope": ["funding_proposal"],
  "variant": ["ngo_project"],
  "category": "results",
  "class": "REQUIRED",
  "severity": "BLOCKING",
  "applies_if": {"results_model_enabled": true},
  "requirement": "Each outcome must have at least one measurable indicator.",
  "check": {
    "type": "DETERMINISTIC",
    "validator": "results.outcome_indicator_link",
    "params": {}
  },
  "stages": ["PLAN", "FINAL"],
  "provenance": {
    "source_type": "PAPERAID_BASELINE",
    "source_ref": "paperaid-funding-v1",
    "source_quote": null,
    "source_location": null,
    "source_version": "1.0",
    "effective_date": "2026-09-28",
    "retrieved_at": null,
    "confidence": 1.0
  },
  "adjustable": {
    "allowed": false,
    "min": null,
    "max": null
  },
  "overrides": [],
  "overridden_by": ["EXTERNAL_MANDATORY"],
  "remediation": "results.create_missing_indicator",
  "ui_message": "Outcome {outcome_id} has no measurable indicator."
}
```

### 4.1 Required schema fields

- `id`
- `scope`
- `category`
- `class`
- `severity`
- `applies_if`
- `requirement`
- `check.type`
- `check.validator`
- `stages`
- `provenance`
- `adjustable`
- `remediation`
- `ui_message`

### 4.2 Do not add fields unless they are operationally used

Avoid a giant theoretical schema. `evidence_required`, for example, can usually be expressed inside the validator configuration rather than becoming a redundant top-level flag.

# 5. Extracted external-requirement schema

Every donor/assignment/template rule extracted from user material must retain its evidence trail.

```json
{
  "requirement_id": "REQ-123",
  "job_id": "job_abc",
  "requirement_key": "narrative.max_pages",
  "value": 10,
  "unit": "pages",
  "class": "REQUIRED",
  "severity": "BLOCKING",
  "source_type": "uploaded_call",
  "source_document_id": "doc_123",
  "source_quote": "The proposal narrative must not exceed 10 pages.",
  "source_location": {
    "page": 17,
    "section": "4.2 Proposal Narrative",
    "field": null
  },
  "confidence": 0.98,
  "locked": true,
  "confirmed_by_user": false,
  "counts_toward_limit_scope": ["core_narrative"],
  "notes": null
}
```

### 5.1 Confidence behavior

Suggested implementation thresholds:

```text
>= 0.90  may auto-activate when no conflict exists
0.75–0.89 activate as provisional and visibly flag
< 0.75   do not lock; require confirmation
```

For especially high-stakes requirements—deadline, eligibility, funding ceiling, cost share, prohibited cost, hard page limit—use stricter handling when extraction is ambiguous.

### 5.2 Evidence check for extracted rules

The extraction workflow should be hybrid:
1. LLM extracts a requirement and quote.
2. Code verifies that the quote or normalized equivalent actually exists at the indicated source location.
3. If verification fails, reduce confidence and do not lock automatically.

# 6. Limits and counting model

PaperAid must support:

```text
WORD_LIMIT
PAGE_LIMIT
CHARACTER_LIMIT
FIELD_LIMIT
```

A document may have several simultaneously.

Example:

```json
{
  "limits": [
    {
      "type": "PAGE_LIMIT",
      "max": 10,
      "scope": ["core_narrative"],
      "render_profile": "donor_profile_123",
      "blocking": true
    },
    {
      "type": "CHARACTER_LIMIT",
      "max": 2000,
      "scope": ["field.project_summary"],
      "includes_spaces": true,
      "blocking": true
    }
  ]
}
```

## 6.1 Page limits

Never declare page compliance from estimated words alone.

```text
word-budget plan
    ↓
draft
    ↓
apply required formatting
    ↓
render
    ↓
count actual pages
    ↓
compress only affected sections if over
```

## 6.2 Scope of a limit

Every structural element should be classifiable, for example:

```text
cover
executive_summary
table_of_contents
core_narrative
embedded_tables
references
budget_narrative
logframe
workplan
annexes
CVs
```

Each external rule sets `counts_toward_limit` for the relevant elements. Do not globally assume that the executive summary, references, tables, or annexes are excluded.

If an external call is ambiguous, PaperAid should count conservatively and warn.

# 7. Resolved job specification

Every job persists one versioned resolved specification. Models receive the resolved specification rather than reconstructing requirements from conversation context.

```json
{
  "spec_id": "spec_001",
  "job_id": "job_001",
  "document_type": "funding_proposal",
  "variant": "ngo_project",
  "mode": "standard",
  "rules_version": "1.0",
  "target_words": 5500,
  "limits": [],
  "required_sections": [],
  "optional_sections": [],
  "formatting": {},
  "citation_style": null,
  "research_policy": {},
  "reference_policy": {},
  "ai_use_policy": null,
  "scoring_criteria": [],
  "active_rules": [],
  "overridden_rules": [],
  "conflicts": [],
  "assumptions": []
}
```

A changed external requirement or user decision creates a new spec version rather than silently rewriting history.

# 8. Shared evidence and reference policy

## 8.1 Source priority depends on claim type

There is no universal static Tier A/Tier B ordering.

### Quantitative factual claims
Prefer:
1. official statistical source / government / authoritative intergovernmental dataset;
2. authoritative report based on primary data;
3. peer-reviewed analysis when appropriate.

### Intervention-effectiveness claims
Prefer:
1. systematic review / meta-analysis;
2. strong primary studies;
3. authoritative evidence synthesis.

### Donor requirements
Only the current governing donor/call/template/addendum source may establish compliance.

### Theory/concept claims
Prefer foundational/original source where appropriate, then strong scholarly synthesis.

## 8.2 Bibliographic status

```text
VERIFIED
PROBABLE
AMBIGUOUS
NOT_VERIFIED
```

PaperAid-added `NOT_VERIFIED` references cannot silently remain in final output.

## 8.3 Claim-support status

```text
SUPPORTED
PARTIALLY_SUPPORTED
NOT_SUPPORTED
CONTRADICTED
INSUFFICIENT_TEXT
```

## 8.4 Numeric claims

A precise numerical claim should not be marked `SUPPORTED` merely because the abstract or title is generally relevant. The exact figure must be supported by accessible source text or a trusted structured dataset.

## 8.5 User-supplied references

Do not silently delete an unverifiable user reference. Flag it and let the user decide unless it is demonstrably fabricated and the workflow explicitly allows correction.

## 8.6 Retractions/corrections

Where metadata permits:
- check retraction/correction status;
- flag retracted work;
- do not silently substitute a different publication.

# 9. Shared pre-draft and post-draft behavior

## 9.1 Gate states

```text
PASS
ASK_ONCE
BLOCK
PROCEED_WITH_ASSUMPTION
```

Block only when proceeding would be invalid, misleading, or wasteful.

Shared blockers include:
- unknown document type;
- unresolved mandatory external requirement;
- conflicting high-authority rules;
- impossible hard-length plan;
- explicit AI prohibition conflicting with a requested coursework full draft.

`ASK_ONCE` should be used for non-fatal missing details such as a coursework word limit or proposal duration. If the user skips, use a documented default where safe and record the assumption.

## 9.2 Validation order

Run:

```text
1. structural checks
2. limits
3. arithmetic / numeric checks
4. required-section checks
5. bibliographic verification
6. claim-source support
7. cross-section consistency
8. semantic quality
9. rendering / formatting
10. senior audit where routing requires it
```

Repair the smallest failing scope. Do not regenerate a full document to fix one local failure.

# 10. Shared numbered rules

| ID | Class | Severity | Stage | User-adjustable | Check | Requirement | Default remediation |

|---|---|---|---|---|---|---|---|

| SH-001 | REQUIRED | BLOCKING | INTAKE,PLAN | No | DETERMINISTIC | External mandatory instructions override PaperAid defaults. | Resolve precedence; external wins. |

| SH-002 | REQUIRED | BLOCKING | INTAKE | No | HYBRID | Every externally extracted requirement must retain the supporting quote and source location. | Re-extract with provenance. |

| SH-003 | REQUIRED | BLOCKING | INTAKE | No | DETERMINISTIC | Low-confidence mandatory extracted rules must not become silently locked. | Require confirmation. |

| SH-004 | REQUIRED | BLOCKING | PLAN,FINAL | No | DETERMINISTIC | Hard word, character, field, or page limits must be typed constraints rather than free-text notes. | Create typed constraint. |

| SH-005 | REQUIRED | BLOCKING | RENDER | No | DETERMINISTIC | Page-limit compliance must be checked on the rendered document using the required format. | Render and count pages. |

| SH-006 | DEFAULT | INFO | PLAN | Yes | DETERMINISTIC | When no external page limit exists, PaperAid plans primarily in words. | Use document default. |

| SH-007 | REQUIRED | BLOCKING | PLAN | No | DETERMINISTIC | Mandatory external sections cannot be removed by the user. | Restore section. |

| SH-008 | QUALITY | WARNING | PLAN | Yes | HYBRID | Published scoring criteria should influence planning depth and word allocation. | Rebalance plan. |

| SH-009 | REQUIRED | BLOCKING | FINAL | No | DETERMINISTIC | PaperAid-added references marked NOT_VERIFIED cannot remain in final output. | Verify, replace, or remove. |

| SH-010 | REQUIRED | BLOCKING | FINAL | No | HYBRID | Claims marked CONTRADICTED cannot remain as unqualified factual claims. | Correct, qualify, or remove. |

| SH-011 | REQUIRED | BLOCKING | FINAL | No | HYBRID | Claims marked NOT_SUPPORTED cannot remain as supported factual assertions. | Find support, qualify, or remove. |

| SH-012 | QUALITY | WARNING | FINAL | No | HYBRID | Stale evidence should be flagged when the task requires current evidence. | Research newer evidence or qualify date. |

| SH-013 | REQUIRED | BLOCKING | FINAL | No | DETERMINISTIC | In-text citations and reference-list entries must correspond where required by style. | Repair mapping. |

| SH-014 | REQUIRED | BLOCKING | FINAL | No | DETERMINISTIC | User-supplied numerical values must not be silently changed. | Restore original; flag discrepancy. |

| SH-015 | REQUIRED | BLOCKING | PLAN,FINAL | No | DETERMINISTIC | All resolved constraints must be persisted in a versioned job specification. | Persist spec. |

| SH-016 | REQUIRED | BLOCKING | PLAN | No | DETERMINISTIC | Unresolved conflicts between external mandatory instructions pause final locking of that requirement. | Ask for resolution. |

| SH-017 | DEFAULT | INFO | PLAN | Yes | DETERMINISTIC | Non-mandatory PaperAid defaults may be changed by the user within hard constraints. | Apply valid preference. |

| SH-018 | REQUIRED | BLOCKING | FINAL,RENDER | No | DETERMINISTIC | Final output must not exceed a hard external maximum after rendering. | Targeted compression. |

| SH-019 | REQUIRED | BLOCKING | FINAL | No | DETERMINISTIC | Final output must include every externally required section or field. | Insert missing content. |

| SH-020 | QUALITY | WARNING | DRAFT,FINAL | No | SEMANTIC | Document logic must remain internally coherent across sections. | Targeted consistency repair. |

| SH-021 | REQUIRED | BLOCKING | INTAKE | No | DETERMINISTIC | An official document-specific template is authoritative for structure when clearly applicable. | Map to template. |

| SH-022 | REQUIRED | BLOCKING | INTAKE,FINAL | No | DETERMINISTIC | Required citation style must be stored and validated explicitly. | Apply required style. |

| SH-023 | QUALITY | WARNING | FINAL | No | HYBRID | Source priority must depend on claim type rather than one static hierarchy. | Re-rank evidence. |

| SH-024 | REQUIRED | BLOCKING | FINAL | No | DETERMINISTIC | Reference metadata must not be fabricated to repair an unverifiable citation. | Flag or replace. |

| SH-025 | QUALITY | WARNING | FINAL | No | HYBRID | Secondary citations should be flagged when the original source is expected and reasonably obtainable. | Retrieve original where practical. |

| SH-026 | REQUIRED | BLOCKING | FINAL | No | HYBRID | A precise numerical factual claim requires source text or structured data that supports the figure. | Find stronger support or mark insufficient. |

| SH-027 | REQUIRED | BLOCKING | FINAL | No | DETERMINISTIC | Known retracted sources must be flagged before final release. | Replace or explicitly flag. |

| SH-028 | DEFAULT | INFO | PLAN | Yes | DETERMINISTIC | PaperAid word allocations are planning defaults, not universal laws. | Allow adjustment within constraints. |

| SH-029 | REQUIRED | BLOCKING | FINAL | No | DETERMINISTIC | A failed blocking rule prevents READY status. | Repair or set NEEDS_REVIEW. |

| SH-030 | QUALITY | INFO | FINAL | No | DETERMINISTIC | Warnings remain visible in the final compliance report even when export is permitted. | Include compliance report. |

# 11. Concept Note rulebook

## 11.1 Variants

```text
RESEARCH_CONCEPT
PROJECT_CONCEPT
FUNDING_CONCEPT
```

The first UI question can simply be:

> What are you preparing? — Research Concept / Project Concept / Funding Concept

If an uploaded template clearly identifies the variant, PaperAid may preselect it and allow correction.

## 11.2 Default length modes

These are PaperAid planning defaults only.

| Mode | Target words | Default range | Typical use |

|---|---|---|---|

| Brief | 900 | 800–1,000 | Letter of inquiry, very small concept, 2-page style call |

| Standard | 1,800 | 1,500–2,000 | Default funding/research concept |

| Extended | 2,900 | 2,500–3,300 | Dense concept-note call or technically detailed concept |

| External | Exact | Exact | Official requirement overrides all PaperAid modes |

PaperAid should show an estimated page range only after formatting is known. Do not present 3–5 pages as a universal law.

## 11.3 Funding Concept Note — Standard 1,800-word plan

| Section | Default words | Adjustable range | Purpose |

|---|---|---|---|

| Summary | 125 | 100–150 | Entire concept in miniature |

| Problem and evidence of need | 400 | 300–500 | Magnitude, population, geography, consequences |

| Target group and geography | 150 | 100–200 | Direct/indirect beneficiaries where relevant |

| Relevance and fit to funder priorities | 275 | 200–350 | Why this call/funder |

| Approach: goal, objectives, main activities, expected results | 475 | 350–550 | Core concept |

| Why this applicant / comparative advantage / partners | 175 | 120–220 | Specific delivery capability |

| Timeline and indicative budget | 75 | 50–120 + table | Conditional if not requested |

| Sustainability and principal risk | 125 | 80–180 | Concise |

If the donor scoring scheme strongly weights relevance, capacity, or another criterion, PaperAid should rebalance the plan inside the hard limit.

## 11.4 Research Concept Note — Standard plan

Default target: **1,800 words**, excluding references.

| Section | Default words |

|---|---|

| Working title / study identification | Separate |

| Background and problem/gap | 400 |

| Aim, objectives, research questions | 180 |

| Brief literature / conceptual context | 350 |

| Methods: design, setting, population, sampling, data, analysis | 500 |

| Ethics and feasibility | 150 |

| Expected contribution / significance | 120 |

| Timeline / resources | 100 |

| References | Separate |

Institutional research-concept rules override this structure.

## 11.5 Project Concept Note — Standard plan

Default target: **1,500 words**.

| Section | Default words |

|---|---|

| Summary | 120 |

| Context/problem/opportunity | 300 |

| Goal/objectives | 180 |

| Proposed approach / activities | 400 |

| Intended results | 180 |

| Target group / stakeholders | 100 |

| Feasibility / risks / resources | 120 |

| Decision requested / next step | 100 |

An internal Project Concept Note should end with a clear decision requested or next step.

## 11.6 Concept Note pre-draft gates

### Funding Concept — BLOCK when
- hard call limit is unresolved;
- required template cannot be mapped;
- eligibility clearly fails and user is asking for submission-ready output;
- no problem/opportunity can be identified;
- no intervention/idea exists.

### Funding Concept — ASK ONCE for
- target group;
- geography;
- duration;
- indicative budget envelope;
- applicant capability facts.

### Research Concept — BLOCK when
- no research topic/problem can be identified;
- institutional hard-rule conflict exists.

### Research Concept — ASK ONCE for
- study population;
- study area;
- academic level/programme;
- broad methodological direction where necessary.

### Project Concept — BLOCK when
- no decision/problem/opportunity is identifiable;
- no proposed action exists.

## 11.7 Concept Note numbered rules

| ID | Class | Severity | Stage | User-adjustable | Check | Requirement | Default remediation |

|---|---|---|---|---|---|---|---|

| CN-001 | REQUIRED | BLOCKING | PLAN | No | DETERMINISTIC | Concept-note variant must resolve to research, project, funding, or external template. | Resolve variant. |

| CN-002 | DEFAULT | INFO | PLAN | Yes | DETERMINISTIC | If no external length exists, Standard targets 1,800 words for funding/research concepts and 1,500 for project concepts. | Apply default target. |

| CN-003 | REQUIRED | BLOCKING | PLAN,RENDER | No | DETERMINISTIC | External page/word/character limits override PaperAid modes. | Use external limit. |

| CN-004 | QUALITY | WARNING | PLAN | Yes | HYBRID | The concept note should remain concise and decision-oriented rather than become a compressed full proposal. | Reduce unnecessary detail. |

| CN-005 | REQUIRED | BLOCKING | PLAN | No | HYBRID | A funding concept must identify a problem/opportunity and proposed intervention. | Request missing core input. |

| CN-006 | QUALITY | WARNING | DRAFT,FINAL | No | SEMANTIC | The problem should identify who is affected, where, and why the issue matters. | Strengthen framing. |

| CN-007 | QUALITY | WARNING | FINAL | No | HYBRID | Material factual claims in the problem section should be evidence-supported. | Add/verify evidence. |

| CN-008 | QUALITY | WARNING | PLAN,FINAL | No | SEMANTIC | Objectives must respond directly to the stated problem. | Realign objectives. |

| CN-009 | DEFAULT | INFO | PLAN | Yes | DETERMINISTIC | Funding concepts normally use 2–4 specific objectives unless external rules specify otherwise. | Adjust count. |

| CN-010 | QUALITY | WARNING | FINAL | No | SEMANTIC | Activities must plausibly contribute to objectives. | Repair mapping. |

| CN-011 | QUALITY | WARNING | FINAL | No | SEMANTIC | Outputs must be plausible products/services of proposed activities. | Repair output logic. |

| CN-012 | QUALITY | WARNING | FINAL | No | SEMANTIC | Outcomes must describe plausible change rather than repeat activities. | Rewrite outcomes. |

| CN-013 | QUALITY | WARNING | FINAL | No | SEMANTIC | Primary target group and geography should be identifiable when relevant. | Add target/geography. |

| CN-014 | REQUIRED | BLOCKING | PLAN,FINAL | No | HYBRID | If a funding call exists, the concept must address its mandatory priority areas. | Add alignment. |

| CN-015 | QUALITY | WARNING | FINAL | No | SEMANTIC | A funding concept must explain why the applicant/consortium is credible for the work. | Add capacity evidence. |

| CN-016 | QUALITY | WARNING | FINAL | No | SEMANTIC | Capacity claims should use specific projects, years, results, roles, or scale rather than adjectives alone. | Make capacity specific. |

| CN-017 | CONDITIONAL | WARNING | PLAN,FINAL | Yes | HYBRID | Include an indicative budget when required or materially necessary to judge feasibility. | Add budget. |

| CN-018 | CONDITIONAL | WARNING | PLAN,FINAL | Yes | HYBRID | Include a high-level timeline when required or material. | Add timeline. |

| CN-019 | QUALITY | WARNING | FINAL | No | SEMANTIC | Indicative budget must be plausible relative to activities and duration. | Review scale. |

| CN-020 | QUALITY | WARNING | FINAL | No | SEMANTIC | Identify at least one principal implementation risk when risk is material. | Add risk. |

| CN-021 | QUALITY | WARNING | FINAL | No | SEMANTIC | Address sustainability/continuation beyond initial support where relevant. | Add sustainability. |

| CN-022 | REQUIRED | BLOCKING | FINAL | No | DETERMINISTIC | Funding concept may not exceed a stated funding ceiling. | Reduce budget. |

| CN-023 | REQUIRED | BLOCKING | FINAL,RENDER | No | DETERMINISTIC | Concept note may not exceed a hard external narrative limit after rendering. | Compress. |

| CN-024 | CONDITIONAL | BLOCKING | FINAL | No | DETERMINISTIC | Mandatory external headings must appear in required order. | Repair structure. |

| CN-025 | QUALITY | WARNING | FINAL | No | SEMANTIC | Funding-concept relevance must connect the problem and intervention to the funder priorities. | Strengthen fit. |

| CN-026 | QUALITY | WARNING | PLAN | Yes | HYBRID | High-weight scoring criteria should receive proportionate depth. | Rebalance words. |

| CN-027 | REQUIRED | BLOCKING | FINAL | No | DETERMINISTIC | PaperAid-added references must pass bibliographic verification. | Verify/replace. |

| CN-028 | QUALITY | WARNING | FINAL | No | HYBRID | Evidence should be current enough for the claim unless older work is foundational/historical. | Update or justify. |

| CN-029 | QUALITY | WARNING | FINAL | No | SEMANTIC | Summary must accurately reflect problem, action, beneficiaries, and expected result. | Rewrite summary. |

| CN-030 | QUALITY | WARNING | FINAL | No | SEMANTIC | Summary must not introduce commitments absent from the body. | Align summary/body. |

| CN-031 | REQUIRED | BLOCKING | PLAN,FINAL | No | HYBRID | Research concepts must identify a research problem or gap. | Clarify gap. |

| CN-032 | QUALITY | WARNING | FINAL | No | SEMANTIC | Research objectives/questions must align with proposed methods. | Repair alignment. |

| CN-033 | QUALITY | WARNING | FINAL | No | SEMANTIC | Research concept methods should cover design, setting/population, sampling/data source, data collection, and analysis at concept-note depth. | Complete methods. |

| CN-034 | CONDITIONAL | WARNING | FINAL | No | SEMANTIC | Research concept should address ethics when human participants, personal data, vulnerable groups, or sensitive issues are involved. | Add ethics. |

| CN-035 | QUALITY | WARNING | FINAL | No | SEMANTIC | Research concept should state intended contribution/significance. | Add contribution. |

| CN-036 | QUALITY | WARNING | FINAL | No | SEMANTIC | Internal project concepts should state the decision/next step requested. | Add decision request. |

| CN-037 | QUALITY | WARNING | FINAL | No | SEMANTIC | Project concepts should not present tentative assumptions as finalized commitments. | Qualify assumptions. |

| CN-038 | REQUIRED | BLOCKING | INTAKE,PLAN | No | HYBRID | Field-specific character limits trigger form mode. | Create field constraints. |

| CN-039 | REQUIRED | BLOCKING | FINAL | No | DETERMINISTIC | Every form-mode field must comply with its own limit. | Compress field. |

| CN-040 | QUALITY | WARNING | FINAL | No | SEMANTIC | Avoid unnecessary duplication across short form fields. | Remove duplication. |

| CN-041 | QUALITY | WARNING | FINAL | No | SEMANTIC | Concept-note language should prioritize decision usefulness over exhaustive technical detail. | Simplify. |

| CN-042 | REQUIRED | BLOCKING | INTAKE,PLAN | No | DETERMINISTIC | Explicit failed applicant eligibility prevents submission-ready status. | Mark ineligible / exploratory only. |

| CN-043 | CONDITIONAL | WARNING | FINAL | No | SEMANTIC | Explain partner roles when partners are material to delivery. | Clarify roles. |

| CN-044 | QUALITY | WARNING | FINAL | No | HYBRID | No section should consume disproportionate space at the expense of highly weighted relevance/fit criteria. | Rebalance. |

| CN-045 | REQUIRED | BLOCKING | FINAL | No | DETERMINISTIC | All blocking Concept Note rules must pass before READY status. | Repair blocking failures. |

# 12. Funding Proposal rulebook

## 12.1 Variants

```text
NGO_PROJECT
RESEARCH_GRANT
EXTERNAL_TEMPLATE
FORM_APPLICATION
```

An official donor structure always overrides PaperAid generic headings.

## 12.2 Planning modes

| Mode | Target narrative words | Default range | Typical signal |

|---|---|---|---|

| Compact | 2,500 | 1,800–3,000 | Small/simple application, limited sites/partners, short delivery chain |

| Standard | 5,500 | 4,500–6,500 | Default serious professional proposal |

| Comprehensive | 10,000 | 8,000–14,000 | Consortium, multi-site/country, complex results/MEL/workstreams |

| External | Exact | Exact | Official donor limit |

Funding amount is only a secondary complexity signal. Do not classify the mode solely from the amount requested.

### 12.2.1 Complexity signals

```text
required_section_count
partner_count
country_or_site_count
project_duration
results_chain_depth
indicator_count
budget_line_complexity
required_annex_count
evaluation_criteria_count
MEL_requirements
submission_form_complexity
```

User may override PaperAid's recommendation when no external hard rule prevents it.

## 12.3 Standard 5,500-word fallback plan

| Section | Default words | Notes |

|---|---|---|

| Executive Summary | 300 | Count separately only when donor rules exclude it |

| Problem / Situation Analysis | 650 | Evidence, root causes, consequences |

| Target Population / Stakeholders | 250 | Who, where, why them |

| Goal & Specific Objectives | 200 | Concise |

| Intervention Logic | 350 | Narrative logic; formal ToC optional |

| Technical Approach / Strategy | 950 | Core design |

| Activities & Implementation | 500 | Sequencing/delivery |

| Expected Results | 300 | Outcomes/outputs |

| Monitoring, Evaluation & Learning | 550 | Measurement and learning |

| Risks & Mitigation | 200 | Principal risks |

| Sustainability / Exit / Scale | 300 | Continuation/handover |

| Organisational Capacity / Management | 400 | Specific capability |

| Budget Narrative / Value-for-Money explanation | 550 | Unless donor separates it |

| TOTAL | 5,500 |  |

Standalone artifacts typically include detailed budget, logframe/results table, workplan, M&E indicator table, annexes, CVs, and policies. Whether they count toward a donor limit is donor-specific.

## 12.4 Compact 2,500-word fallback plan

| Section | Words |

|---|---|

| Executive Summary | 150 |

| Problem / Need | 350 |

| Target Population | 100 |

| Goal / Objectives | 100 |

| Technical Approach | 550 |

| Implementation | 250 |

| Expected Results | 150 |

| MEL | 250 |

| Risk | 100 |

| Sustainability | 150 |

| Capacity / Management | 150 |

| Budget Narrative | 200 |

| TOTAL | 2,500 |

## 12.5 Comprehensive 10,000-word fallback plan

| Section | Words |

|---|---|

| Executive Summary | 450 |

| Problem / Situation Analysis | 1,200 |

| Target Population / Stakeholders | 450 |

| Goal & Objectives | 300 |

| Intervention Logic / ToC narrative | 700 |

| Technical Approach | 1,700 |

| Implementation / Workstreams | 900 |

| Expected Results | 500 |

| MEL | 1,000 |

| Risk / Assumptions | 400 |

| Sustainability / Scale / Exit | 600 |

| Organisational Capacity / Management | 700 |

| Partnerships / Consortium | 400 |

| Budget Narrative / Value for Money | 700 |

| TOTAL PLANNED | 10,000 |

If a standalone partnerships section is irrelevant, redistribute those words rather than forcing the heading.

## 12.6 Results Model — single source of truth

Every non-trivial funding proposal uses a structured Results Model.

```json
{
  "goal": {"id": "G1", "statement": ""},
  "outcomes": [
    {
      "id": "O1",
      "statement": "",
      "indicators": ["I1"],
      "assumptions": [],
      "risks": []
    }
  ],
  "outputs": [
    {
      "id": "OP1",
      "statement": "",
      "outcome_id": "O1",
      "indicators": ["I2"]
    }
  ],
  "activities": [
    {
      "id": "A1",
      "statement": "",
      "output_id": "OP1",
      "responsible_role": "",
      "start": "",
      "end": "",
      "budget_lines": ["B1"]
    }
  ],
  "indicators": [
    {
      "id": "I1",
      "level": "outcome",
      "definition": "",
      "unit": "",
      "baseline": null,
      "baseline_plan": null,
      "target": null,
      "disaggregation": [],
      "means_of_verification": "",
      "frequency": "",
      "responsible_role": ""
    }
  ],
  "budget_lines": [],
  "timeline": []
}
```

The following are rendered from that model rather than independently authored:
- logframe/results table;
- workplan;
- M&E indicator table;
- activity-budget mapping;
- formal ToC diagram when needed.

## 12.7 Canonical results vocabulary

- **Activity:** what the project does.
- **Output:** product/service/deliverable or immediate result substantially under project control.
- **Outcome:** short-/medium-term change in behavior, practice, access, capacity, performance, status, or system functioning.
- **Impact/Goal:** higher-level longer-term intended change.

Do not label “Train 200 nurses” as an outcome.

## 12.8 Indicator minimum fields

Each indicator should support:

```text
definition
level
unit
baseline OR baseline-establishment plan
target
disaggregation where meaningful
means of verification
frequency
responsible role
```

## 12.9 MEL minimum content for Standard/Comprehensive

Normally cover:
- results framework;
- indicators;
- data sources;
- data collection methods/tools;
- baseline plan;
- targets;
- measurement frequency;
- responsibility;
- data-quality assurance;
- reporting;
- learning/adaptation;
- evaluation approach when applicable;
- data protection where personal data is used;
- resource/budget linkage.

Do not hard-code a universal MEL budget percentage. Warn when a substantial MEL system exists with no identifiable resource allocation.

## 12.10 Budget engine

Budget arithmetic is deterministic. Minimum checks:

```text
unit cost × quantity
line subtotal
category subtotal
year subtotal
grand total
funding ceiling
cost-share requirement and calculation base
indirect-cost rate and calculation base
currency
exchange rate + date when conversion is used
staff effort / level of effort
timeline consistency
activity mapping
prohibited costs
numeric consistency with narrative
```

Do not hard-code one indirect-cost percentage or base.

## 12.11 Cross-cutting overlays

Default triggered checks:
- **Safeguarding** when children/vulnerable adults/protection-sensitive groups are involved or donor rules require it.
- **Data protection** when personal, health, or identifiable participant data are processed.

Other overlays activate only when call/sector/profile makes them relevant:
- gender;
- disability inclusion;
- environment;
- climate;
- localisation;
- conflict sensitivity;
- human rights;
- value for money.

Never rely on model memory for donor-policy wording when a current governing document exists.

## 12.12 Research-grant variant

Do not force NGO headings onto research grants.

When a scheme is identified, use the scheme structure. When no scheme is supplied, fallback:

```text
Project Summary / Abstract
Specific Aims / Research Objectives
Significance / Problem
Innovation / Contribution
Research Strategy / Approach
Methods
Analysis
Feasibility
Team / Environment
Ethics / Data Management as relevant
Timeline / Milestones
Budget / Justification
References
```

Fallback strategy narrative: **4,000–6,000 words** unless an external limit applies.

## 12.13 Funding pre-draft gates

### BLOCK
- explicit failed eligibility for submission-ready mode;
- unresolved hard page/word/character constraint;
- mandatory template cannot be mapped;
- no problem/need;
- no intervention concept;
- unresolved conflict in funding ceiling or other mandatory requirement.

### ASK ONCE
- amount requested;
- duration;
- geography;
- applicant legal entity;
- partners;
- target population;
- capacity facts.

### PROCEED WITH ASSUMPTION
Only for non-mandatory information; record the assumption visibly.

## 12.14 Funding Proposal numbered rules

| ID | Class | Severity | Stage | User-adjustable | Check | Requirement | Default remediation |

|---|---|---|---|---|---|---|---|

| FP-001 | REQUIRED | BLOCKING | INTAKE | No | HYBRID | If a funding call/template is supplied, extract and resolve mandatory requirements before drafting. | Run compliance extraction. |

| FP-002 | REQUIRED | BLOCKING | INTAKE | No | DETERMINISTIC | Explicit eligibility criteria must be evaluated before submission-ready drafting. | Evaluate eligibility. |

| FP-003 | REQUIRED | BLOCKING | PLAN | No | DETERMINISTIC | Failed mandatory eligibility prevents READY status. | Mark ineligible. |

| FP-004 | DEFAULT | INFO | PLAN | Yes | DETERMINISTIC | When no external length exists, Standard mode targets 5,500 narrative words. | Apply Standard target. |

| FP-005 | DEFAULT | INFO | PLAN | Yes | HYBRID | Recommend Compact/Standard/Comprehensive primarily from complexity, not funding amount. | Run complexity classifier. |

| FP-006 | REQUIRED | BLOCKING | PLAN,RENDER | No | DETERMINISTIC | External word/page/character limits override PaperAid funding modes. | Use donor limit. |

| FP-007 | REQUIRED | BLOCKING | INTAKE,PLAN | No | HYBRID | Field-limited applications must be represented as per-field constraints. | Create form mode. |

| FP-008 | REQUIRED | BLOCKING | FINAL | No | DETERMINISTIC | Each form field must comply with its own hard limit. | Compress field. |

| FP-009 | QUALITY | WARNING | PLAN | Yes | HYBRID | Published scoring criteria should influence section depth and emphasis. | Rebalance plan. |

| FP-010 | QUALITY | WARNING | PLAN,FINAL | No | SEMANTIC | Proposal must articulate a clear problem/need/opportunity grounded in evidence. | Strengthen problem. |

| FP-011 | QUALITY | WARNING | FINAL | No | SEMANTIC | Problem analysis should identify material root causes, not only symptoms. | Add root-cause analysis. |

| FP-012 | QUALITY | WARNING | FINAL | No | SEMANTIC | Problem analysis should identify affected population and geography. | Add context. |

| FP-013 | QUALITY | WARNING | FINAL | No | HYBRID | Material quantitative claims should be supported by appropriate evidence. | Verify evidence. |

| FP-014 | REQUIRED | BLOCKING | PLAN | No | HYBRID | Every non-trivial funding proposal must have a Results Model. | Build Results Model. |

| FP-015 | QUALITY | WARNING | PLAN,FINAL | No | SEMANTIC | Goal must describe higher-level intended change, not activities. | Rewrite goal. |

| FP-016 | QUALITY | WARNING | PLAN,FINAL | No | SEMANTIC | Objectives must respond directly to the problem/project logic. | Realign objectives. |

| FP-017 | QUALITY | WARNING | FINAL | No | SEMANTIC | Objectives should be sufficiently specific and assessable for the donor context. | Improve objectives. |

| FP-018 | REQUIRED | BLOCKING | PLAN,FINAL | No | DETERMINISTIC | Every activity in the Results Model maps to an output. | Map activity. |

| FP-019 | REQUIRED | BLOCKING | PLAN,FINAL | No | DETERMINISTIC | Every output maps to at least one outcome. | Map output. |

| FP-020 | QUALITY | WARNING | FINAL | No | SEMANTIC | Outputs describe products/services/deliverables rather than activities disguised as results. | Repair output wording. |

| FP-021 | QUALITY | WARNING | FINAL | No | SEMANTIC | Outcomes describe plausible change rather than completed activities. | Repair outcome wording. |

| FP-022 | REQUIRED | BLOCKING | PLAN,FINAL | No | DETERMINISTIC | Every outcome has at least one indicator in Standard/Comprehensive proposals. | Create indicator. |

| FP-023 | CONDITIONAL | WARNING | PLAN,FINAL | No | DETERMINISTIC | Outputs have indicators when required by donor/results framework. | Add output indicator. |

| FP-024 | REQUIRED | BLOCKING | FINAL | No | HYBRID | Each indicator measures the result level under which it sits. | Repair indicator level. |

| FP-025 | REQUIRED | BLOCKING | PLAN,FINAL | No | DETERMINISTIC | Each active indicator has a defined unit. | Add unit. |

| FP-026 | REQUIRED | BLOCKING | PLAN,FINAL | No | DETERMINISTIC | Each outcome indicator has a baseline or stated baseline-establishment plan/date. | Add baseline plan. |

| FP-027 | REQUIRED | BLOCKING | PLAN,FINAL | No | DETERMINISTIC | Each outcome indicator has a target unless donor rules explicitly allow otherwise. | Add target. |

| FP-028 | QUALITY | WARNING | FINAL | No | SEMANTIC | Indicator targets should be plausible relative to baseline, duration, resources, and scale. | Review target. |

| FP-029 | CONDITIONAL | WARNING | FINAL | No | HYBRID | Indicators include meaningful disaggregation when required/relevant. | Add disaggregation. |

| FP-030 | REQUIRED | BLOCKING | FINAL | No | DETERMINISTIC | Each indicator identifies a means of verification/data source. | Add source. |

| FP-031 | REQUIRED | BLOCKING | FINAL | No | DETERMINISTIC | Each indicator identifies measurement frequency where applicable. | Add frequency. |

| FP-032 | REQUIRED | BLOCKING | FINAL | No | DETERMINISTIC | Each indicator identifies a responsible role/unit. | Assign responsibility. |

| FP-033 | QUALITY | WARNING | FINAL | No | SEMANTIC | Technical approach explains why the intervention is expected to address the problem. | Strengthen causal rationale. |

| FP-034 | QUALITY | WARNING | FINAL | No | HYBRID | Technical approach uses effectiveness/rationale evidence where appropriate. | Add evidence. |

| FP-035 | QUALITY | WARNING | FINAL | No | SEMANTIC | Distinguish what is novel/adapted from standard practice when relevant. | Clarify approach. |

| FP-036 | REQUIRED | BLOCKING | PLAN,FINAL | No | DETERMINISTIC | Every major activity appears in the implementation timeline. | Add timeline item. |

| FP-037 | REQUIRED | BLOCKING | PLAN,FINAL | No | DETERMINISTIC | Every costed activity maps to at least one budget line. | Map budget line. |

| FP-038 | REQUIRED | BLOCKING | PLAN,FINAL | No | DETERMINISTIC | Every budget line maps to an activity or declared support/administrative category. | Map budget purpose. |

| FP-039 | REQUIRED | BLOCKING | FINAL | No | DETERMINISTIC | Budget unit cost × quantity equals line subtotal. | Correct arithmetic. |

| FP-040 | REQUIRED | BLOCKING | FINAL | No | DETERMINISTIC | Budget category totals reconcile to the grand total. | Correct totals. |

| FP-041 | REQUIRED | BLOCKING | FINAL | No | DETERMINISTIC | Requested amount does not exceed funding ceiling. | Reduce request. |

| FP-042 | CONDITIONAL | BLOCKING | FINAL | No | DETERMINISTIC | Required cost share/co-financing meets required percentage and calculation base. | Correct cost share. |

| FP-043 | CONDITIONAL | BLOCKING | FINAL | No | DETERMINISTIC | Indirect costs use the rate and base allowed by the governing call/policy. | Correct indirect costs. |

| FP-044 | CONDITIONAL | BLOCKING | FINAL | No | DETERMINISTIC | Prohibited costs identified by the call do not appear in the budget. | Remove prohibited cost. |

| FP-045 | REQUIRED | BLOCKING | FINAL | No | DETERMINISTIC | Multi-year and category subtotals reconcile to the same grand total. | Repair totals. |

| FP-046 | CONDITIONAL | WARNING | FINAL | No | DETERMINISTIC | Currency conversion stores exchange rate and date when conversion affects values. | Add exchange metadata. |

| FP-047 | REQUIRED | BLOCKING | FINAL | No | DETERMINISTIC | Staff effort/LOE is consistent across narrative, timeline, and budget. | Reconcile effort. |

| FP-048 | REQUIRED | BLOCKING | FINAL | No | DETERMINISTIC | Beneficiary counts, duration, totals, and major numeric commitments are consistent across sections/annexes. | Repair numeric inconsistency. |

| FP-049 | QUALITY | WARNING | FINAL | No | SEMANTIC | MEL narrative explains how performance/outcomes will be measured and used. | Strengthen MEL. |

| FP-050 | CONDITIONAL | WARNING | FINAL | No | HYBRID | Substantial MEL plans identify data-quality assurance mechanisms. | Add DQA. |

| FP-051 | QUALITY | WARNING | FINAL | No | SEMANTIC | MEL includes learning/adaptation when implementation learning is relevant. | Add learning loop. |

| FP-052 | CONDITIONAL | WARNING | FINAL | No | SEMANTIC | Evaluation timing/independence is described when evaluation is required/material. | Add evaluation approach. |

| FP-053 | CONDITIONAL | WARNING | FINAL | No | DETERMINISTIC | Projects collecting personal/sensitive data include appropriate data-protection arrangements. | Add data protection. |

| FP-054 | QUALITY | WARNING | FINAL | No | HYBRID | Substantial MEL framework with no identifiable resources is flagged. | Add/justify MEL resources. |

| FP-055 | QUALITY | WARNING | FINAL | No | SEMANTIC | Risk sections pair material risks with concrete mitigation. | Add mitigation. |

| FP-056 | QUALITY | WARNING | FINAL | No | SEMANTIC | Risk mitigation is feasible and owned by a role where practical. | Strengthen ownership. |

| FP-057 | QUALITY | WARNING | FINAL | No | SEMANTIC | Sustainability explains continued benefit/ownership rather than merely asserting sustainability. | Strengthen sustainability. |

| FP-058 | CONDITIONAL | WARNING | FINAL | No | SEMANTIC | Scale/replication is addressed when it is a donor objective or explicit project ambition. | Add scale strategy. |

| FP-059 | QUALITY | WARNING | FINAL | No | SEMANTIC | Capacity claims use specific projects, dates, donors, scale, results, systems, audits, or staff evidence. | Make capacity specific. |

| FP-060 | QUALITY | WARNING | FINAL | No | SEMANTIC | Management structure identifies decision-making and delivery responsibility appropriate to complexity. | Clarify management. |

| FP-061 | CONDITIONAL | WARNING | FINAL | No | SEMANTIC | Partner roles and responsibility division are clear for consortium/co-applicant proposals. | Clarify partner roles. |

| FP-062 | REQUIRED | BLOCKING | FINAL | No | HYBRID | Proposal explicitly addresses mandatory donor priorities and scoring criteria. | Add missing alignment. |

| FP-063 | REQUIRED | BLOCKING | FINAL | No | DETERMINISTIC | Mandatory donor headings/fields are present in required order. | Repair structure. |

| FP-064 | REQUIRED | BLOCKING | FINAL,RENDER | No | DETERMINISTIC | All hard donor limits pass after rendering/form validation. | Compress/restructure. |

| FP-065 | CONDITIONAL | WARNING | PLAN,FINAL | No | HYBRID | Safeguarding is addressed when beneficiary profile or donor policy triggers it. | Add safeguarding. |

| FP-066 | CONDITIONAL | WARNING | PLAN,FINAL | No | HYBRID | Data protection is addressed when personal/health/identifiable data is processed. | Add protection plan. |

| FP-067 | CONDITIONAL | WARNING | PLAN,FINAL | No | HYBRID | Other cross-cutting overlays activate only when call/sector/profile requires or materially warrants them. | Apply relevant overlay. |

| FP-068 | REQUIRED | BLOCKING | INTAKE,FINAL | No | HYBRID | Donor-policy-specific language comes from current governing documents, not model memory. | Retrieve current requirement. |

| FP-069 | QUALITY | WARNING | FINAL | No | SEMANTIC | Executive summary accurately reflects problem, intervention, results, duration, geography, applicant, and request. | Rewrite summary. |

| FP-070 | QUALITY | WARNING | FINAL | No | SEMANTIC | Executive summary introduces no major commitment absent from body/Results Model. | Align summary/body. |

| FP-071 | CONDITIONAL | WARNING | PLAN,FINAL | Yes | HYBRID | Formal ToC section/diagram is required only when call or complexity warrants; internal intervention logic is always required. | Generate formal ToC if triggered. |

| FP-072 | DEFAULT | INFO | PLAN,FINAL | Yes | DETERMINISTIC | Standard/Comprehensive NGO proposals normally render a logframe/results table unless donor format makes it unnecessary. | Generate logframe. |

| FP-073 | REQUIRED | BLOCKING | FINAL | No | DETERMINISTIC | Logframe/results table is rendered from Results Model and cannot diverge from it. | Regenerate from model. |

| FP-074 | REQUIRED | BLOCKING | FINAL | No | DETERMINISTIC | Workplan is rendered from activity/timeline state and cannot contradict narrative dates. | Regenerate workplan. |

| FP-075 | REQUIRED | BLOCKING | FINAL | No | DETERMINISTIC | M&E indicator table is rendered from Results Model and has no orphan indicators. | Repair model. |

| FP-076 | REQUIRED | BLOCKING | FINAL | No | DETERMINISTIC | PaperAid-added references are verified before finalization. | Verify/replace. |

| FP-077 | QUALITY | WARNING | FINAL | No | HYBRID | Effectiveness claims prefer appropriate evidence synthesis where stronger evidence exists. | Improve source quality. |

| FP-078 | CONDITIONAL | BLOCKING | INTAKE,PLAN | No | HYBRID | Identified research-grant schemes switch to scheme-specific structure. | Apply research-grant profile. |

| FP-079 | QUALITY | WARNING | FINAL | No | SEMANTIC | Research-grant significance, contribution/innovation, approach, and methods remain logically aligned. | Repair strategy. |

| FP-080 | REQUIRED | BLOCKING | FINAL | No | DETERMINISTIC | All blocking funding-proposal rules pass before READY status. | Repair blocking failures. |

# 13. Academic Coursework rulebook

## 13.1 Supported types

```text
ESSAY
ACADEMIC_REPORT
CASE_STUDY
LITERATURE_REVIEW
SHORT_RESEARCH_PAPER
REFLECTIVE_ASSIGNMENT
```

`CRITICAL_ANALYSIS` is a directive/quality mode, not a separate document type.

## 13.2 Length fallback

A missing word limit should trigger one targeted question:

> What word limit did your lecturer give you?

If the user skips and no brief contains a limit:

| Level | Fallback target words |

|---|---|

| First-year undergraduate | 1,500 |

| Later undergraduate | 2,000 |

| Postgraduate | 3,000 |

Type adjustments:
- Reflective work: usually 1,000–1,500 unless the brief says otherwise.
- Literature review: PaperAid may recommend ~25% more than the level baseline for a broad review, but this remains a suggestion.
- Short research paper: use level baseline unless task scope clearly requires otherwise.

Never assume a ±10% tolerance unless the brief/institution explicitly permits it.

## 13.3 Assignment parser

Parse:

```text
DIRECTIVE WORDS
SUBJECT-MATTER WORDS
LIMITING WORDS
SUBQUESTIONS
REQUIRED OUTPUTS
```

Example:

> Critically evaluate the effectiveness of community health workers in improving maternal health outcomes in rural Uganda since 2015.

becomes:

```text
directive: critically evaluate
subject: effectiveness of community health workers
outcome domain: maternal health outcomes
geography: rural Uganda
time limit: since 2015
```

Compound questions produce one coverage check per directive/sub-question.

## 13.4 Command-word engine

| Directive | Operational expectation |

|---|---|

| Define | Give precise meaning; distinguish from related concepts if useful. |

| Identify | Select/name relevant items. |

| Describe | Present relevant characteristics, stages, or sequence. |

| Outline | Give main features concisely. |

| Summarise | Condense key ideas without unnecessary detail. |

| Explain | Show how/why; make causal, mechanistic, or logical connection. |

| Analyse | Break into components and examine relationships. |

| Critically analyse | Analyse and evaluate evidence, assumptions, strengths, weaknesses, and limitations. |

| Evaluate | Judge using explicit or inferable criteria and evidence. |

| Discuss | Develop a balanced/reasoned examination; infer precise expectation from rubric/context if the term is used loosely. |

| Compare | Examine similarities and relevant differences. |

| Compare and contrast | Systematically examine similarities and differences. |

| Assess | Determine significance, value, extent, or effectiveness from evidence. |

| Examine | Investigate closely and explain significant features/relationships. |

| Explore | Investigate multiple dimensions without requiring a rigid single conclusion. |

| To what extent / How far | Evaluate degree and state qualified acceptance/rejection. |

| Justify | Give evidence-based reasons for a choice or position. |

| Critique / Criticise | Evaluate strengths, weaknesses, assumptions, evidence, and implications. |

| Review | Summarise and evaluate a body of information according to context. |

| Interpret | Explain meaning/significance of evidence, data, text, or findings. |

| Account for | Explain reasons/causes. |

| Illustrate | Explain using relevant examples/evidence. |

| Recommend / Propose | Present feasible action justified by analysis. |

| Apply | Use a theory/model/method in a specified case/context. |

| Design | Construct a coherent solution/model/plan under constraints. |

| Reflect | Analyse experience/learning rather than merely narrate it. |

`Critically` is a modifier: it raises the required level of judgment for analyse/evaluate/assess/compare/etc.

## 13.5 Rubric conversion

When a rubric is supplied:
1. extract criterion;
2. extract weight;
3. extract top-band descriptor;
4. create a weighted QUALITY rule;
5. map criterion to planned sections;
6. use weighting to influence depth;
7. audit final work per criterion.

Do not translate 40% of marks into exactly 40% of words.

Example:

```json
{
  "criterion": "Critical analysis",
  "weight": 40,
  "target_descriptor": "Demonstrates sustained critical evaluation...",
  "mapped_sections": ["body"],
  "rule_id": "job-rubric-01"
}
```

## 13.6 Research policy

### Research externally when
- independent reading is expected;
- no closed source pack exists;
- current evidence is required;
- the task is a literature review/research paper;
- references are expected but not supplied.

### Do not expand beyond supplied sources when
- brief restricts sources to set readings;
- task is closed-book;
- external sources are prohibited;
- the task is personal reflection where external evidence is not required.

Required readings supplied by the user come first.

There is **no universal references-per-1,000-words rule**. Any source-count recommendation is non-binding and should consider academic level, task breadth, discipline, claim density, word count, and document type.

## 13.7 Essay fallback

```text
Introduction  ≈10%
Main body     ≈80%
Conclusion    ≈10%
```

Allow introductions up to about 15% where genuine framing complexity warrants it. These are quality heuristics, not blocking rules.

## 13.8 Academic Report fallback

```text
Title
Executive Summary (conditional)
Introduction
Background / Context
Method / Approach (conditional)
Findings / Analysis
Discussion (may be combined)
Recommendations (conditional)
Conclusion
References
Appendices
```

Use meaningful headings.

## 13.9 Literature Review fallback

```text
Introduction
Scope / review question
Search/approach paragraph (postgraduate or when required)
Thematic / methodological / conceptual synthesis
Within each theme:
  areas of agreement
  contradictions
  methodological differences
  limitations
  implications
Research gaps
Conclusion
References
```

Do not make “Agreement / Conflict / Gap” a rigid sequential structure if it encourages author-by-author summaries. Synthesis should occur inside themes.

## 13.10 Case Study variants

### Analytical
```text
Introduction
Case context
Analytical framework/model
Analysis of evidence/events
Interpretation
Lessons / implications
Conclusion
```

### Problem-oriented
```text
Introduction
Case context
Problem definition
Analysis / diagnosis
Options / alternatives
Evaluation of options
Recommendation
Implementation considerations
Conclusion
```

## 13.11 Short Research Paper

### Empirical
```text
Introduction
Brief literature/context
Methods
Results/analysis if data are supplied or permitted
Discussion
Conclusion
References
```

### Analytical/non-empirical
```text
Introduction
Brief literature/context
Analytical framework/approach if useful
Main analysis
Discussion
Conclusion
References
```

Do not force a methodology section into a non-empirical task.

## 13.12 Reflective Assignment

```text
Introduction
Brief context/experience
Critical reflection
Integration with theory/evidence if required
Learning/implications
Action plan where appropriate
Conclusion
References where required
```

Never fabricate the student's personal experience. Ask for the experience/context if the task depends on it.

## 13.13 Criticality classifier

Internally classify substantive body paragraphs:

```text
DESCRIPTIVE
ANALYTICAL
EVALUATIVE
REFLECTIVE
```

Use only as a quality signal, not as an official mark.

For `critically evaluate`:
- most substantive body paragraphs should be analytical/evaluative;
- at least one meaningful counter-position/limitation should be addressed where appropriate;
- judgment criteria should be explicit or inferable;
- conclusion should give a reasoned judgment.

For `describe`, do not penalise appropriate description.

## 13.14 AI-use / academic-integrity policy

If the brief/institution explicitly prohibits generative AI:

```text
FULL_DRAFTING = DISABLED
```

PaperAid may provide only support permitted by that policy, such as planning, explanation, research guidance, source organization, feedback on the student's own draft, citation checking, or formatting.

If AI use is explicitly permitted with disclosure, PaperAid may generate a disclosure statement when requested.

If policy is unknown, PaperAid may proceed according to product settings, but must not claim compliance with an unknown institution policy.

Generated coursework does not receive a “make undetectable” or detector-evasion stage. The final internal step is **Academic Quality & Integrity Review**.

## 13.15 Coursework pre-draft gates

### BLOCK
- no assignment question/task;
- unresolved external hard instruction;
- explicit AI prohibition conflicting with requested full drafting;
- mandatory source pack explicitly required but unavailable.

### ASK ONCE
- word limit;
- academic level;
- citation style;
- coursework type if ambiguous;
- required readings referenced but not supplied.

### PROCEED WITH ASSUMPTION
Use level-based word target only after the missing limit has been asked once and skipped. Record the assumption.

## 13.16 Coursework numbered rules

| ID | Class | Severity | Stage | User-adjustable | Check | Requirement | Default remediation |

|---|---|---|---|---|---|---|---|

| CW-001 | REQUIRED | BLOCKING | INTAKE | No | HYBRID | Assignment question/brief must be available before full drafting. | Request task. |

| CW-002 | REQUIRED | BLOCKING | PLAN | No | HYBRID | Directive words, subject matter, limiting words, and subquestions must be parsed before drafting. | Parse task. |

| CW-003 | REQUIRED | BLOCKING | PLAN,FINAL | No | DETERMINISTIC | Every explicit subquestion is represented in the plan and answered in final work. | Add coverage. |

| CW-004 | REQUIRED | BLOCKING | PLAN | No | HYBRID | Coursework type must be resolved or confirmed. | Resolve type. |

| CW-005 | REQUIRED | BLOCKING | PLAN,RENDER | No | DETERMINISTIC | External word/page/character limits override level defaults. | Use external limit. |

| CW-006 | DEFAULT | INFO | PLAN | Yes | DETERMINISTIC | If no limit exists after one clarification, use level-based fallback target. | Apply fallback. |

| CW-007 | REQUIRED | BLOCKING | FINAL | No | DETERMINISTIC | Do not assume ±10% tolerance unless explicitly permitted. | Use configured tolerance only. |

| CW-008 | REQUIRED | BLOCKING | PLAN,FINAL | No | HYBRID | Response must fulfil directive meaning appropriate to context. | Repair task fulfillment. |

| CW-009 | QUALITY | WARNING | FINAL | No | SEMANTIC | A descriptive task is not penalized for appropriately descriptive writing. | Adjust criticality expectation. |

| CW-010 | QUALITY | WARNING | FINAL | No | SEMANTIC | An analytical task examines components/relationships rather than only summarizing. | Add analysis. |

| CW-011 | QUALITY | WARNING | FINAL | No | SEMANTIC | A critical task evaluates evidence, assumptions, strengths, weaknesses, limitations, or competing evidence where appropriate. | Add critical evaluation. |

| CW-012 | QUALITY | WARNING | FINAL | No | SEMANTIC | An evaluative task reaches a reasoned judgment using criteria/evidence. | Add judgment. |

| CW-013 | QUALITY | WARNING | FINAL | No | SEMANTIC | A compare task examines similarities and relevant differences. | Add balance. |

| CW-014 | QUALITY | WARNING | FINAL | No | SEMANTIC | A to-what-extent/how-far task states the degree of acceptance/rejection. | Add qualified judgment. |

| CW-015 | QUALITY | WARNING | FINAL | No | SEMANTIC | A justify task gives evidence-based reasons. | Add justification. |

| CW-016 | QUALITY | WARNING | FINAL | No | SEMANTIC | Recommendations are grounded in preceding analysis. | Align recommendations. |

| CW-017 | QUALITY | WARNING | FINAL | No | SEMANTIC | Reflective tasks analyse learning/experience rather than merely narrate. | Deepen reflection. |

| CW-018 | REQUIRED | BLOCKING | INTAKE,PLAN | No | HYBRID | If a rubric is supplied, criteria and weights are extracted into the resolved specification. | Parse rubric. |

| CW-019 | QUALITY | WARNING | PLAN | Yes | HYBRID | Rubric weights influence depth without direct 1:1 word conversion. | Rebalance plan. |

| CW-020 | QUALITY | WARNING | FINAL | No | SEMANTIC | Final work is assessed against each extracted rubric criterion. | Run rubric audit. |

| CW-021 | REQUIRED | BLOCKING | FINAL | No | HYBRID | Explicit learning outcomes named in brief/rubric are evidenced somewhere in submission. | Add coverage. |

| CW-022 | DEFAULT | INFO | PLAN | Yes | DETERMINISTIC | Essay planning may use approximately 10/80/10 when no better instruction exists. | Apply heuristic. |

| CW-023 | QUALITY | WARNING | FINAL | No | SEMANTIC | Essay introduction establishes context, scope, position where appropriate, and route through response. | Strengthen introduction. |

| CW-024 | QUALITY | WARNING | FINAL | No | SEMANTIC | Introduction should not consume disproportionate space without task justification. | Compress introduction. |

| CW-025 | QUALITY | WARNING | FINAL | No | SEMANTIC | Body paragraphs have clear controlling ideas and contribute to the assignment argument. | Repair focus. |

| CW-026 | QUALITY | WARNING | FINAL | No | SEMANTIC | Source-listing paragraphs with little synthesis are flagged in analytical coursework. | Add synthesis. |

| CW-027 | QUALITY | WARNING | FINAL | No | SEMANTIC | Evidence is interpreted and linked to the assignment question. | Add analysis/link. |

| CW-028 | QUALITY | WARNING | FINAL | No | SEMANTIC | Conclusion answers the task and synthesizes the argument. | Rewrite conclusion. |

| CW-029 | QUALITY | WARNING | FINAL | No | HYBRID | Conclusion does not introduce a major new line of evidence absent from the body. | Move/remove evidence. |

| CW-030 | REQUIRED | BLOCKING | PLAN,FINAL | No | HYBRID | Academic reports follow externally required headings when supplied. | Map report structure. |

| CW-031 | CONDITIONAL | WARNING | PLAN,FINAL | Yes | HYBRID | Empirical reports normally include a method/approach section. | Add method. |

| CW-032 | QUALITY | WARNING | FINAL | No | SEMANTIC | Report findings/analysis are distinguished from unsupported opinion. | Strengthen evidence. |

| CW-033 | CONDITIONAL | WARNING | FINAL | No | SEMANTIC | Report recommendations arise from findings/analysis. | Align recommendations. |

| CW-034 | QUALITY | WARNING | PLAN,FINAL | No | SEMANTIC | Literature reviews synthesize thematically/methodologically/conceptually rather than list studies. | Restructure synthesis. |

| CW-035 | QUALITY | WARNING | FINAL | No | SEMANTIC | Literature reviews compare agreement, contradiction, methodological variation, and limitations within themes where relevant. | Deepen synthesis. |

| CW-036 | QUALITY | WARNING | FINAL | No | SEMANTIC | Literature reviews identify evidence gaps only where supported. | Add/repair gap. |

| CW-037 | CONDITIONAL | WARNING | PLAN,FINAL | Yes | HYBRID | Postgraduate literature reviews include a brief search/selection approach when review methodology is expected. | Add search approach. |

| CW-038 | REQUIRED | BLOCKING | PLAN | No | HYBRID | Case study mode resolves to analytical, problem-oriented, or external format. | Resolve case mode. |

| CW-039 | QUALITY | WARNING | FINAL | No | SEMANTIC | Analytical case studies use an explicit analytical framework/model where appropriate. | Add framework. |

| CW-040 | QUALITY | WARNING | FINAL | No | SEMANTIC | Problem-oriented case studies diagnose before recommending. | Add diagnosis. |

| CW-041 | QUALITY | WARNING | FINAL | No | SEMANTIC | Problem-oriented case studies compare feasible alternatives when warranted. | Add options analysis. |

| CW-042 | CONDITIONAL | WARNING | PLAN,FINAL | No | HYBRID | Empirical short research papers include a method section. | Add methods. |

| CW-043 | QUALITY | WARNING | FINAL | No | SEMANTIC | Non-empirical short research papers use an appropriate analytical approach instead of an artificial method section. | Replace/remove methods. |

| CW-044 | REQUIRED | BLOCKING | INTAKE,PLAN | No | HYBRID | Reflective assignments requiring personal experience may not invent user experience. | Request context. |

| CW-045 | QUALITY | WARNING | FINAL | No | SEMANTIC | Reflective writing connects experience to learning, theory/evidence, or future action as required. | Deepen reflection. |

| CW-046 | REQUIRED | BLOCKING | INTAKE,PLAN | No | HYBRID | Explicit institution/assignment AI-use policy is extracted and applied. | Apply policy. |

| CW-047 | REQUIRED | BLOCKING | PLAN | No | DETERMINISTIC | Explicit generative-AI prohibition disables full-drafting mode. | Switch to support mode. |

| CW-048 | CONDITIONAL | INFO | FINAL | Yes | DETERMINISTIC | If AI is permitted with disclosure, PaperAid may generate a disclosure statement when requested. | Generate disclosure. |

| CW-049 | REQUIRED | BLOCKING | PLAN | No | HYBRID | If brief restricts sources to supplied readings, PaperAid must not add external literature unless permitted. | Use closed source set. |

| CW-050 | CONDITIONAL | WARNING | PLAN,FINAL | Yes | HYBRID | Independent research is performed when the task expects it and source restrictions allow it. | Run research. |

| CW-051 | QUALITY | WARNING | FINAL | No | HYBRID | Required course readings are incorporated where the brief/rubric expects them. | Add required readings. |

| CW-052 | REQUIRED | BLOCKING | FINAL | No | DETERMINISTIC | PaperAid-added references are bibliographically verified. | Verify/replace. |

| CW-053 | REQUIRED | BLOCKING | FINAL | No | HYBRID | A cited source supports the claim for which it is used. | Replace/qualify citation. |

| CW-054 | QUALITY | WARNING | FINAL | No | HYBRID | Source sufficiency is judged by coverage/quality, not fixed references per 1,000 words. | Improve evidence coverage. |

| CW-055 | CONDITIONAL | WARNING | FINAL | Yes | DETERMINISTIC | When no source count is specified, any suggested count is clearly non-binding guidance. | Label guidance. |

| CW-056 | REQUIRED | BLOCKING | FINAL | No | DETERMINISTIC | Required citation style is followed consistently. | Repair citations. |

| CW-057 | REQUIRED | BLOCKING | FINAL | No | DETERMINISTIC | Required in-text citations correspond to reference entries. | Repair mapping. |

| CW-058 | QUALITY | WARNING | FINAL | No | SEMANTIC | Body remains focused on the task instead of drifting into generally relevant but unasked material. | Remove drift. |

| CW-059 | QUALITY | WARNING | FINAL | No | SEMANTIC | Major claims are proportionate to evidence and avoid unsupported certainty. | Qualify claims. |

| CW-060 | QUALITY | WARNING | FINAL | No | SEMANTIC | Counter-evidence or alternative perspectives are considered when required by critical/evaluative directives. | Add counter-position. |

| CW-061 | QUALITY | WARNING | FINAL | No | SEMANTIC | Critical/evaluative coursework acknowledges material limitations where relevant. | Add limitations. |

| CW-062 | QUALITY | WARNING | FINAL | No | SEMANTIC | Transitions support logical progression without repetitive formulaic phrasing. | Improve flow. |

| CW-063 | QUALITY | WARNING | FINAL | No | HYBRID | Most substantive paragraphs in a critically evaluative essay should be analytical/evaluative rather than purely descriptive. | Target weak paragraphs. |

| CW-064 | QUALITY | INFO | FINAL | No | HYBRID | Paragraph criticality labels are internal quality signals, not official grades. | Do not expose as grade. |

| CW-065 | REQUIRED | BLOCKING | FINAL | No | DETERMINISTIC | All required sections/components specified by the brief are present. | Add missing component. |

| CW-066 | REQUIRED | BLOCKING | FINAL,RENDER | No | DETERMINISTIC | Final coursework complies with hard length and formatting requirements after rendering. | Compress/reformat. |

| CW-067 | QUALITY | WARNING | FINAL | No | SEMANTIC | Title/headings accurately reflect content and required structure. | Repair headings. |

| CW-068 | CONDITIONAL | WARNING | FINAL | No | SEMANTIC | Report executive summary summarizes purpose, approach, principal analysis/findings, and recommendations without duplicating introduction. | Rewrite summary. |

| CW-069 | QUALITY | WARNING | FINAL | No | SEMANTIC | Short research papers distinguish evidence/findings from interpretation where applicable. | Clarify results/discussion. |

| CW-070 | QUALITY | WARNING | FINAL | No | SEMANTIC | Literature-review gaps arise from reviewed evidence rather than being invented. | Repair gap claim. |

| CW-071 | REQUIRED | BLOCKING | FINAL | No | DETERMINISTIC | Student-supplied quotations, figures, and required readings are not silently altered. | Restore/flag. |

| CW-072 | QUALITY | WARNING | FINAL | No | SEMANTIC | Final answer makes its central position/judgment explicit when the directive requires one. | Strengthen thesis/judgment. |

| CW-073 | REQUIRED | BLOCKING | FINAL | No | DETERMINISTIC | PaperAid-generated coursework never runs a detector-evasion or make-undetectable stage. | Use Academic Quality & Integrity Review. |

| CW-074 | QUALITY | INFO | FINAL | No | HYBRID | PaperAid rubric/readiness feedback is not presented as an official lecturer grade prediction. | Label as PaperAid assessment. |

| CW-075 | REQUIRED | BLOCKING | FINAL | No | DETERMINISTIC | All blocking coursework rules pass before READY status. | Repair blocking failures. |

# 14. Validator catalog

Validators live in application code and are referenced by rule IDs.

## 14.1 Shared deterministic validators

| Validator ID | Purpose |

|---|---|

| limits.word_count | Count scoped words. |

| limits.character_count | Count characters with/without spaces. |

| limits.rendered_pages | Count actual pages after rendering. |

| limits.field_count | Validate per-field limits. |

| structure.required_sections | Check required headings/fields. |

| structure.order | Check mandatory order. |

| structure.template_match | Check template heading/field map. |

| references.exists | Verify DOI/title/author/year metadata. |

| references.intext_mapping | Check in-text citation ↔ reference list. |

| references.retraction | Check retraction/correction metadata where available. |

| numbers.consistency | Cross-document numeric consistency. |

| dates.duration | Start/end/duration consistency. |

| eligibility.thresholds | Evaluate eligibility thresholds. |

| requirements.conflict | Detect unresolved high-authority conflicts. |

## 14.2 Funding deterministic validators

| Validator ID | Purpose |

|---|---|

| results.activity_output_link | Every activity maps to an output. |

| results.output_outcome_link | Every output maps to an outcome. |

| results.outcome_indicator_link | Every required outcome has an indicator. |

| results.indicator_fields | Unit/baseline/target/source/frequency/owner completeness. |

| budget.line_math | Unit cost × quantity. |

| budget.subtotals | Category/year totals. |

| budget.ceiling | Funding ceiling. |

| budget.cost_share | Cost-share rate/base. |

| budget.indirect_cost | Indirect rate/base. |

| budget.currency | Currency/exchange consistency. |

| budget.prohibited_costs | Detect prohibited costs. |

| budget.activity_mapping | Budget ↔ activity mapping. |

| staff.effort_consistency | Narrative/workplan/budget LOE. |

| timeline.activity_coverage | Every major activity scheduled. |

| logframe.model_consistency | Rendered logframe ↔ Results Model. |

## 14.3 Coursework deterministic validators

| Validator ID | Purpose |

|---|---|

| coursework.subquestion_coverage | Every explicit task component planned/answered. |

| coursework.word_tolerance | Apply only configured tolerance. |

| coursework.required_readings | Required readings used. |

| coursework.source_restriction | Closed source-set compliance. |

| coursework.ai_policy | Apply explicit AI restrictions. |

| coursework.citation_style | Citation/reference formatting. |

## 14.4 Semantic validators

| Validator ID | Purpose |

|---|---|

| semantic.problem_quality | Problem specificity/coherence. |

| semantic.objective_alignment | Problem ↔ objectives. |

| semantic.logic_plausibility | Results-chain plausibility. |

| semantic.output_vs_outcome | Classify results statements. |

| semantic.indicator_validity | Indicator measures intended result. |

| semantic.funder_relevance | Addresses call priorities. |

| semantic.capacity_specificity | Capacity claims are concrete. |

| semantic.risk_quality | Risk/mitigation quality. |

| semantic.sustainability | Sustainability specificity. |

| semantic.directive_fulfillment | Coursework fulfills command word. |

| semantic.criticality | Description vs analysis/evaluation. |

| semantic.synthesis | Literature synthesis quality. |

| semantic.rubric_criterion | Criterion-level quality. |

| semantic.claim_support | Claim-source entailment. |

## 14.5 Hybrid-validator pattern

A hybrid validator should normally:
1. extract deterministic evidence;
2. ask an LLM to interpret/classify only what requires judgment;
3. return structured output;
4. enforce the resulting rule in code.

Example: output vs outcome classification.

# 15. Remediation engine

Every issue has a rule, scope, severity, and remediation path.

```json
{
  "issue_id": "iss_123",
  "rule_id": "FP-022",
  "scope": ["outcome_O2"],
  "severity": "BLOCKING",
  "message": "Outcome O2 has no indicator.",
  "remediation_id": "results.create_missing_indicator",
  "auto_fix_safe": false,
  "requires_user_input": false
}
```

## 15.1 Remediation classes

```text
AUTO_SAFE
TARGETED_GENERATIVE
USER_DECISION
EXTERNAL_RESEARCH
MANUAL_ONLY
```

Examples:
- arithmetic correction → AUTO_SAFE;
- compress paragraph to hard limit → TARGETED_GENERATIVE;
- change project objective → USER_DECISION;
- unverified statistic → EXTERNAL_RESEARCH;
- unresolved donor eligibility conflict → MANUAL_ONLY/USER_DECISION.

# 16. Scoring-aware planning

When scoring criteria are published, store them structurally:

```json
[
  {"criterion":"Relevance","weight":30},
  {"criterion":"Technical approach","weight":25},
  {"criterion":"MEL","weight":20},
  {"criterion":"Capacity","weight":15},
  {"criterion":"Sustainability","weight":10}
]
```

Planning algorithm:

```pseudo
base_plan = document_type_default
map each criterion -> relevant sections
increase minimum depth for higher-weight criteria
normalize within hard word budget
preserve mandatory minimum coverage for every required section
do not enforce weight == word percentage
```

For coursework rubrics, use the same principle.

# 17. Formatting and rendering profiles

A render profile should contain:

```json
{
  "font_family": "Times New Roman",
  "font_size_pt": 12,
  "line_spacing": 1.0,
  "margins": {
    "top_in": 1,
    "bottom_in": 1,
    "left_in": 1,
    "right_in": 1
  },
  "paper_size": "Letter",
  "heading_rules": {},
  "table_rules": {}
}
```

Rendered compliance must use the same profile as final export.

Do not render with generic defaults, declare compliance, then export with different formatting.

# 18. Form / portal submission mode

Some funders use online fields rather than a single narrative.

Each field supports:

```text
field_id
label
required
max_words
max_characters
includes_spaces
allowed_format
dependencies
```

Example:

```json
{
  "field_id": "project_summary",
  "label": "Project Summary",
  "required": true,
  "max_characters": 2000,
  "includes_spaces": true
}
```

PaperAid still presents a coherent workspace but preserves field boundaries for copy/export.

# 19. User-adjustable versus locked values

## 19.1 User-adjustable when no stronger rule exists
- default word target;
- suggested funding mode;
- section emphasis;
- non-mandatory section inclusion;
- non-mandatory section names;
- formatting when unspecified;
- optional annexes;
- non-binding source-count recommendation.

## 19.2 Adjustable only within hard limits
- section word allocations;
- total target under an external maximum;
- number of objectives where no external rule fixes it.

## 19.3 Never adjustable against a mandatory external rule
- hard length cap;
- character cap;
- field cap;
- eligibility;
- deadline;
- funding ceiling;
- cost share;
- prohibited cost;
- mandatory section;
- required citation style;
- explicit AI-use restriction.

# 20. Reference and claim data structures

## 20.1 Reference

```json
{
  "reference_id": "ref_001",
  "raw_text": "",
  "title": "",
  "authors": [],
  "year": null,
  "doi": null,
  "source_database": null,
  "bibliographic_status": "VERIFIED",
  "retraction_status": "CLEAR",
  "user_supplied": false
}
```

## 20.2 Claim

```json
{
  "claim_id": "claim_001",
  "text": "",
  "block_id": "",
  "claim_type": "quantitative",
  "references": ["ref_001"],
  "support_status": "SUPPORTED",
  "support_locator": "",
  "limitations": []
}
```

# 21. Readiness status model

```text
DRAFT
NEEDS_REVIEW
COMPLIANT_WITH_WARNINGS
READY
```

### DRAFT
Generation still in progress.

### NEEDS_REVIEW
At least one blocking rule failed or an external conflict remains.

### COMPLIANT_WITH_WARNINGS
No blocking rule fails, but warnings remain.

### READY
No blocking issue remains and the service-specific release gate is satisfied.

Never call this:
- officially approved;
- guaranteed fundable;
- guaranteed A-grade;
- guaranteed supervisor acceptance.

# 22. UI contract

The rule engine must not create a complicated front end.

## 22.1 Concept Note

```text
Concept Note
  ↓
Research / Project / Funding
  ↓
Enter idea or upload requirements
  ↓
PaperAid creates plan
  ↓
Adjust
  ↓
Draft
```

Plan screen shows only:
- target words;
- estimated rendered pages;
- mandatory locked sections;
- adjustable sections;
- unresolved questions.

## 22.2 Funding Proposal

```text
Upload call / describe opportunity
  ↓
PaperAid reads requirements
  ↓
Eligibility + compliance summary
  ↓
Recommended mode
  ↓
Proposal plan
  ↓
Adjust
  ↓
Draft
```

Show:
- funding ceiling;
- duration;
- hard narrative limit;
- mandatory sections;
- required annexes;
- scoring criteria;
- eligibility status.

Do not expose rule IDs.

## 22.3 Coursework

```text
Upload assignment / paste question
  ↓
PaperAid understood:
- task
- type
- word limit
- referencing
- important requirements
  ↓
Plan
  ↓
Adjust
  ↓
Draft
```

# 23. Model interaction contract

Models receive a compact resolved spec, not the whole rule library.

Example coursework payload:

```json
{
  "document_type": "coursework",
  "variant": "essay",
  "target_words": 2500,
  "directives": ["critically_evaluate"],
  "required_topics": ["digital health", "Uganda", "limitations"],
  "citation_style": "APA7",
  "source_policy": "independent_research",
  "hard_constraints": [],
  "quality_targets": []
}
```

Models do **not** decide:
- whether a hard page limit exists;
- whether budget arithmetic is correct;
- whether a required heading exists;
- whether the donor ceiling is exceeded.

Those are code responsibilities.

# 24. Recommended rule-storage architecture

```text
/rules
  /shared
    base.json
    evidence.json
    references.json
    limits.json
    formatting.json

  /concept-note
    base.json
    research-concept.json
    project-concept.json
    funding-concept.json

  /funding-proposal
    base.json
    ngo-project.json
    research-grant.json

  /coursework
    base.json
    essay.json
    academic-report.json
    case-study.json
    literature-review.json
    short-research-paper.json
    reflective.json

  /profiles
    /donors
    /institutions
```

Do not create one file per rule.

Job-extracted requirements are stored as job data, not permanent rule files.

# 25. Suggested persistence entities

```text
rulebooks
rulebook_versions
profiles
jobs
job_requirement_sets
job_conflicts
documents
document_versions
evidence_packs
references
claims
results_models
coursework_plans
compliance_reports
```

A funding-proposal job persists the Results Model separately from the generated narrative.

# 26. Orchestration pseudocode

## 26.1 Concept Note

```pseudo
create_job(CONCEPT_NOTE)
resolve_variant()
extract_external_requirements_if_any()
resolve_spec()
run_pre_draft_gate()
build_plan()
user_approves_or_edits_plan()
research_if_needed()
draft()
run_deterministic_validators()
run_semantic_validators()
repair_targeted_failures()
render()
validate_limits()
finalize()
```

## 26.2 Funding Proposal

```pseudo
create_job(FUNDING_PROPOSAL)
parse_call_and_template()
extract_requirements_with_quotes()
evaluate_eligibility()
resolve_conflicts()
resolve_spec()
recommend_complexity_mode()
build_results_model()
build_scoring_aware_plan()
user_approves_plan()
research()
draft_sections()
render_logframe_workplan_mel_from_results_model()
build_budget_and_validate()
run_reference_and_claim_checks()
run_semantic_audit()
repair_targeted_failures()
render_final_package()
validate_page_word_character_field_constraints()
finalize()
```

## 26.3 Coursework

```pseudo
create_job(COURSEWORK)
parse_brief()
parse_question()
parse_rubric()
resolve_ai_policy()
resolve_source_policy()
resolve_type()
resolve_length()
build_plan()
user_approves_plan()
research_if_permitted_and_needed()
draft()
validate_task_coverage()
validate_rubric()
validate_references()
run_academic_quality_integrity_review()
repair_targeted_failures()
format_render()
finalize()
```

# 27. Post-draft compliance matrix

## 27.1 Blocking failures

### Shared
- hard limit exceeded;
- mandatory external section missing;
- unresolved mandatory conflict;
- non-existent PaperAid-added reference;
- contradicted/not-supported claim presented as fact;
- broken required citation/reference mapping.

### Funding
- budget over ceiling;
- arithmetic error;
- failed required cost share;
- prohibited cost;
- required outcome indicator missing;
- proposal/logframe/budget figures inconsistent.

### Coursework
- unanswered explicit sub-question;
- explicit source restriction violated;
- explicit AI prohibition violated;
- required brief component missing.

## 27.2 Warnings
- weak evidence;
- stale evidence;
- weak analysis;
- descriptive paragraphs in evaluative tasks;
- vague capacity claims;
- risks with weak mitigation;
- missing sustainability where relevant;
- heuristic proportion imbalance.

Warnings become blocking only when an external rule or service-specific rule says so.

# 28. Golden regression tests

## 28.1 Concept Note
1. No external guidance → Standard funding concept.
2. Hard 2-page concept call.
3. 5-page externally templated concept.
4. Character-limited portal.
5. Missing target group.
6. Failed eligibility.
7. Unverified PaperAid-added reference.
8. Indicative budget above ceiling.
9. Research concept with objectives/method mismatch.
10. Project concept missing decision requested.

## 28.2 Funding Proposal
1. Standard proposal without donor template.
2. 10-page single-spaced call.
3. 20-page double-spaced call.
4. Form application with field limits.
5. Donor call with scoring criteria.
6. Cost-share requirement.
7. Indirect-cost base differing from total direct costs.
8. Prohibited-cost line.
9. Activity without budget line.
10. Outcome without indicator.
11. Inconsistent beneficiary counts.
12. Logframe contradicting narrative.
13. Multi-country consortium.
14. Research grant using scheme-specific headings.
15. Donor cross-cutting overlay requirement.
16. Staff LOE mismatch.
17. Different currency without exchange-rate metadata.
18. Summary introducing an unapproved commitment.

## 28.3 Coursework
1. “Describe...” essay.
2. “Critically evaluate...” essay.
3. Compound directive.
4. Report with mandatory headings.
5. Literature review with author-by-author summary.
6. Analytical case study.
7. Problem-oriented case study.
8. Reflective assignment with missing personal context.
9. Explicit “no generative AI” policy.
10. Closed source pack.
11. Missing word limit.
12. Rubric-weighted assignment.
13. Compare task that only states similarities.
14. Conclusion introducing major new evidence.
15. Citation-style mismatch.
16. Required course reading omitted.
17. Empirical research paper with no methods.
18. Non-empirical paper with artificial methodology section.

# 29. Production acceptance criteria

## Shared
- precedence works consistently;
- conflicts are surfaced;
- external requirements retain quote/location/confidence;
- pages are validated after rendering;
- requirement-set versions persist;
- warnings and blocking failures are distinguishable.

## Concept Note
- all three variants function;
- Brief/Standard/Extended modes function;
- funding fit and applicant fit are separately assessable;
- form mode works;
- external template overrides baseline cleanly.

## Funding Proposal
- complexity recommendation works;
- Results Model persists independently;
- logframe/workplan/MEL can render from Results Model;
- budget checks are deterministic;
- scoring criteria influence plan;
- external page/field limits are validated correctly;
- research-grant variant does not inherit inappropriate NGO headings.

## Coursework
- command-word parser works;
- compound questions create multiple coverage requirements;
- rubric converts to active quality rules;
- explicit AI policy is enforced;
- source restrictions are enforced;
- criticality validator does not penalize descriptive tasks;
- reflective mode does not invent experiences.

# 30. Recommended IDE implementation sequence

## Phase 1 — Rule-engine foundation
Build:
- schema;
- authority precedence;
- conflict resolution;
- active-rule resolution;
- compliance-report model.

## Phase 2 — Requirement extraction
Build:
- quote/location/confidence extraction;
- typed hard constraints;
- low-confidence confirmation;
- form/field extraction.

## Phase 3 — Concept Note
Build:
- variants;
- modes;
- plan templates;
- validators;
- rendered limits.

## Phase 4 — Coursework
Build:
- brief parser;
- directive parser;
- rubric parser;
- document-type templates;
- AI-policy handling;
- source restrictions;
- validators.

## Phase 5 — Funding Proposal
Build:
- compliance extractor;
- complexity recommendation;
- Results Model;
- results validators;
- scoring-aware planner;
- budget engine;
- MEL/logframe/workplan rendering.

## Phase 6 — Research/reference integration
Reuse shared:
- Crossref;
- PubMed;
- OpenAlex;
- official web retrieval;
- claim entailment;
- retraction checks.

## Phase 7 — Render compliance
Build:
- render profiles;
- actual page counting;
- field-limit checks;
- targeted compression.

## Phase 8 — Golden tests/hardening
Run permanent regression suite before production activation.

# 31. Source/provenance note for implementers

This specification synthesizes the existing PaperAid design and the independent rulebook review dated 28 September 2026.

The independent review drew on examples from current/recent official or institutional guidance including:
- U.S. State Department DRL and ECA proposal instructions;
- European Commission / EU external-action application templates;
- Enabel concept-note/application templates;
- UNHCR concept-note guidance;
- UNDEF application systems;
- UNDP small-grant calls;
- NIH grant page-limit guidance;
- Horizon Europe guidance;
- OECD-DAC results terminology;
- university academic-writing guidance from Newcastle, Hull, Federation University, Canterbury, Wolverhampton, Bangor, Sheffield Hallam, and others.

### Important implementation rule

Donor and institution profiles are **dated hints**, not permanent authorities. Every live job must prefer the actual current call, template, addendum, assignment brief, rubric, or institution instruction governing that job.

Do not hard-code temporary agency arrangements or historical guidance as eternally current.

# 32. Final IDE directives

Treat this document as the implementation contract.

1. Do not replace the rule system with giant prompts.
2. Do not duplicate rule logic in UI and backend.
3. Do not put validator code inside rule JSON.
4. Do not create a microservice per document type.
5. Do not expose rule-engine complexity to ordinary users.
6. Do not hard-code donor requirements globally.
7. Do not use page count as the primary internal planning unit.
8. Do not let LLMs perform arithmetic that deterministic code can do exactly.
9. Do not let model memory decide current donor compliance.
10. Do not fabricate references or metadata.
11. Do not silently alter user facts or figures.
12. Do not regenerate whole documents for local failures.
13. Persist the resolved job specification.
14. Persist the Results Model for funding proposals.
15. Persist provenance for extracted requirements.
16. Keep every service plan-first and easy to use.
17. Add a regression test for every discovered failure mode.
18. Preserve the existing PaperAid model-routing architecture; this specification defines rule behavior, not a new provider chain.
19. Before a disruptive refactor, inspect the existing codebase and explain why the change is necessary.
20. Prefer concise maintainable code over architecture theatre.

# 33. Compact implementation reference

```text
CONCEPT NOTE
- Research / Project / Funding
- Brief 900 words
- Standard 1,800 words
- Extended 2,900 words
- External rule always wins
- Need + fit + applicant + approach
- Plan first
- Verify references
- Render limits

FUNDING PROPOSAL
- Compact 2,500 words
- Standard 5,500 words
- Comprehensive 10,000 words
- Complexity-based recommendation
- External call overrides
- Single Results Model
- Deterministic budget
- MEL/logframe/workplan from Results Model
- Scoring-aware planning
- Form mode
- Render compliance

COURSEWORK
- Essay / Report / Case Study / Literature Review / Short Research Paper / Reflective
- Brief overrides defaults
- Parse directive + subject + limits + subquestions
- Level fallback: 1,500 / 2,000 / 3,000 words
- Rubric becomes active rules
- Closed-source restrictions respected
- Explicit no-AI policy disables full drafting
- No detector-evasion stage
- Verify references
- Validate every part of the question
```

**End of PaperAid Final Implementation-Grade Rulebook Specification v1.0**

---

# Appendix A. Extended implementation schemas

## A1. Concept Note plan schema

```json
{
  "plan_id": "cnplan_001",
  "job_id": "job_001",
  "variant": "funding_concept",
  "mode": "standard",
  "target_words": 1800,
  "hard_limits": [],
  "sections": [
    {
      "section_id": "cn_problem",
      "label": "Problem and Evidence of Need",
      "required": true,
      "locked": false,
      "target_words": 400,
      "min_words": 300,
      "max_words": 500,
      "criteria": [
        "problem specificity",
        "evidence of magnitude",
        "population/geography",
        "consequence"
      ],
      "mapped_scoring_criteria": []
    }
  ],
  "total_planned_words": 1800,
  "user_approved": false,
  "spec_version": 1
}
```

The plan is not the final text. It is the contract between intake and generation.

The plan editor may permit the user to:
- increase/decrease section word allocation within hard limits;
- rename non-mandatory headings;
- add a non-mandatory section;
- remove a PaperAid-default section if its logic is preserved elsewhere;
- change emphasis;
- approve the plan.

The plan editor may not permit removal of externally mandatory headings or fields.

## A2. Funding Results Model — extended schema

```json
{
  "results_model_id": "rm_001",
  "job_id": "job_001",
  "version": 3,
  "goal": {
    "id": "G1",
    "statement": "",
    "source": "user_and_plan"
  },
  "objectives": [
    {
      "id": "OBJ1",
      "statement": "",
      "outcome_ids": ["O1"]
    }
  ],
  "outcomes": [
    {
      "id": "O1",
      "statement": "",
      "objective_id": "OBJ1",
      "indicator_ids": ["I1"],
      "assumptions": [],
      "risk_ids": ["R1"]
    }
  ],
  "outputs": [
    {
      "id": "OP1",
      "statement": "",
      "outcome_id": "O1",
      "indicator_ids": ["I2"]
    }
  ],
  "activities": [
    {
      "id": "A1",
      "statement": "",
      "output_id": "OP1",
      "owner_role": "Programme Manager",
      "start_month": 1,
      "end_month": 3,
      "budget_line_ids": ["B1","B2"],
      "dependencies": []
    }
  ],
  "indicators": [
    {
      "id": "I1",
      "result_id": "O1",
      "result_level": "outcome",
      "definition": "",
      "unit": "percent",
      "baseline": 34,
      "baseline_year": 2026,
      "baseline_plan": null,
      "target": 60,
      "target_date": "2028-06",
      "disaggregation": ["sex","district"],
      "means_of_verification": "routine programme database",
      "frequency": "quarterly",
      "responsible_role": "MEL Officer"
    }
  ],
  "risks": [
    {
      "id": "R1",
      "statement": "",
      "likelihood": "medium",
      "impact": "high",
      "mitigation": "",
      "owner_role": "Project Director"
    }
  ],
  "budget_lines": [
    {
      "id": "B1",
      "category": "training",
      "description": "",
      "quantity": 4,
      "unit_cost": 1000,
      "currency": "USD",
      "total": 4000,
      "activity_ids": ["A1"],
      "year": 1
    }
  ],
  "milestones": [],
  "assumptions": [],
  "locked_fields": []
}
```

### A2.1 Lock behavior

Once the user approves a goal, objective, requested amount, duration, target population, or other critical proposal decision, PaperAid may mark it `locked`.

A later edit that affects a locked field must either:
1. be explicitly approved by the user; or
2. come from a higher-authority external requirement.

If a locked field changes, the dependency engine marks downstream artifacts stale.

Example:

```text
Outcome O1 changed
  ↓
Indicator I1 → NEEDS_REVIEW
Output OP1 → NEEDS_REVIEW
MEL table → STALE
Logframe → STALE
Narrative sections referencing O1 → NEEDS_REVIEW
```

Do not leave old generated artifacts silently inconsistent with the new model.

## A3. Coursework plan schema

```json
{
  "plan_id": "cwplan_001",
  "job_id": "job_001",
  "level": "postgraduate",
  "type": "essay",
  "target_words": 2500,
  "directive": ["critically_evaluate"],
  "subject_terms": ["digital health"],
  "limits": {
    "geography": ["Uganda"],
    "time": ["2015-present"]
  },
  "subquestions": [],
  "citation_style": "APA7",
  "source_policy": "independent_research",
  "required_readings": [],
  "sections": [
    {
      "id": "intro",
      "label": "Introduction",
      "target_words": 250,
      "required": true
    },
    {
      "id": "theme_1",
      "label": "Theme 1",
      "target_words": 600,
      "required": true,
      "rubric_criteria": ["critical_analysis"]
    }
  ],
  "rubric_rules": [],
  "ai_use_policy": "unknown",
  "user_approved": false
}
```

## A4. Compliance report schema

```json
{
  "compliance_report_id": "cr_001",
  "job_id": "job_001",
  "spec_version": 3,
  "status": "COMPLIANT_WITH_WARNINGS",
  "summary": {
    "blocking_failures": 0,
    "warnings": 3,
    "info": 5
  },
  "checks": [
    {
      "rule_id": "FP-041",
      "status": "PASS",
      "message": "Requested amount is within the funding ceiling.",
      "evidence": {
        "requested": 480000,
        "ceiling": 500000,
        "currency": "USD"
      }
    }
  ],
  "unresolved_conflicts": [],
  "assumptions": [],
  "generated_at": "..."
}
```

The user-facing compliance view should translate this into plain language rather than displaying raw IDs.

---

# Appendix B. Exact requirement-resolution examples

## B1. Coursework brief with several overlapping constraints

Source A — assignment brief:
- 2,500 words;
- APA 7;
- at least 12 peer-reviewed references;
- critically evaluate;
- no appendices.

Source B — general programme handbook:
- assignments normally use Harvard style.

Resolution:

```text
word target      = 2,500 from assignment brief
citation style   = APA 7 from assignment brief
source minimum   = 12 peer-reviewed from assignment brief
directive        = critically evaluate
appendices       = prohibited
Harvard default  = overridden
```

Reason: the assignment-specific brief is more specific to the job than the generic handbook.

## B2. Funding call where narrative and summary have separate caps

Call:
- Executive Summary: maximum 1 page.
- Proposal Narrative: maximum 10 pages.
- Detailed budget: excluded from narrative limit.

Resolved constraints:

```json
[
  {
    "type":"PAGE_LIMIT",
    "scope":["executive_summary"],
    "max":1
  },
  {
    "type":"PAGE_LIMIT",
    "scope":["core_narrative"],
    "max":10
  },
  {
    "type":"PAGE_LIMIT",
    "scope":["detailed_budget"],
    "counts_toward_parent_limit":false
  }
]
```

PaperAid must not add the executive-summary page to the 10-page narrative unless the call says it counts.

## B3. Funding portal with field limits

Call portal:
- Summary: 2,000 characters including spaces.
- Need: 5,000 characters.
- Approach: 8,000 characters.
- Sustainability: 2,500 characters.

PaperAid should not generate a 5,500-word narrative and then cut it apart. It should plan directly at field level.

## B4. Concept note where scoring weights dominate structure

Scoring:
- Relevance 40%;
- feasibility 20%;
- approach 20%;
- applicant capacity 20%.

PaperAid should increase depth on relevance and ensure it is directly answered. It should not literally allocate exactly 40% of words to relevance if that produces an awkward document.

---

# Appendix C. Detailed pre-draft gate tables

## C1. Funding Concept Note gate

| Check | Status if missing | Notes |
|---|---|---|
| Variant resolved | BLOCK | Cannot choose correct rulebook otherwise |
| Call/template parsed when supplied | BLOCK if mandatory info unresolved | Do not draft blindly |
| Eligibility | BLOCK if clearly failed for submission mode | Exploratory draft may still be allowed if user requests |
| Problem/opportunity | BLOCK | Core concept absent |
| Proposed intervention | BLOCK | Core concept absent |
| Target group | ASK_ONCE | May be inferred only if evidence is strong |
| Geography | ASK_ONCE | May be global if genuinely applicable |
| Applicant capability | ASK_ONCE | Needed for serious funding concept |
| Duration | ASK_ONCE | Use assumption only if external call does not mandate it |
| Budget envelope | ASK_ONCE | Needed if financial feasibility matters |
| Scoring criteria | PASS/parse if present | Used for planning |

## C2. Funding Proposal gate

| Check | Status | Action |
|---|---|---|
| Call/template status | BLOCK if supplied but unreadable | Re-upload / manual entry |
| Eligibility | BLOCK on clear fail | Mark not submission-ready |
| Funding ceiling | BLOCK if conflicting/unknown in mandatory call | Resolve source |
| Duration | ASK_ONCE unless mandatory | Record assumption |
| Target population | ASK_ONCE | Needed for technical logic |
| Geography | ASK_ONCE | Needed for evidence/relevance |
| Intervention idea | BLOCK | No proposal without it |
| Applicant legal entity | ASK_ONCE when eligibility depends on it | Resolve before READY |
| Partners | ASK_ONCE when call/consortium context suggests them | May be none |
| Hard limits | BLOCK if unresolved | Cannot plan correctly |
| Required annexes | Parse | Add checklist |
| Scoring criteria | Parse | Influence plan |

## C3. Coursework gate

| Check | Status | Action |
|---|---|---|
| Assignment question | BLOCK | Request question/brief |
| Directive word | BLOCK if question cannot be interpreted | Clarify task |
| Subquestions | BLOCK if unresolved | Must cover all parts |
| Word/page limit | ASK_ONCE | Level fallback only after skip |
| Academic level | ASK_ONCE | Needed for fallback only |
| Citation style | ASK_ONCE when not stated | User selects or accepts default |
| Rubric | Parse when supplied | Not required if none exists |
| Required readings | ASK_ONCE if brief refers to missing readings | Avoid fabricating course material |
| Source restriction | BLOCK if conflicting with requested research | Apply closed-source mode |
| AI-use policy | Apply if present | May disable full drafting |

---

# Appendix D. Detailed post-draft validator outcomes

## D1. PASS

A rule was checked and satisfied.

## D2. FAIL_BLOCKING

The rule must be repaired before READY.

Examples:
- proposal is 11 pages under a 10-page hard limit;
- budget exceeds ceiling;
- coursework omits one of two explicit questions;
- PaperAid-added citation does not exist;
- required donor field is missing.

## D3. WARN

The document can technically be exported but quality or compliance risk remains.

Examples:
- sustainability is generic;
- literature review is overly descriptive;
- organizational capacity is asserted without examples;
- evidence is old but not invalid.

## D4. INFO

Transparency message, such as:
- PaperAid used its standard 1,800-word Concept Note fallback because no length was provided;
- user declined to provide an institutional AI policy;
- no external source count was specified.

---

# Appendix E. Funding budget validation detail

The budget validator should treat money as structured numeric data, never free-text arithmetic.

## E1. Line item

```json
{
  "line_id":"B12",
  "category":"Personnel",
  "description":"MEL Officer",
  "quantity":12,
  "unit":"month",
  "unit_cost":1800,
  "currency":"USD",
  "computed_total":21600,
  "entered_total":21600,
  "year":1,
  "activity_ids":["A4","A7"],
  "allowable":true
}
```

## E2. Arithmetic rules

- recompute line totals from numeric fields;
- sum categories from lines;
- sum years from categories/lines;
- compare computed total with entered request;
- round only according to configured currency rules;
- never allow prose generation to overwrite numeric truth.

## E3. Cost-share rules

Store:

```text
required_rate
calculation_base: total_project_cost | donor_request | other
required_amount
provided_amount
```

Do not assume cost share is calculated from the donor request.

## E4. Indirect-cost rules

Store:

```text
rate
base_definition
excluded_categories
cap
source_provenance
```

Do not implement a single global indirect-cost formula.

## E5. Narrative consistency

If narrative states:
> “The project requests USD 500,000 over 24 months”

but budget totals USD 498,750 or timeline is 18 months, block READY until reconciled.

---

# Appendix F. Funding results-model validation detail

## F1. Structural graph rules

```text
Goal
  ↑
Outcomes
  ↑
Outputs
  ↑
Activities
```

Every node must be connected unless external donor logic explicitly permits otherwise.

## F2. Orphan rules

Block or warn as configured when:
- activity has no output;
- output has no outcome;
- outcome has no objective/goal relationship;
- indicator measures no result;
- budget line maps nowhere;
- timeline task maps to no activity.

## F3. Result wording classifier

Semantic classifier returns:

```json
{
  "statement":"Train 200 community health workers",
  "predicted_type":"activity",
  "confidence":0.97,
  "current_type":"outcome"
}
```

Code creates a quality failure and requests targeted repair; the classifier itself does not directly mutate the proposal.

## F4. Indicator plausibility

The semantic auditor checks:
- indicator actually measures the stated result;
- unit makes sense;
- numerator/denominator logic is coherent where applicable;
- target is not obviously impossible relative to duration/resources;
- indicator is not simply an activity count for an outcome.

---

# Appendix G. Coursework task-parsing examples

## G1. “Discuss”

Question:
> Discuss the effects of decentralisation on health-service delivery in Uganda.

PaperAid should not simply define decentralisation and list advantages. It should identify relevant dimensions, present evidence/perspectives, and develop a reasoned synthesis consistent with the rubric.

## G2. Compound question

> Explain the major causes of antimicrobial resistance and critically evaluate two policy responses.

Required coverage objects:

```text
Q1: explain major causes
Q2: critically evaluate policy response 1
Q3: critically evaluate policy response 2
```

The plan cannot collapse all three into one generic “Discussion” heading without internal coverage mapping.

## G3. “Compare”

A valid comparison must include similarities and relevant differences. PaperAid must not use the obsolete rule “compare = similarities only.”

## G4. “To what extent”

The conclusion should express degree:
- largely;
- partly;
- weakly;
- under specified conditions;

rather than giving an unqualified yes/no unless evidence genuinely supports it.

---

# Appendix H. Coursework rubric processing detail

A rubric criterion should become a rule object with provenance.

Example source rubric:

```text
Critical analysis — 40%
Excellent work demonstrates sustained critical evaluation of competing evidence...
```

Compiled job rule:

```json
{
  "id":"RUBRIC-JOB-001",
  "class":"QUALITY",
  "severity":"WARNING",
  "weight":40,
  "requirement":"Demonstrate sustained critical evaluation of competing evidence.",
  "source_quote":"Excellent work demonstrates sustained critical evaluation...",
  "source_location":{"page":2,"row":"Critical analysis"},
  "check":{"type":"SEMANTIC","validator":"semantic.rubric_criterion"}
}
```

If the rubric says a criterion is mandatory for passing, severity may become BLOCKING according to that external rule.

---

# Appendix I. User-facing plan examples

## I1. Funding Proposal

```text
PaperAid understood this opportunity

Funding ceiling: USD 500,000
Duration: 24 months
Narrative limit: 10 rendered pages
Required: MEL plan, budget narrative, workplan
Scoring: Relevance 30 | Approach 30 | MEL 20 | Capacity 20

Recommended plan: Standard
Initial internal target: ~5,500 words
Final output will be rendered and compressed to the donor's 10-page limit.

[Adjust Plan]  [Continue]
```

## I2. Coursework

```text
PaperAid understood your assignment

Task: Critically evaluate...
Type: Essay
Level: Postgraduate
Word limit: 2,500
Referencing: APA 7
Sources: Independent scholarly research allowed

Required coverage
✓ intervention effectiveness
✓ Uganda context
✓ limitations
✓ reasoned judgment

Proposed plan
Introduction                       250
Theme 1                            600
Theme 2                            600
Theme 3                            550
Critical synthesis                 250
Conclusion                         250
Total                            2,500

[Adjust Plan]  [Start]
```

## I3. Concept Note

```text
Funding Concept Note
Standard — 1,800 words

Problem and evidence               400
Target group/geography             150
Funder relevance                   275
Approach/results                    475
Applicant advantage                175
Timeline/budget                     75
Sustainability/risk                125
Summary                            125

[Adjust Plan]  [Start]
```

---

# Appendix J. Source registry inherited from independent review

The following source registry is retained so future rule/profile work can trace the evidence used during design. These sources are examples and **must not be treated as permanently current donor rules**.

| Ref | Source | URL |
|---|---|---|
| S1 | US State Department, DRL Proposal Submission Instructions, updated Dec 2023 | https://2021-2025.state.gov/drl-proposal-submission-instructions-psi-for-applications-updated-december-2023/ |
| S2 | US State Department, DRL FY23 DPRK Statements of Interest NOFO | https://2021-2025.state.gov/drl-notice-of-funding-opportunity-nofo-drl-fy23-dprk-access-to-information-programs-statements-of-interest/ |
| S3 | US State Department, DRL Proposal Submission Instructions, Oct 2017 | https://www.state.gov/wp-content/uploads/2019/01/Proposal-Submission-Instructions-PSI-for-Applications-Updated-October-2017.pdf |
| S4 | US State Department, ECA NOFO Proposal Submission Instructions, Feb 2025 | https://eca.state.gov/files/bureau/nofo_psi_2-25.pdf |
| S5 | EU TACSO 3, Concept Note guidance presentation | https://crm.tacso.eu/sites/default/files/2.%20CSF%202021_23_CN%20presenation.pdf |
| S6 | Enabel, Grant Application File template (2026) | https://www.enabel.be/app/uploads/2026/01/1.0_Annex-A_Grant_Application_File_CfP.docx |
| S7 | Enabel, Grant Application File, Mozambique call MOZ22005 | https://www.enabel.be/app/uploads/2026/08/Annex-A_Grant_Application_File_CfP_MOZ22005-10354-1.docx |
| S8 | European Commission, Annex A.2 Grant Application Form, Full Application | https://www.eeas.europa.eu/sites/default/files/annex_a2._grant_application_form-full_application_0.docx |
| S9 | European Commission, Annex A Grant Application Form | https://www.eeas.europa.eu/sites/default/files/annex_a._grant_application_form_en.doc |
| S10 | Cambodia NCSD, Concept Note Guideline and Templates | https://ncsd.moe.gov.kh/sites/default/files/phocadownload/Grant/Window1Round2/annex%20a_concept%20note%20guideline%20%20templates.docx |
| S11 | Guinea MESRS, Modèle de note conceptuelle | https://prig.mesrs.gov.gn/documents/model_note_conceptuelle.pdf |
| S12 | UNHCR, Sample Concept Note Template (2025) | https://www.unhcr.org/handbooks/programme-partnerhub/sites/pph/files/2025-09/Sample%20Concept%20Note%20Template_EN.docx |
| S13 | Grand Challenges Explorations, Rules and Guidelines Round 23 | https://gcgh.grandchallenges.org/sites/default/files/files/GCE_Rules_and_Guidelines_Round23.pdf |
| S14 | UNDEF, How to Apply: Online Project Proposal System | https://www.un.org/democracyfund/node/545 |
| S15 | UNDEF, Round 13 blank project proposal form | https://www.un.org/democracyfund/sites/www.un.org.democracyfund/files/r13_blank_project_proposal_application_form_en.pdf |
| S16 | UNDEF, Round 15 Project Document Guidelines | https://www.un.org/democracyfund/sites/www.un.org.democracyfund/files/r15_project_document_-_guidelines_en_0.docx |
| S17 | UN Voluntary Fund on Disability, Project Proposal Application Form | https://www.un.org/disabilities/documents/unvf/unvf_application_form_instructions.doc |
| S18 | UNDP Thailand, SDG Localisation call for proposals | https://www.undp.org/thailand/news/undp-thailand-sdg-L-call-for-proposals-eng |
| S19 | UNDP Trinidad and Tobago, GEF SGP Call for Proposals 2025 | https://www.undp.org/trinidad-and-tobago/news/gef-sgp-call-proposals-2025 |
| S20 | NIH, Page Limits | https://grants.nih.gov/grants/guide/url_redirect.php?id=41132 |
| S21 | UKRO, Summary of EC webinar on Horizon Europe 2026-2027 novelties | https://www.ukro.ac.uk/news/summary-of-ec-webinar-on-novelties-in-the-2026-2027-horizon-europe-work-programme/ |
| S22 | Horizon Europe page-limit secondary reference used in review | https://eufunds.me/what-is-the-page-limit-of-horizon-europe-proposals/ |
| S23 | Historical transition source cited by independent review; verify live issuing-agency requirements for actual opportunities | https://www.stateoig.gov/report/aud-fa-26-17 |
| S26 | NHTSA, Update on 2 CFR Part 200 | https://www.nhtsa.gov/document/update-2-cfr-part-200 |
| S27 | William T. Grant Foundation, indirect cost FAQs | https://wtgrantfoundation.org/search/indirect%20costs |
| S28 | OECD-DAC Glossary of Key Terms in Evaluation and RBM, 2nd ed. 2023 | https://alnap.org/help-library/resources/glossary-key-terms-evaluation-and-rbm-2023/ |
| S30 | Newcastle University, Introductions and Conclusions | https://www.ncl.ac.uk/mediav8/academic-skills-kit/file-downloads/How%20to%20Write%20Introductions%20and%20Conclusions.pdf |
| S31 | University of Hull, essay structure | https://studyskills.hull.ac.uk/?p=2352 |
| S32 | Federation University, Introductions and Conclusions | https://www.federation.edu.au/students/study-skills/study-resources/academic-writing/introductions-and-conclusions/ |
| S33 | University of Canterbury, Structure of an Academic Essay | https://betterstartapproach.com/content/dam/uoc-main-site/documents/pdfs/d-other/Essay-Structure.pdf |
| S34 | Federation University, Glossary of Instructional Words (2025) | https://www.federation.edu.au/siteassets/files/students/study-skills/glossary_instructional_words_helpsheet-2025.pdf |
| S35 | Bangor University, Instruction Words for Assignments | https://www.bangor.ac.uk/studentservices/disability/documents/instructions-words-for-assignments.pdf |
| S36 | University of Wolverhampton, Assignment Task Words (2025) | https://www.wlv.ac.uk/lib/media/departments/lis/skills/study-guides/2024-study-guides/LS010---Guide-to-Assignment-Task-Words.pdf |
| S38 | Case-study guidance source used by independent review | https://malat-webspace.royalroads.ca/rru0019/how-to-write-the-case-study/ |
| S39 | Sheffield Hallam University, Case studies: structure | https://libguides.shu.ac.uk/casestudies/structure |
| S41 | UK legislation, Skills and Post-16 Education Act 2022 explanatory notes | https://www.legislation.gov.uk/ukpga/2022/21/notes/division/9/index.htm |

The source registry is documentation, not code. Live requirements must be retrieved from the governing source for each real job.

---

# Appendix K. Final implementation checklist for the IDE

Before claiming the rulebook is implemented, confirm all of the following:

### Core engine
- [ ] Rule schema implemented.
- [ ] Class and severity are separate fields.
- [ ] Authority precedence implemented centrally.
- [ ] Conflict log implemented.
- [ ] Extracted external requirements preserve quote/location/confidence.
- [ ] Low-confidence requirements require confirmation.
- [ ] Resolved specification is persisted/versioned.
- [ ] Validators are referenced by ID, not embedded as prompt text.

### Limits/rendering
- [ ] Word limits supported.
- [ ] Character limits supported.
- [ ] Field limits supported.
- [ ] Rendered page limits supported.
- [ ] `counts_toward_limit` scope supported.
- [ ] Targeted compression available.

### Concept Note
- [ ] Research variant.
- [ ] Project variant.
- [ ] Funding variant.
- [ ] Brief/Standard/Extended modes.
- [ ] Funding relevance check.
- [ ] Applicant credibility check.
- [ ] Form mode.
- [ ] Post-draft compliance report.

### Funding Proposal
- [ ] Compact/Standard/Comprehensive recommendation.
- [ ] Complexity classifier.
- [ ] Results Model persistence.
- [ ] Output/outcome/activity graph validators.
- [ ] Indicator fields/validation.
- [ ] Budget arithmetic.
- [ ] Cost share and indirect-cost base support.
- [ ] Prohibited-cost rules.
- [ ] Timeline/activity consistency.
- [ ] Narrative numeric consistency.
- [ ] Logframe generated from Results Model.
- [ ] Workplan generated from Results Model.
- [ ] M&E table generated from Results Model.
- [ ] Research-grant variant.
- [ ] Donor-scoring-aware planning.
- [ ] Conditional overlays.

### Coursework
- [ ] Brief parser.
- [ ] Directive parser.
- [ ] Limiting-word parser.
- [ ] Compound-question coverage.
- [ ] Rubric parser.
- [ ] Essay mode.
- [ ] Report mode.
- [ ] Literature-review mode.
- [ ] Analytical case-study mode.
- [ ] Problem-oriented case-study mode.
- [ ] Short research paper empirical/non-empirical branching.
- [ ] Reflective mode.
- [ ] Closed-source policy.
- [ ] AI-use policy enforcement.
- [ ] Academic Quality & Integrity Review.
- [ ] No detector-evasion step.

### Evidence
- [ ] Bibliographic verification.
- [ ] Claim-source support statuses.
- [ ] Numeric-claim strict support.
- [ ] Retraction/correction check where available.
- [ ] Source hierarchy varies by claim type.

### Testing
- [ ] Golden tests implemented.
- [ ] External precedence tested.
- [ ] Rendered page tests implemented.
- [ ] Budget inconsistency tests implemented.
- [ ] Coursework directive tests implemented.
- [ ] Form-character-limit tests implemented.

When all applicable boxes pass, PaperAid may treat Rulebook v1.0 as production-ready.
