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
  python build.py --portable       Build onedir, then zip it as
                                   dist/VRP-<version>-win64.zip — a no-install
                                   build to hand to testers: unzip anywhere, run
                                   vrp.exe from the folder. Includes CHIRP's test
                                   images in a top-level sample-images/ folder so
                                   a tester with no radio can still open a real
                                   image (--no-samples omits them). Combinable
                                   with --installer.
  python build.py --no-chirp-sync  Verify ./chirp matches the CHIRP_COMMIT pin
                                   but don't auto-checkout it (abort on mismatch
                                   instead of fixing the clone).

Every build first ensures ./chirp is checked out at the tested CHIRP_COMMIT pin
(a clean clone is synced to it automatically) so the frozen app bundles the exact
driver set the test suite passed against — adopting a *newer* CHIRP stays the
deliberate, tested step in tools/update_chirp.py.

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
  - chirp.drivers is loaded by dynamic `__import__` / importlib.import_module
    (see chirp/directory.py), so PyInstaller's static analysis can't discover the
    driver modules on its own — --collect-submodules pulls them in explicitly.
    NOTE: bundling them is NOT sufficient to make them work — see
    chirp_backend.radio._ensure_driver_modules() and the "registered ZERO
    drivers" PROGRESS_LOG entry (2026-07-15).
    chirp.sources needs no --collect-submodules: chirp_backend/repeaterbook.py
    imports `from chirp.sources import repeaterbook` statically (inside
    functions, which PyInstaller's modulegraph still follows), and that pulls in
    `requests`/certifi with it. Verified frozen by tools/spike_frozen_audit.py —
    a LIVE fetch of 40 Delaware repeaters over HTTPS from the frozen .exe.
  - prism (speech) IS bundled, and must be. It is not "supplemental" on the
    desktop: the native UI has no ARIA live region (that died with the webview
    UI), and on Windows the generic DataViewCtrl announces no per-cell cursor,
    so VRP's own Left/Right cell cursor is voiced ONLY through prism. A
    prism-less build navigates cells silently -- see the 2026-07-15 PROGRESS_LOG
    entry. prism ships a native prism.dll in prism/_native/ which it dlopens at
    import time, so --collect-binaries=prism is required; without it `import
    prism` raises FileNotFoundError and speech is silently dead.
    The old "prism drags in ~795 win32more modules plus numpy" note was a
    NUITKA-era artifact (--include-package=win32more force-included the package
    regardless of imports). prism imports only cffi -- never win32more, never
    numpy -- so under PyInstaller, which follows real imports, bundling it costs
    ~1 MB.
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
import zipfile

APP_NAME = "vrp"           # Versatile Radio Programmer short form
RELEASE_PREFIX = "VRP"     # release/tag name: VRP-<version> (tools/release_version.py)
DISPLAY_NAME = "Versatile Radio Programmer"
ENTRY_POINT = "main.py"
INSTALLER_SCRIPT = "installer.iss"

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
CHIRP_DIR = os.path.join(PROJECT_ROOT, "chirp")
CHIRP_PIN_FILE = os.path.join(PROJECT_ROOT, "CHIRP_COMMIT")


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


def _git_chirp(*args) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", CHIRP_DIR, *args], capture_output=True, text=True
    )


def ensure_chirp_on_pin(auto_sync: bool = True) -> bool:
    """Guarantee ./chirp is checked out at the tested CHIRP_COMMIT pin.

    The frozen build must bundle the *exact* CHIRP commit VRP's test suite was
    last run against (the SHA in CHIRP_COMMIT) — never whatever is incidentally
    checked out, and never upstream HEAD. Adopting a newer CHIRP is a deliberate,
    tested step (tools/update_chirp.py fetches, runs the suite, and only then
    bumps the pin); it must not happen as a silent side effect of building, which
    would ship untested driver code.

    So "make CHIRP current" here means "make ./chirp match the pin", which this
    does automatically for a clean clone. It never discards uncommitted work and
    never pulls from the network. Returns True if the build may proceed.
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

        # ---- prism (speech) — REQUIRED, not optional ----
        # prism dlopens a native prism.dll from prism/_native/ (see prism/lib.py
        # _find_native_dir), which PyInstaller does not bundle on its own: it is
        # package *data*, not an import. Without this flag `import prism` raises
        # FileNotFoundError from os.add_dll_directory and the app runs silent —
        # which on Windows means the Left/Right cell cursor, whose only voice is
        # prism, announces nothing. Verified frozen: 14 backends, NVDA acquired.
        "--collect-binaries=prism",
        # Belt-and-braces only: prism imports neither of these (its sole
        # third-party import is cffi). win32more is declared by prismatoid's
        # metadata but never imported, and numpy is not a prismatoid dependency
        # at all. Kept as explicit guards so a future transitive import can't
        # silently balloon the build — the ~795-module win32more blowup that
        # motivated them was a Nuitka --include-package artifact, not something
        # PyInstaller does. Drop them if prism ever genuinely needs win32more.
        "--exclude-module=win32more",
        "--exclude-module=numpy",

        # ---- CHIRP library (drivers loaded by dynamic import) ----
        # Bundling the driver modules is necessary but NOT sufficient: CHIRP
        # discovers them by globbing *.py off disk, which finds nothing in a
        # frozen build. chirp_backend.radio._ensure_driver_modules() repairs
        # that at runtime — without it, zero drivers register and the app can
        # neither open an image nor list a radio. See PROGRESS_LOG 2026-07-15.
        "--collect-submodules=chirp.drivers",
        # NOTE: chirp.sources needs no collect directive. RepeaterBook came back
        # on 2026-07-09 and chirp_backend/repeaterbook.py imports it statically
        # (`from chirp.sources import repeaterbook`, inside functions — which
        # modulegraph still follows), pulling in requests/certifi with it.
        # Verified frozen: a live 40-repeater fetch over HTTPS from the .exe
        # (tools/spike_frozen_audit.py).
        # NOTE: deliberately NOT --collect-data=chirp. CHIRP is an editable
        # install rooted at the repo, so --collect-data=chirp sweeps in the
        # whole working tree — .git/ (~3.8 MB), tests/ radio .img images
        # (~9.5 MB), CI/packaging dirs, and chirp's own branding (share/ logos)
        # — none of which VRP runs. The drivers/sources are pure .py (collected
        # above into the PYZ) with no companion data files, and VRP uses none of
        # CHIRP's data assets (stock_configs/locale/share are wxui- or
        # branding-only). If VRP ever loads a CHIRP data file at runtime, add it
        # back with a targeted --add-data for that one subdir, not the repo.

        # ---- lark (used by chirp.bitwise_grammar) — needs its .lark grammar files
        "--collect-data=lark",

        # ---- CHIRP stock configs (the "Frequency lists" import) ----
        # The ~20 curated CSV lists in chirp/chirp/stock_configs are DATA, not
        # .py, so --collect-submodules doesn't grab them. Bundle just that one
        # subdir (the targeted --add-data the "NOT --collect-data=chirp" note
        # above anticipates) to <root>/chirp/stock_configs, which is exactly
        # where chirp_backend.stock_configs.stock_configs_dir() looks when frozen
        # (sys._MEIPASS/chirp/stock_configs). ensure_chirp_on_pin() ran first, so
        # these match the tested CHIRP_COMMIT.
        "--add-data=%s%schirp/stock_configs" % (
            os.path.join(PROJECT_ROOT, "chirp", "chirp", "stock_configs"),
            os.pathsep,
        ),

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


def _chirp_pin_short() -> str:
    try:
        with open(CHIRP_PIN_FILE, encoding="utf-8") as fh:
            return fh.read().strip()[:12]
    except Exception:  # noqa: BLE001
        return "unknown"


def build_portable(version: str, include_samples: bool = True) -> int:
    """Zip the dist/vrp/ onedir folder into dist/VRP-<version>-win64.zip.

    The no-install distribution: the tester unzips it and runs vrp.exe from the
    folder. The zip's single top-level directory is named for the release
    (VRP-20260715.1/), not "vrp/", so unzipping two releases side by side
    doesn't merge them and the folder on disk says which build it is —
    PyInstaller's onedir doesn't care what its folder is called, only that
    vrp.exe and _internal/ stay together inside it.

    ``include_samples`` also drops CHIRP's test images into a top-level
    ``sample-images/`` folder beside vrp.exe, so a tester with no radio (or no
    cable to hand) can still open a real image and exercise the grid. They go at
    the TOP level deliberately, not into _internal/ — that is app plumbing a
    user should never have to open, and a File-Open dialog needs somewhere
    obvious to point at. They come from ./chirp at the enforced CHIRP_COMMIT
    pin, so they always match the bundled driver set.

    Samples are on by default for the portable build because that IS the tester
    build; the Inno Setup installer never includes them (it wraps dist/vrp/
    only), since a real user has their own radio.
    """
    onedir = os.path.join(PROJECT_ROOT, "dist", APP_NAME)
    if not os.path.isdir(onedir):
        print(f"Cannot build the portable zip: {onedir}{os.sep} not found.")
        print("Run the onedir build first (python build.py, no --onefile).")
        return 1

    top = f"{RELEASE_PREFIX}-{version}"
    zip_path = os.path.join(PROJECT_ROOT, "dist", f"{top}-win64.zip")
    print("\nCreating the portable zip...")
    if os.path.exists(zip_path):
        os.remove(zip_path)  # rebuilding the same release replaces it

    count = 0
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, _dirs, files in os.walk(onedir):
            for name in sorted(files):
                full = os.path.join(root, name)
                # Re-root every entry under the release-named top folder.
                arcname = os.path.join(top, os.path.relpath(full, onedir))
                zf.write(full, arcname)
                count += 1

        samples = 0
        if include_samples:
            images_dir = os.path.join(PROJECT_ROOT, "chirp", "tests", "images")
            if not os.path.isdir(images_dir):
                print(f"! No sample images at {images_dir} — skipping them.")
            else:
                for name in sorted(os.listdir(images_dir)):
                    full = os.path.join(images_dir, name)
                    if not os.path.isfile(full):
                        continue
                    zf.write(full, os.path.join(top, SAMPLES_DIRNAME, name))
                    samples += 1
                zf.writestr(
                    os.path.join(top, SAMPLES_DIRNAME, "README.txt"),
                    _SAMPLES_README.format(chirp_pin=_chirp_pin_short()),
                )
                samples += 1

    size_mb = os.path.getsize(zip_path) / (1024 * 1024)
    print(f"Zipped {count} app files ({size_mb:.1f} MB) under {top}{os.sep}")
    if include_samples and samples:
        print(f"  + {samples} files in {top}{os.sep}{SAMPLES_DIRNAME}{os.sep}")
    return 0


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
    parser.add_argument(
        "--portable",
        action="store_true",
        help="After the onedir build, zip it as dist/VRP-<version>-win64.zip — "
             "a no-install build to hand to testers. Incompatible with --onefile.",
    )
    parser.add_argument(
        "--no-samples",
        action="store_true",
        help="Omit the sample-images/ folder (CHIRP's test images) from the "
             "--portable zip. They're included by default so a tester with no "
             "radio can still open a real image.",
    )
    parser.add_argument(
        "--no-chirp-sync",
        action="store_true",
        help="Don't auto-checkout ./chirp to the CHIRP_COMMIT pin; only verify "
             "and abort on a mismatch. (The pin is always enforced — this just "
             "refuses to modify the clone for you.)",
    )
    args = parser.parse_args()

    if args.installer and args.onefile:
        parser.error(
            "--installer wraps the onedir folder, so it can't be combined with "
            "--onefile."
        )
    if args.portable and args.onefile:
        parser.error(
            "--portable zips the onedir folder, so it can't be combined with "
            "--onefile. (A onefile build is already a single portable .exe.)"
        )

    version = _read_version()

    if not ensure_chirp_on_pin(auto_sync=not args.no_chirp_sync):
        print("\nAborting: ./chirp is not at the tested CHIRP_COMMIT pin.")
        sys.exit(1)

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

    if args.portable:
        rc = build_portable(version, include_samples=not args.no_samples)
        if rc != 0:
            print(f"\nPortable zip failed with exit code {rc}.")
            sys.exit(rc)
        print("\nPortable build ready.")
        print(f"Output: dist{os.sep}{RELEASE_PREFIX}-{version}-win64.zip")

    if args.installer:
        rc = build_installer(version)
        if rc != 0:
            print(f"\nInstaller build failed with exit code {rc}.")
            sys.exit(rc)
        print("\nInstaller built.")
        print(f"Output: dist{os.sep}{APP_NAME}-{version}-setup.exe")


if __name__ == "__main__":
    main()
