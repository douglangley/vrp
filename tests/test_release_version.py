"""Tests for the date-based release scheme (tools/release_version.py).

The scheme is VRP-YYYYMMDD.N — see tools/release_version.py's docstring. These
cover the version arithmetic, the speakable About-box rendering, and the
invariant that the two files carrying the version never drift apart.
"""

import datetime
import importlib.util
import os
import sys

import pytest

from vrp import __version__, describe_version

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load_release_version():
    """Import tools/release_version.py by path (tools/ isn't a package)."""
    path = os.path.join(PROJECT_ROOT, "tools", "release_version.py")
    spec = importlib.util.spec_from_file_location("release_version", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["release_version"] = module
    spec.loader.exec_module(module)
    return module


rv = _load_release_version()


# -- parse_version ---------------------------------------------------------


@pytest.mark.parametrize(
    "version, expected",
    [
        ("20260715.1", ("20260715", 1)),
        ("20260715.2", ("20260715", 2)),
        ("20260715.10", ("20260715", 10)),
        ("20261231.99", ("20261231", 99)),
    ],
)
def test_parse_version_accepts_date_versions(version, expected):
    assert rv.parse_version(version) == expected


@pytest.mark.parametrize(
    "version",
    [
        "0.1.0",           # the old semantic version
        "20260715",        # no build number
        "20260715.0",      # N is 1-based
        "20260715.01",     # N is never zero-padded
        "2026715.1",       # short date
        "20261332.1",      # date-shaped but not a real date
        "20260230.1",      # 30 February
        "v20260715.1",     # tag prefix is not part of the version
        "",
    ],
)
def test_parse_version_rejects_non_scheme(version):
    assert rv.parse_version(version) is None


# -- next_version ----------------------------------------------------------


def test_next_version_starts_at_one_on_a_new_day():
    today = datetime.date(2026, 7, 15)
    assert rv.next_version("20260714.3", today) == "20260715.1"


def test_next_version_increments_within_the_same_day():
    today = datetime.date(2026, 7, 15)
    assert rv.next_version("20260715.1", today) == "20260715.2"
    assert rv.next_version("20260715.2", today) == "20260715.3"
    assert rv.next_version("20260715.9", today) == "20260715.10"


def test_next_version_from_a_non_date_version_starts_today_at_one():
    """The 0.1.0 -> date-scheme transition (and any hand-set odd value)."""
    today = datetime.date(2026, 7, 15)
    assert rv.next_version("0.1.0", today) == "20260715.1"


def test_next_version_is_never_behind_the_current_one():
    """Bumping always moves forward, so releases stay ordered."""
    today = datetime.date(2026, 7, 15)
    current = "20260715.4"
    assert rv.parse_version(rv.next_version(current, today)) > rv.parse_version(current)


def test_versions_order_correctly_as_dates_then_builds():
    ordered = ["20260714.1", "20260714.9", "20260714.10", "20260715.1", "20260801.1"]
    assert sorted(ordered, key=rv.parse_version) == ordered


def test_tag_for_prefixes_the_version():
    assert rv.tag_for("20260715.1") == "VRP-20260715.1"


# -- the version files agree ----------------------------------------------


def test_init_and_pyproject_versions_agree():
    """vrp/__init__.py and pyproject.toml both carry the version; a release that
    updates only one would ship mismatched metadata."""
    assert rv.read_version() == rv.read_pyproject_version()


def test_shipped_version_matches_the_scheme():
    assert rv.parse_version(__version__) is not None, (
        f"{__version__} is not a VRP-YYYYMMDD.N version"
    )


def test_read_version_matches_the_imported_package_version():
    assert rv.read_version() == __version__


def test_write_version_round_trips(tmp_path, monkeypatch):
    """--bump/--set rewrites both files in place, touching only the version."""
    init_py = tmp_path / "__init__.py"
    pyproject = tmp_path / "pyproject.toml"
    init_py.write_text('__all__ = ["__version__"]\n\n__version__ = "20260715.1"\n',
                       encoding="utf-8")
    pyproject.write_text(
        '[project]\nname = "versatile-radio-programmer"\nversion = "20260715.1"\n'
        'dependencies = [\n    "wxpython>=4.2.0",\n]\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(rv, "INIT_PY", str(init_py))
    monkeypatch.setattr(rv, "PYPROJECT", str(pyproject))

    rv.write_version("20260716.1")

    assert rv.read_version() == "20260716.1"
    assert rv.read_pyproject_version() == "20260716.1"
    # The dependency constraint must not be mistaken for the project version.
    assert '"wxpython>=4.2.0"' in pyproject.read_text(encoding="utf-8")
    assert '__all__ = ["__version__"]' in init_py.read_text(encoding="utf-8")


# -- describe_version (the speakable About-box form) -----------------------


def test_describe_version_is_speakable():
    """A screen reader reads '20260715.1' as one huge number; the About box
    carries this form instead so the release is audible."""
    assert describe_version("20260715.1") == "Release 1 of 15 July 2026"


def test_describe_version_does_not_zero_pad_the_day():
    assert describe_version("20260705.2") == "Release 2 of 5 July 2026"


def test_describe_version_reads_the_build_number():
    assert describe_version("20260715.12") == "Release 12 of 15 July 2026"


@pytest.mark.parametrize("version", ["0.1.0", "dev", "20261332.1"])
def test_describe_version_passes_through_non_date_versions(version):
    """A local/dev build shows its version unchanged rather than a bogus date."""
    assert describe_version(version) == version


def test_describe_version_defaults_to_the_shipped_version():
    assert describe_version() == describe_version(__version__)
