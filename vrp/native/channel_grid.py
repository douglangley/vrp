"""The native channel grid: a virtual report-mode wx.ListCtrl.

Virtual (LC_VIRTUAL) so population is instant at any radio size and there is no
paging. Multi-select is on by default. All index/number/selection math is in
grid_model; this class is just the wx widget shell + selection/focus helpers.
"""

from __future__ import annotations

import wx

from chirp_backend import radio as radio_backend
from vrp.native import grid_model

_WIDTH = {"narrow": 90, "wide": 200, "auto": 130}


class ChannelGrid(wx.ListCtrl):
    def __init__(self, parent) -> None:
        super().__init__(
            parent, style=wx.LC_REPORT | wx.LC_VIRTUAL | wx.LC_HRULES
        )
        self.SetName("Memory channels")
        self._cols: list[dict] = []
        self._rows: list[dict] = []

    # -- population ----------------------------------------------------
    def set_state(self, state) -> None:
        """(Re)build columns and rows for the loaded radio."""
        self.ClearAll()
        self._cols = grid_model.column_meta(state)
        for i, col in enumerate(self._cols):
            self.InsertColumn(i, col["label"], width=_WIDTH.get(col["width_hint"], 130))
        self._rows = grid_model.build_rows(state)
        self.SetItemCount(len(self._rows))
        self.Refresh()

    def clear(self) -> None:
        self.ClearAll()
        self._cols, self._rows = [], []
        self.SetItemCount(0)

    # wx virtual-list callback: text for (row item, column).
    def OnGetItemText(self, item: int, column: int) -> str:  # noqa: N802 (wx API)
        return grid_model.cell_text(self._rows[item], self._cols[column]["name"])

    # -- selection / focus --------------------------------------------
    def selected_channel_numbers(self) -> list[int]:
        """Selected channels; falls back to the focused row when none selected."""
        nums, item = [], self.GetFirstSelected()
        while item != -1:
            nums.append(grid_model.index_to_number(self._rows, item))
            item = self.GetNextSelected(item)
        if not nums:
            focused = self.GetFocusedItem()
            if focused != -1:
                nums = [grid_model.index_to_number(self._rows, focused)]
        return sorted(nums)

    def focused_channel(self) -> int | None:
        item = self.GetFocusedItem()
        if item == -1:
            return None
        return grid_model.index_to_number(self._rows, item)

    def select_channels(self, numbers: list[int]) -> None:
        """Replace the selection with exactly ``numbers``."""
        item = self.GetFirstSelected()
        while item != -1:
            nxt = self.GetNextSelected(item)
            self.Select(item, on=False)
            item = nxt
        for n in numbers:
            idx = grid_model.number_to_index(self._rows, n)
            if idx is not None:
                self.Select(idx, on=True)

    def focus_channel(self, number: int) -> None:
        """Move the focused row to ``number`` and ensure the screen reader reads it.

        Also takes keyboard focus to the grid if it doesn't already have it —
        a list item is only announced by NVDA/VoiceOver when its control has
        system focus. Callers that want a single row both selected AND read
        (Go to channel, Find, post-edit return) should pair this with
        ``select_channels([number])``; callers restoring a multi-row block
        (after a move) call ``select_channels(block)`` then ``focus_channel(first)``.
        """
        idx = grid_model.number_to_index(self._rows, number)
        if idx is None:
            return
        if wx.Window.FindFocus() is not self:
            self.SetFocus()
        self.Focus(idx)
        self.EnsureVisible(idx)

    # -- refresh after edits/ops --------------------------------------
    def refresh_numbers(self, numbers: list[int]) -> None:
        """Rebuild the row dicts for ``numbers`` and repaint just those items."""
        from chirp_backend.col_defs import build_column_defs

        cols = build_column_defs(radio_backend.get_state().features)
        for n in numbers:
            idx = grid_model.number_to_index(self._rows, n)
            mem = radio_backend.get_memory(n)
            if idx is None or mem is None:
                continue
            empty = bool(getattr(mem, "empty", False))
            cells = {}
            for col in cols:
                cells[col.name] = (
                    str(n) if col.name == "number"
                    else ("" if empty else col.format_value(mem))
                )
            self._rows[idx] = {
                "number": n, "empty": empty,
                "immutable": list(getattr(mem, "immutable", []) or []),
                "cells": cells,
            }
            self.RefreshItem(idx)

    def reorder_refresh(self) -> None:
        """Refresh row contents/order after a reorder WITHOUT rebuilding columns.

        A move/sort changes which channel is in each slot but not the column
        set, so we keep the columns (avoiding a ClearAll that drops screen-reader
        focus) and just rebuild the row model + repaint.
        """
        state = radio_backend.get_state()
        if not state.loaded:
            return
        self._rows = grid_model.build_rows(state)
        self.SetItemCount(len(self._rows))
        if self._rows:
            self.RefreshItems(0, len(self._rows) - 1)

    def rebuild(self) -> None:
        """Full rebuild after a structural op (move/delete/insert/sort)."""
        state = radio_backend.get_state()
        if state.loaded:
            self.set_state(state)
