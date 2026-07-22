# Plan — Generic cross-radio channel migration

> **Status:** Phases 1 and 2 implemented and verified 2026-07-21 on branch
> `feature/cross-radio-migration` (Phase 1 commit `69cf9b1`; Phase 2 commit
> `00af255`). The generic migration engine and subdevice-aware image UX are
> complete. The remaining phases cover special memories, banks, D-STAR side
> effects, and broader hands-on testing.

## Goal

Move ordinary programmed channels between any two CHIRP-supported radio models
when the destination can represent them, without maintaining a source/target
pair matrix and without requiring a CSV round-trip. Preserve partial success:
one incompatible channel must not prevent the compatible channels from moving.

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
- `chirp_backend/memory_ops.py` — undoable `apply_migration_batch`; legacy
  `import_memories` is a compatibility wrapper.
- `chirp_backend/radio.py` — parent/selected-child state, context identity,
  image/source discovery, save/settings/clone ownership, and corrected CSV
  export.
- `vrp/native/main_window.py` — source-aware clipboard, generic cross-image
  Paste, `.img`/`.csv` File Import, and accessible report display.
- `tests/test_migration.py`, `tests/test_clipboard.py`,
  `tests/test_export_csv.py`, `tests/test_memory_ops.py` — real-driver and UI
  regressions.
- `tools/audit_migrations.py` — opt-in sweep across every pinned CHIRP image and
  exposed subdevice.

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

## Verification baseline after Phase 2 (2026-07-21)

- Full VRP suite: **420 passed**.
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

Run the audit from the repository root:

```powershell
.\.venv\Scripts\python.exe tools\audit_migrations.py
```

## Remaining work

### Phase 2 — Subdevice-aware image UX — complete

Implemented as described above. Hardware downloads of a multi-section radio and
NVDA/VoiceOver hand passes remain part of Phase 6 acceptance, not backend gaps.

### Phase 3 — Special memories

- Decide how named special channels map to ordinary numeric destinations and to
  another model's special names. CHIRP can convert special↔regular by managing
  `number` and `extd_number`, but the user needs an explicit, predictable UX.
- Never silently include call channels, scan limits, or weather memories in an
  ordinary bulk migration.

### Phase 4 — Banks and mapping metadata

- Choose whether bank membership maps by index, bank name, or explicit user
  mapping. CHIRP's `import_bank` is index-based and silently ignores missing
  destination banks; that is too implicit for VRP's detailed-report standard.
- Keep bank changes in the same undo story, or clearly report that they are not
  undoable before enabling them.

### Phase 5 — D-STAR and validation side effects

- Test migrations between real D-STAR fixtures, especially destinations with
  `requires_call_lists`. `import_mem` may add calls before the final memory
  write, so determine whether call-list changes need their own transaction or a
  preflight step.
- Preserve the current rule that a destination without DV support reports an
  incompatibility rather than coercing the channel to analog.

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
3. Run `tools/audit_migrations.py` after any CHIRP pin or migration change.
4. Start with Phase 3 (special memories) unless product priority moves explicit
   bank mapping or Phase 6 hands-on acceptance ahead of it.
5. Keep `chirp/` unmodified and add a real pinned fixture for every new edge
   case.
