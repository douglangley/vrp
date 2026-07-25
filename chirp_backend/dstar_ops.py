"""D-STAR call-list snapshots, verification, and migration safety.

Some older Icom radios store URCALL/RPTCALL values in radio-wide master lists
and keep only list indexes in each memory. CHIRP's ``import_mem`` adds missing
calls before it performs frequency conversion, validation, or the final memory
write. VRP therefore snapshots those lists before each DV conversion and
restores them if that channel fails.

Radios with ``requires_call_lists=False`` store calls directly in each
``DVMemory`` (or otherwise do not require list management) and intentionally
bypass this module.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from chirp import chirp_common


@dataclass(frozen=True)
class CallListSnapshot:
    """Exact radio-wide calls in driver order."""

    urcalls: tuple[str, ...]
    rptcalls: tuple[str, ...]


def requires_call_lists(radio) -> bool:
    """Return whether ``radio`` uses CHIRP's mutable D-STAR call-list contract."""
    if not isinstance(radio, chirp_common.IcomDstarSupport):
        return False
    try:
        return bool(radio.get_features().requires_call_lists)
    except Exception:  # noqa: BLE001 - capability discovery must stay safe
        return False


def memory_requires_call_lists(radio, memory) -> bool:
    return (
        isinstance(memory, chirp_common.DVMemory)
        and requires_call_lists(radio)
    )


def batch_requires_call_lists(radio, batch) -> bool:
    return requires_call_lists(radio) and any(
        isinstance(entry.memory, chirp_common.DVMemory)
        for entry in batch.entries
    )


def capture_call_lists(radio) -> CallListSnapshot:
    """Read both required call lists as immutable exact snapshots."""
    if not requires_call_lists(radio):
        raise ValueError("This radio does not require D-STAR call lists")
    return CallListSnapshot(
        tuple(str(call) for call in radio.get_urcall_list()),
        tuple(str(call) for call in radio.get_repeater_call_list()),
    )


def capture_for_memory(radio, memory) -> CallListSnapshot | None:
    if not memory_requires_call_lists(radio, memory):
        return None
    return capture_call_lists(radio)


def restore_call_lists(radio, snapshot: CallListSnapshot) -> None:
    """Restore and verify both lists exactly, raising if the driver diverges."""
    errors = []
    try:
        radio.set_urcall_list(list(snapshot.urcalls))
    except Exception as exc:  # noqa: BLE001 - still attempt the repeater list
        errors.append(f"URCALL restore failed: {exc}")
    try:
        radio.set_repeater_call_list(list(snapshot.rptcalls))
    except Exception as exc:  # noqa: BLE001
        errors.append(f"RPTCALL restore failed: {exc}")
    if errors:
        raise RuntimeError("; ".join(errors))

    restored = capture_call_lists(radio)
    if restored != snapshot:
        raise RuntimeError(
            "D-STAR call-list verification failed after restore: "
            f"expected {snapshot}, got {restored}"
        )


def added_calls(
    before: CallListSnapshot | None,
    after: CallListSnapshot | None,
) -> tuple[str, ...]:
    """Return newly introduced nonblank calls, preserving list order."""
    if before is None or after is None:
        return ()
    remaining = Counter(
        call for call in before.urcalls + before.rptcalls if call.strip()
    )
    added = []
    for call in after.urcalls + after.rptcalls:
        if not call.strip():
            continue
        if remaining[call]:
            remaining[call] -= 1
        else:
            added.append(call)
    return tuple(added)
