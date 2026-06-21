# VRP Architecture

Versatile Radio Programmer is a wxPython desktop app that puts an accessible front end
on the CHIRP radio programming library. It does **not** run a web server.

```
main.py  (entry; applies the chirp import-path fix, then runs the app)
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
       ├─ native wx dialogs (input/editing — first-class NVDA support):
       │    edit_dialog · ops_dialog · find_dialog · serial_dialogs
       ├─ (preview) editable grid via wx-accessible-grid's AccessibleGrid +
       │    vrp/channel_grid_model.py — try it with tools/grid_preview.py;
       │    NVDA-on-Windows pass owed before it replaces the read-only grid
       ├─ vrp/html.py   : Jinja2 templates → HTML strings; render_view appends
       │                  the mandatory CHIRP attribution footer
       ├─ vrp/speech.py : prism (prismatoid) supplemental speech; no-op if absent
       └─ chirp_backend/: radio.py, memory_ops.py, col_defs.py  (framework-agnostic)
            └─ chirp  (vendored ./chirp, used unmodified; serial + driver library)
```

## Interaction model (current)

- **Grid is read-only and paged** (100 channels/page). Editing/operations happen
  in native wx dialogs, not in the DOM — this keeps large radios (~10k channels)
  fast and avoids the screen reader re-reading the table on every interaction.
  A preview/beta editable grid (see below) is the eventual replacement, pending
  an NVDA-on-Windows pass.
- **Native wx dialogs for all input**: edit one channel (edit_dialog), bulk
  operations (ops_dialog), find (find_dialog), download/upload (serial_dialogs).
  Native dialogs give focus trap, Escape, and NVDA name/role/value for free.
- **Three command surfaces, kept in sync** (see CLAUDE.md "Command Surfaces"):
  the native menu bar, in-page buttons, and global Ctrl-combo shortcuts. A
  focused WebView2 swallows one-shot Alt/Ctrl accelerators (wxWidgets #24786),
  so the bridged in-page shortcuts are the reliable key path for Ctrl combos;
  `wx-accessible-menubar` handles Alt/Alt+mnemonic/F10 for the menu bar itself
  and restores webview focus after a menu closes or the window is
  maximized/reactivated.

## Key choices and why

- **wxPython + AccessibleWebView, not Flask/PyWebView.** Embedded webviews
  historically read poorly in screen readers. `wx-accessible-webview` renders
  semantic HTML the screen reader treats like a real web page, while the native
  wx menubar gives first-class menu accessibility and global accelerators. No
  server means simpler packaging and no localhost surface.
- **HTML as strings, not served files.** Views are Jinja2-rendered fragments
  passed to `set_content`/`append`. The widget supplies `<html lang>`, head, and
  styles, so templates are body fragments. External `<link>`/`<script>` won't
  load (no HTTP origin); assets are inlined via `vrp.html.read_static`.
- **Bridge for interaction.** Page scripts post messages to Python; Python
  pushes updates back with `run_js`/`set_content`. Result envelope:
  `{ok, message, data}`; `message` is always announced.
- **wx-accessible-menubar for menu-bar keyboard access.** A focused WebView2
  swallows Alt/F10 at the OS level before wx ever sees them (#24786). The
  library (extracted from this app) bridges those keys from an in-page
  listener and drives the real native `wx.MenuBar` via
  `WM_SYSCOMMAND`/`SC_KEYMENU`, so the menu stays a genuine native menu — NVDA
  reads it, arrow keys navigate across top-level menus — and restores webview
  focus afterward. One maintained source of truth instead of duplicating the
  workaround inline in `vrp/app.py`.
- **wx-accessible-grid for in-place editing (preview).** The first in-grid-edit
  attempt used roving tabindex; an accessibility-lead review rejected it as a
  Critical (doesn't reliably trigger NVDA focus mode in WebView2). The library
  instead renders a real `<table role="grid">` driven by the
  aria-activedescendant pattern, so NVDA stays in focus mode and reads only the
  changed cell/headers, never the whole table. `vrp/channel_grid_model.py`
  adapts CHIRP's column defs and `memory_ops` to it. Not yet promoted to the
  production channels view — see PROGRESS_LOG.md "2026-06-20" for the
  promotion criteria.
- **Serial on a background thread.** Long radio I/O runs off the UI thread;
  progress is marshalled back with `wx.CallAfter` → `view.status(...)`.
- **prism for what ARIA can't say.** Transient confirmations and progress that
  don't move focus. Degrades to silence if no backend is present.

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
