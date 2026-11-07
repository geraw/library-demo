param(
    [Parameter(Mandatory=$true)][string]$ReferenceCampaignPath,
    [string]$ProvengoJar
)
$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path (Join-Path $PSScriptRoot '..\..\..')).Path
$python = Join-Path $repo '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) { throw "Repository Python not found: $python" }
Get-Command java -ErrorAction Stop | Out-Null
$arguments = @((Join-Path $PSScriptRoot 'resample_split_v009.py'), '--reference-campaign', $ReferenceCampaignPath)
if ($ProvengoJar) { $arguments += @('--jar', $ProvengoJar) }
& $python @arguments
if ($LASTEXITCODE -ne 0) { throw 'v009 stopped. Evidence is preserved in V009_REVIEW_ZIP if available.' }
