# Versatile Radio Programmer (VRP)

**VRP** is a free, open-source, accessible radio memory channel programmer
for amateur radio operators. It lets you read and write memory channels on
hundreds of radio models — fully accessible to screen reader users (NVDA,
JAWS, VoiceOver).

## Quick start (run from source)

**Windows — one step:** install the two prerequisites once, then double-click
`run.bat` (or run it from a terminal):

- **uv** — `winget install --id=astral-sh.uv`
- **git** — https://git-scm.com/download/win

`run.bat` clones the CHIRP library, downloads Python 3.11 and all dependencies
(first run only), and launches the app. Later runs just launch.

**Any platform — manual:**

```bash
git clone https://github.com/douglangley/vrp.git
cd vrp
git clone --depth=1 https://github.com/kk7ds/chirp.git   # CHIRP must exist before sync
uv sync
uv run python main.py
```

You need [uv](https://docs.astral.sh/uv/) and git. uv downloads Python 3.11
itself, so your system Python version doesn't matter. On Windows the Microsoft
Edge **WebView2 runtime** (preinstalled on Windows 11) renders the channel grid;
without it the grid falls back to a plain text view.

To run the tests: `uv sync --extra dev` then `uv run pytest`. To build the
standalone .exe: `build.bat` (see "Packaging with PyInstaller").

## Why VRP exists

Programming amateur radios requires software. The dominant open-source tool
for this is [CHIRP](https://chirpmyradio.com), which has excellent radio
support (700+ models) but a graphical interface that is inaccessible to
blind and low-vision users. The CHIRP project has stated there are no plans
to address this.

VRP solves the problem differently: rather than patching CHIRP's GUI, it
uses the CHIRP *library* as a backend — keeping all the radio driver code
exactly as the CHIRP team maintains it — and provides a new, fully accessible
desktop front end: a wxPython app that renders proper HTML semantics and ARIA
in an embedded, screen-reader-friendly webview.

This means:
- Every radio CHIRP supports, VRP supports automatically
- When CHIRP adds a new radio driver, VRP gets it too (just update the dependency)
- No forking, no rebasing patches, no maintaining a parallel codebase
- The accessible UI is completely separate from the radio driver code

## Relationship to CHIRP

VRP is built *on* CHIRP, not *instead of* CHIRP. Specifically:

- The `chirp` Python package (installed as a dependency from the CHIRP GitHub
  repository) provides all radio hardware communication and driver code
- VRP contributes the accessible front end: a wxPython app that renders
  semantic HTML/ARIA in an embedded webview, with native wx dialogs for editing
  and a thin backend wrapping the CHIRP library
- The CHIRP library is used **unmodified** — VRP never patches driver files
- Both projects are GPLv3 licensed

Think of it like a new front end for an existing engine. The engine (CHIRP's
drivers) belongs to the CHIRP project and its contributors. VRP is the car
body around it.

We are grateful to Dan Smith (kk7ds) and all CHIRP contributors for the
enormous body of reverse-engineering work that makes 700+ radio models
programmable in open-source software.

## Features

- Accessible read-only channel grid (real HTML table) hosted in an embedded
  webview — works with NVDA/JAWS; large radios are paged (100 channels/page)
- **(Preview)** An editable channel grid via the `wx-accessible-grid` library —
  a real `<table role="grid">` with in-cell text/combo/checkbox editing, row
  selection, and delete, read/written through CHIRP's own validation. NVDA-on-
  Windows verification is owed before it replaces the read-only grid above;
  try it standalone with `uv run python tools/grid_preview.py`
- Editing in native wx dialogs (first-class screen-reader support): per-channel
  field editor, bulk operations, find, settings, banks, download/upload
- Bulk operations (delete, delete+shift, insert, move, copy, sort, arrange) over
  a From/To range or an advanced channel list (e.g. `1-5,8,10-12`) — no drag/drop
- Find / Find Next (frequency, name, or comment) with wrap-around
- Download from / upload to radio with live progress announcements (background thread)
- Radio settings editor, banks editor, and online query sources (AMSAT, SatNOGS;
  more sources are incremental)
- Reachable three ways and kept in sync: native menu bar, in-page buttons, and
  global Ctrl-combo keyboard shortcuts (F1 lists them). Menu-bar Alt/F10
  keyboard access is provided by the `wx-accessible-menubar` library, which
  works around a focused WebView2 swallowing Alt (wx #24786)
- High contrast and forced-colors (Windows High Contrast) support
- Packages as a single self-contained .exe (Windows) via PyInstaller

## Architecture

```
main.py                  Thin entry point: applies the chirp path fix, runs app.
vrp/                     wxPython UI layer (the accessible front end).
  app.py                 wx app/window, native menu bar (wx-accessible-menubar),
                         AccessibleWebView host, the window.vrp.postMessage()
                         bridge, keyboard shortcuts, paging, and all command
                         handlers.
  views.py               Renders channel-grid pages (read-only) and single rows.
  channel_grid_model.py  GridModel adapter for the wx-accessible-grid editable
                         grid preview (see tools/grid_preview.py).
  edit_dialog.py         Native wx dialog to edit one channel.
  ops_dialog.py          Native wx dialog for bulk operations.
  find_dialog.py         Native wx Find dialog.
  serial_dialogs.py      Native wx Download / Upload / progress dialogs.
  settings_dialog.py     Native wx radio settings editor (Treebook).
  bank_dialog.py         Native wx dialog to assign a channel to banks.
  query_dialogs.py       Native wx query-source param + import dialogs.
  prefs_dialog.py        Native wx Preferences dialog.
  config.py              Persistent JSON config (preferences + recent files).
  html.py                Jinja2 rendering to HTML strings + CHIRP attribution.
  speech.py              prism speech wrapper (graceful no-op if unavailable).
  _chirp_path.py         Makes the editable ./chirp package importable.
chirp_backend/
  radio.py               Wraps chirp library: load image, read/write memories,
                         serial port download/upload.
  memory_ops.py          Field edits + range operations: set/update channel,
                         move, copy, delete+shift, sort, arrange, find/goto.
  col_defs.py            Column definitions mirroring CHIRP's column hierarchy.
  bank_ops.py            Bank membership operations (assign channels to banks).
  query.py               Online query-source registry + threaded fetch runner.
static/
  css/main.css           Design-system styles, retained for future inlining
                         into the webview (not currently loaded).
templates/
  welcome.html           Welcome view (body fragment).
  channels.html          Memory channel grid (read-only, paged).
  _row_macro.html        Shared macro for one channel row.
tests/                   Unit tests (no radio hardware needed).
tools/
  update_chirp.py        Fetches/tests/pins a new CHIRP commit.
  grid_preview.py        Standalone harness for the wx-accessible-grid preview
                         (loads a CHIRP test image; no full app or radio needed).
build.py                 PyInstaller build script.
pyproject.toml           uv-managed project definition (Python 3.11 pinned).
```

Interactive behavior is small inline `onclick`/`onkeydown` handlers in the view
fragments (plus a global keyboard listener injected via `run_js`); both bridge
to Python with `window.vrp.postMessage(...)`. The UI host is the
`wx-accessible-webview` package (an `AccessibleWebView` wrapping
`wx.html2.WebView`); the native menu bar's keyboard access (Alt / Alt+mnemonic /
F10 against WebView2 swallowing Alt, wx #24786) comes from `wx-accessible-menubar`;
an in-progress editable channel grid (see Features above) uses
`wx-accessible-grid`. `prism`/`prismatoid` provides supplemental speech. There
is no Flask server and no PyWebView.

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
uv run pytest

# Run the desktop app
uv run python main.py

# Experimental Toga prototype (opt-in extra)
uv run --extra toga python main_toga.py

```

The Toga launcher is a parallel prototype. The wxPython app launched by
`uv run python main.py` remains the production UI, and the Toga prototype stays
opt-in through `uv run --extra toga python main_toga.py`, until the native Toga
table passes the screen-reader checklist in
`docs/toga-accessibility-checklist.md`.

```bash
# (optional) debug logging
uv run python main.py --debug

# Install build extras and compile to a single executable with PyInstaller
uv sync --extra build
uv run python build.py
```

Or just run **`build.bat`** (Windows) — it installs the build deps, runs the
build with live output saved to a timestamped `build_*.log`, and reports
success/failure. The build bundles all 552 CHIRP drivers but, unlike the
previous Nuitka-based build, doesn't compile them — it usually finishes in
under a minute.

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

The tested CHIRP commit is pinned in the **`CHIRP_COMMIT`** file; `run.bat` clones
CHIRP and checks out exactly that commit, so everyone runs the same code. The
update script fetches the latest CHIRP, runs the test suite, and — only if it
passes — bumps `CHIRP_COMMIT` to the new commit (rolling `./chirp` back to the
pin on failure). After a successful bump, commit `CHIRP_COMMIT` and rebuild.

Current pin: `6dadd6b` (2026-06-10). (An optional in-app "Update CHIRP from
GitHub" for advanced users is a possible future addition; not part of the normal
flow.)

## Testing Without a Radio

CHIRP ships test image files in `chirp/tests/images/` — one .img per supported
radio model. These can be loaded directly to test the UI and all memory
operations without any hardware. The test suite in `tests/` uses these.

Run the suite with `uv run pytest` (it's fast — about two seconds).

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
