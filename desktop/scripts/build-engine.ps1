$ErrorActionPreference = "Stop"
$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$outDir = Join-Path $repoRoot "desktop\src-tauri\bin"
$workDir = Join-Path $repoRoot ".build\voiceprompt-engine"

Set-Location $repoRoot
if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
  throw "Python is required to build the Voice Prompt sidecar."
}

python -c "import PyInstaller" 2>$null
if ($LASTEXITCODE -ne 0) {
  throw "PyInstaller is not installed. Run: pip install -r requirements-desktop.txt"
}

New-Item -ItemType Directory -Force -Path $outDir | Out-Null
New-Item -ItemType Directory -Force -Path $workDir | Out-Null

python -m PyInstaller `
  --noconfirm `
  --clean `
  --onefile `
  --console `
  --name voiceprompt-engine `
  --distpath $outDir `
  --workpath $workDir `
  --specpath $workDir `
  --collect-all faster_whisper `
  --collect-all ctranslate2 `
  --hidden-import pynput.keyboard._win32 `
  voiceprompt\desktop_sidecar.py

if (-not (Test-Path (Join-Path $outDir "voiceprompt-engine.exe"))) {
  throw "Voice Prompt sidecar build did not produce voiceprompt-engine.exe"
}
Write-Host "Voice Prompt engine built successfully."
