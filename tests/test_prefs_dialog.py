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
            "speak_status_messages": False,
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


def test_unknown_saved_region_falls_back_to_default(app):
    from vrp.prefs_dialog import PreferencesDialog
    from chirp_backend.bandplan import DEFAULT_REGION

    frame = wx.Frame(None)
    try:
        dlg = PreferencesDialog(frame, {
            "speak_status_messages": False,
            "recent_files_count": 9,
            "bandplan_region": "atlantis",
        })
        assert dlg.get_values()["bandplan_region"] == DEFAULT_REGION
        dlg.Destroy()
    finally:
        frame.Destroy()
