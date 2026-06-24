# VRP Master Plan / Roadmap

This is the forward-looking, kept-short list of what's left. History lives in
`PROGRESS_LOG.md`; the feature-by-feature matrix lives in
`docs/chirp-feature-coverage.md`; this file is just priority + status + links
to detailed plans. When a detailed plan exists for an item, it's a dated file
in this same folder (`docs/superpowers/plans/<date>-<topic>.md`) — link it
here rather than duplicating its content.

Status marks: ☐ not started · ◐ in progress · ☑ done.

## Current priority

- ◐ **Serial port hardware verification.** The Download from Radio / Upload
  to Radio commands (Phase 4) have never been run against real hardware in
  any dev session (no hardware available) — this is the most complex
  remaining unverified subsystem in the app. The user has a confirmed-working
  serial connection on COM4 (verified working with RT Systems software), so
  this is now unblocked. Detailed plan:
  [2026-06-23-serial-hardware-verification.md](2026-06-23-serial-hardware-verification.md).

## Other open work

Accessibility / screen-reader passes owed (no blocker, just need a hand pass):
- ☐ NVDA-on-Windows pass for the native UI (menu accelerators, grid
  navigation/selection, dialog focus) — owed since the native UI became the
  Windows/Linux default (PROGRESS_LOG "2026-06-21").
- ☐ VoiceOver hand pass on the webview UI's `wx-accessible-grid` 0.4.1
  (cell names, assertive selection/enter announcements) — owed since
  PROGRESS_LOG "2026-06-21".
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
- ☐ Cut/Paste clipboard semantics on the Edit menu (copy/move already cover
  the need; revisit only if actually wanted).
- ☐ File menu: New (empty image), New Window, Open Stock Config, Load
  Module — all need a model-picker UX decision first.
- ☐ View menu: font size / large font, language.
- ☐ Radio menu: Auto edits toggle, Select bandplan.
- ☐ Developer-only items (reload driver/module, serial trace, bug report) —
  Phase 10, low priority.

Platform follow-through:
- ☐ macOS run-from-source smoke test (`run-mac.sh` + full suite) — flagged
  as unverified in PROGRESS_LOG "2026-06-21 — Per-OS run scripts".
- ☐ Once the native UI is confirmed at parity on every platform: retire
  `vrp/app.py`, `vrp/views.py`, `vrp/html.py`, `vrp/channel_grid_model.py`,
  `templates/`, `static/`, and the `wx-accessible-webview`/
  `wx-accessible-menubar`/`wx-accessible-grid` dependencies; drop `--webview`.
  Blocked on the VoiceOver pass above — native `wx.ListCtrl` still doesn't
  read correctly under VoiceOver (PROGRESS_LOG "2026-06-21 — Platform-aware
  UI default").
