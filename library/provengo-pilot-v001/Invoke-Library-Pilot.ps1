[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$RepoPath,
    [ValidateRange(1,10000)][int]$SampleSize = 100,
    [ValidateRange(1,10000)][int]$MaxLength = 2000,
    [int]$Seed = 1,
    [ValidateRange(1024,65535)][int]$Port = 23443,
    [ValidateRange(1,7200)][int]$CaseTimeout = 300,
    [ValidateRange(1,7200)][int]$SampleTimeout = 300,
    [string]$ConfigPath,
    [string]$OutputPath
)
$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path -LiteralPath $RepoPath).Path
$benchmark = Join-Path $repo 'library\benchmark-v001'
$python = Join-Path $benchmark '.venv-benchmark-v001\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) {
    throw 'Run Setup-Library-Benchmark-v001.ps1 in library\benchmark-v001 first.'
}
if (-not $ConfigPath) { $ConfigPath = Join-Path $benchmark 'tools.local.json' }
$arguments = @(
    (Join-Path $PSScriptRoot 'pilot_library.py')
    '--benchmark', $benchmark
    '--original', (Join-Path $repo 'library\sut\sut.py')
    '--mutants', (Join-Path $PSScriptRoot 'sut_buggy_library.py')
    '--config', $ConfigPath
    '--sample-size', "$SampleSize"
    '--max-length', "$MaxLength"
    '--seed', "$Seed"
    '--port', "$Port"
    '--case-timeout', "$CaseTimeout"
    '--sample-timeout', "$SampleTimeout"
)
if ($OutputPath) { $arguments += @('--output', $OutputPath) }
& $python @arguments
if ($LASTEXITCODE -ne 0) { throw 'Pilot incomplete. See the printed RUN_DIRECTORY.' }
