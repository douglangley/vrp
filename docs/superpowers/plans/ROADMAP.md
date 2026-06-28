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
- ◐ Retire the webview channel-grid stack. The native UI is now the default on
  every platform (PROGRESS_LOG "2026-06-25"), so this is unblocked in principle
  — gated only on the owed VoiceOver hand pass on the native grid above. Plan:
  - Decide the webview's future. The current direction is to **repurpose** the
    `wx-accessible-webview` host for in-app **help/docs** rendering rather than
    delete it outright; the channel-grid pieces (`AccessibleGrid`,
    `vrp/channel_grid_model.py`, `vrp/views.py`, `templates/`, `static/`) are
    what gets retired.
  - **Partly done (2026-06-27, "graceful for now"):** deleted the dead webview
    channel-grid files `vrp/channel_grid_model.py` and `tools/grid_preview.py`;
    `main.py --webview` now fails over to the native UI (it no longer imports).
    `vrp/app.py`, `vrp/views.py`, `templates/`, `static/` are kept for the
    help/docs role. Still to do: strip the dead channel-grid code out of
    `vrp/app.py` (or build the help/docs role), gated on the VoiceOver pass.
