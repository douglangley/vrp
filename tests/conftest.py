"""Pytest setup.

Importing ``vrp`` applies the ``sys.meta_path`` fix (see vrp/_chirp_path.py)
so ``import chirp`` resolves to ``chirp/chirp`` rather than the empty ``./chirp``
repository-root directory, regardless of how pytest is invoked.
"""

import pytest

import vrp  # noqa: F401  (import side effect: chirp path fix)


@pytest.fixture(autouse=True)
def _isolated_config(tmp_path, monkeypatch):
    """Point the config singleton at a throwaway file per test, so tests never
    read/write the real user config (and get deterministic default prefs)."""
    from vrp import config as cfgmod

    monkeypatch.setattr(
        cfgmod, "_instance", cfgmod.Config(path=str(tmp_path / "config.json"))
    )
    yield
