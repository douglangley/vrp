"""Make the editable-installed ``chirp`` package win over the ``./chirp`` clone.

CHIRP is vendored as a sibling clone at ``./chirp`` and installed editable.
Its repository root directory is literally named ``chirp`` and contains no
``__init__.py``. When VRP runs from the project root, that directory sits on
``sys.path`` ahead of everything else, so Python's default ``PathFinder``
resolves ``import chirp`` to the *repository root* as an empty namespace
package — shadowing the real ``chirp/chirp`` package (where ``CHIRP_VERSION``
and the drivers live).

The setuptools editable install registers a meta-path finder that knows the
correct location, but appends it *after* ``PathFinder`` in ``sys.meta_path``,
so it never gets consulted. Moving ``PathFinder`` to the end lets the editable
finder resolve ``chirp`` first while every other import still falls through to
``PathFinder`` unchanged.

Importing this module applies the fix exactly once. It must run before the
first ``import chirp`` anywhere in the process, so it is imported as the very
first line of ``vrp/__init__`` and of ``main.py``. It is a harmless no-op in a
frozen (PyInstaller) build, where there is no ``./chirp`` directory to shadow.
"""

from __future__ import annotations

import sys
from importlib.machinery import PathFinder


def ensure_chirp_importable() -> None:
    """Reorder ``sys.meta_path`` so the editable ``chirp`` finder wins."""
    if PathFinder in sys.meta_path:
        sys.meta_path.remove(PathFinder)
        sys.meta_path.append(PathFinder)
        # Drop any partially-resolved namespace package from a prior import.
        sys.modules.pop("chirp", None)


ensure_chirp_importable()
