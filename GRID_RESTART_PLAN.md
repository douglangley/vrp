# VRP Grid Rebuild — Restart Plan & Keyboard Spec

> **Living document.** Edit the **"Keyboard & function spec"** section freely while
> we wait — add any keys or functions you think of. This is the source of truth
> for the restart; everything else here is context so we don't re-derive it.
>
> **Last updated:** 2026-06-27

---

## STATUS: WIRED — native grid runs on wx-accessible-grid 0.8.0 (with cell cursor)

- **The upstream native backend landed and is wired into the native grid.**
  After a fast iteration on 2026-06-27 the library settled on
  wx-accessible-grid **0.8.0** (commit `e2087ed`): `AccessibleGrid` wraps a
  **`wx.dataview.DataViewListCtrl`** — a real native table (NSTableView on
  macOS, so VoiceOver reads the row *and each cell by column*; the native list
  view on Windows/GTK for NVDA/JAWS/Orca). No WebView, HTML, or JS. This is
  exactly what `WX_ACCESSIBLE_GRID_FEEDBACK.md` asked for.
  - (Interim history: 0.5.0 was a native virtual `wx.ListCtrl`, *silent under
    VoiceOver* on macOS, so 0.7.0 rebased onto DataViewListCtrl; 0.8.0 then added
    back the opt-in Left/Right cell cursor — see the cell-nav bullet below.)
- **Integrated + wired (done):**
  - `pyproject.toml` requires `>=0.8.0`, pinned via a `[tool.uv.sources]` **git
    source** at commit `e2087ed` (0.8.0 is not on PyPI yet — PyPI's latest is
    0.4.1, the retired WebView grid). `uv sync` builds it from GitHub.
  - `vrp/native/channel_grid.py` is now a thin `wx.Panel` wrapper over the
    library's `AccessibleGrid` + a `GridModel` adapter (`_ChannelGridModel`),
    replacing VRP's bespoke `DataViewListCtrl`. The public method surface
    (`set_state`/`clear`/`selected_channel_numbers`/`focused_channel`/
    `selected_count`/`select_channels`/`focus_channel`/`popup_row_menu`/
    `refresh_numbers`/`reorder_refresh`/`rebuild`/`SetFocus`) is unchanged, so
    `main_window.py` needed only a small change: it passes the three grid event
    handlers as callbacks (the panel binds the `DataViewListCtrl` events).
  - `grid_model.py` gained `build_row(number)` for per-row refreshes.
  - All **119 tests pass**; a functional smoke (UV-5R, 128 rows) confirms
    populate/select/focus/per-row-refresh/reorder/rebuild/clear and the cell
    cursor (Right/Right/Left → spoke "146.52, Frequency", "TESTCH, Name",
    "146.52, Frequency") all work.
- **Cell navigation: LANDED in 0.8.0 and wired (issue #2 resolved).** The
  maintainer restored the opt-in Left/Right cell cursor on the DataViewListCtrl
  backend: `AccessibleGrid(..., announce=callable)` binds Left/Right, moves a
  column cursor, and voices `"<value>, <column>"` (or `"blank, <column>"`) via
  the callback; `current_cell()`/`current_column()` expose the cursor position.
  VRP wires `announce` to its prism `Announcer` **on Windows only** (assertive),
  where the generic DataViewCtrl announces no per-cell cursor; on macOS it stays
  `None` so VoiceOver's native VO+Left/Right cell reading is the single voice.
  (`vrp/native/main_window.py`, `cell_announce`; `channel_grid.py` forwards it.)
- **Still owed (the bar — NOT done):** the on-device **NVDA (Windows)** and
  **VoiceOver (macOS)** hand pass on the wired grid, including the new cell
  cursor's *audible* output (the announce string is verified; prism audio is not
  verifiable here). Per the verify-before-commit rule, do not finalize/commit the
  screen-reader claim until that pass is done.
- **Contextual `F2` single-cell edit: LANDED.** `F2` edits just the cursor's
  column via `grid.focused_cell()` (`on_edit_cell`), falling back to the
  full-channel dialog on the number column / immutable fields / when the cursor
  column is unknown (macOS until #3). After a successful edit it re-announces the
  new value as `"<value>, <column>"` (the same form the Left/Right cursor
  speaks) via `ChannelGrid.cell_display()`. **Verified audible under NVDA**
  (2026-06-27, commit `bbd9a74`). `Ctrl+E`/`Enter` still open the full-channel
  `edit_dialog`.
- **Known collateral:** 0.7.0's API dropped `ContextMenuItem` and the editor
  constants (`COMBO/TEXT/...`, `SetResult`), so the retired `--webview` stack
  (`vrp/app.py`, `vrp/channel_grid_model.py`, `tools/grid_preview.py`) no longer
  imports. The default native UI is unaffected. Decide: leave `--webview` broken
  (it's retired), make it fail gracefully, or port it.
- All exploratory changes from the previous attempt (vendoring the grid,
  flipping the default to the webview) were **reverted**. Clean slate.

---

## Confirmed architecture (decided)

- **Everything is native wx.** The channel grid **and** every dialog are native
  controls.
- **The grid uses the wx-accessible-grid library** — but only **after** the
  library is patched so its backend is a real native control, **not** a WebView.
  (Today the library renders an ARIA grid inside a `wx.html2.WebView`; that's the
  thing being patched.)
- **A WebView is allowed ONLY for help / documentation text.** Nowhere else —
  not the grid, not dialogs.
- **The current behavior is the target.** The per-cell navigation + in-cell
  editing UX we have today "works great"; the goal is to reproduce it cleanly on
  the native grid with the full, correct key set below.

---

## Keyboard & function spec  ← EDIT THIS SECTION

### Grid cell navigation
| Key | Action |
|-----|--------|
| `Up` / `Down` | Previous / next **row** |
| `Left` / `Right` | Previous / next **column** (cell) |
| `Enter` / `Tab` | Move to next column |
| `Shift+Tab` | Move to previous column |

### In-cell editing (control type depends on the column)
| Cell type | Behavior |
|-----------|----------|
| Edit box | `F2` **or** start typing → edit mode; `Enter` saves; `Esc` cancels |
| Combo box | `Space` or `F2` opens the list |
| Checkbox | `Space` checks / unchecks |

### Row / channel commands
| Key | Action |
|-----|--------|
| `Ctrl+E` | Edit the **full channel** in the native dialog. **No per-row "edit" button in the grid** — `Ctrl+E` replaces it. |
| `Delete` | **Clear (erase)** channel data — keeps the slot (see "Clear semantics" below) |

### Context menu (Applications key / `Shift+F10`)
| Key | Item |
|-----|------|
| `Ctrl+E` | Edit full channel |
| `F2` | Edit **this** cell, labelled with the column name — e.g. "F2 — Edit frequency", "F2 — Change CTCSS", "F2 — Change power level" |
| `U` | Move channel **up** (no-op if already at position 1) |
| `D` | Move channel **down** (no-op if already at the last position) |
| `Delete` | Clear channel |

> _Add more keys / functions here as you think of them._

---

## Clear / empty channel semantics (verified — code it this way)

- Radios have a **fixed channel count** (a 128-channel radio always has 128).
  "Delete/clear" must **erase the slot, not remove it** — 128 stays 128.
- The backend is already correct: `memory_ops.delete_range` → `_erase_mem` →
  `radio.erase_memory(n)`, which marks the slot `empty=True` and keeps the count.
  `mem.immutable` slots correctly refuse erase.
- **Do NOT** use `delete_and_shift` for plain `Delete` — that compacts/shifts
  channels up, which is the wrong behavior here.

---

## Who provides what (so we wire the right layer)

- **The library (once native) provides:** per-cell arrow navigation + row/column
  header announcements, `F2`/`Enter` in-cell editing of the control types,
  `Enter`/`Tab`/`Shift+Tab` between cells, `Space` for combo/checkbox,
  `Space`/`Ctrl+Space` row selection, `Delete`, and a context-menu callback.
- **VRP wires:** the column → control-type mapping (combo for
  tmode/duplex/mode/power, checkbox for booleans, edit box otherwise), `Ctrl+E`
  dialog, removing the in-grid edit button, the context-menu items (`Ctrl+E` /
  contextual `F2` / `U` / `D` / `Delete`), the move-up/down bounds checks, and
  `Delete` → erase.

---

## Restart sequence (when unblocked)

1. Update the vendored grid to the patched (native-backend) version; confirm it
   is genuinely a native control now.
2. **Hand pass with real screen readers FIRST** — NVDA on Windows and VoiceOver
   on macOS — confirming per-cell navigation + in-cell editing actually read,
   **before** building on top. Do not assume from docs.
3. Wire the keyboard/function spec above into the native UI; keep all dialogs
   native.
4. Verify `Delete` = erase keeps the channel count; add/extend tests per op.
5. Reconcile the docs to the final architecture.

---

## Verified findings (don't re-derive these)

- **wx-accessible-grid 0.4.1 is WebView-only today** (apart from a read-only
  `wx.TextCtrl` text fallback). It must be patched to a native backend before we
  build the "all native" UI on it. (Verified from its source: `grid.py` owns an
  `AccessibleWebView`; `assets.py` is JS in the WebView.)
- **`wx.dataview.DataViewListCtrl` cannot do accessible per-cell editing as-is:**
  no `SetCurrentColumn`, `GetAccessible()` is `None` on Windows, and there is no
  accessible per-cell cursor announced on Left/Right.
- **`radio.erase_memory(n)` is the correct "clear, keep count" operation.**
- **RESOLVED (2026-06-27):** the committed docs claimed `DataViewListCtrl` wraps
  "SysListView32 on Windows." That was **wrong** — `wxDataViewCtrl` is the
  *generic* (custom-drawn) control on Windows; it's native only on GTK and macOS
  (NSTableView). wx still exposes the generic control to MSAA/UIA, so NVDA reads
  its rows (confirmed by the NVDA pass) — but not via a native common control,
  which is why VRP supplies its own Left/Right cell cursor and Shift+F10 handler.
  The docs (`CLAUDE.md`, `README.md`, `docs/architecture.md`, `PROGRESS_LOG.md`,
  `tests/test_native_entry.py`) were corrected accordingly; the research doc's
  SysListView32 references are about the old `wx.ListCtrl` and remain accurate.
