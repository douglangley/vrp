"""Native main window: menu bar, status bar, channel grid, command handlers.

Each command handler calls ``chirp_backend`` directly and pushes results to the
grid (``refresh_numbers``/``rebuild``) and the ``Announcer`` (status bar + prism
speech). Notable points:

- No paging: the grid shows all channels at once.
- Focus management is the primary screen-reader signal; ``grid.SetFocus()`` and
  per-row focus moves do the work, with the Announcer as a fallback.
- on_radio_info: shows a plain-text summary in a read-only edit box (InfoDialog).
- on_shortcuts: displayed with wx.MessageBox (plain text).
- CHIRP attribution: shown permanently in status-bar field 1 and in the About
  box (vrp.about_dialog), satisfying the GPLv3 requirement in CLAUDE.md.
"""

from __future__ import annotations

import logging
import os
import sys
import threading
import time
from dataclasses import dataclass

import wx

from chirp_backend import radio as radio_backend
from vrp import help as vrp_help
from vrp.native.announce import Announcer
from vrp.native.channel_grid import ChannelGrid
from vrp.speech import get_speaker

LOG = logging.getLogger(__name__)


@dataclass
class _Clipboard:
    """In-app clipboard for whole-row cut/copy/paste (no OS clipboard in v1).

    ``mems`` are deep-copied Memory snapshots taken at copy/cut time, so the
    clipboard survives later edits to the source. ``source_numbers`` are the
    original channel numbers — used only for a ``cut`` (to erase the sources when
    the paste lands, making cut+paste a move); a ``copy`` ignores them."""

    mode: str  # "copy" | "cut"
    mems: list
    source_numbers: list[int]

# Keyboard shortcuts table (combo, description).
# Displayed by on_shortcuts (F1).
# (Windows keys, macOS keys, description) — F1 shows the column for the platform
# it is running on (shortcuts_for_platform).
#
# The macOS column is NOT "Ctrl" search-and-replaced. wx maps a "Ctrl+" menu
# accelerator to Command on macOS, so most rows are a straight swap — but three
# are not, and a blind replace would state keys that do nothing:
#
#  - Ctrl+Up/Down is the native list control's own focus-without-selection
#    behaviour, which VRP never binds; NSTableView has no equivalent, so a
#    VoiceOver user navigates with VoiceOver.
#  - Ctrl+Space: the grid's Space handler ignores Ctrl (channel_grid._on_grid_key),
#    and Cmd+Space is Spotlight on macOS, so only plain Space is offered.
#  - Del: a Mac keyboard's "delete" key is Backspace; forward delete is Fn+Delete.
#
# This column must stay in step with help/KeyboardCommands.html — both directions
# are enforced by tests/test_help_keyboard_parity.py.
APP_SHORTCUTS = [
    ("Ctrl+O", "Command+O", "Open image file"),
    ("Ctrl+S", "Command+S", "Save"),
    ("Ctrl+Shift+S", "Command+Shift+S", "Save as"),
    ("Ctrl+Q", "Command+Q", "Exit"),
    ("Ctrl+Shift+D", "Command+Shift+D", "Download from radio"),
    ("Ctrl+Shift+U", "Command+Shift+U", "Upload to radio"),
    ("Ctrl+Shift+P", "Command+Shift+P", "Edit radio settings"),
    ("Ctrl+E / Enter", "Command+E / Enter", "Edit the focused channel (all fields)"),
    ("F2", "F2", "Edit the focused cell (the column at the Left/Right cursor)"),
    ("Del", "Fn+Delete", "Delete the selected channel(s)"),
    ("Ctrl+Z", "Command+Z", "Undo the last change"),
    ("Ctrl+Y / Ctrl+Shift+Z", "Command+Y / Command+Shift+Z",
     "Redo the last undone change"),
    ("Space / Ctrl+Space", "Space", "Select or deselect the focused channel"),
    ("Ctrl+Up / Ctrl+Down", "VoiceOver navigation",
     "Move the cursor without changing the selection"),
    ("Shift+Up / Shift+Down", "Shift+Up / Shift+Down", "Extend the selection"),
    ("Ctrl+A", "Command+A", "Select all channels"),
    ("Ctrl+C", "Command+C", "Copy selected channel(s)"),
    ("Ctrl+X", "Command+X", "Cut selected channel(s)"),
    ("Ctrl+V", "Command+V", "Paste at the focused channel"),
    ("Ctrl+G", "Command+G", "Go to channel"),
    ("Ctrl+B", "Command+B", "Channel banks for the focused channel"),
    ("Ctrl+Shift+Up", "Command+Shift+Up", "Move selected channel(s) up"),
    ("Ctrl+Shift+Down", "Command+Shift+Down", "Move selected channel(s) down"),
    ("Ctrl+Shift+M", "Command+Shift+M", "Move selected channel(s) to a chosen slot"),
    ("Ctrl+M", "Command+M", "Bulk operations dialog"),
    ("Ctrl+F", "Command+F", "Find a channel"),
    ("F3", "F3", "Find next match"),
    ("F1", "F1", "Show this list of keyboard shortcuts"),
]


def shortcuts_for_platform(mac: bool | None = None) -> list[tuple[str, str]]:
    """APP_SHORTCUTS as (keys, description) for the running platform.

    ``mac`` overrides the platform detection (for tests). F1 previously showed
    the Windows column everywhere, so a Mac user was told to press Ctrl+S for a
    command actually bound to Command+S.
    """
    if mac is None:
        mac = sys.platform == "darwin"
    return [(macos if mac else win, desc) for win, macos, desc in APP_SHORTCUTS]


_CHIRP_ATTRIBUTION = (
    "Radio driver support provided by the CHIRP project — chirpmyradio.com."
)


class MainWindow(wx.Frame):
    def __init__(self) -> None:
        super().__init__(None, title="Versatile Radio Programmer", size=(900, 600))

        # Two status bar fields: field 0 for announcements (overwritten freely),
        # field 1 permanently holds the CHIRP attribution (never overwritten).
        self.CreateStatusBar(2)
        self.SetStatusWidths([-3, -2])
        self.SetStatusText(_CHIRP_ATTRIBUTION, 1)

        # Build speech: get_speaker() returns the shared process-wide Speaker.
        # Pass its .speak method; if prism is unavailable the method is a no-op,
        # so Announcer degrades gracefully.
        self._speaker = get_speaker()
        # Announcer calls set_status(message) with ONE argument, which maps to
        # SetStatusText(message) — the no-index form writes field 0 only, so
        # the attribution in field 1 is never touched.
        #
        # speech_enabled honours the "speak_messages" preference (default ON).
        # This is the wiring that was missing: the pref existed but the Announcer
        # was built with speech unconditionally on, so the checkbox did nothing.
        # The cell cursor below deliberately bypasses the pref.
        from vrp.config import get_config as _get_config

        self.announce = Announcer(
            set_status=self.SetStatusText,
            speak=lambda m, interrupt=False: self._speaker.speak(m, interrupt=interrupt),
            speech_enabled=bool(_get_config().get("speak_messages", True)),
        )

        # ChannelGrid binds these to its inner native list itself, re-binding when
        # the list is recreated for a new radio (the library fixes columns at
        # construction), so they are passed as callbacks rather than bound here:
        #  - activate: Enter / double-click a row -> edit it in a native dialog;
        #  - context_menu: Applications key / Shift+F10 / right-click -> row menu;
        #  - selection_changed: debounced multi-select feedback.
        # Delete is NOT a grid key event: a focused native list can swallow the
        # key on macOS, so Delete lives on the Channels-menu "Delete channel(s)\tDel"
        # accelerator instead, which fires reliably regardless of grid focus.
        # Opt-in Left/Right cell cursor: on Windows the native DataViewCtrl is
        # wx's generic control and announces no per-cell cursor, so we voice the
        # moved-to cell ("<value>, <column>") through our prism Announcer
        # (assertive, so quick arrowing speaks the latest cell). On macOS we leave
        # it None — VoiceOver reads cells natively with VO+Left/Right, so a second
        # synthesized voice would just double up.
        # Wire the library's opt-in Left/Right cell cursor on Windows AND macOS.
        # On macOS this was verified on real hardware: a focused DataViewListCtrl
        # (NSTableView) *does* deliver plain Left/Right as EVT_KEY_DOWN (they're
        # not VoiceOver's VO+arrow commands and are native no-ops on a flat table,
        # so nothing eats them), and prism speaks the moved-to cell. So F2 edits
        # the cell you arrowed to, identical to Windows. Left None on GTK/other,
        # where the cursor is untested — on_edit_cell falls back to the picker.
        cell_announce = (
            self._announce_cell if sys.platform in ("win32", "darwin") else None
        )
        self.grid = ChannelGrid(
            self,
            on_activate=self.on_edit_channel,
            on_context_menu=self.on_grid_context_menu,
            on_selection_changed=self._on_grid_selection_changed,
            on_select_toggle=self._on_select_toggle,
            cell_announce=cell_announce,
        )
        self._sel_timer: wx.CallLater | None = None
        # Set by a Space/Ctrl+Space toggle so the debounced count announce doesn't
        # double up on the per-row toggle announce (which already states the count).
        self._suppress_next_count = False
        # In-app cut/copy/paste clipboard (None = empty). See _Clipboard.
        self._clipboard: _Clipboard | None = None
        self._menu_items: dict[str, wx.MenuItem] = {}
        self._radio_gated_keys: set[str] = set()
        # Find state: query string, fields, last matched channel.
        self._find_query: str | None = None
        self._find_fields: tuple = ("freq", "name", "comment")
        self._find_last: int | None = None
        self._build_menubar()
        self._update_menu_state()
        # Apply the saved band-plan region so offset suggestions match where the
        # operator is (Preferences > Band plan). Default: North America.
        from chirp_backend import bandplan
        from vrp.config import get_config

        bandplan.set_region(get_config().get("bandplan_region", bandplan.DEFAULT_REGION))
        # Refresh the Undo/Redo item labels with the next op's description when the
        # Edit menu opens (discoverability; relabeling is safe for accelerators).
        self.Bind(wx.EVT_MENU_OPEN, self._on_menu_open)
        # Ctrl+Shift+Z is a second Redo accelerator (the Redo menu item displays
        # Ctrl+Y). A frame accelerator table is consulted in addition to the menu
        # accelerators, so this adds the alias without disturbing the menu's
        # Ctrl-combos.
        self._redo_accel_id = wx.NewIdRef()
        self.Bind(wx.EVT_MENU, self.on_redo, id=self._redo_accel_id)
        # Guard against discarding unsaved channel edits on window close/Exit.
        self.Bind(wx.EVT_CLOSE, self.on_close_window)
        self.SetAcceleratorTable(wx.AcceleratorTable([
            wx.AcceleratorEntry(wx.ACCEL_CTRL | wx.ACCEL_SHIFT, ord("Z"),
                                self._redo_accel_id),
        ]))
        self.grid.SetFocus()
        # Deferred and delayed: wx.CallAfter alone fires on the very next idle
        # tick, which can race ahead of NVDA's own window-title announcement
        # for the newly shown frame, and a non-interrupting speak request
        # just gets silently dropped if NVDA is still mid-utterance at that
        # moment. wx.CallLater gives the title announcement time to finish;
        # assertive=True additionally tells prism to interrupt/flush whatever
        # is still speaking, so "Ready" is heard either way.
        wx.CallLater(750, self.announce.announce, "Ready", assertive=True)

    def _announce_cell(self, text: str) -> None:
        """Voice the grid's Left/Right cell cursor ("<value>, <column>").

        ``always_speak``: this is the ONLY announcement of which cell the cursor
        is on — wx's generic DataViewCtrl announces no per-cell cursor on
        Windows — so it deliberately ignores the ``speak_messages`` preference.
        Gating it would make Left/Right navigation silent, which is precisely
        what that preference must never be able to cause. It cannot double up
        with the screen reader, because nothing else speaks it.

        ``assertive`` so quick arrowing speaks the latest cell rather than
        queueing behind stale ones. Passed to ChannelGrid as its ``announce``
        callback on Windows/macOS only (None elsewhere, where F2 falls back to
        the column picker).
        """
        LOG.debug("cell-cursor announce: %r", text)  # visible with --debug
        self.announce.announce(text, assertive=True, always_speak=True)

    # -- menu construction --------------------------------------------

    def _build_menubar(self) -> None:
        bar = wx.MenuBar()
        bar.Append(self._build_file_menu(), "&File")
        bar.Append(self._build_edit_menu(), "&Edit")
        bar.Append(self._build_radio_menu(), "&Radio")
        bar.Append(self._build_channels_menu(), "&Channels")
        bar.Append(self._build_help_menu(), "&Help")
        self.SetMenuBar(bar)

    def _add(
        self,
        menu: wx.Menu,
        key: str,
        label: str,
        handler,
        *,
        needs_radio: bool = False,
    ) -> wx.MenuItem:
        item = menu.Append(wx.ID_ANY, label)
        self.Bind(wx.EVT_MENU, handler, item)
        self._menu_items[key] = item
        if needs_radio:
            self._radio_gated_keys.add(key)
        return item

    def _build_file_menu(self) -> wx.Menu:
        m = wx.Menu()
        self._file_menu = m
        self._recent_item: wx.MenuItem | None = None  # the "Open Recent" submenu, when shown
        self._add(m, "open", "&Open Image File…\tCtrl+O", self.on_open)
        self._add(m, "save", "&Save\tCtrl+S", self.on_save, needs_radio=True)
        self._add(m, "save_as", "Save &As…\tCtrl+Shift+S", self.on_save_as, needs_radio=True)
        self._add(m, "close", "&Close Image", self.on_close_image, needs_radio=True)
        m.AppendSeparator()
        self._add(m, "import", "&Import from File…", self.on_import_file, needs_radio=True)
        self._add(m, "export", "&Export to CSV…", self.on_export_csv, needs_radio=True)
        m.AppendSeparator()
        self._add(m, "preferences", "&Preferences…", self.on_preferences)
        self._add(m, "exit", "E&xit\tCtrl+Q", self.on_exit)
        # Insert the "Open Recent" submenu (after Open) per the saved preference.
        self._refresh_recent_menu()
        return m

    def _refresh_recent_menu(self) -> None:
        """(Re)build the File > Open Recent submenu from prefs + recent files.

        Shown only when the recent_files_count preference is >= 1; a count of 0
        removes the submenu entirely (the user asked for it to disappear). Called
        at startup, after each successful open, and after Preferences changes the
        count. Rebuilt from scratch each time to avoid stale entries."""
        from vrp.config import get_config

        cfg = get_config()
        if self._recent_item is not None:
            # Remove() detaches the submenu item; dropping our reference lets it
            # (and its submenu) be freed. wx.Menu has no Destroy(item) in Phoenix.
            self._file_menu.Remove(self._recent_item)
            self._recent_item = None
        if cfg.recent_count() <= 0:
            return
        recents = cfg.recent_to_show()
        sub = wx.Menu()
        if recents:
            basenames = [os.path.basename(p) for p in recents]
            for i, path in enumerate(recents):
                base = basenames[i]
                label = base
                if basenames.count(base) > 1:  # disambiguate dupes with the folder
                    label = f"{base} — {os.path.basename(os.path.dirname(path))}"
                # &N gives a quick Alt+number mnemonic; escape any literal & in
                # the name so it isn't read as a mnemonic; full path in the help.
                item = sub.Append(wx.ID_ANY, f"&{i + 1} {label.replace('&', '&&')}")
                item.SetHelp(path)
                self.Bind(wx.EVT_MENU, lambda e, p=path: self._open_recent(p), item)
            sub.AppendSeparator()
            clear = sub.Append(wx.ID_ANY, "&Clear Recently Opened")
            self.Bind(wx.EVT_MENU, self._on_clear_recent, clear)
        else:
            placeholder = sub.Append(wx.ID_ANY, "(No recent files)")
            placeholder.Enable(False)
        # Position 1 = directly after "Open Image File…".
        self._recent_item = self._file_menu.Insert(1, wx.ID_ANY, "Open &Recent", sub)

    def _build_edit_menu(self) -> wx.Menu:
        m = wx.Menu()
        self._edit_menu = m
        # Undo/Redo gated on a loaded radio only (kept enabled so the accelerator
        # always fires; the handlers announce "Nothing to undo/redo"). Labels are
        # refreshed with the next op's description on menu-open (_on_menu_open).
        self._add(m, "undo", "&Undo\tCtrl+Z", self.on_undo, needs_radio=True)
        self._add(m, "redo", "&Redo\tCtrl+Y", self.on_redo, needs_radio=True)
        m.AppendSeparator()
        self._add(m, "select_all", "Select &All Channels\tCtrl+A",
                  self.on_select_all, needs_radio=True)
        self._add(m, "clear_selection", "&Clear Selection",
                  self.on_clear_selection, needs_radio=True)
        m.AppendSeparator()
        # Copy/Cut/Paste are gated only on a loaded radio (not on having a
        # selection / non-empty clipboard): disabling a menu item also disables
        # its accelerator, and the item wouldn't be re-enabled until the menu
        # reopened — so Ctrl+V right after Ctrl+C would be dead. Keeping them live
        # and letting the handlers announce "Clipboard is empty" / "No channel
        # selected" is both correct and more discoverable.
        self._add(m, "copy", "&Copy\tCtrl+C", self.on_copy, needs_radio=True)
        self._add(m, "cut", "Cu&t\tCtrl+X", self.on_cut, needs_radio=True)
        self._add(m, "paste", "&Paste\tCtrl+V", self.on_paste, needs_radio=True)
        return m

    def _build_radio_menu(self) -> wx.Menu:
        m = wx.Menu()
        self._add(m, "download", "&Download from Radio\tCtrl+Shift+D", self.on_download)
        self._add(m, "upload", "&Upload to Radio\tCtrl+Shift+U", self.on_upload, needs_radio=True)
        self._add(m, "favorites", "&Favorite radios…", self.on_favorites)
        m.AppendSeparator()
        self._add(m, "settings", "&Settings…\tCtrl+Shift+P", self.on_settings, needs_radio=True)
        self._add(m, "radio_info", "Radio &Info…", self.on_radio_info, needs_radio=True)
        m.AppendSeparator()
        # Query Source submenu (online repeater directories). Gated on a loaded
        # radio — results import into it. RadioReference will slot in here later.
        query = wx.Menu()
        self._add(query, "query_repeaterbook", "&RepeaterBook…",
                  self.on_repeaterbook, needs_radio=True)
        self._add(query, "query_freqlists", "&Frequency lists…",
                  self.on_frequency_lists, needs_radio=True)
        m.AppendSubMenu(query, "&Query Source")
        return m

    def _build_channels_menu(self) -> wx.Menu:
        m = wx.Menu()
        self._add(m, "edit", "&Edit channel…\tCtrl+E", self.on_edit_channel, needs_radio=True)
        self._add(m, "edit_cell", "Edit ce&ll…\tF2", self.on_edit_cell, needs_radio=True)
        # Delete needs a menu accelerator, not just the in-grid Del key: a focused
        # native DataViewListCtrl (NSTableView) can swallow EVT_KEY_DOWN on macOS,
        # and macOS has no keyboard context-menu, so the accelerator is the only
        # reliable, discoverable Delete path cross-platform.
        self._add(m, "delete", "&Delete channel(s)\tDel", self.on_delete_channels, needs_radio=True)
        self._add(m, "goto", "&Go to channel…\tCtrl+G", self.on_goto, needs_radio=True)
        self._add(m, "banks", "Channel &banks…\tCtrl+B", self.on_banks, needs_radio=True)
        m.AppendSeparator()
        self._add(m, "move_up", "Move &up\tCtrl+Shift+Up", self.on_move_up, needs_radio=True)
        self._add(m, "move_down", "Move &down\tCtrl+Shift+Down", self.on_move_down, needs_radio=True)
        self._add(m, "move_to", "&Move to channel…\tCtrl+Shift+M", self.on_move_to, needs_radio=True)
        self._add(m, "organize", "Bulk &operations…\tCtrl+M", self.on_organize, needs_radio=True)
        m.AppendSeparator()
        self._add(m, "find", "&Find…\tCtrl+F", self.on_find, needs_radio=True)
        self._add(m, "find_next", "Find &next\tF3", self.on_find_next, needs_radio=True)
        return m

    def _build_help_menu(self) -> wx.Menu:
        m = wx.Menu()
        # Mnemonics here are all distinct: G, K, S, A. "Keyboard Shortcuts" gave
        # up its K (it was the only K) so the full reference — the document a
        # user is told to go read — can have it.
        self._add(m, "getting_started", "&Getting Started", self.on_getting_started)
        self._add(m, "keyboard_commands", "&Keyboard Commands", self.on_keyboard_commands)
        m.AppendSeparator()
        self._add(m, "shortcuts", "Keyboard &Shortcuts\tF1", self.on_shortcuts)
        self._add(m, "about", "&About", self.on_about)
        return m

    def _update_menu_state(self) -> None:
        loaded = radio_backend.get_state().loaded
        for key in self._radio_gated_keys:
            self._menu_items[key].Enable(loaded)

    # -- channel handlers ---------------------------------------------

    def on_edit_channel(self, _evt=None) -> None:
        """Edit the focused channel in a native dialog, then refresh that row."""
        number = self.grid.focused_channel()
        if number is None:
            self.announce.announce("No channel selected.")
            return
        state = radio_backend.get_state()
        mem = radio_backend.get_memory(number)
        if mem is None:
            return
        from vrp.edit_dialog import EditChannelDialog
        from chirp_backend import memory_ops
        from vrp.config import get_config

        apply_defaults = bool(get_config().get("auto_band_defaults", False))
        with EditChannelDialog(self, number, mem, state.features,
                               apply_band_defaults=apply_defaults) as dlg:
            if dlg.ShowModal() != wx.ID_OK:
                self.grid.select_channels([number])
                self.grid.focus_channel(number)
                return
            ok, message, _affected = memory_ops.update_channel(number, dlg.get_values())
        self.grid.refresh_numbers([number])
        self.grid.select_channels([number])
        self.grid.focus_channel(number)
        self.announce.announce(message, assertive=not ok)

    def on_edit_cell(self, _evt=None) -> None:
        """Edit a single field of the focused channel (F2).

        Where the grid has a Left/Right cell cursor (Windows and macOS — see
        ``has_cell_cursor``), F2 edits the cell you arrowed to; the row-header
        ("number") and immutable columns have nothing single-cell to edit, so they
        open the whole-channel dialog. Where there's no cursor (GTK/other), F2 asks
        which field to edit via ``ColumnPickerDialog``, then edits it — so F2 does
        single-cell editing everywhere."""
        number = self.grid.focused_channel()
        if number is None:
            self.announce.announce("No channel selected.")
            return
        mem = radio_backend.get_memory(number)
        if mem is None:
            return

        if self.grid.has_cell_cursor:
            # Windows: edit exactly the cell the Left/Right cursor is on.
            cell = self.grid.focused_cell()
            col_name = cell[1] if cell else "number"
            if col_name == "number" or col_name in (mem.immutable or []):
                self.on_edit_channel()  # nothing single-cell here -> whole channel
                return
            col = self._column_by_name(col_name)
            if col is None:
                self.on_edit_channel()
                return
            self._edit_cell_column(number, mem, col)
            return

        # No cell cursor (GTK/other) — ask which field, then edit it.
        columns = self._editable_columns(mem)
        if not columns:
            self.on_edit_channel()  # nothing single-cell editable (all immutable)
            return
        from vrp.edit_dialog import ColumnPickerDialog

        with ColumnPickerDialog(self, number, columns) as picker:
            chosen = picker.get_column() if picker.ShowModal() == wx.ID_OK else None
        if chosen is None:  # cancelled — restore focus to the row
            self.grid.select_channels([number])
            self.grid.focus_channel(number)
            return
        self._edit_cell_column(number, mem, chosen)

    def _column_by_name(self, col_name: str):
        """The current radio's ``ColumnDef`` for ``col_name``, or ``None``."""
        from chirp_backend.col_defs import build_column_defs

        return next(
            (c for c in build_column_defs(radio_backend.get_state().features)
             if c.name == col_name),
            None,
        )

    def _editable_columns(self, mem) -> list:
        """The channel's single-cell-editable columns — the fields F2's
        column-picker offers where there's no cell cursor (GTK/other). Delegates
        the (headless, tested) predicate to ``col_defs.editable_columns``."""
        from chirp_backend.col_defs import build_column_defs, editable_columns

        return editable_columns(
            build_column_defs(radio_backend.get_state().features), mem.immutable
        )

    def _edit_cell_column(self, number: int, mem, col) -> None:
        """Open ``EditCellDialog`` for one column, then apply + refresh +
        announce. Shared by the Windows cursor path and the macOS picker path."""
        from chirp_backend import memory_ops
        from vrp.edit_dialog import EditCellDialog

        with EditCellDialog(self, number, mem, col) as dlg:
            if dlg.ShowModal() != wx.ID_OK:
                self.grid.select_channels([number])
                self.grid.focus_channel(number)
                return
            # set_channel_field also sets the governing field when a lone edit
            # wouldn't otherwise persist (a tone whose Tone Mode is off, or a
            # Duplex direction with no offset), so the edit actually sticks; note
            # describes any such coupled change to announce.
            ok, message, _affected, note = memory_ops.set_channel_field(
                number, col.name, dlg.get_value()
            )
        self.grid.refresh_numbers([number])
        self.grid.select_channels([number])
        self.grid.focus_channel(number)
        if ok:
            # Re-announce the edited cell's NEW value, in the same
            # "<value>, <column>" form the Left/Right cursor speaks, so the user
            # hears the result of their edit (not just "channel updated").
            # Non-assertive so it queues behind the screen reader's focus read of
            # the row rather than clipping it.
            shown = self.grid.cell_display(number, col.name)
            msg = f"{shown if shown else 'blank'}, {col.label}"
            if note:
                msg += f". {note}"
            self.announce.announce(msg)
        else:
            self.announce.announce(message, assertive=True)

    # -- context menu / delete / selection feedback -------------------

    def on_grid_context_menu(self, event) -> None:
        """Row actions menu — opened by the Applications key, Shift+F10, or a
        right-click. A real ``wx.Menu``, so NVDA reads it and arrow-navigates it
        for free. Without this binding the context key just errors."""
        if not radio_backend.get_state().loaded:
            return
        number = self.grid.focused_channel()
        if number is None:
            return
        sel = self.grid.selected_count()
        menu = wx.Menu()

        def add(label, handler):
            item = menu.Append(wx.ID_ANY, label)
            self.grid.Bind(wx.EVT_MENU, lambda _e: handler(), item)

        # Undo/Redo first, labelled with the op they'd reverse/replay (or a
        # disabled item when there's nothing).
        from chirp_backend.radio import get_undo_manager

        mgr = get_undo_manager()
        ulabel = mgr.peek_undo_label() if mgr else None
        rlabel = mgr.peek_redo_label() if mgr else None
        if ulabel:
            add(f"&Undo {self._menu_safe(ulabel)}\tCtrl+Z", self.on_undo)
        else:
            menu.Append(wx.ID_ANY, "&Undo\tCtrl+Z").Enable(False)
        if rlabel:
            add(f"&Redo {self._menu_safe(rlabel)}\tCtrl+Y", self.on_redo)
        else:
            menu.Append(wx.ID_ANY, "&Redo\tCtrl+Y").Enable(False)
        menu.AppendSeparator()

        add(f"&Edit channel {number}\tCtrl+E", self.on_edit_channel)
        # Single-cell edit. With a cell cursor (Windows/macOS), name the exact
        # column the cursor is on ("Edit cell — Frequency"); without one (GTK),
        # offer a generic entry that opens F2's field-picker (on_edit_cell
        # handles both).
        if self.grid.has_cell_cursor:
            cell = self.grid.focused_cell()
            if cell is not None:
                _cn, col_name = cell
                cmem = radio_backend.get_memory(number)
                if col_name != "number" and cmem is not None and col_name not in (cmem.immutable or []):
                    col = self._column_by_name(col_name)
                    if col is not None:
                        add(f"Edit ce&ll — {col.label}\tF2", self.on_edit_cell)
        else:
            add("Edit a &field…\tF2", self.on_edit_cell)
        add(
            "&Delete selected channels\tDel" if sel > 1 else f"&Delete channel {number}\tDel",
            self.on_delete_channels,
        )
        menu.AppendSeparator()
        add(
            "&Copy selected channels\tCtrl+C" if sel > 1 else f"&Copy channel {number}\tCtrl+C",
            self.on_copy,
        )
        add(
            "Cu&t selected channels\tCtrl+X" if sel > 1 else f"Cu&t channel {number}\tCtrl+X",
            self.on_cut,
        )
        if self._clipboard is not None:
            add(f"&Paste {len(self._clipboard.mems)} channel(s) here\tCtrl+V", self.on_paste)
        else:
            disabled = menu.Append(wx.ID_ANY, "&Paste\tCtrl+V")
            disabled.Enable(False)  # nothing on the clipboard yet
        add(
            "E&xport selected channels to CSV…" if sel > 1
            else f"E&xport channel {number} to CSV…",
            self.on_export_selected_csv,
        )
        menu.AppendSeparator()
        add("Move &up\tCtrl+Shift+Up", self.on_move_up)
        add("Move &down\tCtrl+Shift+Down", self.on_move_down)
        add("&Move to channel…\tCtrl+Shift+M", self.on_move_to)
        # Sort the selected channels in place (values redistributed into the
        # same slots in order — safe for a non-contiguous selection). Only
        # meaningful with two or more selected.
        if sel > 1:
            sort_menu = wx.Menu()

            def add_sort(label, attr):
                item = sort_menu.Append(wx.ID_ANY, label)
                self.grid.Bind(
                    wx.EVT_MENU, lambda _e, a=attr: self._sort_selected(a), item
                )

            add_sort("&Name (A to Z)", "name")
            add_sort("&Receive frequency (low to high)", "freq")
            add_sort("&Transmit frequency (low to high)", "txfreq")
            menu.AppendSubMenu(sort_menu, f"&Sort {sel} selected channels by")
        add("Bulk &operations…", self.on_organize)
        menu.AppendSeparator()
        add("&Go to channel…\tCtrl+G", self.on_goto)
        add("Channel &banks…", self.on_banks)

        # The native list places the menu sensibly on the focused row; exact
        # pixel position is irrelevant to a screen-reader user.
        self.grid.popup_row_menu(menu)
        menu.Destroy()

    def on_delete_channels(self, _evt=None) -> None:
        """Delete the selected (or focused) channel(s), clearing their contents.
        Reachable from the Delete key and the row context menu."""
        from chirp_backend import memory_ops as mo

        if not radio_backend.get_state().loaded:
            self.announce.announce("No radio image is open.", assertive=True)
            return
        numbers = self.grid.selected_channel_numbers()
        if not numbers:
            self.announce.announce("No channel selected.")
            return
        first, last, count = numbers[0], numbers[-1], len(numbers)
        rng = f"channel {first}" if count == 1 else f"{count} channels, {first} to {last}"
        if not self._confirm(
            f"Delete {rng}? Their contents will be cleared. You can undo this with Ctrl+Z."
        ):
            return
        ok, message, _affected = mo.delete_range(numbers)
        if not ok:
            self.announce.announce(message, assertive=True)
            return
        # Plain delete clears slots in place — no rows shift — so repaint just
        # the affected rows. A full rebuild() is unnecessary here and jars the
        # screen-reader focus; keep it for the structural ops in on_organize.
        self.grid.refresh_numbers(numbers)
        low, high = radio_backend.get_state().memory_bounds
        target = min(max(first, low), high)
        self.grid.select_channels([target])
        self.grid.focus_channel(target)
        self.announce.announce(f"{message} Now on channel {target}.", assertive=True)

    def _on_grid_selection_changed(self, event) -> None:
        """Announce the multi-select count once the selection settles, so building
        a Shift+arrow range is audible. A single item that just follows the cursor
        stays quiet (NVDA already reads the focused row), avoiding announce-on-every-
        move noise."""
        event.Skip()
        if self._sel_timer is not None:
            self._sel_timer.Stop()
        self._sel_timer = wx.CallLater(180, self._announce_selection_count)

    def _announce_selection_count(self) -> None:
        self._sel_timer = None
        # A Space/Ctrl+Space toggle already spoke a per-row message stating the
        # count, so skip the debounced count this once to avoid doubling up.
        if self._suppress_next_count:
            self._suppress_next_count = False
            return
        count = self.grid.selected_count()
        if count >= 2:
            self.announce.announce(f"{count} channels selected")

    def _on_select_toggle(self, number: int, selected: bool, count: int) -> None:
        """Announce a Space/Ctrl+Space selection toggle of the focused row. The
        per-row message already states the running count, so suppress the debounced
        count announce that the selection-changed event also schedules."""
        self._suppress_next_count = True
        verb = "Selected" if selected else "Deselected"
        tail = "none selected" if count == 0 else f"{count} selected"
        self.announce.announce(f"{verb} channel {number}. {tail}.")

    # -- selection commands (Edit menu) ------------------------------

    def on_select_all(self, _evt=None) -> None:
        """Select every channel (Edit ▸ Select All / Ctrl+A)."""
        if not radio_backend.get_state().loaded:
            self.announce.announce("No radio image is open.", assertive=True)
            return
        self.grid.select_all()
        # select_all fires the selection-changed event; its debounced count
        # announce would duplicate ours, so suppress it once.
        self._suppress_next_count = True
        self.announce.announce(f"Selected all {self.grid.selected_count()} channels.")

    def on_clear_selection(self, _evt=None) -> None:
        """Clear the selection (Edit ▸ Clear Selection)."""
        if not radio_backend.get_state().loaded:
            self.announce.announce("No radio image is open.", assertive=True)
            return
        self.grid.clear_selection()
        self._suppress_next_count = True
        self.announce.announce("Selection cleared.")

    # -- undo / redo --------------------------------------------------

    def on_undo(self, _evt=None) -> None:
        """Undo the last channel operation (Ctrl+Z)."""
        self._history_step("undo", "Undone")

    def on_redo(self, _evt=None) -> None:
        """Redo the last undone channel operation (Ctrl+Y)."""
        self._history_step("redo", "Redone")

    def _history_step(self, which: str, verb: str) -> None:
        from chirp_backend.radio import get_undo_manager

        if not radio_backend.get_state().loaded:
            self.announce.announce("No radio image is open.", assertive=True)
            return
        mgr = get_undo_manager()
        result = (mgr.undo() if which == "undo" else mgr.redo()) if mgr else None
        if result is None:
            self.announce.announce(f"Nothing to {which}.")
            return
        label, numbers = result
        # The op rewrote these channels; refresh the whole grid (a structural op
        # may have shifted rows) and re-anchor on the affected block.
        self.grid.rebuild()
        numbers = sorted(n for n in numbers) if numbers else []
        if numbers:
            low, high = radio_backend.get_state().memory_bounds
            target = min(max(numbers[0], low), high)
            self.grid.select_channels([n for n in numbers if low <= n <= high])
            self.grid.focus_channel(target)
            self.announce.announce(f"{verb}: {label}. Now on channel {target}.",
                                   assertive=True)
        else:
            self.announce.announce(f"{verb}: {label}.", assertive=True)

    def _on_menu_open(self, event) -> None:
        """When the Edit menu opens, relabel Undo/Redo with the op they'd act on
        (e.g. 'Undo Deleted channel 5'). Relabeling doesn't affect accelerators."""
        if event.GetMenu() is getattr(self, "_edit_menu", None):
            from chirp_backend.radio import get_undo_manager

            mgr = get_undo_manager()
            u = mgr.peek_undo_label() if mgr else None
            r = mgr.peek_redo_label() if mgr else None
            self._menu_items["undo"].SetItemLabel(
                (f"&Undo {self._menu_safe(u)}" if u else "&Undo") + "\tCtrl+Z")
            self._menu_items["redo"].SetItemLabel(
                (f"&Redo {self._menu_safe(r)}" if r else "&Redo") + "\tCtrl+Y")
        event.Skip()

    @staticmethod
    def _menu_safe(text: str) -> str:
        """A menu-safe op label: escape mnemonic '&', drop tabs/newlines, and
        keep it short so the menu item stays readable."""
        text = text.replace("&", "&&").replace("\t", " ").replace("\n", " ").strip()
        return text if len(text) <= 50 else text[:49] + "…"

    # -- clipboard: cut / copy / paste (whole rows) -------------------

    def _snapshot_selection(self) -> tuple[list[int], list] | None:
        """The selected channel numbers and deep-copied Memory snapshots, or None
        (with an announcement) when nothing is available to act on.

        A channel that can't be read (``get_memory`` returns None) is skipped
        rather than crashing on ``.dupe()``; the returned numbers match the
        snapshots actually captured, so a later cut erases only what was copied."""
        if not radio_backend.get_state().loaded:
            self.announce.announce("No radio image is open.", assertive=True)
            return None
        numbers = self.grid.selected_channel_numbers()
        if not numbers:
            self.announce.announce("No channel selected.")
            return None
        readable: list[int] = []
        mems = []
        for n in numbers:
            mem = radio_backend.get_memory(n)
            if mem is None:
                continue
            readable.append(n)
            mems.append(mem.dupe())
        if not mems:
            self.announce.announce(
                "Could not read the selected channel(s).", assertive=True
            )
            return None
        return readable, mems

    def on_copy(self, _evt=None) -> None:
        """Copy the selected channel(s) to the in-app clipboard (source kept)."""
        snap = self._snapshot_selection()
        if snap is None:
            return
        numbers, mems = snap
        self._clipboard = _Clipboard("copy", mems, list(numbers))
        self.announce.announce(f"Copied {len(mems)} channel(s).")

    def on_cut(self, _evt=None) -> None:
        """Cut the selected channel(s) to the clipboard. Deferred: the source is
        untouched until paste, which then moves them (erasing the source)."""
        snap = self._snapshot_selection()
        if snap is None:
            return
        numbers, mems = snap
        self._clipboard = _Clipboard("cut", mems, list(numbers))
        self.announce.announce(f"Cut {len(mems)} channel(s). Paste to move them.")

    def on_paste(self, _evt=None) -> None:
        """Paste the clipboard at the focused channel. Overwrites by default; when
        the destination is occupied, asks whether to overwrite or make room (shift
        the existing channels down). A cut paste moves (erases the source) and
        empties the clipboard; a copy paste keeps it for pasting again."""
        from chirp_backend import memory_ops

        if not radio_backend.get_state().loaded:
            self.announce.announce("No radio image is open.", assertive=True)
            return
        clip = self._clipboard
        if clip is None:
            self.announce.announce("Clipboard is empty.")
            return
        dest = self.grid.focused_channel()
        if dest is None:
            self.announce.announce("No channel selected.")
            return
        n = len(clip.mems)
        low, high = radio_backend.get_state().memory_bounds
        if dest + n - 1 > high:
            self.announce.announce(
                f"Not enough room: pasting {n} channel(s) at {dest} runs past "
                f"channel {high}.",
                assertive=True,
            )
            return

        cut_from = clip.source_numbers if clip.mode == "cut" else None
        cut_set = set(cut_from or [])
        # Occupied destination slots that aren't sources being moved out. An
        # unreadable slot (get_memory None) is treated as empty here — consistent
        # with _destination_occupied / _first_empty_channel — so it never crashes
        # on `.empty`; paste_block does the real write regardless.
        occupied = []
        for k in range(dest, dest + n):
            if k in cut_set:
                continue
            mem = radio_backend.get_memory(k)
            if mem is not None and not mem.empty:
                occupied.append(k)
        make_room = False
        if occupied:
            choice = self._ask_paste_conflict(dest, dest + n - 1, len(occupied))
            if choice is None:
                return  # cancelled — clipboard kept
            make_room = choice == "move"

        ok, message, _affected = memory_ops.paste_block(
            clip.mems, dest, cut_from=cut_from, make_room=make_room
        )
        if not ok:
            self.announce.announce(message, assertive=True)
            return

        # A paste can shift many rows (make_room) or just overwrite a few; either
        # way the same radio's rows changed, so refresh in place and re-anchor on
        # the pasted block.
        self.grid.reorder_refresh()
        self.grid.select_channels(list(range(dest, dest + n)))
        self.grid.focus_channel(dest)
        if clip.mode == "cut":
            self._clipboard = None  # cut is one-shot
        self.announce.announce(f"{message}. Now on channel {dest}.", assertive=True)

    def _ask_paste_conflict(self, first: int, last: int, occupied: int) -> str | None:
        """Ask how to resolve a paste onto occupied channels. Returns
        ``"overwrite"``, ``"move"`` (make room by shifting down), or ``None``
        (cancel). A native message dialog: focus-trapped, Esc cancels, focus
        returns to the grid afterward."""
        where = f"Channel {first} is" if first == last else f"Channels {first} to {last} are"
        msg = (
            f"{where} not empty ({occupied} occupied). Overwrite the destination, "
            "or make room by moving the existing channels down?"
        )
        dlg = wx.MessageDialog(
            self, msg, "Paste — destination not empty",
            wx.YES_NO | wx.CANCEL | wx.ICON_QUESTION,
        )
        dlg.SetYesNoCancelLabels("Overwrite", "Make room", "Cancel")
        try:
            result = dlg.ShowModal()
        finally:
            dlg.Destroy()
            self.grid.SetFocus()
        if result == wx.ID_YES:
            return "overwrite"
        if result == wx.ID_NO:
            return "move"
        return None

    def on_goto(self, _evt=None) -> None:
        """Go to a specific channel by number — prompt, select, and focus it."""
        low, high = radio_backend.get_state().memory_bounds
        n = wx.GetNumberFromUser(
            "Go to channel:", "Channel", "Go to channel", low, low, high, self
        )
        if n == -1:
            return
        self.grid.select_channels([n])
        self.grid.focus_channel(n)
        self.announce.announce(f"Channel {n}")

    def on_banks(self, _evt=None) -> None:
        """Open the banks dialog for the focused channel; apply changes."""
        from chirp_backend import bank_ops
        from vrp.bank_dialog import ChannelBanksDialog

        number = self.grid.focused_channel()
        if number is None:
            self.announce.announce("No channel selected.")
            return
        state = bank_ops.get_bank_state(number)
        if not state.get("ok"):
            self.announce.announce(state.get("message", "Banks unavailable."), assertive=True)
            return

        dlg = ChannelBanksDialog(self, state)
        applied = dlg.ShowModal() == wx.ID_OK and not state["read_only"]
        desired = dlg.get_desired_indexes() if applied else None
        dlg.Destroy()

        if desired is not None:
            ok, message, _affected = bank_ops.apply_bank_changes(number, desired)
            if ok:
                self.announce.announce(message)
            else:
                self.announce.announce(message, assertive=True)
                wx.MessageBox(message, "Banks", wx.OK | wx.ICON_ERROR, self)
        # Return focus to the channel row.
        self.grid.select_channels([number])
        self.grid.focus_channel(number)

    @staticmethod
    def _now_at_phrase(block: list[int]) -> str:
        """Screen-reader phrase for where focus landed after a move/copy.

        Callers prepend their own separator (e.g. ``f"{message}. {phrase}"``).
        """
        first, last = block[0], block[-1]
        if first == last:
            return f"Now on channel {first}."
        return f"Now at channels {first} to {last}, on channel {first}."

    def _do_move(self, direction: int) -> None:
        """Shared implementation for move-up / move-down."""
        from chirp_backend import memory_ops
        from vrp.native import grid_model

        numbers = self.grid.selected_channel_numbers()
        if not numbers:
            return
        ok, message, _affected = memory_ops.move_memories(numbers, direction)
        if ok:
            self.grid.reorder_refresh()
            new_sel, focus = grid_model.selection_after_move(numbers, direction)
            self.grid.select_channels(new_sel)
            self.grid.focus_channel(focus)
            self.announce.announce(f"{message}. {self._now_at_phrase(new_sel)}")
        else:
            self.announce.announce(message, assertive=True)

    def on_move_up(self, _evt=None) -> None:
        self._do_move(-1)

    def on_move_down(self, _evt=None) -> None:
        self._do_move(1)

    def on_move_to(self, _evt=None) -> None:
        """Move the selected channel(s) to start at a user-chosen channel."""
        from chirp_backend import memory_ops
        from vrp.native import grid_model

        numbers = self.grid.selected_channel_numbers()
        if not numbers:
            return
        low, high = radio_backend.get_state().memory_bounds
        dest = wx.GetNumberFromUser(
            f"Move {len(numbers)} channel(s) to start at channel:",
            "Destination", "Move to channel", low, low, high, self,
        )
        if dest == -1:
            return
        ok, message, _affected = memory_ops.move_to(numbers, dest)
        if ok:
            self.grid.reorder_refresh()
            new_sel, focus = grid_model.selection_after_move_to(len(numbers), dest)
            self.grid.select_channels(new_sel)
            self.grid.focus_channel(focus)
            self.announce.announce(f"{message}. {self._now_at_phrase(new_sel)}")
        else:
            self.announce.announce(message, assertive=True)

    def _sort_selected(self, attr: str, reverse: bool = False) -> None:
        """Sort the selected channels in place by ``attr`` ('name', 'freq', or
        the synthetic 'txfreq'). Reachable from the row context menu's Sort
        submenu. The selection may be non-contiguous — ``sort_range`` writes the
        sorted contents back into the same slots in order."""
        from chirp_backend import memory_ops as mo

        if not radio_backend.get_state().loaded:
            self.announce.announce("No radio image is open.", assertive=True)
            return
        numbers = self.grid.selected_channel_numbers()
        if len(numbers) < 2:
            self.announce.announce("Select two or more channels to sort.", assertive=True)
            return
        ok, message, affected = mo.sort_range(numbers, attr, reverse)
        if not ok:
            self.announce.announce(message, assertive=True)
            return
        # Sort changes cell values in place; no rows shift, so a targeted
        # refresh keeps the screen-reader focus steadier than a full rebuild.
        self.grid.refresh_numbers(affected)
        self.grid.select_channels(affected)
        self.grid.focus_channel(affected[0])
        self.announce.announce(f"{message} {self._now_at_phrase(affected)}")

    def on_organize(self, _evt=None) -> None:
        """Open the Bulk operations dialog; dispatch the chosen operation."""
        from chirp_backend import memory_ops as mo
        from vrp.native import grid_model
        from vrp.ops_dialog import ChannelOperationsDialog

        state = radio_backend.get_state()
        if not state.loaded:
            self.announce.announce("No radio image is open.", assertive=True)
            return
        low, high = state.memory_bounds
        default_from = self.grid.focused_channel() or low
        columns = [(c["name"], c["label"]) for c in grid_model.column_meta(state)]
        # Transmit frequency is not a stored column (it's computed from freq +
        # duplex + offset), but users want to sort by it, so offer it too.
        columns.append(("txfreq", "Transmit frequency"))
        with ChannelOperationsDialog(self, low, high, default_from, columns) as dlg:
            if dlg.ShowModal() != wx.ID_OK:
                return
            numbers, _err = dlg.selected_numbers()
            op = dlg.get_operation()

        key = op["op"]
        if key == "export_csv":
            # Not a memory mutation: no confirm, undo, or grid refresh — just
            # write the chosen channels out to a separate CSV file.
            self._do_csv_export(numbers)
            return
        confirm = self._op_confirm_message(key, op, numbers)
        if confirm and not self._confirm(confirm):
            return
        if key in ("move_to", "copy_to") and self._destination_occupied(
            op["dest"], len(numbers)
        ):
            verb = "moved" if key == "move_to" else "copied"
            if not self._confirm(
                f"Channels at {op['dest']} and following are not empty and will "
                f"be overwritten by the {verb} channels. Continue?"
            ):
                return

        runner = {
            "delete": lambda: mo.delete_range(numbers),
            "delete_shift": lambda: mo.delete_and_shift(numbers, op.get("mode", "all")),
            "insert": lambda: mo.insert_row(numbers[0]),
            "move_up": lambda: mo.move_memories(numbers, -1),
            "move_down": lambda: mo.move_memories(numbers, 1),
            "move_to": lambda: mo.move_to(numbers, op["dest"]),
            "copy_to": lambda: mo.copy_memories(numbers, op["dest"]),
            "sort": lambda: mo.sort_range(numbers, op["attr"], op["reverse"]),
            "arrange": lambda: mo.arrange_range(numbers),
        }.get(key)
        if runner is None:
            return
        ok, message, _affected = runner()

        if not ok:
            self.announce.announce(message, assertive=True)
            return

        if key in ("move_up", "move_down", "move_to", "copy_to"):
            # Reorder ops: refresh without ClearAll (preserves screen-reader focus),
            # then reselect the entire moved/copied block.
            self.grid.reorder_refresh()
            if key in ("move_up", "move_down"):
                direction = -1 if key == "move_up" else 1
                block, focus = grid_model.selection_after_move(numbers, direction)
            else:
                dest = op["dest"]
                block, focus = grid_model.selection_after_move_to(len(numbers), dest)
            self.grid.select_channels(block)
            self.grid.focus_channel(focus)
            self.announce.announce(f"{message} {self._now_at_phrase(block)}")
        else:
            # Structural ops (delete, insert, sort, arrange): full rebuild needed,
            # land on the single logical focus target.
            self.grid.rebuild()
            target = self._op_focus_target(key, numbers, op)
            self.grid.select_channels([target])
            self.grid.focus_channel(target)
            self.announce.announce(f"{message} {self._now_at_phrase([target])}")

    def _op_focus_target(self, key: str, numbers: list[int], op: dict) -> int:
        """Mirror of app.py _op_focus_target: where focus lands after an organize op."""
        low, high = radio_backend.get_state().memory_bounds
        if key in ("move_to", "copy_to"):
            target = op["dest"]
        elif key == "move_up":
            target = numbers[0] - 1
        elif key == "move_down":
            target = numbers[0] + 1
        else:
            target = numbers[0]
        return min(max(target, low), high)

    def _op_confirm_message(self, key: str, op: dict, numbers: list[int]) -> str | None:
        """Return a confirmation prompt for destructive/reordering ops, or None."""
        first, last, count = numbers[0], numbers[-1], len(numbers)
        rng = f"{count} channel(s), {first} to {last}"
        if key == "delete":
            return (
                f"Delete {rng}? Their contents will be cleared. "
                "You can undo this with Ctrl+Z."
            )
        if key == "delete_shift":
            scope = (
                "and shift all higher channels down to close the gap (this renumbers them)"
                if op.get("mode", "all") == "all"
                else "and shift channels within the block"
            )
            return f"Delete {rng} {scope}? You can undo this with Ctrl+Z."
        if key == "sort":
            order = "descending" if op.get("reverse") else "ascending"
            return (
                f"Sort {rng} by {op.get('attr')} {order}? This reorders and "
                "renumbers these channels. You can undo this with Ctrl+Z."
            )
        if key == "arrange":
            return (
                f"Compact {rng}, removing empty slots? Channels will be "
                "renumbered. You can undo this with Ctrl+Z."
            )
        return None

    def _destination_occupied(self, dest: int, count: int) -> bool:
        """True if any of the target slots are non-empty."""
        low, high = radio_backend.get_state().memory_bounds
        for n in range(dest, min(high, dest + count - 1) + 1):
            mem = radio_backend.get_memory(n)
            if mem is not None and not getattr(mem, "empty", True):
                return True
        return False

    def on_find(self, _evt=None) -> None:
        """Open the Find dialog; jump to and announce the first match."""
        from chirp_backend import memory_ops
        from vrp.find_dialog import FindDialog

        if not radio_backend.get_state().loaded:
            self.announce.announce("No radio image is open.", assertive=True)
            return

        def _search(query: str, fields: tuple) -> bool:
            self._find_query = query
            self._find_fields = fields
            ok, _message, affected = memory_ops.find(query, None, fields)
            if not ok:
                return False
            self._find_last = affected[0]
            return True

        dlg = FindDialog(self, _search)
        found = dlg.ShowModal() == wx.ID_OK
        dlg.Destroy()
        if found and self._find_last is not None:
            n = self._find_last
            self.grid.select_channels([n])
            self.grid.focus_channel(n)
            self.announce.announce(self._describe_match(n, prefix="Found "))
        else:
            self.grid.SetFocus()

    def on_find_next(self, _evt=None) -> None:
        """Continue the last find, wrapping if needed; announce the result."""
        from chirp_backend import memory_ops

        if not radio_backend.get_state().loaded:
            self.announce.announce("No radio image is open.", assertive=True)
            return
        if not self._find_query:
            self.announce.announce("No active search. Press Ctrl+F to find.", assertive=True)
            return
        low, _high = radio_backend.get_state().memory_bounds
        start = (self._find_last + 1) if self._find_last is not None else low
        ok, _message, affected = memory_ops.find(
            self._find_query, start, self._find_fields
        )
        if not ok:
            self.announce.announce(
                f"No matches for '{self._find_query}'.", assertive=True
            )
            return
        prev = self._find_last
        ch = affected[0]
        self._find_last = ch
        self.grid.select_channels([ch])
        self.grid.focus_channel(ch)
        if prev is not None and ch == prev:
            prefix = "Only match. "
        elif prev is not None and ch <= prev:
            prefix = "Wrapped to start. "
        else:
            prefix = "Next match. "
        self.announce.announce(self._describe_match(ch, prefix=prefix))

    def _describe_match(self, number: int, prefix: str = "") -> str:
        """Human-readable description of a find match."""
        from chirp_backend.col_defs import format_freq_mhz

        mem = radio_backend.get_memory(number)
        detail = ""
        if mem is not None and not getattr(mem, "empty", True):
            name = (getattr(mem, "name", "") or "").strip()
            detail = f": {name or format_freq_mhz(mem.freq)}"
        return f"{prefix}'{self._find_query}' at channel {number}{detail}."

    # -- helpers shared by handlers -----------------------------------

    def _load_into_grid(self) -> None:
        state = radio_backend.get_state()
        if state.loaded:
            self.grid.set_state(state)
            self.SetTitle(f"{state.radio.VENDOR} {state.radio.MODEL} — VRP")
        else:
            self.grid.clear()
            self.SetTitle("Versatile Radio Programmer")
        self._update_menu_state()

    def _confirm(self, message: str) -> bool:
        """Show a Yes/No confirmation dialog. Returns True if the user chose Yes."""
        dlg = wx.MessageDialog(
            self, message, "Please confirm", wx.YES_NO | wx.ICON_WARNING
        )
        dlg.SetYesNoLabels("Yes", "No")
        try:
            return dlg.ShowModal() == wx.ID_YES
        finally:
            dlg.Destroy()

    def _show_error(self, title: str, message: str) -> None:
        """Show an error in a modal, read-only, copyable edit box with an OK
        button, then return focus to the grid.

        A modal is used (not just ``announce``) so the screen reader is
        guaranteed to read the error: focus lands inside the dialog's text, so
        NVDA/VoiceOver read the title and the message directly. An announce-only
        error can be missed — after a file dialog closes, focus is ambiguous and
        a status-bar/prism cue races the screen reader's own focus chatter and
        gets dropped (the "unsupported file error not read" bug). The edit box
        (vs a MessageBox) also lets the user arrow through and copy a long driver
        error. The status bar still gets the text as a visual record."""
        from vrp.info_dialog import InfoDialog

        self.SetStatusText(message)
        dlg = InfoDialog(self, title, message, name="Error message",
                         size=(460, 160), ok_button=True)
        try:
            dlg.ShowModal()
        finally:
            dlg.Destroy()
            self.grid.SetFocus()

    # -- file handlers ------------------------------------------------

    def on_open(self, _evt=None) -> None:
        with wx.FileDialog(
            self, "Open radio image",
            wildcard="Radio images (*.img)|*.img|All files (*.*)|*.*",
            style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST,
        ) as dlg:
            if dlg.ShowModal() != wx.ID_OK:
                return
            path = dlg.GetPath()
        self._open_path(path)

    def _open_path(self, path: str) -> bool:
        """Load a radio image from ``path``, record it in recent files, refresh
        the Recent submenu, and focus the grid. Shared by File > Open and the
        Open Recent submenu. Returns True on success."""
        from vrp.config import get_config

        # Loading replaces the working image — guard unsaved edits first.
        if not self._confirm_discard_or_save():
            return False

        ok, message = radio_backend.load_image(path)
        if not ok:
            # A modal (not just announce) so the error is reliably read — see
            # _show_error. This is the "unsupported file error not read" fix.
            self._show_error("Could not open file", message)
            return False
        self._load_into_grid()
        get_config().add_recent(path)
        self._refresh_recent_menu()
        self.grid.SetFocus()
        # Status bar keeps the detailed message (vendor/model/filename); the
        # spoken cue is just the short "<name> loaded" form. Deferred and
        # interrupting for the same reason the startup "Ready" announcement
        # is: self.grid.SetFocus() above triggers NVDA's own announcement of
        # the newly focused row, and a same-tick, non-interrupting speak
        # request races that and can be silently dropped.
        self.SetStatusText(message)
        name = os.path.splitext(os.path.basename(path))[0]
        wx.CallLater(750, self._speaker.speak, f"{name} loaded", interrupt=True)
        return True

    def _open_recent(self, path: str) -> None:
        """Open a file chosen from the Open Recent submenu. A path that no longer
        exists is dropped from the list (with an announcement) rather than failing
        to load."""
        from vrp.config import get_config

        if not os.path.exists(path):
            get_config().remove_recent(path)
            self._refresh_recent_menu()
            self.announce.announce(
                f"File not found: {os.path.basename(path)}. Removed from recent files.",
                assertive=True,
            )
            self.grid.SetFocus()
            return
        self._open_path(path)

    def _on_clear_recent(self, _evt=None) -> None:
        from vrp.config import get_config

        get_config().clear_recent()
        self._refresh_recent_menu()
        self.announce.announce("Recent files cleared.")
        self.grid.SetFocus()

    def on_save(self, _evt=None) -> bool:
        """Save the loaded image. Returns True on a successful save, False on
        failure or if the user cancelled the Save As it may fall back to."""
        state = radio_backend.get_state()
        if not state.loaded:
            self.announce.announce("No radio image is open.")
            return False
        # No original path (downloaded but never saved) → Save As.
        if not state.image_path:
            return self.on_save_as(_evt)
        ok, message = radio_backend.save_image()
        self.announce.announce(message, assertive=not ok)
        return ok

    def on_save_as(self, _evt=None) -> bool:
        """Save the loaded image to a chosen path. Returns True on a successful
        save, False if the user cancelled the dialog or the save failed."""
        state = radio_backend.get_state()
        if not state.loaded:
            self.announce.announce("No radio image is open.")
            return False
        with wx.FileDialog(
            self, "Save radio image as",
            wildcard="Radio images (*.img)|*.img",
            style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT,
        ) as dlg:
            if dlg.ShowModal() != wx.ID_OK:
                return False
            path = dlg.GetPath()
        ok, message = radio_backend.save_image(path)
        self.announce.announce(message, assertive=not ok)
        if ok:
            self.SetTitle(f"{state.radio.VENDOR} {state.radio.MODEL} — VRP")
        return ok

    def _confirm_discard_or_save(self) -> bool:
        """Guard a destructive step (close, Exit, Open, Download) against
        discarding unsaved channel edits.

        Returns True if it's safe to proceed — no image loaded, no unsaved
        changes, the user chose *Don't save*, or a Save succeeded. Returns False
        to abort — the user chose Cancel, or the Save they asked for failed. On
        abort, focus returns to the grid so the screen reader lands somewhere
        sensible. The dialog is a native, focus-trapped Yes/No/Cancel message
        dialog (Escape = Cancel), read reliably by NVDA/VoiceOver.
        """
        state = radio_backend.get_state()
        if not state.loaded or not state.is_modified:
            return True
        name = (
            os.path.basename(state.image_path) if state.image_path
            else "the current radio"
        )
        dlg = wx.MessageDialog(
            self,
            f"Save changes to {name} before continuing? "
            f"Your unsaved channel edits will be lost otherwise.",
            "Unsaved changes",
            wx.YES_NO | wx.CANCEL | wx.ICON_WARNING,
        )
        dlg.SetYesNoCancelLabels("Save", "Don't save", "Cancel")
        choice = dlg.ShowModal()
        dlg.Destroy()
        if choice == wx.ID_CANCEL:
            self.grid.SetFocus()
            return False
        if choice == wx.ID_NO:
            return True  # discard unsaved changes
        # Yes → Save; veto the destructive step if the save doesn't succeed.
        saved = self.on_save()
        if not saved:
            self.grid.SetFocus()
        return saved

    def on_close_image(self, _evt=None) -> None:
        if not radio_backend.get_state().loaded:
            self.announce.announce("No radio image is open.")
            return
        if not self._confirm_discard_or_save():
            return
        radio_backend.unload()
        self._load_into_grid()
        self.announce.announce("Closed image")

    def on_exit(self, _evt=None) -> None:
        self.Close()

    def on_close_window(self, event: wx.CloseEvent) -> None:
        """EVT_CLOSE handler (window close button and File ▸ Exit). Prompt to
        save unsaved edits; veto the close if the user cancels or a save fails."""
        if event.CanVeto() and not self._confirm_discard_or_save():
            event.Veto()
            return
        self.Destroy()

    def on_import_file(self, _evt=None) -> None:
        """File > Import — import channels from another radio image file."""
        if not radio_backend.get_state().loaded:
            self.announce.announce(
                "Open or download a radio first; imported channels go into it."
            )
            return
        with wx.FileDialog(
            self, "Import channels from radio image file",
            wildcard="Radio images (*.img)|*.img|All files (*.*)|*.*",
            style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST,
        ) as dlg:
            if dlg.ShowModal() != wx.ID_OK:
                return
            path = dlg.GetPath()

        src, message = radio_backend.open_image_as_source(path)
        if src is None:
            self.announce.announce(message, assertive=True)
            wx.MessageBox(message, "Import", wx.OK | wx.ICON_ERROR, self)
            return

        lo, hi = src.get_features().memory_bounds
        count = 0
        for n in range(lo, hi + 1):
            try:
                if not getattr(src.get_memory(n), "empty", True):
                    count += 1
            except Exception:  # noqa: BLE001
                continue
        if count == 0:
            self.announce.announce("That image has no channels to import.")
            return
        self._import_results(src, count)

    def _import_results(self, src_radio, count: int, numbers=None) -> None:
        """Shared import flow: pick destination, import, refresh grid, focus.

        ``numbers`` optionally restricts the import to specific source channel
        numbers (the rows checked in the results picker); None imports all.
        """
        from chirp_backend import memory_ops
        from vrp.query_dialogs import ImportDestinationDialog

        low, high = radio_backend.get_state().memory_bounds
        dlg = ImportDestinationDialog(
            self, count, low, high, self._first_empty_channel()
        )
        ok = dlg.ShowModal() == wx.ID_OK
        dest = dlg.get_destination() if ok else None
        overwrite = dlg.get_overwrite() if ok else False
        dlg.Destroy()
        if not ok:
            self.grid.SetFocus()
            return

        ok, message, affected = memory_ops.import_memories(
            src_radio, dest, overwrite, numbers=numbers
        )
        if ok:
            self._load_into_grid()
            target = affected[0] if affected else dest
            self.grid.focus_channel(target)
            self.announce.announce(message)
        else:
            self.announce.announce(message, assertive=True)
            wx.MessageBox(message, "Import", wx.OK | wx.ICON_ERROR, self)

    def _first_empty_channel(self) -> int:
        low, high = radio_backend.get_state().memory_bounds
        for n in range(low, high + 1):
            mem = radio_backend.get_memory(n)
            if mem is None or getattr(mem, "empty", True):
                return n
        return low

    def on_frequency_lists(self, _evt=None) -> None:
        """Radio ▸ Query Source ▸ Frequency lists.

        Import one of CHIRP's stock frequency lists (NOAA weather, FRS/GMRS,
        MURS, Marine VHF, …) into the loaded radio. A local import — the chosen
        CSV is opened as a source and run through the shared import flow, which
        prompts for the starting channel and overwrite/skip. Requires a loaded
        radio (imported channels go into it)."""
        from chirp_backend import stock_configs

        if not radio_backend.get_state().loaded:
            self.announce.announce(
                "Open or download a radio first; imported channels go into it.",
                assertive=True,
            )
            return
        configs = stock_configs.list_configs()
        if not configs:
            self.announce.announce("No frequency lists are available.", assertive=True)
            return
        from vrp.query_dialogs import FrequencyListDialog

        dlg = FrequencyListDialog(
            self, configs, describe_fn=stock_configs.describe_config
        )
        proceed = dlg.ShowModal() == wx.ID_OK
        selection = dlg.get_selection() if proceed else None
        dlg.Destroy()
        if not selection:
            self.grid.SetFocus()
            return

        name, path = selection
        src, message = radio_backend.open_image_as_source(path)
        if src is None:
            self.announce.announce(message, assertive=True)
            wx.MessageBox(message, "Import", wx.OK | wx.ICON_ERROR, self)
            self.grid.SetFocus()
            return

        lo, hi = src.get_features().memory_bounds
        count = 0
        for n in range(lo, hi + 1):
            try:
                if not getattr(src.get_memory(n), "empty", True):
                    count += 1
            except Exception:  # noqa: BLE001
                continue
        if count == 0:
            self.announce.announce(f"{name} has no channels to import.")
            self.grid.SetFocus()
            return
        self._import_results(src, count)

    def on_repeaterbook(self, _evt=None) -> None:
        """Radio ▸ Query Source ▸ RepeaterBook.

        Gathers the query (country/state + filters) in RepeaterBookQueryDialog,
        runs the fetch on a background thread, and imports the chosen results
        into the loaded radio. The results picker's "Back to search" button
        re-opens the query dialog (prefilled) via _open_repeaterbook_query, so
        query → results loops until Import or Cancel. Requires a loaded radio
        (results import into it) — gated in the menu and guarded here.
        """
        if not radio_backend.get_state().loaded:
            self.announce.announce(
                "Open or download a radio first; RepeaterBook results import "
                "into it.",
                assertive=True,
            )
            return
        self._open_repeaterbook_query()

    def _open_repeaterbook_query(self, prefill: dict | None = None) -> None:
        """Show the query form (optionally prefilled) and kick off the fetch."""
        from vrp.query_dialogs import RepeaterBookQueryDialog

        dlg = RepeaterBookQueryDialog(self, initial=prefill)
        ok = dlg.ShowModal() == wx.ID_OK
        params = dlg.get_params() if ok else None
        form = dlg.get_form() if ok else None
        dlg.Destroy()
        if not ok:
            self.grid.SetFocus()
            return
        self._rb_last_form = form  # remembered so results ▸ Back can prefill
        self._run_repeaterbook_query(params)

    def _run_repeaterbook_query(self, params: dict) -> None:
        """Start the background RepeaterBook fetch behind a progress dialog."""
        from chirp_backend import repeaterbook
        from vrp.serial_dialogs import CloneProgressDialog

        progress = CloneProgressDialog(
            self, "Querying RepeaterBook", allow_cancel=True
        )
        self.Disable()
        progress.Show()
        throttle = {"t": 0.0, "decade": -1}

        def progress_cb(msg, percent):  # background thread
            now = time.monotonic()
            pct = int(percent or 0)
            speak = (now - throttle["t"] >= 1.0) or (pct // 10 != throttle["decade"])
            if speak:
                throttle["t"] = now
                throttle["decade"] = pct // 10
            wx.CallAfter(self._on_query_progress, progress, msg, pct, speak)

        def worker():
            ok, message, result = repeaterbook.fetch(params, progress_cb)
            wx.CallAfter(
                self._on_repeaterbook_done, progress, result, ok, message
            )

        threading.Thread(target=worker, daemon=True).start()

    def _on_query_progress(self, progress, msg: str, percent: int, speak: bool) -> None:
        progress.update(percent, 100, msg)
        if speak and msg:
            self.announce.announce(msg)

    def _on_repeaterbook_done(self, progress, result, ok: bool, message: str) -> None:
        from chirp_backend import repeaterbook

        cancelled = progress.is_cancelled()
        progress.Destroy()
        self.Enable()
        self.grid.SetFocus()

        if cancelled:
            self.announce.announce("RepeaterBook query cancelled.")
            return
        if not ok:
            self.announce.announce(message, assertive=True)
            self._show_error("RepeaterBook query failed", message)
            return
        count = repeaterbook.result_count(result) if result else 0
        if count <= 0:
            # A successful query with no matches — not an error.
            self.announce.announce(message)
            return
        self.announce.announce(f"RepeaterBook: {message}")
        self._pick_and_import_repeaters(result)

    def _pick_and_import_repeaters(self, result) -> None:
        """Let the user check which fetched repeaters to import, then import.

        Shows the multi-select results picker; the checked source channel
        numbers flow into the shared _import_results (destination + overwrite).
        """
        from chirp_backend import repeaterbook
        from vrp.query_dialogs import RepeaterBookResultsDialog

        lines = repeaterbook.result_lines(result)
        dlg = RepeaterBookResultsDialog(self, lines)
        code = dlg.ShowModal()
        selected = dlg.get_selected_numbers() if code == wx.ID_OK else []
        dlg.Destroy()
        if code == wx.ID_BACKWARD:
            # Back to the search form, prefilled with the last query, and re-run.
            self._open_repeaterbook_query(prefill=getattr(self, "_rb_last_form", None))
            return
        if code != wx.ID_OK:
            self.grid.SetFocus()
            return
        if not selected:
            self.announce.announce(
                "No repeaters selected; nothing imported.", assertive=True
            )
            self.grid.SetFocus()
            return
        self._import_results(result, len(selected), numbers=selected)

    def on_export_csv(self, _evt=None) -> None:
        """File > Export — write the loaded radio's whole set of channels to a
        CSV file."""
        self._do_csv_export()

    def on_export_selected_csv(self, _evt=None) -> None:
        """Export just the selected (or focused) channels to CSV — reachable
        from the row context menu and the Bulk operations dialog. Lets a user
        send only the relevant portion of their memories to someone else for
        import."""
        self._do_csv_export(self.grid.selected_channel_numbers())

    def _do_csv_export(self, numbers=None) -> None:
        """Prompt for a path and export channels to CSV. ``numbers`` restricts
        the export to that selection; ``None`` exports the whole image. Shared
        by File > Export, the context menu, and the Bulk operations dialog."""
        if not radio_backend.get_state().loaded:
            self.announce.announce("No radio image is open.")
            return
        if numbers is not None and not numbers:
            self.announce.announce("No channel selected.", assertive=True)
            return
        title = (
            "Export channels to CSV file" if numbers is None
            else f"Export {len(numbers)} selected channel(s) to CSV file"
        )
        with wx.FileDialog(
            self, title,
            wildcard="CSV files (*.csv)|*.csv|All files (*.*)|*.*",
            style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT,
        ) as dlg:
            if dlg.ShowModal() != wx.ID_OK:
                return
            path = dlg.GetPath()
        if not os.path.splitext(path)[1]:
            path += ".csv"

        ok, message, _count = radio_backend.export_to_csv(path, numbers)
        self.announce.announce(message, assertive=not ok)
        if not ok:
            wx.MessageBox(message, "Export", wx.OK | wx.ICON_ERROR, self)
        self.grid.SetFocus()

    def on_preferences(self, _evt=None) -> None:
        """File > Preferences — app settings.

        Exposes the supplemental-speech toggle and the number of recent files to
        show in File > Open Recent (0 hides it).
        """
        from vrp.config import get_config
        from vrp.prefs_dialog import PreferencesDialog

        from chirp_backend import bandplan

        cfg = get_config()
        current = {
            "speak_messages": bool(cfg.get("speak_messages", True)),
            "recent_files_count": cfg.recent_count(),
            "bandplan_region": cfg.get("bandplan_region", bandplan.DEFAULT_REGION),
            "auto_band_defaults": bool(cfg.get("auto_band_defaults", False)),
        }
        dlg = PreferencesDialog(self, current)
        if dlg.ShowModal() != wx.ID_OK:
            dlg.Destroy()
            self.grid.SetFocus()
            return
        values = dlg.get_values()
        dlg.Destroy()

        cfg.set("speak_messages", values["speak_messages"])
        cfg.set_recent_count(values["recent_files_count"])
        cfg.set("bandplan_region", values["bandplan_region"])
        cfg.set("auto_band_defaults", values["auto_band_defaults"])
        bandplan.set_region(values["bandplan_region"])  # takes effect immediately
        # Apply the speech pref immediately too, so the confirmation below is
        # itself spoken/silent according to what the user just chose — the
        # setting demonstrates itself rather than waiting for a restart.
        self.announce.set_speech_enabled(values["speak_messages"])
        self._refresh_recent_menu()
        self.announce.announce("Preferences saved.")
        self.grid.SetFocus()

    # -- radio handlers -----------------------------------------------

    def on_favorites(self, _evt=None) -> None:
        """Radio > Favorite radios — manage the starred-radio list (no loaded
        radio needed; it's used by the Download dialog's All/Favorites toggle)."""
        from vrp.serial_dialogs import FavoritesDialog

        dlg = FavoritesDialog(self, radio_backend.list_radio_models(),
                              describe_fn=radio_backend.describe_model)
        dlg.ShowModal()
        dlg.Destroy()
        self.grid.SetFocus()

    def on_download(self, _evt=None) -> None:
        """Radio > Download from Radio."""
        from vrp.serial_dialogs import DownloadDialog, show_radio_prompts

        # A successful download replaces the working image — guard unsaved edits.
        if not self._confirm_discard_or_save():
            self.grid.SetFocus()
            return

        models = radio_backend.list_radio_models()
        dlg = DownloadDialog(self, radio_backend.list_serial_ports, models,
                             describe_fn=radio_backend.describe_model)
        ok = dlg.ShowModal() == wx.ID_OK
        port, driver_id, label = dlg.get_selection() if ok else (None, None, "")
        dlg.Destroy()
        if not (ok and port and driver_id):
            self.grid.SetFocus()
            return
        # Show any driver-required prompts (experimental/info/pre-download
        # instructions) before opening the port; the user can still back out.
        prompts = radio_backend.get_clone_prompts(driver_id)
        if not show_radio_prompts(self, prompts, pre_title="Download instructions"):
            self.announce.announce("Download canceled.")
            self.grid.SetFocus()
            return
        self._run_clone("download", port, driver_id=driver_id, label=label)

    def on_upload(self, _evt=None) -> None:
        """Radio > Upload to Radio."""
        from vrp.serial_dialogs import UploadDialog, show_radio_prompts

        state = radio_backend.get_state()
        if not state.loaded:
            self.announce.announce("No radio image is open to upload.")
            return
        dlg = UploadDialog(self, radio_backend.list_serial_ports)
        ok = dlg.ShowModal() == wx.ID_OK
        port = dlg.get_port() if ok else None
        dlg.Destroy()
        if not (ok and port):
            self.grid.SetFocus()
            return
        # Driver prompts first (what the user must DO), then VRP's destructive
        # overwrite confirmation (are you SURE) — see the serial plan, Task 4.
        prompts = radio_backend.get_clone_prompts_for_loaded_radio()
        if not show_radio_prompts(self, prompts, pre_title="Upload instructions"):
            self.announce.announce("Upload canceled.")
            self.grid.SetFocus()
            return
        label = f"{state.radio.VENDOR} {state.radio.MODEL}"
        if not self._confirm(
            f"This will overwrite ALL memory channels on the {label} connected to "
            f"{port}. The radio's current contents cannot be recovered. Continue?"
        ):
            self.grid.SetFocus()
            return
        self._run_clone("upload", port, label=label)

    def _run_clone(
        self, kind: str, port: str, driver_id: str = "", label: str = ""
    ) -> None:
        """Run a download/upload on a background thread with live progress.

        Matches the _run_clone pattern in vrp/app.py. Progress is throttled on
        the worker side before marshalling to the UI thread via wx.CallAfter.
        """
        from vrp.serial_dialogs import CloneProgressDialog

        title = "Downloading from radio" if kind == "download" else "Uploading to radio"
        progress = CloneProgressDialog(self, title, allow_cancel=(kind == "download"))
        self.Disable()
        progress.Show()

        throttle = {"t": 0.0, "decade": -1}

        def progress_cb(cur: int, total: int, msg: str) -> None:
            now = time.monotonic()
            pct = int(cur * 100 / total) if total else 0
            speak = (now - throttle["t"] >= 2.0) or (pct // 10 != throttle["decade"])
            if speak:
                throttle["t"] = now
                throttle["decade"] = pct // 10
            wx.CallAfter(self._on_clone_progress, progress, cur, total, msg, speak)

        def worker() -> None:
            if kind == "download":
                ok, message = radio_backend.download_from_radio(
                    port, driver_id, progress_cb
                )
            else:
                ok, message = radio_backend.upload_to_radio(port, progress_cb)
            wx.CallAfter(self._on_clone_done, kind, progress, ok, message)

        threading.Thread(target=worker, daemon=True).start()

    def _on_clone_progress(
        self,
        progress: "CloneProgressDialog",
        cur: int,
        total: int,
        msg: str,
        speak: bool,
    ) -> None:
        progress.update(cur, total, msg)
        if speak and msg:
            self.announce.announce(msg)

    def _on_clone_done(
        self,
        kind: str,
        progress: "CloneProgressDialog",
        ok: bool,
        message: str,
    ) -> None:
        cancelled = progress.is_cancelled()
        progress.Destroy()
        self.Enable()

        if kind == "download":
            if cancelled:
                self.announce.announce(
                    "Download canceled. The radio image was not changed."
                )
                self.grid.SetFocus()
                return
            if ok:
                self._load_into_grid()
                low, _high = radio_backend.get_state().memory_bounds
                self.grid.focus_channel(low)
                self.announce.announce(f"{message}. Channel list updated.")
            else:
                self.announce.announce(message, assertive=True)
                wx.MessageBox(message, "Operation failed", wx.OK | wx.ICON_ERROR, self)
        else:  # upload
            if ok:
                self.announce.announce(message)
            else:
                self.announce.announce(message, assertive=True)
                wx.MessageBox(message, "Operation failed", wx.OK | wx.ICON_ERROR, self)
        self.grid.SetFocus()

    def on_settings(self, _evt=None) -> None:
        """Radio > Settings — open the radio settings editor; apply on OK."""
        from vrp.settings_dialog import RadioSettingsDialog

        if not radio_backend.get_state().loaded:
            self.announce.announce("No radio image is open.")
            return
        if not radio_backend.has_settings():
            self.announce.announce("This radio has no editable settings.")
            return
        settings = radio_backend.get_radio_settings()
        if not settings:
            self.announce.announce("No settings are available for this radio.")
            return

        dlg = RadioSettingsDialog(self, settings)
        applied = dlg.ShowModal() == wx.ID_OK
        changed = dlg.get_changed_count() if applied else 0
        dlg.Destroy()

        if applied and changed:
            ok, message = radio_backend.apply_radio_settings(settings)
            if ok:
                self.announce.announce(
                    f"Radio settings saved. {changed} setting(s) changed."
                )
            else:
                self.announce.announce(message)
                wx.MessageBox(message, "Operation failed", wx.OK | wx.ICON_ERROR, self)
        elif applied:
            self.announce.announce("No settings were changed.")
        self.grid.SetFocus()

    def on_radio_info(self, _evt=None) -> None:
        """Radio > Radio Info — plain-text summary of the loaded radio.

        Builds a plain-text summary from the RadioState fields and shows it in a
        read-only edit box (InfoDialog) so it can be reviewed line by line and
        copied.
        """
        state = radio_backend.get_state()
        if not state.loaded:
            self.announce.announce("No radio image is open.")
            return

        radio = state.radio
        f = radio.get_features()
        variant = getattr(radio, "VARIANT", "") or ""
        source = (
            os.path.basename(state.image_path)
            if state.image_path
            else "Downloaded, not yet saved"
        )

        lines = [
            f"{radio.VENDOR} {radio.MODEL}",
            "",
            "Identity",
            f"  Vendor:           {radio.VENDOR}",
            f"  Model:            {radio.MODEL}",
        ]
        if variant:
            lines.append(f"  Variant:          {variant}")
        lines += [
            f"  Source:           {source}",
            f"  Unsaved changes:  {'Yes' if state.is_modified else 'No'}",
            "",
        ]
        # Same capability/spec block the model-details dialog uses, so Radio Info
        # and "Radio details…" stay consistent.
        lines += radio_backend.describe_features(f)

        from vrp.info_dialog import InfoDialog

        # A read-only edit box (not a MessageBox) so a screen-reader user can
        # arrow through the summary line by line, re-read, and copy it.
        dlg = InfoDialog(self, "Radio Info", "\n".join(lines), name="Radio information")
        dlg.ShowModal()
        dlg.Destroy()
        self.grid.SetFocus()

    # -- help handlers ------------------------------------------------

    def on_shortcuts(self, _evt=None) -> None:
        """Help > Keyboard Shortcuts — show shortcut list in a MessageBox.

        Shows the keys for the platform it is running on: wx maps the Ctrl
        accelerators to Command on macOS, so the Windows column would be wrong
        there (see APP_SHORTCUTS).
        """
        entries = shortcuts_for_platform()
        # Width from the longest key on THIS platform: the macOS column is wider
        # than the Windows one ("Command+Y / Command+Shift+Z"), so a hardcoded
        # pad would ragged the list there.
        width = max(len(keys) for keys, _desc in entries)
        lines = ["Keyboard Shortcuts", ""]
        for combo, desc in entries:
            lines.append(f"  {combo:<{width}}  {desc}")
        wx.MessageBox(
            "\n".join(lines), "Keyboard Shortcuts", wx.OK | wx.ICON_INFORMATION, self
        )
        self.grid.SetFocus()

    def maybe_show_welcome(self) -> None:
        """Show the startup welcome screen, unless the user switched it off.

        Called via wx.CallAfter once the main window is up (vrp.native.app), so
        it has a real parent and focus lands back on the grid afterwards — not
        during __init__, where the frame isn't shown yet.

        The region is saved whichever button is pressed, including Escape: the
        user answered that question by the time they dismiss the screen, and
        re-asking it next launch would be the annoying part.
        """
        from chirp_backend import bandplan
        from vrp.config import get_config
        from vrp.welcome_dialog import WelcomeDialog

        cfg = get_config()
        if not cfg.get("show_welcome", True):
            return

        dlg = WelcomeDialog(
            self, current_region=cfg.get("bandplan_region", bandplan.DEFAULT_REGION)
        )
        try:
            result = dlg.ShowModal()
            region = dlg.region_code()
        finally:
            dlg.Destroy()

        cfg.set("bandplan_region", region)
        bandplan.set_region(region)  # takes effect immediately
        if result == WelcomeDialog.DONT_SHOW:
            cfg.set("show_welcome", False)
        cfg.save()

        self.grid.SetFocus()  # focus lands in the app, not nowhere
        if result == WelcomeDialog.OPEN_GUIDE:
            self.on_getting_started()
            return
        # Confirm the region either way: it is the one thing the screen changed,
        # and a screen-reader user who pressed Escape should still hear it stuck.
        self.announce.announce(
            f"Band plan region set to {bandplan.region_label(region)}."
        )

    def on_getting_started(self, _evt=None) -> None:
        """Help > Getting Started — the guide, in the user's own browser."""
        self._open_help_doc(vrp_help.GETTING_STARTED, "Getting Started guide")

    def on_keyboard_commands(self, _evt=None) -> None:
        """Help > Keyboard Commands — the full reference, in the browser. The
        quick in-app list is still on F1 (on_shortcuts)."""
        self._open_help_doc(vrp_help.KEYBOARD_COMMANDS, "Keyboard Commands list")

    def _open_help_doc(self, name: str, description: str) -> None:
        """Open a help document, announcing either outcome.

        The browser takes focus, so the success announcement is what tells a
        screen-reader user the keypress did something; a missing file is an
        error, so it interrupts (assertive) rather than being missed.
        """
        if vrp_help.open_help(name):
            self.announce.announce(f"Opening the {description} in your browser.")
            return
        self.announce.announce(
            f"The {description} could not be found. It should be in the "
            f"{vrp_help.HELP_DIRNAME} folder next to the program.",
            assertive=True,
        )

    def on_about(self, _evt=None) -> None:
        """Help > About — build information and the CHIRP acknowledgement, each
        in a navigable read-only edit box (see vrp.about_dialog for why not
        wx.adv.AboutBox). The attribution it carries is a GPLv3 requirement.
        """
        from vrp.about_dialog import AboutDialog

        dlg = AboutDialog(self)
        try:
            dlg.ShowModal()
        finally:
            dlg.Destroy()
        self.grid.SetFocus()  # focus returns to the control that opened it
