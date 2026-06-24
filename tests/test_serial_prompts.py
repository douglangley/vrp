"""Tests for driver clone prompts (backend flattening + native dialog flow).

Backend tests (no wx) cover _prompts_dict / get_clone_prompts*; the UI tests
mock wx.MessageBox so they assert the dialog sequence without popping real
modal dialogs, and skip cleanly where wx isn't importable.
"""

import pytest

from chirp import chirp_common
from chirp_backend import radio as radio_backend


class _AllPrompts:
    experimental = "exp text"
    info = "info text"
    pre_download = "download steps"
    pre_upload = "upload steps"


class _RadioWithPrompts:
    @classmethod
    def get_prompts(cls):
        return _AllPrompts()


class _RadioNoPrompts:
    @classmethod
    def get_prompts(cls):
        return chirp_common.RadioPrompts()  # all attributes default to None


# -- backend: flattening + direction mapping --------------------------------

def test_prompts_dict_download_direction():
    d = radio_backend._prompts_dict(_RadioWithPrompts, upload=False)
    assert d == {
        "experimental": "exp text",
        "info": "info text",
        "pre": "download steps",
    }


def test_prompts_dict_upload_uses_pre_upload():
    d = radio_backend._prompts_dict(_RadioWithPrompts, upload=True)
    assert d["pre"] == "upload steps"


def test_prompts_dict_all_none_when_unset():
    d = radio_backend._prompts_dict(_RadioNoPrompts, upload=False)
    assert d == {"experimental": None, "info": None, "pre": None}


def test_get_clone_prompts_unknown_id_returns_all_none():
    # A bad id must not raise — a missing prompt can't block a download.
    d = radio_backend.get_clone_prompts("No_Such_Driver_Id")
    assert d == {"experimental": None, "info": None, "pre": None}


def test_get_clone_prompts_for_loaded_radio_with_no_radio():
    radio_backend.unload()
    d = radio_backend.get_clone_prompts_for_loaded_radio()
    assert d == {"experimental": None, "info": None, "pre": None}


def test_get_clone_prompts_real_driver_uses_gettext_without_raising():
    # Regression: real driver get_prompts() bodies call the gettext builtin _()
    # directly (CHIRP's CLI/GUI install it; VRP must too via _ensure_chirp).
    # The Task-4 fakes used plain strings and missed this NameError. The UV-5R
    # Mini (chirp.drivers.baofeng_uv17Pro.UV5RMini) sets _()-wrapped
    # experimental + pre_download text, so it exercises the path.
    prompts = radio_backend.get_clone_prompts("Baofeng_UV-5R_Mini")
    assert set(prompts) == {"experimental", "info", "pre"}
    assert isinstance(prompts["experimental"], str) and prompts["experimental"]
    assert isinstance(prompts["pre"], str) and prompts["pre"]


# -- UI: native dialog sequence (wx.MessageBox mocked) ----------------------

def test_show_radio_prompts_runs_all_in_order(monkeypatch):
    wx = pytest.importorskip("wx")
    from vrp.serial_dialogs import show_radio_prompts

    calls = []
    answers = iter([wx.YES, wx.OK, wx.OK])

    def fake(message, caption, style, parent=None):
        calls.append(caption)
        return next(answers)

    monkeypatch.setattr(wx, "MessageBox", fake)
    ok = show_radio_prompts(
        None, {"experimental": "e", "info": "i", "pre": "p"},
        pre_title="Upload instructions",
    )
    assert ok is True
    assert calls == ["Experimental driver", "Radio information",
                     "Upload instructions"]


def test_show_radio_prompts_declining_experimental_short_circuits(monkeypatch):
    wx = pytest.importorskip("wx")
    from vrp.serial_dialogs import show_radio_prompts

    calls = []

    def fake(message, caption, style, parent=None):
        calls.append(caption)
        return wx.NO

    monkeypatch.setattr(wx, "MessageBox", fake)
    ok = show_radio_prompts(None, {"experimental": "e", "info": "i", "pre": "p"})
    assert ok is False
    assert calls == ["Experimental driver"]  # info/pre never shown


def test_show_radio_prompts_cancel_on_info_stops(monkeypatch):
    wx = pytest.importorskip("wx")
    from vrp.serial_dialogs import show_radio_prompts

    calls = []

    def fake(message, caption, style, parent=None):
        calls.append(caption)
        return wx.CANCEL

    monkeypatch.setattr(wx, "MessageBox", fake)
    ok = show_radio_prompts(None, {"experimental": None, "info": "i", "pre": "p"})
    assert ok is False
    assert calls == ["Radio information"]


def test_show_radio_prompts_no_prompts_is_noop(monkeypatch):
    wx = pytest.importorskip("wx")
    from vrp.serial_dialogs import show_radio_prompts

    calls = []
    monkeypatch.setattr(wx, "MessageBox", lambda *a, **k: calls.append(1))
    ok = show_radio_prompts(
        None, {"experimental": None, "info": None, "pre": None}
    )
    assert ok is True
    assert calls == []
