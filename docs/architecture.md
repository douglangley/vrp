# VRP Architecture

Versatile Radio Programmer is a wxPython desktop app that puts an accessible front end
on the CHIRP radio programming library. It does **not** run a web server.

There are two UIs sharing one backend, because no single channel-grid
implementation reads correctly on every screen reader (see PROGRESS_LOG.md
"2026-06-21 — Platform-aware UI default"):

- **Native UI (`vrp/native/`)** — a native `wx.ListCtrl` channel grid and a
  native `wx.MenuBar`. No webview, no WebView2, no JS bridge. This is what
  **NVDA on Windows** reads. Default on Windows and Linux.
- **Webview UI (`vrp/app.py`)** — an `AccessibleWebView` hosting an editable
  `AccessibleGrid` (from `wx-accessible-grid`) for the channel table, bridged
  to Python over `window.vrp.postMessage`. This is what **VoiceOver on
  macOS** reads (the native `wx.ListCtrl` doesn't read correctly under
  VoiceOver yet). Default on macOS.

`main.py`'s `parse_mode()` picks the default by `sys.platform`; `--webview`
or `--native` forces either one regardless of platform. **Neither is
legacy** — both are actively maintained, and a new command should land on
both unless it's genuinely specific to one grid's widget API.

Both UIs reuse the same native wx dialogs (edit, bulk operations, find,
settings, banks, download/upload, preferences) and the same `chirp_backend/`.

## Native UI (default on Windows/Linux)

```
main.py  (entry; parse_mode() picks native here unless --webview forces it)
  └─ vrp/native/app.py : run() → MainWindow (wx.Frame)
       ├─ native wx.MenuBar (File / Radio / Channels / Help) — built by
       │    _build_menubar/_add in main_window.py. Each item's label carries
       │    its accelerator (e.g. "&Save\tCtrl+S"); wx wires Alt-mnemonics and
       │    Ctrl-combos automatically — no WebView2 in the way, so none of the
       │    webview UI's #24786 workarounds are needed.
       ├─ vrp/native/channel_grid.py : ChannelGrid (wx.ListCtrl, LC_VIRTUAL)
       │    ├─ virtual + multi-select: every channel is populated at once
       │    │    (no paging); OnGetItemText pulls from vrp/native/grid_model.py
       │    ├─ EVT_LIST_ITEM_ACTIVATED → on_edit_channel (F2/Enter opens the
       │    │    native edit dialog, same as the webview UI's per-row button)
       │    └─ Shift+Arrow / Ctrl+Space select a block; Ctrl+Shift+Up/Down/M
       │         move it, re-selecting + focusing the result afterward
       ├─ native wx dialogs (input/editing — first-class NVDA support, SHARED
       │    with the webview UI): edit_dialog · ops_dialog · find_dialog ·
       │    serial_dialogs · settings_dialog · bank_dialog · query_dialogs ·
       │    prefs_dialog
       ├─ vrp/native/announce.py : Announcer — writes the status bar (field 0;
       │    field 1 permanently holds the CHIRP attribution) and speaks via
       │    vrp/speech.py (prism) if available. The PRIMARY announcement
       │    signal is still focus management (handlers move focus to the
       │    result row); the announcer covers summaries/errors with no
       │    natural focus target
       └─ chirp_backend/: radio.py, memory_ops.py, col_defs.py  (framework-agnostic)
            └─ chirp  (vendored ./chirp, used unmodified; serial + driver library)
```

### Interaction model

- **Grid is virtual and unpaged.** `wx.ListCtrl` with `LC_VIRTUAL` populates
  instantly regardless of radio size (`SetItemCount` + `OnGetItemText`), so
  there's no page-by-page reading and no "channels per page" preference (the
  webview UI's channels-per-page preference is vestigial — see below).
- **Editing still happens in native wx dialogs**, not in-grid: activating a
  row (F2/Enter) opens `edit_dialog.EditChannelDialog`, same dialog the
  webview UI uses. Reordering (move up/down/to) happens directly on the
  grid's selection instead, since `wx.ListCtrl` selection/focus is cheap to
  manage without re-reading the whole table to a screen reader.
- **One command surface, not three.** The webview UI needs a menu bar,
  in-page buttons, and a separate JS shortcut map because a focused WebView2
  ate Alt/Ctrl accelerators (wx #24786). A real `wx.MenuBar` doesn't have that
  problem, so each command is wired exactly once — as a menu item whose label
  carries its accelerator — and `APP_SHORTCUTS` in `main_window.py` is just the
  list F1 displays, not a second wiring path.
- **No JS bridge.** Menu/grid event handlers in `MainWindow` call
  `chirp_backend` functions directly and push results to `ChannelGrid`
  (`refresh_numbers`/`reorder_refresh`/`rebuild`) and `Announcer` in the same
  Python call — there's nothing analogous to `on_bridge_message`.

### Key choices and why

- **Native `wx.ListCtrl` for NVDA.** A native `wx.ListCtrl` and `wx.MenuBar`
  get NVDA support, Alt/Ctrl accelerators, and unlimited-size population for
  free from wxWidgets itself — no JS bridge, no paging, no fight with
  WebView2 swallowing keyboard input (wx #24786). The tradeoff, found the
  hard way (see PROGRESS_LOG.md "2026-06-21 — Platform-aware UI default"): it
  doesn't read correctly under VoiceOver, which is why it isn't the default
  on macOS.
- **Dialogs and `chirp_backend` are unchanged.** The native UI is a
  presentation layer over the same validated backend and the same native wx
  dialogs the webview UI already used for input — only the channel-grid host
  and the menu-bar/shortcut plumbing differ between the two.
- **Status bar + prism for announcements, not ARIA.** There's no DOM, so
  there's no live region. `Announcer` writes a status bar field a screen
  reader can read on demand and optionally speaks via prism; the harder-working
  signal is still moving focus to the row/field a screen reader will read
  automatically.
- **Serial on a background thread.** Same as the webview UI: long radio
  I/O runs off the UI thread; progress is marshalled back with `wx.CallAfter`
  → `self.announce.announce(...)`.

## Webview UI (default on macOS)

```
main.py --webview   (or: parse_mode() picks webview here by default on macOS)
  └─ vrp/app.py : VRPApp / MainWindow (wx.Frame)
       ├─ native wx menu bar (File / Edit / Radio / Channels / Help); keyboard
       │    access (Alt / Alt+mnemonic / F10) via wx-accessible-menubar's
       │    AccessibleMenuBar — works around a focused WebView2 swallowing
       │    those keys (wx #24786)
       ├─ AccessibleWebView (wx.html2.WebView, from wx-accessible-webview)
       │    ├─ hosts the welcome view via vrp/views.py/vrp/html.py when no
       │    │    radio is loaded
       │    ├─ owns document chrome, lang="en", styles, status live region
       │    └─ JS → Python bridge: window.vrp.postMessage({action, ...})
       │                            → MainWindow.on_bridge_message
       ├─ AccessibleGrid (wx-accessible-grid) — the PRODUCTION channel grid,
       │    built by MainWindow._show_grid, replacing the webview control
       │    while a radio is loaded:
       │    ├─ vrp/channel_grid_model.py : ChannelGridModel adapts
       │    │    chirp_backend (build_column_defs, memory_ops.set_field/
       │    │    delete_range) to the library's GridModel — editing routes
       │    │    through CHIRP's own validation, so the value the screen
       │    │    reader confirms is authoritative
       │    ├─ real in-place cell editing (text/combo), Space/Ctrl+Space/
       │    │    Shift+arrow selection, Delete, and a context menu (row menu
       │    │    reachable via Applications key, Shift+F10, or VoiceOver's
       │    │    VO+Shift+M)
       │    └─ Edit ▸ Select All Channels (Ctrl+A) / Clear Selection call the
       │         grid's own select_all_rows()/clear_selection()
       ├─ native wx dialogs (input/editing — first-class NVDA support, shared
       │    with the native UI): edit_dialog · ops_dialog · find_dialog ·
       │    serial_dialogs · settings_dialog · bank_dialog · query_dialogs ·
       │    prefs_dialog
       ├─ vrp/html.py   : Jinja2 templates → HTML strings; render_view appends
       │                  the mandatory CHIRP attribution footer
       ├─ vrp/speech.py : prism (prismatoid) supplemental speech; no-op if absent
       └─ chirp_backend/: radio.py, memory_ops.py, col_defs.py  (framework-agnostic)
            └─ chirp  (vendored ./chirp, used unmodified; serial + driver library)
```

Key points:

- **The channel grid is `AccessibleGrid`, not a read-only HTML table.** VRP's
  first cut of this UI rendered a read-only, paged `<table>` (via
  `vrp/views.py` + `templates/channels.html`) with per-row Edit buttons
  opening a dialog. That model was superseded by the editable
  `AccessibleGrid` (see PROGRESS_LOG.md "2026-06-20"); the old paged-table
  code remains in `vrp/views.py`/`templates/channels.html` as an internal
  fallback behind `if self._grid is None` checks in `vrp/app.py`, but isn't
  reached in normal operation — a radio being loaded always means
  `self._grid` is set. Don't extend the fallback path; extend the grid.
- **`wx-accessible-grid` 0.4.0** composes each cell's accessible name via
  `aria-labelledby` (channel + column header + value + control type) because
  VoiceOver never receives the runtime's live-region announcement on a
  VO+arrow move — the static name has to carry the information instead. NVDA
  gets the same name on focus; the library trims the plain-move echo so NVDA
  doesn't double-speak. Pinned to git tag `v0.4.0` in `pyproject.toml`
  (`[tool.uv.sources]`) until that version reaches PyPI.
- **Three command surfaces, kept in sync**: the native menu bar, in-page
  buttons, and global Ctrl-combo shortcuts. A focused WebView2 swallows
  one-shot Alt/Ctrl accelerators (wxWidgets #24786), so the bridged in-page
  shortcuts are the reliable key path for Ctrl combos; `wx-accessible-menubar`
  handles Alt/Alt+mnemonic/F10 for the menu bar itself and restores webview
  focus after a menu closes or the window is maximized/reactivated.
- **Known VoiceOver limitation:** cell-range selection with Shift+arrow does
  not work under VoiceOver (it intercepts the arrow keys before the page
  sees them). Row/channel selection works via Space, Ctrl+Space, and the
  VO+Shift+M row menu instead.

## CHIRP integration

- Vendored at `./chirp`, **used unmodified**, pinned to a tested commit.
- Installed editable via `[tool.uv.sources]` so `uv sync` sets up everything.
- `vrp/_chirp_path.py` reorders `sys.meta_path` so `import chirp` resolves to
  the real `chirp/chirp` package instead of the empty `./chirp` repo dir.
- Never import `chirp.wxui` (that's the inaccessible GUI we replace). Use the
  library: `directory`, `chirp_common`, drivers, settings, banks, sources.

## Packaging

PyInstaller single-exe with CHIRP bundled (`build.py`); switched from Nuitka,
which compiled all 552 CHIRP drivers to C and took 20–30 minutes per build
(see PROGRESS_LOG.md "Phase 9"). See README "Packaging with PyInstaller".
