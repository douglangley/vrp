"""Explicit cross-radio bank mapping, reporting, persistence, and Undo."""

import os
import shutil

from chirp_backend import bank_ops, memory_ops, migration
from chirp_backend import radio as radio_backend


IMAGES = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "chirp", "tests", "images")
)
IC2200 = os.path.join(IMAGES, "Icom_IC-2200H.img")
IC2720 = os.path.join(IMAGES, "Icom_IC-2720H.img")
BF_F8HP_PRO = os.path.join(IMAGES, "Baofeng_BF-F8HP-PRO.img")
FT7800 = os.path.join(IMAGES, "Yaesu_FT-7800_7900.img")


def teardown_function(_function):
    radio_backend.unload()


def _source(path):
    source, message = radio_backend.open_image_as_source(path)
    assert source is not None, message
    return source


def _membership_indexes(radio, number):
    model = bank_ops.bank_model_for(radio)
    return [
        bank.get_index()
        for bank in model.get_memory_mappings(radio.get_memory(number))
    ]


def test_batch_captures_only_explicit_source_bank_metadata():
    source = _source(IC2200)

    batch = migration.batch_from_radio(source, numbers=[2, 5])

    assert batch.source_bank_memberships[2] == (0,)
    assert batch.source_bank_memberships[5] == ()
    used = migration.used_source_banks(batch)
    assert [(bank.index, bank.name, bank.member_count) for bank in used] == [
        ("A", "BANK-A", 1)
    ]
    assert not batch.bank_read_errors


def test_name_suggestions_are_unique_and_position_mapping_is_explicit():
    source = _source(IC2200)
    target = _source(IC2720)
    batch = migration.batch_from_radio(source, numbers=[2])
    used = migration.used_source_banks(batch)
    target_banks = bank_ops.describe_banks(target).banks

    assert bank_ops.suggest_name_mapping(used, target_banks) == {0: "A"}
    assert bank_ops.suggest_position_mapping(used, target_banks) == {0: "A"}

    duplicate_targets = (
        bank_ops.BankDescriptor(0, "X", "BANK-A", "Bank X: BANK-A"),
        bank_ops.BankDescriptor(1, "Y", "BANK-A", "Bank Y: BANK-A"),
    )
    assert bank_ops.suggest_name_mapping(used, duplicate_targets) == {}


def test_explicit_mapping_replaces_destination_membership_and_reports_it():
    source = _source(IC2200)
    target = _source(IC2720)
    batch = migration.batch_from_radio(source, numbers=[2])
    assert _membership_indexes(target, 9) == []

    report = migration.apply_batch(
        target, batch, destination=9, bank_mapping={0: "B"}
    )

    assert report.imported == 1
    assert report.bank_updated == 1
    assert report.bank_failed == 0
    assert _membership_indexes(target, 9) == ["B"]
    assert "banks applied to 1 channel" in report.summary()


def test_no_bank_plan_leaves_existing_destination_membership_untouched():
    source = _source(IC2200)
    target = _source(IC2720)
    batch = migration.batch_from_radio(source, numbers=[5])
    assert _membership_indexes(target, 0) == ["A"]

    report = migration.apply_batch(target, batch, destination=0)

    assert report.imported == 1
    assert report.bank_updated == 0
    assert _membership_indexes(target, 0) == ["A"]


def test_confirmed_empty_mapping_clears_destination_memberships():
    source = _source(IC2200)
    target = _source(IC2720)
    batch = migration.batch_from_radio(source, numbers=[2])
    assert _membership_indexes(target, 0) == ["A"]

    report = migration.apply_batch(
        target, batch, destination=0, bank_mapping={}
    )

    assert report.imported == 1
    assert report.bank_updated == 1
    assert _membership_indexes(target, 0) == []


def test_fixed_destination_bank_is_a_warning_not_a_memory_failure():
    source = _source(IC2200)
    target = _source(BF_F8HP_PRO)
    batch = migration.batch_from_radio(source, numbers=[2])

    report = migration.apply_batch(
        target, batch, destination=1, bank_mapping={0: 1}
    )

    assert report.imported == 1
    assert report.bank_failed == 1
    assert report.failed == 0
    assert "fixed banks" in report.details_text()


def test_destination_that_cannot_hold_all_mapped_banks_rolls_back():
    source = _source(FT7800)
    target = _source(IC2720)
    batch = migration.batch_from_radio(source, numbers=[1])
    assert batch.source_bank_memberships[1] == (0, 1)
    assert _membership_indexes(target, 9) == []

    report = migration.apply_batch(
        target,
        batch,
        destination=9,
        bank_mapping={0: "A", 1: "B"},
    )

    assert report.imported == 1
    assert report.bank_failed == 1
    assert _membership_indexes(target, 9) == []
    assert "original memberships restored" in report.details_text()


def test_real_multi_membership_destination_receives_all_explicit_mappings():
    source = _source(FT7800)
    target = _source(FT7800)
    batch = migration.batch_from_radio(source, numbers=[1])

    report = migration.apply_batch(
        target,
        batch,
        destination=20,
        bank_mapping={0: "0", 1: "1"},
    )

    assert report.imported == 1
    assert report.bank_updated == 1
    assert set(_membership_indexes(target, 20)) == {"0", "1"}


def test_driver_failure_rolls_bank_membership_back(monkeypatch):
    target = _source(IC2720)
    model = bank_ops.bank_model_for(target)
    model_class = type(model)
    original_add = model_class.add_memory_to_mapping
    assert _membership_indexes(target, 0) == ["A"]

    def fail_bank_b(self, memory, bank):
        if bank.get_index() == "B":
            raise RuntimeError("bank is full")
        return original_add(self, memory, bank)

    monkeypatch.setattr(model_class, "add_memory_to_mapping", fail_bank_b)

    ok, message, changed = bank_ops.replace_bank_memberships(
        target, 0, ["B"]
    )

    assert not ok
    assert not changed
    assert "original memberships restored" in message
    assert _membership_indexes(target, 0) == ["A"]


def test_imported_memory_and_banks_share_undo_redo_and_save(tmp_path):
    working = tmp_path / "IC-2720H.img"
    shutil.copyfile(IC2720, working)
    ok, message = radio_backend.load_image(str(working))
    assert ok, message
    target = radio_backend.get_state().radio
    source = _source(IC2200)
    batch = migration.batch_from_radio(source, numbers=[2])
    before = target.get_memory(9).dupe()
    assert _membership_indexes(target, 9) == []

    ok, message, affected, report = memory_ops.apply_migration_batch(
        batch, 9, overwrite=True, bank_mapping={0: "B"}
    )

    assert ok, report.details_text()
    assert affected == [9]
    assert _membership_indexes(target, 9) == ["B"]

    manager = radio_backend.get_undo_manager()
    manager.undo()
    assert target.get_memory(9).freq == before.freq
    assert _membership_indexes(target, 9) == []

    manager.redo()
    assert target.get_memory(9).freq == source.get_memory(2).freq
    assert _membership_indexes(target, 9) == ["B"]

    ok, message = radio_backend.save_image()
    assert ok, message
    radio_backend.unload()
    ok, message = radio_backend.load_image(str(working))
    assert ok, message
    reopened = radio_backend.get_state().radio
    assert _membership_indexes(reopened, 9) == ["B"]


def test_existing_bank_editor_changes_are_now_undoable():
    ok, message = radio_backend.load_image(IC2720)
    assert ok, message
    radio = radio_backend.get_state().radio
    assert _membership_indexes(radio, 0) == ["A"]

    ok, message, affected = bank_ops.apply_bank_changes(0, ["B"])

    assert ok, message
    assert affected == [0]
    assert _membership_indexes(radio, 0) == ["B"]
    manager = radio_backend.get_undo_manager()
    manager.undo()
    assert _membership_indexes(radio, 0) == ["A"]
    manager.redo()
    assert _membership_indexes(radio, 0) == ["B"]


def test_real_multi_membership_is_not_hidden_by_driver_class_name():
    ok, message = radio_backend.load_image(FT7800)
    assert ok, message

    state = bank_ops.get_bank_state(1)

    assert state["ok"]
    assert state["member_indexes"] == {"0", "1"}
    assert state["mode"] == "multi"
