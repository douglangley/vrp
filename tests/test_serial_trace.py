"""Tests for the byte-level serial trace (chirp_backend/serial_trace.py).

No real serial port: serial.Serial's open/read/write are mocked, so these run
headless. Mirrors the coverage of CHIRP's own tests/unit/test_serialtrace.py,
adapted to VRP's fixed-path (one-per-session) trace file.
"""

import os
from unittest import mock

from chirp_backend import serial_trace
from chirp_backend.serial_trace import TracingSerial, get_trace_entry


def test_default_trace_path_is_in_cwd():
    path = serial_trace.default_trace_path()
    assert os.path.basename(path) == "serial-trace.txt"
    assert os.path.dirname(path) == os.getcwd()


def test_get_trace_entry_marks_empty_read_as_timeout():
    lines = get_trace_entry("R", 0.0, b"")
    assert len(lines) == 1
    assert "# timeout" in lines[0]
    assert lines[0].lstrip().startswith(("0", "1", "2", "3", "4", "5",
                                         "6", "7", "8", "9"))


def test_get_trace_entry_hexdumps_data():
    lines = get_trace_entry("W", 0.0, b"foo")
    joined = "".join(lines)
    assert "66 6f 6f" in joined  # hex for 'foo'
    assert "foo" in joined       # ASCII column


@mock.patch("serial.Serial.open")
def test_open_creates_trace_file(mock_open, tmp_path):
    path = str(tmp_path / "trace.txt")
    trace = TracingSerial(trace_path=path)
    assert trace._tracef is None
    trace.open()
    assert trace._tracef is not None
    assert os.path.exists(path)
    mock_open.assert_called_once()
    trace.close()


@mock.patch("serial.Serial.open")
@mock.patch("serial.Serial.write")
@mock.patch("serial.Serial.read")
def test_log_present_and_noop_when_tracing_disabled(
    mock_read, mock_write, mock_open, tmp_path
):
    # Regression: CHIRP drivers call radio.pipe.log(...) during sync. With a
    # plain serial.Serial that raised AttributeError; TracingSerial must always
    # expose .log() (and write/read) even with tracing off, writing no file.
    mock_read.return_value = b"x"
    path = str(tmp_path / "trace.txt")
    trace = TracingSerial(trace_path=path, trace_enabled=False)
    trace.open()
    assert trace._tracef is None
    assert not os.path.exists(path)  # no file written when disabled
    trace.log("Sending request for 0x0000")  # must not raise
    trace.write(b"foo")              # must not raise
    assert trace.read(1) == b"x"     # pass-through still works
    trace.close()
    assert not os.path.exists(path)


@mock.patch("serial.Serial.open")
@mock.patch("serial.Serial.write")
@mock.patch("serial.Serial.read")
def test_write_and_read_are_logged(mock_read, mock_write, mock_open, tmp_path):
    mock_read.side_effect = [b"123", b""]  # second read yields a timeout
    path = str(tmp_path / "trace.txt")
    trace = TracingSerial(trace_path=path)
    trace.open()
    trace.write(b"foo")
    trace.read(3)
    trace.read(5)
    trace.close()

    content = (tmp_path / "trace.txt").read_text(encoding="utf-8")
    assert "# Serial trace" in content
    assert "foo" in content          # the written bytes' ASCII column
    assert "R # timeout" in content  # the empty read
    assert "Trace ended at" in content


@mock.patch("serial.Serial.open")
@mock.patch("serial.Serial.write")
@mock.patch("serial.Serial.read")
def test_trace_failure_never_breaks_communication(
    mock_read, mock_write, mock_open, tmp_path
):
    mock_read.return_value = b"x"
    trace = TracingSerial(trace_path=str(tmp_path / "trace.txt"))
    trace.open()
    # Force the trace file's writelines to blow up; comms must continue.
    trace._tracef = mock.Mock()
    trace._tracef.writelines.side_effect = OSError("disk full")
    trace.read(1)            # triggers the failing writelines
    assert trace._tracef is None  # trace abandoned, not re-raised
    trace.write(b"bar")      # must not raise even with no trace file
    trace.close()
