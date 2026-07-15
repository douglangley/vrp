"""Desktop announcement helper for the native UI.

The web app used an ARIA live region; off the web the equivalents are (1) the
status bar, which screen readers can read on demand, and (2) prism speech when
available. The PRIMARY announcement is still focus management (handlers move
focus to the result row); this covers operation summaries and errors that have
no natural focus target.

**Two kinds of speech, only one of them optional.** The status bar is not read
spontaneously by NVDA, so prism is the only thing that makes an announcement
*heard*:

- *Announcements* (operation results, errors, progress, selection counts) are
  spoken in addition to what the screen reader already says as focus moves, so
  a user who finds the second voice redundant can turn them off — that is the
  ``speak_messages`` preference, wired here as ``speech_enabled``. Default ON:
  with it off, these reach the user only if they go and read the status bar.
- *Content with no other voice* — chiefly the grid's Left/Right cell cursor,
  which wx's generic DataViewCtrl announces not at all on Windows — passes
  ``always_speak=True`` and ignores the preference. Gating it would make cell
  navigation silent, which is the bug the preference must never be able to
  cause (see PROGRESS_LOG "2026-07-15 — prism"). It never doubles up with the
  screen reader precisely because nothing else announces it.

Decoupled from wx (takes plain callables) so it is unit-testable headless.
"""

from __future__ import annotations

from typing import Callable, Optional


class Announcer:
    def __init__(
        self,
        set_status: Callable[[str], None],
        speak: Optional[Callable[[str, bool], None]] = None,
        speech_enabled: bool = True,
    ) -> None:
        self._set_status = set_status
        self._speak = speak
        self._speech_enabled = bool(speech_enabled)

    @property
    def speech_enabled(self) -> bool:
        return self._speech_enabled

    def set_speech_enabled(self, enabled: bool) -> None:
        """Turn spoken announcements on/off (Preferences applies immediately).

        Does not affect ``always_speak=True`` callers.
        """
        self._speech_enabled = bool(enabled)

    def announce(
        self,
        message: str,
        *,
        assertive: bool = False,
        always_speak: bool = False,
    ) -> None:
        """Show ``message`` in the status bar and speak it (if speech exists).

        ``assertive=True`` (errors) interrupts any in-progress speech so the
        error is heard immediately. Non-assertive announcements do NOT interrupt,
        so they queue behind the screen reader's focus-driven row read instead of
        clipping it.

        ``always_speak=True`` speaks even when the user has turned spoken
        announcements off — for content the screen reader cannot announce by
        itself, so silencing it would leave nothing at all. The status bar is
        always written either way.
        """
        if not message:
            return
        self._set_status(message)
        if self._speak is None:
            return
        if not (self._speech_enabled or always_speak):
            return
        try:
            self._speak(message, assertive)
        except Exception:  # noqa: BLE001 — speech is best-effort, never fatal
            pass
