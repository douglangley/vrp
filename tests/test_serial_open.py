"""Tests for serial-port setup before a clone (chirp_backend.radio).

No real port: serial.Serial is swapped for a recording fake so we can assert
both the values the driver class dictates and the critical ordering — the
port must be assigned (and open() called) only AFTER rts/dtr/rtscts are set,
because passing port= to the constructor would auto-open too early.
"""

from chirp_backend import radio as radio_backend


class _RecordingSerial:
    """Fake serial.Serial that records the order of attribute sets + open()."""

    def __init__(self, *args, **kwargs):
        # Bypass __setattr__ for our own bookkeeping attribute.
        object.__setattr__(self, "events", [])

    def __setattr__(self, name, value):
        self.events.append((name, value))
        object.__setattr__(self, name, value)

    def open(self):
        self.events.append(("open", None))


class _FakeRadio:
    BAUD_RATE = 19200
    HARDWARE_FLOW = True
    WANTS_RTS = False
    WANTS_DTR = True


def test_open_radio_serial_applies_driver_settings(monkeypatch):
    monkeypatch.setattr("serial.Serial", _RecordingSerial)

    pipe = radio_backend._open_radio_serial("COM4", _FakeRadio)

    values = dict(pipe.events)
    assert values["baudrate"] == 19200
    assert values["timeout"] == 0.25
    assert values["rtscts"] is True
    assert values["rts"] is False
    assert values["dtr"] is True
    assert values["port"] == "COM4"


def test_open_radio_serial_sets_port_and_opens_last(monkeypatch):
    monkeypatch.setattr("serial.Serial", _RecordingSerial)

    pipe = radio_backend._open_radio_serial("COM4", _FakeRadio)

    names = [n for n, _ in pipe.events]
    # Port must be assigned only after the flow-control flags are configured.
    assert names.index("port") > names.index("rts")
    assert names.index("port") > names.index("dtr")
    assert names.index("port") > names.index("rtscts")
    # open() must be the very last thing that happens.
    assert names[-1] == "open"


def test_open_radio_serial_uses_tracing_serial_when_tracing(monkeypatch):
    used = {}

    class _TraceRecorder(_RecordingSerial):
        def __init__(self, *a, **k):
            used["constructed"] = True
            super().__init__(*a, **k)

    monkeypatch.setattr(
        "chirp_backend.serial_trace.TracingSerial", _TraceRecorder
    )
    # Make sure the plain path is NOT used when trace=True.
    monkeypatch.setattr("serial.Serial", _RecordingSerial)

    pipe = radio_backend._open_radio_serial("COM4", _FakeRadio, trace=True)

    assert used.get("constructed") is True
    assert isinstance(pipe, _TraceRecorder)
