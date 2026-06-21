import os
from types import SimpleNamespace

import pytest

from chirp_backend import radio as radio_backend

BF888_IMAGE = os.path.abspath(
    os.path.join(
        os.path.dirname(__file__),
        "..",
        "chirp",
        "tests",
        "images",
        "Baofeng_BF-888.img",
    )
)

UV5R_IMAGE = os.path.abspath(
    os.path.join(
        os.path.dirname(__file__),
        "..",
        "chirp",
        "tests",
        "images",
        "Baofeng_UV-5R.img",
    )
)


@pytest.fixture(autouse=True)
def _unload_radio():
    radio_backend.unload()
    yield
    radio_backend.unload()


def test_no_radio_page_is_empty_and_named():
    from vrp_toga.table_model import build_table_page

    page = build_table_page()

    assert page.radio_label == "No radio loaded"
    assert page.columns == ["Ch #", "State"]
    assert page.accessors == ["number", "state", "channel_number", "empty"]
    assert page.rows == []
    assert page.status == "No radio image loaded."


def test_bf888_first_page_has_no_empty_markers_and_hidden_channel_number():
    from vrp_toga.table_model import EMPTY_MARKER, build_table_page

    ok, message = radio_backend.load_image(BF888_IMAGE)
    assert ok, message

    page = build_table_page(page=1, page_size=5)

    assert page.radio_label == "Baofeng BF-888"
    assert page.page == 1
    assert page.total_pages == 4
    assert page.first == 1
    assert page.last == 5
    assert page.total == 16
    assert page.columns[:3] == ["Ch #", "State", "Frequency"]
    assert page.accessors[:4] == ["number", "state", "freq", "name"]
    assert page.accessors[-2:] == ["channel_number", "empty"]
    assert len(page.rows) == 5
    assert page.rows[0]["number"] == "1"
    assert page.rows[0]["channel_number"] == 1
    assert page.rows[0]["empty"] is False
    assert all(row["state"] != EMPTY_MARKER for row in page.rows)
    assert page.status == "Showing channels 1 to 5 of 16, page 1 of 4."


def test_bf888_negative_page_size_falls_back_to_default_metadata():
    from vrp_toga.table_model import build_table_page

    ok, message = radio_backend.load_image(BF888_IMAGE)
    assert ok, message

    page = build_table_page(page=1, page_size=-5)

    assert page.page == 1
    assert page.total_pages == 1
    assert page.first == 1
    assert page.last == 16
    assert len(page.rows) == 16


def test_table_page_status_reflects_modified_flag_after_save(tmp_path):
    from vrp_toga.table_model import build_table_page

    ok, message = radio_backend.load_image(BF888_IMAGE)
    assert ok, message

    page = build_table_page(page=1, page_size=100)
    assert page.status == "Showing channels 1 to 16 of 16, page 1 of 1."

    saved_path = tmp_path / "bf888-copy.img"
    ok, message = radio_backend.save_image(str(saved_path))
    assert ok, message

    page = build_table_page(page=1, page_size=100)
    assert page.radio_label == "Baofeng BF-888"
    assert page.status == "Showing channels 1 to 16 of 16, page 1 of 1."


def test_page_range_clamps_requested_page_to_loaded_bounds():
    from vrp_toga.table_model import page_range

    ok, message = radio_backend.load_image(BF888_IMAGE)
    assert ok, message

    assert page_range(99, page_size=5) == (16, 16)


def test_uv5r_empty_marker_matches_hidden_empty_flag():
    from vrp_toga.table_model import EMPTY_MARKER, build_table_page

    ok, message = radio_backend.load_image(UV5R_IMAGE)
    assert ok, message

    page = build_table_page(page=1, page_size=10)

    assert any(row["empty"] is True for row in page.rows)
    for row in page.rows:
        assert (row["state"] == EMPTY_MARKER) is (row["empty"] is True)


def test_uv5r_second_page_is_clamped_and_sliced():
    from vrp_toga.table_model import build_table_page

    ok, message = radio_backend.load_image(UV5R_IMAGE)
    assert ok, message

    page = build_table_page(page=99, page_size=100)

    assert page.page == 2
    assert page.total_pages == 2
    assert page.first == 100
    assert page.last == 127
    assert len(page.rows) == 28
    assert page.rows[0]["channel_number"] == 100
    assert page.rows[-1]["channel_number"] == 127


def test_page_for_channel_matches_loaded_radio_bounds():
    from vrp_toga.table_model import page_for_channel

    ok, message = radio_backend.load_image(UV5R_IMAGE)
    assert ok, message

    assert page_for_channel(0, page_size=100) == 1
    assert page_for_channel(100, page_size=100) == 2
    assert page_for_channel(999, page_size=100) == 2


def test_refresh_table_reuses_content_table_and_data_when_schema_is_unchanged(
    monkeypatch,
):
    monkeypatch.setenv("TOGA_BACKEND", "toga_dummy")

    from vrp_toga import app as appmod

    app = appmod.VRPTogaApp(
        formal_name=appmod.APP_TITLE,
        app_id="online.techopolis.vrp.toga.test",
    )

    initial_page = SimpleNamespace(
        radio_label="Baofeng BF-888",
        status="Showing channels 1 to 2 of 4, page 1 of 2.",
        columns=["Ch #", "State", "Frequency"],
        accessors=["number", "state", "freq", "channel_number", "empty"],
        rows=[
            {"number": "1", "state": "", "freq": "462.125000", "channel_number": 1, "empty": False},
            {"number": "2", "state": "", "freq": "462.225000", "channel_number": 2, "empty": False},
        ],
        page=1,
        total_pages=2,
        first=1,
        last=2,
        total=4,
        has_prev=False,
        has_next=True,
    )
    next_page = SimpleNamespace(
        radio_label="Baofeng BF-888",
        status="Showing channels 3 to 4 of 4, page 2 of 2.",
        columns=["Ch #", "State", "Frequency"],
        accessors=["number", "state", "freq", "channel_number", "empty"],
        rows=[
            {"number": "3", "state": "", "freq": "462.325000", "channel_number": 3, "empty": False},
            {"number": "4", "state": "", "freq": "462.425000", "channel_number": 4, "empty": False},
        ],
        page=2,
        total_pages=2,
        first=3,
        last=4,
        total=4,
        has_prev=True,
        has_next=False,
    )

    scroll_calls = []
    source = appmod.ListSource(accessors=initial_page.accessors, data=initial_page.rows)
    selected_row = source[1]
    table = SimpleNamespace(
        data=source,
        selection=selected_row,
        scroll_to_row=lambda index: scroll_calls.append(("row", index)),
        scroll_to_top=lambda: scroll_calls.append(("top", None)),
    )
    content = object()

    app._speak_enabled = False
    app._page = 2
    app._last_table_page = initial_page
    app._main_window = SimpleNamespace(content=content)
    app.radio_label = SimpleNamespace(text=initial_page.radio_label)
    app.status_label = SimpleNamespace(text=initial_page.status)
    app.table = table

    refresh_calls = []
    app._refresh_command_state = lambda: refresh_calls.append("refreshed")

    monkeypatch.setattr(appmod, "build_table_page", lambda page: next_page)

    app._refresh_table()

    assert app.main_window.content is content
    assert app.table is table
    assert app.table.data is source
    assert app.radio_label.text == next_page.radio_label
    assert app.status_label.text == next_page.status
    rows = list(app.table.data)
    assert [row.channel_number for row in rows] == [3, 4]
    assert [row.freq for row in rows] == ["462.325000", "462.425000"]
    assert app._last_table_page is next_page
    assert app._page == 2
    assert refresh_calls == ["refreshed"]
    assert scroll_calls == [("row", 1)]


def test_refresh_table_updates_existing_source_and_scrolls_to_top_without_selection(
    monkeypatch,
):
    monkeypatch.setenv("TOGA_BACKEND", "toga_dummy")

    from vrp_toga import app as appmod

    app = appmod.VRPTogaApp(
        formal_name=appmod.APP_TITLE,
        app_id="online.techopolis.vrp.toga.test",
    )

    initial_page = SimpleNamespace(
        radio_label="Baofeng BF-888",
        status="Showing channels 1 to 3 of 4, page 1 of 2.",
        columns=["Ch #", "State", "Frequency"],
        accessors=["number", "state", "freq", "channel_number", "empty"],
        rows=[
            {"number": "1", "state": "", "freq": "462.125000", "channel_number": 1, "empty": False},
            {"number": "2", "state": "", "freq": "462.225000", "channel_number": 2, "empty": False},
            {"number": "3", "state": "", "freq": "462.325000", "channel_number": 3, "empty": False},
        ],
        page=1,
        total_pages=2,
        first=1,
        last=3,
        total=4,
        has_prev=False,
        has_next=True,
    )
    next_page = SimpleNamespace(
        radio_label="Baofeng BF-888",
        status="Showing channels 1 to 2 of 2, page 1 of 1.",
        columns=["Ch #", "State", "Frequency"],
        accessors=["number", "state", "freq", "channel_number", "empty"],
        rows=[
            {"number": "8", "state": "", "freq": "463.125000", "channel_number": 8, "empty": False},
            {"number": "9", "state": "", "freq": "463.225000", "channel_number": 9, "empty": False},
        ],
        page=1,
        total_pages=1,
        first=1,
        last=2,
        total=2,
        has_prev=False,
        has_next=False,
    )

    scroll_calls = []
    source = appmod.ListSource(accessors=initial_page.accessors, data=initial_page.rows)
    table = SimpleNamespace(
        data=source,
        selection=None,
        scroll_to_row=lambda index: scroll_calls.append(("row", index)),
        scroll_to_top=lambda: scroll_calls.append(("top", None)),
    )
    content = object()

    app._speak_enabled = False
    app._page = 1
    app._last_table_page = initial_page
    app._main_window = SimpleNamespace(content=content)
    app.radio_label = SimpleNamespace(text=initial_page.radio_label)
    app.status_label = SimpleNamespace(text=initial_page.status)
    app.table = table

    refresh_calls = []
    app._refresh_command_state = lambda: refresh_calls.append("refreshed")

    monkeypatch.setattr(appmod, "build_table_page", lambda page: next_page)

    app._refresh_table()

    assert app.main_window.content is content
    assert app.table is table
    assert app.table.data is source
    assert app.radio_label.text == next_page.radio_label
    assert app.status_label.text == next_page.status
    rows = list(app.table.data)
    assert [row.channel_number for row in rows] == [8, 9]
    assert [row.freq for row in rows] == ["463.125000", "463.225000"]
    assert app._last_table_page is next_page
    assert app._page == 1
    assert refresh_calls == ["refreshed"]
    assert scroll_calls == [("top", None)]


def test_refresh_table_rebuilds_content_when_schema_changes(monkeypatch):
    monkeypatch.setenv("TOGA_BACKEND", "toga_dummy")

    from vrp_toga import app as appmod

    app = appmod.VRPTogaApp(
        formal_name=appmod.APP_TITLE,
        app_id="online.techopolis.vrp.toga.test",
    )

    initial_page = SimpleNamespace(
        radio_label="No radio loaded",
        status="No radio image loaded.",
        columns=["Ch #", "State"],
        accessors=["number", "state", "channel_number", "empty"],
        rows=[],
        page=1,
        total_pages=1,
        first=0,
        last=0,
        total=0,
        has_prev=False,
        has_next=False,
    )
    loaded_page = SimpleNamespace(
        radio_label="Baofeng BF-888",
        status="Showing channels 1 to 2 of 4, page 1 of 2.",
        columns=["Ch #", "State", "Frequency"],
        accessors=["number", "state", "freq", "channel_number", "empty"],
        rows=[
            {"number": "1", "state": "", "freq": "462.125000", "channel_number": 1, "empty": False},
            {"number": "2", "state": "", "freq": "462.225000", "channel_number": 2, "empty": False},
        ],
        page=1,
        total_pages=2,
        first=1,
        last=2,
        total=4,
        has_prev=False,
        has_next=True,
    )

    app._speak_enabled = False
    app._page = 1
    app._last_table_page = initial_page
    app._main_window = SimpleNamespace(content=object())
    app.status_label = SimpleNamespace(text=initial_page.status)

    new_content = object()
    build_calls = []

    def fake_build_content(self, table_page):
        build_calls.append(table_page)
        self.radio_label = SimpleNamespace(text=table_page.radio_label)
        self.status_label = SimpleNamespace(text=table_page.status)
        self.table = SimpleNamespace(
            data=appmod.ListSource(accessors=table_page.accessors, data=table_page.rows),
            scroll_to_top=lambda: None,
        )
        return new_content

    monkeypatch.setattr(appmod.VRPTogaApp, "_build_content", fake_build_content)
    monkeypatch.setattr(appmod, "build_table_page", lambda page: loaded_page)
    app._refresh_command_state = lambda: None

    app._refresh_table()

    assert build_calls == [loaded_page]
    assert app.main_window.content is new_content
    rows = list(app.table.data)
    assert [row.channel_number for row in rows] == [1, 2]
    assert [row.freq for row in rows] == ["462.125000", "462.225000"]
    assert app.radio_label.text == loaded_page.radio_label
    assert app.status_label.text == loaded_page.status
