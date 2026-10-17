param([string]$Installer = 'release\VoicePrompt-Setup-0.4.0-x64.exe')
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$target = [IO.Path]::GetFullPath((Join-Path $projectRoot '.tools\installed-check'))
if (-not $target.StartsWith($projectRoot.TrimEnd('\') + '\', [StringComparison]::OrdinalIgnoreCase)) {
    throw 'Installer check target is outside the workspace'
}
$registration = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\{C6514AAC-8670-440C-A62D-F0E6EBBE04D1}_is1'
if (Test-Path -LiteralPath $registration) {
    throw 'An installed VoicePrompt is already registered. Run this check in a clean Windows account or VM.'
}
$runKey = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Run'
$startupBefore = Get-ItemProperty -LiteralPath $runKey -Name VoicePrompt -ErrorAction SilentlyContinue
$startupCommand = if ($startupBefore) { $startupBefore.VoicePrompt } else { $null }
$installerPath = (Resolve-Path -LiteralPath (Join-Path $projectRoot $Installer)).Path
$report = [ordered]@{ install = $false; reinstall = $false; workers = $false; uninstall = $false; startup_preserved = $false }
try {
    foreach ($pass in 1,2) {
        $process = Start-Process -FilePath $installerPath -ArgumentList @('/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART','/NOICONS',('/DIR="' + $target + '"'),'/MERGETASKS=!desktopicon,!startup') -WindowStyle Hidden -Wait -PassThru
        if ($process.ExitCode -ne 0) { throw "Installer pass $pass failed: $($process.ExitCode)" }
        if ($pass -eq 1) { $report.install = $true } else { $report.reinstall = $true }
    }
    $smokeOutput = Join-Path $projectRoot 'build\installed-smoke.json'
    $smoke = Start-Process -FilePath (Join-Path $target 'VoicePrompt.exe') -ArgumentList @('--smoke-test', ('"' + $smokeOutput + '"')) -WindowStyle Hidden -PassThru
    if (-not $smoke.WaitForExit(180000)) { $smoke.Kill(); throw 'Installed worker checks timed out' }
    if ($smoke.ExitCode -ne 0) { throw 'Installed worker checks failed' }
    $checks = Get-Content -LiteralPath $smokeOutput -Raw | ConvertFrom-Json
    $report.workers = @($checks.workers.PSObject.Properties).Count -eq 4 -and $checks.rnnoise
    if (-not $report.workers) { throw 'Installed workers or noise library were not verified' }
}
finally {
    $uninstaller = Join-Path $target 'unins000.exe'
    if (Test-Path -LiteralPath $uninstaller) {
        $process = Start-Process -FilePath $uninstaller -ArgumentList @('/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART') -WindowStyle Hidden -Wait -PassThru
        $report.uninstall = $process.ExitCode -eq 0 -and -not (Test-Path -LiteralPath (Join-Path $target 'VoicePrompt.exe'))
    }
    $startupAfter = Get-ItemProperty -LiteralPath $runKey -Name VoicePrompt -ErrorAction SilentlyContinue
    $afterCommand = if ($startupAfter) { $startupAfter.VoicePrompt } else { $null }
    $report.startup_preserved = $afterCommand -eq $startupCommand
    $report | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $projectRoot 'build\installer-check.json') -Encoding utf8
}
if (-not $report.uninstall -or -not $report.startup_preserved) { throw 'Installer cleanup or startup preservation failed' }
$report | ConvertTo-Json
