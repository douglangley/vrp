"""Standalone diagnostic for prism speech, decoupled from the rest of VRP.

We've never directly verified that prism can speak through NVDA on this
machine — the "Ready" startup announcement (vrp/native/main_window.py) is
silent, and it's unclear whether the bug is in our wiring or in prism/NVDA
itself. This script isolates the question by speaking three ways, each
logged with a clear marker so you can tell from the log alone (without
needing to remember what you heard) which paths got as far as calling the
backend:

  1. Raw prism, no wx at all — calls prism directly, before any wx.App exists.
  2. Through vrp.speech.Speaker — same wrapper the app uses, still no wx.
  3. Inside a real wx.App, via wx.CallAfter after app.MainLoop() starts —
     mirrors exactly how vrp/native/main_window.py speaks "Ready" now.

Run it and listen for "one", "two", "three" (NVDA should announce each):

    uv run python tools/speak_test.py

Logs ONLY to logs/speak_test.log (gitignored — delete it freely to start
over), deliberately not to the console: printing progress to the console
while testing speech makes NVDA announce the printed text itself, which
competes with (and can swallow) the actual prism speech we're trying to
hear. The script prints nothing until it's completely done. The window
closes itself after the third phrase.
"""

from __future__ import annotations

import logging
import os
import sys
import time

# tools/ scripts can't `import vrp` via `uv run python tools/X.py` as-is —
# the project root (containing vrp/) isn't on sys.path unless the script
# lives there too (true for main.py, not for anything under tools/). This
# affects every script in tools/, not just this one; worth fixing project-
# wide separately. Patched locally here so this diagnostic actually runs.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import vrp  # noqa: F401, E402  (side effect: makes the vendored chirp importable)

LOG_DIR = os.path.join(os.path.dirname(__file__), "..", "logs")
LOG_PATH = os.path.join(LOG_DIR, "speak_test.log")

LOG = logging.getLogger("speak_test")


def _setup_logging() -> None:
    os.makedirs(LOG_DIR, exist_ok=True)
    # File only, deliberately no StreamHandler — see module docstring: console
    # output during the test gets announced by NVDA and drowns out the actual
    # prism speech we're trying to verify.
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[logging.FileHandler(LOG_PATH, mode="w", encoding="utf-8")],
    )


def _phase_1_raw_prism() -> None:
    LOG.info("--- Phase 1: raw prism, no wx ---")
    try:
        import prism

        ctx = prism.Context()
        LOG.info("backends_count=%s", ctx.backends_count)
        if int(ctx.backends_count) <= 0:
            LOG.warning("No prism backends available at all — stopping here.")
            return
        backend = ctx.create_best()
        # backend.name is a plain string property, not a method.
        name = getattr(backend, "name", None) or repr(backend)
        LOG.info("create_best() -> %s", name)
        LOG.info("Calling backend.speak('Phase one') now...")
        backend.speak("Phase one", interrupt=False)
        LOG.info("backend.speak() returned with no exception.")
    except Exception:
        LOG.exception("Phase 1 raised an exception")


def _phase_2_speaker_wrapper() -> None:
    LOG.info("--- Phase 2: vrp.speech.Speaker, still no wx ---")
    try:
        from vrp.speech import Speaker

        speaker = Speaker()
        LOG.info("Calling Speaker.speak('Phase two') now...")
        speaker.speak("Phase two", interrupt=False)
        LOG.info("Speaker.speak() returned. backend=%r", speaker._backend)
    except Exception:
        LOG.exception("Phase 2 raised an exception")


def _phase_3_inside_wx_app() -> None:
    LOG.info("--- Phase 3: inside a real wx.App, via wx.CallAfter after MainLoop() ---")
    import wx

    from vrp.speech import Speaker

    app = wx.App()
    frame = wx.Frame(None, title="speak_test phase 3")
    speaker = Speaker()

    def _speak_then_close():
        LOG.info("CallAfter fired - calling Speaker.speak('Phase three') now...")
        speaker.speak("Phase three", interrupt=False)
        LOG.info("Speaker.speak() returned for phase three.")
        # Give the backend a couple seconds to actually finish before we exit.
        wx.CallLater(2500, frame.Close)

    frame.Show()
    wx.CallAfter(_speak_then_close)
    app.MainLoop()
    LOG.info("wx.App.MainLoop() exited.")


def main() -> None:
    _setup_logging()
    LOG.info("speak_test starting. Log file: %s", os.path.abspath(LOG_PATH))
    _phase_1_raw_prism()
    time.sleep(5)
    _phase_2_speaker_wrapper()
    time.sleep(5)
    _phase_3_inside_wx_app()
    LOG.info("speak_test done.")
    # Only print after speech is fully over, so this line can't be announced
    # over any of the three phrases.
    print(f"Done. Log written to {os.path.abspath(LOG_PATH)}")


if __name__ == "__main__":
    main()
