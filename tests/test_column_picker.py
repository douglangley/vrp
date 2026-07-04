"""Tests for ColumnPickerDialog — F2's macOS "which field?" chooser. Skips
without a GUI/display (it builds real wx controls)."""

import pytest

from chirp_backend.col_defs import ColumnDef

wx = pytest.importorskip("wx")


@pytest.fixture
def app():
    try:
        a = wx.App()
    except Exception:  # noqa: BLE001 — headless CI
        pytest.skip("no GUI/display available")
    yield a
    a.Destroy()


def _cols():
    return [
        ColumnDef(name="freq", label="Frequency"),
        ColumnDef(name="name", label="Name"),
        ColumnDef(name="tmode", label="Tone Mode"),
    ]


def test_lists_every_column_by_label(app):
    from vrp.edit_dialog import ColumnPickerDialog

    frame = wx.Frame(None)
    dlg = ColumnPickerDialog(frame, 5, _cols())
    try:
        assert dlg._listbox.GetCount() == 3
        assert [dlg._listbox.GetString(i) for i in range(3)] == [
            "Frequency", "Name", "Tone Mode"
        ]
    finally:
        dlg.Destroy()
        frame.Destroy()


def test_defaults_to_first_field_selected(app):
    from vrp.edit_dialog import ColumnPickerDialog

    frame = wx.Frame(None)
    dlg = ColumnPickerDialog(frame, 5, _cols())
    try:
        assert dlg._listbox.GetSelection() == 0
        assert dlg.get_column().name == "freq"
    finally:
        dlg.Destroy()
        frame.Destroy()


def test_get_column_follows_selection(app):
    from vrp.edit_dialog import ColumnPickerDialog

    frame = wx.Frame(None)
    dlg = ColumnPickerDialog(frame, 5, _cols())
    try:
        dlg._listbox.SetSelection(2)
        assert dlg.get_column().name == "tmode"
    finally:
        dlg.Destroy()
        frame.Destroy()


class _FakeKey:
    """Minimal stand-in for wx.KeyEvent (setting m_keyCode on a real one doesn't
    stick in this wx build, the same quirk the native key tests hit)."""

    def __init__(self, code):
        self._code = code
        self.skipped = False

    def GetKeyCode(self):  # noqa: N802 (wx API parity)
        return self._code

    def Skip(self):  # noqa: N802
        self.skipped = True


def test_enter_on_list_accepts(app):
    """Return on the focused list ends the dialog with OK (the macOS Cocoa
    fix — a focused ListBox doesn't forward Return to the default button)."""
    from vrp.edit_dialog import ColumnPickerDialog

    frame = wx.Frame(None)
    dlg = ColumnPickerDialog(frame, 5, _cols())
    ended = []
    dlg.EndModal = lambda rc: ended.append(rc)  # capture instead of running modal
    try:
        dlg._on_list_key(_FakeKey(wx.WXK_RETURN))
        assert ended == [wx.ID_OK]  # accepted
    finally:
        dlg.Destroy()
        frame.Destroy()


def test_other_keys_pass_through(app):
    """A non-Enter key is skipped (type-ahead etc. keep working) and does not
    accept the dialog."""
    from vrp.edit_dialog import ColumnPickerDialog

    frame = wx.Frame(None)
    dlg = ColumnPickerDialog(frame, 5, _cols())
    ended = []
    dlg.EndModal = lambda rc: ended.append(rc)
    try:
        ev = _FakeKey(ord("N"))
        dlg._on_list_key(ev)
        assert ended == []
        assert ev.skipped is True
    finally:
        dlg.Destroy()
        frame.Destroy()
