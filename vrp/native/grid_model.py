"""Pure data/selection model for the native channel grid.

No wx here — everything is plain Python so it can be unit-tested headless.
``build_rows``/``column_meta`` wrap chirp_backend; the selection helpers are
arithmetic that mirrors what memory_ops did to the channels, so the grid can
re-select a moved block without re-reading positions from the radio.
"""

from __future__ import annotations

from chirp_backend import radio as radio_backend
from chirp_backend.col_defs import build_column_defs
from chirp_backend.radio import RadioState

_EMPTY_MARKER_COLS = {"name", "freq"}


def column_meta(state: RadioState) -> list[dict]:
    """Ordered column metadata for the loaded radio (first column = Ch #)."""
    cols = build_column_defs(state.features)
    return [
        {"name": c.name, "label": c.label, "width_hint": c.width_hint}
        for c in cols
    ]


def build_row(number: int, cols=None) -> dict | None:
    """Build the row dict for a single channel, or None if it can't be read.

    Pass ``cols`` (from ``build_column_defs``) to reuse one column build across a
    batch; omit it and the loaded radio's columns are built on demand. Used both
    by ``build_rows`` and by the grid's per-row refresh so updating one edited
    channel doesn't re-read every channel.

    Row shape: {"number": int, "empty": bool, "immutable": list,
                "cells": {col_name: display_str}}.
    """
    if cols is None:
        cols = build_column_defs(radio_backend.get_state().features)
    mem = radio_backend.get_memory(number)
    if mem is None:
        return None
    empty = bool(getattr(mem, "empty", False))
    cells = {}
    for col in cols:
        if col.name == "number":
            cells["number"] = str(number)
        else:
            cells[col.name] = "" if empty else col.format_value(mem)
    return {
        "number": number,
        "empty": empty,
        "immutable": list(getattr(mem, "immutable", []) or []),
        "cells": cells,
    }


def build_rows(state: RadioState) -> list[dict]:
    """One row dict per channel, low..high in order (see ``build_row``)."""
    low, high = state.memory_bounds
    cols = build_column_defs(state.features)
    rows: list[dict] = []
    for number in range(low, high + 1):
        row = build_row(number, cols)
        if row is not None:
            rows.append(row)
    return rows


def cell_text(row: dict, col_name: str) -> str:
    """Display text for a cell, with an empty-channel marker where appropriate."""
    if col_name == "number":
        return str(row["number"])
    if row["empty"] and col_name in _EMPTY_MARKER_COLS:
        return "(empty)"
    return row["cells"].get(col_name, "")


def index_to_number(rows: list[dict], index: int) -> int:
    """Channel number at a ListCtrl item index."""
    return rows[index]["number"]


def number_to_index(rows: list[dict], number: int) -> int | None:
    """ListCtrl item index for a channel number, or None if absent."""
    for i, row in enumerate(rows):
        if row["number"] == number:
            return i
    return None


def selection_after_move(numbers: list[int], direction: int) -> tuple[list[int], int]:
    """Where a moved block lands after ``move_memories``: each n -> n+direction.

    Returns (sorted new channel numbers, channel to focus = the lowest channel number in the moved block).
    """
    new = sorted(n + direction for n in numbers)
    return new, new[0]


def selection_after_move_to(count: int, destination: int) -> tuple[list[int], int]:
    """Where a block lands after ``move_to``: destination..destination+count-1."""
    new = list(range(destination, destination + count))
    return new, destination
