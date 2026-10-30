param(
    [string]$Python = '',
    [string]$InnoCompiler = '.tools\inno\ISCC.exe',
    [string]$SignThumbprint = '',
    [string]$SignToolPath = '',
    [ValidateSet('CurrentUser', 'LocalMachine')][string]$CertificateStore = 'CurrentUser',
    [switch]$AllowUnsignedPreview,
    [switch]$SkipInstaller
)
$ErrorActionPreference = 'Stop'
& (Join-Path $PSScriptRoot 'build_desktop.ps1') @PSBoundParameters
exit $LASTEXITCODE
