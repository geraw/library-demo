[CmdletBinding()]
param(
    [string]$RepoPath = (Split-Path (Split-Path $PSScriptRoot -Parent) -Parent),
    [Parameter(Mandatory)][string]$ReuseRun,
    [ValidateSet(1,2)][int]$Workers = 2,
    [ValidateRange(1,86400)][int]$CaseTimeout = 7200,
    [switch]$PreflightOnly
)
$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path -LiteralPath $RepoPath).Path
$source = (Resolve-Path -LiteralPath $ReuseRun).Path
$python = Join-Path $repo 'library\benchmark-v001\.venv-benchmark-v001\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) { throw 'The existing benchmark Python environment is missing.' }
$arguments = @(
    (Join-Path $PSScriptRoot 'replay_parallel.py'),
    '--repo', $repo, '--reuse-run', $source,
    '--workers', "$Workers", '--case-timeout', "$CaseTimeout"
)
if ($PreflightOnly) { $arguments += '--preflight-only' }
& $python @arguments
if ($LASTEXITCODE -ne 0) { throw 'Replay stopped. See REPLAY_DIRECTORY and its failure.json.' }
