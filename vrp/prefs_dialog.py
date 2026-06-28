"""Native wx Preferences dialog (app settings with a real wired effect).

Prefs that take effect immediately:
- Recently opened files to show — a wx.Choice of 0..9. 0 hides the File >
  Open Recent submenu; 1..9 shows that many recent files.
- Speak status messages aloud — gates the prism supplemental speech. Default
  OFF: the screen reader already reads the live region, so this is opt-in extra
  speech (the label says so to avoid double-speak confusion).

Pure value collector (get_values()); the app applies + persists on OK.
"""

from __future__ import annotations

import wx

RECENT_COUNT_CHOICES = list(range(10))  # 0..9; 0 hides the Recent submenu


class PreferencesDialog(wx.Dialog):
    def __init__(self, parent, current: dict) -> None:
        super().__init__(parent, title="Preferences")
        outer = wx.BoxSizer(wx.VERTICAL)

        grid = wx.FlexGridSizer(cols=2, vgap=8, hgap=10)
        grid.Add(wx.StaticText(self, label="Recently opened files to show:"), 0,
                 wx.ALIGN_CENTER_VERTICAL)
        self.recent_count = wx.Choice(
            self, choices=[str(n) for n in RECENT_COUNT_CHOICES]
        )
        self.recent_count.SetName("Recently opened files to show, 0 to 9, 0 hides the menu")
        cur_recent = current.get("recent_files_count", 9)
        try:
            cur_recent = int(cur_recent)
        except (TypeError, ValueError):
            cur_recent = 9
        cur_recent = max(0, min(9, cur_recent))
        self.recent_count.SetSelection(cur_recent)  # choices are 0..9, so index == value
        grid.Add(self.recent_count)

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
        self.recent_count.SetFocus()

    def get_values(self) -> dict:
        return {
            "recent_files_count": self.recent_count.GetSelection(),  # index == value (0..9)
            "speak_status_messages": self.speak.GetValue(),
        }
