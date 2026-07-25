"""The speak_messages preference is actually WIRED to the Announcer.

Regression guard for a real bug: the pref existed, was shown in Preferences, and
was read/written to the config — but MainWindow built its Announcer with speech
unconditionally on, so the checkbox did nothing. The Announcer's own unit tests
(test_announce.py) all passed the whole time, because the defect was in the
wiring, not the Announcer. These tests drive MainWindow itself.

They also pin the two decisions that make the pref safe:
  - default ON (a silent default would hide every announcement), and
  - the grid cell cursor speaks regardless (it has no other voice).

Skips automatically when no GUI is available.
"""

import pytest

wx = pytest.importorskip("wx")


@pytest.fixture
def app():
    try:
        a = wx.App()
    except Exception:  # noqa: BLE001 — headless CI
        pytest.skip("no GUI/display available")
    yield a
    a.Destroy()


def _window():
    from vrp.native.main_window import MainWindow

    return MainWindow()


def test_announcer_defaults_to_speaking(app):
    """A fresh config (no speak_messages key) must come up speaking."""
    w = _window()
    try:
        assert w.announce.speech_enabled is True
    finally:
        w.Destroy()


def test_announcer_honours_the_pref_when_off(app):
    """The wiring that was missing: config OFF -> Announcer built with speech off."""
    from vrp.config import get_config

    get_config().set("speak_messages", False)
    w = _window()
    try:
        assert w.announce.speech_enabled is False
    finally:
        w.Destroy()


def test_announcer_honours_the_pref_when_on(app):
    from vrp.config import get_config

    get_config().set("speak_messages", True)
    w = _window()
    try:
        assert w.announce.speech_enabled is True
    finally:
        w.Destroy()


def test_abandoned_key_cannot_silence_the_app(app):
    """An existing config carrying only the dead speak_status_messages=False
    must still speak — those stored values record no user choice, and honouring
    them would have silenced every existing user."""
    from vrp.config import get_config

    get_config().set("speak_status_messages", False)
    w = _window()
    try:
        assert w.announce.speech_enabled is True
    finally:
        w.Destroy()


def test_disabling_speech_does_not_silence_the_cell_cursor(app):
    """With announcements off, an ordinary announce() is silent but the grid's
    cell-cursor callback still speaks — otherwise Left/Right would announce
    nothing at all, which is exactly what the pref must never cause."""
    from vrp.config import get_config

    get_config().set("speak_messages", False)
    w = _window()
    try:
        spoken = []
        # Intercept at the Announcer's speech callable, below the gate, so this
        # observes what would actually reach prism.
        w.announce._speak = lambda m, interrupt=False: spoken.append(m)

        w.announce.announce("Moved 3 channels up")
        assert spoken == [], "announcements should be silent when the pref is off"

        # _announce_cell is what ChannelGrid calls on Left/Right.
        w._announce_cell("146.5200, Frequency")
        assert spoken == ["146.5200, Frequency"], (
            "the cell cursor must speak even with announcements turned off"
        )
    finally:
        w.Destroy()


def test_cell_cursor_is_wired_to_the_grid_on_windows_and_mac(app):
    """The platforms where the cell cursor is wired must actually get it —
    otherwise _announce_cell is never called and the test above proves nothing."""
    import sys

    w = _window()
    try:
        expected = sys.platform in ("win32", "darwin")
        assert w.grid.has_cell_cursor is expected
    finally:
        w.Destroy()
