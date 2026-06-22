"""UI selection at startup.

The default front end is chosen by platform — the webview UI on macOS (so
VoiceOver reads the web grid) and the native UI everywhere else (so NVDA reads
the native ``wx.ListCtrl`` grid). Explicit ``--webview`` / ``--native`` flags
override the platform default either way.
"""

from main import parse_mode


def test_platform_default_macos_is_webview():
    assert parse_mode([], platform="darwin") == "webview"
    assert parse_mode(["--debug"], platform="darwin") == "webview"


def test_platform_default_non_macos_is_native():
    assert parse_mode([], platform="win32") == "native"
    assert parse_mode([], platform="linux") == "native"
    assert parse_mode(["--debug"], platform="win32") == "native"


def test_explicit_flags_override_platform():
    # --webview wins even on a platform that would otherwise default to native.
    assert parse_mode(["--webview"], platform="win32") == "webview"
    assert parse_mode(["--webview", "--debug"], platform="win32") == "webview"
    # --native wins even on macOS, which would otherwise default to webview.
    assert parse_mode(["--native"], platform="darwin") == "native"
    assert parse_mode(["--native", "--debug"], platform="darwin") == "native"
