"""Experimental BeeWare Toga launcher for VRP.

The wxPython app remains the production launcher in ``main.py``. This module
exists so the native Toga prototype can be run without touching that path.
"""

import argparse
import logging

import vrp  # noqa: F401  (import side effect: makes vendored chirp importable)


def main() -> None:
    parser = argparse.ArgumentParser(description="Versatile Radio Programmer Toga prototype")
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

    from vrp_toga.app import main as toga_main

    toga_main()


if __name__ == "__main__":
    main()
