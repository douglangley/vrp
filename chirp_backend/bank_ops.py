"""Bank membership operations (Phase 6) — pure functions over the CHIRP bank model.

CHIRP exposes banks via radio.get_mapping_models() -> [MappingModel]. The mode is
encoded in the class: MTOBankModel = a memory may be in MANY banks (multi-select);
StaticBankModel = fixed/read-only (add/remove raise); a plain BankModel = zero or
one bank (single-select). Bank identity is the (opaque) get_index() value, which
may be a string ("1", "A") — treat it as an opaque key.

All CHIRP interaction lives here; the dialog stays UI-only (mirrors how
edit_dialog defers to memory_ops). Functions return data dicts or the standard
(ok, message, affected) tuple.
"""

from __future__ import annotations

import logging

LOG = logging.getLogger(__name__)


def _radio():
    from chirp_backend.radio import get_state

    state = get_state()
    return state.radio if state.loaded else None


def _bank_model():
    radio = _radio()
    if radio is None:
        return None
    try:
        models = radio.get_mapping_models()
    except Exception:  # noqa: BLE001
        return None
    return models[0] if models else None


def _mode(model) -> str:
    from chirp import chirp_common as cc

    if isinstance(model, getattr(cc, "StaticBankModel", ())):
        return "fixed"
    if isinstance(model, getattr(cc, "MTOBankModel", ())):
        return "multi"
    return "single"


def _bank_label(bank) -> str:
    name = (bank.get_name() or "").strip()
    idx = bank.get_index()
    return f"Bank {idx}: {name}" if name else f"Bank {idx}"


def has_bank() -> bool:
    """True if the loaded radio has a usable bank model."""
    radio = _radio()
    if radio is None:
        return False
    if not getattr(radio.get_features(), "has_bank", False):
        return False
    return _bank_model() is not None


def get_bank_state(number: int) -> dict:
    """Describe a channel's bank options + current membership for the dialog.

    Returns {ok, message, mode, read_only, banks: [(index, label)],
    member_indexes: set, number}. On any problem returns {ok: False, message}.
    """
    radio = _radio()
    if radio is None:
        return {"ok": False, "message": "No radio image is open."}
    model = _bank_model()
    if model is None:
        return {"ok": False, "message": "This radio has no banks."}
    try:
        mem = radio.get_memory(number)
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "message": f"Could not read channel {number}: {e}"}
    if getattr(mem, "empty", False):
        return {
            "ok": False,
            "message": f"Channel {number} is empty. Add a frequency before "
            "assigning it to a bank.",
        }

    mode = _mode(model)
    banks = model.get_mappings()
    try:
        member = {b.get_index() for b in model.get_memory_mappings(mem)}
    except Exception:  # noqa: BLE001
        member = set()
    return {
        "ok": True,
        "message": "",
        "mode": mode,
        "read_only": mode == "fixed",
        "banks": [(b.get_index(), _bank_label(b)) for b in banks],
        "member_indexes": member,
        "number": number,
    }


def apply_bank_changes(number: int, desired_indexes) -> tuple[bool, str, list]:
    """Apply the bank-membership diff for a channel; announce the new membership.

    Removes first then adds (helps zero-or-one radios). Reports truthfully if an
    add/remove raises (e.g. fixed banks). Returns (ok, message, affected).
    """
    radio = _radio()
    if radio is None:
        return False, "No radio image is open.", []
    model = _bank_model()
    if model is None:
        return False, "This radio has no banks.", []
    try:
        mem = radio.get_memory(number)
    except Exception as e:  # noqa: BLE001
        return False, f"Could not read channel {number}: {e}", []
    if getattr(mem, "empty", False):
        return False, f"Channel {number} is empty.", []

    by_index = {b.get_index(): b for b in model.get_mappings()}
    try:
        current = {b.get_index() for b in model.get_memory_mappings(mem)}
    except Exception:  # noqa: BLE001
        current = set()
    desired = set(desired_indexes)

    failures: list[str] = []
    for idx in current - desired:
        bank = by_index.get(idx)
        if bank is None:
            continue
        try:
            model.remove_memory_from_mapping(mem, bank)
        except Exception as e:  # noqa: BLE001
            failures.append(f"remove from {_bank_label(bank)}: {e}")
    for idx in desired - current:
        bank = by_index.get(idx)
        if bank is None:
            continue
        try:
            model.add_memory_to_mapping(mem, bank)
        except Exception as e:  # noqa: BLE001
            failures.append(f"add to {_bank_label(bank)}: {e}")

    from chirp_backend.radio import get_state

    get_state().is_modified = True

    if failures:
        return False, f"Some bank changes failed: {'; '.join(failures)}", [number]

    try:
        now = [
            (b.get_name() or "").strip() or f"Bank {b.get_index()}"
            for b in model.get_memory_mappings(radio.get_memory(number))
        ]
    except Exception:  # noqa: BLE001
        now = []
    membership = ", ".join(now) if now else "no banks"
    return True, f"Channel {number} is now in {membership}.", [number]
