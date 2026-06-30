# VRP Architecture

Versatile Radio Programmer is a wxPython desktop app that puts an accessible front end
on the CHIRP radio programming library. It does **not** run a web server, and has
**no webview or browser** anywhere.

**VRP has one UI, built entirely from native wx controls, on both Windows and
macOS.** The channel grid was historically the one control that didn't read on
every screen reader, which is why a second (webview) UI once existed. That
blocker is solved — the grid is now a `wx.dataview.DataViewListCtrl` that wraps a
native list-view per OS:

- **The UI (`vrp/native/`)** — a `wx.dataview.DataViewListCtrl` channel grid and
  a native `wx.MenuBar`. No webview, no WebView2, no JS bridge. On macOS
  `DataViewListCtrl` is a real native control (NSTableView), read directly by
  **VoiceOver**; on Windows it is wx's generic custom-drawn control, exposed to
  MSAA/UIA so **NVDA** reads it (see
  `docs/research/2026-06-24-native-grid-voiceover-feasibility.md` for why the old
  virtual `wx.ListCtrl` was silent under VoiceOver and this isn't).

`main.py` launches this UI (a `--debug` flag is the only option). The native wx
dialogs (edit, bulk operations, find, settings, banks, download/upload,
preferences) and the `chirp_backend/` layer sit underneath it.

> **History:** an embedded-webview UI (`vrp/app.py`, an `AccessibleWebView`
> hosting an editable HTML `AccessibleGrid` bridged to Python over
> `window.vrp.postMessage`) existed for screen readers that couldn't read the
> native grid. Once the native `DataViewListCtrl` was confirmed to read on every
> screen reader, the webview UI — and the `wx-accessible-webview`,
> `wx-accessible-menubar`, and `jinja2` dependencies it needed — was removed
> (PROGRESS_LOG.md "2026-06-29"). If in-app help/docs ever want an HTML view,
> build a small read-only `wx.html2.WebView` viewer (wxPython core, no extra
> dependency) rather than resurrecting that stack.

## The UI

```
main.py  (entry; launches the native UI)
  └─ vrp/native/app.py : run() → MainWindow (wx.Frame)
       ├─ native wx.MenuBar (File / Radio / Channels / Help) — built by
       │    _build_menubar/_add in main_window.py. Each item's label carries
       │    its accelerator (e.g. "&Save\tCtrl+S"); wx wires Alt-mnemonics and
       │    Ctrl-combos automatically.
       ├─ vrp/native/channel_grid.py : ChannelGrid (wx.dataview.DataViewListCtrl)
       │    ├─ native NSTableView on macOS (VoiceOver), wx's generic custom-drawn
       │    │    control on Windows exposed to MSAA (NVDA); multi-select; every
       │    │    channel populated at once (no paging) via AppendItem from
       │    │    vrp/native/grid_model.py
       │    ├─ EVT_DATAVIEW_ITEM_ACTIVATED → on_edit_channel (F2/Enter opens the
       │    │    native edit dialog; the grid itself is read-only/navigable)
       │    └─ Shift+Arrow / Ctrl+Space select a block; Ctrl+Shift+Up/Down/M
       │         move it, re-selecting + focusing the result afterward
       ├─ native wx dialogs (input/editing — first-class NVDA support):
       │    edit_dialog · ops_dialog · find_dialog · serial_dialogs ·
       │    settings_dialog · bank_dialog · query_dialogs · prefs_dialog ·
       │    info_dialog
       ├─ vrp/native/announce.py : Announcer — writes the status bar (field 0;
       │    field 1 permanently holds the CHIRP attribution) and speaks via
       │    vrp/speech.py (prism) if available. The PRIMARY announcement
       │    signal is still focus management (handlers move focus to the
       │    result row); the announcer covers summaries/errors with no
       │    natural focus target
       └─ chirp_backend/: radio.py, memory_ops.py, undo.py, bandplan.py,
            col_defs.py, bank_ops.py, query.py, serial_trace.py (framework-agnostic)
            └─ chirp  (vendored ./chirp, used unmodified; serial + driver library)
```

### Interaction model

- **Grid is unpaged.** The `DataViewListCtrl` is populated with every channel at
  once (`AppendItem` per row from `grid_model.build_rows`), so there's no
  page-by-page reading and no "channels per page" preference. The native list-view
  handles 500+ rows without paging; if eager population ever became a problem,
  `DataViewCtrl` + a `DataViewVirtualListModel` is the virtualized form (see the
  migration sketch in the research doc).
- **Editing happens in native wx dialogs**, not in-grid: activating a row
  (F2/Enter) opens `edit_dialog.EditChannelDialog`. The grid itself is
  read-only/navigable. Reordering (move up/down/to) happens directly on the
  grid's selection, since `DataViewListCtrl` selection/focus is cheap to manage
  without re-reading the whole table to a screen reader.
- **One command surface.** Each command is wired exactly once — as a `wx.MenuBar`
  item whose label carries its accelerator (e.g. `"&Save\tCtrl+S"`); wx handles
  Alt-mnemonics and Ctrl-combos. `APP_SHORTCUTS` in `main_window.py` is just the
  list F1 displays, not a second wiring path.
- **No JS bridge.** Menu/grid event handlers in `MainWindow` call `chirp_backend`
  functions directly and push results to `ChannelGrid`
  (`refresh_numbers`/`rebuild`) and `Announcer` in the same Python call.

### Key choices and why

- **Native `wx.dataview.DataViewListCtrl` for NVDA *and* VoiceOver.** A
  native-backed list-view and `wx.MenuBar` get screen-reader support, Alt/Ctrl
  accelerators, and large-list population for free from wxWidgets itself — no JS
  bridge, no paging. On macOS `DataViewListCtrl` is the native **NSTableView**,
  which carries the platform's full accessibility table implementation, so this
  control reads under VoiceOver where the earlier generic-backed `wx.ListCtrl`
  was silent; on Windows it is wx's generic custom-drawn control (not a native
  common control like SysListView32), but wx exposes it to MSAA/UIA so NVDA reads
  its rows (see PROGRESS_LOG.md "2026-06-21 — Platform-aware UI default" for the
  original ListCtrl regression and
  `docs/research/2026-06-24-native-grid-voiceover-feasibility.md` for the fix).
- **Status bar + prism for announcements, not ARIA.** There's no DOM, so there's
  no live region. `Announcer` writes a status bar field a screen reader can read
  on demand and optionally speaks via prism; the harder-working signal is still
  moving focus to the row/field a screen reader will read automatically.
- **Serial on a background thread.** Long radio I/O runs off the UI thread;
  progress is marshalled back with `wx.CallAfter` → `self.announce.announce(...)`.

## CHIRP integration

- Vendored at `./chirp`, **used unmodified**, pinned to a tested commit.
- Installed editable via `[tool.uv.sources]` so `uv sync` sets up everything.
- `vrp/_chirp_path.py` reorders `sys.meta_path` so `import chirp` resolves to
  the real `chirp/chirp` package instead of the empty `./chirp` repo dir.
- Never import `chirp.wxui` (that's the inaccessible GUI we replace). Use the
  library: `directory`, `chirp_common`, drivers, settings, banks, sources.

## Packaging

PyInstaller onedir build with CHIRP bundled (`build.py`), wrapped into a Windows
installer with Inno Setup (`installer.iss`, via `build.py --installer`) — the way
upstream CHIRP ships its own PyInstaller build. Switched from Nuitka, which
compiled all 552 CHIRP drivers to C and took 20–30 minutes per build (see
PROGRESS_LOG.md "Phase 9"). See README "Packaging with PyInstaller + Inno Setup".
