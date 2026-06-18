"""Native wx Find dialog (Phase 3).

Find is navigation, not mutation: the user types text, picks which field(s) to
search, and is taken to the first matching channel; Ctrl+G steps to the next
match (the backend wraps around). A native dialog gives clean NVDA typing and
avoids the WebView2 find-bar.

The dialog stays open if the text is empty or nothing matches, so the user can
refine without reopening. On OK it calls ``on_search(query, fields) -> bool``
(supplied by the app, which performs the find + jump) and only closes when a
match is found.
"""

from __future__ import annotations

import wx

# (visible label, search_fields tuple passed to memory_ops.find)
FIELD_CHOICES = [
    ("All fields", ("freq", "name", "comment")),
    ("Name", ("name",)),
    ("Frequency", ("freq",)),
    ("Comment", ("comment",)),
]


class FindDialog(wx.Dialog):
    def __init__(self, parent, on_search) -> None:
        super().__init__(parent, title="Find channel")
        self._on_search = on_search

        outer = wx.BoxSizer(wx.VERTICAL)
        grid = wx.FlexGridSizer(cols=2, vgap=6, hgap=8)
        grid.AddGrowableCol(1, 1)

        self.text = wx.TextCtrl(self)
        self.text.SetName("Find text")
        self.field = wx.Choice(self, choices=[label for label, _f in FIELD_CHOICES])
        self.field.SetSelection(0)
        self.field.SetName("Search in")

        grid.Add(wx.StaticText(self, label="Find:"), 0, wx.ALIGN_CENTER_VERTICAL)
        grid.Add(self.text, 0, wx.EXPAND)
        grid.Add(wx.StaticText(self, label="Search in:"), 0, wx.ALIGN_CENTER_VERTICAL)
        grid.Add(self.field)
        outer.Add(grid, 0, wx.EXPAND | wx.ALL, 12)

        self.status = wx.StaticText(self, label="")
        self.status.SetName("Find status")
        outer.Add(self.status, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 12)

        buttons = self.CreateStdDialogButtonSizer(wx.OK | wx.CANCEL)
        ok = self.FindWindowById(wx.ID_OK)
        if ok:
            ok.SetLabel("Find")
        outer.Add(buttons, 0, wx.EXPAND | wx.ALL, 8)

        self.SetSizerAndFit(outer)
        self.Bind(wx.EVT_BUTTON, self._on_ok, id=wx.ID_OK)
        self.text.SetFocus()

    def fields(self) -> tuple:
        return FIELD_CHOICES[self.field.GetSelection()][1]

    def _on_ok(self, event: wx.CommandEvent) -> None:
        query = self.text.GetValue().strip()
        if not query:
            self.status.SetLabel("Enter text to find.")
            self.text.SetFocus()
            return
        if self._on_search(query, self.fields()):
            event.Skip()  # match found → close
            return
        message = f"'{query}' not found."
        self.status.SetLabel(message)
        wx.MessageBox(message, "Find", wx.OK | wx.ICON_INFORMATION, self)
        self.text.SetFocus()
