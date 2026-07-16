"""Entry for the native wxPython UI."""

from __future__ import annotations

import logging


def run(debug: bool = False) -> None:
    import wx

    from vrp.native.main_window import MainWindow

    logging.basicConfig(level=logging.DEBUG if debug else logging.INFO)
    app = wx.App()
    win = MainWindow()
    win.Show()
    # Queued rather than called: it runs once MainLoop is going and the frame is
    # actually on screen, so the welcome dialog has a shown parent to be modal
    # against and focus returns to a live grid when it closes.
    wx.CallAfter(win.maybe_show_welcome)
    app.MainLoop()
