[CmdletBinding()]
param(
    [string]$EvidenceZip,
    [string]$WorkBase = 'D:\Yeshayahu\Temp\ProvengoWork',
    [string]$OutputBase = 'E:\ProvengoRuns',
    [ValidateRange(0,100)][int]$Limit = 10
)
$ErrorActionPreference = 'Stop'
if (-not $EvidenceZip) {
    $latest = Get-ChildItem -LiteralPath $OutputBase -File -Filter 'library-ssd-campaign-*-analysis-*.zip' |
        Sort-Object Name -Descending | Select-Object -First 1
    if (-not $latest) { throw 'Pass -EvidenceZip with the existing analysis ZIP path.' }
    $EvidenceZip = $latest.FullName
}
if (-not (Test-Path -LiteralPath $EvidenceZip -PathType Leaf)) { throw 'Evidence ZIP not found.' }
$python = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) {
    python -m venv (Join-Path $PSScriptRoot '.venv')
    if ($LASTEXITCODE -ne 0) { throw 'Virtual environment creation failed.' }
}
& $python -m pip install -r (Join-Path $PSScriptRoot 'requirements.txt')
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
& $python (Join-Path $PSScriptRoot 'verify.py')
if ($LASTEXITCODE -ne 0) { throw 'Directed verification failed.' }
$tag = 'library-v002-' + (Get-Date -Format 'yyyyMMdd-HHmmss-fff')
$work = Join-Path $WorkBase $tag
$output = Join-Path $OutputBase $tag
Write-Host "ENGINE Flask test_client projected replay (not Provengo)"
Write-Host "RESULT_DIRECTORY $output"
& $python (Join-Path $PSScriptRoot 'replay.py') --evidence $EvidenceZip --work $work --output $output --limit $Limit
if ($LASTEXITCODE -ne 0) { throw 'Replay stopped; working evidence retained.' }
