param([string]$Destination = '')
$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path (Join-Path $PSScriptRoot '..\..\..')).Path
if (-not $Destination) { $Destination = Join-Path $env:USERPROFILE 'Downloads' }
New-Item -ItemType Directory -Force $Destination | Out-Null
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss-fff'
$staging = Join-Path $Destination ("ISSTA-home-v001-" + $stamp)
New-Item -ItemType Directory $staging | Out-Null
Copy-Item -LiteralPath (Join-Path $repo 'library') -Destination $staging -Recurse
foreach ($name in @('README.md','TODO.md')) {
    $path = Join-Path $repo $name
    if (Test-Path $path) { Copy-Item -LiteralPath $path -Destination $staging }
}
git -C $repo rev-parse HEAD | Set-Content (Join-Path $staging 'git-head.txt')
if ($LASTEXITCODE -ne 0) { throw 'Cannot capture Git HEAD.' }
git -C $repo status --short | Set-Content (Join-Path $staging 'git-status.txt')
if ($LASTEXITCODE -ne 0) { throw 'Cannot capture Git status.' }
git -C $repo diff --binary "--output=$(Join-Path $staging 'source-diff.patch')"
if ($LASTEXITCODE -ne 0) { throw 'Cannot capture unstaged diff.' }
git -C $repo diff --cached --binary "--output=$(Join-Path $staging 'staged-diff.patch')"
if ($LASTEXITCODE -ne 0) { throw 'Cannot capture staged diff.' }
git -C $repo bundle create (Join-Path $staging 'repository.bundle') --all
if ($LASTEXITCODE -ne 0) { throw 'Cannot create Git bundle.' }
$logs = Join-Path $staging 'downloaded-logs'
New-Item -ItemType Directory $logs | Out-Null
Get-ChildItem -LiteralPath (Join-Path $env:USERPROFILE 'Downloads') -Filter 'strict-guided-*.log' -File |
    Copy-Item -Destination $logs
$manifest = @(Get-ChildItem -LiteralPath $staging -File -Recurse | ForEach-Object {
    [pscustomobject]@{
        Path = $_.FullName.Substring($staging.Length + 1)
        Bytes = $_.Length
        SHA256 = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash
    }
})
$manifest | ConvertTo-Json -Depth 4 | Set-Content -Encoding UTF8 (Join-Path $staging 'SHA256.json')
$zip = $staging + '.zip'
Compress-Archive -Path (Join-Path $staging '*') -DestinationPath $zip
Write-Host "HOME_TRANSFER_ZIP $zip"
Write-Host "ZIP_SHA256 $((Get-FileHash -LiteralPath $zip -Algorithm SHA256).Hash)"
Write-Host 'Installed tool binaries and .venv are not included. Keep the staging directory until transfer is verified.'
