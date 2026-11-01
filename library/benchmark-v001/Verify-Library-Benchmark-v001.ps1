[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
$python = Join-Path $PSScriptRoot '.venv-benchmark-v001\Scripts\python.exe'
if (-not (Test-Path $python)) { throw 'Run Setup first.' }
& $python -m unittest discover -s (Join-Path $PSScriptRoot 'tests') -p 'test_*.py' -v
if ($LASTEXITCODE -ne 0) { throw 'Verification failed.' }
Write-Host 'LIBRARY_BENCHMARK_V001_VERIFICATION_PASS'
