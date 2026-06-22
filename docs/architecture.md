# VRP Architecture

Versatile Radio Programmer is a wxPython desktop app that puts an accessible front end
on the CHIRP radio programming library. It does **not** run a web server.

There are two UIs sharing one backend:

- **Native UI (default, `vrp/native/`)** — a native `wx.ListCtrl` channel grid
  and a native `wx.MenuBar`. No webview, no WebView2, no JS bridge. Launched by
  `main.py` with no flags.
- **Legacy webview UI (`vrp/app.py`, launched with `--webview`)** — VRP's
  original UI: an `AccessibleWebView` hosting an HTML channel grid, bridged to
  Python over `window.vrp.postMessage`. Being retired; see PROGRESS_LOG.md
  "2026-06-21". Don't build new features on it.

Both UIs reuse the same native wx dialogs (edit, bulk operations, find,
settings, banks, download/upload, preferences) and the same `chirp_backend/`.

## Native UI (default)

```
main.py  (entry; runs the native UI unless --webview is passed)
  └─ vrp/native/app.py : run() → MainWindow (wx.Frame)
       ├─ native wx.MenuBar (File / Radio / Channels / Help) — built by
       │    _build_menubar/_add in main_window.py. Each item's label carries
       │    its accelerator (e.g. "&Save\tCtrl+S"); wx wires Alt-mnemonics and
       │    Ctrl-combos automatically — no WebView2 in the way, so none of the
       │    legacy UI's #24786 workarounds are needed.
       ├─ vrp/native/channel_grid.py : ChannelGrid (wx.ListCtrl, LC_VIRTUAL)
       │    ├─ virtual + multi-select: every channel is populated at once
       │    │    (no paging); OnGetItemText pulls from vrp/native/grid_model.py
       │    ├─ EVT_LIST_ITEM_ACTIVATED → on_edit_channel (F2/Enter opens the
       │    │    native edit dialog, same as the legacy UI's per-row button)
       │    └─ Shift+Arrow / Ctrl+Space select a block; Ctrl+Shift+Up/Down/M
       │         move it, re-selecting + focusing the result afterward
       ├─ native wx dialogs (input/editing — first-class NVDA support, SHARED
       │    with the legacy UI): edit_dialog · ops_dialog · find_dialog ·
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
  legacy UI's paging exists only there).
- **Editing still happens in native wx dialogs**, not in-grid: activating a
  row (F2/Enter) opens `edit_dialog.EditChannelDialog`, same dialog the legacy
  UI uses. Reordering (move up/down/to) happens directly on the grid's
  selection instead, since `wx.ListCtrl` selection/focus is cheap to manage
  without re-reading the whole table to a screen reader.
- **One command surface, not three.** The legacy UI needed a menu bar, in-page
  buttons, and a separate JS shortcut map because a focused WebView2 ate
  Alt/Ctrl accelerators (wx #24786). A real `wx.MenuBar` doesn't have that
  problem, so each command is wired exactly once — as a menu item whose label
  carries its accelerator — and `APP_SHORTCUTS` in `main_window.py` is just the
  list F1 displays, not a second wiring path.
- **No JS bridge.** Menu/grid event handlers in `MainWindow` call
  `chirp_backend` functions directly and push results to `ChannelGrid`
  (`refresh_numbers`/`reorder_refresh`/`rebuild`) and `Announcer` in the same
  Python call — there's nothing analogous to `on_bridge_message`.

### Key choices and why

- **Native `wx.ListCtrl`, not a webview.** The legacy webview UI proved out
  accessible HTML rendering, but it carried real cost: a second embedded
  browser process, a JS↔Python bridge, paging to keep the DOM small, and an
  ongoing fight with WebView2 swallowing keyboard input (wx #24786, the
  `wx-accessible-menubar` library, the in-page shortcut map). A native
  `wx.ListCtrl` and `wx.MenuBar` get NVDA/VoiceOver support, Alt/Ctrl
  accelerators, and unlimited-size population for free from wxWidgets itself.
- **Dialogs and `chirp_backend` are unchanged.** The native UI is a new
  presentation layer over the same validated backend and the same native wx
  dialogs the legacy UI already used for input — only the channel-grid host
  and the menu-bar/shortcut plumbing changed.
- **Status bar + prism for announcements, not ARIA.** There's no DOM, so
  there's no live region. `Announcer` writes a status bar field a screen
  reader can read on demand and optionally speaks via prism; the harder-working
  signal is still moving focus to the row/field a screen reader will read
  automatically.
- **Serial on a background thread.** Unchanged from the legacy UI: long radio
  I/O runs off the UI thread; progress is marshalled back with `wx.CallAfter`
  → `self.announce.announce(...)`.

## Legacy webview UI (`--webview`, being retired)

```
main.py --webview
  └─ vrp/app.py : VRPApp / MainWindow (wx.Frame)
       ├─ native wx menu bar (File / Radio / Channels / Help); keyboard access
       │    (Alt / Alt+mnemonic / F10) via wx-accessible-menubar's
       │    AccessibleMenuBar — works around a focused WebView2 swallowing
       │    those keys (wx #24786)
       ├─ AccessibleWebView (wx.html2.WebView, from wx-accessible-webview)
       │    ├─ renders the READ-ONLY, PAGED channel grid (semantic <table>) +
       │    │    welcome view, via vrp/views.py
       │    ├─ owns document chrome, lang="en", styles, status live region
       │    └─ JS → Python bridge: window.vrp.postMessage({action, ...})
       │                            → MainWindow.on_bridge_message
       ├─ native wx dialogs (input/editing — first-class NVDA support, shared
       │    with the native UI): edit_dialog · ops_dialog · find_dialog ·
       │    serial_dialogs
       ├─ editable grid preview via wx-accessible-grid's AccessibleGrid +
       │    vrp/channel_grid_model.py — try it with tools/grid_preview.py
       ├─ vrp/html.py   : Jinja2 templates → HTML strings; render_view appends
       │                  the mandatory CHIRP attribution footer
       ├─ vrp/speech.py : prism (prismatoid) supplemental speech; no-op if absent
       └─ chirp_backend/: radio.py, memory_ops.py, col_defs.py  (framework-agnostic)
            └─ chirp  (vendored ./chirp, used unmodified; serial + driver library)
```

This is VRP's original UI. It's kept behind `--webview` only until the native
UI above is confirmed at parity (real-hardware download/upload, NVDA-on-Windows
pass on the remaining preview pieces); it is not where new features land. Key
points, for reference while it still exists:

- **Grid is read-only and paged** (100 channels/page) to keep large radios
  (~10k channels) fast and avoid the screen reader re-reading the table on
  every interaction.
- **Three command surfaces, kept in sync**: the native menu bar, in-page
  buttons, and global Ctrl-combo shortcuts. A focused WebView2 swallows
  one-shot Alt/Ctrl accelerators (wxWidgets #24786), so the bridged in-page
  shortcuts are the reliable key path for Ctrl combos; `wx-accessible-menubar`
  handles Alt/Alt+mnemonic/F10 for the menu bar itself and restores webview
  focus after a menu closes or the window is maximized/reactivated.
- **wx-accessible-grid editable grid.** A real `<table role="grid">` driven by
  the aria-activedescendant pattern, so NVDA stays in focus mode and reads only
  the changed cell/headers, never the whole table — this is what the native
  UI's plain `wx.ListCtrl` replaced as the default.

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
