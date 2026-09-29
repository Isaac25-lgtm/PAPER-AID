# Run from a normal Windows terminal with the existing GitHub, gcloud and Firebase sign-ins.
# powershell -ExecutionPolicy Bypass -File .\release-studio-fixes.ps1
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
    'backend/app/api/projects.py', 'backend/app/api/routes.py', 'backend/app/documents/docx_io.py',
    'backend/app/formatting/apply.py', 'backend/app/integrations/files.py', 'backend/app/integrations/store.py',
    'backend/app/jobs/models.py', 'backend/app/jobs/pipeline.py', 'backend/app/jobs/service.py', 'backend/app/jobs/workspace.py',
    'backend/app/proposals/models.py', 'backend/app/proposals/pipeline.py', 'backend/app/proposals/profile.py', 'backend/app/proposals/service.py',
    'backend/tests/serve_e2e.py', 'backend/tests/test_audit_56c4f83.py', 'backend/tests/test_audit_rechecks.py', 'backend/tests/test_studio.py',
    'web/scripts/e2e.mjs', 'web/scripts/e2e-proposal.mjs', 'web/scripts/e2e-audit-56c4f83.mjs',
    'web/src/features/proposals/project-page.tsx', 'web/src/features/results/workspace.tsx',
    'web/src/lib/api-source.ts', 'web/src/lib/data.ts', 'web/src/lib/proposal-types.ts', 'web/src/lib/types.ts',
    'docs/decisions.md', 'docs/Studio_Fixes_Verification_20260929.md', 'release-studio-fixes.ps1'
)
foreach ($staged in (& git diff --cached --name-only)) {
    if ($staged -notin $changedFiles) { throw "Unrelated staged file: $staged" }
}
Invoke-Native 'git' (@('add', '--') + $changedFiles)
Invoke-Native 'git' @('diff', '--cached', '--check')
& git diff --cached --quiet
if ($LASTEXITCODE -eq 1) {
    Invoke-Native 'git' @('commit', '-m', 'Finish studio reliability fixes and regression coverage')
} elseif ($LASTEXITCODE -ne 0) { throw 'Could not inspect the staged changes.' }
Invoke-Native 'git' @('push', 'origin', 'main')
$codeCommit = (& git rev-parse --short HEAD).Trim()
if ($codeCommit -notmatch '^[0-9a-f]+$') { throw 'Could not identify the release commit.' }
$image = "europe-west1-docker.pkg.dev/paperaid-ca172/paperaid/backend:studio-$codeCommit"
Invoke-Native 'gcloud.cmd' @('builds', 'submit', $backendDir, '--tag', $image, '--project', 'paperaid-ca172', '--region', 'europe-west1', '--quiet')
$digest = (& gcloud.cmd artifacts docker images describe $image --project paperaid-ca172 '--format=value(image_summary.digest)').Trim()
if ($LASTEXITCODE -ne 0 -or $digest -notmatch '^sha256:[0-9a-f]{64}$') { throw 'Could not obtain the built image digest.' }
$immutableImage = "europe-west1-docker.pkg.dev/paperaid-ca172/paperaid/backend@$digest"
foreach ($service in @('paperaid-worker', 'paperaid-api')) {
    Invoke-Native 'gcloud.cmd' @('run', 'deploy', $service, '--image', $immutableImage, '--project', 'paperaid-ca172', '--region', 'europe-west1', '--quiet')
}
Invoke-Native 'firebase.cmd' @('deploy', '--only', 'hosting', '--project', 'paperaid-ca172', '--non-interactive')
$apiRevision = (& gcloud.cmd run services describe paperaid-api --project paperaid-ca172 --region europe-west1 '--format=value(status.latestReadyRevisionName)').Trim()
if ($LASTEXITCODE -ne 0) { throw 'Could not confirm the API revision.' }
$workerRevision = (& gcloud.cmd run services describe paperaid-worker --project paperaid-ca172 --region europe-west1 '--format=value(status.latestReadyRevisionName)').Trim()
if ($LASTEXITCODE -ne 0) { throw 'Could not confirm the worker revision.' }
$logPath = Join-Path $repoRoot 'docs\deployment.md'
$log = [System.IO.File]::ReadAllText($logPath)
$separator = '|---|---|---|---|---|---|'
$row = '| ' + (Get-Date -Format 'yyyy-MM-dd') + ' | `' + $codeCommit + '` | `studio-' + $codeCommit + '` (`' + $digest + '`) | `' + $apiRevision + '` | `' + $workerRevision + '` | studio reliability fixes; hosting deployed |'
if (-not $log.Contains($separator)) { throw 'Release-log table was not found.' }
[System.IO.File]::WriteAllText($logPath, $log.Replace($separator, $separator + [Environment]::NewLine + $row))
Invoke-Native 'git' @('add', '--', 'docs/deployment.md')
Invoke-Native 'git' @('commit', '-m', "Record studio release against $codeCommit")
Invoke-Native 'git' @('push', 'origin', 'main')
Write-Output 'Deployment completed: https://paperaid-ca172.web.app'
Write-Output 'Refresh the site and verify the signed-in PC/Android workflow and downloaded Word files.'
