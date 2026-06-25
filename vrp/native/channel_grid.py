"""The native channel grid: a wx.dataview.DataViewListCtrl.

``DataViewListCtrl`` wraps a real native control on each platform, so screen
readers read it for free: SysListView32 on Windows (NVDA) and, crucially,
``NSTableView`` on macOS (VoiceOver). The previous ``wx.ListCtrl`` in report
mode falls back to wx's *generic* (custom-drawn) implementation on macOS, which
exposes no rows/cells to NSAccessibility and was silent under VoiceOver — see
docs/research/2026-06-24-native-grid-voiceover-feasibility.md.

Editing is done in a separate dialog (edit_dialog.py), so every column is
read-only/inert here and the grid is purely navigable. All index/number/
selection math stays in grid_model; this class is just the widget shell +
selection/focus helpers. Rows are addressed by their 0-based position, which
matches the order of ``self._rows``.
"""

from __future__ import annotations

import wx
import wx.dataview as dv

from chirp_backend import radio as radio_backend
from vrp.native import grid_model

_WIDTH = {"narrow": 90, "wide": 200, "auto": 130}


class ChannelGrid(dv.DataViewListCtrl):
    def __init__(self, parent) -> None:
        super().__init__(parent, style=dv.DV_MULTIPLE | dv.DV_ROW_LINES)
        self.SetName("Memory channels")
        self._cols: list[dict] = []
        self._rows: list[dict] = []

    # -- population ----------------------------------------------------
    def set_state(self, state) -> None:
        """(Re)build columns and rows for the loaded radio."""
        self.ClearColumns()
        self.DeleteAllItems()
        self._cols = grid_model.column_meta(state)
        for col in self._cols:
            self.AppendTextColumn(
                col["label"], width=_WIDTH.get(col["width_hint"], 130)
            )
        self._rows = grid_model.build_rows(state)
        for row in self._rows:
            self.AppendItem(
                [grid_model.cell_text(row, c["name"]) for c in self._cols]
            )

    def clear(self) -> None:
        self.DeleteAllItems()
        self.ClearColumns()
        self._cols, self._rows = [], []

    # -- selection / focus --------------------------------------------
    def _current_row(self) -> int | None:
        """0-based row of the focused (current) item, or None."""
        item = self.GetCurrentItem()
        if not item.IsOk():
            return None
        row = self.ItemToRow(item)
        return row if row != wx.NOT_FOUND else None

    def selected_channel_numbers(self) -> list[int]:
        """Selected channels; falls back to the focused row when none selected."""
        nums = []
        for item in self.GetSelections():
            row = self.ItemToRow(item)
            if row != wx.NOT_FOUND:
                nums.append(grid_model.index_to_number(self._rows, row))
        if not nums:
            row = self._current_row()
            if row is not None:
                nums = [grid_model.index_to_number(self._rows, row)]
        return sorted(nums)

    def focused_channel(self) -> int | None:
        row = self._current_row()
        if row is None:
            return None
        return grid_model.index_to_number(self._rows, row)

    def selected_count(self) -> int:
        """Number of selected rows (DataView's GetSelectedItemsCount)."""
        return self.GetSelectedItemsCount()

    def select_channels(self, numbers: list[int]) -> None:
        """Replace the selection with exactly ``numbers``."""
        self.UnselectAll()
        for n in numbers:
            idx = grid_model.number_to_index(self._rows, n)
            if idx is not None:
                self.SelectRow(idx)

    def focus_channel(self, number: int) -> None:
        """Move the focused (current) row to ``number`` so the screen reader reads it.

        Also takes keyboard focus to the grid if it doesn't already have it — a
        row is only announced when its control has system focus. ``SetCurrentItem``
        moves the focus cursor without changing the selection, so callers that
        want a row both selected AND read pair this with ``select_channels``
        (Go to / Find / post-edit return / post-move block restore).
        """
        idx = grid_model.number_to_index(self._rows, number)
        if idx is None:
            return
        # Make the target the current item BEFORE focus arrives: if we called
        # SetFocus() first, the screen reader would announce whatever row was
        # already current (stale/row 0), then announce again after SetCurrentItem
        # — a double/wrong announcement on Go-to / Find / post-edit / post-move.
        item = self.RowToItem(idx)
        self.SetCurrentItem(item)
        self.EnsureVisible(item)
        if wx.Window.FindFocus() is not self:
            self.SetFocus()

    def popup_row_menu(self, menu: wx.Menu) -> None:
        """Show a row context menu. Pixel position is irrelevant to a
        screen-reader user; wx anchors it sensibly on the focused row."""
        self.PopupMenu(menu)

    # -- refresh after edits/ops --------------------------------------
    def refresh_numbers(self, numbers: list[int]) -> None:
        """Rebuild the row dicts for ``numbers`` and update just those cells.

        Updating cell values in place (vs. a full rebuild) keeps the control and
        the screen-reader focus position intact.
        """
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
            for col_index, c in enumerate(self._cols):
                self.SetTextValue(
                    grid_model.cell_text(self._rows[idx], c["name"]), idx, col_index
                )

    def reorder_refresh(self) -> None:
        """Refresh row contents/order after a reorder WITHOUT rebuilding columns.

        A move/sort changes which channel is in each slot but not the column set
        or the row count, so we update each cell in place (no DeleteAllItems that
        would drop screen-reader focus). Falls back to a full rebuild if the row
        count changed unexpectedly.
        """
        state = radio_backend.get_state()
        if not state.loaded:
            return
        new_rows = grid_model.build_rows(state)
        if len(new_rows) != self.GetItemCount():
            self.set_state(state)
            return
        self._rows = new_rows
        for idx, row in enumerate(self._rows):
            for col_index, c in enumerate(self._cols):
                self.SetTextValue(
                    grid_model.cell_text(row, c["name"]), idx, col_index
                )

    def rebuild(self) -> None:
        """Full rebuild after a structural op (move/delete/insert/sort)."""
        state = radio_backend.get_state()
        if state.loaded:
            self.set_state(state)
