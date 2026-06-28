# Plan — Wiring the grid keys (native channel grid)

> **Status:** IN PROGRESS. Branch: `feat/grid-key-wiring`. Windows implementation
> of `Ctrl+E` (full edit) + `F2` (single-cell edit) + the contextual context-menu
> item is **done and unit/smoke-tested**; the NVDA hand pass and the macOS path
> (gated on wx-accessible-grid#3) are still owed. Decisions A/B/C resolved below.
> This realizes the "Keyboard & function spec" in `GRID_RESTART_PLAN.md` against
> the *current* native grid (wx-accessible-grid 0.8.0 `AccessibleGrid`, a
> `DataViewListCtrl`), and is honest about what that architecture can and can't do.

---

## Goal

Make the channel grid's per-cell editing/navigation keys behave as closely to the
`GRID_RESTART_PLAN.md` spec as the native `DataViewListCtrl` allows, without
regressing screen-reader correctness on NVDA (Windows) or VoiceOver (macOS).

## What's already wired (done, shipped on `main`)

| Key | Behavior today |
|-----|----------------|
| `Up` / `Down` | Move row; screen reader reads the row |
| `Left` / `Right` | Move the cell cursor across columns. **Windows:** VRP speaks `"<value>, <column>"` via prism. **macOS:** VoiceOver's own `VO`+`Left`/`Right` reads cells natively |
| `Shift+Up`/`Down`, `Ctrl+Space` | Contiguous / non-contiguous selection |
| `F2` / `Enter` | Open the **full-channel** edit dialog (`EditChannelDialog`) |
| `Del` | Clear (erase) the selected channel(s) — keeps the slot |
| Apps key / `Shift+F10` | Row context menu (Edit / Delete / Move up/down / Move to / Organize / Go to / Banks) |

## Target (spec) vs. feasibility — the gap

| Spec item | Feasible on `DataViewListCtrl`? | Plan |
|-----------|-------------------------------|------|
| `Left`/`Right` = prev/next column | ✅ done | — |
| `Ctrl+E` = edit **full** channel | ✅ | Add `Ctrl+E` accelerator → current full dialog |
| `F2` = edit **this cell** (by column) | ⚠️ partial | `F2` opens the full dialog **pre-focused on the cursor's column** (Windows knows the column; macOS can't — see constraint #2). Not a true in-cell editor |
| In-cell edit box / combo / checkbox (`F2`/`Space` opens the editor *in the cell*) | ❌ | `DataViewListCtrl` is host-driven/read-only here; per-control in-cell editing isn't this architecture. The edit **dialog** is the editor (a real native control, reads correctly) |
| `Enter`/`Tab` = next column, `Shift+Tab` = prev | ❌ (don't) | **DECISION A:** keep `Tab` as native focus traversal (idiomatic; hijacking it breaks keyboard users). `Left`/`Right` already are the cell cursor. Likely drop `Enter`/`Tab`-for-columns |
| `Delete` = clear/erase | ✅ done | — |
| Context menu: `Ctrl+E`, contextual `F2` ("Edit frequency"), `U` up, `D` down, `Delete` | ⚠️ partial | Add a contextual **"Edit `<column>`"** item + single-letter `U`/`D` move items to the existing menu |

## Architectural constraints (read before coding)

1. **Editing is host-driven, not in-cell.** `DataViewListCtrl` doesn't give us an
   accessible in-cell editor per column. The "editor" is `EditChannelDialog` (a
   real native dialog that NVDA/VoiceOver read correctly). So "edit this cell"
   realistically means "open the dialog focused on this cell's field."
2. **macOS can't see the cell cursor — fix requested upstream.**
   wx-accessible-grid 0.8.0 only binds the `Left`/`Right` key handler when an
   `announce` callback is passed — which VRP does **only on Windows** (on macOS
   VoiceOver drives its own cell cursor and we stay silent). So
   `grid.current_cell()` returns the real column only on Windows; on macOS it's
   always column 0, so per-cell `F2` can't know the column there.
   **This is being addressed:** we asked the maintainer to let the cursor's
   column *tracking* be enabled without a *speaking* callback (so the host can
   track the column silently on macOS and let VoiceOver speak) —
   [Community-Access/wx-accessible-grid#3](https://github.com/Community-Access/wx-accessible-grid/issues/3).
   - **If #3 lands:** pass `track_cursor=True` (announce stays `None`) on macOS →
     `current_cell()` works there → per-cell `F2` works on both platforms.
   - **Until then (or if declined):** per-cell `F2` is Windows-only; on macOS
     `F2` falls back to the full dialog. Optionally bind our own key handler on
     `grid.control` to track the column downstream (the issue notes this fallback).
   - **Open feasibility question (in #3):** whether plain `Left`/`Right` reach the
     control's `EVT_KEY_DOWN` under VoiceOver at all — gating whether even the
     downstream fallback works on macOS.
3. **Verify on device.** Every change here is screen-reader behavior. Per the
   project's verify-before-commit rule, the NVDA (and, where relevant, VoiceOver)
   hand pass is required before the work is considered done; functional tests
   prove wiring/strings, not audible output.

## Decisions (RESOLVED)

- **A — Tab/Enter for columns → resolved: don't hijack `Tab`.** `Tab` stays
  native focus traversal; `Enter`/double-click stays full-channel edit;
  `Left`/`Right` are the cell cursor.
- **B — per-cell editor → resolved: B2, a single-field editor.** `F2` opens
  `EditCellDialog` (one column, the right control type) for the cursor's cell;
  `Ctrl+E`/`Enter`/double-click open the full `EditChannelDialog`.
- **C — context-menu `Edit <column>` → resolved: contextual, from the cursor
  column** ("Edit cell — Frequency"), shown only when the cursor is on an
  editable, named column (Windows now; macOS once #3 lands).

## Implementation steps (sequenced)

1. **`Ctrl+E` → full-channel edit.** ✅ DONE — Channels-menu item
   `&Edit channel…\tCtrl+E` → `on_edit_channel`; `APP_SHORTCUTS`/F1 updated.
   `Enter`/double-click still open the full dialog (unchanged).
2. **Single-cell editor.** ✅ DONE — `EditCellDialog` (`vrp/edit_dialog.py`): one
   column, the right control type, same validate-on-OK path. Control builders
   factored to module-level helpers (`make_field_control`/`control_value`) shared
   with `EditChannelDialog`. *Tests:* text + choice value round-trips.
3. **`F2` → edit the cursor's cell.** ✅ DONE — `ChannelGrid.focused_cell()`
   returns `(channel, column_name)` from the cell cursor; `on_edit_cell` opens
   `EditCellDialog` for that column, applies via `update_channel({col: value})`,
   refreshes/refocuses. Number column / read-only / unknown column (macOS) →
   falls back to `on_edit_channel`. `F2` is the Channels-menu `Edit cell…`
   accelerator. *Tests:* cursor→cell mapping; smoke confirms routing
   (number col → full dialog, data col → single-cell dialog).
4. **Context menu: contextual edit.** ✅ DONE — `on_grid_context_menu` adds
   "Edit cell — `<column>`\tF2" when the cursor is on an editable named column.
   `U`/`D` move already work as the open menu's `&up`/`&down` mnemonics (no change
   needed). *Smoke:* contextual item present on a data column.
5. **Docs + F1 sync.** ✅ DONE — `docs/keyboard-map.md` (menu table + grid table),
   `APP_SHORTCUTS` (F1). `GRID_RESTART_PLAN.md` spec annotation: TODO at merge.
6. **Hand pass.** ⏳ OWED — NVDA (Windows): `Ctrl+E`, `F2`-on-cell, context-menu
   item all read and act correctly. macOS: gated on #3 (per-cell `F2` falls back
   to the full dialog until then). Per verify-before-commit, confirm on device
   before the screen-reader claim is final.

## Test strategy

- Headless/GUI smokes (like the existing grid smokes): `current_cell()` → column
  mapping; `EditChannelDialog(focus_field=...)` focuses the right control;
  context menu contains the expected items. These verify *wiring*, not audio.
- Keep the full suite green; add per-change tests as above.

## Out of scope (explicitly)

- True in-cell editors (combo dropdown / checkbox toggle *inside* the cell) — not
  this architecture (constraint #1).
- Hijacking `Tab` for column movement (DECISION A).
- macOS app-level cell cursor (constraint #2) — VoiceOver owns it there.
