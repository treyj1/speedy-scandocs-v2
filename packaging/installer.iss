; The Windows installer, made with Inno Setup after PyInstaller has built dist\Speedy Scandocs. From
; the top folder:
;
;     iscc /DAppVersion=1.1.0 /O. packaging\installer.iss
;
; It installs for the signed-in person only, so it needs no administrator. Settings and the API key
; are kept outside the install folder, so updating or uninstalling leaves them alone.

#define AppName "Speedy Scandocs"
#define AppExe "Speedy Scandocs.exe"
#ifndef AppVersion
  #error Pass the version, for example /DAppVersion=1.1.0
#endif

[Setup]
; Never change AppId. It's how a new version knows to update this one.
AppId={{E2F5B75D-F942-4731-ABC7-2CF7E7C8FF3E}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=GDJ
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
DisableDirPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputBaseFilename=Speedy-Scandocs-Setup-{#AppVersion}
SetupIconFile=..\GDJ Logo.ico
UninstallDisplayIcon={app}\{#AppExe}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no

[InstallDelete]
; Clears the last version's libraries, so an update can't leave old ones behind.
Type: filesandordirs; Name: "{app}\_internal"

[Tasks]
Name: "desktopicon"; Description: "Add a shortcut to the desktop"

[Files]
Source: "..\dist\Speedy Scandocs\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "Open Speedy Scandocs"; Flags: nowait postinstall skipifsilent
