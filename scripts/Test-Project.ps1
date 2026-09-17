[CmdletBinding()]
param()

$ErrorActionPreference = 'Continue'

# Verified working as of ROADMAP.md's 2026-08-28 status note:
#   backend: 435 passed | frontend/e2e: 4 Playwright tests passed
# Keep this list in sync with AGENTS.md's "Build & test commands" section.
$Commands = @(
    'python -m pytest backend/tests',
    'npm test'
)

if ($Commands.Count -eq 0) {
    Write-Host 'Test-Project.ps1: no commands configured yet.'
    exit 0
}

$failed = $false
foreach ($cmd in $Commands) {
    Write-Host "=== Running: $cmd ==="
    cmd /c $cmd
    if ($LASTEXITCODE -ne 0) {
        Write-Host "FAILED ($LASTEXITCODE): $cmd"
        $failed = $true
    }
}

if ($failed) {
    Write-Host ''
    Write-Host 'Test-Project.ps1: one or more checks failed. Do not report this task done.'
    exit 2
}

Write-Host ''
Write-Host 'Test-Project.ps1: all checks passed.'
exit 0
