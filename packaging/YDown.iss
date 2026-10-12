#ifndef AppVersion
  #define AppVersion "0.2.0"
#endif

[Setup]
AppId={{D79B9FF0-C25D-47B2-9FAC-B7AA677EAC6B}
AppName=YDown
AppVersion={#AppVersion}
AppPublisher=loginheaven-jpg
AppPublisherURL=https://github.com/loginheaven-jpg/Ydown
AppUpdatesURL=https://github.com/loginheaven-jpg/Ydown/releases/latest
DefaultDirName={localappdata}\Programs\YDown
DefaultGroupName=YDown
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir=..\dist
OutputBaseFilename=YDown-Setup-x64
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\YDown.exe
CloseApplications=yes
CloseApplicationsFilter=YDown.exe
RestartApplications=no
DisableProgramGroupPage=yes
InfoAfterFile=THIRD-PARTY-NOTICES.md

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "korean"; MessagesFile: "compiler:Languages\Korean.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"

[Files]
Source: "..\dist\YDown\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\YDown"; Filename: "{app}\YDown.exe"
Name: "{autodesktop}\YDown"; Filename: "{app}\YDown.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\YDown.exe"; Description: "Launch YDown"; Flags: nowait postinstall skipifsilent
