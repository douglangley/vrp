# wx-accessible-grid — architecture clarification & native-backend request

**To:** maintainer(s) of [Community-Access/wx-accessible-grid](https://github.com/Community-Access/wx-accessible-grid)
**From:** Versatile Radio Programmer (VRP), an accessible desktop radio
programmer (wxPython + CHIRP). Primary user is blind, NVDA on Windows;
VoiceOver on macOS secondary.
**Re:** v0.4.1 (commit `7123aab4d1ffaa5e1c81841174962e8933e80a14`)

> **Note up front:** this is **not** a "the README is wrong" report. We read the
> source and the README's description (a WebView-hosted ARIA grid) is accurate.
> This is a request to clarify whether a **native-control** backend exists or is
> planned, because our project needs native controls for data entry and wants to
> reserve a WebView strictly for help/documentation.

---

## What we want to build

A fully accessible, **editable** memory-channel grid using **native wx
controls**, where:

- Arrow keys move a single focused **cell** (not the whole row); moving across a
  row announces the column header, moving down a column announces the row
  header.
- `F2`/`Enter` edits a cell **in place** with the right control per column —
  edit box, combo box, checkbox, spin/stepper — `Enter` commits, `Esc` cancels.
- `Space`/`Ctrl+Space` select rows; `Delete` clears; a context menu (Apps key /
  `Shift+F10`) offers row actions.
- A WebView is used **only** for help/documentation screens, **never** for the
  data grid.

## What we found in the source (v0.4.1, `7123aab4`)

We vendored the library and read it. `AccessibleGrid` is a **WebView-hosted ARIA
grid**, by design:

- `src/wx_accessible_grid/grid.py` — `AccessibleGrid` *"owns an
  AccessibleWebView, renders [HTML]"*; it constructs `AccessibleWebView(...)`,
  binds `wx.html2.EVT_WEBVIEW_LOADED`, and pushes the table via
  `set_content(self._render_page())`. All cell navigation/editing/selection is
  gated on `self._awv.using_webview`.
- `src/wx_accessible_grid/assets.py` — the interaction model is JavaScript
  injected into the WebView; the grid is HTML `role="grid"` / `role="gridcell"`
  driven by the `aria-activedescendant` pattern.
- The only non-WebView path is `wx-accessible-webview`'s fallback: a **read-only
  `wx.TextCtrl`** showing tag-stripped text (`webview.py`) — a degraded text
  view, not a native grid.

**Conclusion:** the grid is WebView-only (with a text fallback). There is no
native-control grid backend. The README is correct about this.

## Why native matters to us (and why native wx grids fell short)

We evaluated the native wx options and could not get accessible per-cell
navigation + editing:

- **`wx.dataview.DataViewListCtrl`** — row-oriented. `GetCurrentColumn()` exists
  but there is **no `SetCurrentColumn()`**, `GetAccessible()` returns `None` on
  MSW, and there is no per-cell focus cursor announced to the screen reader as
  you arrow left/right within a row. It is native only on GTK (GtkTreeView) and
  macOS (NSTableView); on Windows it is wxWidgets' **generic** (custom-drawn)
  implementation.
- **`wx.grid.Grid`** — also generic/custom-drawn; inconsistent screen-reader
  results across versions.

This is, we believe, exactly the gap your library exists to fill — by going to a
WebView. We're trying to confirm whether that WebView is the *only* answer.

## Questions / request

1. **Is our reading correct** that wx-accessible-grid is WebView-only (no
   native-control backend)?
2. **Is a native backend in scope or on the roadmap** — e.g., a `DataViewCtrl`/
   `wx.grid.Grid` variant with a real accessible per-cell cursor, or a custom
   `wxAccessible`/UIA/NSAccessibility implementation that exposes per-cell
   navigation without a WebView?
3. **If native is not feasible**, is your recommended answer simply "use the
   WebView grid for the data table"? If so, we'll plan around hosting the WebView
   for the grid and accept that "WebView only for help" cannot hold.
4. **Optional doc suggestion:** the `wx-` name can read like a native wx widget.
   A one-line note near the top of the README ("this renders into a WebView; it
   is not a native wx control") would have saved us a round of confusion — even
   though the body already explains the WebView approach.

## Environment

- wxPython **4.2.5** (msw, Phoenix), wxWidgets **3.2.9**, Python **3.11**,
  Windows 11.
- wx-accessible-grid **0.4.1** (commit `7123aab4`), plus wx-accessible-webview
  and prismatoid (supplemental speech).
