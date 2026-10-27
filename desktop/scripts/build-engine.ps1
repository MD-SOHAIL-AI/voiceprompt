param([string]$Python = '.venv\Scripts\python.exe')
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
Push-Location -LiteralPath $root
try {
    & $Python packaging\prepare_build.py
    if ($LASTEXITCODE -ne 0) { throw 'Asset and license preparation failed' }
    & $Python -m PyInstaller --noconfirm packaging\Engine.spec
    if ($LASTEXITCODE -ne 0) { throw 'Voice engine build failed' }
    Write-Output 'Engine built in dist/VoicePromptEngine. Use scripts/build_desktop.ps1 for the complete application.'
} finally { Pop-Location }
