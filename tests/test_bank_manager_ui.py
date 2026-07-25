"""MainWindow wiring for Radio ▸ Manage banks…."""

import os

import pytest

from chirp_backend import bank_ops
from chirp_backend import radio as radio_backend

wx = pytest.importorskip("wx")


IMAGES = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "chirp", "tests", "images")
)
ID880H = os.path.join(IMAGES, "Icom_ID-880H.img")
UV5R = os.path.join(IMAGES, "Baofeng_UV-5R.img")


@pytest.fixture
def app():
    try:
        instance = wx.App()
    except Exception:  # noqa: BLE001 - headless CI
        pytest.skip("no GUI/display available")
    yield instance
    instance.Destroy()


@pytest.fixture
def win(app):
    from vrp.native.main_window import MainWindow

    window = MainWindow()
    ok, message = radio_backend.load_image(ID880H)
    assert ok, message
    window._load_into_grid()
    try:
        yield window
    finally:
        radio_backend.unload()
        window.Destroy()


def test_manage_banks_is_a_radio_gated_command(win):
    assert "manage_banks" in win._radio_gated_keys


def test_overview_reads_catalog_and_channels_together(win):
    catalog, channels = win._read_bank_overview()

    assert catalog.renameable is True
    assert set(channels) == set(range(len(catalog.banks)))


def test_manage_banks_reports_a_radio_without_banks(app, monkeypatch):
    from vrp.native.main_window import MainWindow

    window = MainWindow()
    ok, message = radio_backend.load_image(UV5R)
    assert ok, message
    window._load_into_grid()
    seen = {}
    monkeypatch.setattr(
        wx, "MessageBox", lambda *a, **k: seen.setdefault("message", a[0])
    )
    try:
        window.on_manage_banks()
        assert "no banks" in seen["message"]
    finally:
        radio_backend.unload()
        window.Destroy()


def test_rename_through_the_window_updates_the_dialog_and_announces(win, monkeypatch):
    from vrp.bank_manager_dialog import BankManagerDialog

    catalog, channels = win._read_bank_overview()
    dlg = BankManagerDialog(win, catalog, channels)
    dlg.list.SetSelection(0)
    dlg._update_buttons()

    class _Prompt:
        def __init__(self, *a, **k):
            pass

        def ShowModal(self):
            return wx.ID_OK

        def GetValue(self):
            return "Harbor"

        def Destroy(self):
            pass

    monkeypatch.setattr(wx, "TextEntryDialog", _Prompt)
    spoken = []
    monkeypatch.setattr(
        win.announce, "announce", lambda text, **k: spoken.append(text)
    )
    try:
        win._rename_bank(dlg)

        assert any("Harbor" in text for text in spoken)
        assert dlg.get_bank().name == "Harbor"
        radio = radio_backend.get_state().radio
        assert bank_ops.describe_banks(radio).banks[0].name == "Harbor"
    finally:
        dlg.Destroy()


def test_rename_failure_is_announced_and_leaves_the_name_alone(win, monkeypatch):
    from vrp.bank_manager_dialog import BankManagerDialog

    catalog, channels = win._read_bank_overview()
    before = catalog.banks[0].name
    dlg = BankManagerDialog(win, catalog, channels)
    dlg.list.SetSelection(0)

    class _Prompt:
        def __init__(self, *a, **k):
            pass

        def ShowModal(self):
            return wx.ID_OK

        def GetValue(self):
            return "Blocked"

        def Destroy(self):
            pass

    monkeypatch.setattr(wx, "TextEntryDialog", _Prompt)
    monkeypatch.setattr(bank_ops, "capture_bank_names", lambda _radio: None)
    monkeypatch.setattr(wx, "MessageBox", lambda *a, **k: None)
    spoken = []
    monkeypatch.setattr(
        win.announce, "announce", lambda text, **k: spoken.append(text)
    )
    try:
        win._rename_bank(dlg)

        assert any("Could not save undo state" in text for text in spoken)
        radio = radio_backend.get_state().radio
        assert bank_ops.describe_banks(radio).banks[0].name == before
    finally:
        dlg.Destroy()


def test_cancelling_the_prompt_writes_nothing(win, monkeypatch):
    from vrp.bank_manager_dialog import BankManagerDialog

    catalog, channels = win._read_bank_overview()
    before = catalog.banks[0].name
    dlg = BankManagerDialog(win, catalog, channels)
    dlg.list.SetSelection(0)

    class _Prompt:
        def __init__(self, *a, **k):
            pass

        def ShowModal(self):
            return wx.ID_CANCEL

        def GetValue(self):
            return "Ignored"

        def Destroy(self):
            pass

    monkeypatch.setattr(wx, "TextEntryDialog", _Prompt)
    try:
        win._rename_bank(dlg)

        radio = radio_backend.get_state().radio
        assert bank_ops.describe_banks(radio).banks[0].name == before
        assert radio_backend.get_state().is_modified is False
    finally:
        dlg.Destroy()


def test_channel_banks_dialog_offers_the_manage_cross_link(win):
    from vrp.bank_dialog import ChannelBanksDialog

    state = bank_ops.get_bank_state(0)
    assert state["ok"], state.get("message")
    dlg = ChannelBanksDialog(win, state)
    try:
        assert dlg.manage_requested is False
        dlg._on_manage(None)
        assert dlg.manage_requested is True
    finally:
        dlg.Destroy()
