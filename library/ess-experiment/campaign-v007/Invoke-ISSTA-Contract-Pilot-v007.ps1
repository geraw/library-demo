param(
    [Parameter(Mandatory=$true)][string]$CampaignPath,
    [string]$PreviousPilot,
    [ValidateSet('both','restler','evomaster')][string]$Tools = 'both',
    [ValidateRange(30,300)][int]$Seconds = 60,
    [string]$EvoMasterJar,
    [string]$RestlerPath,
    [switch]$InstallLocalTools
)
$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path (Join-Path $PSScriptRoot '..\..\..')).Path
$python = Join-Path $repo '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) { throw "Repository Python not found: $python" }
$arguments = @((Join-Path $PSScriptRoot 'contract_pilot_v007.py'), '--campaign', $CampaignPath, '--tools', $Tools, '--seconds', "$Seconds")
if ($PreviousPilot) { $arguments += @('--previous-pilot', $PreviousPilot) }
if ($EvoMasterJar) { $arguments += @('--evomaster-jar', $EvoMasterJar) }
if ($RestlerPath) { $arguments += @('--restler', $RestlerPath) }
if ($InstallLocalTools) { $arguments += '--install-local-tools' }
& $python @arguments
if ($LASTEXITCODE -ne 0) { throw 'v007 pilot incomplete. Inspect V007_REVIEW_ZIP if available.' }
