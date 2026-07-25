"""Generic cross-model migration tests using CHIRP's real radio drivers."""

import os

from chirp_backend import memory_ops
from chirp_backend import radio as radio_backend


IMAGES = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "chirp", "tests", "images")
)
UV5R = os.path.join(IMAGES, "Baofeng_UV-5R.img")
MINI = os.path.join(IMAGES, "Baofeng_UV-5R_Mini.img")


def teardown_function(_function):
    radio_backend.unload()


def _source(path):
    source, message = radio_backend.open_image_as_source(path)
    assert source is not None, message
    return source


def test_mini_to_uv5r_drops_foreign_channel_extras():
    ok, message = radio_backend.load_image(UV5R)
    assert ok, message

    ok, message, affected = memory_ops.import_memories(
        _source(MINI), destination=0, overwrite=True
    )

    assert ok, message
    assert len(affected) == 21
    assert "sqmode" not in message
    assert radio_backend.get_memory(0).freq == 144_925_000


def test_migration_is_one_undoable_operation():
    ok, message = radio_backend.load_image(UV5R)
    assert ok, message
    before = radio_backend.get_memory(0).dupe()

    ok, message, affected = memory_ops.import_memories(
        _source(MINI), destination=0, overwrite=True
    )
    assert ok, message
    assert affected

    result = radio_backend.get_undo_manager().undo()
    assert result is not None
    _label, restored = result
    assert sorted(restored) == affected
    after_undo = radio_backend.get_memory(0)
    assert after_undo.freq == before.freq
    assert after_undo.name == before.name


def test_detailed_report_keeps_each_incompatibility_reason():
    ok, message = radio_backend.load_image(MINI)
    assert ok, message

    from chirp_backend import migration

    batch = migration.batch_from_radio(_source(UV5R))
    ok, summary, affected, report = memory_ops.apply_migration_batch(
        batch, destination=1, overwrite=True
    )

    assert ok, summary
    assert len(affected) == 36
    assert report.imported == 36
    assert report.incompatible == 1
    detail = report.details_text()
    assert "source 1" in detail.lower()
    assert "tx freq" in detail.lower()


def test_out_of_space_is_reported_for_every_remaining_source():
    ok, message = radio_backend.load_image(UV5R)
    assert ok, message

    from chirp_backend import migration

    batch = migration.batch_from_radio(_source(MINI))
    ok, summary, affected, report = memory_ops.apply_migration_batch(
        batch, destination=127, overwrite=True
    )

    assert ok, summary
    assert affected == [127]
    assert report.out_of_space == len(batch.entries) - 1
    assert "did not fit" in summary
