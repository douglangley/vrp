"""Channels-in-a-bank overview, built without CHIRP's broken helper.

``scan_bank_channels`` deliberately asks each memory which banks it belongs to
instead of calling ``MappingModel.get_mapping_memories``. ``StaticBankModel``'s
implementation of that helper divides with ``/``, producing a float that
``range()`` rejects, and ``chirp/`` is never edited here.
"""

import os

import pytest

from chirp_backend import bank_ops
from chirp_backend import radio as radio_backend


IMAGES = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "chirp", "tests", "images")
)
IC2200 = os.path.join(IMAGES, "Icom_IC-2200H.img")
IC2720 = os.path.join(IMAGES, "Icom_IC-2720H.img")
BF_F8HP_PRO = os.path.join(IMAGES, "Baofeng_BF-F8HP-PRO.img")  # fixed banks
UV5R = os.path.join(IMAGES, "Baofeng_UV-5R.img")               # no banks


def teardown_function(_function):
    radio_backend.unload()


def _source(path):
    source, message = radio_backend.open_image_as_source(path)
    assert source is not None, message
    return source


def test_scan_finds_a_known_channel_in_its_bank():
    source = _source(IC2200)

    ok, message, found = bank_ops.scan_bank_channels(source)

    assert ok, message
    assert 2 in [channel.number for channel in found[0]]


def test_scan_returns_an_entry_for_every_bank_including_empty_ones():
    source = _source(IC2200)
    catalog = bank_ops.describe_banks(source)

    ok, _message, found = bank_ops.scan_bank_channels(source)

    assert ok
    assert set(found) == set(range(len(catalog.banks)))
    assert any(found[position] == () for position in found)


def test_scan_carries_speakable_channel_details():
    source = _source(IC2200)

    ok, _message, found = bank_ops.scan_bank_channels(source)

    assert ok
    channel = next(c for c in found[0] if c.number == 2)
    expected = source.get_memory(2)
    assert channel.frequency == expected.freq
    assert channel.name == expected.name.strip()
    assert channel.order is None or isinstance(channel.order, int)


def test_scan_never_reports_an_empty_channel():
    source = _source(IC2720)

    ok, _message, found = bank_ops.scan_bank_channels(source)

    assert ok
    for channels in found.values():
        for channel in channels:
            assert not source.get_memory(channel.number).empty


def test_scan_works_on_fixed_banks():
    """The path that CHIRP's own get_mapping_memories cannot serve."""
    source = _source(BF_F8HP_PRO)
    catalog = bank_ops.describe_banks(source)
    assert catalog.mode == "fixed"

    ok, message, found = bank_ops.scan_bank_channels(source)

    assert ok, message
    assert set(found) == set(range(len(catalog.banks)))
    assert sum(len(channels) for channels in found.values()) > 0


def test_chirp_static_bank_helper_is_still_broken_upstream():
    """Documents why scan_bank_channels exists; fails loudly if CHIRP fixes it."""
    source = _source(BF_F8HP_PRO)
    model = bank_ops.bank_model_for(source)
    bank = model.get_mappings()[0]

    with pytest.raises(TypeError):
        model.get_mapping_memories(bank)


def test_scan_reports_a_radio_without_banks():
    source = _source(UV5R)

    ok, message, found = bank_ops.scan_bank_channels(source)

    assert not ok
    assert "no banks" in message
    assert found == {}
