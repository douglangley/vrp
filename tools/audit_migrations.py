#!/usr/bin/env python
r"""Audit VRP's generic migration route with a representative source corpus.

The default Phase 6 corpus covers VHF/Tone, UHF/DTCS, HF/AM, airband AM,
cross-band split, and a real pinned D-STAR memory. Every case is applied to a
fresh instance of every radio target exposed by CHIRP's pinned fixtures.

An ``incompatible`` result is expected when a destination cannot represent a
case. A ``failed`` result, an unreadable successful write, a changed destination
after rejection, or a rollback warning fails the command. Use
``--source-channel`` (repeatable) to run one or more Generic_CSV.csv channels
instead of the default corpus when debugging a particular conversion.

Run from the repository root::

    .venv\Scripts\python.exe tools\audit_migrations.py
"""

from __future__ import annotations

import argparse
import logging
import sys
import warnings
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import vrp  # noqa: E402,F401 - installs the vendored CHIRP import path
from chirp import chirp_common, directory  # noqa: E402
from chirp.drivers import generic_csv  # noqa: E402
from chirp_backend import migration  # noqa: E402
from chirp_backend.radio import _ensure_chirp  # noqa: E402


@dataclass(frozen=True)
class AuditCase:
    """One source memory and the behavior its label is meant to exercise."""

    key: str
    description: str
    batch: migration.MigrationBatch


def _fixture_batch(
    images: Path,
    filename: str,
    number: int,
    *,
    label: str,
) -> migration.MigrationBatch:
    path = images / filename
    if not path.is_file():
        raise FileNotFoundError(f"Pinned source fixture is missing: {path}")
    source = directory.get_radio_by_image(str(path.resolve()))
    batch = migration.batch_from_radio(source, numbers=[number])
    if not batch.entries:
        raise ValueError(
            f"Pinned source {filename} channel {number} is unavailable"
        )
    batch.source_label = label
    return batch


def build_corpus(
    images: Path,
    source_channels: list[int] | None = None,
) -> list[AuditCase]:
    """Build the default Phase 6 corpus or targeted Generic CSV cases."""
    _ensure_chirp()
    csv_path = images / "Generic_CSV.csv"
    if not csv_path.is_file():
        raise FileNotFoundError(f"Pinned source fixture is missing: {csv_path}")
    csv_source = generic_csv.CSVRadio(str(csv_path))

    if source_channels:
        cases = []
        for number in source_channels:
            batch = migration.batch_from_radio(csv_source, numbers=[number])
            if not batch.entries:
                raise ValueError(
                    f"Generic_CSV.csv channel {number} is empty or unreadable"
                )
            cases.append(
                AuditCase(
                    f"generic_csv_{number}",
                    f"Generic CSV channel {number}",
                    batch,
                )
            )
        return cases

    vhf = migration.batch_from_radio(csv_source, numbers=[26])
    uhf = migration.batch_from_radio(csv_source, numbers=[25])
    airband = migration.batch_from_radio(csv_source, numbers=[88])
    if not vhf.entries or not uhf.entries or not airband.entries:
        raise ValueError("Pinned Generic_CSV.csv corpus channels are unavailable")

    hf = _fixture_batch(
        images,
        "Icom_IC-M710.img",
        0,
        label="Pinned Icom IC-M710 HF/AM",
    )
    if (
        hf.entries[0].memory.freq != 2_182_000
        or hf.entries[0].memory.mode != "AM"
    ):
        raise ValueError("Pinned IC-M710 channel 0 is not the expected HF/AM memory")

    split = _fixture_batch(
        images,
        "Anysecu_WP-9900.img",
        1,
        label="Pinned Anysecu WP-9900 cross-band split",
    )
    if split.entries[0].memory.duplex != "split":
        raise ValueError("Pinned WP-9900 channel 1 is not a split memory")

    dv = _fixture_batch(
        images,
        "Icom_IC-2200H.img",
        17,
        label="Pinned Icom IC-2200H D-STAR",
    )
    if not dv.entries or not isinstance(
        dv.entries[0].memory, chirp_common.DVMemory
    ):
        raise ValueError("Pinned IC-2200H channel 17 is not a readable DV memory")

    return [
        AuditCase("vhf_tone", "VHF repeater with Tone", vhf),
        AuditCase("uhf_dtcs", "UHF repeater with DTCS", uhf),
        AuditCase("hf_am", "HF marine AM", hf),
        AuditCase("airband_am", "VHF airband AM", airband),
        AuditCase(
            "cross_band_split",
            "VHF receive with UHF split transmit",
            split,
        ),
        AuditCase("dstar", "Real Icom D-STAR memory", dv),
    ]


def _targets(parent):
    features = parent.get_features()
    return parent.get_sub_devices() if features.has_sub_devices else [parent]


def _memory_state(memory) -> tuple:
    """Return driver-neutral fields that must survive a rejected migration."""
    if getattr(memory, "empty", False):
        return (True,)

    state = [
        False,
        memory.freq,
        memory.name,
        memory.mode,
        memory.duplex,
        memory.tmode,
        memory.skip,
    ]
    if memory.duplex:
        state.append(memory.offset)
    if memory.tmode in ("Tone", "TSQL", "Cross"):
        state.extend((memory.rtone, memory.ctone))
    if memory.tmode in ("DTCS", "Cross"):
        state.extend(
            (
                memory.dtcs,
                memory.rx_dtcs,
                memory.dtcs_polarity,
                memory.cross_mode,
            )
        )
    if isinstance(memory, chirp_common.DVMemory):
        state.extend(
            (
                memory.dv_urcall,
                memory.dv_rpt1call,
                memory.dv_rpt2call,
                memory.dv_code,
            )
        )
    return tuple(state)


def _audit_case(
    case: AuditCase,
    images: list[Path],
) -> tuple[Counter[str], list[str], int]:
    counts: Counter[str] = Counter()
    failures: list[str] = []
    target_total = 0

    for image_path in images:
        try:
            parent = directory.get_radio_by_image(str(image_path.resolve()))
            targets = _targets(parent)
            if not targets:
                counts["no subdevices"] += 1
                failures.append(f"{case.key}: {image_path.name}: exposed no subdevices")
                continue

            for index, target in enumerate(targets):
                target_total += 1
                features = target.get_features()
                low, _high = features.memory_bounds
                before = target.get_memory(low).dupe()
                report = migration.apply_batch(target, case.batch, low)
                item = report.items[-1] if report.items else None
                status = item.status if item is not None else "no result"
                counts[status] += 1
                context = f"{case.key}: {image_path.name} subdevice {index}"

                if item is None or report.failed:
                    failures.append(f"{context}:\n{report.details_text()}")
                    continue
                if status not in ("imported", "incompatible"):
                    failures.append(
                        f"{context}: unexpected status {status!r}\n"
                        f"{report.details_text()}"
                    )
                    continue
                if any(
                    "rollback failed" in warning.lower()
                    for warning in item.warnings
                ):
                    failures.append(
                        f"{context}: rollback warning\n{report.details_text()}"
                    )

                after = target.get_memory(low)
                if status == "imported" and getattr(after, "empty", True):
                    failures.append(
                        f"{context}: import reported success but destination is empty"
                    )
                if status == "incompatible" and _memory_state(after) != _memory_state(
                    before
                ):
                    failures.append(
                        f"{context}: rejected migration changed destination {low}"
                    )
                if (
                    case.key == "dstar"
                    and "DV" not in features.valid_modes
                    and status == "imported"
                ):
                    failures.append(
                        f"{context}: target without DV support accepted D-STAR"
                    )
        except Exception as exc:  # noqa: BLE001 - audit every fixture
            counts["setup failed"] += 1
            failures.append(
                f"{case.key}: {image_path.name}: "
                f"{type(exc).__name__}: {exc}"
            )

    return counts, failures, target_total


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--images",
        type=Path,
        default=ROOT / "chirp" / "tests" / "images",
        help="directory containing pinned CHIRP fixtures",
    )
    parser.add_argument(
        "--source-channel",
        type=int,
        action="append",
        help=(
            "audit this Generic_CSV.csv channel instead of the default corpus; "
            "repeat for multiple channels"
        ),
    )
    args = parser.parse_args()

    logging.disable(logging.WARNING)
    warnings.simplefilter("ignore")
    _ensure_chirp()

    images = sorted(args.images.glob("*.img"))
    if not images:
        print(f"No CHIRP migration fixtures found in {args.images}")
        return 2
    try:
        cases = build_corpus(args.images, args.source_channel)
    except (FileNotFoundError, ValueError) as exc:
        print(exc)
        return 2

    all_counts: Counter[str] = Counter()
    all_failures: list[str] = []
    expected_targets = None
    for case in cases:
        counts, failures, target_total = _audit_case(case, images)
        all_counts.update(counts)
        all_failures.extend(failures)
        if expected_targets is None:
            expected_targets = target_total
        elif target_total != expected_targets:
            all_failures.append(
                f"{case.key}: target count changed from "
                f"{expected_targets} to {target_total}"
            )
        print(f"{case.key} — {case.description}:")
        for status, count in sorted(counts.items()):
            print(f"  {status}: {count}")

    total = sum(all_counts.values())
    print(
        f"Audited {len(cases)} source case(s) across "
        f"{expected_targets or 0} radio targets from {len(images)} image files "
        f"({total} migrations)."
    )
    print("Totals:")
    for status, count in sorted(all_counts.items()):
        print(f"  {status}: {count}")
    if all_failures:
        print(f"\nUnexpected failures: {len(all_failures)}")
        for failure in all_failures:
            print(f"\n{failure}")
        return 1
    print("No unexpected migration failures.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
