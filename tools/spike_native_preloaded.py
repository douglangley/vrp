"""Spike: launch the NATIVE wx UI (DataViewListCtrl grid) with a radio image
pre-loaded, so the production channel grid can be tested under VoiceOver with
real data. Throwaway harness — not production. Run:

    uv run python tools/spike_native_preloaded.py

VoiceOver test checklist (turn VO on with Cmd+F5):
  1. Focus lands in the "Memory channels" table — does VO announce a table and
     the first row's cells (Ch #, Frequency, Name, ...) with column headers?
  2. Arrow up/down through rows: each row's cells read, including "(empty)" for
     empty channels.
  3. Channels menu > Go to channel… (Ctrl+Shift+G), enter a number: does VO land
     on and read that row exactly once (no double/no speech)?
  4. Select a row, Channels menu > Delete channel(s) (Del): confirm prompt reads,
     deletion announced, focus lands on the next row.
  5. Shift+Arrow to extend a selection: the "N channels selected" count is heard.
  6. Channels menu > Move up / Move down (Ctrl+Shift+Up/Down): moved block stays
     selected and the landing row is read.
"""

import sys

sys.path.insert(0, "/Users/michaelbabcock/code/Versatile-Radio-Programmer")

import vrp  # noqa: F401,E402  (side effect: makes vendored chirp importable)
import wx  # noqa: E402
from chirp_backend import radio as radio_backend  # noqa: E402
from vrp.native.main_window import MainWindow  # noqa: E402

IMAGE = "chirp/tests/images/Baofeng_UV-5R.img"


def main() -> None:
    app = wx.App(False)
    app.SetAppName("VRP (native spike)")
    win = MainWindow()
    win.Show()
    win.Raise()

    def _preload() -> None:
        ok, msg = radio_backend.load_image(IMAGE)
        print(f"PRELOAD ok={ok} msg={msg}", file=sys.stderr)
        if ok:
            win._load_into_grid()  # set_state + title + menu state, as on_open does
            low = radio_backend.get_state().memory_bounds[0]
            win.grid.select_channels([low])
            win.grid.focus_channel(low)

    wx.CallLater(300, _preload)
    app.MainLoop()


if __name__ == "__main__":
    main()
