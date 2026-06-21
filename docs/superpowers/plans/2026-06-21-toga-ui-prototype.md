# Toga UI Prototype Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a parallel BeeWare Toga prototype for VRP with a native `toga.Table` channel list while preserving the existing wxPython application.

**Architecture:** Add `main_toga.py` and a focused `vrp_toga/` package. Keep CHIRP/image behavior in `chirp_backend/`, keep wx code untouched, and put Toga-only table adaptation, command metadata, app shell, and accessibility verification in new files.

**Scope note:** Open Recent is deferred in this prototype. The shared backend may still record recent files, but the Toga UI does not surface a recent-files menu yet.

**Tech Stack:** Python 3.11, BeeWare Toga 0.5.x, `toga-dummy` for import/smoke checks, existing CHIRP backend, pytest.

---

## File Structure

- Modify: `pyproject.toml`
  - Keep `toga>=0.5.4` out of base runtime dependencies.
  - Add a `toga` optional dependency and keep Toga packages in `dev` for non-visual smoke checks.
- Modify: `uv.lock`
  - Regenerate with `uv lock` after dependency changes.
- Create: `main_toga.py`
  - Thin launcher that imports `vrp` first for the CHIRP import-path fix, then runs `vrp_toga.app.main()`.
- Create: `vrp_toga/__init__.py`
  - Package metadata only.
- Create: `vrp_toga/table_model.py`
  - Pure adapter from loaded CHIRP memory data to `toga.Table` headings/accessors/row dictionaries and page status text.
- Create: `vrp_toga/commands.py`
  - Pure command metadata and enabled-state helpers shared by tests and the Toga app.
- Create: `vrp_toga/app.py`
  - Toga `App` subclass, main window, command wiring, buttons, status text, table population, open/save/page actions.
- Create: `tests/test_toga_table_model.py`
  - Pure tests for table headings, row data, empty markers, page math, and no-radio state.
- Create: `tests/test_toga_commands.py`
  - Pure tests for command identity, loaded-radio gating, and shortcut safety.
- Create: `docs/toga-accessibility-checklist.md`
  - Manual screen-reader acceptance checklist derived from the wx app rules.
- Modify: `README.md`
  - Add a short source-run command for the parallel Toga prototype.
- Modify: `docs/architecture.md`
  - Document that `main_toga.py` is an experimental parallel UI and not the default app path.

---

### Task 1: Add Toga Dependencies And Launcher Skeleton

**Files:**
- Modify: `pyproject.toml`
- Modify: `uv.lock`
- Create: `main_toga.py`
- Create: `vrp_toga/__init__.py`

- [ ] **Step 1: Update dependencies**

In `pyproject.toml`, keep the wx production install surface unchanged, add a
`toga` optional dependency for the prototype, and keep Toga packages in `dev`:

```toml
dependencies = [
    # Accessible desktop UI host: a wxPython app whose wx.html2.WebView is
    # wrapped to expose semantic, screen-reader-friendly HTML (NVDA/JAWS).
    "wxpython>=4.2.0",
    "wx-accessible-webview>=0.2.0",
    # Keyboard-accessible native menu bar that works when a focused WebView2
    # swallows Alt (the menu key handling is the library's, not inline here).
    # 0.1.1 adds webview_listener_js for the single-bridge integration.
    "wx-accessible-menubar>=0.1.1",
    # Accessible, editable ARIA data grid (sibling library). The screen-reader-
    # first replacement for the read-only channel table (preview).
    "wx-accessible-grid>=0.1.0",
    # Unified TTS / screen-reader speech (prism). Used to speak things that
    # ARIA alone can't convey. The Python bindings ship as `prismatoid`.
    "prismatoid>=0.16.0",
    # The CHIRP radio driver library. Installed as an editable local package
    # from the sibling ./chirp clone — see [tool.uv.sources] below. Clone it
    # with `git clone --depth=1 https://github.com/kk7ds/chirp.git` before
    # running `uv sync`.
    "chirp",
    # CHIRP library dependencies
    "pyserial>=3.5",
    "lark>=1.1.0",
    "requests>=2.28.0",
    "jinja2>=3.1.0",
]

[project.optional-dependencies]
toga = [
    "toga>=0.5.4",
]
dev = [
    "pytest>=7.0.0",
    "pytest-cov>=4.0.0",
    "toga>=0.5.4",
    "toga-dummy>=0.5.4",
]
```

- [ ] **Step 2: Refresh the lockfile**

Run:

```bash
uv lock
```

Expected: exit 0 and `uv.lock` updated with Toga packages.

- [ ] **Step 3: Create the Toga package skeleton**

Create `vrp_toga/__init__.py`:

```python
"""Experimental BeeWare Toga UI for Versatile Radio Programmer.

This package is a parallel prototype. The production wxPython app remains in
``vrp`` and is launched by ``main.py``.
"""

__all__ = ["__version__"]

__version__ = "0.1.0"
```

- [ ] **Step 4: Create the launcher**

Create `main_toga.py`:

```python
"""Experimental BeeWare Toga launcher for VRP.

The wxPython app remains the production launcher in ``main.py``. This module
exists so the native Toga prototype can be run without touching that path.
"""

import argparse
import logging

import vrp  # noqa: F401  (import side effect: makes vendored chirp importable)


def main() -> None:
    parser = argparse.ArgumentParser(description="Versatile Radio Programmer Toga prototype")
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging.",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    from vrp_toga.app import main as toga_main

    toga_main()


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Run dependency/import smoke checks**

Run:

```bash
uv run --extra dev python -c "import toga; import toga_dummy; import main_toga; import vrp_toga; print('toga imports ok')"
```

Expected:

```text
toga imports ok
```

- [ ] **Step 6: Commit**

Run:

```bash
git add pyproject.toml uv.lock main_toga.py vrp_toga/__init__.py
git commit -m "Add Toga prototype launcher"
```

---

### Task 2: Build The Pure Toga Table Adapter

**Files:**
- Create: `tests/test_toga_table_model.py`
- Create: `vrp_toga/table_model.py`

- [ ] **Step 1: Write failing table-model tests**

Create `tests/test_toga_table_model.py`:

```python
import os

import pytest

from chirp_backend import radio as radio_backend

BF888_IMAGE = os.path.abspath(
    os.path.join(
        os.path.dirname(__file__),
        "..",
        "chirp",
        "tests",
        "images",
        "Baofeng_BF-888.img",
    )
)

UV5R_IMAGE = os.path.abspath(
    os.path.join(
        os.path.dirname(__file__),
        "..",
        "chirp",
        "tests",
        "images",
        "Baofeng_UV-5R.img",
    )
)


@pytest.fixture(autouse=True)
def _unload_radio():
    radio_backend.unload()
    yield
    radio_backend.unload()


def test_no_radio_page_is_empty_and_named():
    from vrp_toga.table_model import build_table_page

    page = build_table_page()

    assert page.radio_label == "No radio loaded"
    assert page.columns == ["Ch #", "State"]
    assert page.accessors == ["number", "state", "channel_number", "empty"]
    assert page.rows == []
    assert page.status == "No radio image loaded."


def test_bf888_first_page_has_empty_text_and_hidden_channel_number():
    from vrp_toga.table_model import EMPTY_MARKER, build_table_page

    ok, message = radio_backend.load_image(BF888_IMAGE)
    assert ok, message

    page = build_table_page(page=1, page_size=5)

    assert page.radio_label == "Baofeng BF-888"
    assert page.page == 1
    assert page.total_pages == 4
    assert page.first == 1
    assert page.last == 5
    assert page.total == 16
    assert page.columns[:3] == ["Ch #", "State", "Frequency"]
    assert page.accessors[:4] == ["number", "state", "freq", "tmode"]
    assert page.accessors[-2:] == ["channel_number", "empty"]
    assert len(page.rows) == 5
    assert page.rows[0]["number"] == "1"
    assert page.rows[0]["channel_number"] == 1
    assert page.rows[0]["empty"] is False
    assert any(row["state"] == EMPTY_MARKER for row in page.rows)
    assert page.status == "Showing channels 1 to 5 of 16, page 1 of 4."


def test_uv5r_second_page_is_clamped_and_sliced():
    from vrp_toga.table_model import build_table_page

    ok, message = radio_backend.load_image(UV5R_IMAGE)
    assert ok, message

    page = build_table_page(page=99, page_size=100)

    assert page.page == 2
    assert page.total_pages == 2
    assert page.first == 100
    assert page.last == 127
    assert len(page.rows) == 28
    assert page.rows[0]["channel_number"] == 100
    assert page.rows[-1]["channel_number"] == 127


def test_page_for_channel_matches_loaded_radio_bounds():
    from vrp_toga.table_model import page_for_channel

    ok, message = radio_backend.load_image(UV5R_IMAGE)
    assert ok, message

    assert page_for_channel(0, page_size=100) == 1
    assert page_for_channel(100, page_size=100) == 2
    assert page_for_channel(999, page_size=100) == 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
uv run --extra dev python -m pytest tests/test_toga_table_model.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'vrp_toga.table_model'`.

- [ ] **Step 3: Implement the table adapter**

Create `vrp_toga/table_model.py`:

```python
"""Pure data adapter for the experimental Toga channel table."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from chirp_backend import radio as radio_backend
from chirp_backend.col_defs import build_column_defs

from vrp.config import get_config

DEFAULT_PAGE_SIZE = 100
EMPTY_MARKER = "(empty)"


@dataclass(frozen=True)
class TablePage:
    """Rows and metadata needed to populate a native ``toga.Table``."""

    radio_label: str
    columns: list[str]
    accessors: list[str]
    rows: list[dict[str, Any]]
    page: int
    total_pages: int
    first: int
    last: int
    total: int
    has_prev: bool
    has_next: bool
    status: str


def _page_size(page_size: int | None = None) -> int:
    if page_size:
        return page_size
    try:
        configured = int(get_config().get("channels_per_page", DEFAULT_PAGE_SIZE))
    except Exception:  # noqa: BLE001 - config should never block table rendering
        configured = DEFAULT_PAGE_SIZE
    return configured or DEFAULT_PAGE_SIZE


def _bounds() -> tuple[int, int]:
    return radio_backend.get_state().memory_bounds


def channel_total() -> int:
    low, high = _bounds()
    return max(0, high - low + 1)


def total_pages(page_size: int | None = None) -> int:
    size = _page_size(page_size)
    total = channel_total()
    return max(1, math.ceil(total / size)) if total else 1


def page_for_channel(number: int, page_size: int | None = None) -> int:
    size = _page_size(page_size)
    low, high = _bounds()
    if high < low:
        return 1
    clamped = min(max(number, low), high)
    page = (clamped - low) // size + 1
    return min(max(page, 1), total_pages(size))


def page_range(page: int, page_size: int | None = None) -> tuple[int, int]:
    size = _page_size(page_size)
    low, high = _bounds()
    if high < low:
        return 0, 0
    start = low + (page - 1) * size
    return start, min(high, start + size - 1)


def _empty_page() -> TablePage:
    return TablePage(
        radio_label="No radio loaded",
        columns=["Ch #", "State"],
        accessors=["number", "state", "channel_number", "empty"],
        rows=[],
        page=1,
        total_pages=1,
        first=0,
        last=0,
        total=0,
        has_prev=False,
        has_next=False,
        status="No radio image loaded.",
    )


def build_table_page(page: int = 1, page_size: int | None = None) -> TablePage:
    """Build one page of Toga table data for the loaded radio."""

    state = radio_backend.get_state()
    if not state.loaded:
        return _empty_page()

    size = _page_size(page_size)
    total = channel_total()
    pages = total_pages(size)
    page = min(max(page, 1), pages)
    first, last = page_range(page, size)

    columns = build_column_defs(state.features)
    display_columns = [column for column in columns if column.name != "number"]
    headings = ["Ch #", "State"] + [column.label for column in display_columns]
    accessors = ["number", "state"] + [column.name for column in display_columns]
    accessors += ["channel_number", "empty"]

    rows: list[dict[str, Any]] = []
    for number in range(first, last + 1):
        mem = radio_backend.get_memory(number)
        if mem is None:
            continue
        empty = bool(getattr(mem, "empty", False))
        row: dict[str, Any] = {
            "number": str(number),
            "state": EMPTY_MARKER if empty else "",
            "channel_number": number,
            "empty": empty,
        }
        for column in display_columns:
            row[column.name] = "" if empty else column.format_value(mem)
        rows.append(row)

    radio_label = f"{state.radio.VENDOR} {state.radio.MODEL}"
    return TablePage(
        radio_label=radio_label,
        columns=headings,
        accessors=accessors,
        rows=rows,
        page=page,
        total_pages=pages,
        first=first,
        last=last,
        total=total,
        has_prev=page > 1,
        has_next=page < pages,
        status=f"Showing channels {first} to {last} of {total}, page {page} of {pages}.",
    )
```

- [ ] **Step 4: Run focused table tests**

Run:

```bash
uv run --extra dev python -m pytest tests/test_toga_table_model.py -v
```

Expected: PASS.

- [ ] **Step 5: Run full test suite**

Run:

```bash
uv run --extra dev python -m pytest
```

Expected: PASS.

- [ ] **Step 6: Commit**

Run:

```bash
git add tests/test_toga_table_model.py vrp_toga/table_model.py
git commit -m "Add Toga table data adapter"
```

---

### Task 3: Add Pure Command Metadata

**Files:**
- Create: `tests/test_toga_commands.py`
- Create: `vrp_toga/commands.py`

- [ ] **Step 1: Write failing command metadata tests**

Create `tests/test_toga_commands.py`:

```python
from vrp_toga.commands import all_command_specs, command_enabled


def test_command_ids_are_unique_and_cover_first_slice():
    specs = all_command_specs()
    ids = [spec.id for spec in specs]

    assert len(ids) == len(set(ids))
    assert {
        "open",
        "save",
        "save_as",
        "close",
        "page_prev",
        "page_next",
        "edit_channel",
        "find",
        "find_next",
        "operations",
        "shortcuts",
    } <= set(ids)


def test_loaded_radio_commands_are_gated():
    by_id = {spec.id: spec for spec in all_command_specs()}

    assert command_enabled(by_id["open"], radio_loaded=False)
    assert command_enabled(by_id["shortcuts"], radio_loaded=False)
    assert not command_enabled(by_id["save"], radio_loaded=False)
    assert not command_enabled(by_id["page_next"], radio_loaded=False)
    assert command_enabled(by_id["save"], radio_loaded=True)
    assert command_enabled(by_id["page_next"], radio_loaded=True)


def test_shortcuts_avoid_single_letter_table_commands():
    specs = all_command_specs()

    for spec in specs:
        if spec.shortcut is None:
            continue
        assert "+" in spec.shortcut, spec
        assert not spec.shortcut.lower().startswith("alt+"), spec
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
uv run --extra dev python -m pytest tests/test_toga_commands.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'vrp_toga.commands'`.

- [ ] **Step 3: Implement command metadata**

Create `vrp_toga/commands.py`:

```python
"""Command metadata for the experimental Toga UI."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CommandSpec:
    id: str
    text: str
    handler: str
    group: str
    section: int
    order: int
    shortcut: str | None = None
    requires_radio: bool = False
    tooltip: str | None = None


_COMMANDS: tuple[CommandSpec, ...] = (
    CommandSpec(
        id="open",
        text="Open Image File",
        handler="on_open",
        group="file",
        section=0,
        order=0,
        shortcut="mod+o",
        tooltip="Open a CHIRP radio image file.",
    ),
    CommandSpec(
        id="save",
        text="Save",
        handler="on_save",
        group="file",
        section=0,
        order=10,
        shortcut="mod+s",
        requires_radio=True,
        tooltip="Save the current radio image.",
    ),
    CommandSpec(
        id="save_as",
        text="Save As",
        handler="on_save_as",
        group="file",
        section=0,
        order=20,
        requires_radio=True,
        tooltip="Save the current radio image to a new file.",
    ),
    CommandSpec(
        id="close",
        text="Close Image",
        handler="on_close_image",
        group="file",
        section=0,
        order=30,
        requires_radio=True,
        tooltip="Close the current radio image.",
    ),
    CommandSpec(
        id="page_prev",
        text="Previous Channel Page",
        handler="on_page_prev",
        group="channels",
        section=0,
        order=0,
        requires_radio=True,
        tooltip="Show the previous page of channels.",
    ),
    CommandSpec(
        id="page_next",
        text="Next Channel Page",
        handler="on_page_next",
        group="channels",
        section=0,
        order=10,
        requires_radio=True,
        tooltip="Show the next page of channels.",
    ),
    CommandSpec(
        id="edit_channel",
        text="Edit Channel",
        handler="on_edit_channel",
        group="channels",
        section=1,
        order=0,
        requires_radio=True,
        tooltip="Edit the selected channel.",
    ),
    CommandSpec(
        id="find",
        text="Find",
        handler="on_find",
        group="channels",
        section=1,
        order=10,
        shortcut="mod+f",
        requires_radio=True,
        tooltip="Find a channel.",
    ),
    CommandSpec(
        id="find_next",
        text="Find Next",
        handler="on_find_next",
        group="channels",
        section=1,
        order=20,
        shortcut="mod+g",
        requires_radio=True,
        tooltip="Find the next matching channel.",
    ),
    CommandSpec(
        id="operations",
        text="Organize Channels",
        handler="on_operations",
        group="channels",
        section=1,
        order=30,
        requires_radio=True,
        tooltip="Move, copy, sort, or delete channels.",
    ),
    CommandSpec(
        id="shortcuts",
        text="Keyboard Shortcuts",
        handler="on_shortcuts",
        group="help",
        section=0,
        order=0,
        tooltip="Show available keyboard shortcuts.",
    ),
)


def all_command_specs() -> tuple[CommandSpec, ...]:
    return _COMMANDS


def command_enabled(spec: CommandSpec, radio_loaded: bool) -> bool:
    return radio_loaded or not spec.requires_radio
```

- [ ] **Step 4: Run focused command tests**

Run:

```bash
uv run --extra dev python -m pytest tests/test_toga_commands.py -v
```

Expected: PASS.

- [ ] **Step 5: Run full test suite**

Run:

```bash
uv run --extra dev python -m pytest
```

Expected: PASS.

- [ ] **Step 6: Commit**

Run:

```bash
git add tests/test_toga_commands.py vrp_toga/commands.py
git commit -m "Add Toga command metadata"
```

---

### Task 4: Build The Toga App Shell With Native Table

**Files:**
- Create: `vrp_toga/app.py`

- [ ] **Step 1: Create the Toga app implementation**

Create `vrp_toga/app.py`:

```python
"""Experimental BeeWare Toga application shell for VRP."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Callable

import toga
from toga.style import Pack
from toga.style.pack import COLUMN, ROW

from chirp_backend import radio as radio_backend

from vrp import __version__
from vrp.config import get_config
from vrp.speech import Speaker
from vrp_toga.commands import CommandSpec, all_command_specs, command_enabled
from vrp_toga.table_model import TablePage, build_table_page

APP_TITLE = "Versatile Radio Programmer Toga Prototype"
ATTRIBUTION = "Radio driver support provided by the CHIRP project — chirpmyradio.com."
IMAGE_TYPES = ["img"]
CHANNELS_GROUP = toga.Group("Channels", order=30)


class VRPTogaApp(toga.App):
    """Parallel native Toga prototype. The wx app remains the production UI."""

    def startup(self) -> None:
        self.speaker = Speaker()
        self._speak_enabled = bool(get_config().get("speak_status_messages", False))
        self._page = 1
        self._last_table_page = build_table_page(self._page)
        self._commands_by_id: dict[str, toga.Command] = {}

        self.main_window = toga.MainWindow(title=APP_TITLE, size=(1200, 800))
        self.main_window.content = self._build_content(self._last_table_page)
        self._install_commands()
        self._refresh_command_state()
        self.main_window.show()

    def _build_content(self, table_page: TablePage) -> toga.Box:
        self.heading = toga.Label(
            "Versatile Radio Programmer",
            id="toga-heading",
            style=Pack(padding_bottom=8),
        )
        self.radio_label = toga.Label(
            table_page.radio_label,
            id="toga-radio-label",
            style=Pack(padding_bottom=8),
        )
        self.status_label = toga.Label(
            table_page.status,
            id="toga-status",
            style=Pack(padding_bottom=8),
        )

        self.open_button = toga.Button("Open Image File", on_press=self.on_open, id="open-button")
        self.save_button = toga.Button("Save", on_press=self.on_save, id="save-button")
        self.prev_button = toga.Button("Previous Page", on_press=self.on_page_prev, id="prev-page-button")
        self.next_button = toga.Button("Next Page", on_press=self.on_page_next, id="next-page-button")
        self.edit_button = toga.Button("Edit Channel", on_press=self.on_edit_channel, id="edit-channel-button")
        self.shortcuts_button = toga.Button("Keyboard Shortcuts", on_press=self.on_shortcuts, id="shortcuts-button")

        button_row = toga.Box(
            children=[
                self.open_button,
                self.save_button,
                self.prev_button,
                self.next_button,
                self.edit_button,
                self.shortcuts_button,
            ],
            style=Pack(direction=ROW, gap=8, padding_bottom=8),
        )

        self.table = toga.Table(
            columns=table_page.columns,
            accessors=table_page.accessors,
            data=table_page.rows,
            missing_value="",
            multiple_select=False,
            on_select=self.on_table_select,
            on_activate=self.on_table_activate,
            id="channel-table",
            style=Pack(flex=1),
        )

        self.attribution = toga.Label(
            ATTRIBUTION,
            id="chirp-attribution",
            style=Pack(padding_top=8),
        )

        return toga.Box(
            children=[
                self.heading,
                self.radio_label,
                self.status_label,
                button_row,
                self.table,
                self.attribution,
            ],
            style=Pack(direction=COLUMN, padding=12),
        )

    def _install_commands(self) -> None:
        for spec in all_command_specs():
            command = toga.Command(
                action=getattr(self, spec.handler),
                text=spec.text,
                tooltip=spec.tooltip,
                shortcut=self._toga_shortcut(spec),
                group=self._toga_group(spec.group),
                section=spec.section,
                order=spec.order,
                enabled=command_enabled(spec, radio_backend.get_state().loaded),
                id=f"vrp_toga.{spec.id}",
            )
            self.commands.add(command)
            self._commands_by_id[spec.id] = command

    @staticmethod
    def _toga_group(name: str):
        if name == "file":
            return toga.Group.FILE
        if name == "help":
            return toga.Group.HELP
        if name == "channels":
            return CHANNELS_GROUP
        raise ValueError(f"Unknown Toga command group: {name}")

    @staticmethod
    def _toga_shortcut(spec: CommandSpec):
        shortcuts = {
            "mod+o": toga.Key.MOD_1 + "o",
            "mod+s": toga.Key.MOD_1 + "s",
            "mod+f": toga.Key.MOD_1 + "f",
            "mod+g": toga.Key.MOD_1 + "g",
        }
        return shortcuts.get(spec.shortcut)

    def _set_status(self, message: str) -> None:
        self.status_label.text = message
        if self._speak_enabled:
            self.speaker.speak(message)

    def _refresh_command_state(self) -> None:
        loaded = radio_backend.get_state().loaded
        for spec in all_command_specs():
            self._commands_by_id[spec.id].enabled = command_enabled(spec, loaded)
        self.save_button.enabled = loaded
        self.prev_button.enabled = loaded and self._last_table_page.has_prev
        self.next_button.enabled = loaded and self._last_table_page.has_next
        self.edit_button.enabled = loaded

    def _refresh_table(self) -> None:
        table_page = build_table_page(self._page)
        self._last_table_page = table_page
        self._page = table_page.page

        # Toga table headings/accessors are read-only after construction, so
        # rebuild the content when a newly loaded radio changes the schema.
        self.main_window.content = self._build_content(table_page)
        self._set_status(table_page.status)
        self._refresh_command_state()
        if table_page.rows:
            self.table.scroll_to_top()

    def _run_dialog(self, coro) -> None:
        asyncio.create_task(coro)

    def on_open(self, widget, **kwargs) -> None:
        self._run_dialog(self._open_image())

    async def _open_image(self) -> None:
        path = await self.main_window.dialog(
            toga.OpenFileDialog("Open radio image", file_types=IMAGE_TYPES)
        )
        if path is None:
            self._set_status("Open image cancelled.")
            return

        ok, message = radio_backend.load_image(str(path))
        if ok:
            get_config().add_recent(str(path))
            self._page = 1
            self._refresh_table()
        self._set_status(message)
        if not ok:
            await self.main_window.dialog(toga.ErrorDialog("Open failed", message))

    def on_save(self, widget, **kwargs) -> None:
        ok, message = radio_backend.save_image()
        self._set_status(message)
        if not ok:
            self._run_dialog(self.main_window.dialog(toga.ErrorDialog("Save failed", message)))

    def on_save_as(self, widget, **kwargs) -> None:
        self._run_dialog(self._save_as())

    async def _save_as(self) -> None:
        state = radio_backend.get_state()
        suggested = Path(state.image_path).name if state.image_path else "radio.img"
        path = await self.main_window.dialog(
            toga.SaveFileDialog(
                "Save radio image as",
                suggested_filename=suggested,
                file_types=IMAGE_TYPES,
            )
        )
        if path is None:
            self._set_status("Save as cancelled.")
            return
        ok, message = radio_backend.save_image(str(path))
        self._set_status(message)
        if ok:
            get_config().add_recent(str(path))
        else:
            await self.main_window.dialog(toga.ErrorDialog("Save failed", message))

    def on_close_image(self, widget, **kwargs) -> None:
        radio_backend.unload()
        self._page = 1
        self._refresh_table()
        self._set_status("Closed radio image.")

    def on_page_prev(self, widget, **kwargs) -> None:
        if self._last_table_page.has_prev:
            self._page -= 1
            self._refresh_table()

    def on_page_next(self, widget, **kwargs) -> None:
        if self._last_table_page.has_next:
            self._page += 1
            self._refresh_table()

    def _selected_channel_number(self) -> int | None:
        row = self.table.selection
        if row is None:
            return None
        return int(row.channel_number)

    def on_table_select(self, widget, **kwargs) -> None:
        number = self._selected_channel_number()
        if number is not None:
            self._set_status(f"Selected channel {number}.")

    def on_table_activate(self, widget, row, **kwargs) -> None:
        self.on_edit_channel(widget)

    def on_edit_channel(self, widget, **kwargs) -> None:
        number = self._selected_channel_number()
        if number is None:
            self._set_status("Select a channel before editing.")
            return
        self._set_status(f"Edit channel {number} is not available in this Toga prototype.")

    def on_find(self, widget, **kwargs) -> None:
        self._set_status("Find is not available in this Toga prototype.")

    def on_find_next(self, widget, **kwargs) -> None:
        self._set_status("Find next is not available in this Toga prototype.")

    def on_operations(self, widget, **kwargs) -> None:
        self._set_status("Organize channels is not available in this Toga prototype.")

    def on_shortcuts(self, widget, **kwargs) -> None:
        lines = []
        for spec in all_command_specs():
            shortcut = spec.shortcut or "menu or button"
            lines.append(f"{spec.text}: {shortcut}")
        self._run_dialog(
            self.main_window.dialog(
                toga.InfoDialog("Keyboard Shortcuts", "\n".join(lines))
            )
        )


def main() -> None:
    app = VRPTogaApp(
        formal_name=APP_TITLE,
        app_id="online.techopolis.vrp.toga",
        version=__version__,
    )
    app.main_loop()
```

- [ ] **Step 2: Run syntax/import smoke check**

Run:

```bash
TOGA_BACKEND=toga_dummy uv run --extra dev python -c "from vrp_toga.app import VRPTogaApp, APP_TITLE; print(APP_TITLE); print(VRPTogaApp)"
```

Expected: prints `Versatile Radio Programmer Toga Prototype` and the `VRPTogaApp` class without importing wx or launching a GUI.

- [ ] **Step 3: Run the Toga launcher with dummy backend for import-level validation**

Run:

```bash
TOGA_BACKEND=toga_dummy uv run --extra dev python main_toga.py --debug
```

Expected: app starts without import errors. Stop it from the terminal with `Ctrl+C` after the startup log appears.

- [ ] **Step 4: Run full test suite**

Run:

```bash
uv run --extra dev python -m pytest
```

Expected: PASS.

- [ ] **Step 5: Commit**

Run:

```bash
git add vrp_toga/app.py
git commit -m "Add Toga app shell"
```

---

### Task 5: Add Table Status Regression And Read-Only Column Check

**Files:**
- Modify: `tests/test_toga_table_model.py`

- [ ] **Step 1: Add a regression test for status after save-state changes**

Append to `tests/test_toga_table_model.py`:

```python
def test_table_page_status_reflects_modified_flag_after_save(tmp_path):
    from vrp_toga.table_model import build_table_page

    ok, message = radio_backend.load_image(BF888_IMAGE)
    assert ok, message

    page = build_table_page(page=1, page_size=100)
    assert page.status == "Showing channels 1 to 16 of 16, page 1 of 1."

    saved_path = tmp_path / "bf888-copy.img"
    ok, message = radio_backend.save_image(str(saved_path))
    assert ok, message

    page = build_table_page(page=1, page_size=100)
    assert page.radio_label == "Baofeng BF-888"
    assert page.status == "Showing channels 1 to 16 of 16, page 1 of 1."
```

- [ ] **Step 2: Run focused tests**

Run:

```bash
uv run --extra dev python -m pytest tests/test_toga_table_model.py -v
```

Expected: PASS.

- [ ] **Step 3: Confirm the app never assigns read-only table schema properties**

Run:

```bash
rg -n "self\\.table\\.(columns|accessors)\\s*=" vrp_toga/app.py
```

Expected: no output and exit 1 from `rg`. Toga table columns/accessors are
constructed with each new table rather than assigned after construction.

- [ ] **Step 4: Run Toga import smoke**

Run:

```bash
TOGA_BACKEND=toga_dummy uv run --extra dev python -c "from vrp_toga.app import VRPTogaApp; print('app import ok')"
```

Expected:

```text
app import ok
```

- [ ] **Step 5: Run full test suite**

Run:

```bash
uv run --extra dev python -m pytest
```

Expected: PASS.

- [ ] **Step 6: Commit**

Run:

```bash
git add tests/test_toga_table_model.py
git commit -m "Add Toga table status regression"
```

---

### Task 6: Add Accessibility Verification Checklist

**Files:**
- Create: `docs/toga-accessibility-checklist.md`

- [ ] **Step 1: Write the checklist**

Create `docs/toga-accessibility-checklist.md`:

```markdown
# Toga Accessibility Checklist

This checklist is required before the Toga prototype can replace any wxPython
workflow. The wxPython app remains the accessibility baseline.

## Environment

- Platform:
- Toga backend:
- Screen reader:
- Radio image used:
- Tester:
- Date:

## Launch And Window

- [ ] `uv run --extra toga python main_toga.py` launches without replacing the wx app.
- [ ] Screen reader announces the window title as "Versatile Radio Programmer Toga Prototype".
- [ ] Keyboard focus starts on a useful control or reaches one with Tab.
- [ ] The required CHIRP attribution is visible and reachable.

## Commands

- [ ] Open Image File is reachable from menu and button.
- [ ] Save is disabled or unavailable before a radio is loaded.
- [ ] Previous Page and Next Page are disabled or unavailable before a radio is loaded.
- [ ] Keyboard Shortcuts opens a readable dialog.
- [ ] No table workflow requires a single-letter shortcut.

## Table

- [ ] After opening an image, the table announces column headers.
- [ ] The table exposes channel number, empty state, and field values.
- [ ] Empty channels are announced with the text "(empty)".
- [ ] Row selection announces enough context to identify the channel.
- [ ] Page changes announce the visible channel range and page number.
- [ ] Large images remain responsive when moving between pages.

## Dialogs And Status

- [ ] File-open cancel returns focus and announces cancellation.
- [ ] File-open errors show an error dialog and announce the error.
- [ ] Save and Save As announce success or failure.
- [ ] Dialogs prevent interaction with the main window while open.
- [ ] Dialog dismissal returns focus to a useful control.

## Result

- [ ] Pass: Toga table behavior is acceptable for the tested screen reader.
- [ ] Fail: Record table/header/focus gaps below before proposing fallback UI.

## Notes
```

- [ ] **Step 2: Commit**

Run:

```bash
git add docs/toga-accessibility-checklist.md
git commit -m "Add Toga accessibility checklist"
```

---

### Task 7: Document Prototype Run Path

**Files:**
- Modify: `README.md`
- Modify: `docs/architecture.md`

- [ ] **Step 1: Update README source-run section**

In `README.md`, under the existing source run commands, add:

```markdown
# Experimental Toga prototype
uv run --extra toga python main_toga.py
```

Add this paragraph immediately below the command:

```markdown
The Toga launcher is a parallel prototype. The wxPython app launched by
`uv run python main.py` remains the production UI until the native Toga table
passes the screen-reader checklist in `docs/toga-accessibility-checklist.md`.
```

- [ ] **Step 2: Update architecture document**

In `docs/architecture.md`, add this section after the main architecture diagram:

```markdown
## Experimental Toga Prototype

`main_toga.py` launches a parallel BeeWare Toga prototype. It reuses
`chirp_backend/` and the framework-neutral column definitions, but owns its own
`vrp_toga/` app shell and native `toga.Table` adapter. This prototype does not
replace the wxPython app; it exists to test whether native Toga widgets can meet
VRP's screen-reader requirements.
```

- [ ] **Step 3: Run docs diff check**

Run:

```bash
git diff --check
```

Expected: no output and exit 0.

- [ ] **Step 4: Commit**

Run:

```bash
git add README.md docs/architecture.md
git commit -m "Document Toga prototype run path"
```

---

### Task 8: Final Verification

**Files:**
- Inspect all changed files.
- No new source files beyond those listed in this plan.

- [ ] **Step 1: Run whitespace check**

Run:

```bash
git diff --check HEAD
```

Expected: no output and exit 0.

- [ ] **Step 2: Run full automated tests**

Run:

```bash
uv run --extra dev python -m pytest
```

Expected:

```text
71 passed
```

Any failures must be investigated before continuing.

- [ ] **Step 3: Run Toga import smoke**

Run:

```bash
TOGA_BACKEND=toga_dummy uv run --extra dev python -c "import main_toga; from vrp_toga.app import VRPTogaApp; print('toga smoke ok')"
```

Expected:

```text
toga smoke ok
```

- [ ] **Step 4: Run wx import smoke**

Run:

```bash
uv run --extra dev python -c "import main; from vrp.app import APP_TITLE; print(APP_TITLE)"
```

Expected:

```text
Versatile Radio Programmer
```

- [ ] **Step 5: Inspect git status**

Run:

```bash
git status --short --branch
```

Expected: on `codex/toga-ui`, clean except for intentional committed changes.

- [ ] **Step 6: Report manual verification gap**

Report that automated checks passed, and explicitly state that NVDA-on-Windows
screen-reader verification remains required using
`docs/toga-accessibility-checklist.md` before this prototype can be considered
accessibility-complete.
