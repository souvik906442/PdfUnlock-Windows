; Inno Setup script - installs PdfUnlock and adds it to Windows "Open with" / Default apps for .pdf
[Setup]
AppId={{6F2B1C7E-3A54-4D0B-9C1F-5D8E7A1B2C34}
AppName=PDF Unlock
AppVersion=1.0
AppPublisher=PdfUnlock
DefaultDirName={autopf}\PdfUnlock
DefaultGroupName=PDF Unlock
PrivilegesRequired=lowest
OutputDir=dist
OutputBaseFilename=PdfUnlock-Setup
SetupIconFile=icon.ico
UninstallDisplayIcon={app}\PdfUnlock.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ChangesAssociations=yes
ArchitecturesInstallIn64BitMode=x64compatible

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; Flags: unchecked

[Files]
Source: "dist\PdfUnlock.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\PDF Unlock"; Filename: "{app}\PdfUnlock.exe"
Name: "{autodesktop}\PDF Unlock"; Filename: "{app}\PdfUnlock.exe"; Tasks: desktopicon

[Registry]
; ProgID
Root: HKCU; Subkey: "Software\Classes\PdfUnlock.pdf"; ValueType: string; ValueName: ""; ValueData: "PDF Document (PDF Unlock)"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\PdfUnlock.pdf\DefaultIcon"; ValueType: string; ValueData: "{app}\PdfUnlock.exe,0"
Root: HKCU; Subkey: "Software\Classes\PdfUnlock.pdf\shell\open\command"; ValueType: string; ValueData: """{app}\PdfUnlock.exe"" ""%1"""
; Show up in the "Open with" list for .pdf
Root: HKCU; Subkey: "Software\Classes\.pdf\OpenWithProgids"; ValueType: string; ValueName: "PdfUnlock.pdf"; ValueData: ""; Flags: uninsdeletevalue
Root: HKCU; Subkey: "Software\Classes\Applications\PdfUnlock.exe\shell\open\command"; ValueType: string; ValueData: """{app}\PdfUnlock.exe"" ""%1"""; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\Applications\PdfUnlock.exe\SupportedTypes"; ValueType: string; ValueName: ".pdf"; ValueData: ""
; Show up in Settings > Default apps
Root: HKCU; Subkey: "Software\PdfUnlock\Capabilities"; ValueType: string; ValueName: "ApplicationName"; ValueData: "PDF Unlock"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\PdfUnlock\Capabilities"; ValueType: string; ValueName: "ApplicationDescription"; ValueData: "Open and unlock password-protected PDFs"
Root: HKCU; Subkey: "Software\PdfUnlock\Capabilities\FileAssociations"; ValueType: string; ValueName: ".pdf"; ValueData: "PdfUnlock.pdf"
Root: HKCU; Subkey: "Software\RegisteredApplications"; ValueType: string; ValueName: "PdfUnlock"; ValueData: "Software\PdfUnlock\Capabilities"; Flags: uninsdeletevalue

[Run]
Filename: "{app}\PdfUnlock.exe"; Description: "Launch PDF Unlock"; Flags: nowait postinstall skipifsilent

[Code]
const
  THUMB_GUID = '{e357fccd-a995-4576-b01f-234630154e96}';   // Explorer thumbnail handler
  PREVIEW_GUID = '{8895b1c6-b41f-4c1c-a562-0d564250836f}'; // Preview pane handler
  OURS = 'PdfUnlock.pdf';

// Looks for the shell handler (thumbnail / preview) that the previous PDF app registered.
function ProgIdHandler(ProgId, Guid: String): String;
var
  V: String;
begin
  Result := '';
  if (ProgId <> '') and (CompareText(ProgId, OURS) <> 0) then
    if RegQueryStringValue(HKCR, ProgId + '\ShellEx\' + Guid, '', V) then
      Result := V;
end;

function FindHandler(Guid: String): String;
var
  Names: TArrayOfString;
  I: Integer;
  V: String;
begin
  Result := '';
  // 1) registered directly on the .pdf key
  if RegQueryStringValue(HKCR, '.pdf\ShellEx\' + Guid, '', V) then
    Result := V;
  // 2) the app the user chose as default before us
  if Result = '' then
    if RegQueryStringValue(HKCU, 'Software\Microsoft\Windows\CurrentVersion\Explorer\FileExts\.pdf\UserChoice', 'ProgId', V) then
      Result := ProgIdHandler(V, Guid);
  // 3) default ProgID of .pdf
  if Result = '' then
    if RegQueryStringValue(HKCR, '.pdf', '', V) then
      Result := ProgIdHandler(V, Guid);
  // 4) any other PDF app that ever registered itself
  if Result = '' then
    if RegGetValueNames(HKCR, '.pdf\OpenWithProgids', Names) then
      for I := 0 to GetArrayLength(Names) - 1 do
        if Result = '' then
          Result := ProgIdHandler(Names[I], Guid);
end;

// Our ProgID would otherwise hide the existing PDF thumbnails, so copy the handlers into it.
procedure CurStepChanged(CurStep: TSetupStep);
var
  H: String;
begin
  if CurStep = ssPostInstall then
  begin
    H := FindHandler(THUMB_GUID);
    if H <> '' then
      RegWriteStringValue(HKCU, 'Software\Classes\' + OURS + '\ShellEx\' + THUMB_GUID, '', H);
    H := FindHandler(PREVIEW_GUID);
    if H <> '' then
      RegWriteStringValue(HKCU, 'Software\Classes\' + OURS + '\ShellEx\' + PREVIEW_GUID, '', H);
  end;
end;
