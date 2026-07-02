"""Tests for VRP's out-of-tree CHIRP drivers (chirp_backend/extra_drivers).

These guard the registration mechanism and the KG-UV96M driver's decode against
CHIRP updates. No hardware or personal image is needed: the decode test builds a
synthetic image at the driver's documented offsets.
"""
import struct

import pytest

from chirp import directory
from chirp_backend import extra_drivers
from chirp_backend.extra_drivers import kguv96m
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
    # valid table @ 0x3200 + N: empty slots are 0x00 (radio convention), ch1 used
    img[0x3200:0x3200 + 401] = b"\x00" * 401
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


def _loaded_radio(freq_hz=146520000, name="TEST"):
    from chirp import memmap
    cls = _get_kguv96m_class()
    r = cls(None)
    r._mmap = memmap.MemoryMapBytes(_synthetic_image(freq_hz, name))
    r.process_mmap()
    return r


def test_kguv96m_set_memory_roundtrip_no_drift():
    # Reading a channel and writing it straight back must not change any byte.
    r = _loaded_radio()
    before = bytes(r.get_mmap().get_packed())
    for n in range(1, 401):
        r.set_memory(r.get_memory(n))
    assert bytes(r.get_mmap().get_packed()) == before


def test_kguv96m_set_memory_edit():
    r = _loaded_radio()
    m = r.get_memory(1)
    m.name = "HELLO"
    m.freq = 145170000
    r.set_memory(m)
    m2 = r.get_memory(1)
    assert m2.name == "HELLO"
    assert m2.freq == 145170000
    # channel 2 (empty) untouched
    assert r.get_memory(2).empty


def test_kguv96m_config_map_covers_channel_tables():
    # The write map must cover the channel, name and valid tables, or edits
    # would never reach the radio.
    covered = set()
    for start, blk, cnt in kguv96m._CONFIG_MAP:
        covered.update(range(start, start + blk * cnt))
    # channel array 0x05e0..0x1edf, names 0x1f00..0x31bf, valid 0x3200..0x3390
    assert set(range(0x05e0, 0x1ee0)) <= covered
    assert set(range(0x1f00, 0x31c0)) <= covered
    assert set(range(0x3200, 0x3391)) <= covered
