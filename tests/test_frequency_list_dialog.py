"""GUI tests for the frequency-list chooser (vrp/query_dialogs.FrequencyListDialog).

Skips without a display. No files needed — the dialog is fed a plain list of
(display_name, path) tuples; opening/importing the CSV happens in the caller."""

import pytest

wx = pytest.importorskip("wx")

from vrp.query_dialogs import FrequencyListDialog  # noqa: E402

SAMPLE = [
    ("US NOAA Weather Alert", "/x/US NOAA Weather Alert.csv"),
    ("US Marine VHF Channels", "/x/US Marine VHF Channels.csv"),
    ("US MURS Channels", "/x/US MURS Channels.csv"),
    ("EU LPD and PMR Channels", "/x/EU LPD and PMR Channels.csv"),
]


@pytest.fixture
def app():
    try:
        a = wx.App()
    except Exception:  # noqa: BLE001 — headless CI
        pytest.skip("no GUI/display available")
    yield a
    a.Destroy()


def test_list_populated_and_default_selection(app):
    dlg = FrequencyListDialog(None, SAMPLE)
    try:
        assert dlg.list.GetCount() == len(SAMPLE)
        # First row selected so the screen reader announces something.
        name, path = dlg.get_selection()
        assert (name, path) == SAMPLE[0]
    finally:
        dlg.Destroy()


def test_filter_narrows_list(app):
    dlg = FrequencyListDialog(None, SAMPLE)
    try:
        dlg.filter.SetValue("murs")
        dlg._apply_filter()
        assert dlg.list.GetCount() == 1
        name, _path = dlg.get_selection()
        assert name == "US MURS Channels"
    finally:
        dlg.Destroy()


def test_filter_no_match_disables_import(app):
    dlg = FrequencyListDialog(None, SAMPLE)
    try:
        dlg.filter.SetValue("zzz-nothing")
        dlg._apply_filter()
        assert dlg.list.GetCount() == 0
        assert dlg.get_selection() is None
        assert not dlg.FindWindowById(wx.ID_OK).IsEnabled()
    finally:
        dlg.Destroy()


def test_import_button_labelled(app):
    dlg = FrequencyListDialog(None, SAMPLE)
    try:
        assert dlg.FindWindowById(wx.ID_OK).GetLabel() == "Import"
    finally:
        dlg.Destroy()


def test_details_button_only_with_describe_fn(app, monkeypatch):
    without = FrequencyListDialog(None, SAMPLE)
    try:
        assert not hasattr(without, "details_btn")
    finally:
        without.Destroy()

    seen = {}

    def describe(path):
        seen["path"] = path
        return "10 channel(s)."

    # Stub InfoDialog so exercising _on_details verifies the describe_fn wiring
    # WITHOUT actually opening a modal window on every test run.
    import vrp.info_dialog as info_mod

    class _FakeInfo:
        def __init__(self, parent, title, text, **kwargs):
            seen["title"] = title
            seen["text"] = text

        def ShowModal(self):
            return 0

        def Destroy(self):
            pass

    monkeypatch.setattr(info_mod, "InfoDialog", _FakeInfo)

    withfn = FrequencyListDialog(None, SAMPLE, describe_fn=describe)
    try:
        assert hasattr(withfn, "details_btn")
        withfn._on_details()  # uses the current selection (row 0); no real dialog
        assert seen["path"] == SAMPLE[0][1]  # describe_fn got the selected path
        assert seen["text"] == "10 channel(s)."  # its output reached the InfoDialog
    finally:
        withfn.Destroy()


def test_filter_and_list_labels_created_before_controls(app):
    # wxMSW names a native control from the StaticText created just before it;
    # assert each control's preceding sibling is its own label (else NVDA reads
    # fields off by one). Same guard as the RepeaterBook dialog tests.
    dlg = FrequencyListDialog(None, SAMPLE)
    try:
        kids = list(dlg.GetChildren())

        def label_before(control, expected):
            prev = kids[kids.index(control) - 1]
            assert isinstance(prev, wx.StaticText)
            assert prev.GetLabel() == expected

        label_before(dlg.filter, "Filter:")
        label_before(dlg.list, "Frequency list:")
    finally:
        dlg.Destroy()
