"""
Memory channel operations — bulk and range operations on the radio image.

All functions here are pure operations: they take a RadioState (or radio
object directly) plus parameters, perform the operation, and return
(success, message, affected_channel_numbers).

This mirrors the operations available in CHIRP's memedit.py but decoupled
from any GUI. The affected_channel_numbers list tells the UI which channels to
re-read and refresh in the grid.

Reference: chirp/chirp/wxui/memedit.py methods:
  _delete_memories_at, _mem_insert, cb_move, _do_sort_memories,
  _arrange_memories, cb_find, cb_goto
"""

import logging
from typing import Optional

from chirp_backend import undo

LOG = logging.getLogger(__name__)

# Type alias for the return value of all operations
OpResult = tuple[bool, str, list[int]]


def _get_radio():
    """Get the active radio from global state."""
    from chirp_backend.radio import get_state
    state = get_state()
    if not state.loaded:
        raise RuntimeError("No radio loaded")
    return state.radio


def _mem_bounds() -> tuple[int, int]:
    from chirp_backend.radio import get_state
    return get_state().memory_bounds


def _get_mem(radio, number: int):
    """Get a memory from the radio (bypasses cache for fresh reads)."""
    return radio.get_memory(number)


def _set_mem(radio, mem) -> None:
    radio.set_memory(mem)


def _erase_mem(radio, number: int) -> None:
    radio.erase_memory(number)


# ---------------------------------------------------------------------------
# Single-field edit (Phase 2)
# ---------------------------------------------------------------------------

def _parse_field_value(radio, mem, field: str, value: str):
    """Convert a user-entered string into the right type for ``field``.

    Mirrors CHIRP's per-column digestion (chirp/wxui/memedit.py) using the
    library's own parsers so we accept the same inputs CHIRP does. Raises
    ValueError/TypeError on bad input (caller turns that into a friendly msg).
    """
    from chirp import chirp_common

    value = value.strip()
    if field in ("freq", "offset"):
        return chirp_common.parse_freq(value)
    if field in ("rtone", "ctone"):
        return float(value)
    if field in ("dtcs", "rx_dtcs"):
        return int(value)
    if field == "tuning_step":
        return float(value)
    if field == "power":
        for level in radio.get_features().valid_power_levels or []:
            if str(level) == value:
                return level
        raise ValueError(f"unknown power level {value!r}")
    # name, comment, and choice columns (tmode, duplex, mode, skip,
    # dtcs_polarity, cross_mode) are set as plain strings.
    return value


def _parse_all(radio, mem, values: dict):
    """Parse every field in ``values`` for ``mem``.

    Returns (parsed_by_field, error) where error is (field, message) on the
    first invalid value, else None. Immutable fields are skipped silently
    (the dialog disables them, so they shouldn't arrive, but be safe).
    """
    parsed: dict = {}
    immutable = mem.immutable or []
    for field, raw in values.items():
        if field in immutable or field == "number":
            continue
        try:
            parsed[field] = _parse_field_value(radio, mem, field, raw)
        except (ValueError, TypeError) as e:
            return {}, (field, f"Invalid {field}: {raw!r} ({e})")
    return parsed, None


def validate_channel_values(number: int, values: dict):
    """Validate (without writing) the values from the edit dialog.

    Returns (ok, message, bad_field) so the dialog can keep itself open and
    move focus to the offending control. ``bad_field`` is None on success.
    """
    try:
        radio = _get_radio()
    except RuntimeError as e:
        return False, str(e), None
    try:
        mem = _get_mem(radio, number)
    except Exception as e:  # noqa: BLE001
        return False, f"Could not read channel {number}: {e}", None
    _parsed, err = _parse_all(radio, mem, values)
    if err:
        return False, err[1], err[0]
    return True, "OK", None


@undo.records
def update_channel(number: int, values: dict) -> OpResult:
    """Apply several field edits to one channel atomically, then write it back.

    Parses everything first; only if all values are valid are they applied and
    the memory written once (so a bad value never leaves a half-edited channel).
    Returns (success, message, [number]).
    """
    try:
        radio = _get_radio()
    except RuntimeError as e:
        return False, str(e), []
    try:
        mem = _get_mem(radio, number)
    except Exception as e:  # noqa: BLE001
        return False, f"Could not read channel {number}: {e}", []

    parsed, err = _parse_all(radio, mem, values)
    if err:
        return False, err[1], []

    try:
        for field, val in parsed.items():
            setattr(mem, field, val)
        # A frequency makes a slot active; zero empties it.
        if "freq" in parsed:
            mem.empty = parsed["freq"] == 0
        _set_mem(radio, mem)
    except Exception as e:  # noqa: BLE001
        return False, f"Failed to update channel {number}: {e}", []

    from chirp_backend.radio import invalidate_cache

    invalidate_cache([number])
    return True, f"Channel {number} updated.", [number]


# Tone/DCS value fields -> the Tone Mode that makes CHIRP persist them. A tone or
# code is discarded unless the Tone Mode uses it, so a lone single-cell edit would
# silently revert (e.g. CTCSS back to the 88.5 default). set_channel_field repairs
# that by turning on the matching mode.
_TONE_MODE_FOR = {"ctone": "TSQL", "rtone": "Tone", "dtcs": "DTCS", "rx_dtcs": "DTCS"}
# A repeater Duplex direction with a zero Offset is meaningless, so CHIRP drops
# the direction. These directions therefore need a nonzero offset alongside them.
_DUPLEX_NEEDS_OFFSET = {"+": "plus", "-": "minus"}


def _field_persisted(radio, number: int, field: str, value) -> bool:
    """Whether the edit stuck: re-read the radio and compare the **parsed**
    intended value to the value now stored. Parsing first avoids type/formatting
    false-negatives — e.g. DTCS input "023" parses to the int 23 that's actually
    stored, where a display-string compare ("023" vs "23") would wrongly report a
    failure and force an unwanted coupling change. On any doubt, assume it stuck,
    so we never force a coupling change we're unsure about."""
    try:
        mem = _get_mem(radio, number)
        want = _parse_field_value(radio, mem, field, str(value))
    except Exception:  # noqa: BLE001
        return True
    got = getattr(mem, field, None)
    if isinstance(want, float) or isinstance(got, float):
        try:
            return abs(float(got) - float(want)) < 0.05
        except (TypeError, ValueError):
            return got == want
    return got == want


def _apply(radio, number: int, values: dict) -> bool:
    """Parse + set + write ``values`` on a fresh read of channel ``number``.
    Best-effort helper for coupling repairs; returns whether it applied."""
    try:
        mem = _get_mem(radio, number)
        parsed, err = _parse_all(radio, mem, values)
        if err:
            return False
        for f, v in parsed.items():
            setattr(mem, f, v)
            if f == "freq":
                mem.empty = v == 0
        _set_mem(radio, mem)
        return True
    except Exception:  # noqa: BLE001
        return False


def _repair_coupling(radio, number: int, field: str, value) -> str | None:
    """After a single-field edit that CHIRP silently dropped (because a governing
    field wasn't set), set the governing field too and re-apply so the edit
    sticks. Returns a short note describing what else was set, or ``None`` when
    nothing was needed. Empirical: only acts when the value truly didn't persist,
    so existing valid setups are left untouched."""
    mode = _TONE_MODE_FOR.get(field)
    if mode is not None:
        if _field_persisted(radio, number, field, value):
            return None
        if _apply(radio, number, {"tmode": mode, field: value}):
            return f"Tone Mode set to {mode} so it takes effect"
        return None

    if field == "duplex" and value in _DUPLEX_NEEDS_OFFSET:
        if _field_persisted(radio, number, field, value):
            return None  # already has an offset — the direction stuck
        from chirp_backend import bandplan

        try:
            mem = _get_mem(radio, number)
            hz = bandplan.suggest_offset_hz(getattr(mem, "freq", 0))
        except Exception:  # noqa: BLE001
            hz = 0
        if not hz:
            return None  # no standard offset for this band; can't auto-fill
        mhz = bandplan.offset_hz_to_mhz_str(hz)
        if _apply(radio, number, {"duplex": value, "offset": mhz}):
            return f"offset {mhz} MHz added so the {_DUPLEX_NEEDS_OFFSET[value]} shift takes effect"
        return None

    return None


@undo.records
def set_channel_field(number: int, field: str, value):
    """Apply one field edit; if a governing field would otherwise make CHIRP drop
    it (a tone/DCS field whose Tone Mode is off, or a Duplex direction with no
    Offset), set that governing field too and re-apply so the value persists. One
    undo step. Returns ``(ok, message, [number], note)`` where ``note`` is a short
    sentence about the coupled change we made, or ``None``.

    The check is empirical — re-read and compare — so an existing valid setup
    (TSQL / DTCS / Cross, or a direction that already has an offset) is untouched."""
    try:
        radio = _get_radio()
    except RuntimeError as e:
        return False, str(e), [], None
    try:
        mem = _get_mem(radio, number)
    except Exception as e:  # noqa: BLE001
        return False, f"Could not read channel {number}: {e}", [], None

    parsed, err = _parse_all(radio, mem, {field: value})
    if err:
        return False, err[1], [], None
    try:
        setattr(mem, field, parsed[field])
        if field == "freq":
            mem.empty = parsed[field] == 0
        _set_mem(radio, mem)
    except Exception as e:  # noqa: BLE001
        return False, f"Failed to update channel {number}: {e}", [], None

    note = _repair_coupling(radio, number, field, value)

    from chirp_backend.radio import invalidate_cache

    invalidate_cache([number])
    return True, f"Channel {number} updated.", [number], note


@undo.records
def import_memories(src_radio, destination: int, overwrite: bool = True) -> OpResult:
    """Import a query/source radio's memories into the loaded radio.

    Copies each non-empty source memory into consecutive destination channels
    starting at ``destination``, adapting it for the target radio via CHIRP's
    import_logic (handles mode/tone/power differences). With overwrite=False,
    occupied destination channels are skipped. Returns (ok, message, affected).
    """
    from chirp import import_logic

    try:
        target = _get_radio()
    except RuntimeError as e:
        return False, str(e), []

    tlo, thi = _mem_bounds()
    src_features = src_radio.get_features()
    slo, shi = src_features.memory_bounds

    dest = destination
    imported = overwritten = skipped = 0
    affected: list[int] = []
    for n in range(slo, shi + 1):
        if dest > thi:
            break
        try:
            src_mem = src_radio.get_memory(n)
        except Exception:  # noqa: BLE001
            continue
        if getattr(src_mem, "empty", False):
            continue

        existing = _get_mem(target, dest)
        if existing is not None and not existing.empty:
            if not overwrite:
                skipped += 1
                dest += 1
                continue
            overwritten += 1

        try:
            mem = import_logic.import_mem(target, src_features, src_mem)
            mem.number = dest
            _set_mem(target, mem)
            imported += 1
            affected.append(dest)
        except Exception as e:  # noqa: BLE001
            LOG.warning("import channel %s -> %s failed: %s", n, dest, e)
            skipped += 1
        dest += 1

    from chirp_backend.radio import get_state, invalidate_cache

    invalidate_cache(affected)
    get_state().is_modified = True

    parts = [f"Imported {imported} channel(s)"]
    if overwritten:
        parts.append(f"{overwritten} overwritten")
    if skipped:
        parts.append(f"{skipped} skipped")
    message = ", ".join(parts) + "."
    return imported > 0, message, affected


def parse_channel_spec(spec: str, low: int, high: int):
    """Parse an advanced channel list like "1-5,8,10-12" into sorted numbers.

    Accepts comma-separated singletons and ``a-b`` ranges (any order). Returns
    (numbers, error); ``numbers`` is sorted and de-duplicated, ``error`` is a
    friendly message (and numbers empty) on bad input or out-of-range values.
    """
    spec = (spec or "").strip()
    if not spec:
        return [], "Enter one or more channels, e.g. 1-5,8,10-12."

    numbers: list[int] = []
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            bits = part.split("-")
            if len(bits) != 2 or not bits[0].strip() or not bits[1].strip():
                return [], f"Invalid range: {part!r}"
            try:
                a, b = int(bits[0]), int(bits[1])
            except ValueError:
                return [], f"Invalid number in {part!r}"
            if a > b:
                a, b = b, a
            numbers.extend(range(a, b + 1))
        else:
            try:
                numbers.append(int(part))
            except ValueError:
                return [], f"Invalid channel: {part!r}"

    out = sorted(set(numbers))
    if not out:
        return [], "No channels specified."
    bad = [n for n in out if n < low or n > high]
    if bad:
        preview = ", ".join(str(n) for n in bad[:5])
        return [], f"Channel(s) out of range ({low} to {high}): {preview}"
    return out, None


# ---------------------------------------------------------------------------
# Single-channel operations
# ---------------------------------------------------------------------------

@undo.records
def delete_memory(number: int) -> OpResult:
    """Erase a single memory channel."""
    try:
        radio = _get_radio()
        mem = _get_mem(radio, number)
        if "empty" in (mem.immutable or []):
            return False, f"Channel {number} cannot be deleted", []
        _erase_mem(radio, number)
        from chirp_backend.radio import invalidate_cache
        invalidate_cache([number])
        return True, f"Channel {number} deleted", [number]
    except Exception as e:
        LOG.exception("delete_memory(%d)", number)
        return False, str(e), []


# ---------------------------------------------------------------------------
# Range delete operations
# ---------------------------------------------------------------------------

@undo.records
def delete_range(numbers: list[int]) -> OpResult:
    """
    Delete a list of channel numbers (erase each one).
    Does not shift any channels up.
    """
    try:
        radio = _get_radio()
        deleted = []
        errors = []
        for n in numbers:
            try:
                mem = _get_mem(radio, n)
                if "empty" in (mem.immutable or []):
                    errors.append(f"{n} (immutable)")
                    continue
                if not mem.empty:
                    _erase_mem(radio, n)
                deleted.append(n)
            except Exception as e:
                errors.append(f"{n} ({e})")

        from chirp_backend.radio import invalidate_cache
        invalidate_cache(deleted)

        if errors:
            return (
                len(deleted) > 0,
                f"Deleted {len(deleted)} channel(s). Errors on: {', '.join(errors)}",
                deleted,
            )
        return True, f"Deleted {len(deleted)} channel(s)", deleted

    except Exception as e:
        LOG.exception("delete_range")
        return False, str(e), []


@undo.records
def delete_and_shift(numbers: list[int], mode: str = "all") -> OpResult:
    """
    Delete channels and shift remaining channels up to fill the gap.

    mode:
      'all'   — shift everything from the deleted range to the end of the
                channel list up by len(numbers) slots.
      'block' — shift only the contiguous block immediately after the
                deleted range, stopping at the first empty channel.

    Mirrors CHIRP's _delete_memories_at(..., shift_up='all'/'block').
    """
    if not numbers:
        return False, "No channels specified", []

    try:
        radio = _get_radio()
        first, last_bound = _mem_bounds()
        numbers_sorted = sorted(numbers)
        delta = len(numbers_sorted)
        next_after = numbers_sorted[-1] + 1

        # First, collect which memories to shift up
        mems_to_move = []
        for n in range(next_after, last_bound + 1):
            try:
                mem = _get_mem(radio, n)
            except Exception:
                break
            if isinstance(mem.extd_number, str) and mem.extd_number:
                break   # hit special channels
            if mode == "block" and mem.empty:
                break
            mems_to_move.append(mem.dupe())

        # Delete the target channels
        ok, msg, deleted = delete_range(numbers_sorted)
        if not ok and not deleted:
            return ok, msg, deleted

        # Shift mems_to_move up by delta
        affected = list(deleted)
        for mem in mems_to_move:
            new_number = mem.number - delta
            mem.number = new_number
            if mem.empty:
                _erase_mem(radio, new_number)
            else:
                _set_mem(radio, mem)
            affected.append(new_number)

        # Erase the now-duplicated tail slots
        if mems_to_move:
            last_moved_orig = mems_to_move[-1].number + delta
            first_hole = mems_to_move[-1].number + 1
            for n in range(first_hole, last_moved_orig + 1):
                try:
                    _erase_mem(radio, n)
                    affected.append(n)
                except Exception:
                    pass

        from chirp_backend.radio import invalidate_cache
        invalidate_cache(affected)

        return (
            True,
            f"Deleted {len(numbers_sorted)} channel(s) and shifted {len(mems_to_move)} up",
            sorted(set(affected)),
        )

    except Exception as e:
        LOG.exception("delete_and_shift")
        return False, str(e), []


# ---------------------------------------------------------------------------
# Insert row (shift down to create a blank slot)
# ---------------------------------------------------------------------------

@undo.records
def insert_row(row_number: int) -> OpResult:
    """
    Insert a blank channel at row_number by finding the next empty slot
    below and shifting everything between down by one.

    Mirrors CHIRP's _mem_insert().
    """
    try:
        radio = _get_radio()
        first, last_bound = _mem_bounds()

        # Find the next empty slot at or below row_number
        empty_slot = None
        for n in range(row_number, last_bound + 1):
            mem = _get_mem(radio, n)
            if mem.empty:
                empty_slot = n
                break

        if empty_slot is None:
            return False, "No empty channel slots below to shift into", []

        affected = []
        # Shift memories down in reverse order from empty_slot to row_number+1
        for target in range(empty_slot, row_number, -1):
            mem = _get_mem(radio, target - 1).dupe()
            mem.number = target
            _set_mem(radio, mem)
            affected.append(target)

        # Erase the newly freed slot at row_number
        _erase_mem(radio, row_number)
        affected.append(row_number)

        from chirp_backend.radio import invalidate_cache
        invalidate_cache(affected)

        return True, f"Inserted blank channel at {row_number}", sorted(affected)

    except Exception as e:
        LOG.exception("insert_row(%d)", row_number)
        return False, str(e), []


# ---------------------------------------------------------------------------
# Move operations
# ---------------------------------------------------------------------------

@undo.records
def move_memories(numbers: list[int], direction: int) -> OpResult:
    """
    Move a selected range of channels up (-1) or down (+1) by one slot.
    Swaps the selected block with the adjacent channel.

    Mirrors CHIRP's cb_move().
    direction must be +1 or -1.
    """
    if direction not in (-1, 1):
        return False, "Direction must be +1 or -1", []

    try:
        radio = _get_radio()
        first_bound, last_bound = _mem_bounds()
        numbers_sorted = sorted(numbers)
        first = numbers_sorted[0]
        last = numbers_sorted[-1]

        if direction < 0 and first == first_bound:
            return False, "Cannot move above the first channel", []
        if direction > 0 and last == last_bound:
            return False, "Cannot move below the last channel", []

        # The channel that gets displaced
        if direction < 0:
            transplant_n = first + direction
        else:
            transplant_n = last + direction

        transplant = _get_mem(radio, transplant_n).dupe()
        new_transplant_number = last if direction < 0 else first
        transplant.number = new_transplant_number

        affected = [transplant_n, new_transplant_number]
        to_set = [transplant]

        for n in numbers_sorted:
            mem = _get_mem(radio, n).dupe()
            mem.number = n + direction
            to_set.append(mem)
            affected.append(mem.number)

        for mem in to_set:
            _set_mem(radio, mem)

        from chirp_backend.radio import invalidate_cache
        invalidate_cache(affected)

        direction_word = "up" if direction < 0 else "down"
        return (
            True,
            f"Moved {len(numbers)} channel(s) {direction_word}",
            sorted(set(affected)),
        )

    except Exception as e:
        LOG.exception("move_memories")
        return False, str(e), []


@undo.records
def move_to(numbers: list[int], destination: int) -> OpResult:
    """
    Move a block of channels to start at destination.
    Source channels are erased after the move.

    This is an extension beyond CHIRP's one-step move — allows jumping
    a selection to any target channel number in one operation.
    """
    try:
        radio = _get_radio()
        first_bound, last_bound = _mem_bounds()
        numbers_sorted = sorted(numbers)
        count = len(numbers_sorted)

        if destination < first_bound or destination + count - 1 > last_bound:
            return False, f"Destination out of range ({first_bound}–{last_bound})", []

        # Check destination range doesn't overlap with source
        dest_range = set(range(destination, destination + count))
        src_range = set(numbers_sorted)
        overlap = dest_range & src_range
        if overlap and overlap != src_range:
            return False, "Destination overlaps with source (partial overlap not allowed)", []

        # Read source memories
        source_mems = [_get_mem(radio, n).dupe() for n in numbers_sorted]
        affected = list(numbers_sorted) + list(dest_range)

        # Write to destination
        for i, mem in enumerate(source_mems):
            mem.number = destination + i
            _set_mem(radio, mem)

        # Erase source (only if not in dest_range)
        for n in numbers_sorted:
            if n not in dest_range:
                _erase_mem(radio, n)

        from chirp_backend.radio import invalidate_cache
        invalidate_cache(sorted(set(affected)))

        return (
            True,
            f"Moved {count} channel(s) to start at channel {destination}",
            sorted(set(affected)),
        )

    except Exception as e:
        LOG.exception("move_to")
        return False, str(e), []


@undo.records
def copy_memories(numbers: list[int], destination: int) -> OpResult:
    """
    Copy a block of channels to start at destination.
    Source channels are NOT erased.
    """
    try:
        radio = _get_radio()
        first_bound, last_bound = _mem_bounds()
        numbers_sorted = sorted(numbers)
        count = len(numbers_sorted)

        if destination < first_bound or destination + count - 1 > last_bound:
            return False, f"Destination out of range ({first_bound}–{last_bound})", []

        source_mems = [_get_mem(radio, n).dupe() for n in numbers_sorted]
        dest_range = list(range(destination, destination + count))

        for i, mem in enumerate(source_mems):
            mem.number = dest_range[i]
            _set_mem(radio, mem)

        from chirp_backend.radio import invalidate_cache
        invalidate_cache(dest_range)

        return (
            True,
            f"Copied {count} channel(s) to channel {destination}",
            dest_range,
        )

    except Exception as e:
        LOG.exception("copy_memories")
        return False, str(e), []


# ---------------------------------------------------------------------------
# Clipboard paste (cut / copy / paste of whole rows)
# ---------------------------------------------------------------------------

@undo.records
def paste_block(
    mems: list,
    destination: int,
    *,
    cut_from: Optional[list[int]] = None,
    make_room: bool = False,
) -> OpResult:
    """Paste a snapshot block of Memory objects starting at ``destination``.

    ``mems`` are duplicated and renumbered to ``destination .. destination+N-1``.
    By default the destination slots are **overwritten**. With ``make_room`` the
    occupied channels from ``destination`` onward are first shifted **down** by
    ``N`` to open a gap; this fails (no change) if there aren't ``N`` empty slots
    near the tail to absorb the shift, so nothing falls off the fixed-size radio.

    ``cut_from`` (the cut/move case) is the list of original source channel
    numbers; they are erased first, then the block is written — so source and
    destination may overlap freely (the data lives in ``mems``). ``cut_from=None``
    is a plain copy (source kept).

    Returns ``(ok, message, affected_channels)``. Mirrors the overwrite behavior
    of :func:`copy_memories`/:func:`move_to` but takes a snapshot block instead of
    re-reading by number, and adds the make-room (insert) option.
    """
    if not mems:
        return False, "Nothing to paste", []

    try:
        radio = _get_radio()
        first_bound, last_bound = _mem_bounds()
        n = len(mems)
        dest_end = destination + n - 1
        dest_range = list(range(destination, dest_end + 1))
        cut_set = set(cut_from or [])

        if destination < first_bound or dest_end > last_bound:
            return False, f"Destination out of range ({first_bound}-{last_bound})", []

        if make_room:
            # Highest occupied channel in [destination, last_bound], treating the
            # cut sources as already empty (they get erased below). Everything
            # from destination up to it shifts down by n, so require room for it
            # before touching anything (atomic: fail leaves the radio unchanged).
            last_nonempty = None
            for k in range(destination, last_bound + 1):
                if k in cut_set:
                    continue
                if not _get_mem(radio, k).empty:
                    last_nonempty = k
            if last_nonempty is not None and last_nonempty + n > last_bound:
                return (
                    False,
                    f"Not enough empty channels to make room for {n} channel(s)",
                    [],
                )

        affected: list[int] = []

        # Cut: erase the sources first (their data is safely in `mems`). Doing it
        # up front keeps the make-room math simple and makes overlap a non-issue.
        for s in cut_set:
            _erase_mem(radio, s)
            affected.append(s)

        if make_room:
            # Open the gap: shift [destination, last_bound-n] down by n, high to
            # low so an unread source is never clobbered. The bottom n slots keep
            # stale copies until the paste overwrites them just below.
            for k in range(last_bound - n, destination - 1, -1):
                mem = _get_mem(radio, k).dupe()
                mem.number = k + n
                if mem.empty:
                    _erase_mem(radio, k + n)
                else:
                    _set_mem(radio, mem)
                affected.append(k + n)

        # Write the snapshot block over the destination slots.
        for i, src in enumerate(mems):
            mem = src.dupe()
            mem.number = dest_range[i]
            if mem.empty:
                _erase_mem(radio, mem.number)
            else:
                _set_mem(radio, mem)
            affected.append(mem.number)

        from chirp_backend.radio import invalidate_cache
        invalidate_cache(sorted(set(affected)))

        verb = "Moved" if cut_set else "Pasted"
        return (
            True,
            f"{verb} {n} channel(s) to channel {destination}",
            sorted(set(affected)),
        )

    except Exception as e:
        LOG.exception("paste_block")
        return False, str(e), []


# ---------------------------------------------------------------------------
# Sort and arrange
# ---------------------------------------------------------------------------

@undo.records
def sort_range(numbers: list[int], attr: str, reverse: bool = False) -> OpResult:
    """
    Sort a contiguous range of channels by a Memory attribute.

    attr must be a valid chirp_common.Memory field name:
      'freq', 'name', 'tmode', 'mode', 'duplex', 'skip', etc.

    Mirrors CHIRP's _do_sort_memories().
    """
    try:
        radio = _get_radio()
        numbers_sorted = sorted(numbers)

        mems = [_get_mem(radio, n).dupe() for n in numbers_sorted]

        # Sort by attr; treat None/empty as sorts-last
        def sort_key(m):
            val = getattr(m, attr, None)
            if val is None:
                return (1, "")
            return (0, str(val).lower())

        mems.sort(key=sort_key, reverse=reverse)

        for i, mem in enumerate(mems):
            mem.number = numbers_sorted[i]
            _set_mem(radio, mem)

        from chirp_backend.radio import invalidate_cache
        invalidate_cache(numbers_sorted)

        direction = "descending" if reverse else "ascending"
        return (
            True,
            f"Sorted {len(numbers_sorted)} channel(s) by {attr} ({direction})",
            numbers_sorted,
        )

    except Exception as e:
        LOG.exception("sort_range")
        return False, str(e), []


@undo.records
def arrange_range(numbers: list[int]) -> OpResult:
    """
    Compact a range: move all non-empty channels to the top of the range,
    pushing empty slots to the bottom.

    Mirrors CHIRP's _arrange_memories() which sorts by mem.empty.
    """
    return sort_range(numbers, "empty", reverse=False)


# ---------------------------------------------------------------------------
# Find and goto
# ---------------------------------------------------------------------------

def find(
    text: str,
    start_number: Optional[int] = None,
    search_fields: tuple = ("freq", "name", "comment"),
) -> OpResult:
    """
    Search channel fields for text (case-insensitive).
    Returns the first matching channel number after start_number,
    wrapping around if necessary.

    Returns affected=[matching_channel_number] on success, affected=[] if not found.
    """
    try:
        radio = _get_radio()
        first_bound, last_bound = _mem_bounds()
        text_lower = text.lower()
        start = start_number if start_number is not None else first_bound
        total = last_bound - first_bound + 1

        for offset in range(total):
            n = first_bound + (start - first_bound + offset) % total
            try:
                mem = _get_mem(radio, n)
                if mem.empty:
                    continue
                for field_name in search_fields:
                    val = getattr(mem, field_name, None)
                    if val is None:
                        continue
                    # Format freq as MHz string for search — the same form the
                    # grid shows (min 3 decimals), so a search for what the user
                    # sees ("146.000") matches, and a partial "146" still does.
                    if field_name == "freq":
                        from chirp_backend.col_defs import format_freq_mhz
                        val = format_freq_mhz(val)
                    else:
                        val = str(val)
                    if text_lower in val.lower():
                        return True, f"Found '{text}' at channel {n}", [n]
            except Exception:
                continue

        return False, f"'{text}' not found", []

    except Exception as e:
        LOG.exception("find")
        return False, str(e), []
