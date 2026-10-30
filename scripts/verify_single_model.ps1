param(
    [string]$Python = '.venv311\Scripts\python.exe',
    [string]$Manifest = 'evaluation\research\conversation\manifest.jsonl',
    [ValidateSet('nemotron', 'moonshine', 'parakeet', 'whisper')][string]$Backend = 'nemotron',
    [switch]$BatchBaseline
)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$installedApp = [IO.Path]::GetFullPath((Join-Path $env:LOCALAPPDATA 'Programs\VoicePrompt\VoicePrompt.exe'))
$runningApps = @(Get-Process -Name VoicePrompt -ErrorAction SilentlyContinue | Where-Object {
    $_.Path -and [IO.Path]::GetFullPath($_.Path) -eq $installedApp
})
Push-Location -LiteralPath $projectRoot
try {
    foreach ($app in $runningApps) {
        $shutdown = [Threading.EventWaitHandle]::OpenExisting('Local\VoicePrompt.Exit.' + $app.Id)
        try { $shutdown.Set() | Out-Null } finally { $shutdown.Dispose() }
        if (-not $app.WaitForExit(15000)) { throw 'VoicePrompt did not close normally. No process was forced to stop.' }
    }
    $extra = @('--backend', $Backend)
    if ($BatchBaseline) { $extra += @('--batch-baseline', '--output', 'evaluation\hardening-0.6.0\whisper-batch.json') }
    & $Python scripts\verify_dictation_reliability.py --manifest $Manifest @extra
    if ($LASTEXITCODE -ne 0) { throw 'The offline dictation replay failed. See its output.' }
} finally {
    # Only reopen the installed application when this check closed it.
    if ($runningApps.Count -gt 0 -and -not (Get-Process -Name VoicePrompt -ErrorAction SilentlyContinue | Where-Object { $_.Path -eq $installedApp })) {
        Start-Process -FilePath $installedApp -WindowStyle Hidden
    }
    Pop-Location
}
