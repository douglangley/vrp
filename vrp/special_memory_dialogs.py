"""Accessible dialogs for explicit single-memory and special-memory import."""

from __future__ import annotations

import wx

from vrp.serial_dialogs import RadioListView


class ImportModeDialog(wx.Dialog):
    """Choose ordinary bulk import or the explicit one-memory workflow."""

    def __init__(
        self,
        parent,
        regular_count: int,
        special_count: int,
        *,
        target_has_specials: bool,
    ) -> None:
        super().__init__(parent, title="Choose what to import")
        outer = wx.BoxSizer(wx.VERTICAL)
        outer.Add(
            wx.StaticText(
                self,
                label=(
                    "Named special memories such as call channels, scan limits, "
                    "VFOs, and home channels are never included in a bulk import."
                ),
            ),
            0,
            wx.ALL,
            10,
        )
        choices = [
            f"Ordinary channels in bulk ({regular_count} programmed)",
            (
                "One memory, regular or special "
                f"({special_count} programmed specials)"
            ),
        ]
        if target_has_specials:
            choices[1] += "; may import to a named target special"
        self.mode = wx.RadioBox(
            self,
            label="Import mode",
            choices=choices,
            majorDimension=1,
            style=wx.RA_SPECIFY_ROWS,
        )
        self.mode.SetName("Import mode")
        if regular_count == 0:
            self.mode.EnableItem(0, False)
            self.mode.SetSelection(1)
        outer.Add(self.mode, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)

        buttons = self.CreateStdDialogButtonSizer(wx.OK | wx.CANCEL)
        ok = self.FindWindowById(wx.ID_OK)
        if ok:
            ok.SetLabel("Next")
        outer.Add(buttons, 0, wx.ALIGN_RIGHT | wx.ALL, 10)
        self.SetSizerAndFit(outer)
        self.SetEscapeId(wx.ID_CANCEL)
        self.mode.SetFocus()

    def get_mode(self) -> str:
        return "bulk" if self.mode.GetSelection() == 0 else "single"


class DestinationTypeDialog(wx.Dialog):
    """Choose whether one source memory goes to a number or named special."""

    def __init__(self, parent, source_label: str) -> None:
        super().__init__(parent, title="Choose destination type")
        outer = wx.BoxSizer(wx.VERTICAL)
        outer.Add(
            wx.StaticText(self, label=f"Source: {source_label}"),
            0,
            wx.ALL,
            10,
        )
        self.kind = wx.RadioBox(
            self,
            label="Destination",
            choices=["Regular numbered channel", "Named special memory"],
            majorDimension=1,
            style=wx.RA_SPECIFY_ROWS,
        )
        self.kind.SetName("Destination type")
        outer.Add(self.kind, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)
        buttons = self.CreateStdDialogButtonSizer(wx.OK | wx.CANCEL)
        ok = self.FindWindowById(wx.ID_OK)
        if ok:
            ok.SetLabel("Next")
        outer.Add(buttons, 0, wx.ALIGN_RIGHT | wx.ALL, 10)
        self.SetSizerAndFit(outer)
        self.SetEscapeId(wx.ID_CANCEL)
        self.kind.SetFocus()

    def get_destination_type(self) -> str:
        return "regular" if self.kind.GetSelection() == 0 else "special"


class MemoryPickerDialog(wx.Dialog):
    """Filter and choose one regular or special memory location."""

    def __init__(
        self,
        parent,
        locations,
        *,
        title: str,
        prompt: str,
        action_label: str,
        current_identifier=None,
    ) -> None:
        super().__init__(
            parent,
            title=title,
            style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER,
        )
        self._locations = list(locations)
        self._filtered = list(self._locations)
        self._current_identifier = current_identifier
        outer = wx.BoxSizer(wx.VERTICAL)
        outer.Add(wx.StaticText(self, label=prompt), 0, wx.ALL, 8)

        # LABEL BEFORE CONTROL — required for the accessible name on wxMSW.
        outer.Add(wx.StaticText(self, label="Filter:"), 0, wx.LEFT | wx.TOP, 8)
        self.filter = wx.TextCtrl(self)
        self.filter.SetName("Memory filter")
        outer.Add(self.filter, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 8)

        outer.Add(
            wx.StaticText(self, label="Memory:"),
            0,
            wx.LEFT | wx.TOP,
            8,
        )
        self.list = RadioListView(
            self,
            name="Memory",
            on_select=self._update_ok,
            size=(500, 260),
        )
        self.list.Set([location.label for location in self._filtered])
        self._select_current()
        outer.Add(self.list, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 8)

        self.count = wx.StaticText(
            self, label=self._count_label(len(self._filtered))
        )
        self.count.SetName("Memory count")
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
        return "1 memory matches" if count == 1 else f"{count} memories match"

    def _select_current(self) -> None:
        if self._current_identifier is None:
            return
        for row, location in enumerate(self._filtered):
            if location.identifier == self._current_identifier:
                self.list.SetSelection(row)
                return

    def _apply_filter(self) -> None:
        text = self.filter.GetValue().strip().lower()
        self._filtered = (
            [
                location
                for location in self._locations
                if text in location.label.lower()
            ]
            if text
            else list(self._locations)
        )
        self.list.Set([location.label for location in self._filtered])
        self._select_current()
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
            ok.Enable(self.get_selection() is not None)

    def get_selection(self):
        row = self.list.GetSelection()
        if 0 <= row < len(self._filtered):
            return self._filtered[row]
        return None
