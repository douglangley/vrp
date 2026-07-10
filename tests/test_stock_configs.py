"""Tests for the CHIRP stock-config ("frequency lists") discovery + description
backend, and an end-to-end import of a stock list into a loaded radio."""

import os

import vrp  # noqa: F401  (import side effect: chirp path fix)

from chirp_backend import stock_configs

IMAGE = os.path.abspath(
    os.path.join(
        os.path.dirname(__file__), "..", "chirp", "tests", "images",
        "Baofeng_UV-5R.img",
    )
)


def _find(name_substr):
    """Return the (display_name, path) of the first config whose name contains
    ``name_substr`` (case-insensitive)."""
    for name, path in stock_configs.list_configs():
        if name_substr.lower() in name.lower():
            return name, path
    raise AssertionError(f"no stock config matching {name_substr!r}")


class TestListConfigs:
    def test_dir_resolves_to_chirp_tree_from_source(self):
        d = stock_configs.stock_configs_dir()
        assert os.path.isdir(d)
        # From source it lives under the chirp package.
        import chirp
        assert d == os.path.join(os.path.dirname(chirp.__file__), "stock_configs")

    def test_lists_configs_sorted_and_csv_stripped(self):
        configs = stock_configs.list_configs()
        assert len(configs) >= 15  # CHIRP ships ~20
        names = [n for n, _ in configs]
        assert names == sorted(names, key=str.lower)  # sorted, case-insensitive
        for name, path in configs:
            assert not name.endswith(".csv")  # extension stripped for display
            assert path.endswith(".csv")
            assert os.path.isfile(path)

    def test_known_config_present(self):
        name, path = _find("NOAA Weather Alert")
        assert "NOAA" in name
        assert os.path.isfile(path)

    def test_frozen_dir_resolves_under_meipass(self, tmp_path, monkeypatch):
        # When frozen (PyInstaller), build.py bundles the CSVs to
        # <_MEIPASS>/chirp/stock_configs via --add-data; the resolver must look
        # there. Simulate a frozen app with a stray bundled list.
        bundled = tmp_path / "chirp" / "stock_configs"
        bundled.mkdir(parents=True)
        (bundled / "US Test List.csv").write_text("Location,Name,Frequency\n")
        (bundled / ".hidden.csv").write_text("x")  # dotfile ignored
        monkeypatch.setattr(stock_configs.sys, "frozen", True, raising=False)
        monkeypatch.setattr(stock_configs.sys, "_MEIPASS", str(tmp_path), raising=False)

        assert stock_configs.stock_configs_dir() == str(bundled)
        configs = stock_configs.list_configs()
        assert configs == [("US Test List", str(bundled / "US Test List.csv"))]


class TestDescribeConfig:
    def test_describe_reports_count_and_frequency(self):
        _name, path = _find("NOAA Weather Alert")
        text = stock_configs.describe_config(path)
        assert "10 channel(s)" in text      # NOAA has 10 weather channels
        assert "162.55" in text             # a known NOAA frequency

    def test_describe_truncates_long_lists(self):
        _name, path = _find("NOAA Weather Alert")
        text = stock_configs.describe_config(path, max_rows=3)
        # 10 channels, only 3 shown -> a "… and 7 more." line.
        assert "and 7 more" in text


class TestImportStockConfig:
    """The stock config imports through the same path the UI uses:
    open_image_as_source -> memory_ops.import_memories."""

    def teardown_method(self):
        from chirp_backend import radio as radio_backend
        radio_backend.unload()

    def test_import_stock_list_into_loaded_radio(self):
        from chirp_backend import radio as radio_backend
        from chirp_backend import memory_ops

        radio_backend.load_image(IMAGE)
        _name, path = _find("NOAA Weather Alert")
        src, message = radio_backend.open_image_as_source(path)
        assert src is not None, message

        dest = 20
        ok, msg, affected = memory_ops.import_memories(src, dest, True)
        assert ok, msg
        assert affected  # some channels landed
        # The first imported channel is at the destination and is a NOAA freq.
        first = radio_backend.get_memory(dest)
        assert not first.empty
        assert 162_000_000 <= first.freq <= 163_000_000
