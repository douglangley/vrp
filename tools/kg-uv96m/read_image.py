"""Read a KG-UV96M into a raw .img file, through VRP's own driver.

Used to grab the "baseline" and "after" images for the settings-diff workflow
(see docs/kg-uv96m-settings/PLAN.md). No USBPcap needed for this step -- it
talks to the radio directly via the driver.

    uv run python tools/kg-uv96m/read_image.py COM4 baseline.img
"""
import sys
import time
from pathlib import Path

# Make the repo root importable when run as a script.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import vrp._chirp_path  # noqa: E402,F401
from chirp_backend import radio as rb  # noqa: E402
import serial  # noqa: E402


def main():
    port = sys.argv[1] if len(sys.argv) > 1 else "COM4"
    out = sys.argv[2] if len(sys.argv) > 2 else "kg-uv96m.img"

    rb._ensure_chirp()
    from chirp import directory
    cls = directory.get_radio("Wouxun_KG-UV96M")

    def status(s):
        pct = int(100 * s.cur / s.max) if getattr(s, "max", 0) else 0
        if pct % 10 == 0:
            sys.stdout.write("\r  reading %d%%   " % pct)
            sys.stdout.flush()

    pipe = serial.Serial(port, cls.BAUD_RATE, timeout=0.6)
    pipe.dtr = True
    pipe.rts = True
    time.sleep(0.1)
    radio = cls(pipe)
    radio.status_fn = status
    print("Reading KG-UV96M on %s @ %d baud..." % (port, cls.BAUD_RATE))
    radio.sync_in()
    pipe.close()

    data = bytes(radio.get_mmap().get_packed())[:0x8000]
    Path(out).write_bytes(data)
    print("\nSaved %s (%d bytes)" % (out, len(data)))


if __name__ == "__main__":
    main()
