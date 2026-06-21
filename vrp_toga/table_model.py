"""Pure data adapter for the experimental Toga channel table."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from chirp_backend import radio as radio_backend
from chirp_backend.col_defs import build_column_defs

from vrp.config import get_config

DEFAULT_PAGE_SIZE = 100
EMPTY_MARKER = "(empty)"


@dataclass(frozen=True)
class TablePage:
    """Rows and metadata needed to populate a native ``toga.Table``."""

    radio_label: str
    columns: list[str]
    accessors: list[str]
    rows: list[dict[str, Any]]
    page: int
    total_pages: int
    first: int
    last: int
    total: int
    has_prev: bool
    has_next: bool
    status: str


def _page_size(page_size: int | None = None) -> int:
    if page_size:
        return page_size
    try:
        configured = int(get_config().get("channels_per_page", DEFAULT_PAGE_SIZE))
    except Exception:  # noqa: BLE001 - config should never block table rendering
        configured = DEFAULT_PAGE_SIZE
    return configured or DEFAULT_PAGE_SIZE


def _bounds() -> tuple[int, int]:
    return radio_backend.get_state().memory_bounds


def channel_total() -> int:
    low, high = _bounds()
    return max(0, high - low + 1)


def total_pages(page_size: int | None = None) -> int:
    size = _page_size(page_size)
    total = channel_total()
    return max(1, math.ceil(total / size)) if total else 1


def page_for_channel(number: int, page_size: int | None = None) -> int:
    size = _page_size(page_size)
    low, high = _bounds()
    if high < low:
        return 1
    clamped = min(max(number, low), high)
    page = (clamped - low) // size + 1
    return min(max(page, 1), total_pages(size))


def page_range(page: int, page_size: int | None = None) -> tuple[int, int]:
    size = _page_size(page_size)
    low, high = _bounds()
    if high < low:
        return 0, 0
    start = low + (page - 1) * size
    return start, min(high, start + size - 1)


def _empty_page() -> TablePage:
    return TablePage(
        radio_label="No radio loaded",
        columns=["Ch #", "State"],
        accessors=["number", "state", "channel_number", "empty"],
        rows=[],
        page=1,
        total_pages=1,
        first=0,
        last=0,
        total=0,
        has_prev=False,
        has_next=False,
        status="No radio image loaded.",
    )


def build_table_page(page: int = 1, page_size: int | None = None) -> TablePage:
    """Build one page of Toga table data for the loaded radio."""

    state = radio_backend.get_state()
    if not state.loaded:
        return _empty_page()

    size = _page_size(page_size)
    total = channel_total()
    pages = total_pages(size)
    page = min(max(page, 1), pages)
    first, last = page_range(page, size)

    columns = build_column_defs(state.features)
    display_columns = [column for column in columns if column.name != "number"]
    names = [column.name for column in display_columns]
    if "name" in names and "tmode" in names:
        name_index = names.index("name")
        tmode_index = names.index("tmode")
        if name_index < tmode_index:
            name_column = display_columns.pop(name_index)
            display_columns.insert(tmode_index, name_column)
    headings = ["Ch #", "State"] + [column.label for column in display_columns]
    accessors = ["number", "state"] + [column.name for column in display_columns]
    accessors += ["channel_number", "empty"]

    rows: list[dict[str, Any]] = []
    for number in range(first, last + 1):
        mem = radio_backend.get_memory(number)
        if mem is None:
            continue
        empty = bool(getattr(mem, "empty", False))
        state_text = EMPTY_MARKER if empty or not getattr(mem, "name", "") else ""
        row: dict[str, Any] = {
            "number": str(number),
            "state": state_text,
            "channel_number": number,
            "empty": empty,
        }
        for column in display_columns:
            row[column.name] = "" if empty else column.format_value(mem)
        rows.append(row)

    radio_label = f"{state.radio.VENDOR} {state.radio.MODEL}"
    return TablePage(
        radio_label=radio_label,
        columns=headings,
        accessors=accessors,
        rows=rows,
        page=page,
        total_pages=pages,
        first=first,
        last=last,
        total=total,
        has_prev=page > 1,
        has_next=page < pages,
        status=f"Showing channels {first} to {last} of {total}, page {page} of {pages}.",
    )
