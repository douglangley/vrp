"""Tests for chirp_backend.radio.list_serial_ports port ordering.

Plain string sort puts 'COM10' before 'COM4' (comparing '1' < '4'), so on a
machine with both a single- and a double-digit port connected, the port
picker's default selection (always index 0) can silently land on the wrong
device. list_serial_ports must sort numerically instead.
"""

from chirp_backend import radio as radio_backend


class _FakePortInfo:
    def __init__(self, device, description="", hwid=""):
        self.device = device
        self.description = description
        self.hwid = hwid


def test_list_serial_ports_sorts_numerically(monkeypatch):
    fake_ports = [
        _FakePortInfo("COM10"),
        _FakePortInfo("COM2"),
        _FakePortInfo("COM4"),
        _FakePortInfo("COM9"),
    ]
    monkeypatch.setattr(
        "serial.tools.list_ports.comports", lambda: fake_ports
    )

    ports = radio_backend.list_serial_ports()

    assert [p["port"] for p in ports] == ["COM2", "COM4", "COM9", "COM10"]
