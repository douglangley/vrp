"""Accessible dialogs for explicit source-bank to destination-bank mapping."""

from __future__ import annotations

import wx

from chirp_backend import bank_ops
from vrp.serial_dialogs import RadioListView


class BankPickerDialog(wx.Dialog):
    """Filter and choose one destination bank."""

    def __init__(self, parent, banks, *, current_index=None) -> None:
        super().__init__(
            parent,
            title="Choose destination bank",
            style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER,
        )
        self._banks = list(banks)
        self._filtered = list(self._banks)
        self._current_index = current_index

        outer = wx.BoxSizer(wx.VERTICAL)
        outer.Add(
            wx.StaticText(
                self,
                label="Choose the exact destination bank for the selected source bank.",
            ),
            0,
            wx.ALL,
            8,
        )
        outer.Add(wx.StaticText(self, label="Filter:"), 0, wx.LEFT | wx.TOP, 8)
        self.filter = wx.TextCtrl(self)
        self.filter.SetName("Destination bank filter")
        outer.Add(self.filter, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 8)

        outer.Add(
            wx.StaticText(self, label="Destination bank:"),
            0,
            wx.LEFT | wx.TOP,
            8,
        )
        self.list = RadioListView(
            self,
            name="Destination bank",
            on_select=self._update_ok,
            size=(480, 260),
        )
        self.list.Set([bank.label for bank in self._filtered])
        self._select_current()
        outer.Add(self.list, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 8)

        self.count = wx.StaticText(self, label=self._count_label(len(self._filtered)))
        self.count.SetName("Destination bank count")
        outer.Add(self.count, 0, wx.ALL, 8)

        buttons = self.CreateStdDialogButtonSizer(wx.OK | wx.CANCEL)
        ok = self.FindWindowById(wx.ID_OK)
        if ok:
            ok.SetLabel("Map")
        outer.Add(buttons, 0, wx.ALIGN_RIGHT | wx.ALL, 8)
        self.SetSizerAndFit(outer)
        self.SetEscapeId(wx.ID_CANCEL)

        self.filter.Bind(wx.EVT_TEXT, lambda _event: self._apply_filter())
        self.filter.Bind(wx.EVT_KEY_DOWN, self._on_filter_key)
        self._update_ok()
        self.filter.SetFocus()

    @staticmethod
    def _count_label(count: int) -> str:
        return "1 bank matches" if count == 1 else f"{count} banks match"

    def _select_current(self) -> None:
        if self._current_index is None:
            return
        for row, bank in enumerate(self._filtered):
            if bank.index == self._current_index:
                self.list.SetSelection(row)
                return

    def _apply_filter(self) -> None:
        query = self.filter.GetValue().strip().casefold()
        self._filtered = (
            [bank for bank in self._banks if query in bank.label.casefold()]
            if query
            else list(self._banks)
        )
        self.list.Set([bank.label for bank in self._filtered])
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


class BankMappingDialog(wx.Dialog):
    """Review and explicitly confirm mappings for the used source banks."""

    def __init__(
        self,
        parent,
        source_banks,
        target_banks,
        *,
        initial_mapping=None,
    ) -> None:
        super().__init__(
            parent,
            title="Map source banks",
            style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER,
        )
        self._source_banks = list(source_banks)
        self._visible = list(self._source_banks)
        self._target_banks = list(target_banks)
        self._targets_by_index = {
            bank.index: bank for bank in self._target_banks
        }
        self._mapping = dict(initial_mapping or {})

        outer = wx.BoxSizer(wx.VERTICAL)
        outer.Add(
            wx.StaticText(
                self,
                label=(
                    "Map each used source bank or leave it as Do not import. "
                    "For every successfully imported channel, the mapped banks "
                    "replace existing destination memberships. The channel and "
                    "bank changes are one Undo step."
                ),
            ),
            0,
            wx.ALL,
            8,
        )
        outer.Add(wx.StaticText(self, label="Filter:"), 0, wx.LEFT | wx.TOP, 8)
        self.filter = wx.TextCtrl(self)
        self.filter.SetName("Source bank filter")
        outer.Add(self.filter, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 8)

        outer.Add(
            wx.StaticText(self, label="Source bank mappings:"),
            0,
            wx.LEFT | wx.TOP,
            8,
        )
        self.list = RadioListView(
            self,
            name="Source bank mappings",
            on_select=self._update_buttons,
            size=(600, 280),
        )
        outer.Add(self.list, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 8)

        self.count = wx.StaticText(self, label="")
        self.count.SetName("Source bank mapping count")
        outer.Add(self.count, 0, wx.LEFT | wx.RIGHT | wx.TOP, 8)

        row = wx.BoxSizer(wx.HORIZONTAL)
        self.map_button = wx.Button(self, label="Map selected…")
        self.skip_button = wx.Button(self, label="Do not import selected")
        row.Add(self.map_button, 0, wx.RIGHT, 6)
        row.Add(self.skip_button, 0)
        outer.Add(row, 0, wx.ALL, 8)

        bulk = wx.BoxSizer(wx.HORIZONTAL)
        self.names_button = wx.Button(self, label="Match exact names")
        self.positions_button = wx.Button(self, label="Match by position")
        self.clear_button = wx.Button(self, label="Clear all mappings")
        bulk.Add(self.names_button, 0, wx.RIGHT, 6)
        bulk.Add(self.positions_button, 0, wx.RIGHT, 6)
        bulk.Add(self.clear_button, 0)
        outer.Add(bulk, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)

        buttons = self.CreateStdDialogButtonSizer(wx.OK | wx.CANCEL)
        ok = self.FindWindowById(wx.ID_OK)
        if ok:
            ok.SetLabel("Import with bank mapping")
        outer.Add(buttons, 0, wx.ALIGN_RIGHT | wx.ALL, 8)

        self.SetSizerAndFit(outer)
        self.SetEscapeId(wx.ID_CANCEL)
        self.filter.Bind(wx.EVT_TEXT, lambda _event: self._apply_filter())
        self.filter.Bind(wx.EVT_KEY_DOWN, self._on_filter_key)
        self.map_button.Bind(wx.EVT_BUTTON, self._on_map_selected)
        self.skip_button.Bind(
            wx.EVT_BUTTON, lambda _event: self.clear_selected()
        )
        self.names_button.Bind(wx.EVT_BUTTON, lambda _event: self.match_names())
        self.positions_button.Bind(
            wx.EVT_BUTTON, lambda _event: self.match_positions()
        )
        self.clear_button.Bind(wx.EVT_BUTTON, lambda _event: self.clear_all())
        self._refresh_rows()
        self.filter.SetFocus()

    def _row_label(self, source) -> str:
        target_index = self._mapping.get(source.position)
        target = self._targets_by_index.get(target_index)
        destination = target.label if target is not None else "Do not import"
        count = source.member_count
        usage = "1 selected channel" if count == 1 else f"{count} selected channels"
        return f"{source.label} — {usage} — maps to {destination}"

    def _refresh_rows(self, *, keep_position=None) -> None:
        self.list.Set([self._row_label(bank) for bank in self._visible])
        if keep_position is not None:
            for row, bank in enumerate(self._visible):
                if bank.position == keep_position:
                    self.list.SetSelection(row)
                    break
        mapped = sum(
            source.position in self._mapping for source in self._source_banks
        )
        self.count.SetLabel(
            f"{len(self._visible)} shown; {mapped} of "
            f"{len(self._source_banks)} source banks mapped."
        )
        self._update_buttons()

    def _selected_source(self):
        row = self.list.GetSelection()
        if 0 <= row < len(self._visible):
            return self._visible[row]
        return None

    def _apply_filter(self) -> None:
        query = self.filter.GetValue().strip().casefold()
        self._visible = (
            [
                bank
                for bank in self._source_banks
                if query in self._row_label(bank).casefold()
            ]
            if query
            else list(self._source_banks)
        )
        self._refresh_rows()

    def _on_filter_key(self, event) -> None:
        if event.GetKeyCode() == wx.WXK_DOWN and self._visible:
            self.list.SetFocus()
            if self.list.GetSelection() == wx.NOT_FOUND:
                self.list.SetSelection(0)
        else:
            event.Skip()

    def _update_buttons(self) -> None:
        selected = self._selected_source()
        self.map_button.Enable(selected is not None)
        self.skip_button.Enable(
            selected is not None and selected.position in self._mapping
        )

    def _on_map_selected(self, _event) -> None:
        source = self._selected_source()
        if source is None:
            return
        picker = BankPickerDialog(
            self,
            self._target_banks,
            current_index=self._mapping.get(source.position),
        )
        try:
            if picker.ShowModal() == wx.ID_OK:
                target = picker.get_selection()
                if target is not None:
                    self.map_selected_to(target.index)
        finally:
            picker.Destroy()

    def map_selected_to(self, target_index) -> None:
        source = self._selected_source()
        if source is None or target_index not in self._targets_by_index:
            return
        self._mapping[source.position] = target_index
        self._refresh_rows(keep_position=source.position)

    def clear_selected(self) -> None:
        source = self._selected_source()
        if source is None:
            return
        self._mapping.pop(source.position, None)
        self._refresh_rows(keep_position=source.position)

    def match_names(self) -> None:
        self._mapping.update(
            bank_ops.suggest_name_mapping(
                self._source_banks, self._target_banks
            )
        )
        self._refresh_rows()

    def match_positions(self) -> None:
        self._mapping.update(
            bank_ops.suggest_position_mapping(
                self._source_banks, self._target_banks
            )
        )
        self._refresh_rows()

    def clear_all(self) -> None:
        self._mapping.clear()
        self._refresh_rows()

    def get_mapping(self) -> dict[int, object]:
        return dict(self._mapping)
