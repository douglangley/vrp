# Plan — Wiring the grid keys (native channel grid)

> **Status:** DRAFT / planning. Branch: `feat/grid-key-wiring`. No code yet.
> This realizes the "Keyboard & function spec" in `GRID_RESTART_PLAN.md` against
> the *current* native grid (wx-accessible-grid 0.8.0 `AccessibleGrid`, a
> `DataViewListCtrl`), and is honest about what that architecture can and can't do.
> Edit freely — open decisions are marked **DECISION**.

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

## Open decisions (resolve before/while implementing)

- **DECISION A — Tab/Enter for columns:** recommend *not* hijacking `Tab` (keep
  native traversal) and keeping `Enter` = activate→edit. `Left`/`Right` stay the
  cell cursor. Confirm.
- **DECISION B — `F2`/`Enter` split vs. `Ctrl+E`:** spec wants `Ctrl+E` = full
  channel and `F2` = this cell. Options:
  - **B1 (recommended):** `Ctrl+E` and `Enter`/double-click → full dialog
    (unchanged); `F2` → full dialog **pre-focused on the cursor's column**
    (Windows) / first editable field (macOS). Lowest risk, one editing surface.
  - **B2:** `F2` opens a **single-field** dialog for just that column. Closer to
    the spec's wording, but a second editing surface to build/maintain.
- **DECISION C — context-menu `Edit <column>`:** label it from the cursor column
  on Windows ("Edit frequency"); on macOS, omit it or show generic "Edit cell"
  (no column known). Confirm wording.

## Implementation steps (sequenced; each lands with tests)

1. **`Ctrl+E` → full-channel edit.** Add the accelerator to the Channels menu
   (`_add(..., "edit_full", "&Edit channel…\tCtrl+E", self.on_edit_channel)`)
   and to `APP_SHORTCUTS`; update `docs/keyboard-map.md` + F1 list. (Keep `F2`
   for now; step 3 changes it.) *Test:* menu/accelerator present.
2. **Per-cell field focus in `EditChannelDialog`.** Add an optional
   `focus_field: str | None` param; when set, focus that field's control instead
   of the default. *Test:* dialog focuses the named field (headless wx smoke).
3. **`F2` → edit the cursor's cell.** New `on_edit_cell` handler: read
   `grid.current_cell()` → column name; open `EditChannelDialog(..., focus_field=col)`.
   On macOS (column unknown) fall back to the full dialog. Rebind `F2` (Channels
   menu) to `on_edit_cell`; keep `Enter`/double-click → full dialog (`on_edit_channel`).
   *Test:* with a known cursor column, the handler computes the right field.
4. **Context menu: contextual edit + `U`/`D`.** In `on_grid_context_menu`, add an
   "Edit `<column>`\tF2" item (Windows) wired to `on_edit_cell`, and `&Up\tU` /
   `&Down\tD` items wired to the existing move handlers (the menu is open, so
   single letters are safe). Keep the existing `Ctrl+E`/Delete/Move-to/etc.
   *Test:* menu contains the contextual + U/D items for a loaded radio.
5. **Docs + F1 sync.** Update `docs/keyboard-map.md`, `APP_SHORTCUTS` (F1), and
   `GRID_RESTART_PLAN.md` ("Keyboard & function spec" → mark done/divergences).
6. **Hand pass.** NVDA (Windows): `Ctrl+E`, `F2`-on-cell, context-menu items all
   read and act correctly. VoiceOver (macOS): `Ctrl+E` + dialog path. Record
   results; only then commit the screen-reader claim.

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
