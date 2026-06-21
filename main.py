"""Versatile Radio Programmer (VRP) — application entry point.

VRP is an accessible front end to the CHIRP radio programming library. It is a
wxPython app. The default UI is the **native** wx interface (a virtual
report-mode ``wx.ListCtrl`` channel grid plus a native menu bar — see
``vrp/native/``), which NVDA on Windows and VoiceOver on macOS read directly.
The legacy ``AccessibleWebView`` UI (``vrp/app.py``) is still launchable with
``--webview`` while it is being retired.

Importing ``vrp`` first applies the CHIRP import-path fix (see
``vrp/_chirp_path.py``) before anything imports the vendored ``chirp`` package.
"""

import argparse
import logging
import os

import vrp  # noqa: F401  (import side effect: makes the vendored chirp importable)


def parse_mode(argv: list[str]) -> str:
    """Return 'webview' if --webview is present, else 'native' (the default)."""
    return "webview" if "--webview" in argv else "native"


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
    parser.add_argument(
        "--webview",
        action="store_true",
        help="Launch the legacy AccessibleWebView UI instead of the native one.",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    if args.webview:
        from vrp.app import run

        run()
    else:
        from vrp.native.app import run

        run(debug=args.debug)


if __name__ == "__main__":
    main()
