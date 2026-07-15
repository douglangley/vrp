"""The portable zip is named for the platform (and arch) it was built on.

A Mac build and a Windows build are different artifacts and must not collide on
the releases page. macOS additionally pins the architecture: an arm64 build will
not run on an Intel Mac, so two Macs must not produce identically-named,
incompatible zips.

These test the naming only. Whether the macOS *packaging* works (ditto, the .app
bundle) can only be established by running build.py on a Mac — see
_build_portable_macos.
"""

import importlib
import os
import sys

import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

build = importlib.import_module("build")


def test_windows_artifact_is_win64(monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    assert build.artifact_suffix() == "win64"


def test_macos_artifact_carries_the_arch(monkeypatch):
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(build.platform, "machine", lambda: "arm64")
    assert build.artifact_suffix() == "macos-arm64"

    monkeypatch.setattr(build.platform, "machine", lambda: "x86_64")
    assert build.artifact_suffix() == "macos-x86_64"


def test_mac_and_windows_artifacts_never_collide(monkeypatch):
    """The bug this prevents: a Mac build emitting VRP-<version>-win64.zip."""
    monkeypatch.setattr(sys, "platform", "win32")
    win = build.artifact_suffix()
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(build.platform, "machine", lambda: "arm64")
    mac = build.artifact_suffix()
    assert win != mac
    assert "win" not in mac


@pytest.mark.parametrize("machine", ["arm64", "x86_64"])
def test_macos_suffix_never_claims_windows(monkeypatch, machine):
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(build.platform, "machine", lambda: machine)
    assert build.artifact_suffix().startswith("macos-")


def _recorders(monkeypatch):
    """Replace both packers with recorders; return the call log."""
    called = {}

    def fake_mac(top, zip_path, include_samples):
        called["mac"] = (top, zip_path)
        return 0

    def fake_zipfile(top, zip_path, include_samples):
        called["zipfile"] = (top, zip_path)
        return 0

    monkeypatch.setattr(build, "_build_portable_macos", fake_mac)
    monkeypatch.setattr(build, "_build_portable_zipfile", fake_zipfile)
    return called


def test_macos_portable_routes_to_the_ditto_path(monkeypatch):
    """build_portable must not hand a .app to the zipfile packer — zipfile drops
    symlinks and the executable bit, leaving a bundle that won't launch."""
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(build.platform, "machine", lambda: "arm64")
    called = _recorders(monkeypatch)

    assert build.build_portable("20260715.3") == 0
    assert "zipfile" not in called, "a .app must not be packed with zipfile"
    top, zip_path = called["mac"]
    assert top == "VRP-20260715.3"
    assert zip_path.endswith("VRP-20260715.3-macos-arm64.zip")


def test_windows_portable_routes_to_the_zipfile_path(monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    called = _recorders(monkeypatch)

    assert build.build_portable("20260715.3") == 0
    assert "mac" not in called
    top, zip_path = called["zipfile"]
    assert top == "VRP-20260715.3"
    assert zip_path.endswith("VRP-20260715.3-win64.zip")
