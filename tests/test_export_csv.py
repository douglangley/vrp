"""Tests for CSV export, including the channel-subset export used by the row
context menu and the Bulk operations dialog (send just the relevant portion of
your memories to someone for import)."""

import csv
import os

import vrp  # noqa: F401  (import side effect: chirp path fix)

from chirp_backend import radio as radio_backend

IMAGE = os.path.abspath(
    os.path.join(
        os.path.dirname(__file__), "..", "chirp", "tests", "images",
        "Baofeng_UV-5R.img",
    )
)
MINI_IMAGE = os.path.abspath(
    os.path.join(
        os.path.dirname(__file__), "..", "chirp", "tests", "images",
        "Baofeng_UV-5R_Mini.img",
    )
)


def _locations(path):
    """Return the Location (channel number) column of an exported CSV as ints."""
    with open(path, newline="") as fh:
        return [int(row["Location"]) for row in csv.DictReader(fh)]


def _nonempty_numbers():
    lo, hi = radio_backend.get_state().memory_bounds
    return [
        n for n in range(lo, hi + 1)
        if not getattr(radio_backend.get_memory(n), "empty", True)
    ]


class TestExportCsv:
    def teardown_method(self):
        radio_backend.unload()

    def test_export_all_when_numbers_none(self, tmp_path):
        radio_backend.load_image(IMAGE)
        path = str(tmp_path / "all.csv")
        ok, _msg, count = radio_backend.export_to_csv(path)
        assert ok
        assert count == len(_nonempty_numbers())
        assert _locations(path) == _nonempty_numbers()

    def test_export_subset(self, tmp_path):
        radio_backend.load_image(IMAGE)
        subset = _nonempty_numbers()[:3]
        assert len(subset) == 3  # image has at least 3 populated channels
        path = str(tmp_path / "subset.csv")
        ok, _msg, count = radio_backend.export_to_csv(path, subset)
        assert ok
        assert count == 3
        assert _locations(path) == subset

    def test_subset_skips_empty_and_dupes_and_out_of_range(self, tmp_path):
        radio_backend.load_image(IMAGE)
        lo, hi = radio_backend.get_state().memory_bounds
        populated = _nonempty_numbers()[:2]
        # Find an empty slot in range to prove it's skipped.
        empty = next(n for n in range(lo, hi + 1)
                     if getattr(radio_backend.get_memory(n), "empty", True))
        # Duplicate a populated channel and add an out-of-range number.
        numbers = populated + [populated[0], empty, hi + 999]
        path = str(tmp_path / "mixed.csv")
        ok, _msg, count = radio_backend.export_to_csv(path, numbers)
        assert ok
        assert count == 2
        assert _locations(path) == populated  # de-duped, sorted, empties dropped

    def test_empty_selection_reports_nothing_to_export(self, tmp_path):
        radio_backend.load_image(IMAGE)
        lo, hi = radio_backend.get_state().memory_bounds
        empty = next(n for n in range(lo, hi + 1)
                     if getattr(radio_backend.get_memory(n), "empty", True))
        path = str(tmp_path / "none.csv")
        ok, msg, count = radio_backend.export_to_csv(path, [empty])
        assert not ok
        assert count == 0
        assert "No channels to export" in msg
        assert not os.path.exists(path)

    def test_no_radio_loaded(self, tmp_path):
        ok, msg, count = radio_backend.export_to_csv(str(tmp_path / "x.csv"), [1, 2])
        assert not ok
        assert count == 0

    def test_radio_starting_at_one_does_not_export_synthetic_channel_zero(
        self, tmp_path
    ):
        radio_backend.load_image(MINI_IMAGE)
        expected = _nonempty_numbers()
        assert expected and expected[0] >= 1

        path = str(tmp_path / "mini.csv")
        ok, _msg, count = radio_backend.export_to_csv(path)

        assert ok
        assert count == len(expected)
        assert _locations(path) == expected
        assert 0 not in _locations(path)
