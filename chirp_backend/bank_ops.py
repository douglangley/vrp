"""Bank discovery, membership editing, and cross-radio mapping support.

CHIRP exposes banks through ``radio.get_mapping_models()``. Bank indexes are
opaque driver identifiers (often strings), names may be blank or duplicated,
and several real drivers allow multiple memberships without inheriting
``MTOBankModel``. This module therefore treats the driver's live mapping API as
the authority and never infers cross-radio equivalence from class names.

Cross-radio policy:

* a source bank is mapped only after the user confirms an explicit plan;
* unique, non-empty exact-name matches may be suggested but are not applied
  until that confirmation;
* successfully imported channels receive exactly their mapped memberships;
* fixed destination banks are reported as unavailable rather than modified;
* a failed per-channel bank change is rolled back before it is reported.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, replace

from chirp_backend import undo

LOG = logging.getLogger(__name__)


@dataclass(frozen=True)
class BankDescriptor:
    """One bank in driver order, with its opaque identity and accessible label."""

    position: int
    index: object
    name: str
    label: str
    member_count: int = 0


@dataclass(frozen=True)
class BankCatalog:
    """Readable destination/source bank capabilities."""

    available: bool
    mutable: bool
    mode: str
    indexed: bool
    banks: tuple[BankDescriptor, ...] = ()
    message: str = ""


@dataclass(frozen=True)
class BankMembership:
    """One exact membership snapshot, including driver ordering when exposed."""

    index: object
    order: object | None = None


@dataclass(frozen=True)
class BankMembershipSnapshot:
    memberships: tuple[BankMembership, ...] = ()


def _radio():
    from chirp_backend.radio import get_state

    state = get_state()
    return state.radio if state.loaded else None


def bank_model_for(radio):
    """Return the first CHIRP BankModel, not merely the first mapping model."""
    if radio is None:
        return None
    from chirp import chirp_common as cc

    try:
        models = radio.get_mapping_models()
    except Exception:  # noqa: BLE001
        return None
    return next(
        (model for model in (models or []) if isinstance(model, cc.BankModel)),
        None,
    )


def _bank_model():
    return bank_model_for(_radio())


def _mode(model) -> str:
    from chirp import chirp_common as cc

    if isinstance(model, getattr(cc, "StaticBankModel", ())):
        return "fixed"
    if isinstance(model, getattr(cc, "MTOBankModel", ())):
        return "multi"
    return "single"


def _clean_name(value) -> str:
    return str(value or "").replace("\x00", "").strip()


def _bank_label(bank) -> str:
    name = _clean_name(bank.get_name())
    idx = bank.get_index()
    return f"Bank {idx}: {name}" if name else f"Bank {idx}"


def describe_banks(radio) -> BankCatalog:
    """Return a safe, stable catalog for source capture or target selection."""
    from chirp import chirp_common as cc

    model = bank_model_for(radio)
    if model is None:
        return BankCatalog(
            False, False, "none", False, message="This radio has no banks."
        )
    mode = _mode(model)
    try:
        mappings = list(model.get_mappings())
    except Exception as exc:  # noqa: BLE001
        return BankCatalog(
            True,
            False,
            mode,
            False,
            message=f"Could not read this radio's banks: {exc}",
        )
    banks = tuple(
        BankDescriptor(
            position,
            bank.get_index(),
            _clean_name(bank.get_name()),
            _bank_label(bank),
        )
        for position, bank in enumerate(mappings)
    )
    return BankCatalog(
        available=True,
        mutable=mode != "fixed",
        mode=mode,
        indexed=isinstance(model, cc.MappingModelIndexInterface),
        banks=banks,
        message=(
            "This radio has fixed banks based on channel position."
            if mode == "fixed"
            else ""
        ),
    )


def _mapping_by_index(model) -> dict:
    return {bank.get_index(): bank for bank in model.get_mappings()}


def capture_bank_membership(
    radio,
    number: int,
    *,
    mutable_only: bool = False,
    model=None,
) -> BankMembershipSnapshot | None:
    """Capture exact memberships for migration metadata or Undo/Redo.

    ``None`` means no usable bank model. An empty snapshot means a mutable bank
    model exists but this channel belongs to no banks.
    """
    from chirp import chirp_common as cc

    model = model or bank_model_for(radio)
    if model is None:
        return None
    if mutable_only and isinstance(model, cc.StaticBankModel):
        return None
    memory = radio.get_memory(number)
    mappings = list(model.get_memory_mappings(memory))
    indexed = isinstance(model, cc.MappingModelIndexInterface)
    memberships = []
    for mapping in mappings:
        order = None
        if indexed:
            try:
                order = model.get_memory_index(memory, mapping)
            except Exception:  # noqa: BLE001 - membership remains restorable
                LOG.warning(
                    "Could not read bank order for channel %s in %s",
                    number,
                    _bank_label(mapping),
                )
        memberships.append(BankMembership(mapping.get_index(), order))
    return BankMembershipSnapshot(tuple(memberships))


def _replace_raw(model, memory, desired: BankMembershipSnapshot) -> None:
    """Replace memberships without rollback; caller owns error handling."""
    from chirp import chirp_common as cc

    by_index = _mapping_by_index(model)
    current = list(model.get_memory_mappings(memory))
    for mapping in current:
        model.remove_memory_from_mapping(memory, mapping)

    indexed = isinstance(model, cc.MappingModelIndexInterface)
    seen = set()
    for membership in desired.memberships:
        if membership.index in seen:
            continue
        seen.add(membership.index)
        mapping = by_index[membership.index]
        model.add_memory_to_mapping(memory, mapping)
        if indexed:
            order = membership.order
            if order is None:
                order = model.get_next_mapping_index(mapping)
            model.set_memory_index(memory, mapping, order)


def replace_bank_memberships(
    radio,
    number: int,
    desired_indexes,
    *,
    exact_orders: dict | None = None,
) -> tuple[bool, str, bool]:
    """Atomically replace one channel's mutable bank memberships.

    Returns ``(ok, message, changed)``. Unknown banks and fixed-bank models are
    rejected before mutation. Driver errors trigger a best-effort rollback to
    the exact prior memberships and ordering.
    """
    from chirp import chirp_common as cc

    model = bank_model_for(radio)
    if model is None:
        return False, "The destination radio has no banks.", False
    if isinstance(model, cc.StaticBankModel):
        return (
            False,
            "The destination radio has fixed banks that cannot be reassigned.",
            False,
        )
    try:
        memory = radio.get_memory(number)
        before = capture_bank_membership(radio, number)
        if before is None:
            return False, "Could not read destination bank memberships.", False
        by_index = _mapping_by_index(model)
    except Exception as exc:  # noqa: BLE001
        return False, f"Could not read destination banks: {exc}", False

    indexes = []
    seen = set()
    for index in desired_indexes:
        if index in seen:
            continue
        seen.add(index)
        indexes.append(index)
    missing = [index for index in indexes if index not in by_index]
    if missing:
        return (
            False,
            "Destination bank(s) are unavailable: "
            + ", ".join(str(index) for index in missing),
            False,
        )

    desired = BankMembershipSnapshot(
        tuple(
            BankMembership(
                index,
                (exact_orders or {}).get(index),
            )
            for index in indexes
        )
    )
    before_indexes = tuple(item.index for item in before.memberships)
    if (
        before_indexes == tuple(indexes)
        and not exact_orders
    ):
        return True, "Bank memberships were already correct.", False

    try:
        _replace_raw(model, memory, desired)
        after = capture_bank_membership(radio, number)
        actual_indexes = (
            {item.index for item in after.memberships}
            if after is not None
            else set()
        )
        if actual_indexes != set(indexes):
            raise RuntimeError(
                "driver stored "
                f"{sorted(str(index) for index in actual_indexes)} instead of "
                f"{sorted(str(index) for index in indexes)}"
            )
    except Exception as exc:  # noqa: BLE001 - rollback a driver-level failure
        LOG.warning(
            "Bank membership update failed for channel %s: %s", number, exc
        )
        try:
            _replace_raw(model, memory, before)
            restored = capture_bank_membership(radio, number)
            if restored != before:
                raise RuntimeError(
                    f"expected {before}, got {restored}"
                )
        except Exception:  # noqa: BLE001
            LOG.exception(
                "Could not roll back bank memberships for channel %s", number
            )
            return (
                False,
                f"Bank update failed and rollback also failed: {exc}",
                True,
            )
        return False, f"Bank update failed; original memberships restored: {exc}", False
    return True, "Bank memberships updated.", True


def restore_bank_membership(
    radio, number: int, snapshot: BankMembershipSnapshot
) -> None:
    """Restore an Undo/Redo snapshot, including destination ordering metadata."""
    exact = {
        item.index: item.order
        for item in snapshot.memberships
        if item.order is not None
    }
    ok, message, _changed = replace_bank_memberships(
        radio,
        number,
        [item.index for item in snapshot.memberships],
        exact_orders=exact,
    )
    if not ok:
        raise RuntimeError(message)


def with_member_counts(
    banks: tuple[BankDescriptor, ...],
    memberships: dict[int | str, tuple[int, ...]],
) -> tuple[BankDescriptor, ...]:
    """Return only used source banks, annotated with selected-channel counts."""
    counts = {bank.position: 0 for bank in banks}
    for positions in memberships.values():
        for position in set(positions):
            if position in counts:
                counts[position] += 1
    return tuple(
        replace(bank, member_count=counts[bank.position])
        for bank in banks
        if counts[bank.position]
    )


def _normalized_name(name: str) -> str:
    return re.sub(r"\s+", " ", _clean_name(name)).casefold()


def suggest_name_mapping(source_banks, target_banks) -> dict[int, object]:
    """Suggest unique exact-name matches; blank or ambiguous names stay unmapped."""
    targets: dict[str, list[BankDescriptor]] = {}
    for bank in target_banks:
        normalized = _normalized_name(bank.name)
        if normalized:
            targets.setdefault(normalized, []).append(bank)
    return {
        source.position: matches[0].index
        for source in source_banks
        if (normalized := _normalized_name(source.name))
        and len(matches := targets.get(normalized, [])) == 1
    }


def suggest_position_mapping(source_banks, target_banks) -> dict[int, object]:
    """Map source list positions to target list positions when the user asks."""
    targets = {bank.position: bank.index for bank in target_banks}
    return {
        source.position: targets[source.position]
        for source in source_banks
        if source.position in targets
    }


def get_bank_state(number: int) -> dict:
    """Describe one active channel's current bank options for the editor."""
    radio = _radio()
    if radio is None:
        return {"ok": False, "message": "No radio image is open."}
    model = _bank_model()
    if model is None:
        return {"ok": False, "message": "This radio has no banks."}
    try:
        mem = radio.get_memory(number)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "message": f"Could not read channel {number}: {exc}"}
    if getattr(mem, "empty", False):
        return {
            "ok": False,
            "message": f"Channel {number} is empty. Add a frequency before "
            "assigning it to a bank.",
        }

    mode = _mode(model)
    banks = model.get_mappings()
    try:
        member = {bank.get_index() for bank in model.get_memory_mappings(mem)}
    except Exception:  # noqa: BLE001
        member = set()
    # Some drivers permit multiple memberships despite inheriting BankModel.
    if len(member) > 1 and mode == "single":
        mode = "multi"
    return {
        "ok": True,
        "message": "",
        "mode": mode,
        "read_only": mode == "fixed",
        "banks": [(bank.get_index(), _bank_label(bank)) for bank in banks],
        "member_indexes": member,
        "number": number,
    }


@undo.records
def apply_bank_changes(number: int, desired_indexes) -> tuple[bool, str, list]:
    """Apply an active channel's bank diff as one Undo/Redo transaction."""
    radio = _radio()
    if radio is None:
        return False, "No radio image is open.", []
    model = _bank_model()
    if model is None:
        return False, "This radio has no banks.", []
    try:
        mem = radio.get_memory(number)
        current = [bank.get_index() for bank in model.get_memory_mappings(mem)]
    except Exception as exc:  # noqa: BLE001
        return False, f"Could not read channel {number}: {exc}", []
    if getattr(mem, "empty", False):
        return False, f"Channel {number} is empty.", []

    desired = list(dict.fromkeys(desired_indexes))
    if current == desired:
        return True, f"Channel {number}'s bank memberships did not change.", []

    from chirp_backend.radio import get_state, get_undo_manager

    manager = get_undo_manager()
    if manager is not None:
        manager.record(number)
    ok, message, changed = replace_bank_memberships(radio, number, desired)
    if not ok:
        return False, message, []
    if changed:
        get_state().is_modified = True

    try:
        now = [
            _clean_name(bank.get_name()) or f"Bank {bank.get_index()}"
            for bank in model.get_memory_mappings(radio.get_memory(number))
        ]
    except Exception:  # noqa: BLE001
        now = []
    membership = ", ".join(now) if now else "no banks"
    return True, f"Channel {number} is now in {membership}.", [number]
