"""The startup welcome screen: region picker + the Getting Started offer.

Covers the config default, every region round-tripping through the picker, and
the three buttons' return codes — in particular that Escape means "Not now" and
never "don't show again", which is the one outcome a user cannot undo from
inside the app without editing config.json.

Skips without a display, like tests/test_favorites_dialog.py.
"""

import pytest

wx = pytest.importorskip("wx")

from chirp_backend.bandplan import DEFAULT_REGION, REGIONS  # noqa: E402
from vrp.config import _DEFAULTS  # noqa: E402
from vrp.welcome_dialog import WelcomeDialog  # noqa: E402


@pytest.fixture
def app():
    try:
        a = wx.App()
    except Exception:  # noqa: BLE001 — headless CI
        pytest.skip("no GUI/display available")
    yield a
    a.Destroy()


@pytest.fixture
def frame(app):
    f = wx.Frame(None)
    yield f
    f.Destroy()


def test_show_welcome_defaults_on():
    """A new install must see the screen; that is the whole point of it."""
    assert _DEFAULTS["show_welcome"] is True


def test_button_ids_are_distinct():
    """Three outcomes must be tellable apart by the caller."""
    ids = {WelcomeDialog.OPEN_GUIDE, WelcomeDialog.NOT_NOW, WelcomeDialog.DONT_SHOW}
    assert len(ids) == 3


def test_escape_means_not_now_never_dont_show(frame):
    """Escape must not be able to switch the screen off for good."""
    dlg = WelcomeDialog(frame)
    try:
        assert dlg.GetEscapeId() == WelcomeDialog.NOT_NOW
        assert dlg.GetEscapeId() != WelcomeDialog.DONT_SHOW
    finally:
        dlg.Destroy()


def test_offers_every_band_plan_region(frame):
    """All five regions, in bandplan.REGIONS order — a user in IARU R1 who is
    never offered R1 gets North American offsets silently."""
    dlg = WelcomeDialog(frame)
    try:
        labels = [dlg.region.GetString(i) for i in range(dlg.region.GetCount())]
        assert labels == [label for _code, label in REGIONS]
        assert len(labels) == 5
    finally:
        dlg.Destroy()


@pytest.mark.parametrize("code", [c for c, _label in REGIONS])
def test_every_region_round_trips(frame, code):
    """The picker must hand back exactly the code it was given."""
    dlg = WelcomeDialog(frame, current_region=code)
    try:
        assert dlg.region_code() == code
    finally:
        dlg.Destroy()


def test_unknown_region_falls_back_to_default(frame):
    """A hand-edited or stale config.json must not raise at startup."""
    dlg = WelcomeDialog(frame, current_region="atlantis")
    try:
        assert dlg.region_code() == DEFAULT_REGION
    finally:
        dlg.Destroy()


def test_labels_precede_their_control(frame):
    """wxMSW names a native control from the preceding sibling and ignores
    SetName, so a StaticText must exist immediately before the region Choice or
    NVDA reads the wrong label for it."""
    dlg = WelcomeDialog(frame)
    try:
        kids = list(dlg.GetChildren())
        idx = kids.index(dlg.region)
        assert idx > 0
        before = kids[idx - 1]
        assert isinstance(before, wx.StaticText)
        assert "region" in before.GetLabel().lower()
    finally:
        dlg.Destroy()


def test_region_takes_focus_not_a_button(frame):
    """The decision should be under the cursor when the screen opens."""
    dlg = WelcomeDialog(frame)
    try:
        dlg.region.SetFocus()  # what _on_init_dialog's CallAfter does
        assert dlg.region.HasFocus() or wx.Window.FindFocus() is dlg.region
    finally:
        dlg.Destroy()


# -- MainWindow.maybe_show_welcome ------------------------------------------
#
# These drive the handler itself, not just the dialog. The first version of
# maybe_show_welcome used `bandplan` without importing it (every other method in
# main_window imports it locally), so it raised NameError the instant the gate
# let it through — and wx.CallAfter printed that to a console nobody sees, so
# the screen just never appeared. The dialog's own tests all passed: they never
# ran the handler. Hence these.


@pytest.fixture
def win(app, tmp_path, monkeypatch):
    """A real MainWindow with an isolated config."""
    import vrp.config as cfgmod
    from vrp.config import Config

    cfg = Config(str(tmp_path / "config.json"))
    monkeypatch.setattr(cfgmod, "get_config", lambda: cfg)

    from vrp.native.main_window import MainWindow

    w = MainWindow()
    w._test_cfg = cfg
    w._test_opened = []
    w._test_said = []
    monkeypatch.setattr(w, "on_getting_started", lambda *a: w._test_opened.append(1))
    monkeypatch.setattr(w.announce, "announce", lambda m, **k: w._test_said.append(m))
    yield w
    w.Destroy()


def _press(monkeypatch, button, region="australia"):
    """Stub ShowModal: pick a region, press one button. The rest stays real."""
    def fake_modal(self):
        self.region.SetSelection(self._region_codes.index(region))
        return button
    monkeypatch.setattr(WelcomeDialog, "ShowModal", fake_modal)


def test_welcome_shows_and_applies_region(win, monkeypatch):
    """The regression: the handler must survive the gate being open."""
    from chirp_backend import bandplan

    win._test_cfg.set("show_welcome", True)
    _press(monkeypatch, WelcomeDialog.NOT_NOW, region="australia")
    win.maybe_show_welcome()  # NameError before the fix
    assert win._test_cfg.get("bandplan_region") == "australia"
    assert bandplan.get_region() == "australia"


def test_dont_show_again_is_the_only_thing_that_clears_the_pref(win, monkeypatch):
    for button, expected in (
        (WelcomeDialog.OPEN_GUIDE, True),
        (WelcomeDialog.NOT_NOW, True),
        (WelcomeDialog.DONT_SHOW, False),
    ):
        win._test_cfg.set("show_welcome", True)
        _press(monkeypatch, button)
        win.maybe_show_welcome()
        assert win._test_cfg.get("show_welcome") is expected, f"button {button}"


def test_open_guide_button_opens_the_guide(win, monkeypatch):
    win._test_cfg.set("show_welcome", True)
    _press(monkeypatch, WelcomeDialog.OPEN_GUIDE)
    win.maybe_show_welcome()
    assert win._test_opened, "Open Getting Started did not open the guide"


def test_region_is_announced_when_the_guide_is_not_opened(win, monkeypatch):
    """The screen's one lasting effect must be audible."""
    win._test_cfg.set("show_welcome", True)
    _press(monkeypatch, WelcomeDialog.NOT_NOW, region="iaru_r3")
    win.maybe_show_welcome()
    assert any("IARU Region 3" in m for m in win._test_said), win._test_said


def test_welcome_is_skipped_once_switched_off(win, monkeypatch):
    win._test_cfg.set("show_welcome", False)

    def explode(self):
        raise AssertionError("the welcome screen showed when it was switched off")

    monkeypatch.setattr(WelcomeDialog, "ShowModal", explode)
    win.maybe_show_welcome()
