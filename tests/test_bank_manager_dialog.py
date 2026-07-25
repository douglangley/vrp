"""GUI contracts for the bank manager and its read-only channel list."""

import pytest

wx = pytest.importorskip("wx")

from chirp_backend.bank_ops import BankCatalog, BankChannel, BankDescriptor  # noqa: E402
from vrp.bank_manager_dialog import (  # noqa: E402
    BankChannelsDialog,
    BankManagerDialog,
)


NAMED_BANKS = (
    BankDescriptor(0, "A", "Repeaters", "Bank A: Repeaters", renameable=True),
    BankDescriptor(1, "B", "", "Bank B", renameable=True),
)
PLAIN_BANKS = (
    BankDescriptor(0, "A", "Repeaters", "Bank A: Repeaters", renameable=False),
)
CHANNELS = {
    0: (
        BankChannel(3, "SIMPLEX", 146520000, 0),
        BankChannel(7, "", 443100000, 1),
    ),
    1: (),
}


def _catalog(banks, renameable):
    return BankCatalog(
        available=True,
        mutable=True,
        mode="multi",
        indexed=True,
        banks=banks,
        renameable=renameable,
    )


@pytest.fixture
def app():
    try:
        instance = wx.App()
    except Exception:  # noqa: BLE001 - headless CI
        pytest.skip("no GUI/display available")
    yield instance
    instance.Destroy()


def test_manager_states_rename_capability_in_words(app):
    dialog = BankManagerDialog(None, _catalog(NAMED_BANKS, True), CHANNELS)
    try:
        assert "can be changed" in dialog.intro.GetLabel()
    finally:
        dialog.Destroy()


def test_manager_states_when_names_cannot_be_changed(app):
    """Rule 7 — capability must be readable text, not just a greyed button."""
    dialog = BankManagerDialog(None, _catalog(PLAIN_BANKS, False), {0: ()})
    try:
        assert "cannot be changed" in dialog.intro.GetLabel()
        assert dialog.rename_button.IsEnabled() is False
    finally:
        dialog.Destroy()


def test_manager_rows_carry_the_channel_count(app):
    dialog = BankManagerDialog(None, _catalog(NAMED_BANKS, True), CHANNELS)
    try:
        assert dialog.list.GetString(0) == "Bank A: Repeaters — 2 channels"
        assert dialog.list.GetString(1) == "Bank B — 0 channels"
    finally:
        dialog.Destroy()


def test_manager_filter_narrows_and_still_returns_the_original_bank(app):
    dialog = BankManagerDialog(None, _catalog(NAMED_BANKS, True), CHANNELS)
    try:
        dialog.filter.SetValue("bank b")
        dialog._apply_filter()
        assert dialog.list.GetCount() == 1
        assert dialog.get_bank() is NAMED_BANKS[1]
        assert "1 bank matches" == dialog.count.GetLabel()
    finally:
        dialog.Destroy()


def test_manager_rename_button_follows_the_selected_bank(app):
    mixed = (
        BankDescriptor(0, "A", "Repeaters", "Bank A: Repeaters", renameable=True),
        BankDescriptor(1, "B", "", "Bank B", renameable=False),
    )
    dialog = BankManagerDialog(None, _catalog(mixed, True), {0: (), 1: ()})
    try:
        dialog.list.SetSelection(0)
        dialog._update_buttons()
        assert dialog.rename_button.IsEnabled() is True

        dialog.list.SetSelection(1)
        dialog._update_buttons()
        assert dialog.rename_button.IsEnabled() is False
    finally:
        dialog.Destroy()


def test_manager_refresh_keeps_the_selected_bank(app):
    dialog = BankManagerDialog(None, _catalog(NAMED_BANKS, True), CHANNELS)
    try:
        dialog.list.SetSelection(1)
        renamed = (
            NAMED_BANKS[0],
            BankDescriptor(1, "B", "Coast", "Bank B: Coast", renameable=True),
        )

        dialog.refresh(_catalog(renamed, True), CHANNELS)

        assert dialog.get_bank().name == "Coast"
        assert dialog.list.GetString(1) == "Bank B: Coast — 0 channels"
    finally:
        dialog.Destroy()


def test_manager_is_escapable(app):
    dialog = BankManagerDialog(None, _catalog(NAMED_BANKS, True), CHANNELS)
    try:
        assert dialog.GetEscapeId() == wx.ID_CANCEL
    finally:
        dialog.Destroy()


def test_channels_dialog_lists_speakable_rows(app):
    dialog = BankChannelsDialog(None, "Bank A: Repeaters", CHANNELS[0])
    try:
        assert dialog.list.GetString(0) == (
            "Channel 3 — 146.52 MHz — SIMPLEX — position 0"
        )
        # An unnamed channel simply omits the name rather than speaking a blank.
        assert dialog.list.GetString(1) == "Channel 7 — 443.1 MHz — position 1"
        assert dialog.get_channel() == 3
    finally:
        dialog.Destroy()


def test_channels_dialog_states_an_empty_bank_in_words(app):
    dialog = BankChannelsDialog(None, "Bank B", ())
    try:
        assert dialog.get_channel() is None
        assert dialog._go.IsEnabled() is False
    finally:
        dialog.Destroy()


def test_channels_dialog_is_escapable(app):
    dialog = BankChannelsDialog(None, "Bank A", CHANNELS[0])
    try:
        assert dialog.GetEscapeId() == wx.ID_CANCEL
    finally:
        dialog.Destroy()
