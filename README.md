# Versatile Radio Programmer (VRP)

**VRP** is a free, open-source, accessible radio memory channel programmer
for amateur radio operators. It lets you read and write memory channels on
hundreds of radio models — fully accessible to screen reader users (NVDA,
JAWS, VoiceOver).

## Quick start (run from source)

**Windows — one step:** install the two prerequisites once, then double-click
`run-win.bat` (or run it from a terminal):

- **uv** — `winget install --id=astral-sh.uv`
- **git** — https://git-scm.com/download/win

**macOS — one step:** install the two prerequisites once, then run
`./run-mac.sh` from a terminal:

- **uv** — `curl -LsSf https://astral.sh/uv/install.sh | sh`
- **git** — `xcode-select --install` (Xcode Command Line Tools)

`run-win.bat`/`run-mac.sh` clone the CHIRP library, download Python 3.11 and
all dependencies (first run only), and launch the app. Later runs just
launch. Either script forwards extra arguments to `main.py`, e.g.
`run-win.bat --debug` or `./run-mac.sh --webview`.

**Any platform — manual:**

```bash
git clone https://github.com/douglangley/vrp.git
cd vrp
git clone --depth=1 https://github.com/kk7ds/chirp.git   # CHIRP must exist before sync
uv sync
uv run python main.py
```

You need [uv](https://docs.astral.sh/uv/) and git. uv downloads Python 3.11
itself, so your system Python version doesn't matter. VRP runs its native wx UI
on every platform by default (see "Architecture"), so the webview UI's Microsoft
Edge WebView2 runtime (preinstalled on Windows 11) is only needed if you force
the old UI with `--webview`.

To run the tests: `uv sync --extra dev` then `uv run python -m pytest`. To build the
standalone .exe (a deliberate release step — testers and end users should just
run from source with the run scripts above): `uv sync --extra build` then
`uv run python build.py` (see "Packaging with PyInstaller").

## Why VRP exists

Programming amateur radios requires software. The dominant open-source tool
for this is [CHIRP](https://chirpmyradio.com), which has excellent radio
support (700+ models) but a graphical interface that is inaccessible to
blind and low-vision users. The CHIRP project has stated there are no plans
to address this.

VRP solves the problem differently: rather than patching CHIRP's GUI, it
uses the CHIRP *library* as a backend — keeping all the radio driver code
exactly as the CHIRP team maintains it — and provides a new, fully accessible
desktop front end built from native wx controls. Its channel grid is a
`wx.dataview.DataViewListCtrl` — a real native control (NSTableView) on macOS,
read directly by **VoiceOver**, and wx's generic custom-drawn control on Windows,
which wx exposes to MSAA/UIA so **NVDA** reads it. This native UI is the default on every
platform. (An older embedded-webview UI, which hosted an accessible HTML grid,
is still reachable with `--webview` while it is retired; its remaining intended
role is rendering in-app help and documentation.)

This means:
- Every radio CHIRP supports, VRP supports automatically
- When CHIRP adds a new radio driver, VRP gets it too (just update the dependency)
- No forking, no rebasing patches, no maintaining a parallel codebase
- The accessible UI is completely separate from the radio driver code

## Relationship to CHIRP

VRP is built *on* CHIRP, not *instead of* CHIRP. Specifically:

- The `chirp` Python package (installed as a dependency from the CHIRP GitHub
  repository) provides all radio hardware communication and driver code
- VRP contributes the accessible front end: a wxPython app with two
  platform-appropriate channel-grid UIs, native wx dialogs for editing, and a
  thin backend wrapping the CHIRP library
- The CHIRP library is used **unmodified** — VRP never patches driver files
- Both projects are GPLv3 licensed

Think of it like a new front end for an existing engine. The engine (CHIRP's
drivers) belongs to the CHIRP project and its contributors. VRP is the car
body around it.

We are grateful to Dan Smith (kk7ds) and all CHIRP contributors for the
enormous body of reverse-engineering work that makes 700+ radio models
programmable in open-source software.

## Features

VRP's production UI is built from native wx controls and is the default on every
platform; an older webview UI is retained behind `--webview` while retired. Both
share the same backend, native dialogs, and feature set.

**Native UI (the default everywhere)** — a `wx.dataview.DataViewListCtrl`
channel grid: native NSTableView on macOS (read directly by **VoiceOver**) and
wx's generic custom-drawn control on Windows (exposed to MSAA/UIA so **NVDA**
reads it), with no webview involved:
- No paging — every channel is populated at once
- Multi-select (Shift+Arrow for a contiguous block, Ctrl+Space for individual
  rows) drives in-place reordering: move up/down a slot or move-to a chosen
  channel, with the moved block re-selected and focused afterward
- Channel editing happens in a native wx dialog (F2/Enter); the grid itself is
  read-only/navigable
- A single native menu bar carries both mnemonics and Ctrl-combo accelerators
  together (no WebView2 to fight); F1 lists every shortcut

**Webview UI (`--webview`, retired)** — an `AccessibleWebView` hosting an
editable `AccessibleGrid` (from `wx-accessible-grid`), read by VoiceOver; no
longer the default on any platform, kept working while retired (intended future
role: help/docs rendering):
- Real in-place cell editing (text/combo) with CHIRP's own validation
- Select All Channels (Ctrl+A) / Clear Selection on the Edit menu; row actions
  (select, edit, delete) via the Applications key, Shift+F10, or VoiceOver's
  VO+Shift+M
- A `wx-accessible-menubar`-driven menu bar that works around a focused
  WebView2 swallowing Alt (wx #24786)

**Both UIs share:**
- Editing in native wx dialogs (first-class screen-reader support): per-channel
  field editor, bulk operations, find, settings, banks, download/upload
- Bulk operations (delete, delete+shift, insert, move, copy, sort, arrange) over
  a From/To range or an advanced channel list (e.g. `1-5,8,10-12`) — no drag/drop
- Suggested repeater offset from CHIRP's band plan when you enter a frequency
  (magnitude only — you pick the +/- direction); optional band-plan defaults for
  mode/step/tone; band-plan region selectable in Preferences
- Find / Find Next (frequency, name, or comment) with wrap-around
- Download from / upload to radio with live progress announcements (background
  thread), favorite-radios list, and a "Radio details" view of any model's specs
- Radio settings editor, banks editor, and online query sources (AMSAT, SatNOGS;
  more sources are incremental)
- High contrast and forced-colors (Windows High Contrast) support
- Packages as a single self-contained .exe (Windows) via PyInstaller

## Architecture

```
main.py                  Entry point: parse_mode() returns the native UI on
                         every platform; --webview/--native override.
vrp/
  native/                 NATIVE UI (the default on every platform): native
                         wx.dataview.DataViewListCtrl grid + wx.MenuBar.
    app.py                Entry point (vrp.native.app.run).
    main_window.py        MainWindow: menu bar, status bar, grid, and all
                         command handlers.
    channel_grid.py       ChannelGrid: wx.dataview.DataViewListCtrl — native
                         NSTableView on macOS (VoiceOver), wx's generic
                         custom-drawn control on Windows exposed to MSAA (NVDA);
                         no paging.
    grid_model.py         Pure data/selection model behind the grid (no wx).
    announce.py           Announcer: status bar + prism speech.
  app.py                  WEBVIEW UI (retained behind --webview, retired): wx
                         app/window, native menu bar (wx-accessible-menubar),
                         AccessibleWebView host, the editable AccessibleGrid
                         channel view, the window.vrp.postMessage() bridge,
                         keyboard shortcuts, and all command handlers.
  views.py                Webview UI: welcome-view rendering. Its read-only
                         paged-table/row-render functions remain as an
                         internal fallback (`if self._grid is None` branches
                         in vrp/app.py) but aren't reached in normal
                         operation — the production channel view is the
                         AccessibleGrid below.
  edit_dialog.py          Native wx dialog to edit one channel (shared by both UIs).
  ops_dialog.py           Native wx dialog for bulk operations (shared).
  find_dialog.py          Native wx Find dialog (shared).
  serial_dialogs.py       Native wx Download / Upload / progress dialogs (shared).
  settings_dialog.py      Native wx radio settings editor, Treebook (shared).
  bank_dialog.py          Native wx dialog to assign a channel to banks (shared).
  query_dialogs.py        Native wx query-source param + import dialogs (shared).
  prefs_dialog.py         Native wx Preferences dialog (shared).
  config.py               Persistent JSON config (preferences + recent files, shared).
  html.py                 Webview UI: Jinja2 rendering to HTML strings + CHIRP attribution.
  speech.py               prism speech wrapper, graceful no-op if unavailable (shared).
  _chirp_path.py          Makes the editable ./chirp package importable (shared).
chirp_backend/
  radio.py               Wraps chirp library: load image, read/write memories,
                         serial port download/upload.
  memory_ops.py          Field edits + range operations: set/update channel,
                         move, copy, delete+shift, sort, arrange, find/goto.
  col_defs.py            Column definitions mirroring CHIRP's column hierarchy.
  bank_ops.py            Bank membership operations (assign channels to banks).
  query.py               Online query-source registry + threaded fetch runner.
static/
  css/main.css           Webview UI only: design-system styles, retained
                         for future inlining into the webview (not currently loaded).
templates/
  welcome.html           Webview UI: welcome view (body fragment).
  channels.html          Webview UI: read-only paged-table fallback (unreached
                         in normal operation — see views.py above).
  _row_macro.html        Shared macro for one channel row, used by channels.html.
tests/                   Unit tests (no radio hardware needed).
tools/
  update_chirp.py        Fetches/tests/pins a new CHIRP commit.
build.py                 PyInstaller build script.
pyproject.toml           uv-managed project definition (Python 3.11 pinned).
```

**Native UI (the default on every platform):** `vrp/native/main_window.py` binds
each command straight to a `wx.MenuBar` item — the accelerator in the item's
label (e.g. `"&Save\tCtrl+S"`) *is* the global shortcut, since a real native
menu has no WebView2 fighting it for Alt/Ctrl. `vrp/native/channel_grid.py` is a
`wx.dataview.DataViewListCtrl` — native NSTableView on macOS (VoiceOver) and
wx's generic custom-drawn control on Windows, exposed to MSAA/UIA so NVDA reads
its rows; it's populated with every channel at once, no paging. Channel
editing is in a native dialog (F2/Enter), so the grid stays read-only/navigable.
There's no JS bridge: handlers call `chirp_backend` directly and push results to
the grid (`refresh_numbers`/`rebuild`) and to `vrp/native/announce.py`'s
`Announcer` (status bar + optional prism speech). Several native wx dialogs
(edit, bulk ops, find, settings, banks, download/upload, preferences) are shared
with the webview UI unchanged.

**Webview UI (`--webview`, retired):** the channel grid is `wx-accessible-grid`'s
`AccessibleGrid` (a real, editable `<table role="grid">`, driven by
`ChannelGridModel`) — VoiceOver reads each cell's name (channel + column
header + value + control type) composed via `aria-labelledby`, since
VoiceOver never receives the runtime's live-region announcement on cell move.
Everything else (menu bar, dialogs, find, settings) is small inline
`onclick`/`onkeydown` handlers in the view fragments (plus a global keyboard
listener injected via `run_js`), bridged to Python with
`window.vrp.postMessage(...)`. The native menu bar's keyboard access (Alt /
Alt+mnemonic / F10 against WebView2 swallowing Alt, wx #24786) comes from
`wx-accessible-menubar`. `prism`/`prismatoid` provides supplemental speech in
both UIs. There is no Flask server and no PyWebView in either.

## Development Setup

This project uses [uv](https://docs.astral.sh/uv/) to manage the Python
version and virtual environment. uv pins Python 3.11 for this project via
`.python-version`, regardless of what Python version you have system-wide.

```bash
# Install uv if you don't have it (one-time)
# Windows:  winget install --id=astral-sh.uv
# Linux/Mac: curl -LsSf https://astral.sh/uv/install.sh | sh

# Clone CHIRP library into the project directory (the radio driver backend).
# Do this BEFORE uv sync — CHIRP is declared as an editable path dependency.
git clone --depth=1 https://github.com/kk7ds/chirp.git

# Create the venv with Python 3.11 and install all dependencies (incl. the
# editable ./chirp and dev tools). uv downloads Python 3.11 automatically if
# needed — your system Python version doesn't matter.
uv sync --extra dev

# Run tests (no radio hardware needed — uses chirp/tests/images/)
# Use `python -m pytest`, not `uv run pytest`, so it always runs in the project
# venv rather than falling back to a global pytest on PATH.
uv run python -m pytest

# Run the desktop app
uv run python main.py

# (optional) debug logging
uv run python main.py --debug

# Install build extras and compile to a single executable with PyInstaller
uv sync --extra build
uv run python build.py
```

When `--debug` is set, a download/upload to a radio writes a byte-level
**serial trace** (every byte sent/received, with timestamps and explicit
`# timeout` markers) to `serial-trace.txt` in the current working directory —
i.e. the project root when you launch with `uv run python main.py --debug`
from the repo. The file is overwritten on each clone session; its path is
logged when the clone starts. This is the primary artifact for diagnosing a
radio that won't talk over the cable — attach it when reporting a
download/upload problem. (It's gitignored.)

The build bundles all 552 CHIRP drivers but, unlike the previous Nuitka-based
build, doesn't compile them — it usually finishes in under a minute. (There is
no double-click `build.bat` wrapper; building is a deliberate release step run
with `uv run python build.py`. Testers and end users run from source via
`run-win.bat` / `run-mac.sh`.)

`build.py` excludes `prism`/`win32more`/`numpy` (prism pulls in the whole
win32more Windows-API surface; speech is opt-in and no-ops without it), and
explicitly collects `chirp.drivers`/`chirp.sources` since CHIRP loads both
via dynamic import that PyInstaller's static analysis can't follow on its own.

## Files NOT to Modify

- `chirp/`  — The upstream CHIRP library. Update via `git pull` only.
  Never edit files inside this directory. If a driver has a bug, report
  it upstream to the CHIRP project.

## Updating CHIRP

CHIRP is vendored at `./chirp`, pinned to a tested commit, and **bundled into the
VRP executable**. End users never pull CHIRP or rebuild — new radio support ships
as a new VRP release. To update CHIRP during development:

```bash
uv run python tools/update_chirp.py
```

The tested CHIRP commit is pinned in the **`CHIRP_COMMIT`** file; `run-win.bat`/
`run-mac.sh` clone CHIRP and check out exactly that commit, so everyone runs
the same code. The
update script fetches the latest CHIRP, runs the test suite, and — only if it
passes — bumps `CHIRP_COMMIT` to the new commit (rolling `./chirp` back to the
pin on failure). After a successful bump, commit `CHIRP_COMMIT` and rebuild.

Current pin: `906e039` (2026-06-25). (An optional in-app "Update CHIRP from
GitHub" for advanced users is a possible future addition; not part of the normal
flow.)

## Testing Without a Radio

CHIRP ships test image files in `chirp/tests/images/` — one .img per supported
radio model. These can be loaded directly to test the UI and all memory
operations without any hardware. The test suite in `tests/` uses these.

Run the suite with `uv sync --extra dev` then `uv run python -m pytest` (it's
fast — about two seconds).

## Packaging with PyInstaller

Target: Python 3.11, Windows x64 primary (Linux secondary).

Build command is in `build.py`. Key flags required:

```
--windowed                       GUI app, no console window
--exclude-module=prism           speech is opt-in/off by default — don't bundle it
--exclude-module=win32more       prism's WebView2/win32 bindings — same reason
--exclude-module=numpy           prism dependency — same reason
--collect-submodules=chirp.drivers   dynamic __import__ — must be explicit
--collect-submodules=chirp.sources   dynamic importlib.import_module — must be explicit
--collect-data=chirp             stock_configs, locale, etc.
--collect-data=lark              .lark grammar files (chirp.bitwise_grammar)
--add-data=static;static         (POSIX: static:static)
--add-data=templates;templates   (POSIX: templates:templates)
```

wxPython, `wx_accessible_webview`, jinja2/markupsafe, and pyserial don't need
explicit flags — PyInstaller's import analysis follows them automatically
since they're imported directly (no dynamic `__import__`).

Previously built with Nuitka (see PROGRESS_LOG.md "Phase 9"), which compiled
all 552 CHIRP drivers to C and took 20–30 minutes per build. PyInstaller just
freezes bytecode, so the same build finishes in well under a minute — switched
for faster iteration.

## Attribution

Radio driver support provided by the [CHIRP project](https://chirpmyradio.com) — chirpmyradio.com.

CHIRP is the work of Dan Smith (kk7ds) and a large community of contributors
who have spent years reverse-engineering the serial protocols and memory formats
of hundreds of radio models. VRP would not exist without that work. If you find
CHIRP useful (and through VRP you are using it), consider contributing to the
CHIRP project — reporting bugs, testing new drivers, or donating via their
download page.

## License

GPLv3 — see LICENSE file.

VRP incorporates the CHIRP radio driver library, copyright Dan Smith and CHIRP
contributors, also GPLv3. See LICENSE for full attribution.
