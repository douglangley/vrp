"""Byte-level serial trace for debugging radio clone sessions.

Mirrors the logic of ``chirp/chirp/wxui/serialtrace.py`` (same GPLv3 codebase),
ported here as VRP's own rather than imported, because ``chirp_backend`` must
never depend on ``chirp.wxui`` (the inaccessible GUI module we replace — see
CLAUDE.md) and must stay free of any dependency on the ``vrp`` UI layer.

A ``TracingSerial`` behaves exactly like ``serial.Serial`` but hex-dumps every
byte written and read — with timestamps and explicit ``# timeout`` markers —
to a trace file. It's used only when debugging is enabled (wired in
``chirp_backend.radio``); a normal clone uses a plain ``serial.Serial``. Tracing
is strictly best-effort: any failure writing the trace is logged and the trace
abandoned, and must never interrupt the real serial communication with the
radio.

The upstream version (un-ported here) also carries a baud-rate-vs-timeout
warning decorator and a rolling history of the last 10 trace files; VRP needs
neither — one trace per clone session, overwritten each time, is enough.
"""

from __future__ import annotations

import datetime
import logging
import os
import time

import serial

from chirp import util

LOG = logging.getLogger(__name__)

_TRACE_FILENAME = "serial-trace.txt"


def default_trace_path() -> str:
    """Path of the per-session serial trace file (overwritten each session).

    Written to the current working directory — i.e. the project root when the
    app is launched from there with ``uv run python main.py --debug`` — so the
    trace is right where you're working and trivially found (and readable by a
    tool/agent helping debug). For an end user launching the packaged exe by
    double-clicking, this is the exe's directory, which is fine for a
    debug-only artifact. Overridable per-instance via ``TracingSerial(trace_path=...)``.
    """
    return os.path.join(os.getcwd(), _TRACE_FILENAME)


def get_trace_entry(direction: str, start_ts: float, data: bytes) -> list[str]:
    """Format the hexdump trace line(s) for one write ('W') or read ('R')."""
    loglines = util.hexprint(data, block_size=16).split("\n")
    ts = time.monotonic() - start_ts
    loglines = [
        "%7.3f %s %s%s" % (ts, direction, line, os.linesep)
        for line in loglines
        if line.strip()
    ]
    if not loglines and direction == "R" and not data:
        # An empty read is a timeout — denote it explicitly for clarity.
        loglines = ["%7.3f %s # timeout%s" % (ts, direction, os.linesep)]
    return loglines


class TracingSerial(serial.Serial):
    """A ``serial.Serial`` that hex-dumps all traffic to a trace file.

    Always use this in place of ``serial.Serial`` for radio clones — CHIRP
    drivers call ``radio.pipe.log(...)`` directly during sync (8 driver
    families do), because CHIRP's own GUI always wraps the port in its
    ``SerialTrace``; a plain ``serial.Serial`` has no ``.log()`` and the clone
    crashes with ``AttributeError``. The ``.log()``/write/read trace methods
    are always present here, but only actually write to a file when
    ``trace_enabled`` is set (i.e. under ``--debug``); otherwise they are
    no-ops and this behaves like a plain ``serial.Serial``.
    """

    def __init__(
        self, *args, trace_path: str | None = None,
        trace_enabled: bool = True, **kwargs,
    ) -> None:
        self._tracef = None
        self._trace_start = 0.0
        self._trace_path = trace_path or default_trace_path()
        self._trace_enabled = trace_enabled
        super().__init__(*args, **kwargs)

    def open(self) -> None:
        super().open()
        if not self._trace_enabled:
            return  # methods stay present, but no trace file is written
        try:
            os.makedirs(os.path.dirname(self._trace_path), exist_ok=True)
            self._trace_start = time.monotonic()
            self._tracef = open(self._trace_path, "w", encoding="utf-8")
            now = datetime.datetime.now()
            self.log("Serial trace %s started at %s" % (self, now.isoformat()))
            LOG.info("Serial trace file created: %s", self._trace_path)
        except Exception as e:  # noqa: BLE001 — tracing is best-effort
            LOG.error("Failed to create serial trace file: %s", e)
            self._tracef = None

    def write(self, data):
        result = super().write(data)
        if self._tracef:
            try:
                self._tracef.writelines(
                    get_trace_entry("W", self._trace_start, data)
                )
            except Exception as e:  # noqa: BLE001
                LOG.error("Failed to write to serial trace file: %s", e)
                self._tracef = None
        return result

    def read(self, size=1):
        data = super().read(size)
        if self._tracef:
            try:
                self._tracef.writelines(
                    get_trace_entry("R", self._trace_start, data)
                )
            except Exception as e:  # noqa: BLE001
                LOG.error("Failed to write to serial trace file: %s", e)
                self._tracef = None
        return data

    def close(self) -> None:
        super().close()
        if self._tracef:
            try:
                now = datetime.datetime.now()
                self.log("Trace ended at %s" % now.isoformat())
                self._tracef.close()
                LOG.info("Serial trace file closed: %s", self._trace_path)
            except Exception as e:  # noqa: BLE001
                LOG.error("Failed to close serial trace file: %s", e)
            finally:
                self._tracef = None

    def log(self, message: str) -> None:
        """Annotate the trace file with a freeform ``# message`` line."""
        if self._tracef:
            try:
                self._tracef.write("# %s\n" % message)
            except Exception as e:  # noqa: BLE001
                LOG.error("Failed to write log message to trace file: %s", e)
                self._tracef = None
