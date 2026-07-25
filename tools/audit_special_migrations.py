#!/usr/bin/env python
r"""Sweep one representative memory across every pinned named special slot.

This is an opt-in compatibility audit, not a normal unit test. A destination
may reject the source as incompatible because a call channel, scan limit, VFO,
home, or band-state slot has model-specific constraints. A ``failed`` result is
unexpected and makes the command fail.

Run from the repository root::

    .venv\Scripts\python.exe tools\audit_special_migrations.py
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
from chirp.drivers import generic_csv  # noqa: E402
from chirp_backend import migration  # noqa: E402
from chirp_backend.radio import _ensure_chirp  # noqa: E402


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
        default=25,
        help="Generic_CSV.csv channel to migrate (default: 25)",
    )
    args = parser.parse_args()

    logging.disable(logging.WARNING)
    warnings.simplefilter("ignore")
    _ensure_chirp()

    source_path = args.images / "Generic_CSV.csv"
    images = sorted(args.images.glob("*.img"))
    if not source_path.is_file() or not images:
        print(f"No CHIRP migration fixtures found in {args.images}")
        return 2
    source = generic_csv.CSVRadio(str(source_path))
    batch = migration.batch_from_identifiers(source, [args.source_channel])
    if not batch.entries:
        print(f"Generic_CSV.csv channel {args.source_channel} is unavailable")
        return 2

    counts: Counter[str] = Counter()
    failures: list[str] = []
    target_count = 0
    for image_path in images:
        try:
            parent = directory.get_radio_by_image(str(image_path.resolve()))
            features = parent.get_features()
            targets = (
                parent.get_sub_devices() if features.has_sub_devices else [parent]
            )
            for index, target in enumerate(targets):
                names = list(target.get_features().valid_special_chans or [])
                if names:
                    target_count += 1
                for name in names:
                    report = migration.apply_batch_to_special(
                        target, batch, name, overwrite=True
                    )
                    status = (
                        report.items[-1].status if report.items else "no result"
                    )
                    counts[status] += 1
                    if report.failed or not report.items:
                        failures.append(
                            f"{image_path.name} subdevice {index} special {name}:\n"
                            f"{report.details_text()}"
                        )
        except Exception as exc:  # noqa: BLE001 - audit every fixture
            counts["setup failed"] += 1
            failures.append(
                f"{image_path.name}: {type(exc).__name__}: {exc}"
            )

    total = sum(counts.values())
    print(
        f"Audited {total} named special memories across "
        f"{target_count} radio targets from {len(images)} image files."
    )
    for status, count in sorted(counts.items()):
        print(f"  {status}: {count}")
    if failures:
        print(f"\nUnexpected failures: {len(failures)}")
        for failure in failures:
            print(f"\n{failure}")
        return 1
    print("No unexpected special-memory migration failures.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
