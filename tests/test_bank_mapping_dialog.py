"""GUI contracts for the explicit bank-mapping dialogs."""

import pytest

wx = pytest.importorskip("wx")

from chirp_backend.bank_ops import BankDescriptor  # noqa: E402
from vrp.bank_mapping_dialog import (  # noqa: E402
    BankMappingDialog,
    BankPickerDialog,
)


SOURCE_BANKS = (
    BankDescriptor(0, "A", "Repeaters", "Bank A: Repeaters", 3),
    BankDescriptor(1, "B", "", "Bank B", 1),
)
TARGET_BANKS = (
    BankDescriptor(0, "X", "Repeaters", "Bank X: Repeaters"),
    BankDescriptor(1, "Y", "Local", "Bank Y: Local"),
    BankDescriptor(2, "Z", "", "Bank Z"),
)


@pytest.fixture
def app():
    try:
        instance = wx.App()
    except Exception:  # noqa: BLE001 - headless CI
        pytest.skip("no GUI/display available")
    yield instance
    instance.Destroy()


def test_destination_picker_filters_and_returns_original_bank(app):
    dialog = BankPickerDialog(None, TARGET_BANKS, current_index="Y")
    try:
        assert dialog.get_selection() is TARGET_BANKS[1]
        dialog.filter.SetValue("bank z")
        dialog._apply_filter()
        assert dialog.list.GetCount() == 1
        assert dialog.get_selection() is TARGET_BANKS[2]
        assert dialog.FindWindowById(wx.ID_OK).GetLabel() == "Map"
    finally:
        dialog.Destroy()


def test_destination_picker_disables_map_when_filter_has_no_match(app):
    dialog = BankPickerDialog(None, TARGET_BANKS)
    try:
        dialog.filter.SetValue("missing")
        dialog._apply_filter()
        assert dialog.get_selection() is None
        assert not dialog.FindWindowById(wx.ID_OK).IsEnabled()
    finally:
        dialog.Destroy()


def test_mapping_dialog_exposes_and_edits_explicit_plan(app):
    dialog = BankMappingDialog(
        None,
        SOURCE_BANKS,
        TARGET_BANKS,
        initial_mapping={0: "X"},
    )
    try:
        assert dialog.get_mapping() == {0: "X"}
        assert "maps to Bank X: Repeaters" in dialog.list.GetString(0)
        dialog.list.SetSelection(1)
        dialog.map_selected_to("Z")
        assert dialog.get_mapping() == {0: "X", 1: "Z"}
        dialog.clear_selected()
        assert dialog.get_mapping() == {0: "X"}
        assert (
            dialog.FindWindowById(wx.ID_OK).GetLabel()
            == "Import with bank mapping"
        )
    finally:
        dialog.Destroy()


def test_bulk_mapping_buttons_are_explicit_and_predictable(app):
    dialog = BankMappingDialog(None, SOURCE_BANKS, TARGET_BANKS)
    try:
        dialog.match_names()
        assert dialog.get_mapping() == {0: "X"}
        dialog.clear_all()
        assert dialog.get_mapping() == {}
        dialog.match_positions()
        assert dialog.get_mapping() == {0: "X", 1: "Y"}
    finally:
        dialog.Destroy()


def test_source_filter_preserves_mapping_for_hidden_banks(app):
    dialog = BankMappingDialog(
        None,
        SOURCE_BANKS,
        TARGET_BANKS,
        initial_mapping={0: "X", 1: "Y"},
    )
    try:
        dialog.filter.SetValue("repeaters")
        dialog._apply_filter()
        assert dialog.list.GetCount() == 1
        assert dialog.get_mapping() == {0: "X", 1: "Y"}
        assert "2 of 2 source banks mapped" in dialog.count.GetLabel()
    finally:
        dialog.Destroy()


def test_labels_immediately_precede_native_filter_and_list_controls(app):
    picker = BankPickerDialog(None, TARGET_BANKS)
    mapping = BankMappingDialog(None, SOURCE_BANKS, TARGET_BANKS)
    try:
        def label_before(dialog, control, expected):
            children = list(dialog.GetChildren())
            previous = children[children.index(control) - 1]
            assert isinstance(previous, wx.StaticText)
            assert previous.GetLabel() == expected

        label_before(picker, picker.filter, "Filter:")
        label_before(picker, picker.list, "Destination bank:")
        label_before(mapping, mapping.filter, "Filter:")
        label_before(mapping, mapping.list, "Source bank mappings:")
    finally:
        picker.Destroy()
        mapping.Destroy()
