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

# Kept identical to vrp/config.py's directory name on purpose: the trace file
# lives next to the user config so there's one obvious place to find it. The
# resolution is duplicated (not imported from vrp.config) so chirp_backend
# stays a pure, UI-agnostic layer that vrp depends on, not the reverse.
_CONFIG_DIRNAME = "OpenMemoryWriter"
_TRACE_FILENAME = "serial-trace.txt"


def _config_dir() -> str:
    if os.name == "nt":
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
    else:
        base = os.environ.get("XDG_CONFIG_HOME") or os.path.join(
            os.path.expanduser("~"), ".config"
        )
    return os.path.join(base, _CONFIG_DIRNAME)


def default_trace_path() -> str:
    """Path of the per-session serial trace file (overwritten each session)."""
    return os.path.join(_config_dir(), _TRACE_FILENAME)


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
    """A ``serial.Serial`` that hex-dumps all traffic to a trace file."""

    def __init__(self, *args, trace_path: str | None = None, **kwargs) -> None:
        self._tracef = None
        self._trace_start = 0.0
        self._trace_path = trace_path or default_trace_path()
        super().__init__(*args, **kwargs)

    def open(self) -> None:
        super().open()
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
