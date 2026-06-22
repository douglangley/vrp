# VRP Keyboard Map

Goal: **everything** in the app is reachable and operable from the keyboard,
including the memory grid. This file is the single source of truth for
shortcuts and is updated as each phase lands.

There are two UIs (see CLAUDE.md "What This Project Is"): the **native UI**
(default, `vrp/native/`) documented first below, and the **legacy webview UI**
(`vrp/app.py`, launched with `--webview`, being retired) documented further
down for as long as it exists. Conventions for both:

- Global commands use `Ctrl`+key (or `Alt` for menus) to avoid clashing with
  NVDA browse-mode single-letter quick navigation.
- Inside the grid, single-letter keys are reserved for the screen reader; grid
  commands use arrows, Enter/F2, and `Ctrl`/`Alt` combinations.

## Native UI (default)

A real native `wx.MenuBar` carries Alt-mnemonics and Ctrl-combo accelerators
together in the same menu item — there's no WebView2 in the way, so there's
only one command surface here (contrast the legacy UI's three, below). `Alt`,
`Alt+letter`, and `F10` all open/navigate the menu the normal Windows way;
arrow keys move across top-level menus; NVDA reads it like any native app menu.

### Menu bar + shortcuts

| Menu | Item | Shortcut | Notes |
|------|------|----------|-------|
| File | Open Image File… | `Ctrl+O` | |
| File | Save | `Ctrl+S` | needs a loaded radio |
| File | Save As… | `Ctrl+Shift+S` | needs a loaded radio |
| File | Close Image | — | needs a loaded radio |
| File | Import from File… | — | needs a loaded radio |
| File | Export to CSV… | — | needs a loaded radio |
| File | Preferences… | — | |
| File | Exit | `Ctrl+Q` | |
| Radio | Download from Radio | `Ctrl+Shift+D` | |
| Radio | Upload to Radio | `Ctrl+Shift+U` | needs a loaded radio |
| Radio | Query Source ▸ … | — | needs a loaded radio; one item per registered source |
| Radio | Settings… | `Ctrl+Shift+P` | needs a loaded radio |
| Radio | Radio Info… | — | needs a loaded radio |
| Channels | Edit channel… | `F2` | needs a loaded radio |
| Channels | Go to channel… | `Ctrl+Shift+G` | needs a loaded radio |
| Channels | Channel banks… | `Ctrl+B` | needs a loaded radio |
| Channels | Move up | `Ctrl+Shift+Up` | needs a loaded radio |
| Channels | Move down | `Ctrl+Shift+Down` | needs a loaded radio |
| Channels | Move to channel… | `Ctrl+Shift+M` | needs a loaded radio |
| Channels | Organize Channels… | `Ctrl+M` | needs a loaded radio |
| Channels | Find… | `Ctrl+F` | needs a loaded radio |
| Channels | Find next | `Ctrl+G` | needs a loaded radio |
| Help | Keyboard Shortcuts | `F1` | shows this list as a plain-text message box |
| Help | About | — | |

Items marked "needs a loaded radio" are disabled until an image is open. F1's
on-screen list (`APP_SHORTCUTS` in `vrp/native/main_window.py`) is kept in
sync with this table by hand — update both when adding a command.

### Channel grid navigation and selection

The grid is a multi-select virtual `wx.ListCtrl` (`vrp/native/channel_grid.py`)
with every channel populated at once — no paging.

| Key | Action |
|-----|--------|
| Arrows | Move focus a row at a time |
| `Shift+Arrow` | Extend a contiguous selection |
| `Ctrl+Space` | Toggle the focused row into/out of a non-contiguous selection |
| `F2` / `Enter` | Open the edit dialog for the focused channel |

### Reorganizing channels

Select one channel, or a group: `Shift+Arrow` extends a contiguous block;
`Ctrl+Space` toggles individual rows for a non-contiguous set. Then:

| Key | Action |
|-----|--------|
| `Ctrl+Shift+Up` | Move the selected channel(s) up one slot |
| `Ctrl+Shift+Down` | Move the selected channel(s) down one slot |
| `Ctrl+Shift+M` | Move the selected channel(s) to a chosen channel |
| `Ctrl+M` | Organize (delete/copy/sort/insert/arrange) dialog |
| `Ctrl+Shift+G` | Go to channel |
| `Ctrl+F` / `Ctrl+G` | Find / Find next |
| `Ctrl+B` | Channel banks for the focused channel |

After a move, the moved block stays selected at its new position and focus
lands on its first channel; the result is announced via the status bar and
speech.

### Dialogs (shared with the legacy UI)

Editing, bulk operations, find, settings, banks, and download/upload all open
the same native wx dialogs the legacy UI uses (see "Memory grid editing",
"Organize Channels", etc. under the legacy section below for the detailed
per-dialog keyboard behavior — Tab order, Enter/Esc, validation-keeps-dialog-
open — which is identical regardless of which UI opened the dialog).

---

## Legacy webview UI (`--webview`, being retired)

The sections below describe `vrp/app.py`, VRP's original UI, kept behind
`--webview` only until the native UI above is confirmed at parity. New
commands should be added to the native UI, not here.

### Native menu bar + in-page shortcuts

There is a native wx menu bar (File / Radio / Channels / Help) AND in-page
buttons AND global Ctrl-combo shortcuts — all three reach the same commands.

About the menu and wxWidgets issue #24786: the webview is the only client-area
control and holds focus essentially permanently, so a focused WebView2
swallows `Alt` entirely — confirmed with NVDA (bare `Alt`, `Alt+F`, `Alt+R` all
did nothing; `Ctrl` accelerators were already covered by the bridged in-page
shortcuts below). This is now solved by the **wx-accessible-menubar** library
(extracted from this app): `_build_menubar` builds the real `wx.MenuBar` and
`MainWindow` hands it to `AccessibleMenuBar`. The library injects an in-page key
listener into the webview (the only place keys survive a focused WebView2),
bridges plain `Alt`, `Alt+mnemonic`, and `F10` back over its own script-message
channel, and drives the real native menu bar via `WM_SYSCOMMAND`/`SC_KEYMENU` —
so it stays a real native Win32 menu (arrow keys + Enter navigate it, `EVT_MENU`
fires, NVDA reads it). Plain `Alt` is confirmed on key-up so it isn't mistaken
for the start of `Alt+letter`/`Alt+Tab`/`Alt+F4`. After a menu closes (or the
window is maximized/reactivated) the library restores webview focus so the
shortcuts stay live. Menu items that need a loaded radio are disabled (announced
"unavailable") until an image is open.

Menu contents: **File** (Open / Open Recent ▸ … / Save / Save As / Close /
Import from File… / Export to CSV… / Preferences… / Exit), **Radio** (Download / Upload / Query Source ▸ … /
Settings… / Radio Info…), **Channels** (Edit channel… / Go to channel… / Channel banks… /
Organize Channels… / Find / Find next / Previous page / Next page), **Help** (Keyboard
Shortcuts / About). "Edit channel…" and "Go to channel…" prompt for a number
(native dialog) — they're the menu equivalents of the per-row Edit button and
the page-nav Go-to field, so every command is reachable from the menu.

### Global shortcuts (handled in-page, bridged to Python)

| Key             | Action                       | Status |
|-----------------|------------------------------|--------|
| `Ctrl+O`        | Open Image File…             | done   |
| `Ctrl+S`        | Save                         | done   |
| `Ctrl+Shift+S`  | Save As…                     | done   |
| `Ctrl+Alt+Left` | Previous channel page        | done   |
| `Ctrl+Alt+Right`| Next channel page            | done   |
| `Ctrl+M`        | Organize Channels dialog     | done   |
| `Ctrl+F`        | Find a channel               | done   |
| `Ctrl+G`        | Find next match              | done   |
| `Ctrl+Shift+D`  | Download from radio          | done   |
| `Ctrl+Shift+U`  | Upload to radio              | done   |
| `Ctrl+Shift+P`  | Edit radio settings          | done   |
| `Ctrl+B`        | Assign a channel to banks    | done   |
| `F1`            | Show keyboard shortcuts list | done   |
| `Alt+F4`        | Exit (native window close)   | done   |

### Menu mnemonics (caught by EVT_CHAR_HOOK, see above)

| Key      | Action                  | Status |
|----------|--------------------------|--------|
| `Alt+F`  | Open the File menu       | done   |
| `Alt+R`  | Open the Radio menu      | done   |
| `Alt+C`  | Open the Channels menu   | done   |
| `Alt+H`  | Open the Help menu       | done   |
| `F10`    | Open the File menu       | done   |

The channel grid is paged (100 channels per page). The "Channel pages" nav
above the table has Previous/Next buttons (disabled at the first/last page) and
a "Go to channel N" field (Enter or Go) that jumps to that channel's page and
focuses its Edit button. Page changes announce the new range; an out-of-range
"Go to" keeps focus in the field and speaks the valid range.

Shortcuts are gated: ignored while typing in a text/search/number field, and
only the listed Ctrl(+Shift) combos are intercepted (NVDA owns the NVDA
modifier, not bare Ctrl+letter, so there's no quick-nav clash). Single-letter
shortcuts are never used (rule #8). Download/Upload and Close currently have
in-page buttons; their shortcuts arrive with the relevant phase.

### Memory grid editing (Phase 2 — done, dialog model)

The grid is a READ-ONLY semantic `<table>`. Editing a channel opens a native
wx dialog (in-grid editing was dropped: on large radios it forced the screen
reader to re-read the whole table on every keystroke). Each row's **second
column** is an "Edit channel N" button (right after the channel-number row
header, so it's quick to reach); activating it opens the dialog with one labeled
control per field. Native dialogs are separate top-level windows, so keyboard
and NVDA work natively (focus trap, Escape, title all free). **Empty channels
expose ALL fields** (so a new channel can be fully defined in one pass) with
focus on Frequency (which carries a "required to activate" hint); immutable
fields are disabled and labeled "(read only)".

| Key                | Context                  | Action                            |
|--------------------|--------------------------|-----------------------------------|
| `Ctrl+Alt+arrows`  | In the table             | NVDA-native table navigation      |
| `Enter` / `Space`  | On a row's Edit button   | Open the edit dialog for that row |
| `Tab` / `Shift+Tab`| In the dialog            | Move between fields                |
| `Enter`            | In the dialog            | OK — validate, save, close        |
| `Esc`              | In the dialog            | Cancel — discard, close           |

On invalid input the dialog stays open, speaks the reason, and focuses the bad
field. On OK only the edited row is refreshed and focus returns to its Edit
button. No bare single-letter shortcuts in the grid (NVDA browse mode owns a–z).

### Editable grid preview (wx-accessible-grid — preview/beta, NVDA pass owed)

Not yet the production channels view (see above); a standalone harness at
`tools/grid_preview.py` (`uv run python tools/grid_preview.py`) previews the
in-progress editable grid, driven by `vrp/channel_grid_model.py`. It renders a
real `<table role="grid">` via the aria-activedescendant pattern so NVDA stays
in focus mode.

| Key                  | Action                                  |
|-----------------------|------------------------------------------|
| Arrows                | Move focus a cell at a time (across a row speaks the column; down a column speaks the channel number) |
| `F2` / `Enter`        | Start editing the focused cell           |
| `Enter`               | Commit the edit                          |
| `Esc`                 | Cancel the edit                          |
| `Space`               | Toggle the row-selection checkbox        |
| `Delete`              | Delete the selected row(s)               |
| Applications key      | Open the row context menu                |

### Organize Channels (move/delete/etc., Phase 3 — done)

`Ctrl+M` (or the "Organize Channels…" button) opens a native wx dialog. There
are no per-row checkboxes (they'd bloat the DOM on large radios). Selection is a
contiguous From/To range by default, with an optional advanced field that takes
a channel list like `1-5,8,10-12`. Pick one operation: Delete, Delete and shift
up, Insert blank, Move up/down, Move to…, Copy to…, Sort…, Arrange (compact).
Only the chosen operation's parameters show (shift mode, destination, sort
column/order). Destructive/reordering ops show a native confirm dialog stating
the range, count, and that it can't be undone (no undo). After an op the
affected page re-renders, focus lands on the result channel, and the result is
announced.

### Download / Upload (Phase 4 — done, hardware test owed)

Radio ▸ Download from Radio (`Ctrl+Shift+D`) opens a native dialog: a serial-port
chooser (with Refresh and an explicit "no ports" state) and a model picker that
is a filter field + list (type to narrow ~550 models by substring). Upload
(`Ctrl+Shift+U`) needs only a port and shows a confirm ("overwrite ALL channels…",
default Cancel). The transfer runs on a background thread; progress is announced
through the live region (throttled), with a gauge for sighted users. Download can
be cancelled (result discarded); upload cannot (a half-written radio is worse).
On download success the grid re-renders and focus moves to the first channel.
Real-radio verification is still owed (no hardware in dev).

### Preferences & Open Recent (config subsystem — done)

Settings persist in a JSON file under the user config dir (atomic writes;
corrupt/missing falls back to defaults). File ▸ Preferences… (a native dialog)
has **Channels per page** (25/50/100/250/500 — changing it re-renders the grid
and re-clamps the page) and **Speak status messages aloud** (off by default;
gates the *supplemental* prism speech — the screen reader always reads the live
region regardless). File ▸ Open Recent ▸ lists the last 8 opened images
(numbered `&1…&8`, basename label with the full path as the item's help text,
parent folder appended only when basenames collide), plus Clear recent files;
empty shows a disabled "(No recent files)". A recent entry that's gone is
announced and pruned. Menu-only (no Ctrl shortcuts).

### Import / Export / Radio Info (Phase 8 — done)

File ▸ Import from File… picks another radio image (native file dialog), loads
it as an independent source (the active radio is untouched), then reuses the
import-destination dialog + import op (adapts each memory via CHIRP import_logic,
overwrite/skip, announces counts, focuses the first imported channel). File ▸
Export to CSV… writes the loaded radio's non-empty channels to a CSV via CHIRP's
generic_csv driver (native save dialog with overwrite prompt; announces count +
file). Radio ▸ Radio Info… shows a read-only accessible dialog (label/value
tables: identity, capacity, capabilities incl. Yes/No flags). All three are
menu-only (no Ctrl shortcut) and disabled until a radio is loaded. Native
printing is intentionally not implemented — Export to CSV is the accessible
equivalent.

### Query sources (Phase 7 — framework + AMSAT/SatNOGS, network test owed)

Radio ▸ Query Source ▸ (a source) opens a native param dialog (with the source's
attribution + a descriptive Terms-of-Service link), then fetches on a background
thread with the shared progress dialog (status announced via the live region).
On success it announces the result count and opens an import dialog: a
destination channel (defaults to the first empty channel) + Overwrite/Skip for
occupied channels. Import adapts each memory for the target radio (CHIRP
import_logic) and announces the counts. Reached via the menu (Alt → R → Q →
source); no Ctrl shortcut (too many sources). Disabled until a radio is loaded
(results import into it). Sources are gated behind a registry; the param dialog
is spec-driven (text + choice kinds). Wired now: AMSAT, SatNOGS, DMR-MARC
(city/state/country) and mapy73.pl (network choice). Still deferred: RepeaterBook
(dynamic country→state cascade), RadioReference (credentials/login), and
przemienniki.net/.eu (band/mode code mapping + coordinates).

### Banks (Phase 6 — done, NVDA pass owed)

Channels ▸ Channel banks… (`Ctrl+B`) prompts for a channel, then opens a native
dialog to assign it to banks: a CheckBox per bank for radios that allow multiple
banks per memory, or a RadioBox ("None" + banks) for zero-or-one radios;
fixed-bank radios show the membership read-only. An intro line states current
membership in words. OK applies the add/remove diff and announces the new
membership; failures are reported truthfully. Only enabled on bank-capable
radios (the menu item is disabled / `Ctrl+B` announces "no banks" otherwise).
Bank renaming and a "channels in a bank" overview are deferred (Phase 6.1).

### Radio settings (Phase 5 — done, NVDA pass owed)

Radio ▸ Settings… (`Ctrl+Shift+P`) opens a native dialog with a `wx.Treebook`:
the tree lists the radio's top-level setting groups; each page is a scrolled
panel of labelled controls (CheckBox / Choice / SpinCtrl / TextCtrl by value
type). Nested sub-groups are flattened into their page under an indented bold
heading. Read-only settings are disabled and labelled "(read only)". OK validates
every value (keeps the dialog open, reveals the offending group's page, focuses
the field, and speaks the reason on failure), then writes all changes via
`set_settings`; Cancel/Escape discards. Initial focus lands on the tree.

### Find (Phase 3 — done)

`Ctrl+F` (or the "Find…" button / Channels ▸ Find) opens a native dialog: a text
field + a "Search in" chooser (All fields / Name / Frequency / Comment). It jumps
to the first matching channel (navigating to its page, focusing its Edit button)
and announces the match. `Ctrl+G` (Find next) steps to the next match; the search
wraps, announcing "Wrapped to start" or "Only match" as appropriate. No match
keeps the dialog open and speaks "not found"; an empty search field is rejected.

### Operations (Phase 3 — planned)

Delete, insert, move up/down, move-to, copy-to, sort, arrange, find/find-next,
goto — all keyboard-accessible, with a "Move to channel…" style dialog instead
of any drag-and-drop. Exact bindings to be filled in when implemented.

