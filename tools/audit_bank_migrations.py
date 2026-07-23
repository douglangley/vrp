#!/usr/bin/env python
r"""Exercise bank replacement and exact rollback across pinned CHIRP images.

This is an opt-in driver compatibility audit. Mutable bank models are changed
in memory only, verified, and restored to their exact membership/order snapshot.
Fixed banks must reject reassignment without mutation. Expected driver capacity
or membership constraints are counted as incompatible; exceptions, rollback
failures, or verification mismatches fail the command.

Run from the repository root::

    .venv\Scripts\python.exe tools\audit_bank_migrations.py
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
from chirp import directory  # noqa: E402
from chirp_backend import bank_ops  # noqa: E402
from chirp_backend.radio import _ensure_chirp  # noqa: E402


def _candidate(radio):
    low, high = radio.get_features().memory_bounds
    for number in range(low, high + 1):
        try:
            memory = radio.get_memory(number)
            if not memory.empty:
                snapshot = bank_ops.capture_bank_membership(radio, number)
                if snapshot is not None:
                    return number, snapshot
        except Exception:  # noqa: BLE001 - try another programmed row
            continue
    return None, None


def _indexes(snapshot):
    return tuple(item.index for item in snapshot.memberships)


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

    counts: Counter[str] = Counter()
    failures: list[str] = []
    models = 0
    target_images = set()
    for image_path in images:
        try:
            parent = directory.get_radio_by_image(str(image_path.resolve()))
            features = parent.get_features()
            targets = (
                parent.get_sub_devices() if features.has_sub_devices else [parent]
            )
            for section, radio in enumerate(targets):
                catalog = bank_ops.describe_banks(radio)
                if not catalog.available:
                    continue
                models += 1
                target_images.add(image_path.name)
                number, before = _candidate(radio)
                if number is None or before is None:
                    counts["no programmed candidate"] += 1
                    continue

                if not catalog.mutable:
                    ok, message, changed = bank_ops.replace_bank_memberships(
                        radio, number, [catalog.banks[0].index]
                    )
                    if ok or changed or "fixed" not in message:
                        failures.append(
                            f"{image_path.name} section {section}: fixed-bank "
                            f"contract was not preserved ({ok}, {changed}, {message})"
                        )
                    else:
                        counts["fixed"] += 1
                    continue

                current = set(_indexes(before))
                target_bank = next(
                    (
                        bank
                        for bank in catalog.banks
                        if bank.index not in current
                    ),
                    catalog.banks[0] if catalog.banks else None,
                )
                if target_bank is None:
                    counts["no banks"] += 1
                    continue

                ok, message, changed = bank_ops.replace_bank_memberships(
                    radio, number, [target_bank.index]
                )
                if not ok:
                    if changed:
                        failures.append(
                            f"{image_path.name} section {section} channel "
                            f"{number}: failed with incomplete rollback: {message}"
                        )
                    else:
                        counts["incompatible"] += 1
                    continue
                after = bank_ops.capture_bank_membership(radio, number)
                if after is None or _indexes(after) != (target_bank.index,):
                    failures.append(
                        f"{image_path.name} section {section} channel {number}: "
                        f"write verification mismatch, got "
                        f"{_indexes(after) if after else None}"
                    )
                    continue

                bank_ops.restore_bank_membership(radio, number, before)
                restored = bank_ops.capture_bank_membership(radio, number)
                if restored != before:
                    failures.append(
                        f"{image_path.name} section {section} channel {number}: "
                        f"rollback verification mismatch, expected {before}, "
                        f"got {restored}"
                    )
                    continue
                counts["mutable verified"] += 1
        except Exception as exc:  # noqa: BLE001 - audit every fixture
            failures.append(
                f"{image_path.name}: {type(exc).__name__}: {exc}"
            )

    print(
        f"Audited {models} bank models across {len(target_images)} image files "
        f"from {len(images)} pinned images."
    )
    for status, count in sorted(counts.items()):
        print(f"  {status}: {count}")
    if failures:
        print(f"\nUnexpected failures: {len(failures)}")
        for failure in failures:
            print(f"\n{failure}")
        return 1
    print("No unexpected bank migration failures.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
