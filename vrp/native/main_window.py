"""Native main window: menu bar, status bar, channel grid, command handlers.

Handler bodies are ported from vrp/app.py (the webview app), swapping webview
refresh for grid refresh + Announcer. Reorganization lives in the Channels menu
(filled in by a later task).

Key differences vs the webview app:
- No paging: the native grid is virtual and shows all channels at once.
- No webview focus restore: grid.SetFocus() replaces _restore_webview_focus().
- on_radio_info: describe_radio_html() returns HTML; we build a plain-text
  summary instead and show it with wx.MessageBox.
- on_shortcuts: displayed with wx.MessageBox (plain text, not HTML).
- on_preferences: channels_per_page is omitted (no paging in native grid);
  only speak_status_messages is offered.
- CHIRP attribution: shown in the About box (wx.adv.AboutBox description),
  satisfying the GPLv3 requirement documented in CLAUDE.md.
"""

from __future__ import annotations

import logging
import os
import threading
import time

import wx
import wx.adv

from chirp_backend import radio as radio_backend
from vrp import __version__
from vrp.native.announce import Announcer
from vrp.native.channel_grid import ChannelGrid
from vrp.speech import Speaker

LOG = logging.getLogger(__name__)

# Keyboard shortcuts table (combo, description).
# Displayed by on_shortcuts (F1).
APP_SHORTCUTS = [
    ("Ctrl+O", "Open image file"),
    ("Ctrl+S", "Save"),
    ("Ctrl+Shift+S", "Save as"),
    ("Ctrl+Shift+D", "Download from radio"),
    ("Ctrl+Shift+U", "Upload to radio"),
    ("Ctrl+Shift+P", "Edit radio settings"),
    ("F2 / Enter", "Edit the focused channel"),
    ("Ctrl+Shift+G", "Go to channel"),
    ("Ctrl+B", "Channel banks for the focused channel"),
    ("Ctrl+Shift+Up", "Move selected channel(s) up"),
    ("Ctrl+Shift+Down", "Move selected channel(s) down"),
    ("Ctrl+Shift+M", "Move selected channel(s) to a chosen slot"),
    ("Ctrl+M", "Organize Channels dialog"),
    ("Ctrl+F", "Find a channel"),
    ("Ctrl+G", "Find next match"),
    ("F1", "Show this list of keyboard shortcuts"),
]


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

        # Build speech: Speaker is a class, not a bare function. Create an
        # instance and pass its .speak method; if prism is unavailable the
        # method is a no-op, so Announcer degrades gracefully.
        self._speaker = Speaker()
        # Announcer calls set_status(message) with ONE argument, which maps to
        # SetStatusText(message) — the no-index form writes field 0 only, so
        # the attribution in field 1 is never touched.
        self.announce = Announcer(
            set_status=self.SetStatusText,
            speak=lambda m, interrupt=False: self._speaker.speak(m, interrupt=interrupt),
        )

        self.grid = ChannelGrid(self)
        self.grid.Bind(wx.EVT_LIST_ITEM_ACTIVATED, self.on_edit_channel)
        # Row context menu (Applications key / Shift+F10 / right-click), a Delete
        # key handler, and debounced multi-select feedback. The native grid had
        # none of these — they previously lived only in the webview grid, so on
        # Windows the context key errored and selecting gave no feedback.
        self.grid.Bind(wx.EVT_CONTEXT_MENU, self.on_grid_context_menu)
        self.grid.Bind(wx.EVT_KEY_DOWN, self._on_grid_key)
        self.grid.Bind(wx.EVT_LIST_ITEM_SELECTED, self._on_grid_selection_changed)
        self.grid.Bind(wx.EVT_LIST_ITEM_DESELECTED, self._on_grid_selection_changed)
        self._sel_timer: wx.CallLater | None = None
        self._menu_items: dict[str, wx.MenuItem] = {}
        self._radio_gated_keys: set[str] = set()
        # Find state: query string, fields, last matched channel.
        self._find_query: str | None = None
        self._find_fields: tuple = ("freq", "name", "comment")
        self._find_last: int | None = None
        self._build_menubar()
        self._update_menu_state()
        self.grid.SetFocus()
        self.announce.announce("Ready")

    # -- menu construction --------------------------------------------

    def _build_menubar(self) -> None:
        bar = wx.MenuBar()
        bar.Append(self._build_file_menu(), "&File")
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
        return m

    def _build_radio_menu(self) -> wx.Menu:
        from chirp_backend import query as query_mod

        m = wx.Menu()
        self._add(m, "download", "&Download from Radio\tCtrl+Shift+D", self.on_download)
        self._add(m, "upload", "&Upload to Radio\tCtrl+Shift+U", self.on_upload, needs_radio=True)
        m.AppendSeparator()

        # Query Source submenu — one item per registered online source.
        # Each item is gated on a loaded radio (the results import into it).
        query_submenu = wx.Menu()
        self._query_submenu_items: list[wx.MenuItem] = []
        for src in query_mod.SOURCES:
            item = query_submenu.Append(wx.ID_ANY, src["label"] + "…")
            self.Bind(
                wx.EVT_MENU,
                lambda e, k=src["key"]: self.on_query_source(k),
                item,
            )
            self._query_submenu_items.append(item)
        self._mi_query_source = m.AppendSubMenu(query_submenu, "&Query Source")

        m.AppendSeparator()
        self._add(m, "settings", "&Settings…\tCtrl+Shift+P", self.on_settings, needs_radio=True)
        self._add(m, "radio_info", "Radio &Info…", self.on_radio_info, needs_radio=True)
        return m

    def _build_channels_menu(self) -> wx.Menu:
        m = wx.Menu()
        self._add(m, "edit", "&Edit channel…\tF2", self.on_edit_channel, needs_radio=True)
        self._add(m, "goto", "&Go to channel…\tCtrl+Shift+G", self.on_goto, needs_radio=True)
        self._add(m, "banks", "Channel &banks…\tCtrl+B", self.on_banks, needs_radio=True)
        m.AppendSeparator()
        self._add(m, "move_up", "Move &up\tCtrl+Shift+Up", self.on_move_up, needs_radio=True)
        self._add(m, "move_down", "Move &down\tCtrl+Shift+Down", self.on_move_down, needs_radio=True)
        self._add(m, "move_to", "&Move to channel…\tCtrl+Shift+M", self.on_move_to, needs_radio=True)
        self._add(m, "organize", "&Organize Channels…\tCtrl+M", self.on_organize, needs_radio=True)
        m.AppendSeparator()
        self._add(m, "find", "&Find…\tCtrl+F", self.on_find, needs_radio=True)
        self._add(m, "find_next", "Find &next\tCtrl+G", self.on_find_next, needs_radio=True)
        return m

    def _build_help_menu(self) -> wx.Menu:
        m = wx.Menu()
        self._add(m, "shortcuts", "&Keyboard Shortcuts\tF1", self.on_shortcuts)
        self._add(m, "about", "&About", self.on_about)
        return m

    def _update_menu_state(self) -> None:
        loaded = radio_backend.get_state().loaded
        for key in self._radio_gated_keys:
            self._menu_items[key].Enable(loaded)
        # Gate the Query Source submenu: disable the parent item and each child
        # item individually when no radio is loaded (results import into the
        # loaded radio, so querying without one is meaningless).
        if hasattr(self, "_mi_query_source"):
            self._mi_query_source.Enable(loaded)
        for item in getattr(self, "_query_submenu_items", []):
            item.Enable(loaded)

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

        with EditChannelDialog(self, number, mem, state.features) as dlg:
            if dlg.ShowModal() != wx.ID_OK:
                self.grid.select_channels([number])
                self.grid.focus_channel(number)
                return
            ok, message, _affected = memory_ops.update_channel(number, dlg.get_values())
        self.grid.refresh_numbers([number])
        self.grid.select_channels([number])
        self.grid.focus_channel(number)
        self.announce.announce(message, assertive=not ok)

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
        sel = self.grid.GetSelectedItemCount()
        menu = wx.Menu()

        def add(label, handler):
            item = menu.Append(wx.ID_ANY, label)
            self.grid.Bind(wx.EVT_MENU, lambda _e: handler(), item)

        add(f"&Edit channel {number}\tEnter", self.on_edit_channel)
        add(
            "&Delete selected channels\tDel" if sel > 1 else f"&Delete channel {number}\tDel",
            self.on_delete_channels,
        )
        menu.AppendSeparator()
        add("Move &up\tCtrl+Shift+Up", self.on_move_up)
        add("Move &down\tCtrl+Shift+Down", self.on_move_down)
        add("&Move to channel…\tCtrl+Shift+M", self.on_move_to)
        add("&Organize channels…", self.on_organize)
        menu.AppendSeparator()
        add("&Go to channel…\tCtrl+Shift+G", self.on_goto)
        add("Channel &banks…", self.on_banks)

        # Keyboard invocation has no pointer position (DefaultPosition); anchor the
        # menu on the focused row so it appears where the user is.
        pos = event.GetPosition()
        if pos == wx.DefaultPosition:
            idx = self.grid.GetFocusedItem()
            rect = self.grid.GetItemRect(idx) if idx != -1 else wx.Rect(0, 0, 0, 0)
            client_pos = rect.GetBottomLeft()
        else:
            client_pos = self.grid.ScreenToClient(pos)
        self.grid.PopupMenu(menu, client_pos)
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
            f"Delete {rng}? Their contents will be cleared. This cannot be undone."
        ):
            return
        ok, message, _affected = mo.delete_range(numbers)
        if not ok:
            self.announce.announce(message, assertive=True)
            return
        self.grid.rebuild()
        low, high = radio_backend.get_state().memory_bounds
        target = min(max(first, low), high)
        self.grid.select_channels([target])
        self.grid.focus_channel(target)
        self.announce.announce(f"{message} Now on channel {target}.", assertive=True)

    def _on_grid_key(self, event) -> None:
        """Delete key deletes the selection; every other key (arrows, Shift+arrow
        range selection, type-ahead) falls through to the native list unchanged."""
        if event.GetKeyCode() == wx.WXK_DELETE:
            self.on_delete_channels()
            return
        event.Skip()

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
        count = self.grid.GetSelectedItemCount()
        if count >= 2:
            self.announce.announce(f"{count} channels selected")

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
            first, last = new_sel[0], new_sel[-1]
            if first == last:
                where = f". Now on channel {first}."
            else:
                where = f". Now at channels {first} to {last}, on channel {first}."
            self.announce.announce(message + where)
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
            first, last = new_sel[0], new_sel[-1]
            if first == last:
                where = f". Now on channel {first}."
            else:
                where = f". Now at channels {first} to {last}, on channel {first}."
            self.announce.announce(message + where)
        else:
            self.announce.announce(message, assertive=True)

    def on_organize(self, _evt=None) -> None:
        """Open the Organize Channels dialog; dispatch the chosen operation."""
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
        with ChannelOperationsDialog(self, low, high, default_from, columns) as dlg:
            if dlg.ShowModal() != wx.ID_OK:
                return
            numbers, _err = dlg.selected_numbers()
            op = dlg.get_operation()

        key = op["op"]
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
            first, last = block[0], block[-1]
            if first == last:
                where = f" Now on channel {first}."
            else:
                where = f" Now at channels {first} to {last}, on channel {first}."
            self.announce.announce(f"{message}{where}")
        else:
            # Structural ops (delete, insert, sort, arrange): full rebuild needed,
            # land on the single logical focus target.
            self.grid.rebuild()
            target = self._op_focus_target(key, numbers, op)
            self.grid.select_channels([target])
            self.grid.focus_channel(target)
            self.announce.announce(f"{message} Now on channel {target}.")

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
                "This cannot be undone."
            )
        if key == "delete_shift":
            scope = (
                "and shift all higher channels down to close the gap (this renumbers them)"
                if op.get("mode", "all") == "all"
                else "and shift channels within the block"
            )
            return f"Delete {rng} {scope}? This cannot be undone."
        if key == "sort":
            order = "descending" if op.get("reverse") else "ascending"
            return (
                f"Sort {rng} by {op.get('attr')} {order}? This reorders and "
                "renumbers these channels. This cannot be undone."
            )
        if key == "arrange":
            return (
                f"Compact {rng}, removing empty slots? Channels will be "
                "renumbered. This cannot be undone."
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
        mem = radio_backend.get_memory(number)
        detail = ""
        if mem is not None and not getattr(mem, "empty", True):
            name = (getattr(mem, "name", "") or "").strip()
            mhz = f"{mem.freq / 1_000_000:.6f}".rstrip("0").rstrip(".")
            detail = f": {name or mhz}"
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
        ok, message = radio_backend.load_image(path)
        if ok:
            self._load_into_grid()
            self.grid.SetFocus()
        self.announce.announce(message)

    def on_save(self, _evt=None) -> None:
        state = radio_backend.get_state()
        if not state.loaded:
            self.announce.announce("No radio image is open.")
            return
        # No original path (downloaded but never saved) → Save As.
        if not state.image_path:
            self.on_save_as(_evt)
            return
        ok, message = radio_backend.save_image()
        self.announce.announce(message, assertive=not ok)

    def on_save_as(self, _evt=None) -> None:
        state = radio_backend.get_state()
        if not state.loaded:
            self.announce.announce("No radio image is open.")
            return
        with wx.FileDialog(
            self, "Save radio image as",
            wildcard="Radio images (*.img)|*.img",
            style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT,
        ) as dlg:
            if dlg.ShowModal() != wx.ID_OK:
                return
            path = dlg.GetPath()
        ok, message = radio_backend.save_image(path)
        self.announce.announce(message, assertive=not ok)
        if ok:
            self.SetTitle(f"{state.radio.VENDOR} {state.radio.MODEL} — VRP")

    def on_close_image(self, _evt=None) -> None:
        if not radio_backend.get_state().loaded:
            self.announce.announce("No radio image is open.")
            return
        radio_backend.unload()
        self._load_into_grid()
        self.announce.announce("Closed image")

    def on_exit(self, _evt=None) -> None:
        self.Close()

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

    def _import_results(self, src_radio, count: int) -> None:
        """Shared import flow: pick destination, import, refresh grid, focus."""
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

        ok, message, affected = memory_ops.import_memories(src_radio, dest, overwrite)
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

    def on_export_csv(self, _evt=None) -> None:
        """File > Export — write the loaded radio's channels to a CSV file."""
        if not radio_backend.get_state().loaded:
            self.announce.announce("No radio image is open.")
            return
        with wx.FileDialog(
            self, "Export channels to CSV file",
            wildcard="CSV files (*.csv)|*.csv|All files (*.*)|*.*",
            style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT,
        ) as dlg:
            if dlg.ShowModal() != wx.ID_OK:
                return
            path = dlg.GetPath()
        if not os.path.splitext(path)[1]:
            path += ".csv"

        ok, message, _count = radio_backend.export_to_csv(path)
        self.announce.announce(message, assertive=not ok)
        if not ok:
            wx.MessageBox(message, "Export", wx.OK | wx.ICON_ERROR, self)
        self.grid.SetFocus()

    def on_preferences(self, _evt=None) -> None:
        """File > Preferences — app settings (supplemental speech).

        The native grid has no paging, so channels_per_page is not offered here.
        Only the supplemental speech toggle is exposed.
        """
        from vrp.config import get_config
        from vrp.prefs_dialog import PreferencesDialog

        cfg = get_config()
        # Pass a dummy channels_per_page so PreferencesDialog renders correctly;
        # the native grid ignores it.
        current = {
            "channels_per_page": int(cfg.get("channels_per_page", 100)),
            "speak_status_messages": bool(cfg.get("speak_status_messages", False)),
        }
        dlg = PreferencesDialog(self, current)
        if dlg.ShowModal() != wx.ID_OK:
            dlg.Destroy()
            self.grid.SetFocus()
            return
        values = dlg.get_values()
        dlg.Destroy()

        cfg.set("speak_status_messages", values["speak_status_messages"])
        self.announce.announce("Preferences saved.")
        self.grid.SetFocus()

    # -- radio handlers -----------------------------------------------

    def on_download(self, _evt=None) -> None:
        """Radio > Download from Radio."""
        from vrp.serial_dialogs import DownloadDialog

        models = radio_backend.list_radio_models()
        dlg = DownloadDialog(self, radio_backend.list_serial_ports, models)
        ok = dlg.ShowModal() == wx.ID_OK
        port, driver_id, label = dlg.get_selection() if ok else (None, None, "")
        dlg.Destroy()
        if ok and port and driver_id:
            self._run_clone("download", port, driver_id=driver_id, label=label)
        else:
            self.grid.SetFocus()

    def on_upload(self, _evt=None) -> None:
        """Radio > Upload to Radio."""
        from vrp.serial_dialogs import UploadDialog

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

    # -- query sources ------------------------------------------------

    def on_query_source(self, key: str) -> None:
        """Radio > Query Source > <name> — ported from vrp/app.py on_query_source.

        Opens QueryParamsDialog (same class as the webview app) to gather any
        source-specific parameters, then runs the fetch on a background thread
        and imports results via _import_results (shared with Import from File).
        Requires a loaded radio — gated in the menu and guarded here.
        """
        from chirp_backend import query
        from vrp.query_dialogs import QueryParamsDialog

        if not radio_backend.get_state().loaded:
            self.announce.announce(
                "Open or download a radio first; query results import into it.",
                assertive=True,
            )
            return
        source = query.get_source(key)
        if source is None:
            return
        dlg = QueryParamsDialog(self, source)
        ok = dlg.ShowModal() == wx.ID_OK
        params = dlg.get_params() if ok else None
        dlg.Destroy()
        if not ok:
            self.grid.SetFocus()
            return
        self._run_query(key, source, params)

    def _run_query(self, key: str, source: dict, params: dict | None) -> None:
        """Start the background fetch for a query source (ported from app.py)."""
        from chirp_backend import query
        from vrp.serial_dialogs import CloneProgressDialog

        radio_result = query.make_source_radio(key)
        if radio_result is None:
            self.announce.announce(
                f"Could not load source {source['label']}.", assertive=True
            )
            self.grid.SetFocus()
            return

        progress = CloneProgressDialog(
            self, f"Querying {source['label']}", allow_cancel=True
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
            ok, message = query.run_fetch(radio_result, params or {}, progress_cb)
            wx.CallAfter(
                self._on_query_done, source, progress, radio_result, ok, message
            )

        threading.Thread(target=worker, daemon=True).start()

    def _on_query_progress(
        self, progress, msg: str, percent: int, speak: bool
    ) -> None:
        progress.update(percent, 100, msg)
        if speak and msg:
            self.announce.announce(msg)

    def _on_query_done(
        self, source: dict, progress, radio_result, ok: bool, message: str
    ) -> None:
        from chirp_backend import query

        cancelled = progress.is_cancelled()
        progress.Destroy()
        self.Enable()
        self.grid.SetFocus()

        if cancelled:
            self.announce.announce("Query cancelled.")
            return
        if not ok:
            self.announce.announce(message, assertive=True)
            wx.MessageBox(message, "Query failed", wx.OK | wx.ICON_ERROR, self)
            return
        self.announce.announce(f"{source['label']}: {message}")
        if query.result_count(radio_result) > 0:
            self._import_results(radio_result, query.result_count(radio_result))

    def on_radio_info(self, _evt=None) -> None:
        """Radio > Radio Info — plain-text summary of the loaded radio.

        vrp/app.py uses describe_radio_html() + show_message() (HTML in a
        webview dialog). In the native app we build an equivalent plain-text
        summary from the same RadioState fields and show it with wx.MessageBox.
        """
        state = radio_backend.get_state()
        if not state.loaded:
            self.announce.announce("No radio image is open.")
            return

        radio = state.radio
        f = radio.get_features()
        lo, hi = f.memory_bounds
        variant = getattr(radio, "VARIANT", "") or ""
        source = (
            os.path.basename(state.image_path)
            if state.image_path
            else "Downloaded, not yet saved"
        )
        bands = "; ".join(
            f"{a / 1_000_000:.3f}–{b / 1_000_000:.3f} MHz"
            for a, b in (getattr(f, "valid_bands", None) or [])
        )
        modes = ", ".join(getattr(f, "valid_modes", None) or [])

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
            "Capacity",
            f"  Channels:         {hi - lo + 1} (numbered {lo} to {hi})",
            "",
            "Capabilities",
            f"  Channel names:    {'Yes' if getattr(f, 'has_name', False) else 'No'}",
            f"  Banks:            {'Yes' if getattr(f, 'has_bank', False) else 'No'}",
            f"  Settings:         {'Yes' if getattr(f, 'has_settings', False) else 'No'}",
            f"  Comments:         {'Yes' if getattr(f, 'has_comment', False) else 'No'}",
            f"  DTCS:             {'Yes' if getattr(f, 'has_dtcs', False) else 'No'}",
            f"  Bands:            {bands or '—'}",
            f"  Modes:            {modes or '—'}",
        ]
        wx.MessageBox("\n".join(lines), "Radio Info", wx.OK | wx.ICON_INFORMATION, self)
        self.grid.SetFocus()

    # -- help handlers ------------------------------------------------

    def on_shortcuts(self, _evt=None) -> None:
        """Help > Keyboard Shortcuts — show shortcut list in a MessageBox."""
        lines = ["Keyboard Shortcuts", ""]
        for combo, desc in APP_SHORTCUTS:
            lines.append(f"  {combo:<22}  {desc}")
        wx.MessageBox(
            "\n".join(lines), "Keyboard Shortcuts", wx.OK | wx.ICON_INFORMATION, self
        )
        self.grid.SetFocus()

    def on_about(self, _evt=None) -> None:
        """Help > About — standard About box.

        The CHIRP attribution ("Radio driver support provided by the CHIRP
        project — chirpmyradio.com.") is a GPLv3 requirement and must appear
        in the About box now that the webview page footer is not present.
        """
        info = wx.adv.AboutDialogInfo()
        info.SetName("Versatile Radio Programmer")
        info.SetVersion(__version__)
        info.SetDescription(
            "An accessible front end to the CHIRP radio programming library.\n\n"
            "Radio driver support provided by the CHIRP project — "
            "chirpmyradio.com."
        )
        info.SetWebSite("https://chirpmyradio.com", "chirpmyradio.com")
        wx.adv.AboutBox(info, self)
        self.grid.SetFocus()
