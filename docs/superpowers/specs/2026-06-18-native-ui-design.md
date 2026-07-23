# Native UI Design

**Status:** Approved-to-build (owner asked to proceed without per-step prompts; this doc is the source of truth — review and flag anything).
**Date:** 2026-06-18
**Branch:** `feat/native-ui` (off `main`)

> **Historical spec / current-state note (2026-07-22):** the native UI is the
> sole UI and the webview has been removed. The clipboard deferred here later
> landed, and now supports generic cross-image/section radio migration plus an
> accessible static/dynamic memory-section chooser and explicit one-memory
> transfer to/from named special channels. Current behavior and the remaining
> bank-mapping, D-STAR, and acceptance work live in
> `docs/superpowers/plans/2026-07-21-cross-radio-migration.md`.

## Goal

Replace VRP's embedded-webview view layer with a fully native wxPython UI that
is first-class accessible on **both** NVDA (Windows) and VoiceOver (macOS),
using native widgets: a real menu bar, a real data grid, and native dialogs
(with combo boxes for enumerated fields). The headline new capability is
**keyboard-driven reorganization of memory channels, including moving a
contiguous or non-contiguous group of channels**, all from the grid.

## Why native (context)

The current app renders semantic HTML into an `AccessibleWebView`. That buys
rich ARIA semantics but costs a lot: a focused WebView2 swallows `Alt`
(wxWidgets #24786), forcing the EVT_CHAR_HOOK menu workaround and an in-page
command region; focus drops on `set_content`; a JS↔Python bridge must be
maintained; and the grid is paged at 100 rows purely because re-rendering the
DOM is expensive.

Native list/menu controls expose accessibility directly through the platform
APIs (UI Automation/MSAA on Windows → NVDA; NSAccessibility on macOS →
VoiceOver). `wx.ListCtrl` in report mode in particular has the longest, most
reliable screen-reader track record on both platforms. Going native removes the
entire #24786 class of bugs and eliminates paging.

## What is reused (unchanged)

These are framework-agnostic or already native, and are reused as-is:

- **`chirp_backend/`** — `radio`, `memory_ops` (incl. group ops:
  `move_memories(numbers, direction)`, `move_to(numbers, destination)`,
  `copy_memories`, `delete_and_shift`, `insert_row`, `sort_range`,
  `arrange_range`, `find`, `goto`, `delete_range`), `col_defs`
  (`build_column_defs(features)`, `memory_to_dict(mem, col_defs)`), `bank_ops`,
  `query`.
- **Native dialogs** in `vrp/`: `edit_dialog.EditChannelDialog` (uses
  `wx.Choice` combo boxes per enum column), `ops_dialog.ChannelOperationsDialog`,
  `find_dialog`, `bank_dialog`, `settings_dialog`, `serial_dialogs`,
  `query_dialogs`, `prefs_dialog`.
- **`vrp/config.py`** (preferences + recent files), **`vrp/speech.py`** (prism
  speech, no-op when unavailable).

What is **replaced** (webview-specific, not used by the native app):
`vrp/html.py`, `vrp/views.py`, the `AccessibleWebView` host, the JS bridge, the
EVT_CHAR_HOOK Alt workaround, and the in-page command region. These remain in
the tree for the existing `main.py` (webview) path during v1; they are retired
in a follow-up once the native UI is screen-reader-verified.

## Architecture

New package `vrp/native/` (each module one responsibility):

- **`main_window.py`** — `MainWindow(wx.Frame)`. Owns the native `wx.MenuBar`
  (File / Radio / Channels / Help), a `wx.StatusBar`, and hosts the channel
  grid. Holds the command handlers (file/radio/channels/help). Handler bodies
  reuse the logic from the existing `vrp/app.py` handlers (call `chirp_backend`,
  open the reused dialogs) but refresh the grid instead of calling
  `set_content`. Menu items that need a loaded radio are enabled/disabled from a
  single `_update_menu_state()`.
- **`channel_grid.py`** — `ChannelGrid(wx.ListCtrl, style=LC_REPORT|LC_VIRTUAL)`.
  Single responsibility: present rows, manage selection, and reorder. Owns an
  in-memory `rows` model (a list of per-channel dicts from `memory_to_dict`),
  implements `OnGetItemText(item, col)`, builds columns from `col_defs`, exposes
  `selected_channel_numbers() -> list[int]`, `focus_channel(n)`,
  `select_channels(nums)`, `reload(state)`, `refresh_rows(nums)`, and the
  reorganization key bindings. No `wx`-free business logic lives here — the
  index/selection math is delegated to `grid_model.py` so it is unit-testable.
- **`grid_model.py`** — pure, `wx`-free helpers: build the row list for a loaded
  radio (wrapping `col_defs`), map ListCtrl item indices ↔ channel numbers,
  compute the post-move selection set (which channel numbers to reselect and
  which to focus) from an op result, and column metadata (header label, width
  hint, alignment). Fully unit-tested without a `wx.App`.
- **`announce.py`** — desktop announcement helper. `Announcer(frame)` with
  `announce(message, *, assertive=False)` that (1) sets the status bar text and
  (2) speaks via `vrp.speech` when available. Focus-to-result is the primary
  screen-reader announcement and is done by the grid/handlers; `announce()`
  covers operation summaries and errors that have no natural focus target.
- **`app.py`** (native) — `run(debug: bool)` that creates the `wx.App` and
  `MainWindow`. Thin.

Entry: `main.py --native` launches `vrp.native.app.run()`; with no flag it
launches the existing webview app (unchanged). Both coexist during v1.

## Channel grid

- **Control:** `wx.ListCtrl` with `wx.LC_REPORT | wx.LC_VIRTUAL`. Multi-select
  is the default (no `LC_SINGLE_SEL`). Virtual mode means population is instant
  regardless of radio size and there is **no paging** (a single scrollable list
  of all channels).
- **Columns:** built from `col_defs.build_column_defs(features)`. Column 0 is
  the channel number (the row's identity). Remaining columns follow the radio's
  feature set (Frequency, Name, Tone, etc.). Empty channels render an explicit
  textual "(empty)" marker in the Name/Frequency cells — never color-only
  (accessibility rule #7).
- **Row model:** an in-memory list; `OnGetItemText(item, col)` reads from it.
  `reload(state)` rebuilds it from the loaded radio; `refresh_rows(nums)` updates
  specific channels after an edit/op via `RefreshItem`.
- **Navigation:** native arrow keys move the focused row (screen reader reads the
  row), Home/End jump to first/last, type-ahead is native. No bare single-letter
  app shortcuts in the grid (rule #8) — those belong to the screen reader/native
  control.

## Menu bar

Native `wx.MenuBar`, same command surface as today, all reused handlers:

- **File:** Open, Open Recent ▸, Save, Save As, Close, Import from File…,
  Export to CSV…, Preferences…, Exit.
- **Radio:** Download, Upload, Query Source ▸ (one item per `query.SOURCES`),
  Settings…, Radio Info…
- **Channels:** Edit channel…, Go to channel…, Channel banks…, the
  reorganization commands (Move up, Move down, Move to…), Organize Channels…
  (the full ops dialog), Find, Find next.
- **Help:** Keyboard Shortcuts, About.

Because there is no webview, `Alt`/`Alt+letter`/`F10` open menus natively and
screen readers read them. The EVT_CHAR_HOOK workaround is **not** needed.
Accelerators (Ctrl+O, Ctrl+S, etc.) are real menu accelerators and fire
normally.

## Editing (combo boxes)

Editing a channel opens the reused `EditChannelDialog`: a native modal with one
labeled control per field, `wx.Choice` **combo boxes** for enumerated fields
(mode, duplex, tone mode, power, tuning step, etc.). `Enter`/`F2` on a focused
grid row opens it; on OK the edited row(s) refresh in place and focus returns to
that row. Empty channels expose all fields with focus on Frequency. This
preserves the project's deliberate dialog-based editing model (in-grid editing
was rejected for forcing full-table re-reads).

## Reorganization (headline feature)

The grid's native multi-selection is the operand for every reorder/bulk op.

- **Selecting a group:** `Shift+Arrow` extends a contiguous selection;
  `Ctrl+Space` toggles individual rows for a non-contiguous set — all native
  `wx.ListCtrl` behavior, announced by the screen reader.
  `selected_channel_numbers()` returns the chosen channels (falling back to the
  focused row when nothing is explicitly selected).
- **Move up / down:** `Ctrl+Shift+Up` / `Ctrl+Shift+Down` (also in the Channels
  menu). Collect the selection → `memory_ops.move_memories(numbers, direction)`
  → refresh affected rows → reselect the moved channels at their new positions
  and focus the first → announce e.g. "Moved 4 channels up. Now channels 5
  through 8." Disabled (announced) when the move would run past the ends.
- **Move to channel…:** `Ctrl+Shift+M` (and menu) opens a small native
  number-prompt dialog for the destination (the same simple pattern as "Go to
  channel"), then `memory_ops.move_to(numbers, destination)` → refresh, reselect
  at the destination, focus, announce. The full "Move to" with column options
  remains reachable through `Organize Channels…` (`ops_dialog`); this keyboard
  command is the fast path.
- **Other bulk ops:** Delete, Delete and shift, Copy to…, Insert blank, Sort…,
  Arrange (compact) via `Organize Channels…` (`ops_dialog`), which defaults its
  range to the current grid selection. Destructive/reordering ops confirm with a
  native dialog stating range, count, and "cannot be undone" (no undo), matching
  current behavior.
- **Selection restore math** (the tricky part) is computed in `grid_model` from
  the op's `OpResult.affected` channel list, so it is unit-tested without a GUI:
  given the affected channels and direction/destination, produce the set to
  reselect and the channel to focus.

## Accessibility requirements (enforced)

1. Every control (menu items, grid, dialog fields, status bar) exposes a correct
   Name / Role / Value / State to the platform a11y API. Native widgets provide
   this; custom-drawn controls are avoided (no `wx.grid.Grid`).
2. The grid is a real native list/grid (`wx.ListCtrl` report mode) with column
   headers, so screen readers announce column titles and row position.
3. Operation results, errors, and progress are announced: focus moves to the
   relevant row (primary), and `Announcer.announce()` updates the status bar and
   speaks via prism when present. Long serial operations announce throttled
   progress (reusing the existing background-thread + `wx.CallAfter` pattern).
4. Dialogs (reused) are native modals: focus-trapped, Escape-closable,
   title-labeled, return focus to the trigger — already satisfied by wx.
5. No operation requires the mouse. Every reorganization has a keyboard path
   (move up/down, move-to, organize dialog).
6. Focus is managed after every op: after a move, focus the first moved channel;
   after delete, focus the next surviving row (or the list); after a dialog
   closes, focus returns to the originating row.
7. State is never color-only: empty channels and any error/marker state carry
   text the screen reader can read.
8. No bare single-letter app shortcuts; reorganization uses Ctrl+Shift combos.
   Menu accelerators are standard.

## Entry point & coexistence

`main.py` gains a `--native` flag → `vrp.native.app.run(debug=...)`. Without the
flag the existing webview app runs unchanged. This keeps the working app intact,
makes the two directly comparable on a screen reader, and is fully reversible.
Once the native UI passes manual NVDA + VoiceOver acceptance, a follow-up
retires the webview layer and makes native the default.

## Testing strategy

- **Pure logic (unit-tested, no `wx.App`):** `grid_model` row building from a
  loaded radio image, item-index ↔ channel-number mapping, post-move selection
  computation, column metadata, empty-channel text markers. These use the same
  `chirp/tests/images/*.img` fixtures the existing tests use — no hardware, no
  GUI.
- **Reused backend** keeps its existing tests (already green).
- **GUI widget layer** (the `wx.ListCtrl`/`wx.MenuBar`/dialog wiring) is verified
  by manual NVDA + VoiceOver acceptance, mirroring how dialog-opening actions are
  validated today (they need a running `wx.App`). Where a headless `wx.App` smoke
  test is feasible on the dev machine, add a minimal "frame constructs, grid
  populates N rows from a test image, selection→numbers works" test, but do not
  block on headless GUI testing in CI.

## Out of scope (v1) / follow-ups

- Retiring the webview layer (`html.py`, `views.py`, webview host) — separate
  follow-up after SR sign-off.
- Cut/paste channel clipboard model — `move`/`move-to` cover "reorganize a
  group"; clipboard is a later enhancement (YAGNI now).
- A bank-filter combo box above the grid — possible later; not needed for v1.
- "Open Stock Config", "Load Module", Print — already deferred in the feature
  coverage doc; unchanged.

## Risks to validate on real screen readers (acceptance gate)

- `wx.ListCtrl` virtual report mode reads correctly on **VoiceOver/macOS**
  (row/column announcement, multi-select announcement). Primary risk; if
  VoiceOver handling is poor, fall back to a non-virtual `ListCtrl` or evaluate
  `DataViewListCtrl`. The grid is wrapped behind `channel_grid.py` so the swap is
  contained.
- Multi-select extend/toggle is announced clearly on both readers.
- Move/reorder announcements (focus-to-result + status/speech) are sufficient and
  not too verbose.
- Menu accelerators and `Alt` menu access behave natively on both platforms.
