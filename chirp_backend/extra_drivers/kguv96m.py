"""CHIRP driver for the Wouxun KG-UV96M (sold by mtcradio.com).

Reverse-engineered from a USBPcap capture of an RT Systems clone plus a full
read of the radio, and verified field-by-field against an RT Systems CSV export.

The KG-UV96M uses the same clone protocol as the Wouxun KG-935G family
(``chirp.drivers.kg935g``): ``0x7c`` framing, ``0x57`` running-XOR obfuscation,
8-bit checksum, ``CMD_RD`` (``0x82``) 64-byte block reads. It differs in four
ways:

  1. Serial baud is 9600 (kg935g is 19200).
  2. It does NOT answer ``CMD_ID`` (``0x80``) -- identify by reading the
     immutable factory info block at ``0x0340`` (``WOUXUN``) instead of the
     handshake. (Not the model name at ``0x049b`` -- that is the user-editable
     Startup Message.)
  3. Multi-byte integers are little-endian (kg935g is big-endian).
  4. 400 channels, with channel/name/valid tables at KG-UV96M-specific
     addresses (channels ``0x05e0 + N*16``, names ``0x1f00 + N*12``, valid
     ``0x3200 + N``; ``0x9E`` = used, ``0x00`` = empty -- ``0x9E`` is kg935g's
     ``MEM_VALID``).

This subclasses ``KG935GRadio`` for the transport (encrypt/decrypt/
``_read_record``/``_write_record``) and tone model, and overrides the memory
format, identify, download, upload, features and decode.

Read and channel write/upload are both supported and verified against real
hardware (no-op round-trip + a reversible single-channel edit). The upload
``_CONFIG_MAP`` (which regions to write, and block sizes) was captured verbatim
from an RT Systems upload, and ``set_memory`` produces byte-identical channel
records to the OEM software. Radio-wide *settings* are not yet mapped
(``has_settings = False``); only channel memory is editable.
"""
import logging
import struct
import time

from chirp import bitwise, chirp_common, directory, errors, memmap
from chirp.drivers import kg935g
from chirp.settings import (RadioSettings, RadioSettingGroup, RadioSetting,
                            RadioSettingValueInteger, RadioSettingValueList,
                            RadioSettingValueString)

LOG = logging.getLogger(__name__)

MEM_VALID = kg935g.MEM_VALID  # 0x9E

# --- radio-wide settings option lists (see docs/kg-uv96m-settings/) ----------
# For _TOT / _PTT_DELAY the stored byte is (index + 1); for the others it is the
# list index directly.
_TOT_OPTS = ["%d seconds" % (v * 15) for v in range(1, 61)]        # 15..900 s
_PTT_DELAY_OPTS = ["%d ms" % (v * 100) for v in range(1, 31)]      # 100..3000
_BACKLIGHT_OPTS = (["On"] + ["%d seconds" % v for v in range(1, 21)]
                   + ["Off"])                                       # idx: On=0..Off=21
_AUTOLOCK_OPTS = ["Off", "10 seconds", "20 seconds", "30 seconds",
                  "40 seconds", "50 seconds", "60 seconds"]
_STEP_OPTS = ["2.5K", "5K", "6.25K", "8.33K", "10K", "12.5K",
              "25K", "50K", "100K", "1000K"]
_BRT_STANDBY_OPTS = ["Off"] + [str(v) for v in range(1, 11)]       # Off=0, 1..10
_MEM_SIZE = 0x8000
_BLOCK = 64

# Which regions to write on upload, and in what block sizes -- captured
# verbatim from an RT Systems upload (CMD_WR frames). Each tuple is
# (start, blocksize, count); ragged tail blocks are their own single-count
# region. We write EXACTLY the regions/sizes the OEM tool writes and nothing
# else, so reserved/read-only areas the radio doesn't accept are never touched.
_CONFIG_MAP = (
    (0x0420, 64, 3),    # header / settings
    (0x0540, 32, 1),
    (0x05e0, 64, 100),  # channel memory (400 x 16 = 6400 bytes)
    (0x1ee0, 16, 1),
    (0x1f00, 64, 75),   # channel names (400 x 12 = 4800 bytes)
    (0x31c0, 12, 1),
    (0x3200, 64, 6),    # valid table (0x3200..0x337f)
    (0x3380, 17, 1),    # valid table tail (..0x3390)
    (0x3700, 40, 1),    # settings
    (0x3400, 64, 1),
    (0x3440, 62, 1),
    (0x3500, 64, 3),
    (0x35c0, 60, 1),
    (0x04e0, 64, 1),    # header regions RT writes last
    (0x0525, 32, 1),
)

# Little-endian version of kg935g's per-channel record, at KG-UV96M addresses.
# Slot 0 is unused (1-based channels), matching kg935g.
_MEM_FORMAT_96M = """
#seekto 0x05e0;
struct {
    ul32 rxfreq;
    ul32 txfreq;
    ul16 rxtone;
    ul16 txtone;
    u8   scrambler:4,
         power:4;
    u8   unknown1:2,
         scan_add:1,
         unknown2:1,
         compander:1,
         mute_mode:2,
         iswide:1;
    u8   step;
    u8   squelch;
} memory[401];

#seekto 0x1f00;
struct {
    u8 name[8];
    u8 pad[4];
} names[401];

#seekto 0x3200;
u8 valid[401];

// --- radio-wide settings (mapped so far; addresses verified by diff) ---
#seekto 0x0423;
u8 time_out_timer;      // value x 15 seconds (1..60)
#seekto 0x042b;
u8 backlight_time;      // 0=On, 1..20=seconds, 21=Off
u8 brightness_active;   // 1..10
u8 brightness_standby;  // 0=Off, 1..10
#seekto 0x0431;
u8 ptt_id_delay;        // value x 100 ms (1..30)
#seekto 0x0437;
u8 auto_lock;           // index into _AUTOLOCK_OPTS
#seekto 0x0474;
ul16 work_channel_b;    // channel 1..400
ul16 work_channel_a;    // channel 1..400
#seekto 0x0479;
u8 step;                // index into _STEP_OPTS
#seekto 0x047b;
u8 squelch;             // 0..9
#seekto 0x049b;
u8 startup_message[16]; // ASCII, space-padded
#seekto 0x04af;
u8 area_message[8];     // ASCII, space-padded
"""


@directory.register
class KGUV96MRadio(kg935g.KG935GRadio):
    """Wouxun KG-UV96M"""
    VENDOR = "Wouxun"
    MODEL = "KG-UV96M"
    _model = b"KG-UV96M"
    BAUD_RATE = 9600
    # KG-UV96M is Low / High on the front panel; index 1 (Mid) keeps the raw
    # power value (0=Low, 2=High) indexing correctly.
    POWER_LEVELS = [chirp_common.PowerLevel("Low", watts=1.0),
                    chirp_common.PowerLevel("Mid", watts=2.5),
                    chirp_common.PowerLevel("High", watts=5.0)]

    @classmethod
    def match_model(cls, filedata, filename):
        # Identify by the IMMUTABLE factory info block at 0x0340 (WOUXUN /
        # QuanZhou), which lives below the write map (0x0420) so nothing ever
        # overwrites it. The model name at 0x049b is the user-editable Startup
        # Message and must NOT be relied on (a user can rename it).
        return (len(filedata) >= 0x0360
                and filedata[0x0340:0x0346] == b"WOUXUN"
                and filedata[0x0358:0x0360] == b"QuanZhou")

    def process_mmap(self):
        self._memobj = bitwise.parse(_MEM_FORMAT_96M, self._mmap)

    # -- transport -----------------------------------------------------------
    def _identify(self):
        """KG-UV96M has no CMD_ID handshake; identify by reading the immutable
        factory info block at 0x0340 (contains 'WOUXUN').

        We deliberately do NOT key on the model name at 0x049b: that is the
        user-editable Startup Message, so a renamed radio would fail to
        identify. 0x0340 lives below the write map (0x0420) and is never
        overwritten. The radio occasionally drops the first transaction after
        the port is opened, so retry a few times before giving up.
        """
        last = None
        for attempt in range(5):
            try:
                self._write_record(kg935g.CMD_RD,
                                    struct.pack(">HB", 0x0340, _BLOCK))
                _err, resp = self._read_record()
            except errors.RadioNoResponse as e:
                last = e
                time.sleep(0.1)
                continue
            if b"WOUXUN" in bytes(resp):
                LOG.info("Identified Wouxun clone radio (attempt %d)",
                         attempt + 1)
                return
            last = errors.RadioError(
                "Not a recognized Wouxun radio (info block=%r)"
                % bytes(resp[:24]))
            break
        raise last or errors.RadioNoResponse()

    def _download(self):
        """Read the whole 32 KiB memory in 64-byte blocks.

        Overrides kg935g's ``_download``/``_do_download`` to (a) produce a clean
        exactly-32768-byte image and (b) retry individual blocks, since the
        radio occasionally drops a transaction (kg935g's version aborts the
        whole clone on the first hiccup).
        """
        self._identify()
        image = bytearray(b"\xff" * _MEM_SIZE)
        for addr in range(0, _MEM_SIZE, _BLOCK):
            for attempt in range(4):
                try:
                    self._write_record(
                        kg935g.CMD_RD, struct.pack(">HB", addr, _BLOCK))
                    cs_error, resp = self._read_record()
                except errors.RadioNoResponse:
                    time.sleep(0.05)
                    continue
                if cs_error or len(resp) < 2 + _BLOCK:
                    continue
                if struct.unpack(">H", resp[0:2])[0] != addr:
                    continue
                image[addr:addr + _BLOCK] = resp[2:2 + _BLOCK]
                break
            else:
                raise errors.RadioError(
                    "No valid response for block 0x%04x" % addr)
            if self.status_fn:
                status = chirp_common.Status()
                status.cur = addr
                status.max = _MEM_SIZE
                status.msg = "Cloning from radio"
                self.status_fn(status)
        return memmap.MemoryMapBytes(bytes(image))

    # -- features / decode ---------------------------------------------------
    def get_features(self):
        rf = chirp_common.RadioFeatures()
        rf.has_settings = True    # 12 settings mapped (see get_settings)
        rf.has_ctone = True
        rf.has_rx_dtcs = True
        rf.has_cross = True
        rf.has_tuning_step = False
        rf.has_bank = False
        rf.can_odd_split = True
        rf.valid_skips = ["", "S"]
        rf.valid_tmodes = ["", "Tone", "TSQL", "DTCS", "Cross"]
        rf.valid_cross_modes = ["Tone->Tone", "Tone->DTCS", "DTCS->Tone",
                                "DTCS->", "->Tone", "->DTCS", "DTCS->DTCS"]
        rf.valid_modes = ["FM", "NFM"]
        rf.valid_power_levels = self.POWER_LEVELS
        rf.valid_name_length = 8
        rf.valid_characters = chirp_common.CHARSET_ASCII
        rf.valid_duplexes = ["", "-", "+", "split", "off"]
        rf.valid_bands = [(108000000, 180000000),   # airband RX / VHF
                          (400000000, 520000000)]    # UHF / FRS / GMRS
        rf.memory_bounds = (1, 400)
        return rf

    def _get_power(self, _mem, mem):
        try:
            mem.power = self.POWER_LEVELS[int(_mem.power) & 0x3]
        except IndexError:
            mem.power = self.POWER_LEVELS[-1]

    def get_memory(self, number):
        _mem = self._memobj.memory[number]
        _nam = self._memobj.names[number]

        mem = chirp_common.Memory()
        mem.number = number
        if int(self._memobj.valid[number]) != MEM_VALID:
            mem.empty = True
            return mem

        mem.freq = int(_mem.rxfreq) * 10
        txf = int(_mem.txfreq)
        if txf in (0, 0xFFFFFFFF):
            mem.duplex = "off"
            mem.offset = 0
        elif txf == int(_mem.rxfreq):
            mem.duplex = ""
            mem.offset = 0
        else:
            diff = txf * 10 - mem.freq
            if abs(diff) > 70000000:
                mem.duplex = "split"
                mem.offset = txf * 10
            else:
                mem.duplex = "-" if diff < 0 else "+"
                mem.offset = abs(diff)

        for ch in _nam.name:
            if int(ch) != 0:
                mem.name += chr(int(ch))
        mem.name = mem.name.rstrip()

        self.tone_model.get_tone(_mem, mem)
        mem.mode = "FM" if int(_mem.iswide) else "NFM"
        mem.skip = "" if int(_mem.scan_add) else "S"
        self._get_power(_mem, mem)
        return mem

    def get_extra(self, _mem, mem):
        # per-channel "extra" settings not yet mapped for this model
        return

    # -- write / upload ------------------------------------------------------
    def _set_power(self, mem):
        try:
            return self.POWER_LEVELS.index(mem.power)
        except ValueError:
            return len(self.POWER_LEVELS) - 1  # default High

    def set_memory(self, mem):
        """Write one channel back into the image.

        Only the fields this driver understands are modified; every other byte
        of the 16-byte record is left exactly as it was read from the radio, so
        an unedited channel round-trips byte-for-byte and we never write a value
        we haven't verified. A genuinely new (previously empty) slot is wiped to
        zero first to avoid ghost/factory bytes.
        """
        number = mem.number
        _mem = self._memobj.memory[number]
        _nam = self._memobj.names[number]

        if mem.empty:
            self._memobj.valid[number] = 0x00
            return

        was_empty = int(self._memobj.valid[number]) != MEM_VALID
        if was_empty:
            _mem.fill_raw(b"\x00")
            _nam.fill_raw(b"\x00")

        _mem.rxfreq = mem.freq // 10
        if mem.duplex == "off":
            # The radio stores "TX off" as 0x00000000 (observed on the airband
            # RX-only channel), not kg935g's 0xFFFFFFFF; match the radio.
            _mem.txfreq = 0
        elif mem.duplex == "split":
            _mem.txfreq = mem.offset // 10
        elif mem.duplex == "+":
            _mem.txfreq = (mem.freq + mem.offset) // 10
        elif mem.duplex == "-":
            _mem.txfreq = (mem.freq - mem.offset) // 10
        else:
            _mem.txfreq = mem.freq // 10

        self.tone_model.set_tone(mem, _mem)
        _mem.iswide = 1 if mem.mode == "FM" else 0
        _mem.scan_add = 0 if mem.skip == "S" else 1
        if mem.power is not None:
            _mem.power = self._set_power(mem)

        for i in range(len(_nam.name)):
            _nam.name[i] = ord(mem.name[i]) if i < len(mem.name) else 0x00

        self._memobj.valid[number] = MEM_VALID

    def _do_upload(self):
        mmap = self.get_mmap()
        total = sum(bs * cnt for _, bs, cnt in _CONFIG_MAP)
        done = 0
        for start, blocksize, count in _CONFIG_MAP:
            for addr in range(start, start + blocksize * count, blocksize):
                chunk = bytes(mmap[addr:addr + blocksize])
                for attempt in range(4):
                    self._write_record(
                        kg935g.CMD_WR, struct.pack(">H", addr) + chunk)
                    try:
                        cserr, ack = self._read_record()
                    except errors.RadioNoResponse:
                        time.sleep(0.05)
                        continue
                    if not cserr and len(ack) >= 2 and \
                            struct.unpack(">H", ack[0:2])[0] == addr:
                        break
                else:
                    raise errors.RadioError(
                        "Radio did not ack write block 0x%04x" % addr)
                done += blocksize
                if self.status_fn:
                    status = chirp_common.Status()
                    status.cur = done
                    status.max = total
                    status.msg = "Cloning to radio"
                    self.status_fn(status)
        self._finish()  # CMD_END (0x81)

    def sync_out(self):
        try:
            self._identify()
            self._do_upload()
        except errors.RadioError:
            raise
        except Exception as e:  # noqa: BLE001
            raise errors.RadioError("Failed to upload to radio: %s" % e)

    # -- radio-wide settings (the 12 mapped so far) --------------------------
    @staticmethod
    def _get_str(field):
        s = ""
        for b in field:
            b = int(b)
            if b in (0x00, 0xFF):   # NUL or uninitialized -> end of string
                break
            s += chr(b) if 32 <= b < 127 else ""
        return s.rstrip()

    @staticmethod
    def _set_str(field, value, length):
        for i in range(length):
            field[i] = ord(value[i]) if i < len(value) else 0x20  # space-pad

    @staticmethod
    def _clamp(v, lo, hi):
        return max(lo, min(hi, v))

    def get_settings(self):
        m = self._memobj

        def add_list(group, name, label, opts, idx):
            idx = idx if 0 <= idx < len(opts) else 0
            group.append(RadioSetting(
                name, label, RadioSettingValueList(opts, current_index=idx)))

        basic = RadioSettingGroup("basic", "Basic")
        add_list(basic, "squelch", "Squelch",
                 [str(i) for i in range(10)], self._clamp(int(m.squelch), 0, 9))
        add_list(basic, "time_out_timer", "Time-Out Timer",
                 _TOT_OPTS, int(m.time_out_timer) - 1)
        add_list(basic, "ptt_id_delay", "PTT-ID Delay",
                 _PTT_DELAY_OPTS, int(m.ptt_id_delay) - 1)
        add_list(basic, "auto_lock", "Auto Keypad Lock",
                 _AUTOLOCK_OPTS, int(m.auto_lock))
        add_list(basic, "step", "Tuning Step", _STEP_OPTS, int(m.step))
        basic.append(RadioSetting(
            "work_channel_a", "Work Channel A",
            RadioSettingValueInteger(
                1, 400, self._clamp(int(m.work_channel_a), 1, 400))))
        basic.append(RadioSetting(
            "work_channel_b", "Work Channel B",
            RadioSettingValueInteger(
                1, 400, self._clamp(int(m.work_channel_b), 1, 400))))

        display = RadioSettingGroup("display", "Display")
        add_list(display, "backlight_time", "Backlight Time",
                 _BACKLIGHT_OPTS, int(m.backlight_time))
        display.append(RadioSetting(
            "brightness_active", "Brightness (Active)",
            RadioSettingValueInteger(
                1, 10, self._clamp(int(m.brightness_active), 1, 10))))
        add_list(display, "brightness_standby", "Brightness (Standby)",
                 _BRT_STANDBY_OPTS, int(m.brightness_standby))

        messages = RadioSettingGroup("messages", "Messages")
        messages.append(RadioSetting(
            "startup_message", "Startup Message (max 16)",
            RadioSettingValueString(0, 16, self._get_str(m.startup_message),
                                    autopad=False)))
        messages.append(RadioSetting(
            "area_message", "Area Message (max 8)",
            RadioSettingValueString(0, 8, self._get_str(m.area_message),
                                    autopad=False)))

        return RadioSettings(basic, display, messages)

    def set_settings(self, settings):
        m = self._memobj
        for element in settings:
            if not isinstance(element, RadioSetting):
                self.set_settings(element)
                continue
            name = element.get_name()
            val = element.value
            if name == "squelch":
                m.squelch = int(str(val))
            elif name == "time_out_timer":
                m.time_out_timer = _TOT_OPTS.index(str(val)) + 1
            elif name == "ptt_id_delay":
                m.ptt_id_delay = _PTT_DELAY_OPTS.index(str(val)) + 1
            elif name == "auto_lock":
                m.auto_lock = _AUTOLOCK_OPTS.index(str(val))
            elif name == "step":
                m.step = _STEP_OPTS.index(str(val))
            elif name == "work_channel_a":
                m.work_channel_a = int(val)
            elif name == "work_channel_b":
                m.work_channel_b = int(val)
            elif name == "backlight_time":
                m.backlight_time = _BACKLIGHT_OPTS.index(str(val))
            elif name == "brightness_active":
                m.brightness_active = int(val)
            elif name == "brightness_standby":
                m.brightness_standby = _BRT_STANDBY_OPTS.index(str(val))
            elif name == "startup_message":
                self._set_str(m.startup_message, str(val), 16)
            elif name == "area_message":
                self._set_str(m.area_message, str(val), 8)
