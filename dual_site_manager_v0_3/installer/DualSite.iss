#define MyAppName "DualSite Inventory"
#define MyAppVersion "0.3.0"
#define MyAppExeName "DualSiteInventory.exe"

[Setup]
AppId={{5B3EC6E3-4D6B-476B-90EC-FA806F59A8A8}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
DefaultDirName={localappdata}\Programs\DualSiteInventory
DefaultGroupName={#MyAppName}
OutputDir=..\release
OutputBaseFilename=DualSiteInventory_Setup_v0.3.0
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
UninstallDisplayName={#MyAppName}
DisableProgramGroupPage=yes

[Files]
Source: "..\dist\DualSiteInventory\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autodesktop}\双站商品管理中心"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon
Name: "{group}\双站商品管理中心"; Filename: "{app}\{#MyAppExeName}"

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "快捷方式:"; Flags: checkedonce

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "启动双站商品管理中心"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; 用户数据保存在 %APPDATA% / Documents 等目录，不会在卸载时删除。
