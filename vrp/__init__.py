"""Versatile Radio Programmer (VRP) application package.

The wxPython UI layer that hosts CHIRP's functionality accessibly. The CHIRP
library itself is wrapped by the sibling ``chirp_backend`` package; everything
under ``vrp`` is the accessible front end (the native ``vrp/native`` app window
and grid, the shared native wx dialogs, and speech).

The first import below reorders the import machinery so the vendored, editable
``chirp`` package resolves correctly before anything tries to import it. Keep
it first.
"""

from vrp import _chirp_path as _chirp_path  # noqa: F401  (side effect: path fix)

__all__ = ["__version__"]

__version__ = "0.1.0"
