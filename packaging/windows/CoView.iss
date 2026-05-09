#ifndef AppVersion
#define AppVersion "0.0.0"
#endif
#ifndef ProjectRoot
#define ProjectRoot "..\.."
#endif
#ifndef SourceDir
#define SourceDir "..\..\dist\CoView"
#endif
#ifndef OutputDir
#define OutputDir "..\..\dist"
#endif

[Setup]
AppId={{6F1B2D2D-2A7E-4F0D-8D08-6A91E1C0C0A7}
AppName=CoView
AppVersion={#AppVersion}
AppPublisher=CoView Team
AppPublisherURL=https://github.com/mini-yifan/CoView
AppSupportURL=https://github.com/mini-yifan/CoView/issues
AppUpdatesURL=https://github.com/mini-yifan/CoView/releases
DefaultDirName={autopf}\CoView
DefaultGroupName=CoView
DisableProgramGroupPage=yes
OutputDir={#OutputDir}
OutputBaseFilename=CoView-{#AppVersion}-Windows-Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
SetupIconFile={#ProjectRoot}\app_icons\AppIcon.ico
UninstallDisplayIcon={app}\CoView.exe
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\CoView"; Filename: "{app}\CoView.exe"
Name: "{autodesktop}\CoView"; Filename: "{app}\CoView.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\CoView.exe"; Description: "{cm:LaunchProgram,CoView}"; Flags: nowait postinstall skipifsilent
