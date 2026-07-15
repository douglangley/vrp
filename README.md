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
`run-win.bat --debug`.

**Any platform — manual:**

```bash
git clone https://github.com/douglangley/vrp.git
cd vrp
git clone --depth=1 https://github.com/kk7ds/chirp.git   # CHIRP must exist before sync
uv sync
uv run python main.py
```

You need [uv](https://docs.astral.sh/uv/) and git. uv downloads Python 3.11
itself, so your system Python version doesn't matter. VRP's UI is built entirely
from native wx controls (see "Architecture") — there is no webview or browser, so
no WebView2 runtime is required.

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
which wx exposes to MSAA/UIA so **NVDA** reads it. This is the only UI; there is
no webview or browser anywhere in the app.

This means:
- Every radio CHIRP supports, VRP supports automatically
- When CHIRP adds a new radio driver, VRP gets it too (just update the dependency)
- No forking, no rebasing patches, no maintaining a parallel codebase
- The accessible UI is completely separate from the radio driver code

## Relationship to CHIRP

VRP is built *on* CHIRP, not *instead of* CHIRP. Specifically:

- The `chirp` Python package (installed as a dependency from the CHIRP GitHub
  repository) provides all radio hardware communication and driver code
- VRP contributes the accessible front end: a wxPython app with a native
  `DataViewListCtrl` channel grid, native wx dialogs for editing, and a thin
  backend wrapping the CHIRP library
- The CHIRP library is used **unmodified** — VRP never patches driver files
- Both projects are GPLv3 licensed

Think of it like a new front end for an existing engine. The engine (CHIRP's
drivers) belongs to the CHIRP project and its contributors. VRP is the car
body around it.

We are grateful to Dan Smith (kk7ds) and all CHIRP contributors for the
enormous body of reverse-engineering work that makes 700+ radio models
programmable in open-source software.

## Features

VRP's UI is built entirely from native wx controls — a single front end on every
platform, with no webview or browser involved.

**The channel grid** is a `wx.dataview.DataViewListCtrl`: native NSTableView on
macOS (read directly by **VoiceOver**) and wx's generic custom-drawn control on
Windows (exposed to MSAA/UIA so **NVDA** reads it):
- No paging — every channel is populated at once
- Multi-select (Shift+Arrow for a contiguous block, Ctrl+Space for individual
  rows) drives in-place reordering: move up/down a slot or move-to a chosen
  channel, with the moved block re-selected and focused afterward
- Whole-row cut/copy/paste and channel-edit undo/redo
- Channel editing happens in a native wx dialog (F2/Enter); the grid itself is
  read-only/navigable
- A single native menu bar carries both mnemonics and Ctrl-combo accelerators
  together; F1 lists every shortcut

**Backed by:**
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
- Packages as a Windows installer (Inno Setup) wrapping a PyInstaller build

## Architecture

```
main.py                  Entry point: launches the native UI (--debug flag).
vrp/
  native/                 The UI: native wx.dataview.DataViewListCtrl grid +
                         wx.MenuBar (no webview, no JS bridge).
    app.py                Entry point (vrp.native.app.run).
    main_window.py        MainWindow: menu bar, status bar, grid, and all
                         command handlers.
    channel_grid.py       ChannelGrid: wx.dataview.DataViewListCtrl — native
                         NSTableView on macOS (VoiceOver), wx's generic
                         custom-drawn control on Windows exposed to MSAA (NVDA);
                         no paging.
    grid_model.py         Pure data/selection model behind the grid (no wx).
    announce.py           Announcer: status bar + prism speech.
  edit_dialog.py          Native wx dialog to edit one channel.
  ops_dialog.py           Native wx dialog for bulk operations.
  find_dialog.py          Native wx Find dialog.
  serial_dialogs.py       Native wx Download / Upload / favorites / progress dialogs.
  settings_dialog.py      Native wx radio settings editor, Treebook.
  bank_dialog.py          Native wx dialog to assign a channel to banks.
  query_dialogs.py        Native wx query-source param + import dialogs.
  prefs_dialog.py         Native wx Preferences dialog.
  info_dialog.py          Read-only multiline edit box (Radio Info / details).
  config.py               Persistent JSON config (prefs + recent files + favorites).
  speech.py               prism speech wrapper, graceful no-op if unavailable.
  _chirp_path.py          Makes the editable ./chirp package importable.
chirp_backend/
  radio.py               Wraps chirp library: load image, read/write memories,
                         serial port download/upload, describe_model.
  memory_ops.py          Field edits + range operations: set/update channel,
                         move, copy, delete+shift, sort, arrange, find/goto.
  undo.py                Channel-edit undo/redo (UndoManager).
  col_defs.py            Column definitions mirroring CHIRP's column hierarchy.
  bank_ops.py            Bank membership operations (assign channels to banks).
  bandplan.py            Suggested repeater offset + band defaults, by region.
  query.py               Online query-source registry + threaded fetch runner.
  serial_trace.py        Byte-level serial trace (written under --debug).
tests/                   Unit tests (no radio hardware needed).
tools/
  update_chirp.py        Fetches/tests/pins a new CHIRP commit.
build.py                 PyInstaller build script.
pyproject.toml           uv-managed project definition (Python 3.11 pinned).
```

`vrp/native/main_window.py` binds each command straight to a `wx.MenuBar` item —
the accelerator in the item's label (e.g. `"&Save\tCtrl+S"`) *is* the global
shortcut. `vrp/native/channel_grid.py` is a `wx.dataview.DataViewListCtrl` —
native NSTableView on macOS (VoiceOver) and wx's generic custom-drawn control on
Windows, exposed to MSAA/UIA so NVDA reads its rows; it's populated with every
channel at once, no paging. Channel editing is in a native dialog (F2/Enter), so
the grid stays read-only/navigable. There's no web server, webview, or JS bridge:
handlers call `chirp_backend` directly and push results to the grid
(`refresh_numbers`/`rebuild`) and to `vrp/native/announce.py`'s `Announcer`
(status bar + optional prism speech). `prism`/`prismatoid` provides the
supplemental speech.

> **History:** VRP once shipped a second, embedded-webview UI (an
> `AccessibleWebView` hosting an editable HTML grid) for screen readers that
> couldn't read the native grid. Once the native `DataViewListCtrl` was confirmed
> to read on every screen reader, that UI — and its `wx-accessible-webview`,
> `wx-accessible-menubar`, and `jinja2` dependencies — was removed
> (PROGRESS_LOG.md "2026-06-29").

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

# Install build extras and build the app folder + Windows installer
uv sync --extra build
uv run python build.py --installer   # needs Inno Setup 6 for the installer
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
build, doesn't compile them — it usually finishes in under a minute. By default
`build.py` produces a **onedir** `dist/vrp/` folder (instant startup — no
per-launch self-extraction), and `--installer` then wraps it with **Inno Setup**
into `dist/vrp-<version>-setup.exe` (Start-menu shortcut + uninstaller). Use
`--onefile` only for a quick throwaway single-exe test. (There is no double-click
`build.bat` wrapper; building is a deliberate release step. Testers and end users
run from source via `run-win.bat` / `run-mac.sh`.)

`build.py` bundles `prism` with `--collect-binaries=prism` — **required**, not
optional: prism dlopens a native `prism.dll` from `prism/_native/`, which
PyInstaller doesn't bundle on its own, and without it `import prism` raises
`FileNotFoundError` and the app runs **silent**. That matters because the
Windows cell cursor (Left/Right) has no other voice. It costs about 1 MB;
`win32more`/`numpy` stay excluded as guards but prism imports neither (only
`cffi`). `build.py` also explicitly collects `chirp.drivers`, since CHIRP loads
drivers via dynamic import that PyInstaller's static analysis can't follow.

Before building, `build.py` enforces the CHIRP pin: it checks that `./chirp` is
at the `CHIRP_COMMIT` SHA and syncs a clean clone to it automatically, so the
build always bundles the exact, tested driver set. It never pulls from the
network — adopting a newer CHIRP is the deliberate, tested step in
`tools/update_chirp.py`. Pass `--no-chirp-sync` to verify only (abort on a
mismatch rather than fixing the clone).

## Releases (dates, not version numbers)

VRP releases are named for the day they were cut:

```
VRP-20260715.1     the first release cut on 15 July 2026
VRP-20260715.2     a second release the same day
VRP-20260716.1     the next day's first release
```

The version string is `YYYYMMDD.N` (`VRP-` prefixes the git tag and the release
artifacts). `N` starts at 1 each day and increments for each further release that
day. There is no semantic-version meaning to read into it — **the newest date is
simply the newest build**, which is all a tester needs to know.

The version lives in `vrp/__init__.py` (`__version__`, what the app and
`build.py` read) and `pyproject.toml`, which must agree; `tools/release_version.py`
writes both and a test asserts they match. To cut a release:

```bash
uv run python tools/release_version.py --bump    # 20260715.1 -> 20260715.2, or a new day -> .1
uv run python -m pytest
uv run python build.py --portable                # or --installer
git commit -am "chore(release): VRP-20260715.2" && git tag VRP-20260715.2
```

`--show` prints the current version, `--set <version>` forces one, and `--check`
verifies the two version files agree. The About box shows the exact version plus
a **speakable** rendering of it ("Release 1 of 15 July 2026") — a screen reader
reads the bare `20260715.1` as one huge number, which tells the user nothing.

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

## Packaging with PyInstaller + Inno Setup

Target: Python 3.11, Windows x64 primary (Linux secondary).

The pipeline is two steps: PyInstaller freezes the app into a `dist/vrp/`
**onedir** folder, then Inno Setup (`installer.iss`) wraps that folder into a
`dist/vrp-<version>-setup.exe` installer. `build.py --installer` runs both. This
mirrors how upstream CHIRP ships its own PyInstaller build (a real installer with
a Start-menu shortcut and uninstaller, not a loose self-extracting `.exe`).

**`build.py --portable`** is the no-install alternative: it zips the same onedir
folder into `dist/VRP-<version>-win64.zip`, whose single top-level directory is
named for the release (`VRP-20260715.1/`) rather than `vrp/`. A tester unzips it
anywhere and runs `vrp.exe` from the folder — nothing is installed, and two
releases unzipped side by side stay separate instead of merging. Handy for
handing a build to a few people without an installer; `--installer` is still how
the app is meant to ship broadly. The two are combinable.

Why onedir over onefile: onefile re-extracts the whole interpreter + wxPython +
552 drivers to a temp dir on *every* launch (multi-second cold start) and is a
frequent Defender/SmartScreen false-positive trigger; onedir launches instantly.
UPX is deliberately not used — it barely shrinks a wx app and is itself an AV
trigger. The installer (`--installer`) needs Inno Setup 6
(https://jrsoftware.org/isinfo.php); `build.py` finds `ISCC.exe` on PATH or in
the default install dir, or honors `INNO_SETUP_ISCC`. The installer's `AppId`
GUID in `installer.iss` must stay stable across releases so upgrades replace the
prior install instead of stacking side by side.

Build command is in `build.py`. Key PyInstaller flags required:

```
--windowed                       GUI app, no console window
--collect-binaries=prism         prism's native prism.dll — REQUIRED, or speech dies silently
--exclude-module=win32more       guard only; prism does not import it (Nuitka-era bloat)
--exclude-module=numpy           guard only; not a prism dependency
--collect-submodules=chirp.drivers   dynamic __import__ — must be explicit
--collect-data=lark              .lark grammar files (chirp.bitwise_grammar)
--add-data=...chirp/stock_configs    the "Frequency lists" CSVs (data, not modules)
```

wxPython, `wx_accessible_grid`, and pyserial don't need explicit flags —
PyInstaller's import analysis follows them automatically since they're imported
directly (no dynamic `__import__`). The native UI renders no HTML, so there are
no `static/`/`templates/` data dirs to bundle.

Previously built with Nuitka (see PROGRESS_LOG.md "Phase 9"), which compiled
all 552 CHIRP drivers to C and took 20–30 minutes per build. PyInstaller just
freezes bytecode, so the same build finishes in well under a minute — switched
for faster iteration. Nuitka isn't worth revisiting: the 552 drivers are loaded
by dynamic `__import__`, so it can't follow them without force-compiling all of
them (back to the 20–30 min builds), and it yields no size or startup win for a
wx GUI that idles on serial I/O.

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
