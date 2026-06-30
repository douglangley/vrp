# VRP Master Plan / Roadmap

This is the forward-looking, kept-short list of what's left. History lives in
`PROGRESS_LOG.md`; the feature-by-feature matrix lives in
`docs/chirp-feature-coverage.md`; this file is just priority + status + links
to detailed plans. When a detailed plan exists for an item, it's a dated file
in this same folder (`docs/superpowers/plans/<date>-<topic>.md`) — link it
here rather than duplicating its content.

Status marks: ☐ not started · ◐ in progress · ☑ done.

## Current priority

- ☑ **Serial port hardware verification.** Both **Download and Upload are
  verified on real hardware** (Baofeng UV-5R Mini over COM4 — download
  2026-06-23, upload 2026-06-24), and the serial backend was hardened against
  CHIRP's reference clone code (flow-control setup, submodel detection, driver
  prompts, gettext `_` shim, clone-mode guard, byte-level trace; plus a
  desktop-a11y/wx review of the dialogs). Remaining is just **broader
  coverage**, not a blocker: confirmation on a second machine/port (handed to a
  COM10 tester) and models beyond the UV-5R Mini. Detailed plan + findings:
  [2026-06-23-serial-hardware-verification.md](2026-06-23-serial-hardware-verification.md).

## Other open work

Accessibility / screen-reader passes owed (no blocker, just need a hand pass):
- ☐ NVDA-on-Windows pass for the native UI (menu accelerators, grid
  navigation/selection, dialog focus) — must be **re-run** after the grid
  migrated to `DataViewListCtrl` (PROGRESS_LOG "2026-06-25"), since that changes
  the control NVDA reads.
- ☐ **VoiceOver hand pass on the native UI's `DataViewListCtrl` grid** — the
  migration (PROGRESS_LOG "2026-06-25") is designed to read under VoiceOver via
  NSTableView, but the actual on-device VoiceOver pass on macOS is still owed
  and is what makes "native everywhere" final.
- ☐ NVDA pass on the radio settings editor (Treebook tree↔panel F6 hop, 
  non-1-step SpinCtrls).
- ☐ NVDA pass on the banks editor (membership readout, checkbox/radiobox state).

Query sources (Phase 7):
- ☐ Live network test for AMSAT/SatNOGS/DMR-MARC/mapy73.pl (no network
  available in past dev sessions).
- ◐ RepeaterBook — needs a dynamic country→state cascade control.
- ◐ RadioReference — needs a credentials/login param form.
- ◐ przemienniki.net / .eu — needs band/mode code mapping + coordinates.

Smaller deferred items (chirp-feature-coverage.md "☐"/"◐" rows):
- ☐ Bank renaming + "channels in a bank" overview (Phase 6.1).
- ☑ Cut/Paste clipboard (done 2026-06-27 — native grid row clipboard).
- ☐ File menu: New (empty image), New Window, Open Stock Config, Load
  Module — all need a model-picker UX decision first.
- ☐ View menu: font size / large font, language.
- ☑ Auto edits + band plan (done 2026-06-28): offset suggestion (always on,
  magnitude only), opt-in "Apply band-plan defaults" (mode/step/tone), and the
  band-plan **region** chosen in Preferences (not the Radio menu — it's a global
  setting). See PROGRESS_LOG and `chirp_backend/bandplan.py`.
- ☐ Developer-only items (reload driver/module, serial trace, bug report) —
  Phase 10, low priority.

New since 2026-06-28 (VRP-only enhancements, done — see PROGRESS_LOG):
- ☑ Favorite radios (Radio ▸ Favorite radios… manager + Download All/Favorites
  toggle; `vrp/serial_dialogs.py`, `vrp/config.py`).
- ☑ Radio Info as a read-only edit box + "Radio details…" in the browsing
  dialogs (`vrp/info_dialog.py`, `chirp_backend.radio.describe_model`).
- ☑ Type-ahead model/favorites lists (`RadioListView`, a wx.ListCtrl) — NVDA on
  Windows; **macOS VoiceOver of these serial dialogs is unverified** and
  wx.ListCtrl is generic there, so revisit the control if the macOS pass covers
  them.

Platform follow-through:
- ☐ macOS run-from-source smoke test (`run-mac.sh` + full suite) — flagged
  as unverified in PROGRESS_LOG "2026-06-21 — Per-OS run scripts".
- ☑ **Retire the webview UI — done (2026-06-29).** The whole webview stack was
  removed: `vrp/app.py`, `vrp/views.py`, `vrp/html.py`, `templates/`, `static/`,
  `tests/test_views.py`, the `--webview`/`--native` mode flags, and the
  `wx-accessible-webview`, `wx-accessible-menubar`, and `jinja2` dependencies. On
  inspection it wasn't a reusable "host" — it was a full alternate front end for
  the editable channel grid (1,642-line `app.py` duplicating every command) and
  it no longer even imported. If in-app **help/docs** want an HTML view later,
  build a small purpose-made read-only `wx.html2.WebView` viewer (wxPython core,
  no extra dependency) rather than reviving this. See PROGRESS_LOG "2026-06-29".
