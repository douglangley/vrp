"""Versatile Radio Programmer (VRP) — application entry point.

VRP is an accessible front end to the CHIRP radio programming library. It is a
wxPython app with a single, native UI (``vrp/native/``): a channel grid built on
``wx-accessible-grid``'s ``AccessibleGrid`` (a ``wx.dataview.DataViewListCtrl``)
plus a native ``wx.MenuBar``. The grid is a real native table on each OS (the
native list view on Windows, NSTableView on macOS), so **both NVDA and
VoiceOver** read its rows directly.

There used to be a second, webview-based UI; it was retired and removed once the
native grid read on every screen reader (see PROGRESS_LOG.md "2026-06-25" and
"2026-06-29 — Removed the retired webview UI"). There is no web server and no
browser anywhere in the app.

Importing ``vrp`` first applies the CHIRP import-path fix (see
``vrp/_chirp_path.py``) before anything imports the vendored ``chirp`` package.
"""

import argparse
import logging

import vrp  # noqa: F401  (import side effect: makes the vendored chirp importable)


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

    from vrp.native.app import run

    run(debug=args.debug)


if __name__ == "__main__":
    main()
