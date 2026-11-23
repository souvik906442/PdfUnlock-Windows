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
