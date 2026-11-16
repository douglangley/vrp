# Plan — CHIRP Editor Fidelity and Workflow Hardening

> Status: ☐ Not started. This plan covers recommendations **1, 2, 3, 4, 5,
> and 7** from the 2026-08-07 comparison with the web CHIRP project. Regional
> query sources (recommendation 6) are intentionally not part of this plan.

## Goal

Make VRP's native, accessible editor follow the capabilities and validation
rules of each pinned CHIRP driver; prove that fidelity across the pinned image
corpus; add safe operating-system clipboard interchange and an accessible
problem-report workflow; then split `vrp/native/main_window.py` along the
behavioral boundaries established by those tests.

This is six related workstreams, retaining their original recommendation
numbers so progress can be traced back to the source review:

1. Memory-field and `RadioFeatures` parity.
2. Shared validation and upload preflight.
3. Corpus-level editor fidelity audit.
4. Operating-system clipboard interchange.
5. Report-a-problem workflow.
7. Modularize `main_window.py` after behavior is locked down.

## Source-audit baseline

The initial source audit was run 2026-08-07 against pinned CHIRP commit
`c2e70ff`. These counts are a baseline, not constants to hard-code:

- 552 registered driver classes instantiated far enough to inspect their
  `RadioFeatures`, with no feature-discovery failures.
- 453 drivers advertise fixed power levels; 6 advertise variable power.
- 134 drivers have no editable name; 8 have no offset; 49 have no separate
  receive tone; 99 have DTCS without separate receive DTCS; and 77 have DTCS
  without editable DTCS polarity.
- 51 drivers' valid tone lists and 197 drivers' valid DTCS lists differ from
  CHIRP's global defaults. Of the drivers with cross tones, 416 expose a
  driver-specific set of valid cross modes.
- 26 classes advertise D-STAR/DV support.
- All 358 pinned image fixtures load. Of those, 259 contain at least one
  populated driver-specific `Memory.extra`, and 9 contain at least one
  populated `DVMemory`.

The audit exposed specific current gaps in `chirp_backend/col_defs.py`: power,
driver-private extra settings, and direct D-STAR fields are absent; several
choices come from global CHIRP constants instead of the active driver's
features; and receive-tone availability is also being used to hide the
transmit-tone field. Ordinary channel edits parse values but do not run the
driver's `validate_memory()`. Migration already does, so this work should
consolidate the two paths rather than create another validation implementation.

## Invariants and scope boundaries

- Pinned CHIRP is the source of truth for capabilities, conversion, parsing,
  and validation. Do not copy driver tables into VRP and do not modify
  `chirp/`.
- Keep `chirp_backend/` independent of wx. UI-specific clipboard, dialogs,
  focus, and announcements remain under `vrp/`.
- Continue to use the radio's active memory child for channels and the physical
  parent for settings, save, and upload when subdevices are present.
- Preserve VRP's rich in-process clipboard payload, including migration
  context, banks, and D-STAR metadata. System text is an additional interchange
  representation, not a replacement.
- Never deserialize CHIRP's pickled custom clipboard format from an untrusted
  system clipboard. CHIRP-compatible TSV is the safe cross-process contract.
- Validation errors block a write; warnings are visible and require a clear
  user decision where proceeding is safe. No validation result is silently
  discarded.
- All new UI must be keyboard-only operable, expose names/roles/state to screen
  readers, announce results, move focus to the useful next control, restore
  focus on close, and work under high contrast and enlarged fonts.
- Item 7 is deliberately last. Refactoring must not be mixed with behavioral
  changes from items 1–5.

## 1 — Memory-field and `RadioFeatures` parity

### Backend capability schema

Create one framework-independent editor schema derived from the active radio's
`RadioFeatures` and, where needed, the selected memory instance. It should be
the sole source for grid columns, edit-dialog controls, parsing, choices,
editability, and validation field labels.

The schema must:

- Respect `has_name`, `has_offset`, `has_mode`, `has_tuning_step`, `has_bank`,
  `has_ctone`, `has_rx_dtcs`, `has_dtcs_polarity`, `has_cross`, and immutable
  memory fields independently. In particular, lack of `ctone` must not hide
  transmit `rtone`.
- Use the active driver's `valid_modes`, `valid_tmodes`, `valid_duplexes`,
  `valid_tuning_steps`, `valid_skips`, `valid_bands`, `valid_tones`,
  `valid_dtcs_codes`, and `valid_cross_modes`, with a documented fallback only
  when CHIRP provides no driver-specific value.
- Expose fixed power choices from `valid_power_levels` and a bounded numeric
  editor for variable-power drivers. Conversion must preserve CHIRP
  `PowerLevel` semantics rather than treating its display label as identity.
- Discover `Memory.extra` setting groups recursively and describe boolean,
  list, integer, float, and string values with their limits, choices,
  mutability, and labels. Unknown setting types remain preserved and read-only
  rather than being dropped.
- Expose D-STAR call/code fields for `DVMemory` when the driver supports them,
  using the driver's valid call lists and code bounds.
- Represent fields present in an existing memory even when a driver capability
  declaration is incomplete, but keep them read-only and record the mismatch
  for the audit rather than silently losing data.

Keep common, scannable fields in the grid. Add Power there when supported.
Place driver-specific extra settings and D-STAR fields in clearly labelled,
keyboard-reachable sections of the full channel editor so a model with dozens
of private values does not make the grid unusable.

### Write path

- Extend the current parser/update path instead of building a second memory
  editor. `memory_ops` already recognizes power and should remain the common
  conversion boundary.
- Apply edits to a duplicate memory, validate it, and only then commit it to the
  radio. A failed conversion or validation must leave the original untouched.
- Preserve unedited `extra`, DV, immutable, bank, and special-memory metadata.
- Re-read the memory after a successful write and report driver-side
  normalization or rejection instead of displaying stale requested values.
- Include newly editable fields in channel snapshots and Undo/Redo.

### Acceptance

- A driver without a field never offers a misleading editable control for it.
- Every driver-specific choice list is used exactly, including lists that
  differ from CHIRP globals.
- Fixed and variable power round-trip without type or value drift.
- Supported extra settings and DV fields can be read, changed, saved, undone,
  and reopened; unsupported or unknown values survive a no-op edit unchanged.
- Empty, ordinary, and named-special memories retain correct immutable rules.
- Unit tests cover each capability flag and setting type, not only the fixture
  models encountered by the corpus.

## 2 — Shared validation and upload preflight

### Shared validation service

Extract a backend validation result model used by direct edits, bulk
operations, migration, paste, import, and upload preflight. It should:

- Run parsing and range checks first, then call
  `radio.validate_memory(FrozenMemory(candidate))`.
- Use CHIRP's `split_validation_msgs()` to retain warning/error severity and
  preserve the driver's original message.
- Attach a memory number and best-effort field identity without inventing a
  precise field when CHIRP only returns a whole-memory message.
- Convert unexpected validator exceptions into a reported failure with enough
  internal context for logging, not a crash or a silently accepted memory.
- Return structured data; formatting and accessible dialogs belong to the UI.

Replace migration's private validation handling with this service once parity
tests show the same outcomes.

### Direct and bulk edits

- Validate the complete candidate memory before `set_memory()`.
- Block errors and focus the first associated control. Present warnings in a
  navigable dialog and allow an explicit Apply/Cancel decision when the driver
  permits the write.
- For multi-memory operations, keep partial-success semantics and present one
  accessible per-channel report. Undo must cover every successfully written
  memory and leave rejected memories unchanged.

### Upload preflight

Before opening the serial port or entering clone mode:

1. Validate every non-empty ordinary and supported special memory in the
   active radio image.
2. Show a summary grouped by error and warning, with a filterable/navigable
   detail list and Go to channel where possible.
3. Block upload when errors exist. Permit an explicit **Upload despite
   warnings** choice when only warnings exist.
4. Restore focus to Upload, the report, or the selected offending channel as
   appropriate. Announce the counts and decision.

Preflight must not mutate the image and must run before any hardware I/O. A
driver with no meaningful validator should pass without noise. Tests must prove
that a blocked upload never calls `sync_out()` and that warning override calls
it exactly once.

## 3 — Corpus-level editor fidelity audit

Build a reusable audit over the pinned CHIRP images and their static/dynamic
subdevices. It complements targeted unit tests; it is not a substitute for
them.

For every loadable view and representative populated, empty, special, extra,
and DV memory, check:

- The generated schema agrees with `RadioFeatures` and immutable flags.
- Existing values are representable by their controls, even if a driver's
  declaration is incomplete.
- A schema read plus no-op write does not drift frequency, duplex/offset,
  tones, DTCS, polarity, mode, step, skip, name, comment, power, `extra`, or DV
  values.
- Each typed extra setting can be converted to and from its editor value at its
  limits without mutating sibling settings.
- Validation severity is preserved and the upload preflight enumerates the
  same occupied memory set.
- The audit works on duplicated in-memory images only and never touches radio
  hardware or overwrites a source fixture.

Keep a fast deterministic test subset in the normal suite and provide the full
corpus run as an explicit test/audit command. The full report should include
driver/image/subdevice identity, memory identity, field, expected/actual value,
and exception; summarize known capability-declaration mismatches separately
from VRP failures. Re-run and update the baseline after each pinned CHIRP
update.

The item is complete only when all 358 current fixtures are accounted for and
every exception is either fixed or documented as an upstream driver limitation
with a regression case.

## 4 — Operating-system clipboard interchange

Add a system-text layer around the existing Cut/Copy/Paste engine:

- On Copy, retain the rich internal payload and also publish the selected
  memories as CHIRP-compatible TSV using CHIRP's `generic_csv.TSVRadio`
  serialization. This makes the same clipboard useful in CHIRP, spreadsheets,
  and text tools.
- On Paste, prefer the internal payload only while it still corresponds to the
  current system clipboard. Otherwise read Unicode text and parse a full TSV
  (with header) or rows using CHIRP's TSV/default header rules.
- Route parsed external memories through the same generic migration,
  overwrite/skip, validation, bank, D-STAR, partial-success, and Undo/Redo path
  as file import and cross-image Paste.
- Do not consume or produce CHIRP's pickled custom clipboard object. TSV gives
  cross-process compatibility without executing serialized clipboard data.
- Cut must write a usable clipboard before deleting source rows. If the system
  clipboard cannot be opened or populated, leave the source unchanged and
  report the failure.
- Reject malformed or non-memory text without changing the image. Give an
  accessible reason and keep focus on the selection.

Tests should cover VRP→VRP across windows, CHIRP TSV→VRP, VRP TSV→CHIRP's
parser, spreadsheet-style headerless rows, Unicode names/comments, multiple
rows, stale internal clipboard state, malformed data, incompatible target
models, and failed clipboard access. Add a short manual Windows/NVDA and
macOS/VoiceOver interchange matrix.

## 5 — Report-a-problem workflow

Replace the deferred “bug report” placeholder with a user-facing, accessible
Help command. It should collect a reviewable diagnostic draft, never submit or
attach anything automatically.

Include by default:

- VRP version/build, Python, wxPython, operating system/architecture, and the
  pinned CHIRP commit.
- Active radio vendor/model/variant, driver class ID, image-vs-live origin, and
  selected subdevice identity. Do not include channel contents.
- The last operation category and sanitized exception/traceback when one is
  available.
- A bounded, sanitized log tail plus whether serial tracing was enabled. Redact
  filesystem user names, serial-port device paths where practical, credentials,
  query parameters/tokens, frequencies, channel names/comments, call signs,
  and raw radio/image data.
- User-editable steps to reproduce, expected result, actual result, and any
  additional information the user deliberately chooses to add.

The dialog must present the complete report in a labelled, read-only-but-
selectable multiline control. Provide **Copy report**, **Save report…**, and
**Open issue page** actions. Opening the issue page uses the default browser
only after the user has reviewed the report; copying the text remains a
complete offline path. No telemetry, background upload, GitHub authentication,
or image/log attachment is part of this work.

Test deterministic collection, redaction, truncation, missing-log and
no-active-radio states, clipboard/save failures, browser-launch failure, focus
order, Escape/cancel, and focus restoration. The help documentation must say
exactly what is and is not collected.

## 7 — Modularize `main_window.py`

Start only after items 1–5 have their behavior and integration tests. Treat the
current `MainFrame` as a coordination shell and extract one bounded workflow at
a time. Likely boundaries are:

- file/open/save/import/export and recent-file coordination;
- clipboard, migration, Undo/Redo, and selection coordination;
- radio query/frequency-list commands;
- serial download/upload and upload-preflight coordination;
- help, diagnostics, and problem reporting.

Prefer small collaborator/controller objects with explicit dependencies and
callbacks over deep inheritance or a stack of mixins. Keep shared state
ownership obvious: active image/view, physical parent, dirty state, selection,
undo manager, and status announcer must each have one authoritative owner.

For every extraction:

1. Add/confirm characterization tests for menu binding, command enablement,
   focus restoration, announcements, dirty state, and failure handling.
2. Move one workflow without renaming unrelated code or changing UI text.
3. Keep a single real wx `MenuBar`; do not introduce proxy menus or a second
   command-routing system.
4. Run the focused tests and full suite before the next extraction.
5. Record the new ownership boundary in a short module docstring or developer
   note.

Completion means `MainFrame` primarily composes the window, owns document-level
state, and delegates workflows through testable interfaces. Line count alone
is not an acceptance criterion; reduced coupling and unchanged behavior are.

## Recommended sequence

1. Begin item 3 with audit helpers and characterization tests so they can guide
   items 1 and 2.
2. Implement item 1 in slices: capability schema, power, extra settings, then
   DV fields. Expand the audit after each slice.
3. Implement item 2 and reuse it in migration before adding upload preflight.
4. Finish the full item 3 corpus run and document upstream exceptions.
5. Add item 4 using the now-validated import/migration path.
6. Add item 5 using the existing logging/version information and new validation
   reports where relevant.
7. Complete item 7 as behavior-preserving extractions.

Items 1–3 are the first release gate. Items 4 and 5 may follow independently
once the shared backend behavior is stable. Item 7 must remain last.

## Completion checklist

- ☐ Capability-driven editor schema is the only field/choice source.
- ☐ Power, supported `Memory.extra`, and DV fields round-trip accessibly.
- ☐ Direct, bulk, migration, paste/import, and upload paths share validation.
- ☐ Upload preflight blocks errors before hardware I/O and reports warnings.
- ☐ Full pinned-image editor audit has no unexplained VRP failures.
- ☐ System clipboard safely interoperates with CHIRP TSV and spreadsheets.
- ☐ Users can review, copy, save, and optionally open an issue from a sanitized
  problem report.
- ☐ `main_window.py` is split along tested workflow boundaries with no
  accessibility or behavior regression.
- ☐ Unit, integration, full corpus, Windows/NVDA, and macOS/VoiceOver checks are
  recorded in `PROGRESS_LOG.md` as each workstream lands.

## Explicit non-goals

- Regional query providers or other recommendation-6 work.
- A browser/Pyodide/Web Serial/WebUSB front end.
- Editing or forking pinned CHIRP source.
- Replacing VRP's rich internal clipboard with plain text.
- Automatic telemetry, issue submission, or diagnostic attachments.
- Opportunistic visual redesign during the `main_window.py` split.
