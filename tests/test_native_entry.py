"""The native UI is the default; --webview opts into the legacy webview app."""

from main import parse_mode


def test_default_is_native():
    assert parse_mode([]) == "native"
    assert parse_mode(["--debug"]) == "native"


def test_webview_flag_selects_webview():
    assert parse_mode(["--webview"]) == "webview"
    assert parse_mode(["--webview", "--debug"]) == "webview"
