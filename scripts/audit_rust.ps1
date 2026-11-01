param([string]$Report = 'build\rust-audit-0.6.0.json')
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$destination = Join-Path $root '.tools\cargo-audit-0.22.2'
$archive = Join-Path $root '.tools\cargo-audit-0.22.2.zip'
$expected = '0a7316540862c13d954f648917ceacca593747baed6eec180fafa590be2710ab'
New-Item -ItemType Directory -Force (Split-Path -Parent $archive) | Out-Null
if (-not (Test-Path -LiteralPath $archive) -or (Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant() -ne $expected) {
    Invoke-WebRequest -Uri 'https://github.com/rustsec/rustsec/releases/download/cargo-audit/v0.22.2/cargo-audit-x86_64-pc-windows-msvc-v0.22.2.zip' -OutFile $archive
}
if ((Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant() -ne $expected) { throw 'cargo-audit checksum mismatch' }
$zip = [IO.Compression.ZipFile]::OpenRead($archive)
try {
    foreach ($entry in $zip.Entries) {
        $target = [IO.Path]::GetFullPath((Join-Path $destination $entry.FullName))
        if (-not $target.StartsWith($destination + '\', [StringComparison]::OrdinalIgnoreCase)) { throw 'Unsafe cargo-audit archive path' }
    }
} finally { $zip.Dispose() }
Expand-Archive -LiteralPath $archive -DestinationPath $destination -Force
$executable = Get-ChildItem -LiteralPath $destination -Filter cargo-audit.exe -Recurse -File | Select-Object -First 1
if (-not $executable) { throw 'cargo-audit executable missing' }
Push-Location -LiteralPath $root
try {
    New-Item -ItemType Directory -Force (Split-Path -Parent $Report) | Out-Null
    & $executable.FullName audit --file desktop\src-tauri\Cargo.lock --json --db .tools\rustsec-advisories > $Report
    if ($LASTEXITCODE -ne 0) { throw ('Rust dependency audit failed; inspect ' + $Report) }
} finally { Pop-Location }
