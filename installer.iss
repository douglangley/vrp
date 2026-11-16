; installer.iss — Inno Setup script for Versatile Radio Programmer (VRP)
;
; Wraps the PyInstaller *onedir* output (dist\VRP\) into a Windows installer
; with a Start-menu shortcut and an uninstaller — the way upstream CHIRP ships
; its PyInstaller build, rather than as a loose self-extracting .exe.
;
; Build the folder first, then compile this script:
;
;   uv run python build.py --installer        (does both for you)
;
; or, equivalently, by hand:
;
;   uv run python build.py                     (produces dist\VRP\)
;   ISCC installer.iss /DMyAppVersion=20260715.1
;
; Requires Inno Setup 6: https://jrsoftware.org/isinfo.php
; build.py passes the version in via /DMyAppVersion; this fallback only applies
; when ISCC is run by hand without it. Versions are dates (YYYYMMDD.N — see
; tools/release_version.py); AppVersion takes an arbitrary string, so the date
; scheme needs nothing special here.

#ifndef MyAppVersion
  #define MyAppVersion "0.0.0"
#endif

#define MyAppName "Versatile Radio Programmer"
; Must match build.py's APP_NAME (PyInstaller's --name), which produces VRP.exe.
#define MyAppExeName "VRP.exe"
#define MyAppPublisher "Versatile Radio Programmer"
; Driver support is CHIRP's; the attribution also lives in the app (status bar
; field 1 + About box) per CLAUDE.md.
#define MyAppURL "https://chirpmyradio.com"

[Setup]
; AppId uniquely identifies the app for upgrades/uninstall — keep it STABLE
; across releases (do not regenerate it, or upgrades become side-by-side
; installs). The leading "{{" is an escaped literal brace in Inno's syntax.
AppId={{7C2F1B6E-3A4D-4E9B-9C61-2D5E8F0A1B34}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
UninstallDisplayIcon={app}\{#MyAppExeName}
; VRP is built as a native 64-bit app. "x64compatible" installs in 64-bit mode
; on x64 Windows (and ARM64 under x64 emulation). Requires Inno Setup 6.3+
; (we build with 6.7.x); older 6.x used the now-deprecated "x64".
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=dist
OutputBaseFilename=VRP-{#MyAppVersion}-setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
; Offer a per-user install so a standard (non-admin) account can install too —
; the wizard asks which when elevation isn't available.
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; Pull in the entire PyInstaller onedir tree: the .exe, _internal/, and the two
; folders build.py stages beside the exe — help\ (the Help menu opens these) and
; sample-images\ (CHIRP's test images, so a user with no radio or no cable can
; still open a real image). Because this recurses, both arrive with no rule of
; their own; build.py --no-samples simply leaves sample-images\ out of dist\VRP\
; and the Check below drops its shortcut to match.
Source: "dist\VRP\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
; A Start-menu route to the samples. They install into {app}\sample-images,
; which a user would otherwise have to know to go hunting for in Program Files —
; and "browse to the install directory" is a poor instruction for the screen
; reader users this app is built for. Opens the folder in Explorer.
Name: "{group}\Sample radio images"; Filename: "{app}\sample-images"; Check: DirExists(ExpandConstant('{app}\sample-images'))
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
; Standard accessible "launch now" checkbox on the final wizard page.
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#MyAppName}}"; Flags: nowait postinstall skipifsilent
