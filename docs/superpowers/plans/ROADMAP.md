# VRP Master Plan / Roadmap

This is the forward-looking, kept-short list of what's left. History lives in
`PROGRESS_LOG.md`; the feature-by-feature matrix lives in
`docs/chirp-feature-coverage.md`; this file is just priority + status + links
to detailed plans. When a detailed plan exists for an item, it's a dated file
in this same folder (`docs/superpowers/plans/<date>-<topic>.md`) — link it
here rather than duplicating its content.

Status marks: ☐ not started · ◐ in progress · ☑ done.

## Current priority

- ◐ **Generic cross-radio migration.** Phases 1–5 landed through 2026-07-24:
  direct
  cross-image Copy/Paste and `.img`/`.csv` Import share CHIRP's model-generic
  conversion, preserve partial success with per-channel accessible reports,
  safely turn cross-image/section Cut into Copy, and are one-step undoable.
  Static and dynamic CHIRP subdevices now have an accessible chooser for Open,
  Import, post-Download, and later section switching; parent Save/Settings/
  Upload ownership is retained. File Import can explicitly map one regular or
  named special source to a numbered or named-special target; bulk import never
  includes specials. Ordinary import and cross-image Paste now offer explicit,
  filterable bank mapping with exact-name suggestions, opt-in position
  matching, per-channel rollback, and memory+bank Undo/Redo. Verified with 479
  project tests, all 23 pinned subdevice parents (50 views), all 1,989 special
  slots across 70 targets, and all 70 bank models (54 mutable, 16 fixed)—all
  audits have zero unexpected failures.
  D-STAR migrations now transactionally add required call signs, exactly roll
  back call lists and partially written memories on rejection, and include
  radio-global state in Undo/Redo. The D-STAR audit
  covers all 240 actual DV fixture memories against four required-list targets
  (960 cases) plus a 385-target representative sweep, with zero unexpected
  failures. Phase 6's expanded audit now covers six VHF/UHF/HF/AM/split/DV
  sources across all 385 targets: 2,310 migrations with 814 imports, 1,496
  expected incompatibilities, and zero unexpected failures. Windows/NVDA is a
  user-confirmed pass as of 2026-07-25. **Next:** complete the versioned
  VoiceOver hand-pass matrix on macOS. Detailed status/resume plan:
  [2026-07-21-cross-radio-migration.md](2026-07-21-cross-radio-migration.md).

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
- ☑ NVDA-on-Windows pass for the Phase 6 migration flows — user-confirmed
  2026-07-25 after the grid migrated to `DataViewListCtrl`; the exact reader
  version and per-check transcript were not supplied.
- ☐ **VoiceOver hand pass on the native UI's `DataViewListCtrl` grid** — the
  migration (PROGRESS_LOG "2026-06-25") is designed to read under VoiceOver via
  NSTableView, but the actual on-device VoiceOver pass on macOS is still owed
  and is what makes "native everywhere" final.
- ☐ NVDA pass on the radio settings editor (Treebook tree↔panel F6 hop, 
  non-1-step SpinCtrls).
- ☐ NVDA pass on the banks editor (membership readout, checkbox/radiobox state).

Query sources (Phase 7):
- The generic query framework and the earlier sources (AMSAT, SatNOGS, DMR-MARC,
  mapy73.pl) were **removed 2026-07-05** — they weren't going to be used. The
  `chirp_backend/query.py` framework and `QueryParamsDialog` are gone; the shared
  `ImportDestinationDialog` + `memory_ops.apply_migration_batch` path stays (it
  backs Import from File, RepeaterBook, and Frequency lists). Recoverable from
  git history.
- ◐ RepeaterBook — **wired via CHIRP's mirror** (2026-07-09). Radio ▸ Query
  Source ▸ RepeaterBook…: country→state cascade + filter/open-only/mode form,
  background fetch, shared import flow. Backend `chirp_backend/repeaterbook.py`
  wraps CHIRP's tested source, which pulls pre-built dumps from
  `data.chirpmyradio.com/rb/` with the generic CHIRP User-Agent (no credential).
  **Owed:** the direct RepeaterBook API — a localized `VRPRepeaterBook.get_data`
  override + `USER_AGENT`, once RepeaterBook issues VRP a per-app User-Agent;
  and an NVDA pass on the query dialog + progress.
- ☑ **Frequency lists (CHIRP stock configs)** — done 2026-07-10. Radio ▸ Query
  Source ▸ Frequency lists… imports one of CHIRP's ~20 curated CSV lists into the
  loaded radio via a filterable chooser + the shared import flow. Read from the
  pinned CHIRP tree; frozen build bundles them with a targeted `--add-data` (no
  repo copy, no run-script change). Plan:
  [2026-07-10-stock-configs-frequency-lists.md](2026-07-10-stock-configs-frequency-lists.md).
  Owed: NVDA pass on the chooser dialog + import. Possible follow-ups:
  user-supplied lists (a user stock-config dir + reveal) and per-channel
  multi-select within a list (`_import_results` already takes `numbers=`).
- ☐ RadioReference — purpose-built after RepeaterBook (credentials/login form).

Smaller deferred items (chirp-feature-coverage.md "☐"/"◐" rows):
- ◐ **Bank renaming + "channels in a bank" overview (Phase 6.1).** Implemented
  2026-07-25; only the NVDA hand pass is left. Radio ▸ Manage banks… renames a
  bank where the driver actually stores names and lists a bank's channels
  read-only with Go to channel; Ctrl+B keeps per-channel assignment and
  cross-links to it. Every rename is confirmed by rereading the bank — the
  pinned Kenwood TK-890 exposes `set_name` but stores nothing, and ID-880H
  truncates to six characters, both of which are now reported rather than
  hidden. Renames are undoable through a composite radio-wide snapshot shared
  with D-STAR call lists. Migration still never renames a destination bank.
  519 tests; the bank audit adds 36 verified renames across 70 models with zero
  unexpected failures. Plan:
  [2026-07-25-bank-names-and-overview.md](2026-07-25-bank-names-and-overview.md).
- ☑ Cut/Paste clipboard (same-image row clipboard done 2026-06-27; generic
  cross-image conversion done 2026-07-21 — remaining metadata phases are linked
  under Current priority).
- ☐ File menu: New (empty image), New Window, Load Module — all need a
  model-picker UX decision first. (Open Stock Config is covered as an import —
  see Frequency lists above.)
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
