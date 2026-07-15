"""Versatile Radio Programmer (VRP) application package.

The wxPython UI layer that hosts CHIRP's functionality accessibly. The CHIRP
library itself is wrapped by the sibling ``chirp_backend`` package; everything
under ``vrp`` is the accessible front end (the native ``vrp/native`` app window
and grid, the shared native wx dialogs, and speech).

The first import below reorders the import machinery so the vendored, editable
``chirp`` package resolves correctly before anything tries to import it. Keep
it first.
"""

from vrp import _chirp_path as _chirp_path  # noqa: F401  (side effect: path fix)

import datetime as _datetime
import re as _re

__all__ = ["__version__", "describe_version"]

# Date-based release version: YYYYMMDD.N — see tools/release_version.py, which
# is what sets this (and the matching pyproject.toml version). Released as
# VRP-<version>; N starts at 1 each day.
__version__ = "20260715.3"

_DATE_VERSION_RE = _re.compile(r"(\d{4})(\d{2})(\d{2})\.(\d+)")


def describe_version(version: str | None = None) -> str:
    """A speakable rendering of a date-based version, e.g. "Release 1 of 15 July
    2026" for ``20260715.1``.

    A screen reader reads the raw version as one huge number ("twenty million,
    two hundred sixty thousand..."), which tells the user nothing. The About box
    shows this alongside the exact string so the release is *audible*, not just
    visible. Anything that isn't a date-based version (a local dev build) is
    returned unchanged.
    """
    version = version or __version__
    match = _DATE_VERSION_RE.fullmatch(version.strip())
    if not match:
        return version
    year, month, day, build = match.groups()
    try:
        stamp = _datetime.date(int(year), int(month), int(day))
    except ValueError:  # date-shaped but not a real date
        return version
    # %d zero-pads ("05 July"); strip it so the day reads naturally.
    return f"Release {int(build)} of {stamp.strftime('%d %B %Y').lstrip('0')}"
