$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
. (Join-Path $root 'scripts\windows_signing.ps1')
$script:checks = 0
function Assert-Check([bool]$Condition, [string]$Message) {
    if (-not $Condition) { throw $Message }
    $script:checks++
}
function Assert-Rejected([scriptblock]$Action, [string]$Message) {
    $failure = $null
    try { & $Action | Out-Null } catch { $failure = $_.Exception.Message }
    Assert-Check ($null -ne $failure -and $failure -like ('*' + $Message + '*')) "Expected rejection containing '$Message', got '$failure'"
}

# These checks run before a Python/Rust build or any staging-directory mutation.
Assert-Rejected { Initialize-VoicePromptSigning } 'Release blocked'
Assert-Rejected { & (Join-Path $root 'scripts\build_desktop.ps1') -Python 'must-not-run.exe' } 'Release blocked'
Assert-Rejected { & (Join-Path $root 'scripts\build_windows.ps1') -Python 'must-not-run.exe' } 'Release blocked'
Assert-Rejected { Initialize-VoicePromptSigning -Thumbprint ('A' * 40) -AllowUnsignedPreview } 'not both'
Assert-Rejected { Initialize-VoicePromptSigning -Thumbprint 'invalid' } '40-character'
$preview = Initialize-VoicePromptSigning -AllowUnsignedPreview -WarningAction SilentlyContinue
Assert-Check (-not $preview.Enabled) 'Explicit unsigned preview must not enable signing'

# Model the Windows signature API; never import a certificate or change trust.
$global:VoicePromptTestidentity = 'A' * 40
$global:VoicePromptTestsignatureStatus = 'Valid'
$global:VoicePromptTestsigner = $global:VoicePromptTestidentity
$global:VoicePromptTesttimestamp = [pscustomobject]@{ Subject = 'CN=Test timestamp authority' }
$global:VoicePromptTestDifferentEngineSigner = $false
function Get-AuthenticodeSignature {
    param([string]$LiteralPath)
    $thumbprint = if ($global:VoicePromptTestDifferentEngineSigner -and $LiteralPath.EndsWith('VoicePromptEngine.exe')) { 'B' * 40 } else { $global:VoicePromptTestsigner }
    [pscustomobject]@{
        Status = $global:VoicePromptTestsignatureStatus
        SignerCertificate = $(if ($global:VoicePromptTestsignatureStatus -eq 'NotSigned') { $null } else { [pscustomobject]@{ Subject = 'CN=Test Publisher'; Thumbprint = $thumbprint } })
        TimeStamperCertificate = $global:VoicePromptTesttimestamp
    }
}
Assert-VoicePromptSignature -Path 'test.exe' -ExpectedThumbprint $global:VoicePromptTestidentity | Out-Null
$script:checks++
$global:VoicePromptTesttimestamp = $null
Assert-Rejected { Assert-VoicePromptSignature -Path 'test.exe' } 'timestamp'
$global:VoicePromptTesttimestamp = [pscustomobject]@{ Subject = 'CN=Test timestamp authority' }
$global:VoicePromptTestsigner = 'B' * 40
Assert-Rejected { Assert-VoicePromptSignature -Path 'test.exe' -ExpectedThumbprint $global:VoicePromptTestidentity } 'Unexpected signing identity'
$global:VoicePromptTestsigner = $global:VoicePromptTestidentity
$global:VoicePromptTestsignatureStatus = 'HashMismatch'
Assert-Rejected { Assert-VoicePromptSignature -Path 'test.exe' } 'HashMismatch'
$global:VoicePromptTestsignatureStatus = 'NotTrusted'
Assert-Rejected { Assert-VoicePromptSignature -Path 'test.exe' } 'NotTrusted'
$global:VoicePromptTestsignatureStatus = 'Valid'

$script:toolExitCode = 0
$script:toolCalls = @()
function Test-SignTool {
    $script:toolCalls += ,@($args)
    $global:LASTEXITCODE = $script:toolExitCode
}
$signing = [pscustomobject]@{ Enabled = $true; Thumbprint = $global:VoicePromptTestidentity; SignToolPath = 'Test-SignTool'; CertificateStore = 'LocalMachine' }
Invoke-VoicePromptSigning -Signing $signing -Path "C:\build's path\app.exe"
Assert-Check ($script:toolCalls.Count -eq 2) 'Signing must also run verification'
Assert-Check ($script:toolCalls[0] -contains '/sm') 'Machine certificate store must be honored'
Assert-Check ($script:toolCalls[0] -contains '/tr' -and $script:toolCalls[0] -contains 'SHA256') 'Signing must request a SHA-256 timestamp'
Assert-Check ($script:toolCalls[1] -contains '/pa' -and $script:toolCalls[1] -contains '/tw') 'Verification must require Authenticode and a timestamp'
$script:toolExitCode = 2
Assert-Rejected { Invoke-VoicePromptSigning -Signing $signing -Path 'test.exe' } 'Signing or timestamping failed'
$script:toolExitCode = 0
$signing.SignToolPath = 'C:\SDK $tools\signtool.exe'
$innoTool = Get-VoicePromptInnoSignTool -Signing $signing
Assert-Check ($innoTool.Contains('$qC:\SDK $$tools\signtool.exe$q') -and $innoTool.EndsWith(' $f')) 'Inno must quote SDK and artifact paths and escape literal dollars'

$temporary = Join-Path ([IO.Path]::GetTempPath()) ('voiceprompt-signing-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path (Join-Path $temporary 'engine') -Force | Out-Null
try {
    $global:VoicePromptTestCertificate = [pscustomobject]@{
        Subject = 'CN=Test Publisher'; Issuer = 'CN=Test CA'; HasPrivateKey = $true
        NotBefore = (Get-Date).AddDays(-1); NotAfter = (Get-Date).AddDays(365)
        EnhancedKeyUsageList = @([pscustomobject]@{ ObjectId = [pscustomobject]@{ Value = '1.3.6.1.5.5.7.3.3' } })
    }
    function Get-Item {
        [CmdletBinding()]param([string]$LiteralPath)
        if ($LiteralPath.StartsWith('Cert:\')) { return $global:VoicePromptTestCertificate }
        Microsoft.PowerShell.Management\Get-Item @PSBoundParameters
    }
    $toolFixture = Join-Path $temporary 'SDK tool.exe'
    Set-Content -LiteralPath $toolFixture -Value 'Never executed; certificate preflight fixture.'
    $configured = Initialize-VoicePromptSigning -Thumbprint ('a ' * 40) -SignToolPath $toolFixture -CertificateStore LocalMachine
    Assert-Check ($configured.Enabled -and $configured.Thumbprint -ceq ('A' * 40) -and $configured.CertificateStore -eq 'LocalMachine') 'Certificate identity and store must be normalized correctly'
    $global:VoicePromptTestCertificate.HasPrivateKey = $false
    Assert-Rejected { Initialize-VoicePromptSigning -Thumbprint $global:VoicePromptTestidentity -SignToolPath $toolFixture } 'no accessible private key'
    $global:VoicePromptTestCertificate.HasPrivateKey = $true
    $global:VoicePromptTestCertificate.NotAfter = (Get-Date).AddDays(-1)
    Assert-Rejected { Initialize-VoicePromptSigning -Thumbprint $global:VoicePromptTestidentity -SignToolPath $toolFixture } 'not currently valid'
    $global:VoicePromptTestCertificate.NotAfter = (Get-Date).AddDays(365)
    $global:VoicePromptTestCertificate.NotBefore = (Get-Date).AddDays(1)
    Assert-Rejected { Initialize-VoicePromptSigning -Thumbprint $global:VoicePromptTestidentity -SignToolPath $toolFixture } 'not currently valid'
    $global:VoicePromptTestCertificate.NotBefore = (Get-Date).AddDays(-1)
    $global:VoicePromptTestCertificate.Issuer = $global:VoicePromptTestCertificate.Subject
    Assert-Rejected { Initialize-VoicePromptSigning -Thumbprint $global:VoicePromptTestidentity -SignToolPath $toolFixture } 'Self-signed'
    $global:VoicePromptTestCertificate.Issuer = 'CN=Test CA'
    $global:VoicePromptTestCertificate.EnhancedKeyUsageList = @()
    Assert-Rejected { Initialize-VoicePromptSigning -Thumbprint $global:VoicePromptTestidentity -SignToolPath $toolFixture } 'not authorized for code signing'

    $installer = Join-Path $temporary 'setup.exe'
    foreach ($path in @($installer, (Join-Path $temporary 'VoicePrompt.exe'), (Join-Path $temporary 'engine\VoicePromptEngine.exe'))) {
        Set-Content -LiteralPath $path -Value 'Signing-gate fixture; not an executable.'
    }
    $checksumPath = $installer + '.sha256'
    $checksum = (Get-FileHash -LiteralPath $installer -Algorithm SHA256).Hash.ToLowerInvariant() + '  setup.exe'
    Set-Content -LiteralPath $checksumPath -Value $checksum
    $audit = Join-Path $root 'scripts\check_windows_signing.ps1'
    & $audit -Installer $installer -Stage $temporary -ExpectedThumbprint $global:VoicePromptTestidentity | Out-Null
    $report = Get-Content -LiteralPath ($installer + '.signing.json') -Raw | ConvertFrom-Json
    Assert-Check ($report.signing_verified -and $report.artifacts.Count -eq 3) 'Signed release must audit all three artifacts'
    Assert-Check (-not $report.smartscreen_reputation_verified) 'Signature validity cannot claim SmartScreen reputation'
    $global:VoicePromptTestDifferentEngineSigner = $true
    Assert-Rejected { & $audit -Installer $installer -Stage $temporary } 'same signing identity'
    $global:VoicePromptTestDifferentEngineSigner = $false

    $global:VoicePromptTestsignatureStatus = 'NotSigned'
    $global:VoicePromptTesttimestamp = $null
    Assert-Rejected { & $audit -Installer $installer -Stage $temporary } 'NotSigned'
    & $audit -Installer $installer -Stage $temporary -AllowUnsignedPreview | Out-Null
    $report = Get-Content -LiteralPath ($installer + '.signing.json') -Raw | ConvertFrom-Json
    Assert-Check (-not $report.signing_verified -and $report.mode -eq 'unsigned-preview') 'Unsigned preview cannot pass the signing gate'
    $global:VoicePromptTestsignatureStatus = 'HashMismatch'
    Assert-Rejected { & $audit -Installer $installer -Stage $temporary -AllowUnsignedPreview } 'HashMismatch'

    $global:VoicePromptTestsignatureStatus = 'Valid'
    $global:VoicePromptTesttimestamp = [pscustomobject]@{ Subject = 'CN=Test timestamp authority' }
    Add-Content -LiteralPath $installer -Value 'Tampered after checksumming'
    Assert-Rejected { & $audit -Installer $installer -Stage $temporary } 'SHA-256'
    Set-Content -LiteralPath $checksumPath -Value ((Get-FileHash -LiteralPath $installer -Algorithm SHA256).Hash.ToLowerInvariant() + '  other.exe')
    Assert-Rejected { & $audit -Installer $installer -Stage $temporary } 'SHA-256'
    Remove-Item -LiteralPath $checksumPath
    Assert-Rejected { & $audit -Installer $installer -Stage $temporary } 'SHA-256'
    Set-Content -LiteralPath $checksumPath -Value ((Get-FileHash -LiteralPath $installer -Algorithm SHA256).Hash.ToLowerInvariant() + '  setup.exe')
    Remove-Item -LiteralPath (Join-Path $temporary 'VoicePrompt.exe')
    Assert-Rejected { & $audit -Installer $installer -Stage $temporary } 'Missing artifact'
} finally {
    $resolved = [IO.Path]::GetFullPath($temporary)
    $tempRoot = [IO.Path]::GetFullPath([IO.Path]::GetTempPath()).TrimEnd('\') + '\'
    if (-not $resolved.StartsWith($tempRoot, [StringComparison]::OrdinalIgnoreCase)) { throw 'Test cleanup escaped the temporary directory' }
    Remove-Item -LiteralPath $resolved -Recurse -Force
}
Write-Output ("Windows signing checks passed: $script:checks")
