"""Multi-section radio images use CHIRP sub-devices without losing the parent.

The parent radio owns the complete image/clone lifecycle.  One child is the
active memory view shown in VRP's grid.  These tests use both CHIRP sub-device
styles: the FT-8800's static left/right views and the TK-3180K2's zones, which
are generated only after the image has been parsed.
"""

import os
import shutil

import pytest

from chirp_backend import radio as radio_backend


IMAGES = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "chirp", "tests", "images")
)
FT8800 = os.path.join(IMAGES, "Yaesu_FT-8800.img")
TK3180 = os.path.join(IMAGES, "Kenwood_TK-3180K2.img")

PINNED_SUBDEVICE_IMAGES = (
    ("Bajeton_BJ7800.img", 4),
    ("Baojie_BJ-9900.img", 2),
    ("BTECH_UV-50X3.img", 2),
    ("Icom_IC-E90.img", 2),
    ("Icom_IC-W32A.img", 2),
    ("Icom_IC-W32E.img", 2),
    ("Jetstream_JT270MH.img", 2),
    ("Kenwood_TK-280.img", 1),
    ("Kenwood_TK-3140K.img", 2),
    ("Kenwood_TK-3180K2.img", 3),
    ("Kenwood_TK-481.img", 2),
    ("Kenwood_TK-7160K.img", 1),
    ("Kenwood_TK-8180.img", 1),
    ("Kenwood_TK-880.img", 2),
    ("Kenwood_TK-981.img", 3),
    ("LUITON_LT-725UV.img", 2),
    ("Radtel_RT-920.img", 4),
    ("Retevis_RA87.img", 2),
    ("Yaesu_FT-7100M.img", 2),
    ("Yaesu_FT-8100.img", 2),
    ("Yaesu_FT-8800.img", 2),
    ("Yaesu_FTM-350.img", 2),
    ("Yaesu_VX-1.img", 3),
)


def teardown_function(_function):
    radio_backend.unload()


@pytest.mark.parametrize("filename, expected_count", PINNED_SUBDEVICE_IMAGES)
def test_every_pinned_chirp_parent_expands_to_its_memory_views(
    filename, expected_count
):
    image_set, message = radio_backend.load_image_set(
        os.path.join(IMAGES, filename)
    )

    assert image_set is not None, message
    assert len(image_set.devices) == expected_count
    assert all(device is not image_set.parent for device in image_set.devices)
    assert len(image_set.labels) == expected_count
    assert all(label and len(label) < 200 for label in image_set.labels)


def test_static_subdevices_are_discovered_without_activating_the_image():
    image_set, message = radio_backend.load_image_set(FT8800)

    assert image_set is not None, message
    assert not radio_backend.get_state().loaded
    assert image_set.parent.VENDOR == "Yaesu"
    assert image_set.parent.MODEL == "FT-8800"
    assert [radio.VARIANT for radio in image_set.devices] == ["Left", "Right"]
    assert image_set.labels == (
        "Left — channels 1 to 512",
        "Right — channels 1 to 512",
    )


def test_loading_a_selected_subdevice_retains_the_physical_parent():
    ok, message = radio_backend.load_image(FT8800, subdevice_index=1)

    assert ok, message
    state = radio_backend.get_state()
    assert state.parent_radio is not state.radio
    assert state.parent_radio.MODEL == "FT-8800"
    assert state.radio.VARIANT == "Right"
    assert state.subdevice_index == 1
    assert state.has_multiple_subdevices
    assert state.context_id.endswith(":1")


def test_save_writes_the_complete_parent_image(tmp_path):
    working = tmp_path / "FT-8800.img"
    shutil.copyfile(FT8800, working)
    ok, message = radio_backend.load_image(str(working), subdevice_index=1)
    assert ok, message

    memory = radio_backend.get_memory(1).dupe()
    memory.name = "VRPTST"
    ok, message = radio_backend.set_memory(memory)
    assert ok, message
    ok, message = radio_backend.save_image()
    assert ok, message

    radio_backend.unload()
    ok, message = radio_backend.load_image(str(working), subdevice_index=1)
    assert ok, message
    assert radio_backend.get_memory(1).name == "VRPTST"


def test_dynamic_subdevice_labels_never_use_generated_class_names():
    image_set, message = radio_backend.load_image_set(TK3180)

    assert image_set is not None, message
    assert len(image_set.devices) == 3
    assert image_set.labels == (
        "Zone FRS/GMRS — channels 1 to 250",
        "Zone Channels — channels 1 to 250",
        "Zone GMRS Wide — channels 1 to 250",
    )
    # CHIRP's generated classes for this fixture can exceed 20,000 characters.
    assert max(map(len, image_set.labels)) < 100


def test_dynamic_zone_edit_is_saved_through_its_parent(tmp_path):
    working = tmp_path / "TK-3180K2.img"
    shutil.copyfile(TK3180, working)
    ok, message = radio_backend.load_image(str(working), subdevice_index=2)
    assert ok, message
    low, high = radio_backend.get_state().memory_bounds
    number = next(
        n for n in range(low, high + 1)
        if not radio_backend.get_memory(n).empty
    )
    memory = radio_backend.get_memory(number).dupe()
    memory.name = "VRPZONE"
    ok, message = radio_backend.set_memory(memory)
    assert ok, message
    ok, message = radio_backend.save_image()
    assert ok, message

    radio_backend.unload()
    ok, message = radio_backend.load_image(str(working), subdevice_index=2)
    assert ok, message
    assert radio_backend.get_memory(number).name == "VRPZONE"


def test_open_source_can_select_a_subdevice_without_changing_active_radio():
    ok, message = radio_backend.load_image(FT8800, subdevice_index=0)
    assert ok, message
    active_document = radio_backend.get_state().document_id

    source, message = radio_backend.open_image_as_source(
        FT8800, subdevice_index=1
    )

    assert source is not None, message
    assert source.VARIANT == "Right"
    assert radio_backend.get_state().radio.VARIANT == "Left"
    assert radio_backend.get_state().document_id == active_document


def test_switching_sections_preserves_edits_but_resets_section_undo():
    from chirp_backend import memory_ops

    ok, message = radio_backend.load_image(FT8800, subdevice_index=0)
    assert ok, message
    state = radio_backend.get_state()
    first_context = state.context_id
    ok, message, _affected = memory_ops.update_channel(1, {"name": "CHGONE"})
    assert ok, message
    assert state.is_modified
    assert radio_backend.get_undo_manager().can_undo()

    ok, message = radio_backend.select_subdevice(1)

    assert ok, message
    assert state.radio.VARIANT == "Right"
    assert state.context_id != first_context
    assert state.is_modified
    assert not radio_backend.get_undo_manager().can_undo()

    # Returning to an object that was previously wrapped must install exactly
    # one fresh recorder, not wrap the old wrapper recursively.
    ok, message = radio_backend.select_subdevice(0)
    assert ok, message
    ok, message, _affected = memory_ops.update_channel(1, {"name": "CHGTWO"})
    assert ok, message
    assert radio_backend.get_undo_manager().can_undo()
    radio_backend.get_undo_manager().undo()
    assert radio_backend.get_memory(1).name == "CHGONE"
