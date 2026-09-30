# Run from a normal Windows terminal with the existing GitHub, gcloud and Firebase sign-ins.
# powershell -ExecutionPolicy Bypass -File .\release-four-models.ps1
$ErrorActionPreference = 'Stop'
$repoRoot = [System.IO.Path]::GetFullPath($PSScriptRoot)
$backendDir = Join-Path $repoRoot 'backend'
$webDir = Join-Path $repoRoot 'web'

function Invoke-Native([string]$Command, [string[]]$Arguments) {
    & $Command @Arguments
    if ($LASTEXITCODE -ne 0) { throw "$Command failed with exit code $LASTEXITCODE" }
}

Set-Location -LiteralPath $repoRoot
if ((& git branch --show-current) -ne 'main') { throw 'Release from main after merging the verified changes.' }

Push-Location -LiteralPath $backendDir
try {
    Invoke-Native '.\.venv\Scripts\python.exe' @('-m', 'ruff', 'check', 'app', 'tests')
    $testTemp = Join-Path $env:TEMP ('paperaid-release-tests-' + [guid]::NewGuid().ToString('N'))
    Invoke-Native '.\.venv\Scripts\python.exe' @('-m', 'pytest', '-q', '-p', 'no:cacheprovider', '--basetemp', $testTemp)
} finally { Pop-Location }

Push-Location -LiteralPath $webDir
try {
    Invoke-Native 'npm.cmd' @('test')
    Invoke-Native 'npm.cmd' @('run', 'typecheck')
    $hostingDir = [System.IO.Path]::GetFullPath((Join-Path $webDir 'hosting'))
    if ($hostingDir -ne (Join-Path $repoRoot 'web\hosting')) { throw 'Unexpected hosting build directory.' }
    Invoke-Native 'npx.cmd' @('vite', 'build', '--mode', 'production', '--outDir', $hostingDir, '--emptyOutDir')
} finally { Pop-Location }

$changedFiles = @(
    'CLAUDE.md',
    'backend/.env.example',
    'backend/app/ai/costs.py',
    'backend/app/ai/orchestration.py',
    'backend/app/ai/prompts/analyse-v3.md',
    'backend/app/ai/prompts/finalise-v3.md',
    'backend/app/ai/prompts/finalise-v4.md',
    'backend/app/ai/prompts/guide-v1.md',
    'backend/app/ai/prompts/p-brief-v2.md',
    'backend/app/ai/prompts/p-draft-v2.md',
    'backend/app/ai/prompts/p-finalise-v3.md',
    'backend/app/ai/prompts/p-finalise-v4.md',
    'backend/app/ai/prompts/p-fix-v2.md',
    'backend/app/ai/prompts/p-guide-v1.md',
    'backend/app/ai/prompts/p-plan-review-v1.md',
    'backend/app/ai/prompts/p-plan-review-v2.md',
    'backend/app/ai/prompts/p-profile-finalise-v2.md',
    'backend/app/ai/prompts/p-profile-finalise-v3.md',
    'backend/app/ai/prompts/p-profile-guide-v1.md',
    'backend/app/ai/prompts/p-profile-review-v1.md',
    'backend/app/ai/prompts/p-review-v2.md',
    'backend/app/ai/prompts/p-review-v3.md',
    'backend/app/ai/prompts/released.json',
    'backend/app/ai/prompts/review-v3.md',
    'backend/app/ai/prompts/spec-critique-v2.md',
    'backend/app/ai/prompts/spec-finalise-v2.md',
    'backend/app/ai/prompts/spec-finalise-v3.md',
    'backend/app/ai/prompts/spec-guide-v1.md',
    'backend/app/ai/prompts/spec-review-v2.md',
    'backend/app/analysis/signals.py',
    'backend/app/api/projects.py',
    'backend/app/core/config.py',
    'backend/app/jobs/models.py',
    'backend/app/jobs/pipeline.py',
    'backend/app/jobs/service.py',
    'backend/app/jobs/workspace.py',
    'backend/app/latex/package.py',
    'backend/app/pricing/quote.py',
    'backend/app/proposals/ai.py',
    'backend/app/proposals/evidence.py',
    'backend/app/proposals/models.py',
    'backend/app/proposals/pipeline.py',
    'backend/app/proposals/service.py',
    'backend/app/reports/builder.py',
    'backend/calibrate.py',
    'backend/cost_report.py',
    'backend/inspect_ai_score.py',
    'backend/tests/conftest.py',
    'backend/tests/fake_models.py',
    'backend/tests/serve_e2e.py',
    'backend/tests/test_ai.py',
    'backend/tests/test_ai_coverage.py',
    'backend/tests/test_api.py',
    'backend/tests/test_audit_20260928.py',
    'backend/tests/test_codex_review.py',
    'backend/tests/test_finish_chapter.py',
    'backend/tests/test_four_model_delivery.py',
    'backend/tests/test_four_model_fixes.py',
    'backend/tests/test_four_models.py',
    'backend/tests/test_pilot_fixes.py',
    'backend/tests/test_profiles.py',
    'backend/tests/test_proposals.py',
    'backend/tests/test_sections.py',
    'docs/Four_Model_Algorithm_20260929.md',
    'docs/Studio_Fixes_Verification_20260929.md',
    'docs/decisions.md',
    'docs/deployment.md',
    'release-four-models.ps1',
    'web/scripts/e2e-audit-56c4f83.mjs',
    'web/scripts/e2e-proposal.mjs',
    'web/scripts/e2e.mjs',
    'web/src/components/layout/app-layout.tsx',
    'web/src/components/layout/public-layout.tsx',
    'web/src/features/jobs/job-page.tsx',
    'web/src/features/marketing/hero-preview.tsx',
    'web/src/features/marketing/home-page.tsx',
    'web/src/features/marketing/info-pages.tsx',
    'web/src/features/marketing/sections.tsx',
    'web/src/features/proposals/project-page.tsx',
    'web/src/features/results/report.tsx',
    'web/src/features/results/workspace.tsx',
    'web/src/features/studio/options.tsx',
    'web/src/features/studio/studio.tsx',
    'web/src/features/upload/new-job-page.tsx',
    'web/src/features/upload/service-chooser.tsx',
    'web/src/lib/api-source.ts',
    'web/src/lib/data.ts',
    'web/src/lib/proposal-types.ts',
    'web/src/lib/services.ts',
    'web/src/lib/types.ts'
)
foreach ($staged in (& git diff --cached --name-only)) {
    if ($staged -notin $changedFiles) { throw "Unrelated staged file: $staged" }
}
Invoke-Native 'git' (@('add', '--') + $changedFiles)
Invoke-Native 'git' @('diff', '--cached', '--check')
& git diff --cached --quiet
if ($LASTEXITCODE -eq 1) {
    Invoke-Native 'git' @('commit', '-m', 'Four-model algorithm, three sections and Finish chapter')
} elseif ($LASTEXITCODE -ne 0) { throw 'Could not inspect the staged changes.' }
Invoke-Native 'git' @('push', 'origin', 'main')
$codeCommit = (& git rev-parse --short HEAD).Trim()
if ($codeCommit -notmatch '^[0-9a-f]+$') { throw 'Could not identify the release commit.' }
$image = "europe-west1-docker.pkg.dev/paperaid-ca172/paperaid/backend:four-models-$codeCommit"
Invoke-Native 'gcloud.cmd' @('builds', 'submit', $backendDir, '--tag', $image, '--project', 'paperaid-ca172', '--region', 'europe-west1', '--quiet')
$digest = (& gcloud.cmd artifacts docker images describe $image --project paperaid-ca172 '--format=value(image_summary.digest)').Trim()
if ($LASTEXITCODE -ne 0 -or $digest -notmatch '^sha256:[0-9a-f]{64}$') { throw 'Could not obtain the built image digest.' }
$immutableImage = "europe-west1-docker.pkg.dev/paperaid-ca172/paperaid/backend@$digest"
foreach ($service in @('paperaid-worker', 'paperaid-api')) {
    Invoke-Native 'gcloud.cmd' @('run', 'deploy', $service, '--image', $immutableImage, '--project', 'paperaid-ca172', '--region', 'europe-west1', '--update-env-vars', 'LEAD_MODEL=openai:gpt-6-sol,WRITER_MODEL=anthropic:claude-opus-5-5,AI_CHECK_MODEL=openai:gpt-6-luna,AI_CHECK_PEER_MODEL=anthropic:claude-sonnet-5-5,ROUTINE_MODEL=openai:gpt-6-luna,DRAFTING_MODEL=anthropic:claude-sonnet-5-5,REQUIRE_DUAL_APPROVAL=true,FRONTIER_GUIDANCE=true,PARTIAL_CHAPTERS=false,SHOW_AI_SCORE=false', '--quiet')
}
Invoke-Native 'firebase.cmd' @('deploy', '--only', 'hosting', '--project', 'paperaid-ca172', '--non-interactive')
$apiRevision = (& gcloud.cmd run services describe paperaid-api --project paperaid-ca172 --region europe-west1 '--format=value(status.latestReadyRevisionName)').Trim()
if ($LASTEXITCODE -ne 0) { throw 'Could not confirm the API revision.' }
$workerRevision = (& gcloud.cmd run services describe paperaid-worker --project paperaid-ca172 --region europe-west1 '--format=value(status.latestReadyRevisionName)').Trim()
if ($LASTEXITCODE -ne 0) { throw 'Could not confirm the worker revision.' }
$logPath = Join-Path $repoRoot 'docs\deployment.md'
$log = [System.IO.File]::ReadAllText($logPath)
$separator = '|---|---|---|---|---|---|'
$row = '| ' + (Get-Date -Format 'yyyy-MM-dd') + ' | `' + $codeCommit + '` | `four-models-' + $codeCommit + '` (`' + $digest + '`) | `' + $apiRevision + '` | `' + $workerRevision + '` | four-model algorithm and explicit check coverage; hosting deployed |'
if (-not $log.Contains($separator)) { throw 'Release-log table was not found.' }
[System.IO.File]::WriteAllText($logPath, $log.Replace($separator, $separator + [Environment]::NewLine + $row))
Invoke-Native 'git' @('add', '--', 'docs/deployment.md')
Invoke-Native 'git' @('commit', '-m', "Record four-model release against $codeCommit")
Invoke-Native 'git' @('push', 'origin', 'main')
Write-Output 'Deployment completed: https://paperaid-ca172.web.app'
Write-Output 'Refresh the site and verify the signed-in PC/Android workflow and downloaded Word files.'
