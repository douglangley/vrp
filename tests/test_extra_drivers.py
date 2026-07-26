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
    # radio-wide settings region with sane defaults
    img[0x0423] = 4          # time_out_timer -> 60 s
    img[0x042b] = 10         # backlight_time -> 10 s
    img[0x042c] = 8          # brightness active
    img[0x042d] = 1          # brightness standby
    img[0x0431] = 3          # ptt_id_delay -> 300 ms
    img[0x0437] = 0          # auto_lock -> Off
    struct.pack_into("<H", img, 0x0474, 2)   # work channel B
    struct.pack_into("<H", img, 0x0476, 1)   # work channel A
    img[0x0479] = 6          # step -> 25K
    img[0x047b] = 5          # squelch
    img[0x049b:0x049b + 16] = b"TEST".ljust(16, b" ")
    img[0x04af:0x04af + 8] = b"AREA".ljust(8, b" ")
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


def test_kguv96m_tone_modes_roundtrip():
    # CTCSS / TSQL / DTCS (incl. split polarity) must survive set->get. Uses the
    # inherited KenwoodToneModel (dcs_base 0x4000, pol 0x2000) — same u16 field
    # and scheme as the verified CTCSS decode.
    r = _loaded_radio()

    m = r.get_memory(1)
    m.tmode = "Tone"; m.rtone = 88.5
    r.set_memory(m)
    g = r.get_memory(1)
    assert g.tmode == "Tone" and g.rtone == 88.5

    m = r.get_memory(1)
    m.tmode = "TSQL"; m.ctone = 100.0
    r.set_memory(m)
    g = r.get_memory(1)
    assert g.tmode == "TSQL" and g.ctone == 100.0

    for dtcs, pol in [(23, "NN"), (754, "RR"), (23, "RN")]:
        m = r.get_memory(1)
        m.tmode = "DTCS"; m.dtcs = dtcs; m.dtcs_polarity = pol
        r.set_memory(m)
        g = r.get_memory(1)
        assert g.tmode == "DTCS" and g.dtcs == dtcs and g.dtcs_polarity == pol


def test_kguv96m_settings_roundtrip():
    from chirp.settings import RadioSetting
    r = _loaded_radio()
    r.get_features().has_settings  # ensure enabled path

    # edit a representative spread of settings
    settings = r.get_settings()
    edits = {"squelch": "3", "time_out_timer": "300 seconds",
             "step": "12.5K", "auto_lock": "30 seconds",
             "backlight_time": "Off", "brightness_active": 7,
             "work_channel_b": 250, "startup_message": "HELLO"}
    for group in settings:
        for s in group:
            if isinstance(s, RadioSetting) and s.get_name() in edits:
                s.value = edits[s.get_name()]
    r.set_settings(settings)

    # read back and confirm the values stuck
    got = {}
    for group in r.get_settings():
        for s in group:
            if isinstance(s, RadioSetting):
                got[s.get_name()] = str(s.value)
    assert got["squelch"] == "3"
    assert got["time_out_timer"] == "300 seconds"
    assert got["step"] == "12.5K"
    assert got["auto_lock"] == "30 seconds"
    assert got["backlight_time"] == "Off"
    assert got["brightness_active"] == "7"
    assert got["work_channel_b"] == "250"
    assert got["startup_message"] == "HELLO"

    # a setting we did NOT touch must survive unchanged
    assert got["brightness_standby"] == "1"  # synthetic image default


def test_kguv96m_settings_addresses():
    # get_settings must read the exact mapped bytes.
    import struct
    r = _loaded_radio()
    img = bytearray(r.get_mmap().get_packed())
    img[0x047b] = 7          # squelch
    img[0x0423] = 3          # TOT: 3 -> 45 seconds
    struct.pack_into("<H", img, 0x0474, 321)   # work channel B
    from chirp import memmap
    r._mmap = memmap.MemoryMapBytes(bytes(img))
    r.process_mmap()
    got = {s.get_name(): str(s.value)
           for g in r.get_settings() for s in g
           if hasattr(s, "get_name")}
    assert got["squelch"] == "7"
    assert got["time_out_timer"] == "45 seconds"
    assert got["work_channel_b"] == "321"


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
