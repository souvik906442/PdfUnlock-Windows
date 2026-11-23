; Inno Setup script - installs PdfUnlock, adds it to "Open with" / Default apps for .pdf,
; and registers its own Explorer thumbnail provider for PDF files.
[Setup]
AppId={{6F2B1C7E-3A54-4D0B-9C1F-5D8E7A1B2C34}
AppName=PDF Unlock
AppVersion=1.1
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
CloseApplications=yes
ArchitecturesInstallIn64BitMode=x64compatible

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; Flags: unchecked
Name: "lockedthumbs"; Description: "Also show thumbnails for password-protected PDFs whose password is saved (thumbnail images are kept in the Windows thumbnail cache)"; Flags: unchecked

[Files]
; PyInstaller folder (PdfUnlock.exe + libraries) and PdfUnlockThumb.dll
Source: "dist\PdfUnlock\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\PDF Unlock"; Filename: "{app}\PdfUnlock.exe"
Name: "{autodesktop}\PDF Unlock"; Filename: "{app}\PdfUnlock.exe"; Tasks: desktopicon

[Registry]
; Settings read by the thumbnail provider
Root: HKCU; Subkey: "Software\PdfUnlock"; ValueType: string; ValueName: "ExePath"; ValueData: "{app}\PdfUnlock.exe"
Root: HKCU; Subkey: "Software\PdfUnlock"; ValueType: dword; ValueName: "LockedThumbnails"; ValueData: 1; Tasks: lockedthumbs
Root: HKCU; Subkey: "Software\PdfUnlock"; ValueType: dword; ValueName: "LockedThumbnails"; ValueData: 0; Tasks: not lockedthumbs

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

; Thumbnail provider (COM class + hooked to our file types)
Root: HKCU; Subkey: "Software\Classes\CLSID\{{B4E3C8A2-6D1F-4F5B-9A47-2C7E5D9F1A63}"; ValueType: string; ValueName: ""; ValueData: "PDF Unlock Thumbnail Provider"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\CLSID\{{B4E3C8A2-6D1F-4F5B-9A47-2C7E5D9F1A63}\InprocServer32"; ValueType: string; ValueName: ""; ValueData: "{app}\PdfUnlockThumb.dll"
Root: HKCU; Subkey: "Software\Classes\CLSID\{{B4E3C8A2-6D1F-4F5B-9A47-2C7E5D9F1A63}\InprocServer32"; ValueType: string; ValueName: "ThreadingModel"; ValueData: "Apartment"
Root: HKCU; Subkey: "Software\Classes\PdfUnlock.pdf\ShellEx\{{e357fccd-a995-4576-b01f-234630154e96}"; ValueType: string; ValueName: ""; ValueData: "{{B4E3C8A2-6D1F-4F5B-9A47-2C7E5D9F1A63}"
Root: HKCU; Subkey: "Software\Classes\Applications\PdfUnlock.exe\ShellEx\{{e357fccd-a995-4576-b01f-234630154e96}"; ValueType: string; ValueName: ""; ValueData: "{{B4E3C8A2-6D1F-4F5B-9A47-2C7E5D9F1A63}"
Root: HKCU; Subkey: "Software\Classes\.pdf\ShellEx\{{e357fccd-a995-4576-b01f-234630154e96}"; ValueType: string; ValueName: ""; ValueData: "{{B4E3C8A2-6D1F-4F5B-9A47-2C7E5D9F1A63}"; Flags: uninsdeletekey

[Run]
Filename: "{app}\PdfUnlock.exe"; Description: "Launch PDF Unlock"; Flags: nowait postinstall skipifsilent
