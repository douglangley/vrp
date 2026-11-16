"""Help > Sample Radio Images, and the folder it points at.

Every build ships CHIRP's test images, but until this command existed nothing in
the app said where they were. On Windows the installer adds a Start-menu
shortcut; a macOS .app has no equivalent, and after an /Applications install the
images sit inside the bundle where the only route is Show Package Contents. This
command is that route on both platforms, so the locator has to resolve correctly
in three quite different layouts: running from source, a Windows onedir build,
and a macOS bundle.

No wx import here — the menu wiring is checked against main_window.py's source,
the same approach test_help_keyboard_parity.py takes, so these run headless.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

from vrp import help as vrp_help

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MAIN_WINDOW = PROJECT_ROOT / "vrp" / "native" / "main_window.py"


def test_from_source_the_folder_is_chirps_test_images():
    """There is no sample-images/ in the repo — the staged copies are made from
    CHIRP's test images at build time. Testers run from source (run-win.bat),
    so this is the path most users of this command actually get."""
    assert not getattr(sys, "frozen", False), "test assumes an unfrozen run"
    resolved = vrp_help.samples_dir()

    assert resolved == PROJECT_ROOT / "chirp" / "tests" / "images"
    assert resolved.is_dir(), "the CHIRP clone should provide tests/images"
    assert any(resolved.glob("*.img"))


def test_frozen_windows_looks_beside_the_executable(tmp_path, monkeypatch):
    """Staged beside VRP.exe, never under _internal/ — a user has to be able to
    reach these from a File > Open dialog."""
    exe_dir = tmp_path / "VRP"
    (exe_dir / vrp_help.SAMPLES_DIRNAME).mkdir(parents=True)
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(exe_dir / "VRP.exe"))

    assert vrp_help.samples_dir() == exe_dir / vrp_help.SAMPLES_DIRNAME


def test_frozen_macos_falls_through_to_the_bundle_resources(tmp_path, monkeypatch):
    """Inside a .app the executable is at Contents/MacOS/VRP, so "beside it" is
    somewhere no user can see; the staged copy is in Contents/Resources/."""
    contents = tmp_path / "VRP.app" / "Contents"
    (contents / "MacOS").mkdir(parents=True)
    (contents / "Resources" / vrp_help.SAMPLES_DIRNAME).mkdir(parents=True)
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(contents / "MacOS" / "VRP"))

    assert vrp_help.samples_dir() == (
        contents / "Resources" / vrp_help.SAMPLES_DIRNAME
    )


def test_the_locator_mirrors_help_dir(tmp_path, monkeypatch):
    """Both folders are staged into the same two places by build.py and
    setup.py, so they must resolve the same way or one of them is wrong."""
    exe_dir = tmp_path / "VRP"
    (exe_dir / vrp_help.SAMPLES_DIRNAME).mkdir(parents=True)
    (exe_dir / vrp_help.HELP_DIRNAME).mkdir(parents=True)
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(exe_dir / "VRP.exe"))

    assert vrp_help.samples_dir().parent == vrp_help.help_dir().parent


def test_a_missing_folder_reports_failure_rather_than_opening_nothing(tmp_path):
    """--no-samples builds exist, and an unzip can drop the folder. The caller
    announces the failure; it must not silently appear to work."""
    assert vrp_help.open_folder(tmp_path / "not-here") is False


def test_open_folder_uses_the_platform_file_manager(tmp_path, monkeypatch):
    """Not webbrowser.open: handed a directory it can hand the user a browser's
    file listing instead of Explorer/Finder, which is a far worse place to be
    reading filenames with a screen reader."""
    calls = []
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(
        vrp_help.subprocess, "run", lambda cmd, **kw: calls.append(cmd) or None
    )

    assert vrp_help.open_folder(tmp_path) is True
    assert calls == [["open", str(tmp_path)]]


def test_open_folder_survives_a_failing_file_manager(tmp_path, monkeypatch):
    def boom(*_a, **_kw):
        raise OSError("no file manager")

    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(vrp_help.subprocess, "run", boom)

    assert vrp_help.open_folder(tmp_path) is False


wx = pytest.importorskip("wx")


@pytest.fixture
def app():
    try:
        instance = wx.App()
    except Exception:  # noqa: BLE001 - headless CI
        pytest.skip("no GUI/display available")
    yield instance
    instance.Destroy()


@pytest.fixture
def win(app):
    from vrp.native.main_window import MainWindow

    window = MainWindow()
    try:
        yield window
    finally:
        window.Destroy()


def test_the_menu_item_is_built_and_bound(win):
    """The real menu, not the source text: a bad label or a handler typo shows
    up here rather than at runtime in front of a user."""
    item = win._menu_items["sample_images"]
    assert "Sample" in item.GetItemLabelText()
    assert item.IsEnabled(), "must work with no radio loaded — that is the point"


def test_the_command_needs_no_radio(win):
    """Someone with no radio is exactly who needs the sample images, so this
    must never join the radio-gated commands."""
    assert "sample_images" not in win._radio_gated_keys


def test_invoking_it_announces_success(win, monkeypatch):
    monkeypatch.setattr(vrp_help, "open_samples", lambda: True)
    spoken = []
    monkeypatch.setattr(
        win.announce, "announce",
        lambda msg, **kw: spoken.append((msg, kw)),
    )

    win.on_sample_images()

    assert len(spoken) == 1
    message, kwargs = spoken[0]
    assert "sample radio images" in message.lower()
    # It tells the user what to do next; the folder alone is not the goal.
    assert "Open Image File" in message
    assert not kwargs.get("assertive")


def test_a_missing_folder_is_an_assertive_error_naming_the_path(win, monkeypatch):
    """--no-samples builds exist. The error interrupts, and says where it looked
    so the user can go and find it."""
    monkeypatch.setattr(vrp_help, "open_samples", lambda: False)
    spoken = []
    monkeypatch.setattr(
        win.announce, "announce",
        lambda msg, **kw: spoken.append((msg, kw)),
    )

    win.on_sample_images()

    assert len(spoken) == 1
    message, kwargs = spoken[0]
    assert kwargs.get("assertive") is True
    assert str(vrp_help.samples_dir()) in message


def _help_menu_source() -> str:
    src = MAIN_WINDOW.read_text(encoding="utf-8")
    return src.split("def _build_help_menu(")[1].split("\n    def ")[0]


def test_the_command_is_in_the_help_menu():
    menu = _help_menu_source()
    assert '"sample_images"' in menu
    assert "self.on_sample_images" in menu


def test_the_menu_mnemonics_stay_distinct():
    """wx gives a repeated mnemonic to whichever item it hits first, so a
    collision silently makes one item unreachable by keyboard."""
    mnemonics = re.findall(r'"[^"]*?&(\w)[^"]*?"', _help_menu_source())
    assert mnemonics, "no mnemonics parsed out of the Help menu"
    assert len(mnemonics) == len(set(mnemonics)), (
        f"duplicate Help menu mnemonics: {mnemonics}"
    )


def test_the_handler_announces_both_outcomes():
    """a11y rule 3: the file manager takes focus, so the announcement is what
    tells a screen reader user the keypress did anything — and a missing folder
    is an error, so it interrupts."""
    src = MAIN_WINDOW.read_text(encoding="utf-8")
    handler = src.split("def on_sample_images(")[1].split("\n    def ")[0]
    assert handler.count("self.announce.announce(") == 2
    assert "assertive=True" in handler


def test_the_command_claims_no_keyboard_shortcut():
    """It has no accelerator, so it must stay out of APP_SHORTCUTS — an entry
    there with no matching key would break the F1 list and the parity test."""
    src = MAIN_WINDOW.read_text(encoding="utf-8")
    block = re.search(r"APP_SHORTCUTS = \[(.*?)\n\]", src, re.S)
    assert block
    assert "Sample" not in block.group(1)
    menu = _help_menu_source()
    sample_line = next(
        line for line in menu.splitlines() if '"sample_images"' in line
    )
    assert "\\t" not in sample_line, "unexpected accelerator on the menu item"
