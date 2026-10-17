param([string]$Installer = 'release\VoicePrompt-Setup-0.4.1-x64.exe')
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$target = [IO.Path]::GetFullPath((Join-Path $projectRoot '.tools\installed check''s'))
if (-not $target.StartsWith($projectRoot.TrimEnd('\') + '\', [StringComparison]::OrdinalIgnoreCase)) {
    throw 'Installer check target is outside the workspace'
}
$registration = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\{C6514AAC-8670-440C-A62D-F0E6EBBE04D1}_is1'
if (Test-Path -LiteralPath $registration) {
    throw 'An installed VoicePrompt is already registered. Run this check in a clean Windows account or VM.'
}
$runKey = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Run'
$startupNames = @('VoicePrompt', 'Voice Prompt', 'Prompt Voice')
$startupBefore = @{}
foreach ($name in $startupNames) {
    $entry = Get-ItemProperty -LiteralPath $runKey -Name $name -ErrorAction SilentlyContinue
    $startupBefore[$name] = if ($entry) { $entry.$name } else { $null }
}
$installerPath = (Resolve-Path -LiteralPath (Join-Path $projectRoot $Installer)).Path
$installedExe = Join-Path $target 'VoicePrompt.exe'
$report = [ordered]@{ install = $false; reinstall = $false; workers = $false; live_uninstall = $false; runtime_startup_removed = $false; legacy_startup_removed = $false; unrelated_startup_preserved = $false; portable_preserved = $false; shortcuts_removed = $false; data_preserved = $false; uninstall = $false; startup_preserved = $false }
$dataDirectory = Join-Path $env:LOCALAPPDATA 'VoicePrompt'
New-Item -ItemType Directory -Force -Path $dataDirectory | Out-Null
$dataMarker = Join-Path $dataDirectory ('installer-check-' + [guid]::NewGuid().ToString('N') + '.txt')
Set-Content -LiteralPath $dataMarker -Value 'Preserve this saved user file.' -Encoding utf8
$dataHash = (Get-FileHash -LiteralPath $dataMarker).Hash
$desktopLink = Join-Path ([Environment]::GetFolderPath('Desktop')) 'VoicePrompt.lnk'
$menuLink = Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs\VoicePrompt\VoicePrompt.lnk'

function Get-InstalledProcesses {
    @(Get-CimInstance Win32_Process -Filter "Name = 'VoicePrompt.exe'" | Where-Object { $_.ExecutablePath -eq $installedExe })
}

function Start-LiveSmoke([string]$Executable, [string]$Label) {
    $output = Join-Path $projectRoot ('build\' + $Label + '.json')
    if (Test-Path -LiteralPath $output) { Remove-Item -LiteralPath $output }
    $process = Start-Process -FilePath $Executable -ArgumentList @('--smoke-test', ('"' + $output + '"'), '--hold-for-uninstall') -WindowStyle Hidden -PassThru
    $deadline = [DateTime]::UtcNow.AddSeconds(180)
    do {
        if ($process.HasExited) { throw 'App exited before live uninstall check' }
        $checks = $null
        if (Test-Path -LiteralPath $output) {
            try { $checks = Get-Content -LiteralPath $output -Raw | ConvertFrom-Json } catch { $checks = $null }
        }
        if ($checks.holding_for_uninstall) { return [pscustomobject]@{ Process = $process; Output = $output; Checks = $checks } }
        Start-Sleep -Milliseconds 200
    } while ([DateTime]::UtcNow -lt $deadline)
    # This is the process this test just launched, not an application name match.
    $process.Kill()
    throw 'Live worker checks timed out'
}

function Invoke-Uninstaller([string]$LogName) {
    $uninstaller = Join-Path $target 'unins000.exe'
    if (-not (Test-Path -LiteralPath $uninstaller)) { throw 'Installed uninstaller is missing' }
    $log = Join-Path $projectRoot ('build\' + $LogName + '.log')
    $process = Start-Process -FilePath $uninstaller -ArgumentList @('/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART',('/LOG="' + $log + '"')) -WindowStyle Hidden -PassThru
    if (-not $process.WaitForExit(45000)) { throw 'Uninstall timed out' }
    if ($process.ExitCode -ne 0) { throw "Uninstaller failed: $($process.ExitCode)" }
    $deadline = [DateTime]::UtcNow.AddSeconds(10)
    while ((Test-Path -LiteralPath $target) -and [DateTime]::UtcNow -lt $deadline) { Start-Sleep -Milliseconds 200 }
    if ((Test-Path -LiteralPath $target) -or @(Get-InstalledProcesses).Count -ne 0 -or (Test-Path -LiteralPath $registration)) {
        throw 'Uninstall left installed files, running processes, or its Windows registration behind'
    }
    if ((Test-Path -LiteralPath $desktopLink) -or (Test-Path -LiteralPath $menuLink)) { throw 'Uninstall left an application shortcut behind' }
}

$portable = $null
try {
    $portable = Start-LiveSmoke (Join-Path $projectRoot 'dist\VoicePrompt\VoicePrompt.exe') 'portable-uninstall-control'
    foreach ($scenario in @('installer-startup', 'runtime-startup')) {
        $startupTask = if ($scenario -eq 'installer-startup') { 'startup' } else { '!startup' }
        foreach ($pass in 1,2) {
            $process = Start-Process -FilePath $installerPath -ArgumentList @('/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART',('/DIR="' + $target + '"'),('/MERGETASKS=desktopicon,' + $startupTask)) -WindowStyle Hidden -Wait -PassThru
            if ($process.ExitCode -ne 0) { throw "Installer pass $pass failed: $($process.ExitCode)" }
            if ($pass -eq 1) { $report.install = $true } else { $report.reinstall = $true }
        }
        if (-not (Test-Path -LiteralPath $desktopLink) -or -not (Test-Path -LiteralPath $menuLink)) { throw 'Installer shortcuts were not created' }
        if (-not (Test-Path -LiteralPath $runKey)) { New-Item -Path $runKey -Force | Out-Null }
        if ($scenario -eq 'runtime-startup') {
            # The app can enable startup after installation without the installer task.
            Set-ItemProperty -LiteralPath $runKey -Name VoicePrompt -Value ('"' + $installedExe + '"')
        } else {
            $startup = (Get-ItemProperty -LiteralPath $runKey -Name VoicePrompt).VoicePrompt
            if ($startup -ne ('"' + $installedExe + '"')) { throw 'Installer startup task did not register the installed executable' }
        }
        Set-ItemProperty -LiteralPath $runKey -Name 'Prompt Voice' -Value 'pythonw.exe -m bridgevoice.main'
        Set-ItemProperty -LiteralPath $runKey -Name 'Voice Prompt' -Value '"C:\UnrelatedApp\Other.exe"'
        $smoke = Start-LiveSmoke $installedExe ('installed-' + $scenario)
        $checks = $smoke.Checks
        $report.workers = @($checks.workers.PSObject.Properties).Count -eq 4 -and $checks.rnnoise
        if (-not $report.workers -or @(Get-InstalledProcesses).Count -lt 2) { throw 'Live app and speech worker were not verified' }
        Invoke-Uninstaller ('uninstall-' + $scenario)
        if (-not $smoke.Process.WaitForExit(10000)) { throw 'App did not exit during uninstall' }
        $checks = Get-Content -LiteralPath $smoke.Output -Raw | ConvertFrom-Json
        if (-not $checks.shutdown_received) { throw 'App was terminated without receiving the normal shutdown request' }
        if ($portable.Process.HasExited) { throw 'Uninstall stopped a separate portable copy' }
        $report.portable_preserved = $true
        foreach ($name in @('VoicePrompt','Prompt Voice')) {
            if (Get-ItemProperty -LiteralPath $runKey -Name $name -ErrorAction SilentlyContinue) { throw "Startup entry remained: $name" }
        }
        if ((Get-ItemProperty -LiteralPath $runKey -Name 'Voice Prompt').'Voice Prompt' -ne '"C:\UnrelatedApp\Other.exe"') { throw 'An unrelated startup command was removed' }
        $report.live_uninstall = $true
        $report.shortcuts_removed = $true
        $report.legacy_startup_removed = $true
        $report.unrelated_startup_preserved = $true
        if ($scenario -eq 'runtime-startup') { $report.runtime_startup_removed = $true }
        $report.uninstall = $true
    }
    $report.data_preserved = (Test-Path -LiteralPath $dataMarker) -and (Get-FileHash -LiteralPath $dataMarker).Hash -eq $dataHash
    if (-not $report.data_preserved) { throw 'Saved user data was changed by uninstall' }
}
finally {
    try {
        if (Test-Path -LiteralPath (Join-Path $target 'unins000.exe')) { Invoke-Uninstaller 'uninstall-final-cleanup' }
    } finally {
        if ($portable -and -not $portable.Process.HasExited) {
            try {
                $shutdown = [Threading.EventWaitHandle]::OpenExisting('Local\VoicePrompt.Exit.' + $portable.Process.Id)
                try { $shutdown.Set() | Out-Null } finally { $shutdown.Dispose() }
                if (-not $portable.Process.WaitForExit(10000)) { $portable.Process.Kill() }
            } catch { $portable.Process.Kill() }
        }
        foreach ($name in $startupNames) {
            if ($null -eq $startupBefore[$name]) { Remove-ItemProperty -LiteralPath $runKey -Name $name -ErrorAction SilentlyContinue }
            else { Set-ItemProperty -LiteralPath $runKey -Name $name -Value $startupBefore[$name] }
        }
        $report.startup_preserved = $true
        foreach ($name in $startupNames) {
            $entry = Get-ItemProperty -LiteralPath $runKey -Name $name -ErrorAction SilentlyContinue
            $command = if ($entry) { $entry.$name } else { $null }
            if ($command -ne $startupBefore[$name]) { $report.startup_preserved = $false }
        }
        if (Test-Path -LiteralPath $dataMarker) { Remove-Item -LiteralPath $dataMarker }
        $report | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $projectRoot 'build\installer-check.json') -Encoding utf8
    }
}
if (-not $report.startup_preserved) { throw 'Test did not restore the original startup registrations' }
$report | ConvertTo-Json
