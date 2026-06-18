"""Build HTML views from the loaded radio's state.

The memory channel grid is a fully server-rendered, semantic, READ-ONLY
``<table>``, rendered one PAGE at a time so large radios (thousands of
channels) stay fast — a full-table DOM is what made the screen reader slow.
Editing is done in a native wx dialog (see ``vrp.edit_dialog``), not in the
grid. Each row ends with an Edit button; after a successful edit only that one
row is re-rendered via :func:`render_row`.

Page math (``page`` is 1-based) lives here as pure functions so it is unit
testable: :func:`total_pages`, :func:`page_for_channel`, :func:`page_range`,
:func:`channel_total`.
"""

from __future__ import annotations

import math

from chirp_backend import radio as radio_backend
from chirp_backend.col_defs import build_column_defs

from vrp import __version__, html

PAGE_SIZE = 100  # fallback default if no config is available


def _page_size(page_size: int | None) -> int:
    """Resolve the page size: an explicit value, else the configured value,
    else the fallback default. Tolerates config/wx being unavailable (headless)."""
    if page_size:
        return page_size
    try:
        from vrp.config import get_config

        return int(get_config().get("channels_per_page", PAGE_SIZE)) or PAGE_SIZE
    except Exception:  # noqa: BLE001
        return PAGE_SIZE


def _bounds() -> tuple[int, int]:
    return radio_backend.get_state().memory_bounds


def channel_total() -> int:
    low, high = _bounds()
    return max(0, high - low + 1)


def total_pages(page_size: int | None = None) -> int:
    page_size = _page_size(page_size)
    total = channel_total()
    return max(1, math.ceil(total / page_size)) if total else 1


def page_for_channel(number: int, page_size: int | None = None) -> int:
    """1-based page that contains ``number`` (clamped to valid pages)."""
    page_size = _page_size(page_size)
    low, _high = _bounds()
    page = (number - low) // page_size + 1
    return min(max(page, 1), total_pages(page_size))


def page_range(page: int, page_size: int | None = None) -> tuple[int, int]:
    """Inclusive (first, last) channel numbers shown on ``page``."""
    page_size = _page_size(page_size)
    low, high = _bounds()
    start = low + (page - 1) * page_size
    return start, min(high, start + page_size - 1)


def _data_columns():
    """Column defs for the loaded radio, excluding the channel-number column."""
    features = radio_backend.get_state().features
    return [c for c in build_column_defs(features) if c.name != "number"]


def _build_row(number: int, cols) -> dict | None:
    """Build the render dict for one channel, or None if it can't be read."""
    mem = radio_backend.get_memory(number)
    if mem is None:
        return None
    empty = bool(getattr(mem, "empty", False))
    cells = [
        {"display": "" if empty else col.format_value(mem)} for col in cols
    ]
    return {"number": number, "empty": empty, "cells": cells}


def render_channels(page: int = 1, page_size: int | None = None) -> str:
    """Render one page of the channel grid for the currently loaded radio.

    Falls back to the welcome view if no radio is loaded.
    """
    state = radio_backend.get_state()
    if not state.loaded:
        return html.render_view("welcome.html", version=__version__)

    page_size = _page_size(page_size)
    low, high = _bounds()
    tp = total_pages(page_size)
    page = min(max(page, 1), tp)
    first, last = page_range(page, page_size)

    cols = _data_columns()
    rows = [r for n in range(first, last + 1) if (r := _build_row(n, cols))]

    # Destination ranges for the Prev/Next accessible names (clamped).
    prev_first, prev_last = page_range(page - 1, page_size)
    next_first, next_last = page_range(page + 1, page_size)

    radio_name = f"{state.radio.VENDOR} {state.radio.MODEL}"
    return html.render_view(
        "channels.html",
        radio_name=radio_name,
        columns=[c.label for c in cols],
        rows=rows,
        low=low,
        high=high,
        total=channel_total(),
        page=page,
        total_pages=tp,
        first=first,
        last=last,
        has_prev=page > 1,
        has_next=page < tp,
        prev_first=max(low, prev_first),
        prev_last=max(low, prev_last),
        next_first=min(high, next_first),
        next_last=min(high, next_last),
    )


def render_row(number: int) -> str:
    """Render one channel row's inner HTML (for surgical, single-row refresh).

    Uses the same macro the full grid uses, so refreshed rows match exactly.
    Returns "" if no radio is loaded or the channel can't be read.
    """
    if not radio_backend.get_state().loaded:
        return ""
    cols = _data_columns()
    row = _build_row(number, cols)
    if row is None:
        return ""
    return html.render_macro(
        "_row_macro.html", "row_inner", row, [c.label for c in cols]
    )
