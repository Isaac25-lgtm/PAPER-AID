# PaperAid production-readiness audit

17 November 2026, Kampala · Candidate `dc67e636f29f31df31eeaff9f6aed2b402e57442` · Last recorded production release `8f3ea3544`

**Hold this candidate. Keep the current invite-only pilot and leave payments disabled.** The candidate can miss unit changes in academic output and can show the app before the user’s acceptance is known. The guide also covers controls at common desktop widths. [Candidate CI](https://github.com/Isaac25-lgtm/PAPER-AID/actions/runs/44153190950) · [Release log](deployment.md#release-log)

The audit uses the November 15 review as a baseline and checks the candidate across identity, upload and document intake, job execution and recovery, academic output, billing, notifications, administration, hosting and rollout. The browser and academic probes use local synthetic data. The production checks use public read-only endpoints. [November 15 audit](Codex_Production_Audit_and_Handoff_20261115.md)

## Candidate findings

### P1 — Unit checking misses contradictions in source-backed figures

The small-integer exemption treats values through 12 as plain counts even when a duration or currency is explicit. The checker accepted “12 months” against “12 days” and “USD 12” against “UGX 12.” It also accepted “14 months” when the source said “14 days” and separately mentioned “Version 14.” An unrelated bare occurrence suppresses a known contradiction for the same value. It flagged “12%” against the equivalent “12 per cent.” These results came from direct calls to the same validator used by proposal and coursework/funding reviews.

Normalize quantities and units together. Apply the count exemption only to unqualified values, and keep a matching bare occurrence from overriding explicit contradictory evidence elsewhere. Check the text that is actually exported, including tables, after repair. Keep the policy tied to the version frozen into each quote. [Figure validator](../backend/app/proposals/evidence.py#L391) · [Proposal checks](../backend/app/proposals/pipeline.py#L1399) · [Works checks](../backend/app/works/pipeline.py#L918)

### P1 — The consent gate renders the workspace before acceptance is known

In Chromium, delaying the preferences response left the dashboard visible. Returning `termsAccepted: false` then replaced it with the gate. Returning HTTP 503 left the dashboard visible indefinitely. The route uses the same visible state for initial loading and failure. The server checks terms on submission paths, while operations such as creating a draft and uploading a paper do not check the accepted version. The existing in-session prompt also accepts with one click and uses the version the page already loaded.

Track loading, accepted, current terms required and unavailable states explicitly. Offer retry when the lookup fails. Use one version-aware acceptance flow when an open tab encounters stale terms, and enforce current terms on the server where PaperAid starts handling user documents. Keep public terms, sign-out and account recovery accessible. Include the synthetic daily canary account in the terms-version rollover check. [App gate](../web/src/components/layout/app-layout.tsx#L80) · [Existing prompt](../web/src/features/account/terms.tsx#L87) · [Terms and draft intake](../backend/app/jobs/service.py#L123)

### P2 — The expanded walkthrough covers usable controls

At 1024×768 and 1280×800, Chromium’s hit test reached the walkthrough over the visible `Open`, work-section, `History` and `Redraft my paper` controls at their centers. On a fresh 390px viewport the guide started collapsed. Help and the Help-to-tour transition worked at that width.

Give the walkthrough its own layout space or start it collapsed when it would overlap page controls. Recheck pointer access and keyboard focus at tablet and desktop widths. The guide should also reflect service availability. For example, proposal review and AI drafting are subject to the account’s service access, and the funding Start form requires a problem description as well as a project title and intervention. [Guide positioning](../web/src/features/guide/section-guide.tsx#L93) · [Guide copy](../web/src/features/guide/scenes.ts#L96) · [Funding Start validation](../web/src/features/start/start-page.tsx#L150)

### P2 — Reference matching mishandles short titles and numeric subtitles

A valid synthetic DOI lookup for an exact one-word title returned `NOT_VERIFIED`. The matcher skips all one-word titles before the registry record can count as a match. For “Global health: 2020 and beyond” published in 2024, the parser selected 2020 as the year in a local probe. The title matcher iterates an unordered set containing the full title and its prefix, and retains whichever equal-scoring match it sees first. The shorter match leaves the subtitle year outside the title.

Prefer the longest exact match, allow exact one-word titles with DOI or author/year corroboration, and use recognizable publication-year positions. Add tests against the public verification result as well as the parser. [Reference title and year matching](../backend/app/analysis/references.py#L41)

### P2 — The inbox can omit or clear unseen completions

The list takes 20 terminal jobs sorted by creation time and filters out unannounced steps after the limit. In a local fixture with 20 newer jobs and one older job that finished last, the inbox omitted that last completion and reported zero unread. Bundled successes also consume slots before filtering. Opening the bell marks everything through the server’s current time read. A job that finishes between fetching the list and opening it can therefore be marked read without appearing in that list.

Query deliverable notices in completion order with a stable tie-breaker, then mark read through the newest notice actually delivered to the browser. At full page size the current poll can read 21 job records plus a wallet every 90 seconds per visible tab. Measure read volume with representative active users and job histories. [Inbox query](../backend/app/notify.py#L99) · [Firestore sort and lookahead](../backend/app/integrations/store.py#L646) · [Read timestamp](../backend/app/api/routes.py#L197)

### P2 — Browser preference writes need rollout and race handling

In Chromium, a delayed preferences response reset the browser to Day after the user chose Night. Overlapping writes can also arrive out of order. In addition, the old worker and API serialize the entire wallet with their schema. During a mixed-version rollout or rollback, an old wallet writer can drop the new appearance and inbox fields.

Protect in-flight local changes from stale loads and serialize or version writes. Verify old and new wallet writers during a staged release, including completion of a job submitted before the switch. [Theme synchronization](../web/src/components/layout/app-layout.tsx#L80) · [Wallet fields](../backend/app/jobs/models.py#L343) · [Firestore wallet writes](../backend/app/integrations/store.py#L746)

On an allowed separate origin, the new preferences `PUT` returned HTTP 400 at preflight because the CORS allowlist omits `PUT`. Firebase Hosting and the Vite development proxy use a same-origin route, so this affects separate-origin deployments. [CORS settings](../backend/app/main.py#L55)

### P3 — Report-only CSP has no reporting destination

The header can surface violations in a browser console. It has no configured reporting endpoint, so a release team cannot base enforcement on reports arriving from real use. Check Google sign-in, App Check, font and asset loading, and document downloads against the candidate policy in a staging browser. Configure and verify collection if enforcement will depend on field reports. [Hosting header](../firebase.json#L19)

## Wider launch and payments

| Area | Evidence and remaining gate |
|---|---|
| Identity and uploads | Firebase verifies revocation and App Check on protected routes. Direct client Firebase rules deny access by default. Sensitive admin writes still rely on the admin claim without checking recent authentication or a second factor. Verify operator MFA, step-up on sensitive actions, and ingress throttling. [Auth](../backend/app/core/auth.py#L32) · [Admin writes](../backend/app/api/routes.py#L397) · [Upload limits](../backend/app/core/uploads.py#L19) |
| AI spend and billing | Quote, reservation, settlement and retry paths exist. The daily ceiling is optional and the implementation contends on one Firestore document per day. Demonstrate a hard stop and clean transaction recovery under concurrent stage starts, and reconcile charges against Vertex usage before enabling payments. The last infrastructure audit recorded the aggregate ceiling as unset. [Daily limit](../backend/app/core/config.py#L188) · [Budget transaction](../backend/app/integrations/store.py#L624) |
| Queue, workload and observability | Stage leases and reconciliation are in place. Maintenance and reliability still collect whole result sets before filtering; the dashboard loads complete collections per user. Measure delivery and p95 latency across polling, uploads and synchronous rebuild/export. Alert when the canary misses a successful terminal outcome. The scheduler claims the day before creating the canary job and mostly checks the previous job later. [Reconciliation](../backend/app/jobs/service.py#L1217) · [Reliability](../backend/app/jobs/reliability.py#L90) · [Canary](../backend/app/jobs/canary.py#L74) |
| Recovery and privacy | The prior infrastructure audit recorded Firestore point-in-time recovery, scheduled backups and Storage soft delete. A joint restore remains unproven. Restore metadata, linked objects, work versions and wallet records together, then verify downloads, ownership and deletion behavior. Confirm that published retention matches archive and cleanup behavior. [Recovery evidence](Codex_Production_Audit_and_Handoff_20261115.md#production-evidence) · [Cleanup](../backend/app/jobs/service.py#L1251) |
| Dependencies and rollout | The Python advisory check found zero known vulnerabilities in the pinned constraints. The fresh npm audit reports five high-severity lockfile entries involving the Firebase Firestore chain and RE2JS. The named modules are absent from the 32 source maps of the local production build. Check the package update and put advisory checks into CI. The release script deploys services directly. Test the exact API, worker and Hosting combination on a candidate before moving traffic, including compatibility with old tabs and in-flight jobs. [CI](../.github/workflows/ci.yml) · [Release script](../release.sh#L47) |

## Verification

- GitHub’s backend and web checks succeeded for the exact candidate. Its backend workflow runs tests and native-renderer checks in the Linux image. The handoff records 1,411 backend passes and five browser journeys.
- Locally, 25 focused backend tests, Ruff and `pip check` passed. All 18 web tests, TypeScript and a fresh production build passed. The first local build could not clear the existing Windows `dist/assets` directory. Building to a fresh temporary directory succeeded.
- The local Windows full-suite run was interrupted after 20% with one failure shown by the runner and no traceback. The completed Linux CI run is the full-suite result for this audit.
- Local Chromium reproduced the consent, guide and appearance findings. All five browser journeys passed using stand-ins and a file-backed store. The first Paper Check attempt hit an upload HTTP 429 while the backend suite was running. The second reached the PDF step, where the audit harness was counting drafts in the default data directory instead of the temporary store. With the correct directory configured, Paper Check passed through university formatting, credits, admin and cross-account access checks.
- Public readiness returned `processingEnabled: true`. The public catalog returned terms version `2026-11-15` with payments and credits off, and the retired Data Lab path returned 404. Current cloud IAM, Firestore contention, joint restore, signed-in production delivery, and paid model output quality remain unverified in this audit.
