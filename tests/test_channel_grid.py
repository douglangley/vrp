"""Smoke test for ChannelGrid. Skips automatically when no GUI is available."""

import os

import pytest

from chirp_backend import radio as radio_backend

wx = pytest.importorskip("wx")

IMAGE = os.path.abspath(
    os.path.join(
        os.path.dirname(__file__), "..", "chirp", "tests", "images",
        "Baofeng_BF-888.img",
    )
)


@pytest.fixture
def app():
    try:
        a = wx.App()
    except Exception:  # noqa: BLE001 — no display (headless CI)
        pytest.skip("no GUI/display available")
    yield a
    a.Destroy()


def test_grid_populates_and_maps_selection(app):
    from vrp.native.channel_grid import ChannelGrid

    radio_backend.load_image(IMAGE)
    try:
        frame = wx.Frame(None)
        grid = ChannelGrid(frame)
        grid.set_state(radio_backend.get_state())
        assert grid.GetItemCount() == 16
        assert grid.GetColumnCount() >= 2
        grid.select_channels([3, 4])
        assert grid.selected_channel_numbers() == [3, 4]
        frame.Destroy()
    finally:
        radio_backend.unload()


class _FakeKey:
    """Minimal stand-in for wx.KeyEvent for the grid key handler."""

    def __init__(self, key, shift=False, alt=False):
        self._key, self._shift, self._alt, self.skipped = key, shift, alt, False

    def GetKeyCode(self):  # noqa: N802 (wx API parity)
        return self._key

    def ShiftDown(self):  # noqa: N802 (wx API parity)
        return self._shift

    def AltDown(self):  # noqa: N802 (wx API parity)
        return self._alt

    def Skip(self):  # noqa: N802 (wx API parity)
        self.skipped = True


def test_shift_f10_routes_to_context_menu(app):
    """Shift+F10 must open the row context menu — the generic Windows
    DataViewCtrl doesn't raise the context-menu event for it, so ChannelGrid
    wires the key itself. Other keys are skipped so the cell cursor still works."""
    from vrp.native.channel_grid import ChannelGrid

    calls = []
    frame = wx.Frame(None)
    try:
        grid = ChannelGrid(frame, on_context_menu=lambda e: calls.append(e))

        shift_f10 = _FakeKey(wx.WXK_F10, shift=True)
        grid._on_grid_key(shift_f10)
        assert len(calls) == 1  # context menu opened
        assert not shift_f10.skipped  # consumed, not passed on

        # A plain F10 (no Shift) and an unrelated key must NOT open the menu and
        # must be skipped so other handlers (e.g. the Left/Right cursor) see them.
        plain_f10 = _FakeKey(wx.WXK_F10, shift=False)
        grid._on_grid_key(plain_f10)
        other = _FakeKey(ord("A"))
        grid._on_grid_key(other)
        assert len(calls) == 1  # unchanged
        assert plain_f10.skipped and other.skipped
    finally:
        frame.Destroy()


def test_toggle_focused_selection_uses_real_selection(app):
    """Space/Ctrl+Space toggles the focused row in/out of the REAL selection.
    Toggling off the only selected row must leave a real empty selection (count 0)
    — i.e. it must not use the focused-row fallback in selected_channel_numbers."""
    from vrp.native.channel_grid import ChannelGrid

    radio_backend.load_image(IMAGE)
    try:
        frame = wx.Frame(None)
        grid = ChannelGrid(frame)
        grid.set_state(radio_backend.get_state())
        grid.focus_channel(3)

        number, selected, count = grid.toggle_focused_selection()
        assert (number, selected, count) == (3, True, 1)
        assert grid.selected_count() == 1

        number2, selected2, count2 = grid.toggle_focused_selection()
        assert (number2, selected2, count2) == (3, False, 0)
        assert grid.selected_count() == 0  # really empty, not the fallback
    finally:
        radio_backend.unload()
        frame.Destroy()


def test_space_key_routes_to_select_toggle(app):
    """Space (and Ctrl+Space) invoke the toggle and the on_select_toggle callback,
    and consume the key; a bare letter is skipped."""
    from vrp.native.channel_grid import ChannelGrid

    radio_backend.load_image(IMAGE)
    try:
        toggles = []
        frame = wx.Frame(None)
        grid = ChannelGrid(frame, on_select_toggle=lambda *a: toggles.append(a))
        grid.set_state(radio_backend.get_state())
        grid.focus_channel(5)

        space = _FakeKey(wx.WXK_SPACE)
        grid._on_grid_key(space)
        assert len(toggles) == 1
        assert toggles[0] == (5, True, 1)  # (number, now_selected, total)
        assert not space.skipped  # consumed

        # Ctrl+Space (shift flag irrelevant; alt would be skipped) toggles back off.
        ctrl_space = _FakeKey(wx.WXK_SPACE)
        grid._on_grid_key(ctrl_space)
        assert toggles[-1] == (5, False, 0)

        other = _FakeKey(ord("X"))
        grid._on_grid_key(other)
        assert other.skipped  # not a handled key
    finally:
        radio_backend.unload()
        frame.Destroy()


def test_main_window_announces_ready_on_startup(app):
    from vrp.native.main_window import MainWindow

    win = MainWindow()
    try:
        # The startup announce fires on a 750ms wx.CallLater, which needs a
        # real running event loop to dispatch — wx.YieldIfNeeded() alone
        # doesn't reliably pump timer events. Run MainLoop() briefly and
        # exit it once that's had time to fire.
        wx.CallLater(900, app.ExitMainLoop)
        app.MainLoop()
        sb = win.GetStatusBar()
        assert sb is not None
        assert sb.GetStatusText(0) == "Ready"
    finally:
        win.Destroy()


def test_main_window_constructs_and_lists_channels(app):
    from vrp.native.main_window import MainWindow

    win = MainWindow()
    try:
        radio_backend.load_image(IMAGE)
        win._load_into_grid()
        assert win.grid.GetItemCount() == 16
        assert win.GetMenuBar().GetMenuCount() == 4

        # CHIRP attribution must be permanently visible in status field 1.
        sb = win.GetStatusBar()
        assert sb is not None
        assert "chirpmyradio.com" in sb.GetStatusText(1)

        # Radio menu must include a Query Source submenu.
        radio_menu = win.GetMenuBar().GetMenu(1)  # "&Radio" is index 1
        labels = [radio_menu.FindItemByPosition(i).GetItemLabel()
                  for i in range(radio_menu.GetMenuItemCount())]
        assert any("Query Source" in lbl for lbl in labels)
    finally:
        radio_backend.unload()
        win.Destroy()
