# Plan — Undo/Redo for channel edits (Edit menu, context menu, Ctrl+Z / Ctrl+Y)

> **Status:** DRAFT (design 2026-06-27, all decisions resolved — redo is IN v1).
> Adds a bounded **undo + redo history** for channel-memory operations to the
> native UI, reversing/replaying edits, deletes, moves, copies, cut/paste, sort,
> insert, arrange, and import. Builds on [[project-grid-row-clipboard]] / the
> native grid.

---

## Goal

A reliable, screen-reader-friendly **Undo** (`Ctrl+Z`) and **Redo**
(`Ctrl+Y` / `Ctrl+Shift+Z`) — Edit menu + context menu — that reverse/replay the
last channel-memory operation(s), announcing what changed and restoring focus.
Scope v1: **channel memory** only (not radio Settings, banks, or download — see
"Scope").

## Why this is cheap: one choke point

**Every** channel write in the app goes through the loaded radio object's
`set_memory()` / `erase_memory()` — reached via `memory_ops._set_mem` /
`_erase_mem` (used by all ~12 ops) and `radio.py`'s own `set_memory`/
`erase_memory`. So undo is added by instrumenting that one choke point to capture
**pre-images**, not by editing each operation.

## Design: transaction + pre-image snapshots

A new `chirp_backend/undo.py` `UndoManager` (single instance, like the radio
state):

- **Recorder.** When a radio loads, wrap its `set_memory`/`erase_memory` so that —
  *only while a transaction is open* — the first write to a given channel first
  records that channel's **current** state as a pre-image:
  `pre[number] = radio.get_memory(number).dupe()` (carrying its `.empty` flag).
  Subsequent writes to the same channel in the same transaction are ignored (the
  original is already captured). Then the real write proceeds.
- **Transaction = one history entry.** Each public mutating op runs inside
  `with undo.transaction(label):`. On success it commits one entry
  `{label, before: [(number, Memory|empty)], after: [(number, Memory|empty)]}`
  onto a **bounded** undo stack (e.g. last 30; oldest dropped). `before` is the
  captured pre-images; `after` is the touched channels' state re-read at commit
  time (so redo can replay it). Empty transactions (no writes) commit nothing.
  Committing a new entry **clears the redo stack** (standard history semantics).
- **Nesting.** Some ops call others (`delete_and_shift` → `delete_range`), so the
  manager **ref-counts** transactions: inner calls record into the outer
  transaction and only the outermost commits an entry. (Prevents double entries /
  partial undo.)
- **Undo.** `undo.undo()` pops the top undo entry, restores its `before` images
  (`erase_memory(number)` if empty else `set_memory(image)`), pushes the entry
  onto the **redo** stack, and returns `(label, restored_numbers)`. The restore
  runs *outside* recording (it must not create a new history entry).
- **Redo.** `undo.redo()` pops the top redo entry, restores its `after` images,
  pushes it back onto the **undo** stack, and returns `(label, restored_numbers)`.
  Also outside recording.

Why pre-images per touched channel work for **every** op, including structural
ones (move/insert/shift/sort/paste-make-room): those ops just write channels, so
the recorder captures exactly the slots that changed and undo rewrites them. It
even cleanly reverses a partially-applied op that errored mid-way.

### Wiring the transaction around ops
Decorate each mutating function in `memory_ops.py` (e.g. `@undo.records`) so the
transaction opens automatically and the **label comes from the op's returned
message** ("Deleted 3 channels…", "Pasted 2 channels…") — no per-op label
strings to maintain. The decorator opens the transaction, runs the op, and
commits with `result.message` as the label only when `ok` is true (aborts/discards
the transaction on failure or no-op). Mutating ops to decorate: `set_field`,
`update_channel`, `import_memories`, `delete_memory`, `delete_range`,
`delete_and_shift`, `insert_row`, `move_memories`, `move_to`, `copy_memories`,
`paste_block`, `sort_range`, `arrange_range`.

## UI wiring (native)

- **Edit menu** (`_build_edit_menu`): add **Undo `Ctrl+Z`** and **Redo `Ctrl+Y`**
  at the **top**, then a separator before Select All. Also bind
  `Ctrl+Shift+Z` to redo (common alias) — as a second accelerator via an
  `wx.AcceleratorTable` entry or a hidden item, since a menu item shows only one.
  Optionally relabel the items to **"Undo <last label>" / "Redo <next label>"** on
  `EVT_MENU_OPEN` for discoverability (relabeling is safe; only *disabling* breaks
  accelerators — so keep them enabled, see below).
- **Context menu** (`on_grid_context_menu`): add **Undo** and **Redo** (with the
  relevant labels when present).
- **`APP_SHORTCUTS`** (F1): add `Ctrl+Z` "Undo the last change" and
  `Ctrl+Y / Ctrl+Shift+Z` "Redo". Update `docs/keyboard-map.md`.
- **Enable state:** gate on a loaded radio **only** (like Copy/Cut/Paste) — keep
  both enabled so the accelerators always fire; the handlers announce **"Nothing
  to undo" / "Nothing to redo"** when the respective stack is empty. (Disabling
  would kill the accelerator until the menu reopened.)

### `on_undo` / `on_redo` handlers (`MainWindow`)
1. `entry = undo.undo()` (or `undo.redo()`); if `None` → announce "Nothing to
   undo." / "Nothing to redo." and return.
2. `radio.invalidate_cache(restored_numbers)`; `self.grid.rebuild()`.
3. Select the restored channels, focus the first; announce **"Undid {label}."** /
   **"Redid {label}. Now on channel N."** (assertive).

## Scope (v1)

- **In:** all channel-memory ops listed above (the common edits).
- **Out (v1):** radio **Settings** (`set_settings`) and **bank** assignments —
  different write paths; leave non-undoable for now (or a Phase 3). **Download
  from radio** replaces the whole image — exclude from undo; **clear the undo
  stack** on download, on loading a new image, and on closing the image.
- **Save** doesn't change memory — leaves the stacks untouched.
- **Redo** — **in v1.** The redo stack is cleared whenever a new op commits and
  whenever the undo stack is cleared (load/close/download).

## Edge cases / rules

- **Stack lifetime:** cleared on new image load / close / download. Bounded depth
  (drop oldest). Pre-images are small `Memory` dupes — memory cost is trivial.
- **Immutable / failed writes:** if restoring a pre-image raises (immutable slot),
  report it (don't half-leave a confusing state); match existing op error
  behavior.
- **`is_modified`:** an undo is itself a change to the in-memory image — set/keep
  `is_modified` true (the file still differs from disk until saved). (Undoing back
  to the exact saved state could clear it, but that's a refinement, not v1.)
- **"Cannot be undone" warnings:** once undo lands, drop/relax the
  "This cannot be undone" text in the delete/move confirm dialogs.
- **Focus after undo:** restored block selected, first channel focused, announced
  (Accessibility Rules #3/#6).

## Implementation steps (sequenced)

1. **`chirp_backend/undo.py`** — ✅ DONE. `UndoManager` with injected
   `get_memory`/`set_memory`/`erase_memory` (no wx, no globals): ref-counted
   `transaction(label)` context manager, `record(number)` pre-image API,
   `commit`/`abort`, bounded **undo + redo** stacks, `undo()`/`redo()` (restore
   with recording suspended), `can_undo`/`can_redo`/`peek_*_label`/`clear`. 11
   headless unit tests in `tests/test_undo.py` (undo restores before, redo
   restores after, new op clears redo, nesting → one entry, empty txn → nothing,
   first-touch-only per channel, empty pre-image → erase, stack bound, empty
   stacks → None, abort on exception, clear).
2. **Recorder hook** — ✅ DONE. `radio.py` `_install_undo(radio)` wraps the CHIRP
   radio's `set_memory`/`erase_memory` (the real choke point — `memory_ops._set_mem`
   /`_erase_mem` call them directly) so each write `record()`s a pre-image into a
   fresh module-singleton `UndoManager` (`get_undo_manager()`); restores go through
   the *original* methods + `invalidate_cache`. Called on load_image/download;
   history dropped on `unload`. Guarded so a driver that refuses attribute
   assignment just disables undo. Tests: load installs / unload clears; write in a
   transaction is undoable+redoable; write outside isn't recorded; reload resets.
3. **Decorate `memory_ops` mutators** with `@undo.records` (label from result).
   Tests: each op kind produces one entry that round-trips (op → undo → original,
   then redo → post-op state), incl. a nested op (`delete_and_shift`).
4. **`on_undo`/`on_redo` + Edit menu + context menu + `Ctrl+Z` / `Ctrl+Y` /
   `Ctrl+Shift+Z` + `APP_SHORTCUTS`** in `main_window.py`; gate on loaded radio;
   "Nothing to undo/redo" when empty; rebuild + focus + announce. Tests: handler
   routes, empty-stack announces, post-undo/redo selection/focus (headless, like
   `tests/test_clipboard.py`).
5. **Docs** — `docs/keyboard-map.md` (Edit menu + Ctrl+Z/Ctrl+Y), F1 list,
   `docs/chirp-feature-coverage.md`; relax the "cannot be undone" confirm text.
6. **NVDA hand pass** — undo *and redo* of edit / delete / move / cut-paste /
   paste-make-room read and restore correctly; the "Nothing to undo/redo" paths;
   macOS/VoiceOver follow-up (menu/context-menu work there regardless).

## Test strategy

- Recorder + manager: full headless unit coverage (every memory op must round-trip
  through undo *and redo* — project testing rule), incl. nesting, redo-cleared-on-
  new-op, stack bound, empty txn, empty↔non-empty images.
- Handler: headless smokes (routing, empty-stack announces, selection/focus after).
- Audio (announcements) verified on device per [[feedback-verify-before-commit]].
