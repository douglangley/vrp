# Cross-radio migration screen-reader acceptance

This is the repeatable Phase 6 hand-test matrix for the native VRP UI. Automated
tests verify backend state and dialog contracts, but only a person listening to
NVDA or VoiceOver can approve spoken output, focus order, and report navigation.

## Current status

| Environment | Status | Last attempt |
|---|---|---|
| Windows + NVDA | Pass — user confirmed | 2026-07-25 on `a556e71`: the user confirmed the Windows side is working; the NVDA version and exact per-check speech/focus transcript were not supplied |
| macOS + VoiceOver | Pending hand pass | A separate tester will run this later on a Mac |
| Automated migration corpus | Pass | 2,310 migrations: 814 imported, 1,496 expected incompatibilities, zero failures |

Record the screen reader and version, VRP commit, Pass/Fail, exact speech, final
focus, and any issue link for every numbered check. Do not turn “not run” into a
pass based only on unit tests.

The Windows result above is a human acceptance result, not an inference from
automation. Its missing version and per-check transcript are recorded explicitly
rather than invented. The result lines below retain that distinction; macOS is
the remaining Phase 6 platform pass.

## Preparation

1. Check out `feature/cross-radio-migration` and run `uv sync --extra dev`.
2. Copy these pinned fixtures to a disposable folder so an accidental Save
   cannot alter `chirp/`:

   - `Baofeng_UV-5R.img`
   - `Baofeng_UV-5R_Mini.img`
   - `Icom_IC-2200H.img`
   - `Icom_IC-2720H.img`
   - `Icom_IC-2100H.img`
   - `Icom_IC-208H.img`
   - `Yaesu_FT-8800.img`

3. Start the reader, then launch `uv run python main.py`.
4. Keep supplemental speech enabled in Preferences. Test once with it disabled
   afterward to ensure native focus remains sufficient for dialogs and rows.

Known fixture locations: UV-5R channels 0 and 1 are populated and channel 2 is
empty; UV-5R Mini channels 1–21 are populated and channel 22 is empty;
IC-2200H channel 17 is DV and channel 18 is empty; IC-2720H channel 17 is empty.

## A. Cross-image Copy and focus

1. Open the UV-5R copy, focus channel 0, and press `Ctrl+C`.
2. Open the UV-5R Mini copy, focus empty channel 22, and press `Ctrl+V`.
3. Confirm the summary is spoken once, channel 22 becomes selected and focused,
   and arrow navigation reads the converted row without losing the grid.
4. Press `Ctrl+Z`, then `Ctrl+Y`. Confirm each operation is announced and focus
   remains on channel 22 after the grid refresh.

Result: **Windows/NVDA covered by the user-confirmed pass; detailed transcript
not supplied. macOS/VoiceOver pending.**

## B. Cross-image Cut safety

1. Open the UV-5R copy, focus channel 1, and press `Ctrl+X`.
2. Open the Mini copy, focus empty channel 22, and press `Ctrl+V`.
3. Confirm the announcement includes “Source image was unchanged; clipboard is
   now Copy.”
4. Focus channel 23 and paste again. The second paste must work because the
   clipboard became Copy.
5. Reopen the UV-5R copy and confirm channel 1 was never erased.

Result: **Windows/NVDA covered by the user-confirmed pass; detailed transcript
not supplied. macOS/VoiceOver pending.**

## C. Occupied destination choices

Copy UV-5R channel 0, open the Mini copy, and focus occupied channel 1. Repeat
from a clean destination for each choice:

1. **Cancel/Escape:** no write, focus returns to the grid, clipboard remains.
2. **Skip:** destination stays unchanged; the details dialog identifies the
   occupied row.
3. **Overwrite:** destination changes, the imported row is focused, and
   `Ctrl+Z` restores the original row.

NVDA/VoiceOver must announce the dialog title, message, and the distinct
**Overwrite**, **Skip**, and **Cancel** buttons. It must never offer
**Make room** for a cross-radio paste.

Result: **Windows/NVDA covered by the user-confirmed pass; detailed transcript
not supplied. macOS/VoiceOver pending.**

## D. Incompatibility report navigation and copy

1. Open the IC-2200H copy and copy DV channel 17.
2. Open the UV-5R copy, focus empty channel 2, and paste.
3. If asked about banks, choose **Import channels only**.
4. Confirm the **Paste details** dialog opens with focus in the read-only
   **Migration details** text.
5. Arrow through the source, destination, status, and “does not support D-STAR”
   reason. Use `Ctrl+A`, `Ctrl+C`, and paste into a text editor to verify the
   complete report is copyable.
6. Tab to OK, close it, and confirm focus returns to the channel grid. Channel 2
   must remain empty.

Result: **Windows/NVDA covered by the user-confirmed pass; detailed transcript
not supplied. macOS/VoiceOver pending.**

## E. Explicit bank mapping

1. Open IC-2200H, copy channel 2 (source Bank A), then open IC-2720H and focus
   empty channel 17.
2. Paste and navigate the filterable **Map source banks** dialog entirely by
   keyboard. Review the source bank, map it explicitly to destination Bank B,
   and choose **Import with bank mapping**.
3. Confirm channel 17 is focused and its Bank B membership is visible through
   `Ctrl+B`.
4. Undo and Redo; both memory and bank membership must move together.

Result: **Windows/NVDA covered by the user-confirmed pass; detailed transcript
not supplied. macOS/VoiceOver pending.**

## F. Explicit named-special transfer

1. Open the IC-208H destination and choose **File ▸ Import from File** with the
   IC-2100H source.
2. Choose **One memory**, select source special `C`, choose a named-special
   destination, and select `C1`.
3. Confirm a same-name suggestion never bypasses either picker and an occupied
   special presents a separate **Overwrite/Cancel** confirmation.
4. Complete the import, then Undo and Redo. The announcement must say
   “Special memory C1,” not expose its driver virtual number as a grid row.

Result: **Windows/NVDA covered by the user-confirmed pass; detailed transcript
not supplied. macOS/VoiceOver pending.**

## G. Multi-section Cut safety

1. Open FT-8800 and choose the first memory section.
2. Cut a populated channel, switch with **Radio ▸ Select memory section…**, and
   paste into an empty row on the other section.
3. Confirm the source section is unchanged, the clipboard becomes Copy, and
   section switching preserves image modifications while starting section-local
   Undo history.

Result: **Windows/NVDA covered by the user-confirmed pass; detailed transcript
not supplied. macOS/VoiceOver pending.**

## Platform-specific observations

- Windows/NVDA: `Up`/`Down` must read rows; VRP’s `Left`/`Right` cell cursor
  should speak “value, column” without duplicate or clipped speech.
- macOS/VoiceOver: use VoiceOver’s native `VO`+arrow table navigation.
  `NSTableView` must expose rows, cells, headers, selection, modal dialogs, and
  the migration report. Do not require the Windows-only supplemental cell
  cursor.

## Automated evidence

The hand pass complements, rather than repeats:

- `tests/test_clipboard.py`
- `tests/test_migration.py`
- `tests/test_special_import_ui.py`
- `tests/test_bank_import_ui.py`
- `tests/test_dstar_migration.py`
- `tests/test_migration_audit_corpus.py`
- `tools/audit_migrations.py`

The default broad audit covers VHF/Tone, UHF/DTCS, HF/AM, airband AM,
cross-band split, and real D-STAR sources against all pinned targets.
