#ifndef AppVersion
  #define AppVersion "0.5.0"
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

[Dirs]
Name: "{app}"; Flags: uninsalwaysuninstall
Name: "{app}\_internal"; Flags: uninsalwaysuninstall

[Icons]
Name: "{group}\VoicePrompt"; Filename: "{app}\VoicePrompt.exe"
Name: "{autodesktop}\VoicePrompt"; Filename: "{app}\VoicePrompt.exe"; Tasks: desktopicon

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "VoicePrompt"; ValueData: """{app}\VoicePrompt.exe"""; Tasks: startup

[Run]
Filename: "{app}\VoicePrompt.exe"; Description: "Open VoicePrompt"; Flags: nowait postinstall skipifsilent

[Code]
const
  RunKey = 'Software\Microsoft\Windows\CurrentVersion\Run';

function OpenEvent(Access: LongWord; InheritHandle: Boolean; Name: String): THandle;
  external 'OpenEventW@kernel32.dll stdcall';
function SetEvent(Event: THandle): Boolean;
  external 'SetEvent@kernel32.dll stdcall';
function CloseHandle(Handle: THandle): Boolean;
  external 'CloseHandle@kernel32.dll stdcall';
function GetBundleAttributes(Path: String): LongWord;
  external 'GetFileAttributesW@kernel32.dll stdcall';

function InstalledProcesses(Wmi: Variant): Variant;
var
  Path, EnginePath: String;
begin
  Path := ExpandConstant('{app}\VoicePrompt.exe');
  StringChangeEx(Path, '\', '\\', True);
  StringChangeEx(Path, '''', '\''', True);
  EnginePath := ExpandConstant('{app}\engine\VoicePromptEngine.exe');
  StringChangeEx(EnginePath, '\', '\\', True);
  StringChangeEx(EnginePath, '''', '\''', True);
  Result := Wmi.ExecQuery('SELECT * FROM Win32_Process WHERE ExecutablePath = ''' + Path + ''' OR ExecutablePath = ''' + EnginePath + '''');
end;

function StopInstalledProcesses: Boolean;
var
  Locator, Wmi, Processes, Process: Variant;
  I, Attempt: Integer;
  Event: THandle;
  Signalled: Boolean;
begin
  Result := False;
  try
    Locator := CreateOleObject('WbemScripting.SWbemLocator');
    Wmi := Locator.ConnectServer('', 'root\CIMV2');
    Processes := InstalledProcesses(Wmi);
    Signalled := False;
    for I := 0 to Processes.Count - 1 do begin
      Process := Processes.ItemIndex(I);
      Event := OpenEvent($0002, False, 'Local\VoicePrompt.Exit.' + IntToStr(Process.ProcessId));
      if Event <> 0 then begin
        if SetEvent(Event) then begin
          Signalled := True;
          Log('Requested normal shutdown of installed VoicePrompt PID ' + IntToStr(Process.ProcessId));
        end;
        CloseHandle(Event);
      end;
    end;
    if Signalled then begin
      for Attempt := 1 to 50 do begin
        if InstalledProcesses(Wmi).Count = 0 then begin
          Result := True;
          Exit;
        end;
        Sleep(200);
      end;
    end;
    { Older builds have no shutdown event. Also stop orphaned or stuck workers.
      Match the full installed path, never every Python/VoicePrompt process. }
    Processes := InstalledProcesses(Wmi);
    for I := 0 to Processes.Count - 1 do begin
      Process := Processes.ItemIndex(I);
      Log('Stopping remaining installed VoicePrompt PID ' + IntToStr(Process.ProcessId));
      try
        Process.Terminate(0);
      except
        Log('Process exited or could not be stopped: ' + GetExceptionMessage);
      end;
    end;
    for Attempt := 1 to 25 do begin
      if InstalledProcesses(Wmi).Count = 0 then begin
        Result := True;
        Exit;
      end;
      Sleep(200);
    end;
  except
    Log('Cannot verify VoicePrompt shutdown: ' + GetExceptionMessage);
  end;
end;

procedure RemoveStartupEntry(Name: String);
var
  Command: String;
begin
  if RegQueryStringValue(HKCU, RunKey, Name, Command) then begin
    Command := Lowercase(Command);
    if (Pos(Lowercase(ExpandConstant('{app}\VoicePrompt.exe')), Command) > 0) or
       (Pos('-m voiceprompt.launcher', Command) > 0) or
       (Pos('-m voiceprompt.main', Command) > 0) or
       (Pos('-m bridgevoice.main', Command) > 0) then begin
      if not RegDeleteValue(HKCU, RunKey, Name) then
        RaiseException('Could not remove VoicePrompt startup entry. Close Windows Settings and try again.');
      Log('Removed VoicePrompt startup entry: ' + Name);
    end;
  end;
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  Result := '';
  if not StopInstalledProcesses then
    Result := 'VoicePrompt is still running. Quit it from the tray, then try again.';
end;

procedure RemoveEmptyBundleDirectories(Path: String);
var
  Entry: TFindRec;
begin
  if (GetBundleAttributes(Path) and $400) <> 0 then Exit;
  if FindFirst(AddBackslash(Path) + '*', Entry) then begin
    try
      repeat
        if (Entry.Name <> '.') and (Entry.Name <> '..') and
           ((Entry.Attributes and $10) <> 0) and
           ((Entry.Attributes and $400) = 0) then
          RemoveEmptyBundleDirectories(AddBackslash(Path) + Entry.Name);
      until not FindNext(Entry);
    finally
      FindClose(Entry);
    end;
  end;
  { RemoveDir only removes empty directories; never follow junctions or delete files. }
  if RemoveDir(Path) then Log('Removed empty bundle directory: ' + Path);
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usUninstall then begin
    if not StopInstalledProcesses then
      RaiseException('VoicePrompt could not close. Quit it from the tray, then run Uninstall again.');
    { Runtime settings can enable startup even when the installer task was off. }
    RemoveStartupEntry('VoicePrompt');
    RemoveStartupEntry('Voice Prompt');
    RemoveStartupEntry('Prompt Voice');
  end;
  if CurUninstallStep = usPostUninstall then begin
    if FileExists(ExpandConstant('{app}\VoicePrompt.exe')) then
      RaiseException('VoicePrompt.exe could not be removed. Close VoicePrompt and run Uninstall again.');
    { A failed older uninstall can leave directories that predate this install. }
    RemoveEmptyBundleDirectories(ExpandConstant('{app}\_internal'));
    RemoveDir(ExpandConstant('{app}'));
  end;
  { Only installed files are removed. Source code, saved data and shared model
    caches are preserved; do not recursively delete the app folder or a profile. }
end;
