"""CHIRP stock configs ("frequency lists") — discovery + description.

CHIRP ships ~20 curated CSV frequency lists (NOAA weather, US/CA FRS+GMRS, MURS,
Marine VHF, aviation, railroad, EU PMR/LPD, …) in the ``chirp.stock_configs``
package directory. VRP imports one of them into the loaded radio via the normal
import path (``radio.open_image_as_source`` -> ``memory_ops.import_memories``),
so this module only has to *locate* and *describe* the files — it does not open
or import them itself.

Framework-agnostic (no wx), so it is unit-testable headless.

Path resolution (see the plan
``docs/superpowers/plans/2026-07-10-stock-configs-frequency-lists.md``):
  - From source: the files live in the cloned, pinned CHIRP tree at
    ``<chirp package>/stock_configs`` (the run scripts always clone + check out
    CHIRP at ``CHIRP_COMMIT``, so they are present and current).
  - Frozen (PyInstaller): ``build.py`` bundles them with a targeted ``--add-data``
    to ``chirp/stock_configs`` under the extraction root, so we resolve them at
    ``<sys._MEIPASS>/chirp/stock_configs``. We deliberately use an explicit
    filesystem path rather than ``importlib.resources`` because the directory has
    no ``__init__.py`` and is bundled as data, not as a collected package.
"""

from __future__ import annotations

import os
import sys
from typing import List, Tuple


def stock_configs_dir() -> str:
    """Absolute path to the directory holding the stock-config CSV files.

    Resolves the frozen (PyInstaller) location first, then the CHIRP source
    tree. The returned path may not exist (a broken clone/build); callers use
    :func:`list_configs`, which tolerates a missing directory.
    """
    meipass = getattr(sys, "_MEIPASS", None)
    if getattr(sys, "frozen", False) and meipass:
        return os.path.join(meipass, "chirp", "stock_configs")
    import chirp

    return os.path.join(os.path.dirname(chirp.__file__), "stock_configs")


def _is_config_file(name: str) -> bool:
    """A visible ``.csv`` list — skip dotfiles and editor backups, as CHIRP does."""
    if name.startswith(".") or name.endswith("~"):
        return False
    return name.lower().endswith(".csv")


def list_configs() -> List[Tuple[str, str]]:
    """Return ``[(display_name, abs_path), …]`` for every stock config, sorted by
    display name. ``display_name`` is the filename without the ``.csv`` extension
    (e.g. ``"US NOAA Weather Alert"``). Returns ``[]`` if the directory is
    missing."""
    directory = stock_configs_dir()
    try:
        names = os.listdir(directory)
    except OSError:
        return []
    configs = [
        (os.path.splitext(name)[0], os.path.join(directory, name))
        for name in names
        if _is_config_file(name)
    ]
    configs.sort(key=lambda pair: pair[0].lower())
    return configs


def describe_config(path: str, *, max_rows: int = 12) -> str:
    """A short, screen-reader-friendly summary of a stock config for the Details
    view: the channel count plus the first ``max_rows`` ``frequency  name`` rows.
    Opens the CSV through the same source path the import uses, so what's
    described is exactly what would import."""
    from chirp_backend import radio as radio_backend
    from chirp_backend.col_defs import format_freq_mhz

    src, message = radio_backend.open_image_as_source(path)
    if src is None:
        return message

    try:
        lo, hi = src.get_features().memory_bounds
    except Exception:  # noqa: BLE001
        return "Could not read this frequency list."

    rows: List[str] = []
    total = 0
    for n in range(lo, hi + 1):
        try:
            mem = src.get_memory(n)
        except Exception:  # noqa: BLE001
            continue
        if getattr(mem, "empty", True):
            continue
        total += 1
        if len(rows) < max_rows:
            name = (getattr(mem, "name", "") or "").strip()
            freq = format_freq_mhz(mem.freq) if getattr(mem, "freq", 0) else ""
            label = f"{freq} MHz" if freq else ""
            rows.append(f"  {mem.number}: {label}  {name}".rstrip())

    if total == 0:
        return "This frequency list has no channels."

    lines = [f"{total} channel(s) in this frequency list.", ""]
    lines.extend(rows)
    if total > len(rows):
        lines.append(f"  … and {total - len(rows)} more.")
    return "\n".join(lines)
