"""GUI contract for the accessible memory-section chooser."""

import pytest

wx = pytest.importorskip("wx")

from vrp.subdevice_dialog import SubdeviceDialog  # noqa: E402


LABELS = (
    "Left — channels 1 to 512",
    "Right — channels 1 to 512",
    "Packet — channels 1 to 100",
)


@pytest.fixture
def app():
    try:
        instance = wx.App()
    except Exception:  # noqa: BLE001 - headless CI
        pytest.skip("no GUI/display available")
    yield instance
    instance.Destroy()


def test_list_and_current_section_are_selected(app):
    dialog = SubdeviceDialog(None, LABELS, current_index=1)
    try:
        assert dialog.list.GetCount() == 3
        assert dialog.get_index() == 1
        assert dialog.FindWindowById(wx.ID_OK).GetLabel() == "Open"
    finally:
        dialog.Destroy()

def test_filter_returns_original_section_index(app):
    dialog = SubdeviceDialog(None, LABELS, action_label="Import")
    try:
        dialog.filter.SetValue("packet")
        dialog._apply_filter()
        assert dialog.list.GetCount() == 1
        assert dialog.get_index() == 2
        assert dialog.FindWindowById(wx.ID_OK).GetLabel() == "Import"
    finally:
        dialog.Destroy()


def test_no_match_disables_action(app):
    dialog = SubdeviceDialog(None, LABELS)
    try:
        dialog.filter.SetValue("nothing")
        dialog._apply_filter()
        assert dialog.get_index() is None
        assert not dialog.FindWindowById(wx.ID_OK).IsEnabled()
    finally:
        dialog.Destroy()


def test_labels_are_created_immediately_before_controls(app):
    dialog = SubdeviceDialog(None, LABELS)
    try:
        children = list(dialog.GetChildren())

        def label_before(control, expected):
            previous = children[children.index(control) - 1]
            assert isinstance(previous, wx.StaticText)
            assert previous.GetLabel() == expected

        label_before(dialog.filter, "Filter:")
        label_before(dialog.list, "Memory section:")
    finally:
        dialog.Destroy()
