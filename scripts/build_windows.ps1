param([string]$Python = '.venv\Scripts\python.exe', [string]$InnoCompiler = '.tools\inno\ISCC.exe', [string]$SignThumbprint = '', [switch]$SkipInstaller)
& (Join-Path $PSScriptRoot 'build_desktop.ps1') -Python $Python -InnoCompiler $InnoCompiler -SignThumbprint $SignThumbprint -SkipInstaller:$SkipInstaller
exit $LASTEXITCODE
