param([string]$Python = '.venv311\Scripts\python.exe', [string]$AppDirectory = '')
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
if (-not $AppDirectory) { $AppDirectory = Join-Path $root 'dist\VoicePrompt' }
$profile = Join-Path $root ('.tools\native-profile-' + [guid]::NewGuid().ToString('N'))
& $Python (Join-Path $root 'scripts\create_acceptance_profile.py') $profile
if ($LASTEXITCODE -ne 0) { throw 'Could not create isolated verification data' }
$oldProfile = $env:VOICEPROMPT_ACCEPTANCE_DIR
$oldBrowser = $env:WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS
$oldInspect = $env:VOICEPROMPT_INSPECT_PORT
$oldPython = $env:VOICEPROMPT_PYTHON
$listener = [Net.Sockets.TcpListener]::new([Net.IPAddress]::Loopback, 0)
$listener.Start()
$inspectPort = $listener.LocalEndpoint.Port
$listener.Stop()
$inspectUrl = 'http://127.0.0.1:' + $inspectPort
$env:VOICEPROMPT_INSPECT_PORT = [string]$inspectPort
$env:VOICEPROMPT_ACCEPTANCE_DIR = $profile
$env:VOICEPROMPT_PYTHON = (Get-Command $Python -ErrorAction SilentlyContinue).Source
if (-not $env:VOICEPROMPT_PYTHON) { $env:VOICEPROMPT_PYTHON = (Resolve-Path -LiteralPath $Python).Path }
$env:WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS = '--remote-debugging-port=' + $inspectPort
$app = $null
$holder = $null
try {
    $holder = Start-Process -FilePath $env:VOICEPROMPT_PYTHON -ArgumentList @(
        ('"' + (Join-Path $root 'scripts\check_engine_bridge.py') + '"'),
        '--hold-instance', ('"' + $profile + '"')
    ) -WindowStyle Hidden -PassThru
    $deadline = [DateTime]::UtcNow.AddSeconds(10)
    while (-not (Test-Path -LiteralPath (Join-Path $profile '.instance-ready'))) {
        if ($holder.HasExited -or [DateTime]::UtcNow -gt $deadline) { throw 'Could not simulate the older tray instance' }
        Start-Sleep -Milliseconds 100
    }
    $app = Start-Process -FilePath (Join-Path $AppDirectory 'VoicePrompt.exe') -WindowStyle Hidden -PassThru
    $deadline = [DateTime]::UtcNow.AddSeconds(60)
    do {
        try { $ready = Invoke-RestMethod -Uri ($inspectUrl + '/json/version'); if ($ready.webSocketDebuggerUrl) { break } } catch {}
        Start-Sleep -Milliseconds 300
    } while ([DateTime]::UtcNow -lt $deadline -and -not $app.HasExited)
    if (-not $ready.webSocketDebuggerUrl) { throw 'Native WebView2 inspection did not become available' }
    Push-Location (Join-Path $root 'desktop')
    try { node scripts\verify-ui.cjs --cdp $inspectUrl --expect-instance-conflict; if ($LASTEXITCODE -ne 0) { throw 'Native UI checks failed' } } finally { Pop-Location }
} finally {
    if ($holder -and -not $holder.HasExited) {
        New-Item -ItemType File -Force -Path (Join-Path $profile '.instance-release') | Out-Null
        if (-not $holder.WaitForExit(3000)) { $holder.Kill() }
    }
    if ($app -and -not $app.HasExited) {
        try {
            $event = [Threading.EventWaitHandle]::OpenExisting('Local\VoicePrompt.Exit.' + $app.Id)
            try { $event.Set() | Out-Null } finally { $event.Dispose() }
            if (-not $app.WaitForExit(10000)) { $app.Kill() }
        } catch { $app.Kill() }
    }
    $env:VOICEPROMPT_ACCEPTANCE_DIR = $oldProfile
    $env:WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS = $oldBrowser
    $env:VOICEPROMPT_INSPECT_PORT = $oldInspect
    $env:VOICEPROMPT_PYTHON = $oldPython
}
