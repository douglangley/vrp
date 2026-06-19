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
    app.MainLoop()
