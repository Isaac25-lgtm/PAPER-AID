# PaperAid: four-model implementation and verification

## Requested behavior

The owner changed the earlier cheapest-single-reviewer request: Luna and Sonnet should do the work; Sol and Opus should guide and approve rewriting. The implementation uses two independent writing-pattern checks and requires both frontier approvals for delivered changed wording.

| Work | Model |
|---|---|
| Writing-pattern checks, before and after | GPT-6 Luna and Claude Sonnet 5.5, independently |
| Routine analysis, research, initial plans | GPT-6 Luna |
| Working critique, drafting, rewriting and repairs | Claude Sonnet 5.5 |
| Additional plan guidance | Claude Opus 5.5 |
| Final instructions, readiness review | GPT-6 Sol |
| Release review of generated wording | GPT-6 Sol and Claude Opus 5.5, independently |

Model routes and approval policy are frozen on each estimate/quote. Existing jobs retain their original algorithm. The execution and quote projections use the same routing function.

## What LOW currently means

PaperAid measures formulaic writing patterns. It does not verify human or AI authorship. Eligible prose passages have at least 25 words; headings, references, quotations and table cells are excluded. Code assigns rule scores; models judge context and may reject false positives. The rule component contributes 50%; the two checking models contribute 25% each. Passage scores are weighted by their word counts. Existing thresholds remain LOW below 15%, MODERATE below 32%, HIGH from 32%.

These thresholds are provisional. We have not measured sensitivity, false positives or calibration on a labelled set of human, AI and mixed writing. Adding a second model does not supply that evidence.

The former prompt allowed an unflagged passage to be omitted, and omitted passages were interpreted as LOW. The new prompt requires an explicit result for every supplied ID. Coverage requires both responses. Incomplete coverage suppresses the overall percentage and shows **Check incomplete** in the workspace and Word report. Disagreement is retained and its passages are labelled in the paper. Confidence is LOW when judgments differ.

The supplied job ID is cloud-only in this session. Its LOW result has not been attributed to any particular cause. Run the following in a normal terminal with your existing Google sign-in, then share its scoring metadata:

```powershell
Set-Location -LiteralPath 'F:\MY FILES\DATA SCIENCE\PAPER AID\backend'
.\.venv\Scripts\python.exe .\inspect_ai_score.py job_8a5808635e3e
```

The helper only reads that job and its internal files. It prints counts, scores, model names, versions and costs; it does not print paper wording, identity fields or credentials, and makes no AI calls.

## Approval rules

Both Sol and Opus inspect the exact same changed wording independently. Either rejection, omitted answer or substantive issue blocks the change. Every repair needs two new approvals. The request cache binds each answer to its task, model, prompt and payload, so an earlier answer cannot approve different wording.

For uploaded papers, rejected changes retain the student's original wording and the result carries warnings. For chapter revisions, the previous section is retained. A new chapter has no earlier text: with the `PARTIAL_CHAPTERS` switch off (the default, owner decision 2026-09-30) an unapproved or missing section means no chapter is released and nothing is charged; with it on, the approved sections are delivered, charged by their share, and "Finish chapter" writes the rest, the draft and its finishes never costing more than one chapter. The switch stays off while a rollback to `1d573b6` may be needed, because that release cannot protect a partly written chapter. New proposal plans and institution profiles require both final approvals. Code removes untraceable text before the final approval, so both reviewers approve the wording that is delivered; a final check refuses any later change. University formatting rules require both reviews; when they are not approved the rest of the job is delivered without them and that part is refunded. Deterministic formatting and LaTeX keep their existing code checks.

Writing-check reports can be downloaded without frontier editing reviews: they add no wording to the paper. Since 2026-09-30 they, and the website, present writing-pattern feedback only (see the Phase 4 finding below).

## Verification and release status

Local implementation, not deployed. Built and verified by Claude on 2026-09-29 in the phases agreed with
Codex; Codex audits the whole change before release.

**Tests (test doubles, no paid calls).** Backend suite: 515 passed, none failed (final run, after the pilot fixes;
ruff clean). The web typecheck, the web unit tests and the production build
pass. The four browser journeys (main, proposal, recovery, audit) pass.

**Real models (paid, owner go-ahead; total $4.33).**

1. *Calibration pilot* (`backend/calibrate.py`, $1.42): 10 human papers (Ugandan public-health articles
   in PLOS ONE, 2015-2019, written before AI tools) and 10 AI-written papers on the same topics (5 by Sol,
   5 by Opus, $0.74 to write). Every check was complete; no low-against-high disagreement occurred.

   | Formula (rules / checker / checker) | Human mean | AI-written mean | Rated MODERATE or HIGH |
   |---|---|---|---|
   | current 50 / 25 / 25 | 6% (5-8) | 6% (5-10) | none of 20 |
   | 25 / 37.5 / 37.5 | 9% | 9% | none |
   | models only 0 / 50 / 50 | 12% (10-14) | 11% (10-15) | 1 AI paper (test half) |

   **The writing-pattern check does not separate AI-written from human papers.** Both checkers rate almost
   every passage "low" in both groups, and the rules score near zero in both (mean 0.0 to 0.06). No weighting
   can fix that: the scores carry no signal to weight. This is why AI-written papers come out LOW. It is a
   pilot (edited journal articles, frontier-model essays, 20 papers), but the two groups are
   indistinguishable, so changing the formula is not the remedy.

2. *Jobs through the new pipeline* (local app, fixed prices):

   | Job | Result | AI spend | Price | Spend ÷ price |
   |---|---|---|---|---|
   | AI Check, human paper (7,492 words) | 7%, LOW, complete | $0.12 | UGX 5,000 | 0.10 |
   | AI Check, AI-written paper (2,215 words) | 5%, LOW, complete | $0.03 | UGX 2,000 | 0.07 |
   | Refine, AI-written (2,072 words) | 7 of 8 rewritten; 6% → 6% | $0.48 | UGX 4,000 | 0.49 |
   | Deep redraft, AI-written (1,892 words) | 1 group rewritten, 2 left by the plan | $0.15 | UGX 7,000 | 0.09 |
   | Proposal plan (first run) | refused by the reviewers | $0.24 | not charged | lost |
   | Proposal plan (after the fixes) | approved by both | $0.25 | UGX 2,000 | 0.51 |
   | Chapter One | 11 of 11 sections approved | $0.88 | UGX 5,000 | 0.70 |

   For comparison, the live two-model jobs this month spent 2-13% of their price (`cost_report.py`).

3. *Defects the pilot found, fixed and tested* (`tests/test_pilot_fixes.py`): an over-long plan field was
   cut mid-sentence ("…"), and the plan reviewers refused the plan for it; it now ends at a complete sentence.
   The plan reviewers also required the finished proposal's reference list of a plan; `p-plan-review-v2` says
   a plan cites by evidence id and the reference list is built later.

**Rollback** was checked against the released code (`1d573b6`): see `deployment.md`, "Rolling back the
four-model release".

**Open for the owner before release:** (a) the AI-likeness score cannot detect frontier-model writing
(above), so how it is presented, or what replaces it, is an owner decision; (b) Refine, plans and chapters
now spend about half or more of their price (Chapter One 70%, above the 50% target), so prices or the
Opus guidance step (`FRONTIER_GUIDANCE`) need a decision.
