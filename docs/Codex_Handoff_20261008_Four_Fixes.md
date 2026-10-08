# Handoff to Claude — four follow-up fixes, 8 October 2026

Base: `edff36b` (release `2fe13d6`). Owner instruction: fix the four confirmed findings; Claude performs
the tests. Changes are local and uncommitted. No deployment, cloud changes, paid calls, or test runs.

## What changed

1. `backend/app/works/pipeline.py`: removed ambiguous "For example", "For illustration", and "To
   illustrate" numeric exemptions. Explicit hypothetical openings still explain coursework examples;
   the exemption remains unavailable to funding documents. New prompts `w-draft-v4` and `w-repair-v5`
   match the code and are registered by SHA256. `orchestration.py`, `works/ai.py`, and CLAUDE.md point
   to the new versions. Older released prompt files were not edited.
2. In the same pipeline, graph removal now requires the graph as the removal instruction's object.
   Keeping/retaining a graph or saying "not the graph" takes precedence, including across instructions.
   Removing a graph's caption, a nearby paragraph, or a table does not delete the graph. Ambiguous
   instructions preserve the graph.
3. `backend/app/datalab/pipeline.py`: one manifest entry per original section, with its first/last
   part range. Splitting no longer multiplies repeated manifest entries. The exact payload guard
   remains, including refusal when the repeated supporting context itself cannot fit.
4. Both `web/src/features/{works,proposals}/workspace-page.tsx` now key their selected page by route
   ID and use `use-page-record.ts` / `record-loader.ts`. Poll responses cannot overwrite a newer
   displayed response; saved mutations invalidate pending polls; older server timestamps (including
   microseconds) and different record IDs are rejected. Cleanup also invalidates delayed callbacks.
   A response may still display while a newer poll is pending, preventing starvation on connections
   slower than the four-second polling interval. Existing document/chapter response guards remain.
5. Updated the stale chapter-request comment in `proposals/models.py`: an unnamed whole-chapter
   request requires every targeted section, as the existing publication check already enforces.

## Regression tests written — not run

- `backend/tests/test_codex_20261008.py`: factual and genuinely hypothetical numeric sentences;
  mixed graph instructions, negation, caption removal and positive removal; long REPORT and
  CHAPTER_FOUR reviews under a 900-word limit. The review test checks all original words survive,
  every outgoing part fits, and the manifest stays at one entry per original section. It also
  checks oversized repeated context is refused.
- `backend/tests/test_proposal_v2.py`: unnamed "Use future tense throughout" request, with only
  one section changed (must stay OPEN) and every section changed/reviewed (must become APPLIED).
- `web/src/lib/record-loader.test.ts`: reverse response order, stale errors, navigation cleanup,
  mutation-versus-poll ordering, older mutation responses, microsecond timestamps, and slow polling.
- `web/scripts/e2e-workspace-races.mjs`: synthetic local browser journey for coursework and research
  proposals. Holds work/project A's response until B is displayed, then releases A; also releases
  the first four-second refresh after the second. Verifies the displayed text stays on B/new version.
  Uses localhost:5000 and the existing local test authentication; it submits no jobs or model requests.

## Claude's verification work

First review the new code and tests. Run the focused regressions, then the full normal gates. Do not
weaken assertions just to make the suite pass; report and correct any implementation or fixture gaps.

From `backend`:

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests/test_codex_20261008.py tests/test_codex_20261007b.py tests/test_proposal_v2.py --basetemp "$env:TEMP\pa1008"
.\.venv\Scripts\python.exe -m pytest -q --basetemp "$env:TEMP\pa1008full"
.\.venv\Scripts\python.exe -m ruff check app tests
```

From `web`:

```powershell
npm test
npm run typecheck
npm run build
node scripts/e2e-workspace-races.mjs
```

The browser command requires the local test backend (`python -m tests.serve_e2e`) and web server.
Run the usual five browser journeys as well. No paid model call is needed for these regressions.
If browser fixtures need adjustment, preserve the deliberately delayed responses and assertions.

Please mutation-check the important regressions: restoring the old hypothetical pattern, graph
heuristic, Data Lab manifest, or unguarded parent loader should fail its corresponding test.

## State and limits

- Static checks passed: Python AST parsing of changed/new Python files, `node --check` on the new
  browser script, and `git diff --check`. No application code was imported by the Python check.
  These are not the unrun test gates. Do not claim the patch passed suites until you run them.
- Strict Data Lab disclosure and prices are unchanged.
- Graph handling is conservative: conflicting instructions keep the graph.
- Repeated review context that cannot fit still fails safely; it is not silently dropped.
- Include the new prompt, test, hook, loader, browser script and this handoff when preparing a commit.
  Other untracked repository files predate this work; do not stage them indiscriminately.
- No release has been made. Obtain/observe the owner's release authorization separately after testing.
