"""A :class:`wx_accessible_grid.GridModel` backed by the loaded radio.

This bridges VRP's CHIRP-facing backend (``chirp_backend``) to the reusable
``wx-accessible-grid`` library, so the memory channel table can be an editable,
screen-reader-first ARIA grid instead of the read-only HTML table plus a separate
edit dialog. Columns come from the same :func:`build_column_defs` the old table
and the edit dialog use, so the radio never shows a field it doesn't support.

Row index is 0-based; the channel number is ``memory_bounds[0] + row`` (CHIRP
channels usually start at 0). Editing routes through ``memory_ops.set_field``,
which parses and validates with CHIRP's own parsers and writes back via
``set_memory`` — so the value the screen reader confirms is the authoritative,
normalized one. Immutable fields (per ``mem.immutable``) and the channel-number
column are read-only.
"""

from __future__ import annotations

from wx_accessible_grid import COMBO, NONE, TEXT, Column, GridModel, SetResult

from chirp_backend import memory_ops
from chirp_backend import radio as radio_backend
from chirp_backend.col_defs import build_column_defs


class ChannelGridModel(GridModel):
    """Expose the loaded radio's memory channels to ``AccessibleGrid``."""

    def __init__(self) -> None:
        self._cols_cache: list | None = None
        self._coldefs: dict = {}

    # -- shape -------------------------------------------------------------

    def _low(self) -> int:
        return radio_backend.get_state().memory_bounds[0]

    def columns(self) -> list[Column]:
        if self._cols_cache is not None:
            return self._cols_cache
        features = radio_backend.get_state().features
        cols: list[Column] = []
        for cd in build_column_defs(features):
            self._coldefs[cd.name] = cd
            if cd.name == "number":
                cols.append(Column("number", cd.label, editor=NONE, is_row_header=True))
            elif cd.input_type == "select":
                cols.append(Column(cd.name, cd.label, editor=COMBO, choices=list(cd.choices)))
            else:
                # Frequency, offset, name, comment: CHIRP parses these from text.
                cols.append(Column(cd.name, cd.label, editor=TEXT, editable=cd.editable))
        self._cols_cache = cols
        return cols

    def row_count(self) -> int:
        low, high = radio_backend.get_state().memory_bounds
        return max(0, high - low + 1)

    # -- reading -----------------------------------------------------------

    def _mem(self, row: int):
        return radio_backend.get_memory(self._low() + row)

    def display(self, row: int, column: str) -> str:
        number = self._low() + row
        if column == "number":
            return str(number)
        mem = self._mem(row)
        if mem is None or getattr(mem, "empty", False):
            return ""
        cd = self._coldefs.get(column)
        return cd.format_value(mem) if cd else ""

    def row_label(self, row: int) -> str:
        return str(self._low() + row)

    def is_editable(self, row: int, column: str) -> bool:
        if column == "number":
            return False
        cd = self._coldefs.get(column)
        if cd is None or not cd.editable:
            return False
        mem = self._mem(row)
        if mem is not None and column in (getattr(mem, "immutable", None) or []):
            return False
        return True

    def choices(self, row: int, column: str) -> list[str]:
        cd = self._coldefs.get(column)
        return list(cd.choices) if cd else []

    # -- writing -----------------------------------------------------------

    def set_cell(self, row: int, column: str, value: str) -> SetResult:
        number = self._low() + row
        ok, message, _affected = memory_ops.set_field(number, column, value)
        if not ok:
            return SetResult(False, message=message)
        return SetResult(True, display=self.display(row, column), message=message)

    def delete_rows(self, rows: list[int]) -> SetResult:
        low = self._low()
        numbers = [low + r for r in rows]
        ok, message, _affected = memory_ops.delete_range(numbers)
        return SetResult(ok, message=message)
