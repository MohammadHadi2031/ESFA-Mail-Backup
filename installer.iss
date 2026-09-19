#define MyAppName "ESFA Mail Backup"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "ESFA Group"
#define MyAppExeName "EsfaMailBackup.exe"

[Setup]
AppId={{CB4DD57E-A9F4-4CEB-ABF4-5B5B5A21D911}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\Programs\EsfaMailBackup
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=Output
OutputBaseFilename=ESFA-Mail-Backup-Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayName={#MyAppName}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Files]
Source: "dist\EsfaMailBackup\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName}"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "powershell.exe"; Parameters: "-NoProfile -NonInteractive -ExecutionPolicy Bypass -Command ""Get-ScheduledTask -TaskName 'ESFA Mail Backup','Hetzner Mail Backup' -ErrorAction SilentlyContinue | Unregister-ScheduledTask -Confirm:$false"""; RunOnceId: "RemoveScheduledTasks"; Flags: runhidden waituntilterminated

