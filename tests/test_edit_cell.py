"""Tests for the single-cell editor (EditCellDialog) and the grid's
cursor-to-cell mapping (ChannelGrid.focused_cell). Skip without a GUI."""

import os

import pytest

from chirp_backend import radio as radio_backend

wx = pytest.importorskip("wx")

IMAGE = os.path.abspath(
    os.path.join(
        os.path.dirname(__file__), "..", "chirp", "tests", "images",
        "Baofeng_UV-5R.img",
    )
)


@pytest.fixture
def app():
    try:
        a = wx.App()
    except Exception:  # noqa: BLE001 — headless CI
        pytest.skip("no GUI/display available")
    yield a
    a.Destroy()


def _col(name):
    from chirp_backend.col_defs import build_column_defs

    cols = build_column_defs(radio_backend.get_state().features)
    return next(c for c in cols if c.name == name)


def test_edit_cell_dialog_text_value_round_trips(app):
    from vrp.edit_dialog import EditCellDialog

    radio_backend.load_image(IMAGE)
    try:
        frame = wx.Frame(None)
        dlg = EditCellDialog(frame, 2, radio_backend.get_memory(2), _col("name"))
        dlg._ctrl.SetValue("HELLO")
        assert dlg.get_value() == "HELLO"
        dlg.Destroy()
        frame.Destroy()
    finally:
        radio_backend.unload()


def test_edit_cell_dialog_choice_value_round_trips(app):
    from vrp.edit_dialog import EditCellDialog

    radio_backend.load_image(IMAGE)
    try:
        frame = wx.Frame(None)
        col = _col("mode")
        dlg = EditCellDialog(frame, 2, radio_backend.get_memory(2), col)
        dlg._ctrl.SetStringSelection(col.choices[0])
        assert dlg.get_value() == col.choices[0]
        dlg.Destroy()
        frame.Destroy()
    finally:
        radio_backend.unload()


def test_tmode_blank_choice_shown_as_none_round_trips(app):
    from vrp.edit_dialog import EditCellDialog

    radio_backend.load_image(IMAGE)
    try:
        frame = wx.Frame(None)
        col = _col("tmode")
        # No duplicate blank entry, and the empty option reads as "None".
        assert col.choices.count("") == 1
        # A channel with no tone (tmode "") shows the "None" label, not a blank.
        mem = radio_backend.get_memory(2)
        mem.tmode = ""
        dlg = EditCellDialog(frame, 2, mem, col)
        labels = [dlg._ctrl.GetString(i) for i in range(dlg._ctrl.GetCount())]
        assert "None" in labels and "" not in labels
        assert dlg._ctrl.GetStringSelection() == "None"
        # ...but the value read back out is the empty string CHIRP expects.
        assert dlg.get_value() == ""
        dlg.Destroy()
        frame.Destroy()
    finally:
        radio_backend.unload()


def test_duplex_choices_shown_as_full_words_round_trip(app):
    from vrp.edit_dialog import make_field_control, control_value

    radio_backend.load_image(IMAGE)
    try:
        frame = wx.Frame(None)
        col = _col("duplex")
        assert col.choices.count("") == 1  # no duplicate blank
        # Each raw value shows a spoken word but reads back as the raw value.
        expected = {"": "Simplex", "-": "Minus", "+": "Plus",
                    "split": "Split", "off": "Off"}
        for raw, label in expected.items():
            if raw not in col.choices:
                continue
            ctrl = make_field_control(frame, col, raw)
            assert ctrl.GetStringSelection() == label
            assert control_value(ctrl) == raw
        labels = [_label for _label in expected.values()]
        ctrl = make_field_control(frame, col, "")
        shown = [ctrl.GetString(i) for i in range(ctrl.GetCount())]
        assert "" not in shown and set(shown) <= set(labels)
        frame.Destroy()
    finally:
        radio_backend.unload()


def test_skip_choices_use_valid_skips_and_full_words(app):
    from vrp.edit_dialog import make_field_control, control_value

    radio_backend.load_image(IMAGE)
    try:
        frame = wx.Frame(None)
        f = radio_backend.get_state().features
        col = _col("skip")
        # Only the radio's supported skip values are offered (CHIRP parity).
        assert col.choices == [""] + [s for s in f.valid_skips if s != ""]
        for raw, label in {"": "None", "S": "Skip", "P": "Priority scan"}.items():
            if raw not in col.choices:
                continue
            ctrl = make_field_control(frame, col, raw)
            assert ctrl.GetStringSelection() == label
            assert control_value(ctrl) == raw
        frame.Destroy()
    finally:
        radio_backend.unload()


def test_edit_dialog_suggests_offset_on_frequency_change(app):
    from vrp.edit_dialog import EditChannelDialog, control_value

    radio_backend.load_image(IMAGE)
    try:
        frame = wx.Frame(None)
        feats = radio_backend.get_state().features
        mem = radio_backend.get_memory(2)

        def fill(freq, preset=None):
            dlg = EditChannelDialog(frame, 2, mem, feats)
            offc = dlg._controls["offset"][0]
            if preset is not None:
                offc.SetValue(preset)
                dlg._last_freq = "force-change"
            dlg._controls["freq"][0].SetValue(freq)
            ev = wx.FocusEvent(wx.wxEVT_KILL_FOCUS)
            dlg._on_frequency_changed(ev)
            value = control_value(offc)
            status = dlg._status.GetLabel()
            dlg.Destroy()
            return value, status

        assert fill("146.94") == ("0.6", "Suggested offset 0.6 MHz"
                                  " — set Duplex to plus or minus to use it.")
        assert fill("442.5")[0] == "5"          # 70 cm -> 5 MHz
        assert fill("146.52")[0] == "0.6"       # simplex still suggests
        assert fill("7.25") == ("", "")         # HF -> no suggestion, no announce
        assert fill("146.94", preset="1.0")[0] == "1.0"  # existing offset kept
        frame.Destroy()
    finally:
        radio_backend.unload()


def test_band_defaults_applied_only_when_enabled(app):
    from vrp.edit_dialog import EditChannelDialog, control_value

    radio_backend.load_image(IMAGE)
    try:
        frame = wx.Frame(None)
        feats = radio_backend.get_state().features

        def change_freq(apply):
            mem = radio_backend.get_memory(2)
            mem.empty = False
            mem.freq, mem.duplex, mem.offset, mem.mode = 0, "", 0, "NFM"
            dlg = EditChannelDialog(frame, 2, mem, feats,
                                    apply_band_defaults=apply)
            dlg._controls["freq"][0].SetValue("145.30")  # NA 2 m FM sub-band
            dlg._on_frequency_changed(wx.FocusEvent(wx.wxEVT_KILL_FOCUS))
            mode = control_value(dlg._controls["mode"][0])
            offset = control_value(dlg._controls["offset"][0])
            status = dlg._status.GetLabel()
            dlg.Destroy()
            return mode, offset, status

        # Off: only the offset suggestion runs; mode left alone.
        mode, offset, status = change_freq(False)
        assert offset == "0.6" and mode == "NFM"
        assert "Band defaults" not in status

        # On: mode also set to the band default, and announced.
        mode, offset, status = change_freq(True)
        assert offset == "0.6" and mode == "FM"
        assert "Band defaults: mode FM" in status
        frame.Destroy()
    finally:
        radio_backend.unload()


def test_edit_cell_offset_prefills_band_suggestion(app):
    from vrp.edit_dialog import EditCellDialog, control_value

    radio_backend.load_image(IMAGE)
    try:
        frame = wx.Frame(None)
        offcol = _col("offset")

        def open_offset(freq_hz, duplex="", offset=0):
            mem = radio_backend.get_memory(2)
            mem.empty = False
            mem.freq, mem.duplex, mem.offset = freq_hz, duplex, offset
            dlg = EditCellDialog(frame, 2, mem, offcol)
            value = control_value(dlg._ctrl)
            status = dlg._status.GetLabel()
            dlg.Destroy()
            return value, status

        # Blank offset on a 2 m channel -> pre-filled 0.6 and announced.
        value, status = open_offset(146_940_000)
        assert value == "0.6"
        assert status.startswith("Suggested offset 0.6 MHz")
        # 70 cm -> 5; HF -> nothing.
        assert open_offset(442_500_000)[0] == "5"
        assert open_offset(7_250_000) == ("", "")
        # An offset already set is left alone (no overwrite, no announce).
        assert open_offset(146_940_000, duplex="-", offset=1_000_000) == ("1", "")
        frame.Destroy()
    finally:
        radio_backend.unload()


def test_cell_display_matches_model_text(app):
    from vrp.native.channel_grid import ChannelGrid
    from vrp.native import grid_model

    radio_backend.load_image(IMAGE)
    try:
        frame = wx.Frame(None)
        grid = ChannelGrid(frame)
        grid.set_state(radio_backend.get_state())
        assert grid.cell_display(2, "number") == "2"
        idx = grid_model.number_to_index(grid._model.rows, 2)
        assert grid.cell_display(2, "name") == grid_model.cell_text(
            grid._model.rows[idx], "name"
        )
        assert grid.cell_display(99999, "name") == ""  # unknown channel
        frame.Destroy()
    finally:
        radio_backend.unload()


def test_focused_cell_maps_cursor_to_channel_and_column(app):
    from vrp.native.channel_grid import ChannelGrid

    radio_backend.load_image(IMAGE)
    try:
        frame = wx.Frame(None)
        # cell_announce (even a no-op) enables VRP's column-locked cursor.
        grid = ChannelGrid(frame, cell_announce=lambda t: None)
        grid.set_state(radio_backend.get_state())
        grid.focus_channel(2)
        n, col = grid.focused_cell()
        assert (n, col) == (2, "number")  # cursor starts on the row-header column
        for _ in range(2):  # Right, Right -> column index 2 (library owns arrows)
            ev = wx.KeyEvent(wx.wxEVT_KEY_DOWN)
            ev.SetKeyCode(wx.WXK_RIGHT)
            grid._grid._on_key_down(ev)
        n2, col2 = grid.focused_cell()
        assert n2 == 2
        assert col2 == grid._model.columns()[2].name
        frame.Destroy()
    finally:
        radio_backend.unload()


def _press(grid, keycode):
    # The four arrows are owned by the library's cell cursor (grid._grid),
    # which VRP binds after — so drive the library handler directly.
    ev = wx.KeyEvent(wx.wxEVT_KEY_DOWN)
    ev.SetKeyCode(keycode)
    grid._grid._on_key_down(ev)


def test_down_arrow_is_column_locked(app):
    """Arrowing DOWN moves to the next row but stays in the same column (the
    column-locked cursor), and speaks concise "Channel N, <cell>" text — not the
    whole row."""
    from vrp.native.channel_grid import ChannelGrid

    radio_backend.load_image(IMAGE)
    try:
        frame = wx.Frame(None)
        spoken = []
        grid = ChannelGrid(frame, cell_announce=spoken.append)
        grid.set_state(radio_backend.get_state())
        grid.focus_channel(1)

        _press(grid, wx.WXK_RIGHT)
        _press(grid, wx.WXK_RIGHT)          # into column index 2
        col_after_right = grid.focused_cell()[1]
        _press(grid, wx.WXK_DOWN)           # next row, SAME column

        n, col = grid.focused_cell()
        assert n == 2                        # moved to the next channel
        assert col == col_after_right        # column unchanged (locked)
        # The down-arrow announcement leads with the row header, not the column
        # name, and doesn't enumerate the whole row.
        assert spoken[-1].startswith("Channel 2")
        frame.Destroy()
    finally:
        radio_backend.unload()
