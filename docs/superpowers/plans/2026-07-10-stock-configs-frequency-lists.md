# Plan — Import from frequency lists (CHIRP stock configs)

Status: ☑ implemented 2026-07-10 (see PROGRESS_LOG). Owed: NVDA pass on the
chooser dialog + a frozen-build smoke that the CSVs bundle and import. Created
2026-07-10.

## Goal

Let the user import one of CHIRP's built-in **stock configs** (20 curated
frequency lists — NOAA weather, US/CA FRS+GMRS, MURS, Marine VHF, aviation,
railroad, EU PMR/LPD, etc.) into the **loaded** radio, starting at a chosen
channel. Surfaced as **Radio ▸ Query Source ▸ Frequency lists…**, directly under
RepeaterBook.

This is a *local* import (no network), unlike RepeaterBook, but it reuses the
exact same destination + import machinery.

## Decisions (confirmed with the user, 2026-07-10)

1. **Picker UX:** a single "Frequency lists…" menu item opens a **filterable
   chooser dialog** (type-ahead list of the 20 lists + a Details button), then
   the existing destination dialog. (Not a 20-item nested submenu.)
2. **Scope (v1):** import the **whole** selected list. (A per-channel
   multi-select picker like RepeaterBook's is a possible later enhancement.)
3. **Menu:** keep the existing **"Query Source"** submenu; add "Frequency lists…"
   under "RepeaterBook…". (No rename.)
4. **Packaging:** **bundle from the CHIRP tree, no repo copy.** Source runs read
   `./chirp/chirp/stock_configs` directly (the run scripts already clone + pin
   CHIRP, so it is always present and current); the frozen build adds one
   targeted `--add-data` from the pinned tree. No files copied into VRP, and
   **run-win.bat / run-mac.sh are unchanged.**

## What already exists (so most of this is wiring, not new machinery)

- `chirp_backend/radio.py :: open_image_as_source(path)` — opens any CHIRP image,
  **including a `.csv`**, as a standalone source radio. Verified: a stock CSV
  loads as "Generic CSV" with the right channel count.
- `MainWindow._import_results(src_radio, count, numbers=None)` — the shared
  import flow: shows **`ImportDestinationDialog`** (which already asks for the
  **starting channel** and **overwrite-vs-skip**), calls
  `memory_ops.import_memories(...)`, reloads the grid, focuses the first
  imported channel, and announces the result. RepeaterBook and Import-from-File
  both already go through it.
- `ImportDestinationDialog` (`vrp/query_dialogs.py`) — destination + overwrite.
- `RadioListView` (`vrp/serial_dialogs.py`) — the a11y-tuned, type-ahead
  `wx.ListCtrl` used by the model picker; reuse it for the list chooser.

**Answer to "what else do we need besides a starting channel?"** — just
overwrite-vs-skip, and both are already collected by `ImportDestinationDialog`.
Nothing else.

## Design

### 1. Backend: `chirp_backend/stock_configs.py` (new)

Framework-agnostic (no wx), unit-testable headless.

- `stock_configs_dir() -> str`
  - Frozen (`getattr(sys, "frozen", False)` / `sys._MEIPASS`): return
    `os.path.join(sys._MEIPASS, "chirp", "stock_configs")` (the `--add-data`
    destination — see Packaging).
  - From source: `os.path.join(os.path.dirname(chirp.__file__),
    "stock_configs")`. (Do **not** rely on `importlib.resources` for the frozen
    case: the dir has no `__init__.py` and we bundle via `--add-data`, not
    `--collect-data`, so an explicit `sys._MEIPASS` path is the robust choice.)
- `list_configs() -> list[tuple[str, str]]`
  - Return `[(display_name, abs_path), …]` sorted by display name, for every
    `*.csv` in the dir (skip dotfiles / `~` backups, mirroring CHIRP's filter).
    `display_name` = filename without the `.csv` extension
    (e.g. "US NOAA Weather Alert").
- `describe_config(path) -> str` (for the Details button)
  - Open via `radio_backend.open_image_as_source(path)`, count non-empty
    channels, and format a short block: channel count + the first several
    `freq  name` rows. Reuse `col_defs.format_freq_mhz` for display. Returns a
    plain string for `InfoDialog`.

### 2. UI: `FrequencyListDialog` (in `vrp/query_dialogs.py`)

A real modal `wx.Dialog`, titled "Import from frequency list" (title = accessible
name). Mirrors `ModelPicker`'s accessible pattern:

- A **filter** `wx.TextCtrl` (label created *before* the control — see the
  wxMSW label-before-control rule) that narrows the list as you type.
- A **`RadioListView`** (single-column, type-ahead) of the display names; opens
  with the first item selected/focused.
- **Details…** button → `describe_config(selected)` shown in the read-only,
  navigable `InfoDialog` (`vrp/info_dialog.py`); returns focus to the list.
- **Import** (default / `wx.ID_OK`) and **Cancel** (`wx.ID_CANCEL`,
  `SetEscapeId` so Escape closes). `get_selection()` returns the chosen
  `(display_name, path)`.
- Focus returns to the grid when the dialog closes.

### 3. Handler: `MainWindow.on_frequency_lists` (in `main_window.py`)

```
def on_frequency_lists(self, _evt=None):
    if not radio loaded: announce "Open or download a radio first…"; return
    configs = stock_configs.list_configs()
    if not configs: announce "No frequency lists are available."; return
    dlg = FrequencyListDialog(self, configs, describe_fn=stock_configs.describe_config)
    if dlg.ShowModal() != wx.ID_OK: focus grid; return
    name, path = dlg.get_selection(); dlg.Destroy()
    src, message = radio_backend.open_image_as_source(path)
    if src is None: announce+MessageBox(message, assertive); return
    count = <non-empty channels in src>
    if count == 0: announce "That list has no channels."; return
    self._import_results(src, count)   # start channel + overwrite + import + focus
```

Gated on a loaded radio (menu `needs_radio=True`, guarded in the handler), like
RepeaterBook — imported channels go into the loaded image.

### 4. Menu wiring (`_build_radio_menu`)

Add under the existing RepeaterBook item in the "Query Source" submenu:

```
self._add(query, "query_freqlists", "&Frequency lists…",
          self.on_frequency_lists, needs_radio=True)
```

No new global accelerator. Update `APP_SHORTCUTS`? No (menu-only, no accel), but
update `docs/keyboard-map.md` and `docs/chirp-feature-coverage.md` per CLAUDE.md.

### 5. Packaging (`build.py` only)

Add one targeted PyInstaller data flag (the file even anticipates this in its
"NOT --collect-data=chirp" note):

```
--add-data=<PROJECT_ROOT>/chirp/chirp/stock_configs{os.pathsep-ish}chirp/stock_configs
```

(Use PyInstaller's `src{SEP}dest` form with the platform separator, as the code
already does for other data.) `ensure_chirp_on_pin()` runs first, so the bundled
CSVs always match the tested `CHIRP_COMMIT`. Frozen runtime dir becomes
`os.path.join(sys._MEIPASS, "chirp", "stock_configs")` — matches
`stock_configs_dir()`.

**No changes to run-win.bat / run-mac.sh** — they clone + checkout CHIRP at the
pin, so source runs read the CSVs straight from `./chirp/chirp/stock_configs`.

## Tests

- `tests/test_stock_configs.py` (backend, headless):
  - `list_configs()` returns 20 entries, sorted, `.csv` stripped, dotfiles
    skipped; each path exists.
  - `stock_configs_dir()` resolves to the CHIRP tree from source.
  - `describe_config()` on "US NOAA Weather Alert" reports 10 channels and
    includes a known frequency (162.550) — proves the open+count path.
  - End-to-end: `open_image_as_source(<a stock path>)` →
    `memory_ops.import_memories(src, dest, overwrite)` lands the channels at the
    destination in a loaded UV-5R (reuse the existing import test scaffolding).
- Dialog smoke test (like `test_repeaterbook_dialog.py`): construct
  `FrequencyListDialog`, assert the list is populated, the filter narrows it, and
  `get_selection()` returns a `(name, path)` pair. Assert label-before-control
  order (guard against the wxMSW off-by-one).

## Accessibility checklist (enforce)

- Every control labeled; **label created before its control** (wxMSW MSAA rule).
- Real modal dialog with a title; Escape = Cancel; focus returns to the grid.
- Type-ahead list (RadioListView) — NVDA reads rows; VoiceOver caveat noted (the
  same known wx.ListCtrl-on-macOS limitation as the model picker).
- Import result + errors announced via `self.announce`; focus moves to the first
  imported channel (the announcer is the fallback, focus is primary).
- **Owed:** an on-device **NVDA pass** on the chooser dialog + the import; the
  macOS/VoiceOver pass rides along with the existing serial-dialog caveat.

## Out of scope for v1 (possible later)

- **User-supplied lists.** CHIRP also scans a user config dir and offers "Open
  stock config directory". VRP could add a user `stock_configs` folder + a
  "reveal" action so operators drop in their own CSV lists. Cheap, but deferred.
- **Per-channel multi-select** within a list (RepeaterBook-style results picker).
  `_import_results` already supports a `numbers=` subset, so this is a small
  follow-up if wanted.
- **CHIRP's MD5 legacy-dedup** logic — not needed; VRP reads only the bundled set.

## Rollout order

1. `chirp_backend/stock_configs.py` + `tests/test_stock_configs.py` (backend green).
2. `FrequencyListDialog` + dialog smoke test.
3. `on_frequency_lists` + menu wiring.
4. `build.py --add-data`; verify a frozen build lists + imports a stock config.
5. Docs: `keyboard-map.md`, `chirp-feature-coverage.md` (Open Stock Config row),
   ROADMAP, PROGRESS_LOG. Then the owed NVDA pass.
