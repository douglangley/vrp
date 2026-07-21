"""Generic channel migration between CHIRP radio models.

CHIRP deliberately represents an ordinary channel with the model-neutral
``Memory``/``DVMemory`` classes.  Cross-model migration is therefore a
conversion pipeline, not a collection of source/destination model pairs:

1. snapshot populated source memories and their source ``RadioFeatures``;
2. remove driver-private ``Memory.extra`` data when model identities differ;
3. run CHIRP's ``import_logic.import_mem`` for destination-specific
   frequency, name, power, tone, mode, duplex, D-STAR and validation handling;
4. write each compatible result and retain an itemised report for everything
   that could not be migrated.

This module has no wx dependency so file import, query import, and clipboard
paste can all use exactly the same behavior.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from chirp import chirp_common, directory, errors, import_logic

LOG = logging.getLogger(__name__)


def radio_id(radio) -> str:
    """Return CHIRP's stable driver identity, with a test-double fallback."""
    cls = radio.__class__
    try:
        return directory.radio_class_id(cls)
    except (AttributeError, TypeError):
        return f"{cls.__module__}.{cls.__qualname__}"


def radio_label(radio) -> str:
    """Return a concise human label for a radio/source object."""
    vendor = getattr(radio, "VENDOR", "")
    model = getattr(radio, "MODEL", "")
    variant = getattr(radio, "VARIANT", "")
    label = " ".join(str(x) for x in (vendor, model, variant) if x)
    return label or radio.__class__.__name__


@dataclass(frozen=True)
class MigrationEntry:
    """One populated source channel and its immutable-at-batch-time snapshot."""

    source_number: int
    memory: object


@dataclass(frozen=True)
class MigrationReadError:
    source_number: int
    message: str


@dataclass
class MigrationBatch:
    """Portable source payload used by every migration entry point."""

    source_label: str
    source_radio_id: str
    source_features: object
    entries: list[MigrationEntry] = field(default_factory=list)
    source_document_id: str | None = None
    read_errors: list[MigrationReadError] = field(default_factory=list)


@dataclass(frozen=True)
class MigrationItemResult:
    source_number: int
    destination_number: int | None
    status: str
    message: str = ""
    warnings: tuple[str, ...] = ()
    overwritten: bool = False


@dataclass
class MigrationReport:
    """Machine-readable counts plus accessible plain-text migration details."""

    source_label: str
    target_label: str
    items: list[MigrationItemResult] = field(default_factory=list)

    def _count(self, status: str) -> int:
        return sum(item.status == status for item in self.items)

    @property
    def imported(self) -> int:
        return self._count("imported")

    @property
    def incompatible(self) -> int:
        return self._count("incompatible")

    @property
    def failed(self) -> int:
        return self._count("failed")

    @property
    def occupied(self) -> int:
        return self._count("occupied")

    @property
    def out_of_space(self) -> int:
        return self._count("out_of_space")

    @property
    def overwritten(self) -> int:
        return sum(item.overwritten for item in self.items)

    @property
    def warning_count(self) -> int:
        return sum(len(item.warnings) for item in self.items)

    @property
    def affected(self) -> list[int]:
        return [
            item.destination_number
            for item in self.items
            if item.status == "imported" and item.destination_number is not None
        ]

    @property
    def ok(self) -> bool:
        return self.imported > 0

    @property
    def has_issues(self) -> bool:
        return bool(
            self.incompatible + self.failed + self.occupied + self.out_of_space
        )

    def summary(self) -> str:
        parts = [f"Imported {self.imported} channel(s)"]
        if self.overwritten:
            parts.append(f"{self.overwritten} overwritten")
        if self.occupied:
            parts.append(f"{self.occupied} occupied and skipped")
        if self.incompatible:
            parts.append(f"{self.incompatible} incompatible")
        if self.failed:
            parts.append(f"{self.failed} failed")
        if self.out_of_space:
            parts.append(f"{self.out_of_space} did not fit")
        if self.warning_count:
            parts.append(f"{self.warning_count} warning(s)")
        return ", ".join(parts) + "."

    def details_text(self) -> str:
        lines = [
            f"Source: {self.source_label}",
            f"Destination: {self.target_label}",
            self.summary(),
            "",
        ]
        for item in self.items:
            route = f"Source {item.source_number}"
            if item.destination_number is not None:
                route += f" -> destination {item.destination_number}"
            detail = item.message or item.status.replace("_", " ")
            lines.append(f"{route}: {item.status.replace('_', ' ')} — {detail}")
            for warning in item.warnings:
                lines.append(f"  Warning: {warning}")
        return "\n".join(lines).rstrip()


def batch_from_memories(
    memories,
    source_numbers,
    source_features,
    source_radio_id: str,
    source_label: str,
    source_document_id: str | None = None,
) -> MigrationBatch:
    """Build a migration batch from clipboard-style memory snapshots."""
    entries = [
        MigrationEntry(number, memory.dupe())
        for number, memory in zip(source_numbers, memories)
        if not getattr(memory, "empty", False)
    ]
    return MigrationBatch(
        source_label=source_label,
        source_radio_id=source_radio_id,
        source_features=source_features,
        entries=entries,
        source_document_id=source_document_id,
    )


def batch_from_radio(
    source_radio,
    numbers=None,
    *,
    source_document_id: str | None = None,
    include_empty: bool = False,
) -> MigrationBatch:
    """Snapshot selected (or all) source memories in ascending channel order."""
    features = source_radio.get_features()
    low, high = features.memory_bounds
    if numbers is None:
        source_numbers = range(low, high + 1)
    else:
        source_numbers = sorted({n for n in numbers if low <= n <= high})

    batch = MigrationBatch(
        source_label=radio_label(source_radio),
        source_radio_id=radio_id(source_radio),
        source_features=features,
        source_document_id=source_document_id,
    )
    for number in source_numbers:
        try:
            memory = source_radio.get_memory(number)
        except Exception as exc:  # noqa: BLE001 - retain per-channel failure
            batch.read_errors.append(MigrationReadError(number, str(exc)))
            continue
        if memory is None:
            batch.read_errors.append(
                MigrationReadError(number, "The source channel could not be read")
            )
            continue
        if getattr(memory, "empty", False) and not include_empty:
            continue
        batch.entries.append(MigrationEntry(number, memory.dupe()))
    return batch


def apply_batch(
    target_radio,
    batch: MigrationBatch,
    destination: int,
    *,
    overwrite: bool = True,
) -> MigrationReport:
    """Convert and write a batch to consecutive target slots.

    Every populated source entry consumes one destination position, including
    incompatible and skipped entries. This preserves the source ordering while
    still allowing later compatible rows to migrate as a partial success.
    """
    report = MigrationReport(batch.source_label, radio_label(target_radio))
    for read_error in batch.read_errors:
        report.items.append(
            MigrationItemResult(
                read_error.source_number,
                None,
                "failed",
                f"Could not read source channel: {read_error.message}",
            )
        )

    low, high = target_radio.get_features().memory_bounds
    target_identity = radio_id(target_radio)
    dest = destination
    for entry in batch.entries:
        if dest < low or dest > high:
            report.items.append(
                MigrationItemResult(
                    entry.source_number,
                    dest,
                    "out_of_space",
                    f"Destination is outside channels {low}-{high}",
                )
            )
            dest += 1
            continue

        try:
            existing = target_radio.get_memory(dest)
        except Exception as exc:  # noqa: BLE001
            report.items.append(
                MigrationItemResult(
                    entry.source_number,
                    dest,
                    "failed",
                    f"Could not read destination channel: {exc}",
                )
            )
            dest += 1
            continue

        was_occupied = existing is not None and not getattr(existing, "empty", True)
        if was_occupied and not overwrite:
            report.items.append(
                MigrationItemResult(
                    entry.source_number,
                    dest,
                    "occupied",
                    "Destination channel is not empty",
                )
            )
            dest += 1
            continue

        source_memory = entry.memory.dupe()
        # Driver-private settings cannot be interpreted by another driver.
        # This is the same boundary CHIRP's editor applies during cross-radio
        # copy/paste, and prevents settings such as ``sqmode`` leaking between
        # related but structurally different models.
        if batch.source_radio_id != target_identity:
            source_memory.extra = []

        try:
            converted = import_logic.import_mem(
                target_radio,
                batch.source_features,
                source_memory,
                overrides={"number": dest, "extd_number": ""},
            )
            warnings: tuple[str, ...] = ()
            validate = getattr(target_radio, "validate_memory", None)
            if validate is not None:
                messages = validate(chirp_common.FrozenMemory(converted))
                validation_warnings, validation_errors = (
                    chirp_common.split_validation_msgs(messages)
                )
                if validation_errors:
                    raise import_logic.DestNotCompatible(
                        ", ".join(str(msg) for msg in validation_errors)
                    )
                warnings = tuple(str(msg) for msg in validation_warnings)
            target_radio.set_memory(converted)
        except (
            import_logic.DestNotCompatible,
            chirp_common.ImmutableValueError,
            errors.RadioError,
            errors.InvalidDataError,
            errors.InvalidValueError,
            ValueError,
        ) as exc:
            LOG.warning(
                "migration source %s -> destination %s incompatible: %s",
                entry.source_number,
                dest,
                exc,
            )
            report.items.append(
                MigrationItemResult(
                    entry.source_number, dest, "incompatible", str(exc)
                )
            )
        except Exception as exc:  # noqa: BLE001 - isolate driver failures by row
            LOG.exception(
                "migration source %s -> destination %s failed",
                entry.source_number,
                dest,
            )
            report.items.append(
                MigrationItemResult(entry.source_number, dest, "failed", str(exc))
            )
        else:
            report.items.append(
                MigrationItemResult(
                    entry.source_number,
                    dest,
                    "imported",
                    "Imported",
                    warnings,
                    overwritten=was_occupied,
                )
            )
        dest += 1

    return report
