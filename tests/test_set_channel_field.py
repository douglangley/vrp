"""Tests for memory_ops.set_channel_field — the single-cell apply that also turns
on the matching Tone Mode when a lone tone/DCS edit wouldn't otherwise persist.

Uses a real radio image (not the stub in test_memory_ops), because the behaviour
under test is CHIRP's own: it discards a CTCSS/DCS value unless the Tone Mode uses
it, so a stub that stores anything wouldn't exercise the fix. No hardware needed.
"""

import os

import pytest

from chirp_backend import radio as radio_backend
from chirp_backend import memory_ops

IMAGE = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "chirp", "tests", "images",
                 "Baofeng_UV-5R.img")
)


@pytest.fixture
def loaded():
    ok, message = radio_backend.load_image(IMAGE)
    assert ok, message
    yield
    radio_backend.unload()


def _first_populated_no_tone():
    """A populated channel whose Tone Mode is off (the case the fix targets)."""
    lo, hi = radio_backend.get_state().memory_bounds
    for n in range(lo, hi + 1):
        m = radio_backend.get_memory(n)
        if m and not getattr(m, "empty", True) and m.tmode == "":
            return n
    pytest.skip("no populated, tone-off channel in the image")


def test_ctone_alone_sets_tsql_and_persists(loaded):
    n = _first_populated_no_tone()
    ok, _msg, affected, note = memory_ops.set_channel_field(n, "ctone", "110.9")
    assert ok and affected == [n]
    assert note and "TSQL" in note          # switched the mode on, and says so
    m = radio_backend.get_memory(n)
    assert m.tmode == "TSQL"
    assert abs(m.ctone - 110.9) < 0.05       # and the tone actually stuck


def test_rtone_alone_sets_tone_mode(loaded):
    n = _first_populated_no_tone()
    _ok, _msg, _aff, note = memory_ops.set_channel_field(n, "rtone", "123.0")
    assert note and "Tone" in note
    m = radio_backend.get_memory(n)
    assert m.tmode == "Tone" and abs(m.rtone - 123.0) < 0.05


def test_non_tone_field_does_not_couple(loaded):
    """A Mode edit persists on its own; no coupled change."""
    n = _first_populated_no_tone()
    before = radio_backend.get_memory(n)
    new_mode = "NFM" if before.mode != "NFM" else "FM"
    _ok, _msg, _aff, note = memory_ops.set_channel_field(n, "mode", new_mode)
    assert note is None
    assert radio_backend.get_memory(n).mode == new_mode


def test_ctone_when_already_tsql_is_left_alone(loaded):
    """If the Tone Mode already keeps the value, don't re-set it (no clobber)."""
    n = _first_populated_no_tone()
    memory_ops.update_channel(n, {"tmode": "TSQL", "ctone": "88.5"})
    _ok, _msg, _aff, note = memory_ops.set_channel_field(n, "ctone", "100.0")
    assert note is None                      # already effective, no switch
    m = radio_backend.get_memory(n)
    assert m.tmode == "TSQL" and abs(m.ctone - 100.0) < 0.05


def _first_simplex_channel():
    """A populated channel with no Duplex offset (the case the fix targets)."""
    lo, hi = radio_backend.get_state().memory_bounds
    for n in range(lo, hi + 1):
        m = radio_backend.get_memory(n)
        if m and not getattr(m, "empty", True) and m.duplex == "" and m.freq:
            return n
    pytest.skip("no simplex channel in the image")


def test_duplex_minus_alone_adds_offset_so_it_persists(loaded):
    """Setting Duplex to minus on a simplex channel would revert (zero offset);
    the fix fills the band's standard offset so the direction sticks."""
    n = _first_simplex_channel()
    _ok, _msg, _aff, note = memory_ops.set_channel_field(n, "duplex", "-")
    assert note and "offset" in note.lower()
    m = radio_backend.get_memory(n)
    assert m.duplex == "-" and m.offset > 0   # direction kept, offset filled


def test_duplex_with_existing_offset_is_left_alone(loaded):
    """When an offset is already present, the direction persists on its own."""
    n = _first_simplex_channel()
    memory_ops.update_channel(n, {"duplex": "-", "offset": "0.600000"})
    _ok, _msg, _aff, note = memory_ops.set_channel_field(n, "duplex", "+")
    assert note is None                       # already had an offset, no fill
    assert radio_backend.get_memory(n).duplex == "+"
