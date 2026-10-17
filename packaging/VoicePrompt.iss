#ifndef AppVersion
  #define AppVersion "0.4.0"
#endif
#define RepoRoot AddBackslash(SourcePath) + ".."

[Setup]
AppId={{C6514AAC-8670-440C-A62D-F0E6EBBE04D1}
AppName=VoicePrompt
AppVersion={#AppVersion}
AppPublisher=VoicePrompt contributors
AppPublisherURL=https://github.com/MD-SOHAIL-AI/voiceprompt
AppSupportURL=https://github.com/MD-SOHAIL-AI/voiceprompt/issues
AppUpdatesURL=https://github.com/MD-SOHAIL-AI/voiceprompt/releases
DefaultDirName={localappdata}\Programs\VoicePrompt
DefaultGroupName=VoicePrompt
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.17763
WizardStyle=modern
DisableProgramGroupPage=yes
LicenseFile={#RepoRoot}\LICENSE
OutputDir={#RepoRoot}\release
OutputBaseFilename=VoicePrompt-Setup-{#AppVersion}-x64
SetupIconFile={#RepoRoot}\build\VoicePrompt.ico
UninstallDisplayIcon={app}\VoicePrompt.exe
Compression=lzma2/normal
SolidCompression=yes
CloseApplications=yes
RestartApplications=no
SetupMutex=VoicePrompt.Setup

[Tasks]
Name: desktopicon; Description: "Create a desktop shortcut"; Flags: unchecked
Name: startup; Description: "Start VoicePrompt after Windows sign-in"; Flags: unchecked

[Files]
Source: "{#RepoRoot}\dist\VoicePrompt\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\VoicePrompt"; Filename: "{app}\VoicePrompt.exe"
Name: "{autodesktop}\VoicePrompt"; Filename: "{app}\VoicePrompt.exe"; Tasks: desktopicon

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "VoicePrompt"; ValueData: """{app}\VoicePrompt.exe"""; Tasks: startup; Flags: uninsdeletevalue

[Run]
Filename: "{app}\VoicePrompt.exe"; Description: "Open VoicePrompt"; Flags: nowait postinstall skipifsilent

[Code]
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  { User data and model caches are intentionally preserved during uninstall. }
end;
