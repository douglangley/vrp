"""Unit tests for ``col_defs.editable_columns`` — the field set F2's
column-picker offers (editable AND not the "number" row header AND not immutable
for the memory). Pure, no wx, no GUI."""

import os

import pytest

from chirp_backend import radio as radio_backend
from chirp_backend.col_defs import ColumnDef, build_column_defs, editable_columns

IMAGE = os.path.abspath(
    os.path.join(
        os.path.dirname(__file__), "..", "chirp", "tests", "images",
        "Baofeng_BF-888.img",
    )
)


def _cols():
    return [
        ColumnDef(name="number", label="Ch #", editable=False),
        ColumnDef(name="freq", label="Frequency"),
        ColumnDef(name="name", label="Name"),
        ColumnDef(name="power", label="Power"),
    ]


def test_excludes_number_row_header():
    names = [c.name for c in editable_columns(_cols())]
    assert "number" not in names


def test_excludes_non_editable_columns():
    cols = _cols() + [ColumnDef(name="readonly", label="RO", editable=False)]
    names = [c.name for c in editable_columns(cols)]
    assert "readonly" not in names


def test_excludes_immutable_fields_for_this_memory():
    names = [c.name for c in editable_columns(_cols(), immutable=["freq", "power"])]
    assert names == ["name"]


def test_none_immutable_is_treated_as_empty():
    names = [c.name for c in editable_columns(_cols(), immutable=None)]
    assert names == ["freq", "name", "power"]


def test_keeps_column_definition_order():
    result = editable_columns(_cols())
    assert [c.name for c in result] == ["freq", "name", "power"]


@pytest.fixture
def state():
    ok, message = radio_backend.load_image(IMAGE)
    assert ok, message
    yield radio_backend.get_state()
    radio_backend.unload()


def test_real_radio_columns_are_all_editable_and_exclude_number(state):
    """End-to-end against a real driver's column set (headless)."""
    result = editable_columns(build_column_defs(state.features))
    names = [c.name for c in result]
    assert "number" not in names
    assert names, "a real radio should expose at least one editable field"
    assert all(c.editable for c in result)
