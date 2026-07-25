"""GUI contracts for the explicit single/special-memory import dialogs."""

from types import SimpleNamespace

import pytest

wx = pytest.importorskip("wx")

from vrp.special_memory_dialogs import (  # noqa: E402
    DestinationTypeDialog,
    ImportModeDialog,
    MemoryPickerDialog,
)


LOCATIONS = [
    SimpleNamespace(identifier=1, label="Channel 1 — LOCAL — 146.520000 MHz"),
    SimpleNamespace(identifier="C", label="Special C — CALL — 146.100000 MHz"),
    SimpleNamespace(identifier="1A", label="Special 1A — 144.000000 MHz"),
]


@pytest.fixture
def app():
    try:
        instance = wx.App()
    except Exception:  # noqa: BLE001 - headless CI
        pytest.skip("no GUI/display available")
    yield instance
    instance.Destroy()


def test_import_mode_disables_empty_bulk_choice(app):
    dialog = ImportModeDialog(
        None, 0, 2, target_has_specials=True
    )
    try:
        assert not dialog.mode.IsItemEnabled(0)
        assert dialog.get_mode() == "single"
        assert dialog.FindWindowById(wx.ID_OK).GetLabel() == "Next"
    finally:
        dialog.Destroy()


def test_destination_type_is_explicit(app):
    dialog = DestinationTypeDialog(None, LOCATIONS[1].label)
    try:
        assert dialog.get_destination_type() == "regular"
        dialog.kind.SetSelection(1)
        assert dialog.get_destination_type() == "special"
    finally:
        dialog.Destroy()


def test_memory_picker_filters_and_returns_original_object(app):
    dialog = MemoryPickerDialog(
        None,
        LOCATIONS,
        title="Choose source",
        prompt="Choose one source memory.",
        action_label="Select",
        current_identifier="C",
    )
    try:
        assert dialog.get_selection() is LOCATIONS[1]
        dialog.filter.SetValue("1a")
        dialog._apply_filter()
        assert dialog.list.GetCount() == 1
        assert dialog.get_selection() is LOCATIONS[2]
        assert dialog.FindWindowById(wx.ID_OK).GetLabel() == "Select"
    finally:
        dialog.Destroy()


def test_no_match_disables_picker_action(app):
    dialog = MemoryPickerDialog(
        None,
        LOCATIONS,
        title="Choose source",
        prompt="Choose one source memory.",
        action_label="Select",
    )
    try:
        dialog.filter.SetValue("not present")
        dialog._apply_filter()
        assert dialog.get_selection() is None
        assert not dialog.FindWindowById(wx.ID_OK).IsEnabled()
    finally:
        dialog.Destroy()


def test_picker_labels_immediately_precede_native_controls(app):
    dialog = MemoryPickerDialog(
        None,
        LOCATIONS,
        title="Choose source",
        prompt="Choose one source memory.",
        action_label="Select",
    )
    try:
        children = list(dialog.GetChildren())

        def label_before(control, expected):
            previous = children[children.index(control) - 1]
            assert isinstance(previous, wx.StaticText)
            assert previous.GetLabel() == expected

        label_before(dialog.filter, "Filter:")
        label_before(dialog.list, "Memory:")
    finally:
        dialog.Destroy()
