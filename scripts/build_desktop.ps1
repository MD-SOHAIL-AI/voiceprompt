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
    $version = [regex]::Match((Get-Content pyproject.toml -Raw), '(?m)^version = "([^"]+)"').Groups[1].Value
    if (-not $version) { throw 'Missing canonical build version' }
    & $Python scripts\verify_versions.py
    if ($LASTEXITCODE -ne 0) { throw 'Build versions disagree' }
    & $Python packaging\prepare_build.py
    if ($LASTEXITCODE -ne 0) { throw 'Build preparation failed' }
    & $Python -m PyInstaller --noconfirm packaging\Engine.spec
    if ($LASTEXITCODE -ne 0) { throw 'Voice engine packaging failed' }
    Push-Location desktop
    try {
        & npm.cmd ci
        if ($LASTEXITCODE -ne 0) { throw 'Frontend dependency installation failed' }
        & npm.cmd run tauri -- build --no-bundle
        if ($LASTEXITCODE -ne 0) { throw 'Native desktop build failed' }
    } finally { Pop-Location }
    $stage = Join-Path $projectRoot 'dist\VoicePrompt'
    if ([IO.Path]::GetFullPath($stage) -ne (Join-Path $projectRoot 'dist\VoicePrompt')) { throw 'Unexpected stage path' }
    # Existing builds remain intact until both components have built successfully.
    # Stage only app-owned files; user data lives outside this directory.
    if (Test-Path -LiteralPath $stage) { Remove-Item -LiteralPath $stage -Recurse -Force }
    New-Item -ItemType Directory -Force -Path $stage | Out-Null
    Copy-Item -LiteralPath 'desktop\src-tauri\target\release\VoicePrompt.exe' -Destination (Join-Path $stage 'VoicePrompt.exe') -Force
    $engineStage = Join-Path $stage 'engine'
    New-Item -ItemType Directory -Force -Path $engineStage | Out-Null
    Get-ChildItem -LiteralPath 'dist\VoicePromptEngine' | Copy-Item -Destination $engineStage -Recurse -Force
    Copy-Item -LiteralPath LICENSE,THIRD_PARTY_NOTICES.md -Destination $stage -Force
    if (Test-Path -LiteralPath 'build\licenses') { Copy-Item -LiteralPath 'build\licenses' -Destination $stage -Recurse -Force }
    $fontLicenses = Join-Path $stage 'licenses\encode-sans'
    New-Item -ItemType Directory -Force -Path $fontLicenses | Out-Null
    Copy-Item -LiteralPath 'desktop\src\assets\fonts\OFL.txt' -Destination $fontLicenses
    if ($SignThumbprint) {
        foreach ($file in @((Join-Path $stage 'VoicePrompt.exe'), (Join-Path $engineStage 'VoicePromptEngine.exe'))) {
            & signtool sign /sha1 $SignThumbprint /fd SHA256 /tr http://timestamp.digicert.com /td SHA256 $file
            if ($LASTEXITCODE -ne 0) { throw 'Executable signing failed' }
        }
    }
    $smokeOutput = Join-Path $projectRoot 'build\frozen-smoke.json'
    if (Test-Path -LiteralPath $smokeOutput) { Remove-Item -LiteralPath $smokeOutput }
    $smoke = Start-Process -FilePath (Join-Path $stage 'VoicePrompt.exe') -ArgumentList @('--smoke-test', ('"' + $smokeOutput + '"')) -WindowStyle Hidden -PassThru
    if (-not $smoke.WaitForExit(180000)) { $smoke.Kill(); throw 'Frozen checks timed out' }
    if ($smoke.ExitCode -ne 0 -or -not (Test-Path -LiteralPath $smokeOutput)) { throw 'Frozen checks failed' }
    $checks = Get-Content -LiteralPath $smokeOutput -Raw | ConvertFrom-Json
    if ($checks.error -or -not $checks.tauri -or @($checks.workers.PSObject.Properties).Count -ne 4 -or -not $checks.rnnoise) { throw 'Frozen checks did not verify Tauri and all speech workers' }
    New-Item -ItemType Directory -Force -Path release | Out-Null
    if (-not $SkipInstaller) {
        if (-not (Test-Path -LiteralPath $InnoCompiler)) { $InnoCompiler = 'C:\Program Files (x86)\Inno Setup 6\ISCC.exe' }
        if (-not (Test-Path -LiteralPath $InnoCompiler)) { throw 'Inno Setup 6 is required for the installer' }
        & $InnoCompiler ('/DAppVersion=' + $version) packaging\VoicePrompt.iss
        if ($LASTEXITCODE -ne 0) { throw 'Installer compilation failed' }
        $installer = Join-Path $projectRoot ('release\VoicePrompt-Setup-' + $version + '-x64.exe')
        if ($SignThumbprint) {
            & signtool sign /sha1 $SignThumbprint /fd SHA256 /tr http://timestamp.digicert.com /td SHA256 $installer
            if ($LASTEXITCODE -ne 0) { throw 'Installer signing failed' }
        }
        $hash = (Get-FileHash -LiteralPath $installer -Algorithm SHA256).Hash.ToLowerInvariant()
        ($hash + '  ' + (Split-Path -Leaf $installer)) | Set-Content -LiteralPath ($installer + '.sha256') -Encoding ascii
    }
    Write-Output 'Native desktop, voice engine, and validated package staged in dist/VoicePrompt.'
} finally { Pop-Location }
