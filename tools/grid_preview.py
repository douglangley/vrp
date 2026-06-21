"""Preview the new accessible channel grid against a real CHIRP radio image.

This is a focused test harness for `wx-accessible-grid` inside VRP, decoupled
from the full app: it loads a radio image (a CHIRP test image by default, no
hardware needed) and shows the memory channels in an editable ARIA grid backed
by `vrp.channel_grid_model.ChannelGridModel`.

Run it with a screen reader (NVDA on Windows is the real target):

    uv run python tools/grid_preview.py
    uv run python tools/grid_preview.py path/to/radio.img

Try: arrow around (across a row speaks the column, down a column speaks the
channel number), F2 or Enter to edit a cell, Enter to commit / Escape to cancel,
Space to select a row, Delete to delete, the Applications key for the row menu.
"""

from __future__ import annotations

import os
import sys

import vrp  # noqa: F401  (side effect: makes the vendored chirp importable)
import wx

from wx_accessible_grid import AccessibleGrid

from chirp_backend import radio as radio_backend
from vrp.channel_grid_model import ChannelGridModel

DEFAULT_IMAGE = os.path.join(
    os.path.dirname(__file__), "..", "chirp", "tests", "images", "Baofeng_UV-5R.img"
)


class PreviewFrame(wx.Frame):
    def __init__(self, image_path: str) -> None:
        ok, message = radio_backend.load_image(image_path)
        state = radio_backend.get_state()
        radio_name = (
            f"{state.radio.VENDOR} {state.radio.MODEL}" if ok and state.loaded else "(no radio)"
        )
        super().__init__(None, title=f"VRP grid preview — {radio_name}", size=(1100, 650))
        if not ok:
            wx.MessageBox(message, "Could not load image", wx.OK | wx.ICON_ERROR)
            wx.CallAfter(self.Close)
            return

        panel = wx.Panel(self)
        self.model = ChannelGridModel()
        self.grid = AccessibleGrid(
            panel,
            self.model,
            label=f"{radio_name} memory channels",
            page_size=100,
            row_select=True,
            on_context=self._on_context,
            description="Arrow to move, F2 or Enter to edit, Space to select, Delete to delete.",
        )
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(self.grid.control, 1, wx.EXPAND)
        panel.SetSizer(sizer)
        self.Show()
        wx.CallAfter(self.grid.focus)

    def _on_context(self, row: int, column: str) -> None:
        number = self.model.row_label(row)
        menu = wx.Menu()
        delete = menu.Append(wx.ID_ANY, f"Delete channel {number}\tDel")
        self.Bind(
            wx.EVT_MENU,
            lambda _e: (self.model.delete_rows([row]), self.grid.refresh()),
            delete,
        )
        self.grid.control.PopupMenu(menu)
        menu.Destroy()


def main() -> None:
    image = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_IMAGE
    app = wx.App()
    PreviewFrame(os.path.abspath(image))
    app.MainLoop()


if __name__ == "__main__":
    main()
