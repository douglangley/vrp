"""Guard: VRP code must never import ``chirp.wxui``.

``chirp.wxui`` is CHIRP's own (inaccessible) wxPython GUI — the thing VRP
replaces. CLAUDE.md forbids importing it from VRP code; this test enforces that
rule mechanically instead of by review alone.

It parses each first-party ``.py`` file's AST and inspects only real ``import``
statements, so the legitimate *references* to ``chirp.wxui`` in docstrings and
comments (e.g. ``chirp_backend/serial_trace.py`` mirrors
``chirp/chirp/wxui/serialtrace.py``, and ``chirp_backend/radio.py`` explains why
it does NOT use ``chirp.wxui.clone``) do not trip it.
"""

from __future__ import annotations

import ast
import os

# First-party source trees to scan (never ./chirp — that's the vendored library).
_ROOTS = ("vrp", "chirp_backend")
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _iter_py_files():
    for root in _ROOTS:
        for dirpath, _dirs, files in os.walk(os.path.join(_PROJECT_ROOT, root)):
            if "__pycache__" in dirpath:
                continue
            for name in files:
                if name.endswith(".py"):
                    yield os.path.join(dirpath, name)


def _imports_wxui(path: str) -> bool:
    with open(path, encoding="utf-8") as fh:
        tree = ast.parse(fh.read(), filename=path)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            if any(a.name == "chirp.wxui" or a.name.startswith("chirp.wxui.")
                   for a in node.names):
                return True
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if mod == "chirp.wxui" or mod.startswith("chirp.wxui."):
                return True
            # `from chirp import wxui`
            if mod == "chirp" and any(a.name == "wxui" for a in node.names):
                return True
    return False


def test_no_first_party_module_imports_chirp_wxui():
    offenders = [
        os.path.relpath(p, _PROJECT_ROOT)
        for p in _iter_py_files()
        if _imports_wxui(p)
    ]
    assert not offenders, (
        "chirp.wxui is CHIRP's inaccessible GUI and must not be imported by VRP "
        f"code (CLAUDE.md). Offending file(s): {offenders}"
    )
