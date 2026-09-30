# PaperAid: completion of the interrupted fixes

Date: 2026-09-29. Completed by Codex against the working changes on top of `667c5ac`.

## Release status

Superseded: the owner released these fixes as `1d573b6` (record `51b6f42`); see `deployment.md`. The paragraph below describes the state when this report was written.

The source changes are completed locally. **This is not a confirmation of a new live release.** This session cannot reach Google's token service: the connection to `oauth2.googleapis.com` fails with Windows socket error 10013 under the sandbox's network permissions. Re-authentication would not fix that restriction. Git staging also fails because the sandbox cannot create `.git/index.lock`; the changes remain uncommitted in the working tree. The release script handles committing and pushing from the normal terminal.

The last release recorded in `deployment.md` remains v16 (`6f39072`). No cloud permissions, secrets, payment settings or owner jobs were changed for this verification. Browser jobs used a separate temporary directory, test providers and ports 5002/8002.

## What is fixed

| Finding | Completed behavior and evidence |
|---|---|
| H03: guide upload/deletion | An unsuccessful attachment removes its own file, including ordinary database exceptions. Attempts have individual names in the project's guide directory under `users/`, covered by the storage retention backstop. Project deletion removes replaced attempts and old flat guide names, while preserving other projects' guides. Regression tests cover failed attachment, concurrent deletion and replaced/legacy copies. |
| H05: unresolved revision billing | Only sections changed and accepted by the final review count as resolved delivery. Unresolved comments remain open. A revision resolving nothing fails without a charge; partial settlement follows the resolved share. The forced unresolved-review test passes. |
| M10: interrupted local credit history | A torn ledger tail is cut before the next append/replay. Backfill tolerates damaged records. The test verifies both the correct balance and the complete readable credit history. |
| H04: guide migration | A quoted PROFILE job resolves the migrated input path. The regression prices a job before migration, moves the guide, then completes the job. Missing files have a specific recoverable message. |
| M27: PDF snapshot/cache | The export and its cache key use the same project snapshot. A details edit during export causes the next PDF to use a new cache entry. The race regression passes using a test compiler; actual PDF compilation has the environment limitation below. |
| M16: malformed institution profile | Non-string text, invalid chapter identifiers and overflowing numbers are safely interpreted or classified as an unusable guide. Seven malformed-response cases pass. |
| M17: missing-profile recovery | The standard-structure recovery button is available in Details even after chapters exist. The backend test restores the profile while retaining the written chapter; the browser confirms the recovery endpoint is called. |
| Current keep/undo choices | Continuation rebuilds from the student's current choices, including after a prior reviewed download. A reviewed download is saved under a unique path and published only if the choices still match inside the update. The additional concurrent-choice test rejects the stale build and removes only that attempt's file. |
| Exact passage scope | Invalid selections in Ask for changes are rejected. Explicit selections include short editable passages that the AI score excluded; the planner no longer cuts them at the analysed-word cap. A 305-paragraph test verifies both the saved scope and every actual planner target. Up to 3,000 passages are supported with a single stored instruction. |
| Score wording and layout | The percentage and band are compact on the right; marked passages remain on the left and explanations on the right. Confidence, counts and explanation are behind the information button. The wording describes a weighted writing-pattern score, not a share of AI-authored words or a repeatability guarantee. The main browser journey asserts this layout. |
| Abandoned chapter requests | Each student request is quoted by its own comment ID. Earlier abandoned requests do not join a later quote or the default supervisor-comment revision. Cancellation removes the request. Backend scope checks and the proposal browser journey pass. |
| Historical chapter requests | Ask for changes is available only for the current chapter version. The browser verifies that viewing a historical version hides the request form and explains how to choose that version first. |

## Additional problems found and corrected while finishing

1. **Formatting and logos change paragraph IDs.** Reusing the original ID could select a different paragraph, or reject a valid choice. The code now carries IDs through layout operations using the actual Word XML paragraph elements. It does not match text, so identical paragraphs remain distinguishable. Tests cover refinement and formatting-only jobs with both an essay and a dissertation, including repeated paragraphs.
2. **Harvard preliminary-page formatting overwrote the mapping lookup.** The main browser journey exposed this after the first implementation. The preceding paragraph used for the Roman-numbered section now has its own variable. The dissertation regressions cover this branch, and the browser continuation now succeeds.
3. **Older refined results could show neither percentage.** The document endpoint recovers the before score from saved analysis, and the after score from the saved review/refined document when the matching algorithm's inputs are available. It makes no provider calls. Insufficient saved data remains unavailable rather than producing an invented value. Backend and browser regressions cover the recovery.
4. **Two existing tests used obsolete contracts.** The guide race test now matches the new directory, and the concept-paper revision test submits the actual student comment ID. Their checks remain substantive.

## Verification results

- Final targeted backend run: **68 passed** (`test_audit_rechecks.py`, `test_audit_56c4f83.py`, `test_studio.py`).
- Additional reviewed-download race regression, added after that run: **1 passed**.
- Backend Ruff: clean.
- Frontend unit tests: **5 passed**; TypeScript typecheck: passed.
- Production Vite build: passed, built outside the existing locked `web/dist` directory.
- Main browser journey: passed with no unexpected error responses, including the previously failing selected-passage continuation from the Harvard-formatted, logo-bearing result.
- Proposal browser journey: passed, including cancelled and submitted student requests.
- Audit browser journey: passed, including failed-version handling, historical-version restrictions, missing-profile recovery, rejected Deep Redraft groups and recovered before/after percentages.
- Broad backend run before the final Harvard mapping correction: **435 passed, 9 skipped, 1 failed**. The failure was `test_the_proposal_downloads_as_a_pdf`. A subsequent standalone probe using only a tiny LaTeX document also failed before compilation: MiKTeX logged a fatal Windows error while starting its file-database refresh utility under the sandbox account. The final mapping correction is covered by the passing targeted runs and browser journey; the entire broad suite was not rerun after that correction.

**Do not describe the full backend suite as green.** Actual PDF compilation must pass in the owner's normal terminal or the production Linux image. The release script retains the full test gate and will stop if it fails. Tests of PDF caching and error reporting pass; they do not replace compilation verification.

No real provider calls were made during these tests. No real signed-in cloud browser check, Word desktop inspection or new live deployment was completed in this restricted session.

## Release from the owner's normal terminal

From the project root, using the existing GitHub, Google Cloud and Firebase sign-ins:

```powershell
powershell -ExecutionPolicy Bypass -File .\release-studio-fixes.ps1
```

The script runs backend tests and lint, frontend tests and typecheck, builds `web/hosting`, stages only this change set, commits and pushes, builds one backend image, deploys its immutable digest to both services, publishes Hosting, and records the ready revisions in the release log. It preserves existing service configuration. It has been parsed successfully, but cloud steps have not been executed here.

After deployment, verify the account on PC and Android, including an older finished paper's score and a selected-passage request from a formatted result. Download a real proposal PDF and open representative Word outputs in Word.

The unrelated pre-existing audit scratch directories and UCU manual are excluded from the script's commit list.

## Temporary CLI cleanup

The isolated browser-test servers were stopped. A temporary copy of the existing Google Cloud CLI configuration was used to test whether the failure came from its normal unwritable configuration directory or the network. Its cached authentication material was never printed or committed. Automatic approval review rejected deleting this temporary directory, giving only "blocked by policy" as its reason. Delete the following directory from the owner's normal terminal or File Explorer:

```text
C:\Users\USER\AppData\Local\Temp\paperaid_fix_726dab54c7c04116adf7140034cf16c6\gcloud
```

This is only the scratch copy; keep the normal Google Cloud SDK configuration.
