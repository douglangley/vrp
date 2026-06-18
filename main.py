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

    from vrp.app import run

    run()


if __name__ == "__main__":
    main()
