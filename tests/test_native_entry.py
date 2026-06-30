"""Startup entry point.

VRP has a single, native UI (``vrp/native/``): its
``wx.dataview.DataViewListCtrl`` grid is the native NSTableView on macOS (read by
VoiceOver) and wx's generic custom-drawn control on Windows (exposed to MSAA so
NVDA reads it). The webview UI that once existed behind ``--webview`` was retired
and removed (PROGRESS_LOG.md "2026-06-29"), so ``main()`` just launches the
native UI.
"""

import sys

import main as main_mod


def test_main_launches_native_ui(monkeypatch):
    """`main()` launches the native UI."""
    import vrp.native.app as native_app

    calls = {}
    # `main()` does `from vrp.native.app import run`, which binds the module's
    # current `run` attribute — so patching it here is what gets called.
    monkeypatch.setattr(native_app, "run", lambda **kw: calls.setdefault("native", kw))
    monkeypatch.setattr(sys, "argv", ["main.py"])

    main_mod.main()

    assert calls.get("native") == {"debug": False}


def test_debug_flag_passes_through(monkeypatch):
    import vrp.native.app as native_app

    calls = {}
    monkeypatch.setattr(native_app, "run", lambda **kw: calls.setdefault("native", kw))
    monkeypatch.setattr(sys, "argv", ["main.py", "--debug"])

    main_mod.main()

    assert calls.get("native") == {"debug": True}
