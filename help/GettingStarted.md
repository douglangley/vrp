# Versatile Radio Programmer (VRP) — Getting Started

## Announcing a new radio programmer

**VRP — the Versatile Radio Programmer** — programs over 550 radios, and it is
built to be used by a screen reader user entirely from the keyboard.

- Available for **Windows** and **macOS**.
- Tested on Windows with **NVDA**, **JAWS**, and **Narrator**, and on macOS with
  **VoiceOver**.
- Built on the **CHIRP** radio programming project.

CHIRP has long been difficult for blind and visually impaired people to use. So
VRP takes a different approach: it uses CHIRP's back end for the radio drivers
and the radio communications, but the **entire user interface has been rebuilt
from scratch** to work with screen readers on both Windows and macOS.

This is very much a first version. We have had a small group of testers so far,
so you will probably find bugs. We are open to any and all suggestions, and we
will do our best to fix problems as they get reported.

### With thanks to the CHIRP project

VRP is an accessible front end that takes advantage of the open source CHIRP
radio programming software, found at **chirpmyradio.com** and
**github.com/kk7ds/chirp**. We would like to thank them, and to acknowledge that
this software would not be possible without their hard work.

Every radio VRP can talk to, it talks to through a driver that a CHIRP volunteer
wrote, tested, and still maintains — most of them worked out by taking a radio's
protocol apart by hand, without any help from the manufacturer. That is years of
patient work by a lot of people, given away freely, and it is the foundation this
program stands on. It keeps paying off, too: when CHIRP adds a radio or fixes a
driver, VRP picks that up and ships it in a new release.

VRP is released under the **GPL v3** — the same licence CHIRP uses. The terms
that let us build on their work are the terms we pass on to you.

## About the keys in this guide

Windows and macOS use different modifier keys for the same commands:

- On **Windows**, menu commands use **Ctrl** (for example, Ctrl+S to save).
- On **macOS**, the same commands use **Command** (for example, Command+S).

Everything else — the arrow keys, Space, Tab, Enter, Escape, and the function
keys — is the same on both platforms. Where a key genuinely differs, it is
called out.

**Press F1 at any time** to hear the full list of shortcuts read out of the app
itself. The **Help** menu also has **Getting Started** (this guide) and
**Keyboard Commands** (the full reference), which open in your browser.

## Downloading from your radio

1. Plug your radio data cable into a USB port on the computer, and into the
   connector on the radio.
2. Start VRP.
3. Go to the **Radio** menu and choose **Download from Radio**
   (Windows: Ctrl+Shift+D — macOS: Command+Shift+D).
4. Select the **COM port** (on macOS, the **serial port**) that the radio is
   connected to.
5. Select your radio model from the list.
6. **Tab** to the **Download** button and press it to transfer the data from the
   radio.

### Finding the right port

A computer often has internal ports of its own, so you may need to try more than
one. A valid port for a radio cable usually has a name containing one of these:

- **CH340**
- **FTDI**
- **PL2303**
- **USB com** followed by a number

On macOS, look for a port whose name starts with `/dev/cu.usbserial` or
`/dev/cu.SLAB_USBtoUART`.

### Finding your radio in the list

The model list holds around 550 radios, so it has a **filter field**: just start
typing part of the model name and the list narrows as you type. Two things make
it easier to live with:

- **Show: All radios / Favorites** — flip the list to just your starred radios.
  You manage that list from **Radio ▸ Favorite radios…**.
- **Radio details…** — reports the highlighted model's specs (bands, channel
  count, features) before you commit to it.

The transfer runs in the background and announces its progress as it goes. A
download can be cancelled; an **upload cannot**, because a half-written radio is
worse than no radio.

## Editing the memory channels

Once you have downloaded from your radio, you land in the channel grid.

| What you want | Windows | macOS |
|---|---|---|
| Move between channels | Up / Down | Up / Down |
| Move between the fields of a channel | Left / Right | Left / Right |
| Edit the **one field** you are sitting on | F2 | F2 |
| Edit the **whole channel** in one dialog | Enter, or Ctrl+E | Enter, or Command+E |
| Go straight to a channel number | Ctrl+G | Command+G |
| Find a channel | Ctrl+F | Command+F |
| Find the next match | F3 | F3 |
| Delete the selected channel(s) | Del | Fn+Delete, or the Channels menu |
| Undo | Ctrl+Z | Command+Z |
| Redo | Ctrl+Y, or Ctrl+Shift+Z | Command+Y, or Command+Shift+Z |
| Open the menu for the current row | Applications key, or Shift+F10 | Use the menu bar |

**Left and Right** move a cell cursor across the row and speak the value and the
column name as you go — "146.940, Frequency". This works on both Windows and
macOS. VoiceOver users on macOS can also use VO+Left / VO+Right, which reads the
same cells natively.

**F2 edits the cell you arrowed to**, in a small single-field dialog. **Enter**
(or Ctrl+E / Command+E) is different: it opens the **whole channel** in one
friendly dialog you move through with **Tab** and **Shift+Tab**. That full
dialog is usually the easier way to set up a channel from scratch — an empty
channel exposes every field in it, so you can define the channel in one pass.

Every dialog in VRP works the same way: **Tab** and **Shift+Tab** move between
fields, **Enter** accepts, and **Escape** cancels. If something you typed is not
valid, the dialog stays open, tells you why, and puts you on the field that
needs fixing.

### The row context menu

Once you are on a channel — or have selected several — press **Shift+F10** or the
**Applications key** to open a menu of everything you can do to that row, without
going to the menu bar for it. It is an ordinary menu: your screen reader reads it,
you arrow through it, and Escape closes it. (macOS has no context-menu key, so use
the menu bar there — the same commands live in the Channels and Edit menus.)

The menu is built fresh each time you open it, so it describes exactly what you
are sitting on. Items name the channel when one is selected ("Delete channel 5")
and the selection when several are ("Delete selected channels"). What you get:

| Item | Key | Notes |
|---|---|---|
| **Undo** / **Redo** | Ctrl+Z / Ctrl+Y | Named for the operation they reverse or replay — "Undo Deleted channel 5". Greyed out when there is nothing to undo or redo. |
| **Edit channel N** | Ctrl+E | The whole channel in one dialog. |
| **Edit cell — <column>** | F2 | Names the column your cell cursor is on: "Edit cell — Frequency". Left out when the cursor is on the channel number, or on a field this radio will not let you change. |
| **Delete channel N** / **Delete selected channels** | Del | Asks you to confirm first. |
| **Copy** / **Cut** | Ctrl+C / Ctrl+X | |
| **Paste N channel(s) here** | Ctrl+V | Tells you how many are on the clipboard. Greyed out while the clipboard is empty. |
| **Export … to CSV…** | | The focused channel, or the whole selection. |
| **Move up** / **Move down** | Ctrl+Shift+Up / Down | |
| **Move to channel…** | Ctrl+Shift+M | |
| **Sort N selected channels by** | | A submenu — Name, Receive frequency, Transmit frequency. Only appears with two or more channels selected. |
| **Bulk operations…** | | |
| **Go to channel…** | Ctrl+G | |
| **Channel banks…** | | On radios that have banks. |

The menu only opens when a radio image is loaded — there is nothing to act on
before that.

### A helping hand with offsets

When you type a **frequency** into the edit dialog, VRP fills in the standard
repeater **offset** for that band from CHIRP's band plan and tells you so — for
example, 146.94 gives you 0.6 MHz, and 442.5 gives you 5 MHz.

It only fills in the **size** of the offset. **You still choose the plus or
minus direction** in the Duplex field, and an offset you have already set is
never overwritten. Which band plan it uses is set in **File ▸ Preferences ▸ Band
plan (region)**.

## Selecting channels

| What you want | Windows | macOS |
|---|---|---|
| Select a run of channels | Shift+Up / Shift+Down | Shift+Up / Shift+Down |
| Select or deselect the current channel | Space (or Ctrl+Space) | Space |
| Move the cursor **without** changing the selection | Ctrl+Up / Ctrl+Down | Use VoiceOver navigation |
| Select all channels | Ctrl+A | Command+A |

To pick out **scattered, non-consecutive channels**: move to a channel you want
and press **Space** to select it. To get to the next one without losing what you
have already selected, hold **Ctrl** while you arrow (on macOS, use VoiceOver's
own navigation, since Ctrl+Up is Mission Control there). Press **Space** again on
each channel you want. VRP announces each one — "Selected channel 12, 3
selected" — so you always know where you stand.

## Moving channels around

The direct way, once you have a channel or a group selected:

| What you want | Windows | macOS |
|---|---|---|
| Move up one slot | Ctrl+Shift+Up | Command+Shift+Up |
| Move down one slot | Ctrl+Shift+Down | Command+Shift+Down |
| Move to a specific channel | Ctrl+Shift+M | Command+Shift+M |

The cut-and-paste way, which also works across scattered selections:

1. Select the channel or channels you want.
2. Press **Ctrl+X** (macOS: Command+X) to cut them.
3. Move to the destination channel.
4. Press **Ctrl+V** (macOS: Command+V) to paste.

**Ctrl+C / Command+C** copies instead of moving. Cut is *deferred* — nothing
actually changes until you paste. If the same image and memory section are
still active, the paste moves the channels and clears the originals. If you
open or download another radio, or switch to another side or zone first, VRP
converts each channel for that destination and leaves the original section
unchanged; the Cut becomes Copy so you can paste again.

If you paste onto a channel that is **already occupied**, VRP does not silently
clobber it. A dialog asks whether you want to **Overwrite** it, **Make room**
(shift the existing channels down to insert yours), or **Cancel** within one
image. Across radio images the choices are **Overwrite**, **Skip**, or
**Cancel**. Any incompatible channels are skipped individually, and a
navigable, copyable details window explains why; compatible channels still
paste.

Cross-radio bulk migration covers regular numbered channels. **File ▸ Import
from File** can also transfer one explicitly selected regular or special memory
to a numbered channel or named special on the destination. It never silently
includes call channels, scan limits, VFOs, home channels, or other specials in
a bulk import. A same-name target is only preselected for you to confirm, and
an occupied special asks separately before overwrite. Radio-wide settings and
bank membership are not copied. When an image has multiple sides, VFOs, bands,
or zones, Open and Import show a filterable **Memory section** chooser. **Radio
▸ Select memory section…** switches the grid later; Save and Upload still
include the complete radio image.

After any move, the moved channels stay selected at their new home, focus lands
on the first of them, and the result is announced.

Everything here is undoable — **Ctrl+Z / Command+Z** — and VRP tells you what it
reversed ("Undone: Deleted channel 5").

## Doing a lot at once

**Ctrl+M** (macOS: Command+M) opens **Bulk operations**, for when you want to
work on a range rather than one channel at a time. Pick a From/To range (or type
a list like `1-5,8,10-12` in the advanced field), then choose one operation:
delete, delete and shift up, insert blank, move, copy, **sort**, arrange
(compact out the gaps), or export to CSV. Anything destructive asks you to
confirm first, stating the range and the count.

**Sorting** is worth knowing about: you can sort a selection by Name, Receive
frequency, or Transmit frequency. The row context menu (Applications key or
Shift+F10 on Windows) has a quick **Sort selected channels by** submenu when you
have two or more channels selected.

## Saving and uploading

- **Save**: **File ▸ Save** — Ctrl+S (macOS: Command+S). **Save As** is
  Ctrl+Shift+S (macOS: Command+Shift+S).
- **Upload to the radio**: **Radio ▸ Upload to Radio** — Ctrl+Shift+U (macOS:
  Command+Shift+U). It confirms first, because it overwrites **all** the
  channels in the radio.
- **Open a saved image later**: **File ▸ Open Image File** — Ctrl+O (macOS:
  Command+O). Recently opened files are listed under **File ▸ Open Recent**.

VRP will not let you lose work by accident. If you try to exit, close, open
another image, or download from a radio while you have unsaved channel edits, it
stops and asks: **Save**, **Don't save**, or **Cancel**.

## Worth exploring next

- **Radio ▸ Settings** (Ctrl+Shift+P / Command+Shift+P) — the radio's own
  settings, laid out as a navigable tree of labelled controls.
- **Radio ▸ Select memory section…** — on a multi-side or multi-zone radio,
  choose which section the channel grid shows. Open, Import, and Download also
  offer this chooser when needed.
- **Channels ▸ Channel banks** (Ctrl+B / Command+B) — assign a channel to the
  radio's banks, on radios that have them.
- **Radio ▸ Query Source ▸ RepeaterBook** — look up repeaters by country and
  state, filter by band and mode, then pick the ones you want with Space and
  import them straight into your radio.
- **Radio ▸ Query Source ▸ Frequency lists** — import one of CHIRP's ready-made
  lists (NOAA weather, FRS/GMRS, MURS, Marine VHF, aviation, railroad, PMR, and
  more). No internet needed.
- **File ▸ Import from File** and **File ▸ Export to CSV** — move channels
  directly between images, import a CHIRP CSV, or send someone just the part of
  your memories they asked for.
  Import and cross-image Paste use the same CHIRP conversion and compatibility
  report. If either radio has named special memories, Import lets you choose
  ordinary bulk migration or explicitly map one regular/special memory.
  (There is no print command; Export to CSV is the accessible equivalent.)
- **File ▸ Preferences** — how many recent files to show, which band plan region
  to use, whether entering a frequency should also fill in mode/step/tone, and
  whether VRP speaks status messages aloud on top of your screen reader.
- **Radio ▸ Radio Info** — everything VRP knows about the loaded radio, in a
  read-only box you can arrow through and copy from.

## Full keyboard reference

| Command | Windows | macOS |
|---|---|---|
| Show the keyboard shortcuts | F1 | F1 |
| Open image file | Ctrl+O | Command+O |
| Save | Ctrl+S | Command+S |
| Save as | Ctrl+Shift+S | Command+Shift+S |
| Exit | Ctrl+Q | Command+Q |
| Download from radio | Ctrl+Shift+D | Command+Shift+D |
| Upload to radio | Ctrl+Shift+U | Command+Shift+U |
| Radio settings | Ctrl+Shift+P | Command+Shift+P |
| Edit the focused channel (all fields) | Ctrl+E, or Enter | Command+E, or Enter |
| Edit the focused cell | F2 | F2 |
| Delete the selected channel(s) | Del | Fn+Delete |
| Undo | Ctrl+Z | Command+Z |
| Redo | Ctrl+Y, or Ctrl+Shift+Z | Command+Y, or Command+Shift+Z |
| Select or deselect the focused channel | Space, or Ctrl+Space | Space |
| Move the cursor without changing the selection | Ctrl+Up / Ctrl+Down | VoiceOver navigation |
| Extend the selection | Shift+Up / Shift+Down | Shift+Up / Shift+Down |
| Select all channels | Ctrl+A | Command+A |
| Copy | Ctrl+C | Command+C |
| Cut | Ctrl+X | Command+X |
| Paste at the focused channel | Ctrl+V | Command+V |
| Go to channel | Ctrl+G | Command+G |
| Channel banks | Ctrl+B | Command+B |
| Move selected channel(s) up | Ctrl+Shift+Up | Command+Shift+Up |
| Move selected channel(s) down | Ctrl+Shift+Down | Command+Shift+Down |
| Move selected channel(s) to a chosen slot | Ctrl+Shift+M | Command+Shift+M |
| Bulk operations | Ctrl+M | Command+M |
| Find a channel | Ctrl+F | Command+F |
| Find next match | F3 | F3 |
| Row context menu | Applications key, or Shift+F10 | Use the menu bar |

## Reporting bugs

We expect you to find things. When you report a bug, it helps enormously to
include:

- Your **radio model** and the **cable** you are using.
- Your **operating system** and **screen reader**.
- The **VRP version**, which is in **Help ▸ About** — it reads it out as
  something like "Release 3 of 15 July 2026".
- What you did, what you heard, and what you expected to hear.

---

*Radio driver support provided by the CHIRP project — chirpmyradio.com.*
