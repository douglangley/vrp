# CLAUDE.md — Instructions for Claude Code

## What This Project Is

**Versatile Radio Programmer (VRP)** — an accessible desktop radio memory channel
programmer. It wraps the CHIRP Python library (in ./chirp/) in a wxPython app
whose `AccessibleWebView` (from the `wx-accessible-webview` package) renders
semantic, screen-reader-friendly HTML, with a native menu bar driven by
`wx-accessible-menubar` and (preview/beta) an editable channel grid via
`wx-accessible-grid` — see "Accessible UI Libraries" below. It uses `prism`
(the `prismatoid` bindings) for supplemental speech, then packages to a single
.exe with PyInstaller. There is NO web server and NO browser — HTML is
rendered to strings and shown in the embedded webview; page scripts talk to
Python over a JS→Python bridge.

The CHIRP library (./chirp/) is used UNMODIFIED as a dependency. Never edit
files inside ./chirp/. Update it with git pull only.

The primary user is blind and uses NVDA on Windows. Every piece of UI code
must be accessible to screen readers. This is not optional.

## Accessible UI Libraries (sibling projects — don't reinvent inline)

- `wx-accessible-webview` — `AccessibleWebView` wrapping `wx.html2.WebView`;
  the page-rendering host (see vrp/app.py, vrp/html.py).
- `wx-accessible-menubar` — `AccessibleMenuBar`; owns Alt / Alt+mnemonic / F10
  menu-bar keyboard access against a focused WebView2 swallowing Alt (wx
  #24786). Wired in `MainWindow.__init__`; `_build_menubar` still builds the
  real `wx.MenuBar`.
- `wx-accessible-grid` — `AccessibleGrid` + `GridModel`; an editable
  `<table role="grid">` driven by the aria-activedescendant pattern. VRP's
  adapter is `vrp/channel_grid_model.py` (`ChannelGridModel`); try it with
  `uv run python tools/grid_preview.py`. **Status: preview/beta — the
  NVDA-on-Windows pass is not done yet.** The production channels view is
  still the read-only table + edit dialog (vrp/views.py + vrp/edit_dialog.py).
  See PROGRESS_LOG.md "2026-06-20" for the promotion criteria.

All three were extracted from this app; fix issues upstream in the library,
not as a local workaround in vrp/app.py.

## Required Attribution (do not remove)

Every page in the app must display:
  "Radio driver support provided by the CHIRP project — chirpmyradio.com."

This is appended to every rendered view by `vrp.html.render_view`
(ATTRIBUTION_HTML). Always render top-level views through `render_view` so the
notice is present. It is a GPLv3 legal requirement as well as the right thing
to do. Do not remove or obscure it.

## Project Structure Quick Reference

- main.py              — thin entry point (applies chirp path fix, runs app)
- vrp/                 — wxPython UI layer (the accessible front end)
  - app.py             — wx app/window, native menu bar, webview host, JS↔Python
                         bridge, keyboard shortcuts, paging, and all command
                         handlers (file, edit, operations, find, download/upload)
  - views.py           — render channel-grid pages (read-only) and single rows
  - edit_dialog.py     — native wx dialog to edit one channel
  - ops_dialog.py      — native wx dialog for bulk operations (delete/move/…)
  - find_dialog.py     — native wx Find dialog
  - serial_dialogs.py  — native wx Download/Upload/progress dialogs
  - settings_dialog.py — native wx radio settings editor (Treebook)
  - bank_dialog.py     — native wx dialog to assign a channel to banks
  - query_dialogs.py   — native wx query-source param + import dialogs
  - prefs_dialog.py    — native wx Preferences dialog
  - config.py          — persistent JSON config (preferences + recent files)
  - html.py            — Jinja2 rendering to strings + attribution footer
  - speech.py          — prism speech wrapper (graceful no-op if unavailable)
  - _chirp_path.py     — makes the editable ./chirp package importable
  - channel_grid_model.py — GridModel adapter for the wx-accessible-grid
                         editable grid preview (see tools/grid_preview.py)
- chirp_backend/       — all chirp library interaction (framework-agnostic):
                         radio, memory_ops, col_defs, bank_ops, query
- static/css/main.css  — design-system styles, retained for future inlining
                         into the webview (not currently loaded)
- templates/           — Jinja2 view fragments (welcome, channels, _row_macro)
- tests/               — unit tests (no hardware needed)
- tools/               — update_chirp.py (CHIRP version bump) and
                         grid_preview.py (standalone wx-accessible-grid preview
                         harness, no full app needed)
- build.py             — PyInstaller build script
- chirp/               — upstream CHIRP library (DO NOT EDIT)

## Command Surfaces (keep in sync)

Every user command is reachable three ways and they must stay in sync:
1. The native **menu bar** (`_build_menubar` in vrp/app.py) — File / Radio /
   Channels / Help. A focused WebView2 eats one-shot Alt/Ctrl accelerators
   (wxWidgets #24786); `wx-accessible-menubar`'s `AccessibleMenuBar` (wired in
   `MainWindow.__init__`) bridges plain `Alt`, `Alt+mnemonic`, and `F10` from an
   in-page key listener and restores webview focus after a menu closes or the
   window is maximized/reactivated. Individual menu-item handlers also restore
   focus via `_menu_then_focus`.
2. In-page **buttons** in the view fragments (bridge via `window.vrp.postMessage`).
3. Global **Ctrl-combo shortcuts** (`_SHORTCUTS_JS` map + `APP_SHORTCUTS`),
   handled inside the page so they work despite #24786; also listed by F1.

When adding a command: wire the handler, add a menu item (disable it in
`_radio_menu_items` if it needs a loaded radio), add the shortcut to
`_SHORTCUTS_JS` + `APP_SHORTCUTS` (+ `aria-keyshortcuts` on any button), and
update `docs/keyboard-map.md` and `docs/chirp-feature-coverage.md`.

## Accessibility Rules (Enforce These Always)

1. Every <button>, <input>, <select>, <a> must have an accessible name.
   Use aria-label if visible text is absent or insufficient.

2. The memory channel table must be a real <table> element with:
   - <thead> containing <th scope="col"> for every column
   - <tbody> with <tr> rows
   - Row number in a <th scope="row"> cell
   Never use div/span grids for tabular data.

3. All dynamic feedback (operation results, errors, loading states, progress)
   must be announced. Two channels exist:
   - From Python: call `self.view.status('Message here')` — the
     AccessibleWebView routes it to its built-in ARIA live region.
   - From page JavaScript (e.g. grid edits): update an in-page
     aria-live region (id="status-announcer", aria-live="polite";
     use aria-live="assertive" for errors).
   Every operation result and error MUST go through one of these.

4. Modal dialogs must:
   - Have role="dialog" and aria-labelledby pointing to the dialog title
   - Trap focus (Tab/Shift+Tab cycle only within the dialog)
   - Return focus to the triggering element when closed
   - Be closeable with Escape key

5. No operation should require drag-and-drop. Every operation that sighted
   users might do by dragging must have a keyboard-accessible alternative
   (e.g. "Move to channel..." dialog).

6. Focus must be managed after operations. After deleting rows, focus goes
   to the next row or the table itself. After a dialog closes, focus returns
   to the element that opened it.

7. Do not use color as the only indicator of state. Empty channels, error
   rows, etc. must also have text or icon indicators readable by screen readers.

8. Keyboard shortcuts: avoid single-letter shortcuts in the table without a
   modifier key, as these conflict with NVDA's quick navigation in browse mode.
   Use Ctrl+key combinations for global shortcuts.

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

After any operation, the bridge handler must return the updated channel data
for the affected range so the view can refresh just those rows.

## Bridge Message Shape (JS ↔ Python)

Page scripts call `window.vrp.postMessage(JSON.stringify({action, ...}))` (the
native wx.html2 script-message handler; `.postMessage`, not `.post`). Inline
`onclick`/`onkeydown` work in fragments; `<script>` tags injected via
`set_content` do NOT run, so document-level listeners are installed once via
`view.run_js`. Messages arrive at `MainWindow.on_bridge_message`. Handlers send
results back to the page (via `view.run_js(...)` or `view.set_content/append`).
Use a consistent envelope for results pushed to the page:
{
  "ok": true/false,
  "message": "Human-readable result for screen reader announcement",
  "data": { ... }   // operation-specific payload
}

On error: ok=false, message describes the error, data may be absent.
The view always announces `message` (host status or in-page live region)
regardless of ok value.

## Serial Port / Radio I/O

Serial operations (download from radio, upload to radio) are long-running.
They run on a wx background thread (see chirp/wxui/radiothread.py for CHIRP's
pattern). Progress is marshalled back to the UI thread with `wx.CallAfter`,
which calls `view.status(...)` so the user hears each progress message.

Never block the wx main (UI) thread with serial I/O.

## Code Style

- Python: follow PEP 8, type hints on all public functions
- JavaScript: vanilla JS only, no frameworks, no build step required
- HTML: semantic elements first, ARIA only where native semantics are insufficient
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
6dadd6b, 2026-06-10). `uv sync` installs the editable ./chirp automatically —
no separate `uv pip install -e ./chirp` step.

## Testing

Run tests with: uv run pytest
Tests use chirp/tests/images/ image files — no radio hardware needed.
Every memory operation in memory_ops.py must have a corresponding test.

## Running

Desktop app:    uv run python main.py
Debug logging:  uv run python main.py --debug

## Updating CHIRP

CHIRP is vendored at ./chirp, pinned to a tested commit recorded in the
**`CHIRP_COMMIT`** file (currently 6dadd6b), and bundled into the exe. The
`./chirp` tree itself is gitignored, not committed; `run.bat` clones it and
checks out the `CHIRP_COMMIT` SHA so everyone runs identical code. To update:
`uv run python tools/update_chirp.py` — fetches latest CHIRP, checks it out
(detached HEAD), runs the tests, and on green **writes the new SHA to
`CHIRP_COMMIT`** automatically (rolls ./chirp back to the old pin on failure).
After a green bump, commit `CHIRP_COMMIT` (and note the SHA in PROGRESS_LOG.md)
and rebuild. End users never pull/rebuild — updates ship as new VRP releases.

## Building

uv sync --extra build
uv run python build.py
Output: dist/<appname>.exe (Windows) or dist/<appname> (Linux)

Or run `build.bat` (Windows): installs build deps, builds with live output +
timestamped `build_*.log`, reports success/failure. Usually well under a
minute (552 drivers bundled, not compiled — see "Notes" below).

Notes:
- Packager is **PyInstaller** (switched from Nuitka — compiling 552 CHIRP
  drivers to C took 20-30 min/build; PyInstaller just freezes bytecode).
  See PROGRESS_LOG "Phase 9" for the original Nuitka debugging history.
- `build.py` excludes `prism`/`win32more`/`numpy` (`--exclude-module`) —
  prism pulls in the entire win32more Windows-API surface; speech is opt-in
  and no-ops without it.
- `build.py` explicitly `--collect-submodules` for `chirp.drivers` and
  `chirp.sources` — both are loaded via dynamic `__import__`/
  `importlib.import_module`, which PyInstaller's static analysis can't follow.
- `uv sync --extra build` installs only the build extra (drops pytest). Use
  `uv sync --extra dev --extra build` to have both, or re-run `uv sync --extra dev`
  afterward to get the test tools back.
- If PyInstaller fails on a specific package, see README.md "Packaging with
  PyInstaller".
