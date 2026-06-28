"""Tests for the native UI undo/redo handlers (MainWindow.on_undo/on_redo).

Drives MainWindow against a real image: an op runs through memory_ops (recorded
by the decorator), then on_undo/on_redo restore/replay it and the grid refreshes.
Skips without a GUI."""

import os

import pytest

from chirp_backend import radio as radio_backend

wx = pytest.importorskip("wx")

IMAGE = os.path.abspath(
    os.path.join(
        os.path.dirname(__file__), "..", "chirp", "tests", "images",
        "Baofeng_UV-5R.img",
    )
)


@pytest.fixture
def app():
    try:
        a = wx.App()
    except Exception:  # noqa: BLE001 — headless CI
        pytest.skip("no GUI/display available")
    yield a
    a.Destroy()


@pytest.fixture
def win(app):
    from vrp.native.main_window import MainWindow

    w = MainWindow()
    radio_backend.load_image(IMAGE)
    w._load_into_grid()
    try:
        yield w
    finally:
        radio_backend.unload()
        w.Destroy()


def _first_nonempty():
    lo, hi = radio_backend.get_state().memory_bounds
    for n in range(lo, hi + 1):
        if not radio_backend.get_memory(n).empty:
            return n
    return None


def test_undo_redo_round_trip_through_handlers(win):
    from chirp_backend import memory_ops

    n = _first_nonempty()
    before = radio_backend.get_memory(n).name
    memory_ops.update_channel(n, {"name": "QWERTY"})
    assert radio_backend.get_memory(n).name == "QWERTY"

    win.on_undo()
    assert radio_backend.get_memory(n).name == before

    win.on_redo()
    assert radio_backend.get_memory(n).name == "QWERTY"


def test_undo_with_empty_history_is_safe(win):
    # Fresh image: nothing to undo. Must not raise (just announces).
    win.on_undo()
    win.on_redo()


def test_edit_menu_has_undo_redo(win):
    edit_menu = win.GetMenuBar().GetMenu(1)  # File(0), Edit(1)
    labels = " ".join(
        edit_menu.FindItemByPosition(i).GetItemLabelText()
        for i in range(edit_menu.GetMenuItemCount())
    ).lower()
    assert "undo" in labels and "redo" in labels
    assert win._menu_items["undo"].IsEnabled()
    assert win._menu_items["redo"].IsEnabled()


def test_ctrl_shift_z_accelerator_triggers_redo(win):
    """The Ctrl+Shift+Z accelerator id is bound to on_redo (the redo alias)."""
    from chirp_backend import memory_ops

    n = _first_nonempty()
    before = radio_backend.get_memory(n).name
    memory_ops.update_channel(n, {"name": "ALIASD"})
    win.on_undo()
    assert radio_backend.get_memory(n).name == before

    # Fire the command the Ctrl+Shift+Z accelerator maps to.
    evt = wx.CommandEvent(wx.wxEVT_MENU, int(win._redo_accel_id))
    win.GetEventHandler().ProcessEvent(evt)
    assert radio_backend.get_memory(n).name == "ALIASD"


def test_menu_open_relabels_undo_with_op(win):
    from chirp_backend import memory_ops

    n = _first_nonempty()
    memory_ops.delete_range([n])  # label ~ "Deleted 1 channel(s)..."

    # Simulate the Edit menu opening.
    evt = wx.MenuEvent(wx.wxEVT_MENU_OPEN, menu=win._edit_menu)
    win._on_menu_open(evt)
    label = win._menu_items["undo"].GetItemLabelText()
    assert "Deleted" in label  # relabeled with the op it would undo
