param([Parameter(Mandatory=$true)][string]$ControlCampaignPath)
$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path (Join-Path $PSScriptRoot '..\..\..')).Path
$python = Join-Path $repo '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) { throw "Repository Python not found: $python" }
& $python (Join-Path $PSScriptRoot 'mutant_pilot_v008.py') --control-campaign $ControlCampaignPath
if ($LASTEXITCODE -ne 0) { throw 'v008 incomplete. Inspect V008_REVIEW_ZIP if available.' }
