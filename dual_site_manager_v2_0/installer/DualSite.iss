#define MyAppName "BlackBoxShop"
#define MyAppVersion "2.0.0"
#define MyAppExeName "DualSiteInventory.exe"

[Setup]
AppId={{5B3EC6E3-4D6B-476B-90EC-FA806F59A8A8}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
DefaultDirName={localappdata}\Programs\BlackBoxShop
DefaultGroupName={#MyAppName}
OutputDir=C:\ds\release
OutputBaseFilename=BlackBoxShop_Setup_v2.0.0
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
UninstallDisplayName={#MyAppName}
DisableProgramGroupPage=yes

[Files]
Source: "C:\ds\dist\DualSiteInventory\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autodesktop}\黑盒铺子"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon
Name: "{group}\黑盒铺子"; Filename: "{app}\{#MyAppExeName}"

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "快捷方式:"; Flags: checkedonce

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "启动黑盒铺子"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; 不删除用户数据库、截图、配置和历史数据。
