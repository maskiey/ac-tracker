; Inno Setup — 在仓库根目录、完成 PyInstaller 后执行:
;   & "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe" /DMyAppVersion=1.0.0 packaging\AC-Tracker.iss
#ifndef MyAppVersion
#define MyAppVersion "1.0.0"
#endif
#define MyAppName "AC Tracker"
#define MyAppPublisher "maskiey"
#define MyAppExeName "AC-Tracker.exe"

[Setup]
AppId={{E4B8A2C1-7F90-4D3E-9A1B-6C5D8E2F0A3B}}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\Programs\{#MyAppName}
DefaultGroupName={#MyAppName}
OutputDir=..
OutputBaseFilename=AC-Tracker-Windows-Setup
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64
DisableProgramGroupPage=yes
CloseApplications=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "..\dist\AC-Tracker\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
; WorkingDir 必须与 exe 同目录，否则 PyInstaller/WebView2 从快捷方式启动时 cwd 可能为 System32 导致无法运行
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; Description: "{cm:LaunchProgram,{#MyAppName}}"; Flags: nowait postinstall skipifsilent
