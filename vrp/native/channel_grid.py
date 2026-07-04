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
        on_select_toggle=None,
        cell_announce=None,
    ) -> None:
        super().__init__(parent)
        self._model = _ChannelGridModel()
        # ``cell_announce`` enables the library's opt-in Left/Right cell cursor:
        # a ``callable(str)`` the grid calls with "<value>, <column>" as the
        # cursor moves across a row. Wired on Windows AND macOS (main_window
        # verified plain Left/Right reach the DataViewListCtrl on both, and prism
        # speaks the cell); left None on GTK/other, where it's untested.
        #
        # When it's None the library never binds its Left/Right handler, so the
        # cell cursor never leaves column 0 and ``focused_cell()`` can't report
        # which column the user is on. ``has_cell_cursor`` lets callers (F2 /
        # on_edit_cell) branch on that without re-checking the platform.
        self._announce_cell = cell_announce
        self._has_cell_cursor = cell_announce is not None
        # PROTOTYPE (column-locked navigation): when VRP has a cell cursor it owns
        # ALL FOUR arrow keys, not just Left/Right, and keeps its own (row, column)
        # cursor. On Up/Down it speaks concise, column-locked text ("Channel N,
        # <cell>") and scrolls WITHOUT moving the native selection — that's what
        # stops the screen reader's automatic full-row read. Native selection is
        # synced to this cursor only at action time (edit / delete / context menu).
        # So we pass announce=None to the library (we don't want its Left/Right-
        # only cursor) and drive everything from _on_grid_key.
        self._cur_row = 0
        self._cur_col = 0
        self._grid = AccessibleGrid(self, self._model, label=_LABEL, announce=None)
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
        self._context_menu_cb = on_context_menu
        # ``on_select_toggle(number, now_selected, total)`` — called when
        # Space/Ctrl+Space toggles the focused row, so the host can announce it.
        self._on_select_toggle = on_select_toggle
        if on_context_menu is not None or on_select_toggle is not None or self._has_cell_cursor:
            # One EVT_KEY_DOWN handler for the keys we drive ourselves: the four
            # arrows (the column-locked cursor), Shift+F10 (the generic control
            # raises the context-menu event only for the Applications key /
            # right-click), and Space/Ctrl+Space (native no-ops here). Everything
            # else is Skipped.
            self._list.Bind(wx.EVT_KEY_DOWN, self._on_grid_key)
        if on_selection_changed is not None:
            self._list.Bind(dv.EVT_DATAVIEW_SELECTION_CHANGED, on_selection_changed)

    def _on_grid_key(self, event: wx.KeyEvent) -> None:
        """Drive the column-locked cursor (four arrows), Shift+F10 (row context
        menu), and Space/Ctrl+Space (toggle selection). Consumed keys don't Skip;
        everything else does."""
        code = event.GetKeyCode()
        # Column-locked navigation. Plain (unmodified) arrows move OUR cursor and
        # speak concise text; we consume them so the native control never changes
        # the selection (which is what would trigger the screen reader's full-row
        # read). Shift/Ctrl+arrows fall through to native range/selection behavior.
        if (self._has_cell_cursor and not event.HasModifiers()
                and not event.ShiftDown()
                and code in (wx.WXK_UP, wx.WXK_DOWN, wx.WXK_LEFT, wx.WXK_RIGHT)):
            self._move_cursor(code)
            return
        if code == wx.WXK_F10 and event.ShiftDown() and self._context_menu_cb is not None:
            self._sync_native_to_cursor()  # act on the cursor row
            self._context_menu_cb(event)
            return
        # Space or Ctrl+Space toggles selection of the focused row. (Plain Space
        # is a native no-op on this control, so consuming it costs nothing.)
        if code == wx.WXK_SPACE and not event.AltDown() and self._on_select_toggle is not None:
            self._sync_native_to_cursor()  # toggle the cursor row, not row 0
            result = self.toggle_focused_selection()
            if result is not None:
                self._on_select_toggle(*result)
            return
        event.Skip()

    # -- column-locked cursor (prototype) -----------------------------
    def _move_cursor(self, code: int) -> None:
        """Move the app cursor one step, scroll to it WITHOUT selecting, and
        speak it. Up/Down: concise "Channel N, <cell>" (row header + current
        column). Left/Right: "<value>, <column>" (the column changed, so name it)."""
        n_rows = len(self._model.rows)
        n_cols = len(self._model.columns())
        if n_rows == 0 or n_cols == 0:
            return
        # Clamp the cursor into range (a rebuild may have shrunk the grid).
        self._cur_row = max(0, min(self._cur_row, n_rows - 1))
        self._cur_col = max(0, min(self._cur_col, n_cols - 1))

        if code in (wx.WXK_UP, wx.WXK_DOWN):
            self._cur_row = max(0, min(
                self._cur_row + (1 if code == wx.WXK_DOWN else -1), n_rows - 1))
            self._list.EnsureVisible(self._list.RowToItem(self._cur_row))
            self._announce(self._row_axis_text())
        else:  # LEFT / RIGHT
            self._cur_col = max(0, min(
                self._cur_col + (1 if code == wx.WXK_RIGHT else -1), n_cols - 1))
            self._announce(self._col_axis_text())

    def _cursor_number(self) -> int | None:
        if 0 <= self._cur_row < len(self._model.rows):
            return grid_model.index_to_number(self._model.rows, self._cur_row)
        return None

    def _cursor_value(self) -> tuple[str, str]:
        """(column label, cell value) at the cursor."""
        cols = self._model.columns()
        col = cols[self._cur_col]
        return col.label, grid_model.cell_text(self._model.rows[self._cur_row], col.name)

    def _row_axis_text(self) -> str:
        number = self._cursor_number()
        col = self._model.columns()[self._cur_col]
        # On the row-header column, "Channel N" already IS the value — don't say
        # it twice. Otherwise: channel number + the current column's cell (no
        # column name — the user knows the column they're travelling down).
        if col.name == "number":
            return f"Channel {number}"
        _label, value = self._cursor_value()
        return f"Channel {number}, {value if value else 'blank'}"

    def _col_axis_text(self) -> str:
        label, value = self._cursor_value()
        return f"{value if value else 'blank'}, {label}"

    def _announce(self, text: str) -> None:
        if self._announce_cell is not None:
            self._announce_cell(text)

    def _sync_native_to_cursor(self) -> None:
        """Point the native current item at the app cursor row, so actions
        (edit / delete / context menu) target what the user last arrowed to.
        This does move the native selection (and the reader may read the row),
        but only at action time, which is acceptable."""
        if self._has_cell_cursor and 0 <= self._cur_row < len(self._model.rows):
            self._list.SetCurrentItem(self._list.RowToItem(self._cur_row))

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
        self._cur_row = 0  # reset the column-locked cursor for the new radio
        self._cur_col = 0
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
        """Selected channels. With the column-locked cursor, a single-row action
        targets the CURSOR row (the app cursor is the source of truth, not the
        native selection, which we don't move while arrowing); an explicit
        Shift/Ctrl multi-selection still wins."""
        rows = self._model.rows
        if self._has_cell_cursor:
            real = [self._list.ItemToRow(it) for it in self._list.GetSelections()]
            real = [r for r in real if r != wx.NOT_FOUND]
            if not real:
                num = self._cursor_number()
                return [num] if num is not None else []
            return sorted(grid_model.index_to_number(rows, r) for r in real
                          if 0 <= r < len(rows))
        nums = [
            grid_model.index_to_number(rows, r)
            for r in self._grid.selected_rows()
            if 0 <= r < len(rows)
        ]
        return sorted(nums)

    def focused_channel(self) -> int | None:
        if self._has_cell_cursor:
            return self._cursor_number()
        row = self._grid.focused_row()
        if row is None or not (0 <= row < len(self._model.rows)):
            return None
        return grid_model.index_to_number(self._model.rows, row)

    @property
    def has_cell_cursor(self) -> bool:
        """Whether this grid has a working Left/Right cell cursor (so
        ``focused_cell()`` reports the real column). True where ``cell_announce``
        was wired (Windows and macOS); False on GTK/other, where F2 can't know the
        column from the cursor and takes the column-picker path instead."""
        return self._has_cell_cursor

    def focused_cell(self) -> tuple[int, str] | None:
        """(channel number, column name) at the app cursor, or None. Wired on
        Windows and macOS (``has_cell_cursor``); on GTK/other there's no cursor,
        so callers take the column-picker path instead."""
        if not self._has_cell_cursor:
            return None
        rows = self._model.rows
        cols = self._model.columns()
        if not (0 <= self._cur_row < len(rows)) or not (0 <= self._cur_col < len(cols)):
            return None
        return grid_model.index_to_number(rows, self._cur_row), cols[self._cur_col].name

    def selected_count(self) -> int:
        """Actual number of selected rows (no focused-row fallback)."""
        return self._list.GetSelectedItemsCount()

    def toggle_focused_selection(self) -> tuple[int, bool, int] | None:
        """Toggle the focused row in/out of the **real** selection (Space /
        Ctrl+Space). Returns ``(channel_number, now_selected, total_selected)`` or
        ``None`` when there is no focused row.

        Uses the control's real selection (``IsRowSelected``/``SelectRow``/
        ``UnselectRow``), never ``selected_channel_numbers()`` — that falls back to
        the focused row when the real selection is empty, which would make
        deselecting the last row impossible."""
        row = self._grid.focused_row()
        if row is None or not (0 <= row < len(self._model.rows)):
            return None
        now_selected = not self._list.IsRowSelected(row)
        if now_selected:
            self._list.SelectRow(row)
        else:
            self._list.UnselectRow(row)
        number = grid_model.index_to_number(self._model.rows, row)
        return number, now_selected, self._list.GetSelectedItemsCount()

    def cell_display(self, number: int, col_name: str) -> str:
        """The display text shown (and read) for a cell — the same text the
        Left/Right cursor speaks. Empty after a refresh returns ``""``."""
        idx = grid_model.number_to_index(self._model.rows, number)
        if idx is None:
            return ""
        return grid_model.cell_text(self._model.rows[idx], col_name)

    def select_channels(self, numbers: list[int]) -> None:
        """Replace the selection with exactly ``numbers``."""
        idxs = []
        for n in numbers:
            idx = grid_model.number_to_index(self._model.rows, n)
            if idx is not None:
                idxs.append(idx)
        self._grid.select_rows(idxs)

    def select_all(self) -> None:
        """Select every row (Edit ▸ Select All / Ctrl+A)."""
        self._list.SelectAll()

    def clear_selection(self) -> None:
        """Clear the selection (Edit ▸ Clear Selection)."""
        self._list.UnselectAll()

    def focus_channel(self, number: int) -> None:
        """Move focus to ``number`` so the screen reader reads it (takes keyboard
        focus to the grid if needed). Pair with ``select_channels`` when a row
        should be both selected AND read (Go to / Find / post-edit / post-move).
        Also moves the app cursor to that row so column-locked arrowing continues
        from where the action left off."""
        idx = grid_model.number_to_index(self._model.rows, number)
        if idx is not None:
            self._cur_row = idx
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
