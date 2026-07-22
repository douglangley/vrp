"""Accessible chooser for a radio image's memory sections."""

from __future__ import annotations

import wx

from vrp.serial_dialogs import RadioListView


class SubdeviceDialog(wx.Dialog):
    """Pick one CHIRP sub-device using the app's native screen-reader list."""

    def __init__(
        self,
        parent,
        labels,
        *,
        title: str = "Choose memory section",
        action_label: str = "Open",
        current_index: int = 0,
    ) -> None:
        super().__init__(
            parent,
            title=title,
            style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER,
        )
        self._choices = list(enumerate(labels))
        self._filtered = list(self._choices)
        self._current_index = current_index

        outer = wx.BoxSizer(wx.VERTICAL)
        outer.Add(
            wx.StaticText(
                self,
                label="This radio image has more than one memory section.",
            ),
            0,
            wx.ALL,
            8,
        )

        # LABEL BEFORE CONTROL — wxMSW uses this adjacency for the accessible
        # name exposed to NVDA/JAWS.
        outer.Add(wx.StaticText(self, label="Filter:"), 0, wx.LEFT | wx.TOP, 8)
        self.filter = wx.TextCtrl(self)
        self.filter.SetName("Memory section filter")
        outer.Add(self.filter, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 8)

        outer.Add(
            wx.StaticText(self, label="Memory section:"),
            0,
            wx.LEFT | wx.TOP,
            8,
        )
        self.list = RadioListView(
            self,
            name="Memory section",
            on_select=self._update_ok,
            size=(420, 220),
        )
        self.list.Set([label for _index, label in self._filtered])
        if 0 <= current_index < len(self._choices):
            self.list.SetSelection(current_index)
        outer.Add(self.list, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 8)

        self.count = wx.StaticText(
            self, label=self._count_label(len(self._filtered))
        )
        self.count.SetName("Memory section count")
        outer.Add(self.count, 0, wx.ALL, 8)

        buttons = self.CreateStdDialogButtonSizer(wx.OK | wx.CANCEL)
        ok = self.FindWindowById(wx.ID_OK)
        if ok:
            ok.SetLabel(action_label)
        outer.Add(buttons, 0, wx.ALIGN_RIGHT | wx.ALL, 8)

        self.SetSizerAndFit(outer)
        self.SetEscapeId(wx.ID_CANCEL)
        self.filter.Bind(wx.EVT_TEXT, lambda _event: self._apply_filter())
        self.filter.Bind(wx.EVT_KEY_DOWN, self._on_filter_key)
        self._update_ok()
        self.filter.SetFocus()

    @staticmethod
    def _count_label(count: int) -> str:
        return "1 section matches" if count == 1 else f"{count} sections match"

    def _apply_filter(self) -> None:
        text = self.filter.GetValue().strip().lower()
        self._filtered = (
            [choice for choice in self._choices if text in choice[1].lower()]
            if text
            else list(self._choices)
        )
        self.list.Set([label for _index, label in self._filtered])
        for row, (index, _label) in enumerate(self._filtered):
            if index == self._current_index:
                self.list.SetSelection(row)
                break
        self.count.SetLabel(self._count_label(len(self._filtered)))
        self._update_ok()

    def _on_filter_key(self, event) -> None:
        if event.GetKeyCode() == wx.WXK_DOWN and self._filtered:
            self.list.SetFocus()
            if self.list.GetSelection() == wx.NOT_FOUND:
                self.list.SetSelection(0)
        else:
            event.Skip()

    def _update_ok(self) -> None:
        ok = self.FindWindowById(wx.ID_OK)
        if ok:
            ok.Enable(self.get_index() is not None)

    def get_index(self) -> int | None:
        """Return the original section index selected after filtering."""
        row = self.list.GetSelection()
        if 0 <= row < len(self._filtered):
            return self._filtered[row][0]
        return None
