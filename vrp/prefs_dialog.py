"""Native wx Preferences dialog (app settings with a real wired effect).

Two prefs that take effect immediately:
- Channels per page (grid paging size) — a wx.Choice of known-good values.
- Speak status messages aloud — gates the prism supplemental speech. Default
  OFF: the screen reader already reads the live region, so this is opt-in extra
  speech (the label says so to avoid double-speak confusion).

Pure value collector (get_values()); the app applies + persists on OK.
"""

from __future__ import annotations

import wx

PAGE_CHOICES = [25, 50, 100, 250, 500]


class PreferencesDialog(wx.Dialog):
    def __init__(self, parent, current: dict) -> None:
        super().__init__(parent, title="Preferences")
        outer = wx.BoxSizer(wx.VERTICAL)

        grid = wx.FlexGridSizer(cols=2, vgap=8, hgap=10)
        grid.Add(wx.StaticText(self, label="Channels per page:"), 0,
                 wx.ALIGN_CENTER_VERTICAL)
        self.page = wx.Choice(self, choices=[str(n) for n in PAGE_CHOICES])
        self.page.SetName("Channels per page")
        cur = int(current.get("channels_per_page", 100))
        self.page.SetSelection(
            PAGE_CHOICES.index(cur) if cur in PAGE_CHOICES else PAGE_CHOICES.index(100)
        )
        grid.Add(self.page)
        outer.Add(grid, 0, wx.ALL, 12)

        self.speak = wx.CheckBox(
            self,
            label="Speak status messages aloud (in addition to your screen reader)",
        )
        self.speak.SetName(
            "Speak status messages aloud, in addition to your screen reader"
        )
        self.speak.SetValue(bool(current.get("speak_status_messages", False)))
        outer.Add(self.speak, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 12)

        outer.Add(self.CreateStdDialogButtonSizer(wx.OK | wx.CANCEL), 0,
                  wx.EXPAND | wx.ALL, 8)
        self.SetSizerAndFit(outer)
        self.page.SetFocus()

    def get_values(self) -> dict:
        return {
            "channels_per_page": PAGE_CHOICES[self.page.GetSelection()],
            "speak_status_messages": self.speak.GetValue(),
        }
