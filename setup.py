"""setup.py — py2app build for Versatile Radio Programmer (macOS only).

This is an EXPERIMENTAL, alternate macOS packaging path. The project's
primary, tested packager is PyInstaller (build.py), which already produces a
macOS artifact via `build.py --portable` (see CLAUDE.md "Building"). This
file exists alongside it, not in place of it.

Usage:
  uv sync --extra py2app
  uv run python setup.py py2app
Output: dist/vrp.app

Notes on how this differs from the PyInstaller build:
  - PyInstaller freezes pure-Python modules into a zipped PYZ archive, which
    is why chirp/drivers/__init__.py's filesystem glob (building __all__)
    comes up empty when frozen — see chirp_backend.radio._ensure_driver_
    modules() and the "registered ZERO drivers" PROGRESS_LOG entry. py2app's
    'packages' option instead copies whole package trees as REAL, unzipped
    files under Contents/Resources/lib/pythonX.Y/, so that glob works
    unmodified, exactly as it does running from source. _ensure_driver_
    modules() still runs (radio.py always calls it) but is a no-op here.
  - Because 'packages' copies entire trees regardless of what's statically
    imported, this also picks up chirp/stock_configs/*.csv and prism's
    native libprism.dylib for free, without PyInstaller's targeted
    --add-data / --collect-binaries flags.
  - Requires a macOS "framework" Python build (real .so/.dylib files for
    stdlib extensions) — uv's managed python-build-standalone interpreter is
    statically linked and py2app cannot introspect it (fails partway through
    trying to locate zlib's file). Build with a framework Python, e.g.
    `brew install python@3.11` (NOT the project's normal uv-managed venv):
        /opt/homebrew/bin/python3.11 -m venv .venv-py2app
        uv pip install --python .venv-py2app/bin/python \\
            wxpython prismatoid pyserial lark requests py2app \\
            "wx-accessible-grid @ git+https://github.com/payown/wx-accessible-grid.git@494103f8d7c82f79bc40221d823a7991d8984cf6"
        .venv-py2app/bin/python setup.py py2app
  - See the STAGE_DIR comment below for why the build runs from a staging
    directory rather than the repo root directly.
"""

import os
import re
import shutil
import sys

from setuptools import setup

if sys.platform != "darwin":
    sys.exit("setup.py (py2app) only supports macOS. Use build.py on Windows.")

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))


def _read_version() -> str:
    """Read __version__ from vrp/__init__.py without importing it (mirrors
    build.py._read_version — importing vrp has an import-machinery side
    effect via vrp._chirp_path)."""
    init_py = os.path.join(PROJECT_ROOT, "vrp", "__init__.py")
    with open(init_py, encoding="utf-8") as fh:
        match = re.search(r'^__version__\s*=\s*"([^"]+)"', fh.read(), re.M)
    if not match:
        raise RuntimeError(f"Could not find __version__ in {init_py}")
    return match.group(1)


APP_NAME = "vrp"
DISPLAY_NAME = "Versatile Radio Programmer"
VERSION = _read_version()

# py2app's get_bootstrap() (build_app.py) checks os.path.exists(pkg_name)
# against the CURRENT WORKING DIRECTORY before treating a 'packages' entry as
# a dotted import name to resolve via sys.path. Run from the repo root, the
# bare string "chirp" coincidentally matches a *real* relative path there —
# but the wrong one: ./chirp is the clone root (holding tests/, tools/,
# chirpc, setup.py, ...), not ./chirp/chirp, the actual importable package
# two levels down. That silently bundles the whole clone — including CHIRP's
# own test images and dev tooling — under Contents/Resources/.../chirp/
# instead of just the package (verified: a fresh build's bundled "chirp" had
# no drivers/ or stock_configs/ subdirectory at all, just the clone's
# top-level files). "chirp_backend" and "vrp" happen to dodge this only by
# coincidence, since those import names ARE their own real top-level repo
# directories.
#
# Building from a dedicated staging directory containing symlinks straight to
# the real package roots removes the ambiguity entirely: cwd no longer has a
# "chirp" entry that resolves to anything but chirp/chirp itself.
STAGE_DIR = os.path.join(PROJECT_ROOT, "build", "py2app_stage")
DIST_DIR = os.path.join(PROJECT_ROOT, "dist")

shutil.rmtree(STAGE_DIR, ignore_errors=True)
os.makedirs(STAGE_DIR)
for link_name, real_target in [
    ("chirp", os.path.join(PROJECT_ROOT, "chirp", "chirp")),
    ("chirp_backend", os.path.join(PROJECT_ROOT, "chirp_backend")),
    ("vrp", os.path.join(PROJECT_ROOT, "vrp")),
    ("main.py", os.path.join(PROJECT_ROOT, "main.py")),
]:
    os.symlink(real_target, os.path.join(STAGE_DIR, link_name))
os.chdir(STAGE_DIR)

OPTIONS = {
    "argv_emulation": False,
    "packages": [
        # Whole-tree copies (real files on disk in the bundle), not just
        # statically-followed imports — see the module docstring.
        "chirp",
        "chirp_backend",
        "vrp",
        "prism",
        "cffi",  # prism's sole third-party import; ships a compiled
                 # _cffi_backend extension that modulegraph's normal
                 # dependency walk doesn't reliably pick up
        "lark",
        "certifi",
    ],
    # Never imported by VRP; guards against the bundle silently ballooning if
    # that ever changes (mirrors build.py's PyInstaller excludes).
    "excludes": ["numpy", "win32more", "tkinter"],
    "plist": {
        "CFBundleName": DISPLAY_NAME,
        "CFBundleDisplayName": DISPLAY_NAME,
        "CFBundleIdentifier": "com.chirpmyradio.vrp",
        "CFBundleVersion": VERSION,
        "CFBundleShortVersionString": VERSION,
        "NSHumanReadableCopyright": (
            "Radio driver support provided by the CHIRP project "
            "— chirpmyradio.com."
        ),
        "NSHighResolutionCapable": True,
        "LSMinimumSystemVersion": "10.13",
    },
}

try:
    setup(
        name=APP_NAME,
        app=["main.py"],
        options={"py2app": OPTIONS},
    )
finally:
    os.chdir(PROJECT_ROOT)

built_app = os.path.join(STAGE_DIR, "dist", f"{DISPLAY_NAME}.app")
final_app = os.path.join(DIST_DIR, f"{APP_NAME}.app")
if os.path.isdir(built_app):
    os.makedirs(DIST_DIR, exist_ok=True)
    if os.path.isdir(final_app):
        shutil.rmtree(final_app)
    shutil.move(built_app, final_app)
    print(f"\nBuild succeeded.\nOutput: {os.path.relpath(final_app, PROJECT_ROOT)}")
