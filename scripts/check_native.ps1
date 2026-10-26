param([string]$Python = '.venv\Scripts\python.exe')
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$profile = Join-Path $root ('.tools\native-profile-' + [guid]::NewGuid().ToString('N'))
& $Python (Join-Path $root 'scripts\create_acceptance_profile.py') $profile
if ($LASTEXITCODE -ne 0) { throw 'Could not create isolated verification data' }
$oldProfile = $env:VOICEPROMPT_ACCEPTANCE_DIR
$oldBrowser = $env:WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS
$env:VOICEPROMPT_ACCEPTANCE_DIR = $profile
$env:VOICEPROMPT_PYTHON = (Get-Command $Python -ErrorAction SilentlyContinue).Source
if (-not $env:VOICEPROMPT_PYTHON) { $env:VOICEPROMPT_PYTHON = (Resolve-Path -LiteralPath $Python).Path }
$env:WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS = '--remote-debugging-port=9224'
$app = $null
try {
    $app = Start-Process -FilePath (Join-Path $root 'dist\VoicePrompt\VoicePrompt.exe') -WindowStyle Hidden -PassThru
    $deadline = [DateTime]::UtcNow.AddSeconds(60)
    do {
        try { $ready = Invoke-RestMethod -Uri 'http://127.0.0.1:9224/json/version'; if ($ready.webSocketDebuggerUrl) { break } } catch {}
        Start-Sleep -Milliseconds 300
    } while ([DateTime]::UtcNow -lt $deadline -and -not $app.HasExited)
    if (-not $ready.webSocketDebuggerUrl) { throw 'Native WebView2 inspection did not become available' }
    Push-Location (Join-Path $root 'desktop')
    try { node scripts\verify-ui.cjs --cdp http://127.0.0.1:9224; if ($LASTEXITCODE -ne 0) { throw 'Native UI checks failed' } } finally { Pop-Location }
} finally {
    if ($app -and -not $app.HasExited) {
        try {
            $event = [Threading.EventWaitHandle]::OpenExisting('Local\VoicePrompt.Exit.' + $app.Id)
            try { $event.Set() | Out-Null } finally { $event.Dispose() }
            if (-not $app.WaitForExit(10000)) { $app.Kill() }
        } catch { $app.Kill() }
    }
    $env:VOICEPROMPT_ACCEPTANCE_DIR = $oldProfile
    $env:WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS = $oldBrowser
}
