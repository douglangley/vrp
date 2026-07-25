"""setup.py — py2app build for Versatile Radio Programmer (macOS only).

This is an EXPERIMENTAL, alternate macOS packaging path. The project's
primary, tested packager is PyInstaller (build.py), which already produces a
macOS artifact via `build.py --portable` (see CLAUDE.md "Building"). This
file exists alongside it, not in place of it, and follows the same
conventions build.py documents there: the CHIRP_COMMIT pin is enforced before
every build, and --portable produces the same versioned,
ditto-zipped-with-sample-images artifact PyInstaller's macOS path does.

Usage:
  uv sync --extra py2app
  uv run python setup.py py2app              Build to
                                              dist/VRP-<version>-macos-<arch>.app.
  uv run python setup.py py2app --portable    Also zip it as
                                               dist/VRP-<version>-macos-<arch>.zip
                                               (see build_portable() below).

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
        .venv-py2app/bin/python setup.py py2app --portable
  - See the STAGE_DIR comment below for why the build runs from a staging
    directory rather than the repo root directly.
"""

import os
import platform
import re
import shutil
import subprocess
import sys

from setuptools import setup

if sys.platform != "darwin":
    sys.exit("setup.py (py2app) only supports macOS. Use build.py on Windows.")

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
CHIRP_DIR = os.path.join(PROJECT_ROOT, "chirp")
CHIRP_PIN_FILE = os.path.join(PROJECT_ROOT, "CHIRP_COMMIT")
RELEASE_PREFIX = "VRP"
SAMPLES_DIRNAME = "sample-images"

_SAMPLES_README = """\
Sample radio images
===================

These let you try VRP with no radio and no cable:

    File > Open Image File...   then pick any .img in this folder.

They are the CHIRP project's test images - one saved memory image per supported
radio model - bundled from the exact CHIRP commit this build was made against
({chirp_pin}), so they match the drivers inside this build. Opening and editing
one only changes your copy here; nothing is written to a radio unless you
explicitly use Radio > Upload to Radio.

Handy ones to start with:
    Baofeng_UV-5R_Mini.img
    Baofeng_UV-5R.img
    Quansheng_UV-K5.img

Radio driver support provided by the CHIRP project - chirpmyradio.com.
"""


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


def _git_chirp(*args) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", CHIRP_DIR, *args], capture_output=True, text=True
    )


def ensure_chirp_on_pin(auto_sync: bool = True) -> bool:
    """Guarantee ./chirp is checked out at the tested CHIRP_COMMIT pin.

    Ported from build.py's function of the same name — CLAUDE.md "Building"
    requires every build (not just the PyInstaller one) to bundle the exact
    CHIRP commit the test suite last ran against, never whatever is
    incidentally checked out. See build.py's docstring for the full
    rationale; this is a straight port, not a reimplementation.
    """
    if not os.path.isfile(CHIRP_PIN_FILE):
        print("! CHIRP_COMMIT pin file missing — skipping the CHIRP version check.")
        return True
    if not os.path.isdir(os.path.join(CHIRP_DIR, ".git")):
        print("! ./chirp is not a git clone — skipping the CHIRP version check.")
        return True

    with open(CHIRP_PIN_FILE, encoding="utf-8") as fh:
        pin = fh.read().strip()

    resolved = _git_chirp("rev-parse", "--verify", "--quiet", f"{pin}^{{commit}}")
    if resolved.returncode != 0:
        print(f"! Pinned CHIRP commit {pin[:12]} is not present in ./chirp.")
        print("  Fetch it first:  uv run python tools/update_chirp.py")
        return False
    pinned_sha = resolved.stdout.strip()
    head_sha = _git_chirp("rev-parse", "HEAD").stdout.strip()

    if head_sha == pinned_sha:
        print(f"CHIRP is at the pinned commit {pinned_sha[:12]} (OK).")
        return True

    print(f"! ./chirp is at {head_sha[:12]}, but CHIRP_COMMIT pins {pinned_sha[:12]}.")
    if _git_chirp("status", "--porcelain").stdout.strip():
        print("  ./chirp has uncommitted changes — refusing to touch it.")
        print("  Clean/stash them or check out the pin manually, then rebuild.")
        return False
    if not auto_sync:
        print("  Re-run without --no-chirp-sync to check out the pin automatically,")
        print(f"  or do it by hand:  git -C chirp checkout --detach {pinned_sha[:12]}")
        return False
    print(f"  Syncing ./chirp to the pinned commit {pinned_sha[:12]}...")
    checkout = _git_chirp("checkout", "--detach", "--quiet", pinned_sha)
    if checkout.returncode != 0:
        print("  git checkout failed:\n" + (checkout.stderr or "").strip())
        return False
    print("  Synced.")
    return True


def _chirp_pin_short() -> str:
    try:
        with open(CHIRP_PIN_FILE, encoding="utf-8") as fh:
            return fh.read().strip()[:12]
    except Exception:  # noqa: BLE001
        return "unknown"


def artifact_suffix() -> str:
    """Ported from build.py — macOS builds are architecture-bound, so the
    arch is part of the artifact name (an arm64 build won't run on Intel)."""
    return f"macos-{platform.machine()}"


def _sample_files() -> list:
    """CHIRP's test images (absolute paths), or [] if the tree isn't there."""
    images_dir = os.path.join(PROJECT_ROOT, "chirp", "tests", "images")
    if not os.path.isdir(images_dir):
        print(f"! No sample images at {images_dir} - skipping them.")
        return []
    return [
        os.path.join(images_dir, name)
        for name in sorted(os.listdir(images_dir))
        if os.path.isfile(os.path.join(images_dir, name))
    ]


def build_portable(app_path: str, version: str, include_samples: bool = True) -> int:
    """Stage the .app + sample-images, then zip with ditto — same approach as
    build.py's _build_portable_macos (see that function's docstring for why
    ditto, not zipfile, is required for a .app bundle). Output:
    dist/VRP-<version>-macos-<arch>.zip, holding
    VRP-<version>/VRP-<version>-macos-<arch>.app (+ sample-images/).
    """
    if shutil.which("ditto") is None:
        print("Cannot build the portable zip: `ditto` not found on PATH.")
        return 1

    top = f"{RELEASE_PREFIX}-{version}"
    zip_path = os.path.join(
        PROJECT_ROOT, "dist", f"{top}-{artifact_suffix()}.zip"
    )
    staging_root = os.path.join(PROJECT_ROOT, "build", "py2app_portable")
    staging = os.path.join(staging_root, top)
    shutil.rmtree(staging_root, ignore_errors=True)
    os.makedirs(staging, exist_ok=True)

    print("\nStaging the portable bundle...")
    rc = subprocess.run(
        ["ditto", app_path, os.path.join(staging, os.path.basename(app_path))]
    )
    if rc.returncode != 0:
        print(f"ditto failed to copy the .app (exit {rc.returncode}).")
        return rc.returncode

    samples = 0
    if include_samples:
        files = _sample_files()
        if files:
            samples_dir = os.path.join(staging, SAMPLES_DIRNAME)
            os.makedirs(samples_dir, exist_ok=True)
            for full in files:
                shutil.copy2(full, samples_dir)
                samples += 1
            with open(os.path.join(samples_dir, "README.txt"), "w",
                      encoding="utf-8") as fh:
                fh.write(_SAMPLES_README.format(chirp_pin=_chirp_pin_short()))
            samples += 1

    print("Creating the portable zip with ditto...")
    if os.path.exists(zip_path):
        os.remove(zip_path)
    rc = subprocess.run([
        "ditto", "-c", "-k", "--sequesterRsrc", "--keepParent",
        staging, zip_path,
    ])
    if rc.returncode != 0:
        print(f"ditto failed to create the zip (exit {rc.returncode}).")
        return rc.returncode
    shutil.rmtree(staging_root, ignore_errors=True)

    size_mb = os.path.getsize(zip_path) / (1024 * 1024)
    print(f"Zipped {os.path.basename(app_path)} ({size_mb:.1f} MB) under {top}/")
    if samples:
        print(f"  + {samples} files in {top}/{SAMPLES_DIRNAME}/")
    print(f"Output: {os.path.relpath(zip_path, PROJECT_ROOT)}")
    print(
        "\nNOTE: the .app is unsigned and unnotarized, so Gatekeeper refuses "
        "it\non first launch. Testers must right-click the app and choose "
        "Open, or run:\n"
        f"    xattr -dr com.apple.quarantine /path/to/{top}/"
        f"{os.path.basename(app_path)}\n"
        "Say so in the release notes."
    )
    return 0


PORTABLE = "--portable" in sys.argv
if PORTABLE:
    sys.argv.remove("--portable")

if not ensure_chirp_on_pin():
    print("\nAborting: ./chirp is not at the tested CHIRP_COMMIT pin.")
    sys.exit(1)

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
# Named to match the portable zip exactly (VRP-<version>-macos-<arch>.app),
# not the generic "vrp.app" build.py's PyInstaller path uses — a tester with
# several builds on disk (or unzipped side by side) can tell them apart by
# the .app name alone, the same way the zip and its VRP-<version>/ top folder
# already do.
RELEASE_APP_NAME = f"{RELEASE_PREFIX}-{VERSION}-{artifact_suffix()}"
final_app = os.path.join(DIST_DIR, f"{RELEASE_APP_NAME}.app")
if os.path.isdir(built_app):
    os.makedirs(DIST_DIR, exist_ok=True)
    if os.path.isdir(final_app):
        shutil.rmtree(final_app)
    shutil.move(built_app, final_app)
    print(f"\nBuild succeeded.\nOutput: {os.path.relpath(final_app, PROJECT_ROOT)}")

    if PORTABLE:
        rc = build_portable(final_app, VERSION)
        if rc != 0:
            print(f"\nPortable zip failed with exit code {rc}.")
            sys.exit(rc)
        print("\nPortable build ready.")
