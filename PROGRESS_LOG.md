# Versatile Radio Programmer — Progress Log

A dated, append-only record of work so development can continue in phases
across sessions. Newest entries at the top. See `docs/` for the phase plan,
architecture, keyboard map, and CHIRP feature-coverage checklist.

---

## 2026-06-24 — Fix: Download dialog model search broke on punctuation

The Download-from-Radio model filter did a raw case-folded substring match
against the driver label, so typing `uv5r` matched **nothing** and `UV5`
matched only 2 unrelated models (`Baojie BJ-UV55`, `Ruyage UV58Plus`) — because
the real labels carry a hyphen (`Baofeng UV-5R`). New `filter_models()` in
`vrp/serial_dialogs.py` normalizes both the query and each label (lowercase +
strip non-alphanumerics) and treats whitespace as multiple required terms, so
`uv5r` now matches `Baofeng UV-5R` / `UV-5R Mini` / `UV-5RH` / … and
`baofeng 5r` matches any Baofeng whose model contains `5r`. Extracted as a pure
function and unit-tested, including a regression against the real CHIRP labels.
114 passing.

## 2026-06-24 — Remove build.bat (run-from-source only) + rename config dir to VRP

**Removed `build.bat`.** A tester ran the old double-click `build.bat` (which
packages an .exe) instead of running from source, and got a stale/confusing
result. Everyone now runs from source via `run-win.bat` / `run-mac.sh`;
building a release .exe stays available but is a deliberate developer step
(`uv sync --extra build` + `uv run python build.py`), not a double-click
wrapper. Updated the references that pointed at `build.bat` (README, CLAUDE.md,
`tools/update_chirp.py`) to the `build.py` invocation. `build.py` itself is
unchanged.

**Renamed the user config directory `OpenMemoryWriter` → `VRP`.** The config
dir still carried the project's pre-rename name (`%APPDATA%\OpenMemoryWriter\`
/ `~/.config/OpenMemoryWriter/`), leaking it via `config.json`. `vrp/config.py`
now uses `VRP`, with a one-time best-effort migration: on first run, if the new
`VRP/config.json` doesn't exist but a legacy `OpenMemoryWriter/config.json`
does, it's copied forward, so existing testers keep their preferences and
recent files. Tests cover the new path, the migration, and that an existing
new config is never overwritten by the legacy one. (`_LEGACY_DIRNAME =
"OpenMemoryWriter"` remains in `config.py` only to drive that migration;
historical PROGRESS_LOG entries that mention the old name are left intact as an
accurate record.)

Suite: 108 passing.

## 2026-06-23 — Fix: port picker's default selection could land on the wrong COM port

**Symptom.** A real-hardware **upload** attempt (Task 7e, the owed test from the
entry below) produced `serial-trace.txt` showing VRP open **COM10** and send the
exact, correct CHIRP ident magic for the Baofeng UV-5R Mini
(`PROGRAMCOLORPROU` / `chirp.drivers.baofeng_uv17Pro.MSTRING_UV17PROGPS`, at
115200 baud — matches `UV17Pro.BAUD_RATE` exactly, so the bytes on the wire
were not the bug). The reply was a single byte `0x50` (`'P'`) — the first byte
of what was just sent, echoed back — instead of the expected `0x06` ACK
(`_fingerprint`). `_do_ident()` correctly raised
`RadioError("Unexpected response from radio")`. The prior verified download
(see entry below) had used **COM4**, not COM10.

**Root cause.** `chirp_backend/radio.py::list_serial_ports()` sorted ports
with plain string comparison: `sorted(ports, key=lambda p: p.device)`. Python
string order is character-by-character, so `'COM10' < 'COM4'` (`'1' < '4'`) —
confirmed interactively: `sorted(['COM4','COM10','COM2','COM9'])` →
`['COM10','COM2','COM4','COM9']`. `vrp/serial_dialogs.py::PortPicker.refresh()`
always pre-selects index 0 of that list. On any machine with both a
single- and a double-digit port enumerated (COM10+ shows up easily —
Bluetooth virtual ports, FTDI hubs, a second adapter), the dialog's *default*
selection silently lands on whichever port string-sorts first, not the
radio's actual port. Nothing in the code names a specific port — the bug is
in the ordering, not a hardcoded value — but an unreliable default made the
wrong port the path of least resistance, which is almost certainly what put
this upload attempt on COM10.

**Fix.** Added `_natural_sort_key()` to `chirp_backend/radio.py` (splits each
device string into text/digit runs via regex, compares digit runs as `int`)
and used it as `list_serial_ports()`'s sort key. Ports now order
`COM2, COM4, COM9, COM10, ...`. The key isn't COM-specific, so it also fixes
the equivalent problem on Linux (`/dev/ttyUSB2` vs `/dev/ttyUSB10`, etc.).
Test: `tests/test_serial_ports_list.py::test_list_serial_ports_sorts_numerically`
(fakes `serial.tools.list_ports.comports()` with COM10/COM2/COM4/COM9 and
asserts numeric output order). Full suite: 104 passed.

**Not yet independently re-verified against real hardware** (no hardware
access here) — flagging for whoever next attempts Task 7e (upload, still
owed): confirm the port dropdown now defaults sensibly when more than one
serial device is enumerated, and separately confirm upload itself completes
once the right port is selected (this fix only changes which port is
*pre-selected by default*; the dropdown was always manually overridable, so
this would not by itself have blocked anyone who explicitly chose COM4).

## 2026-06-23 — Serial clone hardening + real-hardware download VERIFIED

Phase 4's download/upload had never run against a real radio (no hardware in
prior sessions). With a radio now available, reviewed the serial backend
against CHIRP's own clone code (`chirp/wxui/clone.py`, `chirp_common.py`),
fixed the gaps, and verified a real download. Work tracked in
`docs/superpowers/plans/2026-06-23-serial-hardware-verification.md`; master
list in `docs/superpowers/plans/ROADMAP.md` (new).

**What was wrong / fixed (`chirp_backend/radio.py` unless noted):**
- **Serial port setup ignored the driver's flow-control prefs.** The old
  `serial.Serial(port, baud, timeout=1)` auto-opened immediately with RTS/DTR
  at pyserial defaults. New `_open_radio_serial()` mirrors CHIRP's
  `open_serial`: construct closed, set baud/`timeout=0.25`/`rtscts`=
  HARDWARE_FLOW/`rts`=WANTS_RTS/`dtr`=WANTS_DTR, then assign port and open.
- **No submodel auto-detection.** `_detect_radio_class()` now calls
  `detect_from_serial()` before `sync_in()` (download): a returned class
  replaces the user's pick, `NotImplementedError` keeps it, `RadioError`
  propagates as a real failure.
- **Driver prompts were never shown.** Many drivers carry required manual
  steps (experimental risk, info, pre-download/upload instructions) via
  `get_prompts()`. Backend `get_clone_prompts*()` flatten them;
  `serial_dialogs.show_radio_prompts()` shows them as native, screen-reader-
  accessible `wx.MessageBox` dialogs before the port opens. Wired into
  `on_download`/`on_upload` (native UI). Upload order (user decision): driver
  prompts first, then VRP's "overwrite ALL channels" confirm.
- **`NameError: name '_' is not defined`** — driver `get_prompts()`/clone
  code calls the gettext builtin `_()`; CHIRP's CLI/GUI install it but VRP
  never did, so `get_clone_prompts()` crashed for real drivers (would have
  broken Download before it started). `_ensure_chirp()` now installs an
  identity `_` builtin (guarded), same shim chirpc uses.
- **Non-clone (live) radios** in the picker now fail with a clear message
  before opening the port (`issubclass(..., CloneModeRadio)` guard), instead
  of a cryptic mid-clone `AttributeError`. (Live-radio support still oos.)
- **Byte-level serial trace** for debugging: `chirp_backend/serial_trace.py`
  `TracingSerial` (ported from CHIRP's `serialtrace`, NOT imported from
  `chirp.wxui`) hex-dumps every byte in/out to `serial-trace.txt` in the CWD
  when `--debug` is set. Gitignored.

**Reviewed and confirmed NOT gaps:** `NEEDS_COMPAT_SERIAL` only affects the
in-memory map representation in `load_mmap`, not the pipe; drivers call
`radio.status_fn(status)` for both directions, so our `status_fn` hook drives
upload progress too (CHIRP's upload dialog sets a differently-named
`_status_fn` — a latent no-op there that doesn't affect us).

**Verified (real hardware):** Baofeng UV-5R Mini
(`chirp.drivers.baofeng_uv17Pro.UV5RMini`, 115200 baud) downloaded over COM4.
The serial trace shows a clean handshake (PROGRAMCOLORPRO → ACK → ident block
reading "5RMINI" → SEND! → ACK), a full sequential memory dump 0x0000–0xa180
(~41 KB) with no mid-stream timeouts, and a clean close — `sync_in()` returned
normally and the grid populated. Tests: 103 passing (mocked-serial unit tests
for port setup, detection branches, prompt flow incl. a real-driver
`get_prompts()` regression, and the trace).

**Follow-up (same day) — `pipe.log` AttributeError on non-`--debug` runs.**
The verified download above was a `--debug` run, which used `TracingSerial`. A
plain `run-win.bat` (no `--debug`) then crashed: `'Serial' object has no
attribute 'log'`. Root cause: CHIRP drivers call `radio.pipe.log(...)` during
sync (8 driver families — CHIRP's GUI *always* wraps the port in its
`SerialTrace`), so the pipe must always expose `.log()`. Our code only used
`TracingSerial` under `--debug` and a plain `serial.Serial` otherwise. Fix:
`_open_radio_serial` now *always* returns a `TracingSerial`; a new
`trace_enabled` flag gates only whether the trace *file* is written (still
`--debug`-only) — `.log()`/write/read are always present and no-op when
tracing is off. Regression tests added (105 passing). Re-ran a `--debug`
download after the fix: still a clean UV-5R Mini dump. Pushed to `main`
(`eb9c602`) and handed to a second tester (different machine, COM10) for
broader confirmation — specifically the no-`--debug` path (the `--debug` trace
can't exercise it, since `--debug` used `TracingSerial` even before the fix)
and a port other than COM4.

**Still owed:** (1) real-hardware **upload** test (write path; same pipe/prompt
machinery, untested `sync_out`); (2) a no-`--debug` download confirmation
(expected from the COM10 tester); (3) models beyond the UV-5R Mini. NVDA pass
on the prompt dialogs is desirable but they're native message boxes.

## 2026-06-21 — Platform-aware UI default + grid 0.4.0 (VoiceOver cell names, Edit menu)

**Regression + root cause.** A morning merge ("Merge native UI to main and make
it the default") flipped `main.py`'s default from the webview UI to the native
`wx.ListCtrl` UI. On macOS/VoiceOver that silently muted the app (the native grid
reads on NVDA/Windows but not VoiceOver). Forensics: every webview file was
byte-identical to the last known-good commit (a055c92); only the launcher default
had changed. See the cross-platform grid split note.

**Fix — platform-aware default (`main.py`).** `parse_mode()` picks the UI by
`sys.platform`: webview on macOS (VoiceOver reads the web grid), native elsewhere
(NVDA reads the `wx.ListCtrl` grid), with `--webview` / `--native` to override.
Entry-point test is now platform-parametrized.

**wx-accessible-grid 0.4.0** (git tag `v0.4.0`, pinned in `pyproject.toml` until
published to PyPI):
- *Accessible name via aria-labelledby.* Each data cell's name = channel + column
  header + value + control type, so VoiceOver speaks the headers and control type
  on every focus move. VoiceOver never receives the VO+arrow, so the runtime's
  live-region announcement can't fire on macOS; the static name is the channel it
  reads. Plain-move echo trimmed so NVDA (same name on focus) doesn't
  double-speak. Validated by a 3-lens accessibility design pass.
- *Context menu reachable under VoiceOver.* `contextmenu` DOM event handled (not
  just the ContextMenu key macOS lacks) so VO+Shift+M / right-click open the
  native row menu where selection lives.
- *Bulk APIs.* `select_all_rows()` / `clear_selection()`; Ctrl+A selects all rows.
- *Contrast.* AA selection colors; selection never conveyed by color alone.

**VRP.** Edit menu (Select All Channels, Clear Selection) wired to the grid bulk
APIs; grid description names the row-menu triggers (Applications key / Shift+F10 /
VoiceOver VO+Shift+M).

**Tried and reverted.** A positive-only per-row "selected" token baked into the
cell name (to read selection state on move) was implemented, then REVERTED:
announcing selection on plain movement is the chatter bug already fixed and it
broke selection for the VoiceOver user. Selection is announced only on the
selection action. (See the memory note.)

**Known limitation (work on later).** Cell-range selection with Shift+arrow does
NOT work under VoiceOver — VoiceOver intercepts the arrow keys before the page
sees them. Row/channel selection works via Space, Ctrl+Space, and the VO+Shift+M
row menu (Select this channel / Select range to here). A VoiceOver-reachable
cell-range command via the context menu is the likely follow-up.

**Verified:** wx-accessible-grid 18 tests; VRP 79 tests; app launches clean on
macOS (webview default). **Still owed (the bar):** a hand pass with VoiceOver on
the Mac and NVDA on Windows before any of this is called done.

**Update (same day) — grid 0.4.1 + command-line open.** Selection feedback and
the grid-enter announcement are now ASSERTIVE, not polite: VoiceOver routinely
drops polite announcements (especially as the grid opens or when a context menu
closes), so "Channel N selected" and the on-open "Channel 1" landing were going
unspoken — which read as "selection doesn't announce" and "it starts mid-list."
Also added `vrp <file>` (and `run(open_path=...)`) to open an image on launch.
VRP now pins grid **v0.4.1**. Note: VoiceOver will not move its own cursor onto a
programmatically focused webview cell, so the grid focuses channel 1 and announces
it assertively rather than being able to force VO's cursor there. Still owed: the
VoiceOver/NVDA hand pass.

## 2026-06-21 — Per-OS run scripts (run-win.bat / run-mac.sh) + dependency refresh

`run.bat` only ever covered Windows; renamed it to **`run-win.bat`** and added
**`run-mac.sh`**, a bash equivalent (checks for `uv`/`git`, clones and pins
`./chirp` from `CHIRP_COMMIT`, runs `uv sync`, then `uv run python main.py
"$@"`). Both scripts now forward extra CLI args (e.g. `--debug`, `--webview`)
to `main.py`. `chmod +x` set on `run-mac.sh`.

Confirmed the existing `uv.lock` already resolves correctly for both
platforms: `prismatoid` carries macOS wheels and marks its `win32more`
dependency `sys_platform == 'win32'` (so it's skipped entirely outside
Windows), and `wxpython`/the `wx-accessible-*` libraries all publish macOS
wheels too — no pyproject.toml changes were needed for cross-platform
resolution. Ran `uv lock --upgrade` to pick up the latest compatible patch
releases (certifi, coverage, pytest, win32more-core); `uv sync --extra dev`
and the full suite (`uv run pytest`, 78 tests) stayed green on Windows
afterward. macOS execution itself is unverified in this session (no macOS
machine available here) — the next macOS session should run `./run-mac.sh`
and the suite there to confirm.

## 2026-06-21 — Native UI merged to main and made the default

The channel grid is now a native virtual report-mode `wx.ListCtrl`
(`vrp/native/channel_grid.py`), driven by a pure data/selection model
(`vrp/native/grid_model.py`) and shown in a new `MainWindow`
(`vrp/native/main_window.py`) with a native `wx.MenuBar`. NVDA on Windows and
VoiceOver on macOS read it directly — no WebView2, no second webview, no JS
bridge for the grid. Announcements go through `vrp/native/announce.py`'s
`Announcer` (status bar + optional prism speech) instead of an ARIA live
region; the native UI's command surface collapses to one (menu items carry
their own accelerators) instead of the webview UI's three (menu bar / in-page
buttons / JS shortcut map), since a real `wx.MenuBar` doesn't have wx #24786's
WebView2-swallows-Alt problem to work around.

The native UI reuses the existing native wx dialogs unchanged (edit, bulk
operations, find, settings, banks, download/upload, preferences) — only the
channel-grid host and the menu/shortcut plumbing are new.

`main.py` now launches the native UI by default; the legacy `AccessibleWebView`
app (`vrp/app.py` + the `wx-accessible-grid` web grid from the entry below)
stays reachable with `--webview` while it is retired. It is not getting new
features going forward — see CLAUDE.md "What This Project Is".

**Verified (macOS):** opens a CHIRP test image, the ListCtrl populates 500
channels across 14 columns with live cell data; full suite (78 tests) green.

**Open / next:**
- NVDA-on-Windows pass for the native UI (menu accelerators, grid
  navigation/selection, dialog focus) — the webview UI's NVDA passes don't
  carry over since there's no webview involved.
- Real-hardware download/upload verification, still owed from earlier phases,
  applies equally to the native UI (same `serial_dialogs.py`).
- Once the native UI is confirmed at parity on every platform it's the
  default for, retire `vrp/app.py`, `vrp/views.py`, `vrp/html.py`,
  `vrp/channel_grid_model.py`, `templates/`, `static/`, and the
  `wx-accessible-webview`/`wx-accessible-menubar`/`wx-accessible-grid`
  dependencies, and remove the `--webview` flag.

**Correction (same day):** launching the native UI unconditionally on every
platform was the bug — see "Platform-aware UI default" above. The webview UI
is not legacy/retiring on macOS; it's that platform's default until the
native grid is proven under VoiceOver.

## 2026-06-20 — Editable channel grid via new wx-accessible-grid library

The read-only-table-plus-edit-dialog model (Phase 2 rework) was the right call at
the time, but the goal all along was a real editable grid. Built it as a reusable
spin-out library, `wx-accessible-grid` (sibling of wx-accessible-webview and
wx-accessible-menubar, at ../wx-accessible-grid), and wired VRP up as its first
consumer.

Why a library, and why it doesn't repeat the old failure: it renders a real
`<table role="grid">` into an AccessibleWebView and drives it with the
**aria-activedescendant** pattern (the table is the one focusable element; the
active cell is the active descendant). That keeps NVDA in focus mode reading only
the focused cell and the headers that changed, instead of re-reading the whole
table on every arrow, which is exactly what killed the earlier in-grid attempt.
Arrow nav, F2/Enter in-cell editing (text/combo/checkbox/slider/stepper), Space
selection, Delete, and a context-menu callback are all in the library.

The accessibility-lead review (4 specialists) was a NO-SHIP on the first cut
(roving tabindex does not reliably trigger NVDA focus mode in WebView2); all three
Criticals and most should-fixes were applied before this landed.

VRP integration:
- `vrp/channel_grid_model.py` — `ChannelGridModel` maps `build_column_defs` to the
  library's columns (number = read-only row header, select = combo, the rest =
  text), reads via `radio_backend.get_memory`, writes via `memory_ops.set_field`
  (so edits validate/normalize through CHIRP and the announced value is
  authoritative), deletes via `delete_range`. Immutable fields and the number
  column are read-only.
- `tools/grid_preview.py` — loads a radio image (a CHIRP test image by default)
  and shows the channels in the grid. `uv run python tools/grid_preview.py`.
- Dependency added to `pyproject.toml` (+ `[tool.uv.sources]` editable path);
  installed editable into the venv.

**Verified (Mac):** loads Baofeng_UV-5R.img (128 channels), every real column
renders with real data, a name edit persists (and the UV-5R's name-length
truncation comes back as the cell's authoritative display — the validate/normalize
round-trip works), an invalid frequency is rejected and the old value kept. VRP's
own suite still green (`uv run pytest` → 63 passed).

**Open / next:**
- **Make-or-break: NVDA on the Windows VM.** Run `uv run python tools/grid_preview.py`
  in the Windows clone with NVDA. Step 1 is the focus-mode gate: Tab into the grid,
  press Down, expect to hear a sibling cell (not a document line / beep). The
  review's full VM test script covers all five editors, selection, delete, paging,
  and edit-failed.
- The existing read-only channels view and the native edit dialog are untouched;
  the grid is a preview/beta path. Once NVDA proves it out, make it the channels
  view and keep the edit dialog as the full-row fallback (good for defining an
  empty channel in one pass). Then sync menu/shortcuts/docs per CLAUDE.md.

---

## 2026-06-18 — FIXED: the actual cause of dead buttons (supersedes the entry below)

The entry below this one found a real, reproducible native crash, but it was
a secondary/rarer issue, not the dominant cause of "nothing happens when I
click". The actual cause, found and fixed in a further follow-up session:

**Root cause:** `_on_webview_loaded` injected `_SHORTCUTS_JS` via
`wx.CallAfter(self.view.run_js, _SHORTCUTS_JS)`, deferred specifically to
avoid a known "nested RunScript inside the native WebView2 loaded callback"
problem (see the original comment, preserved in the fix). `wx.CallAfter`
schedules work on wx's idle-event queue, which — confirmed by direct,
repeatable testing — can still run while nested inside the same native call
stack as the `EVT_WEBVIEW_LOADED` event. It doesn't always surface the
"Unknown runtime error" dialog that motivated the original deferral, but it
silently breaks the `AddScriptMessageHandler` script-message channel for the
rest of the session: `window.vrp` still exists, `postMessage` still exists
and is callable from JS with no error, but `EVT_WEBVIEW_SCRIPT_MESSAGE_RECEIVED`
never fires again in Python — meaning every in-page button, plus every
Ctrl-combo shortcut (which is *literally what `_SHORTCUTS_JS` itself
installs*), goes dead immediately after the page loads. This is a 100%
reproducible, deterministic bug, confirmed by:
- A monkeypatched copy of the real `MainWindow` with `_on_webview_loaded`
  neutralized: bridge worked.
- The same, but replaying the original `wx.CallAfter(...)` logic: bridge
  broke, immediately, every time.
- Swapping just `CallAfter` for `wx.CallLater(50, ...)` (a real OS timer
  instead of an idle-event, landing in a guaranteed fresh top-level
  message-loop iteration): bridge worked, repeatedly, with the real
  `_SHORTCUTS_JS` content, confirmed via 5+ repeated UI-Automation-driven
  button invokes with zero failures.

**Fix applied:** `vrp/app.py`, `_on_webview_loaded` — changed
`wx.CallAfter(self.view.run_js, _SHORTCUTS_JS)` to
`wx.CallLater(50, self.view.run_js, _SHORTCUTS_JS)`. Comment updated in place
to record why `CallAfter` wasn't sufficient.

**Relationship to the native-crash entry below:** that crash (SIGSEGV inside
`wx\_html2.cp311-win_amd64.pyd`) is real and was reproduced independently of
this bug, under heavy UI-Automation-driven repeated invokes specifically —
it's a separate, rarer issue, most likely still an environmental
WebView2-runtime/wxWidgets ABI edge case. It is **not** what most users would
have hit; this `CallAfter`/`CallLater` bug is what made every button and
shortcut appear permanently dead from the first interaction onward, which
matches every symptom in the original bug report below. The previous plan's
WebView2 Fixed-Version-Runtime workaround is no longer needed for the primary
symptom and was not pursued further; the large runtime files downloaded
during that investigation were deleted from the project root.

Also fixed in the same session (unrelated, found during a code audit):
`_import_results` in `vrp/app.py` referenced an undefined name
(`radio_result`) instead of its own `src_radio` parameter — guaranteed
`NameError` on every completed import. Fixed.

`uv run pytest` — 63/63 passing after these changes.

---

## 2026-06-18 — ROOT CAUSE FOUND: native WebView2 crash, not app code (corrects entry below)

The investigation below (same date) chased the wrong cause. Live debugging in
a follow-up session established the real root cause:

- Windows Event Log ("Application Error", source `python.exe`) shows the
  **same crash signature** recurring for hours, predating the menu-bar/
  `EVT_CHAR_HOOK` edits described below entirely (earliest matching entry:
  6/17 7:44 PM): a SIGSEGV/access-violation (`0xc0000005`) inside
  `wx\_html2.cp311-win_amd64.pyd` (wxPython's WebView2 binding), at the
  **identical fault offset (`0x1c00`) every time**.
- Confirmed live: invoking the real app's "Open Image File" button (via UI
  Automation, bypassing keyboard/mouse routing entirely) killed the process
  outright (exit code 139/SIGSEGV) with **zero** Python-level exception or
  log output — this is why nothing showed up even with `--debug`: the
  process was dying natively, silently, with no console (`--windowed`).
- A from-scratch, minimal `AccessibleWebView` test script — no menu bar, no
  `vrp/app.py` code at all — reproduced the **identical crash, same module,
  same offset**, on the same kind of button invoke. This rules out anything
  specific to this app's window/menu-bar construction order.
- A full audit of `vrp/app.py` (`MainWindow.__init__`, `_build_menubar`,
  `_on_char_hook`, focus-restoration helpers) and every dialog file found
  **no lifecycle bug** that could explain a native crash in the WebView2
  binding. The project rename (omw -> VRP) happened in the single initial
  commit (no separate rename commit exists), and a repo-wide grep for "omw"
  found zero leftover references — the rename was clean and is not
  implicated either.
- Versions: wxPython 4.2.5 / wxWidgets 3.2.9, against the installed WebView2
  **Evergreen** Runtime 149.0.4022.69 (Windows auto-updating channel). Most
  likely cause: an ABI mismatch between wxWidgets' WebView2 backend and this
  particular (very new) runtime build.

**Conclusion: the menu-bar-construction-order revert and the `EVT_CHAR_HOOK`
disable documented below did not fix anything** — they happened to land on a
state that simply hadn't yet triggered the crash during that round of manual
testing. Re-applying either change is not blocked by anything found here.

**Also fixed in passing** (found during the audit, unrelated to the crash):
`_import_results` in `vrp/app.py` referenced an undefined name (`radio_result`)
instead of its own `src_radio` parameter — a guaranteed `NameError` on every
completed import (query-source or import-from-file). Fixed.

**Next step (workaround, not yet completed):** pin a WebView2 **Fixed
Version** Runtime for local dev via the `VRP_WEBVIEW2_RUNTIME_DIR` env var
(wired up in `main.py`, no-op unless set) to sidestep the Evergreen-runtime
ABI mismatch. Blocked on obtaining the actual runtime files — Microsoft's
download page generates the link client-side via JS after picking
version+arch, and browser automation wasn't available this session. Until
this is done, the app remains effectively unusable for any in-page
interaction; expect the same crash on the first button/keystroke.

---

## 2026-06-18 — OPEN: webview input appears totally dead (in progress, mid-diagnosis)

**Status: unresolved, reverted to last-known state, paused for a machine reboot.**

Chain of reports, in order:
1. "Control+O to open a file is not working" — fixed by catching Ctrl+O at
   the native `EVT_CHAR_HOOK` level (mirroring the earlier Alt-menu-mnemonic
   fix), theory being WebView2 treats Ctrl-combos as "browser accelerator
   keys" it can consume before the page's own JS keydown listener sees them.
2. "It works most of the time but breaks after you open a file — additional
   opens don't work via hotkey OR the page button." This ruled out the
   WebView2-accelerator-key theory (the hotkey path now bypassed the webview
   entirely via EVT_CHAR_HOOK, yet still broke identically to the button) —
   pointed at something common to both paths (`on_open`, or app state).
3. Asked the user to run `uv run python main.py --debug` from a terminal to
   see if an exception was being silently swallowed (the app is `--windowed`,
   no console). Result: **no debug output at all**, not even from the first
   "Open Image File…" button press — meaning the click never reached Python.
4. Suspected the `EVT_CHAR_HOOK` binding added today (for Alt mnemonics +
   Ctrl+O) as a regression and disabled it (commented out the `Bind` call in
   `MainWindow.__init__`). Bug persisted with it disabled.
5. Asked the user to check whether **F12** (WebView2's own built-in DevTools
   toggle — independent of any of our code) does anything. **It does not.**
   This is the most important data point so far: if the webview can't even
   trigger its own native F12 handling, the control may not be receiving
   keyboard input/focus at all, which would explain every symptom above
   uniformly (our bridge, our shortcuts, AND WebView2's own built-ins all
   failing the same way) — pointing away from a JS-bridge-registration race
   theory and toward a focus/construction-order issue instead.
6. Reverted the *other* change made today: building `_build_menubar()`
   **before** constructing the webview (vs. its original position, after).
   Both `vrp/app.py` changes are now reverted to pre-today behavior:
   - `EVT_CHAR_HOOK` binding commented out (search for "TEMPORARILY DISABLED"
     in `MainWindow.__init__`).
   - `_build_menubar()` call moved back to after the webview/sizer setup
     (search for "TEMPORARILY REVERTED").
   - The Ctrl+O-specific handling inside `_on_char_hook` is moot while the
     binding above it is disabled, but the code is still there, unused.
   - Tests pass (63/63) throughout — none of this is covered by the test
     suite, which only exercises `chirp_backend`/`views`/`config`, not live
     wx event routing.

**Not yet known:** whether reverting the construction-order change (step 6)
fixes it — the user was about to retest when they asked to reboot the machine
first. **Next step on resume: clean relaunch (`uv run python main.py
--debug`), retest F12 and the Open button.**

If reverting BOTH changes still doesn't restore F12/button interaction, the
cause predates today's session entirely (something environmental — possibly
a WebView2 runtime update, a stuck process, or something unrelated to recent
code at all) and the investigation needs to widen beyond `vrp/app.py`.

Also from today, unrelated to the above and NOT reverted (working, separate
from this investigation):
- `wx.CallAfter`-deferred `_SHORTCUTS_JS` injection in `_on_webview_loaded`
  (fixes a spurious "Unknown runtime error" dialog from nested `RunScript`
  calls — see the entry/commit for that fix if one exists; this was verified
  working before the input-dead regression appeared).
- Switched packager Nuitka → PyInstaller (see entry below) — built and smoke
  tested successfully, unrelated to this webview-input issue.
- Added `payown` and `accesswatch` as GitHub collaborators (admin) on
  douglangley/Versatile-Radio-Programmer.

**Uncommitted right now:** only `vrp/app.py` (the disable/revert edits above).
Safe on disk regardless of reboot — `git status --short` shows just that one
modified file. Not committed because it's a mid-diagnosis state, not a
validated fix.

---

## 2026-06-17 — Switched packager: Nuitka → PyInstaller (build time)

Nuitka compiled all 552 CHIRP drivers to C on every build — 20-30 minutes
even after the Phase 9 bloat fixes (wx.lib.agw / win32more / numpy exclusions).
Replaced with PyInstaller, which freezes bytecode instead of compiling, so the
same build now finishes in well under a minute.

- `build.py` rewritten around `python -m PyInstaller`: `--windowed` (no
  console), `--exclude-module` for `prism`/`win32more`/`numpy` (same reasoning
  as before — speech is opt-in/off by default and no-ops without prism),
  `--collect-submodules` for `chirp.drivers` and `chirp.sources` (both are
  loaded via dynamic `__import__`/`importlib.import_module` — confirmed in
  `chirp/directory.py` and `chirp_backend/query.py` — so PyInstaller's static
  analysis can't find them on its own, same constraint Nuitka had),
  `--collect-data` for `chirp` (stock_configs/locale) and `lark` (grammar
  files), `--add-data` for `static`/`templates`. `--no-onefile` still builds
  to `dist/vrp/` instead.
- `pyproject.toml` build extra now installs `pyinstaller` instead of
  `nuitka`/`ordered-set`.
- `build.bat` updated (still installs deps + tees a timestamped log), wording
  changed from "~20-30 min" to reflect the new build time.
- README "Packaging with Nuitka" → "Packaging with PyInstaller", CLAUDE.md
  "Building" section updated to match.
- wxPython/jinja2/markupsafe/pyserial need no explicit flags — PyInstaller
  follows them automatically since (unlike the old `--include-package=wx`
  Nuitka flag) we never asked it to grab whole packages, only what's imported.

**Bug found and fixed during verification:** the first build "succeeded" (exit
0) but logged 200+ `Hidden import 'chirp.drivers.X' not found` lines. Root
cause: CHIRP is installed editable via uv (PEP 660), which routes imports
through a generated `__editable___chirp_0_finder.py` on `sys.meta_path`.
`collect_submodules()` resolves names fine (it does a real import), but
PyInstaller's static modulegraph analysis walks `sys.path` directly and
doesn't know about that custom finder, so it couldn't locate the `.py` files
for the hidden imports it had been told to add — they were silently dropped
from the bundle. Fixed by adding `--paths=<repo>/chirp` (the real source dir)
to `build.py`, giving modulegraph a standard path-based way to find them.

**Verified:** `--no-onefile` build completed in ~13-19s (vs. 20-30 *min* for
Nuitka). Confirmed via `PyInstaller.archive.readers` that all 192
`chirp.drivers.*` and 10 `chirp.sources.*` modules are actually embedded in
the PYZ (not just listed). Launched `dist/vrp/vrp.exe` — ran without crashing.
Built a throwaway console smoke-test exe with the same flags that calls
`directory.import_drivers()` and loads `chirp/tests/images/Abbree_AR-518.img`
end-to-end inside the frozen environment — passed ("Loaded: Abbree AR-518").
Build/test artifacts (`build/`, `dist/`, smoke-test exe) cleaned up after
verification; not committed.

---

## 2026-06-17 — Pin CHIRP to a tested commit (reproducible from source)

Made the vendored CHIRP version reproducible across machines without committing
the `./chirp` tree (it stays gitignored). Approach:

- New **`CHIRP_COMMIT`** file (tracked) holds the full tested SHA
  (`6dadd6b…`). One line, SHA first, so batch `set /p` and Python parse cleanly.
- **`run.bat`** reads it into `%CHIRP_SHA%` and, right after the shallow clone,
  pins via `git -C chirp fetch --depth=1 origin %SHA% && git checkout %SHA%`
  (WARNING + fall back to latest if that fails). Verified fetch-by-SHA works
  against GitHub (`kk7ds/chirp`) on a shallow clone — exit 0.
- **`tools/update_chirp.py`** rewritten for the now-detached-HEAD clone: was
  `git pull --ff-only` (breaks on detached HEAD). Now fetches latest, checks it
  out detached, runs pytest, and on pass **writes the new SHA back to
  `CHIRP_COMMIT`** (rolls `./chirp` back to the old pin on failure). The pin file
  is the single source of truth; bump it, commit it, rebuild.
- README "Updating CHIRP" updated to describe the pin file + auto-bump flow.

---

## 2026-06-17 — Run-from-source launcher (GitHub readiness)

Added `run.bat` (Windows) for contributors cloning from GitHub: checks for uv +
git, clones CHIRP into ./chirp if missing (it's a required editable path dep, so
it must exist before `uv sync`), runs `uv sync`, then `uv run python main.py`.
Idempotent — first run sets everything up, later runs just launch; pauses only on
error. Added a "Quick start (run from source)" section to the README (run.bat +
manual cross-platform steps, prerequisites, WebView2 note). `/chirp/` stays
gitignored so contributors clone it themselves via the script.

---

## 2026-06-17 — Phase 9: CHIRP update strategy + Nuitka packaging

**CHIRP update strategy (done):** `tools/update_chirp.py` — pulls latest CHIRP,
runs the VRP test suite against it, reports pass/fail (+ rollback command on
failure). On success: record the new SHA (PROGRESS_LOG/CLAUDE) and rebuild. CHIRP
is bundled in the exe; end users never pull/rebuild (updates = new VRP releases).
Documented in README "Updating CHIRP" + CLAUDE.md. Pinned commit: 6dadd6b.

**Nuitka packaging (in progress):**
- Toolchain confirmed: Nuitka 4.1.2 + MSVC `cl 14.3` (no compiler download).
- `build.py` hardened: `--assume-yes-for-downloads` (never blocks on a prompt)
  and `--include-package=chirp.sources` (query sources are imported dynamically,
  so Nuitka won't auto-follow them; `chirp.drivers` was already included).
- Note: `uv sync --extra build` drops the dev extras (pytest); use
  `uv sync --extra dev --extra build` for both.

**Build debugging — two bloat sources found & fixed.** First build attempts ran
30–40+ min / 3.2 GB / stalled. Diagnosed (a minimal Nuitka build is 10s, so the
toolchain is fine):
1. `--include-package=win32more` pulled the ENTIRE Windows API binding surface
   (~795 modules) via prism → removed; prism/win32more/numpy now
   `--nofollow-import-to` (speech is opt-in/off-by-default and no-ops without
   prism — see vrp/speech.py).
2. `--include-package=wx` force-compiled ALL of wxPython incl. the huge
   `wx.lib.agw` widget set → removed; Nuitka now follows only the wx modules we
   import (core, wx.adv, wx.html2).
Validated: the app **shell** (wx + webview + chirp core + jinja + lark, drivers
excluded) builds cleanly in ~4 min → 33 MB exe. The remaining build cost is
compiling the 552 CHIRP `drivers` (required for full radio support) — inherently
~20–30 min, but bounded and correct now. The full driver build is a long offline
release step; exe launch + load-image smoke still owed once a full build is run.

**Decision: full build deferred to run offline.** Added `build.bat` (Windows) —
installs build deps, runs `build.py` with live output Tee'd to a timestamped
`build_*.log` (gitignored) for debugging, and reports success/failure. The user
runs it outside Claude. Dev env restored (`uv sync --extra dev`); 63 tests pass.

---

## 2026-06-17 — Test suite cleanup (25s → ~2s)

Profiled the slow suite. CHIRP itself was fast (import_drivers 0.22s, image loads
<0.25s, reading 1000 channels 0.01s). One test dominated — 
`test_render_channels_is_accessible_table` at **23s**. Root cause: the new
config-driven page size made `render_channels` → `views._page_size` →
`get_config()` call `wx.StandardPaths.Get()`, which **spins up an implicit wx.App
(~6s, 23s in-test) when no App exists** (headless pytest). (The earlier
"minutes" were also several `uv run pytest` processes running concurrently and
contending.)

Fixes:
- `vrp/config.py`: compute the config path from env vars (`%APPDATA%` /
  `$XDG_CONFIG_HOME`/`~/.config`) instead of `wx.StandardPaths` — no implicit
  wx.App, deterministic, headless-safe. Same location as before (APPDATA), so no
  migration.
- `tests/conftest.py`: autouse fixture points the config singleton at a temp file
  per test — no reading/writing the real user config, deterministic default prefs.
- `pyproject.toml`: `filterwarnings` to silence the vendored-CHIRP
  DeprecationWarnings (kept our own warnings visible).

**Result:** full `uv run pytest` → **63 passed in ~1.8s** (3s wall), clean output.
Slowest test now 0.36s. (Bonus: the app no longer risks creating a stray implicit
wx.App on config access.)

---

## 2026-06-17 — Bug fixes: empty-channel editing, Edit-button position, rename

User-reported fixes (accessibility-lead reviewed):
1. **Bug — empty channel edit only offered Frequency.** Repro: open
   `Baofeng_5RX.img`, edit channel 0 (empty) → only Frequency was editable.
   Fix (`vrp/edit_dialog.py`): empty channels now expose ALL editable fields
   (immutable still disabled), pre-filled with the radio's defaults; the
   Frequency field carries a "required to activate; leave blank to keep empty"
   hint. Verified on 5RX: empty ch0 now shows all 13 fields.
2. **Edit button moved to the start of the row.** `_row_macro.html` now emits
   `<th scope="row">` (row header, kept first for semantics), then the Edit
   button cell, then the data cells. `channels.html` header reordered to
   Ch # / Edit / columns (dropped the trailing "Actions"); caption updated.
3. **Renamed "Channel operations" → "Organize Channels"** (the dialog also
   inserts/copies/sorts/arranges, so the lead rejected "Move/Delete" as
   inaccurate). Updated the menu item, in-page button (+ aria-label "Organize
   channels (move, delete, copy, sort)"), the `<nav>` label, the dialog title,
   and the Ctrl+M F1 description.

**Verified:** smoke on 5RX — empty ch0 exposes 13 fields, non-empty ch1 OK, row
order is th < Edit < data, 15 header columns match the body, rename present in
render + dialog title. Updated the two tests that asserted the old "Actions"
header / "Channel operations" nav label. Docs updated.

**Owed: NVDA pass** — confirm Edit announces in column 2 (row header still reads
"channel N"), the empty-channel dialog reads the Frequency hint and lets you set
everything, and the renamed button/menu read correctly. (User noted channel-1
editing "seems ok, more testing needed.")

---

## 2026-06-17 — More query sources (DMR-MARC, mapy73.pl)

Added two no-credential sources to the Phase 7 registry:
- **DMR-MARC** (`DMRMARCRadio`) — city / state / country text params.
- **mapy73.pl** (`Mapy73Pl`) — a "Network" choice (16 fixed options).

Framework extension: `QueryParamsDialog` now renders a `choice` param kind
(wx.Choice) in addition to text, and `get_params()` always includes every
declared param (some sources read `params['key']` directly, so a missing key
would crash `do_fetch`). The Radio ▸ Query Source submenu auto-lists them
(it iterates the registry). Still deferred (need special param handling):
RepeaterBook (dynamic country→state cascade), RadioReference (credentials),
przemienniki.net/.eu (band/mode code mapping + coords).

**Tests/verify:** `test_query_sources_registry` extended (all 4 source classes
import; mapy73 choice spec); dialog smoke — DMR-MARC yields city/state/country
keys (present even when blank), mapy73 yields the selected `api_option`.
Network fetch still owed (no network in dev).

---

## 2026-06-17 — Config / preferences subsystem (Preferences + Open Recent)

**Goal:** A persistent config store enabling app preferences and recent files.
Accessibility-lead reviewed.

**Store (vrp/config.py):** JSON at `wx.StandardPaths` user-config dir
(`OpenMemoryWriter/config.json`); atomic write (temp + os.replace); missing/
corrupt → defaults (never blocks startup). `get/set`, `add_recent` (de-dupe,
move-to-front, cap 8), `remove_recent`, `clear_recent`. `get_config()` singleton.

**Preferences (vrp/prefs_dialog.py + app.py `on_preferences`):** native dialog
with **Channels per page** (wx.Choice 25/50/100/250/500) and **Speak status
messages aloud** (CheckBox, default OFF — gates the *supplemental* prism speech;
the live region is always spoken by the screen reader). OK persists + applies
immediately: page-size change re-renders the grid and re-clamps the page +
announces; speech toggle updates `self._speak_enabled` (gated in `_announce` and
`on_not_implemented`). File ▸ Preferences… (`wx.ID_PREFERENCES`).

**Page size is now config-driven:** `views._page_size(None)` resolves the
configured value (fallback 100, tolerant of headless/no-wx), so all existing
`views.*` call sites pick it up with no changes.

**Open Recent (app.py):** File ▸ Open Recent submenu rebuilt dynamically
(`_rebuild_recent_menu`) — `&1…&8` basename labels (full path in the item help;
parent folder appended on basename collision), a Clear item, and a disabled
"(No recent files)" placeholder when empty. `_open_path` records every
successful open; a recent entry that's missing/unloadable is announced and
pruned. Refactored `on_open` to use `_open_path`.

**Tests:** `tests/test_config.py` (defaults, persistence, corrupt-fallback,
recent de-dup/cap/order, clear); views honor an explicit page_size. **63 pass.**
(Suite is slower now — the Phase 6–8 tests load large images, e.g. FT-60's 1000
channels; consider trimming to smaller test images later.)

**Verified:** full `uv run pytest` → 63 passed; config/page-size direct checks +
wx smoke (Open Recent menu, Preferences dialog, page-size effect) all OK.

**Owed: manual check** — Preferences (change page size → grid re-pages; toggle
speech), and Open Recent across opens/restart.

**Still deferred** (CHIRP-GUI editor behaviors / need a model picker): Open Stock
Config, Select bandplan, Auto edits, New (empty image), New Window.

---

## 2026-06-17 — Phase 8 (slice): Import-from-file, Export-CSV, Radio Info

**Goal:** The concrete, testable items of the Phase 8 grab-bag. Accessibility-
lead reviewed. Deferred (need a config/recent-files subsystem or are CHIRP-GUI
editor behaviors): Preferences, Open Recent, Open Stock Config, Select bandplan,
Auto edits, New (empty image), New Window. Print intentionally not implemented
(native print is inaccessible; Export-to-CSV is the equivalent).

**Backend (chirp_backend/radio.py):**
- `open_image_as_source(path)` — loads an image into a STANDALONE radio for
  import WITHOUT touching the global `_state` (critical: load_image would have
  replaced the active radio).
- `export_to_csv(path)` — copies non-empty channels into `generic_csv.CSVRadio`
  via `import_logic.import_mem` and `save_mmap`; zero-count guard; does NOT
  alter the working image's saved state.
- `describe_radio_html(state)` — escaped label/value `<table>`s (identity /
  capacity / capabilities with Yes/No flags) for the Radio Info dialog.

**UI (vrp/app.py):**
- File ▸ Import from File… (`on_import_file`): native FileDialog → source →
  reuses the shared `_import_results` (renamed from `_import_query_results`) with
  the existing ImportDestinationDialog + `memory_ops.import_memories`.
- File ▸ Export to CSV… (`on_export_csv`): native save FileDialog
  (FD_OVERWRITE_PROMPT), appends .csv, announces result.
- Radio ▸ Radio Info… (`on_radio_info`): `show_message` accessible HTML dialog.
- All three added to `_radio_menu_items` (disabled until a radio is loaded);
  menu-only (no Ctrl shortcuts). Import binds directly (manages its own focus);
  Export/Info via `_menu_then_focus`.

**Tests:** open-as-source doesn't mutate state + imports from a file source;
export→CSV round-trip (reopen the CSV, channel count matches); describe HTML
content. 57 pass.

**Verified:** `uv run pytest` → 57 passed; menu-gating smoke OK.

**Owed: manual check** — open a radio, Import from another image (e.g. FT-60 →
UV-5R), Export to CSV and reopen the file, and read Radio Info with NVDA.

**Next:** the deferred config/preferences subsystem (Phase 8.x), then Phase 9
(CHIRP update strategy + Nuitka packaging) and Phase 10 (coverage/hardening).

---

## 2026-06-17 — Phase 7: query sources (framework + AMSAT/SatNOGS)

**Goal:** Query online databases and import results into the loaded radio.
Accessibility-lead reviewed. Network-bound and large (7 sources, some with
credentials) — this slice builds the reusable framework + import op + the two
no-credential sources; the param-heavy/credential sources are mechanical
follow-ups (add a registry entry + param form).

**Backend:**
- `chirp_backend/query.py`: SOURCES registry (AMSAT, SatNOGS) with label/
  module/class/attribution/ToS/params; `make_source_radio(key)`,
  `run_fetch(radio, params, progress_cb)` (adapts CHIRP QueryStatus → progress
  callback, runs do_fetch, returns (ok, message)), `result_count`.
- `memory_ops.import_memories(src_radio, destination, overwrite)`: copies each
  non-empty source memory into consecutive channels, adapting via CHIRP
  `import_logic.import_mem` (handles mode/tone/power differences); skips or
  overwrites occupied channels; returns (ok, "Imported N…", affected). TESTED
  (synthetic source → UV-5R).

**UI (vrp/query_dialogs.py + app.py):**
- `QueryParamsDialog` (per-source params; AMSAT/SatNOGS have none) shows the
  source attribution + a descriptive `wx.adv.HyperlinkCtrl` ToS link.
- `ImportDestinationDialog`: start-channel SpinCtrl (defaults to first empty) +
  Overwrite/Skip RadioBox.
- `app.py`: Radio ▸ **Query Source** submenu (one item per registered source,
  in `_radio_menu_items` so disabled until a radio is loaded). `on_query_source`
  → params dialog → `_run_query` (background thread + CloneProgressDialog +
  throttled live-region status) → `_on_query_done` (announce count) →
  `_import_query_results` (destination dialog → import_memories → re-render +
  focus first imported channel + announce). No Ctrl shortcut (too many sources;
  reached via Alt→R→Q).

**Tests:** registry + class import; `run_fetch` success + failure with a fake
source; `import_memories` into UV-5R. Smoke (wx): param/import dialogs construct,
ToS link, submenu present + gated. 54 pass.

**Verified:** `uv run pytest` → 54 passed; query smoke OK.

**Owed: live network test** (no network here) — actual AMSAT/SatNOGS fetch →
progress announcements → import. **Deferred (7.x):** RepeaterBook, RadioReference
(credentials), DMR-MARC, przemienniki.net/.eu, mapy73.pl param forms; and the
read-only results-preview grid (review-before-import).

**Next:** Phase 8 — Import/Export, Print, Radio info, Auto edits, Bandplan,
Preferences.

---

## 2026-06-17 — Phase 6: banks editor (assign channels to banks)

**Goal:** Assign a memory channel to banks. Accessibility-lead reviewed; scoped
to membership (bank renaming + a "channels in a bank" overview deferred to 6.1).

**Backend (chirp_backend/bank_ops.py — new, pure functions):**
- `has_bank()`, `get_bank_state(number)` (mode + banks + current membership),
  `apply_bank_changes(number, desired_indexes)` (removes then adds the diff,
  reports failures truthfully, announces resulting membership). Mode from the
  CHIRP class: `MTOBankModel`→multi, `StaticBankModel`→fixed/read-only, else
  `BankModel`→single (zero-or-one). Bank identity = `get_index()` (opaque; may
  be a string). Model via `radio.get_mapping_models()[0]`. Empty channels and
  fixed banks handled.

**UI (vrp/bank_dialog.py):** `ChannelBanksDialog` — CheckBox per bank (multi) or
a RadioBox of "None" + banks (single); fixed shows disabled controls, Close-only.
Intro line states current membership in words (rule #7). `get_desired_indexes()`.

**app.py:** `on_channel_banks(data)` — number from data or a prompt (Ctrl+B);
opens the dialog, applies the diff, announces, navigates to + focuses the row.
Channels ▸ "Channel banks…" + `Ctrl+B` (bridge + APP_SHORTCUTS, in F1).
`_update_menu_state` gates the menu item on `bank_ops.has_bank()` (disabled on
no-radio / no-bank radios).

**Tests:** bank assign round-trip on Yaesu FT-60 (add→member→remove); banks
absent on BF-888. Smoke (wx): single-mode dialog (10 banks) + desired-index
selection + menu gating across no-radio/no-bank/bank radios. 50 pass.

**Verified:** `uv run pytest` → 50 passed; bank smoke OK.

**Owed: NVDA pass** (dialog read-out of membership + checkbox/radiobox state).
**Deferred (6.1):** bank renaming ("Manage banks…"), "channels in a bank…"
overview, and an in-grid per-row Banks button.

**Next:** Phase 7 — query sources (RadioReference, RepeaterBook, etc.).

---

## 2026-06-17 — Phase 5: radio settings editor

**Goal:** View/edit the radio's settings tree. Accessibility-lead reviewed the
model (single modal dialog + wx.Treebook + native controls per value type).

**Backend (chirp_backend/radio.py):** `has_settings()`, `get_radio_settings()`
(returns the live RadioSettingGroup tree), `apply_radio_settings(settings)`
(`set_settings` + mark modified). All guarded/thread-locked.

**UI (vrp/settings_dialog.py):** `RadioSettingsDialog` — a `wx.Treebook` whose
tree mirrors the top-level groups; each page is a scrolled FlexGridSizer of
label+control pairs. Value→control: Boolean→CheckBox, List→Choice,
Integer→SpinCtrl (min/max/step), String/Float→TextCtrl (String SetMaxLength).
Immutable values disabled + "(read only)". Nested sub-groups are FLATTENED into
their top-level page with an indented bold heading (robust vs wx Treebook
sub-page ordering; tree still segments top-level groups). On OK every enabled
control is written via `value.set_value` (validates); a bad value keeps the
dialog open, selects the offending control's page, focuses it, and speaks the
reason. Cancel discards (values are only mutated on OK). Initial focus = tree.

**app.py:** `on_settings` (guards loaded + has_settings, opens dialog, applies on
OK, announces "Radio settings saved. N changed." / "No settings were changed.",
restores webview focus). Wired all three surfaces: Radio ▸ Settings… +
`Ctrl+Shift+P` (`_SHORTCUTS_JS` + `APP_SHORTCUTS` + dispatch); menu item added to
`_radio_menu_items` (disabled until a radio is loaded).

**Tests:** settings available + boolean change + apply round-trip; none-when-no-
radio. Smoke (wx): 5 Treebook pages / 80 controls on UV-5R, toggle→OK→apply
changed 1, menu enable/disable. 48 pass.

**Verified:** `uv run pytest` → 48 passed; settings smoke OK.

**Owed: NVDA pass** (accessibility-lead flagged the Treebook tree↔panel F6 hop
and SpinCtrl non-1 step as the spots to verify live).

**Next:** Phase 6 — banks editor (`bankedit.py`).

---

## 2026-06-16 — Menu completeness + documentation/memory refresh

- **Menu coverage:** every implemented command is now reachable from the native
  menu bar. Added Channels ▸ **Edit channel…** and **Go to channel…** (native
  number prompt → existing `on_edit_channel` / `on_goto`); both disabled until a
  radio is loaded. Audited: File (Open/Save/Save As/Close/Exit), Radio
  (Download/Upload), Channels (Edit/Go to/Operations/Find/Find next/Prev/Next
  page), Help (Shortcuts/About) — all 16 commands present.
- **CLAUDE.md:** added a "Command Surfaces (keep in sync)" section (menu +
  buttons + Ctrl shortcuts; how to add a new command) and listed the new vrp
  modules (ops_dialog, find_dialog, serial_dialogs).
- **README / docs/architecture.md:** updated structure + an "Interaction model"
  section (read-only paged grid, native dialogs, three command surfaces, #24786).
- **docs/keyboard-map.md:** documented the full menu contents incl. Edit/Go to.
- **Memory:** refreshed architecture-decision with the matured design and a
  pointer to PROGRESS_LOG.md/docs as the source of truth; updated MEMORY.md.
- Verified: full menu audit (all commands present; Edit/Go to enable with radio);
  `uv run pytest` → 46 passed.

---

## 2026-06-16 — Phase 4: Serial download / upload

**Goal:** Read from / write to a physical radio over the serial cable. Reviewed
by accessibility-lead (+ wxPython/desktop-a11y specialists).

**Backend fixes (chirp_backend/radio.py) — the scaffold was broken vs current
CHIRP:**
- `list_radio_models()` rewritten to iterate `directory.DRV_TO_RADIO` (the old
  `DET_RADIOS`/`RADIOS` don't exist); returns {id, vendor, model, variant, label}
  with CHIRP's real driver id (552 models). `download_from_radio` now takes that
  driver id and looks it up via `directory.get_radio(id)` (old code joined
  "vendor model" with a space — wrong key format).
- Fixed the status callback: CHIRP calls `radio.status_fn(status)` with a Status
  object; the old code assigned a Status *instance* (not callable). New
  `_make_status_fn` adapts `status.cur/.max/.msg` to our progress callback.
  Pipes are closed on error.

**UI (vrp/serial_dialogs.py + app.py):**
- `DownloadDialog`: PortPicker (Choice + Refresh + explicit no-ports state) +
  model picker = filter field + ListBox narrowing ~550 models by substring (so
  NVDA hears the filtered count). Download button disabled until port+model set.
- `UploadDialog`: port picker only; app shows a native confirm ("overwrite ALL
  channels…", default Cancel) before writing.
- `CloneProgressDialog`: modeless gauge + status text; download has Cancel.
- `app.py`: `on_download`/`on_upload`; `_run_clone` runs the (synchronous,
  not-cancel-aware) backend on a daemon thread and marshals progress via
  `wx.CallAfter`, throttled (≥2s or 10% step) to the live region; gauge updates
  every tick. `_on_clone_done` (UI thread) destroys the dialog, re-enables the
  frame, restores webview focus; on download success re-renders the grid +
  focuses the first channel + announces; failures announce + show an error
  dialog. Download Cancel discards the result; upload has no Cancel (can't
  safely abort a half-written radio — flagged for a backend follow-up if true
  cancel is wanted). Radio menu items rebound to the handlers; Upload disabled
  until a radio is loaded; `Ctrl+Shift+D` / `Ctrl+Shift+U` added (bridge +
  APP_SHORTCUTS + menu accelerators).

**Tests:** `list_radio_models` count + id round-trip; download-unknown-driver
and upload-without-radio error paths. Smoke (wx): download dialog filter+
selection, zero-ports degradation, upload dialog, progress dialog, Upload menu
enable/disable. 46 pass.

**Verified:** `uv run pytest` → 46 passed; serial UI smoke OK.

**Owed: real-radio test** — no hardware in dev. Need to verify an actual
download (model picker → progress announcements → grid populates) and upload
(confirm → progress) over a serial cable with NVDA. Cancel during download is
"discard result" (the transfer still completes; backend isn't interruptible).

**Next:** Phase 5 — radio settings editor (`settingsedit.py`).

---

## 2026-06-16 — Phase 3 (slice 2): Find / Find Next  → Phase 3 complete

**Goal:** Find a channel by text and step through matches. Implemented to the
accessibility-lead's Phase 3 model (§5).

**Done:**
- New `vrp/find_dialog.py`: native `FindDialog` — text field + "Search in"
  chooser (All fields / Name / Frequency / Comment). On OK it calls the app's
  search callback; stays open + speaks "not found" on a miss, rejects empty.
- `vrp/app.py`: `on_find` (opens dialog, then focuses the matched row and
  announces), `_find_from_dialog` (search callback: runs `memory_ops.find`,
  navigates to the match's page), `on_find_next` (continues from the last match;
  backend wraps — announces "Next match" / "Wrapped to start" / "Only match"),
  `_describe_match`. `Ctrl+F` / `Ctrl+G` added to `_SHORTCUTS_JS` + `APP_SHORTCUTS`
  (Ctrl+F intercepted so the WebView2 find-bar doesn't take it). Find state on
  MainWindow (query/fields/last). Channels menu: Find / Find next; in-page
  "Find…" button (`#find-btn`).
- Reuses the existing `memory_ops.find(text, start, fields)` (first match after
  start, wrapping) — no separate match list needed.
- Tests: field-choice mapping, `find` locate/wrap/miss; "Find…" button present.
  Smoke: locate + find-next wrap + miss + no-active-search. 43 pass.

**Verified:** `uv run pytest` → 43 passed; find smoke OK.

**Phase 3 status: COMPLETE** (bulk operations + Find/Find Next; Goto via paging).
Not done by design: Cut/Paste clipboard semantics (copy/move cover the need);
revisit if wanted.

**Owed: manual NVDA pass** — Ctrl+F dialog, jump+announce, Ctrl+G stepping/wrap,
not-found handling.

**Next:** Phase 4 — Serial download/upload (the Radio menu stubs).

---

## 2026-06-16 — Native menu bar restored

**Why:** Revisited the earlier menu-bar removal. Research (wxWidgets issue
#24786) corrected the basis: a focused WebView2 consumes one-shot Alt+key
mnemonics / Ctrl accelerators, BUT plain Alt still selects the menu bar and an
OPEN menu is a native Win32 menu (arrows + Enter work, EVT_MENU fires, NVDA
reads it). So the menu is genuinely usable, not inert — my prior removal was on
an incomplete picture. Accessibility-lead re-reviewed and endorsed re-adding it
as a complement (not replacement) to the buttons + bridged shortcuts.

**Done (vrp/app.py):**
- `_build_menubar`: File (Open/Save/Save As/Close/Exit), Radio (Download/Upload
  stubs), Channels (Operations Ctrl+M / Previous Ctrl+Alt+Left / Next
  Ctrl+Alt+Right), Help (Keyboard Shortcuts F1 / About). Mnemonics + accelerator
  text shown for discoverability; labels mirror the in-page buttons.
- Menu items reuse existing handlers. Context items (Save/Save As/Close/
  Operations/Prev/Next) disable when no radio (`_update_menu_state`, called on
  open/close); stubs stay enabled and announce; Open/Exit/Shortcuts/About always
  enabled.
- `_menu_then_focus` wrapper restores webview focus after menu actions that
  don't themselves move focus into the page, so bridged Ctrl shortcuts stay live
  (rule #6). Open/Operations/paging manage their own focus.
- Per accessibility-lead: no DOM `role="menubar"` (one native menu + one set of
  in-page buttons); F1 list and bridge stay the source of truth for shortcuts.

**Verified:** menu smoke (4 menus; context items disabled with no radio, enabled
after load; focus-restore runs). `uv run pytest` → 41 passed.

**Owed: manual NVDA pass** — Alt selects the menu, arrows/Enter operate it,
results announce, focus returns to the page, and a bridged Ctrl shortcut fires
immediately after without clicking into the page.

---

## 2026-06-16 — Phase 3 (slice 1): bulk channel operations

**Goal:** Range selection + bulk operations (delete, delete+shift, insert,
move, copy, sort, arrange). Accessibility-lead reviewed the model.

**Decisions (user):** contiguous From/To by default *plus* an advanced channel
list (`1-5,8,10-12`); **no undo** — native confirm dialogs guard destructive
ops. No per-row checkboxes (would re-bloat the DOM that paging just fixed).

**Done:**
- Backend: `memory_ops.parse_channel_spec(spec, low, high)` parses the advanced
  list (ranges + singletons, reversed ranges, dedupe, bounds-checked). All bulk
  ops already existed (`delete_range`, `delete_and_shift`, `insert_row`,
  `move_memories`, `move_to`, `copy_memories`, `sort_range`, `arrange_range`).
- New `vrp/ops_dialog.py`: native `ChannelOperationsDialog` — From/To SpinCtrls
  + advanced list field (advanced wins when non-empty) + live affected-count
  summary + operation `RadioBox` + a contextual parameter area (shift mode /
  destination / sort column+order) shown per operation. Validates on OK (stays
  open, speaks reason, focuses the field).
- `vrp/app.py`: `operations` action + `Ctrl+M` (added to `_SHORTCUTS_JS` map and
  `APP_SHORTCUTS`). `on_operations` opens the dialog; `_perform_operation`
  confirms destructive/reordering ops (and guards copy/move overwrite via
  `_destination_occupied`), runs the backend op, then re-renders the affected
  page, focuses the result channel (`_op_focus_target`), and announces
  "…Now on channel N." `_confirm_message` builds exact range/count/renumber
  warnings; `_confirm` is a native `wx.MessageDialog` (default No).
- `templates/channels.html`: `<nav aria-label="Channel operations">` with the
  `#ops-btn` "Channel operations…" button (`aria-keyshortcuts="Control+M"`).
- Tests: `parse_channel_spec` (ranges/dedupe/errors), operations button present.
  41 pass. Smoke: dialog selection (default + advanced) + params (sort), and a
  real delete via `_perform_operation` clears the channel.

**Verified:** `uv run pytest` → 41 passed. Ops smoke OK.

**Open / next:**
- **Owed: manual NVDA pass** — Ctrl+M dialog, advanced list, confirm wording,
  focus lands on the result channel, announcements.
- **Phase 3 slice 2:** Find / Find Next (native find dialog + host-side match
  list + Ctrl+F / Ctrl+G jump-and-announce loop). Cut/Paste clipboard semantics
  if wanted (copy/move already covered).
- Non-contiguous selection works for delete; move/sort/arrange assume the
  backend's list semantics — validate behavior on scattered sets during the
  NVDA pass.

---

## 2026-06-16 — Cleanup: remove dead Flask-era frontend

Removed the legacy Flask client-render cluster (confirmed unreferenced by the
live wx/webview code): `static/js/{announce,api,index,modal,operations,serial,
table}.js`, `templates/{base,index,settings}.html`, and
`chirp_backend/routes.py` (the unused Flask route layer). These were superseded
by `vrp/views.py` + `channels.html`/`welcome.html`/`_row_macro.html` and inline
bridge handlers. Kept `static/css/main.css` (design-system styles flagged for
future inlining into the webview). Updated CLAUDE.md / README structure notes.
`uv run pytest` → 39 passed; app still constructs.

---

## 2026-06-16 — Phase 2: table paging (large-radio performance)

**Goal:** Render the channel grid one page at a time so radios with thousands
of channels are fast (the read-only grid was already light, but a full ~10k-row
DOM is still costly to render/expose). Accessibility-lead reviewed the design.

**Done:**
- `vrp/views.py`: page-aware `render_channels(page, page_size=PAGE_SIZE=100)` and
  pure, unit-tested page math — `total_pages`, `page_for_channel`, `page_range`,
  `channel_total`. Only the current page's rows are rendered.
- `templates/channels.html`: a `<nav aria-label="Channel pages">` with
  Previous/Next buttons (disabled at boundaries; accessible names include the
  destination range; `aria-keyshortcuts` Ctrl+Alt+Left/Right), a `#page-status`
  span, and a "Go to channel" group (`<label>` + `type=text inputmode=numeric`
  + Go; Enter-to-go). Caption states the current page range; intro `<p>` keeps
  the grand total.
- `vrp/app.py`: `self._page` state (reset on open/close); dispatch
  `page_prev`/`page_next`/`goto`. `_change_page` clamps, re-renders, returns
  focus to the pressed button (or the opposite one if it became disabled at a
  boundary), and announces the new range politely. `on_goto` validates in
  Python — on success jumps to the channel's page and focuses its Edit button;
  on out-of-range/blank keeps focus in the field and interrupt-announces the
  valid range. Generalized `_focus_element(id)`. Added Ctrl+Alt+Left/Right to
  `_SHORTCUTS_JS` + `APP_SHORTCUTS` (so they appear in F1).
- Tests: page math + slicing (UV-5R 128 ch → 2 pages of 100/28), paging nav
  present, out-of-range page clamped. 39 pass.

**Verified:** `uv run pytest` → 39 passed. Paging smoke: prev/next clamp at
boundaries, goto jumps to the right page and ignores out-of-range/blank.

**Open / next:**
- **Owed: manual NVDA pass** — page Prev/Next keep focus on the button and
  announce the range; Ctrl+Alt+Left/Right page; "Go to channel" jumps + focuses
  the Edit button; out-of-range speaks the valid range.
- Stale `static/js/table.js` (legacy Flask client-render) is dead code — flagged
  by the review for a separate cleanup.
- **Phase 3:** range selection + operations.

---

## 2026-06-16 — Phase 2 REWORK: edit via native wx dialog (not in-grid)

**Why:** Real-world testing on a ~10,000-channel radio showed the in-cell
editing model was slow — putting controls in the grid forced the screen reader
to re-read the whole table on every Tab/interaction. Project owner's call (a
blind NVDA user): keep the grid read-only and edit each channel in a native wx
dialog. Accessibility-lead reviewed and endorsed it as a *stronger* satisfaction
of the modal rule (#4) than an in-page dialog (native dialogs get focus trap,
Escape, and title announcement for free; no WebView2 keyboard capture).

**Done:**
- Backend: `memory_ops.update_channel(number, values)` applies several fields
  atomically (parse all → if all valid, set + single `set_memory`); reuses
  `_parse_field_value`. `memory_ops.validate_channel_values()` returns
  (ok, message, bad_field) so the dialog can stay open and focus the bad field.
- New `vrp/edit_dialog.py`: `EditChannelDialog` (native wx) built from the same
  `build_column_defs` as the table — `wx.TextCtrl`/`wx.Choice`, immutable fields
  disabled + "(read only)", empty channels expose only Frequency, OK validates
  (keeps dialog open + speaks reason + focuses bad field on failure), Cancel
  discards. `wx.StdDialogButtonSizer` gives Enter=OK / Escape=Cancel natively.
- Grid is read-only again: `templates/channels.html` + new
  `templates/_row_macro.html` (shared `row_inner` macro) — plain cells, an
  Actions column, a per-row `<button id="edit-btn-N" aria-label="Edit channel N">`
  that bridges `{action:'edit_channel',number:N}`. Caption rewritten.
- `vrp/views.py`: read-only cells; `render_row(n)` re-renders one row via the
  shared macro (`vrp.html.render_macro`) for surgical refresh; dropped the
  in-cell `columns_meta`/editable scaffolding.
- `vrp/app.py`: dispatch `edit_channel` → `on_edit_channel` (open dialog →
  `update_channel` → `_refresh_row` surgical run_js → announce → `_focus_edit_button`
  returns focus to the row's Edit button across the native↔web boundary,
  SetFocus on the webview first so NVDA follows). Removed the in-cell
  `on_edit`/`_refresh_cell`, the grid-edit JS install, and `window.__vrpCols`.
- Removed `static/js/grid_edit.js` (no longer used; inline onclick + native
  dialog replace it).
- Tests updated: read-only grid + per-row Edit button + Actions header +
  `ch-row` ids; `render_row` matches the grid; `update_channel` (multi-field,
  atomic-on-invalid); `validate_channel_values` reports bad field.

**Verified:** `uv run pytest` → 37 passed. Dialog smoke: non-empty channel
exposes editable fields, empty channel exposes only Frequency, dispatch routes
`edit_channel`, refresh/focus helpers run without error.

**Open / next:**
- **Owed: manual NVDA pass** — Edit button opens the dialog, fields are
  announced, OK/Cancel return focus to the Edit button, the row updates, results
  announced; invalid input keeps the dialog open and speaks the reason.
- **Strongly recommended next (accessibility-lead):** the read-only grid is now
  light, but *initial render* of a ~10k-row table is still a large-DOM cost.
  Add table paging/segmentation + a "Go to / Edit channel N" (Ctrl+E) jump so
  navigating a huge radio is fast. (Deferred from this turn.)
- `col_defs` still includes Name on radios that ignore it (e.g. BF-888).

---

## 2026-06-16 — Phase 2 (superseded): in-cell editing

**Goal:** Make memory channel cells editable from the keyboard, persisting via
CHIRP's `set_memory`.

**Interaction model (accessibility-lead ruling): "edit-to-reveal".** The grid
stays a plain semantic `<table>` (NO `role="grid"`/roving tabindex — fragile
under NVDA + WebView2). Editable cells render as `<button>`s ("{column}:
{value}. Press Enter to edit"); activating one (Enter/Space, or F2) swaps a
native `<input>`/`<select>` into the same `<td>`, which auto-switches NVDA to
focus mode. Enter commits, Escape cancels, blur commits; focus always returns
to the cell button. Always-live controls were rejected (they'd spam
"combo box/edit" on every cell during table reading and invite accidental
edits). Native `<select>` for choice fields, `<input type=text inputmode=decimal>`
for frequency (NOT `type=number`).

**Done:**
- Backend: `memory_ops.set_field(number, field, value)` — parses/validates per
  field using CHIRP's own parsers (`chirp_common.parse_freq`, float/int, power
  level match), rejects immutable fields and the channel-number column, writes
  via `set_memory`, invalidates cache. Returns the standard OpResult.
- `vrp/views.py`: grid now emits per-cell metadata (field, label, display,
  input_type, editable, button_label) + `columns_meta()` (field → label/
  input_type/choices) for the edit JS. Empty channels expose only Frequency;
  immutable fields render read-only with a hidden "(read only)" marker.
- `templates/channels.html`: editable cells = `<button class="cell-edit">` with
  `data-ch/data-field/data-type`; read-only cells = plain text; caption updated
  with editing instructions. **Accessibility-lead reviewed.**
- `static/js/grid_edit.js`: the edit-to-reveal behavior (delegated off
  document; installed once via run_js). Posts `{action:'edit',ch,field,value}`;
  `window.__vrpSetCell` applies Python's authoritative value/label.
- `vrp/app.py`: installs grid JS on webview load; pushes `window.__vrpCols` on
  each grid render; dispatches `edit` → `on_edit` (persists, announces,
  surgically refreshes the cell; full re-render only when empty/active state
  flips).
- Tests: editable-button structure, `columns_meta`, `set_field` (text persists
  on UV-5R, frequency parses, invalid rejected, number rejected). 34 pass.

**Verified:** `uv run pytest` → 34 passed. Headless smoke: grid_edit.js loads,
columns_meta serializes, window constructs, edits via the bridge persist
(name + freq on UV-5R), invalid edits handled gracefully.

**Open / next:**
- **Owed: manual NVDA pass** (the accessibility-lead ship gate) — confirm table
  reading stays quiet, Enter enters focus mode announcing "{column}, channel
  {n}, editing", Enter/Escape return focus to the cell, results announced,
  empty rows expose only Frequency.
- Known limitation: dependent cells (e.g. Offset when Duplex changes) only
  refresh on the next full render; empty→populated triggers a full re-render
  (focus returns to content top). Refine to row-level refresh in a later phase.
- `col_defs` includes the Name column even on radios without name support
  (e.g. BF-888 ignores it) — consider filtering on `features.has_name`.
- **Phase 3:** range selection + memory operations (delete/insert/move/copy/
  sort/arrange, find/goto).

---

## 2026-06-16 — Phase 1: Open/Save + read-only channel grid

**Goal:** Open and save radio image files and render the memory channel grid
read-only.

**Done:**
- File menu wired: Open Image File (Ctrl+O), Save (Ctrl+S), Save As
  (Ctrl+Shift+S), Close Image (Ctrl+W). Save/Save As/Close enable only when a
  radio is loaded; Save with no prior path falls back to Save As; native
  `wx.FileDialog` for open/save (accessible). Window title reflects radio + file.
- `vrp/views.py`: `render_channels()` builds a fully server-rendered, semantic
  table from `chirp_backend` (`build_column_defs` + `format_value`); falls back
  to the welcome view when nothing is loaded.
- `templates/channels.html`: read-only grid — **reviewed by accessibility-lead**.
  Real `<table>`, `<th scope="col">` headers, `<th scope="row">` channel number,
  guidance in `<caption>`. Empty channels carry a VISIBLE "(empty)" text marker
  in the row header (resolves the rule #7 color-only concern AND the screen-
  reader need with one non-color indicator).
- `chirp_backend/radio.py`: fixed `load_image` for the current CHIRP API —
  `directory.get_radio_by_image(path)` returns a loaded radio *instance* (the
  old scaffold called `radio_class(None)` + `load_mmap`, which raised
  "object is not callable"). Added `unload()` for File ▸ Close.
- Tests: `tests/test_views.py` — load image, accessible-table structure
  (16 scoped row headers for BF-888), visible empty marker, save round-trip,
  no-radio fallback.

**Reconciliation note (accessibility review):** the accessibility-lead flagged
`.visually-hidden` vs `.sr-only` and `row-empty` color against `static/css/
main.css`. That legacy Flask stylesheet is NOT loaded in the webview — the
active styles are the widget's built-in `DEFAULT_STYLES`. Making the empty
marker visible text sidesteps the hidden-class question and is strictly more
accessible. **Follow-up:** adopt the design-system CSS (high-contrast, sticky
headers, row-empty) into the webview via inlined `styles=` — tracked for a
later phase.

**Verified:** `uv run pytest` → 28 passed. Loaded `Baofeng_BF-888.img`
(bounds 1–16), grid renders with scoped headers + empty markers, save
round-trips. Non-visible wx construction smoke test passes (Save disabled
pre-load, WebView2 backend present).

**Fix (post-launch feedback): no visible way to open a file.** User launched
and saw no controls (Phase 1 relied only on the native wx menu bar; the HTML
views had no buttons). Fixed, reviewed by accessibility-lead:
- Added a visible "Open Image File…" button on the welcome view (in a
  `<nav aria-label="Primary actions">`) and a `<nav aria-label="File actions">`
  with Open / Save / Save As / Close on the channel view. Buttons post over the
  bridge via inline `onclick` (set_content injects via innerHTML, so `<script>`
  in a fragment doesn't run, but inline handlers do).
- Wired `on_bridge_message` to dispatch open/save/save_as/close to the existing
  handlers, which announce results via the live region (rule #3).
- Fixed a latent accessibility bug: `welcome.html`/`channels.html` each added
  their own `<main>`, nesting inside the host's `<main id="content">` (two main
  landmarks). Removed the inner wrappers.
- Used `role="toolbar"` → labeled `<nav>` (toolbar would promise roving
  arrow-key focus we don't implement). `&hellip;` for ellipses.
- Verified: render contains the buttons, no nested `<main>`, dispatch routes
  correctly; 28 tests still pass.
- NOTE: still unexplained why the native menu bar wasn't visible for the user;
  the in-page buttons make it moot, and are the better accessible affordance.

**Fix #2 (post-launch feedback): Alt doesn't open the menu.** Root cause: the
embedded WebView2 captures the keyboard, so the native wx menu bar's Alt
activation/accelerators never reach wx. Consulted accessibility-lead +
keyboard-navigator; recommendation = in-page Ctrl-combo shortcuts bridged to
Python + visible buttons + `aria-keyshortcuts` + F1 help; remove the inert
native menu bar (it announces as operable to NVDA object-nav but does nothing).
Implemented:
- Removed the native menu bar (`GetMenuBar()` is now None).
- Global shortcuts handled in-page via a document-level keydown listener
  installed once on `EVT_WEBVIEW_LOADED` (run_js): Ctrl+O / Ctrl+S /
  Ctrl+Shift+S / F1, posted over the bridge. Gated against text-field typing;
  only our Ctrl(+Shift) combos intercepted (no NVDA quick-nav clash).
- `aria-keyshortcuts` on the buttons (NVDA announces "Open Image File, button,
  Control+O"); added Keyboard Shortcuts (F1) and About buttons to the welcome
  view, Keyboard Shortcuts to the channel view.
- F1 → accessible modal (`show_message`) listing shortcuts as a real table.
  Single source: `APP_SHORTCUTS` in app.py.
- Verified: menu bar gone, dispatch routes open/save/save_as/close/shortcuts/
  about/download/upload, templates carry aria-keyshortcuts; 28 tests pass.
- Updated docs/keyboard-map.md with the rationale and the new model.

**Open / next:**
- Still manual: relaunch, confirm Ctrl+O opens the dialog, F1 shows the
  shortcuts list, and NVDA announces the button shortcuts.
- Deferred within Phase 1: New (needs model picker), Open Recent, Open Stock
  Config — carry into a Phase 1 follow-up or fold into later phases.
- Legacy `static/js/*` and `templates/{base,index,settings}.html` remain
  Flask-era; superseded by `views.py` + `channels.html` for the grid.
- **Phase 2:** editable cells + full keyboard grid model.

---

## 2026-06-16 — Phase 0: Realignment & app shell

**Goal:** Reorient the project from the original Flask + PyWebView scaffold to
the chosen stack (wxPython + `wx-accessible-webview` + `prism`), and stand up a
launchable, screen-reader-readable app shell.

**Decisions (confirmed with user):**
- UI host = wxPython app + `AccessibleWebView` (semantic HTML in an embedded
  webview). NO Flask, NO PyWebView. Serial I/O will run on wx background
  threads (not SSE).
- Supplemental speech = `prism` (PyPI dist `prismatoid`, import name `prism`).
- CHIRP distribution = bundle into the Nuitka exe (pinned commit); ship updates
  as new VRP releases; optional in-app "Update CHIRP from GitHub" later. End
  users never git pull or rebuild.

**Done:**
- Cloned CHIRP into `./chirp`, **pinned at commit `6dadd6b`** (2026-06-10).
- `pyproject.toml`: declared `chirp` as an editable path source (so `uv sync`
  alone sets up the env); removed the invalid `[tool.uv] python-version` field;
  swapped Flask/PyWebView for `wxpython`, `wx-accessible-webview`, `prismatoid`;
  kept `jinja2` (templating without Flask). `uv sync --extra dev` clean.
- Verified the new deps import: wx 4.2.5, `wx_accessible_webview`
  (AccessibleWebView/AccessibleHtmlDialog/show_message/confirm/…), `prism`
  (Context → create_best → Backend.speak).
- Fixed a real CHIRP import bug: from the project root the `./chirp` repo dir
  shadowed the installed `chirp` package (editable finder appended after
  `PathFinder`, so `import chirp` resolved to an empty namespace and
  `CHIRP_VERSION` failed). Fix: `vrp/_chirp_path.py` moves `PathFinder` to the
  end of `sys.meta_path` before any chirp import; imported first by `vrp` and
  `tests/conftest.py`. Verified `import chirp` now resolves to `chirp/chirp`.
- New `vrp/` package: `app.py` (wx app, main window, File/Radio/Help menubar
  with Phase-0 stubs that announce "not yet implemented", `AccessibleWebView`
  host, `window.vrp.post()` bridge → `on_bridge_message`, About dialog),
  `html.py` (Jinja2 render + `render_view` that appends the mandatory CHIRP
  attribution footer), `speech.py` (graceful prism wrapper).
- `main.py` rewritten as a thin entry point (`--debug` flag).
- `templates/welcome.html` Phase-0 welcome view — **reviewed and approved by
  the accessibility-lead** (removed redundant `aria-labelledby`/`role="note"`;
  attribution handled centrally).
- `build.py` Nuitka flags updated to the new stack (wx/webview/prism/win32more/
  numpy/jinja2; dropped pywebview/flask). Full packaging deferred to Phase 9.
- Updated `CLAUDE.md` and `README.md` to the new architecture.

**Verified:** `uv run pytest` → 23 passed. Headless check: chirp imports, the
welcome view renders with attribution, speech degrades gracefully, `vrp.app`
imports without errors.

**Open / next:**
- Manual verification still owed: launch `uv run python main.py` and confirm the
  window opens and NVDA reads the welcome view (requires the WebView2 runtime
  on Windows). Not auto-launched to avoid popping a window unprompted.
- Legacy `templates/{base,index,settings}.html` and `static/js/*` still use
  Flask `url_for`/SSE; they'll be adapted to the bridge in Phase 1.
- **Phase 1:** Open/Save image files and render the channel grid (read-only)
  via `chirp_backend` + the bridge.
