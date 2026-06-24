"""Tests for live submodel detection before a download (chirp_backend.radio).

No hardware: the pipe is a Mock and the fake driver classes' detect_from_serial
exercise each branch CHIRP defines — returns a class, raises
NotImplementedError, or raises errors.RadioError.
"""

from unittest import mock

import pytest

from chirp import errors
from chirp_backend import radio as radio_backend


class _DetectsOther:
    """detect_from_serial reports a different (detected) class."""

    @classmethod
    def detect_from_serial(cls, pipe):
        return _DetectedVariant


class _DetectedVariant:
    VENDOR = "Acme"
    MODEL = "Detected-9000"


class _NoDetection:
    """The common case: driver has no serial detection."""

    @classmethod
    def detect_from_serial(cls, pipe):
        raise NotImplementedError()


class _DetectionFails:
    """Detection ran against the radio and explicitly failed."""

    @classmethod
    def detect_from_serial(cls, pipe):
        raise errors.RadioError("wrong radio on this port")


def test_detect_returns_the_detected_class():
    result = radio_backend._detect_radio_class(_DetectsOther, mock.Mock())
    assert result is _DetectedVariant


def test_detect_keeps_pick_when_not_implemented():
    result = radio_backend._detect_radio_class(_NoDetection, mock.Mock())
    assert result is _NoDetection


def test_detect_propagates_radio_error():
    # A real detection failure must NOT silently fall back to the user's pick.
    with pytest.raises(errors.RadioError):
        radio_backend._detect_radio_class(_DetectionFails, mock.Mock())


def test_download_rejects_non_clone_mode_radio(monkeypatch):
    """A live (non-clone) radio fails clearly, before any port is opened."""
    from chirp import directory

    class _LiveRadio:  # not a CloneModeRadio subclass
        VENDOR = "Acme"
        MODEL = "Live-1"

    monkeypatch.setattr(directory, "get_radio", lambda _id: _LiveRadio)
    opened = []
    monkeypatch.setattr(
        radio_backend, "_open_radio_serial",
        lambda *a, **k: opened.append(True),
    )

    ok, message = radio_backend.download_from_radio(
        "COM4", "any_id", lambda c, t, m: None
    )
    assert ok is False
    assert "live connection" in message
    assert opened == []  # guarded before the serial port was touched
