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

Frozen, help/ sits BESIDE the executable (dist/vrp/help/), not inside
_internal/, for the same reason sample-images/ does: a user should be able to
find and open these files themselves without opening the app's plumbing.
"""

from __future__ import annotations

import logging
import sys
import webbrowser
from pathlib import Path

log = logging.getLogger(__name__)

HELP_DIRNAME = "help"

# The shipped documents, by the name the Help menu knows them as.
GETTING_STARTED = "GettingStarted.html"
KEYBOARD_COMMANDS = "KeyboardCommands.html"


def help_dir() -> Path:
    """The directory holding the help documents.

    From source: the repo's help/ folder (this file is vrp/help.py, so the repo
    root is two parents up).

    Frozen: beside the executable — except on macOS, where the executable lives
    inside vrp.app/Contents/MacOS/ and "beside" it is somewhere no user can see,
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
