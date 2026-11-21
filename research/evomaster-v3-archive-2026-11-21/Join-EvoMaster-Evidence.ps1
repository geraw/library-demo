[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$RepositoryPath,

    [Parameter(Mandatory = $true)]
    [string]$DestinationPath
)

$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path -LiteralPath $RepositoryPath).Path
$evidenceDirectory = Join-Path $repo 'research/evomaster-v3-archive-2026-11-21/evidence'
$manifestPath = Join-Path $evidenceDirectory 'parts-manifest.json'
if (-not (Test-Path -LiteralPath $manifestPath)) {
    throw "Evidence manifest not found: $manifestPath"
}

$manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
$destination = [System.IO.Path]::GetFullPath($DestinationPath)
$destinationParent = Split-Path -Parent $destination
if (-not (Test-Path -LiteralPath $destinationParent)) {
    New-Item -ItemType Directory -Path $destinationParent -Force | Out-Null
}
if (Test-Path -LiteralPath $destination) {
    throw "Destination already exists; no file was overwritten: $destination"
}

$outputStream = [System.IO.File]::Open(
    $destination,
    [System.IO.FileMode]::CreateNew,
    [System.IO.FileAccess]::Write,
    [System.IO.FileShare]::None
)
try {
    foreach ($part in $manifest.parts) {
        if ([System.IO.Path]::GetFileName($part.file) -ne $part.file) {
            throw "Invalid part filename in manifest: $($part.file)"
        }
        $partPath = Join-Path $evidenceDirectory $part.file
        if (-not (Test-Path -LiteralPath $partPath)) {
            throw "Archive part is missing: $partPath"
        }
        $actualHash = (Get-FileHash -LiteralPath $partPath -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($actualHash -ne $part.sha256) {
            throw "Checksum mismatch for $($part.file)"
        }
        $inputStream = [System.IO.File]::OpenRead($partPath)
        try {
            $inputStream.CopyTo($outputStream)
        } finally {
            $inputStream.Dispose()
        }
    }
    $outputStream.Flush()
} finally {
    $outputStream.Dispose()
}

$actualSize = (Get-Item -LiteralPath $destination).Length
if ($actualSize -ne [int64]$manifest.archive_size_bytes) {
    Remove-Item -LiteralPath $destination -Force
    throw 'Reassembled archive size does not match the manifest.'
}
$actualHash = (Get-FileHash -LiteralPath $destination -Algorithm SHA256).Hash.ToLowerInvariant()
if ($actualHash -ne $manifest.archive_sha256) {
    Remove-Item -LiteralPath $destination -Force
    throw 'Reassembled archive SHA-256 does not match the manifest.'
}

Write-Host "Reassembled and verified: $destination"
Write-Host "Archive SHA-256: $actualHash"
