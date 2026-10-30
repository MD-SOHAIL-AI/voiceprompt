param(
    [string]$Installer = '',
    [string]$Stage = '',
    [string]$ExpectedThumbprint = '',
    [string]$ReportPath = '',
    [switch]$AllowUnsignedPreview
)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'windows_signing.ps1')
$projectRoot = Split-Path -Parent $PSScriptRoot
if (-not $Installer) {
    $version = [regex]::Match((Get-Content (Join-Path $projectRoot 'pyproject.toml') -Raw), '(?m)^version = "([^"]+)"').Groups[1].Value
    $suffix = if ($AllowUnsignedPreview) { '-unsigned-preview' } else { '' }
    $Installer = Join-Path $projectRoot ("release\VoicePrompt-Setup-$version-x64$suffix.exe")
}
if (-not $Stage) { $Stage = Join-Path $projectRoot 'dist\VoicePrompt' }
if (-not $ReportPath) { $ReportPath = $Installer + '.signing.json' }
if ($ExpectedThumbprint) {
    $ExpectedThumbprint = ($ExpectedThumbprint -replace '\s', '').ToUpperInvariant()
    if ($ExpectedThumbprint -notmatch '^[A-F0-9]{40}$') { throw 'ExpectedThumbprint must be a 40-character certificate thumbprint.' }
}
$problems = [System.Collections.Generic.List[string]]::new()
$records = @()
foreach ($path in @($Installer, (Join-Path $Stage 'VoicePrompt.exe'), (Join-Path $Stage 'engine\VoicePromptEngine.exe'))) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        $problems.Add("Missing artifact: $path")
        continue
    }
    $signature = Get-AuthenticodeSignature -LiteralPath $path
    $valid = $signature.Status -eq 'Valid' -and $null -ne $signature.TimeStamperCertificate
    $records += [pscustomobject]@{
        file = (Split-Path -Leaf $path)
        sha256 = (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant()
        signature_status = [string]$signature.Status
        publisher = $signature.SignerCertificate.Subject
        signer_thumbprint = $signature.SignerCertificate.Thumbprint
        timestamp_authority = $signature.TimeStamperCertificate.Subject
        trusted_and_timestamped = $valid
    }
    if (-not $AllowUnsignedPreview -or $signature.Status -ne 'NotSigned') {
        try { Assert-VoicePromptSignature -Path $path -ExpectedThumbprint $ExpectedThumbprint | Out-Null }
        catch { $problems.Add($_.Exception.Message) }
    }
}
if (-not $AllowUnsignedPreview -and @($records | Where-Object { $_.signature_status -eq 'Valid' }).Count -eq 3 -and @($records.signer_thumbprint | Select-Object -Unique).Count -ne 1) {
    $problems.Add('The installer, desktop and engine must use the same signing identity.')
}
$checksumMatches = $false
if ((Test-Path -LiteralPath ($Installer + '.sha256')) -and (Test-Path -LiteralPath $Installer -PathType Leaf)) {
    $expected = (Get-Content -LiteralPath ($Installer + '.sha256') -Raw).Trim()
    $hash = (Get-FileHash -LiteralPath $Installer -Algorithm SHA256).Hash.ToLowerInvariant()
    $checksumMatches = $expected -eq ($hash + '  ' + (Split-Path -Leaf $Installer))
}
if (-not $checksumMatches) { $problems.Add('Installer SHA-256 sidecar is missing or does not match the final installer bytes.') }
$report = [ordered]@{
    checked_at_utc = [DateTime]::UtcNow.ToString('o')
    mode = $(if ($AllowUnsignedPreview) { 'unsigned-preview' } else { 'signed-release' })
    signing_verified = (-not $AllowUnsignedPreview -and $problems.Count -eq 0)
    smartscreen_reputation_verified = $false
    installer_checksum_matches = $checksumMatches
    artifacts = @($records)
    errors = @($problems.ToArray())
}
$report | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $ReportPath -Encoding utf8
if ($problems.Count) { throw ('Windows release verification failed: ' + ($problems -join '; ')) }
Write-Output ("Windows signing audit passed ({0}); report: {1}" -f $report.mode, $ReportPath)
