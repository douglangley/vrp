"""Versatile Radio Programmer (VRP) — application entry point.

VRP is an accessible front end to the CHIRP radio programming library. It is a
wxPython app with two interchangeable front ends, because no single channel
grid reads on every screen reader (see PROGRESS_LOG.md and the memory note on
the cross-platform grid split):

* the **native** UI (``vrp/native/``) — a ``wx.dataview.DataViewListCtrl``
  channel grid plus a native menu bar. Its grid wraps a native control on each
  OS (SysListView32 on Windows, NSTableView on macOS), so **both NVDA and
  VoiceOver** read it. This is the default on every platform.
* the **webview** UI (``vrp/app.py``) — the ``AccessibleWebView`` rendering the
  ``wx-accessible-grid`` Excel-style channel grid. Kept available via
  ``--webview`` while the webview stack is retired.

The native UI is the default everywhere; force the webview explicitly with
``--webview`` (or the native UI with ``--native``).

Importing ``vrp`` first applies the CHIRP import-path fix (see
``vrp/_chirp_path.py``) before anything imports the vendored ``chirp`` package.
"""

import argparse
import logging
import os
import sys

import vrp  # noqa: F401  (import side effect: makes the vendored chirp importable)


def parse_mode(argv: list[str], platform: str | None = None) -> str:
    """Pick which front end to launch.

    An explicit ``--webview`` or ``--native`` flag always wins. Otherwise the
    default is the **native** UI on every platform: its
    ``wx.dataview.DataViewListCtrl`` channel grid wraps a native control on each
    OS (SysListView32 on Windows, NSTableView on macOS), so NVDA *and* VoiceOver
    both read it. The webview UI remains available with ``--webview``.
    ``platform`` is accepted for tests/overrides but no longer changes the
    default (it used to route macOS to the webview, before the grid migration).
    """
    if "--webview" in argv:
        return "webview"
    if "--native" in argv:
        return "native"
    return "native"


# Opt-in local dev knob: point at an extracted WebView2 Fixed Version Runtime
# folder to bypass the system Evergreen runtime. Must be set before any
# wx.html2.WebView/AccessibleWebView is constructed. No-op unless set, so this
# changes nothing for anyone who hasn't opted in. (Only matters for --webview.)
_runtime_dir = os.environ.get("VRP_WEBVIEW2_RUNTIME_DIR")
if _runtime_dir:
    os.environ.setdefault("WEBVIEW2_BROWSER_EXECUTABLE_FOLDER", _runtime_dir)


def main() -> None:
    parser = argparse.ArgumentParser(description="Versatile Radio Programmer")
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging.",
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--webview",
        action="store_true",
        help="Force the AccessibleWebView UI (the VoiceOver-friendly web grid).",
    )
    group.add_argument(
        "--native",
        action="store_true",
        help="Force the native wx.ListCtrl UI (the NVDA-friendly native grid).",
    )
    parser.add_argument(
        "file",
        nargs="?",
        help="Optional radio image (.img) to open on launch.",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    if parse_mode(sys.argv[1:]) == "webview":
        from vrp.app import run

        run(open_path=args.file)
    else:
        from vrp.native.app import run

        run(debug=args.debug)


if __name__ == "__main__":
    main()
