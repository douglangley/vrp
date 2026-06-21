"""Desktop announcement helper for the native UI.

The web app used an ARIA live region; off the web the equivalents are (1) the
status bar, which screen readers can read on demand, and (2) prism speech when
available. The PRIMARY announcement is still focus management (handlers move
focus to the result row); this covers operation summaries and errors that have
no natural focus target.

Decoupled from wx (takes plain callables) so it is unit-testable headless.
"""

from __future__ import annotations

from typing import Callable, Optional


class Announcer:
    def __init__(
        self,
        set_status: Callable[[str], None],
        speak: Optional[Callable[[str, bool], None]] = None,
    ) -> None:
        self._set_status = set_status
        self._speak = speak

    def announce(self, message: str, *, assertive: bool = False) -> None:
        """Show ``message`` in the status bar and speak it (if speech exists).

        ``assertive=True`` (errors) interrupts any in-progress speech so the
        error is heard immediately. Non-assertive announcements do NOT interrupt,
        so they queue behind the screen reader's focus-driven row read instead of
        clipping it.
        """
        if not message:
            return
        self._set_status(message)
        if self._speak is not None:
            try:
                self._speak(message, assertive)
            except Exception:  # noqa: BLE001 — speech is best-effort, never fatal
                pass
