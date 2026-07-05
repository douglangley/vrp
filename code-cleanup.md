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

### 1.4 `delete_and_shift` with a non-contiguous selection — verify semantics

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

### 1.5 Settings dialog writes back *unchanged* values on OK

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

### 1.7 Housekeeping with a correctness edge: the grid-library pin

`pyproject.toml` pins `wx-accessible-grid` to the **payown fork**
(`rev 494103f...`, PR Community-Access/wx-accessible-grid#4). Check whether the
PR merged; if so, repoint to the Community-Access rev and re-run the suite +
an NVDA smoke of the grid. (Already tracked in PROGRESS_LOG "Open / next".)

---

## Phase 2 — Dead code removal

All confirmed by grep to have **zero callers** in `vrp/`, `chirp_backend/`,
`main.py`, `build.py` (some have test-only callers, noted). Remove code + its
tests together; one commit per bullet or one sweep commit.

- [ ] **2.1 `radio.describe_radio_html`** (`chirp_backend/radio.py:343-395`) —
  webview-era HTML builder, no callers. ~50 lines.
- [ ] **2.2 `memory_ops.set_field`** (`chirp_backend/memory_ops.py:87-129`) —
  superseded by `set_channel_field` (coupled-field repair) and
  `update_channel`; no callers.
- [ ] **2.3 `memory_ops.goto`** (`chirp_backend/memory_ops.py:997-1015`) — the
  native `on_goto` does its own bounds/select/focus; only
  `tests/test_memory_ops.py:330-336` calls it. Remove both.
- [ ] **2.4 `bank_ops.has_bank`** (`chirp_backend/bank_ops.py:55-62`) — no
  callers (`on_banks` uses `get_bank_state`).
- [ ] **2.5 `col_defs.memory_to_dict` + `ColumnDef.to_dict`**
  (`chirp_backend/col_defs.py:47-56,289-304`) — Flask/webview-era JSON
  serialization, no callers.
- [ ] **2.6 `RadioState.serial_port`** (`chirp_backend/radio.py:64`) — written
  on download/unload, **never read** (the Download dialog uses
  `config.last_serial_port` instead). Remove the field, or start showing it in
  Radio Info ("Downloaded via COM4") — decide, don't leave write-only state.
- [ ] **2.7 `tools/` spikes** — `spike_native_voiceover.py`,
  `spike_native_preloaded.py`, `speak_test.py` are documented throwaways.
  Delete them (git history keeps them) or move to `tools/spikes/` with a
  one-line README. Keep `tools/update_chirp.py`.
- [ ] **2.8 Module-level `radio.set_memory`/`erase_memory`** — only
  `tests/test_undo.py` uses them; the app writes via `memory_ops`. Fold into
  5.1 (single write path) rather than deleting blind.

**Verify after the sweep:** full suite; `python -c "import vrp.native.main_window"`;
grep shows no dangling references.

---

## Phase 3 — CHIRP usage & bundle audit ("only what we need")

The CHIRP clone itself must stay (it is the driver library, pinned and bundled
by design). The audit is about what VRP *pulls in around it*.

- [ ] **3.1 Drop `--collect-submodules=chirp.sources` from `build.py`.**
  Confirmed: since the query-source removal (2026-07-05), **nothing in VRP
  imports `chirp.sources`** — the collect directive now bundles dead modules
  (and is the only reason `requests` gets frozen in). When RepeaterBook returns
  it will be a *static* import (`from chirp.sources import repeaterbook`),
  which PyInstaller follows on its own — so this doesn't need to come back.
  Also update the stale comment in `build.py:35-38` that still cites
  `chirp_backend/query.py`.
- [ ] **3.2 Decide the `requests` dependency.** In `pyproject.toml` it's listed
  as a "CHIRP library dependency", but grep shows `requests` is imported only
  by `chirp.wxui.*` (never imported by VRP) and `chirp.sources.*` (no longer
  imported). **No driver imports it.** Options: (a) drop it now and re-add with
  RepeaterBook (chirp.sources.repeaterbook needs it), or (b) keep it with a
  comment "needed by chirp.sources.repeaterbook — used again when RepeaterBook
  lands". Check whether the editable `./chirp` install already declares it
  transitively (then VRP's explicit pin is redundant either way).
- [ ] **3.3 Verify `lark` and `pyserial` stay** (they do — `chirp.bitwise_grammar`
  and the serial pipe). Confirm `--collect-data=lark` is still required by
  building and loading one image from the frozen exe.
- [ ] **3.4 Rebuild and compare.** `uv run python build.py` before/after; note
  the onedir size delta and confirm the PYZ driver-module count is unchanged
  (~192 modules / 552 models). Frozen-app smoke: open an image, edit a cell,
  save. **This is the step that catches a collect mistake — do not skip.**
- [ ] **3.5 Prism-less binary check** (already owed in PROGRESS_LOG): the
  release exe excludes `prism` — verify the channel grid still reads under NVDA
  in a built binary (announcements degrade to status-bar-only by design; the
  grid itself must still read).

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
- [ ] **4.2 `on_delete_channels` rebuilds the whole grid needlessly.** Plain
  Delete (`delete_range`) erases slots **in place** — no rows shift — yet the
  handler calls `self.grid.rebuild()` (`vrp/native/main_window.py:575`), which
  rebuilds every row dict and repaints the whole control.
  `refresh_numbers(affected)` is sufficient and keeps screen-reader focus
  steadier. (Keep `rebuild()` for the genuinely structural ops.) Cheap win,
  do this one.
- [ ] **4.3 `paste_block` make-room scan reads every channel uncached.** The
  occupancy scan (`chirp_backend/memory_ops.py:829-835`) walks
  `destination..last_bound` with direct driver reads and no early exit. Iterate
  from the tail and break at the first non-empty instead. Same pattern applies
  to `find` (`:970-987`) — fine as-is unless profiling says otherwise.
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
- [ ] **5.2 Share one `Speaker`.** `main_window.py`, `edit_dialog.py`, and
  `serial_dialogs.py` each build a module/instance-level `Speaker()` — three
  prism contexts. Add `vrp.speech.get_speaker()` (module singleton) and use it
  everywhere. Behavior identical; one backend acquisition.
- [ ] **5.3 Extract the "Now on channel N / Now at channels A to B" phrasing**
  duplicated in `_do_move`, `on_move_to`, and `on_organize`
  (`vrp/native/main_window.py:867-871,903-907,976-980`) into one helper.
- [ ] **5.4 Docstring/comment drift sweep** (stale architecture references that
  mislead future readers — the webview/Flask era is gone):
  - `chirp_backend/radio.py:2` — "for use by Flask routes".
  - `chirp_backend/memory_ops.py:8-10` — "tells the Flask route…".
  - `chirp_backend/col_defs.py:12-13` — "used by the Flask routes… frontend".
  - `vrp/edit_dialog.py:3-8` — "instead of editing in the HTML grid… fast,
    read-only HTML table".
  - `vrp/_chirp_path.py:20` — "a frozen (Nuitka) build" → PyInstaller.
  - `GRID_RESTART_PLAN.md` — superseded by the 2026-07-04 work (0.9.0,
    cell cursor on macOS too); add a "SUPERSEDED — see PROGRESS_LOG 2026-07-04"
    banner or fold what's still true into `docs/` and retire it.
- [ ] **5.5 `vrp/query_dialogs.py` naming.** Now holds only
  `ImportDestinationDialog` (kept deliberately for RepeaterBook's return —
  see PROGRESS_LOG 2026-07-05). Leave the filename, but make the module
  docstring say exactly that so nobody "cleans it up".

---

## Phase 6 — Test-coverage gaps to close alongside the fixes

- [ ] `is_modified` lifecycle (edit → dirty; save → clean; undo → dirty). (1.1)
- [ ] Unsaved-changes decision helper: modified+cancel vetoes, save-fail vetoes,
  unmodified passes straight through. (1.2)
- [ ] Clipboard ops with an unreadable channel (stub raising `get_memory`). (1.3)
- [ ] `delete_and_shift` non-contiguous behavior (whichever fix is chosen). (1.4)
- [ ] Settings OK-with-no-edits → zero `set_value` calls / `changed()` count 0. (1.5)
- [ ] Grid guard: `chirp.wxui` never imported (0.2).
- [ ] Post-delete focus lands on the erased slot without a full rebuild (4.2 —
  assert `refresh_numbers` path, not `rebuild`).

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
