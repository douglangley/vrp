"""Unit tests for chirp_backend/undo.py (pure UndoManager, no wx, no hardware).

A minimal stub radio provides get/set/erase. We drive the manager the way the
real wiring will: record(number) before each write, inside a transaction; then
undo/redo and check the stub's channel contents round-trip."""

import sys
import os

# Allow importing chirp_backend when run as a script.
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from chirp_backend.undo import UndoManager  # noqa: E402


class StubMemory:
    def __init__(self, number, name="", empty=False):
        self.number = number
        self.name = name
        self.empty = empty

    def dupe(self):
        import copy
        return copy.copy(self)


class StubRadio:
    def __init__(self, n=20):
        self._c = {i: StubMemory(i, empty=True) for i in range(n)}

    def get_memory(self, number):
        return self._c[number]

    def set_memory(self, mem):
        self._c[mem.number] = mem

    def erase_memory(self, number):
        self._c[number] = StubMemory(number, empty=True)


def _mgr(radio, **kw):
    return UndoManager(radio.get_memory, radio.set_memory, radio.erase_memory, **kw)


def _fill(radio, number, name):
    radio.set_memory(StubMemory(number, name=name))


def _edit(radio, mgr, number, name):
    """Simulate an op: record the pre-image, then write — inside a transaction."""
    with mgr.transaction(f"Edit {number}"):
        mgr.record(number)
        radio.set_memory(StubMemory(number, name=name))


def test_undo_restores_before_image():
    radio = StubRadio()
    _fill(radio, 5, "A")
    mgr = _mgr(radio)

    _edit(radio, mgr, 5, "B")
    assert radio.get_memory(5).name == "B"

    label, nums = mgr.undo()
    assert label == "Edit 5" and nums == [5]
    assert radio.get_memory(5).name == "A"


def test_redo_restores_after_image():
    radio = StubRadio()
    _fill(radio, 5, "A")
    mgr = _mgr(radio)
    _edit(radio, mgr, 5, "B")

    mgr.undo()
    assert radio.get_memory(5).name == "A"
    label, nums = mgr.redo()
    assert label == "Edit 5" and nums == [5]
    assert radio.get_memory(5).name == "B"


def test_new_op_clears_redo():
    radio = StubRadio()
    _fill(radio, 5, "A")
    mgr = _mgr(radio)
    _edit(radio, mgr, 5, "B")
    mgr.undo()
    assert mgr.can_redo()

    _edit(radio, mgr, 6, "C")  # a new op invalidates the redo branch
    assert not mgr.can_redo()
    assert mgr.redo() is None


def test_nested_transactions_make_one_entry():
    radio = StubRadio()
    _fill(radio, 1, "one")
    _fill(radio, 2, "two")
    mgr = _mgr(radio)

    with mgr.transaction("outer"):
        mgr.record(1)
        radio.set_memory(StubMemory(1, name="ONE"))
        with mgr.transaction("inner"):  # e.g. delete_and_shift -> delete_range
            mgr.record(2)
            radio.set_memory(StubMemory(2, name="TWO"))

    assert mgr.peek_undo_label() == "outer"
    label, nums = mgr.undo()
    assert label == "outer" and sorted(nums) == [1, 2]
    assert radio.get_memory(1).name == "one"
    assert radio.get_memory(2).name == "two"
    assert not mgr.can_undo()  # the inner op did not push its own entry


def test_empty_transaction_pushes_nothing():
    radio = StubRadio()
    mgr = _mgr(radio)
    with mgr.transaction("noop"):
        pass  # no record/write
    assert not mgr.can_undo()


def test_record_only_first_touch_per_channel():
    radio = StubRadio()
    _fill(radio, 5, "A")
    mgr = _mgr(radio)
    with mgr.transaction("multi"):
        mgr.record(5)
        radio.set_memory(StubMemory(5, name="B"))
        mgr.record(5)  # ignored — original "A" already captured
        radio.set_memory(StubMemory(5, name="C"))
    mgr.undo()
    assert radio.get_memory(5).name == "A"  # back to the very first pre-image


def test_empty_preimage_undo_erases():
    radio = StubRadio()  # channel 5 starts empty
    mgr = _mgr(radio)
    with mgr.transaction("fill 5"):
        mgr.record(5)  # captures the empty slot
        radio.set_memory(StubMemory(5, name="NEW"))
    assert not radio.get_memory(5).empty

    mgr.undo()
    assert radio.get_memory(5).empty  # restored to blank by erasing


def test_stack_is_bounded():
    radio = StubRadio()
    mgr = _mgr(radio, max_depth=2)
    for i in range(3):
        _edit(radio, mgr, 5, f"v{i}")
    # Only the last two ops are retained.
    assert mgr.undo() is not None  # v2 -> v1
    assert mgr.undo() is not None  # v1 -> v0
    assert mgr.undo() is None      # the first op was dropped


def test_undo_redo_empty_returns_none():
    radio = StubRadio()
    mgr = _mgr(radio)
    assert mgr.undo() is None
    assert mgr.redo() is None


def test_transaction_aborts_on_exception():
    radio = StubRadio()
    _fill(radio, 5, "A")
    mgr = _mgr(radio)
    try:
        with mgr.transaction("boom"):
            mgr.record(5)
            radio.set_memory(StubMemory(5, name="B"))
            raise ValueError("op failed")
    except ValueError:
        pass
    # The aborted op leaves no undo entry (the partial write itself stands; undo
    # history just doesn't record a failed op).
    assert not mgr.can_undo()


def test_clear_drops_history():
    radio = StubRadio()
    _fill(radio, 5, "A")
    mgr = _mgr(radio)
    _edit(radio, mgr, 5, "B")
    mgr.undo()
    mgr.clear()
    assert not mgr.can_undo() and not mgr.can_redo()
