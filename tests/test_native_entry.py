"""The --native flag selects the native app without launching wx."""

from main import parse_mode


def test_native_flag_selects_native():
    assert parse_mode(["--native"]) == "native"
    assert parse_mode(["--native", "--debug"]) == "native"


def test_default_is_webview():
    assert parse_mode([]) == "webview"
    assert parse_mode(["--debug"]) == "webview"
