"""Explicit migration between ordinary and named CHIRP special memories."""

import os
import shutil

from chirp_backend import memory_ops
from chirp_backend import migration
from chirp_backend import radio as radio_backend


IMAGES = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "chirp", "tests", "images")
)
IC2100 = os.path.join(IMAGES, "Icom_IC-2100H.img")
IC208 = os.path.join(IMAGES, "Icom_IC-208H.img")
UV5R = os.path.join(IMAGES, "Baofeng_UV-5R.img")
IC2200 = os.path.join(IMAGES, "Icom_IC-2200H.img")
ID4100 = os.path.join(IMAGES, "Icom_ID-4100.img")
FT65R = os.path.join(IMAGES, "Yaesu_FT-65R.img")
GENERIC = os.path.join(IMAGES, "Generic_CSV.csv")


def teardown_function(_function):
    radio_backend.unload()


def _source(path):
    source, message = radio_backend.open_image_as_source(path)
    assert source is not None, message
    return source


def test_bulk_batch_never_silently_includes_special_memories():
    source = _source(IC2100)

    batch = migration.batch_from_radio(source)

    assert batch.entries
    assert all(isinstance(entry.source_number, int) for entry in batch.entries)
    assert all(not entry.memory.extd_number for entry in batch.entries)
    assert "C" not in [entry.source_number for entry in batch.entries]


def test_location_catalog_distinguishes_regular_and_special_memories():
    source = _source(IC2100)

    locations = migration.list_memory_locations(source)

    call = next(location for location in locations if location.identifier == "C")
    assert call.is_special
    assert call.number == 507
    assert "Special C" in call.label
    assert "155.355000 MHz" in call.label
    assert any(
        isinstance(location.identifier, int) and not location.is_special
        for location in locations
    )


def test_special_source_can_migrate_to_an_ordinary_channel():
    source = _source(IC2100)
    target = _source(UV5R)
    batch = migration.batch_from_identifiers(source, ["C"])

    report = migration.apply_batch(target, batch, destination=0)

    assert report.imported == 1, report.details_text()
    imported = target.get_memory(0)
    assert imported.freq == source.get_memory("C").freq
    assert imported.extd_number == ""


def test_special_source_can_map_to_a_differently_named_target_special():
    source = _source(IC2100)
    target = _source(IC208)
    batch = migration.batch_from_identifiers(source, ["C"])

    report = migration.apply_batch_to_special(
        target, batch, destination_name="C1"
    )

    assert report.imported == 1, report.details_text()
    imported = target.get_memory("C1")
    assert imported.freq == source.get_memory("C").freq
    assert imported.extd_number == "C1"
    assert report.items[0].destination_number == "C1"


def test_ordinary_source_can_map_to_a_target_special():
    source = _source(IC2100)
    target = _source(IC208)
    ordinary = next(
        location for location in migration.list_memory_locations(
            source, include_special=False
        )
    )
    batch = migration.batch_from_identifiers(source, [ordinary.identifier])

    report = migration.apply_batch_to_special(
        target, batch, destination_name="C1"
    )

    assert report.imported == 1, report.details_text()
    imported = target.get_memory("C1")
    assert imported.freq == ordinary.memory.freq
    assert imported.extd_number == "C1"


def test_occupied_special_can_be_skipped_explicitly():
    source = _source(IC2100)
    target = _source(IC208)
    batch = migration.batch_from_identifiers(source, ["C"])
    before = target.get_memory("C1").dupe()

    report = migration.apply_batch_to_special(
        target, batch, destination_name="C1", overwrite=False
    )

    assert report.occupied == 1
    after = target.get_memory("C1")
    assert after.freq == before.freq


def test_unknown_special_destination_is_reported_not_written():
    source = _source(IC2100)
    target = _source(IC208)
    batch = migration.batch_from_identifiers(source, ["C"])

    report = migration.apply_batch_to_special(
        target, batch, destination_name="NOT-A-CHANNEL"
    )

    assert report.incompatible == 1
    assert "not available" in report.details_text()


def test_broken_driver_immutable_field_is_a_clear_incompatibility():
    source = _source(IC2100)
    target = _source(IC2200)
    batch = migration.batch_from_identifiers(source, ["C"])

    report = migration.apply_batch_to_special(
        target, batch, destination_name="C"
    )

    assert report.incompatible == 1
    assert report.failed == 0
    assert "immutable field" in report.details_text()


def test_driver_virtual_number_limitation_is_incompatible_not_failed():
    source = _source(GENERIC)
    target = _source(ID4100)
    batch = migration.batch_from_identifiers(source, [25])

    report = migration.apply_batch_to_special(
        target, batch, destination_name="144-C0"
    )

    assert report.incompatible == 1
    assert report.failed == 0
    assert "virtual channel number" in report.details_text()


def test_plain_driver_band_exception_is_incompatible_not_failed():
    source = _source(GENERIC)
    target = _source(FT65R)
    batch = migration.batch_from_identifiers(source, [25])

    report = migration.apply_batch_to_special(
        target, batch, destination_name="VFO A VHF"
    )

    assert report.incompatible == 1
    assert report.failed == 0
    assert "out of range" in report.details_text()


def test_special_write_is_saved_and_undoable_through_active_parent(tmp_path):
    working = tmp_path / "IC-208H.img"
    shutil.copyfile(IC208, working)
    ok, message = radio_backend.load_image(str(working))
    assert ok, message
    target = radio_backend.get_state().radio
    before = target.get_memory("1A").dupe()
    assert before.empty
    source = _source(IC2100)
    batch = migration.batch_from_identifiers(source, ["C"])

    ok, message, affected, report = memory_ops.apply_migration_batch_to_special(
        batch, "1A", overwrite=True
    )

    assert ok, report.details_text()
    assert affected == ["1A"]
    changed = target.get_memory("1A")
    assert changed.freq == source.get_memory("C").freq
    result = radio_backend.get_undo_manager().undo()
    assert result is not None
    _label, restored = result
    assert restored == ["1A"]
    restored_memory = target.get_memory("1A")
    assert restored_memory.empty
    assert restored_memory.freq == before.freq

    # Redo the special write, save the complete image, and verify it survives.
    radio_backend.get_undo_manager().redo()
    ok, message = radio_backend.save_image()
    assert ok, message
    radio_backend.unload()
    ok, message = radio_backend.load_image(str(working))
    assert ok, message
    assert radio_backend.get_state().radio.get_memory("1A").freq == changed.freq
