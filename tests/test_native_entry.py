"""UI selection at startup.

The native UI is the default on every platform: its
``wx.dataview.DataViewListCtrl`` grid is the native NSTableView on macOS (read by
VoiceOver) and wx's generic custom-drawn control on Windows (exposed to MSAA so
NVDA reads it). The webview UI stays available via ``--webview`` while it is retired;
``--native`` forces the native UI explicitly. ``--webview`` still parses to
"webview", but the webview UI is retired and no longer imports against
wx-accessible-grid 0.8.0, so ``main()`` fails over to the native UI instead of
crashing (see ``test_webview_falls_back_to_native_when_unimportable``).
"""

import sys

import main as main_mod
from main import parse_mode


def test_platform_default_is_native_everywhere():
    assert parse_mode([], platform="darwin") == "native"
    assert parse_mode([], platform="win32") == "native"
    assert parse_mode([], platform="linux") == "native"
    assert parse_mode(["--debug"], platform="darwin") == "native"
    assert parse_mode(["--debug"], platform="win32") == "native"


def test_explicit_flags_override_default():
    # --webview opts back into the webview UI on any platform, including macOS.
    assert parse_mode(["--webview"], platform="darwin") == "webview"
    assert parse_mode(["--webview", "--debug"], platform="win32") == "webview"
    # --native is the default but still honored explicitly.
    assert parse_mode(["--native"], platform="darwin") == "native"
    assert parse_mode(["--native", "--debug"], platform="win32") == "native"


def test_webview_falls_back_to_native_when_unimportable(monkeypatch):
    """`--webview` must not crash now that the webview UI is retired and no longer
    imports. `main()` should catch the ImportError and launch the native UI."""
    import vrp.native.app as native_app

    calls = {}
    # `main()` does `from vrp.native.app import run`, which binds the module's
    # current `run` attribute — so patching it here is what gets called.
    monkeypatch.setattr(native_app, "run", lambda **kw: calls.setdefault("native", kw))
    monkeypatch.setattr(sys, "argv", ["main.py", "--webview"])

    # Should not raise, despite vrp.app being unimportable.
    main_mod.main()

    assert "native" in calls  # fell back to the native UI
