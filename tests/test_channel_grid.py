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
