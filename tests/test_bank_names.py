"""Bank renaming: capability, verified writes, Undo/Redo, and persistence.

Every case runs against a real pinned CHIRP driver. Renaming is confirmed by
rereading the bank, because ``chirp_common.NamedBank`` supplies a base
``set_name`` that only assigns an attribute — the class hierarchy is not
evidence that a name reached the image.
"""

import os
import shutil

import pytest

from chirp_backend import bank_ops
from chirp_backend import radio as radio_backend


IMAGES = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "chirp", "tests", "images")
)
ID880H = os.path.join(IMAGES, "Icom_ID-880H.img")       # renameable, 6-char names
IC2720 = os.path.join(IMAGES, "Icom_IC-2720H.img")      # mutable, not renameable
BF_F8HP_PRO = os.path.join(IMAGES, "Baofeng_BF-F8HP-PRO.img")  # fixed, not renameable
RT920 = os.path.join(IMAGES, "Radtel_RT-920.img")       # fixed banks, renameable names
TK890 = os.path.join(IMAGES, "Kenwood_TK-890.img")      # set_name exists, stores nothing


def teardown_function(_function):
    radio_backend.unload()


def _load(path):
    ok, message = radio_backend.load_image(path)
    assert ok, message
    return radio_backend.get_state().radio


def _name(radio, position=0):
    return bank_ops.describe_banks(radio).banks[position].name


def test_catalog_reports_rename_capability_per_bank_and_overall():
    radio = _load(ID880H)

    catalog = bank_ops.describe_banks(radio)

    assert catalog.renameable is True
    assert all(bank.renameable for bank in catalog.banks)


def test_catalog_reports_no_rename_capability_on_a_plain_bank_driver():
    radio = _load(IC2720)

    catalog = bank_ops.describe_banks(radio)

    assert catalog.available and catalog.mutable
    assert catalog.renameable is False
    assert not any(bank.renameable for bank in catalog.banks)


def test_fixed_membership_does_not_imply_unnameable_banks():
    """Radtel RT-920 pins membership to channel position but names are writable."""
    radio = _load(RT920)

    catalog = bank_ops.describe_banks(radio)

    assert catalog.mode == "fixed"
    assert catalog.mutable is False
    assert catalog.renameable is True

    ok, message, stored = bank_ops.rename_bank(0, "Travel")

    assert ok, message
    assert stored
    assert _name(radio) == stored


def test_rename_is_confirmed_by_rereading_the_bank():
    radio = _load(ID880H)
    before = _name(radio)

    ok, message, stored = bank_ops.rename_bank(0, "Hills")

    assert ok, message
    assert stored == "Hills"
    assert _name(radio) == "Hills"
    assert stored != before
    assert radio_backend.get_state().is_modified is True


def test_driver_truncation_is_reported_rather_than_claimed_verbatim():
    """ID-880H stores 6 characters; the user must hear what was really stored."""
    radio = _load(ID880H)

    ok, message, stored = bank_ops.rename_bank(1, "ABCDEFGHIJKLMNOP")

    assert ok, message
    assert stored == "ABCDEF"
    assert "shortened by the radio" in message
    assert _name(radio, 1) == "ABCDEF"


def test_rename_is_rejected_on_a_driver_without_named_banks():
    radio = _load(IC2720)
    before = _name(radio)

    ok, message, stored = bank_ops.rename_bank(0, "Anything")

    assert not ok
    assert "cannot be renamed" in message
    assert stored == before
    assert _name(radio) == before
    assert radio_backend.get_state().is_modified is False


def test_rename_is_rejected_on_fixed_unnameable_banks():
    radio = _load(BF_F8HP_PRO)
    before = _name(radio)

    ok, message, _stored = bank_ops.rename_bank(0, "Anything")

    assert not ok
    assert "cannot be renamed" in message
    assert _name(radio) == before


def test_out_of_range_position_is_rejected():
    _load(ID880H)

    ok, message, _stored = bank_ops.rename_bank(999, "Nope")

    assert not ok
    assert "no longer available" in message


def test_unchanged_name_reports_success_and_records_no_history():
    radio = _load(ID880H)
    current = _name(radio)
    manager = radio_backend.get_undo_manager()

    ok, message, stored = bank_ops.rename_bank(0, current)

    assert ok
    assert "did not change" in message
    assert stored == current
    assert manager.can_undo() is False
    assert radio_backend.get_state().is_modified is False


def test_rename_undo_and_redo_restore_the_name_without_touching_memories():
    radio = _load(ID880H)
    before = _name(radio)
    channel_before = radio.get_memory(0).dupe()
    manager = radio_backend.get_undo_manager()

    ok, _message, stored = bank_ops.rename_bank(0, "Coast")
    assert ok

    label, numbers = manager.undo()
    assert numbers == []          # a rename writes no memory
    assert "Coast" in label
    assert _name(radio) == before
    assert radio.get_memory(0).freq == channel_before.freq

    manager.redo()
    assert _name(radio) == stored
    assert radio.get_memory(0).freq == channel_before.freq


def test_rename_survives_save_and_reopen(tmp_path):
    working = tmp_path / "ID-880H.img"
    shutil.copyfile(ID880H, working)
    _load(str(working))

    ok, _message, stored = bank_ops.rename_bank(0, "Summit")
    assert ok

    ok, message = radio_backend.save_image()
    assert ok, message
    radio_backend.unload()
    reopened = _load(str(working))

    assert _name(reopened) == stored


def test_capture_and_restore_bank_names_round_trip():
    radio = _load(ID880H)
    snapshot = bank_ops.capture_bank_names(radio)
    assert snapshot is not None

    ok, _message, _stored = bank_ops.rename_bank(0, "Zzz")
    assert ok
    assert _name(radio) != snapshot[0]

    bank_ops.restore_bank_names(radio, snapshot)

    assert _name(radio) == snapshot[0]


def test_restore_rejects_a_snapshot_of_the_wrong_length():
    radio = _load(ID880H)

    with pytest.raises(RuntimeError, match="Bank count changed"):
        bank_ops.restore_bank_names(radio, ("only-one",))


def test_capture_returns_none_when_the_radio_has_no_banks():
    source, message = radio_backend.open_image_as_source(
        os.path.join(IMAGES, "Baofeng_UV-5R.img")
    )
    assert source is not None, message

    assert bank_ops.bank_model_for(source) is None
    assert bank_ops.capture_bank_names(source) is None


def test_driver_that_accepts_but_discards_a_name_is_reported_as_failure():
    """Kenwood TK-890: the real case that makes verify-on-reread mandatory.

    ``MemBank`` exposes a genuine ``set_name``, so a capability check alone says
    "renameable". This pinned image configures ``grp_name_length`` as 0, so the
    driver filters the whole name away and stores nothing. Rereading is the only
    thing that keeps VRP from reporting a rename that never happened.
    """
    radio = _load(TK890)
    assert bank_ops.describe_banks(radio).renameable is True
    before = _name(radio)

    ok, message, stored = bank_ops.rename_bank(0, "Harbor")

    assert not ok
    assert "did not store" in message
    assert stored == before
    assert _name(radio) == before
    assert radio_backend.get_state().is_modified is False


def test_rename_is_fail_closed_when_undo_state_cannot_be_captured(monkeypatch):
    """A rename we could not snapshot is a rename we could not undo."""
    radio = _load(ID880H)
    before = _name(radio)
    monkeypatch.setattr(bank_ops, "capture_bank_names", lambda _radio: None)

    ok, message, stored = bank_ops.rename_bank(0, "Nope")

    assert not ok
    assert "Could not save undo state" in message
    assert stored == before
    assert _name(radio) == before
    assert radio_backend.get_state().is_modified is False
