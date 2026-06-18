"""build.py — PyInstaller build script for Versatile Radio Programmer.

Usage:
  python build.py                  Build a single-file executable
  python build.py --no-onefile     Build to a dist/vrp/ folder instead (much
                                    faster to launch — no self-extraction step)

Requirements:
  uv sync --extra build            (installs pyinstaller)

Notes:
  - chirp.drivers and chirp.sources are loaded by dynamic `__import__` /
    importlib.import_module(name) (see chirp/directory.py and
    chirp_backend/query.py), so PyInstaller's static import analysis can't
    discover them on its own — --collect-submodules pulls them in explicitly.
  - prism (supplemental speech) is intentionally NOT bundled: it drags in the
    entire win32more Windows-API binding surface (~795 modules) plus numpy.
    Speech is opt-in and OFF by default; vrp/speech.py no-ops without prism.
  - Switched from Nuitka (see PROGRESS_LOG.md "Phase 9") because compiling
    552 CHIRP drivers to C took 20-30 minutes per build; PyInstaller just
    freezes bytecode, so the same build takes well under a minute.
"""

import argparse
import os
import subprocess
import sys

APP_NAME = "vrp"           # Versatile Radio Programmer short form
DISPLAY_NAME = "Versatile Radio Programmer"
ENTRY_POINT = "main.py"

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))

# PyInstaller's --add-data wants "src<sep>dest", sep is OS-specific. The
# generated .spec lives under --specpath, so relative source paths resolve
# against THAT directory, not the cwd — use absolute paths to avoid surprises.
_SEP = ";" if os.name == "nt" else ":"


def build(onefile: bool = True) -> int:
    cmd = [
        sys.executable, "-m", "PyInstaller",

        "--name", APP_NAME,
        "--noconfirm",       # overwrite a previous dist/build without prompting
        "--clean",           # don't reuse a stale PyInstaller cache

        # ---- Output mode ----
        *(["--onefile"] if onefile else []),

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

        # ---- App data: templates + static (rendered/inlined at runtime) ----
        f"--add-data={os.path.join(PROJECT_ROOT, 'static')}{_SEP}static",
        f"--add-data={os.path.join(PROJECT_ROOT, 'templates')}{_SEP}templates",

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


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build Versatile Radio Programmer with PyInstaller"
    )
    parser.add_argument(
        "--no-onefile",
        action="store_true",
        help="Build to dist/vrp/ folder instead of a single executable",
    )
    args = parser.parse_args()

    rc = build(onefile=not args.no_onefile)
    if rc == 0:
        print("\nBuild succeeded.")
        suffix = ".exe" if os.name == "nt" else ""
        if args.no_onefile:
            print(f"Output: dist{os.sep}{APP_NAME}{os.sep}{APP_NAME}{suffix}")
        else:
            print(f"Output: dist{os.sep}{APP_NAME}{suffix}")
    else:
        print(f"\nBuild failed with exit code {rc}.")
        print("See README.md section 'Packaging with PyInstaller' for known fixes.")


if __name__ == "__main__":
    main()
