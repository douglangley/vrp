"""Tests for VRP's out-of-tree CHIRP drivers (chirp_backend/extra_drivers).

These guard the registration mechanism and the KG-UV96M driver's decode against
CHIRP updates. No hardware or personal image is needed: the decode test builds a
synthetic image at the driver's documented offsets.
"""
import struct

import pytest

from chirp import directory
from chirp_backend import extra_drivers
from chirp_backend import radio as radio_backend


@pytest.fixture(scope="module", autouse=True)
def _chirp_loaded():
    # Ensures directory.import_drivers() + extra_drivers.register_all() have run.
    radio_backend._ensure_chirp()


def _get_kguv96m_class():
    return directory.get_radio("Wouxun_KG-UV96M")


def test_kguv96m_registered():
    models = {m["id"]: m for m in radio_backend.list_radio_models()}
    assert "Wouxun_KG-UV96M" in models
    assert models["Wouxun_KG-UV96M"]["vendor"] == "Wouxun"
    assert models["Wouxun_KG-UV96M"]["model"] == "KG-UV96M"


def test_kguv96m_features():
    cls = _get_kguv96m_class()
    assert cls.BAUD_RATE == 9600
    rf = cls(None).get_features()
    assert rf.memory_bounds == (1, 400)
    assert "FM" in rf.valid_modes and "NFM" in rf.valid_modes


def test_registry_id_matches_class():
    # The hard-coded id in _EXTRA_DRIVERS must match what CHIRP computes, or the
    # upstream-skip guard silently never triggers.
    for _mod, _cls, rid in extra_drivers._EXTRA_DRIVERS:
        cls = directory.get_radio(rid)
        assert directory.radio_class_id(cls) == rid


def test_register_all_is_idempotent_and_skips_existing():
    # Everything in _EXTRA_DRIVERS is already registered, so a second call must
    # register nothing new and must NOT raise "Duplicate radio driver id".
    before = dict(directory.DRV_TO_RADIO)
    newly = extra_drivers.register_all()
    assert newly == []
    assert directory.DRV_TO_RADIO == before


def _synthetic_image(freq_hz=146520000, name="TEST"):
    """Build a 32 KiB image with channel 1 programmed at the KG-UV96M offsets."""
    img = bytearray(b"\xff" * 0x8000)
    # channel 1 record @ 0x05f0 (little-endian): rxfreq=txfreq (simplex),
    # no tones, power=High(2)/wide+scan.
    rec = struct.pack("<II", freq_hz // 10, freq_hz // 10)  # rxfreq, txfreq
    rec += struct.pack("<HH", 0, 0)                          # rxtone, txtone
    rec += bytes([0x02, 0x21, 0x01, 0x00])                   # pwr, flags, step, sq
    img[0x05f0:0x05f0 + 16] = rec
    # name @ 0x1f0c
    nm = name.encode("ascii")[:8].ljust(12, b"\x00")
    img[0x1f0c:0x1f0c + 12] = nm
    # valid flag @ 0x3200 + 1
    img[0x3200 + 1] = 0x9E  # MEM_VALID
    return bytes(img)


def test_kguv96m_decode_synthetic():
    from chirp import memmap
    cls = _get_kguv96m_class()
    r = cls(None)
    r._mmap = memmap.MemoryMapBytes(_synthetic_image())
    r.process_mmap()

    m = r.get_memory(1)
    assert not m.empty
    assert m.freq == 146520000
    assert m.duplex == ""
    assert m.mode == "FM"
    assert m.name == "TEST"
    assert str(m.power) == "High"

    # channel 2 has no valid flag -> empty
    assert r.get_memory(2).empty


def test_kguv96m_upload_blocked():
    from chirp import errors
    cls = _get_kguv96m_class()
    r = cls(None)
    with pytest.raises(errors.RadioError):
        r.sync_out()
