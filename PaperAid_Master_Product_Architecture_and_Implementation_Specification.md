# PaperAid — Master Product, Architecture and Implementation Specification

**IDE Handoff Specification for a Production-Grade, Firebase-Centred Academic Paper Processing Platform**  
**Version:** 1.0  
**Prepared:** 2026-09-23  
**Status:** Authoritative IDE handoff for the PaperAid first production release.

> **IDE instruction:** Read this document before generating architecture or code. Keep the system runnable after every implementation stage. Expose the complete polished frontend early at `http://localhost:5000`, then continue replacing fixtures with Firebase and backend behaviour. The specification is deliberately opinionated to prevent AI-generated overengineering and spaghetti code. Where a detail is not prescribed, choose the simplest production-safe implementation consistent with this document.

## Executive Summary

PaperAid is a paid, job-oriented academic paper-processing platform. A student uploads a paper, optionally uploads a university or departmental formatting guide, chooses the work required, receives a server-calculated quote, and the platform processes the job asynchronously. The initial service catalogue is AI Check, Check + Refine, Academic Formatting, University Template Formatting, Deep Redraft and LaTeX Conversion. The product is not a generic chatbot and ordinary users do not choose model names or write system prompts. The product value is the finished job: a checked, refined, formatted, redrafted or converted paper returned as a secure downloadable artifact.

The approved architecture is Firebase-centred. The frontend is React + TypeScript + Vite on Firebase Hosting. Firebase Authentication manages identity, Cloud Firestore holds operational metadata, Firebase/Cloud Storage holds files, Firebase App Check adds abuse resistance, a Python FastAPI backend runs on Cloud Run, and Google Cloud Tasks dispatches controlled background work. Provider secrets remain server-side in Google Secret Manager or runtime secret bindings. OpenAI and Anthropic APIs are called only by the backend. Payments are represented in the state model but disabled until the non-payment system is stable. No Render, PostgreSQL, Redis, Kubernetes, Kafka, RabbitMQ or microservice fleet is required at launch.

The launch planning assumption is about 500 registered users in the first month and bursts of five to ten simultaneous submissions. The application may accept all eligible jobs, but the queue initially dispatches about five active processing jobs at once. Remaining jobs are queued and start automatically as slots become available. This protects provider quotas and cost while keeping the browser responsive. Increasing the concurrency limit later is a configuration change, not an architectural rewrite.

The first engineering milestone is visual. The IDE must configure Vite to run on port 5000 and implement the public site plus the full authenticated experience against realistic fixture data before deep backend coupling. The landing page should achieve the clean, product-led quality associated with leading writing-assistant SaaS products: generous whitespace, strong hierarchy, green PaperAid branding, a realistic product mockup in the hero, concise feature cards and obvious calls to action. It may be inspired by Grammarly-style design quality, but it must remain original in branding, wording, composition and assets.

The document-processing philosophy is conservative. DOCX is the preferred editable format. Text-based PDF is supported for analysis and rewriting; scanned PDF is rejected in V1 rather than silently invoking OCR. Standard refinement changes selected blocks rather than regenerating the entire paper. Citations, quotations, URLs, numbers and other protected spans are locked or validated. An independent audit checks semantic drift and only failed blocks are repaired. University formatting is interpreted into a structured `FormattingSpec`, then deterministic document code applies the actual layout.

The coding standard is “enterprise without spaghetti.” Enterprise means secure, observable, recoverable, tested and understandable. It does not mean more layers. A three-line function should not become a manager/repository/factory hierarchy. Business rules such as pricing, job transitions, authorization and cost ceilings have one source of truth. Model SDKs are isolated because they are genuine external boundaries; otherwise direct code is preferred. Dead scaffolding is removed as stages become real.

## Approved Architecture

```text
Browser / Mobile Web
        |
        v
Firebase Hosting — React + TypeScript + Vite
        |
        +--> Firebase Authentication
        +--> Firebase App Check
        +--> Firebase Storage (secure direct upload/download)
        |
        v
Cloud Run — Python FastAPI trusted backend
        |
        +--> Cloud Firestore (users, jobs, quotes, config)
        +--> Google Cloud Tasks (controlled async queue)
        |          |
        |          v
        |      Cloud Run worker endpoint
        |          |
        |          +--> DocumentModel / DOCX / PDF / LaTeX engine
        |          +--> OpenAI API (configured analysis/audit model)
        |          +--> Anthropic API (configured writing model)
        |          +--> Firebase Storage outputs/artifacts
        |
        +--> Secret Manager / runtime secret bindings

Future: verified Mobile Money/payment provider gates queue release
```

## How the IDE Should Interpret Priorities

1. Security and document integrity outrank convenience.
2. Correctness and maintainability outrank clever abstraction.
3. User-visible quality outranks tiny API-cost savings when the cost difference is commercially immaterial.
4. Deterministic code outranks model calls for formatting, pricing, state transitions and authorization.
5. The first usable visual must appear early at localhost:5000.
6. The application must remain deployable and runnable as each stage replaces mock behaviour.
7. Payments are deliberately last; the core product must work with `PAYMENTS_ENABLED=false`.
8. Unsupported features should be hidden rather than shipped partially.

## Table of Contents

- 1. Product Vision and Non-Negotiable Principles
- 2. Scope, Users and Service Boundaries
- 3. Brand and Visual Direction
- 4. Public Landing Page
- 5. Early Visual Milestone on localhost:5000
- 6. Application Routes and Information Architecture
- 7. Core User Journey from Upload to Delivery
- 8. Service Catalogue and Compatibility
- 9. AI-Likeness Analysis and Score Presentation
- 10. Standard Refinement Workflow
- 11. Deep Redraft Workflow
- 12. University Guideline and Template Upload
- 13. Deterministic Academic Formatting Engine
- 14. LaTeX Conversion
- 15. Pricing and Quote Engine
- 16. Approved Firebase-Centred Architecture
- 17. Repository Structure and Engineering Boundaries
- 18. Local Development and Developer Experience
- 19. Authentication and Account Model
- 20. Firestore Data Model
- 21. Storage Layout and Retention
- 22. Cloud Run FastAPI Backend
- 23. Cloud Tasks Queue and Concurrency
- 24. Job State Machine and Progress
- 25. Internal Document Model and Extraction
- 26. AI Provider Layer and Model Configuration
- 27. Prompt and Structured Output Governance
- 28. AI Cost Accounting and Spend Ceilings
- 29. Security Architecture
- 30. Rate Limiting and Abuse Prevention
- 31. Privacy, Retention and Confidentiality
- 32. Reliability, Idempotency and Recovery
- 33. Observability, Logging and Operational Metrics
- 34. Admin Console
- 35. Frontend State and Component Strategy
- 36. Responsive Design and Accessibility
- 37. Testing Strategy
- 38. Performance and Capacity for the First 500 Users
- 39. CI, Deployment and Environments
- 40. Payment-Ready Architecture with Integration Deferred
- 41. Implementation Sequence and Early Review Gates
- 42. Coding Standard, Definition of Done and Deferred Scope
- Appendix A. Canonical Repository Structure
- Appendix B. Product Screens and UI Inventory
- Appendix C. Core Data and State Contracts
- Appendix D. API Surface
- Appendix E. Model Orchestration Contracts
- Appendix F. Environment and Configuration
- Appendix G. Test and Acceptance Catalogue
- Appendix H. Operational Runbook
- Appendix I. Risk Register
- Appendix J. Launch Checklist
- Appendix K. Deferred Roadmap

# 1. Product Vision and Non-Negotiable Principles

PaperAid is a job-oriented academic paper-processing platform. A student uploads a paper, chooses work, receives a quote, and receives a finished result. The product must combine premium visual quality with a deliberately compact architecture and codebase.

## Required outcomes

- PaperAid must prioritise completed paper jobs over open-ended chat interactions.
- The implementation must be enterprise-grade in reliability and security without enterprise theatre or unnecessary infrastructure.
- The code must be concise, readable and human-like; simple logic must remain simple rather than being expanded into layers.
- The first-month design target is about 500 registered users and bursts of five to ten simultaneous users without redesign.
- Important writing and audit stages may use premium models because output quality is more important than saving a few hundred shillings.
- Model names, price metadata, concurrency and service limits must remain configurable rather than scattered through code.
- PaperAid must never promise that its AI-likeness estimate equals Turnitin or any other third-party detector.
- Payments must be designed into the domain but remain disabled until the non-payment system works end to end.

## Detailed implementation requirements

### R01 — PaperAid must prioritise completed paper jobs over open-ended chat interactions.

**Implementation.** Implement the smallest cohesive production-safe solution that satisfies this requirement. Keep business rules in one source of truth, avoid speculative abstractions, expose failures explicitly, and add a durable test or verification step where the behaviour can regress. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is opaque model behaviour, semantic drift or unnecessary token use. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R02 — The implementation must be enterprise-grade in reliability and security without enterprise theatre or unnecessary infrastructure.

**Implementation.** Fail closed. Verify Firebase identity and App Check where required, keep secrets in Google Secret Manager/Cloud Run secret bindings, validate ownership on every job operation, rate-limit expensive actions, and never log raw paper content or secret values. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is unauthorised access to private documents, secrets or privileged state. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R03 — The code must be concise, readable and human-like; simple logic must remain simple rather than being expanded into layers.

**Implementation.** Use structured Cloud Logging and a small operational admin surface. Store only metadata needed to diagnose jobs. Prefer high-signal operational metrics and avoid building a separate analytics platform or exposing paper content by default. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is opaque model behaviour, semantic drift or unnecessary token use. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R04 — The first-month design target is about 500 registered users and bursts of five to ten simultaneous users without redesign.

**Implementation.** Implement the smallest cohesive production-safe solution that satisfies this requirement. Keep business rules in one source of truth, avoid speculative abstractions, expose failures explicitly, and add a durable test or verification step where the behaviour can regress. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is ambiguity, duplicated logic or an unreliable user experience. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R05 — Important writing and audit stages may use premium models because output quality is more important than saving a few hundred shillings.

**Implementation.** Keep model SDK calls server-side in small provider adapters. Model names are configuration. Control-flow outputs should use validated structured schemas; rewritten prose may be free text. Record model, prompt version, tokens, latency and estimated cost for every paid call, and bound retries. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is opaque model behaviour, semantic drift or unnecessary token use. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R06 — Model names, price metadata, concurrency and service limits must remain configurable rather than scattered through code.

**Implementation.** Use Google Cloud Tasks as the production queue. Start with roughly five concurrent dispatched jobs, make the limit configurable, use OIDC-authenticated task delivery, and make enqueue/worker execution idempotent. Do not invent an in-memory production queue. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is duplicate processing, stuck jobs or uncontrolled provider spend. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R07 — PaperAid must never promise that its AI-likeness estimate equals Turnitin or any other third-party detector.

**Implementation.** Implement the smallest cohesive production-safe solution that satisfies this requirement. Keep business rules in one source of truth, avoid speculative abstractions, expose failures explicitly, and add a durable test or verification step where the behaviour can regress. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is opaque model behaviour, semantic drift or unnecessary token use. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R08 — Payments must be designed into the domain but remain disabled until the non-payment system works end to end.

**Implementation.** Make this server-authoritative and versioned. The client may display values but must never choose the final amount or mark a payment successful. Store an immutable quote snapshot. Payments remain feature-flagged off until the non-payment product is stable. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is opaque model behaviour, semantic drift or unnecessary token use. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
# 2. Scope, Users and Service Boundaries

The first release serves students and researchers who have academic papers or university guidelines and want a finished processing service. It should not attempt to become an LMS, plagiarism database, research repository, collaboration suite or generic AI chat product.

## Required outcomes

- Primary users are university students working on coursework, essays, reports, proposals and dissertations.
- Secondary users are researchers who need formatting, refinement or LaTeX conversion.
- The MVP must accept DOCX and text-based PDF while rejecting scanned PDFs with a clear instruction rather than silently adding OCR.
- DOCX is the highest-fidelity editable format; PDF analysis is supported but perfect round-trip PDF formatting must not be promised.
- The initial catalogue is AI Check, Check + Refine, Academic Formatting, University Template Formatting, Deep Redraft and LaTeX Conversion.
- Formatting-only jobs must not rewrite body prose.
- Deep redraft must be an explicit higher-cost choice and must not be silently substituted for normal refinement.
- Features not production-ready must be hidden instead of exposed as partially working controls.

## Detailed implementation requirements

### R01 — Primary users are university students working on coursework, essays, reports, proposals and dissertations.

**Implementation.** Implement the smallest cohesive production-safe solution that satisfies this requirement. Keep business rules in one source of truth, avoid speculative abstractions, expose failures explicitly, and add a durable test or verification step where the behaviour can regress. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is ambiguity, duplicated logic or an unreliable user experience. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R02 — Secondary users are researchers who need formatting, refinement or LaTeX conversion.

**Implementation.** Keep model SDK calls server-side in small provider adapters. Model names are configuration. Control-flow outputs should use validated structured schemas; rewritten prose may be free text. Record model, prompt version, tokens, latency and estimated cost for every paid call, and bound retries. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is silent corruption of the paper, formatting or protected academic content. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R03 — The MVP must accept DOCX and text-based PDF while rejecting scanned PDFs with a clear instruction rather than silently adding OCR.

**Implementation.** Use a source-independent internal DocumentModel with stable block identifiers. Preserve the uploaded source, patch DOCX selectively, and use deterministic document code for formatting. Reject scanned/encrypted/unsafe inputs rather than silently producing low-quality output. Protect citations, quotations, numerals and other locked spans. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is silent corruption of the paper, formatting or protected academic content. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R04 — DOCX is the highest-fidelity editable format; PDF analysis is supported but perfect round-trip PDF formatting must not be promised.

**Implementation.** Use a source-independent internal DocumentModel with stable block identifiers. Preserve the uploaded source, patch DOCX selectively, and use deterministic document code for formatting. Reject scanned/encrypted/unsafe inputs rather than silently producing low-quality output. Protect citations, quotations, numerals and other locked spans. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is silent corruption of the paper, formatting or protected academic content. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R05 — The initial catalogue is AI Check, Check + Refine, Academic Formatting, University Template Formatting, Deep Redraft and LaTeX Conversion.

**Implementation.** Keep model SDK calls server-side in small provider adapters. Model names are configuration. Control-flow outputs should use validated structured schemas; rewritten prose may be free text. Record model, prompt version, tokens, latency and estimated cost for every paid call, and bound retries. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is silent corruption of the paper, formatting or protected academic content. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R06 — Formatting-only jobs must not rewrite body prose.

**Implementation.** Use a source-independent internal DocumentModel with stable block identifiers. Preserve the uploaded source, patch DOCX selectively, and use deterministic document code for formatting. Reject scanned/encrypted/unsafe inputs rather than silently producing low-quality output. Protect citations, quotations, numerals and other locked spans. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is silent corruption of the paper, formatting or protected academic content. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R07 — Deep redraft must be an explicit higher-cost choice and must not be silently substituted for normal refinement.

**Implementation.** Keep model SDK calls server-side in small provider adapters. Model names are configuration. Control-flow outputs should use validated structured schemas; rewritten prose may be free text. Record model, prompt version, tokens, latency and estimated cost for every paid call, and bound retries. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is opaque model behaviour, semantic drift or unnecessary token use. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R08 — Features not production-ready must be hidden instead of exposed as partially working controls.

**Implementation.** Implement the smallest cohesive production-safe solution that satisfies this requirement. Keep business rules in one source of truth, avoid speculative abstractions, expose failures explicitly, and add a durable test or verification step where the behaviour can regress. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is ambiguity, duplicated logic or an unreliable user experience. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
# 3. Brand and Visual Direction

PaperAid should look like a serious paid writing SaaS product. The visual quality target is the clarity, whitespace and product-led presentation associated with leading writing assistants, while all branding, copy and composition remain distinctly PaperAid.

## Required outcomes

- Use PaperAid consistently as the product name in page titles, metadata, code-visible labels and marketing copy.
- Use a clean white and pale-green surface system with a confident green accent, dark neutral typography and restrained shadows.
- Create a small design-token system for colour, spacing, radii, type sizes and elevation instead of scattered visual values.
- The landing hero must show a realistic product interface rather than generic robot artwork.
- The interface must remain visually calm when showing many findings, with hierarchy, grouping and progressive disclosure.
- Do not copy Grammarly logos, exact wording, illustrations or pixel-identical layouts; imitate category quality rather than proprietary identity.
- Mobile composition must be intentionally designed rather than merely shrinking desktop panels.
- The first public beta should look credible enough that asking a student to pay does not feel premature.

## Detailed implementation requirements

### R01 — Use PaperAid consistently as the product name in page titles, metadata, code-visible labels and marketing copy.

**Implementation.** Implement this in the React + TypeScript + Vite frontend, using PaperAid design tokens and reusable components. Vite must bind to port 5000 in development. Keep mock data behind fixtures/adapters so visual work can be reviewed before Firebase and AI are connected. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is opaque model behaviour, semantic drift or unnecessary token use. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R02 — Use a clean white and pale-green surface system with a confident green accent, dark neutral typography and restrained shadows.

**Implementation.** Implement this in the React + TypeScript + Vite frontend, using PaperAid design tokens and reusable components. Vite must bind to port 5000 in development. Keep mock data behind fixtures/adapters so visual work can be reviewed before Firebase and AI are connected. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is opaque model behaviour, semantic drift or unnecessary token use. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R03 — Create a small design-token system for colour, spacing, radii, type sizes and elevation instead of scattered visual values.

**Implementation.** Implement this in the React + TypeScript + Vite frontend, using PaperAid design tokens and reusable components. Vite must bind to port 5000 in development. Keep mock data behind fixtures/adapters so visual work can be reviewed before Firebase and AI are connected. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is ambiguity, duplicated logic or an unreliable user experience. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R04 — The landing hero must show a realistic product interface rather than generic robot artwork.

**Implementation.** Implement this in the React + TypeScript + Vite frontend, using PaperAid design tokens and reusable components. Vite must bind to port 5000 in development. Keep mock data behind fixtures/adapters so visual work can be reviewed before Firebase and AI are connected. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is ambiguity, duplicated logic or an unreliable user experience. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R05 — The interface must remain visually calm when showing many findings, with hierarchy, grouping and progressive disclosure.

**Implementation.** Implement this in the React + TypeScript + Vite frontend, using PaperAid design tokens and reusable components. Vite must bind to port 5000 in development. Keep mock data behind fixtures/adapters so visual work can be reviewed before Firebase and AI are connected. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is opaque model behaviour, semantic drift or unnecessary token use. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R06 — Do not copy Grammarly logos, exact wording, illustrations or pixel-identical layouts; imitate category quality rather than proprietary identity.

**Implementation.** Implement this in the React + TypeScript + Vite frontend, using PaperAid design tokens and reusable components. Vite must bind to port 5000 in development. Keep mock data behind fixtures/adapters so visual work can be reviewed before Firebase and AI are connected. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is ambiguity, duplicated logic or an unreliable user experience. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R07 — Mobile composition must be intentionally designed rather than merely shrinking desktop panels.

**Implementation.** Implement this in the React + TypeScript + Vite frontend, using PaperAid design tokens and reusable components. Vite must bind to port 5000 in development. Keep mock data behind fixtures/adapters so visual work can be reviewed before Firebase and AI are connected. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is ambiguity, duplicated logic or an unreliable user experience. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R08 — The first public beta should look credible enough that asking a student to pay does not feel premature.

**Implementation.** Implement this in the React + TypeScript + Vite frontend, using PaperAid design tokens and reusable components. Vite must bind to port 5000 in development. Keep mock data behind fixtures/adapters so visual work can be reviewed before Firebase and AI are connected. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is ambiguity, duplicated logic or an unreliable user experience. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
# 4. Public Landing Page

The public landing page is the commercial front door and must explain what PaperAid does within seconds. Every section should answer a customer question rather than adding generic AI marketing filler.

## Required outcomes

- The hero must contain a concise headline, explanatory copy, primary upload CTA, secondary how-it-works CTA and a PaperAid product preview.
- The public navigation should remain short: Product, Features, Pricing, For Students, Resources, Sign in and Get started.
- The page must present the six core services in a compact feature section.
- The page must explain the four-step journey as Upload, Choose service, Pay and Download, with beta wording adjusted when payments are disabled.
- Public pricing cards may show indicative UGX bands, but the post-upload server quote is authoritative.
- Privacy, content-preservation and estimated-score disclaimers must be visible without dominating the page.
- The landing page must include proper page title, meta description, social metadata, heading hierarchy and favicon.
- Unauthenticated users clicking Upload must return to the intended new-job flow after authentication rather than landing aimlessly on a dashboard.

## Detailed implementation requirements

### R01 — The hero must contain a concise headline, explanatory copy, primary upload CTA, secondary how-it-works CTA and a PaperAid product preview.

**Implementation.** Implement this in the React + TypeScript + Vite frontend, using PaperAid design tokens and reusable components. Vite must bind to port 5000 in development. Keep mock data behind fixtures/adapters so visual work can be reviewed before Firebase and AI are connected. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is opaque model behaviour, semantic drift or unnecessary token use. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R02 — The public navigation should remain short: Product, Features, Pricing, For Students, Resources, Sign in and Get started.

**Implementation.** Implement this in the React + TypeScript + Vite frontend, using PaperAid design tokens and reusable components. Vite must bind to port 5000 in development. Keep mock data behind fixtures/adapters so visual work can be reviewed before Firebase and AI are connected. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is opaque model behaviour, semantic drift or unnecessary token use. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R03 — The page must present the six core services in a compact feature section.

**Implementation.** Implement this in the React + TypeScript + Vite frontend, using PaperAid design tokens and reusable components. Vite must bind to port 5000 in development. Keep mock data behind fixtures/adapters so visual work can be reviewed before Firebase and AI are connected. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is ambiguity, duplicated logic or an unreliable user experience. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R04 — The page must explain the four-step journey as Upload, Choose service, Pay and Download, with beta wording adjusted when payments are disabled.

**Implementation.** Implement this in the React + TypeScript + Vite frontend, using PaperAid design tokens and reusable components. Vite must bind to port 5000 in development. Keep mock data behind fixtures/adapters so visual work can be reviewed before Firebase and AI are connected. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is opaque model behaviour, semantic drift or unnecessary token use. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R05 — Public pricing cards may show indicative UGX bands, but the post-upload server quote is authoritative.

**Implementation.** Implement this in the React + TypeScript + Vite frontend, using PaperAid design tokens and reusable components. Vite must bind to port 5000 in development. Keep mock data behind fixtures/adapters so visual work can be reviewed before Firebase and AI are connected. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is unauthorised access to private documents, secrets or privileged state. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R06 — Privacy, content-preservation and estimated-score disclaimers must be visible without dominating the page.

**Implementation.** Implement this in the React + TypeScript + Vite frontend, using PaperAid design tokens and reusable components. Vite must bind to port 5000 in development. Keep mock data behind fixtures/adapters so visual work can be reviewed before Firebase and AI are connected. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is unauthorised access to private documents, secrets or privileged state. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R07 — The landing page must include proper page title, meta description, social metadata, heading hierarchy and favicon.

**Implementation.** Implement this in the React + TypeScript + Vite frontend, using PaperAid design tokens and reusable components. Vite must bind to port 5000 in development. Keep mock data behind fixtures/adapters so visual work can be reviewed before Firebase and AI are connected. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is ambiguity, duplicated logic or an unreliable user experience. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R08 — Unauthenticated users clicking Upload must return to the intended new-job flow after authentication rather than landing aimlessly on a dashboard.

**Implementation.** Implement this in the React + TypeScript + Vite frontend, using PaperAid design tokens and reusable components. Vite must bind to port 5000 in development. Keep mock data behind fixtures/adapters so visual work can be reviewed before Firebase and AI are connected. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is unauthorised access to private documents, secrets or privileged state. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
# 5. Early Visual Milestone on localhost:5000

The IDE must expose a polished, navigable version of PaperAid early so the visual direction can be reviewed before deep backend work. This is a risk-control milestone rather than a throwaway wireframe.

## Required outcomes

- Configure Vite to run the frontend on http://localhost:5000 by default.
- Before real Firebase and model integrations are required, build the landing page, authentication screens, dashboard, new-job flow, processing states, results, history and admin shell using realistic fixtures.
- The early UI must already be responsive and close to production visual quality, not a grey-box wireframe.
- Mock data must live behind fixtures or a small data adapter instead of being hard-coded throughout page components.
- Create representative mock states for queued, analysing, refining, formatting, completed and failed jobs.
- Backend work may continue after the early visual milestone is available; the system should remain runnable throughout implementation.
- Visual review must cover phone, tablet and desktop widths before backend coupling makes layout changes expensive.
- Loading, error, empty, disabled, focus and hover states must be designed during the visual milestone rather than left for final polish.

## Detailed implementation requirements

### R01 — Configure Vite to run the frontend on http://localhost:5000 by default.

**Implementation.** Implement this in the React + TypeScript + Vite frontend, using PaperAid design tokens and reusable components. Vite must bind to port 5000 in development. Keep mock data behind fixtures/adapters so visual work can be reviewed before Firebase and AI are connected. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is ambiguity, duplicated logic or an unreliable user experience. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R02 — Before real Firebase and model integrations are required, build the landing page, authentication screens, dashboard, new-job flow, processing states, results, history and admin shell using realistic fixtures.

**Implementation.** Implement this in the React + TypeScript + Vite frontend, using PaperAid design tokens and reusable components. Vite must bind to port 5000 in development. Keep mock data behind fixtures/adapters so visual work can be reviewed before Firebase and AI are connected. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is unauthorised access to private documents, secrets or privileged state. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R03 — The early UI must already be responsive and close to production visual quality, not a grey-box wireframe.

**Implementation.** Implement this in the React + TypeScript + Vite frontend, using PaperAid design tokens and reusable components. Vite must bind to port 5000 in development. Keep mock data behind fixtures/adapters so visual work can be reviewed before Firebase and AI are connected. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is ambiguity, duplicated logic or an unreliable user experience. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R04 — Mock data must live behind fixtures or a small data adapter instead of being hard-coded throughout page components.

**Implementation.** Implement this in the React + TypeScript + Vite frontend, using PaperAid design tokens and reusable components. Vite must bind to port 5000 in development. Keep mock data behind fixtures/adapters so visual work can be reviewed before Firebase and AI are connected. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is ambiguity, duplicated logic or an unreliable user experience. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R05 — Create representative mock states for queued, analysing, refining, formatting, completed and failed jobs.

**Implementation.** Implement this in the React + TypeScript + Vite frontend, using PaperAid design tokens and reusable components. Vite must bind to port 5000 in development. Keep mock data behind fixtures/adapters so visual work can be reviewed before Firebase and AI are connected. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is silent corruption of the paper, formatting or protected academic content. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R06 — Backend work may continue after the early visual milestone is available; the system should remain runnable throughout implementation.

**Implementation.** Implement this in the React + TypeScript + Vite frontend, using PaperAid design tokens and reusable components. Vite must bind to port 5000 in development. Keep mock data behind fixtures/adapters so visual work can be reviewed before Firebase and AI are connected. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is opaque model behaviour, semantic drift or unnecessary token use. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R07 — Visual review must cover phone, tablet and desktop widths before backend coupling makes layout changes expensive.

**Implementation.** Implement this in the React + TypeScript + Vite frontend, using PaperAid design tokens and reusable components. Vite must bind to port 5000 in development. Keep mock data behind fixtures/adapters so visual work can be reviewed before Firebase and AI are connected. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is ambiguity, duplicated logic or an unreliable user experience. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R08 — Loading, error, empty, disabled, focus and hover states must be designed during the visual milestone rather than left for final polish.

**Implementation.** Implement this in the React + TypeScript + Vite frontend, using PaperAid design tokens and reusable components. Vite must bind to port 5000 in development. Keep mock data behind fixtures/adapters so visual work can be reviewed before Firebase and AI are connected. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is duplicate processing, stuck jobs or uncontrolled provider spend. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
# 6. Application Routes and Information Architecture

The authenticated product should stay small and obvious. Routes must map to real user intentions and there should be one canonical place for a job rather than multiple competing detail pages.

## Required outcomes

- Provide public routes for home, features, pricing, privacy and authentication.
- Provide /app as the signed-in home with a prominent New paper job action and recent jobs.
- Provide /app/new for upload, optional guideline upload, service selection, quote and submit/payment preparation.
- Provide /app/jobs/:jobId as the canonical job page for queued, processing, failed and completed states.
- Provide /app/history with cursor-based pagination and simple filters instead of loading an unbounded history.
- Provide a small settings/account area for profile, retention preference and account deletion actions.
- Provide /admin only to verified admin users and enforce the restriction on the backend as well as in navigation.
- Refreshing an in-progress route must recover from persisted server state instead of losing the job.

## Detailed implementation requirements

### R01 — Provide public routes for home, features, pricing, privacy and authentication.

**Implementation.** Use the relevant Firebase managed service directly and keep ownership rules explicit. The browser may use Firebase client SDKs for permitted operations, while privileged state changes remain server-owned. Security rules and emulator deny-tests are part of the implementation, not optional documentation. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is unauthorised access to private documents, secrets or privileged state. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R02 — Provide /app as the signed-in home with a prominent New paper job action and recent jobs.

**Implementation.** Use a source-independent internal DocumentModel with stable block identifiers. Preserve the uploaded source, patch DOCX selectively, and use deterministic document code for formatting. Reject scanned/encrypted/unsafe inputs rather than silently producing low-quality output. Protect citations, quotations, numerals and other locked spans. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is silent corruption of the paper, formatting or protected academic content. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R03 — Provide /app/new for upload, optional guideline upload, service selection, quote and submit/payment preparation.

**Implementation.** Use a source-independent internal DocumentModel with stable block identifiers. Preserve the uploaded source, patch DOCX selectively, and use deterministic document code for formatting. Reject scanned/encrypted/unsafe inputs rather than silently producing low-quality output. Protect citations, quotations, numerals and other locked spans. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is silent corruption of the paper, formatting or protected academic content. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R04 — Provide /app/jobs/:jobId as the canonical job page for queued, processing, failed and completed states.

**Implementation.** Use Google Cloud Tasks as the production queue. Start with roughly five concurrent dispatched jobs, make the limit configurable, use OIDC-authenticated task delivery, and make enqueue/worker execution idempotent. Do not invent an in-memory production queue. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is silent corruption of the paper, formatting or protected academic content. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R05 — Provide /app/history with cursor-based pagination and simple filters instead of loading an unbounded history.

**Implementation.** Use a source-independent internal DocumentModel with stable block identifiers. Preserve the uploaded source, patch DOCX selectively, and use deterministic document code for formatting. Reject scanned/encrypted/unsafe inputs rather than silently producing low-quality output. Protect citations, quotations, numerals and other locked spans. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is silent corruption of the paper, formatting or protected academic content. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R06 — Provide a small settings/account area for profile, retention preference and account deletion actions.

**Implementation.** Use a source-independent internal DocumentModel with stable block identifiers. Preserve the uploaded source, patch DOCX selectively, and use deterministic document code for formatting. Reject scanned/encrypted/unsafe inputs rather than silently producing low-quality output. Protect citations, quotations, numerals and other locked spans. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is silent corruption of the paper, formatting or protected academic content. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R07 — Provide /admin only to verified admin users and enforce the restriction on the backend as well as in navigation.

**Implementation.** Use a source-independent internal DocumentModel with stable block identifiers. Preserve the uploaded source, patch DOCX selectively, and use deterministic document code for formatting. Reject scanned/encrypted/unsafe inputs rather than silently producing low-quality output. Protect citations, quotations, numerals and other locked spans. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is silent corruption of the paper, formatting or protected academic content. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R08 — Refreshing an in-progress route must recover from persisted server state instead of losing the job.

**Implementation.** Use a source-independent internal DocumentModel with stable block identifiers. Preserve the uploaded source, patch DOCX selectively, and use deterministic document code for formatting. Reject scanned/encrypted/unsafe inputs rather than silently producing low-quality output. Protect citations, quotations, numerals and other locked spans. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is silent corruption of the paper, formatting or protected academic content. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
# 7. Core User Journey from Upload to Delivery

The primary experience should feel like handing a paper to a competent service desk. The user does not manage prompts, tokens, providers or queue settings; they provide the paper, choose work, see the quote and receive the output.

## Required outcomes

- The user must be able to upload one primary paper and optionally one university guideline/template file.
- Client-side upload checks are convenience only; the backend or worker must repeat all security-sensitive validation.
- The system must inspect document metrics and compatible services before calculating the authoritative quote.
- When payments are enabled, only server-verified payment may release a job to processing; beta mode must use an explicit bypass state.
- Accepted jobs must be queued asynchronously so the browser never waits minutes on one processing HTTP request.
- Progress must use meaningful stages rather than a fake continuously moving percentage bar.
- The user must be able to close the browser and return later without affecting processing.
- The completed page must provide output downloads, summary of work performed, warnings, before/after information where relevant and retention information.

## Detailed implementation requirements

### R01 — The user must be able to upload one primary paper and optionally one university guideline/template file.

**Implementation.** Implement the smallest cohesive production-safe solution that satisfies this requirement. Keep business rules in one source of truth, avoid speculative abstractions, expose failures explicitly, and add a durable test or verification step where the behaviour can regress. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is ambiguity, duplicated logic or an unreliable user experience. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R02 — Client-side upload checks are convenience only; the backend or worker must repeat all security-sensitive validation.

**Implementation.** Fail closed. Verify Firebase identity and App Check where required, keep secrets in Google Secret Manager/Cloud Run secret bindings, validate ownership on every job operation, rate-limit expensive actions, and never log raw paper content or secret values. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is unauthorised access to private documents, secrets or privileged state. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R03 — The system must inspect document metrics and compatible services before calculating the authoritative quote.

**Implementation.** Use the relevant Firebase managed service directly and keep ownership rules explicit. The browser may use Firebase client SDKs for permitted operations, while privileged state changes remain server-owned. Security rules and emulator deny-tests are part of the implementation, not optional documentation. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is unauthorised access to private documents, secrets or privileged state. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R04 — When payments are enabled, only server-verified payment may release a job to processing; beta mode must use an explicit bypass state.

**Implementation.** Make this server-authoritative and versioned. The client may display values but must never choose the final amount or mark a payment successful. Store an immutable quote snapshot. Payments remain feature-flagged off until the non-payment product is stable. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is duplicate processing, stuck jobs or uncontrolled provider spend. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R05 — Accepted jobs must be queued asynchronously so the browser never waits minutes on one processing HTTP request.

**Implementation.** Use Google Cloud Tasks as the production queue. Start with roughly five concurrent dispatched jobs, make the limit configurable, use OIDC-authenticated task delivery, and make enqueue/worker execution idempotent. Do not invent an in-memory production queue. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is duplicate processing, stuck jobs or uncontrolled provider spend. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R06 — Progress must use meaningful stages rather than a fake continuously moving percentage bar.

**Implementation.** Implement the smallest cohesive production-safe solution that satisfies this requirement. Keep business rules in one source of truth, avoid speculative abstractions, expose failures explicitly, and add a durable test or verification step where the behaviour can regress. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is ambiguity, duplicated logic or an unreliable user experience. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R07 — The user must be able to close the browser and return later without affecting processing.

**Implementation.** Implement the smallest cohesive production-safe solution that satisfies this requirement. Keep business rules in one source of truth, avoid speculative abstractions, expose failures explicitly, and add a durable test or verification step where the behaviour can regress. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is ambiguity, duplicated logic or an unreliable user experience. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R08 — The completed page must provide output downloads, summary of work performed, warnings, before/after information where relevant and retention information.

**Implementation.** Use a source-independent internal DocumentModel with stable block identifiers. Preserve the uploaded source, patch DOCX selectively, and use deterministic document code for formatting. Reject scanned/encrypted/unsafe inputs rather than silently producing low-quality output. Protect citations, quotations, numerals and other locked spans. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is silent corruption of the paper, formatting or protected academic content. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
# 8. Service Catalogue and Compatibility

Services should be explicit capabilities with defined pipelines so pricing, state and output remain auditable. Bundles may exist in the UI but must decompose into known internal stages.

## Required outcomes

- AI Check must analyse and report without silently rewriting the source document.
- Check + Refine must analyse, selectively rewrite, independently audit and export a revised document.
- Academic Formatting must apply a configured academic preset without modifying body wording.
- University Template Formatting must parse an uploaded guideline into a structured formatting specification and apply it deterministically.
- Deep Redraft must perform higher-scope section-aware rewriting only after explicit user choice and a higher quote.
- LaTeX Conversion must generate a controlled .tex project and optional compiled PDF when safe and supported.
- A Full Paper Service may combine several capabilities but must still record which stages ran and what each stage cost.
- The service catalogue must support hiding unfinished services through configuration without leaving dead UI paths.

## Detailed implementation requirements

### R01 — AI Check must analyse and report without silently rewriting the source document.

**Implementation.** Keep model SDK calls server-side in small provider adapters. Model names are configuration. Control-flow outputs should use validated structured schemas; rewritten prose may be free text. Record model, prompt version, tokens, latency and estimated cost for every paid call, and bound retries. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is silent corruption of the paper, formatting or protected academic content. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R02 — Check + Refine must analyse, selectively rewrite, independently audit and export a revised document.

**Implementation.** Keep model SDK calls server-side in small provider adapters. Model names are configuration. Control-flow outputs should use validated structured schemas; rewritten prose may be free text. Record model, prompt version, tokens, latency and estimated cost for every paid call, and bound retries. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is silent corruption of the paper, formatting or protected academic content. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R03 — Academic Formatting must apply a configured academic preset without modifying body wording.

**Implementation.** Use a source-independent internal DocumentModel with stable block identifiers. Preserve the uploaded source, patch DOCX selectively, and use deterministic document code for formatting. Reject scanned/encrypted/unsafe inputs rather than silently producing low-quality output. Protect citations, quotations, numerals and other locked spans. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is silent corruption of the paper, formatting or protected academic content. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R04 — University Template Formatting must parse an uploaded guideline into a structured formatting specification and apply it deterministically.

**Implementation.** Use a source-independent internal DocumentModel with stable block identifiers. Preserve the uploaded source, patch DOCX selectively, and use deterministic document code for formatting. Reject scanned/encrypted/unsafe inputs rather than silently producing low-quality output. Protect citations, quotations, numerals and other locked spans. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is silent corruption of the paper, formatting or protected academic content. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R05 — Deep Redraft must perform higher-scope section-aware rewriting only after explicit user choice and a higher quote.

**Implementation.** Keep model SDK calls server-side in small provider adapters. Model names are configuration. Control-flow outputs should use validated structured schemas; rewritten prose may be free text. Record model, prompt version, tokens, latency and estimated cost for every paid call, and bound retries. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is opaque model behaviour, semantic drift or unnecessary token use. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R06 — LaTeX Conversion must generate a controlled .tex project and optional compiled PDF when safe and supported.

**Implementation.** Use a source-independent internal DocumentModel with stable block identifiers. Preserve the uploaded source, patch DOCX selectively, and use deterministic document code for formatting. Reject scanned/encrypted/unsafe inputs rather than silently producing low-quality output. Protect citations, quotations, numerals and other locked spans. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is silent corruption of the paper, formatting or protected academic content. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R07 — A Full Paper Service may combine several capabilities but must still record which stages ran and what each stage cost.

**Implementation.** Use structured Cloud Logging and a small operational admin surface. Store only metadata needed to diagnose jobs. Prefer high-signal operational metrics and avoid building a separate analytics platform or exposing paper content by default. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is ambiguity, duplicated logic or an unreliable user experience. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R08 — The service catalogue must support hiding unfinished services through configuration without leaving dead UI paths.

**Implementation.** Use structured Cloud Logging and a small operational admin surface. Store only metadata needed to diagnose jobs. Prefer high-signal operational metrics and avoid building a separate analytics platform or exposing paper content by default. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is ambiguity, duplicated logic or an unreliable user experience. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
# 9. AI-Likeness Analysis and Score Presentation

PaperAid may advertise an AI Check, but the result must be presented as an internal estimate rather than a definitive authorship determination. The product should be useful because it identifies patterns and passages, not because it pretends to reproduce a third-party detector.

## Required outcomes

- Label the score Estimated AI-likeness or an equally clear phrase everywhere it appears.
- Never label the result as a Turnitin score, guarantee a target third-party percentage or imply access to a proprietary detector model.
- Analyse text at stable paragraph/block level and return structured findings with reason codes and user-readable explanations.
- Down-weight or exclude bibliographies, long quotations, code-like content and table-heavy sections from the aggregate score where appropriate.
- Calculate the displayed document score deterministically from block-level findings and version the aggregation algorithm.
- Provide an uncertainty/confidence indication so very short or structurally unusual documents do not appear falsely precise.
- Retain before and after analysis snapshots when refinement is performed instead of overwriting the first result.
- Display a permanent concise disclaimer explaining false positives and disagreement between AI detectors.

## Detailed implementation requirements

### R01 — Label the score Estimated AI-likeness or an equally clear phrase everywhere it appears.

**Implementation.** Implement the smallest cohesive production-safe solution that satisfies this requirement. Keep business rules in one source of truth, avoid speculative abstractions, expose failures explicitly, and add a durable test or verification step where the behaviour can regress. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is opaque model behaviour, semantic drift or unnecessary token use. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R02 — Never label the result as a Turnitin score, guarantee a target third-party percentage or imply access to a proprietary detector model.

**Implementation.** Keep model SDK calls server-side in small provider adapters. Model names are configuration. Control-flow outputs should use validated structured schemas; rewritten prose may be free text. Record model, prompt version, tokens, latency and estimated cost for every paid call, and bound retries. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is opaque model behaviour, semantic drift or unnecessary token use. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R03 — Analyse text at stable paragraph/block level and return structured findings with reason codes and user-readable explanations.

**Implementation.** Implement the smallest cohesive production-safe solution that satisfies this requirement. Keep business rules in one source of truth, avoid speculative abstractions, expose failures explicitly, and add a durable test or verification step where the behaviour can regress. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is opaque model behaviour, semantic drift or unnecessary token use. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R04 — Down-weight or exclude bibliographies, long quotations, code-like content and table-heavy sections from the aggregate score where appropriate.

**Implementation.** Implement the smallest cohesive production-safe solution that satisfies this requirement. Keep business rules in one source of truth, avoid speculative abstractions, expose failures explicitly, and add a durable test or verification step where the behaviour can regress. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is opaque model behaviour, semantic drift or unnecessary token use. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R05 — Calculate the displayed document score deterministically from block-level findings and version the aggregation algorithm.

**Implementation.** Use a source-independent internal DocumentModel with stable block identifiers. Preserve the uploaded source, patch DOCX selectively, and use deterministic document code for formatting. Reject scanned/encrypted/unsafe inputs rather than silently producing low-quality output. Protect citations, quotations, numerals and other locked spans. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is silent corruption of the paper, formatting or protected academic content. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R06 — Provide an uncertainty/confidence indication so very short or structurally unusual documents do not appear falsely precise.

**Implementation.** Use a source-independent internal DocumentModel with stable block identifiers. Preserve the uploaded source, patch DOCX selectively, and use deterministic document code for formatting. Reject scanned/encrypted/unsafe inputs rather than silently producing low-quality output. Protect citations, quotations, numerals and other locked spans. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is silent corruption of the paper, formatting or protected academic content. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R07 — Retain before and after analysis snapshots when refinement is performed instead of overwriting the first result.

**Implementation.** Keep model SDK calls server-side in small provider adapters. Model names are configuration. Control-flow outputs should use validated structured schemas; rewritten prose may be free text. Record model, prompt version, tokens, latency and estimated cost for every paid call, and bound retries. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is opaque model behaviour, semantic drift or unnecessary token use. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R08 — Display a permanent concise disclaimer explaining false positives and disagreement between AI detectors.

**Implementation.** Keep model SDK calls server-side in small provider adapters. Model names are configuration. Control-flow outputs should use validated structured schemas; rewritten prose may be free text. Record model, prompt version, tokens, latency and estimated cost for every paid call, and bound retries. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is opaque model behaviour, semantic drift or unnecessary token use. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
# 10. Standard Refinement Workflow

Standard refinement is the main editing service. Its default behaviour is selective: improve passages that need work while preserving the student’s argument, source material, facts and untouched paragraphs.

## Required outcomes

- Candidate paragraphs for refinement must be selected from analysis findings and service intensity using deterministic thresholds.
- Normal refinement must not regenerate the complete paper by default.
- Provide the writing model enough outline and neighbouring context to preserve coherence without repeatedly resending the whole document when not necessary.
- Protect citations, quotations, URLs, numbers and other sensitive spans through placeholders and post-generation validation where appropriate.
- Retain a block-level original-to-revised mapping for diffing, audit and safe DOCX patching.
- Run an independent audit that checks meaning drift, altered numbers, missing citations, invented claims and broken transitions.
- Only failed blocks should enter targeted repair whenever possible, with one or two bounded repair attempts.
- If quality control still fails, the job must stop with a clear quality warning rather than deliver a polished but altered document.

## Detailed implementation requirements

### R01 — Candidate paragraphs for refinement must be selected from analysis findings and service intensity using deterministic thresholds.

**Implementation.** Keep model SDK calls server-side in small provider adapters. Model names are configuration. Control-flow outputs should use validated structured schemas; rewritten prose may be free text. Record model, prompt version, tokens, latency and estimated cost for every paid call, and bound retries. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is opaque model behaviour, semantic drift or unnecessary token use. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R02 — Normal refinement must not regenerate the complete paper by default.

**Implementation.** Keep model SDK calls server-side in small provider adapters. Model names are configuration. Control-flow outputs should use validated structured schemas; rewritten prose may be free text. Record model, prompt version, tokens, latency and estimated cost for every paid call, and bound retries. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is opaque model behaviour, semantic drift or unnecessary token use. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R03 — Provide the writing model enough outline and neighbouring context to preserve coherence without repeatedly resending the whole document when not necessary.

**Implementation.** Keep model SDK calls server-side in small provider adapters. Model names are configuration. Control-flow outputs should use validated structured schemas; rewritten prose may be free text. Record model, prompt version, tokens, latency and estimated cost for every paid call, and bound retries. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is silent corruption of the paper, formatting or protected academic content. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R04 — Protect citations, quotations, URLs, numbers and other sensitive spans through placeholders and post-generation validation where appropriate.

**Implementation.** Keep model SDK calls server-side in small provider adapters. Model names are configuration. Control-flow outputs should use validated structured schemas; rewritten prose may be free text. Record model, prompt version, tokens, latency and estimated cost for every paid call, and bound retries. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is silent corruption of the paper, formatting or protected academic content. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R05 — Retain a block-level original-to-revised mapping for diffing, audit and safe DOCX patching.

**Implementation.** Keep model SDK calls server-side in small provider adapters. Model names are configuration. Control-flow outputs should use validated structured schemas; rewritten prose may be free text. Record model, prompt version, tokens, latency and estimated cost for every paid call, and bound retries. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is silent corruption of the paper, formatting or protected academic content. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R06 — Run an independent audit that checks meaning drift, altered numbers, missing citations, invented claims and broken transitions.

**Implementation.** Keep model SDK calls server-side in small provider adapters. Model names are configuration. Control-flow outputs should use validated structured schemas; rewritten prose may be free text. Record model, prompt version, tokens, latency and estimated cost for every paid call, and bound retries. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is silent corruption of the paper, formatting or protected academic content. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R07 — Only failed blocks should enter targeted repair whenever possible, with one or two bounded repair attempts.

**Implementation.** Keep model SDK calls server-side in small provider adapters. Model names are configuration. Control-flow outputs should use validated structured schemas; rewritten prose may be free text. Record model, prompt version, tokens, latency and estimated cost for every paid call, and bound retries. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is opaque model behaviour, semantic drift or unnecessary token use. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R08 — If quality control still fails, the job must stop with a clear quality warning rather than deliver a polished but altered document.

**Implementation.** Keep model SDK calls server-side in small provider adapters. Model names are configuration. Control-flow outputs should use validated structured schemas; rewritten prose may be free text. Record model, prompt version, tokens, latency and estimated cost for every paid call, and bound retries. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is silent corruption of the paper, formatting or protected academic content. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
# 11. Deep Redraft Workflow

Deep redraft is for papers needing substantial structural and language-level intervention. Because the scope is materially larger than refinement, PaperAid must estimate the likely share of affected text, show the higher price, and preserve a clear plan and audit trail.

## Required outcomes

- Estimate redraft scope in broad bands or an approximate range before the user accepts the service.
- Create an internal section-by-section redraft plan before generating replacement prose.
- Chunk and rewrite by logical section boundaries rather than arbitrary token slices or isolated sentences.
- Preserve supplied facts, citations, data values and study details; do not invent sources, statistics or participant information.
- Keep section-level before/after artifacts so the final audit can compare the redraft with the source.
- Run an independent final audit on every deep-redraft job.
- Enforce a hard model-spend ceiling for deep redraft and count retries against the same budget.
- Summarise the scale of change and any unresolved warnings on the completed job page.

## Detailed implementation requirements

### R01 — Estimate redraft scope in broad bands or an approximate range before the user accepts the service.

**Implementation.** Keep model SDK calls server-side in small provider adapters. Model names are configuration. Control-flow outputs should use validated structured schemas; rewritten prose may be free text. Record model, prompt version, tokens, latency and estimated cost for every paid call, and bound retries. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is opaque model behaviour, semantic drift or unnecessary token use. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R02 — Create an internal section-by-section redraft plan before generating replacement prose.

**Implementation.** Keep model SDK calls server-side in small provider adapters. Model names are configuration. Control-flow outputs should use validated structured schemas; rewritten prose may be free text. Record model, prompt version, tokens, latency and estimated cost for every paid call, and bound retries. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is opaque model behaviour, semantic drift or unnecessary token use. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R03 — Chunk and rewrite by logical section boundaries rather than arbitrary token slices or isolated sentences.

**Implementation.** Keep model SDK calls server-side in small provider adapters. Model names are configuration. Control-flow outputs should use validated structured schemas; rewritten prose may be free text. Record model, prompt version, tokens, latency and estimated cost for every paid call, and bound retries. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is opaque model behaviour, semantic drift or unnecessary token use. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R04 — Preserve supplied facts, citations, data values and study details; do not invent sources, statistics or participant information.

**Implementation.** Keep model SDK calls server-side in small provider adapters. Model names are configuration. Control-flow outputs should use validated structured schemas; rewritten prose may be free text. Record model, prompt version, tokens, latency and estimated cost for every paid call, and bound retries. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is silent corruption of the paper, formatting or protected academic content. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R05 — Keep section-level before/after artifacts so the final audit can compare the redraft with the source.

**Implementation.** Keep model SDK calls server-side in small provider adapters. Model names are configuration. Control-flow outputs should use validated structured schemas; rewritten prose may be free text. Record model, prompt version, tokens, latency and estimated cost for every paid call, and bound retries. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is opaque model behaviour, semantic drift or unnecessary token use. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R06 — Run an independent final audit on every deep-redraft job.

**Implementation.** Keep model SDK calls server-side in small provider adapters. Model names are configuration. Control-flow outputs should use validated structured schemas; rewritten prose may be free text. Record model, prompt version, tokens, latency and estimated cost for every paid call, and bound retries. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is opaque model behaviour, semantic drift or unnecessary token use. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R07 — Enforce a hard model-spend ceiling for deep redraft and count retries against the same budget.

**Implementation.** Keep model SDK calls server-side in small provider adapters. Model names are configuration. Control-flow outputs should use validated structured schemas; rewritten prose may be free text. Record model, prompt version, tokens, latency and estimated cost for every paid call, and bound retries. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is opaque model behaviour, semantic drift or unnecessary token use. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R08 — Summarise the scale of change and any unresolved warnings on the completed job page.

**Implementation.** Keep model SDK calls server-side in small provider adapters. Model names are configuration. Control-flow outputs should use validated structured schemas; rewritten prose may be free text. Record model, prompt version, tokens, latency and estimated cost for every paid call, and bound retries. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is opaque model behaviour, semantic drift or unnecessary token use. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
# 12. University Guideline and Template Upload

A user may upload institutional formatting guidance or a template together with the paper. AI can interpret natural-language rules, but the actual formatter must consume a structured specification rather than repeatedly asking a model to style the document.

## Required outcomes

- Store the guideline/template as a distinct file role and never confuse it with the student paper.
- Extract text and useful document-style information from DOCX or text-based PDF guidelines.
- Convert detected requirements into a typed FormattingSpec covering page, typography, spacing, heading, numbering, pagination, caption and reference rules.
- Record source provenance or snippets for important extracted rules so ambiguous interpretations can be diagnosed.
- Detect conflicting instructions and flag them instead of silently applying contradictory values.
- Show a concise user-facing summary of the most important detected rules before expensive formatting work when practical.
- Design the FormattingSpec so later curated university presets can use the same deterministic formatter.
- Do not require users to review dozens of low-level fields; surface only material rules and warnings.

## Detailed implementation requirements

### R01 — Store the guideline/template as a distinct file role and never confuse it with the student paper.

**Implementation.** Implement the smallest cohesive production-safe solution that satisfies this requirement. Keep business rules in one source of truth, avoid speculative abstractions, expose failures explicitly, and add a durable test or verification step where the behaviour can regress. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is ambiguity, duplicated logic or an unreliable user experience. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R02 — Extract text and useful document-style information from DOCX or text-based PDF guidelines.

**Implementation.** Use a source-independent internal DocumentModel with stable block identifiers. Preserve the uploaded source, patch DOCX selectively, and use deterministic document code for formatting. Reject scanned/encrypted/unsafe inputs rather than silently producing low-quality output. Protect citations, quotations, numerals and other locked spans. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is silent corruption of the paper, formatting or protected academic content. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R03 — Convert detected requirements into a typed FormattingSpec covering page, typography, spacing, heading, numbering, pagination, caption and reference rules.

**Implementation.** Use a source-independent internal DocumentModel with stable block identifiers. Preserve the uploaded source, patch DOCX selectively, and use deterministic document code for formatting. Reject scanned/encrypted/unsafe inputs rather than silently producing low-quality output. Protect citations, quotations, numerals and other locked spans. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is silent corruption of the paper, formatting or protected academic content. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R04 — Record source provenance or snippets for important extracted rules so ambiguous interpretations can be diagnosed.

**Implementation.** Implement the smallest cohesive production-safe solution that satisfies this requirement. Keep business rules in one source of truth, avoid speculative abstractions, expose failures explicitly, and add a durable test or verification step where the behaviour can regress. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is ambiguity, duplicated logic or an unreliable user experience. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R05 — Detect conflicting instructions and flag them instead of silently applying contradictory values.

**Implementation.** Implement the smallest cohesive production-safe solution that satisfies this requirement. Keep business rules in one source of truth, avoid speculative abstractions, expose failures explicitly, and add a durable test or verification step where the behaviour can regress. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is ambiguity, duplicated logic or an unreliable user experience. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R06 — Show a concise user-facing summary of the most important detected rules before expensive formatting work when practical.

**Implementation.** Use a source-independent internal DocumentModel with stable block identifiers. Preserve the uploaded source, patch DOCX selectively, and use deterministic document code for formatting. Reject scanned/encrypted/unsafe inputs rather than silently producing low-quality output. Protect citations, quotations, numerals and other locked spans. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is silent corruption of the paper, formatting or protected academic content. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R07 — Design the FormattingSpec so later curated university presets can use the same deterministic formatter.

**Implementation.** Use a source-independent internal DocumentModel with stable block identifiers. Preserve the uploaded source, patch DOCX selectively, and use deterministic document code for formatting. Reject scanned/encrypted/unsafe inputs rather than silently producing low-quality output. Protect citations, quotations, numerals and other locked spans. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is silent corruption of the paper, formatting or protected academic content. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R08 — Do not require users to review dozens of low-level fields; surface only material rules and warnings.

**Implementation.** Implement the smallest cohesive production-safe solution that satisfies this requirement. Keep business rules in one source of truth, avoid speculative abstractions, expose failures explicitly, and add a durable test or verification step where the behaviour can regress. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is ambiguity, duplicated logic or an unreliable user experience. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
# 13. Deterministic Academic Formatting Engine

Once formatting rules are known, PaperAid should apply them with deterministic document code. This protects content, lowers model cost and makes output repeatable. AI interprets rules; code performs layout.

## Required outcomes

- Use python-docx for ordinary DOCX operations and targeted OOXML only for capabilities python-docx does not expose cleanly.
- Prefer named Word styles such as Normal, Title, Heading 1–3, Caption and References over thousands of direct-format overrides.
- Apply page size, margins, orientation and section rules while preserving intentional section exceptions such as landscape tables.
- Apply line spacing, paragraph spacing and indentation through paragraph/style properties rather than inserting blank paragraphs.
- Map recognised headings to a consistent hierarchy and prepare a valid table-of-contents structure.
- Support preliminary Roman page numbering and main Arabic numbering when the FormattingSpec requests it.
- Formatting-only jobs must preserve body text, verified through text checksum/diff rules that ignore legitimate field changes.
- Representative formatted DOCX fixtures must be rendered visually during QA to catch layout issues that text-only tests cannot see.

## Detailed implementation requirements

### R01 — Use python-docx for ordinary DOCX operations and targeted OOXML only for capabilities python-docx does not expose cleanly.

**Implementation.** Use a source-independent internal DocumentModel with stable block identifiers. Preserve the uploaded source, patch DOCX selectively, and use deterministic document code for formatting. Reject scanned/encrypted/unsafe inputs rather than silently producing low-quality output. Protect citations, quotations, numerals and other locked spans. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is silent corruption of the paper, formatting or protected academic content. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R02 — Prefer named Word styles such as Normal, Title, Heading 1–3, Caption and References over thousands of direct-format overrides.

**Implementation.** Use a source-independent internal DocumentModel with stable block identifiers. Preserve the uploaded source, patch DOCX selectively, and use deterministic document code for formatting. Reject scanned/encrypted/unsafe inputs rather than silently producing low-quality output. Protect citations, quotations, numerals and other locked spans. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is silent corruption of the paper, formatting or protected academic content. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R03 — Apply page size, margins, orientation and section rules while preserving intentional section exceptions such as landscape tables.

**Implementation.** Use a source-independent internal DocumentModel with stable block identifiers. Preserve the uploaded source, patch DOCX selectively, and use deterministic document code for formatting. Reject scanned/encrypted/unsafe inputs rather than silently producing low-quality output. Protect citations, quotations, numerals and other locked spans. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is silent corruption of the paper, formatting or protected academic content. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R04 — Apply line spacing, paragraph spacing and indentation through paragraph/style properties rather than inserting blank paragraphs.

**Implementation.** Use a source-independent internal DocumentModel with stable block identifiers. Preserve the uploaded source, patch DOCX selectively, and use deterministic document code for formatting. Reject scanned/encrypted/unsafe inputs rather than silently producing low-quality output. Protect citations, quotations, numerals and other locked spans. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is silent corruption of the paper, formatting or protected academic content. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R05 — Map recognised headings to a consistent hierarchy and prepare a valid table-of-contents structure.

**Implementation.** Use a source-independent internal DocumentModel with stable block identifiers. Preserve the uploaded source, patch DOCX selectively, and use deterministic document code for formatting. Reject scanned/encrypted/unsafe inputs rather than silently producing low-quality output. Protect citations, quotations, numerals and other locked spans. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is silent corruption of the paper, formatting or protected academic content. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R06 — Support preliminary Roman page numbering and main Arabic numbering when the FormattingSpec requests it.

**Implementation.** Use a source-independent internal DocumentModel with stable block identifiers. Preserve the uploaded source, patch DOCX selectively, and use deterministic document code for formatting. Reject scanned/encrypted/unsafe inputs rather than silently producing low-quality output. Protect citations, quotations, numerals and other locked spans. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is silent corruption of the paper, formatting or protected academic content. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R07 — Formatting-only jobs must preserve body text, verified through text checksum/diff rules that ignore legitimate field changes.

**Implementation.** Use a source-independent internal DocumentModel with stable block identifiers. Preserve the uploaded source, patch DOCX selectively, and use deterministic document code for formatting. Reject scanned/encrypted/unsafe inputs rather than silently producing low-quality output. Protect citations, quotations, numerals and other locked spans. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is silent corruption of the paper, formatting or protected academic content. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R08 — Representative formatted DOCX fixtures must be rendered visually during QA to catch layout issues that text-only tests cannot see.

**Implementation.** Implement this in the React + TypeScript + Vite frontend, using PaperAid design tokens and reusable components. Vite must bind to port 5000 in development. Keep mock data behind fixtures/adapters so visual work can be reviewed before Firebase and AI are connected. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is silent corruption of the paper, formatting or protected academic content. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
# 14. LaTeX Conversion

LaTeX conversion is a premium export capability, not the centre of the MVP. It must be deterministic and security-conscious so document conversion does not become a remote-code-execution path.

## Required outcomes

- Do not execute arbitrary user-uploaded LaTeX source in the MVP.
- Generate LaTeX from PaperAid-controlled source conversion or the internal DocumentModel.
- Use a pinned Pandoc version or another deterministic converter for DOCX-to-LaTeX where it reduces complexity.
- If compiled PDF is offered, use a constrained compiler such as Tectonic with shell escape disabled and without unnecessary network access.
- Normalise extracted asset filenames and keep all generated files inside an isolated job directory.
- Do not fabricate BibTeX metadata that cannot be derived safely; preserve a formatted references section when structured bibliography data is unavailable.
- Treat compilation failure as a recoverable output condition when a useful .tex package can still be delivered.
- Clearly warn users that complex Word-only layouts may not map perfectly to LaTeX.

## Detailed implementation requirements

### R01 — Do not execute arbitrary user-uploaded LaTeX source in the MVP.

**Implementation.** Use a source-independent internal DocumentModel with stable block identifiers. Preserve the uploaded source, patch DOCX selectively, and use deterministic document code for formatting. Reject scanned/encrypted/unsafe inputs rather than silently producing low-quality output. Protect citations, quotations, numerals and other locked spans. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is silent corruption of the paper, formatting or protected academic content. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R02 — Generate LaTeX from PaperAid-controlled source conversion or the internal DocumentModel.

**Implementation.** Keep model SDK calls server-side in small provider adapters. Model names are configuration. Control-flow outputs should use validated structured schemas; rewritten prose may be free text. Record model, prompt version, tokens, latency and estimated cost for every paid call, and bound retries. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is silent corruption of the paper, formatting or protected academic content. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R03 — Use a pinned Pandoc version or another deterministic converter for DOCX-to-LaTeX where it reduces complexity.

**Implementation.** Use a source-independent internal DocumentModel with stable block identifiers. Preserve the uploaded source, patch DOCX selectively, and use deterministic document code for formatting. Reject scanned/encrypted/unsafe inputs rather than silently producing low-quality output. Protect citations, quotations, numerals and other locked spans. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is silent corruption of the paper, formatting or protected academic content. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R04 — If compiled PDF is offered, use a constrained compiler such as Tectonic with shell escape disabled and without unnecessary network access.

**Implementation.** Use a source-independent internal DocumentModel with stable block identifiers. Preserve the uploaded source, patch DOCX selectively, and use deterministic document code for formatting. Reject scanned/encrypted/unsafe inputs rather than silently producing low-quality output. Protect citations, quotations, numerals and other locked spans. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is silent corruption of the paper, formatting or protected academic content. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R05 — Normalise extracted asset filenames and keep all generated files inside an isolated job directory.

**Implementation.** Use a source-independent internal DocumentModel with stable block identifiers. Preserve the uploaded source, patch DOCX selectively, and use deterministic document code for formatting. Reject scanned/encrypted/unsafe inputs rather than silently producing low-quality output. Protect citations, quotations, numerals and other locked spans. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is silent corruption of the paper, formatting or protected academic content. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R06 — Do not fabricate BibTeX metadata that cannot be derived safely; preserve a formatted references section when structured bibliography data is unavailable.

**Implementation.** Use a source-independent internal DocumentModel with stable block identifiers. Preserve the uploaded source, patch DOCX selectively, and use deterministic document code for formatting. Reject scanned/encrypted/unsafe inputs rather than silently producing low-quality output. Protect citations, quotations, numerals and other locked spans. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is silent corruption of the paper, formatting or protected academic content. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R07 — Treat compilation failure as a recoverable output condition when a useful .tex package can still be delivered.

**Implementation.** Use a source-independent internal DocumentModel with stable block identifiers. Preserve the uploaded source, patch DOCX selectively, and use deterministic document code for formatting. Reject scanned/encrypted/unsafe inputs rather than silently producing low-quality output. Protect citations, quotations, numerals and other locked spans. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is silent corruption of the paper, formatting or protected academic content. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R08 — Clearly warn users that complex Word-only layouts may not map perfectly to LaTeX.

**Implementation.** Use a source-independent internal DocumentModel with stable block identifiers. Preserve the uploaded source, patch DOCX selectively, and use deterministic document code for formatting. Reject scanned/encrypted/unsafe inputs rather than silently producing low-quality output. Protect citations, quotations, numerals and other locked spans. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is silent corruption of the paper, formatting or protected academic content. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
# 15. Pricing and Quote Engine

Pricing should be transparent to users but authoritative on the backend. The system does not need algorithmic dynamic pricing; it needs simple, versioned rules that reflect paper length, selected work and rewrite scope.

## Required outcomes

- Calculate authoritative quotes on the server and ignore any client-submitted final amount.
- Use document metrics such as word count, page estimate and selected services as quote inputs.
- Use simple service base fees or multipliers and broad rewrite-intensity bands rather than unstable one-percent pricing differences.
- Store the pricing version and all quote inputs on an immutable quote snapshot.
- Expire quotes after a defined period and issue a new quote if job scope changes.
- Keep a public indicative price band for marketing separate from the authoritative post-upload quote.
- Continue generating quotes while PAYMENTS_ENABLED is false so the business model is tested during beta.
- Keep the pricing formula in one backend module with unit tests and never duplicate it in frontend components.

## Detailed implementation requirements

### R01 — Calculate authoritative quotes on the server and ignore any client-submitted final amount.

**Implementation.** Use the relevant Firebase managed service directly and keep ownership rules explicit. The browser may use Firebase client SDKs for permitted operations, while privileged state changes remain server-owned. Security rules and emulator deny-tests are part of the implementation, not optional documentation. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is unauthorised access to private documents, secrets or privileged state. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R02 — Use document metrics such as word count, page estimate and selected services as quote inputs.

**Implementation.** Use a source-independent internal DocumentModel with stable block identifiers. Preserve the uploaded source, patch DOCX selectively, and use deterministic document code for formatting. Reject scanned/encrypted/unsafe inputs rather than silently producing low-quality output. Protect citations, quotations, numerals and other locked spans. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is silent corruption of the paper, formatting or protected academic content. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R03 — Use simple service base fees or multipliers and broad rewrite-intensity bands rather than unstable one-percent pricing differences.

**Implementation.** Make this server-authoritative and versioned. The client may display values but must never choose the final amount or mark a payment successful. Store an immutable quote snapshot. Payments remain feature-flagged off until the non-payment product is stable. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is ambiguity, duplicated logic or an unreliable user experience. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R04 — Store the pricing version and all quote inputs on an immutable quote snapshot.

**Implementation.** Make this server-authoritative and versioned. The client may display values but must never choose the final amount or mark a payment successful. Store an immutable quote snapshot. Payments remain feature-flagged off until the non-payment product is stable. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is ambiguity, duplicated logic or an unreliable user experience. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R05 — Expire quotes after a defined period and issue a new quote if job scope changes.

**Implementation.** Make this server-authoritative and versioned. The client may display values but must never choose the final amount or mark a payment successful. Store an immutable quote snapshot. Payments remain feature-flagged off until the non-payment product is stable. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is ambiguity, duplicated logic or an unreliable user experience. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R06 — Keep a public indicative price band for marketing separate from the authoritative post-upload quote.

**Implementation.** Use the relevant Firebase managed service directly and keep ownership rules explicit. The browser may use Firebase client SDKs for permitted operations, while privileged state changes remain server-owned. Security rules and emulator deny-tests are part of the implementation, not optional documentation. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is unauthorised access to private documents, secrets or privileged state. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R07 — Continue generating quotes while PAYMENTS_ENABLED is false so the business model is tested during beta.

**Implementation.** Keep model SDK calls server-side in small provider adapters. Model names are configuration. Control-flow outputs should use validated structured schemas; rewritten prose may be free text. Record model, prompt version, tokens, latency and estimated cost for every paid call, and bound retries. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is opaque model behaviour, semantic drift or unnecessary token use. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R08 — Keep the pricing formula in one backend module with unit tests and never duplicate it in frontend components.

**Implementation.** Implement this in the React + TypeScript + Vite frontend, using PaperAid design tokens and reusable components. Vite must bind to port 5000 in development. Keep mock data behind fixtures/adapters so visual work can be reviewed before Firebase and AI are connected. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is ambiguity, duplicated logic or an unreliable user experience. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
# 16. Approved Firebase-Centred Architecture

PaperAid will remain on a Firebase-centred Google Cloud stack. This is sufficient for the expected launch scale, reduces operational surfaces and allows managed authentication, files, metadata, queueing, hosting and container execution without a second cloud provider.

## Required outcomes

- Use React + TypeScript + Vite for the frontend and host the production build on Firebase Hosting.
- Use Firebase Authentication for identity and Cloud Firestore for operational metadata.
- Use Firebase/Google Cloud Storage for uploaded papers, guideline files and generated outputs.
- Use Firebase App Check as an additional anti-abuse signal on protected browser-facing endpoints.
- Use one coherent Python FastAPI backend deployed to Cloud Run for trusted business rules, document processing and model orchestration.
- Use Google Cloud Tasks as the production queue for asynchronous paper jobs.
- Use Google Secret Manager or Cloud Run secret bindings for OpenAI, Anthropic and future payment credentials.
- Do not add Render, PostgreSQL, Redis, Kubernetes, Kafka, RabbitMQ or a microservice fleet unless later measurements demonstrate a concrete need.

## Detailed implementation requirements

### R01 — Use React + TypeScript + Vite for the frontend and host the production build on Firebase Hosting.

**Implementation.** Implement this in the React + TypeScript + Vite frontend, using PaperAid design tokens and reusable components. Vite must bind to port 5000 in development. Keep mock data behind fixtures/adapters so visual work can be reviewed before Firebase and AI are connected. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is ambiguity, duplicated logic or an unreliable user experience. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R02 — Use Firebase Authentication for identity and Cloud Firestore for operational metadata.

**Implementation.** Use the relevant Firebase managed service directly and keep ownership rules explicit. The browser may use Firebase client SDKs for permitted operations, while privileged state changes remain server-owned. Security rules and emulator deny-tests are part of the implementation, not optional documentation. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is unauthorised access to private documents, secrets or privileged state. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R03 — Use Firebase/Google Cloud Storage for uploaded papers, guideline files and generated outputs.

**Implementation.** Use the relevant Firebase managed service directly and keep ownership rules explicit. The browser may use Firebase client SDKs for permitted operations, while privileged state changes remain server-owned. Security rules and emulator deny-tests are part of the implementation, not optional documentation. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is ambiguity, duplicated logic or an unreliable user experience. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R04 — Use Firebase App Check as an additional anti-abuse signal on protected browser-facing endpoints.

**Implementation.** Use the relevant Firebase managed service directly and keep ownership rules explicit. The browser may use Firebase client SDKs for permitted operations, while privileged state changes remain server-owned. Security rules and emulator deny-tests are part of the implementation, not optional documentation. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is ambiguity, duplicated logic or an unreliable user experience. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R05 — Use one coherent Python FastAPI backend deployed to Cloud Run for trusted business rules, document processing and model orchestration.

**Implementation.** Use the relevant Firebase managed service directly and keep ownership rules explicit. The browser may use Firebase client SDKs for permitted operations, while privileged state changes remain server-owned. Security rules and emulator deny-tests are part of the implementation, not optional documentation. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is silent corruption of the paper, formatting or protected academic content. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R06 — Use Google Cloud Tasks as the production queue for asynchronous paper jobs.

**Implementation.** Use the relevant Firebase managed service directly and keep ownership rules explicit. The browser may use Firebase client SDKs for permitted operations, while privileged state changes remain server-owned. Security rules and emulator deny-tests are part of the implementation, not optional documentation. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is duplicate processing, stuck jobs or uncontrolled provider spend. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R07 — Use Google Secret Manager or Cloud Run secret bindings for OpenAI, Anthropic and future payment credentials.

**Implementation.** Use the relevant Firebase managed service directly and keep ownership rules explicit. The browser may use Firebase client SDKs for permitted operations, while privileged state changes remain server-owned. Security rules and emulator deny-tests are part of the implementation, not optional documentation. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is unauthorised access to private documents, secrets or privileged state. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R08 — Do not add Render, PostgreSQL, Redis, Kubernetes, Kafka, RabbitMQ or a microservice fleet unless later measurements demonstrate a concrete need.

**Implementation.** Use the relevant Firebase managed service directly and keep ownership rules explicit. The browser may use Firebase client SDKs for permitted operations, while privileged state changes remain server-owned. Security rules and emulator deny-tests are part of the implementation, not optional documentation. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is ambiguity, duplicated logic or an unreliable user experience. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
# 17. Repository Structure and Engineering Boundaries

The codebase should be one straightforward repository containing the web application, Python backend and Firebase/cloud configuration. Folder boundaries should reflect real deployable or domain concerns, not architecture fashion.

## Required outcomes

- Use a root layout with web, backend, firebase/config, scripts and docs areas rather than a monorepo framework.
- Organise frontend code by feature plus a small shared UI layer; avoid one giant components directory or dozens of micro-packages.
- Organise backend code around api, jobs, documents, ai, formatting, pricing, security, integrations and core configuration.
- Keep HTTP route handlers thin and keep document manipulation or prompt strings out of route modules.
- Keep OpenAI and Anthropic SDK-specific code inside small provider adapters.
- Keep prompts and structured-output schemas version controlled and grouped by task.
- Do not create a helper, class or file when it does not improve naming, reuse, testing or separation of a genuine responsibility.
- The final repository tree must remain navigable enough that a competent engineer can trace a job end to end without searching hundreds of files.

## Detailed implementation requirements

### R01 — Use a root layout with web, backend, firebase/config, scripts and docs areas rather than a monorepo framework.

**Implementation.** Use the relevant Firebase managed service directly and keep ownership rules explicit. The browser may use Firebase client SDKs for permitted operations, while privileged state changes remain server-owned. Security rules and emulator deny-tests are part of the implementation, not optional documentation. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is ambiguity, duplicated logic or an unreliable user experience. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R02 — Organise frontend code by feature plus a small shared UI layer; avoid one giant components directory or dozens of micro-packages.

**Implementation.** Implement this in the React + TypeScript + Vite frontend, using PaperAid design tokens and reusable components. Vite must bind to port 5000 in development. Keep mock data behind fixtures/adapters so visual work can be reviewed before Firebase and AI are connected. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is ambiguity, duplicated logic or an unreliable user experience. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R03 — Organise backend code around api, jobs, documents, ai, formatting, pricing, security, integrations and core configuration.

**Implementation.** Use a source-independent internal DocumentModel with stable block identifiers. Preserve the uploaded source, patch DOCX selectively, and use deterministic document code for formatting. Reject scanned/encrypted/unsafe inputs rather than silently producing low-quality output. Protect citations, quotations, numerals and other locked spans. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is unauthorised access to private documents, secrets or privileged state. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R04 — Keep HTTP route handlers thin and keep document manipulation or prompt strings out of route modules.

**Implementation.** Keep model SDK calls server-side in small provider adapters. Model names are configuration. Control-flow outputs should use validated structured schemas; rewritten prose may be free text. Record model, prompt version, tokens, latency and estimated cost for every paid call, and bound retries. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is silent corruption of the paper, formatting or protected academic content. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R05 — Keep OpenAI and Anthropic SDK-specific code inside small provider adapters.

**Implementation.** Keep model SDK calls server-side in small provider adapters. Model names are configuration. Control-flow outputs should use validated structured schemas; rewritten prose may be free text. Record model, prompt version, tokens, latency and estimated cost for every paid call, and bound retries. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is opaque model behaviour, semantic drift or unnecessary token use. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R06 — Keep prompts and structured-output schemas version controlled and grouped by task.

**Implementation.** Keep model SDK calls server-side in small provider adapters. Model names are configuration. Control-flow outputs should use validated structured schemas; rewritten prose may be free text. Record model, prompt version, tokens, latency and estimated cost for every paid call, and bound retries. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is opaque model behaviour, semantic drift or unnecessary token use. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R07 — Do not create a helper, class or file when it does not improve naming, reuse, testing or separation of a genuine responsibility.

**Implementation.** Test at the lowest sensible layer: unit tests for deterministic rules, Firebase Emulator tests for access rules, document fixtures for preservation, mocked-provider contract tests for AI flows, Playwright for the critical user journey, and a ten-job concurrency/load exercise before launch. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is ambiguity, duplicated logic or an unreliable user experience. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R08 — The final repository tree must remain navigable enough that a competent engineer can trace a job end to end without searching hundreds of files.

**Implementation.** Implement the smallest cohesive production-safe solution that satisfies this requirement. Keep business rules in one source of truth, avoid speculative abstractions, expose failures explicitly, and add a durable test or verification step where the behaviour can regress. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is opaque model behaviour, semantic drift or unnecessary token use. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
# 18. Local Development and Developer Experience

Local development must be repeatable, safe and fast enough for an IDE agent to iterate without production credentials. The user specifically needs the visible application early at localhost:5000.

## Required outcomes

- Provide a documented bootstrap sequence for web and backend dependencies.
- Run the frontend on port 5000 and the local backend on a separate documented port with a Vite /api proxy.
- Provide .env.example files containing variable names but never real secrets.
- Provide deterministic mock OpenAI and Anthropic adapters so the complete UI and workflow can be exercised without provider spend.
- Use Firebase Emulator Suite for Auth, Firestore and Storage tests where practical, but do not block the first static visual milestone on emulator setup.
- Provide small synthetic seed data covering new user, recent jobs, queue, processing, completed and failed states.
- Keep production-only App Check and service-account requirements explicitly bypassed only under controlled local configuration.
- The README must state the exact commands needed to reach http://localhost:5000 from a fresh checkout.

## Detailed implementation requirements

### R01 — Provide a documented bootstrap sequence for web and backend dependencies.

**Implementation.** Use a source-independent internal DocumentModel with stable block identifiers. Preserve the uploaded source, patch DOCX selectively, and use deterministic document code for formatting. Reject scanned/encrypted/unsafe inputs rather than silently producing low-quality output. Protect citations, quotations, numerals and other locked spans. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is silent corruption of the paper, formatting or protected academic content. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R02 — Run the frontend on port 5000 and the local backend on a separate documented port with a Vite /api proxy.

**Implementation.** Implement this in the React + TypeScript + Vite frontend, using PaperAid design tokens and reusable components. Vite must bind to port 5000 in development. Keep mock data behind fixtures/adapters so visual work can be reviewed before Firebase and AI are connected. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is silent corruption of the paper, formatting or protected academic content. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R03 — Provide .env.example files containing variable names but never real secrets.

**Implementation.** Fail closed. Verify Firebase identity and App Check where required, keep secrets in Google Secret Manager/Cloud Run secret bindings, validate ownership on every job operation, rate-limit expensive actions, and never log raw paper content or secret values. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is unauthorised access to private documents, secrets or privileged state. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R04 — Provide deterministic mock OpenAI and Anthropic adapters so the complete UI and workflow can be exercised without provider spend.

**Implementation.** Keep model SDK calls server-side in small provider adapters. Model names are configuration. Control-flow outputs should use validated structured schemas; rewritten prose may be free text. Record model, prompt version, tokens, latency and estimated cost for every paid call, and bound retries. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is opaque model behaviour, semantic drift or unnecessary token use. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R05 — Use Firebase Emulator Suite for Auth, Firestore and Storage tests where practical, but do not block the first static visual milestone on emulator setup.

**Implementation.** Implement this in the React + TypeScript + Vite frontend, using PaperAid design tokens and reusable components. Vite must bind to port 5000 in development. Keep mock data behind fixtures/adapters so visual work can be reviewed before Firebase and AI are connected. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is unauthorised access to private documents, secrets or privileged state. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R06 — Provide small synthetic seed data covering new user, recent jobs, queue, processing, completed and failed states.

**Implementation.** Use Google Cloud Tasks as the production queue. Start with roughly five concurrent dispatched jobs, make the limit configurable, use OIDC-authenticated task delivery, and make enqueue/worker execution idempotent. Do not invent an in-memory production queue. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is duplicate processing, stuck jobs or uncontrolled provider spend. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R07 — Keep production-only App Check and service-account requirements explicitly bypassed only under controlled local configuration.

**Implementation.** Implement the smallest cohesive production-safe solution that satisfies this requirement. Keep business rules in one source of truth, avoid speculative abstractions, expose failures explicitly, and add a durable test or verification step where the behaviour can regress. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is ambiguity, duplicated logic or an unreliable user experience. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R08 — The README must state the exact commands needed to reach http://localhost:5000 from a fresh checkout.

**Implementation.** Implement this in the React + TypeScript + Vite frontend, using PaperAid design tokens and reusable components. Vite must bind to port 5000 in development. Keep mock data behind fixtures/adapters so visual work can be reviewed before Firebase and AI are connected. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is duplicate processing, stuck jobs or uncontrolled provider spend. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
# 19. Authentication and Account Model

Identity should be delegated to Firebase Authentication. PaperAid needs only a minimal account model and must not collect unnecessary personal information merely because it can.

## Required outcomes

- Support email/password initially and optionally Google sign-in if desired.
- Use Firebase UID as the canonical ownership key across jobs and Storage paths.
- Create a minimal profile record on first authenticated use with only fields needed for the product.
- Verify Firebase ID tokens on every protected backend endpoint rather than trusting client user identifiers.
- Use Firebase custom claims for admin authorization and do not let a user-controlled profile field grant admin rights.
- Use Firebase-managed session/token refresh instead of building a custom JWT system.
- Design account deletion to remove or schedule deletion of jobs and stored files rather than deleting only the Auth record.
- Authentication errors must return a recoverable sign-in experience without leaking whether another user owns a requested job.

## Detailed implementation requirements

### R01 — Support email/password initially and optionally Google sign-in if desired.

**Implementation.** Use the relevant Firebase managed service directly and keep ownership rules explicit. The browser may use Firebase client SDKs for permitted operations, while privileged state changes remain server-owned. Security rules and emulator deny-tests are part of the implementation, not optional documentation. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is unauthorised access to private documents, secrets or privileged state. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R02 — Use Firebase UID as the canonical ownership key across jobs and Storage paths.

**Implementation.** Use the relevant Firebase managed service directly and keep ownership rules explicit. The browser may use Firebase client SDKs for permitted operations, while privileged state changes remain server-owned. Security rules and emulator deny-tests are part of the implementation, not optional documentation. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is unauthorised access to private documents, secrets or privileged state. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R03 — Create a minimal profile record on first authenticated use with only fields needed for the product.

**Implementation.** Use the relevant Firebase managed service directly and keep ownership rules explicit. The browser may use Firebase client SDKs for permitted operations, while privileged state changes remain server-owned. Security rules and emulator deny-tests are part of the implementation, not optional documentation. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is unauthorised access to private documents, secrets or privileged state. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R04 — Verify Firebase ID tokens on every protected backend endpoint rather than trusting client user identifiers.

**Implementation.** Use the relevant Firebase managed service directly and keep ownership rules explicit. The browser may use Firebase client SDKs for permitted operations, while privileged state changes remain server-owned. Security rules and emulator deny-tests are part of the implementation, not optional documentation. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is unauthorised access to private documents, secrets or privileged state. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R05 — Use Firebase custom claims for admin authorization and do not let a user-controlled profile field grant admin rights.

**Implementation.** Use the relevant Firebase managed service directly and keep ownership rules explicit. The browser may use Firebase client SDKs for permitted operations, while privileged state changes remain server-owned. Security rules and emulator deny-tests are part of the implementation, not optional documentation. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is unauthorised access to private documents, secrets or privileged state. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R06 — Use Firebase-managed session/token refresh instead of building a custom JWT system.

**Implementation.** Use the relevant Firebase managed service directly and keep ownership rules explicit. The browser may use Firebase client SDKs for permitted operations, while privileged state changes remain server-owned. Security rules and emulator deny-tests are part of the implementation, not optional documentation. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is unauthorised access to private documents, secrets or privileged state. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R07 — Design account deletion to remove or schedule deletion of jobs and stored files rather than deleting only the Auth record.

**Implementation.** Use the relevant Firebase managed service directly and keep ownership rules explicit. The browser may use Firebase client SDKs for permitted operations, while privileged state changes remain server-owned. Security rules and emulator deny-tests are part of the implementation, not optional documentation. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is unauthorised access to private documents, secrets or privileged state. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R08 — Authentication errors must return a recoverable sign-in experience without leaking whether another user owns a requested job.

**Implementation.** Use the relevant Firebase managed service directly and keep ownership rules explicit. The browser may use Firebase client SDKs for permitted operations, while privileged state changes remain server-owned. Security rules and emulator deny-tests are part of the implementation, not optional documentation. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is unauthorised access to private documents, secrets or privileged state. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
# 20. Firestore Data Model

Firestore stores job and account metadata, not complete paper bodies. The model should directly support the queries the product actually uses and should avoid deeply nested structures or unbounded arrays.

## Required outcomes

- Use users/{uid} for minimal profiles and a top-level jobs/{jobId} collection containing ownerUid for operational queries.
- The job document must be the source of truth for owner, service selection, state, quote, file references, progress, output references, costs and safe failure metadata.
- Ordinary clients may read owned job metadata but must not directly write privileged state, paid status, quote amount or completion fields.
- Use server timestamps for important lifecycle transitions and immutable identifiers for quotes and jobs.
- Store large analysis artifacts or extracted text in Storage or bounded subcollections instead of exceeding Firestore document limits.
- Create only indexes required by real queries such as ownerUid plus createdAt/status.
- Use a small config collection for pricing/public limits if runtime configuration is needed, with server-controlled writes and safe defaults in code.
- If user-facing job events are stored, keep them bounded and free of raw paper content.

## Detailed implementation requirements

### R01 — Use users/{uid} for minimal profiles and a top-level jobs/{jobId} collection containing ownerUid for operational queries.

**Implementation.** Use the relevant Firebase managed service directly and keep ownership rules explicit. The browser may use Firebase client SDKs for permitted operations, while privileged state changes remain server-owned. Security rules and emulator deny-tests are part of the implementation, not optional documentation. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is opaque model behaviour, semantic drift or unnecessary token use. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R02 — The job document must be the source of truth for owner, service selection, state, quote, file references, progress, output references, costs and safe failure metadata.

**Implementation.** Use the relevant Firebase managed service directly and keep ownership rules explicit. The browser may use Firebase client SDKs for permitted operations, while privileged state changes remain server-owned. Security rules and emulator deny-tests are part of the implementation, not optional documentation. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is silent corruption of the paper, formatting or protected academic content. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R03 — Ordinary clients may read owned job metadata but must not directly write privileged state, paid status, quote amount or completion fields.

**Implementation.** Use the relevant Firebase managed service directly and keep ownership rules explicit. The browser may use Firebase client SDKs for permitted operations, while privileged state changes remain server-owned. Security rules and emulator deny-tests are part of the implementation, not optional documentation. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is duplicate processing, stuck jobs or uncontrolled provider spend. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R04 — Use server timestamps for important lifecycle transitions and immutable identifiers for quotes and jobs.

**Implementation.** Use the relevant Firebase managed service directly and keep ownership rules explicit. The browser may use Firebase client SDKs for permitted operations, while privileged state changes remain server-owned. Security rules and emulator deny-tests are part of the implementation, not optional documentation. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is opaque model behaviour, semantic drift or unnecessary token use. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R05 — Store large analysis artifacts or extracted text in Storage or bounded subcollections instead of exceeding Firestore document limits.

**Implementation.** Use the relevant Firebase managed service directly and keep ownership rules explicit. The browser may use Firebase client SDKs for permitted operations, while privileged state changes remain server-owned. Security rules and emulator deny-tests are part of the implementation, not optional documentation. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is silent corruption of the paper, formatting or protected academic content. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R06 — Create only indexes required by real queries such as ownerUid plus createdAt/status.

**Implementation.** Use the relevant Firebase managed service directly and keep ownership rules explicit. The browser may use Firebase client SDKs for permitted operations, while privileged state changes remain server-owned. Security rules and emulator deny-tests are part of the implementation, not optional documentation. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is opaque model behaviour, semantic drift or unnecessary token use. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R07 — Use a small config collection for pricing/public limits if runtime configuration is needed, with server-controlled writes and safe defaults in code.

**Implementation.** Use the relevant Firebase managed service directly and keep ownership rules explicit. The browser may use Firebase client SDKs for permitted operations, while privileged state changes remain server-owned. Security rules and emulator deny-tests are part of the implementation, not optional documentation. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is opaque model behaviour, semantic drift or unnecessary token use. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R08 — If user-facing job events are stored, keep them bounded and free of raw paper content.

**Implementation.** Use the relevant Firebase managed service directly and keep ownership rules explicit. The browser may use Firebase client SDKs for permitted operations, while privileged state changes remain server-owned. Security rules and emulator deny-tests are part of the implementation, not optional documentation. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is opaque model behaviour, semantic drift or unnecessary token use. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
# 21. Storage Layout and Retention

Academic files are sensitive assets. Storage layout must make ownership obvious, make cleanup simple and keep temporary or generated copies from becoming an uncontrolled shadow archive.

## Required outcomes

- Use predictable job-scoped paths containing the authenticated UID and job ID for input, guideline, output and internal artifacts.
- Do not use the user-supplied filename as the storage object identifier; retain it only as safe display metadata.
- Use Firebase Storage rules to limit ordinary users to their own permitted paths and repeat security-sensitive validation in the backend.
- Download each job into its own temporary Cloud Run working directory and delete that workspace after completion or failure cleanup.
- Never modify the uploaded source object in place; generated output must be a new object.
- Define a configurable default retention period such as 30 days and store expiresAt metadata where useful.
- Provide explicit user deletion for eligible completed/failed jobs and make deletion idempotent.
- Never log signed URLs, raw file contents or sensitive extracted text.

## Detailed implementation requirements

### R01 — Use predictable job-scoped paths containing the authenticated UID and job ID for input, guideline, output and internal artifacts.

**Implementation.** Use the relevant Firebase managed service directly and keep ownership rules explicit. The browser may use Firebase client SDKs for permitted operations, while privileged state changes remain server-owned. Security rules and emulator deny-tests are part of the implementation, not optional documentation. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is unauthorised access to private documents, secrets or privileged state. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R02 — Do not use the user-supplied filename as the storage object identifier; retain it only as safe display metadata.

**Implementation.** Use the relevant Firebase managed service directly and keep ownership rules explicit. The browser may use Firebase client SDKs for permitted operations, while privileged state changes remain server-owned. Security rules and emulator deny-tests are part of the implementation, not optional documentation. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is opaque model behaviour, semantic drift or unnecessary token use. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R03 — Use Firebase Storage rules to limit ordinary users to their own permitted paths and repeat security-sensitive validation in the backend.

**Implementation.** Use the relevant Firebase managed service directly and keep ownership rules explicit. The browser may use Firebase client SDKs for permitted operations, while privileged state changes remain server-owned. Security rules and emulator deny-tests are part of the implementation, not optional documentation. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is unauthorised access to private documents, secrets or privileged state. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R04 — Download each job into its own temporary Cloud Run working directory and delete that workspace after completion or failure cleanup.

**Implementation.** Use the relevant Firebase managed service directly and keep ownership rules explicit. The browser may use Firebase client SDKs for permitted operations, while privileged state changes remain server-owned. Security rules and emulator deny-tests are part of the implementation, not optional documentation. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is opaque model behaviour, semantic drift or unnecessary token use. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R05 — Never modify the uploaded source object in place; generated output must be a new object.

**Implementation.** Use the relevant Firebase managed service directly and keep ownership rules explicit. The browser may use Firebase client SDKs for permitted operations, while privileged state changes remain server-owned. Security rules and emulator deny-tests are part of the implementation, not optional documentation. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is ambiguity, duplicated logic or an unreliable user experience. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R06 — Define a configurable default retention period such as 30 days and store expiresAt metadata where useful.

**Implementation.** Use the relevant Firebase managed service directly and keep ownership rules explicit. The browser may use Firebase client SDKs for permitted operations, while privileged state changes remain server-owned. Security rules and emulator deny-tests are part of the implementation, not optional documentation. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is ambiguity, duplicated logic or an unreliable user experience. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R07 — Provide explicit user deletion for eligible completed/failed jobs and make deletion idempotent.

**Implementation.** Use the relevant Firebase managed service directly and keep ownership rules explicit. The browser may use Firebase client SDKs for permitted operations, while privileged state changes remain server-owned. Security rules and emulator deny-tests are part of the implementation, not optional documentation. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is opaque model behaviour, semantic drift or unnecessary token use. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R08 — Never log signed URLs, raw file contents or sensitive extracted text.

**Implementation.** Use the relevant Firebase managed service directly and keep ownership rules explicit. The browser may use Firebase client SDKs for permitted operations, while privileged state changes remain server-owned. Security rules and emulator deny-tests are part of the implementation, not optional documentation. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is ambiguity, duplicated logic or an unreliable user experience. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
# 22. Cloud Run FastAPI Backend

The backend is one coherent Python FastAPI application. It owns trusted business rules, authorization, quoting, queue dispatch, document processing and model orchestration. Routes must remain thin and domain logic must be testable without HTTP.

## Required outcomes

- Use FastAPI with Pydantic v2 request/response schemas and explicit domain enums.
- Centralise Firebase token verification and App Check verification in reusable dependencies rather than copying auth logic across routes.
- Keep the public API intentionally small: quotes, jobs, job detail/cancel/delete, admin operations and internal task callbacks.
- Move expensive document/model processing into queued worker execution rather than holding a browser HTTP request open for minutes.
- Use request correlation IDs and structured JSON logs on every backend request and worker invocation.
- Validate identifiers, service combinations and payloads before business logic runs and return safe 4xx errors for bad input.
- Keep business services independent of FastAPI request objects so pricing, state transitions and job rules can be unit-tested directly.
- Expose lightweight health/readiness endpoints that never call paid AI providers.

## Detailed implementation requirements

### R01 — Use FastAPI with Pydantic v2 request/response schemas and explicit domain enums.

**Implementation.** Implement the smallest cohesive production-safe solution that satisfies this requirement. Keep business rules in one source of truth, avoid speculative abstractions, expose failures explicitly, and add a durable test or verification step where the behaviour can regress. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is opaque model behaviour, semantic drift or unnecessary token use. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R02 — Centralise Firebase token verification and App Check verification in reusable dependencies rather than copying auth logic across routes.

**Implementation.** Use the relevant Firebase managed service directly and keep ownership rules explicit. The browser may use Firebase client SDKs for permitted operations, while privileged state changes remain server-owned. Security rules and emulator deny-tests are part of the implementation, not optional documentation. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is unauthorised access to private documents, secrets or privileged state. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R03 — Keep the public API intentionally small: quotes, jobs, job detail/cancel/delete, admin operations and internal task callbacks.

**Implementation.** Make this server-authoritative and versioned. The client may display values but must never choose the final amount or mark a payment successful. Store an immutable quote snapshot. Payments remain feature-flagged off until the non-payment product is stable. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is opaque model behaviour, semantic drift or unnecessary token use. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R04 — Move expensive document/model processing into queued worker execution rather than holding a browser HTTP request open for minutes.

**Implementation.** Use Google Cloud Tasks as the production queue. Start with roughly five concurrent dispatched jobs, make the limit configurable, use OIDC-authenticated task delivery, and make enqueue/worker execution idempotent. Do not invent an in-memory production queue. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is silent corruption of the paper, formatting or protected academic content. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R05 — Use request correlation IDs and structured JSON logs on every backend request and worker invocation.

**Implementation.** Use structured Cloud Logging and a small operational admin surface. Store only metadata needed to diagnose jobs. Prefer high-signal operational metrics and avoid building a separate analytics platform or exposing paper content by default. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is ambiguity, duplicated logic or an unreliable user experience. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R06 — Validate identifiers, service combinations and payloads before business logic runs and return safe 4xx errors for bad input.

**Implementation.** Use structured Cloud Logging and a small operational admin surface. Store only metadata needed to diagnose jobs. Prefer high-signal operational metrics and avoid building a separate analytics platform or exposing paper content by default. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is ambiguity, duplicated logic or an unreliable user experience. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R07 — Keep business services independent of FastAPI request objects so pricing, state transitions and job rules can be unit-tested directly.

**Implementation.** Test at the lowest sensible layer: unit tests for deterministic rules, Firebase Emulator tests for access rules, document fixtures for preservation, mocked-provider contract tests for AI flows, Playwright for the critical user journey, and a ten-job concurrency/load exercise before launch. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is duplicate processing, stuck jobs or uncontrolled provider spend. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R08 — Expose lightweight health/readiness endpoints that never call paid AI providers.

**Implementation.** Keep model SDK calls server-side in small provider adapters. Model names are configuration. Control-flow outputs should use validated structured schemas; rewritten prose may be free text. Record model, prompt version, tokens, latency and estimated cost for every paid call, and bound retries. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is opaque model behaviour, semantic drift or unnecessary token use. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
# 23. Cloud Tasks Queue and Concurrency

Cloud Tasks is the pressure regulator between customer submissions and expensive paper processing. PaperAid should accept bursts but only dispatch a controlled number of active jobs until real telemetry supports more.

## Required outcomes

- Create a dedicated Cloud Tasks queue for paper-processing jobs.
- Start with approximately five concurrent dispatched jobs and keep the dispatch limit configurable so it can later rise toward ten or more.
- Use deterministic task names or a persisted queue token so duplicate submit/enqueue operations are harmless.
- Authenticate task delivery to the internal worker endpoint with a dedicated service account/OIDC identity.
- Classify retryable provider/network errors separately from permanent user/document errors before allowing Cloud Tasks to retry.
- Use exponential backoff with bounded attempts and avoid nested retry storms between SDK and queue layers.
- Acquire a job-level state lock/transaction before expensive work so duplicate task delivery cannot create two active workflows.
- Represent queued state honestly in the UI and allow the user to close the page; do not promise an exact wait time the platform cannot know.

## Detailed implementation requirements

### R01 — Create a dedicated Cloud Tasks queue for paper-processing jobs.

**Implementation.** Use Google Cloud Tasks as the production queue. Start with roughly five concurrent dispatched jobs, make the limit configurable, use OIDC-authenticated task delivery, and make enqueue/worker execution idempotent. Do not invent an in-memory production queue. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is duplicate processing, stuck jobs or uncontrolled provider spend. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R02 — Start with approximately five concurrent dispatched jobs and keep the dispatch limit configurable so it can later rise toward ten or more.

**Implementation.** Use Google Cloud Tasks as the production queue. Start with roughly five concurrent dispatched jobs, make the limit configurable, use OIDC-authenticated task delivery, and make enqueue/worker execution idempotent. Do not invent an in-memory production queue. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is duplicate processing, stuck jobs or uncontrolled provider spend. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R03 — Use deterministic task names or a persisted queue token so duplicate submit/enqueue operations are harmless.

**Implementation.** Use Google Cloud Tasks as the production queue. Start with roughly five concurrent dispatched jobs, make the limit configurable, use OIDC-authenticated task delivery, and make enqueue/worker execution idempotent. Do not invent an in-memory production queue. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is duplicate processing, stuck jobs or uncontrolled provider spend. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R04 — Authenticate task delivery to the internal worker endpoint with a dedicated service account/OIDC identity.

**Implementation.** Use the relevant Firebase managed service directly and keep ownership rules explicit. The browser may use Firebase client SDKs for permitted operations, while privileged state changes remain server-owned. Security rules and emulator deny-tests are part of the implementation, not optional documentation. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is unauthorised access to private documents, secrets or privileged state. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R05 — Classify retryable provider/network errors separately from permanent user/document errors before allowing Cloud Tasks to retry.

**Implementation.** Use Google Cloud Tasks as the production queue. Start with roughly five concurrent dispatched jobs, make the limit configurable, use OIDC-authenticated task delivery, and make enqueue/worker execution idempotent. Do not invent an in-memory production queue. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is silent corruption of the paper, formatting or protected academic content. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R06 — Use exponential backoff with bounded attempts and avoid nested retry storms between SDK and queue layers.

**Implementation.** Use Google Cloud Tasks as the production queue. Start with roughly five concurrent dispatched jobs, make the limit configurable, use OIDC-authenticated task delivery, and make enqueue/worker execution idempotent. Do not invent an in-memory production queue. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is duplicate processing, stuck jobs or uncontrolled provider spend. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R07 — Acquire a job-level state lock/transaction before expensive work so duplicate task delivery cannot create two active workflows.

**Implementation.** Use Google Cloud Tasks as the production queue. Start with roughly five concurrent dispatched jobs, make the limit configurable, use OIDC-authenticated task delivery, and make enqueue/worker execution idempotent. Do not invent an in-memory production queue. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is duplicate processing, stuck jobs or uncontrolled provider spend. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R08 — Represent queued state honestly in the UI and allow the user to close the page; do not promise an exact wait time the platform cannot know.

**Implementation.** Use Google Cloud Tasks as the production queue. Start with roughly five concurrent dispatched jobs, make the limit configurable, use OIDC-authenticated task delivery, and make enqueue/worker execution idempotent. Do not invent an in-memory production queue. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is duplicate processing, stuck jobs or uncontrolled provider spend. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
# 24. Job State Machine and Progress

The job state machine is the central anti-spaghetti mechanism for the workflow. State transitions must be explicit, legal and testable rather than being arbitrary strings set in many functions.

## Required outcomes

- Define one processing-state enum containing draft/uploaded/quoted/payment/queued and the relevant processing/terminal states.
- Keep payment state logically separate enough that a paid job can later fail processing without becoming unpaid.
- Define allowed state transitions in one module and reject illegal transitions with a domain error.
- Persist meaningful timestamps for creation, queue, start, completion and failure rather than logging every tiny internal step to Firestore.
- Use stage names such as extracting, analysing, refining, redrafting, formatting, auditing and exporting only when the selected service actually runs them.
- Store a short user-facing status message separately from technical error detail.
- Represent retryable failure and final failure distinctly so operations and UI can behave correctly.
- Cancellation must be state-aware and idempotent, and completed jobs must be effectively immutable except for retention/deletion metadata.

## Detailed implementation requirements

### R01 — Define one processing-state enum containing draft/uploaded/quoted/payment/queued and the relevant processing/terminal states.

**Implementation.** Use Google Cloud Tasks as the production queue. Start with roughly five concurrent dispatched jobs, make the limit configurable, use OIDC-authenticated task delivery, and make enqueue/worker execution idempotent. Do not invent an in-memory production queue. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is duplicate processing, stuck jobs or uncontrolled provider spend. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R02 — Keep payment state logically separate enough that a paid job can later fail processing without becoming unpaid.

**Implementation.** Make this server-authoritative and versioned. The client may display values but must never choose the final amount or mark a payment successful. Store an immutable quote snapshot. Payments remain feature-flagged off until the non-payment product is stable. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is duplicate processing, stuck jobs or uncontrolled provider spend. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R03 — Define allowed state transitions in one module and reject illegal transitions with a domain error.

**Implementation.** Implement the smallest cohesive production-safe solution that satisfies this requirement. Keep business rules in one source of truth, avoid speculative abstractions, expose failures explicitly, and add a durable test or verification step where the behaviour can regress. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is duplicate processing, stuck jobs or uncontrolled provider spend. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R04 — Persist meaningful timestamps for creation, queue, start, completion and failure rather than logging every tiny internal step to Firestore.

**Implementation.** Use the relevant Firebase managed service directly and keep ownership rules explicit. The browser may use Firebase client SDKs for permitted operations, while privileged state changes remain server-owned. Security rules and emulator deny-tests are part of the implementation, not optional documentation. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is duplicate processing, stuck jobs or uncontrolled provider spend. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R05 — Use stage names such as extracting, analysing, refining, redrafting, formatting, auditing and exporting only when the selected service actually runs them.

**Implementation.** Keep model SDK calls server-side in small provider adapters. Model names are configuration. Control-flow outputs should use validated structured schemas; rewritten prose may be free text. Record model, prompt version, tokens, latency and estimated cost for every paid call, and bound retries. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is silent corruption of the paper, formatting or protected academic content. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R06 — Store a short user-facing status message separately from technical error detail.

**Implementation.** Fail closed. Verify Firebase identity and App Check where required, keep secrets in Google Secret Manager/Cloud Run secret bindings, validate ownership on every job operation, rate-limit expensive actions, and never log raw paper content or secret values. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is duplicate processing, stuck jobs or uncontrolled provider spend. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R07 — Represent retryable failure and final failure distinctly so operations and UI can behave correctly.

**Implementation.** Use Google Cloud Tasks as the production queue. Start with roughly five concurrent dispatched jobs, make the limit configurable, use OIDC-authenticated task delivery, and make enqueue/worker execution idempotent. Do not invent an in-memory production queue. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is duplicate processing, stuck jobs or uncontrolled provider spend. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R08 — Cancellation must be state-aware and idempotent, and completed jobs must be effectively immutable except for retention/deletion metadata.

**Implementation.** Implement the smallest cohesive production-safe solution that satisfies this requirement. Keep business rules in one source of truth, avoid speculative abstractions, expose failures explicitly, and add a durable test or verification step where the behaviour can regress. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is duplicate processing, stuck jobs or uncontrolled provider spend. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
# 25. Internal Document Model and Extraction

PaperAid needs one structured representation between raw files and AI operations. The DocumentModel should preserve logical order and block identity without forcing the rest of the system to manipulate Word XML or plain unstructured text.

## Required outcomes

- Represent the paper as ordered blocks with stable IDs and block types such as heading, paragraph, list item, table cell, caption and reference.
- Retain source metadata sufficient to map revised blocks back into the original DOCX without rebuilding unchanged content.
- Walk DOCX paragraphs and tables in source order and retain paragraph style and relevant run-level information.
- Extract text and page boundaries from text-based PDF and detect very low text yield as a likely scanned document.
- Build a heading-based outline for context and section-aware chunking, with a conservative fallback for papers with weak heading structure.
- Detect protected spans such as inline citations, quotations, URLs, important numerals and named source markers before rewriting.
- Never alter the source file in place; create a working copy and separate final output.
- Use section-aware chunking for documents that exceed comfortable model context rather than arbitrary character slicing.

## Detailed implementation requirements

### R01 — Represent the paper as ordered blocks with stable IDs and block types such as heading, paragraph, list item, table cell, caption and reference.

**Implementation.** Keep model SDK calls server-side in small provider adapters. Model names are configuration. Control-flow outputs should use validated structured schemas; rewritten prose may be free text. Record model, prompt version, tokens, latency and estimated cost for every paid call, and bound retries. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is silent corruption of the paper, formatting or protected academic content. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R02 — Retain source metadata sufficient to map revised blocks back into the original DOCX without rebuilding unchanged content.

**Implementation.** Keep model SDK calls server-side in small provider adapters. Model names are configuration. Control-flow outputs should use validated structured schemas; rewritten prose may be free text. Record model, prompt version, tokens, latency and estimated cost for every paid call, and bound retries. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is silent corruption of the paper, formatting or protected academic content. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R03 — Walk DOCX paragraphs and tables in source order and retain paragraph style and relevant run-level information.

**Implementation.** Keep model SDK calls server-side in small provider adapters. Model names are configuration. Control-flow outputs should use validated structured schemas; rewritten prose may be free text. Record model, prompt version, tokens, latency and estimated cost for every paid call, and bound retries. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is silent corruption of the paper, formatting or protected academic content. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R04 — Extract text and page boundaries from text-based PDF and detect very low text yield as a likely scanned document.

**Implementation.** Keep model SDK calls server-side in small provider adapters. Model names are configuration. Control-flow outputs should use validated structured schemas; rewritten prose may be free text. Record model, prompt version, tokens, latency and estimated cost for every paid call, and bound retries. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is silent corruption of the paper, formatting or protected academic content. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R05 — Build a heading-based outline for context and section-aware chunking, with a conservative fallback for papers with weak heading structure.

**Implementation.** Keep model SDK calls server-side in small provider adapters. Model names are configuration. Control-flow outputs should use validated structured schemas; rewritten prose may be free text. Record model, prompt version, tokens, latency and estimated cost for every paid call, and bound retries. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is silent corruption of the paper, formatting or protected academic content. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R06 — Detect protected spans such as inline citations, quotations, URLs, important numerals and named source markers before rewriting.

**Implementation.** Keep model SDK calls server-side in small provider adapters. Model names are configuration. Control-flow outputs should use validated structured schemas; rewritten prose may be free text. Record model, prompt version, tokens, latency and estimated cost for every paid call, and bound retries. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is silent corruption of the paper, formatting or protected academic content. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R07 — Never alter the source file in place; create a working copy and separate final output.

**Implementation.** Keep model SDK calls server-side in small provider adapters. Model names are configuration. Control-flow outputs should use validated structured schemas; rewritten prose may be free text. Record model, prompt version, tokens, latency and estimated cost for every paid call, and bound retries. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is silent corruption of the paper, formatting or protected academic content. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R08 — Use section-aware chunking for documents that exceed comfortable model context rather than arbitrary character slicing.

**Implementation.** Keep model SDK calls server-side in small provider adapters. Model names are configuration. Control-flow outputs should use validated structured schemas; rewritten prose may be free text. Record model, prompt version, tokens, latency and estimated cost for every paid call, and bound retries. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is silent corruption of the paper, formatting or protected academic content. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
# 26. AI Provider Layer and Model Configuration

PaperAid should use official OpenAI and Anthropic SDKs directly behind a small provider boundary. It does not need a general agent framework. The pipeline is explicit: analysis/plan, writing or refinement, independent audit, targeted repair when needed.

## Required outcomes

- Keep OpenAI-specific and Anthropic-specific SDK calls inside small provider modules.
- Keep model IDs in server configuration, with separate model settings for analysis/planning, writing, audit and repair as needed.
- The premium default may use GPT-6 Sol for analysis/audit and Claude Opus 5.5 for writing/refinement, but business logic must not hard-code these names.
- Record provider, model, prompt version, input/output/cached token counts where available, latency and estimated cost for every paid call.
- Set explicit provider timeouts and classify timeout/rate-limit/server errors for bounded retry behaviour.
- Do not introduce LangChain, LangGraph or another agent orchestration framework for the initial workflow.
- Provider SDK objects must not leak into Firestore/document modules; orchestration should receive validated provider-neutral results.
- Provide a deterministic mock provider implementation for local development and CI.

## Detailed implementation requirements

### R01 — Keep OpenAI-specific and Anthropic-specific SDK calls inside small provider modules.

**Implementation.** Keep model SDK calls server-side in small provider adapters. Model names are configuration. Control-flow outputs should use validated structured schemas; rewritten prose may be free text. Record model, prompt version, tokens, latency and estimated cost for every paid call, and bound retries. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is opaque model behaviour, semantic drift or unnecessary token use. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R02 — Keep model IDs in server configuration, with separate model settings for analysis/planning, writing, audit and repair as needed.

**Implementation.** Keep model SDK calls server-side in small provider adapters. Model names are configuration. Control-flow outputs should use validated structured schemas; rewritten prose may be free text. Record model, prompt version, tokens, latency and estimated cost for every paid call, and bound retries. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is opaque model behaviour, semantic drift or unnecessary token use. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R03 — The premium default may use GPT-6 Sol for analysis/audit and Claude Opus 5.5 for writing/refinement, but business logic must not hard-code these names.

**Implementation.** Keep model SDK calls server-side in small provider adapters. Model names are configuration. Control-flow outputs should use validated structured schemas; rewritten prose may be free text. Record model, prompt version, tokens, latency and estimated cost for every paid call, and bound retries. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is opaque model behaviour, semantic drift or unnecessary token use. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R04 — Record provider, model, prompt version, input/output/cached token counts where available, latency and estimated cost for every paid call.

**Implementation.** Keep model SDK calls server-side in small provider adapters. Model names are configuration. Control-flow outputs should use validated structured schemas; rewritten prose may be free text. Record model, prompt version, tokens, latency and estimated cost for every paid call, and bound retries. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is opaque model behaviour, semantic drift or unnecessary token use. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R05 — Set explicit provider timeouts and classify timeout/rate-limit/server errors for bounded retry behaviour.

**Implementation.** Use Google Cloud Tasks as the production queue. Start with roughly five concurrent dispatched jobs, make the limit configurable, use OIDC-authenticated task delivery, and make enqueue/worker execution idempotent. Do not invent an in-memory production queue. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is duplicate processing, stuck jobs or uncontrolled provider spend. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R06 — Do not introduce LangChain, LangGraph or another agent orchestration framework for the initial workflow.

**Implementation.** Keep model SDK calls server-side in small provider adapters. Model names are configuration. Control-flow outputs should use validated structured schemas; rewritten prose may be free text. Record model, prompt version, tokens, latency and estimated cost for every paid call, and bound retries. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is opaque model behaviour, semantic drift or unnecessary token use. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R07 — Provider SDK objects must not leak into Firestore/document modules; orchestration should receive validated provider-neutral results.

**Implementation.** Use the relevant Firebase managed service directly and keep ownership rules explicit. The browser may use Firebase client SDKs for permitted operations, while privileged state changes remain server-owned. Security rules and emulator deny-tests are part of the implementation, not optional documentation. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is silent corruption of the paper, formatting or protected academic content. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R08 — Provide a deterministic mock provider implementation for local development and CI.

**Implementation.** Keep model SDK calls server-side in small provider adapters. Model names are configuration. Control-flow outputs should use validated structured schemas; rewritten prose may be free text. Record model, prompt version, tokens, latency and estimated cost for every paid call, and bound retries. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is opaque model behaviour, semantic drift or unnecessary token use. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
# 27. Prompt and Structured Output Governance

Prompts are versioned production assets. They should be reviewable in source control, resistant to prompt injection from uploaded documents and paired with typed schemas wherever model output controls system behaviour.

## Required outcomes

- Store prompts in dedicated version-controlled files or constants grouped by task rather than giant strings inside HTTP routes.
- Give each important prompt a stable version identifier and record that version with generated artifacts.
- Place PaperAid instructions in the system/developer instruction layer and clearly delimit uploaded document text as untrusted data.
- Explicitly tell models that instructions appearing inside a paper are content and must not override PaperAid workflow rules.
- Use validated structured output schemas for analysis findings, audits, redraft plans and formatting specifications.
- Allow at most a bounded repair/retry when a model returns malformed structured data.
- Keep rewritten prose separate from control metadata so free-form text cannot accidentally drive state transitions.
- Maintain a small golden/fixture suite for critical prompt behaviours without running paid provider calls in normal CI.

## Detailed implementation requirements

### R01 — Store prompts in dedicated version-controlled files or constants grouped by task rather than giant strings inside HTTP routes.

**Implementation.** Keep model SDK calls server-side in small provider adapters. Model names are configuration. Control-flow outputs should use validated structured schemas; rewritten prose may be free text. Record model, prompt version, tokens, latency and estimated cost for every paid call, and bound retries. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is opaque model behaviour, semantic drift or unnecessary token use. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R02 — Give each important prompt a stable version identifier and record that version with generated artifacts.

**Implementation.** Keep model SDK calls server-side in small provider adapters. Model names are configuration. Control-flow outputs should use validated structured schemas; rewritten prose may be free text. Record model, prompt version, tokens, latency and estimated cost for every paid call, and bound retries. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is opaque model behaviour, semantic drift or unnecessary token use. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R03 — Place PaperAid instructions in the system/developer instruction layer and clearly delimit uploaded document text as untrusted data.

**Implementation.** Keep model SDK calls server-side in small provider adapters. Model names are configuration. Control-flow outputs should use validated structured schemas; rewritten prose may be free text. Record model, prompt version, tokens, latency and estimated cost for every paid call, and bound retries. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is silent corruption of the paper, formatting or protected academic content. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R04 — Explicitly tell models that instructions appearing inside a paper are content and must not override PaperAid workflow rules.

**Implementation.** Keep model SDK calls server-side in small provider adapters. Model names are configuration. Control-flow outputs should use validated structured schemas; rewritten prose may be free text. Record model, prompt version, tokens, latency and estimated cost for every paid call, and bound retries. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is opaque model behaviour, semantic drift or unnecessary token use. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R05 — Use validated structured output schemas for analysis findings, audits, redraft plans and formatting specifications.

**Implementation.** Keep model SDK calls server-side in small provider adapters. Model names are configuration. Control-flow outputs should use validated structured schemas; rewritten prose may be free text. Record model, prompt version, tokens, latency and estimated cost for every paid call, and bound retries. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is silent corruption of the paper, formatting or protected academic content. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R06 — Allow at most a bounded repair/retry when a model returns malformed structured data.

**Implementation.** Use Google Cloud Tasks as the production queue. Start with roughly five concurrent dispatched jobs, make the limit configurable, use OIDC-authenticated task delivery, and make enqueue/worker execution idempotent. Do not invent an in-memory production queue. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is duplicate processing, stuck jobs or uncontrolled provider spend. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R07 — Keep rewritten prose separate from control metadata so free-form text cannot accidentally drive state transitions.

**Implementation.** Keep model SDK calls server-side in small provider adapters. Model names are configuration. Control-flow outputs should use validated structured schemas; rewritten prose may be free text. Record model, prompt version, tokens, latency and estimated cost for every paid call, and bound retries. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is duplicate processing, stuck jobs or uncontrolled provider spend. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R08 — Maintain a small golden/fixture suite for critical prompt behaviours without running paid provider calls in normal CI.

**Implementation.** Keep model SDK calls server-side in small provider adapters. Model names are configuration. Control-flow outputs should use validated structured schemas; rewritten prose may be free text. Record model, prompt version, tokens, latency and estimated cost for every paid call, and bound retries. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is opaque model behaviour, semantic drift or unnecessary token use. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
# 28. AI Cost Accounting and Spend Ceilings

Model inference may be inexpensive per paper, but uncontrolled retries and long outputs can still create losses. PaperAid must make per-call and per-job model spend observable and bounded.

## Required outcomes

- Normalise provider usage metadata into a common model-usage record keyed to job and stage.
- Maintain a versioned model-price table so estimated historical cost can be explained even when provider prices change.
- Aggregate call-level estimated cost into a job-level total visible in the admin console.
- Derive a job-specific spend budget from service type, document size and accepted price, with an additional absolute platform ceiling.
- Before an expensive model call, estimate whether the call could push the job beyond its remaining budget and stop safely when necessary.
- Count retries against the same cost ceiling and never reset cost tracking on worker restart.
- Log cost anomalies and expose simple service/model cost summaries so real unit economics can replace estimates after launch.
- Do not weaken citation/quality audits merely to save a trivial amount of model cost without evidence that quality remains acceptable.

## Detailed implementation requirements

### R01 — Normalise provider usage metadata into a common model-usage record keyed to job and stage.

**Implementation.** Keep model SDK calls server-side in small provider adapters. Model names are configuration. Control-flow outputs should use validated structured schemas; rewritten prose may be free text. Record model, prompt version, tokens, latency and estimated cost for every paid call, and bound retries. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is opaque model behaviour, semantic drift or unnecessary token use. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R02 — Maintain a versioned model-price table so estimated historical cost can be explained even when provider prices change.

**Implementation.** Keep model SDK calls server-side in small provider adapters. Model names are configuration. Control-flow outputs should use validated structured schemas; rewritten prose may be free text. Record model, prompt version, tokens, latency and estimated cost for every paid call, and bound retries. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is opaque model behaviour, semantic drift or unnecessary token use. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R03 — Aggregate call-level estimated cost into a job-level total visible in the admin console.

**Implementation.** Keep model SDK calls server-side in small provider adapters. Model names are configuration. Control-flow outputs should use validated structured schemas; rewritten prose may be free text. Record model, prompt version, tokens, latency and estimated cost for every paid call, and bound retries. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is opaque model behaviour, semantic drift or unnecessary token use. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R04 — Derive a job-specific spend budget from service type, document size and accepted price, with an additional absolute platform ceiling.

**Implementation.** Keep model SDK calls server-side in small provider adapters. Model names are configuration. Control-flow outputs should use validated structured schemas; rewritten prose may be free text. Record model, prompt version, tokens, latency and estimated cost for every paid call, and bound retries. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is silent corruption of the paper, formatting or protected academic content. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R05 — Before an expensive model call, estimate whether the call could push the job beyond its remaining budget and stop safely when necessary.

**Implementation.** Keep model SDK calls server-side in small provider adapters. Model names are configuration. Control-flow outputs should use validated structured schemas; rewritten prose may be free text. Record model, prompt version, tokens, latency and estimated cost for every paid call, and bound retries. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is opaque model behaviour, semantic drift or unnecessary token use. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R06 — Count retries against the same cost ceiling and never reset cost tracking on worker restart.

**Implementation.** Keep model SDK calls server-side in small provider adapters. Model names are configuration. Control-flow outputs should use validated structured schemas; rewritten prose may be free text. Record model, prompt version, tokens, latency and estimated cost for every paid call, and bound retries. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is opaque model behaviour, semantic drift or unnecessary token use. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R07 — Log cost anomalies and expose simple service/model cost summaries so real unit economics can replace estimates after launch.

**Implementation.** Keep model SDK calls server-side in small provider adapters. Model names are configuration. Control-flow outputs should use validated structured schemas; rewritten prose may be free text. Record model, prompt version, tokens, latency and estimated cost for every paid call, and bound retries. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is opaque model behaviour, semantic drift or unnecessary token use. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R08 — Do not weaken citation/quality audits merely to save a trivial amount of model cost without evidence that quality remains acceptable.

**Implementation.** Keep model SDK calls server-side in small provider adapters. Model names are configuration. Control-flow outputs should use validated structured schemas; rewritten prose may be free text. Record model, prompt version, tokens, latency and estimated cost for every paid call, and bound retries. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is silent corruption of the paper, formatting or protected academic content. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
# 29. Security Architecture

Security is cross-cutting and must exist from the first real Firebase/backend integration. PaperAid holds private academic documents and paid API credentials, so identity, ownership, input safety and least privilege are mandatory.

## Required outcomes

- Every protected public backend request must verify a Firebase ID token and obtain the acting UID from the verified token rather than the request body.
- Use Firebase App Check on high-value browser-facing endpoints in production, with only explicit local development bypass.
- Check job ownership on every job-specific operation so one authenticated user cannot access another user’s metadata or files.
- Store OpenAI, Anthropic and future payment secrets only in Google Secret Manager/Cloud Run secret bindings and never in the frontend bundle.
- Use least-privilege runtime service accounts for Cloud Run and a dedicated task invoker identity where practical.
- Validate file extension, MIME/container signature, size, archive expansion ratio, entry count, encryption and macro-enabled formats before processing.
- Allow CORS only from approved production and development origins; internal task endpoints remain service-authenticated regardless of CORS.
- Treat document hyperlinks and embedded instructions as inert data and never automatically fetch remote resources referenced by a paper.

## Detailed implementation requirements

### R01 — Every protected public backend request must verify a Firebase ID token and obtain the acting UID from the verified token rather than the request body.

**Implementation.** Use the relevant Firebase managed service directly and keep ownership rules explicit. The browser may use Firebase client SDKs for permitted operations, while privileged state changes remain server-owned. Security rules and emulator deny-tests are part of the implementation, not optional documentation. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is unauthorised access to private documents, secrets or privileged state. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R02 — Use Firebase App Check on high-value browser-facing endpoints in production, with only explicit local development bypass.

**Implementation.** Use the relevant Firebase managed service directly and keep ownership rules explicit. The browser may use Firebase client SDKs for permitted operations, while privileged state changes remain server-owned. Security rules and emulator deny-tests are part of the implementation, not optional documentation. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is unauthorised access to private documents, secrets or privileged state. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R03 — Check job ownership on every job-specific operation so one authenticated user cannot access another user’s metadata or files.

**Implementation.** Use the relevant Firebase managed service directly and keep ownership rules explicit. The browser may use Firebase client SDKs for permitted operations, while privileged state changes remain server-owned. Security rules and emulator deny-tests are part of the implementation, not optional documentation. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is unauthorised access to private documents, secrets or privileged state. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R04 — Store OpenAI, Anthropic and future payment secrets only in Google Secret Manager/Cloud Run secret bindings and never in the frontend bundle.

**Implementation.** Implement this in the React + TypeScript + Vite frontend, using PaperAid design tokens and reusable components. Vite must bind to port 5000 in development. Keep mock data behind fixtures/adapters so visual work can be reviewed before Firebase and AI are connected. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is unauthorised access to private documents, secrets or privileged state. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R05 — Use least-privilege runtime service accounts for Cloud Run and a dedicated task invoker identity where practical.

**Implementation.** Fail closed. Verify Firebase identity and App Check where required, keep secrets in Google Secret Manager/Cloud Run secret bindings, validate ownership on every job operation, rate-limit expensive actions, and never log raw paper content or secret values. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is unauthorised access to private documents, secrets or privileged state. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R06 — Validate file extension, MIME/container signature, size, archive expansion ratio, entry count, encryption and macro-enabled formats before processing.

**Implementation.** Use a source-independent internal DocumentModel with stable block identifiers. Preserve the uploaded source, patch DOCX selectively, and use deterministic document code for formatting. Reject scanned/encrypted/unsafe inputs rather than silently producing low-quality output. Protect citations, quotations, numerals and other locked spans. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is unauthorised access to private documents, secrets or privileged state. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R07 — Allow CORS only from approved production and development origins; internal task endpoints remain service-authenticated regardless of CORS.

**Implementation.** Use the relevant Firebase managed service directly and keep ownership rules explicit. The browser may use Firebase client SDKs for permitted operations, while privileged state changes remain server-owned. Security rules and emulator deny-tests are part of the implementation, not optional documentation. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is unauthorised access to private documents, secrets or privileged state. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R08 — Treat document hyperlinks and embedded instructions as inert data and never automatically fetch remote resources referenced by a paper.

**Implementation.** Use a source-independent internal DocumentModel with stable block identifiers. Preserve the uploaded source, patch DOCX selectively, and use deterministic document code for formatting. Reject scanned/encrypted/unsafe inputs rather than silently producing low-quality output. Protect citations, quotations, numerals and other locked spans. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is unauthorised access to private documents, secrets or privileged state. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
# 30. Rate Limiting and Abuse Prevention

At launch scale, PaperAid can use simple server-side limits rather than Redis or a dedicated gateway. The goal is to prevent cost abuse and queue monopolisation while keeping legitimate student use frictionless.

## Required outcomes

- Rate-limit expensive low-frequency actions such as quote creation, job submission and repeated analysis requests per authenticated user.
- Limit the number of non-terminal active jobs per ordinary user, initially around three.
- Apply explicit maximum upload bytes, PDF pages and document words before model calls.
- Return a clear 429 or product-specific limit message with retry guidance rather than a generic server error.
- Keep provider quotas and Cloud Tasks dispatch limits as secondary safety controls rather than the only abuse protection.
- Provide a server-side emergency processing switch that can temporarily stop new model jobs without deleting user data or redeploying the frontend.
- Log rate-limit and abuse events with user/job IDs but never with raw paper content.
- Do not add Redis solely for rate limiting unless actual traffic demonstrates Firestore/simple backend limits are insufficient.

## Detailed implementation requirements

### R01 — Rate-limit expensive low-frequency actions such as quote creation, job submission and repeated analysis requests per authenticated user.

**Implementation.** Use the relevant Firebase managed service directly and keep ownership rules explicit. The browser may use Firebase client SDKs for permitted operations, while privileged state changes remain server-owned. Security rules and emulator deny-tests are part of the implementation, not optional documentation. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is unauthorised access to private documents, secrets or privileged state. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R02 — Limit the number of non-terminal active jobs per ordinary user, initially around three.

**Implementation.** Fail closed. Verify Firebase identity and App Check where required, keep secrets in Google Secret Manager/Cloud Run secret bindings, validate ownership on every job operation, rate-limit expensive actions, and never log raw paper content or secret values. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is ambiguity, duplicated logic or an unreliable user experience. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R03 — Apply explicit maximum upload bytes, PDF pages and document words before model calls.

**Implementation.** Keep model SDK calls server-side in small provider adapters. Model names are configuration. Control-flow outputs should use validated structured schemas; rewritten prose may be free text. Record model, prompt version, tokens, latency and estimated cost for every paid call, and bound retries. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is silent corruption of the paper, formatting or protected academic content. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R04 — Return a clear 429 or product-specific limit message with retry guidance rather than a generic server error.

**Implementation.** Use Google Cloud Tasks as the production queue. Start with roughly five concurrent dispatched jobs, make the limit configurable, use OIDC-authenticated task delivery, and make enqueue/worker execution idempotent. Do not invent an in-memory production queue. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is duplicate processing, stuck jobs or uncontrolled provider spend. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R05 — Keep provider quotas and Cloud Tasks dispatch limits as secondary safety controls rather than the only abuse protection.

**Implementation.** Use Google Cloud Tasks as the production queue. Start with roughly five concurrent dispatched jobs, make the limit configurable, use OIDC-authenticated task delivery, and make enqueue/worker execution idempotent. Do not invent an in-memory production queue. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is ambiguity, duplicated logic or an unreliable user experience. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R06 — Provide a server-side emergency processing switch that can temporarily stop new model jobs without deleting user data or redeploying the frontend.

**Implementation.** Implement this in the React + TypeScript + Vite frontend, using PaperAid design tokens and reusable components. Vite must bind to port 5000 in development. Keep mock data behind fixtures/adapters so visual work can be reviewed before Firebase and AI are connected. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is opaque model behaviour, semantic drift or unnecessary token use. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R07 — Log rate-limit and abuse events with user/job IDs but never with raw paper content.

**Implementation.** Fail closed. Verify Firebase identity and App Check where required, keep secrets in Google Secret Manager/Cloud Run secret bindings, validate ownership on every job operation, rate-limit expensive actions, and never log raw paper content or secret values. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is ambiguity, duplicated logic or an unreliable user experience. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R08 — Do not add Redis solely for rate limiting unless actual traffic demonstrates Firestore/simple backend limits are insufficient.

**Implementation.** Use the relevant Firebase managed service directly and keep ownership rules explicit. The browser may use Firebase client SDKs for permitted operations, while privileged state changes remain server-owned. Security rules and emulator deny-tests are part of the implementation, not optional documentation. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is ambiguity, duplicated logic or an unreliable user experience. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
# 31. Privacy, Retention and Confidentiality

PaperAid must behave like a service entrusted with private academic work. The implementation should minimise personal data, minimise document copies and make retention/deletion behaviour explicit and technically enforceable.

## Required outcomes

- Define a default retention period for source and generated files, initially configurable around thirty days unless product policy changes.
- Store expiresAt or equivalent metadata so cleanup can be automated and visible to the user.
- Never write raw document paragraphs, full model prompts containing the paper or signed download URLs to normal application logs.
- Delete temporary worker directories after completion or failure cleanup.
- Provide a user-triggered job deletion path and a complete account-deletion workflow that includes associated storage and metadata handling.
- Do not use uploaded student documents as a training dataset without a future explicit consent and policy change.
- Record which external AI provider/model processed a job without exposing private content in operational metadata.
- Avoid unnecessary backups or developer-created duplicate buckets that would undermine the stated retention period.

## Detailed implementation requirements

### R01 — Define a default retention period for source and generated files, initially configurable around thirty days unless product policy changes.

**Implementation.** Fail closed. Verify Firebase identity and App Check where required, keep secrets in Google Secret Manager/Cloud Run secret bindings, validate ownership on every job operation, rate-limit expensive actions, and never log raw paper content or secret values. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is unauthorised access to private documents, secrets or privileged state. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R02 — Store expiresAt or equivalent metadata so cleanup can be automated and visible to the user.

**Implementation.** Fail closed. Verify Firebase identity and App Check where required, keep secrets in Google Secret Manager/Cloud Run secret bindings, validate ownership on every job operation, rate-limit expensive actions, and never log raw paper content or secret values. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is unauthorised access to private documents, secrets or privileged state. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R03 — Never write raw document paragraphs, full model prompts containing the paper or signed download URLs to normal application logs.

**Implementation.** Keep model SDK calls server-side in small provider adapters. Model names are configuration. Control-flow outputs should use validated structured schemas; rewritten prose may be free text. Record model, prompt version, tokens, latency and estimated cost for every paid call, and bound retries. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is unauthorised access to private documents, secrets or privileged state. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R04 — Delete temporary worker directories after completion or failure cleanup.

**Implementation.** Fail closed. Verify Firebase identity and App Check where required, keep secrets in Google Secret Manager/Cloud Run secret bindings, validate ownership on every job operation, rate-limit expensive actions, and never log raw paper content or secret values. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is unauthorised access to private documents, secrets or privileged state. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R05 — Provide a user-triggered job deletion path and a complete account-deletion workflow that includes associated storage and metadata handling.

**Implementation.** Use the relevant Firebase managed service directly and keep ownership rules explicit. The browser may use Firebase client SDKs for permitted operations, while privileged state changes remain server-owned. Security rules and emulator deny-tests are part of the implementation, not optional documentation. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is unauthorised access to private documents, secrets or privileged state. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R06 — Do not use uploaded student documents as a training dataset without a future explicit consent and policy change.

**Implementation.** Use a source-independent internal DocumentModel with stable block identifiers. Preserve the uploaded source, patch DOCX selectively, and use deterministic document code for formatting. Reject scanned/encrypted/unsafe inputs rather than silently producing low-quality output. Protect citations, quotations, numerals and other locked spans. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is unauthorised access to private documents, secrets or privileged state. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R07 — Record which external AI provider/model processed a job without exposing private content in operational metadata.

**Implementation.** Keep model SDK calls server-side in small provider adapters. Model names are configuration. Control-flow outputs should use validated structured schemas; rewritten prose may be free text. Record model, prompt version, tokens, latency and estimated cost for every paid call, and bound retries. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is unauthorised access to private documents, secrets or privileged state. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R08 — Avoid unnecessary backups or developer-created duplicate buckets that would undermine the stated retention period.

**Implementation.** Fail closed. Verify Firebase identity and App Check where required, keep secrets in Google Secret Manager/Cloud Run secret bindings, validate ownership on every job operation, rate-limit expensive actions, and never log raw paper content or secret values. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is unauthorised access to private documents, secrets or privileged state. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
# 32. Reliability, Idempotency and Recovery

PaperAid must behave predictably through browser retries, provider failures, worker restarts and duplicate Cloud Tasks delivery. Reliability comes from explicit state, checkpoints and bounded retries, not from extra services.

## Required outcomes

- Assign stable job IDs and model-call IDs and use idempotency identity for submit, enqueue and payment/webhook operations.
- Persist major stage artifacts before advancing state so a retry can resume instead of repeating every paid model call.
- Classify domain failures such as invalid document, provider rate limit, provider unavailable, budget exceeded and unsafe output centrally.
- Retry transient failures only and fail permanent validation/security errors immediately.
- Bound both SDK-level and queue-level retries to avoid nested retry storms.
- When retries are exhausted, mark the job in a visible final-failure state with a safe user message and admin diagnostic metadata.
- Use admin retry for eligible failures rather than manually editing Firestore state.
- Duplicate task delivery after a job has completed or is already active must exit harmlessly without another model call.

## Detailed implementation requirements

### R01 — Assign stable job IDs and model-call IDs and use idempotency identity for submit, enqueue and payment/webhook operations.

**Implementation.** Use Google Cloud Tasks as the production queue. Start with roughly five concurrent dispatched jobs, make the limit configurable, use OIDC-authenticated task delivery, and make enqueue/worker execution idempotent. Do not invent an in-memory production queue. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is duplicate processing, stuck jobs or uncontrolled provider spend. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R02 — Persist major stage artifacts before advancing state so a retry can resume instead of repeating every paid model call.

**Implementation.** Use Google Cloud Tasks as the production queue. Start with roughly five concurrent dispatched jobs, make the limit configurable, use OIDC-authenticated task delivery, and make enqueue/worker execution idempotent. Do not invent an in-memory production queue. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is duplicate processing, stuck jobs or uncontrolled provider spend. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R03 — Classify domain failures such as invalid document, provider rate limit, provider unavailable, budget exceeded and unsafe output centrally.

**Implementation.** Use a source-independent internal DocumentModel with stable block identifiers. Preserve the uploaded source, patch DOCX selectively, and use deterministic document code for formatting. Reject scanned/encrypted/unsafe inputs rather than silently producing low-quality output. Protect citations, quotations, numerals and other locked spans. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is silent corruption of the paper, formatting or protected academic content. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R04 — Retry transient failures only and fail permanent validation/security errors immediately.

**Implementation.** Use Google Cloud Tasks as the production queue. Start with roughly five concurrent dispatched jobs, make the limit configurable, use OIDC-authenticated task delivery, and make enqueue/worker execution idempotent. Do not invent an in-memory production queue. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is unauthorised access to private documents, secrets or privileged state. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R05 — Bound both SDK-level and queue-level retries to avoid nested retry storms.

**Implementation.** Use Google Cloud Tasks as the production queue. Start with roughly five concurrent dispatched jobs, make the limit configurable, use OIDC-authenticated task delivery, and make enqueue/worker execution idempotent. Do not invent an in-memory production queue. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is duplicate processing, stuck jobs or uncontrolled provider spend. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R06 — When retries are exhausted, mark the job in a visible final-failure state with a safe user message and admin diagnostic metadata.

**Implementation.** Use structured Cloud Logging and a small operational admin surface. Store only metadata needed to diagnose jobs. Prefer high-signal operational metrics and avoid building a separate analytics platform or exposing paper content by default. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is duplicate processing, stuck jobs or uncontrolled provider spend. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R07 — Use admin retry for eligible failures rather than manually editing Firestore state.

**Implementation.** Use the relevant Firebase managed service directly and keep ownership rules explicit. The browser may use Firebase client SDKs for permitted operations, while privileged state changes remain server-owned. Security rules and emulator deny-tests are part of the implementation, not optional documentation. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is duplicate processing, stuck jobs or uncontrolled provider spend. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R08 — Duplicate task delivery after a job has completed or is already active must exit harmlessly without another model call.

**Implementation.** Keep model SDK calls server-side in small provider adapters. Model names are configuration. Control-flow outputs should use validated structured schemas; rewritten prose may be free text. Record model, prompt version, tokens, latency and estimated cost for every paid call, and bound retries. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is opaque model behaviour, semantic drift or unnecessary token use. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
# 33. Observability, Logging and Operational Metrics

PaperAid needs enough operational visibility to diagnose failed jobs, provider slowdowns, queue pressure and model cost without building a separate observability platform. Google Cloud logging and monitoring are sufficient for the first release.

## Required outcomes

- Emit structured JSON logs with request ID, job ID, stage, severity, duration and safe error code.
- Never log raw paper text, provider prompts containing the paper, secret values or signed file URLs.
- Measure stage durations so operations can distinguish extraction, analysis, writing, audit, formatting and export bottlenecks.
- Record model latency and usage metadata alongside job cost records.
- Expose lightweight health and readiness endpoints that do not call paid providers.
- Create a small set of high-signal monitoring alerts for elevated 5xx errors, repeated worker failures, queue backlog, configuration failure and unexpected spend.
- Keep detailed diagnostics in Cloud Logging and only the small amount of metadata needed by the product/admin UI in Firestore.
- Every support-visible failure must be traceable by job ID from the admin console into backend logs.

## Detailed implementation requirements

### R01 — Emit structured JSON logs with request ID, job ID, stage, severity, duration and safe error code.

**Implementation.** Use structured Cloud Logging and a small operational admin surface. Store only metadata needed to diagnose jobs. Prefer high-signal operational metrics and avoid building a separate analytics platform or exposing paper content by default. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is ambiguity, duplicated logic or an unreliable user experience. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R02 — Never log raw paper text, provider prompts containing the paper, secret values or signed file URLs.

**Implementation.** Keep model SDK calls server-side in small provider adapters. Model names are configuration. Control-flow outputs should use validated structured schemas; rewritten prose may be free text. Record model, prompt version, tokens, latency and estimated cost for every paid call, and bound retries. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is unauthorised access to private documents, secrets or privileged state. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R03 — Measure stage durations so operations can distinguish extraction, analysis, writing, audit, formatting and export bottlenecks.

**Implementation.** Keep model SDK calls server-side in small provider adapters. Model names are configuration. Control-flow outputs should use validated structured schemas; rewritten prose may be free text. Record model, prompt version, tokens, latency and estimated cost for every paid call, and bound retries. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is silent corruption of the paper, formatting or protected academic content. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R04 — Record model latency and usage metadata alongside job cost records.

**Implementation.** Keep model SDK calls server-side in small provider adapters. Model names are configuration. Control-flow outputs should use validated structured schemas; rewritten prose may be free text. Record model, prompt version, tokens, latency and estimated cost for every paid call, and bound retries. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is opaque model behaviour, semantic drift or unnecessary token use. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R05 — Expose lightweight health and readiness endpoints that do not call paid providers.

**Implementation.** Use structured Cloud Logging and a small operational admin surface. Store only metadata needed to diagnose jobs. Prefer high-signal operational metrics and avoid building a separate analytics platform or exposing paper content by default. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is opaque model behaviour, semantic drift or unnecessary token use. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R06 — Create a small set of high-signal monitoring alerts for elevated 5xx errors, repeated worker failures, queue backlog, configuration failure and unexpected spend.

**Implementation.** Use Google Cloud Tasks as the production queue. Start with roughly five concurrent dispatched jobs, make the limit configurable, use OIDC-authenticated task delivery, and make enqueue/worker execution idempotent. Do not invent an in-memory production queue. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is duplicate processing, stuck jobs or uncontrolled provider spend. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R07 — Keep detailed diagnostics in Cloud Logging and only the small amount of metadata needed by the product/admin UI in Firestore.

**Implementation.** Use the relevant Firebase managed service directly and keep ownership rules explicit. The browser may use Firebase client SDKs for permitted operations, while privileged state changes remain server-owned. Security rules and emulator deny-tests are part of the implementation, not optional documentation. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is opaque model behaviour, semantic drift or unnecessary token use. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R08 — Every support-visible failure must be traceable by job ID from the admin console into backend logs.

**Implementation.** Use structured Cloud Logging and a small operational admin surface. Store only metadata needed to diagnose jobs. Prefer high-signal operational metrics and avoid building a separate analytics platform or exposing paper content by default. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is opaque model behaviour, semantic drift or unnecessary token use. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
# 34. Admin Console

The admin console is an operational tool, not a second product. It should help the owner see what is happening, what failed, what it cost and whether a job can be safely retried or cancelled.

## Required outcomes

- Allow only verified admin custom claims to access admin routes and endpoints.
- Show compact summary metrics for recent jobs, queued/active jobs, completion rate, recent failures and estimated AI spend.
- Provide a paginated/filterable job table with user identifier, service, status, created time, duration and cost metadata.
- Provide a job detail view with state timeline, model calls, quote/payment state, file metadata and safe error detail without displaying full paper content by default.
- Allow safe idempotent retry of eligible failed jobs and cancellation of eligible queued jobs.
- Record who initiated an admin action and when.
- Keep mutable configuration controls minimal; prefer validated configuration rather than a generic free-form settings editor.
- Do not build CRM, marketing automation or a data warehouse into the admin console in the first release.

## Detailed implementation requirements

### R01 — Allow only verified admin custom claims to access admin routes and endpoints.

**Implementation.** Use structured Cloud Logging and a small operational admin surface. Store only metadata needed to diagnose jobs. Prefer high-signal operational metrics and avoid building a separate analytics platform or exposing paper content by default. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is opaque model behaviour, semantic drift or unnecessary token use. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R02 — Show compact summary metrics for recent jobs, queued/active jobs, completion rate, recent failures and estimated AI spend.

**Implementation.** Use Google Cloud Tasks as the production queue. Start with roughly five concurrent dispatched jobs, make the limit configurable, use OIDC-authenticated task delivery, and make enqueue/worker execution idempotent. Do not invent an in-memory production queue. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is duplicate processing, stuck jobs or uncontrolled provider spend. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R03 — Provide a paginated/filterable job table with user identifier, service, status, created time, duration and cost metadata.

**Implementation.** Use structured Cloud Logging and a small operational admin surface. Store only metadata needed to diagnose jobs. Prefer high-signal operational metrics and avoid building a separate analytics platform or exposing paper content by default. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is ambiguity, duplicated logic or an unreliable user experience. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R04 — Provide a job detail view with state timeline, model calls, quote/payment state, file metadata and safe error detail without displaying full paper content by default.

**Implementation.** Keep model SDK calls server-side in small provider adapters. Model names are configuration. Control-flow outputs should use validated structured schemas; rewritten prose may be free text. Record model, prompt version, tokens, latency and estimated cost for every paid call, and bound retries. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is duplicate processing, stuck jobs or uncontrolled provider spend. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R05 — Allow safe idempotent retry of eligible failed jobs and cancellation of eligible queued jobs.

**Implementation.** Use Google Cloud Tasks as the production queue. Start with roughly five concurrent dispatched jobs, make the limit configurable, use OIDC-authenticated task delivery, and make enqueue/worker execution idempotent. Do not invent an in-memory production queue. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is duplicate processing, stuck jobs or uncontrolled provider spend. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R06 — Record who initiated an admin action and when.

**Implementation.** Use structured Cloud Logging and a small operational admin surface. Store only metadata needed to diagnose jobs. Prefer high-signal operational metrics and avoid building a separate analytics platform or exposing paper content by default. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is ambiguity, duplicated logic or an unreliable user experience. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R07 — Keep mutable configuration controls minimal; prefer validated configuration rather than a generic free-form settings editor.

**Implementation.** Use structured Cloud Logging and a small operational admin surface. Store only metadata needed to diagnose jobs. Prefer high-signal operational metrics and avoid building a separate analytics platform or exposing paper content by default. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is ambiguity, duplicated logic or an unreliable user experience. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R08 — Do not build CRM, marketing automation or a data warehouse into the admin console in the first release.

**Implementation.** Use structured Cloud Logging and a small operational admin surface. Store only metadata needed to diagnose jobs. Prefer high-signal operational metrics and avoid building a separate analytics platform or exposing paper content by default. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is ambiguity, duplicated logic or an unreliable user experience. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
# 35. Frontend State and Component Strategy

The frontend workflow is mostly server state plus local form state. It should remain easy to understand and should not adopt a heavyweight global state architecture without evidence.

## Required outcomes

- Use React local state/hooks for ordinary component state and one small Firebase Auth context for identity/session state.
- Avoid Redux or another global store unless a real cross-application state problem appears during implementation.
- Centralise authenticated API requests, Firebase/App Check headers and safe error parsing in a small API client.
- Use Firestore subscription or a simple status polling abstraction for live job progress and cleanly unsubscribe on route changes.
- Use React Hook Form with Zod or an equivalently direct approach for complex upload/service forms if it improves clarity.
- Build a compact reusable UI layer for common controls such as Button, Card, Input, Dialog, Badge, Tabs, FileDropzone, StatusBadge, ScoreRing and FindingCard.
- Do not turn every div or three-line markup fragment into a reusable component.
- Use CSS variables/design tokens plus Tailwind or a similarly direct styling approach and avoid a large UI framework that fights the desired visual identity.

## Detailed implementation requirements

### R01 — Use React local state/hooks for ordinary component state and one small Firebase Auth context for identity/session state.

**Implementation.** Implement this in the React + TypeScript + Vite frontend, using PaperAid design tokens and reusable components. Vite must bind to port 5000 in development. Keep mock data behind fixtures/adapters so visual work can be reviewed before Firebase and AI are connected. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is unauthorised access to private documents, secrets or privileged state. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R02 — Avoid Redux or another global store unless a real cross-application state problem appears during implementation.

**Implementation.** Implement this in the React + TypeScript + Vite frontend, using PaperAid design tokens and reusable components. Vite must bind to port 5000 in development. Keep mock data behind fixtures/adapters so visual work can be reviewed before Firebase and AI are connected. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is duplicate processing, stuck jobs or uncontrolled provider spend. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R03 — Centralise authenticated API requests, Firebase/App Check headers and safe error parsing in a small API client.

**Implementation.** Implement this in the React + TypeScript + Vite frontend, using PaperAid design tokens and reusable components. Vite must bind to port 5000 in development. Keep mock data behind fixtures/adapters so visual work can be reviewed before Firebase and AI are connected. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is unauthorised access to private documents, secrets or privileged state. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R04 — Use Firestore subscription or a simple status polling abstraction for live job progress and cleanly unsubscribe on route changes.

**Implementation.** Implement this in the React + TypeScript + Vite frontend, using PaperAid design tokens and reusable components. Vite must bind to port 5000 in development. Keep mock data behind fixtures/adapters so visual work can be reviewed before Firebase and AI are connected. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is duplicate processing, stuck jobs or uncontrolled provider spend. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R05 — Use React Hook Form with Zod or an equivalently direct approach for complex upload/service forms if it improves clarity.

**Implementation.** Implement this in the React + TypeScript + Vite frontend, using PaperAid design tokens and reusable components. Vite must bind to port 5000 in development. Keep mock data behind fixtures/adapters so visual work can be reviewed before Firebase and AI are connected. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is duplicate processing, stuck jobs or uncontrolled provider spend. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R06 — Build a compact reusable UI layer for common controls such as Button, Card, Input, Dialog, Badge, Tabs, FileDropzone, StatusBadge, ScoreRing and FindingCard.

**Implementation.** Implement this in the React + TypeScript + Vite frontend, using PaperAid design tokens and reusable components. Vite must bind to port 5000 in development. Keep mock data behind fixtures/adapters so visual work can be reviewed before Firebase and AI are connected. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is duplicate processing, stuck jobs or uncontrolled provider spend. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R07 — Do not turn every div or three-line markup fragment into a reusable component.

**Implementation.** Implement this in the React + TypeScript + Vite frontend, using PaperAid design tokens and reusable components. Vite must bind to port 5000 in development. Keep mock data behind fixtures/adapters so visual work can be reviewed before Firebase and AI are connected. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is duplicate processing, stuck jobs or uncontrolled provider spend. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R08 — Use CSS variables/design tokens plus Tailwind or a similarly direct styling approach and avoid a large UI framework that fights the desired visual identity.

**Implementation.** Implement this in the React + TypeScript + Vite frontend, using PaperAid design tokens and reusable components. Vite must bind to port 5000 in development. Keep mock data behind fixtures/adapters so visual work can be reviewed before Firebase and AI are connected. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is duplicate processing, stuck jobs or uncontrolled provider spend. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
# 36. Responsive Design and Accessibility

Mobile usability is part of the core product because many target users will begin or finish the journey on phones. Accessibility improves real usability and should be built into controls rather than added as an audit-only afterthought.

## Required outcomes

- Design the critical upload, service, quote, processing and download flows mobile-first.
- Use semantic HTML and ensure every interactive element has an accessible name and visible keyboard focus.
- Colour may reinforce status but must never be the only way status or severity is communicated.
- Use responsive composition so the hero product preview simplifies on small screens instead of becoming an unreadable miniature desktop editor.
- Ensure file upload, payment-ready flow and downloads work in modern mobile browsers.
- Associate form labels, helper text and validation errors correctly and move focus to useful error locations where appropriate.
- Respect prefers-reduced-motion for nonessential animation while keeping processing state understandable.
- Run keyboard-only and basic automated accessibility checks on the critical user journey before launch.

## Detailed implementation requirements

### R01 — Design the critical upload, service, quote, processing and download flows mobile-first.

**Implementation.** Make this server-authoritative and versioned. The client may display values but must never choose the final amount or mark a payment successful. Store an immutable quote snapshot. Payments remain feature-flagged off until the non-payment product is stable. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is ambiguity, duplicated logic or an unreliable user experience. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R02 — Use semantic HTML and ensure every interactive element has an accessible name and visible keyboard focus.

**Implementation.** Implement the smallest cohesive production-safe solution that satisfies this requirement. Keep business rules in one source of truth, avoid speculative abstractions, expose failures explicitly, and add a durable test or verification step where the behaviour can regress. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is ambiguity, duplicated logic or an unreliable user experience. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R03 — Colour may reinforce status but must never be the only way status or severity is communicated.

**Implementation.** Implement the smallest cohesive production-safe solution that satisfies this requirement. Keep business rules in one source of truth, avoid speculative abstractions, expose failures explicitly, and add a durable test or verification step where the behaviour can regress. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is ambiguity, duplicated logic or an unreliable user experience. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R04 — Use responsive composition so the hero product preview simplifies on small screens instead of becoming an unreadable miniature desktop editor.

**Implementation.** Implement the smallest cohesive production-safe solution that satisfies this requirement. Keep business rules in one source of truth, avoid speculative abstractions, expose failures explicitly, and add a durable test or verification step where the behaviour can regress. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is ambiguity, duplicated logic or an unreliable user experience. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R05 — Ensure file upload, payment-ready flow and downloads work in modern mobile browsers.

**Implementation.** Make this server-authoritative and versioned. The client may display values but must never choose the final amount or mark a payment successful. Store an immutable quote snapshot. Payments remain feature-flagged off until the non-payment product is stable. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is ambiguity, duplicated logic or an unreliable user experience. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R06 — Associate form labels, helper text and validation errors correctly and move focus to useful error locations where appropriate.

**Implementation.** Implement the smallest cohesive production-safe solution that satisfies this requirement. Keep business rules in one source of truth, avoid speculative abstractions, expose failures explicitly, and add a durable test or verification step where the behaviour can regress. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is ambiguity, duplicated logic or an unreliable user experience. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R07 — Respect prefers-reduced-motion for nonessential animation while keeping processing state understandable.

**Implementation.** Implement the smallest cohesive production-safe solution that satisfies this requirement. Keep business rules in one source of truth, avoid speculative abstractions, expose failures explicitly, and add a durable test or verification step where the behaviour can regress. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is duplicate processing, stuck jobs or uncontrolled provider spend. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R08 — Run keyboard-only and basic automated accessibility checks on the critical user journey before launch.

**Implementation.** Implement the smallest cohesive production-safe solution that satisfies this requirement. Keep business rules in one source of truth, avoid speculative abstractions, expose failures explicitly, and add a durable test or verification step where the behaviour can regress. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is ambiguity, duplicated logic or an unreliable user experience. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
# 37. Testing Strategy

Testing should concentrate on errors that would expose data, spend money twice, corrupt papers or misprice jobs. A small high-value test suite is preferred over generated coverage theatre.

## Required outcomes

- Use fast unit tests for pricing, state transitions, score aggregation, protected-span restoration and cost-budget rules.
- Use Firebase Emulator tests for Firestore and Storage owner-versus-non-owner access and admin restrictions.
- Use synthetic DOCX/PDF fixtures for extraction, patching, formatting, pagination, tables, headings and scanned-PDF rejection.
- Mock OpenAI and Anthropic adapters in normal CI and test malformed structured output, timeout, rate limit, partial output and excessive usage cases.
- Use Playwright for a small number of end-to-end critical journeys from sign in to completed/downloadable job.
- Add explicit idempotency tests for double submit, duplicate queue delivery and admin retry.
- Add security tests for prompt-injection text embedded in a paper and unsafe file/container inputs.
- Before launch, run a ten-simultaneous-submission load test with mock providers and a small controlled real-provider smoke test within quota.

## Detailed implementation requirements

### R01 — Use fast unit tests for pricing, state transitions, score aggregation, protected-span restoration and cost-budget rules.

**Implementation.** Fail closed. Verify Firebase identity and App Check where required, keep secrets in Google Secret Manager/Cloud Run secret bindings, validate ownership on every job operation, rate-limit expensive actions, and never log raw paper content or secret values. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is duplicate processing, stuck jobs or uncontrolled provider spend. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R02 — Use Firebase Emulator tests for Firestore and Storage owner-versus-non-owner access and admin restrictions.

**Implementation.** Use the relevant Firebase managed service directly and keep ownership rules explicit. The browser may use Firebase client SDKs for permitted operations, while privileged state changes remain server-owned. Security rules and emulator deny-tests are part of the implementation, not optional documentation. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is ambiguity, duplicated logic or an unreliable user experience. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R03 — Use synthetic DOCX/PDF fixtures for extraction, patching, formatting, pagination, tables, headings and scanned-PDF rejection.

**Implementation.** Use a source-independent internal DocumentModel with stable block identifiers. Preserve the uploaded source, patch DOCX selectively, and use deterministic document code for formatting. Reject scanned/encrypted/unsafe inputs rather than silently producing low-quality output. Protect citations, quotations, numerals and other locked spans. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is silent corruption of the paper, formatting or protected academic content. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R04 — Mock OpenAI and Anthropic adapters in normal CI and test malformed structured output, timeout, rate limit, partial output and excessive usage cases.

**Implementation.** Keep model SDK calls server-side in small provider adapters. Model names are configuration. Control-flow outputs should use validated structured schemas; rewritten prose may be free text. Record model, prompt version, tokens, latency and estimated cost for every paid call, and bound retries. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is opaque model behaviour, semantic drift or unnecessary token use. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R05 — Use Playwright for a small number of end-to-end critical journeys from sign in to completed/downloadable job.

**Implementation.** Fail closed. Verify Firebase identity and App Check where required, keep secrets in Google Secret Manager/Cloud Run secret bindings, validate ownership on every job operation, rate-limit expensive actions, and never log raw paper content or secret values. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is ambiguity, duplicated logic or an unreliable user experience. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R06 — Add explicit idempotency tests for double submit, duplicate queue delivery and admin retry.

**Implementation.** Use Google Cloud Tasks as the production queue. Start with roughly five concurrent dispatched jobs, make the limit configurable, use OIDC-authenticated task delivery, and make enqueue/worker execution idempotent. Do not invent an in-memory production queue. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is duplicate processing, stuck jobs or uncontrolled provider spend. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R07 — Add security tests for prompt-injection text embedded in a paper and unsafe file/container inputs.

**Implementation.** Keep model SDK calls server-side in small provider adapters. Model names are configuration. Control-flow outputs should use validated structured schemas; rewritten prose may be free text. Record model, prompt version, tokens, latency and estimated cost for every paid call, and bound retries. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is unauthorised access to private documents, secrets or privileged state. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R08 — Before launch, run a ten-simultaneous-submission load test with mock providers and a small controlled real-provider smoke test within quota.

**Implementation.** Fail closed. Verify Firebase identity and App Check where required, keep secrets in Google Secret Manager/Cloud Run secret bindings, validate ownership on every job operation, rate-limit expensive actions, and never log raw paper content or secret values. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is ambiguity, duplicated logic or an unreliable user experience. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
# 38. Performance and Capacity for the First 500 Users

The expected first-month load is modest by cloud standards but the product must remain responsive when several students submit at once. Asynchronous queueing and CDN hosting provide most of the required headroom without extra infrastructure.

## Required outcomes

- Assume roughly 500 registered users in month one and bursts of up to ten simultaneous job submissions.
- Initially dispatch about five active paper-processing jobs concurrently while allowing additional submissions to remain queued.
- Host static frontend assets through Firebase Hosting/CDN and optimise large images or marketing mockups before production.
- Keep interactive API endpoints lightweight and never return complete document text in dashboard/history responses.
- Use bounded Firestore queries and cursor pagination for job history/admin tables.
- Allow Cloud Run autoscaling to handle instances while per-job working directories remain isolated.
- Adjust queue concurrency only after checking OpenAI/Anthropic quotas and real stage latency/cost metrics.
- Add a new infrastructure component only when measurement identifies a concrete bottleneck; do not pre-optimise for hypothetical millions of users.

## Detailed implementation requirements

### R01 — Assume roughly 500 registered users in month one and bursts of up to ten simultaneous job submissions.

**Implementation.** Implement the smallest cohesive production-safe solution that satisfies this requirement. Keep business rules in one source of truth, avoid speculative abstractions, expose failures explicitly, and add a durable test or verification step where the behaviour can regress. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is ambiguity, duplicated logic or an unreliable user experience. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R02 — Initially dispatch about five active paper-processing jobs concurrently while allowing additional submissions to remain queued.

**Implementation.** Use Google Cloud Tasks as the production queue. Start with roughly five concurrent dispatched jobs, make the limit configurable, use OIDC-authenticated task delivery, and make enqueue/worker execution idempotent. Do not invent an in-memory production queue. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is duplicate processing, stuck jobs or uncontrolled provider spend. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R03 — Host static frontend assets through Firebase Hosting/CDN and optimise large images or marketing mockups before production.

**Implementation.** Implement this in the React + TypeScript + Vite frontend, using PaperAid design tokens and reusable components. Vite must bind to port 5000 in development. Keep mock data behind fixtures/adapters so visual work can be reviewed before Firebase and AI are connected. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is ambiguity, duplicated logic or an unreliable user experience. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R04 — Keep interactive API endpoints lightweight and never return complete document text in dashboard/history responses.

**Implementation.** Use a source-independent internal DocumentModel with stable block identifiers. Preserve the uploaded source, patch DOCX selectively, and use deterministic document code for formatting. Reject scanned/encrypted/unsafe inputs rather than silently producing low-quality output. Protect citations, quotations, numerals and other locked spans. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is silent corruption of the paper, formatting or protected academic content. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R05 — Use bounded Firestore queries and cursor pagination for job history/admin tables.

**Implementation.** Use the relevant Firebase managed service directly and keep ownership rules explicit. The browser may use Firebase client SDKs for permitted operations, while privileged state changes remain server-owned. Security rules and emulator deny-tests are part of the implementation, not optional documentation. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is ambiguity, duplicated logic or an unreliable user experience. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R06 — Allow Cloud Run autoscaling to handle instances while per-job working directories remain isolated.

**Implementation.** Implement the smallest cohesive production-safe solution that satisfies this requirement. Keep business rules in one source of truth, avoid speculative abstractions, expose failures explicitly, and add a durable test or verification step where the behaviour can regress. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is opaque model behaviour, semantic drift or unnecessary token use. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R07 — Adjust queue concurrency only after checking OpenAI/Anthropic quotas and real stage latency/cost metrics.

**Implementation.** Use Google Cloud Tasks as the production queue. Start with roughly five concurrent dispatched jobs, make the limit configurable, use OIDC-authenticated task delivery, and make enqueue/worker execution idempotent. Do not invent an in-memory production queue. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is duplicate processing, stuck jobs or uncontrolled provider spend. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R08 — Add a new infrastructure component only when measurement identifies a concrete bottleneck; do not pre-optimise for hypothetical millions of users.

**Implementation.** Implement the smallest cohesive production-safe solution that satisfies this requirement. Keep business rules in one source of truth, avoid speculative abstractions, expose failures explicitly, and add a durable test or verification step where the behaviour can regress. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is ambiguity, duplicated logic or an unreliable user experience. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
# 39. CI, Deployment and Environments

Deployment should be repeatable and boring. The repository must contain the commands and configuration needed to reproduce hosting, rules and Cloud Run releases rather than depending on undocumented console edits.

## Required outcomes

- Maintain clear development and production configuration; add staging only if it improves testing without creating operational drag.
- Run frontend lint/typecheck/tests/build and backend lint/type/tests before a production deployment.
- Build one pinned backend container image containing the document and optional LaTeX tooling required by enabled features.
- Deploy Firebase Hosting, Firestore rules/indexes and Storage rules from version-controlled configuration.
- Use environment variables and secret bindings for project IDs, origins, model names, limits and provider keys.
- Keep feature flags for PAYMENTS_ENABLED, real-provider mode, LaTeX compilation and other incomplete capabilities server-authoritative.
- Preserve previous Cloud Run revisions and Firebase Hosting release history so rollback is documented and quick.
- After each production deployment, run a small synthetic end-to-end smoke job and verify logs/status/download before declaring success.

## Detailed implementation requirements

### R01 — Maintain clear development and production configuration; add staging only if it improves testing without creating operational drag.

**Implementation.** Test at the lowest sensible layer: unit tests for deterministic rules, Firebase Emulator tests for access rules, document fixtures for preservation, mocked-provider contract tests for AI flows, Playwright for the critical user journey, and a ten-job concurrency/load exercise before launch. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is opaque model behaviour, semantic drift or unnecessary token use. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R02 — Run frontend lint/typecheck/tests/build and backend lint/type/tests before a production deployment.

**Implementation.** Implement this in the React + TypeScript + Vite frontend, using PaperAid design tokens and reusable components. Vite must bind to port 5000 in development. Keep mock data behind fixtures/adapters so visual work can be reviewed before Firebase and AI are connected. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is ambiguity, duplicated logic or an unreliable user experience. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R03 — Build one pinned backend container image containing the document and optional LaTeX tooling required by enabled features.

**Implementation.** Use a source-independent internal DocumentModel with stable block identifiers. Preserve the uploaded source, patch DOCX selectively, and use deterministic document code for formatting. Reject scanned/encrypted/unsafe inputs rather than silently producing low-quality output. Protect citations, quotations, numerals and other locked spans. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is silent corruption of the paper, formatting or protected academic content. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R04 — Deploy Firebase Hosting, Firestore rules/indexes and Storage rules from version-controlled configuration.

**Implementation.** Use the relevant Firebase managed service directly and keep ownership rules explicit. The browser may use Firebase client SDKs for permitted operations, while privileged state changes remain server-owned. Security rules and emulator deny-tests are part of the implementation, not optional documentation. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is ambiguity, duplicated logic or an unreliable user experience. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R05 — Use environment variables and secret bindings for project IDs, origins, model names, limits and provider keys.

**Implementation.** Keep model SDK calls server-side in small provider adapters. Model names are configuration. Control-flow outputs should use validated structured schemas; rewritten prose may be free text. Record model, prompt version, tokens, latency and estimated cost for every paid call, and bound retries. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is unauthorised access to private documents, secrets or privileged state. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R06 — Keep feature flags for PAYMENTS_ENABLED, real-provider mode, LaTeX compilation and other incomplete capabilities server-authoritative.

**Implementation.** Use the relevant Firebase managed service directly and keep ownership rules explicit. The browser may use Firebase client SDKs for permitted operations, while privileged state changes remain server-owned. Security rules and emulator deny-tests are part of the implementation, not optional documentation. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is unauthorised access to private documents, secrets or privileged state. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R07 — Preserve previous Cloud Run revisions and Firebase Hosting release history so rollback is documented and quick.

**Implementation.** Use the relevant Firebase managed service directly and keep ownership rules explicit. The browser may use Firebase client SDKs for permitted operations, while privileged state changes remain server-owned. Security rules and emulator deny-tests are part of the implementation, not optional documentation. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is silent corruption of the paper, formatting or protected academic content. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R08 — After each production deployment, run a small synthetic end-to-end smoke job and verify logs/status/download before declaring success.

**Implementation.** Use structured Cloud Logging and a small operational admin surface. Store only metadata needed to diagnose jobs. Prefer high-signal operational metrics and avoid building a separate analytics platform or exposing paper content by default. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is ambiguity, duplicated logic or an unreliable user experience. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
# 40. Payment-Ready Architecture with Integration Deferred

Payment should be part of the state model now but connected only after PaperAid works reliably without it. The later integration should support Mobile Money and any chosen provider without coupling the whole job engine to vendor-specific fields.

## Required outcomes

- Keep quote state, payment state and processing state separate enough that each can fail or succeed independently.
- When PAYMENTS_ENABLED is false, record an explicit BETA_BYPASS or NOT_REQUIRED state rather than pretending a payment succeeded.
- When payments are enabled, only a verified server-side provider result may release the job to Cloud Tasks.
- Never trust a browser redirect or success screen as evidence of payment.
- Reconcile provider amount and currency against the immutable accepted quote before queueing.
- Make payment/webhook handling idempotent by provider transaction identifier so duplicate callbacks are harmless.
- Store only transaction references and reconciliation metadata, not payment secrets or unnecessary sensitive financial data.
- Place provider-specific code behind one narrow payment adapter after the provider is selected and avoid designing domain entities around one vendor.

## Detailed implementation requirements

### R01 — Keep quote state, payment state and processing state separate enough that each can fail or succeed independently.

**Implementation.** Make this server-authoritative and versioned. The client may display values but must never choose the final amount or mark a payment successful. Store an immutable quote snapshot. Payments remain feature-flagged off until the non-payment product is stable. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is duplicate processing, stuck jobs or uncontrolled provider spend. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R02 — When PAYMENTS_ENABLED is false, record an explicit BETA_BYPASS or NOT_REQUIRED state rather than pretending a payment succeeded.

**Implementation.** Make this server-authoritative and versioned. The client may display values but must never choose the final amount or mark a payment successful. Store an immutable quote snapshot. Payments remain feature-flagged off until the non-payment product is stable. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is duplicate processing, stuck jobs or uncontrolled provider spend. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R03 — When payments are enabled, only a verified server-side provider result may release the job to Cloud Tasks.

**Implementation.** Use Google Cloud Tasks as the production queue. Start with roughly five concurrent dispatched jobs, make the limit configurable, use OIDC-authenticated task delivery, and make enqueue/worker execution idempotent. Do not invent an in-memory production queue. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is ambiguity, duplicated logic or an unreliable user experience. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R04 — Never trust a browser redirect or success screen as evidence of payment.

**Implementation.** Make this server-authoritative and versioned. The client may display values but must never choose the final amount or mark a payment successful. Store an immutable quote snapshot. Payments remain feature-flagged off until the non-payment product is stable. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is ambiguity, duplicated logic or an unreliable user experience. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R05 — Reconcile provider amount and currency against the immutable accepted quote before queueing.

**Implementation.** Use Google Cloud Tasks as the production queue. Start with roughly five concurrent dispatched jobs, make the limit configurable, use OIDC-authenticated task delivery, and make enqueue/worker execution idempotent. Do not invent an in-memory production queue. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is duplicate processing, stuck jobs or uncontrolled provider spend. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R06 — Make payment/webhook handling idempotent by provider transaction identifier so duplicate callbacks are harmless.

**Implementation.** Make this server-authoritative and versioned. The client may display values but must never choose the final amount or mark a payment successful. Store an immutable quote snapshot. Payments remain feature-flagged off until the non-payment product is stable. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is ambiguity, duplicated logic or an unreliable user experience. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R07 — Store only transaction references and reconciliation metadata, not payment secrets or unnecessary sensitive financial data.

**Implementation.** Make this server-authoritative and versioned. The client may display values but must never choose the final amount or mark a payment successful. Store an immutable quote snapshot. Payments remain feature-flagged off until the non-payment product is stable. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is unauthorised access to private documents, secrets or privileged state. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R08 — Place provider-specific code behind one narrow payment adapter after the provider is selected and avoid designing domain entities around one vendor.

**Implementation.** Make this server-authoritative and versioned. The client may display values but must never choose the final amount or mark a payment successful. Store an immutable quote snapshot. Payments remain feature-flagged off until the non-payment product is stable. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is opaque model behaviour, semantic drift or unnecessary token use. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
# 41. Implementation Sequence and Early Review Gates

Implementation must proceed in vertical slices that keep the repository runnable. The IDE should expose the visual product first, then replace mocks with real infrastructure in stages, rather than attempting the entire stack in one giant generation.

## Required outcomes

- Stage A must establish the engineering constitution, repository, design tokens, landing page and all major UI routes on localhost:5000 with realistic fixtures.
- Stage B must add Firebase Auth, Firestore, Storage, security rules and secure upload/job metadata while preserving the approved UI.
- Stage C must add the job state machine, Cloud Tasks queue and a mocked worker so real asynchronous progress drives the existing screens.
- Stage D must implement the DocumentModel, DOCX/PDF extraction, protected spans, DOCX patch/export and deterministic formatting foundations.
- Stage E must add real provider adapters and the analysis, standard refinement, audit and targeted repair workflow.
- Stage F must add deep redraft, university guideline parsing, formatting application, LaTeX, admin operations, monitoring and hardening.
- Stage G must run security, document, end-to-end and ten-job load acceptance checks and deploy a payment-disabled public beta.
- Stage H adds the selected payment provider only after the core beta is stable; no earlier stage should be blocked by payment API selection.

## Detailed implementation requirements

### R01 — Stage A must establish the engineering constitution, repository, design tokens, landing page and all major UI routes on localhost:5000 with realistic fixtures.

**Implementation.** Implement this in the React + TypeScript + Vite frontend, using PaperAid design tokens and reusable components. Vite must bind to port 5000 in development. Keep mock data behind fixtures/adapters so visual work can be reviewed before Firebase and AI are connected. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is ambiguity, duplicated logic or an unreliable user experience. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R02 — Stage B must add Firebase Auth, Firestore, Storage, security rules and secure upload/job metadata while preserving the approved UI.

**Implementation.** Use the relevant Firebase managed service directly and keep ownership rules explicit. The browser may use Firebase client SDKs for permitted operations, while privileged state changes remain server-owned. Security rules and emulator deny-tests are part of the implementation, not optional documentation. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is unauthorised access to private documents, secrets or privileged state. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R03 — Stage C must add the job state machine, Cloud Tasks queue and a mocked worker so real asynchronous progress drives the existing screens.

**Implementation.** Use Google Cloud Tasks as the production queue. Start with roughly five concurrent dispatched jobs, make the limit configurable, use OIDC-authenticated task delivery, and make enqueue/worker execution idempotent. Do not invent an in-memory production queue. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is duplicate processing, stuck jobs or uncontrolled provider spend. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R04 — Stage D must implement the DocumentModel, DOCX/PDF extraction, protected spans, DOCX patch/export and deterministic formatting foundations.

**Implementation.** Keep model SDK calls server-side in small provider adapters. Model names are configuration. Control-flow outputs should use validated structured schemas; rewritten prose may be free text. Record model, prompt version, tokens, latency and estimated cost for every paid call, and bound retries. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is silent corruption of the paper, formatting or protected academic content. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R05 — Stage E must add real provider adapters and the analysis, standard refinement, audit and targeted repair workflow.

**Implementation.** Keep model SDK calls server-side in small provider adapters. Model names are configuration. Control-flow outputs should use validated structured schemas; rewritten prose may be free text. Record model, prompt version, tokens, latency and estimated cost for every paid call, and bound retries. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is opaque model behaviour, semantic drift or unnecessary token use. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R06 — Stage F must add deep redraft, university guideline parsing, formatting application, LaTeX, admin operations, monitoring and hardening.

**Implementation.** Keep model SDK calls server-side in small provider adapters. Model names are configuration. Control-flow outputs should use validated structured schemas; rewritten prose may be free text. Record model, prompt version, tokens, latency and estimated cost for every paid call, and bound retries. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is silent corruption of the paper, formatting or protected academic content. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R07 — Stage G must run security, document, end-to-end and ten-job load acceptance checks and deploy a payment-disabled public beta.

**Implementation.** Use a source-independent internal DocumentModel with stable block identifiers. Preserve the uploaded source, patch DOCX selectively, and use deterministic document code for formatting. Reject scanned/encrypted/unsafe inputs rather than silently producing low-quality output. Protect citations, quotations, numerals and other locked spans. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is unauthorised access to private documents, secrets or privileged state. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R08 — Stage H adds the selected payment provider only after the core beta is stable; no earlier stage should be blocked by payment API selection.

**Implementation.** Make this server-authoritative and versioned. The client may display values but must never choose the final amount or mark a payment successful. Store an immutable quote snapshot. Payments remain feature-flagged off until the non-payment product is stable. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is ambiguity, duplicated logic or an unreliable user experience. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
# 42. Coding Standard, Definition of Done and Deferred Scope

The IDE must treat simplicity as a quality requirement and finish each stage by removing scaffolding and duplication. A feature is done when the running product, tests and operations agree on its behaviour—not when code exists somewhere.

## Required outcomes

- Do not create architecture theatre: repositories, managers, factories, coordinators, buses or generic frameworks with one trivial implementation are prohibited unless a current requirement justifies them.
- Avoid both giant god files and hundreds of one-function files; group cohesive logic and split only when responsibilities genuinely diverge.
- Do not use TypeScript any or broad Python type-ignore/exception suppression to make errors disappear; model uncertain data explicitly.
- Catch exceptions only where context, classification, recovery or boundary translation is added; never blanket-catch and silently continue.
- Delete dead code, obsolete mock paths and abandoned experiments as each stage becomes real.
- The public beta definition of done includes polished mobile/desktop UI, secure ownership, queue backpressure, working model keys, output delivery, admin diagnostics, cost tracking and ten-submission load acceptance.
- Defer OCR, custom plagiarism database, bespoke trained AI detector, real-time collaborative editing, vector-database research library, LMS integrations, native mobile apps and complex subscriptions until real demand proves their value.
- If an optional service cannot meet its acceptance criteria, hide it for launch instead of weakening the whole application to ship it.

## Detailed implementation requirements

### R01 — Do not create architecture theatre: repositories, managers, factories, coordinators, buses or generic frameworks with one trivial implementation are prohibited unless a current requirement justifies them.

**Implementation.** Implement the smallest cohesive production-safe solution that satisfies this requirement. Keep business rules in one source of truth, avoid speculative abstractions, expose failures explicitly, and add a durable test or verification step where the behaviour can regress. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is ambiguity, duplicated logic or an unreliable user experience. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R02 — Avoid both giant god files and hundreds of one-function files; group cohesive logic and split only when responsibilities genuinely diverge.

**Implementation.** Use structured Cloud Logging and a small operational admin surface. Store only metadata needed to diagnose jobs. Prefer high-signal operational metrics and avoid building a separate analytics platform or exposing paper content by default. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is ambiguity, duplicated logic or an unreliable user experience. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R03 — Do not use TypeScript any or broad Python type-ignore/exception suppression to make errors disappear; model uncertain data explicitly.

**Implementation.** Keep model SDK calls server-side in small provider adapters. Model names are configuration. Control-flow outputs should use validated structured schemas; rewritten prose may be free text. Record model, prompt version, tokens, latency and estimated cost for every paid call, and bound retries. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is opaque model behaviour, semantic drift or unnecessary token use. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R04 — Catch exceptions only where context, classification, recovery or boundary translation is added; never blanket-catch and silently continue.

**Implementation.** Implement the smallest cohesive production-safe solution that satisfies this requirement. Keep business rules in one source of truth, avoid speculative abstractions, expose failures explicitly, and add a durable test or verification step where the behaviour can regress. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is ambiguity, duplicated logic or an unreliable user experience. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R05 — Delete dead code, obsolete mock paths and abandoned experiments as each stage becomes real.

**Implementation.** Implement the smallest cohesive production-safe solution that satisfies this requirement. Keep business rules in one source of truth, avoid speculative abstractions, expose failures explicitly, and add a durable test or verification step where the behaviour can regress. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is ambiguity, duplicated logic or an unreliable user experience. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R06 — The public beta definition of done includes polished mobile/desktop UI, secure ownership, queue backpressure, working model keys, output delivery, admin diagnostics, cost tracking and ten-submission load acceptance.

**Implementation.** Use Google Cloud Tasks as the production queue. Start with roughly five concurrent dispatched jobs, make the limit configurable, use OIDC-authenticated task delivery, and make enqueue/worker execution idempotent. Do not invent an in-memory production queue. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is unauthorised access to private documents, secrets or privileged state. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R07 — Defer OCR, custom plagiarism database, bespoke trained AI detector, real-time collaborative editing, vector-database research library, LMS integrations, native mobile apps and complex subscriptions until real demand proves their value.

**Implementation.** Keep model SDK calls server-side in small provider adapters. Model names are configuration. Control-flow outputs should use validated structured schemas; rewritten prose may be free text. Record model, prompt version, tokens, latency and estimated cost for every paid call, and bound retries. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is opaque model behaviour, semantic drift or unnecessary token use. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
### R08 — If an optional service cannot meet its acceptance criteria, hide it for launch instead of weakening the whole application to ship it.

**Implementation.** Test at the lowest sensible layer: unit tests for deterministic rules, Firebase Emulator tests for access rules, document fixtures for preservation, mocked-provider contract tests for AI flows, Playwright for the critical user journey, and a ten-job concurrency/load exercise before launch. Reuse the existing typed domain objects and keep the rule in one source of truth. The browser may improve usability, but trusted decisions stay on the server. Do not introduce another infrastructure service or abstraction unless this requirement creates a real second implementation or a measured bottleneck.

**Guardrails and failure behaviour.** The main risk is ambiguity, duplicated logic or an unreliable user experience. If the operation cannot be completed safely, stop at the relevant boundary, persist a safe job/error state when applicable, and provide an actionable user message. Do not silently downgrade security, switch to a materially different paid service, mark incomplete work as successful, or create an unbounded retry loop.

**Acceptance.** Demonstrate the behaviour in the running product and add the smallest durable test or verification step at the appropriate layer. Include the important denial/failure path as well as the happy path. The implementation should be understandable from the repository structure and should not duplicate logic across frontend and backend.
# Appendix A. Canonical Repository Structure

The repository is intentionally small. Do not introduce Nx/Turborepo or a package graph merely because the project contains a frontend and backend. One Git repository is enough.

```text
paperaid/
├── README.md
├── .editorconfig
├── .gitignore
├── firebase.json
├── firestore.rules
├── firestore.indexes.json
├── storage.rules
├── web/
│   ├── package.json
│   ├── vite.config.ts                 # server.port = 5000
│   ├── tsconfig.json
│   └── src/
│       ├── main.tsx
│       ├── app/
│       │   ├── router.tsx
│       │   ├── providers.tsx
│       │   └── routes/
│       ├── components/
│       │   ├── ui/
│       │   └── layout/
│       ├── features/
│       │   ├── auth/
│       │   ├── jobs/
│       │   ├── upload/
│       │   ├── analysis/
│       │   ├── results/
│       │   ├── pricing/
│       │   └── admin/
│       ├── lib/
│       │   ├── api.ts
│       │   ├── firebase.ts
│       │   ├── app-check.ts
│       │   └── formatting.ts
│       ├── fixtures/
│       └── styles/globals.css
├── backend/
│   ├── pyproject.toml
│   ├── dependency-lock-file
│   ├── Dockerfile
│   └── app/
│       ├── main.py
│       ├── core/                      # config, errors, auth, logging
│       ├── api/                       # quotes, jobs, admin, tasks
│       ├── jobs/                      # models, state machine, service, worker
│       ├── documents/                 # model, readers, protected spans, writers
│       ├── ai/
│       │   ├── orchestration.py
│       │   ├── schemas.py
│       │   ├── prompts/
│       │   └── providers/             # openai, anthropic, mock
│       ├── formatting/                # FormattingSpec + deterministic apply
│       ├── pricing/
│       ├── security/
│       └── integrations/              # Firestore, Storage, Tasks, payments stub
├── scripts/
│   ├── seed_dev.py
│   ├── load_test.py
│   └── deployment-notes.md
└── docs/
    ├── architecture.md
    ├── operations.md
    └── privacy-notes.md
```

Repository rules are strict but simple. The browser never imports model SDKs or secrets. HTTP routes may call domain services, but domain services do not depend on FastAPI request objects. The document package never talks directly to Firestore or AI providers; it receives files/DocumentModels and returns structured results. The AI package does not know Storage paths unless the job orchestrator explicitly provides the content it needs. External integrations are thin adapters, not alternate homes for business rules. If a helper has one trivial caller and does not improve readability, keep the logic in the caller. If a file grows because it contains multiple responsibilities, split by responsibility rather than by an arbitrary line count.

# Appendix B. Product Screens and UI Inventory

## Public site

The home page should visually resemble a mature writing SaaS product. At desktop size the hero is a two-column composition: marketing message and CTAs on the left, realistic PaperAid editor/analysis preview on the right. The preview should contain a research-paper excerpt with highlighted passages, suggestion cards for generic phrasing, repetitive structure, formatting inconsistency and weak transition, plus a compact estimated AI-likeness before/after area. The hero should not depend on a raster screenshot if the same effect can be built with lightweight reusable UI components, because component-based mockups stay crisp and responsive.

Below the hero, show a compact feature grid: AI Check, Refinement, Academic Formatting, Deep Redraft, University Templates and LaTeX Conversion. Follow with a four-step flow, then indicative pricing, then a trust/privacy section. Keep copy short. The public site should make “Upload your paper” the dominant action. A user should understand within one viewport that PaperAid checks writing patterns, improves text, applies academic formatting and returns a finished document.

## Sign in and registration

Keep authentication minimal. Email/password is sufficient for V1; optional Google sign-in is acceptable. Avoid collecting institution, programme, age, phone number or demographic data during account creation unless a concrete operational requirement appears. Preserve the intended destination so a visitor who clicked Upload returns to the new-job workflow after authentication.

## Dashboard

The signed-in home begins with a large “New paper job” action and a short recent-jobs list. Do not fill the screen with vanity graphs. Each job row/card shows safe filename, selected service, created date, status and quote/price state where useful. New users see an empty state that explains the upload flow.

## New job

The new-job flow contains one primary source upload, one optional university guideline upload, detected file facts, service cards, refinement/redraft intensity where applicable, extracted guideline summary, quote summary and the submit/payment gate. The system must explain when a service costs more because it rewrites more of the paper. It must also explain that AI-likeness percentages are estimates and cannot guarantee a third-party detector result.

## Processing job

The job page uses a stage timeline rather than a fake smooth percentage. Typical labels are Queued, Extracting, Analysing, Refining, Auditing, Formatting, Exporting and Ready, but only stages relevant to the selected service should appear. Tell users they can close the page and return later. If a job is delayed by a retryable provider issue, show a neutral processing-delay message rather than provider-specific jargon.

## Result screens

AI Check results show the estimated score, confidence/uncertainty, issue categories and passage-level findings. Refinement results show before/after estimate, changed-block count or approximate share, audit result, warnings and downloadable output. Formatting results show the applied rule summary and formatting warnings. Deep redraft results show the changed sections and audit outcome. The mobile version should not render two full ten-page documents side by side; diff only changed blocks in an expandable list.

## History and settings

History is cursor-paginated and filterable by status/service. Expired files show an honest “file expired” state. Settings remains small: display name, retention preference where supported, account deletion and legal links. Do not build a complex profile system.

## Admin

Admin screens are denser but use the same visual language. Provide high-signal operational summaries, recent failures and a paginated job table. Full paper text is hidden by default. Admin actions such as retry or cancel require explicit confirmation and backend authorization.

## Shared UI primitives

Build only primitives that are actually used: Button, Card, Input, Select, Checkbox/Radio, Tabs, Dialog/Drawer, Alert, Badge, StatusBadge, Skeleton, EmptyState, FileDropzone, FileChip, ServiceCard, PriceSummary, StageTimeline, ScoreRing, FindingCard, DiffBlock, DownloadCard and Pagination. Avoid a huge generated design system with unused components.

# Appendix C. Core Data and State Contracts

## Job record

A job is the source of truth for one PaperAid operation. At minimum it contains: job ID, owner UID, processing state, payment state, selected services, source file metadata/path, optional guideline metadata/path, quote snapshot, progress message/stage, analysis summary, output file references, estimated model cost, safe failure metadata, lifecycle timestamps and expiration timestamp. Large block-level analysis artifacts should be stored separately rather than growing one Firestore document indefinitely.

Example conceptual shape:

```json
{
  "id": "job_...",
  "ownerUid": "firebase_uid",
  "status": "QUEUED",
  "paymentStatus": "BETA_BYPASS",
  "services": ["AI_CHECK", "REFINE"],
  "source": {
    "storagePath": "users/<uid>/jobs/<job>/input/source.docx",
    "originalName": "coursework.docx",
    "contentType": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "sizeBytes": 123456,
    "wordCount": 4300,
    "pageEstimate": 9
  },
  "guideline": null,
  "quote": {
    "id": "quote_...",
    "currency": "UGX",
    "amount": 5000,
    "pricingVersion": "v1",
    "expiresAt": "timestamp"
  },
  "progress": {
    "stage": "ANALYSING",
    "message": "Reviewing writing patterns",
    "updatedAt": "timestamp"
  },
  "analysisSummary": {
    "estimatedAiLikeness": 31,
    "confidence": "MEDIUM",
    "findingCount": 14,
    "algorithmVersion": "ai-likeness-v1"
  },
  "outputFiles": [],
  "modelCost": {"estimatedUsd": 0.21},
  "failure": null,
  "createdAt": "timestamp",
  "updatedAt": "timestamp",
  "completedAt": null,
  "expiresAt": "timestamp"
}
```

## Processing states

Recommended processing states: `DRAFT`, `UPLOADED`, `QUOTED`, `AWAITING_PAYMENT`, `QUEUED`, `EXTRACTING`, `ANALYSING`, `REFINING`, `REDRAFTING`, `FORMATTING`, `AUDITING`, `EXPORTING`, `COMPLETED`, `FAILED_RETRYABLE`, `FAILED_FINAL`, `CANCELLED`. Not every service visits every state. The transition table is centralised. A worker must never skip from QUEUED to COMPLETED without the required artifact/stage outputs.

Payment states may include `NOT_REQUIRED`, `AWAITING_PAYMENT`, `PENDING`, `PAID`, `FAILED`, `REFUNDED`, `BETA_BYPASS`. Payment state must not be conflated with processing success.

## Analysis artifact

Each analyzable block has a stable block ID, score/risk band where appropriate, reason codes, explanation, recommended action and severity. The aggregate score is calculated deterministically from these results and stored with analysis algorithm version, provider/model and prompt version. Before and after analysis snapshots are separate records.

## FormattingSpec

The format specification contains page size, margins, default font, default font size, line spacing, paragraph spacing/indent, alignment, heading-level styles, heading numbering, pagination rules, caption rules, reference/citation style hints, TOC expectations, title/preliminary-page rules, warnings and provenance. The formatter consumes these fields; it does not reread the raw university guideline.

## Model usage

Each paid call records job ID, call ID, stage, provider, model, prompt version, input/output/cached tokens where available, latency, estimated cost and timestamp. Do not include raw paper text.

# Appendix D. API Surface

The API should remain small enough to understand on one OpenAPI page.

`POST /api/quotes` validates ownership/file/service inputs, inspects document metrics and returns a server-authoritative quote. It may reuse an unexpired quote when inputs are unchanged. It requires Firebase authentication and production App Check.

`POST /api/jobs` accepts an approved quote and submits the job. In beta it records `BETA_BYPASS` and queues. When payments are enabled it must not queue until server-side payment verification succeeds. This endpoint is idempotent.

`GET /api/jobs/{jobId}` returns safe job metadata to the owner. If the frontend reads job status directly from Firestore, this endpoint can remain useful for server-authoritative detail and support tooling.

`POST /api/jobs/{jobId}/cancel` requests cancellation only in allowed states. It is idempotent and should not pretend to abort an already-running external API call instantaneously.

`DELETE /api/jobs/{jobId}` schedules deletion of eligible files/metadata according to policy.

`POST /api/admin/jobs/{jobId}/retry` requeues an eligible failure after verifying an admin custom claim. It records the admin action and is idempotent.

`POST /tasks/process-job` is internal. It accepts a job identifier, verifies task service identity, acquires the job state lock and runs the workflow. Duplicate delivery after completion should return harmlessly without reprocessing.

All errors use one safe shape containing an application code, user-readable message and request ID. Never return stack traces, provider payloads containing a student paper, secret configuration or internal filesystem paths.

# Appendix E. Model Orchestration Contracts

## Standard AI Check

1. Load and validate the source.
2. Build DocumentModel and identify non-prose/protected areas.
3. Send analyzable blocks with outline/context to the configured analysis model.
4. Validate strict structured findings.
5. Aggregate block-level findings deterministically into the displayed estimated AI-likeness score.
6. Store report and user-facing summary.
7. No rewriting stage is executed.

## Standard refinement

1. Run or load analysis.
2. Choose candidate blocks using deterministic thresholds/service intensity.
3. Build context package for each target group: outline, neighbouring blocks, protected placeholders and explicit preservation constraints.
4. Send targets to the configured writing model.
5. Validate block IDs and protected placeholders.
6. Run deterministic numeric/citation checks.
7. Send original/revised blocks to the configured independent audit model.
8. Repair only failed blocks, with a bounded attempt count.
9. Patch accepted revisions into a copy of the source DOCX.
10. Reanalyse revised text if a post-refinement estimate is part of the service.
11. Export and store final output plus change summary.

## Deep redraft

1. Analyse paper and estimate affected share.
2. Build a section plan.
3. Lock facts/citations/protected values.
4. Rewrite logical sections, not arbitrary token windows.
5. Store section before/after artifacts.
6. Run independent audit.
7. Repair only audit failures within budget.
8. Export and report scale of change.

## University formatting

1. Parse the guide separately from the paper.
2. Convert rules to FormattingSpec and warnings/provenance.
3. Present material rule summary when user review is required.
4. Apply formatting with deterministic DOCX code.
5. Verify body text checksum for format-only jobs.
6. Render/inspect representative fixture output in automated/manual QA.

## Prompt-injection rule

Uploaded document text is untrusted data. Prompts must explicitly state that instructions contained in the paper or university file do not override PaperAid instructions. Models are never given tool capability to read secrets, change job state, fetch arbitrary URLs or bypass the orchestrator. Control decisions are based on schema-validated output and deterministic server logic.

# Appendix F. Environment and Configuration

Frontend-safe variables include Firebase web configuration, App Check public site key if applicable, API base URL and a development-only mock-mode flag. No OpenAI, Anthropic, payment or service-account secret may ever use a `VITE_` variable or appear in the browser bundle.

Backend configuration should include Firebase project/bucket identifiers, Cloud Tasks project/location/queue, worker URL and invoker service account, OpenAI and Anthropic secret bindings, configured model IDs for analysis/writing/audit/repair, `PAYMENTS_ENABLED`, upload/page/word limits, active jobs per user, default retention days, allowed origins, App Check requirement, provider timeout, LaTeX compilation flag, log level and emergency processing switch.

Validate configuration at startup. Production should fail closed when required security configuration is missing. Development may explicitly select mock providers and local bypasses. Do not create a generic dynamic configuration platform in V1; a small Firestore config document for pricing/public limits is enough.

# Appendix G. Test and Acceptance Catalogue

The following behaviours are minimum release gates. Implement them at the lowest useful layer rather than writing every test as E2E.

## Identity and ownership

- Unauthenticated quote/job requests are rejected.
- A user can read their own job and cannot read another user’s job.
- A user cannot mark a job paid, completed or admin-owned from the client.
- Admin endpoints reject non-admin users.
- Expired/invalid Firebase tokens are handled safely.
- Production App Check rejection is tested.
- Local App Check bypass works only in explicit local configuration.

## File safety

- Valid DOCX is accepted.
- Valid text-based PDF is accepted.
- DOCM/macro-enabled files are rejected.
- Encrypted PDF is rejected.
- Scanned PDF with insufficient extractable text is rejected with the correct message.
- Oversized documents and page/word-limit violations are rejected before model calls.
- Renamed executable/invalid container is rejected.
- ZIP-bomb-like DOCX archive characteristics are rejected.
- Path-traversal filenames are normalised and cannot escape job directories.
- Concurrent job workspaces are isolated.

## Quote and pricing

- A short AI-check paper and a ten-page refinement paper produce deterministic expected quotes for the current pricing configuration.
- Deep redraft price is higher than equivalent standard refinement.
- Quote stores pricing version and expires correctly.
- Client-supplied amount is ignored.
- Changing scope causes a new quote.
- Beta mode still creates the quote even though payment is bypassed.

## State and queue

- Every legal state transition succeeds and every illegal transition is rejected.
- Double-click submit creates one job/task.
- Duplicate Cloud Tasks delivery does not duplicate processing.
- Retryable provider failure retries within bounds.
- Permanent invalid-document failure does not retry repeatedly.
- A queued job can be cancelled; completed job cancellation is rejected.
- Worker restart after a completed stage resumes from checkpoint rather than repeating all paid calls.
- Ten submitted jobs respect the configured queue concurrency.

## AI and preservation

- Analysis structured output validates.
- One malformed structured response may be repaired/retried within bounds.
- Unknown block IDs from a model are rejected.
- Protected citation placeholders survive rewriting exactly once.
- Changed numerals/citations are caught by deterministic checks or audit.
- Missing protected placeholder fails the block rather than silently patching it.
- Repair loop is bounded.
- Before/after analysis records are separate.
- References/non-prose content does not dominate the aggregate score.
- Prompt-injection text inside a paper remains inert data.

## Document engine

- Interleaved paragraph/table order is preserved.
- Heading styles and outline are extracted.
- Unchanged blocks stay unchanged after selective refinement.
- Revised paragraph maps back to the intended source block.
- Formatting-only body-text checksum remains stable.
- Margins, spacing, headings and pagination rules apply on representative fixtures.
- Intentional landscape section is preserved.
- Table/figure captions survive formatting.
- Simple LaTeX export compiles when compilation is enabled.
- Unsafe TeX constructs are removed or blocked.

## Frontend

- Landing page renders correctly on common phone and desktop widths.
- Upload CTA preserves destination through sign-in.
- Invalid file gives a useful error before submit.
- Service selection and quote screen are readable on mobile.
- Queued and processing states update without refresh.
- Completed job provides secure download.
- Failed job provides an actionable message.
- History pagination works.
- Admin route is both visually hidden and server-protected.
- Keyboard-only critical journey works.
- Reduced-motion mode remains understandable.

## Operations and cost

- Every model call records usage and the job total equals the sum of calls.
- Pre-call budget guard prevents an expensive call when the remaining budget is insufficient.
- Retries count toward the same budget.
- Logs contain no raw document text.
- Request and job IDs allow one job to be traced across logs.
- Health checks do not call AI providers.
- Ten simultaneous submissions do not make interactive API endpoints unusable.

# Appendix H. Operational Runbook

## Job stuck in QUEUED

Check Cloud Tasks queue status, the task name/job ID, OIDC invocation permissions and the Firestore job state. If the task is missing, use the idempotent admin retry/requeue action. Never manually set the job to a later state merely to make the UI appear unstuck.

## Provider rate-limit failures

Identify the provider, inspect queue concurrency and quota, and reduce dispatch if bursts are causing repeated 429s. Confirm retries are not nested excessively at both SDK and queue layers. Keep the job in a safe delayed/retry state and do not expose provider internals to the user.

## Corrupted DOCX output

Preserve the job artifact before retention cleanup, compare source and output using document debug/fixture tooling, identify whether corruption occurred during extraction, patching, formatting or export, and create a synthetic regression fixture before fixing. Unchanged blocks should not have been rebuilt unnecessarily.

## Unexpected AI spend increase

Compare token use per stage, recent model configuration, retry counts and document-length mix. Verify cost metadata. If spend is actively uncontrolled, use the server-side processing switch or lower queue dispatch. Do not remove quality-control safeguards as the first reaction.

## Suspected cross-user access

Treat as a high-severity incident. Disable the affected access path if necessary, preserve logs, verify Firestore/Storage rules and backend ownership checks, invalidate any affected signed-link mechanism and determine scope before resuming normal use.

## Provider-key compromise

Revoke and rotate the key in the provider, update the secret binding, deploy a new Cloud Run revision, inspect usage, and verify that no browser bundle or repository history contained the key. Add a prevention check if the compromise came from deployment configuration.

## Rollback

Identify the last known-good Cloud Run revision and Firebase Hosting release. Roll backend traffic first if server behaviour is unsafe, then frontend if API compatibility requires it. Prefer additive/backward-compatible Firestore changes so rollback remains practical. Run a synthetic end-to-end job after rollback.

# Appendix I. Risk Register

| Risk | Impact | Launch likelihood | Primary mitigation |
|---|---|---|---|
| AI score mistaken for proof | High | Medium | Estimated label, disclaimer, confidence and passage evidence |
| Model alters citations/numbers | High | Medium | Protected spans, deterministic diff, audit and targeted repair |
| Duplicate task spends twice | High | Low | Idempotent task identity, state lock, checkpoints |
| Provider outage delays jobs | Medium | Medium | Retry classification, queue backoff, admin retry |
| One user monopolises queue | Medium | Medium | Active-job cap, rate limits, queue concurrency |
| Cross-user file access | Critical | Low | Rules, ownership checks, deny tests |
| Secret appears in frontend | Critical | Low | Server-only SDKs, secret bindings, bundle scan |
| Scanned PDF produces nonsense | Medium | Medium | Detect poor extraction and reject without OCR |
| Formatting damages layout | High | Medium | Deterministic styles, fixtures, rendered QA |
| Unsafe LaTeX execution | Critical | Low | PaperAid-generated source only, constrained compiler |
| Model cost exceeds revenue | Medium | Medium | Per-call accounting, job budget, bounded retry |
| UI looks unfinished | High | Medium | Early localhost visual milestone and design gate |
| Spaghetti code slows changes | High | Medium | Simplicity constitution, refactoring each stage |
| Payment provider forces redesign | Medium | Low | Separate quote/payment/process state and adapter |
| PaperAid name conflict | Medium | Low/unknown | Formal trademark/domain clearance before major marketing spend |

# Appendix J. Launch Checklist

**Visual/product:** polished original PaperAid landing page; mobile layouts intentionally designed; enabled services match marketing copy; estimated-score disclaimer appears wherever needed; all major CTAs work; no third-party logo or wording suggests affiliation.

**Core workflow:** sign in; source upload; optional guideline upload; server quote; beta/payment gate; queue; live status; completion; secure download; history; deletion/retention state.

**Document quality:** selective refinement changes only intended blocks; protected citations/numbers validated; deep redraft audited; format-only checksum stable; guideline parser produces usable FormattingSpec; LaTeX hidden if not reliable enough for release.

**Security:** Auth verification; App Check; Firestore and Storage deny tests; task OIDC; production CORS; secrets not in repository/frontend; file validation; rate limits; active-job caps; least-privilege runtime account.

**Reliability:** double-submit test; duplicate-task test; provider 429/5xx retry test; final failures visible to admin; cost ceiling tested; logs traceable and content-safe; retention cleanup configured; rollback documented.

**Capacity:** ten simultaneous submissions tested; queue dispatch remains at configured limit; interactive API remains responsive; provider quotas checked for launch concurrency.

**Release hygiene:** frontend and backend type/lint/test/build pass; critical E2E passes; security rules tests pass; no critical TODO/placeholder; README commands current; model and prompt versions recorded; a production smoke job completes.

# Appendix K. Deferred Roadmap

The IDE must not opportunistically add the following to V1: OCR for scanned documents, a custom plagiarism database, a bespoke trained AI-detector model, real-time collaborative editing, Google-Docs-style live editor, vector-database research library, university LMS/SIS integrations, enterprise SSO, native mobile apps, complex subscription/credit systems, Kafka/RabbitMQ/Redis, Kubernetes, multi-region active-active architecture or a data warehouse. These are valid future ideas only when real usage supplies evidence. The architecture should not block sensible evolution, but it should not pay the complexity cost before the need exists.

A future AI detector can replace or complement the internal score because scoring is already a modular artifact. OCR can later become a preprocessing service if scanned-PDF rejection becomes a measurable conversion problem. Subscription bundles can be introduced once job frequency and price sensitivity are known. Institution presets can be curated using the same FormattingSpec already used for uploaded guidelines. None of these futures require turning V1 into a speculative platform today.
