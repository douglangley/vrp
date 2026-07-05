"""get_speaker() returns one shared Speaker (Phase 5.2).

The main window and every dialog that speaks share this instance so the prism
backend is acquired once, not once per window."""

from vrp import speech


def test_get_speaker_is_singleton():
    a = speech.get_speaker()
    b = speech.get_speaker()
    assert a is b
    assert isinstance(a, speech.Speaker)
