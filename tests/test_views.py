"""Phase 1 tests: load a radio image, render the read-only grid, save, unload.

Uses a CHIRP stock test image (no hardware needed). Verifies the accessible
table structure the grid template must always produce.
"""

import os
import tempfile

import pytest

from chirp_backend import radio as radio_backend
from vrp import views

IMAGE = os.path.abspath(
    os.path.join(
        os.path.dirname(__file__), "..", "chirp", "tests", "images", "Baofeng_BF-888.img"
    )
)


@pytest.fixture
def loaded_radio():
    ok, message = radio_backend.load_image(IMAGE)
    assert ok, message
    yield radio_backend.get_state()
    radio_backend.unload()


def test_load_image_sets_state(loaded_radio):
    assert loaded_radio.loaded
    assert loaded_radio.radio.VENDOR == "Baofeng"
    assert loaded_radio.radio.MODEL == "BF-888"
    assert loaded_radio.memory_bounds == (1, 16)


def test_render_channels_is_accessible_table(loaded_radio):
    out = views.render_channels()
    # Real table with column + row scoped headers (CLAUDE rule #2).
    assert "<table>" in out
    assert '<th scope="col">Ch #</th>' in out
    assert out.count('scope="row"') == 16  # one row header per channel
    # Caption carries the table description; attribution footer is present.
    assert "Memory channels for Baofeng BF-888" in out
    assert "chirpmyradio.com" in out


def test_empty_channels_have_visible_text_marker(loaded_radio):
    # BF-888 stock image has empty channels; emptiness must be conveyed as
    # text (not color alone) per CLAUDE rule #7.
    out = views.render_channels()
    assert "(empty)" in out


def test_save_image_round_trips(loaded_radio):
    tmp = os.path.join(tempfile.gettempdir(), "vrp_test_roundtrip.img")
    try:
        ok, message = radio_backend.save_image(tmp)
        assert ok, message
        assert os.path.exists(tmp)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def test_render_without_radio_falls_back_to_welcome():
    radio_backend.unload()
    out = views.render_channels()
    assert "Versatile Radio Programmer" in out  # welcome view heading


def _first_nonempty(state) -> int:
    low, high = state.memory_bounds
    for n in range(low, high + 1):
        mem = radio_backend.get_memory(n)
        if mem is not None and not mem.empty:
            return n
    raise AssertionError("no non-empty channel in test image")


def test_grid_is_readonly_with_per_row_edit_buttons(loaded_radio):
    out = views.render_channels()
    # Editing is via a dialog, not in the grid: cells are read-only, each row
    # has a uniquely-labeled Edit button, and there's an Actions column.
    assert "cell-edit" not in out
    assert '<th scope="col">Edit</th>' in out  # Edit column (second column)
    assert 'id="ch-row-1"' in out
    assert 'aria-label="Edit channel 1"' in out
    assert "action:'edit_channel'" in out


def test_render_row_matches_grid_row(loaded_radio):
    inner = views.render_row(1)
    assert 'scope="row"' in inner
    assert 'id="edit-btn-1"' in inner
    # The same row markup appears in the full grid render.
    assert inner.strip() in views.render_channels()


def test_update_channel_applies_multiple_fields():
    from chirp_backend import memory_ops

    ok, message = radio_backend.load_image(NAMED_IMAGE)
    assert ok, message
    try:
        state = radio_backend.get_state()
        ch = _first_nonempty(state)
        ok, message, affected = memory_ops.update_channel(
            ch, {"name": "MULTI", "freq": "147.000"}
        )
        assert ok, message
        assert affected == [ch]
        mem = radio_backend.get_memory(ch)
        assert "MULTI" in mem.name
        assert mem.freq == 147_000_000
    finally:
        radio_backend.unload()


def test_update_channel_atomic_on_invalid(loaded_radio):
    # If any field is invalid, nothing is written (atomic).
    from chirp_backend import memory_ops

    ch = _first_nonempty(loaded_radio)
    before = radio_backend.get_memory(ch).freq
    ok, message, _ = memory_ops.update_channel(
        ch, {"freq": "146.520", "tmode": "TSQL", "ctone": "not-a-tone"}
    )
    assert not ok
    assert radio_backend.get_memory(ch).freq == before  # unchanged


def test_validate_channel_values_reports_bad_field(loaded_radio):
    from chirp_backend import memory_ops

    ch = _first_nonempty(loaded_radio)
    ok, message, bad_field = memory_ops.validate_channel_values(
        ch, {"freq": "garbage"}
    )
    assert not ok
    assert bad_field == "freq"


def test_parse_channel_spec():
    from chirp_backend import memory_ops

    nums, err = memory_ops.parse_channel_spec("1-5,8,10-12", 0, 20)
    assert err is None
    assert nums == [1, 2, 3, 4, 5, 8, 10, 11, 12]
    # reversed range, dedupe
    nums, err = memory_ops.parse_channel_spec("5-1,3,3", 0, 20)
    assert err is None and nums == [1, 2, 3, 4, 5]
    # errors
    assert memory_ops.parse_channel_spec("", 0, 20)[1]
    assert memory_ops.parse_channel_spec("1-100", 0, 20)[1]  # out of range
    assert memory_ops.parse_channel_spec("abc", 0, 20)[1]    # non-numeric


def test_operations_button_present(loaded_radio):
    out = views.render_channels(1)
    assert 'aria-label="Organize channels"' in out
    assert 'id="ops-btn"' in out
    assert "action:'operations'" in out
    assert 'id="find-btn"' in out
    assert "action:'find'" in out


BANK_IMAGE = os.path.abspath(
    os.path.join(
        os.path.dirname(__file__), "..", "chirp", "tests", "images", "Yaesu_FT-60.img"
    )
)


def _fake_source(freqs):
    """A NetworkResultRadio pre-populated with simple FM memories."""
    from chirp.sources import base
    from chirp import chirp_common

    radio = base.NetworkResultRadio()
    mems = []
    for i, f in enumerate(freqs):
        m = chirp_common.Memory()
        m.number = i
        m.freq = f
        m.name = f"S{i}"
        m.mode = "FM"
        m.empty = False
        mems.append(m)
    radio._memories = mems
    return radio


def test_open_image_as_source_does_not_mutate_state():
    from chirp_backend import memory_ops

    ok, message = radio_backend.load_image(NAMED_IMAGE)  # UV-5R is the active radio
    assert ok, message
    try:
        src, msg = radio_backend.open_image_as_source(BANK_IMAGE)  # FT-60 as source
        assert src is not None, msg
        # the active radio must be unchanged
        assert radio_backend.get_state().radio.MODEL == "UV-5R"
        # and importing from the file source works
        ok, message, affected = memory_ops.import_memories(src, destination=0, overwrite=True)
        assert ok, message
        assert affected
    finally:
        radio_backend.unload()


def test_export_to_csv_round_trip():
    import os
    import tempfile

    ok, message = radio_backend.load_image(NAMED_IMAGE)
    assert ok, message
    tmp = os.path.join(tempfile.gettempdir(), "vrp_export_test.csv")
    try:
        ok, message, count = radio_backend.export_to_csv(tmp)
        assert ok, message
        assert count > 0 and os.path.exists(tmp)
        # reopening the CSV as a source yields the same channel count
        src, _msg = radio_backend.open_image_as_source(tmp)
        assert src is not None
        slo, shi = src.get_features().memory_bounds
        nonempty = sum(
            1 for n in range(slo, shi + 1) if not src.get_memory(n).empty
        )
        assert nonempty == count
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)
        radio_backend.unload()


def test_describe_radio_html(loaded_radio):
    out = radio_backend.describe_radio_html(loaded_radio)
    assert "Baofeng" in out and "BF-888" in out
    assert "Channels" in out and ("Yes" in out or "No" in out)
    assert "<table>" in out and 'scope="row"' in out


def test_query_sources_registry():
    from chirp_backend import query

    keys = [s["key"] for s in query.SOURCES]
    for key in ("amsat", "satnogs", "dmrmarc", "mapy73"):
        assert key in keys, key
        # every registered source class is importable
        assert query.make_source_radio(key) is not None, key
    assert query.get_source("amsat")["cls"] == "RadioAmateurSatellites"
    # mapy73 exposes a choice param with options
    mapy = query.get_source("mapy73")
    assert mapy["params"][0]["kind"] == "choice" and mapy["params"][0]["options"]


def test_query_run_fetch_with_fake_source():
    from chirp_backend import query

    radio = _fake_source([145_800_000, 146_520_000])
    progress = []
    radio.do_fetch = lambda status, params: status.send_status("Loading", 50)
    ok, message = query.run_fetch(radio, {}, lambda m, p: progress.append((m, p)))
    assert ok and "2 result" in message
    assert progress and progress[0] == ("Loading", 50)


def test_query_run_fetch_reports_failure():
    from chirp_backend import query

    radio = _fake_source([])
    radio.do_fetch = lambda status, params: status.send_fail("network down")
    ok, message = query.run_fetch(radio, {}, None)
    assert not ok and "network down" in message


def test_import_memories_into_loaded_radio():
    from chirp_backend import memory_ops

    ok, message = radio_backend.load_image(NAMED_IMAGE)  # UV-5R (VHF/UHF)
    assert ok, message
    try:
        src = _fake_source([145_800_000, 146_520_000])
        ok, message, affected = memory_ops.import_memories(src, destination=0, overwrite=True)
        assert ok, message
        assert len(affected) == 2
        assert radio_backend.get_memory(0).freq == 145_800_000
        assert radio_backend.get_memory(1).freq == 146_520_000
    finally:
        radio_backend.unload()


def test_banks_assign_round_trip():
    from chirp_backend import bank_ops

    ok, message = radio_backend.load_image(BANK_IMAGE)
    assert ok, message
    try:
        assert bank_ops.has_bank()
        ch = _first_nonempty(radio_backend.get_state())
        state = bank_ops.get_bank_state(ch)
        assert state["ok"] and state["banks"]
        idx = state["banks"][0][0]
        ok, msg, aff = bank_ops.apply_bank_changes(ch, {idx})
        assert ok, msg
        assert aff == [ch]
        assert idx in bank_ops.get_bank_state(ch)["member_indexes"]
        # remove it again
        ok, msg, _ = bank_ops.apply_bank_changes(ch, set())
        assert ok, msg
        assert not bank_ops.get_bank_state(ch)["member_indexes"]
    finally:
        radio_backend.unload()


def test_banks_absent_on_simple_radio(loaded_radio):
    # BF-888 (the loaded_radio fixture image) has no banks.
    from chirp_backend import bank_ops

    assert not bank_ops.has_bank()
    state = bank_ops.get_bank_state(1)
    assert not state["ok"]


def test_radio_settings_available_and_apply():
    from chirp import settings as cs

    ok, message = radio_backend.load_image(NAMED_IMAGE)
    assert ok, message
    try:
        assert radio_backend.has_settings()
        groups = radio_backend.get_radio_settings()
        assert groups and len(groups) >= 1

        # Flip a mutable boolean setting and apply it back.
        target = None
        for g in groups:
            for s in g.walk():
                value = list(s)[0]
                if isinstance(value, cs.RadioSettingValueBoolean) and value.get_mutable():
                    target = value
                    break
            if target:
                break
        assert target is not None, "expected a boolean setting on the UV-5R"
        target.set_value(not bool(target.get_value()))
        assert target.changed()
        ok, message = radio_backend.apply_radio_settings(groups)
        assert ok, message
    finally:
        radio_backend.unload()


def test_settings_none_when_no_radio():
    radio_backend.unload()
    assert not radio_backend.has_settings()
    assert radio_backend.get_radio_settings() is None


def test_list_radio_models_and_lookup():
    from chirp import directory

    models = radio_backend.list_radio_models()
    assert len(models) > 100
    m = models[0]
    assert {"id", "vendor", "model", "label"} <= set(m)
    # ids round-trip through CHIRP's driver lookup
    assert directory.get_radio(m["id"]) is not None


def test_download_unknown_driver_fails_gracefully():
    calls = []
    ok, message = radio_backend.download_from_radio(
        "COMX", "No_Such_Driver_Id", lambda c, t, msg: calls.append(msg)
    )
    assert not ok
    assert "Unknown radio" in message


def test_upload_without_radio_fails():
    radio_backend.unload()
    ok, message = radio_backend.upload_to_radio("COMX", lambda c, t, m: None)
    assert not ok
    assert "No radio loaded" in message


def test_find_field_choices():
    from vrp.find_dialog import FIELD_CHOICES

    labels = [label for label, _f in FIELD_CHOICES]
    assert "All fields" in labels and "Name" in labels
    # mapping yields field tuples passed to memory_ops.find
    assert dict(FIELD_CHOICES)["Name"] == ("name",)


def test_find_locates_and_misses():
    from chirp_backend import memory_ops

    ok, message = radio_backend.load_image(NAMED_IMAGE)
    assert ok, message
    try:
        ch = _first_nonempty(radio_backend.get_state())
        memory_ops.update_channel(ch, {"name": "FINDME"})
        ok, _msg, affected = memory_ops.find("FINDME", None, ("name",))
        assert ok and affected == [ch]
        # find-next from just after the match wraps back to the only match
        ok2, _msg2, aff2 = memory_ops.find("FINDME", ch + 1, ("name",))
        assert ok2 and aff2 == [ch]
        # a miss
        assert not memory_ops.find("NO_SUCH_TEXT_XYZ", None, ("name",))[0]
    finally:
        radio_backend.unload()


def test_paging_controls_present(loaded_radio):
    out = views.render_channels(1)
    assert 'aria-label="Channel pages"' in out
    assert 'id="page-status"' in out
    assert 'id="goto-input"' in out
    # BF-888 has 16 channels (< PAGE_SIZE): one page, both nav buttons disabled.
    assert out.count('scope="row"') == 16
    assert "page 1 of 1" in out


def test_views_honor_explicit_page_size(loaded_radio):
    # BF-888 has 16 channels (bounds 1..16).
    assert views.total_pages(page_size=5) == 4  # ceil(16/5)
    assert views.page_range(1, page_size=5) == (1, 5)
    assert views.page_for_channel(11, page_size=5) == 3
    assert views.render_channels(1, page_size=5).count('scope="row"') == 5


def test_paging_math_and_slicing():
    # UV-5R: 128 channels numbered 0..127, PAGE_SIZE 100 -> 2 pages.
    ok, message = radio_backend.load_image(NAMED_IMAGE)
    assert ok, message
    try:
        assert views.channel_total() == 128
        assert views.total_pages() == 2
        assert views.page_for_channel(0) == 1
        assert views.page_for_channel(100) == 2
        assert views.page_for_channel(127) == 2
        assert views.page_range(1) == (0, 99)
        assert views.page_range(2) == (100, 127)

        p1 = views.render_channels(1)
        assert p1.count('scope="row"') == 100
        assert 'id="ch-row-0"' in p1 and 'id="ch-row-100"' not in p1

        p2 = views.render_channels(2)
        assert p2.count('scope="row"') == 28  # channels 100..127
        assert 'id="ch-row-100"' in p2 and 'id="ch-row-0"' not in p2
    finally:
        radio_backend.unload()

    # out-of-range page is clamped, not an error
    radio_backend.load_image(IMAGE)
    try:
        assert views.render_channels(999).count('scope="row"') == 16
    finally:
        radio_backend.unload()


NAMED_IMAGE = os.path.abspath(
    os.path.join(
        os.path.dirname(__file__), "..", "chirp", "tests", "images", "Baofeng_UV-5R.img"
    )
)


def test_set_field_persists_text():
    # BF-888 has no channel names; use a radio that does so the write sticks.
    from chirp_backend import memory_ops

    ok, message = radio_backend.load_image(NAMED_IMAGE)
    assert ok, message
    try:
        state = radio_backend.get_state()
        assert state.features.has_name
        ch = _first_nonempty(state)
        ok, message, affected = memory_ops.set_field(ch, "name", "TEST")
        assert ok, message
        assert affected == [ch]
        assert "TEST" in radio_backend.get_memory(ch).name
    finally:
        radio_backend.unload()


def test_set_field_parses_frequency(loaded_radio):
    from chirp_backend import memory_ops

    ch = _first_nonempty(loaded_radio)
    ok, message, _ = memory_ops.set_field(ch, "freq", "146.520")
    assert ok, message
    assert radio_backend.get_memory(ch).freq == 146_520_000


def test_set_field_rejects_invalid_frequency(loaded_radio):
    from chirp_backend import memory_ops

    ch = _first_nonempty(loaded_radio)
    ok, message, _ = memory_ops.set_field(ch, "freq", "not-a-frequency")
    assert not ok
    assert "Invalid value" in message


def test_set_field_rejects_channel_number(loaded_radio):
    from chirp_backend import memory_ops

    ok, message, _ = memory_ops.set_field(1, "number", "5")
    assert not ok
