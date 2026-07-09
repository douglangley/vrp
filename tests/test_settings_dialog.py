"""GUI smoke tests for the Radio settings dialog (Phase 1.5).

Verifies that OK writes back only the controls the user actually changed, so a
value with significant trailing padding isn't silently rewritten (and
value.changed() isn't spuriously tripped). Skips automatically when no
display/wx.App is available."""

import pytest

wx = pytest.importorskip("wx")

from chirp import settings as cs  # noqa: E402


@pytest.fixture
def app():
    try:
        a = wx.App()
    except Exception:  # noqa: BLE001 — headless CI
        pytest.skip("no GUI/display available")
    yield a
    a.Destroy()


def _make_dialog(frame, value):
    from vrp.settings_dialog import RadioSettingsDialog

    setting = cs.RadioSetting("field", "Field", value)
    group = cs.RadioSettingGroup("basic", "Basic", setting)
    return RadioSettingsDialog(frame, [group])


def _click_ok(dlg):
    evt = wx.CommandEvent(wx.wxEVT_COMMAND_BUTTON_CLICKED, wx.ID_OK)
    dlg._on_ok(evt)


def test_ok_with_no_edits_writes_nothing(app):
    # autopad=False keeps the trailing spaces, so a naive "write everything on
    # OK" would rstrip the display value ("ABC") back onto a padded current
    # ("ABC  ") and spuriously flag changed(). The fix skips unchanged controls.
    value = cs.RadioSettingValueString(0, 8, "ABC  ", autopad=False)

    frame = wx.Frame(None)
    try:
        dlg = _make_dialog(frame, value)  # RadioSetting init late-initializes value
        assert value.get_value() == "ABC  "
        # The control shows the value rstrip()'d...
        _v, ctrl = dlg._controls[0]
        assert dlg._read(ctrl) == "ABC"
        # ...but OK with no user edit leaves the padded value and changed() flag
        # untouched.
        _click_ok(dlg)
        assert value.get_value() == "ABC  "
        assert value.changed() is False
        assert dlg.get_changed_count() == 0
        dlg.Destroy()
    finally:
        frame.Destroy()


def test_ok_writes_genuine_edit(app):
    value = cs.RadioSettingValueString(0, 8, "ABC  ", autopad=False)

    frame = wx.Frame(None)
    try:
        dlg = _make_dialog(frame, value)
        _v, ctrl = dlg._controls[0]
        ctrl.SetValue("XYZ")
        _click_ok(dlg)
        assert value.get_value() == "XYZ"
        assert value.changed() is True
        assert dlg.get_changed_count() == 1
        dlg.Destroy()
    finally:
        frame.Destroy()
