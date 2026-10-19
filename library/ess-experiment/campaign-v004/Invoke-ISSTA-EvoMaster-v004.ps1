param(
    [Parameter(Mandatory=$true)][string]$CampaignPath,
    [Parameter(Mandatory=$true)][string]$EvoMasterJar
)
$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path (Join-Path $PSScriptRoot '..\..\..')).Path
$python = Join-Path $repo '.venv\Scripts\python.exe'
if (-not (Test-Path $EvoMasterJar)) { throw 'EvoMaster JAR does not exist.' }
if (-not (Test-Path (Join-Path $CampaignPath 'budget.json'))) {
    throw 'A completed Provengo campaign budget.json is required. No default budget is substituted.'
}
& $python (Join-Path $PSScriptRoot 'campaign_v004.py') evomaster `
    --campaign $CampaignPath --jar $EvoMasterJar
if ($LASTEXITCODE -ne 0) { throw 'EvoMaster stopped. Inspect its output directory.' }
