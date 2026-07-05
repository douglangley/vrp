# VRP Keyboard Map

Goal: **everything** in the app is reachable and operable from the keyboard,
including the memory grid. This file is the single source of truth for
shortcuts and is updated as each feature lands.

VRP has one UI, built entirely from native wx controls (see CLAUDE.md "What This
Project Is"). Conventions:

- Global commands use `Ctrl`+key (or `Alt` for menus) to avoid clashing with
  NVDA browse-mode single-letter quick navigation.
- Inside the grid, single-letter keys are reserved for the screen reader; grid
  commands use arrows, Enter/F2, and `Ctrl`/`Alt` combinations.

## Menu bar

A real native `wx.MenuBar` carries Alt-mnemonics and Ctrl-combo accelerators
together in the same menu item, so there's one command surface. `Alt`,
`Alt+letter`, and `F10` all open/navigate the menu the normal Windows way;
arrow keys move across top-level menus; NVDA reads it like any native app menu.

### Menu bar + shortcuts

| Menu | Item | Shortcut | Notes |
|------|------|----------|-------|
| File | Open Image File… | `Ctrl+O` | |
| File | Open Recent ▸ … | `Alt`+digit | submenu of recent images; count set in Preferences (0 hides it) |
| File | Save | `Ctrl+S` | needs a loaded radio |
| File | Save As… | `Ctrl+Shift+S` | needs a loaded radio |
| File | Close Image | — | needs a loaded radio |
| File | Import from File… | — | needs a loaded radio |
| File | Export to CSV… | — | needs a loaded radio |
| File | Preferences… | — | |
| File | Exit | `Ctrl+Q` | |
| Edit | Undo | `Ctrl+Z` | needs a loaded radio; reverses the last channel op (announces "Nothing to undo" when empty) |
| Edit | Redo | `Ctrl+Y` (or `Ctrl+Shift+Z`) | needs a loaded radio; replays the last undone op |
| Edit | Select All Channels | `Ctrl+A` | needs a loaded radio |
| Edit | Clear Selection | — | needs a loaded radio |
| Edit | Copy | `Ctrl+C` | needs a loaded radio; copies the selected channel(s) |
| Edit | Cut | `Ctrl+X` | needs a loaded radio; deferred — moves on paste |
| Edit | Paste | `Ctrl+V` | needs a loaded radio; pastes at the focused channel |
| Radio | Download from Radio | `Ctrl+Shift+D` | model list has a **Show: All radios / Favorites** toggle (default All) and a **Radio details…** button |
| Radio | Upload to Radio | `Ctrl+Shift+U` | needs a loaded radio |
| Radio | Favorite radios… | — | manage starred radios (no loaded radio needed); used by Download's Favorites toggle; has a **Radio details…** button |
| Radio | Radio Info… | — | needs a loaded radio; opens a read-only, navigable, copyable edit box |
| Radio | Query Source ▸ … | — | needs a loaded radio; one item per registered source |
| Radio | Settings… | `Ctrl+Shift+P` | needs a loaded radio |
| Channels | Edit channel… | `Ctrl+E` | needs a loaded radio; all fields (also `Enter` / double-click on the grid) |
| Channels | Edit cell… | `F2` | needs a loaded radio; edits the focused cell (the column at the Left/Right cursor) |
| Channels | Delete channel(s) | `Del` | needs a loaded radio; clears the selected channel(s) |
| Channels | Go to channel… | `Ctrl+G` | needs a loaded radio; prompt for a number, then select + focus it |
| Channels | Channel banks… | `Ctrl+B` | needs a loaded radio |
| Channels | Move up | `Ctrl+Shift+Up` | needs a loaded radio |
| Channels | Move down | `Ctrl+Shift+Down` | needs a loaded radio |
| Channels | Move to channel… | `Ctrl+Shift+M` | needs a loaded radio |
| Channels | Bulk operations… | `Ctrl+M` | needs a loaded radio; delete/delete+shift/insert/move/copy/sort/arrange over a range or list |
| Channels | Find… | `Ctrl+F` | needs a loaded radio |
| Channels | Find next | `F3` | needs a loaded radio |
| Help | Keyboard Shortcuts | `F1` | shows this list as a plain-text message box |
| Help | About | — | |

Items marked "needs a loaded radio" are disabled until an image is open. F1's
on-screen list (`APP_SHORTCUTS` in `vrp/native/main_window.py`) is kept in
sync with this table by hand — update both when adding a command.

**File ▸ Open Recent** lists the most-recently opened images (newest first),
each labelled with an `Alt`+digit mnemonic (`&1`…`&9`) inside the submenu and
its full path in the status-bar help (the parent folder is appended only when
two basenames collide); a final **Clear Recently Opened** empties the list.
How many to show is set by **File ▸ Preferences ▸ Recently opened files to
show** (a 0–9 chooser): **0 removes the submenu entirely**, 1–9 shows that
many. Recent entries are menu-only (no Ctrl shortcut); a file that no longer
exists is announced and dropped from the list when chosen.

## Channel grid navigation and selection

The grid is a multi-select `wx.dataview.DataViewListCtrl`, provided by
`wx-accessible-grid`'s `AccessibleGrid` (`vrp/native/channel_grid.py`), with
every channel populated at once — no paging. It is a real native table on each
platform (the native list view on Windows, NSTableView on macOS), so NVDA and
VoiceOver both read its rows. On macOS VoiceOver also reads across a row's cells
by column natively (`VO`+`Left`/`Right`); on Windows the native list announces
no per-cell cursor, so VRP adds an app-level `Left`/`Right` cell cursor that
speaks `"<value>, <column>"` through its supplemental (prism) speech.

| Key | Action |
|-----|--------|
| `Up` / `Down` | Move focus a row at a time (the screen reader reads the row); selection follows |
| `Ctrl+Up` / `Ctrl+Down` | Move the focus cursor to the prev/next row **without changing the selection** (native; NVDA still reads the row) |
| `Left` / `Right` | Move a cell cursor across the row's columns. **Windows:** VRP speaks `"<value>, <column>"`. **macOS:** use VoiceOver's own `VO`+`Left`/`Right`, which reads cells natively |
| `Space` / `Ctrl+Space` | Toggle the focused row in/out of the selection (announces "Selected/Deselected channel N, K selected") |
| `Shift+Up` / `Shift+Down` | Extend a contiguous selection |
| `Ctrl+A` | Select all channels |
| `Ctrl+C` / `Ctrl+X` / `Ctrl+V` | Copy / Cut (deferred — moves on paste) / Paste the selected channel(s) at the focused channel |
| `Ctrl+Z` / `Ctrl+Y` | Undo / Redo the last channel operation |
| `Ctrl+E` / `Enter` | Edit the focused channel — **all** fields (full dialog) |
| `F2` | Edit the **focused cell** in a single-field dialog — the column at the Left/Right cursor (Windows and macOS). The row-header or a read-only column falls back to the full dialog. On platforms without the cell cursor (GTK), F2 first asks which field via a picker, then edits it |
| `Del` | Delete the selected channel(s) (Channels-menu accelerator) |
| `Applications` key / `Shift+F10` | Open the row context menu (Edit channel / Edit cell / Delete / Copy / Cut / Paste / Move up/down / Move to / Bulk operations / Go to / Banks). The generic Windows DataViewCtrl raises this for the Applications key and a right-click natively; VRP wires `Shift+F10` itself (`ChannelGrid._on_grid_key`) since the control doesn't |

## Reorganizing channels

Select one channel, or a group: `Shift+Arrow` extends a contiguous block;
`Space`/`Ctrl+Space` toggles individual rows for a non-contiguous set (use
`Ctrl+Arrow` to move the cursor between rows without disturbing the selection).
Then:

| Key | Action |
|-----|--------|
| `Ctrl+Z` / `Ctrl+Y` | Undo / Redo the last channel operation |
| `Ctrl+C` / `Ctrl+X` / `Ctrl+V` | Copy / Cut / Paste the selected channel(s) |
| `Ctrl+Shift+Up` | Move the selected channel(s) up one slot |
| `Ctrl+Shift+Down` | Move the selected channel(s) down one slot |
| `Ctrl+Shift+M` | Move the selected channel(s) to a chosen channel |
| `Ctrl+M` | Bulk operations (delete/copy/sort/insert/arrange) dialog |
| `Ctrl+G` | Go to channel |
| `Ctrl+F` / `F3` | Find / Find next |
| `Ctrl+B` | Channel banks for the focused channel |

After a move, the moved block stays selected at its new position and focus
lands on its first channel; the result is announced via the status bar and
speech.

**Cut / copy / paste** work on whole rows with an in-app clipboard (current
image only). `Ctrl+C` snapshots the selected channel(s); `Ctrl+X` marks them
(deferred — nothing changes until you paste, which then *moves* them and clears
the clipboard); `Ctrl+V` pastes at the focused channel. Paste **overwrites** the
destination, but when the destination is occupied a dialog offers **Overwrite**,
**Make room** (shift the existing channels down to insert — blocked if there
aren't enough empty slots near the end), or **Cancel**. The radio's channel
count is fixed, so nothing is ever added or pushed off the end.

**Undo / redo** cover every channel operation — edit, delete, move, copy,
cut/paste, sort, insert, arrange, import. `Ctrl+Z` undoes the last one and
announces what it reversed (e.g. "Undone: Deleted channel 5"); `Ctrl+Y` (or
`Ctrl+Shift+Z`) redoes it. The Edit menu's Undo/Redo items show the operation
they'd act on; the history is bounded (most-recent ops) and cleared when you
load, close, or download an image. Radio Settings and bank assignments are not
yet undoable.

## Dialogs

Editing, bulk operations, find, settings, banks, and download/upload all open
native wx dialogs. Across all of them: `Tab`/`Shift+Tab` move between fields,
`Enter` is OK (validate + save + close), `Esc`/Cancel discards, and on invalid
input the dialog stays open, speaks the reason, and focuses the bad field.
Per-dialog detail is below under "Dialogs (detail)".

In the **Edit channel** dialog, changing the **Frequency** auto-fills a blank
**Offset** field with the band's standard repeater shift from CHIRP's band plan
(e.g. 146.94 → 0.6 MHz, 442.5 → 5 MHz) and announces it ("Suggested offset 0.6
MHz — set Duplex to plus or minus to use it."). The single-cell **Edit cell**
editor (`F2` on the Offset cell) does the same on open, using the channel's own
frequency, with the value pre-selected so Enter accepts it. Only the *magnitude*
is filled — you choose the `+`/`-` **Duplex** direction; an offset you've already
set is never overwritten. The band plan is chosen in **File ▸ Preferences ▸ Band
plan (region)**.

**Empty channels expose ALL fields** in the edit dialog (so a new channel can be
fully defined in one pass) with focus on Frequency (which carries a "required to
activate" hint); immutable fields are disabled and labeled "(read only)".

## Dialogs (detail)

### Bulk operations (move/delete/etc.)

`Ctrl+M` (or Channels ▸ Bulk operations…) opens a native wx dialog. There are no
per-row checkboxes. Selection is a contiguous From/To range by default, with an
optional advanced field that takes a channel list like `1-5,8,10-12`. Pick one
operation: Delete, Delete and shift up, Insert blank, Move up/down, Move to…,
Copy to…, Sort…, Arrange (compact). Only the chosen operation's parameters show
(shift mode, destination, sort column/order). Destructive/reordering ops show a
native confirm dialog stating the range and count. After an op the grid
refreshes, focus lands on the result channel, and the result is announced.

### Find

`Ctrl+F` (or Channels ▸ Find) opens a native dialog: a text field + a "Search
in" chooser (All fields / Name / Frequency / Comment). It jumps to the first
matching channel (focusing its row in the grid) and announces the match.
`F3`/`Ctrl+G` (Find next) steps to the next match; the search wraps, announcing
"Wrapped to start" or "Only match" as appropriate. No match keeps the dialog
open and speaks "not found"; an empty search field is rejected.

### Download / Upload

Radio ▸ Download from Radio (`Ctrl+Shift+D`) opens a native dialog: a serial-port
chooser (with Refresh and an explicit "no ports" state) and a model picker that
is a filter field + type-ahead list (type to narrow ~550 models by substring),
plus a **Show: All radios / Favorites** toggle and a **Radio details…** button.
Upload (`Ctrl+Shift+U`) needs only a port and shows a confirm ("overwrite ALL
channels…", default Cancel). The transfer runs on a background thread; progress
is announced (throttled), with a gauge for sighted users. Download can be
cancelled (result discarded); upload cannot (a half-written radio is worse). On
download success the grid refreshes and focus moves to the first channel.

### Favorite radios

Radio ▸ Favorite radios… opens a dual-list manager (no loaded radio needed):
left = all radios with a filter + **Add to favorites**; right = **Your
favorites** + **Remove from favorites**; Close. Favorites are stored as CHIRP
driver ids and drive the Download dialog's Favorites toggle. A **Radio details…**
button shows the highlighted model's specs in a read-only edit box. Escape
closes.

### Preferences & Open Recent

Settings persist in a JSON file under the user config dir (atomic writes;
corrupt/missing falls back to defaults). File ▸ Preferences… (a native dialog)
has **Recently opened files to show** (0–9; 0 hides the Open Recent submenu),
**Band plan (region)** (North America / Australia / IARU R1–R2–R3; picks which
CHIRP band plan supplies the editor's suggested repeater offsets), **Apply
band-plan defaults** (off by default; when on, entering a frequency also fills
mode/tuning step/tone from the band plan — the offset is suggested regardless,
and the +/- duplex direction is always left to you), and **Speak status messages
aloud** (off by default; gates the *supplemental* prism speech — the screen
reader always reads the status bar regardless). Recent entries are menu-only (no
Ctrl shortcuts); a recent entry that's gone is announced and pruned.

### Import / Export / Radio Info

File ▸ Import from File… picks another radio image (native file dialog), loads
it as an independent source (the active radio is untouched), then reuses the
import-destination dialog + import op (adapts each memory via CHIRP import_logic,
overwrite/skip, announces counts, focuses the first imported channel). File ▸
Export to CSV… writes the loaded radio's non-empty channels to a CSV via CHIRP's
generic_csv driver (native save dialog with overwrite prompt; announces count +
file). Radio ▸ Radio Info… shows the loaded radio's specs in a read-only,
navigable, copyable edit box (`vrp/info_dialog.py`). All three are menu-only (no
Ctrl shortcut) and disabled until a radio is loaded. Native printing is
intentionally not implemented — Export to CSV is the accessible equivalent.

### Query sources

Radio ▸ Query Source ▸ (a source) opens a native param dialog (with the source's
attribution + a descriptive Terms-of-Service link), then fetches on a background
thread with the shared progress dialog (status announced). On success it
announces the result count and opens an import dialog: a destination channel
(defaults to the first empty channel) + Overwrite/Skip for occupied channels.
Import adapts each memory for the target radio (CHIRP import_logic) and announces
the counts. Reached via the menu (Alt → R → Q → source); no Ctrl shortcut (too
many sources). Disabled until a radio is loaded. Wired now: AMSAT, SatNOGS,
DMR-MARC (city/state/country) and mapy73.pl (network choice). Still deferred:
RepeaterBook (dynamic country→state cascade), RadioReference (credentials/login),
and przemienniki.net/.eu (band/mode code mapping + coordinates).

### Banks

Channels ▸ Channel banks… (`Ctrl+B`) prompts for a channel, then opens a native
dialog to assign it to banks: a CheckBox per bank for radios that allow multiple
banks per memory, or a RadioBox ("None" + banks) for zero-or-one radios;
fixed-bank radios show the membership read-only. An intro line states current
membership in words. OK applies the add/remove diff and announces the new
membership; failures are reported truthfully. Only enabled on bank-capable
radios (the menu item is disabled / `Ctrl+B` announces "no banks" otherwise).
Bank renaming and a "channels in a bank" overview are deferred. NVDA pass owed.

### Radio settings

Radio ▸ Settings… (`Ctrl+Shift+P`) opens a native dialog with a `wx.Treebook`:
the tree lists the radio's top-level setting groups; each page is a scrolled
panel of labelled controls (CheckBox / Choice / SpinCtrl / TextCtrl by value
type). Nested sub-groups are flattened into their page under an indented bold
heading. Read-only settings are disabled and labelled "(read only)". OK validates
every value (keeps the dialog open, reveals the offending group's page, focuses
the field, and speaks the reason on failure), then writes all changes via
`set_settings`; Cancel/Escape discards. Initial focus lands on the tree. NVDA
pass owed.
