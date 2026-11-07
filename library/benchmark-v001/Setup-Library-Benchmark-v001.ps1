[CmdletBinding()]
param(
    [string]$ProvengoJar,
    [string]$EvoMasterJar,
    [string]$RestlerPath,
    [string]$Java = 'java',
    [string]$AnalyzerHome,
    [switch]$InstallNativeTools
)
$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$venv = Join-Path $root '.venv-benchmark-v001'
$python = Join-Path $venv 'Scripts\python.exe'
if (-not (Test-Path $python)) {
    if (Get-Command py -ErrorAction SilentlyContinue) { & py -3 -m venv $venv }
    elseif (Get-Command python -ErrorAction SilentlyContinue) { & python -m venv $venv }
    else { throw 'Python 3.10+ is required. Install Python, then repeat this command.' }
    if ($LASTEXITCODE -ne 0) { throw 'Virtual environment creation failed.' }
}
& $python -c 'import sys; assert sys.version_info >= (3,10), "Python 3.10+ required"'
if ($LASTEXITCODE -ne 0) { throw 'Unsupported Python version.' }
& $python -m pip install -r (Join-Path $root 'requirements-v001.txt')
if ($LASTEXITCODE -ne 0) { throw 'Python dependency installation failed.' }
& $python -m unittest discover -s (Join-Path $root 'tests') -p 'test_*.py' -v
if ($LASTEXITCODE -ne 0) { throw 'Benchmark verification failed; no campaign was started.' }
$arguments = @((Join-Path $root 'configure_v001.py'), '--java', $Java)
if ($ProvengoJar) { $arguments += @('--provengo-jar', $ProvengoJar) }
if ($EvoMasterJar) { $arguments += @('--evomaster-jar', $EvoMasterJar) }
if ($RestlerPath) { $arguments += @('--restler', $RestlerPath) }
if ($AnalyzerHome) { $arguments += @('--analyzer-home', $AnalyzerHome) }
if ($InstallNativeTools) { $arguments += '--install-native' }
& $python @arguments
if ($LASTEXITCODE -ne 0) { throw 'Tool configuration failed. The actual failure is printed above and saved under library/benchmark-v001/setup-logs. No campaign was started.' }
Write-Host 'LIBRARY_BENCHMARK_V001_SETUP_COMPLETE'
