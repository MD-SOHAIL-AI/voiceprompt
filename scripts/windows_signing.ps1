# Shared by the build and release audit. No certificates or trust roots are created.
function Resolve-VoicePromptSignTool {
    param([string]$Path = '')
    if ($Path) { return (Resolve-Path -LiteralPath $Path -ErrorAction Stop).Path }
    $command = Get-Command signtool.exe -ErrorAction SilentlyContinue
    if ($command) { return $command.Source }
    $root = Split-Path -Parent $PSScriptRoot
    $patterns = @(
        (Join-Path ${env:ProgramFiles(x86)} 'Windows Kits\10\bin\*\x64\signtool.exe'),
        (Join-Path $root '.tools\windows-sdk-buildtools-*\bin\*\x64\signtool.exe')
    )
    $tools = @(Get-ChildItem -Path $patterns -File -ErrorAction SilentlyContinue | Sort-Object FullName -Descending)
    if ($tools.Count) { return $tools[0].FullName }
    throw 'Windows SDK signtool.exe is required. Install the Windows SDK or supply -SignToolPath.'
}

function Initialize-VoicePromptSigning {
    param(
        [string]$Thumbprint = '',
        [switch]$AllowUnsignedPreview,
        [string]$SignToolPath = '',
        [ValidateSet('CurrentUser', 'LocalMachine')][string]$CertificateStore = 'CurrentUser'
    )
    if ($Thumbprint -and $AllowUnsignedPreview) {
        throw 'Choose a signed release or -AllowUnsignedPreview, not both.'
    }
    if (-not $Thumbprint) {
        if (-not $AllowUnsignedPreview) {
            throw 'Release blocked: a trusted code-signing identity is required. Supply -SignThumbprint, or explicitly use -AllowUnsignedPreview for testing. See docs/windows-signing.md.'
        }
        Write-Warning 'Unsigned preview: Windows SmartScreen may block this package. This is not a signed public release.'
        return [pscustomobject]@{ Enabled = $false; Thumbprint = ''; SignToolPath = ''; CertificateStore = $CertificateStore }
    }
    $Thumbprint = ($Thumbprint -replace '\s', '').ToUpperInvariant()
    if ($Thumbprint -notmatch '^[A-F0-9]{40}$') { throw 'SignThumbprint must be a 40-character certificate thumbprint.' }
    $certificate = Get-Item -LiteralPath ("Cert:\{0}\My\{1}" -f $CertificateStore, $Thumbprint) -ErrorAction Stop
    if (-not $certificate.HasPrivateKey) { throw 'The signing certificate has no accessible private key. Connect its token or configure its signing provider.' }
    $now = Get-Date
    if ($certificate.NotBefore -gt $now -or $certificate.NotAfter -le $now) { throw 'The signing certificate is not currently valid.' }
    if ($certificate.Subject -eq $certificate.Issuer) { throw 'Self-signed certificates cannot be used for public releases.' }
    $usages = @($certificate.EnhancedKeyUsageList | ForEach-Object { $_.ObjectId.Value })
    if ($usages -notcontains '1.3.6.1.5.5.7.3.3') { throw 'The selected certificate is not authorized for code signing.' }
    return [pscustomobject]@{
        Enabled = $true; Thumbprint = $Thumbprint
        SignToolPath = (Resolve-VoicePromptSignTool -Path $SignToolPath)
        CertificateStore = $CertificateStore
    }
}

function Assert-VoicePromptSignature {
    param([string]$Path, [string]$ExpectedThumbprint = '')
    $signature = Get-AuthenticodeSignature -LiteralPath $Path -ErrorAction Stop
    if ($signature.Status -ne 'Valid') { throw "Untrusted or invalid signature on ${Path}: $($signature.Status)" }
    if (-not $signature.TimeStamperCertificate) { throw "Missing trusted timestamp on $Path" }
    if ($ExpectedThumbprint -and $signature.SignerCertificate.Thumbprint -ne $ExpectedThumbprint) {
        throw "Unexpected signing identity on $Path"
    }
    return $signature
}

function Invoke-VoicePromptSigning {
    param($Signing, [string]$Path)
    if (-not $Signing.Enabled) { throw 'Signing requires a configured publisher identity.' }
    $arguments = @('sign', '/sha1', $Signing.Thumbprint, '/fd', 'SHA256', '/tr', 'http://timestamp.digicert.com', '/td', 'SHA256', '/d', 'VoicePrompt')
    if ($Signing.CertificateStore -eq 'LocalMachine') { $arguments += '/sm' }
    & $Signing.SignToolPath @arguments $Path
    if ($LASTEXITCODE -ne 0) { throw "Signing or timestamping failed for $Path" }
    & $Signing.SignToolPath verify /pa /all /tw $Path
    if ($LASTEXITCODE -ne 0) { throw "Authenticode verification failed for $Path" }
    Assert-VoicePromptSignature -Path $Path -ExpectedThumbprint $Signing.Thumbprint | Out-Null
}

function Get-VoicePromptInnoSignTool {
    param($Signing)
    # Inno substitutes $q/$f itself. Escape literal dollars in the SDK path.
    $toolPath = $Signing.SignToolPath.Replace('$', '$$')
    $command = '/Svoiceprompt=$q' + $toolPath + '$q sign /sha1 ' + $Signing.Thumbprint +
        ' /fd SHA256 /tr http://timestamp.digicert.com /td SHA256 /d $qVoicePrompt$q'
    if ($Signing.CertificateStore -eq 'LocalMachine') { $command += ' /sm' }
    return ($command + ' $f')
}
