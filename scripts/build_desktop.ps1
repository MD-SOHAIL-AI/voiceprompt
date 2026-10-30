param(
    [string]$Python = '',
    [string]$InnoCompiler = '.tools\inno\ISCC.exe',
    [string]$SignThumbprint = '',
    [string]$SignToolPath = '',
    [ValidateSet('CurrentUser', 'LocalMachine')][string]$CertificateStore = 'CurrentUser',
    [switch]$AllowUnsignedPreview,
    [string]$NativeExecutable = '',
    [switch]$SkipInstaller
)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot 'windows_signing.ps1')
# Refuse an accidental unsigned release before building or replacing any files.
$signing = Initialize-VoicePromptSigning -Thumbprint $SignThumbprint -SignToolPath $SignToolPath -CertificateStore $CertificateStore -AllowUnsignedPreview:$AllowUnsignedPreview
if (-not $Python) { $Python = if (Test-Path -LiteralPath (Join-Path $projectRoot '.venv311\Scripts\python.exe')) { '.venv311\Scripts\python.exe' } else { '.venv\Scripts\python.exe' } }
Push-Location -LiteralPath $projectRoot
try {
    $version = [regex]::Match((Get-Content pyproject.toml -Raw), '(?m)^version = "([^"]+)"').Groups[1].Value
    if (-not $version) { throw 'Missing canonical build version' }
    $nativePath = ''
    if ($NativeExecutable) {
        $nativePath = (Resolve-Path -LiteralPath $NativeExecutable).Path
        if ([IO.Path]::GetExtension($nativePath) -ne '.exe') { throw 'NativeExecutable must be an existing Windows executable' }
        $shellVersion = (Get-Item -LiteralPath $nativePath).VersionInfo.ProductVersion
        if ($shellVersion -ne $version) { throw "Desktop shell $shellVersion differs from engine $version. Rebuild the desktop shell before packaging this update." }
        # Keep an explicit supplied shell outside the staging directory, which
        # is replaced below only after the repaired engine builds successfully.
        $nativeCopy = Join-Path $projectRoot 'build\VoicePrompt-supplied-shell.exe'
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $nativeCopy) | Out-Null
        if ($nativePath -ne $nativeCopy) { Copy-Item -LiteralPath $nativePath -Destination $nativeCopy -Force }
        $nativePath = $nativeCopy
        Write-Output ('Reusing explicitly supplied desktop shell: ' + (Get-FileHash -LiteralPath $nativePath -Algorithm SHA256).Hash)
    }
    & $Python scripts\verify_versions.py
    if ($LASTEXITCODE -ne 0) { throw 'Build versions disagree' }
    & $Python packaging\prepare_build.py
    if ($LASTEXITCODE -ne 0) { throw 'Build preparation failed' }
    & $Python -m PyInstaller --noconfirm packaging\Engine.spec
    if ($LASTEXITCODE -ne 0) { throw 'Voice engine packaging failed' }
    if (-not $nativePath) {
        . (Join-Path $PSScriptRoot 'windows_toolchain.ps1')
        Initialize-VoicePromptToolchain
        Push-Location desktop
        try {
            & npm.cmd ci
            if ($LASTEXITCODE -ne 0) { throw 'Frontend dependency installation failed' }
            & npm.cmd run tauri -- build --no-bundle
            if ($LASTEXITCODE -ne 0) { throw 'Native desktop build failed' }
        } finally { Pop-Location }
        $nativePath = Join-Path $projectRoot 'desktop\src-tauri\target\release\VoicePrompt.exe'
    }
    if ((Get-Item -LiteralPath $nativePath).VersionInfo.ProductVersion -ne $version) { throw 'Desktop executable version differs from the release. Rebuild the desktop before packaging.' }
    $stage = Join-Path $projectRoot 'dist\VoicePrompt'
    if ([IO.Path]::GetFullPath($stage) -ne (Join-Path $projectRoot 'dist\VoicePrompt')) { throw 'Unexpected stage path' }
    # Existing builds remain intact until both components have built successfully.
    # Stage only app-owned files; user data lives outside this directory.
    if (Test-Path -LiteralPath $stage) { Remove-Item -LiteralPath $stage -Recurse -Force }
    New-Item -ItemType Directory -Force -Path $stage | Out-Null
    Copy-Item -LiteralPath $nativePath -Destination (Join-Path $stage 'VoicePrompt.exe') -Force
    $engineStage = Join-Path $stage 'engine'
    New-Item -ItemType Directory -Force -Path $engineStage | Out-Null
    Get-ChildItem -LiteralPath 'dist\VoicePromptEngine' | Copy-Item -Destination $engineStage -Recurse -Force
    Copy-Item -LiteralPath LICENSE,THIRD_PARTY_NOTICES.md -Destination $stage -Force
    if (Test-Path -LiteralPath 'build\licenses') { Copy-Item -LiteralPath 'build\licenses' -Destination $stage -Recurse -Force }
    $fontLicenses = Join-Path $stage 'licenses\encode-sans'
    New-Item -ItemType Directory -Force -Path $fontLicenses | Out-Null
    Copy-Item -LiteralPath 'desktop\src\assets\fonts\OFL.txt' -Destination $fontLicenses
    if ($signing.Enabled) {
        foreach ($file in @((Join-Path $stage 'VoicePrompt.exe'), (Join-Path $engineStage 'VoicePromptEngine.exe'))) {
            Invoke-VoicePromptSigning -Signing $signing -Path $file
        }
    }
    @{
           engine_version = $version; desktop_shell_reused = [bool]$NativeExecutable;
           protocol_version = 2;
           source_commit = (& git rev-parse HEAD);
           source_dirty = [bool](& git status --porcelain --untracked-files=no);
           engine_sha256 = (Get-FileHash -LiteralPath (Join-Path $engineStage 'VoicePromptEngine.exe') -Algorithm SHA256).Hash.ToLowerInvariant();
           desktop_shell_file_version = (Get-Item -LiteralPath $nativePath).VersionInfo.FileVersion;
           desktop_shell_sha256 = (Get-FileHash -LiteralPath (Join-Path $stage 'VoicePrompt.exe') -Algorithm SHA256).Hash.ToLowerInvariant();
           signing_mode = $(if ($signing.Enabled) { 'signed-release' } else { 'unsigned-preview' });
           signer_thumbprint = $signing.Thumbprint } |
            ConvertTo-Json | Set-Content -LiteralPath (Join-Path $stage 'build-manifest.json') -Encoding utf8
    $smokeOutput = Join-Path $projectRoot 'build\frozen-smoke.json'
    if (Test-Path -LiteralPath $smokeOutput) { Remove-Item -LiteralPath $smokeOutput }
    $smoke = Start-Process -FilePath (Join-Path $stage 'VoicePrompt.exe') -ArgumentList @('--smoke-test', ('"' + $smokeOutput + '"')) -WindowStyle Hidden -PassThru
    if (-not $smoke.WaitForExit(180000)) { $smoke.Kill(); throw 'Frozen checks timed out' }
    if ($smoke.ExitCode -ne 0 -or -not (Test-Path -LiteralPath $smokeOutput)) { throw 'Frozen checks failed' }
    $checks = Get-Content -LiteralPath $smokeOutput -Raw | ConvertFrom-Json
    if ($checks.error -or -not $checks.tauri -or @($checks.workers.PSObject.Properties).Count -ne 4 -or -not $checks.rnnoise -or $checks.version -ne $version) { throw 'Frozen checks did not verify the release version, Tauri and all speech workers' }
    New-Item -ItemType Directory -Force -Path release | Out-Null
    if (-not $SkipInstaller) {
        $webviewBootstrapper = Join-Path $projectRoot 'build\MicrosoftEdgeWebview2Setup.exe'
        if (-not (Test-Path -LiteralPath $webviewBootstrapper)) {
            Invoke-WebRequest -Uri 'https://go.microsoft.com/fwlink/p/?LinkId=2124703' -OutFile $webviewBootstrapper
        }
        $webviewSignature = Get-AuthenticodeSignature -LiteralPath $webviewBootstrapper
        if ($webviewSignature.Status -ne 'Valid' -or $webviewSignature.SignerCertificate.Subject -notmatch 'O=Microsoft Corporation') {
            throw 'WebView2 prerequisite must have a valid Microsoft signature'
        }
        if (-not (Test-Path -LiteralPath $InnoCompiler)) { $InnoCompiler = 'C:\Program Files (x86)\Inno Setup 6\ISCC.exe' }
        if (-not (Test-Path -LiteralPath $InnoCompiler)) { throw 'Inno Setup 6 is required for the installer' }
        $compilerArguments = @('/DAppVersion=' + $version)
        if ($signing.Enabled) {
            # Inno signs Setup, its temporary copies and the embedded uninstaller.
            # Use a fresh directory so no cached uninstaller from another signer is reused.
            $signedUninstallerDirectory = Join-Path $projectRoot ('build\signed-uninstallers\' + [guid]::NewGuid().ToString('N'))
            New-Item -ItemType Directory -Path $signedUninstallerDirectory -Force | Out-Null
            $compilerArguments += @('/DSignedRelease', ('/DSignedUninstallerPath=' + $signedUninstallerDirectory), (Get-VoicePromptInnoSignTool -Signing $signing))
        } else {
            $compilerArguments += '/DUnsignedPreview'
        }
        & $InnoCompiler @compilerArguments packaging\VoicePrompt.iss
        if ($LASTEXITCODE -ne 0) { throw 'Installer compilation failed' }
        $suffix = if ($signing.Enabled) { '' } else { '-unsigned-preview' }
        $installer = Join-Path $projectRoot ('release\VoicePrompt-Setup-' + $version + '-x64' + $suffix + '.exe')
        if ($signing.Enabled) {
            Assert-VoicePromptSignature -Path $installer -ExpectedThumbprint $signing.Thumbprint | Out-Null
            $uninstallers = @(Get-ChildItem -LiteralPath $signedUninstallerDirectory -File)
            if (-not $uninstallers.Count) { throw 'Inno did not produce a signed uninstaller.' }
            foreach ($uninstaller in $uninstallers) {
                Assert-VoicePromptSignature -Path $uninstaller.FullName -ExpectedThumbprint $signing.Thumbprint | Out-Null
            }
        }
        $hash = (Get-FileHash -LiteralPath $installer -Algorithm SHA256).Hash.ToLowerInvariant()
        ($hash + '  ' + (Split-Path -Leaf $installer)) | Set-Content -LiteralPath ($installer + '.sha256') -Encoding ascii
        & (Join-Path $PSScriptRoot 'check_windows_signing.ps1') -Installer $installer -Stage $stage -ExpectedThumbprint $signing.Thumbprint -AllowUnsignedPreview:$AllowUnsignedPreview
    }
    Write-Output 'Native desktop, voice engine, and validated package staged in dist/VoicePrompt.'
} finally { Pop-Location }
