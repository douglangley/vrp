"""CHIRP driver for the Wouxun KG-UV96M (sold by mtcradio.com).

Reverse-engineered from a USBPcap capture of an RT Systems clone plus a full
read of the radio, and verified field-by-field against an RT Systems CSV export.

The KG-UV96M uses the same clone protocol as the Wouxun KG-935G family
(``chirp.drivers.kg935g``): ``0x7c`` framing, ``0x57`` running-XOR obfuscation,
8-bit checksum, ``CMD_RD`` (``0x82``) 64-byte block reads. It differs in four
ways:

  1. Serial baud is 9600 (kg935g is 19200).
  2. It does NOT answer ``CMD_ID`` (``0x80``) -- identify by reading the model
     block at ``0x0480`` instead of the handshake.
  3. Multi-byte integers are little-endian (kg935g is big-endian).
  4. 400 channels, with channel/name/valid tables at KG-UV96M-specific
     addresses (channels ``0x05e0 + N*16``, names ``0x1f00 + N*12``, valid
     ``0x3200 + N``; ``0x9E`` = used, ``0x00`` = empty -- ``0x9E`` is kg935g's
     ``MEM_VALID``).

This subclasses ``KG935GRadio`` for the transport (encrypt/decrypt/
``_read_record``/``_write_record``) and tone model, and overrides the memory
format, identify, download, features and decode.

Upload is intentionally not yet enabled: the writable-region map has not been
reverse-engineered, so ``set_memory``/``sync_out`` raise rather than risk
writing bad data to the radio.
"""
import logging
import struct
import time

from chirp import bitwise, chirp_common, directory, errors, memmap
from chirp.drivers import kg935g

LOG = logging.getLogger(__name__)

MEM_VALID = kg935g.MEM_VALID  # 0x9E
_MEM_SIZE = 0x8000
_BLOCK = 64

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
        # The model block at 0x049b holds the ASCII model name.
        return len(filedata) >= 0x04a3 and \
            filedata[0x049b:0x04a3] == b"KG-UV96M"

    def process_mmap(self):
        self._memobj = bitwise.parse(_MEM_FORMAT_96M, self._mmap)

    # -- transport -----------------------------------------------------------
    def _identify(self):
        """KG-UV96M has no CMD_ID handshake; identify by reading the model
        block at 0x0480 (contains the ASCII 'KG-UV96M').

        The radio occasionally drops the first transaction after the port is
        opened, so retry a few times before giving up.
        """
        last = None
        for attempt in range(5):
            try:
                self._write_record(kg935g.CMD_RD,
                                    struct.pack(">HB", 0x0480, _BLOCK))
                _err, resp = self._read_record()
            except errors.RadioNoResponse as e:
                last = e
                time.sleep(0.1)
                continue
            if b"KG-UV96M" in bytes(resp):
                LOG.info("Identified KG-UV96M (attempt %d)", attempt + 1)
                return
            last = errors.RadioError(
                "Radio is not a KG-UV96M (model block=%r)" % bytes(resp[:24]))
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
        rf.has_settings = False   # radio-wide settings not yet mapped
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

    # -- upload: not yet supported ------------------------------------------
    def set_memory(self, mem):
        raise errors.RadioError(
            "Upload to the KG-UV96M is not yet supported by this driver.")

    def sync_out(self):
        raise errors.RadioError(
            "Upload to the KG-UV96M is not yet supported by this driver.")
