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

    def test_delete_immutable_none_does_not_crash(self, stub_radio):
        # Some drivers report immutable as None; "empty" in None would TypeError.
        _fill(stub_radio, (5, "REPEATER"))
        stub_radio._channels[5].immutable = None
        from chirp_backend.memory_ops import delete_memory
        ok, msg, affected = delete_memory(5)
        assert ok
        assert stub_radio.get_memory(5).empty


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

    def test_delete_range_immutable_none_does_not_crash(self, stub_radio):
        _fill(stub_radio, (1, "A"), (2, "B"))
        stub_radio._channels[1].immutable = None  # driver reports None
        from chirp_backend.memory_ops import delete_range
        ok, msg, affected = delete_range([1, 2])
        assert ok
        assert stub_radio.get_memory(1).empty and stub_radio.get_memory(2).empty


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

    def test_noncontiguous_selection_rejected(self, stub_radio):
        # A gappy selection (1-3, 5) has no well-defined shift; reject cleanly
        # and leave the radio untouched rather than corrupting the layout.
        _fill(stub_radio, (1, "B"), (2, "C"), (3, "D"), (4, "E"), (5, "F"),
              (6, "G"))
        from chirp_backend.memory_ops import delete_and_shift
        ok, msg, affected = delete_and_shift([1, 2, 3, 5], mode="all")
        assert not ok
        assert "contiguous" in msg.lower()
        assert affected == []
        # Nothing moved or erased.
        assert stub_radio.get_memory(4).name == "E"
        assert stub_radio.get_memory(6).name == "G"

    def test_contiguous_out_of_order_still_shifts(self, stub_radio):
        # Same channels, given unsorted and with a duplicate, are contiguous.
        _fill(stub_radio, (1, "B"), (2, "C"), (3, "D"), (4, "E"))
        from chirp_backend.memory_ops import delete_and_shift
        ok, _msg, _affected = delete_and_shift([3, 1, 2, 2], mode="all")
        assert ok
        assert stub_radio.get_memory(1).name == "E"  # 4 shifted up to 1
        assert stub_radio.get_memory(2).empty

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

    def test_sort_non_contiguous_uses_selected_slots(self, stub_radio):
        # Values from scattered slots 0,2,4 are sorted and written back into
        # those same slots in ascending order; the in-between slots are untouched.
        _fill(stub_radio, (0, "Zebra"), (2, "Alpha"), (4, "Mike"), (1, "Keep1"), (3, "Keep3"))
        from chirp_backend.memory_ops import sort_range
        ok, msg, affected = sort_range([0, 2, 4], attr="name")
        assert ok
        assert affected == [0, 2, 4]
        assert stub_radio.get_memory(0).name == "Alpha"
        assert stub_radio.get_memory(2).name == "Mike"
        assert stub_radio.get_memory(4).name == "Zebra"
        # Untouched neighbours.
        assert stub_radio.get_memory(1).name == "Keep1"
        assert stub_radio.get_memory(3).name == "Keep3"

    def test_sort_by_freq_is_numeric(self, stub_radio):
        # A string sort would order 99 MHz after 146 MHz ('9' > '1'); numeric
        # sort must place 99 MHz first.
        from chirp_backend.memory_ops import sort_range
        stub_radio.set_memory(StubMemory(0, freq=146_000_000, name="mid"))
        stub_radio.set_memory(StubMemory(1, freq=99_000_000, name="low"))
        stub_radio.set_memory(StubMemory(2, freq=440_000_000, name="high"))
        ok, msg, affected = sort_range([0, 1, 2], attr="freq")
        assert ok
        assert stub_radio.get_memory(0).freq == 99_000_000
        assert stub_radio.get_memory(1).freq == 146_000_000
        assert stub_radio.get_memory(2).freq == 440_000_000
        assert "receive frequency" in msg

    def test_sort_by_transmit_frequency(self, stub_radio):
        # tx = freq (+/-) offset by duplex; split -> offset is the tx freq.
        from chirp_backend.memory_ops import sort_range
        m0 = StubMemory(0, freq=146_000_000, name="plus")   # tx 146.6
        m0.duplex, m0.offset = "+", 600_000
        m1 = StubMemory(1, freq=145_000_000, name="simplex")  # tx 145.0
        m1.duplex, m1.offset = "", 0
        m2 = StubMemory(2, freq=147_000_000, name="minus")  # tx 146.4
        m2.duplex, m2.offset = "-", 600_000
        for m in (m0, m1, m2):
            stub_radio.set_memory(m)
        ok, msg, affected = sort_range([0, 1, 2], attr="txfreq")
        assert ok
        # Ascending tx order: 145.0 (simplex), 146.4 (minus), 146.6 (plus).
        assert stub_radio.get_memory(0).name == "simplex"
        assert stub_radio.get_memory(1).name == "minus"
        assert stub_radio.get_memory(2).name == "plus"
        assert "transmit frequency" in msg

    def test_tx_frequency_helper(self):
        from chirp_backend.memory_ops import tx_frequency
        m = StubMemory(0, freq=146_000_000)
        m.duplex, m.offset = "+", 600_000
        assert tx_frequency(m) == 146_600_000
        m.duplex = "-"
        assert tx_frequency(m) == 145_400_000
        m.duplex, m.offset = "split", 446_000_000
        assert tx_frequency(m) == 446_000_000
        m.duplex, m.offset = "", 600_000
        assert tx_frequency(m) == 146_000_000


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
# Tests: paste_block (cut / copy / paste of whole rows)
# ---------------------------------------------------------------------------

class TestPasteBlock:
    def _clip(self, *names):
        """Snapshot rows like the clipboard would. Numbers are placeholders —
        paste_block renumbers each row to its destination slot."""
        return [
            StubMemory(i, freq=146_000_000 + i, name=nm)
            for i, nm in enumerate(names)
        ]

    def test_copy_overwrite_into_empty(self, stub_radio):
        from chirp_backend.memory_ops import paste_block
        ok, msg, affected = paste_block(self._clip("A", "B"), destination=10)
        assert ok
        assert stub_radio.get_memory(10).name == "A"
        assert stub_radio.get_memory(11).name == "B"
        assert 10 in affected and 11 in affected
        assert "Pasted" in msg

    def test_copy_overwrites_occupied(self, stub_radio):
        _fill(stub_radio, (10, "OLD"))
        from chirp_backend.memory_ops import paste_block
        ok, _, _ = paste_block(self._clip("NEW"), destination=10)
        assert ok
        assert stub_radio.get_memory(10).name == "NEW"

    def test_cut_move_erases_source(self, stub_radio):
        _fill(stub_radio, (5, "A"), (6, "B"))
        from chirp_backend.memory_ops import paste_block
        ok, msg, _ = paste_block(self._clip("A", "B"), destination=10, cut_from=[5, 6])
        assert ok
        assert stub_radio.get_memory(10).name == "A"
        assert stub_radio.get_memory(11).name == "B"
        assert stub_radio.get_memory(5).empty
        assert stub_radio.get_memory(6).empty
        assert "Moved" in msg

    def test_cut_move_with_overlap(self, stub_radio):
        # Cut 5,6,7 then paste at 6 (overlaps source). Snapshot makes it safe.
        _fill(stub_radio, (5, "A"), (6, "B"), (7, "C"))
        from chirp_backend.memory_ops import paste_block
        ok, _, _ = paste_block(
            self._clip("A", "B", "C"), destination=6, cut_from=[5, 6, 7]
        )
        assert ok
        assert stub_radio.get_memory(6).name == "A"
        assert stub_radio.get_memory(7).name == "B"
        assert stub_radio.get_memory(8).name == "C"
        assert stub_radio.get_memory(5).empty  # source not in dest range, erased

    def test_make_room_shifts_occupied_down(self, stub_radio):
        # 6,7,8 occupied; insert 2 rows at 6 -> old 6,7,8 shift to 8,9,10.
        _fill(stub_radio, (6, "X"), (7, "Y"), (8, "Z"))
        from chirp_backend.memory_ops import paste_block
        ok, _, _ = paste_block(self._clip("A", "B"), destination=6, make_room=True)
        assert ok
        assert stub_radio.get_memory(6).name == "A"
        assert stub_radio.get_memory(7).name == "B"
        assert stub_radio.get_memory(8).name == "X"
        assert stub_radio.get_memory(9).name == "Y"
        assert stub_radio.get_memory(10).name == "Z"

    def test_make_room_fails_without_empty_tail(self, stub_radio):
        # Fill every channel 0..19; no room to shift -> fail, radio unchanged.
        _fill(stub_radio, *[(i, f"C{i}") for i in range(20)])
        from chirp_backend.memory_ops import paste_block
        ok, msg, affected = paste_block(self._clip("A"), destination=5, make_room=True)
        assert not ok
        assert affected == []
        assert stub_radio.get_memory(5).name == "C5"  # unchanged

    def test_make_room_finds_highest_occupied_across_gap(self, stub_radio):
        # Only channel 18 occupied; 5..17 empty. The tail-first occupancy scan
        # must still find 18 (not stop at the empties) so shifting it down by 2
        # off the end (18+2 > 19) is correctly rejected.
        _fill(stub_radio, (18, "T"))
        from chirp_backend.memory_ops import paste_block
        ok, _, affected = paste_block(
            self._clip("A", "B"), destination=5, make_room=True
        )
        assert not ok
        assert affected == []
        assert stub_radio.get_memory(18).name == "T"  # unchanged

    def test_make_room_across_gap_succeeds_with_room(self, stub_radio):
        # Same gap layout but the occupied slot is low enough to shift down by 2.
        _fill(stub_radio, (10, "T"))
        from chirp_backend.memory_ops import paste_block
        ok, _, _ = paste_block(self._clip("A", "B"), destination=5, make_room=True)
        assert ok
        assert stub_radio.get_memory(5).name == "A"
        assert stub_radio.get_memory(6).name == "B"
        assert stub_radio.get_memory(12).name == "T"  # 10 shifted down by 2

    def test_out_of_range_fails(self, stub_radio):
        from chirp_backend.memory_ops import paste_block
        ok, _, _ = paste_block(self._clip("A", "B"), destination=19)  # 19,20 -> OOB
        assert not ok

    def test_empty_clipboard_fails(self, stub_radio):
        from chirp_backend.memory_ops import paste_block
        ok, _, _ = paste_block([], destination=5)
        assert not ok

    def test_cut_make_room_combined(self, stub_radio):
        # Cut source below destination, paste with make_room at occupied slots.
        _fill(stub_radio, (2, "S1"), (3, "S2"), (10, "X"), (11, "Y"))
        from chirp_backend.memory_ops import paste_block
        ok, _, _ = paste_block(
            self._clip("S1", "S2"), destination=10, cut_from=[2, 3], make_room=True
        )
        assert ok
        assert stub_radio.get_memory(2).empty and stub_radio.get_memory(3).empty
        assert stub_radio.get_memory(10).name == "S1"
        assert stub_radio.get_memory(11).name == "S2"
        assert stub_radio.get_memory(12).name == "X"
        assert stub_radio.get_memory(13).name == "Y"


class TestImportMemories:
    """import_memories, incl. the numbers= subset (results-picker) path.

    import_logic.import_mem is stubbed to identity so these exercise the
    selection/placement logic, not CHIRP's field adaptation (which needs real
    driver Memory objects — covered by the live end-to-end drive)."""

    def _source(self):
        src = StubRadio(num_channels=5)
        for i in range(5):
            src.set_memory(StubMemory(i, freq=146_000_000 + i * 100_000,
                                      name=f"R{i}", empty=False))
        return src

    @pytest.fixture
    def identity_import(self, monkeypatch):
        monkeypatch.setattr("chirp.import_logic.import_mem",
                            lambda target, feats, mem: mem.dupe())

    def test_import_all(self, stub_radio, identity_import):
        from chirp_backend.memory_ops import import_memories
        ok, _msg, affected = import_memories(self._source(), 0, overwrite=True)
        assert ok
        assert affected == [0, 1, 2, 3, 4]  # empties 5..19 skipped
        assert stub_radio.get_memory(0).name == "R0"

    def test_import_subset_places_selected_consecutively(self, stub_radio, identity_import):
        from chirp_backend.memory_ops import import_memories
        ok, _msg, affected = import_memories(
            self._source(), 3, overwrite=True, numbers=[0, 2, 4]
        )
        assert ok
        assert affected == [3, 4, 5]
        assert stub_radio.get_memory(3).name == "R0"
        assert stub_radio.get_memory(4).name == "R2"
        assert stub_radio.get_memory(5).name == "R4"

    def test_import_subset_ignores_dupes_and_out_of_range(self, stub_radio, identity_import):
        from chirp_backend.memory_ops import import_memories
        ok, _msg, affected = import_memories(
            self._source(), 0, overwrite=True, numbers=[2, 2, 99, -1, 0]
        )
        assert ok
        assert affected == [0, 1]  # {0, 2}, ascending
        assert stub_radio.get_memory(0).name == "R0"
        assert stub_radio.get_memory(1).name == "R2"

    def test_import_empty_subset_imports_nothing(self, stub_radio, identity_import):
        from chirp_backend.memory_ops import import_memories
        ok, _msg, affected = import_memories(
            self._source(), 0, overwrite=True, numbers=[]
        )
        assert not ok  # imported 0 -> ok is False
        assert affected == []
