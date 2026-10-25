[CmdletBinding()]
param(
    [string]$OriginalRepo = 'C:\work\temp\vikunja_study',
    [string]$StudyRoot = 'C:\work\temp\gitea_tse_study',
    [string]$ProvengoJar = 'C:\work\temp\vikunja_tse_study\Provengo-2026-01-10.uber.jar',
    [string]$Package,
    [ValidateRange(1,2147483647)][int]$Seed = 1,
    [string]$Python = 'python'
)
$ErrorActionPreference = 'Stop'
$argsForPython = @((Join-Path $PSScriptRoot 'work_v001.py'),
    '--original-repo', $OriginalRepo, '--study-root', $StudyRoot,
    '--jar', $ProvengoJar, '--seed', [string]$Seed)
if ($Package) { $argsForPython += @('--package', $Package) }
& $Python @argsForPython
if ($LASTEXITCODE -ne 0) {
    throw 'Work integration incomplete. Keep local evidence and inspect INTEGRATION_STATUS. Upload only UPLOAD THIS FILE if printed.'
}
