# Plan — Rearranging memory channels: selection model + clipboard (cut/copy/paste)

> **Status:** AGREED 2026-06-27 — all design decisions resolved (see "Decisions"
> and the former open questions, now folded in). Ready to implement. Extends the
> native channel grid (`vrp/native/`) so whole **rows** (channels) can be selected
> and rearranged with a clipboard, on top of the existing Move up/down/to.
> **Rows only — cells are never moved.**

---

## Goal

Let the user select one or more whole channels and rearrange them fluidly with a
keyboard clipboard model that NVDA users already know from Windows list views:
move a focus cursor independent of the selection, toggle rows into a selection,
extend a contiguous selection, and **cut / copy / paste** whole rows. Keep every
action screen-reader-correct (focus + announce) and respect the radio's **fixed
channel count** (slots are overwritten or shifted, never added/removed).

## What already exists (don't rebuild)

- **Backend ops** (`chirp_backend/memory_ops.py`) already do overwrite move/copy
  by destination:
  - `move_to(numbers, dest)` — write block at `dest`, **overwrite**, **erase
    source**; range-checked, rejects partial overlap. (= cut+paste/overwrite.)
  - `copy_memories(numbers, dest)` — write block at `dest`, **overwrite**, keep
    source. (= copy+paste/overwrite.)
  - `move_memories(numbers, ±1)` (swap adjacent), `delete_range` (erase, keep
    count), `delete_and_shift`, `insert_row`, `sort_range`, `arrange_range`.
  - `radio.erase_memory(n)` keeps the fixed count; `mem.immutable` slots refuse
    edits/erase.
- **Move commands** wired today: `Ctrl+Shift+Up/Down` (move up/down),
  `Ctrl+Shift+M` ("Move to channel…"), and "Copy to channel…" in the Organize
  dialog. Context menu has Move up/down/to.
- **Grid selection/focus API** (`vrp/native/channel_grid.py` over the library's
  `AccessibleGrid`): `selected_channel_numbers()`, `selected_count()`,
  `focused_channel()`, `select_channels()`, `focus_channel()`, plus the library's
  `select_rows()/selected_rows()/focus_row()/focused_row()`. VRP already owns an
  `EVT_KEY_DOWN` handler on the list (`_on_shift_f10`) bound *after* the library's
  Left/Right cursor handler — the hook for new navigation keys.

## Decisions (RESOLVED 2026-06-27)

- **D1 — Paste = overwrite at the focused channel**, matching the backend and the
  fixed channel count (nothing falls off the end). **On conflict** (destination
  slots occupied) show a dialog: **Overwrite** / **Move (make room)** / **Cancel**
  (see "Conflict dialog").
- **D2 — Cut is deferred** (file-manager style): `Ctrl+X` only *marks* the rows;
  the source is untouched until `Ctrl+V`, which performs the move (overwrite or
  make-room per D1) and then erases the source. No paste ⇒ no change. `Esc`, a new
  cut/copy, or pasting clears the pending cut.
- **D3 — Clipboard snapshots the row data** — `Ctrl+C`/`Ctrl+X` deep-copy
  (`mem.dupe()`) the selected `Memory` objects into an in-app clipboard, so the
  clipboard survives later edits to the source and can support pasting into a
  different radio image later. Adds a backend `paste_block(mems, dest, ...)` op.
- **D4 — A new Edit menu.** The native menu bar (File/Radio/Channels/Help) gains
  an **Edit** menu (between File and Radio) holding **Select All (Ctrl+A), Clear
  Selection, ──, Copy (Ctrl+C), Cut (Ctrl+X), Paste (Ctrl+V)**. Copy/Cut/Paste
  also go in the row context menu.
- **D5 — "Move" in the conflict dialog = shift-down-insert.** When the user
  chooses Move, shift the occupied destination channels (and everything below)
  **down** by the clipboard size to make room, then drop the pasted rows at the
  cursor. Requires enough empty slots near the tail to absorb the shift; otherwise
  the paste is **blocked with a clear reason** (no silent data loss off the end).
- **D6 — In-app clipboard only for v1.** Copy/cut/paste operate within the current
  radio image. No OS clipboard and no cross-image paste yet; the snapshot design
  (D3) leaves the door open to add them later.

## Keyboard & menu spec

### Selection / cursor (grid navigation — handled in the grid, not the menu)
| Key | Action |
|-----|--------|
| `Up` / `Down` | Move the row; selection follows (today's behavior) |
| `Ctrl+Up` / `Ctrl+Down` | Move the **focus cursor** to the prev/next row **without changing the selection** *(new)* |
| `Space` / `Ctrl+Space` | Toggle the focused row in / out of the selection |
| `Shift+Up` / `Shift+Down` | Extend a **contiguous** selection from the anchor |

### Clipboard & move (Edit + context menus, each with an accelerator)
The native menu item's accelerator *is* the global shortcut (one surface — see
CLAUDE.md "Command Surfaces"), so these need no manual key binding.
| Key | Menu | Action |
|-----|------|--------|
| `Ctrl+C` | Edit, context | Copy selected rows to the clipboard |
| `Ctrl+X` | Edit, context | Cut selected rows (deferred — marks them) |
| `Ctrl+V` | Edit, context | Paste at the focused channel (overwrite / conflict dialog) |
| `Ctrl+A` | Edit | Select all channels |
| — | Edit | Clear selection |
| `Ctrl+Shift+Up/Down/M` | Channels, context | Move up / down / to (existing) |

All clipboard items are gated on a loaded radio; Paste is additionally disabled
when the clipboard is empty; Copy/Cut disabled when nothing is selected.

## Architecture

### 1. Selection model (the riskiest part — spike FIRST)
The Windows grid is the **generic, custom-drawn DataViewCtrl** (not a native
common control), so we cannot assume it implements the standard focus-vs-selection
list model. **Step 0 is an NVDA spike** confirming what the control already does:
- Does `Shift+Up/Down` extend selection and `Ctrl+Space` toggle? (claimed today)
- Does `Ctrl+Up/Down` move focus *without* changing selection? (likely NOT native)
- Does plain `Space` toggle the focused row?

For anything the control doesn't do, wire it in `channel_grid.py` by extending the
existing `EVT_KEY_DOWN` handler (the one that does Left/Right + Shift+F10), using
the library's `focus_row()/select_rows()/selected_rows()/focused_row()`. New grid
methods (pure-ish, announced via the `Announcer` on Windows like the cell cursor):
- `move_focus(direction)` — `SetCurrentItem` to prev/next row, **no** selection
  change; ensure visible; announce the row.
- `toggle_focused_selection()` — add/remove the focused row from the selection.
- `extend_selection(direction)` — grow/shrink the contiguous range from a tracked
  **anchor** row (set when a plain move or a fresh selection starts).
- Track `_selection_anchor` for Shift+range behavior.

**macOS/VoiceOver caveat** (consistent with the existing #3 caveat and the webview
note that Shift+Arrow range-select doesn't work under VoiceOver): VoiceOver drives
its own selection with VO+keys and intercepts arrows. Target **Windows/NVDA
first**; on macOS fall back to VoiceOver-native selection and the menu/context-menu
items (which always work). Don't fight VoiceOver for arrow keys.

### 2. Clipboard state (on `MainWindow`)
```python
# Snapshot clipboard for whole-row rearrange. None = empty.
self._clipboard: _Clipboard | None = None
# _Clipboard: mode: Literal["copy","cut"]; mems: list[Memory] (dupes, renumbered
# to 0..n-1 offsets); source_numbers: list[int]; source_radio_id (for future
# cross-image guard / same-radio check).
```
- **Copy** (`on_copy`): snapshot `radio.get_memory(n).dupe()` for each selected
  number; mode="copy"; announce "Copied N channel(s)."
- **Cut** (`on_cut`): same snapshot; mode="cut"; remember `source_numbers`;
  announce "Cut N channel(s) — paste to move them." **Source untouched** (D2).
- **Paste** (`on_paste`): destination = `focused_channel()`. Compute the dest
  range `[dest, dest+len-1]`; range-check. Detect occupied dest slots → maybe the
  conflict dialog (below). Then call the backend (below). For mode="cut": after a
  successful write, the op also erases `source_numbers` not in the dest range, and
  the clipboard is cleared (cut is one-shot). For mode="copy": clipboard kept.
- Clear the pending cut on `Esc` in the grid, on a new copy/cut, and after paste.

### 3. Backend: `paste_block` (new, in `memory_ops.py`)
```python
def paste_block(mems, destination, *, cut_from=None, make_room=False) -> OpResult:
    """Write a snapshot block of Memory objects starting at `destination`,
    renumbering them. Overwrites by default; if make_room, shift existing
    channels from `destination` down by len(mems) first (requires enough empty
    tail slots, else fail). If cut_from is given, erase those source numbers not
    within the written range (the move/cut case). Range-checked; immutable slots
    reported, not silently skipped."""
```
- Generalizes `copy_memories` (cut_from=None, make_room=False) and `move_to`
  (cut_from=source). Consider refactoring those two to call it, or leave them and
  add `paste_block` alongside (decide during impl; keep their tests green).
- Returns `(ok, message, affected_channels)` like every op; the handler refreshes
  `affected` and focuses the first pasted channel.
- **make_room math** is the subtle part: shifting on a fixed-size radio can push
  channels off the end — only allowed when the tail has ≥ len(mems) empty slots
  in the shift region; otherwise fail with a clear message. The cut + make_room +
  overlapping source/dest combination is the trickiest; cover it with tests.

### 4. Conflict dialog (D1)
On paste, if any destination slot in `[dest, dest+len-1]` is non-empty:
- Title/message: "Channels `dest`–`end` are not empty." Buttons:
  - **Overwrite** → `paste_block(..., make_room=False)`
  - **Move (make room)** → `paste_block(..., make_room=True)` (shift existing
    down; may fail if not enough empty tail — announce why)
  - **Cancel** → no-op, keep clipboard
- Native `wx` dialog: role=dialog, focus-trapped, Esc=Cancel, returns focus to the
  grid (Accessibility Rule #4). If the dest is entirely empty, skip the dialog and
  overwrite directly.

### 5. Menu wiring
- Add `_build_edit_menu` → File, **Edit**, Radio, Channels, Help. `_add(...)` each
  Copy/Cut/Paste with accelerators + `needs_radio=True`; track Paste/Copy/Cut
  enable state in `_update_menu_state` (Paste needs a non-empty clipboard; Copy/Cut
  need a selection).
- Add the same three to `on_grid_context_menu` (near the existing Move items).
- Add the combos to `APP_SHORTCUTS` (F1) and update `docs/keyboard-map.md` +
  `docs/chirp-feature-coverage.md`.

## Edge cases / rules
- **Fixed count:** paste never changes the channel count; overwrite replaces,
  make-room shifts within bounds (or fails). Never add/remove slots.
- **Immutable slots:** pasting onto / erasing an immutable slot must report a
  clear failure, not partially apply (mirror existing op behavior).
- **Empty rows:** copying an empty channel is allowed (it pastes "blank" over the
  dest — useful for clearing); or skip empties — decide in impl, default allow.
- **Partial overlap** of source and dest on a cut/move: reuse `move_to`'s rule
  (reject partial overlap) or handle via snapshot (snapshot makes overlap safe
  since we hold copies) — snapshot likely removes this restriction; verify.
- **Selection after paste:** select the pasted block, focus its first channel,
  announce "Pasted N channel(s) at channel X" (Rule #3 + #6).
- **No selection / no focus / clipboard empty:** announce a gentle message, no-op.

## Implementation steps (sequenced)
0. **NVDA selection spike** — verify what the generic DataViewCtrl already does
   for `Shift+Arrow` / `Ctrl+Space` / `Ctrl+Arrow` / `Space`. Decide what to wire.
   *(verify-before-commit: this gates the whole selection model.)*
1. **Selection model in `channel_grid.py`** — `move_focus`, `toggle_focused_
   selection`, `extend_selection` + anchor; bind the new keys in the existing
   `EVT_KEY_DOWN` handler; announce via `Announcer` on Windows. NVDA pass.
2. **Backend `paste_block`** + unit tests (overwrite, make-room success/﻿fail on
   fixed count, cut+erase-source, overlap, immutable, empty). Per the testing rule.
3. **Clipboard + handlers** (`on_copy/on_cut/on_paste`, `_Clipboard`) in
   `main_window.py`; deferred-cut bookkeeping; selection/focus/announce after.
4. **Conflict dialog** (overwrite / move / cancel), native + accessible.
5. **Menus** — new Edit menu + context-menu items + `APP_SHORTCUTS`;
   `_update_menu_state` enable/disable; update `GetMenuCount()` test (4 → 5) and
   the Radio-menu-index assertion in `tests/test_channel_grid.py`.
6. **Docs** — `docs/keyboard-map.md` (native selection + Edit menu tables),
   `docs/chirp-feature-coverage.md`, F1 list.
7. **Full NVDA hand pass** of the whole flow; macOS/VoiceOver noted as follow-up.

## Test strategy
- Backend: `paste_block` gets full unit coverage (every memory op must — project
  rule), including fixed-count make-room boundaries and cut+source-erase.
- Grid: headless smokes for `move_focus`/`toggle`/`extend` selection math and the
  clipboard handler routing (snapshot taken, dest computed, op called, selection
  after) — these verify wiring/strings, **not** audio.
- Menu: extend the existing menu-count/structure test for the new Edit menu.
- Audio (cursor/selection announcements) is verified on-device per
  [[feedback-verify-before-commit]], not by tests.

## Resolved (formerly open questions, 2026-06-27)
1. **"Move" in the conflict dialog = shift-down-insert** (D5): shift the occupied
   destination channels down to make room and insert the pasted block, bounded by
   empty tail slots; block with a reason if there isn't room.
2. **Select All + Clear Selection are included** in the Edit menu now (D4).
3. **In-app clipboard only for v1** (D6): no OS clipboard / cross-image paste yet;
   the snapshot design leaves room to add them later.
