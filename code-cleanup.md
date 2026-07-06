# Code Cleanup & Debug Plan

> **Working document.** A phased, work-in-pieces plan from a full source review on
> 2026-07-05 (all of `vrp/`, `chirp_backend/`, `main.py`, `build.py`, entry
> points, tests, and the build/dependency surface). Each item is independently
> committable with its own verification step. Check items off as they land and
> note the commit; add findings as they turn up.
>
> Baseline at time of writing: **198 tests passing** (`uv run python -m pytest`),
> commit `d3544e7` on `main`.

## Ground rules (from CLAUDE.md — apply to every phase)

- Never edit `./chirp/` — it stays vendored and unmodified, pinned by `CHIRP_COMMIT`.
- Never import `chirp.wxui` from VRP code.
- Every user-visible change must keep its screen-reader path: announce via
  `Announcer`, manage focus after operations, and **hardware-verify under NVDA
  before claiming an audible behavior works** (the verify-before-commit rule).
- Run `uv run python -m pytest` after every step; add a test with every fix.

---

## Phase 0 — Baseline & guardrails (do first, ~30 min) — DONE 2026-07-05

- [x] **0.1 Record the baseline.** 198 tests passing on `main` @ `d3544e7`.
- [x] **0.2 Add a `chirp.wxui` import guard test.**
  `tests/test_no_wxui_import.py` — AST-based (so the legitimate docstring/comment
  references to `chirp.wxui` in `serial_trace.py`/`radio.py`/`bandplan.py` don't
  trip it); scans `vrp/` + `chirp_backend/`.
- [x] **0.3 Clean the repo root.** Gitignored the artifacts **in place** rather
  than moving them (safer for the active KG-UV96M RE workflow than relocating
  files tooling may reference): `*.pcap`, `*.pid`, `RadioSettings.png`, `csv.txt`.
  They stay on disk; they just no longer clutter `git status`. Reorganize into a
  `captures/` folder later if desired.

---

## Phase 1 — Correctness bugs (highest priority)

### 1.1 `is_modified` is never set by channel edits — BUG — FIXED 2026-07-05

**DONE.** Marked dirty in the `_install_undo` recorder wrappers
(`recording_set`/`recording_erase` and the undo/redo `restore_*`), the single
choke point every write passes through. Test: `tests/test_is_modified.py`
(fresh-load clean → edit dirties → save clears → undo re-dirties; plus delete
dirties). 202 tests pass.

<details><summary>Original finding</summary>

**What:** `RadioState.is_modified` is only set by `import_memories`,
`bank_ops.apply_bank_changes`, `apply_radio_settings`, and
`download_from_radio`. Every ordinary channel operation (edit, delete, move,
sort, paste, undo/redo — all of `memory_ops`) writes through
`memory_ops._set_mem`/`_erase_mem` → the radio instance methods directly
(`chirp_backend/memory_ops.py:47-52`) and **never marks the image modified**.
The module-level `radio.set_memory`/`erase_memory` functions that do set the
flag (`chirp_backend/radio.py:180-214`) are called **only by tests**.

**Why it matters:** Radio Info reports "Unsaved changes: No" after you've edited
channels, and any future unsaved-changes prompt (1.2) would be built on a flag
that lies.

**Fix (one choke point):** `_install_undo` (`chirp_backend/radio.py:241`)
already wraps the loaded radio's `set_memory`/`erase_memory` — every channel
write funnels through it. Set `_state.is_modified = True` in `recording_set`/
`recording_erase`, and also in `restore_set`/`restore_erase` (an undo *is* a
change relative to the file on disk). Then decide the fate of the now-redundant
module-level `radio.set_memory`/`erase_memory` (see 5.1).

**Verify:** unit test — load image → `set_channel_field` → `is_modified` is
True; save → False; undo → True again.

</details>

### 1.2 No unsaved-changes prompt anywhere — data-loss BUG

**What:** `MainWindow` has no `EVT_CLOSE` handler; `on_exit` just calls
`Close()`. `on_close_image`, `_open_path` (File ▸ Open over a modified image),
and `on_download` (download replaces the loaded image) never check
`is_modified`. Exiting or loading over unsaved work silently discards it.

**Fix (depends on 1.1):**
- Add an `EVT_CLOSE` handler on `MainWindow`: if `is_modified`, show a native
  Yes/No/Cancel `wx.MessageDialog` ("Save changes to <name> before closing?"),
  with `SetYesNoCancelLabels("Save", "Don't save", "Cancel")`. Save routes
  through `on_save` (which falls back to Save As for never-saved downloads).
  Veto on Cancel or failed save.
- Factor a `_confirm_discard_or_save() -> bool` helper and call it from
  `on_close_image`, `_open_path`, `_open_recent`, and `on_download` before the
  destructive step.
- Accessibility: the dialog is a native message dialog (focus-trapped, Escape =
  Cancel); after a veto return focus to the grid.

**Verify:** headless test for the helper's decision logic; manual NVDA pass on
the dialog (title + buttons read, Escape cancels).

### 1.3 `get_memory()` can return `None` → crash paths in clipboard/paste — FIXED 2026-07-05

**DONE.** `_snapshot_selection` now skips unreadable channels (and announces if
none remain); `on_paste`'s occupancy check treats a None slot as empty
(consistent with `_destination_occupied`/`_first_empty_channel`). Tests:
`test_clipboard.py::test_copy_skips_unreadable_channel`,
`test_copy_all_unreadable_returns_none`,
`test_paste_over_unreadable_destination_no_crash`. 205 tests pass.

<details><summary>Original finding</summary>

**What:** `radio_backend.get_memory` returns `None` on a read failure
(`chirp_backend/radio.py:163-177`), but:
- `MainWindow._snapshot_selection` does `radio_backend.get_memory(n).dupe()`
  (`vrp/native/main_window.py:704`) → `AttributeError` on None.
- `on_paste` does `not radio_backend.get_memory(k).empty`
  (`vrp/native/main_window.py:759`) → same.

**Fix:** treat `None` as "unreadable" — skip with a friendly announce (copy) or
treat as empty (paste occupancy check). Keep it small.

**Verify:** unit test with a stub radio whose `get_memory` raises for one
channel.

</details>

### 1.4 `delete_and_shift` with a non-contiguous selection — FIXED 2026-07-05

**DONE (option a — restrict to contiguous).** `delete_and_shift` now dedupes/
sorts its input and, if it isn't a solid `low..high` run, returns
`(False, "Delete and shift needs a contiguous range …", [])` before touching
the radio — `on_organize` announces that assertively. A contiguous spec given
unsorted/with duplicates still works. Tests:
`test_noncontiguous_selection_rejected`, `test_contiguous_out_of_order_still_shifts`.
Commit 022f5b9. 223 tests pass.

<details><summary>Original finding</summary>

**What:** `delete_and_shift` (`chirp_backend/memory_ops.py:502`) computes
`delta = len(numbers)` and shifts everything after `numbers_sorted[-1]` up by
`delta`. For a **non-contiguous** spec (the Bulk-operations "Advanced channel
list" accepts `1-5,8,10-12`), channels *between* the deleted ones are not
shifted and the result leaves the wrong gaps.

**Fix options (pick after reading CHIRP's `_delete_memories_at` closely):**
(a) restrict delete-and-shift to a contiguous selection in `ops_dialog` (clear
error message), or (b) implement true multi-gap compaction. Option (a) is
simpler and honest; CHIRP's own UI operates on grid selections and has the same
ambiguity.

**Verify:** unit test for the chosen behavior (non-contiguous input → clean
error, or correct compaction).

</details>

### 1.5 Settings dialog writes back *unchanged* values on OK — FIXED 2026-07-05

**DONE.** `RadioSettingsDialog` records each control's build-time value
(`self._initial`) and `_on_ok` skips any control whose read-back is unchanged,
so `set_value` runs only for genuine edits. Test:
`tests/test_settings_dialog.py` (no-edit OK → `changed()` False, count 0; a real
edit still writes and counts). 215 tests pass.

<details><summary>Original finding</summary>

**What:** `RadioSettingsDialog._on_ok` calls `value.set_value(...)` for every
enabled control (`vrp/settings_dialog.py:147-162`), not just changed ones — and
the string display was built with `.rstrip()` (`:118`), so a driver value with
significant trailing padding would be written back altered and may flag
`value.changed()` spuriously (miscounting "N setting(s) changed", possibly
perturbing driver state).

**Fix:** only `set_value` when the control's read-back differs from the current
`value.get_value()` (string-compare in the same form shown). Keep the rstrip
for display only.

**Verify:** unit test with a stub RadioSettingValueString carrying trailing
spaces: OK with no edits → `changed()` False everywhere, count 0.

</details>

### 1.6 Minor robustness — PARTIAL 2026-07-05

- [x] `delete_memory`/`delete_range` `"empty" in mem.immutable` → `(mem.immutable
  or [])` so a driver reporting `immutable=None` doesn't `TypeError`. Tests:
  `test_delete_immutable_none_does_not_crash`,
  `test_delete_range_immutable_none_does_not_crash`.
- [ ] `vrp/native/app.py` duplicate `logging.basicConfig` — **left as-is** on
  review: it's idempotent (main.py configures the root logger first, so this is
  a no-op there) and `vrp.native.app.run()` is a documented standalone entry
  point that benefits from the fallback config if called without `main()`.
  Not worth the churn/risk. Reopen only if it actually causes a problem.
- [ ] macOS `test_channel_grid` xfail — **deferred**: can't reproduce or verify
  on Windows. Do it during a macOS pass so the xfail condition is real.

### 1.9 Frequency display truncated trailing zeros ("146") — FIXED 2026-07-05 (user-reported)

**What:** `FrequencyColumn.format_value` did `f"{mhz:.6f}".rstrip("0").rstrip(".")`,
so a whole-MHz channel (146_000_000 Hz) displayed as **"146"** — hiding that it's
a real frequency and dropping the meaningful trailing digits.

**Fix:** New `col_defs.format_freq_mhz(freq_hz)` formats from the **integer Hz**
(no float rounding) with **at least 3 decimals** ("146" → "146.000") while never
truncating finer data (146.0125, 145.9875, 146.00625 kept). Used by
`FrequencyColumn`, and — for consistency so search/announcements match what's
shown — by `memory_ops.find`'s freq normalization and
`MainWindow._describe_match`. Offset formatting left unchanged (not reported).

**Verified:** `tests/test_freq_format.py` (whole-MHz → 3 decimals, kHz kept,
finer-than-kHz not truncated, no float error, empty/zero blank) + a real-image
runtime drive through the grid path: whole-MHz cell reads "146.000", 12.5 kHz
reads "146.0125". 213 tests pass.

### 1.8 Load-failure error not read by the screen reader — FIXED 2026-07-05 (user-reported)

**What:** Opening an unsupported/corrupt file showed nothing readable — the error
("Failed to load image: Unsupported model …") only went to the status bar +
prism via `announce`, with **no modal**. After the file dialog closes, focus is
ambiguous and the status-bar/prism cue races the screen reader's own focus
chatter, so NVDA dropped it. Every other error path in the app uses a modal.

**Fix:** New `MainWindow._show_error(title, message)` shows the error in a modal,
read-only, **copyable edit box with an OK button** (`InfoDialog(ok_button=True)`,
a new option), then returns focus to the grid — so the reader is guaranteed to
read it (focus lands in the dialog text) and a long driver error can be arrowed
through / copied. Wired into `_open_path` (covers File ▸ Open and Open Recent).
Status bar still gets the text as a visual record.

**Verified:** headless tests (`test_info_dialog.py::test_info_dialog_ok_button_variant`,
`test_channel_grid.py::test_open_failure_shows_modal_error`) + a runtime drive of
the real path (unsupported file → modal built with the right title/text/OK
button, status bar set). 207 tests pass. **Owed: your NVDA confirmation** that
the dialog reads on open (it uses InfoDialog's existing, NVDA-verified focus
path).

**Note:** `_open_recent`'s separate "File not found — removed from recent"
pre-check is still announce-only. Same class of issue but a different, lower-
severity flow (it auto-removes the entry and refocuses the grid); left as-is
unless you want it modal too.

### 1.7 Housekeeping with a correctness edge: the grid-library pin

`pyproject.toml` pins `wx-accessible-grid` to the **payown fork**
(`rev 494103f...`, PR Community-Access/wx-accessible-grid#4). Check whether the
PR merged; if so, repoint to the Community-Access rev and re-run the suite +
an NVDA smoke of the grid. (Already tracked in PROGRESS_LOG "Open / next".)

---

## Phase 2 — Dead code removal — MOSTLY DONE 2026-07-05

All confirmed by grep to have **zero callers** in `vrp/`, `chirp_backend/`,
`main.py`, `build.py` (some had test-only callers, removed with them).

- [x] **2.1 `radio.describe_radio_html`** — webview-era HTML builder, removed.
- [x] **2.2 `memory_ops.set_field`** — superseded by `set_channel_field` /
  `update_channel`, removed.
- [x] **2.3 `memory_ops.goto`** + its two tests — `on_goto` does its own
  bounds/select/focus; removed.
- [x] **2.4 `bank_ops.has_bank`** — removed (`on_banks` uses `get_bank_state`).
- [x] **2.5 `col_defs.memory_to_dict` + `ColumnDef.to_dict`** — Flask/webview-era
  JSON serialization, removed.
- [x] **2.6 `RadioState.serial_port`** — removed the write-only field and its
  two assignments (unload/download). If "Downloaded via COMx" is ever wanted in
  Radio Info, add it back as a *read* path deliberately.
- [ ] **2.7 `tools/` spikes** — **DEFERRED (user's call).** They're referenced
  by `docs/research/2026-06-24-native-grid-voiceover-feasibility.md` and relate
  to ongoing macOS VoiceOver work, so not deleting exploratory tooling
  unilaterally. Delete or move to `tools/spikes/` when you decide.
- [ ] **2.8 Module-level `radio.set_memory`/`erase_memory`** — deferred to
  Phase 5.1 (single write path) rather than deleting blind (tests use them).

**Verified:** 205 tests pass; `import chirp_backend.*` clean; grep shows no
dangling references to any removed symbol.

---

## Phase 3 — CHIRP usage & bundle audit ("only what we need") — DONE 2026-07-05 (3.5 owed)

The CHIRP clone itself must stay (it is the driver library, pinned and bundled
by design). The audit was about what VRP *pulls in around it*.

- [x] **3.1 Dropped `--collect-submodules=chirp.sources` from `build.py`.**
  Nothing in VRP imports `chirp.sources` since the query-source removal, so the
  directive only bundled dead modules (and dragged in `requests`). A future
  RepeaterBook will be a *static* import PyInstaller follows on its own. Stale
  comment citing `chirp_backend/query.py` fixed too.
- [x] **3.2 `requests` kept, annotated.** CHIRP's own `setup.py` declares
  `requests`, so the editable `./chirp` install pulls it in transitively (VRP's
  pin is redundant but harmless) — but it is **only reachable via
  `chirp.sources`**, which is no longer collected, so it is **no longer in the
  frozen app**. Kept in `pyproject.toml` (with a clarifying comment) so the
  source env matches CHIRP and RepeaterBook works when it returns.
- [x] **3.3 `lark` + `pyserial` confirmed bundled** (10 lark entries incl.
  grammar data in COLLECT; 31 serial modules in the PYZ).
- [x] **3.4 Rebuilt and verified.** `uv run python build.py` succeeds. Bundle
  TOC (`build/vrp/*.toc`): **191 `chirp.drivers` modules** (unchanged, ~552
  models), **0 `chirp.sources`**, **0 `requests`** anywhere (PYZ/COLLECT/
  Analysis). `dist/vrp` is **50 MB** (removing `requests` also drops
  urllib3/certifi/idna/charset-normalizer). Dev venv restored; 205 tests pass.
- [ ] **3.5 Prism-less binary NVDA check** — **OWED TO USER** (needs the built
  exe + NVDA): the release exe excludes `prism`, so confirm the channel grid
  still reads under NVDA in the frozen binary (announcements degrade to
  status-bar-only by design; the grid itself must still read). The exe is built
  at `dist/vrp/vrp.exe` right now if you want to test it.

---

## Phase 4 — Performance (measured; act only where it shows)

**Baseline measured 2026-07-05** (this machine, warm cache):
`directory.import_drivers()` = **0.20s** (552 drivers) · `load_image` (1024-ch
Radtel RT-880G, the largest test image) = **0.31s** · `grid_model.build_rows`
for 1024 channels = **0.07s** · full `number_to_index` sweep ×1024 = **0.018s**.

**Conclusion: the backend has no serious bottleneck.** Don't rewrite it. The
plausible hotspots are UI-side and in a few uncached scan loops:

- [ ] **4.1 Measure the real UI populate.** Time `ChannelGrid.set_state` on the
  1024-channel image in the running app (row-by-row `AppendItem` into
  `DataViewListCtrl` is the suspect, and it's the *library's* loop). If it
  stalls (>~300ms), check whether wx-accessible-grid Freezes around populate;
  if not, file/patch upstream (same channel as the cell-cursor work). Measure
  before touching anything.
- [x] **4.2 `on_delete_channels` rebuilds the whole grid needlessly** — DONE
  2026-07-05 (commit 9cd8ffa). Plain Delete now calls
  `self.grid.refresh_numbers(numbers)` (in-place repaint); `rebuild()` kept for
  the structural ops in `on_organize`. Test asserts the non-rebuild path + focus
  on the cleared slot. **Owed:** NVDA confirmation that focus reads steadily.
- [x] **4.3 `paste_block` make-room scan reads every channel uncached** — DONE
  2026-07-05 (commit 0a3fcc9). Now scans `[destination, last_bound]` from the
  tail down and breaks at the first occupied slot (only the highest matters).
  Tests: two make-room-across-a-gap cases. `find` (`:970-987`) left as-is (fine
  unless profiling says otherwise).
- [ ] **4.4 `number_to_index` is a linear scan** (`vrp/native/grid_model.py:111`)
  called per-number by `select_channels` → O(N·M) on a big paste/undo
  selection. Rows are built contiguous `low..high`, so `number - low` with a
  bounds check (fallback to the scan if the row-number doesn't match) is exact
  and O(1). Only worth it if 4.1's measurements show selection restore lagging;
  18ms for a full sweep says it's marginal.
- [ ] **4.5 Startup:** 0.2s driver import + instant onedir launch — leave it
  alone. (Recorded so nobody "optimizes" it later without numbers.)

**Verify each:** suite + a stopwatch run on the 1024-channel image, and an NVDA
pass on 4.2 (focus must stay on the deleted row's slot).

---

## Phase 5 — Consolidation & consistency

- [ ] **5.1 One write path for memories.** Today there are two:
  `memory_ops._set_mem/_erase_mem` (used by the app; no cache update, no
  `is_modified`) and `radio.set_memory/erase_memory` module functions (cache +
  `is_modified`; used only by tests). After 1.1 puts `is_modified` in the
  recorder wrapper, either (a) delete the module-level pair and let
  `invalidate_cache` remain the contract, or (b) route `memory_ops` through
  them. (a) is less churn; pick one and document it in `radio.py`'s docstring.
- [x] **5.2 Share one `Speaker`** — DONE 2026-07-05 (commit a7f4b63).
  `vrp.speech.get_speaker()` module singleton; `main_window`, `edit_dialog`, and
  `serial_dialogs` all use it. Test: `tests/test_speaker_singleton.py`.
- [x] **5.3 Extract the "Now on channel N / Now at channels A to B" phrasing** —
  DONE 2026-07-05 (commit 16282ec). One `MainWindow._now_at_phrase(block)`
  helper; `_do_move`, `on_move_to`, and both `on_organize` branches use it, with
  callers keeping their own separator so announced text is byte-for-byte
  unchanged. Test: `tests/test_now_at_phrase.py`.
- [x] **5.4 Docstring/comment drift sweep** — DONE 2026-07-05 (commit 6bc04b4).
  Stale architecture references that mislead future readers (the webview/Flask
  era is gone) corrected:
  - `chirp_backend/radio.py:2` — "for use by Flask routes".
  - `chirp_backend/memory_ops.py:8-10` — "tells the Flask route…".
  - `chirp_backend/col_defs.py:12-13` — "used by the Flask routes… frontend".
  - `vrp/edit_dialog.py:3-8` — "instead of editing in the HTML grid… fast,
    read-only HTML table".
  - `vrp/_chirp_path.py:20` — "a frozen (Nuitka) build" → PyInstaller.
  - `GRID_RESTART_PLAN.md` — superseded by the 2026-07-04 work (0.9.0,
    cell cursor on macOS too); add a "SUPERSEDED — see PROGRESS_LOG 2026-07-04"
    banner or fold what's still true into `docs/` and retire it.
- [x] **5.5 `vrp/query_dialogs.py` naming** — DONE 2026-07-05 (commit 6bc04b4).
  Module docstring now says the plural name is kept deliberately for
  RepeaterBook's return so nobody "cleans it up".

---

## Phase 6 — Test-coverage gaps to close alongside the fixes

- [ ] `is_modified` lifecycle (edit → dirty; save → clean; undo → dirty). (1.1)
- [ ] Unsaved-changes decision helper: modified+cancel vetoes, save-fail vetoes,
  unmodified passes straight through. (1.2)
- [ ] Clipboard ops with an unreadable channel (stub raising `get_memory`). (1.3)
- [x] `delete_and_shift` non-contiguous behavior (whichever fix is chosen). (1.4)
  DONE (commit 022f5b9).
- [x] Settings OK-with-no-edits → zero `set_value` calls / `changed()` count 0. (1.5)
  DONE (commit 242ca7b).
- [ ] Grid guard: `chirp.wxui` never imported (0.2).
- [x] Post-delete focus lands on the erased slot without a full rebuild (4.2 —
  assert `refresh_numbers` path, not `rebuild`). DONE (commit 9cd8ffa).

---

## Suggested working order (each ~30–90 min, independently shippable)

1. Phase 0 (baseline, wxui guard, repo-root tidy)
2. 1.1 + 1.2 together (`is_modified` + unsaved prompt — one feature, NVDA pass)
3. 1.3, 1.6 (small robustness batch)
4. Phase 2 sweep (dead code — big diff, zero behavior change, easy review)
5. 3.1–3.4 (build audit + rebuild + frozen smoke), then 3.5 (NVDA on the exe)
6. 4.2 (delete → refresh_numbers) and 4.3 (tail-scan) with tests
7. 1.4 and 1.5 (each needs a design decision first)
8. Phase 5 (consolidation), Phase 6 items not already landed
9. 1.7 (pin bump) whenever upstream PR #4 merges

## Explicitly out of scope (noted so they aren't re-litigated)

- Rewriting the memory cache or the undo design — both are sound.
- i18n `_()` wrapping (CLAUDE.md wants it "planned for"; it's a project of its
  own — track separately).
- Nuitka or any packager change — settled (PROGRESS_LOG 2026-06-29).
- Removing the `./chirp` clone or trimming its tree — it must stay unmodified
  and pinned; the build already excludes its data/`.git` from the bundle.
- RepeaterBook/RadioReference — separate feature work, pending API access.
