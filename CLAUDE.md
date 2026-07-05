# CLAUDE.md — Instructions for Claude Code

## What This Project Is

**Versatile Radio Programmer (VRP)** — an accessible desktop radio memory channel
programmer. It wraps the CHIRP Python library (in ./chirp/) in a wxPython app.

**VRP has one UI, built entirely from native wx controls, on both Windows and
macOS.** The channel grid was historically the one control that did not read on
every screen reader, which is why a second (webview) UI once existed. That
blocker was solved (see PROGRESS_LOG.md "2026-06-25 — Native UI is the default on
every platform" and "2026-06-24 — native-grid VoiceOver feasibility"), so the
webview UI was **removed entirely** (PROGRESS_LOG.md "2026-06-29 — Removed the
retired webview UI"), along with its `wx-accessible-webview`,
`wx-accessible-menubar`, and `jinja2` dependencies. There is **no web server, no
webview, and no browser** anywhere in the app.

**The UI** (`vrp/native/`) is a `wx.dataview.DataViewListCtrl` channel grid plus
a real native `wx.MenuBar`. On macOS `DataViewListCtrl` is a real native control
(NSTableView), so **VoiceOver** reads it directly; on Windows it is wx's
**generic, custom-drawn** control — not a native common control like
SysListView32 — but wx exposes it to MSAA/UIA so **NVDA** reads its rows. (VRP
adds its own Left/Right cell cursor — announced via prism — and a Shift+F10
handler: the generic Windows control provides neither a per-cell cursor nor the
context-menu event. The cursor is wired on **macOS** too: plain Left/Right reach
the NSTableView there and prism speaks each cell, which is what lets F2 edit the
focused cell rather than fall back to a field picker.) The previous virtual
`wx.ListCtrl` *did* wrap
the native SysListView32 on Windows, but fell back to wx's generic control on
macOS, which exposed nothing to NSAccessibility and was silent under VoiceOver —
see `docs/research/2026-06-24-native-grid-voiceover-feasibility.md`.

`main.py` launches the native UI (just a `--debug` flag now — the old
`--webview`/`--native` mode flags are gone). `prism` (the `prismatoid` bindings)
provides supplemental speech, and the app packages to a single .exe with
PyInstaller.

> **If in-app help/docs are added later** and an HTML view is genuinely the right
> tool, build a small, purpose-made read-only viewer (a `wx.Frame`/`wx.Dialog`
> hosting a read-only `wx.html2.WebView`, which is part of wxPython core — no
> extra dependency). Do **not** resurrect the old webview stack: it was a full
> alternate front end for the editable channel grid, not a doc viewer, and shares
> nothing useful with a help window.

The CHIRP library (./chirp/) is used UNMODIFIED as a dependency. Never edit
files inside ./chirp/. Update it with git pull only.

The primary user is blind and uses NVDA on Windows. Every piece of UI code
must be accessible to screen readers. This is not optional.

## Required Attribution (do not remove)

The app must display:
  "Radio driver support provided by the CHIRP project — chirpmyradio.com."

It is shown permanently in status-bar field 1 (`vrp/native/main_window.py`,
`_CHIRP_ATTRIBUTION`, never overwritten by `Announcer`) and in the About box. It
is a GPLv3 legal requirement as well as the right thing to do. Do not remove or
obscure it. Any future help/docs page must carry it too.

## Project Structure Quick Reference

- main.py              — thin entry point; launches the native UI (`--debug` flag)
- vrp/                 — wxPython UI layer (the accessible front end)
  - native/            — the UI: native wx.dataview.DataViewListCtrl grid +
                         wx.MenuBar, no webview/JS bridge
    - app.py           — entry point (`vrp.native.app.run`)
    - main_window.py   — MainWindow: menu bar, status bar, grid, and all
                         command handlers (file, edit, operations, find,
                         download/upload)
    - channel_grid.py  — ChannelGrid: wx.dataview.DataViewListCtrl — native
                         NSTableView on macOS (VoiceOver) and wx's generic
                         custom-drawn control on Windows, exposed to MSAA so NVDA
                         reads it; no paging — every channel is always populated
    - grid_model.py    — pure data/selection model behind the grid (no wx;
                         unit-testable headless)
    - announce.py      — Announcer: status bar + prism speech (the screen-reader
                         feedback channel)
  - edit_dialog.py     — native wx dialog to edit one channel + single cell;
                         on a frequency change it fills the band's offset
                         (always) and, opt-in, mode/step/tone
  - ops_dialog.py      — native wx "Bulk operations" dialog
                         (delete/delete+shift/insert/move/copy/sort/arrange)
  - find_dialog.py     — native wx Find dialog
  - serial_dialogs.py  — native wx Download/Upload/Favorites/progress dialogs +
                         the shared filter ModelPicker and type-ahead
                         RadioListView (a wx.ListCtrl)
  - settings_dialog.py — native wx radio settings editor, Treebook
  - bank_dialog.py     — native wx dialog to assign a channel to banks
  - query_dialogs.py   — native wx import-destination dialog (ImportDestination
                         Dialog; shared by Import from File — the online
                         query-source dialogs were removed, see PROGRESS_LOG)
  - prefs_dialog.py    — native wx Preferences dialog: recent-files count, band
                         plan region, apply-band-defaults, speak-aloud
  - info_dialog.py     — read-only multiline edit box for reviewing text (Radio
                         Info, "Radio details…"); navigable + copyable
  - config.py          — persistent JSON config: prefs + recent files +
                         favorite radios + band-plan region
  - speech.py          — prism speech wrapper, graceful no-op if unavailable
  - _chirp_path.py     — makes the editable ./chirp package importable
- chirp_backend/       — all chirp library interaction (framework-agnostic):
                         radio (incl. describe_model), memory_ops, undo
                         (channel-edit undo/redo), bandplan (suggested repeater
                         offset + band defaults, by region), col_defs, bank_ops,
                         serial_trace
- tests/               — unit tests (no hardware needed)
- tools/               — update_chirp.py (CHIRP version bump); throwaway spikes
- build.py             — PyInstaller build script
- chirp/               — upstream CHIRP library (DO NOT EDIT)

## Command Surface (`vrp/native/main_window.py`)

A real `wx.MenuBar` makes the menu item's accelerator (the `\tCtrl+...`/`\tF2`
suffix in its label, e.g. `"&Save\tCtrl+S"`) *the* global shortcut — one surface,
not several. `_build_menubar`/`_add` wire each command exactly once: a menu item
with its accelerator, bound via `self.Bind(wx.EVT_MENU, handler, item)`,
optionally gated on a loaded radio (`needs_radio=True`, tracked in
`_radio_gated_keys`, enabled/disabled by `_update_menu_state`). F1
(`on_shortcuts`) shows the `APP_SHORTCUTS` list as a plain-text `wx.MessageBox` —
keep it in sync with the menu accelerators by hand.

When adding a command: add it via `self._add(menu, key, label_with_accelerator,
handler, needs_radio=...)` in the right `_build_*_menu`, add the same combo to
`APP_SHORTCUTS`, and update `docs/keyboard-map.md` and
`docs/chirp-feature-coverage.md`.

## Accessibility Rules (Enforce These Always)

1. Every control must have an accessible name. For native wx controls, give the
   control a label (or `SetName`/an associated `wx.StaticText`) so NVDA/VoiceOver
   announce it.

2. Tabular data must expose real rows, columns, and headers to the
   accessibility API — never a hand-drawn grid. The channel table is a
   `wx.dataview.DataViewListCtrl`, which wraps a native list-view per OS and
   reports rows/columns/headers to MSAA/UIA (NVDA) and NSAccessibility
   (VoiceOver) for free. Any HTML you render for a future help/docs page must use
   a real `<table>` with `<th scope="col">`/`<th scope="row">`.

3. All dynamic feedback (operation results, errors, loading states, progress)
   must be announced. Call `self.announce.announce('Message here')` (a
   `vrp.native.announce.Announcer`) — it writes the status bar and, if prism
   speech is available, speaks it too. Pass `assertive=True` for errors so they
   interrupt any speech in progress. The announcer is a fallback, not the primary
   signal: handlers should still move focus to the result row/field so the screen
   reader reads it directly. Every operation result and error MUST go through the
   announcer path.

4. Modal dialogs must:
   - Be a real `wx.Dialog` with a title (sets the accessible name)
   - Trap focus within the dialog (wx modal dialogs do this; don't defeat it)
   - Return focus to the triggering control when closed
   - Be closeable with Escape (`SetEscapeId`/a Cancel button)

5. No operation should require drag-and-drop. Every operation that sighted
   users might do by dragging must have a keyboard-accessible alternative
   (e.g. "Move to channel..." dialog).

6. Focus must be managed after operations. After deleting rows, focus goes
   to the next row or the grid itself. After a dialog closes, focus returns
   to the control that opened it.

7. Do not use color as the only indicator of state. Empty channels, error
   rows, etc. must also have text indicators readable by screen readers.

8. Keyboard shortcuts: avoid single-letter shortcuts in the grid without a
   modifier key, as these conflict with NVDA's quick navigation. Use Ctrl+key
   combinations for global shortcuts.

## CHIRP Library Rules

- Never import from chirp.wxui — that's the inaccessible GUI we're replacing
- Always call directory.import_drivers() before any radio operations
- Radio driver modules are dynamically imported; always pass
  --collect-submodules=chirp.drivers to PyInstaller (see build.py)
- The Memory object fields: freq (int Hz), name (str), tmode, rtone, ctone,
  dtcs, rx_dtcs, dtcs_polarity, cross_mode, duplex, offset, mode,
  tuning_step, skip, power, comment, empty (bool), immutable (list)
- mem.empty == True means the channel slot is unused
- mem.immutable is a list of field names that cannot be changed for that memory

## Memory Operations Reference

All implemented in chirp_backend/memory_ops.py. When adding new operations,
follow the same pattern: pure functions taking a radio object + parameters,
returning (success: bool, message: str, affected_channels: list).

Operations that modify the radio must call radio.set_memory() or
radio.erase_memory() — never modify the memory map directly.

After any operation, refresh the affected range in the grid:
`self.grid.refresh_numbers(numbers)` for in-place field edits, or
`self.grid.rebuild()` for structural ops (insert/delete/move that shift rows).

## Serial Port / Radio I/O

Serial operations (download from radio, upload to radio) are long-running.
They run on a wx background thread (see chirp/wxui/radiothread.py for CHIRP's
pattern). Progress is marshalled back to the UI thread with `wx.CallAfter`,
which calls `self.announce.announce(...)` so the user hears each progress
message.

Never block the wx main (UI) thread with serial I/O.

## Code Style

- Python: follow PEP 8, type hints on all public functions
- Comments: explain *why*, not *what*
- All user-visible strings: plan for i18n (wrap in _() even if not translated yet)

## Setup (uv manages Python 3.11 automatically)

```bash
# Clone the CHIRP library into ./chirp BEFORE syncing — it is declared as an
# editable path dependency in pyproject.toml ([tool.uv.sources]).
git clone --depth=1 https://github.com/kk7ds/chirp.git
uv sync --extra dev
```

CHIRP is pinned for reproducibility; record the commit when updating (current:
906e039, 2026-06-25). `uv sync` installs the editable ./chirp automatically —
no separate `uv pip install -e ./chirp` step.

## Testing

Run tests with: `uv sync --extra dev` (once, to install pytest) then
`uv run python -m pytest`. Use `python -m pytest`, not `uv run pytest`: the
latter falls back to any pytest on PATH (e.g. a global one under a different
Python with no `pyserial`) if the venv doesn't have it, silently running the
suite in the wrong environment. `python -m pytest` always uses the project
venv and errors clearly if pytest is missing. The run scripts use
`uv sync --inexact`, so launching the app no longer prunes pytest from the venv.
Tests use chirp/tests/images/ image files — no radio hardware needed.
Every memory operation in memory_ops.py must have a corresponding test.

## Running

Desktop app:    uv run python main.py
Debug logging:  uv run python main.py --debug

## Updating CHIRP

CHIRP is vendored at ./chirp, pinned to a tested commit recorded in the
**`CHIRP_COMMIT`** file (currently 906e039), and bundled into the exe. The
`./chirp` tree itself is gitignored, not committed; `run-win.bat`/`run-mac.sh`
clone it and check out the `CHIRP_COMMIT` SHA so everyone runs identical code.
To update:
`uv run python tools/update_chirp.py` — fetches latest CHIRP, checks it out
(detached HEAD), runs the tests, and on green **writes the new SHA to
`CHIRP_COMMIT`** automatically (rolls ./chirp back to the old pin on failure).
After a green bump, commit `CHIRP_COMMIT` (and note the SHA in PROGRESS_LOG.md)
and rebuild. End users never pull/rebuild — updates ship as new VRP releases.

## Building

Building a release .exe is a deliberate developer/release step, not something
testers or end users run — **everyone runs from source via `run-win.bat` /
`run-mac.sh`** (see "Running from source" / the run scripts). There is no
double-click build wrapper (the old `build.bat` was removed because a tester
ran it by mistake). To cut a release build:

uv sync --extra build
uv run python build.py --installer
Output: dist/vrp/ (the app folder) + dist/vrp-<version>-setup.exe (the installer)

`build.py` defaults to **onedir** (a `dist/vrp/` folder), not onefile, because
onefile re-extracts the whole interpreter + wxPython + 552 drivers to a temp dir
on every launch (the slow cold start) and trips Defender/SmartScreen more often;
onedir starts instantly. `--installer` then wraps that folder with **Inno Setup**
(`installer.iss`) into a `dist/vrp-<version>-setup.exe` with a Start-menu shortcut
and uninstaller — the way upstream CHIRP ships its own PyInstaller build. Use
`python build.py --onefile` only for a quick throwaway single-exe test. The
PyInstaller step is well under a minute (552 drivers bundled, not compiled — see
"Notes" below). Inno Setup 6 is required for `--installer`
(https://jrsoftware.org/isinfo.php); set `INNO_SETUP_ISCC` if `ISCC.exe` isn't
found on PATH or in the default install dir.

Notes:
- Packager is **PyInstaller** (switched from Nuitka — compiling 552 CHIRP
  drivers to C took 20-30 min/build; PyInstaller just freezes bytecode).
  Nuitka would compile the 552 dynamically-imported drivers with no size or
  startup win for a wx GUI, so it stays retired. See PROGRESS_LOG "Phase 9" for
  the original Nuitka debugging history.
- `build.py` excludes `prism`/`win32more`/`numpy` (`--exclude-module`) —
  prism pulls in the entire win32more Windows-API surface; speech is opt-in
  and no-ops without it.
- `build.py` explicitly `--collect-submodules` for `chirp.drivers` and
  `chirp.sources` — both are loaded via dynamic `__import__`/
  `importlib.import_module`, which PyInstaller's static analysis can't follow.
- **Every build first enforces the CHIRP pin** (`ensure_chirp_on_pin`): it
  verifies `./chirp` is checked out at the `CHIRP_COMMIT` SHA and, for a clean
  clone, syncs it there automatically, so the frozen app always bundles the exact
  driver set the test suite passed against. It never fetches from the network and
  never discards uncommitted CHIRP changes — adopting a *newer* CHIRP stays the
  deliberate, tested step in `tools/update_chirp.py`. It aborts the build if the
  clone is off-pin and dirty, or if the pinned commit isn't fetched locally.
  `--no-chirp-sync` verifies only (aborts on mismatch instead of fixing it).
- `uv sync --extra build` installs only the build extra (drops pytest). Use
  `uv sync --extra dev --extra build` to have both, or re-run `uv sync --extra dev`
  afterward to get the test tools back.
- If PyInstaller fails on a specific package, see README.md "Packaging with
  PyInstaller".
