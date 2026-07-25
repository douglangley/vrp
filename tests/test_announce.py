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


# -- the speak_messages gate ----------------------------------------------


def test_speech_is_enabled_by_default():
    """Default ON: with no live region and a status bar NVDA won't read
    spontaneously, speech off means announcements are never heard."""
    spoken, speak = _recorder()
    a = Announcer(set_status=lambda s: None, speak=speak)
    assert a.speech_enabled is True
    a.announce("Saved")
    assert spoken == [("Saved", False)]


def test_disabled_speech_still_writes_the_status_bar():
    statuses = []
    spoken, speak = _recorder()
    a = Announcer(set_status=statuses.append, speak=speak, speech_enabled=False)
    a.announce("Moved 3 channels up")
    assert statuses == ["Moved 3 channels up"]
    assert spoken == []


def test_disabled_speech_silences_even_assertive_announcements():
    """Errors are announcements too — the user asked for no speech."""
    spoken, speak = _recorder()
    a = Announcer(set_status=lambda s: None, speak=speak, speech_enabled=False)
    a.announce("Save failed", assertive=True)
    assert spoken == []


def test_always_speak_ignores_the_gate():
    """The grid cell cursor's only voice. If the pref could silence it, Left/
    Right navigation would announce nothing at all — the bug the pref must
    never be able to cause."""
    spoken, speak = _recorder()
    a = Announcer(set_status=lambda s: None, speak=speak, speech_enabled=False)
    a.announce("146.5200, Frequency", assertive=True, always_speak=True)
    assert spoken == [("146.5200, Frequency", True)]


def test_always_speak_still_writes_the_status_bar():
    statuses = []
    a = Announcer(set_status=statuses.append, speak=None, speech_enabled=False)
    a.announce("146.5200, Frequency", always_speak=True)
    assert statuses == ["146.5200, Frequency"]


def test_set_speech_enabled_toggles_at_runtime():
    """Preferences applies immediately, so the confirmation it speaks (or
    doesn't) reflects the choice just made — no restart."""
    spoken, speak = _recorder()
    a = Announcer(set_status=lambda s: None, speak=speak)
    a.set_speech_enabled(False)
    a.announce("quiet")
    assert spoken == []
    a.set_speech_enabled(True)
    a.announce("loud")
    assert spoken == [("loud", False)]
    assert a.speech_enabled is True


def test_set_speech_enabled_does_not_gag_always_speak():
    """Turning announcements off at runtime must not silence the cell cursor."""
    spoken, speak = _recorder()
    a = Announcer(set_status=lambda s: None, speak=speak)
    a.set_speech_enabled(False)
    a.announce("cell", always_speak=True)
    assert spoken == [("cell", False)]
