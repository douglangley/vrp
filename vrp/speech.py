"""Supplemental speech via prism (prismatoid bindings).

The accessible webview conveys almost everything through semantic HTML and
ARIA live regions, which the user's screen reader announces. A few things a
screen reader cannot infer from the DOM alone — for example a transient
confirmation that does not move focus, or progress on a long serial operation
the user is waiting through — are better spoken directly. ``Speaker`` is a thin
wrapper over prism for exactly those cases.

It degrades gracefully: if no speech backend is available (no screen reader /
TTS installed, or running in CI), every method becomes a no-op rather than
raising, so the UI never breaks because speech is unavailable.
"""

from __future__ import annotations

import logging

LOG = logging.getLogger(__name__)


class Speaker:
    """Lazily-initialised wrapper around a prism speech backend."""

    def __init__(self) -> None:
        self._backend = None
        self._tried = False

    def _ensure_backend(self):
        """Acquire the best available backend once; cache the result."""
        if self._tried:
            return self._backend
        self._tried = True
        try:
            import prism

            ctx = prism.Context()
            # backends_count is an int property, not a method.
            if int(ctx.backends_count) <= 0:
                LOG.info("prism: no speech backends available; speech disabled")
                return None
            self._backend = ctx.create_best()
            LOG.info("prism: using backend %s", self._safe_name(self._backend))
        except Exception as exc:  # pragma: no cover - environment dependent
            # Missing TTS, no audio device, import failure, etc. Never fatal.
            LOG.warning("prism: speech unavailable (%s); continuing silent", exc)
            self._backend = None
        return self._backend

    @staticmethod
    def _safe_name(backend) -> str:
        try:
            return backend.name()
        except Exception:
            return repr(backend)

    def speak(self, text: str, interrupt: bool = False) -> None:
        """Speak ``text``. No-op if no backend is available."""
        backend = self._ensure_backend()
        if backend is None or not text:
            return
        try:
            backend.speak(text, interrupt=interrupt)
        except Exception as exc:  # pragma: no cover - environment dependent
            LOG.warning("prism: speak failed (%s)", exc)

    def stop(self) -> None:
        """Stop any in-progress speech. No-op if no backend is available."""
        backend = self._ensure_backend()
        if backend is None:
            return
        try:
            backend.stop()
        except Exception as exc:  # pragma: no cover - environment dependent
            LOG.warning("prism: stop failed (%s)", exc)
