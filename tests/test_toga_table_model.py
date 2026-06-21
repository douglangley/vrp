import os

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


def test_bf888_first_page_has_empty_text_and_hidden_channel_number():
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
    assert page.accessors[:4] == ["number", "state", "freq", "tmode"]
    assert page.accessors[-2:] == ["channel_number", "empty"]
    assert len(page.rows) == 5
    assert page.rows[0]["number"] == "1"
    assert page.rows[0]["channel_number"] == 1
    assert page.rows[0]["empty"] is False
    assert any(row["state"] == EMPTY_MARKER for row in page.rows)
    assert page.status == "Showing channels 1 to 5 of 16, page 1 of 4."


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
