"""
Unit tests for chirp_backend/memory_ops.py.

Tests run without any radio hardware. We use a chirp_common.Memory
list directly, stubbing out the radio object so we can test all the
operation logic without needing to load a .img file.

Run with: python -m pytest tests/
"""

import sys
import os
import pytest

# Add parent dir to path so we can import chirp_backend
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


# ---------------------------------------------------------------------------
# Minimal stub radio for testing
# ---------------------------------------------------------------------------

class StubMemory:
    """Minimal Memory-like object for testing."""
    def __init__(self, number, freq=146_520_000, name="", empty=False):
        self.number = number
        self.freq = freq
        self.name = name
        self.empty = empty
        self.immutable = []
        self.extd_number = ""
        self.tmode = ""
        self.rtone = 88.5
        self.ctone = 88.5
        self.dtcs = 23
        self.rx_dtcs = 23
        self.dtcs_polarity = "NN"
        self.cross_mode = "Tone->Tone"
        self.duplex = ""
        self.offset = 600_000
        self.mode = "FM"
        self.tuning_step = 5.0
        self.skip = ""
        self.comment = ""
        self.power = None

    def dupe(self):
        import copy
        return copy.copy(self)


class StubRadio:
    """Minimal radio stub with in-memory channel storage."""
    VENDOR = "Test"
    MODEL = "StubRadio"

    def __init__(self, num_channels=20):
        self._channels = {}
        for i in range(num_channels):
            self._channels[i] = StubMemory(i, empty=True)

    def get_features(self):
        class F:
            memory_bounds = (0, 19)
        return F()

    def get_memory(self, number):
        if number not in self._channels:
            raise Exception(f"Channel {number} out of range")
        return self._channels[number]

    def set_memory(self, mem):
        self._channels[mem.number] = mem

    def erase_memory(self, number):
        if number in self._channels:
            self._channels[number] = StubMemory(number, empty=True)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def stub_radio(monkeypatch):
    """
    Patch chirp_backend.memory_ops to use a fresh StubRadio for each test.
    This replaces _get_radio() and _mem_bounds() with stub versions.
    """
    radio = StubRadio(num_channels=20)

    import chirp_backend.memory_ops as ops_mod
    monkeypatch.setattr(ops_mod, '_get_radio', lambda: radio)
    monkeypatch.setattr(ops_mod, '_mem_bounds', lambda: (0, 19))

    # Also patch invalidate_cache so it's a no-op in tests
    import chirp_backend.radio as radio_mod
    monkeypatch.setattr(radio_mod, 'invalidate_cache', lambda numbers=None: None)

    return radio


def _fill(radio, *numbers_and_names):
    """Helper: fill channels with test data. Pass (number, name) tuples."""
    for number, name in numbers_and_names:
        mem = StubMemory(number, freq=146_000_000 + number * 100_000, name=name)
        radio.set_memory(mem)


# ---------------------------------------------------------------------------
# Tests: delete_memory
# ---------------------------------------------------------------------------

class TestDeleteMemory:
    def test_delete_single(self, stub_radio):
        _fill(stub_radio, (5, "REPEATER"))
        from chirp_backend.memory_ops import delete_memory
        ok, msg, affected = delete_memory(5)
        assert ok
        assert 5 in affected
        assert stub_radio.get_memory(5).empty

    def test_delete_empty_is_ok(self, stub_radio):
        from chirp_backend.memory_ops import delete_memory
        ok, msg, affected = delete_memory(0)
        assert ok  # erasing an already-empty slot is fine

    def test_delete_immutable_fails(self, stub_radio):
        stub_radio._channels[3].immutable = ["empty"]
        from chirp_backend.memory_ops import delete_memory
        ok, msg, affected = delete_memory(3)
        assert not ok
        assert affected == []


# ---------------------------------------------------------------------------
# Tests: delete_range
# ---------------------------------------------------------------------------

class TestDeleteRange:
    def test_delete_multiple(self, stub_radio):
        _fill(stub_radio, (1, "A"), (2, "B"), (3, "C"))
        from chirp_backend.memory_ops import delete_range
        ok, msg, affected = delete_range([1, 2, 3])
        assert ok
        for n in [1, 2, 3]:
            assert stub_radio.get_memory(n).empty

    def test_delete_empty_list(self, stub_radio):
        from chirp_backend.memory_ops import delete_range
        ok, msg, affected = delete_range([])
        assert ok
        assert affected == []


# ---------------------------------------------------------------------------
# Tests: delete_and_shift
# ---------------------------------------------------------------------------

class TestDeleteAndShift:
    def test_shift_all(self, stub_radio):
        _fill(stub_radio, (0, "A"), (1, "B"), (2, "C"), (3, "D"))
        from chirp_backend.memory_ops import delete_and_shift
        ok, msg, affected = delete_and_shift([1], mode="all")
        assert ok
        # Channel 0 unchanged
        assert stub_radio.get_memory(0).name == "A"
        # B deleted, C and D shifted up
        assert stub_radio.get_memory(1).name == "C"
        assert stub_radio.get_memory(2).name == "D"
        assert stub_radio.get_memory(3).empty

    def test_shift_block(self, stub_radio):
        # Fill channels 0-2 (block), 3 empty, 4-5 another block
        _fill(stub_radio, (0, "A"), (1, "B"), (2, "C"), (4, "X"), (5, "Y"))
        from chirp_backend.memory_ops import delete_and_shift
        ok, msg, affected = delete_and_shift([0], mode="block")
        assert ok
        # B and C shift up to 0 and 1, then hole at 2
        assert stub_radio.get_memory(0).name == "B"
        assert stub_radio.get_memory(1).name == "C"
        assert stub_radio.get_memory(2).empty
        # X and Y at 4,5 should be untouched (different block)
        assert stub_radio.get_memory(4).name == "X"


# ---------------------------------------------------------------------------
# Tests: insert_row
# ---------------------------------------------------------------------------

class TestInsertRow:
    def test_insert_creates_blank(self, stub_radio):
        _fill(stub_radio, (0, "A"), (1, "B"), (2, "C"))
        from chirp_backend.memory_ops import insert_row
        ok, msg, affected = insert_row(1)
        assert ok
        assert stub_radio.get_memory(0).name == "A"
        assert stub_radio.get_memory(1).empty   # blank inserted here
        assert stub_radio.get_memory(2).name == "B"
        assert stub_radio.get_memory(3).name == "C"

    def test_insert_no_empty_slot_fails(self, stub_radio):
        # Fill all channels
        for i in range(20):
            stub_radio.set_memory(StubMemory(i, name=f"CH{i}"))
        from chirp_backend.memory_ops import insert_row
        ok, msg, affected = insert_row(0)
        assert not ok


# ---------------------------------------------------------------------------
# Tests: move_memories
# ---------------------------------------------------------------------------

class TestMoveMemories:
    def test_move_down(self, stub_radio):
        _fill(stub_radio, (2, "A"), (3, "B"))
        from chirp_backend.memory_ops import move_memories
        ok, msg, affected = move_memories([2], direction=1)
        assert ok
        assert stub_radio.get_memory(3).name == "A"
        assert stub_radio.get_memory(2).name == "B"

    def test_move_up(self, stub_radio):
        _fill(stub_radio, (2, "A"), (3, "B"))
        from chirp_backend.memory_ops import move_memories
        ok, msg, affected = move_memories([3], direction=-1)
        assert ok
        assert stub_radio.get_memory(2).name == "B"
        assert stub_radio.get_memory(3).name == "A"

    def test_move_above_first_fails(self, stub_radio):
        _fill(stub_radio, (0, "A"))
        from chirp_backend.memory_ops import move_memories
        ok, msg, affected = move_memories([0], direction=-1)
        assert not ok

    def test_move_below_last_fails(self, stub_radio):
        _fill(stub_radio, (19, "A"))
        from chirp_backend.memory_ops import move_memories
        ok, msg, affected = move_memories([19], direction=1)
        assert not ok


# ---------------------------------------------------------------------------
# Tests: move_to
# ---------------------------------------------------------------------------

class TestMoveTo:
    def test_move_to_destination(self, stub_radio):
        _fill(stub_radio, (0, "A"), (1, "B"))
        from chirp_backend.memory_ops import move_to
        ok, msg, affected = move_to([0, 1], destination=5)
        assert ok
        assert stub_radio.get_memory(5).name == "A"
        assert stub_radio.get_memory(6).name == "B"
        assert stub_radio.get_memory(0).empty
        assert stub_radio.get_memory(1).empty

    def test_move_to_out_of_range(self, stub_radio):
        _fill(stub_radio, (0, "A"))
        from chirp_backend.memory_ops import move_to
        ok, msg, affected = move_to([0], destination=100)
        assert not ok


# ---------------------------------------------------------------------------
# Tests: sort_range
# ---------------------------------------------------------------------------

class TestSortRange:
    def test_sort_by_name(self, stub_radio):
        _fill(stub_radio, (0, "Zebra"), (1, "Alpha"), (2, "Mike"))
        from chirp_backend.memory_ops import sort_range
        ok, msg, affected = sort_range([0, 1, 2], attr="name")
        assert ok
        assert stub_radio.get_memory(0).name == "Alpha"
        assert stub_radio.get_memory(1).name == "Mike"
        assert stub_radio.get_memory(2).name == "Zebra"

    def test_sort_by_name_descending(self, stub_radio):
        _fill(stub_radio, (0, "Zebra"), (1, "Alpha"), (2, "Mike"))
        from chirp_backend.memory_ops import sort_range
        ok, msg, affected = sort_range([0, 1, 2], attr="name", reverse=True)
        assert ok
        assert stub_radio.get_memory(0).name == "Zebra"


# ---------------------------------------------------------------------------
# Tests: find
# ---------------------------------------------------------------------------

class TestFind:
    def test_find_by_name(self, stub_radio):
        _fill(stub_radio, (0, "REPEATER"), (5, "SIMPLEX"), (10, "WEATHER"))
        from chirp_backend.memory_ops import find
        ok, msg, affected = find("SIMPLEX")
        assert ok
        assert affected == [5]

    def test_find_case_insensitive(self, stub_radio):
        _fill(stub_radio, (3, "Repeater"))
        from chirp_backend.memory_ops import find
        ok, msg, affected = find("repeater")
        assert ok
        assert affected == [3]

    def test_find_not_found(self, stub_radio):
        from chirp_backend.memory_ops import find
        ok, msg, affected = find("DOESNOTEXIST")
        assert not ok
        assert affected == []

    def test_find_wraps_around(self, stub_radio):
        _fill(stub_radio, (2, "TARGET"))
        from chirp_backend.memory_ops import find
        # Start searching from channel 10 — should wrap and find channel 2
        ok, msg, affected = find("TARGET", start_number=10)
        assert ok
        assert affected == [2]


# ---------------------------------------------------------------------------
# Tests: goto
# ---------------------------------------------------------------------------

class TestGoto:
    def test_goto_valid(self, stub_radio):
        from chirp_backend.memory_ops import goto
        ok, msg, affected = goto(10)
        assert ok
        assert affected == [10]

    def test_goto_out_of_range(self, stub_radio):
        from chirp_backend.memory_ops import goto
        ok, msg, affected = goto(99)
        assert not ok
