"""Versatile Radio Programmer (VRP) — application entry point.

VRP is an accessible front end to the CHIRP radio programming library. It is a
wxPython app that hosts semantic, screen-reader-friendly HTML in an
``AccessibleWebView`` (no web server, no browser). See ``vrp/app.py`` for the
window and ``CLAUDE.md`` for the project's accessibility rules.

Importing ``vrp`` first applies the CHIRP import-path fix (see
``vrp/_chirp_path.py``) before anything imports the vendored ``chirp`` package.
"""

import argparse
import logging
import os
import sys

import vrp  # noqa: F401  (import side effect: makes the vendored chirp importable)


def parse_mode(argv: list[str]) -> str:
    """Return 'native' if --native is present, else 'webview'."""
    return "native" if "--native" in argv else "webview"


# Opt-in local dev knob: point at an extracted WebView2 Fixed Version Runtime
# folder to bypass the system Evergreen runtime. Must be set before any
# wx.html2.WebView/AccessibleWebView is constructed. No-op unless set, so this
# changes nothing for anyone who hasn't opted in.
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
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    from vrp.app import run

    run()


if __name__ == "__main__":
    if parse_mode(sys.argv) == "native":
        from vrp.native.app import run

        debug = "--debug" in sys.argv
        run(debug=debug)
    else:
        main()
