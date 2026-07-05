"""Native wx dialog for choosing where imported channels land.

ImportDestinationDialog chooses the destination channel for a block of imported
memories and how to treat occupied channels; the import itself goes through
memory_ops.import_memories. Shared by the "Import from File" flow.
"""

from __future__ import annotations

import wx


class ImportDestinationDialog(wx.Dialog):
    def __init__(self, parent, count: int, low: int, high: int, default_dest: int) -> None:
        super().__init__(parent, title="Import channels")
        outer = wx.BoxSizer(wx.VERTICAL)
        outer.Add(
            wx.StaticText(self, label=f"{count} result(s) ready to import."),
            0, wx.ALL, 10,
        )

        row = wx.BoxSizer(wx.HORIZONTAL)
        row.Add(wx.StaticText(self, label="Start at channel:"), 0,
                wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 6)
        self.dest = wx.SpinCtrl(self, min=low, max=high, initial=default_dest)
        self.dest.SetName("Start at channel")
        row.Add(self.dest)
        outer.Add(row, 0, wx.ALL, 10)

        self.mode = wx.RadioBox(
            self, label="If a destination channel already has data",
            choices=["Overwrite it", "Skip it"],
            majorDimension=1, style=wx.RA_SPECIFY_COLS,
        )
        outer.Add(self.mode, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)

        buttons = self.CreateStdDialogButtonSizer(wx.OK | wx.CANCEL)
        ok = self.FindWindowById(wx.ID_OK)
        if ok:
            ok.SetLabel("Import")
        outer.Add(buttons, 0, wx.EXPAND | wx.ALL, 8)
        self.SetSizerAndFit(outer)

    def get_destination(self) -> int:
        return self.dest.GetValue()

    def get_overwrite(self) -> bool:
        return self.mode.GetSelection() == 0
