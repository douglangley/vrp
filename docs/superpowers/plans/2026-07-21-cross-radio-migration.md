# Plan — Generic cross-radio channel migration

> **Status:** Phases 1–5 implemented and verified through 2026-07-24 on branch
> `feature/cross-radio-migration` (Phase 1 commit `69cf9b1`; Phase 2 commit
> `00af255`; Phase 3 commit `56f6fd5`; Phase 4 commit `8f8d9bd`). The generic migration engine,
> subdevice-aware image UX, explicit single special-memory workflow, and
> explicit bank mapping and transactional D-STAR call-list support are
> complete. The remaining phase covers broader fixture and hands-on testing.

## Goal

Move programmed channels between any two CHIRP-supported radio models when the
destination can represent them, without maintaining a source/target pair matrix
and without requiring a CSV round-trip. Preserve partial success: one
incompatible channel must not prevent the compatible channels from moving.
Named special memories require an explicit one-source/one-target mapping and
are never included in ordinary bulk migration.

The motivating UV-5R ↔ UV-5R Mini case is a regression fixture, not a special
case. Model-specific behavior remains in CHIRP's drivers and import logic.

## What CHIRP does

CHIRP's editor clipboard serializes model-neutral `Memory`/`DVMemory` objects,
the source `RadioFeatures`, and a stable `directory.radio_class_id`. On paste it
runs each populated memory through `chirp.import_logic.import_mem`, validates it
against the target, and writes only compatible results. Driver-private
`Memory.extra` settings are discarded when radio class IDs differ.

`import_mem` already owns the important conversions and checks: frequency/band,
filtered names, power matching, tones and DTCS, automatic mode selection,
duplex/split/off, immutability, target validation, and D-STAR/call-list support.
Therefore VRP must use that generic pipeline, not invent pairwise migrations.

## Decisions implemented in Phase 1

1. **One shared engine.** `chirp_backend/migration.py` is wx-free and is used by
   File Import, query/frequency-list import, and cross-image clipboard Paste.
2. **Stable source identity.** A `MigrationBatch` carries source features, radio
   class ID, label, optional document/section context, populated memory
   snapshots, and read errors.
3. **Populated numeric channels only.** Empty rows are omitted and surviving
   source rows are packed consecutively from the chosen destination. Each
   populated source consumes one destination position even if it is skipped or
   incompatible, preserving relative layout.
4. **Destination number during conversion.** `import_mem` receives
   `overrides={"number": destination, "extd_number": ""}` so immutable-policy
   checks inspect the actual target slot rather than the source channel number.
5. **Private extras stay private.** When source and target radio IDs differ,
   VRP clears `Memory.extra` before conversion. Exact same-driver migrations
   retain extras. Clearing before conversion is deliberate: Mini-specific
   `sqmode` data otherwise survives `import_mem` and fails in UV-5R
   `set_memory`.
6. **Partial result model.** Every source row receives one status: imported,
   occupied, incompatible, failed, or out of space. Warnings and exact CHIRP
   reasons are retained in `MigrationReport`; the UI shows issue reports in a
   navigable, copyable `InfoDialog`.
7. **Overwrite or skip.** File/query import keeps the existing destination
   dialog. Cross-image Paste offers Overwrite / Skip / Cancel for occupied
   target slots. It never shifts foreign raw rows. Same-document Paste retains
   Overwrite / Make room / Cancel.
8. **Safe deferred Cut.** `RadioState.document_id` changes on every open or
   download. Phase 2 refines this with `context_id` (document plus section).
   Cut + Paste erases sources only when that exact context remains active.
   After switching images or sections, a Cut safely becomes Copy and the
   snapshots remain available.
9. **One undo transaction.** All successful writes from a migration batch are
   recorded by `@undo.records` as one operation. Partial success is still one
   undo step.
10. **CSV interoperability.** Import's picker exposes `.img` and `.csv` files.
    Export sizes `CSVRadio` to the real maximum channel, erases its synthetic
    channel zero, and converts to base `chirp_common.Memory` as upstream CHIRP
    does.

## Implemented files

- `chirp_backend/migration.py` — payload, identity, conversion, validation, and
  detailed result/report types.
- `chirp_backend/dstar_ops.py` — D-STAR call-list capability discovery,
  snapshots, exact restoration, and added-call reporting.
- `chirp_backend/memory_ops.py` — undoable `apply_migration_batch`; legacy
  `import_memories` is a compatibility wrapper.
- `chirp_backend/radio.py` — parent/selected-child state, context identity,
  image/source discovery, save/settings/clone ownership, and corrected CSV
  export.
- `vrp/native/main_window.py` — source-aware clipboard, generic cross-image
  Paste, `.img`/`.csv` File Import, explicit special-memory flow, and accessible
  report display.
- `vrp/special_memory_dialogs.py` — accessible import-mode, destination-type,
  and filterable regular/special memory pickers.
- `vrp/bank_mapping_dialog.py` — filterable, explicit source-to-destination
  bank mapping and destination-bank picker.
- `tests/test_migration.py`, `tests/test_clipboard.py`,
  `tests/test_export_csv.py`, `tests/test_memory_ops.py` — real-driver and UI
  regressions.
- `tests/test_special_migration.py`, `tests/test_special_memory_dialogs.py`,
  `tests/test_special_import_ui.py` — special conversion, persistence,
  accessibility, and UI-policy regressions.
- `tests/test_bank_migration.py`, `tests/test_bank_mapping_dialog.py`, and
  `tests/test_bank_import_ui.py` — real-driver bank mapping, rollback,
  undo/persistence, accessible dialog, clipboard, and import-policy coverage.
- `tests/test_dstar_migration.py` — real-driver D-STAR conversion, call-list
  mutation/rollback, partial success, special-memory, and Undo/Redo coverage.
- `tools/audit_migrations.py` — opt-in sweep across every pinned CHIRP image and
  exposed subdevice.
- `tools/audit_special_migrations.py` — opt-in sweep of a representative source
  memory into every named special slot exposed by the pinned fixture corpus.
- `tools/audit_bank_migrations.py` — opt-in mutable-write/verify/exact-rollback
  and fixed-bank rejection sweep across every pinned bank model.
- `tools/audit_dstar_migrations.py` — opt-in DV target sweep plus every actual
  pinned `DVMemory` against every call-list-owning destination.

## Decisions implemented in Phase 2

1. **Parent owns the image; child owns the grid.** `RadioState.physical_radio`
   retains CHIRP's parent for Save/Save As, Settings, clone prompts, and Upload.
   `RadioState.radio` is the selected child used by memory, bank, export, and
   migration operations.
2. **Parse before choosing.** `load_image_set` parses the parent and calls
   `get_sub_devices` once, so drivers with `has_dynamic_subdevices` can build
   zones from their loaded image. `activate_image_set` is separate, which means
   canceling the chooser leaves the currently open document untouched.
3. **Single-child parents still use their child.** A parent reporting
   `has_sub_devices` is never used as the memory grid merely because it returns
   one child; the chooser is skipped and that child is selected automatically.
4. **External metadata is linked.** Parents implementing
   `ExternalMemoryProperties` run `link_device_metadata(children)` exactly as
   CHIRP's editor does, so per-memory metadata is included in a later parent
   save.
5. **Accessible section chooser.** `SubdeviceDialog` uses the existing native
   `RadioListView` (SysListView32 on Windows, NSTableView/GtkTreeView elsewhere),
   adjacent labels, filtering, a count, explicit action/Cancel buttons, and
   Escape. It is used by Open, Import, and post-Download; Radio ▸ Select memory
   section… permits later switching.
6. **Stable human labels.** Choices use CHIRP `VARIANT` plus channel bounds, not
   generated Python class names. This matters for dynamic Kenwood fixtures whose
   generated class names exceed 20,000 characters.
7. **Section-safe clipboard identity.** `RadioState.context_id` combines the
   document UUID and selected section. Paste uses raw move/make-room semantics
   only in that exact context. After switching sections, Paste uses generic
   migration and a deferred Cut becomes Copy, so same-numbered rows in another
   side/zone cannot be erased.
8. **Section-local undo.** Switching sections restores the previous child's
   original write methods before installing a fresh recorder on the next child.
   Image changes and the dirty flag remain, while undo history resets rather
   than accidentally wrapping an old recorder recursively.

Phase 2 adds `vrp/subdevice_dialog.py`, `tests/test_subdevices.py`, and
`tests/test_subdevice_dialog.py`, plus interaction coverage in the grid and
clipboard test modules.

## Decisions implemented in Phase 3

1. **Bulk remains numeric-only.** Existing File Import, query/frequency-list
   import, and cross-image Paste still enumerate only populated ordinary channel
   numbers. They never pull named specials into a bulk operation.
2. **One explicit source and destination.** File Import offers ordinary bulk or
   one memory when either side exposes specials. The single-memory path accepts
   a populated regular or special source, then requires a numbered or named
   special destination.
3. **Same name is a preselection, not an automatic mapping.** When both radios
   expose a special with the same name, VRP selects it in the target picker for
   convenience. The user must still accept it. This avoids pretending that
   `CALL`, `HOME`, scan limits, VFO state, and band-specific variants share one
   universal meaning.
4. **Occupied specials require explicit overwrite.** The target picker does not
   write. An occupied named target gets a second confirmation whose safe default
   is not to overwrite.
5. **CHIRP owns field conversion.** Special→regular, regular→special, and
   special→special all use `import_logic.import_mem`. For named targets VRP
   preserves the destination slot's virtual number, `extd_number`, and genuine
   immutable values while clearing cross-driver private extras.
6. **Driver defects are reportable incompatibilities.** Invalid immutable field
   declarations, drivers that cannot reread a special by virtual number, and
   plain out-of-band setter exceptions are classified as incompatibilities.
   Unknown exceptions remain failures, so the audit still catches regressions.
7. **Special writes are undoable and persistent.** The undo recorder keys named
   specials by `extd_number`; restoring an empty special uses `set_memory`
   rather than numeric erase. Save/reopen uses the physical parent image exactly
   like an ordinary edit.
8. **Accessible native selection.** `MemoryPickerDialog` uses `RadioListView`
   with an adjacent label, filter, count, explicit action/Cancel buttons, and
   Escape. The import-mode and destination-type choices are explicit native
   radio controls.

## Decisions implemented in Phase 4

1. **Bank transfer is explicit.** Only banks used by the selected source
   channels appear. Unique, non-empty exact-name matches are suggestions; the
   user confirms them in the mapping dialog. Position mapping is available
   only through an explicit **Match by position** action. VRP never silently
   uses CHIRP's index/position policy.
2. **Unmapped means omitted.** A source bank left as **Do not import** creates
   no target membership. Destination bank names are never renamed.
3. **Replacement semantics are stated before import.** When bank transfer is
   enabled, every successfully imported channel receives exactly its mapped
   memberships, replacing existing target memberships. If all selected source
   channels are unbanked, the user explicitly chooses whether to clear or keep
   destination memberships.
4. **Unsupported targets require consent.** A destination with no banks, fixed
   banks, or unreadable bank metadata gets an explicit **Import channels only**
   confirmation. Cancel performs no writes.
5. **Per-channel atomicity.** A driver rejection or verification mismatch
   rolls that channel's bank state back to its exact prior memberships and
   indexed ordering. The compatible memory remains imported and the report
   contains a bank warning; bank failures never silently drop memberships.
6. **One undo/redo transaction.** `UndoManager` can snapshot auxiliary state.
   Migration memory writes and mapped bank memberships share one transaction;
   Undo/Redo restores both, including indexed ordering. The existing
   **Channel banks** editor is now undoable through the same mechanism.
7. **Clipboard metadata is durable.** Copy/Cut captures its `MigrationBatch`
   while the source section is active, so cross-image or cross-section Paste
   retains source memberships after the source radio is no longer active.
8. **Driver behavior is authoritative.** VRP discovers actual `BankModel`
   instances and verifies live memberships. It does not assume class names
   accurately describe multi-membership capacity; real drivers that permit
   multiple banks through a plain `BankModel` remain supported.

## Decisions implemented in Phase 5

1. **CHIRP remains the conversion authority.** `import_logic.import_mem`
   continues to convert `DVMemory` fields and reject a DV channel when the
   destination cannot represent it. VRP never coerces rejected DV data into an
   analog channel.
2. **Call lists are transaction state.** On destinations whose
   `IcomDstarSupport` features declare `requires_call_lists`, VRP snapshots
   `urcalls` and `rptcalls` before each DV attempt. Calls added by CHIRP are
   retained only when that channel writes successfully.
3. **Rejected rows leave no side effects.** Conversion, validation, and driver
   write failures restore both call lists exactly, including duplicates and
   order. A failed channel does not remove additions made by an earlier
   successful row in the same partial batch.
4. **Partially written memories are repaired.** Some real drivers mutate their
   raw destination before raising. VRP snapshots the destination and restores
   it after any failed write attempt, so a reportable rejection cannot leave a
   damaged channel behind.
5. **Undo/Redo includes radio-global state.** `UndoManager` has an opt-in global
   snapshot in addition to per-memory and auxiliary bank snapshots. D-STAR
   imports record required call lists once per transaction; Undo/Redo restores
   lists before memories because list-indexed setters need the matching entries.
6. **Successful additions are visible, not separately confirmed.** The normal
   migration confirmation remains sufficient. `MigrationReport` summarizes and
   itemizes newly added call signs without adding another modal dialog.
7. **Direct-call drivers stay untouched.** Radios with
   `requires_call_lists=False` carry calls directly in `DVMemory`; VRP does not
   mutate their master call lists.
8. **Snapshot failure is fail-closed.** If required call-list state cannot be
   captured for the active batch, no destination memory is written.

The motivating real failure is Icom ID-4100 channel 0 into an IC-2200H
destination. CHIRP added padded `CQCQCQ` call-list data and the IC-2200H setter
partially changed its raw memory before rejecting the call. The Phase 5 rollback
restores both pieces exactly.

## Verification baseline after Phase 5 (2026-07-24)

- Full VRP suite: **475 passed**.
- Subdevice backend coverage: all **23 pinned parent fixtures** expand to their
  expected **50 child views**; both static FT-8800 and dynamic TK-3180K2 edits
  survive parent Save/reopen.
- GUI coverage verifies chooser filtering/accessibility, selected-section Open,
  cancel-without-replacement, menu/title state, and cross-section Cut safety.
- Focused migration/clipboard/export/memory tests: **71 passed**.
- Real UV-5R Mini → UV-5R: all 21 populated fixture channels imported after
  foreign extras were removed.
- Real UV-5R → UV-5R Mini: 36 compatible channels imported and the one invalid
  transmit-frequency channel was retained in the detailed report.
- Pinned CHIRP audit: **385 targets from 358 image files**; 276 accepted the
  representative Generic CSV channel, 109 rejected it with normal model/band
  compatibility reasons, and **0 unexpected failures**.
- Special-memory audit: **1,989 named slots across 70 radio targets from 358
  image files**; 1,007 imported, 982 returned expected incompatibilities, and
  **0 unexpected failures**.
- Bank audit: **70 bank models across 63 image files from 358 pinned images**;
  all **54 mutable models** passed write/verify/exact-rollback, all **16 fixed
  models** rejected reassignment, and there were **0 unexpected failures**.
- D-STAR inventory: **15 DV-capable targets** and **240 populated actual
  `DVMemory` records** in the pinned corpus. Four targets require master call
  lists: IC-2200H, IC-U82, IC-V82, and ID-800H.
- D-STAR representative target sweep: **385 targets**; 13 imported and 372
  returned expected incompatibilities, with **0 unexpected failures**.
- D-STAR call-list corpus: **960 cases** (240 actual DV memories × four
  required-list targets); 482 imported and 478 returned expected
  incompatibilities. Every rejected destination memory and both call lists
  restored exactly, with **0 unexpected failures**.

Run all audits from the repository root:

```powershell
.\.venv\Scripts\python.exe tools\audit_migrations.py
.\.venv\Scripts\python.exe tools\audit_special_migrations.py
.\.venv\Scripts\python.exe tools\audit_bank_migrations.py
.\.venv\Scripts\python.exe tools\audit_dstar_migrations.py
```

## Remaining work

### Phase 2 — Subdevice-aware image UX — complete

Implemented as described above. Hardware downloads of a multi-section radio and
NVDA/VoiceOver hand passes remain part of Phase 6 acceptance, not backend gaps.

### Phase 3 — Special memories — complete

Implemented as described above. Special memories remain outside the ordinary
grid and bulk clipboard path; File Import is the deliberate one-memory entry
point. Physical-radio and screen-reader hand passes remain Phase 6 acceptance.

### Phase 4 — Banks and mapping metadata — complete

Implemented as described above. Bank names remain destination-owned; this
phase maps membership only. NVDA/VoiceOver hand passes remain Phase 6
acceptance.

### Phase 5 — D-STAR and validation side effects — complete

Implemented as described above. Required call lists and partially mutated
destination memories now roll back per channel and participate in the same
transaction-wide Undo/Redo state as the imported memories. Successful additions
are included in the migration report.

### Phase 6 — Acceptance and stronger compatibility audit

- NVDA hand pass: cross-image Copy/Paste, cross-image Cut safety,
  Overwrite/Skip/Cancel, issue report navigation/copy, and Undo.
- VoiceOver pass on the same flow.
- Expand the audit source corpus beyond one 443.1 MHz Generic CSV channel to
  representative VHF, UHF, HF/AM, split, tone/DTCS, and DV memories. Expected
  incompatibilities remain valid; only unclassified failures fail the audit.
- Consider a non-mutating preview once reports are useful before the user
  confirms a large import.

## Explicit non-goals

- Pairwise converters such as UV-5R-to-Mini classes.
- Migrating radio-wide settings or clone-image bytes between models.
- Editing the vendored `chirp/` tree.
- Claiming that every channel is representable on every radio. “All models”
  means every driver uses the same tested conversion route; the destination's
  bands and features still decide compatibility per channel.

## Resume checklist

1. Check out `feature/cross-radio-migration` and confirm it tracks
   `origin/feature/cross-radio-migration`.
2. Run `uv sync --extra dev`, then `uv run python -m pytest`.
3. Run `tools/audit_migrations.py`, `tools/audit_special_migrations.py`,
   `tools/audit_bank_migrations.py`, and `tools/audit_dstar_migrations.py` after
   any CHIRP pin or migration change.
4. Start Phase 6 by expanding the ordinary audit source corpus, then run the
   NVDA/VoiceOver acceptance matrix.
5. Keep `chirp/` unmodified and add a real pinned fixture for every new edge
   case.
