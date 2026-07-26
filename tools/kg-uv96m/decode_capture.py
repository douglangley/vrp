"""Decode a USBPcap capture of an FTDI serial session with the KG-UV96M.

Prints, in time order: FTDI control requests (baud rate, DTR/RTS, data bits),
bulk WRITE payloads (host -> radio), and bulk READ payloads (radio -> host,
with FTDI's 2-byte status prefix stripped). Frame layout on the wire is
``0x7c <cmd> 0xff <len> encrypt(payload + checksum)``; this tool also decrypts
the kg935g-family payload (running XOR seeded 0x57) so you can read the address
and data of each CMD_RD (0x82) / CMD_WR (0x83).

Capture with USBPcap first (see docs/kg-uv96m-settings/PLAN.md), then:

    uv run python tools/kg-uv96m/decode_capture.py capture.pcap
"""
import struct
import sys

DLT_USBPCAP = 249
CMD = {0x80: "IDENT", 0x81: "END", 0x82: "READ", 0x83: "WRITE"}


def strip_ftdi_in(data):
    out = bytearray()
    for i in range(0, len(data), 64):
        out += data[i:i + 64][2:]   # drop FTDI's 2 modem-status bytes
    return bytes(out)


def decrypt(data):
    out = bytearray()
    prev = 0x57
    for b in data:
        out.append(prev ^ b)
        prev = b
    return bytes(out)


def _frames(stream):
    """Yield (cmd, decrypted_payload) from a reassembled serial byte stream."""
    i = 0
    while i + 4 <= len(stream):
        if stream[i] != 0x7c:
            i += 1
            continue
        cmd, length = stream[i + 1], stream[i + 3]
        enc = stream[i + 4:i + 4 + length + 1]
        if len(enc) < length + 1:
            break
        yield cmd, decrypt(enc)[:length]
        i += 4 + length + 1


def main(path):
    blob = open(path, "rb").read()
    if blob[:4] not in (b"\xd4\xc3\xb2\xa1", b"\xa1\xb2\xc3\xd4"):
        print("Not a classic pcap file")
        return
    off = 24
    out_stream = bytearray()
    in_stream = bytearray()
    while off + 16 <= len(blob):
        _, _, incl, _ = struct.unpack("<IIII", blob[off:off + 16])
        off += 16
        pkt = blob[off:off + incl]
        off += incl
        if len(pkt) < 27:
            continue
        hlen = struct.unpack("<H", pkt[0:2])[0]
        endpoint, transfer = pkt[21], pkt[22]
        dlen = struct.unpack("<I", pkt[23:27])[0]
        payload = pkt[hlen:hlen + dlen]
        if transfer == 3 and (endpoint & 0x80):       # bulk IN
            in_stream += strip_ftdi_in(payload)
        elif transfer == 3:                            # bulk OUT
            out_stream += payload

    print("=== WRITES / commands (host -> radio) ===")
    for cmd, pl in _frames(out_stream):
        name = CMD.get(cmd, "0x%02x" % cmd)
        if cmd in (0x82, 0x83) and len(pl) >= 2:
            addr = struct.unpack(">H", pl[0:2])[0]
            print("  %-5s addr=0x%04x len=%d  %s" % (
                name, addr, len(pl) - 2, pl[2:].hex(" ")))
        else:
            print("  %-5s %s" % (name, pl.hex(" ")))

    print("\n=== READ responses (radio -> host), reassembled ===")
    for cmd, pl in _frames(in_stream):
        name = CMD.get(cmd, "0x%02x" % cmd)
        print("  %-5s %s" % (name, pl[:16].hex(" ")))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "capture.pcap")
