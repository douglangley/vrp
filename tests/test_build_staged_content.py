"""help/ and sample-images/ must reach EVERY artifact, not just the tester zip.

Two bugs prompted these:

- The Inno Setup installer shipped no sample images. They were added straight
  into the portable zip, so anyone who installed VRP the normal way had no means
  of opening a real image without a radio and a cable already in hand.
- The py2app bundle shipped no help documents at all. py2app's `packages` only
  copies importable trees, and help/ is a plain repo folder, so Help ▸ Getting
  Started opened nothing.

The fix in both cases is the same shape: stage the content into the built app
once, and let each packager inherit it from there. So these tests assert on the
staging step and on each packager's route to it, rather than on the packagers'
output — which would need PyInstaller, Inno Setup and a Mac to observe.
"""

import importlib
import os
import pathlib
import sys

import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

build = importlib.import_module("build")

REPO = pathlib.Path(PROJECT_ROOT)


@pytest.fixture
def fake_tree(tmp_path, monkeypatch):
    """A throwaway repo root: two sample images, one help doc, empty dist/."""
    images = tmp_path / "chirp" / "tests" / "images"
    images.mkdir(parents=True)
    (images / "Baofeng_UV-5R.img").write_bytes(b"\x00" * 16)
    (images / "Quansheng_UV-K5.img").write_bytes(b"\x00" * 16)

    help_dir = tmp_path / "help"
    help_dir.mkdir()
    (help_dir / "GettingStarted.html").write_text("<h1>hi</h1>", encoding="utf-8")

    monkeypatch.setattr(build, "PROJECT_ROOT", str(tmp_path))
    return tmp_path


def _onedir(root):
    d = root / "dist" / build.APP_NAME
    d.mkdir(parents=True)
    return d


def test_samples_land_beside_the_exe_not_in_internal(fake_tree, monkeypatch):
    """The installer recurses the app folder, so staging here is what puts the
    images in an installed copy. _internal/ would be the wrong place twice
    over: the installer would still ship them, but a user could never find
    them from a File > Open dialog."""
    monkeypatch.setattr(sys, "platform", "win32")
    onedir = _onedir(fake_tree)

    assert build.stage_samples() == 0

    staged = onedir / build.SAMPLES_DIRNAME
    assert staged.is_dir()
    assert (staged / "Baofeng_UV-5R.img").is_file()
    assert (staged / "README.txt").is_file()
    assert not (onedir / "_internal").exists()


def test_staged_samples_carry_the_chirp_pin_readme(fake_tree, monkeypatch):
    """The README names the CHIRP commit the images came from — they only match
    the bundled drivers because both come from the same pin."""
    monkeypatch.setattr(sys, "platform", "win32")
    onedir = _onedir(fake_tree)
    build.stage_samples()

    readme = (onedir / build.SAMPLES_DIRNAME / "README.txt").read_text(
        encoding="utf-8"
    )
    assert build._chirp_pin_short() in readme
    assert "chirpmyradio.com" in readme


def test_restaging_drops_images_retired_by_a_chirp_bump(fake_tree, monkeypatch):
    """Re-copied from scratch: a stale image in dist/ must not ship forever."""
    monkeypatch.setattr(sys, "platform", "win32")
    onedir = _onedir(fake_tree)
    staged = onedir / build.SAMPLES_DIRNAME
    staged.mkdir()
    (staged / "Retired_Model.img").write_bytes(b"\x00")

    build.stage_samples()

    assert not (staged / "Retired_Model.img").exists()
    assert (staged / "Baofeng_UV-5R.img").is_file()


def test_macos_stages_into_the_bundle_so_applications_keeps_them(
    fake_tree, monkeypatch
):
    """Contents/Resources/ is the only copy that survives dragging VRP.app to
    /Applications and throwing the download away."""
    monkeypatch.setattr(sys, "platform", "darwin")
    _onedir(fake_tree)
    resources = (
        fake_tree / "dist" / f"{build.APP_NAME}.app" / "Contents" / "Resources"
    )
    resources.mkdir(parents=True)

    assert build.stage_samples() == 0
    assert build.stage_help() == 0

    assert (resources / build.SAMPLES_DIRNAME / "Baofeng_UV-5R.img").is_file()
    assert (resources / build.HELP_DIRNAME / "GettingStarted.html").is_file()


def test_staging_survives_a_missing_source_tree(tmp_path, monkeypatch):
    """A CHIRP clone without tests/images must not crash the build."""
    monkeypatch.setattr(build, "PROJECT_ROOT", str(tmp_path))
    monkeypatch.setattr(sys, "platform", "win32")
    _onedir(tmp_path)

    assert build.stage_samples() == 0
    assert build.stage_help() == 0


def test_the_installer_inherits_both_folders_by_recursing_the_app_dir():
    """installer.iss has no rule of its own for help/ or sample-images/ — it
    recurses dist\\VRP\\*, which is why staging is the single source of truth.
    If that Source line ever narrows, both silently stop shipping."""
    iss = (REPO / "installer.iss").read_text(encoding="utf-8")
    assert 'Source: "dist\\VRP\\*"' in iss
    assert "recursesubdirs" in iss


def test_the_installer_offers_a_route_to_the_samples():
    """Installed, the images sit under Program Files. "Browse to the install
    directory" is a poor instruction for a screen reader user, so the Start
    menu gets an entry — guarded, since --no-samples omits the folder."""
    iss = (REPO / "installer.iss").read_text(encoding="utf-8")
    icon = next(
        line for line in iss.splitlines()
        if line.startswith("Name:") and "sample-images" in line
    )
    assert "Check: DirExists" in icon


def test_py2app_stages_help_and_samples_into_the_bundle():
    """The regression this file exists for. Checked against source text because
    setup.py sys.exit()s off macOS and runs a build as an import side effect."""
    source = (REPO / "setup.py").read_text(encoding="utf-8")
    assert "def stage_bundle_extras(" in source
    assert "stage_bundle_extras(final_app)" in source, (
        "the py2app build must stage the extras, not just define the function"
    )
    body = source.split("def stage_bundle_extras(")[1].split("\ndef ")[0]
    assert "HELP_DIRNAME" in body
    assert "SAMPLES_DIRNAME" in body
    assert '"Contents", "Resources"' in body


def test_both_macos_builds_agree_on_the_bundle_layout():
    """vrp/help.py finds help/ at exactly one path inside a bundle, so the
    PyInstaller and py2app builds have to put it in the same place."""
    helper = (REPO / "vrp" / "help.py").read_text(encoding="utf-8")
    assert '"Resources" / HELP_DIRNAME' in helper
    assert '"Contents",\n                         "Resources", HELP_DIRNAME' in (
        (REPO / "build.py").read_text(encoding="utf-8")
    )
    assert '"Contents", "Resources"' in (
        (REPO / "setup.py").read_text(encoding="utf-8")
    )
