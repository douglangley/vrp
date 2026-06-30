"""build.py — PyInstaller build script for Versatile Radio Programmer.

Usage:
  python build.py                  Build to a dist/vrp/ folder (onedir; the
                                   default). Starts instantly — no per-launch
                                   self-extraction.
  python build.py --onefile        Build a single dist/vrp.exe instead. Slower
                                   cold start (it re-extracts the interpreter +
                                   wxPython + 552 drivers to a temp dir on every
                                   launch) and trips Defender/SmartScreen more
                                   often — handy only for a quick throwaway test.
  python build.py --installer      Build onedir, then compile a Windows installer
                                   (installer.iss) with Inno Setup. This is how
                                   the app is meant to ship.

Requirements:
  uv sync --extra build            (installs pyinstaller)
  Inno Setup 6 (only for --installer)   https://jrsoftware.org/isinfo.php

Notes:
  - Default is onedir, not onefile. onefile unpacks the whole interpreter +
    wxPython + 552 CHIRP drivers to a temp dir on *every* launch — that is the
    slow cold start — and it is a frequent antivirus/SmartScreen false-positive
    trigger. onedir starts immediately; ship the folder wrapped in the Inno Setup
    installer (--installer), which is exactly how upstream CHIRP distributes its
    own PyInstaller build (Start-menu shortcut + uninstaller, not a loose .exe).
  - chirp.drivers and chirp.sources are loaded by dynamic `__import__` /
    importlib.import_module(name) (see chirp/directory.py and
    chirp_backend/query.py), so PyInstaller's static import analysis can't
    discover them on its own — --collect-submodules pulls them in explicitly.
  - prism (supplemental speech) is intentionally NOT bundled: it drags in the
    entire win32more Windows-API binding surface (~795 modules) plus numpy.
    Speech is opt-in and OFF by default; vrp/speech.py no-ops without prism.
  - UPX is deliberately not used (no --upx-dir): it barely shrinks a wx app,
    slows the build, and is a major antivirus false-positive trigger.
  - Switched from Nuitka (see PROGRESS_LOG.md "Phase 9") because compiling
    552 CHIRP drivers to C took 20-30 minutes per build; PyInstaller just
    freezes bytecode, so the same build takes well under a minute.
"""

import argparse
import os
import re
import shutil
import subprocess
import sys

APP_NAME = "vrp"           # Versatile Radio Programmer short form
DISPLAY_NAME = "Versatile Radio Programmer"
ENTRY_POINT = "main.py"
INSTALLER_SCRIPT = "installer.iss"

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))


def _read_version() -> str:
    """Read __version__ from vrp/__init__.py without importing it.

    Importing vrp has an import-machinery side effect (vrp._chirp_path), so a
    plain regex read keeps the build script side-effect free.
    """
    init_py = os.path.join(PROJECT_ROOT, "vrp", "__init__.py")
    with open(init_py, encoding="utf-8") as fh:
        match = re.search(r'^__version__\s*=\s*"([^"]+)"', fh.read(), re.M)
    if not match:
        raise RuntimeError(f"Could not find __version__ in {init_py}")
    return match.group(1)


def build(onefile: bool) -> int:
    cmd = [
        sys.executable, "-m", "PyInstaller",

        "--name", APP_NAME,
        "--noconfirm",       # overwrite a previous dist/build without prompting
        "--clean",           # don't reuse a stale PyInstaller cache

        # ---- Output mode ----
        # onedir (default): a dist/vrp/ folder that launches with no extraction
        # step. onefile: a single self-extracting dist/vrp.exe (slower start).
        *(["--onefile"] if onefile else ["--onedir"]),

        # ---- No console window (GUI app) ----
        "--windowed",

        # ---- CHIRP is an editable install (PEP 660, via uv) ----
        # PyInstaller's static modulegraph analysis doesn't go through Python's
        # import machinery (it can't see uv's custom editable-install finder),
        # so --collect-submodules below finds the dynamically-imported driver/
        # source module *names* but can't locate their actual .py files unless
        # the real source directory is also on its search path.
        f"--paths={os.path.join(PROJECT_ROOT, 'chirp')}",

        # ---- prism (supplemental speech) is intentionally NOT bundled ----
        "--exclude-module=prism",
        "--exclude-module=win32more",
        "--exclude-module=numpy",

        # ---- CHIRP library (drivers/sources loaded by dynamic import) ----
        "--collect-submodules=chirp.drivers",
        "--collect-submodules=chirp.sources",
        "--collect-data=chirp",              # stock_configs, locale, etc.

        # ---- lark (used by chirp.bitwise_grammar) — needs its .lark grammar files
        "--collect-data=lark",

        # NOTE: the native UI renders no HTML, so there are no templates/ or
        # static/ assets to bundle (the webview UI that needed them was removed —
        # see CLAUDE.md / PROGRESS_LOG.md "2026-06-29").

        # ---- Output locations (match the old Nuitka layout) ----
        "--distpath=dist",
        "--workpath=build",
        "--specpath=build",

        ENTRY_POINT,
    ]

    print("Running PyInstaller build...")
    print("Command:", " ".join(cmd))
    print()

    return subprocess.run(cmd).returncode


def _find_iscc() -> str | None:
    """Locate the Inno Setup command-line compiler (ISCC.exe).

    Order: an explicit INNO_SETUP_ISCC override, then PATH, then the standard
    install locations for Inno Setup 6.
    """
    override = os.environ.get("INNO_SETUP_ISCC")
    if override and os.path.isfile(override):
        return override

    on_path = shutil.which("ISCC")
    if on_path:
        return on_path

    program_files = [
        os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
        os.environ.get("ProgramFiles", r"C:\Program Files"),
    ]
    for base in program_files:
        candidate = os.path.join(base, "Inno Setup 6", "ISCC.exe")
        if os.path.isfile(candidate):
            return candidate
    return None


def build_installer(version: str) -> int:
    """Compile installer.iss with Inno Setup, wrapping the dist/vrp/ folder."""
    onedir = os.path.join(PROJECT_ROOT, "dist", APP_NAME)
    if not os.path.isdir(onedir):
        print(f"Cannot build installer: {onedir}{os.sep} not found.")
        print("Run the onedir build first (python build.py, no --onefile).")
        return 1

    iscc = _find_iscc()
    if not iscc:
        print("Inno Setup compiler (ISCC.exe) not found.")
        print("Install Inno Setup 6 from https://jrsoftware.org/isinfo.php,")
        print("or set INNO_SETUP_ISCC to the full path of ISCC.exe.")
        return 1

    cmd = [iscc, f"/DMyAppVersion={version}",
           os.path.join(PROJECT_ROOT, INSTALLER_SCRIPT)]
    print("\nRunning Inno Setup...")
    print("Command:", " ".join(cmd))
    print()
    return subprocess.run(cmd).returncode


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build Versatile Radio Programmer with PyInstaller"
    )
    parser.add_argument(
        "--onefile",
        action="store_true",
        help="Build a single self-extracting dist/vrp.exe (slower start) "
             "instead of the default dist/vrp/ folder.",
    )
    parser.add_argument(
        "--installer",
        action="store_true",
        help="After the onedir build, compile the Windows installer with Inno "
             "Setup (installer.iss). Incompatible with --onefile.",
    )
    args = parser.parse_args()

    if args.installer and args.onefile:
        parser.error(
            "--installer wraps the onedir folder, so it can't be combined with "
            "--onefile."
        )

    version = _read_version()

    rc = build(onefile=args.onefile)
    if rc != 0:
        print(f"\nBuild failed with exit code {rc}.")
        print("See README.md section 'Packaging with PyInstaller' for known fixes.")
        sys.exit(rc)

    print("\nBuild succeeded.")
    suffix = ".exe" if os.name == "nt" else ""
    if args.onefile:
        print(f"Output: dist{os.sep}{APP_NAME}{suffix}")
    else:
        print(f"Output: dist{os.sep}{APP_NAME}{os.sep}{APP_NAME}{suffix}")

    if args.installer:
        rc = build_installer(version)
        if rc != 0:
            print(f"\nInstaller build failed with exit code {rc}.")
            sys.exit(rc)
        print("\nInstaller built.")
        print(f"Output: dist{os.sep}{APP_NAME}-{version}-setup.exe")


if __name__ == "__main__":
    main()
