; installer.iss — Inno Setup script for Versatile Radio Programmer (VRP)
;
; Wraps the PyInstaller *onedir* output (dist\vrp\) into a Windows installer
; with a Start-menu shortcut and an uninstaller — the way upstream CHIRP ships
; its PyInstaller build, rather than as a loose self-extracting .exe.
;
; Build the folder first, then compile this script:
;
;   uv run python build.py --installer        (does both for you)
;
; or, equivalently, by hand:
;
;   uv run python build.py                     (produces dist\vrp\)
;   ISCC installer.iss /DMyAppVersion=0.1.0
;
; Requires Inno Setup 6: https://jrsoftware.org/isinfo.php
; build.py passes the version in via /DMyAppVersion; this fallback only applies
; when ISCC is run by hand without it.

#ifndef MyAppVersion
  #define MyAppVersion "0.0.0"
#endif

#define MyAppName "Versatile Radio Programmer"
#define MyAppExeName "vrp.exe"
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
; VRP is built as a native 64-bit app. "x64" installs in 64-bit mode on x64
; Windows and is accepted by every Inno Setup 6.x (alias for x64os on 6.3+).
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64
OutputDir=dist
OutputBaseFilename=vrp-{#MyAppVersion}-setup
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
; Pull in the entire PyInstaller onedir tree (the .exe plus _internal/).
Source: "dist\vrp\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
; Standard accessible "launch now" checkbox on the final wizard page.
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#MyAppName}}"; Flags: nowait postinstall skipifsilent
