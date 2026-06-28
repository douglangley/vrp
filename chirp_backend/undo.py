"""Undo/redo history for channel-memory operations (pure, framework-agnostic).

Every channel write funnels through the loaded radio's ``set_memory`` /
``erase_memory``, so this manager records a per-channel **pre-image** for each
channel a top-level operation touches — inside a ref-counted **transaction** —
and, at commit, the matching **after-image**. Undo restores the before-images;
redo restores the after-images. One transaction = one history entry.

Radio access (read/write) is **injected** (``get_memory`` / ``set_memory`` /
``erase_memory``), so this module has no wx and no global state and is
unit-testable headless. The recorder hook (radio.py) calls :meth:`record` before
each write; the ``@records`` decorator (memory_ops) opens a transaction per op.

Design notes:
- **Ref-counted transactions**: ops that call other ops (``delete_and_shift`` →
  ``delete_range``) nest; inner calls record into the outer transaction and only
  the outermost commits one entry.
- **Pre-image once per channel**: the first write to a channel in a transaction is
  captured; later writes to the same channel are ignored (we already hold the
  original).
- **A new op clears the redo branch** (standard history semantics).
- Undo/redo restores run with recording **suspended**, so they never create new
  history entries.
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from dataclasses import dataclass

LOG = logging.getLogger(__name__)

DEFAULT_MAX_DEPTH = 30


@dataclass
class _Entry:
    """One undoable operation: the touched channels' state before and after.

    ``before``/``after`` are lists of Memory snapshots (each carries ``.number``
    and ``.empty``); an empty snapshot means the slot was blank, so restoring it
    erases rather than sets."""

    label: str
    before: list
    after: list


class UndoManager:
    """A bounded undo + redo history over injected radio read/write callables."""

    def __init__(self, get_memory, set_memory, erase_memory,
                 max_depth: int = DEFAULT_MAX_DEPTH) -> None:
        self._get = get_memory
        self._set = set_memory
        self._erase = erase_memory
        self._max = max_depth
        self._undo: list[_Entry] = []
        self._redo: list[_Entry] = []
        # Open-transaction state.
        self._depth = 0
        self._label: str | None = None
        self._before: dict[int, object] = {}
        self._order: list[int] = []
        self._applying = False  # True while restoring (suppresses recording)

    # -- transaction --------------------------------------------------

    @contextmanager
    def transaction(self, label: str):
        """Run a top-level op as one history entry. Commits on clean exit, aborts
        (records nothing) if the body raises (the exception still propagates)."""
        self.begin(label)
        ok = False
        try:
            yield
            ok = True
        finally:
            self.commit() if ok else self.abort()

    def begin(self, label: str) -> None:
        if self._depth == 0:
            self._label = label
            self._before = {}
            self._order = []
        self._depth += 1

    def record(self, number: int) -> None:
        """Capture the current (pre-write) state of ``number`` once per
        transaction. Call **before** the write. No-op when no transaction is open
        or while applying an undo/redo."""
        if self._depth == 0 or self._applying or number in self._before:
            return
        try:
            self._before[number] = self._get(number).dupe()
        except Exception:  # noqa: BLE001 — can't snapshot: skip (best effort)
            LOG.exception("undo: failed to snapshot channel %s", number)
            return
        self._order.append(number)

    def commit(self) -> None:
        if self._depth == 0:
            return
        self._depth -= 1
        if self._depth > 0:
            return  # inner transaction; the outermost commits
        if not self._order:  # nothing was written
            self._reset_txn()
            return
        before = [self._before[n] for n in self._order]
        after = []
        for n in self._order:
            try:
                after.append(self._get(n).dupe())
            except Exception:  # noqa: BLE001
                LOG.exception("undo: failed to capture after-image for %s", n)
        self._undo.append(_Entry(self._label or "", before, after))
        if len(self._undo) > self._max:
            self._undo.pop(0)
        self._redo.clear()
        self._reset_txn()

    def abort(self) -> None:
        if self._depth == 0:
            return
        self._depth -= 1
        if self._depth == 0:
            self._reset_txn()

    def _reset_txn(self) -> None:
        self._label = None
        self._before = {}
        self._order = []

    # -- undo / redo --------------------------------------------------

    def undo(self) -> tuple[str, list[int]] | None:
        """Restore the most recent op's before-images. Returns ``(label,
        restored_channel_numbers)`` or ``None`` when there's nothing to undo."""
        if not self._undo:
            return None
        entry = self._undo.pop()
        self._apply(entry.before)
        self._redo.append(entry)
        return entry.label, [m.number for m in entry.before]

    def redo(self) -> tuple[str, list[int]] | None:
        """Re-apply the most recently undone op's after-images. Returns ``(label,
        restored_channel_numbers)`` or ``None`` when there's nothing to redo."""
        if not self._redo:
            return None
        entry = self._redo.pop()
        self._apply(entry.after)
        self._undo.append(entry)
        return entry.label, [m.number for m in entry.after]

    def _apply(self, images: list) -> None:
        """Write a set of snapshots back to the radio without recording them.
        An empty snapshot erases its slot; otherwise it is set (from a dupe, so
        the stored snapshot stays pristine for a later undo/redo)."""
        self._applying = True
        try:
            for mem in images:
                if getattr(mem, "empty", False):
                    self._erase(mem.number)
                else:
                    self._set(mem.dupe())
        finally:
            self._applying = False

    # -- introspection ------------------------------------------------

    def can_undo(self) -> bool:
        return bool(self._undo)

    def can_redo(self) -> bool:
        return bool(self._redo)

    def peek_undo_label(self) -> str | None:
        return self._undo[-1].label if self._undo else None

    def peek_redo_label(self) -> str | None:
        return self._redo[-1].label if self._redo else None

    def clear(self) -> None:
        """Drop all history (on new image load / close / download)."""
        self._undo.clear()
        self._redo.clear()
        self._depth = 0
        self._applying = False
        self._reset_txn()
