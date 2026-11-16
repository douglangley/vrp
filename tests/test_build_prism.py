"""build.py must ship prism's compiled core, or the frozen app has no speech.

prismatoid 0.18 turned its bindings into a compiled cffi extension that lives in
``prism/_native/`` and is reached through a runtime ``__path__`` append, and that
imports ``_cffi_backend`` from C. PyInstaller's static analysis sees neither, so
a build using only ``--collect-binaries=prism`` crashes on ``import prism`` --
verified by freezing a probe (PROGRESS_LOG 2026-11-16). These tests pin the two
extra PyInstaller args and the refusal to build without the extension.
"""

import importlib
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

build = importlib.import_module("build")


def test_ships_the_installed_prism_extension_into_its_native_folder():
    args = build.prism_native_args()

    binaries = [a for a in args if a.startswith("--add-binary=")]
    assert binaries, args
    for arg in binaries:
        source, dest = arg[len("--add-binary="):].rsplit(os.pathsep, 1)
        assert os.path.basename(source).startswith("_prism_cffi")
        assert os.path.isfile(source)
        # Must land where prism/_native.py adds to the package __path__.
        assert dest == "prism/_native"


def test_names_the_cffi_backend_the_extension_imports_from_c():
    assert "--hidden-import=_cffi_backend" in build.prism_native_args()


def test_refuses_to_build_when_the_extension_is_missing(tmp_path, monkeypatch):
    (tmp_path / "_native").mkdir()
    (tmp_path / "_native" / "prism.dll").write_bytes(b"")

    class _Spec:
        submodule_search_locations = [str(tmp_path)]

    monkeypatch.setattr("importlib.util.find_spec", lambda name: _Spec())

    with pytest.raises(SystemExit, match="no speech"):
        build.prism_native_args()
