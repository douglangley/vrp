"""GUI smoke tests for the Preferences dialog (band-plan region selector).
Skips automatically when no display/wx.App is available."""

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


def test_region_choice_round_trips(app):
    from vrp.prefs_dialog import PreferencesDialog

    frame = wx.Frame(None)
    try:
        dlg = PreferencesDialog(frame, {
            "speak_messages": True,
            "recent_files_count": 9,
            "bandplan_region": "iaru_r1",
        })
        # Opens on the saved region...
        assert dlg.region.GetSelection() == dlg._region_codes.index("iaru_r1")
        assert dlg.get_values()["bandplan_region"] == "iaru_r1"
        # ...and reports the shortname after the user changes it.
        idx = dlg._region_codes.index("australia")
        dlg.region.SetSelection(idx)
        assert dlg.get_values()["bandplan_region"] == "australia"
        dlg.Destroy()
    finally:
        frame.Destroy()


def test_auto_band_defaults_checkbox_round_trips(app):
    from vrp.prefs_dialog import PreferencesDialog

    frame = wx.Frame(None)
    try:
        dlg = PreferencesDialog(frame, {
            "speak_messages": True,
            "recent_files_count": 9,
            "bandplan_region": "north_america",
            "auto_band_defaults": True,
        })
        assert dlg.auto_defaults.GetValue() is True
        assert dlg.get_values()["auto_band_defaults"] is True
        dlg.auto_defaults.SetValue(False)
        assert dlg.get_values()["auto_band_defaults"] is False
        dlg.Destroy()
    finally:
        frame.Destroy()


def test_speak_messages_checkbox_round_trips(app):
    """The pref the user actually toggles. It was dead for a while — read and
    written but never consulted — so this guards the round-trip."""
    from vrp.prefs_dialog import PreferencesDialog

    frame = wx.Frame(None)
    try:
        dlg = PreferencesDialog(frame, {
            "speak_messages": True,
            "recent_files_count": 9,
            "bandplan_region": "north_america",
        })
        assert dlg.speak.GetValue() is True
        assert dlg.get_values()["speak_messages"] is True
        dlg.speak.SetValue(False)
        assert dlg.get_values()["speak_messages"] is False
        dlg.Destroy()
    finally:
        frame.Destroy()


def test_speak_messages_defaults_on_when_absent(app):
    """A config with no speak_messages key (e.g. one carrying only the
    abandoned speak_status_messages) must open with speech ON, not off."""
    from vrp.prefs_dialog import PreferencesDialog

    frame = wx.Frame(None)
    try:
        dlg = PreferencesDialog(frame, {
            "recent_files_count": 9,
            "bandplan_region": "north_america",
            "speak_status_messages": False,  # the abandoned key — must not win
        })
        assert dlg.speak.GetValue() is True
        assert dlg.get_values()["speak_messages"] is True
        dlg.Destroy()
    finally:
        frame.Destroy()


def test_speak_checkbox_label_mentions_grid_always_speaks(app):
    """The label must not imply turning this off silences grid navigation — it
    doesn't, and a user who expected silence there would think it was broken."""
    from vrp.prefs_dialog import PreferencesDialog

    frame = wx.Frame(None)
    try:
        dlg = PreferencesDialog(frame, {
            "speak_messages": True,
            "recent_files_count": 9,
            "bandplan_region": "north_america",
        })
        assert "always speaks" in dlg.speak.GetLabel()
        dlg.Destroy()
    finally:
        frame.Destroy()


def test_unknown_saved_region_falls_back_to_default(app):
    from vrp.prefs_dialog import PreferencesDialog
    from chirp_backend.bandplan import DEFAULT_REGION

    frame = wx.Frame(None)
    try:
        dlg = PreferencesDialog(frame, {
            "speak_messages": True,
            "recent_files_count": 9,
            "bandplan_region": "atlantis",
        })
        assert dlg.get_values()["bandplan_region"] == DEFAULT_REGION
        dlg.Destroy()
    finally:
        frame.Destroy()
