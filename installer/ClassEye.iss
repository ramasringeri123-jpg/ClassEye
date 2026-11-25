; ClassEye Windows installer (Inno Setup 6). Built by:  python tools/build.py --installer
; Installs for the current user by default (no admin password needed on college PCs);
; the user can choose "install for all users" if they are an administrator.

#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif
#define AppName "ClassEye"
#define AppExe "ClassEye.exe"
#define AppURL "https://github.com/ramasringeri123-jpg/ClassEye"

[Setup]
AppId={{2BCB1625-4993-4D59-B65F-6AA6878365A5}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=ClassEye contributors
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}/issues
AppUpdatesURL={#AppURL}/releases
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
LicenseFile=..\LICENSE
SetupIconFile=..\assets\classeye.ico
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName}
OutputDir=..\dist
OutputBaseFilename=ClassEye-Setup-{#AppVersion}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "..\dist\ClassEye\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{autoprograms}\ClassEye Reports"; Filename: "{userdocs}\ClassEye Reports"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Dirs]
Name: "{userdocs}\ClassEye Reports"

[Run]
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent

; Student photos, settings (%LOCALAPPDATA%\ClassEye) and reports (Documents\ClassEye Reports)
; are deliberately NOT removed on uninstall, so updating or reinstalling never loses data.
