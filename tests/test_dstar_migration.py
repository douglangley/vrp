"""Transactional D-STAR migration across real pinned CHIRP drivers."""

import os
import shutil

from chirp_backend import dstar_ops, memory_ops, migration
from chirp_backend import radio as radio_backend


IMAGES = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "chirp", "tests", "images")
)
IC2200 = os.path.join(IMAGES, "Icom_IC-2200H.img")
IC2820 = os.path.join(IMAGES, "Icom_IC-2820H.img")
ID4100 = os.path.join(IMAGES, "Icom_ID-4100.img")
ICV82 = os.path.join(IMAGES, "Icom_IC-V82.img")
UV5R = os.path.join(IMAGES, "Baofeng_UV-5R.img")


def teardown_function(_function):
    radio_backend.unload()


def _source(path):
    source, message = radio_backend.open_image_as_source(path)
    assert source is not None, message
    return source


def _dv_batch(*memories):
    source = _source(IC2200)
    return migration.batch_from_memories(
        memories,
        [memory.number for memory in memories],
        source.get_features(),
        migration.radio_id(source),
        migration.radio_label(source),
    )


def _custom_dv(source, number, *, freq, suffix):
    memory = source.get_memory(17).dupe()
    memory.number = number
    memory.freq = freq
    memory.name = f"DV{suffix}"
    memory.dv_urcall = f"USER{suffix}"
    memory.dv_rpt1call = f"RPT{suffix} A"
    memory.dv_rpt2call = f"RPT{suffix} G"
    return memory


def test_required_call_lists_are_added_and_reported_for_real_drivers():
    source = _source(IC2200)
    target = _source(ICV82)
    before = dstar_ops.capture_call_lists(target)
    batch = migration.batch_from_radio(source, numbers=[17])

    report = migration.apply_batch(target, batch, destination=10)

    after = dstar_ops.capture_call_lists(target)
    assert report.imported == 1
    assert report.dstar_calls_added == 3
    assert set(dstar_ops.added_calls(before, after)) == {
        "UR2",
        "W4WBC C",
        "W4WBC G",
    }
    assert "3 D-STAR call(s) added" in report.summary()
    assert "D-STAR calls: Added" in report.details_text()
    imported = target.get_memory(10)
    assert imported.mode == "DV"


def test_direct_call_dv_radio_does_not_mutate_master_lists():
    source = _source(IC2200)
    target = _source(IC2820)
    before = (
        tuple(target.get_urcall_list()),
        tuple(target.get_repeater_call_list()),
    )

    report = migration.apply_batch(
        target,
        migration.batch_from_radio(source, numbers=[17]),
        destination=20,
    )

    after = (
        tuple(target.get_urcall_list()),
        tuple(target.get_repeater_call_list()),
    )
    assert report.imported == 1
    assert report.dstar_calls_added == 0
    assert after == before
    assert target.get_memory(20).dv_rpt1call == "W4WBC C"


def test_dv_to_analog_is_incompatible_not_coerced():
    source = _source(IC2200)
    target = _source(UV5R)
    before = target.get_memory(10).dupe()

    report = migration.apply_batch(
        target,
        migration.batch_from_radio(source, numbers=[17]),
        destination=10,
    )

    after = target.get_memory(10)
    assert report.imported == 0
    assert report.incompatible == 1
    assert "does not support D-STAR" in report.details_text()
    assert after.freq == before.freq
    assert after.name == before.name


def test_conversion_failure_restores_call_lists_exactly():
    source = _source(IC2200)
    target = _source(ICV82)
    before = dstar_ops.capture_call_lists(target)
    incompatible = _custom_dv(source, 40, freq=440_000_000, suffix="2")

    report = migration.apply_batch(
        target, _dv_batch(incompatible), destination=10
    )

    assert report.incompatible == 1
    assert dstar_ops.capture_call_lists(target) == before
    assert target.get_memory(10).empty


def test_memory_write_failure_restores_call_lists_exactly(monkeypatch):
    source = _source(IC2200)
    target = _source(ICV82)
    before = dstar_ops.capture_call_lists(target)
    memory = _custom_dv(source, 41, freq=145_000_000, suffix="3")

    def fail_write(_memory):
        raise RuntimeError("simulated memory write failure")

    monkeypatch.setattr(target, "set_memory", fail_write)
    report = migration.apply_batch(target, _dv_batch(memory), destination=10)

    assert report.failed == 1
    assert "simulated memory write failure" in report.details_text()
    assert dstar_ops.capture_call_lists(target) == before


def test_partial_real_driver_write_restores_memory_and_calls_exactly():
    source = _source(ID4100)
    target = _source(IC2200)
    destination = 18
    before_raw = target.get_raw_memory(destination)
    before_calls = dstar_ops.capture_call_lists(target)

    report = migration.apply_batch(
        target,
        migration.batch_from_radio(source, numbers=[0]),
        destination=destination,
    )

    assert report.incompatible == 1
    assert "'CQCQCQ  ' is not in list" in report.details_text()
    assert target.get_raw_memory(destination) == before_raw
    assert dstar_ops.capture_call_lists(target) == before_calls


def test_partial_batch_keeps_only_calls_for_successful_memories():
    source = _source(IC2200)
    target = _source(ICV82)
    before = dstar_ops.capture_call_lists(target)
    accepted = _custom_dv(source, 42, freq=145_000_000, suffix="4")
    rejected = _custom_dv(source, 43, freq=440_000_000, suffix="5")

    report = migration.apply_batch(
        target,
        _dv_batch(accepted, rejected),
        destination=10,
    )

    after = dstar_ops.capture_call_lists(target)
    assert report.imported == 1
    assert report.incompatible == 1
    assert set(dstar_ops.added_calls(before, after)) == {
        "USER4",
        "RPT4 A",
        "RPT4 G",
    }
    assert "USER5" not in after.urcalls
    assert "RPT5 A" not in after.rptcalls


def test_full_call_list_is_incompatible_without_mutation():
    source = _source(IC2200)
    target = _source(ICV82)
    target.set_urcall_list([f"U{i}" for i in range(6)])
    target.set_repeater_call_list([f"R{i}" for i in range(6)])
    before = dstar_ops.capture_call_lists(target)
    memory = _custom_dv(source, 44, freq=145_000_000, suffix="6")

    report = migration.apply_batch(target, _dv_batch(memory), destination=10)

    assert report.incompatible == 1
    assert "No room to add callsign" in report.details_text()
    assert dstar_ops.capture_call_lists(target) == before


def test_special_memory_rejection_also_restores_call_lists():
    source = _source(IC2200)
    target = _source(ICV82)
    before = dstar_ops.capture_call_lists(target)
    incompatible = _custom_dv(source, 45, freq=440_000_000, suffix="7")

    report = migration.apply_batch_to_special(
        target,
        _dv_batch(incompatible),
        destination_name="C",
    )

    assert report.incompatible == 1
    assert dstar_ops.capture_call_lists(target) == before


def test_memory_and_call_lists_share_undo_redo_and_save(tmp_path):
    working = tmp_path / "Icom_IC-V82.img"
    shutil.copyfile(ICV82, working)
    ok, message = radio_backend.load_image(str(working))
    assert ok, message
    target = radio_backend.get_state().radio
    before_memory = target.get_memory(10).dupe()
    before_calls = dstar_ops.capture_call_lists(target)
    batch = migration.batch_from_radio(_source(IC2200), numbers=[17])

    ok, message, affected, report = memory_ops.apply_migration_batch(
        batch, destination=10
    )

    assert ok, report.details_text()
    assert affected == [10]
    after_calls = dstar_ops.capture_call_lists(target)
    assert after_calls != before_calls

    manager = radio_backend.get_undo_manager()
    manager.undo()
    assert target.get_memory(10).freq == before_memory.freq
    assert dstar_ops.capture_call_lists(target) == before_calls

    manager.redo()
    assert target.get_memory(10).mode == "DV"
    assert dstar_ops.capture_call_lists(target) == after_calls

    ok, message = radio_backend.save_image()
    assert ok, message
    radio_backend.unload()
    ok, message = radio_backend.load_image(str(working))
    assert ok, message
    reopened = radio_backend.get_state().radio
    assert reopened.get_memory(10).mode == "DV"
    assert dstar_ops.capture_call_lists(reopened) == after_calls


def test_snapshot_failure_refuses_active_import_before_any_write(monkeypatch):
    ok, message = radio_backend.load_image(ICV82)
    assert ok, message
    target = radio_backend.get_state().radio
    before = target.get_memory(10).dupe()
    batch = migration.batch_from_radio(_source(IC2200), numbers=[17])

    def fail_snapshot():
        raise RuntimeError("simulated call-list read failure")

    monkeypatch.setattr(target, "get_urcall_list", fail_snapshot)
    ok, _message, affected, report = memory_ops.apply_migration_batch(
        batch, destination=10
    )

    assert not ok
    assert not affected
    assert report.failed == 1
    assert "nothing was imported" in report.details_text()
    after = target.get_memory(10)
    assert after.freq == before.freq
    assert after.name == before.name
