"""Unit test for MainWindow._now_at_phrase (Phase 5.3).

The move/copy handlers all share one phrase for where screen-reader focus
landed; this locks its two forms (single channel vs. a block). It's a pure
@staticmethod, so no wx.App/frame is needed — but importing MainWindow pulls in
wx, so skip when wx is unavailable."""

import pytest

pytest.importorskip("wx")

from vrp.native.main_window import MainWindow  # noqa: E402


def test_single_channel_phrase():
    assert MainWindow._now_at_phrase([7]) == "Now on channel 7."


def test_block_phrase():
    assert (
        MainWindow._now_at_phrase([3, 4, 5])
        == "Now at channels 3 to 5, on channel 3."
    )
