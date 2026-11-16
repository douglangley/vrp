"""Two naming invariants, pulling in opposite directions on purpose.

**The zip carries the version.** A Mac build and a Windows build are different
artifacts and must not collide on the releases page. macOS additionally pins the
architecture: an arm64 build will not run on an Intel Mac, so two Macs must not
produce identically-named, incompatible zips.

**What comes OUT of the zip does not.** The extracted folder is plain VRP/ and
the bundle inside it plain VRP.app, so a new release replaces the installed one
instead of accumulating beside it — macOS identifies an app in /Applications by
its bundle name, so a versioned name would install a second copy every release
and leave the user able to launch a stale build. Guarding this is the whole
point of the tests below: it regressed once already, with the py2app path
emitting VRP-<version>-macos-<arch>.app.

These test the naming only. Whether the macOS *packaging* works (ditto, the .app
bundle) can only be established by running build.py on a Mac — see
_build_portable_macos.
"""

import importlib
import os
import pathlib
import re
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
    assert top == "VRP"
    assert zip_path.endswith("VRP-20260715.3-macos-arm64.zip")


@pytest.mark.parametrize(
    "plat, packer", [("darwin", "mac"), ("win32", "zipfile")]
)
def test_the_extracted_folder_never_carries_the_version(monkeypatch, plat, packer):
    """Unzipping release N+1 must land on release N, not beside it.

    The version belongs on the zip filename only. If it leaks into the top-level
    folder, every release unzips to its own VRP-<version>/ and an upgrader ends
    up with a pile of folders and no signal about which one to run.
    """
    monkeypatch.setattr(sys, "platform", plat)
    monkeypatch.setattr(build.platform, "machine", lambda: "arm64")
    called = _recorders(monkeypatch)

    assert build.build_portable("20260715.3") == 0
    top, zip_path = called[packer]
    assert top == "VRP"
    assert "20260715.3" not in top
    assert "20260715.3" in os.path.basename(zip_path)


def test_the_app_name_is_stable_and_uppercase():
    """APP_NAME is PyInstaller's --name, so it IS the shipped filename.

    Uppercase because it is user-facing (the Dock, /Applications, a Start-menu
    target), and free of the version so upgrades replace rather than accumulate.
    """
    assert build.APP_NAME == "VRP"


def test_py2app_names_the_bundle_without_the_version():
    """setup.py's py2app path must agree with build.py's PyInstaller path.

    Checked against the source text rather than by import: setup.py sys.exit()s
    on any non-macOS platform (and runs a py2app build as an import side
    effect), so it cannot be imported here. This is the exact regression that
    prompted the change — the py2app path built
    VRP-<version>-macos-<arch>.app, which /Applications treats as a brand-new
    app on every release.
    """
    source = (
        pathlib.Path(PROJECT_ROOT) / "setup.py"
    ).read_text(encoding="utf-8")
    match = re.search(r"^final_app\s*=\s*(.+)$", source, re.M)
    assert match, "setup.py no longer defines final_app"
    assignment = match.group(1)
    assert "RELEASE_PREFIX" in assignment
    assert "VERSION" not in assignment, (
        "the py2app bundle name must not carry the version — a versioned "
        "VRP-<version>.app installs a second app instead of replacing the first"
    )
    assert "artifact_suffix" not in assignment


def _fake_macos_dist(tmp_path, monkeypatch):
    """A darwin build tree with a dist/VRP.app and the platform tools stubbed.

    Everything build_dmg shells out to (ditto, hdiutil) is macOS-only, so the
    calls are recorded instead of run. That covers the layout and the command
    line; whether hdiutil likes them can only be learned on a Mac.
    """
    (tmp_path / "dist" / f"{build.APP_NAME}.app").mkdir(parents=True)
    images = tmp_path / "chirp" / "tests" / "images"
    images.mkdir(parents=True)
    (images / "Baofeng_UV-5R.img").write_bytes(b"\x00" * 16)

    monkeypatch.setattr(build, "PROJECT_ROOT", str(tmp_path))
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(build.platform, "machine", lambda: "arm64")
    monkeypatch.setattr(build.shutil, "which", lambda _name: "/usr/bin/stub")

    calls = []
    links = []

    class _Ok:
        returncode = 0

    def fake_run(cmd, *_a, **_kw):
        calls.append(cmd)
        if cmd[0] == "hdiutil":
            # hdiutil would create the image; the size report needs a real file.
            open(cmd[-1], "wb").write(b"\x00" * 1024)
        return _Ok()

    monkeypatch.setattr(build.subprocess, "run", fake_run)
    monkeypatch.setattr(build.os, "symlink", lambda t, l: links.append((t, l)))
    return calls, links


def test_the_dmg_offers_an_applications_symlink_to_drag_onto(tmp_path, monkeypatch):
    """The drag IS the install. Without the symlink beside the app, the user has
    to know to open a second Finder window and find /Applications themselves."""
    _calls, links = _fake_macos_dist(tmp_path, monkeypatch)

    assert build.build_dmg("20260715.3") == 0
    assert links, "no /Applications symlink was created in the volume"
    target, link = links[0]
    assert target == "/Applications"
    assert os.path.basename(link) == "Applications"


def test_the_dmg_is_named_and_volumed_for_the_release(tmp_path, monkeypatch):
    """Same split as the zip: the download carries the version, the app inside
    does not. A mounted volume should still say which build it is."""
    calls, _links = _fake_macos_dist(tmp_path, monkeypatch)

    assert build.build_dmg("20260715.3") == 0
    hdiutil = next(c for c in calls if c[0] == "hdiutil")
    assert hdiutil[-1].endswith("VRP-20260715.3-macos-arm64.dmg")
    assert hdiutil[hdiutil.index("-volname") + 1] == "VRP-20260715.3"
    assert hdiutil[hdiutil.index("-format") + 1] == "UDZO"


def test_the_dmg_copies_the_bundle_with_ditto_not_shutil(tmp_path, monkeypatch):
    """A .app relies on symlinks and the executable bit; shutil loses both and
    leaves a bundle that will not launch."""
    calls, _links = _fake_macos_dist(tmp_path, monkeypatch)

    assert build.build_dmg("20260715.3") == 0
    assert any(c[0] == "ditto" for c in calls)


def test_the_dmg_carries_install_and_gatekeeper_instructions(tmp_path, monkeypatch):
    """Unsigned and unnotarized, so the first launch fails in a way that looks
    like a broken download unless the image says otherwise."""
    _fake_macos_dist(tmp_path, monkeypatch)
    build.build_dmg("20260715.3")

    readme = build._DMG_README
    assert "drag VRP onto the Applications folder" in readme
    assert "quarantine" in readme
    assert "Help > Sample Radio Images" in readme
    assert "Radio driver support provided by the CHIRP project" in readme


def test_the_dmg_refuses_to_build_off_macos(tmp_path, monkeypatch):
    """hdiutil is macOS-only. Failing loudly beats emitting a corrupt file."""
    monkeypatch.setattr(build, "PROJECT_ROOT", str(tmp_path))
    monkeypatch.setattr(sys, "platform", "win32")
    assert build.build_dmg("20260715.3") == 1


def test_the_dmg_refuses_when_the_bundle_is_missing(tmp_path, monkeypatch):
    """--onefile and a plain COLLECT folder both leave no .app to wrap."""
    monkeypatch.setattr(build, "PROJECT_ROOT", str(tmp_path))
    monkeypatch.setattr(sys, "platform", "darwin")
    (tmp_path / "dist").mkdir()
    assert build.build_dmg("20260715.3") == 1


def test_windows_portable_routes_to_the_zipfile_path(monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    called = _recorders(monkeypatch)

    assert build.build_portable("20260715.3") == 0
    assert "mac" not in called
    top, zip_path = called["zipfile"]
    assert top == "VRP"
    assert zip_path.endswith("VRP-20260715.3-win64.zip")
