param(
    [string]$ProvengoJar = 'C:\Program Files\Provengo\Provengo Cli\Provengo.uber.jar',
    [string]$Java = 'java',
    [int]$CaseTimeoutSeconds = 120,
    [int]$ArmTimeoutSeconds = 7200,
    [switch]$PrepareOnly
)
$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path (Join-Path $PSScriptRoot '..\..\..')).Path
$python = Join-Path $repo '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) { throw "Repository Python not found: $python" }
if (-not (Test-Path -LiteralPath $ProvengoJar)) { throw "Local Provengo JAR not found: $ProvengoJar" }
Get-Command $Java -ErrorAction Stop | Out-Null
& $python -c 'import flask'
if ($LASTEXITCODE -ne 0) { throw 'Flask is missing from the repository Python environment.' }
$arguments = @((Join-Path $PSScriptRoot 'work_machine_v012.py'), '--jar', $ProvengoJar,
    '--java', $Java, '--case-timeout', $CaseTimeoutSeconds, '--arm-timeout', $ArmTimeoutSeconds)
if ($PrepareOnly) { $arguments += '--prepare-only' }
& $python @arguments
if ($LASTEXITCODE -ne 0) { throw 'v012 stopped. Inspect the console and V011_REVIEW_ZIP if available.' }
