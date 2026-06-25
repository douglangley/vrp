# Native channel grid under VoiceOver — feasibility (2026-06-24)

**Question.** Can VRP retire the webview UI and run ONE native wx UI on every
platform, including macOS/VoiceOver? The blocker on record: making the native
`wx.ListCtrl` grid the macOS default "silently muted the app" under VoiceOver
(PROGRESS_LOG 2026-06-21). Nobody investigated the muteness — it was only
observed, then worked around by routing macOS to the webview.

**Environment (confirmed).** wxPython **4.2.5**, **osx-cocoa (Phoenix)**,
wxWidgets **3.2.9**. The production grid is `vrp/native/channel_grid.py`: a
`wx.ListCtrl` built with `LC_REPORT | LC_VIRTUAL | LC_HRULES`, populated lazily
via `OnGetItemText(item, column)`, ~500 rows × up to 14 columns, multi-select.

---

## Mechanism — why a virtual report-mode `wx.ListCtrl` is mute on VoiceOver but fine on NVDA

`wx.ListCtrl` is not one control; it's a façade over a per-platform backend, and
the backend decides what the accessibility API sees.

- **Windows.** `LC_REPORT` `wx.ListCtrl` is a thin wrapper over the native
  Win32 **SysListView32** (list-view common control). That control already
  implements MSAA/UIA: each subitem is exposed as a cell with text, the header
  exposes column names, selection state is reported. NVDA reads it directly with
  zero extra work. Virtual mode (`LC_VIRTUAL`) changes only *where the text
  comes from* (the `OnGetItemText` callback instead of stored items) — the
  control still renders through SysListView32, so the accessibility surface is
  unchanged. This is why VRP's grid reads perfectly under NVDA.

- **macOS.** There is **no native Cocoa list-view that matches `LC_REPORT`'s
  multi-column report layout**, so wxWidgets falls back to its **generic**
  (`wxGenericListCtrl`) implementation: wx draws the rows, header, and grid
  lines itself into a plain `NSView`. A custom-drawn `NSView` is, by default,
  **not an accessibility element** and exposes **no children, no rows, no cells,
  no role** to NSAccessibility. VoiceOver sees an opaque empty view — hence
  "silently muted." wxWidgets' generic list provides only a partial, largely
  non-functional `wxAccessible` shim on macOS; it does not synthesize the
  NSAccessibility row/cell tree VoiceOver needs. Virtual mode makes this *worse*
  if anything (no backing `NSCell`/item objects exist at all). So the muteness
  is **structural**, not a bug we can patch in VRP — it's the generic backend
  having essentially no NSAccessibility implementation.

**The fix is to pick a wx control that wraps a REAL native Cocoa view**, because
those views carry Apple's own NSAccessibility implementation for free.

---

## Ranked candidate approaches for VoiceOver-readability on macOS

1. **`wx.dataview.DataViewListCtrl` / `DataViewCtrl` — best, and almost
   certainly what "Taylor" used.** On macOS, `wxDataViewCtrl` wraps a native
   **`NSTableView`** (and `NSOutlineView` for tree mode). `NSTableView` ships
   Apple's full NSAccessibility table implementation: it exposes the table role,
   rows, columns, per-cell values, and the column headers, all of which
   VoiceOver reads out of the box — including per-column cell values
   ("Frequency, 146.520"). This is the standard answer to "I need a wx grid that
   VoiceOver reads," and it matches the peer report. `DataViewListCtrl` is the
   simple list-of-rows API; `DataViewCtrl` + a custom `wx.dataview.DataViewModel`
   is the virtual/large-data form (see migration sketch).

2. **`wx.grid.Grid` — secondary, uncertain.** `wxGrid` is also a generic,
   wx-drawn control on macOS (like the generic ListCtrl), BUT it carries a more
   developed `wxGridCellAccessible`/`wxGridAccessible` layer than the generic
   list. Real-world VoiceOver results are inconsistent across wx versions; worth
   testing in the spike but not the favorite. If DataView reads and Grid does
   not, prefer DataView.

3. **Non-virtual `wx.ListCtrl` (`LC_REPORT` without `LC_VIRTUAL`).** Same
   generic macOS backend as today; dropping virtual mode does **not** change the
   NSAccessibility story. Not expected to help. (Included mentally as a control,
   not in the spike — it's the same dead end as Variant A.)

4. **Custom `wx.Accessible` override on the existing generic ListCtrl.** On
   Windows `wx.Accessible` bridges to MSAA. On macOS the `wxAccessible` →
   NSAccessibility path is **incomplete/largely unimplemented** in wxWidgets
   3.2.x, so hand-rolling a `GetChild`/`GetName`/`GetRole` tree is high-effort
   and likely still won't produce a navigable NSAccessibility table. Not worth
   it when a native-backed control exists. Lowest rank.

**Recommendation: migrate the native grid to `wx.dataview` (DataViewListCtrl
for the simple case, DataViewCtrl + DataViewModel for 500-row virtualization).**
Confirm empirically with the spike before touching production.

---

## What to look for in the spike results

Run `uv run python tools/spike_native_voiceover.py`, VoiceOver on (Cmd+F5), Tab
between the three labeled controls, arrow through each. Record per variant:

- **Variant A (virtual ListCtrl):** expected **SILENT** (confirms the
  mechanism). If it *does* read, the whole premise changes — report that.
- **Variant B (DataViewListCtrl):** expected to read **rows AND per-column cell
  values**, ideally with column headers ("Frequency, 146.520"). This passing is
  the green light for migration.
- **Variant C (wx.grid.Grid):** unknown — note whether it reads cells, rows
  only, or nothing.

Decision: if B reads cells (+headers), migrate to DataView. If only C reads,
fall back to Grid. If none read, the native-everywhere goal is blocked and the
webview stays the macOS default.

---

## Migration sketch — `channel_grid.py` → DataView (IF Variant B passes)

The current grid is virtual for instant population at 500+ channels. DataView
supports the same via a model, so virtualization is preserved.

**Small radios / simplest port — `DataViewListCtrl`:**
- Replace `wx.ListCtrl(... LC_REPORT|LC_VIRTUAL)` with
  `wx.dataview.DataViewListCtrl(parent)`.
- `set_state`: `AppendTextColumn(label, width=...)` per column (from
  `grid_model.column_meta`), then `AppendItem([cell_text(row, col) ...])` per
  row from `grid_model.build_rows`. `DeleteAllItems()` / `ClearColumns()`
  replace `ClearAll()`.
- This stores all rows eagerly — fine functionally but loses virtualization.

**Production form (keep virtualization) — `DataViewCtrl` + `DataViewModel`:**
- Subclass `wx.dataview.DataViewVirtualListModel(row_count)`; implement
  `GetValueByRow(row, col)` (returns the same string `grid_model.cell_text`
  produces today), `GetColumnCount`, `GetColumnType` ("string"). This is the
  direct analog of `OnGetItemText` — `grid_model` stays unchanged and headless.
- `AssociateModel(model)`, then `AppendColumn(DataViewColumn(...))` per column.
- On edits/ops call `model.RowChanged(row)` / `RowValueChanged(row, col)` /
  `Reset(new_count)` instead of `RefreshItem` / `SetItemCount` — these are the
  refresh hooks `refresh_numbers` / `reorder_refresh` / `rebuild` map onto.

**Selection / focus API changes (the bulk of the porting work):**
- `GetFirstSelected`/`GetNextSelected`/`Select`/`Focus`/`GetFocusedItem` →
  `GetSelections()` (returns `DataViewItemArray`), `SetSelections`,
  `Select(item)`, `SetCurrentItem(item)`, `GetCurrentItem`. Rows are addressed
  by `DataViewItem`, not int index: convert with
  `model.GetItem(row)` / `model.GetRow(item)`. `index_to_number` /
  `number_to_index` in `grid_model` stay; only the wx-side lookup wrapper
  changes. `selected_channel_numbers` / `focus_channel` / `select_channels`
  in `channel_grid.py` get rewritten against the DataView API.
- Activation event: `EVT_LIST_ITEM_ACTIVATED` → `EVT_DATAVIEW_ITEM_ACTIVATED`;
  selection events → `EVT_DATAVIEW_SELECTION_CHANGED`; context menu →
  `EVT_DATAVIEW_ITEM_CONTEXT_MENU` (these are wired in `main_window.py`).

---

## Open risks

- **Inline / cell editing.** VRP edits channels via a separate native dialog
  (`edit_dialog.py`), not inline — so DataView's editable-column complexity is
  largely avoidable. Keep edits in the dialog; the grid stays effectively
  read-only/navigable. Confirm VoiceOver still reads cells in a read-only
  DataView (it should — NSTableView reads regardless of editability).
- **500-row virtualization.** `DataViewVirtualListModel` handles this, but the
  refresh granularity differs from `RefreshItem`; verify `refresh_numbers`'
  per-row repaint maps cleanly to `RowValueChanged` without full resets
  (full `Reset()` may drop VoiceOver focus, the same hazard `ClearAll` has).
- **Selection model.** `DataViewItem` indirection plus the moved-block
  re-selection logic (`selection_after_move*`) needs careful porting; the
  arithmetic stays in `grid_model` but the wx selection calls change shape.
- **Column sizing.** `_WIDTH` width hints carry over to `DataViewColumn`
  widths; auto-size behavior on macOS NSTableView differs — verify wide columns
  (name/comment) aren't truncated for VoiceOver (truncation can affect what VO
  speaks).
- **Focus-on-open announcement.** Today the grid takes focus and the Announcer
  speaks "Ready". With NSTableView, VoiceOver may announce the table itself on
  focus; confirm the landing row is read and there's no double-speak.
- **Per-OS regression.** DataView wraps native list-view on Windows too, so
  NVDA should still read it — but this changes the control NVDA reads, so the
  Windows NVDA pass must be re-run, not assumed.

**Next step:** owner runs the spike under VoiceOver and reports per-variant
results. No production change until Variant B (or C) is confirmed reading cells.
