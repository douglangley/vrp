"""The settings dialog surfaces plain-language help for the focused setting."""

import pytest

wx = pytest.importorskip("wx")

from chirp import settings as cs  # noqa: E402

from vrp.settings_dialog import RadioSettingsDialog  # noqa: E402


@pytest.fixture
def app():
    try:
        instance = wx.App()
    except Exception:  # noqa: BLE001 - headless CI
        pytest.skip("no GUI/display available")
    yield instance
    instance.Destroy()


def _group():
    group = cs.RadioSettingGroup("basic", "Basic")

    known = cs.RadioSetting(
        "squelch", "Squelch Level", cs.RadioSettingValueInteger(0, 9, 3)
    )
    documented = cs.RadioSetting(
        "tot", "Time-out timer", cs.RadioSettingValueInteger(0, 600, 60)
    )
    documented.set_doc("This radio stops transmitting after the chosen time.")
    unknown = cs.RadioSetting(
        "wibble", "Wibble", cs.RadioSettingValueBoolean(False)
    )

    group.append(known)
    group.append(documented)
    group.append(unknown)
    return group


def test_dialog_has_a_navigable_named_description_box(app):
    dialog = RadioSettingsDialog(None, [_group()])
    try:
        box = dialog._description
        assert box.GetName() == "Setting description"
        assert not box.IsEditable()          # read-only but focusable/copyable
        assert box.GetValue() == dialog._DEFAULT_DESCRIPTION
    finally:
        dialog.Destroy()


def test_known_setting_gets_vrps_description(app):
    dialog = RadioSettingsDialog(None, [_group()])
    try:
        texts = list(dialog._description_of.values())
        assert any("speaker unmutes" in text for text in texts)
    finally:
        dialog.Destroy()


def test_driver_documentation_is_preferred_over_the_generic_table(app):
    dialog = RadioSettingsDialog(None, [_group()])
    try:
        texts = list(dialog._description_of.values())
        assert any(
            text == "This radio stops transmitting after the chosen time."
            for text in texts
        ), texts
        # The generic time-out text must not also be present for that control.
        assert not any("cannot hold the repeater open" in t for t in texts)
    finally:
        dialog.Destroy()


def test_undescribed_setting_says_so_rather_than_showing_nothing(app):
    """A11y rule 7 — absence must be stated, not implied by an empty box."""
    dialog = RadioSettingsDialog(None, [_group()])
    try:
        assert dialog._NO_DESCRIPTION in dialog._description_of.values()
    finally:
        dialog.Destroy()


def test_focusing_a_control_updates_the_description(app):
    dialog = RadioSettingsDialog(None, [_group()])
    try:
        ctrl_id, expected = next(
            (cid, text)
            for cid, text in dialog._description_of.items()
            if "speaker unmutes" in text
        )
        ctrl = dialog.FindWindowById(ctrl_id)
        assert ctrl is not None

        # Fire the same event the focus binding listens for.
        event = wx.FocusEvent(wx.wxEVT_SET_FOCUS, ctrl_id)
        event.SetEventObject(ctrl)
        ctrl.GetEventHandler().ProcessEvent(event)

        assert dialog._description.GetValue() == expected
    finally:
        dialog.Destroy()


def test_every_control_carries_a_description_entry(app):
    dialog = RadioSettingsDialog(None, [_group()])
    try:
        for _value, ctrl in dialog._controls:
            assert ctrl.GetId() in dialog._description_of
    finally:
        dialog.Destroy()
