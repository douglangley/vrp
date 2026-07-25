"""tools/release_version.py — date-based release versioning for VRP.

VRP releases are named for the day they were cut, not for a semantic version:

    VRP-20260715.1      the first release cut on 15 July 2026
    VRP-20260715.2      a second release the same day
    VRP-20260716.1      the next day's first release

The version string itself is ``YYYYMMDD.N`` (``20260715.1``); ``VRP-`` is the
prefix used for git tags and release artifacts. ``N`` starts at 1 each day and
increments for every further release that day. It is never zero-padded, so the
version stays a valid PEP 440 release segment and both PEP 440 and plain
integer comparison order releases correctly (``20260715.10`` > ``20260715.9``).

Why dates: VRP has no compatibility contract to communicate — testers just want
the newest build. A date says "how fresh is this" at a glance, which a semantic
version does not.

Usage:
  python tools/release_version.py --show      Print the current version.
  python tools/release_version.py --bump      Set the version for a release cut
                                              today (today.1, or today.N+1 if
                                              today already has releases) and
                                              write it to both version files.
  python tools/release_version.py --set V     Set an explicit version.
  python tools/release_version.py --check     Verify the two version files agree
                                              (exit 1 if they don't).

The version is written to BOTH files that carry it, which must always agree:
  - vrp/__init__.py   __version__ — what the app and build.py read
  - pyproject.toml    version     — package metadata for uv

Cutting a release:
  uv run python tools/release_version.py --bump
  uv run python -m pytest
  uv run python build.py --portable          (or --installer)
  git commit -am "chore(release): VRP-<version>" && git tag VRP-<version>
"""

from __future__ import annotations

import argparse
import datetime
import os
import re
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INIT_PY = os.path.join(PROJECT_ROOT, "vrp", "__init__.py")
PYPROJECT = os.path.join(PROJECT_ROOT, "pyproject.toml")

TAG_PREFIX = "VRP-"

# YYYYMMDD.N — N is 1-based and never zero-padded.
_VERSION_RE = re.compile(r"^(\d{8})\.([1-9]\d*)$")

# Anchored to their own file's syntax so neither pattern can match the other's
# incidental text (e.g. a dependency's version constraint in pyproject.toml).
_INIT_RE = re.compile(r'^(__version__\s*=\s*")([^"]+)(")', re.M)
_PYPROJECT_RE = re.compile(r'^(version\s*=\s*")([^"]+)(")', re.M)


def parse_version(version: str) -> tuple[str, int] | None:
    """Split a date-based version into ``(YYYYMMDD, N)``, or None if it isn't one.

    Returns None for anything that doesn't match the scheme — including a
    date-shaped string that isn't a real calendar date (``20261332.1``) — so
    callers can fall back rather than trusting a bogus stamp.
    """
    match = _VERSION_RE.match(version.strip())
    if not match:
        return None
    stamp, build = match.groups()
    try:
        datetime.datetime.strptime(stamp, "%Y%m%d")
    except ValueError:
        return None
    return stamp, int(build)


def next_version(current: str, today: datetime.date | None = None) -> str:
    """The version for a release cut today, given the ``current`` version.

    Same day as ``current`` -> increment the build number; any other day (or a
    current version that isn't date-based at all, e.g. the old ``0.1.0``) ->
    start today at ``.1``.
    """
    today = today or datetime.date.today()
    stamp = today.strftime("%Y%m%d")
    parsed = parse_version(current)
    if parsed and parsed[0] == stamp:
        return f"{stamp}.{parsed[1] + 1}"
    return f"{stamp}.1"


def tag_for(version: str) -> str:
    """The git tag / artifact name for a version (``VRP-20260715.1``)."""
    return f"{TAG_PREFIX}{version}"


def _read(path: str, pattern: re.Pattern) -> str:
    with open(path, encoding="utf-8") as fh:
        match = pattern.search(fh.read())
    if not match:
        raise RuntimeError(f"Could not find a version to read in {path}")
    return match.group(2)


def _write(path: str, pattern: re.Pattern, version: str) -> None:
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    new_text, count = pattern.subn(rf"\g<1>{version}\g<3>", text, count=1)
    if count != 1:
        raise RuntimeError(f"Could not find a version to write in {path}")
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(new_text)


def read_version() -> str:
    """The current version from vrp/__init__.py (the source of truth)."""
    return _read(INIT_PY, _INIT_RE)


def read_pyproject_version() -> str:
    return _read(PYPROJECT, _PYPROJECT_RE)


def write_version(version: str) -> None:
    """Write ``version`` to both files that carry it."""
    _write(INIT_PY, _INIT_RE, version)
    _write(PYPROJECT, _PYPROJECT_RE, version)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Date-based release versioning for VRP (VRP-YYYYMMDD.N)"
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--show", action="store_true",
                       help="Print the current version and exit.")
    group.add_argument("--bump", action="store_true",
                       help="Set the version for a release cut today.")
    group.add_argument("--set", dest="explicit", metavar="VERSION",
                       help="Set an explicit version (must be YYYYMMDD.N).")
    group.add_argument("--check", action="store_true",
                       help="Verify the two version files agree.")
    args = parser.parse_args()

    current = read_version()

    if args.show:
        print(f"{tag_for(current)}   (version {current})")
        return

    if args.check:
        other = read_pyproject_version()
        if current != other:
            print(f"! Version mismatch: vrp/__init__.py has {current}, "
                  f"pyproject.toml has {other}.")
            print("  Fix with:  python tools/release_version.py --set <version>")
            sys.exit(1)
        print(f"Both version files agree: {current} (OK).")
        return

    version = args.explicit or next_version(current)
    if args.explicit and not parse_version(version):
        parser.error(
            f"'{version}' is not a valid date-based version (expected YYYYMMDD.N, "
            "e.g. 20260715.1)."
        )
    write_version(version)
    print(f"{current}  ->  {version}")
    print(f"Release: {tag_for(version)}")
    print("\nNext:")
    print("  uv run python -m pytest")
    print("  uv run python build.py --portable")
    print(f'  git commit -am "chore(release): {tag_for(version)}" && '
          f"git tag {tag_for(version)}")


if __name__ == "__main__":
    main()
