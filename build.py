"""build.py — PyInstaller build script for Versatile Radio Programmer.

Usage:
  python build.py                  Build to a dist/VRP/ folder (onedir; the
                                   default). Starts instantly — no per-launch
                                   self-extraction.
  python build.py --onefile        Build a single dist/VRP.exe instead. Slower
                                   cold start (it re-extracts the interpreter +
                                   wxPython + 552 drivers to a temp dir on every
                                   launch) and trips Defender/SmartScreen more
                                   often — handy only for a quick throwaway test.
  python build.py --installer      Build onedir, then compile a Windows installer
                                   (installer.iss) with Inno Setup. This is how
                                   the app is meant to ship on Windows.
                                   Windows-only.
  python build.py --dmg            The macOS counterpart: wrap dist/VRP.app in
                                   dist/VRP-<version>-macos-<arch>.dmg, holding
                                   the app beside an /Applications symlink to
                                   drag it onto. This is how the app is meant to
                                   ship on a Mac. macOS-only.
  python build.py --portable       Build onedir, then zip it as
                                   dist/VRP-<version>-<platform>.zip — a
                                   no-install build to hand to testers: unzip
                                   anywhere and run it from the folder. The zip
                                   carries the version; what comes OUT of it is
                                   named plain "VRP" so a new release lands on
                                   top of the old one instead of beside it.
                                   Windows: -win64.zip holding VRP/VRP.exe +
                                   _internal/. macOS: -macos-<arch>.zip holding
                                   VRP/VRP.app, zipped with ditto (zipfile would
                                   break the bundle). Combinable with --installer
                                   (Windows only).
  python build.py --no-samples     Leave CHIRP's test images out of the build.
  python build.py --no-chirp-sync  Verify ./chirp matches the CHIRP_COMMIT pin
                                   but don't auto-checkout it (abort on mismatch
                                   instead of fixing the clone).

EVERY build stages two things into the app before anything packages it up:
help/ (the Help menu opens these) and sample-images/ (CHIRP's test images, so
anyone with no radio or no cable can still open a real image). Both land at the
TOP level beside the executable — never under _internal/ — and on macOS in the
bundle's Contents/Resources/. The portable zip and the Inno Setup installer then
inherit them from that one staged copy rather than each assembling their own.

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
    entry. prism ships a native prism.dll in prism/_native/, so
    --collect-binaries=prism is required. Since prismatoid 0.18 its bindings
    are also a compiled cffi extension in that folder, which needs an explicit
    --add-binary plus --hidden-import=_cffi_backend (prism_native_args()).
    Missing any of these, `import prism` fails and speech is silently dead.
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
import platform
import re
import shutil
import subprocess
import sys
import zipfile

# Drives PyInstaller's --name, so it IS the shipped filename: VRP.exe / VRP.app
# / the dist/VRP/ onedir folder. Uppercase because it is user-facing (the Dock,
# /Applications, a Start-menu target), and STABLE across releases on purpose —
# macOS keys "is this the same app?" off the bundle name, so a versioned name
# would install a second copy every release instead of replacing the first.
APP_NAME = "VRP"           # Versatile Radio Programmer short form
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


def prism_native_args() -> list:
    """PyInstaller args that make prism's compiled core loadable when frozen.

    Since prismatoid 0.18 the Python bindings are a compiled cffi extension
    (``prism/_native/_prism_cffi.pyd`` on Windows, ``...abi3.so`` elsewhere)
    rather than an ABI-mode ``dlopen`` from ``prism/lib.py``. Two things about
    it are invisible to PyInstaller's static analysis, and each one alone
    leaves a frozen build that crashes on ``import prism`` — which VRP survives
    by going silent, the worst possible failure for this app:

    * The extension lives in ``_native/``, which ``prism/_native.py`` appends to
      the package ``__path__`` at runtime. ``--collect-binaries`` skips Python
      extension modules and ``--hidden-import=prism._prism_cffi`` cannot find
      it, so it is shipped explicitly into the same ``prism/_native`` folder.
    * The extension imports ``_cffi_backend`` from C, so it is named as a
      hidden import.

    Verified 2026-11-16 by freezing a probe: without these, ``No module named
    'prism._prism_cffi'`` then ``'_cffi_backend'``; with them, 15 backends and
    NVDA acquired. Aborts the build if no compiled extension is found, rather
    than producing an app with no voice.
    """
    import importlib.machinery
    import importlib.util

    spec = importlib.util.find_spec("prism")
    if spec is None or not spec.submodule_search_locations:
        raise SystemExit("prism (prismatoid) is not installed; cannot build.")
    native_dir = os.path.join(list(spec.submodule_search_locations)[0], "_native")
    suffixes = tuple(importlib.machinery.EXTENSION_SUFFIXES)
    extensions = sorted(
        name for name in (os.listdir(native_dir) if os.path.isdir(native_dir) else [])
        if name.startswith("_prism_cffi") and name.endswith(suffixes)
    )
    if not extensions:
        raise SystemExit(
            f"No compiled prism extension (_prism_cffi*) in {native_dir}. A build "
            "without it has no speech; check the installed prismatoid version."
        )
    args = [
        "--add-binary=%s%sprism/_native" % (os.path.join(native_dir, name), os.pathsep)
        for name in extensions
    ]
    args.append("--hidden-import=_cffi_backend")
    return args


def build(onefile: bool) -> int:
    cmd = [
        sys.executable, "-m", "PyInstaller",

        "--name", APP_NAME,
        "--noconfirm",       # overwrite a previous dist/build without prompting
        "--clean",           # don't reuse a stale PyInstaller cache

        # ---- Output mode ----
        # onedir (default): a dist/VRP/ folder that launches with no extraction
        # step. onefile: a single self-extracting dist/VRP.exe (slower start).
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
        # prism loads a native prism.dll from prism/_native/ (see
        # prism/_native.py), which PyInstaller does not bundle on its own: it is
        # package *data*, not an import. Without this flag `import prism` fails
        # and the app runs silent — which on Windows means the Left/Right cell
        # cursor, whose only voice is prism, announces nothing.
        "--collect-binaries=prism",
        # ...and, since prismatoid 0.18, its compiled cffi extension plus the
        # _cffi_backend it imports from C — see prism_native_args(). Verified
        # frozen 2026-11-16 with 0.18.3: 15 backends, NVDA acquired.
        *prism_native_args(),
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
        # VRP's out-of-tree drivers are imported dynamically by
        # chirp_backend.extra_drivers.register_all() (importlib.import_module),
        # which PyInstaller's static analysis can't follow — collect explicitly
        # so the packaged exe ships them (e.g. the Wouxun KG-UV96M driver).
        "--collect-submodules=chirp_backend.extra_drivers",
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


HELP_DIRNAME = "help"


def stage_help(onefile: bool = False) -> int:
    """Copy the repo's help/ documents into the built app.

    The Help menu opens these in the user's browser (see vrp/help.py), so they
    must ship with EVERY build, not just the portable zip the way sample-images
    does. Staging them into dist/VRP/ means both downstream artifacts get them
    for free: the portable zip walks that folder, and installer.iss recurses
    dist\\vrp\\*.

    They are copied in rather than passed to PyInstaller's --add-data because in
    PyInstaller 6 datas land under _internal/. Help belongs beside the
    executable: vrp/help.py looks for it there, and a user who wants to read the
    guide without launching the app (or mail it to someone) should not have to
    go digging through the app's plumbing to find it.

    Re-copied from scratch on every build, so a doc deleted from the repo does
    not linger in dist/ and ship forever.
    """
    src = os.path.join(PROJECT_ROOT, HELP_DIRNAME)
    if not os.path.isdir(src):
        print(f"! No help documents at {src} - skipping them.")
        return 0

    if onefile:
        # onefile puts the exe straight in dist/, so help/ goes beside it there.
        dests = [os.path.join(PROJECT_ROOT, "dist", HELP_DIRNAME)]
    elif sys.platform == "darwin":
        # Inside a .app, sys.executable is VRP.app/Contents/MacOS/VRP, so
        # "beside the executable" is not a place a user can see. Contents/
        # Resources/ is the bundle convention and is what vrp/help.py's macOS
        # candidate looks for. The raw COLLECT folder gets a copy too, since
        # --portable ships the .app but the folder is still runnable.
        # NOT yet exercised on a Mac - see CLAUDE.md on the macOS build.
        dests = [
            os.path.join(PROJECT_ROOT, "dist", f"{APP_NAME}.app", "Contents",
                         "Resources", HELP_DIRNAME),
            os.path.join(PROJECT_ROOT, "dist", APP_NAME, HELP_DIRNAME),
        ]
    else:
        dests = [os.path.join(PROJECT_ROOT, "dist", APP_NAME, HELP_DIRNAME)]

    count = 0
    for dest in dests:
        parent = os.path.dirname(dest)
        if not os.path.isdir(parent):
            # e.g. dist/VRP.app absent because --windowed didn't run.
            print(f"! {parent} not found - skipping help/ there.")
            continue
        if os.path.isdir(dest):
            shutil.rmtree(dest)
        shutil.copytree(src, dest)
        count = sum(len(files) for _r, _d, files in os.walk(dest))
        print(f"  + {count} help documents in "
              f"{os.path.relpath(dest, os.path.join(PROJECT_ROOT, 'dist'))}")
    return 0


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


def artifact_suffix() -> str:
    """Platform/arch tag for the portable zip's filename.

    macOS builds are architecture-bound in a way the Windows one isn't (an
    arm64 build will not run on an Intel Mac), so the arch is part of the name
    - otherwise two Macs produce identically-named, incompatible artifacts.
    """
    if sys.platform == "darwin":
        return f"macos-{platform.machine()}"      # macos-arm64 / macos-x86_64
    if sys.platform.startswith("win"):
        return "win64"
    return f"{sys.platform}-{platform.machine()}"


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


def stage_samples(onefile: bool = False) -> int:
    """Copy CHIRP's test images into the built app, exactly as stage_help does.

    They used to be added straight into the portable zip, which meant the
    *installer* never carried them: a user who ran setup.exe got no way to try
    the app without a radio and a cable in hand. Staging them into the app
    folder instead gives every downstream artifact the same content from one
    source of truth - the portable zip walks dist/VRP/, installer.iss recurses
    dist\\VRP\\*, and the macOS bundle carries its own copy.

    Placement mirrors stage_help for the same reason: TOP LEVEL, beside the
    executable, never under _internal/. A tester has to reach these from a
    File > Open Image File dialog, and the app's plumbing is not somewhere a
    user should be asked to go digging.

    macOS is the awkward case. Contents/Resources/ is where a bundle's data
    belongs and is the only copy that survives dragging VRP.app to
    /Applications - but a .app's interior is not browsable from an Open dialog
    without Show Package Contents. The portable zip therefore ALSO drops a copy
    beside the bundle (see _build_portable_macos), which is the one a Mac tester
    actually opens. Roughly 9 MB uncompressed, ~0.5 MB in the zip.

    They come from ./chirp at the enforced CHIRP_COMMIT pin, so they always
    match the drivers this build bundles. Re-copied from scratch every build, so
    images dropped by a CHIRP bump do not linger in dist/ and ship forever.
    """
    files = _sample_files()
    if not files:
        return 0

    if onefile:
        dests = [os.path.join(PROJECT_ROOT, "dist", SAMPLES_DIRNAME)]
    elif sys.platform == "darwin":
        dests = [
            os.path.join(PROJECT_ROOT, "dist", f"{APP_NAME}.app", "Contents",
                         "Resources", SAMPLES_DIRNAME),
            os.path.join(PROJECT_ROOT, "dist", APP_NAME, SAMPLES_DIRNAME),
        ]
    else:
        dests = [os.path.join(PROJECT_ROOT, "dist", APP_NAME, SAMPLES_DIRNAME)]

    for dest in dests:
        parent = os.path.dirname(dest)
        if not os.path.isdir(parent):
            # e.g. dist/VRP.app absent because --windowed didn't run.
            print(f"! {parent} not found - skipping {SAMPLES_DIRNAME}/ there.")
            continue
        if os.path.isdir(dest):
            shutil.rmtree(dest)
        os.makedirs(dest)
        for full in files:
            shutil.copy2(full, dest)
        with open(os.path.join(dest, "README.txt"), "w", encoding="utf-8") as fh:
            fh.write(_SAMPLES_README.format(chirp_pin=_chirp_pin_short()))
        print(f"  + {len(files)} sample images in "
              f"{os.path.relpath(dest, os.path.join(PROJECT_ROOT, 'dist'))}")
    return 0


def build_portable(version: str, include_samples: bool = True) -> int:
    """Zip the frozen app into dist/VRP-<version>-<platform>.zip.

    The no-install distribution: the tester unzips it and runs the app straight
    out of the folder.

    **The version lives on the zip, never on what comes out of it.** The single
    top-level directory is plain "VRP/", holding VRP.exe (Windows) or VRP.app
    (macOS). That asymmetry is the point: the *download* has to be tellable
    apart (two releases in ~/Downloads, and a browser silently renaming the
    second one "VRP (1).zip" helps nobody), but the *installed* thing has to
    keep one identity so upgrading replaces it. A versioned VRP-20260715.3.app
    dragged to /Applications sits beside VRP-20260714.1.app forever; a
    versioned folder leaves the user running whichever old build they happen to
    click.

    The cost, accepted deliberately: extracting a new release over an existing
    VRP/ folder MERGES rather than replaces, so files dropped between builds
    (a retired DLL, a removed help doc) survive in place. Delete the old folder
    first for a clean run — the Windows packer says so on stdout. macOS is
    unaffected: Finder replaces a .app bundle wholesale rather than merging it.

    help/ and sample-images/ are NOT added here. stage_help/stage_samples put
    them in the app folder before this runs, so the walk below picks them up the
    same way the installer does - one staging step, every artifact consistent.
    ``include_samples`` survives only for the macOS top-level copy; see
    _build_portable_macos.

    Windows and macOS need genuinely different packaging, not just a different
    filename - see _build_portable_macos.
    """
    top = RELEASE_PREFIX
    zip_path = os.path.join(
        PROJECT_ROOT, "dist",
        f"{RELEASE_PREFIX}-{version}-{artifact_suffix()}.zip",
    )
    if sys.platform == "darwin":
        return _build_portable_macos(top, zip_path, include_samples)
    return _build_portable_zipfile(top, zip_path, include_samples)


def _build_portable_zipfile(top: str, zip_path: str, include_samples: bool) -> int:
    """Windows/Linux: zip the dist/VRP/ onedir folder with zipfile.

    PyInstaller's onedir doesn't care what its folder is called, only that the
    executable and _internal/ stay together inside it - so re-rooting every
    entry under the top folder is safe here. It is NOT safe for a macOS .app;
    see _build_portable_macos.

    ``include_samples`` is unused: stage_samples already put the images in the
    onedir folder (or didn't, under --no-samples), and the walk below ships
    whatever is there. The parameter stays for signature parity with the macOS
    packer, which does still act on it.
    """
    onedir = os.path.join(PROJECT_ROOT, "dist", APP_NAME)
    if not os.path.isdir(onedir):
        print(f"Cannot build the portable zip: {onedir}{os.sep} not found.")
        print("Run the onedir build first (python build.py, no --onefile).")
        return 1

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

    size_mb = os.path.getsize(zip_path) / (1024 * 1024)
    print(f"Zipped {count} files ({size_mb:.1f} MB) under {top}{os.sep} "
          f"(app + help + samples)")
    print(f"Output: {os.path.relpath(zip_path, PROJECT_ROOT)}")
    print(
        f"\nNOTE: this unzips to a plain {top}{os.sep} folder, so a new release "
        f"lands on top\nof the old one. Windows MERGES an extract into an "
        f"existing folder rather than\nreplacing it, so files retired between "
        f"builds would linger. Tell upgraders to\ndelete the old "
        f"{top}{os.sep} first. Say so in the release notes."
    )
    return 0


def _build_portable_macos(top: str, zip_path: str, include_samples: bool) -> int:
    """macOS: stage VRP.app + sample-images, then zip them with ditto.

    Two things make this genuinely different from the Windows path:

    1. **The artifact is dist/VRP.app, not dist/VRP/.** With --windowed,
       PyInstaller emits BOTH: dist/VRP/ (the raw COLLECT folder) and
       dist/VRP.app (the bundle). Shipping the folder would hand a Mac user a
       bare unix binary instead of something they can double-click.

    2. **A .app must not be zipped with Python's zipfile.** zipfile follows
       symlinks instead of storing them (a bundle's Frameworks/ relies on them)
       and extractall() does not restore the executable bit - either one leaves
       a bundle that will not launch. `ditto -c -k --sequesterRsrc
       --keepParent` is the platform's own tool and preserves symlinks,
       permissions and resource forks. It is used for the staging copy too, for
       the same reason.

    Staging (build/portable/VRP/) exists so sample-images/ can sit BESIDE the
    .app inside the zip, matching the Windows layout; --keepParent then puts
    that folder at the zip root.

    That beside-the-app copy is deliberately a SECOND copy: stage_samples
    already put the images in the bundle's Contents/Resources/, which is what
    survives dragging VRP.app to /Applications, but a .app's interior is not
    browsable from a File > Open dialog without Show Package Contents. The
    outer copy is the one a tester actually opens. ~0.5 MB compressed for the
    pair, which is the right trade against telling a blind user to right-click
    into a bundle. (Windows needs no equivalent: the installer puts
    sample-images/ in the install directory, where it is a normal folder.)

    NOT YET RUN ON A MAC - written on Windows and unverified. Every failure
    mode here is loud (missing .app, missing ditto, non-zero ditto exit) rather
    than silent, so a broken run says so instead of shipping a dead bundle.
    """
    app = os.path.join(PROJECT_ROOT, "dist", f"{APP_NAME}.app")
    if not os.path.isdir(app):
        print(f"Cannot build the portable zip: {app} not found.")
        print("Run the onedir build first (python build.py, no --onefile);")
        print("PyInstaller only produces the .app with --windowed.")
        return 1
    if shutil.which("ditto") is None:
        print("Cannot build the portable zip: `ditto` not found on PATH.")
        print("It ships with macOS. A .app must not be zipped with zipfile -")
        print("symlinks and permissions are lost and the bundle won't launch.")
        return 1

    staging_root = os.path.join(PROJECT_ROOT, "build", "portable")
    staging = os.path.join(staging_root, top)
    shutil.rmtree(staging_root, ignore_errors=True)
    os.makedirs(staging, exist_ok=True)

    print("\nStaging the portable bundle...")
    # ditto, not copytree - same symlink/permission reasons as the zip step.
    rc = subprocess.run(["ditto", app, os.path.join(staging, f"{APP_NAME}.app")])
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
                shutil.copy2(full, samples_dir)  # plain data files
                samples += 1
            with open(os.path.join(samples_dir, "README.txt"), "w",
                      encoding="utf-8") as fh:
                fh.write(_SAMPLES_README.format(chirp_pin=_chirp_pin_short()))
            samples += 1

    print("Creating the portable zip with ditto...")
    if os.path.exists(zip_path):
        os.remove(zip_path)  # rebuilding the same release replaces it
    rc = subprocess.run([
        "ditto", "-c", "-k", "--sequesterRsrc", "--keepParent",
        staging, zip_path,
    ])
    if rc.returncode != 0:
        print(f"ditto failed to create the zip (exit {rc.returncode}).")
        return rc.returncode
    shutil.rmtree(staging_root, ignore_errors=True)

    size_mb = os.path.getsize(zip_path) / (1024 * 1024)
    print(f"Zipped {APP_NAME}.app ({size_mb:.1f} MB) under {top}/")
    if samples:
        print(f"  + {samples} files in {top}/{SAMPLES_DIRNAME}/")
    print(f"Output: {os.path.relpath(zip_path, PROJECT_ROOT)}")
    print(
        "\nNOTE: the .app is unsigned and unnotarized, so Gatekeeper refuses "
        "it\non first launch (more firmly than Windows SmartScreen does). "
        "Testers must\nright-click the app and choose Open, or run:\n"
        f"    xattr -dr com.apple.quarantine /path/to/{top}/{APP_NAME}.app\n"
        "Say so in the release notes."
    )
    return 0


_DMG_README = """\
Versatile Radio Programmer (VRP)
================================

To install: drag VRP onto the Applications folder in this window.

Then eject this disk image and launch VRP from Applications (or Spotlight).
Installing over an older VRP replaces it - the app is always named "VRP", never
VRP-<date>, so upgrades don't pile up.

First launch: VRP is not signed with an Apple Developer ID yet, so macOS refuses
to open it the ordinary way. RIGHT-CLICK (or Control-click) VRP in Applications,
choose Open, then confirm. You only do this once. If you prefer the Terminal:

    xattr -dr com.apple.quarantine /Applications/VRP.app

Sample radio images
-------------------

The sample-images folder here holds one saved memory image per radio CHIRP
supports, so you can try VRP with no radio and no cable: File > Open Image File,
then pick any .img.

A copy also travels inside the app, and Help > Sample Radio Images opens it in
Finder - so you do not need to keep this disk image to reach them.

Radio driver support provided by the CHIRP project - chirpmyradio.com.
"""


def build_dmg(version: str, include_samples: bool = True) -> int:
    """Wrap dist/VRP.app in a macOS disk image - the counterpart to --installer.

    A .dmg is what a Mac user expects an installer to be: mount it, drag the app
    onto the Applications alias sitting beside it, eject. That drag is the whole
    install, which is why the symlink matters - without it the user has to know
    to open a second Finder window and find /Applications themselves.

    Layout inside the volume:
        VRP.app
        Applications -> /Applications      (the drop target)
        sample-images/                     (also inside the .app; see below)
        README.txt                         (install + Gatekeeper instructions)

    sample-images/ is here as well as in the bundle because this is the one
    moment the user is looking at a real Finder window with the images in it.
    The in-bundle copy is what survives the install, reachable afterwards from
    Help > Sample Radio Images.

    UDZO (zlib-compressed, read-only) is the ordinary format for a distributed
    dmg; the volume is named for the release so a mounted image says which build
    it is, even though the app inside is deliberately unversioned.

    NOT YET RUN ON A MAC - hdiutil exists only there. Every failure mode is loud
    (missing .app, missing hdiutil, non-zero exit) rather than silent.
    """
    if sys.platform != "darwin":
        print("A .dmg can only be built on macOS (hdiutil is macOS-only).")
        return 1

    app = os.path.join(PROJECT_ROOT, "dist", f"{APP_NAME}.app")
    if not os.path.isdir(app):
        print(f"Cannot build the dmg: {app} not found.")
        print("Run the onedir build first (python build.py, no --onefile);")
        print("PyInstaller only produces the .app with --windowed.")
        return 1
    if shutil.which("hdiutil") is None:
        print("Cannot build the dmg: `hdiutil` not found on PATH.")
        print("It ships with macOS.")
        return 1

    volume = f"{RELEASE_PREFIX}-{version}"
    dmg_path = os.path.join(
        PROJECT_ROOT, "dist", f"{volume}-{artifact_suffix()}.dmg"
    )
    staging_root = os.path.join(PROJECT_ROOT, "build", "dmg")
    staging = os.path.join(staging_root, volume)
    shutil.rmtree(staging_root, ignore_errors=True)
    os.makedirs(staging, exist_ok=True)

    print("\nStaging the disk image...")
    # ditto, not copytree - a .app relies on symlinks and the executable bit,
    # and shutil follows/loses both. Same reason as the portable zip.
    rc = subprocess.run(["ditto", app, os.path.join(staging, f"{APP_NAME}.app")])
    if rc.returncode != 0:
        print(f"ditto failed to copy the .app (exit {rc.returncode}).")
        return rc.returncode

    # The drop target. A relative symlink would point inside the volume; this
    # must be the absolute /Applications on the user's machine.
    os.symlink("/Applications", os.path.join(staging, "Applications"))

    if include_samples:
        files = _sample_files()
        if files:
            samples_dir = os.path.join(staging, SAMPLES_DIRNAME)
            os.makedirs(samples_dir, exist_ok=True)
            for full in files:
                shutil.copy2(full, samples_dir)  # plain data files
            with open(os.path.join(samples_dir, "README.txt"), "w",
                      encoding="utf-8") as fh:
                fh.write(_SAMPLES_README.format(chirp_pin=_chirp_pin_short()))
            print(f"  + {len(files)} sample images")

    with open(os.path.join(staging, "README.txt"), "w", encoding="utf-8") as fh:
        fh.write(_DMG_README)

    print("Creating the disk image with hdiutil...")
    if os.path.exists(dmg_path):
        os.remove(dmg_path)  # rebuilding the same release replaces it
    cmd = [
        "hdiutil", "create",
        "-volname", volume,
        "-srcfolder", staging,
        "-ov",                 # overwrite an existing image
        "-format", "UDZO",     # compressed, read-only: the distribution format
        dmg_path,
    ]
    print("Command:", " ".join(cmd))
    rc = subprocess.run(cmd)
    if rc.returncode != 0:
        print(f"hdiutil failed (exit {rc.returncode}).")
        return rc.returncode
    shutil.rmtree(staging_root, ignore_errors=True)

    size_mb = os.path.getsize(dmg_path) / (1024 * 1024)
    print(f"Disk image built ({size_mb:.1f} MB), volume name {volume}")
    print(f"Output: {os.path.relpath(dmg_path, PROJECT_ROOT)}")
    print(
        "\nNOTE: the .app inside is unsigned and unnotarized, so Gatekeeper "
        "refuses it\non first launch. The README.txt in the image tells the "
        "user to right-click ->\nOpen. Say so in the release notes too."
    )
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
    """Compile installer.iss with Inno Setup, wrapping the dist/VRP/ folder."""
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
        help="Build a single self-extracting dist/VRP.exe (slower start) "
             "instead of the default dist/VRP/ folder.",
    )
    parser.add_argument(
        "--installer",
        action="store_true",
        help="After the onedir build, compile the Windows installer with Inno "
             "Setup (installer.iss). Incompatible with --onefile.",
    )
    parser.add_argument(
        "--dmg",
        action="store_true",
        help="After the onedir build, wrap dist/VRP.app in a macOS disk image "
             "(VRP.app + an /Applications symlink to drag it onto). The macOS "
             "counterpart to --installer; macOS-only, incompatible with "
             "--onefile.",
    )
    parser.add_argument(
        "--portable",
        action="store_true",
        help="After the onedir build, zip it as "
             "dist/VRP-<version>-<platform>.zip (unzipping to a plain VRP/ "
             "folder) — a no-install build to hand to testers. Incompatible "
             "with --onefile.",
    )
    parser.add_argument(
        "--no-samples",
        action="store_true",
        help="Omit the sample-images/ folder (CHIRP's test images) from the "
             "build entirely — the app folder, the portable zip AND the "
             "installer. They're included by default so anyone with no radio "
             "(or no cable to hand) can still open a real image.",
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
    if args.installer and not sys.platform.startswith("win"):
        parser.error(
            "--installer builds a Windows installer with Inno Setup and only "
            "works on Windows. On macOS use --portable, which produces a "
            "zipped .app."
        )
    if args.portable and args.onefile:
        parser.error(
            "--portable zips the onedir folder, so it can't be combined with "
            "--onefile. (A onefile build is already a single portable .exe.)"
        )
    if args.dmg and args.onefile:
        parser.error(
            "--dmg wraps the .app bundle, which only --windowed onedir "
            "produces, so it can't be combined with --onefile."
        )
    if args.dmg and sys.platform != "darwin":
        parser.error(
            "--dmg builds a macOS disk image with hdiutil and only works on "
            "macOS. On Windows use --installer, which produces a setup.exe."
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

    # Help docs and sample images ship with EVERY build, not just the portable
    # zip, so both run before the portable/installer steps that package dist/
    # up. Everything downstream then inherits them from one staged source.
    print("\nStaging the help documents...")
    stage_help(onefile=args.onefile)

    if args.no_samples:
        print("\nSkipping the sample images (--no-samples).")
    else:
        print("\nStaging the sample images...")
        stage_samples(onefile=args.onefile)

    suffix = ".exe" if os.name == "nt" else ""
    if args.onefile:
        print(f"Output: dist{os.sep}{APP_NAME}{suffix}")
    elif sys.platform == "darwin":
        # --windowed on macOS emits BOTH the raw folder and the .app bundle;
        # the .app is the one to ship (--portable zips it).
        print(f"Output: dist{os.sep}{APP_NAME}.app  "
              f"(and the raw folder dist{os.sep}{APP_NAME}{os.sep})")
    else:
        print(f"Output: dist{os.sep}{APP_NAME}{os.sep}{APP_NAME}{suffix}")

    if args.portable:
        rc = build_portable(version, include_samples=not args.no_samples)
        if rc != 0:
            print(f"\nPortable zip failed with exit code {rc}.")
            sys.exit(rc)
        print("\nPortable build ready.")

    if args.dmg:
        rc = build_dmg(version, include_samples=not args.no_samples)
        if rc != 0:
            print(f"\nDisk image failed with exit code {rc}.")
            sys.exit(rc)
        print("\nDisk image ready.")

    if args.installer:
        rc = build_installer(version)
        if rc != 0:
            print(f"\nInstaller build failed with exit code {rc}.")
            sys.exit(rc)
        print("\nInstaller built.")
        print(f"Output: dist{os.sep}{APP_NAME}-{version}-setup.exe")


if __name__ == "__main__":
    main()
