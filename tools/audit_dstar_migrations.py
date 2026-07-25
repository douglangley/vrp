#!/usr/bin/env python
r"""Audit D-STAR compatibility and call-list atomicity across pinned fixtures.

The audit has two passes:

* migrate one real DV memory into every pinned radio target, verifying that
  analog-only targets never accept/coerce it; and
* migrate every populated pinned DV memory into every target whose CHIRP
  driver requires master URCALL/RPTCALL lists, restoring the destination
  memory through its driver and verifying exact call lists after every case.

Normal band, capacity, and driver compatibility rejections are expected.
Unexpected failures, analog coercion, or restoration mismatches fail the
command.

Run from the repository root::

    .venv\Scripts\python.exe tools\audit_dstar_migrations.py
"""

from __future__ import annotations

import argparse
import logging
import sys
import warnings
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import vrp  # noqa: E402,F401 - installs the vendored CHIRP import path
from chirp import chirp_common, directory  # noqa: E402
from chirp_backend import dstar_ops, migration  # noqa: E402
from chirp_backend.radio import _ensure_chirp  # noqa: E402


def _targets(parent):
    features = parent.get_features()
    return parent.get_sub_devices() if features.has_sub_devices else [parent]


def _first_destination(radio) -> int:
    low, high = radio.get_features().memory_bounds
    for number in range(low, high + 1):
        try:
            if radio.get_memory(number).empty:
                return number
        except Exception:  # noqa: BLE001 - try the next ordinary slot
            continue
    return low


def _restore_memory(radio, memory) -> None:
    if memory.empty and not getattr(memory, "extd_number", ""):
        radio.erase_memory(memory.number)
    else:
        radio.set_memory(memory.dupe())


def _dv_batches(images: list[Path]):
    batches = []
    source_targets = 0
    for image_path in images:
        try:
            parent = directory.get_radio_by_image(str(image_path.resolve()))
            for section, radio in enumerate(_targets(parent)):
                features = radio.get_features()
                if "DV" not in features.valid_modes:
                    continue
                source_targets += 1
                low, high = features.memory_bounds
                for number in range(low, high + 1):
                    try:
                        memory = radio.get_memory(number)
                    except Exception:  # noqa: BLE001 - unreadable source omitted
                        continue
                    if (
                        getattr(memory, "empty", True)
                        or not isinstance(memory, chirp_common.DVMemory)
                    ):
                        continue
                    batch = migration.batch_from_memories(
                        [memory],
                        [number],
                        features,
                        migration.radio_id(radio),
                        (
                            f"{migration.radio_label(radio)} "
                            f"({image_path.name}, section {section})"
                        ),
                    )
                    batches.append(batch)
        except Exception:  # noqa: BLE001 - target sweep reports setup issues
            continue
    return batches, source_targets


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--images",
        type=Path,
        default=ROOT / "chirp" / "tests" / "images",
        help="directory containing pinned CHIRP fixtures",
    )
    args = parser.parse_args()

    logging.disable(logging.WARNING)
    warnings.simplefilter("ignore")
    _ensure_chirp()

    images = sorted(args.images.glob("*.img"))
    if not images:
        print(f"No CHIRP migration fixtures found in {args.images}")
        return 2

    source = directory.get_radio_by_image(
        str((args.images / "Icom_IC-2200H.img").resolve())
    )
    representative = migration.batch_from_radio(source, numbers=[17])
    if not representative.entries:
        print("Pinned IC-2200H DV source channel 17 is unavailable")
        return 2

    target_counts: Counter[str] = Counter()
    failures: list[str] = []
    target_total = 0
    required_targets = []
    for image_path in images:
        try:
            parent = directory.get_radio_by_image(str(image_path.resolve()))
            radios = _targets(parent)
            if not radios:
                failures.append(f"{image_path.name}: exposed no subdevices")
                continue
            for section, target in enumerate(radios):
                target_total += 1
                features = target.get_features()
                destination = features.memory_bounds[0]
                report = migration.apply_batch(
                    target, representative, destination
                )
                status = report.items[-1].status if report.items else "no result"
                target_counts[status] += 1
                if report.failed or not report.items:
                    failures.append(
                        f"{image_path.name} section {section}:\n"
                        f"{report.details_text()}"
                    )
                if "DV" not in features.valid_modes and report.imported:
                    failures.append(
                        f"{image_path.name} section {section}: analog-only "
                        "target accepted a DV memory"
                    )
                if dstar_ops.requires_call_lists(target):
                    required_targets.append((image_path, section))
        except Exception as exc:  # noqa: BLE001 - audit every fixture
            failures.append(
                f"{image_path.name}: {type(exc).__name__}: {exc}"
            )

    batches, dv_source_targets = _dv_batches(images)
    call_counts: Counter[str] = Counter()
    call_cases = 0
    for image_path, section in required_targets:
        try:
            parent = directory.get_radio_by_image(str(image_path.resolve()))
            target = _targets(parent)[section]
            destination = _first_destination(target)
            for batch in batches:
                call_cases += 1
                before_memory = target.get_memory(destination).dupe()
                before_raw = target.get_raw_memory(destination)
                before_calls = dstar_ops.capture_call_lists(target)
                report = migration.apply_batch(
                    target, batch, destination, overwrite=True
                )
                status = report.items[-1].status if report.items else "no result"
                call_counts[status] += 1
                if report.failed or not report.items:
                    failures.append(
                        f"{image_path.name} section {section}, "
                        f"{batch.source_label}:\n{report.details_text()}"
                    )
                if not report.imported:
                    if target.get_raw_memory(destination) != before_raw:
                        failures.append(
                            f"{image_path.name} section {section}: rejected "
                            f"migration changed destination memory {destination} "
                            f"for {batch.source_label}"
                        )
                else:
                    _restore_memory(target, before_memory)
                dstar_ops.restore_call_lists(target, before_calls)
                if dstar_ops.capture_call_lists(target) != before_calls:
                    failures.append(
                        f"{image_path.name} section {section}: call lists did "
                        f"not restore after {batch.source_label}"
                    )
        except Exception as exc:  # noqa: BLE001 - continue remaining targets
            failures.append(
                f"{image_path.name} section {section}: "
                f"{type(exc).__name__}: {exc}"
            )

    print(
        f"Audited one DV memory across {target_total} radio targets from "
        f"{len(images)} pinned images."
    )
    for status, count in sorted(target_counts.items()):
        print(f"  {status}: {count}")
    print(
        f"Audited {len(batches)} populated DV memories from "
        f"{dv_source_targets} DV-capable targets across "
        f"{len(required_targets)} call-list-required targets "
        f"({call_cases} cases)."
    )
    for status, count in sorted(call_counts.items()):
        print(f"  {status}: {count}")
    if failures:
        print(f"\nUnexpected failures: {len(failures)}")
        for failure in failures:
            print(f"\n{failure}")
        return 1
    print("No unexpected D-STAR migration failures.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
