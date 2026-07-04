"""Unit tests for the native grid model (pure, no wx)."""

import os

import pytest

from chirp_backend import radio as radio_backend
from vrp.native import grid_model

IMAGE = os.path.abspath(
    os.path.join(
        os.path.dirname(__file__), "..", "chirp", "tests", "images",
        "Baofeng_BF-888.img",
    )
)


@pytest.fixture
def state():
    ok, message = radio_backend.load_image(IMAGE)
    assert ok, message
    yield radio_backend.get_state()
    radio_backend.unload()


def test_column_meta_starts_with_channel_number(state):
    cols = grid_model.column_meta(state)
    assert cols[0]["name"] == "number"
    assert cols[0]["label"] == "Ch #"
    assert all({"name", "label", "width_hint"} <= c.keys() for c in cols)


def test_build_rows_covers_all_channels_in_order(state):
    rows = grid_model.build_rows(state)
    assert [r["number"] for r in rows] == list(range(1, 17))  # BF-888 = 1..16
    assert all("cells" in r and "empty" in r for r in rows)


def test_cell_text_channel_number_always_shown(state):
    rows = grid_model.build_rows(state)
    assert grid_model.cell_text(rows[0], "number") == "1"


def test_empty_channel_has_text_marker_not_blank():
    # cell_text is pure — test it directly with a synthetic empty row dict.
    # BF-888 has no empty channels in its stock image, so we don't use build_rows
    # here; the row dict shape is what build_rows produces for any empty channel.
    empty_row = {"number": 5, "empty": True, "immutable": [], "cells": {"name": "", "freq": ""}}
    assert grid_model.cell_text(empty_row, "name") == "(empty)"
    assert grid_model.cell_text(empty_row, "freq") == "(empty)"
    assert grid_model.cell_text(empty_row, "number") == "5"  # number always shown


def test_index_number_mapping_round_trips(state):
    rows = grid_model.build_rows(state)
    assert grid_model.index_to_number(rows, 0) == 1
    assert grid_model.number_to_index(rows, 1) == 0
    assert grid_model.number_to_index(rows, 999) is None


def test_selection_after_move_shifts_block_by_direction():
    sel, focus = grid_model.selection_after_move([7, 5, 6], -1)
    assert sel == [4, 5, 6]
    assert focus == 4
    sel, focus = grid_model.selection_after_move([5, 6], 1)
    assert sel == [6, 7]
    assert focus == 6


def test_selection_after_move_to_lands_at_destination():
    sel, focus = grid_model.selection_after_move_to(3, 10)
    assert sel == [10, 11, 12]
    assert focus == 10


# -- inactive coupled-field marker (UV-5R has tone/offset columns) -------------
_UV5R = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "chirp", "tests", "images",
                 "Baofeng_UV-5R.img")
)


@pytest.fixture
def uv5r():
    ok, message = radio_backend.load_image(_UV5R)
    assert ok, message
    yield radio_backend.get_state()
    radio_backend.unload()


def _tone_off_channel():
    lo, hi = radio_backend.get_state().memory_bounds
    for n in range(lo, hi + 1):
        m = radio_backend.get_memory(n)
        if m and not getattr(m, "empty", True) and m.tmode == "":
            return n
    pytest.skip("no tone-off channel in image")


def test_inactive_tone_cell_is_marked_off(uv5r):
    from chirp_backend.col_defs import build_column_defs
    cols = build_column_defs(uv5r.features)
    n = _tone_off_channel()
    row = grid_model.build_row(n, cols)
    # A tone the mode doesn't use reads "<value> (off)", not a bare active value.
    assert grid_model.cell_text(row, "ctone").endswith("(off)")


def test_marker_clears_when_field_activated(uv5r):
    from chirp_backend import memory_ops
    from chirp_backend.col_defs import build_column_defs
    cols = build_column_defs(uv5r.features)
    n = _tone_off_channel()
    memory_ops.set_channel_field(n, "ctone", "110.9")  # turns on TSQL
    row = grid_model.build_row(n, cols)
    assert grid_model.cell_text(row, "ctone") == "110.9"  # active, no "(off)"
