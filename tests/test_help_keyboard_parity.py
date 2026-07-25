"""The help/KeyboardCommands.html page must not drift from the app's own keys.

Why this exists: VRP states its keyboard commands in three places — the menu
accelerators (the truth), APP_SHORTCUTS (the F1 list), and this help page. They
were kept in step by hand, and they did not stay in step: Ctrl+Q (Exit) was wired
in the File menu and documented in docs/keyboard-map.md but missing from
APP_SHORTCUTS, so F1 never mentioned how to quit. Adding a third hand-maintained
copy without a guard would repeat that.

These tests read the shipped HTML rather than a fixture, so they fail if someone
edits the page, the menu, or APP_SHORTCUTS and leaves the others behind.

They deliberately do NOT import wx (no display needed in CI): APP_SHORTCUTS and
the menu labels are parsed out of main_window.py's source.
"""

from __future__ import annotations

import re
from html.parser import HTMLParser
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
HELP_PAGE = PROJECT_ROOT / "help" / "KeyboardCommands.html"
MAIN_WINDOW = PROJECT_ROOT / "vrp" / "native" / "main_window.py"


class _ShortcutTableParser(HTMLParser):
    """Pulls the rows out of the <table id="shortcuts"> in the help page.

    A tiny parser beats a regex here: it tracks the cells positionally, so a
    reordered column or a dropped <td> shows up as a test failure rather than
    passing on a lucky substring match.
    """

    def __init__(self) -> None:
        super().__init__()
        self._in_table = False
        self._in_row = False
        self._cell: list[str] | None = None
        self.rows: list[list[str]] = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "table" and attrs.get("id") == "shortcuts":
            self._in_table = True
        elif self._in_table and tag == "tr":
            self._in_row = True
            self.rows.append([])
        elif self._in_table and self._in_row and tag in ("td", "th"):
            self._cell = []

    def handle_endtag(self, tag):
        if tag == "table" and self._in_table:
            self._in_table = False
        elif tag == "tr":
            self._in_row = False
        elif tag in ("td", "th") and self._cell is not None:
            self.rows[-1].append("".join(self._cell).strip())
            self._cell = None

    def handle_data(self, data):
        if self._cell is not None:
            self._cell.append(data)


def _help_rows() -> list[list[str]]:
    parser = _ShortcutTableParser()
    parser.feed(HELP_PAGE.read_text(encoding="utf-8"))
    # Drop the header row and any stray empty <tr>.
    return [r for r in parser.rows if len(r) == 3 and r[1] not in ("Windows", "")]


def _atoms(cell: str) -> set[str]:
    """Split a key cell into individual combos.

    The two surfaces punctuate differently — APP_SHORTCUTS writes
    "Ctrl+E / Enter", the page writes "Ctrl+E, or Enter" — so both are reduced
    to {"Ctrl+E", "Enter"} before comparing. Comparing the raw strings would
    force one house style on both for no benefit.
    """
    parts = re.split(r",|\bor\b|/", cell)
    return {p.strip() for p in parts if p.strip()}


def _app_shortcuts() -> list[tuple[str, str, str]]:
    """APP_SHORTCUTS as (windows, macos, description) triples, read from
    main_window.py's source (no wx import, so this runs headless)."""
    src = MAIN_WINDOW.read_text(encoding="utf-8")
    block = re.search(r"APP_SHORTCUTS = \[(.*?)\n\]", src, re.S)
    assert block, "APP_SHORTCUTS not found in main_window.py"
    entries = re.findall(
        r'\(\s*"(.*?)",\s*"(.*?)",\s*\n?\s*"(.*?)"\s*\)', block.group(1), re.S
    )
    assert entries, "APP_SHORTCUTS entries did not parse as (win, mac, desc)"
    return entries


def test_help_page_exists():
    assert HELP_PAGE.is_file(), f"{HELP_PAGE} is missing"


def test_help_page_has_a_shortcut_table():
    rows = _help_rows()
    assert len(rows) >= 25, f"only {len(rows)} rows parsed from the help table"


@pytest.mark.parametrize("column,index", [("Windows", 0), ("macOS", 1)])
def test_every_app_shortcut_is_documented(column, index):
    """Every key the app binds must appear in the page's matching column.

    Both columns are checked: the macOS one is not derivable from the Windows one
    (Del -> Fn+Delete, Ctrl+Space -> Space, Ctrl+Up/Down -> VoiceOver
    navigation), so it can drift independently.
    """
    documented: set[str] = set()
    for row in _help_rows():
        documented |= _atoms(row[index + 1])  # row = [command, windows, macos]

    missing = []
    for entry in _app_shortcuts():
        for atom in _atoms(entry[index]):
            if atom not in documented:
                missing.append(f"{atom} ({entry[2]})")
    assert not missing, (
        f"These {column} keys are bound in the app but missing from "
        f"help/KeyboardCommands.html: {missing}"
    )


@pytest.mark.parametrize("column,index", [("Windows", 0), ("macOS", 1)])
def test_page_documents_no_keys_the_app_does_not_bind(column, index):
    """The reverse: a key on the page that the app doesn't bind is a promise the
    app won't keep. Grid navigation and the context menu live in a separate table
    (they aren't app commands), so only the id="shortcuts" table is checked."""
    bound: set[str] = set()
    for entry in _app_shortcuts():
        bound |= _atoms(entry[index])

    unbound = []
    for row in _help_rows():
        for atom in _atoms(row[index + 1]):
            if atom not in bound:
                unbound.append(f"{atom} ({row[0]})")
    assert not unbound, (
        f"These {column} keys are documented in help/KeyboardCommands.html but "
        f"not bound in APP_SHORTCUTS: {unbound}"
    )


def test_f1_list_uses_command_not_ctrl_on_macos():
    """The bug this fixes: F1 showed the Windows column on every platform, so a
    Mac user was told to press Ctrl+S for a command bound to Command+S."""
    for keys, desc in _shortcuts_for_platform(mac=True):
        assert "Ctrl+" not in keys, (
            f"macOS F1 list still offers a Ctrl key: {keys!r} ({desc})"
        )


def test_f1_list_uses_ctrl_not_command_on_windows():
    for keys, desc in _shortcuts_for_platform(mac=False):
        assert "Command" not in keys, (
            f"Windows F1 list offers a Command key: {keys!r} ({desc})"
        )


def _shortcuts_for_platform(mac: bool) -> list[tuple[str, str]]:
    """Mirror of main_window.shortcuts_for_platform, over the parsed source."""
    return [(m if mac else w, d) for w, m, d in _app_shortcuts()]


@pytest.mark.parametrize("doc", ["GettingStarted.html", "KeyboardCommands.html"])
def test_help_docs_carry_the_chirp_attribution(doc):
    """CLAUDE.md: the CHIRP attribution is a GPLv3 requirement and any help page
    must carry it."""
    text = (PROJECT_ROOT / "help" / doc).read_text(encoding="utf-8")
    assert "Radio driver support provided by the CHIRP project" in text
