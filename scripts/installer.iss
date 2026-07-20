; installer.iss - computa Windows installer (Inno Setup 6).
;
; Builds dist\computa-setup.exe: the standard double-click installer flow.
; Per-user install (no UAC for the install itself; the first-run setup
; window elevates on its own when it actually needs admin).
;
; Build via:  python build.py installer
; (assembles the payload dir and invokes ISCC with the defines below)
;
; The installer copies files, registers uninstall in Apps & Features,
; optionally adds the install dir to the user PATH, and offers to launch
; the first-run setup window (hardware preflight, games/display survey,
; safety snapshot). Installing never applies a profile.

#ifndef AppVer
  #define AppVer "0.0.0"
#endif
#ifndef PayloadDir
  #define PayloadDir "..\build\installer-payload"
#endif

[Setup]
AppId={{7C2F19D4-52A8-4E0B-9B7E-C0A17E6D3F11}
AppName=computa
AppVersion={#AppVer}
AppPublisher=Computa contributors
AppPublisherURL=https://github.com/RJW34/computa
DefaultDirName={localappdata}\AdaptiveBattleStationOptimizer
DisableDirPage=yes
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputBaseFilename=computa-setup
WizardStyle=modern
UninstallDisplayName=computa
UninstallDisplayIcon={app}\computa.exe
SolidCompression=yes
Compression=lzma2

[Tasks]
Name: "addpath"; Description: "Let me run 'computa' from the command line (adds the install folder to PATH)"; Flags: unchecked

[Files]
Source: "{#PayloadDir}\computa.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#PayloadDir}\abso\tray\*"; DestDir: "{app}\abso\tray"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{userprograms}\computa\computa tray"; Filename: "wscript.exe"; Parameters: """{app}\abso\tray\ABSO-Tray.vbs"""; WorkingDir: "{app}\abso\tray"; IconFilename: "{app}\computa.exe"
Name: "{userprograms}\computa\computa setup"; Filename: "wscript.exe"; Parameters: """{app}\abso\tray\ABSO-FirstRun.vbs"""; WorkingDir: "{app}\abso\tray"; IconFilename: "{app}\computa.exe"

[Registry]
Root: HKCU; Subkey: "Environment"; ValueType: expandsz; ValueName: "Path"; ValueData: "{olddata};{app}"; Tasks: addpath; Check: NeedsAddPath(ExpandConstant('{app}'))

[Run]
Filename: "wscript.exe"; Parameters: """{app}\abso\tray\ABSO-FirstRun.vbs"""; WorkingDir: "{app}\abso\tray"; Description: "Run first-time setup now (recommended)"; Flags: postinstall nowait skipifsilent

[UninstallRun]
; Restore the setup-time baseline before files are removed. Elevates with
; one UAC prompt; declining skips the restore but uninstall still proceeds.
Filename: "powershell.exe"; Parameters: "-NoProfile -Command ""try {{ Start-Process -FilePath '{app}\computa.exe' -ArgumentList 'uninstall','--yes' -Verb RunAs -Wait }} catch {{}}"""; Flags: runhidden; RunOnceId: "ComputaRestoreBaseline"

[Code]
function NeedsAddPath(Param: string): boolean;
var
  OrigPath: string;
begin
  if not RegQueryStringValue(HKEY_CURRENT_USER, 'Environment', 'Path', OrigPath) then
  begin
    Result := True;
    exit;
  end;
  Result := Pos(';' + Uppercase(Param) + ';', ';' + Uppercase(OrigPath) + ';') = 0;
end;

procedure RemoveFromUserPath(const Dir: string);
var
  OrigPath, NewPath: string;
  P: Integer;
begin
  if not RegQueryStringValue(HKEY_CURRENT_USER, 'Environment', 'Path', OrigPath) then
    exit;
  NewPath := ';' + OrigPath + ';';
  P := Pos(';' + Uppercase(Dir) + ';', Uppercase(NewPath));
  if P > 0 then
  begin
    Delete(NewPath, P, Length(Dir) + 1);
    if (Length(NewPath) > 0) and (NewPath[1] = ';') then
      Delete(NewPath, 1, 1);
    if (Length(NewPath) > 0) and (NewPath[Length(NewPath)] = ';') then
      Delete(NewPath, Length(NewPath), 1);
    RegWriteStringValue(HKEY_CURRENT_USER, 'Environment', 'Path', NewPath);
  end;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usPostUninstall then
    RemoveFromUserPath(ExpandConstant('{app}'));
end;
