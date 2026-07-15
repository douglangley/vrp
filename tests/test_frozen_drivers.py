"""CHIRP's drivers register in a FROZEN build, where __all__ can't be globbed.

Regression guard for a bug that made every release build unusable: the frozen
app failed to open ANY radio image — "Unsupported model Baofeng UV-5R Mini".

chirp/drivers/__init__.py builds __all__ by globbing *.py off the filesystem. In
a frozen build the drivers live inside PyInstaller's PYZ archive, so the glob
finds nothing, __all__ is empty, and directory.import_drivers()'s frozen branch
iterates that empty list — registering zero drivers.

Testing this honestly is harder than it looks, and the easy versions are
worthless:

  - Emptying __all__ in-process proves nothing about registration: the registry
    is a process-wide global that earlier imports have already filled, so the
    assertions pass with the fix removed.
  - Emptying __all__ on a *source* run proves nothing either: import_drivers()
    only consults __all__ when `sys.platform == 'win32' and sys.frozen`;
    otherwise it globs and succeeds regardless.

So the end-to-end test runs in a SUBPROCESS with sys.frozen forced on and
__all__ emptied — the exact state a frozen build starts in — and carries its own
negative control, so it fails loudly if the setup ever stops reproducing the
bug. (The full real-world proof is a frozen console build:
tools/spike_frozen_drivers.py.)
"""

import os
import subprocess
import sys
import textwrap

import pytest

from chirp_backend import radio as radio_backend

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


_PRELUDE = """
    import sys
    import vrp                      # chirp import-path fix
    sys.frozen = True               # make import_drivers take its frozen branch
    import chirp.drivers
    chirp.drivers.__all__ = []      # what the frozen glob actually produces
    from chirp import directory
"""


def _run(body: str) -> str:
    """Run ``body`` in a fresh interpreter that looks frozen to CHIRP.

    Each block is dedented separately — dedent() strips only the prefix common
    to the whole string, so concatenating first would leave one block indented.
    """
    code = textwrap.dedent(_PRELUDE) + textwrap.dedent(body)
    proc = subprocess.run(
        [sys.executable, "-c", code],
        cwd=PROJECT_ROOT, capture_output=True, text=True, timeout=180,
    )
    assert proc.returncode == 0, (
        f"subprocess failed:\nstdout:{proc.stdout}\nstderr:{proc.stderr}"
    )
    return proc.stdout.strip().splitlines()[-1]


# -- the repair itself (runs in-process; catches the core defect) ----------


def test_repopulates_an_empty_driver_list(monkeypatch):
    """The frozen state: __all__ empty -> rebuild it rather than register none."""
    import chirp.drivers

    monkeypatch.setattr(chirp.drivers, "__all__", [], raising=False)
    count = radio_backend._ensure_driver_modules()
    assert count > 100, f"expected the full driver module set, got {count}"
    assert len(chirp.drivers.__all__) == count
    assert "uv5r" in chirp.drivers.__all__


def test_leaves_a_populated_driver_list_alone():
    """On a source run CHIRP's own glob works — don't second-guess it."""
    import chirp.drivers

    before = list(chirp.drivers.__all__)
    assert before, "source runs should have a glob-populated __all__"
    count = radio_backend._ensure_driver_modules()
    assert count == len(before)
    assert list(chirp.drivers.__all__) == before


# -- end-to-end, in a simulated frozen interpreter -------------------------


@pytest.mark.skipif(
    sys.platform != "win32",
    reason="import_drivers()'s frozen branch is win32-only; elsewhere it globs",
)
def test_negative_control_frozen_without_the_repair_registers_nothing():
    """Proves the simulation genuinely reproduces the bug. If this ever starts
    passing, the test below is no longer testing anything."""
    out = _run("""
        directory.import_drivers()
        print(len(directory.DRV_TO_RADIO))
    """)
    assert out == "0", (
        f"expected the frozen bug to register 0 drivers, got {out} — the "
        "simulation no longer reproduces it, so the guard below is void"
    )


@pytest.mark.skipif(
    sys.platform != "win32",
    reason="import_drivers()'s frozen branch is win32-only; elsewhere it globs",
)
def test_frozen_registers_drivers_with_the_repair():
    out = _run("""
        from chirp_backend import radio as rb
        rb._ensure_driver_modules()
        directory.import_drivers()
        print(len(directory.DRV_TO_RADIO))
    """)
    assert int(out) > 500, f"expected the full driver set, got {out}"


@pytest.mark.skipif(
    sys.platform != "win32",
    reason="import_drivers()'s frozen branch is win32-only; elsewhere it globs",
)
def test_frozen_can_open_the_image_that_failed_for_the_user():
    """The exact user-visible failure: "Unsupported model Baofeng UV-5R Mini"
    when opening a test image in the release build."""
    image = os.path.join(
        PROJECT_ROOT, "chirp", "tests", "images", "Baofeng_UV-5R_Mini.img"
    )
    out = _run(f"""
        from chirp_backend import radio as rb
        ok, message = rb.load_image(r"{image}")
        print("%s|%s" % (ok, message))
    """)
    assert out.startswith("True|"), f"load_image failed frozen: {out}"
    assert "Unsupported model" not in out
