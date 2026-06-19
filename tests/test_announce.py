"""Unit tests for the desktop Announcer (no wx — uses fakes)."""

from vrp.native.announce import Announcer


def test_announce_sets_status_and_speaks():
    statuses, spoken = [], []
    a = Announcer(set_status=statuses.append, speak=spoken.append)
    a.announce("Moved 3 channels up")
    assert statuses == ["Moved 3 channels up"]
    assert spoken == ["Moved 3 channels up"]


def test_announce_tolerates_missing_speech():
    statuses = []
    a = Announcer(set_status=statuses.append, speak=None)
    a.announce("Saved")  # must not raise without a speak backend
    assert statuses == ["Saved"]


def test_announce_ignores_empty_message():
    statuses, spoken = [], []
    a = Announcer(set_status=statuses.append, speak=spoken.append)
    a.announce("")
    assert statuses == [] and spoken == []
