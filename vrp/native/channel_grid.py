"""The native channel grid, built on wx-accessible-grid's ``AccessibleGrid``.

``AccessibleGrid`` (>=0.7.0) wraps a ``wx.dataview.DataViewListCtrl`` — a real
native table on every platform, so screen readers read it directly: it wraps
``NSTableView`` on macOS (VoiceOver reads the row *and each cell by column*, e.g.
"Frequency, 146.520") and the native list view on Windows/GTK for NVDA/JAWS/Orca.
No WebView, HTML, or JS in the path. (The library's brief 0.5.x virtual
``wx.ListCtrl`` backend was silent under VoiceOver — wx's report-mode ListCtrl
falls back to a generic custom-drawn control on macOS — which is why it rebased
onto DataViewListCtrl.)

The grid is row-oriented; editing is host-driven: read the selection, edit
through a native dialog (edit_dialog.py), then refresh the affected rows. Every
column is therefore read-only/navigable here. All index/number/selection math
stays in grid_model; this module is the widget shell plus the model adapter.

``ChannelGrid`` is a ``wx.Panel`` that owns one ``AccessibleGrid`` for its whole
life: a changed column set (a new radio) is applied in place with the library's
``set_columns()``, and row edits with ``refresh``/``refresh_rows`` — both keep
the control and the screen reader's focus. Rows are addressed by their 0-based
position, matching ``model.rows``.
"""

from __future__ import annotations

import wx
import wx.dataview as dv

from chirp_backend import radio as radio_backend
from chirp_backend.col_defs import build_column_defs
from wx_accessible_grid import AUTO, WIDE, NARROW, AccessibleGrid, Column, GridModel
from vrp.native import grid_model

_HINTS = {NARROW, WIDE, AUTO}
_LABEL = "Memory channels"


class _ChannelGridModel(GridModel):
    """Adapts the pure ``grid_model`` row/column data to the library's model.

    Holds the same row dicts ``grid_model.build_rows`` produces and answers the
    grid's per-cell ``cell_text`` calls from them. ``set_data`` swaps the columns
    and rows wholesale (radio load); the host mutates ``rows`` in place for
    per-row/structural refreshes.
    """

    def __init__(self) -> None:
        self._cols: list[Column] = []
        self.rows: list[dict] = []

    def set_data(self, cols_meta: list[dict], rows: list[dict]) -> None:
        self._cols = [
            Column(
                c["name"],
                c["label"],
                is_row_header=(c["name"] == "number"),
                width_hint=c["width_hint"] if c["width_hint"] in _HINTS else AUTO,
            )
            for c in cols_meta
        ]
        self.rows = rows

    # -- GridModel interface ------------------------------------------
    def columns(self) -> list[Column]:
        return self._cols

    def row_count(self) -> int:
        return len(self.rows)

    def cell_text(self, row: int, column: str) -> str:
        if 0 <= row < len(self.rows):
            return grid_model.cell_text(self.rows[row], column)
        return ""


class ChannelGrid(wx.Panel):
    def __init__(
        self,
        parent: wx.Window,
        *,
        on_activate=None,
        on_context_menu=None,
        on_selection_changed=None,
        cell_announce=None,
    ) -> None:
        super().__init__(parent)
        self._model = _ChannelGridModel()
        # ``cell_announce`` enables the library's opt-in Left/Right cell cursor:
        # a ``callable(str)`` the grid calls with "<value>, <column>" as the
        # cursor moves across a row. Wired on Windows/NVDA (where the generic
        # DataViewCtrl announces no per-cell cursor) and left None on macOS, where
        # VoiceOver reads cells natively with VO+Left/Right — see main_window.
        self._grid = AccessibleGrid(
            self, self._model, label=_LABEL, announce=cell_announce
        )
        self._list: dv.DataViewListCtrl = self._grid.control

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(self._list, 1, wx.EXPAND)
        self.SetSizer(sizer)

        # The control persists for the panel's life, so bind once. These mirror
        # the events VRP bound directly before the grid moved into the library.
        if on_activate is not None:
            self._list.Bind(dv.EVT_DATAVIEW_ITEM_ACTIVATED, on_activate)
        if on_context_menu is not None:
            self._list.Bind(dv.EVT_DATAVIEW_ITEM_CONTEXT_MENU, on_context_menu)
        if on_selection_changed is not None:
            self._list.Bind(dv.EVT_DATAVIEW_SELECTION_CHANGED, on_selection_changed)

    def SetFocus(self) -> None:  # noqa: N802 (wx API)
        """Focus the inner list — a native row is only spoken when it has focus."""
        self._list.SetFocus()

    # -- population ----------------------------------------------------
    def set_state(self, state) -> None:
        """(Re)build columns and rows for the loaded radio.

        ``set_columns`` rebuilds the column shape in place on the existing
        control (a different radio can have a different feature/column set)."""
        self._model.set_data(grid_model.column_meta(state), grid_model.build_rows(state))
        self._grid.set_columns()
        # Establish a current (focused) row on the freshly populated control.
        # A just-populated DataViewListCtrl has *no* current item, so a later
        # SetFocus() lands on the control but on no row: the screen reader
        # announces nothing and the Left/Right cell cursor has no row to read
        # (focused_row() is None), until the user alt-tabs away and back, which
        # makes wx re-establish a current item. We set it here, WITHOUT taking
        # focus — the caller decides when to focus the grid.
        if self._model.rows:
            self._list.SetCurrentItem(self._list.RowToItem(0))

    def clear(self) -> None:
        self._model.set_data([], [])
        self._grid.set_columns()

    # -- selection / focus --------------------------------------------
    def selected_channel_numbers(self) -> list[int]:
        """Selected channels; falls back to the focused row when none selected
        (the library's ``selected_rows`` already applies that fallback)."""
        rows = self._model.rows
        nums = [
            grid_model.index_to_number(rows, r)
            for r in self._grid.selected_rows()
            if 0 <= r < len(rows)
        ]
        return sorted(nums)

    def focused_channel(self) -> int | None:
        row = self._grid.focused_row()
        if row is None or not (0 <= row < len(self._model.rows)):
            return None
        return grid_model.index_to_number(self._model.rows, row)

    def selected_count(self) -> int:
        """Actual number of selected rows (no focused-row fallback)."""
        return self._list.GetSelectedItemsCount()

    def select_channels(self, numbers: list[int]) -> None:
        """Replace the selection with exactly ``numbers``."""
        idxs = []
        for n in numbers:
            idx = grid_model.number_to_index(self._model.rows, n)
            if idx is not None:
                idxs.append(idx)
        self._grid.select_rows(idxs)

    def focus_channel(self, number: int) -> None:
        """Move focus to ``number`` so the screen reader reads it (takes keyboard
        focus to the grid if needed). Pair with ``select_channels`` when a row
        should be both selected AND read (Go to / Find / post-edit / post-move)."""
        idx = grid_model.number_to_index(self._model.rows, number)
        if idx is not None:
            self._grid.focus_row(idx)

    def popup_row_menu(self, menu: wx.Menu) -> None:
        """Show a row context menu. Pixel position is irrelevant to a
        screen-reader user; wx anchors it sensibly on the focused row. Popped up
        on the panel so the menu-item handlers (bound on this panel) receive the
        commands."""
        self.PopupMenu(menu)

    # -- passthroughs (used by tests and callers) ---------------------
    def GetItemCount(self) -> int:  # noqa: N802 (wx API parity)
        return self._list.GetItemCount()

    def GetColumnCount(self) -> int:  # noqa: N802 (wx API parity)
        return self._list.GetColumnCount()

    # -- refresh after edits/ops --------------------------------------
    def refresh_numbers(self, numbers: list[int]) -> None:
        """Rebuild the row dicts for ``numbers`` and repaint just those rows in
        place, keeping the control and the screen-reader focus position."""
        cols = build_column_defs(radio_backend.get_state().features)
        changed = []
        for n in numbers:
            idx = grid_model.number_to_index(self._model.rows, n)
            row = grid_model.build_row(n, cols)
            if idx is None or row is None:
                continue
            self._model.rows[idx] = row
            changed.append(idx)
        self._grid.refresh_rows(changed)

    def reorder_refresh(self) -> None:
        """Refresh row contents/order after a reorder. A move/sort changes which
        channel sits in each slot but not the column set, so rebuild the row data
        and repaint in place (``refresh`` falls back to a full rebuild if the row
        count changed)."""
        state = radio_backend.get_state()
        if not state.loaded:
            return
        self._model.rows = grid_model.build_rows(state)
        self._grid.refresh()

    def rebuild(self) -> None:
        """Refresh after a structural op (delete/move/insert/sort) on the same
        radio: the column set is unchanged, so rebuild the row data and let
        ``refresh`` repaint in place (or re-populate if the row count changed).
        Use ``set_state`` for a different radio (changed columns)."""
        self.reorder_refresh()
