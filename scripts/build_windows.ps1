param(
    [string]$Python = '.venv\Scripts\python.exe',
    [string]$InnoCompiler = '.tools\inno\ISCC.exe',
    [string]$SignThumbprint = '',
    [switch]$SkipInstaller
)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Push-Location -LiteralPath $projectRoot
try {
    & $Python packaging\prepare_build.py
    if ($LASTEXITCODE -ne 0) { throw 'Build preparation failed' }
    & $Python -m PyInstaller --noconfirm packaging\VoicePrompt.spec
    if ($LASTEXITCODE -ne 0) { throw 'Application bundling failed' }
    if ($SignThumbprint) {
        & signtool sign /sha1 $SignThumbprint /fd SHA256 /tr http://timestamp.digicert.com /td SHA256 dist\VoicePrompt\VoicePrompt.exe
        if ($LASTEXITCODE -ne 0) { throw 'Application signing failed' }
    }
    $smokeOutput = Join-Path $projectRoot 'build\frozen-smoke.json'
    if (Test-Path -LiteralPath $smokeOutput) { Remove-Item -LiteralPath $smokeOutput }
    $smoke = Start-Process -FilePath (Join-Path $projectRoot 'dist\VoicePrompt\VoicePrompt.exe') -ArgumentList @('--smoke-test', ('"' + $smokeOutput + '"')) -WindowStyle Hidden -PassThru
    if (-not $smoke.WaitForExit(180000)) { $smoke.Kill(); throw 'Frozen smoke check timed out' }
    if ($smoke.ExitCode -ne 0 -or -not (Test-Path -LiteralPath $smokeOutput)) { throw 'Frozen smoke check failed' }
    $smokeResult = Get-Content -LiteralPath $smokeOutput -Raw | ConvertFrom-Json
    if ($smokeResult.error -or @($smokeResult.workers.PSObject.Properties).Count -ne 4 -or -not $smokeResult.rnnoise) {
        throw 'Frozen checks did not verify every speech engine and the noise library'
    }
    New-Item -ItemType Directory -Force -Path release | Out-Null
    if (-not $SkipInstaller) {
        if (-not (Test-Path -LiteralPath $InnoCompiler)) {
            $installed = 'C:\Program Files (x86)\Inno Setup 6\ISCC.exe'
            if (Test-Path -LiteralPath $installed) { $InnoCompiler = $installed }
            else { throw 'Inno Setup compiler missing. Supply -InnoCompiler or use -SkipInstaller.' }
        }
        & $InnoCompiler packaging\VoicePrompt.iss
        if ($LASTEXITCODE -ne 0) { throw 'Installer compilation failed' }
        if ($SignThumbprint) {
            & signtool sign /sha1 $SignThumbprint /fd SHA256 /tr http://timestamp.digicert.com /td SHA256 release\VoicePrompt-Setup-0.4.1-x64.exe
            if ($LASTEXITCODE -ne 0) { throw 'Installer signing failed' }
        }
    }
    Get-ChildItem -LiteralPath release -Filter '*.exe' | ForEach-Object {
        $hash = Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256
        ($hash.Hash.ToLowerInvariant() + '  ' + $_.Name) | Set-Content -LiteralPath ($_.FullName + '.sha256') -Encoding ascii
    }
    Write-Output 'Build complete. Artifacts are in release/; smoke evidence is in build/frozen-smoke.json.'
}
finally { Pop-Location }
