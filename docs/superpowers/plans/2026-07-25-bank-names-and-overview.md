# Plan — Bank names and channels-in-a-bank overview (Phase 6.1)

> **Status:** Implemented 2026-07-25 on branch `feature/cross-radio-migration`
> (from docs baseline `6d1bfa7`). Suite **519 passed**; all four migration
> audits hold their baselines. The NVDA hand pass is the remaining work.

## Goal

Close the two bank gaps that cross-radio migration deliberately left open:

1. **Bank names cannot be changed.** Migration Phase 4 maps membership only and
   never renames a destination bank — a correct migration invariant, but it
   leaves the user with no way to rename a bank at all.
2. **There is no way to see what is in a bank.** Membership is only visible one
   channel at a time through Ctrl+B. Answering "which channels are in Bank A?"
   currently means opening every channel in turn.

Phase 6.1 adds accessible, verified, undoable bank renaming where the driver
supports it, plus a read-only per-bank channel overview with Go to channel.

This does **not** change any migration invariant. Migration still never renames
a destination bank, and bank names still do not transfer between radios.

## What CHIRP does

- `chirp_common.NamedBank(Bank)` adds `set_name`. The base implementation only
  assigns `self._name` and does **not** persist to the image; 16 driver modules
  override it to write the radio's memory map (Yaesu VX3/VX6/VX8, FT1D, FT2D,
  FT70, FT2900; Icom via `icf.py` plus IC-2730/IC-2820/IC-9x/ID-880; Kenwood
  THD74; Radtel RT880G/RT900; Retevis HA1G).
- CHIRP's own GUI gates renaming on `hasattr(bank, 'set_name')`, not on the
  `NamedBank` class (`chirp/wxui/bankedit.py:189`, `:200`).
- CHIRP's only rename affordance is **double-clicking a grid column header**
  (`chirp/wxui/bankedit.py:193`). It is mouse-only, performs no verification,
  reports no truncation, and is not undoable. This is precisely the class of
  interaction VRP exists to replace.
- `MappingModel.get_mapping_memories(mapping)` looks like the natural way to
  list a bank's channels, but `StaticBankModel`'s implementation is broken
  upstream: `count = (hi - lo + 1) / self._num_banks` is a float, so
  `range(count)` raises `TypeError` (`chirp/chirp_common.py:794`). VRP must not
  call it.

## Decisions

1. **Capability is per bank, discovered live.** Gate on
   `hasattr(bank, "set_name")`, matching CHIRP, rather than
   `isinstance(bank, NamedBank)`. Consistent with the existing bank invariant
   that driver behavior — not class hierarchy — is authoritative.
2. **Every rename is verified by rereading.** Because the base `set_name` does
   not persist and real drivers silently truncate or filter characters, a
   rename re-reads the bank through a fresh `get_mappings()` call and compares.
   A name that did not stick is a reported failure and does not set
   `is_modified`. A name that stuck in altered form (truncated, upper-cased,
   padding stripped) succeeds and the announcement states what was actually
   stored.
3. **Renames are radio-global undo state.** Bank names are not per-memory, so
   they go through `UndoManager`'s `get_global_state`/`set_global_state` hook.
   That hook is currently wired *exclusively* to D-STAR call lists and is only
   installed when `dstar_ops.requires_call_lists(radio)` is true. It becomes a
   **composite** snapshot covering call lists and bank names independently, so
   a radio with either or both gets correct Undo/Redo. Following the existing
   D-STAR invariant, a failed global snapshot is fail-closed: no rename.
4. **The overview is built from `get_memory_mappings`, not
   `get_mapping_memories`.** One pass over the channel range, asking each memory
   which banks it belongs to. This avoids the broken upstream `StaticBankModel`
   method and works uniformly for fixed, single, and multi bank models.
5. **The overview is read-only plus Go to channel.** Membership editing stays in
   Ctrl+B, which is already verified, rolled back on failure, and undoable.
   Go to channel reuses the existing `on_goto` pattern —
   `grid.select_channels([n])` then `grid.focus_channel(n)`.
6. **Unsupported cases are stated in words, never implied by a disabled
   control** (a11y rule 7). Fixed banks, banks the driver cannot rename, and
   unreadable bank metadata each get an explicit sentence in the dialog and in
   the announcement.
7. **Radio ▸ Manage banks… is the entry point.** Renaming is a radio-level
   operation; Ctrl+B is per-channel and today refuses to open on an empty
   channel (`bank_ops.get_bank_state`), which would make rename unreachable
   from an empty row. Ctrl+B gains a **Manage banks…** button as a cross-link
   and is otherwise unchanged.
8. **No new accelerator.** Like the other Radio-menu dialogs (Favorite radios…,
   Radio Info…), Manage banks… is menu-only. `APP_SHORTCUTS`, F1, and
   `help/KeyboardCommands.html` therefore need no change — that surface is only
   for accelerator-bearing commands.

## Planned surface

### `chirp_backend/bank_ops.py`

- `BankCatalog` gains `renameable: bool` (any bank exposes `set_name`).
- `BankDescriptor` gains `renameable: bool` per bank.
- `rename_bank(position, new_name) -> (ok, message, stored_name)` — `@undo.records`,
  verified by reread, fail-closed on snapshot failure.
- `capture_bank_names(radio)` / `restore_bank_names(radio, snapshot)` — global
  Undo/Redo state.
- `list_bank_channels(radio, position) -> (ok, message, rows)` — one pass over
  the channel range using `get_memory_mappings`; each row carries number,
  frequency, name, and driver order where the model is indexed.

### `chirp_backend/radio.py`

- Composite global snapshot replacing the D-STAR-only wiring at `:566-584`.
  Installed when the radio requires call lists **or** has renameable banks.

### `vrp/bank_manager_dialog.py` (new)

Accessible bank manager: a `RadioListView` of banks (name, index, channel
count), **Rename…**, **Show channels…**, **Close**. Rename uses a labelled
`wx.TextCtrl` in a small dialog, not an inline list edit. The channel list is a
second `RadioListView` with a **Go to channel** button. Per the wx label rule,
every `StaticText` label is created before its control.

### `vrp/bank_dialog.py`, `vrp/native/main_window.py`

Cross-link button; `Radio ▸ Manage banks…` menu item wired with
`needs_radio=True`, plus its handler.

### Tests

- `tests/test_bank_names.py` — real-driver rename, verify-on-reread,
  truncation reporting, non-persisting `set_name` treated as failure,
  fixed/unnameable rejection, Undo/Redo, save/reopen persistence, and composite
  global state on a radio that has both call lists and renameable banks.
- `tests/test_bank_overview.py` — channel listing across fixed/single/multi
  models, empty bank, and the `StaticBankModel` path that must not call
  `get_mapping_memories`.
- `tests/test_bank_manager_dialog.py` — accessible names, label-before-control
  order, filter/count, Escape, focus return, and read-only messaging.
- `tools/audit_bank_migrations.py` — extend the existing 70-model sweep to also
  record rename capability and, for renameable models, a
  write/verify/exact-restore cycle. Baseline to be recorded once run.

## Verification results (2026-07-25)

- Full suite **519 passed** (479 before, +40 new across four modules).
- **Ordinary migration audit unchanged:** 2,310 migrations, 814 imported,
  1,496 expected incompatibilities, zero unexpected failures.
- **Special audit unchanged:** 1,989 named slots, 1,007 imported, 982 expected
  incompatibilities, zero unexpected failures.
- **D-STAR audit unchanged:** 385-target sweep 13/372, plus 960 required-call-
  list cases 482/478, zero unexpected failures. This is the check that the
  composite global undo state did not disturb call-list handling.
- **Extended bank audit:** 70 bank models — 16 fixed, 54 mutable verified
  (unchanged), plus the new name sweep: **36 names verified** through
  write/reread/exact-restore, **33 not supported**, and **1 write ignored by
  the driver**, with zero unexpected failures.

### What the rename sweep found

The single "write ignored" model is **Kenwood TK-890**. Its `MemBank` exposes a
real `set_name`, so any capability check — `hasattr` or `NamedBank` — reports
the bank as renameable. The pinned image configures `grp_name_length` as **0**,
so `set_group_name` filters the entire name away and stores nothing while
raising no error.

This is the concrete justification for decision 2. Without rereading, VRP would
have announced "Bank renamed to Harbor" after storing nothing. It is now a
real-driver regression test
(`test_driver_that_accepts_but_discards_a_name_is_reported_as_failure`).

Icom ID-880H supplied the truncation case: a 6-character limit turns
"Repeaters" into "Repeat", which the announcement states rather than hides.

## Remaining work

1. Manual NVDA pass on Windows; add a Phase 6.1 section to
   `docs/testing/2026-07-25-cross-radio-migration-accessibility.md` covering
   rename announcement, truncation wording, overview navigation, Go to channel
   focus landing, and Undo/Redo.
2. macOS/VoiceOver stays with the existing Phase 6 Mac tester backlog.

## Explicit non-goals

- Renaming destination banks during migration. The Phase 4 invariant stands.
- Transferring bank names between radios.
- Creating or deleting banks — the driver owns the bank count.
- Editing membership from the overview (Ctrl+B remains the one editing path).
- Editing the vendored `chirp/` tree, including the broken
  `StaticBankModel.get_mapping_memories`.

## Resume checklist

1. `feature/cross-radio-migration`, `uv sync --extra dev`, suite green.
2. Backend first (`bank_ops` + composite undo), with tests, before any wx code.
3. Dialogs second; label before control, Escape, focus return.
4. Re-run all four migration audits plus the extended bank audit.
5. Record the NVDA pass with exact speech; do not infer it from unit tests.
