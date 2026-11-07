$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path (Join-Path $PSScriptRoot '..\..\..')).Path
$python = Join-Path $repo '.venv\Scripts\python.exe'
& $python (Join-Path $PSScriptRoot 'campaign_v004.py') prepare --repo $repo
if ($LASTEXITCODE -ne 0) { throw 'Model preparation failed.' }
