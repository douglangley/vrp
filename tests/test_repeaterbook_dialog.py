"""GUI tests for the RepeaterBook query dialog (vrp/query_dialogs.py).

Skips without a display. No network: the dialog only reads CHIRP's geography
lists and builds a params dict; the fetch itself lives in main_window/backend.
"""

import pytest

wx = pytest.importorskip("wx")

from vrp.query_dialogs import RepeaterBookQueryDialog  # noqa: E402


@pytest.fixture
def app():
    try:
        a = wx.App()
    except Exception:  # noqa: BLE001 — headless CI
        pytest.skip("no GUI/display available")
    yield a
    a.Destroy()


def test_defaults_to_us_with_states_enabled(app):
    dlg = RepeaterBookQueryDialog(None)
    try:
        assert dlg.country.GetStringSelection() == "United States"
        assert dlg.state.IsEnabled()
        assert dlg.state.GetCount() > 0
        assert "Oregon" in [dlg.state.GetString(i) for i in range(dlg.state.GetCount())]
    finally:
        dlg.Destroy()


def test_row_country_disables_state(app):
    dlg = RepeaterBookQueryDialog(None)
    try:
        idx = dlg.country.FindString("Germany")
        assert idx != wx.NOT_FOUND
        dlg.country.SetSelection(idx)
        dlg._on_country()
        assert not dlg.state.IsEnabled()
        # A country without sub-regions yields state "all" in the params.
        assert dlg.get_params()["state"] == "all"
    finally:
        dlg.Destroy()


def test_get_params_reflects_controls(app):
    dlg = RepeaterBookQueryDialog(None)
    try:
        dlg.state.SetStringSelection("Oregon")
        dlg.filter.SetValue("  portland  ")
        dlg.open_only.SetValue(True)
        fm = dlg.modes.FindString("FM")
        dlg.modes.Check(fm, True)

        params = dlg.get_params()
        assert params["country"] == "United States"
        assert params["state"] == "Oregon"
        assert params["filter"] == "portland"  # stripped
        assert params["openonly"] is True
        assert params["modes"] == ["FM"]
        # Sanity: the keys do_fetch pops with no default are all present.
        assert {"lat", "lon", "dist", "cached"} <= set(params)
    finally:
        dlg.Destroy()
