# Handoff to Codex — PaperAid

**From:** Claude (Anthropic's Claude Opus 5.5, running in Claude Code inside VS Code)
**Date:** 2026-09-23
**Project folder:** `f:\MY FILES\DATA SCIENCE\PAPER AID`
**Project owner:** the user (the person who will prompt you). They make every product decision.

---

## 1. Who I am and what I did

I was asked to read the project's handoff specification in full, then write my own independent execution plan so the owner could compare approaches. I did both. **No code has been written.** The folder is not a git repository yet.

What I did, in order:

1. Read `PaperAid_Master_Product_Architecture_and_Implementation_Specification.md` in full (3,615 lines, ~87k words).
2. Extracted the `.docx` version and diffed it against the `.md`. The text is the same (only list and backtick formatting differ). The `.docx` also embeds one image, a **landing-page visual reference mockup**. I reviewed it; §3 of my plan discusses what it shows.
3. Checked current Claude model IDs and pricing against Anthropic's reference material (cached 2026-06-24). I did not verify the OpenAI model the spec names.
4. Wrote **`PaperAid_Execution_Plan_Claude.md`**, my full plan (~6,700 words). **That file is the main thing I'm handing you.**

---

## 2. Files in this folder

| File | What it is | How to treat it |
|---|---|---|
| `PaperAid_Master_Product_Architecture_and_Implementation_Specification.md` | The owner's master spec (authoritative source) | Source of truth for requirements. See the warning in §3 before reading it all |
| `PaperAid_Master_Product_Architecture_and_Implementation_Specification.docx` | The same spec plus the landing-page mockup image (`word/media/image1.png` inside the zip) | Open it only for the image |
| `PaperAid_Execution_Plan_Claude.md` | **My independent execution plan** | Read it in full. It is a proposal, not an approved plan |
| `HANDOFF_FOR_CODEX.md` | This file | Orientation |

---

## 3. Read the spec efficiently: most of it is boilerplate

The spec has 42 sections, each with 8 requirements (R01–R08), and each requirement has "Implementation", "Guardrails" and "Acceptance" paragraphs. I measured these:

- The 336 "Implementation" paragraphs contain only **10 unique texts**, rotated.
- The "Guardrails" paragraphs contain **5 unique texts**; the "Acceptance" paragraphs contain **1**.
- Many are attached to the wrong requirement. Example: §1 R06 "model names must be configurable" is followed by a paragraph about Cloud Tasks.

**Do not treat those per-requirement paragraphs as requirement-specific instructions.** The real content is:

- the front matter (lines 1–121): executive summary, approved architecture and priority order;
- each section's intro paragraph plus its **"Required outcomes"** bullet list;
- **Appendices A–K** (from line 3188 onward). These are high quality: the repo layout, UI inventory, job-record JSON, state enums, API surface, orchestration steps, env config, test catalogue, runbook, risk register, launch checklist and deferred roadmap.

This command prints the non-boilerplate body of sections 5–42:

```bash
awk 'NR>=414 && NR<3188' PaperAid_Master_Product_Architecture_and_Implementation_Specification.md \
 | grep -v '^\*\*Implementation\.\*\*\|^\*\*Guardrails\|^\*\*Acceptance\|^### R0\|^## Detailed implementation requirements\|^$'
```

Sections 1–4 have the same structure. Their "Required outcomes" lists are near the top of the file.

---

## 4. The project in one paragraph

PaperAid is a paid, job-oriented academic paper service for university students, mainly in Uganda (UGX pricing, Mobile Money later).

- **The job:** a student uploads a DOCX or text-based PDF, plus an optional university guideline. They choose a service and get a server-calculated quote. The job runs asynchronously and returns a downloadable result.
- **Services:** AI Check, Check + Refine, Academic Formatting, University Template Formatting, Deep Redraft and LaTeX Conversion.
- **Approved stack:** React + TypeScript + Vite (dev server on **port 5000**) on Firebase Hosting; Firebase Auth, Firestore, Storage and App Check; one Python FastAPI backend on Cloud Run; Google Cloud Tasks (about 5 concurrent jobs); Secret Manager; OpenAI and Anthropic called only from the server.
- **Payments:** modelled in the data from the start, but turned off by a `PAYMENTS_ENABLED` flag until the rest works.
- **Explicitly banned unless measured need appears:** Redis, PostgreSQL, Kubernetes, Kafka/RabbitMQ, microservices, LangChain/LangGraph, Redux, and architecture theatre such as managers, factories and repositories with one implementation.

---

## 5. What my plan proposes (read the file for the reasoning)

`PaperAid_Execution_Plan_Claude.md`, section by section:

- **§0**: the ten points where I diverge from the spec. Start here.
- **§2**: an audit of the spec, including gaps I found. The biggest: no endpoint creates a job ID before upload, completed jobs send no notification, and refine/format have no defined output for PDF input.
- **§3**: **positioning risk.** The mockup's "68% → 12%" AI-score hero and its "maximum originality" copy market the product as a way past AI detectors. I recommend reframing around clarity, formatting and a self-check, with tracked-changes output. *The owner has not decided this yet.*
- **§4**: architecture changes:
  - one Docker image deployed as two Cloud Run services (a public API and an internal, IAM-only worker with concurrency 1);
  - **one pipeline stage per Cloud Tasks invocation**, with a Firestore lease and checkpoints, to stay under Cloud Tasks' 30-minute dispatch deadline;
  - the job's lifecycle status and its processing stage stored as separate fields;
  - a resource-oriented API;
  - TypeScript types generated from the Pydantic/OpenAPI models;
  - library choices.
- **§5**: the AI and document pipeline:
  - the DocumentModel;
  - **opaque-segment placeholders** protecting citation fields (Zotero/Mendeley), footnotes, equations, hyperlinks and differently-formatted runs;
  - a tracked-changes DOCX output;
  - a calibrated hybrid AI-likeness score;
  - refinement → audit → repair, keeping the original text of any block that still fails;
  - model roles and a cost table.
- **§6**: the formatting engine, with curated university presets first and uploaded-guideline parsing in wave 2.
- **§7**: launch in waves. The beta has 3 services (AI Check, Check + Refine, Academic Formatting).
- **§8**: **Phases 0–8 with review gates**, about 10 weeks to a paid public launch. It ends with a table mapping my phases to the spec's Stages A–H. Key change: a CLI "quality lab" (Phase 2) proves document safety and AI quality on about 20 real papers *before* Firebase, queue and worker work.
- **§9**: the pricing formula (per 1,000 words) and a per-job model-spend budget.
- **§10–11**: security and compliance additions (Uganda Data Protection and Privacy Act 2019) and the testing and eval strategy.
- **§13**: **nine open decisions for the owner.**
- **§14**: additions to the risk register.

---

## 6. Status of decisions

**Approved by the owner** (per the spec): the stack in §4 above, port 5000, payments deferred behind a flag, the banned-technology list, the "enterprise without spaghetti" coding standard, and building the visual milestone first.

**Proposed by me, not yet approved.** Treat these as suggestions, not settled facts:

- the positioning change;
- the three-service beta;
- a paid public launch instead of a free public beta;
- stage-per-task execution;
- two Cloud Run services;
- the status/stage split;
- tracked-changes output;
- building the quality lab before Firebase.

**Open (see plan §13):** positioning, launch scope, payments timing, GCP region (`africa-south1` vs `europe-west1`), which provider keys exist and the spend ceiling, corpus availability, email provider, refund policy, and domain/trademark.

---

## 7. Claims in my plan you should verify rather than trust

I was confident enough to write these down, but not all of them were checked against a live source:

| Claim | My confidence | Action |
|---|---|---|
| Claude Opus 5.5 = `claude-opus-5-5`, $4 / $20 per million input/output tokens, cache reads $0.20, 1M context, thinking always on, default effort `medium`, no forced `tool_choice` (use structured outputs) | High (Anthropic reference, cached 2026-06-24) | Re-check at build time |
| "GPT-6 Sol" model name and pricing | **Unverified** | Confirm with the owner and OpenAI's docs. My cost table uses an assumed range |
| Cloud Tasks HTTP-target maximum dispatch deadline is 30 minutes | High | Confirm in the GCP docs. The stage-per-task design depends on it |
| Firestore, Cloud Run, Cloud Tasks and Storage are all available in `africa-south1` | **Unverified** | Check before creating the Firestore database (its location is permanent) |
| PyMuPDF is AGPL-licensed, so prefer pdfplumber/pypdf | High | — |
| Tectonic can run offline from a pre-cached bundle | Medium–high | Verify the flag name on the pinned version |
| Uganda DPPA 2019: PDPO registration and cross-border transfer conditions | Medium | Needs a legal review, not engineering judgement |
| Payment providers listed for Uganda (MTN MoMo / Airtel direct, Flutterwave, Pesapal, DPO, Relworx, Yo! Payments) | Medium | Candidates to evaluate, not recommendations |
| ~3,700 UGX per USD | Medium | Check the current rate |
| The AI providers' usage policies address academic dishonesty and deceptive use | Medium | Read the current policy text against the final marketing copy |

---

## 8. How to proceed

Follow the owner's instructions first. If they haven't said what to do:

1. **Don't start coding yet.** The §13 decisions affect landing copy, scope and phase order. Ask the owner which decisions they've made.
2. If you're asked to **compare plans**:
   - read my §0 and §8 mapping table, then compare against the spec's §41 ("Implementation Sequence") and any plan of your own or the owner's;
   - be specific about disagreements, and say where you think I'm wrong. The owner wants independent views, not agreement.
3. When implementation starts (Phase 0 in my plan, Stage A in the spec):
   - `git init`;
   - create the repo skeleton from spec Appendix A;
   - distil the spec into a short rules file (I proposed `CLAUDE.md`; for you, `AGENTS.md` serves the same role) plus a condensed `docs/spec.md`;
   - record decisions in `docs/decisions.md`;
   - then build the visual milestone on `http://localhost:5000` against fixture data.
4. **Keep the app runnable after every step. Never put provider keys in the frontend or in `VITE_` variables. Never commit secrets.** The owner holds all credentials.

---

## 9. Contact point

If something in my plan is unclear, the reasoning is almost always in the section cited in §5 above. Where my plan and the owner's spec disagree, **the spec wins until the owner says otherwise.**

— Claude
