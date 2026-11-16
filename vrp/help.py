"""Locating and opening the shipped help documents.

The docs open in the user's own browser rather than an in-app view. That is a
deliberate accessibility choice, not a shortcut: a screen-reader user reading a
long structured document wants browse mode — H to jump by heading, T by table, K
by link, arrow keys to read line by line — and they already have that, tuned to
their taste, in the browser they use every day. An embedded wx.html2.WebView
would also mean requesting the Edge backend explicitly (wx's MSW default is
IE/Trident, whose screen-reader support is legacy), shipping WebView2Loader.dll,
and depending on the WebView2 runtime being installed on the tester's machine —
risking a silent fall back to IE, or a Help menu that does nothing. See
PROGRESS_LOG "2026-06-29 — Removed the retired webview UI" for the related
decision not to keep the old webview stack for docs.

Frozen, help/ sits BESIDE the executable (dist/VRP/help/), not inside
_internal/, for the same reason sample-images/ does: a user should be able to
find and open these files themselves without opening the app's plumbing.
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import webbrowser
from pathlib import Path

log = logging.getLogger(__name__)

HELP_DIRNAME = "help"
SAMPLES_DIRNAME = "sample-images"

# The shipped documents, by the name the Help menu knows them as.
GETTING_STARTED = "GettingStarted.html"
KEYBOARD_COMMANDS = "KeyboardCommands.html"


def help_dir() -> Path:
    """The directory holding the help documents.

    From source: the repo's help/ folder (this file is vrp/help.py, so the repo
    root is two parents up).

    Frozen: beside the executable — except on macOS, where the executable lives
    inside VRP.app/Contents/MacOS/ and "beside" it is somewhere no user can see,
    so build.py stages the docs into the bundle's Contents/Resources/ instead
    (the platform convention). Both are checked; the Windows/onedir location
    wins when present, and is what the caller reports when nothing is found.
    """
    if not getattr(sys, "frozen", False):
        return Path(__file__).resolve().parent.parent / HELP_DIRNAME

    exe_dir = Path(sys.executable).resolve().parent
    beside_exe = exe_dir / HELP_DIRNAME
    candidates = (
        beside_exe,
        exe_dir.parent / "Resources" / HELP_DIRNAME,  # macOS .app bundle
    )
    for candidate in candidates:
        if candidate.is_dir():
            return candidate
    return beside_exe


def help_path(name: str) -> Path:
    """The full path to one help document. May not exist; callers check."""
    return help_dir() / name


def samples_dir() -> Path:
    """The directory holding CHIRP's sample radio images.

    Frozen, this mirrors help_dir() exactly — beside the executable, or the
    bundle's Contents/Resources/ on macOS — because build.py's stage_samples and
    setup.py's stage_bundle_extras put both folders in the same two places.

    From source it is ./chirp/tests/images instead: there is no sample-images/
    in the repo, the staged copies are made from CHIRP's test images at build
    time. That is not a fallback for developers only — CLAUDE.md has testers
    running from source via run-win.bat/run-mac.sh, so this is the path most
    people who use the Help menu item will actually get.
    """
    if not getattr(sys, "frozen", False):
        root = Path(__file__).resolve().parent.parent
        return root / "chirp" / "tests" / "images"

    exe_dir = Path(sys.executable).resolve().parent
    beside_exe = exe_dir / SAMPLES_DIRNAME
    candidates = (
        beside_exe,
        exe_dir.parent / "Resources" / SAMPLES_DIRNAME,  # macOS .app bundle
    )
    for candidate in candidates:
        if candidate.is_dir():
            return candidate
    return beside_exe


def open_folder(path: Path) -> bool:
    """Show a folder in the platform's file manager.

    Not webbrowser.open: handed a directory it is inconsistent across platforms
    and can hand the user a browser's file listing instead of Explorer or
    Finder, which is a much worse place to be reading filenames with a screen
    reader. Each platform's own "open this the way a double-click would" tool
    does the right thing.

    Returns False when the folder is missing (a --no-samples build, or an unzip
    that dropped it) so the caller can say so rather than leave the user
    pressing a menu item that silently does nothing.
    """
    if not path.is_dir():
        log.error("Folder not found: %s", path)
        return False
    log.debug("Opening folder: %s", path)
    try:
        if sys.platform == "win32":
            os.startfile(path)  # noqa: S606 - Windows-only, no shell involved
        elif sys.platform == "darwin":
            subprocess.run(["open", str(path)], check=True)
        else:
            subprocess.run(["xdg-open", str(path)], check=True)
    except Exception:  # noqa: BLE001 - any failure is "it didn't open"
        log.exception("Could not open the folder: %s", path)
        return False
    return True


def open_samples() -> bool:
    """Show the sample radio images folder. False if it isn't there."""
    return open_folder(samples_dir())


def open_help(name: str) -> bool:
    """Open a help document in the user's default browser.

    Returns False when the file is missing (a broken build, or a portable unzip
    that dropped the folder) so the caller can announce the failure rather than
    leave the user pressing a menu item that silently does nothing.
    """
    path = help_path(name)
    if not path.is_file():
        log.error("Help document not found: %s", path)
        return False
    log.debug("Opening help document: %s", path)
    # as_uri() gives a proper file:// URL and percent-escapes spaces, which a
    # bare path does not — webbrowser is unreliable with unescaped Windows paths.
    webbrowser.open(path.as_uri())
    return True
