# Use the installed MSVC environment, or the verified project-local SDK layout.
function Initialize-VoicePromptToolchain {
    $root = Split-Path -Parent $PSScriptRoot
    if (Get-Command link.exe -ErrorAction SilentlyContinue) { return }
    $compiler = Get-ChildItem -Path (Join-Path $root '.tools\msvc-tools\Contents\VC\Tools\MSVC\*') -Directory -ErrorAction SilentlyContinue | Sort-Object Name -Descending | Select-Object -First 1
    $sdk = Join-Path $root '.tools\windows-sdk\sdk'
    $crt = Join-Path $root '.tools\windows-sdk\crt'
    if (-not $compiler -or -not (Test-Path -LiteralPath (Join-Path $sdk 'lib\um\x86_64'))) {
        throw 'Install Microsoft C++ Build Tools and Windows SDK, then run from a Developer PowerShell. The project-local SDK is unavailable.'
    }
    $env:PATH = (Join-Path $compiler.FullName 'bin\Hostx64\x64') + ';' + $env:PATH
    $resourceCompiler = Get-ChildItem -Path (Join-Path $root '.tools\windows-sdk-buildtools-*\bin\*\x64\rc.exe') -File -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($resourceCompiler) { $env:PATH = $resourceCompiler.DirectoryName + ';' + $env:PATH }
    $env:LIB = @((Join-Path $compiler.FullName 'lib\x64'), (Join-Path $sdk 'lib\um\x86_64'), (Join-Path $sdk 'lib\ucrt\x86_64'), (Join-Path $crt 'lib\x86_64')) -join ';'
    $env:INCLUDE = @((Join-Path $compiler.FullName 'include'), (Join-Path $sdk 'include\um'), (Join-Path $sdk 'include\shared'), (Join-Path $sdk 'include\ucrt'), (Join-Path $crt 'include')) -join ';'
    $cargo = Join-Path $env:USERPROFILE '.cargo\bin'
    if (Test-Path -LiteralPath $cargo) { $env:PATH = $cargo + ';' + $env:PATH }
}
