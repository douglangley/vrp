"""Unit tests for the desktop Announcer (no wx — uses fakes)."""

from vrp.native.announce import Announcer


def _recorder():
    spoken = []
    def speak(message, interrupt=False):
        spoken.append((message, interrupt))
    return spoken, speak


def test_announce_sets_status_and_speaks_non_interrupting_by_default():
    statuses = []
    spoken, speak = _recorder()
    a = Announcer(set_status=statuses.append, speak=speak)
    a.announce("Moved 3 channels up")
    assert statuses == ["Moved 3 channels up"]
    assert spoken == [("Moved 3 channels up", False)]


def test_announce_assertive_interrupts():
    spoken, speak = _recorder()
    a = Announcer(set_status=lambda s: None, speak=speak)
    a.announce("Save failed", assertive=True)
    assert spoken == [("Save failed", True)]


def test_announce_tolerates_missing_speech():
    statuses = []
    a = Announcer(set_status=statuses.append, speak=None)
    a.announce("Saved")
    assert statuses == ["Saved"]


def test_announce_ignores_empty_message():
    statuses = []
    spoken, speak = _recorder()
    a = Announcer(set_status=statuses.append, speak=speak)
    a.announce("")
    assert statuses == [] and spoken == []
