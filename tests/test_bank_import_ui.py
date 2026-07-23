"""MainWindow wiring for explicit cross-radio bank mapping."""

import os

import pytest

from chirp_backend import bank_ops, migration
from chirp_backend import radio as radio_backend

wx = pytest.importorskip("wx")


IMAGES = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "chirp", "tests", "images")
)
IC2200 = os.path.join(IMAGES, "Icom_IC-2200H.img")
IC2720 = os.path.join(IMAGES, "Icom_IC-2720H.img")
BF_F8HP_PRO = os.path.join(IMAGES, "Baofeng_BF-F8HP-PRO.img")
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
    ok, message = radio_backend.load_image(IC2720)
    assert ok, message
    window._load_into_grid()
    try:
        yield window
    finally:
        radio_backend.unload()
        window.Destroy()


def _source(path=IC2200):
    source, message = radio_backend.open_image_as_source(path)
    assert source is not None, message
    return source


def _memberships(number):
    radio = radio_backend.get_state().radio
    model = bank_ops.bank_model_for(radio)
    return [
        bank.get_index()
        for bank in model.get_memory_mappings(radio.get_memory(number))
    ]


class _DestinationAtNine:
    def __init__(self, *_args, **_kwargs):
        pass

    def ShowModal(self):
        return wx.ID_OK

    def get_destination(self):
        return 9

    def get_overwrite(self):
        return True

    def Destroy(self):
        pass


def test_file_import_applies_only_the_confirmed_bank_mapping(
    win, monkeypatch
):
    source = _source()
    batch = migration.batch_from_radio(source, numbers=[2])
    monkeypatch.setattr(
        "vrp.query_dialogs.ImportDestinationDialog", _DestinationAtNine
    )
    seen = []

    def choose(candidate):
        seen.extend(migration.used_source_banks(candidate))
        return True, {0: "B"}

    monkeypatch.setattr(win, "_choose_bank_mapping", choose)

    win._import_batch(batch, 1)

    assert [(bank.index, bank.member_count) for bank in seen] == [("A", 1)]
    assert _memberships(9) == ["B"]


def test_canceling_bank_mapping_prevents_channel_and_bank_write(
    win, monkeypatch
):
    source = _source()
    batch = migration.batch_from_radio(source, numbers=[2])
    before = radio_backend.get_memory(9).dupe()
    before_banks = _memberships(9)
    monkeypatch.setattr(
        "vrp.query_dialogs.ImportDestinationDialog", _DestinationAtNine
    )
    monkeypatch.setattr(win, "_choose_bank_mapping", lambda _batch: (False, None))

    win._import_batch(batch, 1)

    after = radio_backend.get_memory(9)
    assert after.freq == before.freq
    assert _memberships(9) == before_banks


def test_fixed_destination_requires_channel_only_confirmation(win, monkeypatch):
    ok, message = radio_backend.load_image(BF_F8HP_PRO)
    assert ok, message
    win._load_into_grid()
    batch = migration.batch_from_radio(_source(), numbers=[2])
    reasons = []
    monkeypatch.setattr(
        win,
        "_confirm_import_without_banks",
        lambda reason: reasons.append(reason) or True,
    )

    proceed, mapping = win._choose_bank_mapping(batch)

    assert proceed
    assert mapping is None
    assert reasons and "fixed banks" in reasons[0]


def test_destination_without_banks_requires_channel_only_confirmation(
    win, monkeypatch
):
    ok, message = radio_backend.load_image(UV5R)
    assert ok, message
    win._load_into_grid()
    batch = migration.batch_from_radio(_source(), numbers=[2])
    reasons = []
    monkeypatch.setattr(
        win,
        "_confirm_import_without_banks",
        lambda reason: reasons.append(reason) or True,
    )

    proceed, mapping = win._choose_bank_mapping(batch)

    assert proceed
    assert mapping is None
    assert reasons and "no banks" in reasons[0]


def test_unbanked_source_explicitly_chooses_clear_or_keep(win, monkeypatch):
    batch = migration.batch_from_radio(_source(), numbers=[5])
    assert batch.source_banks
    assert batch.source_bank_memberships[5] == ()
    monkeypatch.setattr(
        win, "_choose_unbanked_source_policy", lambda: (True, {})
    )

    proceed, mapping = win._choose_bank_mapping(batch)

    assert proceed
    assert mapping == {}


def test_cross_image_clipboard_keeps_source_bank_metadata(win, monkeypatch):
    ok, message = radio_backend.load_image(IC2200)
    assert ok, message
    win._load_into_grid()
    win.grid.select_channels([2])
    win.grid.focus_channel(2)
    win.on_copy()
    assert win._clipboard.migration_batch.source_bank_memberships[2] == (0,)

    ok, message = radio_backend.load_image(IC2720)
    assert ok, message
    win._load_into_grid()
    win.grid.focus_channel(9)
    monkeypatch.setattr(win, "_ask_migration_conflict", lambda *args: True)
    monkeypatch.setattr(
        win, "_choose_bank_mapping", lambda _batch: (True, {0: "B"})
    )

    win.on_paste()

    assert _memberships(9) == ["B"]
