"""Tests for the native UI cut/copy/paste clipboard handlers (MainWindow).

These drive MainWindow.on_copy/on_cut/on_paste against a real CHIRP image. The
conflict dialog (_ask_paste_conflict) is monkeypatched so paths run headless
without a modal. paste_block's own correctness is covered in test_memory_ops.py;
here we verify the handler wiring (clipboard state, destination, cut vs copy,
guards, and the dialog choice -> make_room mapping). Skips without a GUI."""

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
MINI_IMAGE = os.path.abspath(
    os.path.join(
        os.path.dirname(__file__), "..", "chirp", "tests", "images",
        "Baofeng_UV-5R_Mini.img",
    )
)
FT8800_IMAGE = os.path.abspath(
    os.path.join(
        os.path.dirname(__file__), "..", "chirp", "tests", "images",
        "Yaesu_FT-8800.img",
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


def _first_empty(low, high):
    for n in range(low, high + 1):
        if radio_backend.get_memory(n).empty:
            return n
    return None


def _first_nonempty(low, high):
    for n in range(low, high + 1):
        if not radio_backend.get_memory(n).empty:
            return n
    return None


def test_on_copy_populates_clipboard(win):
    win.grid.select_channels([2, 3])
    win.on_copy()
    assert win._clipboard is not None
    assert win._clipboard.mode == "copy"
    assert len(win._clipboard.mems) == 2
    assert win._clipboard.source_numbers == [2, 3]


def test_on_cut_populates_clipboard(win):
    win.grid.select_channels([4, 5])
    win.on_cut()
    assert win._clipboard.mode == "cut"
    assert win._clipboard.source_numbers == [4, 5]


def test_paste_empty_clipboard_does_nothing(win, monkeypatch):
    from chirp_backend import memory_ops

    monkeypatch.setattr(
        memory_ops, "paste_block",
        lambda *a, **k: pytest.fail("paste_block called with empty clipboard"),
    )
    win._clipboard = None
    win.on_paste()  # should just announce, not paste


def test_copy_paste_into_empty(win, monkeypatch):
    low, high = radio_backend.get_state().memory_bounds
    src = _first_nonempty(low, high)
    dest = _first_empty(low, high)
    assert src is not None and dest is not None and src != dest
    src_name = radio_backend.get_memory(src).name
    src_freq = radio_backend.get_memory(src).freq

    # An empty destination must not trigger the conflict dialog.
    monkeypatch.setattr(
        win, "_ask_paste_conflict",
        lambda *a: pytest.fail("conflict dialog shown for empty destination"),
    )
    win.grid.select_channels([src])
    win.on_copy()
    win.grid.focus_channel(dest)
    win.on_paste()

    pasted = radio_backend.get_memory(dest)
    assert not pasted.empty
    assert pasted.name == src_name and pasted.freq == src_freq
    assert radio_backend.get_memory(src).name == src_name  # copy keeps source
    assert win._clipboard is not None  # copy keeps the clipboard


def test_cut_paste_moves_and_clears_clipboard(win, monkeypatch):
    low, high = radio_backend.get_state().memory_bounds
    src = _first_nonempty(low, high)
    dest = _first_empty(low, high)
    assert src is not None and dest is not None and src != dest
    src_name = radio_backend.get_memory(src).name

    monkeypatch.setattr(win, "_ask_paste_conflict", lambda *a: "overwrite")
    win.grid.select_channels([src])
    win.on_cut()
    win.grid.focus_channel(dest)
    win.on_paste()

    assert radio_backend.get_memory(dest).name == src_name
    assert radio_backend.get_memory(src).empty  # source moved away
    assert win._clipboard is None  # cut is one-shot


def test_paste_runs_past_end_is_blocked(win, monkeypatch):
    from chirp_backend import memory_ops

    low, high = radio_backend.get_state().memory_bounds
    win.grid.select_channels([low, low + 1])  # two-channel clipboard
    win.on_copy()
    win.grid.focus_channel(high)  # dest+1 would be high+1 -> out of range

    monkeypatch.setattr(
        memory_ops, "paste_block",
        lambda *a, **k: pytest.fail("paste_block called when paste runs past end"),
    )
    win.on_paste()  # should announce the no-room error, not paste


def test_paste_conflict_move_passes_make_room(win, monkeypatch):
    low, high = radio_backend.get_state().memory_bounds
    src = _first_nonempty(low, high)
    # A non-empty destination distinct from the source forces the conflict dialog.
    dest = next(
        (n for n in range(low, high + 1)
         if not radio_backend.get_memory(n).empty and n != src),
        None,
    )
    assert dest is not None

    from chirp_backend import memory_ops

    captured = {}
    real = memory_ops.paste_block

    def spy(mems, destination, **kw):
        captured["dest"] = destination
        captured["kw"] = kw
        return real(mems, destination, **kw)

    monkeypatch.setattr(memory_ops, "paste_block", spy)
    monkeypatch.setattr(win, "_ask_paste_conflict", lambda *a: "move")

    win.grid.select_channels([src])
    win.on_copy()
    win.grid.focus_channel(dest)
    win.on_paste()

    assert captured["dest"] == dest
    assert captured["kw"]["make_room"] is True
    assert captured["kw"]["cut_from"] is None  # copy, not cut


def test_paste_conflict_cancel_makes_no_change(win, monkeypatch):
    from chirp_backend import memory_ops

    low, high = radio_backend.get_state().memory_bounds
    src = _first_nonempty(low, high)
    dest = next(
        (n for n in range(low, high + 1)
         if not radio_backend.get_memory(n).empty and n != src),
        None,
    )
    assert dest is not None
    dest_name = radio_backend.get_memory(dest).name

    monkeypatch.setattr(
        memory_ops, "paste_block",
        lambda *a, **k: pytest.fail("paste_block called after cancel"),
    )
    monkeypatch.setattr(win, "_ask_paste_conflict", lambda *a: None)

    win.grid.select_channels([src])
    win.on_copy()
    win.grid.focus_channel(dest)
    win.on_paste()

    assert radio_backend.get_memory(dest).name == dest_name  # unchanged


def test_copy_skips_unreadable_channel(win, monkeypatch):
    """A channel whose get_memory returns None is skipped, not crashed on."""
    orig = radio_backend.get_memory
    monkeypatch.setattr(
        radio_backend, "get_memory", lambda n: None if n == 2 else orig(n)
    )
    win.grid.select_channels([2, 3])
    win.on_copy()  # would AttributeError on None.dupe() before the fix
    assert win._clipboard is not None
    assert win._clipboard.source_numbers == [3]  # unreadable 2 dropped
    assert len(win._clipboard.mems) == 1


def test_copy_all_unreadable_returns_none(win, monkeypatch):
    """When nothing selected can be read, copy announces and leaves the
    clipboard empty rather than crashing."""
    monkeypatch.setattr(radio_backend, "get_memory", lambda n: None)
    win.grid.select_channels([2, 3])
    win.on_copy()
    assert win._clipboard is None


def test_paste_over_unreadable_destination_no_crash(win, monkeypatch):
    """An unreadable destination slot is treated as empty in the occupancy
    check (no crash on .empty, no spurious conflict dialog)."""
    from chirp_backend import memory_ops

    low, high = radio_backend.get_state().memory_bounds
    src = _first_nonempty(low, high)
    dest = _first_empty(low, high)
    assert src is not None and dest is not None
    win.grid.select_channels([src])
    win.on_copy()  # snapshot taken while get_memory is still real

    orig = radio_backend.get_memory
    monkeypatch.setattr(
        radio_backend, "get_memory", lambda n: None if n == dest else orig(n)
    )
    monkeypatch.setattr(
        win, "_ask_paste_conflict",
        lambda *a: pytest.fail("conflict dialog shown for unreadable (empty) dest"),
    )
    called = {}
    real = memory_ops.paste_block

    def spy(*a, **k):
        called["yes"] = True
        return real(*a, **k)

    monkeypatch.setattr(memory_ops, "paste_block", spy)
    win.grid.focus_channel(dest)
    win.on_paste()  # must not raise
    assert called.get("yes")  # paste proceeded, treating None dest as empty


def test_ask_paste_conflict_maps_buttons(win, monkeypatch):
    """The dialog's Yes/No/Cancel map to overwrite/move/None."""
    results = iter([wx.ID_YES, wx.ID_NO, wx.ID_CANCEL])
    monkeypatch.setattr(wx.MessageDialog, "ShowModal", lambda self: next(results))
    monkeypatch.setattr(wx.MessageDialog, "Destroy", lambda self: None)

    assert win._ask_paste_conflict(5, 5, 1) == "overwrite"
    assert win._ask_paste_conflict(5, 7, 3) == "move"
    assert win._ask_paste_conflict(5, 5, 1) is None


def test_ask_migration_conflict_maps_buttons(win, monkeypatch):
    """Cross-image conflicts offer overwrite/skip/cancel, never make-room."""
    results = iter([wx.ID_YES, wx.ID_NO, wx.ID_CANCEL])
    monkeypatch.setattr(wx.MessageDialog, "ShowModal", lambda self: next(results))
    monkeypatch.setattr(wx.MessageDialog, "Destroy", lambda self: None)

    assert win._ask_migration_conflict(5, 5, 1) is True
    assert win._ask_migration_conflict(5, 7, 3) is False
    assert win._ask_migration_conflict(5, 5, 1) is None


def test_cross_image_copy_uses_migration_conversion(win, monkeypatch):
    """A UV-5R PowerLevel/extra object cannot be written raw to a Mini. The
    cross-document path must run CHIRP import logic first."""
    low, high = radio_backend.get_state().memory_bounds
    src = _first_nonempty(low, high)
    win.grid.select_channels([src])
    win.on_copy()
    source_name = win._clipboard.mems[0].name

    ok, message = radio_backend.load_image(MINI_IMAGE)
    assert ok, message
    win._load_into_grid()
    low, high = radio_backend.get_state().memory_bounds
    dest = _first_empty(low, high)
    assert dest is not None
    win.grid.focus_channel(dest)
    monkeypatch.setattr(
        win, "_ask_paste_conflict",
        lambda *args: pytest.fail("empty destination should not conflict"),
    )

    win.on_paste()

    pasted = radio_backend.get_memory(dest)
    assert not pasted.empty
    assert pasted.name == source_name


def test_cross_image_cut_never_erases_same_number_in_destination(win, monkeypatch):
    low, high = radio_backend.get_state().memory_bounds
    src = _first_nonempty(low, high)
    win.grid.select_channels([src])
    win.on_cut()

    ok, message = radio_backend.load_image(MINI_IMAGE)
    assert ok, message
    win._load_into_grid()
    before = radio_backend.get_memory(1).dupe()
    assert not before.empty
    low, high = radio_backend.get_state().memory_bounds
    dest = _first_empty(low, high)
    assert dest is not None and dest != 1
    win.grid.focus_channel(dest)
    monkeypatch.setattr(
        win, "_ask_paste_conflict",
        lambda *args: pytest.fail("empty destination should not conflict"),
    )

    win.on_paste()

    after = radio_backend.get_memory(1)
    assert not after.empty
    assert after.freq == before.freq
    assert win._clipboard is not None
    assert win._clipboard.mode == "copy"


def test_cross_section_cut_never_erases_same_number_in_other_side(win, monkeypatch):
    ok, message = radio_backend.load_image(FT8800_IMAGE, subdevice_index=0)
    assert ok, message
    win._load_into_grid()
    low, high = radio_backend.get_state().memory_bounds
    source = _first_nonempty(low, high)
    assert source is not None
    win.grid.select_channels([source])
    win.on_cut()

    ok, message = radio_backend.select_subdevice(1)
    assert ok, message
    win._load_into_grid()
    same_number_before = radio_backend.get_memory(source).dupe()
    destination = _first_empty(low, high)
    assert destination is not None and destination != source
    win.grid.focus_channel(destination)
    monkeypatch.setattr(
        win,
        "_ask_paste_conflict",
        lambda *args: pytest.fail("empty destination should not conflict"),
    )

    win.on_paste()

    same_number_after = radio_backend.get_memory(source)
    assert same_number_after.freq == same_number_before.freq
    assert same_number_after.name == same_number_before.name
    assert win._clipboard.mode == "copy"


def test_cross_image_skip_preserves_occupied_destination(win, monkeypatch):
    low, high = radio_backend.get_state().memory_bounds
    src = _first_nonempty(low, high)
    win.grid.select_channels([src])
    win.on_copy()

    ok, message = radio_backend.load_image(MINI_IMAGE)
    assert ok, message
    win._load_into_grid()
    low, high = radio_backend.get_state().memory_bounds
    dest = _first_nonempty(low, high)
    before = radio_backend.get_memory(dest).dupe()
    reports = []
    monkeypatch.setattr(win, "_ask_migration_conflict", lambda *args: False)
    monkeypatch.setattr(
        win, "_show_migration_report", lambda report, *args: reports.append(report)
    )
    win.grid.focus_channel(dest)

    win.on_paste()

    after = radio_backend.get_memory(dest)
    assert after.freq == before.freq and after.name == before.name
    assert reports and reports[0].occupied == 1
