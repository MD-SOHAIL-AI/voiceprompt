param(
    [string]$Python = '.venv-release\Scripts\python.exe',
    [string]$Manifest = 'evaluation\research\conversation\manifest.jsonl',
    [switch]$Endurance
)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$installed = [IO.Path]::GetFullPath((Join-Path $env:LOCALAPPDATA 'Programs\VoicePrompt\VoicePrompt.exe'))
$apps = @(Get-Process -Name VoicePrompt -ErrorAction SilentlyContinue | Where-Object { $_.Path -eq $installed })
$failures = @()
Push-Location -LiteralPath $root
try {
    foreach ($app in $apps) {
        $event = [Threading.EventWaitHandle]::OpenExisting('Local\VoicePrompt.Exit.' + $app.Id)
        try { $event.Set() | Out-Null } finally { $event.Dispose() }
        if (-not $app.WaitForExit(15000)) { throw 'The installed app did not close normally. No process was forced to stop.' }
    }
    New-Item -ItemType Directory -Force evaluation\hardening-0.6.0 | Out-Null
    foreach ($backend in @('nemotron', 'moonshine', 'parakeet', 'whisper')) {
        Write-Output ('Testing local ' + $backend)
        $comparison = @()
        if ($backend -eq 'whisper') { $comparison = @('--whisper-phrases', '--compare-batch') }
        & $Python scripts\verify_dictation_reliability.py --manifest $Manifest --backend $backend --noise-suppression both --output ('evaluation\hardening-0.6.0\' + $backend + '.json') @comparison
        if ($LASTEXITCODE -ne 0) { $failures += $backend }
    }
    if ($Endurance) {
        & $Python scripts\verify_endurance.py --seconds 300 --backend nemotron --output evaluation\hardening-0.6.0\endurance.json
        if ($LASTEXITCODE -ne 0) { $failures += 'endurance' }
    }
} finally {
    if ($apps.Count -gt 0) { Start-Process -FilePath $installed -WindowStyle Hidden }
    Pop-Location
}
if ($failures.Count) { throw ('Local validation failed: ' + ($failures -join ', ')) }
