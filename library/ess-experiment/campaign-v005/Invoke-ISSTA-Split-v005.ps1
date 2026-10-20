param([Parameter(Mandatory=$true)][string]$CampaignPath)
$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path (Join-Path $PSScriptRoot '..\..\..')).Path
& (Join-Path $repo '.venv\Scripts\python.exe') (Join-Path $PSScriptRoot 'split_v005.py') replay --campaign $CampaignPath
if ($LASTEXITCODE -ne 0) { throw 'Split replay stopped. Existing evidence is preserved.' }
