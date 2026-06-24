#!/usr/bin/env python
"""Dev helper: update the vendored CHIRP clone and verify it against VRP's tests.

CHIRP is vendored at ./chirp, pinned to a tested commit recorded in the
CHIRP_COMMIT file, and bundled into the VRP exe. End users never pull CHIRP or
rebuild — updates ship as new VRP releases (run.bat clones + checks out the
pinned commit for them).

This script implements the dev-side update loop: fetch the latest CHIRP, check
it out, run the VRP test suite against it, and — only if the tests pass — bump
the CHIRP_COMMIT pin to the new commit. On failure it rolls ./chirp back to the
currently-pinned commit. After a successful bump, commit CHIRP_COMMIT and
rebuild (uv run python build.py).

Run:  uv run python tools/update_chirp.py
"""

from __future__ import annotations

import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHIRP = os.path.join(ROOT, "chirp")
PIN_FILE = os.path.join(ROOT, "CHIRP_COMMIT")


def _git(*args) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", CHIRP, *args], capture_output=True, text=True)


def _head() -> str:
    return _git("rev-parse", "HEAD").stdout.strip()


def main() -> int:
    if not os.path.isdir(os.path.join(CHIRP, ".git")):
        print("No ./chirp git clone found. Run run.bat (or clone it) first.")
        return 1

    old = _head()
    print(f"Current CHIRP commit: {old[:12]}")

    print("Fetching the latest CHIRP...")
    if _git("fetch", "--depth=1", "origin", "HEAD").returncode != 0:
        print("git fetch failed (network issue?).")
        return 1
    if _git("checkout", "--detach", "--quiet", "FETCH_HEAD").returncode != 0:
        print("Could not check out the fetched commit.")
        return 1

    new = _head()
    if new == old:
        print("Already up to date.")
        return 0
    print(f"Updated CHIRP: {old[:12]} -> {new[:12]}")

    print("\nRunning VRP test suite against the new CHIRP...")
    rc = subprocess.run([sys.executable, "-m", "pytest", "-q"]).returncode
    if rc == 0:
        with open(PIN_FILE, "w", encoding="utf-8") as f:
            f.write(new + "\n")
        print(f"\nTests pass. Updated the pin (CHIRP_COMMIT -> {new[:12]}).")
        print("Commit CHIRP_COMMIT and rebuild: uv run python build.py")
    else:
        print(f"\nTests FAILED against CHIRP {new[:12]}. Rolling ./chirp back to "
              f"the pinned commit {old[:12]}...")
        _git("checkout", "--detach", "--quiet", old)
        print("Rolled back. The pin is unchanged.")
    return rc


if __name__ == "__main__":
    sys.exit(main())
