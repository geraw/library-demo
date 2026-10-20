param(
    [Parameter(Mandatory=$true)][string]$CampaignPath,
    [string]$EvoMasterJar,
    [string]$RestlerPath,
    [switch]$InstallLocalTools
)
$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path (Join-Path $PSScriptRoot '..\..\..')).Path
$python = Join-Path $repo '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) { throw "Repository Python not found: $python" }
$arguments = @((Join-Path $PSScriptRoot 'pilot_v006.py'), '--campaign', $CampaignPath)
if ($EvoMasterJar) { $arguments += @('--evomaster-jar', $EvoMasterJar) }
if ($RestlerPath) { $arguments += @('--restler', $RestlerPath) }
if ($InstallLocalTools) { $arguments += '--install-local-tools' }
& $python @arguments
if ($LASTEXITCODE -ne 0) { throw 'Pilot incomplete. Inspect the output and REVIEW_ZIP if available.' }
