"""UI selection at startup.

The native UI is the default on every platform: its
``wx.dataview.DataViewListCtrl`` grid is the native NSTableView on macOS (read by
VoiceOver) and wx's generic custom-drawn control on Windows (exposed to MSAA so
NVDA reads it). The webview UI stays available via ``--webview`` while it is retired;
``--native`` forces the native UI explicitly.
"""

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
