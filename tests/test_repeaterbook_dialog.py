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


def test_each_field_label_created_immediately_before_its_control(app):
    # Root-cause regression guard. On Windows wxMSW names a native control from
    # the StaticText created just before it (SetName does NOT reach MSAA), so a
    # field label must be created immediately before its control or the screen
    # reader reads every field off by one. GetChildren() is creation order;
    # assert each control's preceding sibling is its own label. Verified at the
    # MSAA level (oleacc get_accName) during development.
    dlg = RepeaterBookQueryDialog(None)
    try:
        kids = list(dlg.GetChildren())

        def label_before(control, expected):
            prev = kids[kids.index(control) - 1]
            assert isinstance(prev, wx.StaticText), (
                f"{expected!r}: expected a StaticText created before the control, "
                f"got {type(prev).__name__}"
            )
            assert prev.GetLabel() == expected

        label_before(dlg.country, "Country:")
        label_before(dlg.state, "State or province:")
        label_before(dlg.filter, "Search (city, callsign, county):")
        label_before(dlg.modes, "Modes (leave all clear for any):")
    finally:
        dlg.Destroy()


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
