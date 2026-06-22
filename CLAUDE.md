# CLAUDE.md — Instructions for Claude Code

## What This Project Is

**Versatile Radio Programmer (VRP)** — an accessible desktop radio memory channel
programmer. It wraps the CHIRP Python library (in ./chirp/) in a wxPython app.

The **default UI** (`vrp/native/`, launched by `main.py` with no flags) is
fully native: a virtual report-mode `wx.ListCtrl` channel grid plus a real
native `wx.MenuBar`, read directly by NVDA on Windows and VoiceOver on macOS —
no webview, no WebView2, no JS bridge. It uses `prism` (the `prismatoid`
bindings) for supplemental speech, then packages to a single .exe with
PyInstaller. There is NO web server and NO browser.

A **legacy UI** (`vrp/app.py`) is still launchable with `--webview` while it is
retired (see PROGRESS_LOG.md "2026-06-21"). It hosts an `AccessibleWebView`
(from `wx-accessible-webview`) that renders semantic, screen-reader-friendly
HTML — page scripts talk to Python over a JS→Python bridge — with a native menu
bar driven by `wx-accessible-menubar` and an editable channel grid via
`wx-accessible-grid` (see "Accessible UI Libraries" below). **Do not build new
features on the legacy path; it exists only to be removed once parity is
confirmed.**

Several native wx dialogs (`edit_dialog.py`, `ops_dialog.py`, `find_dialog.py`,
`serial_dialogs.py`, `settings_dialog.py`, `bank_dialog.py`, `query_dialogs.py`,
`prefs_dialog.py`, `config.py` — all in `vrp/`) are shared by both UIs.

The CHIRP library (./chirp/) is used UNMODIFIED as a dependency. Never edit
files inside ./chirp/. Update it with git pull only.

The primary user is blind and uses NVDA on Windows. Every piece of UI code
must be accessible to screen readers. This is not optional.

## Accessible UI Libraries (sibling projects — don't reinvent inline)

**These three libraries are used only by the legacy `--webview` UI
(`vrp/app.py`).** The default native UI (`vrp/native/`) needs none of them — a
real `wx.ListCtrl` + `wx.MenuBar` doesn't have the WebView2-swallows-Alt problem
or the webview-table-re-reads-on-edit problem these libraries exist to solve.

- `wx-accessible-webview` — `AccessibleWebView` wrapping `wx.html2.WebView`;
  the page-rendering host (see vrp/app.py, vrp/html.py).
- `wx-accessible-menubar` — `AccessibleMenuBar`; owns Alt / Alt+mnemonic / F10
  menu-bar keyboard access against a focused WebView2 swallowing Alt (wx
  #24786). Wired in `MainWindow.__init__`; `_build_menubar` still builds the
  real `wx.MenuBar`.
- `wx-accessible-grid` — `AccessibleGrid` + `GridModel`; an editable
  `<table role="grid">` driven by the aria-activedescendant pattern. VRP's
  adapter is `vrp/channel_grid_model.py` (`ChannelGridModel`); try it with
  `uv run python tools/grid_preview.py`. This was briefly the production
  channels view in the webview UI (see PROGRESS_LOG.md "2026-06-20") before
  the native UI (`vrp/native/channel_grid.py`, a plain `wx.ListCtrl`) replaced
  it as the default — see PROGRESS_LOG.md "2026-06-21".

All three were extracted from this app; fix issues upstream in the library,
not as a local workaround in vrp/app.py. They're maintained only as long as
the legacy webview UI exists.

## Required Attribution (do not remove)

Every page in the app must display:
  "Radio driver support provided by the CHIRP project — chirpmyradio.com."

This is appended to every rendered view by `vrp.html.render_view`
(ATTRIBUTION_HTML). Always render top-level views through `render_view` so the
notice is present. It is a GPLv3 legal requirement as well as the right thing
to do. Do not remove or obscure it.

## Project Structure Quick Reference

- main.py              — thin entry point; runs the native UI by default,
                         or the legacy webview UI with `--webview`
- vrp/                 — wxPython UI layer (the accessible front end)
  - native/            — **default UI**: native wx.ListCtrl grid + wx.MenuBar,
                         no webview/JS bridge
    - app.py           — entry point (`vrp.native.app.run`)
    - main_window.py   — MainWindow: menu bar, status bar, grid, and all
                         command handlers (file, edit, operations, find,
                         download/upload)
    - channel_grid.py  — ChannelGrid: virtual report-mode wx.ListCtrl (no
                         paging — every channel is always populated)
    - grid_model.py    — pure data/selection model behind the grid (no wx;
                         unit-testable headless)
    - announce.py      — Announcer: status bar + prism speech, the native
                         equivalent of the webview's ARIA live region
  - app.py             — **legacy UI** (`--webview` only, being retired): wx
                         app/window, native menu bar, webview host, JS↔Python
                         bridge, keyboard shortcuts, paging, and all command
                         handlers (file, edit, operations, find, download/upload)
  - views.py           — legacy: renders channel-grid pages (read-only) and
                         single rows for the webview UI
  - edit_dialog.py     — native wx dialog to edit one channel (shared by both UIs)
  - ops_dialog.py      — native wx dialog for bulk operations, shared (delete/move/…)
  - find_dialog.py     — native wx Find dialog (shared by both UIs)
  - serial_dialogs.py  — native wx Download/Upload/progress dialogs (shared)
  - settings_dialog.py — native wx radio settings editor, Treebook (shared)
  - bank_dialog.py     — native wx dialog to assign a channel to banks (shared)
  - query_dialogs.py   — native wx query-source param + import dialogs (shared)
  - prefs_dialog.py    — native wx Preferences dialog (shared)
  - config.py          — persistent JSON config, preferences + recent files (shared)
  - html.py            — legacy: Jinja2 rendering to strings + attribution footer
  - speech.py          — prism speech wrapper, graceful no-op if unavailable (shared)
  - _chirp_path.py     — makes the editable ./chirp package importable (shared)
  - channel_grid_model.py — legacy: GridModel adapter for the wx-accessible-grid
                         editable grid (see tools/grid_preview.py)
- chirp_backend/       — all chirp library interaction (framework-agnostic):
                         radio, memory_ops, col_defs, bank_ops, query
- static/css/main.css  — legacy webview UI only: design-system styles, retained
                         for future inlining into the webview (not currently loaded)
- templates/           — legacy webview UI only: Jinja2 view fragments
                         (welcome, channels, _row_macro)
- tests/               — unit tests (no hardware needed)
- tools/               — update_chirp.py (CHIRP version bump) and
                         grid_preview.py (standalone wx-accessible-grid preview
                         harness for the legacy editable grid, no full app needed)
- build.py             — PyInstaller build script
- chirp/               — upstream CHIRP library (DO NOT EDIT)

## Command Surfaces (keep in sync)

### Native UI (default — `vrp/native/main_window.py`)

A real `wx.MenuBar` has no WebView2 to fight, so the menu item's accelerator
(the `\tCtrl+...`/`\tF2` suffix in its label, e.g. `"&Save\tCtrl+S"`) *is* the
global shortcut — one surface, not three. `_build_menubar`/`_add` wire each
command exactly once: a menu item with its accelerator, bound via
`self.Bind(wx.EVT_MENU, handler, item)`, optionally gated on a loaded radio
(`needs_radio=True`, tracked in `_radio_gated_keys`, enabled/disabled by
`_update_menu_state`). F1 (`on_shortcuts`) shows the `APP_SHORTCUTS` list as a
plain-text `wx.MessageBox` — keep it in sync with the menu accelerators by hand.

When adding a command: add it via `self._add(menu, key, label_with_accelerator,
handler, needs_radio=...)` in the right `_build_*_menu`, add the same combo to
`APP_SHORTCUTS`, and update `docs/keyboard-map.md` and
`docs/chirp-feature-coverage.md`.

### Legacy webview UI (`--webview`, `vrp/app.py` — being retired)

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

When adding a command here: wire the handler, add a menu item (disable it in
`_radio_menu_items` if it needs a loaded radio), add the shortcut to
`_SHORTCUTS_JS` + `APP_SHORTCUTS` (+ `aria-keyshortcuts` on any button), and
update `docs/keyboard-map.md` and `docs/chirp-feature-coverage.md`. Don't add
new commands to the legacy UI unless they're also going into the native one —
it's being removed, not extended.

## Accessibility Rules (Enforce These Always)

1. Every <button>, <input>, <select>, <a> must have an accessible name.
   Use aria-label if visible text is absent or insufficient.

2. The memory channel table must be a real <table> element with:
   - <thead> containing <th scope="col"> for every column
   - <tbody> with <tr> rows
   - Row number in a <th scope="row"> cell
   Never use div/span grids for tabular data.

3. All dynamic feedback (operation results, errors, loading states, progress)
   must be announced.
   - **Native UI (default):** call `self.announce.announce('Message here')`
     (a `vrp.native.announce.Announcer`) — it writes the status bar and, if
     prism speech is available, speaks it too. Pass `assertive=True` for
     errors so they interrupt any speech in progress. The announcer is a
     fallback, not the primary signal: handlers should still move focus to
     the result row/field so the screen reader reads it directly.
   - **Legacy webview UI (`--webview`):** from Python, call
     `self.view.status('Message here')` (the AccessibleWebView routes it to
     its built-in ARIA live region); from page JavaScript (e.g. grid edits),
     update the in-page aria-live region (id="status-announcer",
     aria-live="polite"; use aria-live="assertive" for errors).
   Every operation result and error MUST go through the announcer/live-region
   path for whichever UI it's in.

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

After any operation, the affected range must be refreshed in whichever UI is
active: native UI calls `self.grid.refresh_numbers(numbers)` (or `.rebuild()`
for structural ops); legacy webview UI returns the updated channel data from
the bridge handler so the view can refresh just those rows.

## Bridge Message Shape (JS ↔ Python)

**Applies only to the legacy `--webview` UI (`vrp/app.py`).** The native UI
(`vrp/native/`, default) has no JS bridge at all — its handlers call
`chirp_backend` and update `ChannelGrid`/`Announcer` directly, in Python.

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
which calls `self.announce.announce(...)` (native UI) or `view.status(...)`
(legacy webview UI) so the user hears each progress message.

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
`./chirp` tree itself is gitignored, not committed; `run-win.bat`/`run-mac.sh`
clone it and check out the `CHIRP_COMMIT` SHA so everyone runs identical code.
To update:
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
