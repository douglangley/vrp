"""wxPython application shell for Versatile Radio Programmer.

The app is a wx ``Frame`` whose entire client area is a single
``AccessibleWebView``. The webview renders semantic HTML views (welcome screen,
channel grid, dialogs) that NVDA/JAWS read like a web page. Page code talks back
to Python through the ``window.vrp.postMessage(...)`` bridge, routed here to
:meth:`MainWindow.on_bridge_message`.

Commands are reachable three ways, by design: a native wx menu bar, visible
in-page buttons (with ``aria-keyshortcuts``), and global Ctrl-combo shortcuts
handled inside the page and bridged to Python (the mechanism the webview also
uses for Escape/F6); F1 lists them.

Menu vs shortcuts and wxWidgets issue #24786: the webview is the ONLY child
control in the frame, and it holds keyboard focus essentially permanently (no
other native control to tab to), so a focused WebView2 swallows Alt entirely
— confirmed with NVDA: bare Alt, Alt+F, Alt+R all do nothing, not just
one-shot mnemonics as originally assumed. The bridged in-page Ctrl-combo
shortcuts already covered Ctrl accelerators; menu *mnemonics* needed a
separate fix: ``MainWindow`` binds ``EVT_CHAR_HOOK`` on the frame, which wx
implements via a low-level keyboard hook on Windows specifically so it can
see keys a child control would otherwise consume (the same mechanism
``wx_accessible_webview``'s own dialogs already use for Escape). Alt+letter
and F10 are detected there and drive the real native menu bar into its
keyboard loop by posting ``WM_SYSCOMMAND``/``SC_KEYMENU`` to the frame — the
exact message Windows itself sends on Alt, which WebView2 was eating. That
puts the actual menu bar in navigation mode, so Left/Right move across
File/Radio/Channels/Help and Up/Down/Enter work, NVDA-readable, ``EVT_MENU``
fires normally. (An earlier attempt used ``PopupMenu()`` on a single
``wx.Menu``, but a detached popup has no menu-bar context, so Left/Right were
dead — see ``_open_menu_bar_menu``. Bare Alt-alone-opens-menu is intentionally
not implemented — see ``_on_char_hook``.) After a menu closes, webview focus
is restored so the bridged shortcuts stay live.
"""

from __future__ import annotations

import json
import logging

import wx
import wx.adv
import wx.html2
from wx_accessible_webview import AccessibleWebView, show_message

from chirp_backend import radio as radio_backend

from vrp import __version__, html, views
from vrp.speech import Speaker

LOG = logging.getLogger(__name__)

APP_TITLE = "Versatile Radio Programmer"

# CHIRP images have many driver-specific extensions, so don't over-filter.
IMAGE_WILDCARD = "Radio image files (*.img)|*.img|All files (*.*)|*.*"

# Application keyboard shortcuts. (W3C aria-keyshortcuts token, description,
# bridge action). Ctrl-combos are safe: NVDA's own commands use the NVDA
# modifier, so intercepting these in the page doesn't clash with quick-nav.
# Single letters are never used (rule #8). This list drives the F1 help.
# The Alt+letter/F10 entries are native menu mnemonics caught by
# _on_char_hook (not page-bridged), so their action is None — on_shortcuts
# only displays combo+description, it doesn't dispatch on action.
APP_SHORTCUTS = [
    ("Alt+F", "Open the File menu", None),
    ("Alt+R", "Open the Radio menu", None),
    ("Alt+C", "Open the Channels menu", None),
    ("Alt+H", "Open the Help menu", None),
    ("F10", "Open the File menu", None),
    ("Control+O", "Open image file", "open"),
    ("Control+S", "Save", "save"),
    ("Control+Shift+S", "Save as", "save_as"),
    ("Control+Alt+Left", "Previous channel page", "page_prev"),
    ("Control+Alt+Right", "Next channel page", "page_next"),
    ("Control+M", "Organize channels (move, delete, copy, sort)", "operations"),
    ("Control+F", "Find a channel", "find"),
    ("Control+G", "Find next match", "find_next"),
    ("Control+Shift+D", "Download from radio", "download"),
    ("Control+Shift+U", "Upload to radio", "upload"),
    ("Control+Shift+P", "Edit radio settings", "settings"),
    ("Control+B", "Assign a channel to banks", "channel_banks"),
    ("F1", "Show this list of keyboard shortcuts", "shortcuts"),
]

# Installed into the page once, after load, via run_js. set_content injects
# views with innerHTML (so <script> tags in a fragment never run), but a
# document-level listener installed this way persists across view swaps. It
# posts the matching action to Python; the handler performs it and announces.
_SHORTCUTS_JS = """
(function(){
  if (window.__vrpKeys) return;
  window.__vrpKeys = true;
  function post(action){ if(window.vrp){ window.vrp.postMessage(JSON.stringify({action:action})); } }
  function postMenu(index){ if(window.vrp){ window.vrp.postMessage(JSON.stringify({action:'menu_open', index:index})); } }
  function inText(el){
    if(!el) return false;
    if(el.tagName==='TEXTAREA' || el.isContentEditable) return true;
    if(el.tagName==='INPUT'){ var t=(el.type||'text').toLowerCase();
      return ['text','search','number','email','tel','url','password'].indexOf(t)!==-1; }
    return false;
  }
  // Native menu bar. A focused WebView2 hides Alt/F10 from wx, but the page
  // still sees them here. Alt by itself activates the bar (confirmed on keyup,
  // so it isn't mistaken for the start of Alt+letter / Alt+Tab); Alt+F/R/C/H
  // opens that menu; F10 activates the bar. Python then drives the real menu.
  var altAlone = false;
  document.addEventListener('keyup', function(e){
    if(e.key==='Alt'){
      if(altAlone){ e.preventDefault(); post('menu_activate'); }
      altAlone=false;
    }
  }, true);
  document.addEventListener('keydown', function(e){
    if(e.key==='Alt' && !e.ctrlKey && !e.shiftKey && !e.metaKey){ altAlone=true; return; }
    if(e.key==='F10' && !e.altKey && !e.ctrlKey && !e.shiftKey && !e.metaKey){
      altAlone=false; e.preventDefault(); post('menu_activate'); return; }
    if(e.altKey && !e.ctrlKey && !e.metaKey){
      var mk=(e.key||'').toLowerCase();
      var midx={'f':0,'r':1,'c':2,'h':3}[mk];
      altAlone=false;
      if(midx!==undefined){ e.preventDefault(); postMenu(midx); return; }
    } else if(e.key!=='Alt'){ altAlone=false; }
    if(e.key==='F1'){ e.preventDefault(); post('shortcuts'); return; }
    if(e.ctrlKey && e.altKey && !e.metaKey){          // Ctrl+Alt+arrows = paging
      if(e.key==='ArrowRight'){ e.preventDefault(); post('page_next'); return; }
      if(e.key==='ArrowLeft'){ e.preventDefault(); post('page_prev'); return; }
    }
    if(!e.ctrlKey || e.altKey || e.metaKey) return;   // only our Ctrl(+Shift) combos
    if(inText(document.activeElement)) return;          // don't hijack typing
    var combo=(e.shiftKey?'shift+':'') + (e.key||'').toLowerCase();
    var action={'o':'open','s':'save','shift+s':'save_as','m':'operations',
                'f':'find','g':'find_next','shift+d':'download','shift+u':'upload',
                'shift+p':'settings','b':'channel_banks'}[combo];
    if(!action) return;
    e.preventDefault();   // safe: NVDA does not own Ctrl+letter
    post(action);
  }, true);
})();
"""


class MainWindow(wx.Frame):
    """Top-level application window."""

    def __init__(self) -> None:
        super().__init__(None, title=APP_TITLE, size=(1200, 800))
        self.SetMinSize((800, 600))

        self.speaker = Speaker()
        from vrp.config import get_config

        self._speak_enabled = bool(get_config().get("speak_status_messages", False))
        self._page = 1  # 1-based current page of the channel grid
        # Find state (Find Next continues from the last match; backend wraps).
        self._find_query: str | None = None
        self._find_fields: tuple = ("freq", "name", "comment")
        self._find_last: int | None = None

        self.CreateStatusBar()
        self.SetStatusText("Ready")

        # TEMPORARILY REVERTED for diagnosis: this used to build the menu bar
        # AFTER the webview existed; today it was reordered to build it
        # BEFORE, plus an EVT_CHAR_HOOK binding was added (already disabled
        # above this point in history) — and in-page interaction (even the
        # very first button press, AND WebView2's own built-in F12 devtools
        # toggle) stopped working entirely afterward. Reverting construction
        # order to isolate whether IT is responsible, independent of
        # EVT_CHAR_HOOK. Re-apply the reorder only once this is ruled out.
        # self._build_menubar()

        # The accessible HTML host. handler_name="vrp" exposes
        # window.vrp.postMessage() to page code; messages arrive at
        # on_bridge_message. The widget owns the document chrome, lang, styles,
        # and a status live region.
        self.view = AccessibleWebView(
            self,
            title=APP_TITLE,
            lang="en",
            live_region=True,
            handler_name="vrp",
            on_message=self.on_bridge_message,
            open_links_externally=True,
        )

        # Install the global keyboard-shortcut listener once the page is loaded
        # (run_js needs a loaded document). The underlying control fires
        # EVT_WEBVIEW_LOADED; Skip() so the widget's own loaded handler (which
        # flushes pending content) still runs.
        if self.view.using_webview and self.view.view is not None:
            self.view.view.Bind(wx.html2.EVT_WEBVIEW_LOADED, self._on_webview_loaded)

        # AccessibleWebView is a wrapper, not a wx.Window; .control is the
        # underlying webview (or a TextCtrl fallback if no WebView backend).
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(self.view.control, 1, wx.EXPAND)
        self.SetSizer(sizer)

        self._build_menubar()
        # Wire the keyboard hook that drives the native menu bar (plain Alt,
        # Alt+letter, F10). EVT_CHAR_HOOK is a low-level key hook that sees keys
        # before the focused WebView2 can swallow them. _on_char_hook Skip()s
        # every key it doesn't consume, so in-page typing, buttons, and the
        # webview's own keys are unaffected. (Historically disabled during a
        # diagnosis of a menu-build-order bug that is now reverted; re-enabled.)
        self.Bind(wx.EVT_CHAR_HOOK, self._on_char_hook)
        # Log when a native menu actually opens, to confirm activation works.
        self.Bind(wx.EVT_MENU_OPEN, self._on_menu_open)
        # Maximizing / reactivating the window can move focus off the webview
        # onto the frame; the menu keys are caught inside the page, so they go
        # dead until focus is back in the content. Pull it back (rule #6).
        self.Bind(wx.EVT_MAXIMIZE, self._on_maximize)
        self.Bind(wx.EVT_ACTIVATE, self._on_activate)
        self.show_welcome()
        self.view.focus()

    # -- native menu bar ---------------------------------------------------

    def _build_menubar(self) -> None:
        """A native menu bar that complements the in-page buttons + shortcuts.

        Per wxWidgets issue #24786 a focused WebView2 swallows Alt entirely, so
        menu mnemonics are caught by ``_on_char_hook`` (EVT_CHAR_HOOK) instead of
        relying on the OS's normal Alt-routing; Ctrl accelerators are handled by
        the in-page bridge. Either way the menu itself is a real native Win32
        menu (arrows + Enter work, EVT_MENU fires), genuinely keyboard/NVDA
        usable. Accelerator text is shown for discoverability. Labels mirror the
        in-page buttons so the same action is named the same.
        """
        bar = wx.MenuBar()

        file_menu = wx.Menu()
        m_open = file_menu.Append(wx.ID_OPEN, "&Open Image File\tCtrl+O")
        self._recent_menu = wx.Menu()
        file_menu.AppendSubMenu(self._recent_menu, "Open &Recent")
        self._mi_save = file_menu.Append(wx.ID_SAVE, "&Save\tCtrl+S")
        self._mi_save_as = file_menu.Append(wx.ID_SAVEAS, "Save &As\tCtrl+Shift+S")
        self._mi_close = file_menu.Append(wx.ID_CLOSE, "&Close Image")
        file_menu.AppendSeparator()
        self._mi_import = file_menu.Append(wx.ID_ANY, "&Import from File…")
        self._mi_export = file_menu.Append(wx.ID_ANY, "&Export to CSV…")
        file_menu.AppendSeparator()
        self._mi_prefs = file_menu.Append(wx.ID_PREFERENCES, "&Preferences…")
        file_menu.AppendSeparator()
        m_exit = file_menu.Append(wx.ID_EXIT, "E&xit")
        bar.Append(file_menu, "&File")

        radio_menu = wx.Menu()
        m_download = radio_menu.Append(wx.ID_ANY, "&Download from Radio\tCtrl+Shift+D")
        self._mi_upload = radio_menu.Append(wx.ID_ANY, "&Upload to Radio\tCtrl+Shift+U")
        radio_menu.AppendSeparator()
        from chirp_backend import query as query_mod

        query_submenu = wx.Menu()
        self._mi_query = []
        for src in query_mod.SOURCES:
            item = query_submenu.Append(wx.ID_ANY, src["label"] + "…")
            self.Bind(wx.EVT_MENU, lambda e, k=src["key"]: self.on_query_source(k), item)
            self._mi_query.append(item)
        radio_menu.AppendSubMenu(query_submenu, "&Query Source")
        radio_menu.AppendSeparator()
        self._mi_settings = radio_menu.Append(wx.ID_ANY, "&Settings…\tCtrl+Shift+P")
        self._mi_radio_info = radio_menu.Append(wx.ID_ANY, "Radio &Info…")
        bar.Append(radio_menu, "&Radio")

        ch_menu = wx.Menu()
        self._mi_edit = ch_menu.Append(wx.ID_ANY, "&Edit channel…")
        self._mi_goto = ch_menu.Append(wx.ID_ANY, "&Go to channel…")
        self._mi_banks = ch_menu.Append(wx.ID_ANY, "Channel ban&ks…\tCtrl+B")
        self._mi_ops = ch_menu.Append(wx.ID_ANY, "&Organize Channels…\tCtrl+M")
        ch_menu.AppendSeparator()
        self._mi_find = ch_menu.Append(wx.ID_ANY, "&Find\tCtrl+F")
        self._mi_find_next = ch_menu.Append(wx.ID_ANY, "Find ne&xt\tCtrl+G")
        ch_menu.AppendSeparator()
        self._mi_prev = ch_menu.Append(wx.ID_ANY, "&Previous page\tCtrl+Alt+Left")
        self._mi_next = ch_menu.Append(wx.ID_ANY, "Nex&t page\tCtrl+Alt+Right")
        bar.Append(ch_menu, "&Channels")

        help_menu = wx.Menu()
        m_keys = help_menu.Append(wx.ID_ANY, "&Keyboard Shortcuts\tF1")
        m_about = help_menu.Append(wx.ID_ABOUT, "&About")
        bar.Append(help_menu, "&Help")

        self.SetMenuBar(bar)

        # Items that move focus into the page themselves (re-render / focus a
        # row or control) bind directly. Items that don't manage focus get a
        # wrapper that restores webview focus afterward, so the bridged Ctrl
        # shortcuts keep working without an extra click into the page (rule #6).
        self.Bind(wx.EVT_MENU, self.on_open, m_open)
        self.Bind(wx.EVT_MENU, self.on_operations, self._mi_ops)
        self.Bind(wx.EVT_MENU, self.on_menu_edit_channel, self._mi_edit)
        self.Bind(wx.EVT_MENU, self.on_menu_goto, self._mi_goto)
        self.Bind(wx.EVT_MENU, lambda e: self.on_channel_banks({}), self._mi_banks)
        self.Bind(wx.EVT_MENU, self.on_find, self._mi_find)
        self.Bind(wx.EVT_MENU, lambda e: self.on_find_next(), self._mi_find_next)
        self.Bind(wx.EVT_MENU, lambda e: self._change_page(self._page - 1, "prev"), self._mi_prev)
        self.Bind(wx.EVT_MENU, lambda e: self._change_page(self._page + 1, "next"), self._mi_next)
        self.Bind(wx.EVT_MENU, self.on_exit, m_exit)

        self.Bind(wx.EVT_MENU, self._menu_then_focus(self.on_save), self._mi_save)
        self.Bind(wx.EVT_MENU, self._menu_then_focus(self.on_save_as), self._mi_save_as)
        self.Bind(wx.EVT_MENU, self._menu_then_focus(self.on_close_image), self._mi_close)
        self.Bind(wx.EVT_MENU, self.on_import_file, self._mi_import)  # manages own focus
        self.Bind(wx.EVT_MENU, self._menu_then_focus(self.on_export_csv), self._mi_export)
        self.Bind(wx.EVT_MENU, self._menu_then_focus(self.on_radio_info), self._mi_radio_info)
        self.Bind(wx.EVT_MENU, self.on_preferences, self._mi_prefs)  # manages own focus
        self.Bind(wx.EVT_MENU, self._menu_then_focus(self.on_about), m_about)
        self.Bind(wx.EVT_MENU, self._menu_then_focus(self.on_shortcuts), m_keys)
        # Download/Upload manage their own focus (dialogs + grid re-render).
        self.Bind(wx.EVT_MENU, self.on_download, m_download)
        self.Bind(wx.EVT_MENU, self.on_upload, self._mi_upload)
        self.Bind(wx.EVT_MENU, self.on_settings, self._mi_settings)

        self._radio_menu_items = (
            self._mi_save, self._mi_save_as, self._mi_close,
            self._mi_edit, self._mi_goto, self._mi_ops,
            self._mi_find, self._mi_find_next,
            self._mi_prev, self._mi_next, self._mi_upload, self._mi_settings,
            self._mi_import, self._mi_export, self._mi_radio_info,
            *self._mi_query,  # query needs a loaded radio to import into
        )
        self._update_menu_state()
        self._rebuild_recent_menu()

        # The native menu loop (opened via Alt/F10 → SC_KEYMENU) leaves focus on
        # the frame when it closes without a selection (e.g. Escape). Return
        # focus to the webview so the page keeps receiving keys and NVDA lands
        # back in the grid. Chosen items already restore focus via
        # _menu_then_focus / their own re-render.
        self.Bind(wx.EVT_MENU_CLOSE, self._on_menu_close)

    def _menu_then_focus(self, handler):
        """Wrap a menu handler so webview focus is restored after it runs."""
        def wrapper(event):
            handler(event)
            self._restore_webview_focus()
        return wrapper

    def _restore_webview_focus(self) -> None:
        if self.view.using_webview and self.view.view is not None:
            self.view.view.SetFocus()
        self.view.focus()

    def _on_menu_open(self, event: wx.MenuEvent) -> None:
        """Diagnostic: confirms a native menu actually opened (key path works)."""
        LOG.debug("menu OPEN fired — native menu activated")
        event.Skip()

    def _on_maximize(self, event: wx.MaximizeEvent) -> None:
        """Keep keys alive after maximize: focus can land on the frame, but the
        menu keys are caught in the page, so return focus to the webview."""
        event.Skip()
        LOG.debug("maximize — restoring webview focus")
        wx.CallAfter(self._restore_webview_focus)

    def _on_activate(self, event: wx.ActivateEvent) -> None:
        """Return focus to the webview when the window regains activation, so the
        in-page key handling keeps working (e.g. after Alt+Tab or maximize)."""
        event.Skip()
        # Skip while a modal dialog is up (the frame is disabled then), so we
        # don't yank focus away from the dialog.
        if event.GetActive() and self.IsEnabled():
            wx.CallAfter(self._restore_webview_focus)

    def _on_menu_close(self, event: wx.MenuEvent) -> None:
        """Return focus to the webview after a native menu closes (e.g. Escape)."""
        event.Skip()
        # Defer until the menu loop has fully unwound, or SetFocus is ignored.
        wx.CallAfter(self._restore_webview_focus)

    # Mnemonic letter -> top-level menu index, matching _build_menubar's
    # bar.Append() order and the &File/&Radio/&Channels/&Help accelerators.
    _MNEMONIC_TO_MENU_INDEX = {"F": 0, "R": 1, "C": 2, "H": 3}

    def _on_char_hook(self, event: wx.KeyEvent) -> None:
        """Catch menu keys before the focused WebView2 can swallow them.

        The webview holds keyboard focus essentially permanently (it's the only
        client-area control), and a focused WebView2 swallows Alt and Ctrl/Alt
        combos — confirmed with NVDA (see module docstring). EVT_CHAR_HOOK is a
        low-level keyboard hook on Windows that sees the key before WebView2
        does (the same mechanism wx_accessible_webview's own dialogs use for
        Escape), so we use it to drive the native menu bar:

        * Plain Alt, tapped alone, activates the menu bar (then Right/Left walk
          across the top-level menus, like any native Windows app). "Alone"
          can't be known until we see whether another key follows, so it arms a
          short timer that ANY other key below cancels — so Alt+F, Alt+Tab and
          Alt+F4 cancel cleanly because their second key arrives first.
        * Alt+letter opens that menu; F10 activates the bar.
        * Ctrl+O is caught here because WebView2 treats Ctrl/Alt combos as
          browser accelerator keys (``AreBrowserAcceleratorKeysEnabled``, on by
          default, not exposed by wx.html2.WebView) and can eat Ctrl+O before
          the page's own ``_SHORTCUTS_JS`` listener sees it.

        Must call event.Skip() for every key we don't consume, or normal typing
        in the webview breaks (EVT_CHAR_HOOK is the highest-priority key event
        in wx and stops propagation otherwise).
        """
        key = event.GetKeyCode()
        LOG.debug(
            "char_hook key=%d alt=%s ctrl=%s shift=%s",
            key, event.AltDown(), event.ControlDown(), event.ShiftDown(),
        )

        # Plain Alt by itself: arm menu-bar activation (cancelled below if a
        # second key turns it into a combo).
        if key == wx.WXK_ALT and not event.ControlDown() and not event.ShiftDown():
            self._schedule_bare_alt()
            event.Skip()
            return

        # Any other key means Alt was not tapped alone — drop the pending arm.
        self._cancel_bare_alt()

        if event.AltDown() and not event.ControlDown() and not event.ShiftDown():
            letter = chr(key).upper() if 32 <= key < 128 else ""
            index = self._MNEMONIC_TO_MENU_INDEX.get(letter)
            if index is not None:
                self._open_menu_bar_menu(index)
                return  # consumed
        if key == wx.WXK_F10 and not event.HasAnyModifiers():
            self._activate_menu_bar()  # highlight the bar (Windows F10 convention)
            return  # consumed
        if event.ControlDown() and not event.AltDown() and not event.ShiftDown() and key == ord("O"):
            self.on_open(None)
            return  # consumed
        event.Skip()

    # Top-level menu index -> its mnemonic key code, matching _build_menubar's
    # &File/&Radio/&Channels/&Help order. Used to drive the native menu bar.
    _MENU_INDEX_TO_MNEMONIC = {0: ord("f"), 1: ord("r"), 2: ord("c"), 3: ord("h")}

    def _post_sc_keymenu(self, lparam: int) -> bool:
        """Windows: post the menu-activation message that Alt normally sends.

        WM_SYSCOMMAND / SC_KEYMENU is the exact signal Windows itself uses when
        you press Alt, which the focused WebView2 swallows (#24786). ``lparam``
        is a menu's mnemonic char to open that menu, or 0 to just activate the
        bar (highlight the first item) so Left/Right walk across it. Either way
        the OS enters the real menu-bar keyboard loop. Returns False off Windows.
        """
        if wx.Platform != "__WXMSW__":
            return False
        import ctypes
        from ctypes import wintypes

        WM_SYSCOMMAND = 0x0112
        SC_KEYMENU = 0xF100
        user32 = ctypes.windll.user32
        # Set argtypes so the 64-bit HWND isn't truncated to a C int.
        user32.PostMessageW.argtypes = [
            wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM,
        ]
        user32.PostMessageW.restype = wintypes.BOOL
        hwnd = self.GetHandle()
        ok = user32.PostMessageW(hwnd, WM_SYSCOMMAND, SC_KEYMENU, lparam)
        fg = user32.GetForegroundWindow()
        LOG.debug(
            "SC_KEYMENU lparam=%d post_ok=%s hwnd=%s foreground=%s match=%s",
            lparam, bool(ok), hwnd, fg, hwnd == fg,
        )
        return True

    def _open_menu_bar_menu(self, index: int) -> None:
        """Open a top-level menu in the REAL native menu-bar keyboard loop.

        Earlier this popped one wx.Menu with PopupMenu(), but a standalone
        popup has no menu-bar context, so Left/Right (move between File / Radio
        / Channels / Help) were dead — you could only go Up/Down within the one
        menu. Driving the native menu bar via SC_KEYMENU restores Left/Right and
        reads correctly in NVDA. Non-Windows platforms keep PopupMenu.
        """
        if self._post_sc_keymenu(self._MENU_INDEX_TO_MNEMONIC.get(index, 0)):
            return
        bar = self.GetMenuBar()
        menu = bar.GetMenu(index)
        self.PopupMenu(menu, wx.Point(0, 0))
        self._restore_webview_focus()

    def _activate_menu_bar(self) -> None:
        """Plain Alt / F10: highlight the menu bar with no menu dropped, so
        Right/Left walk across File/Radio/Channels/Help like a native app."""
        self._bare_alt_timer = None
        if not self._post_sc_keymenu(0):
            self._open_menu_bar_menu(0)  # non-Windows: open the first menu

    def _schedule_bare_alt(self) -> None:
        """Arm plain-Alt menu-bar activation. We can't tell Alt-tapped-alone
        from the start of a combo (Alt+F, Alt+Tab, Alt+F4) until another key
        does or doesn't follow, so a short timer fires and ANY other key in
        ``_on_char_hook`` cancels it. Tunable; 200 ms reads as instant."""
        self._cancel_bare_alt()
        self._bare_alt_timer = wx.CallLater(200, self._activate_menu_bar)

    def _cancel_bare_alt(self) -> None:
        timer = getattr(self, "_bare_alt_timer", None)
        if timer is not None and timer.IsRunning():
            timer.Stop()
        self._bare_alt_timer = None

    def _update_menu_state(self) -> None:
        """Disable channel/file items that need a loaded radio (NVDA hears
        'unavailable'); stubs stay enabled and announce instead."""
        loaded = radio_backend.get_state().loaded
        for item in getattr(self, "_radio_menu_items", ()):
            item.Enable(loaded)
        # Banks only exist on bank-capable radios — gate separately.
        if getattr(self, "_mi_banks", None) is not None:
            from chirp_backend import bank_ops

            self._mi_banks.Enable(loaded and bank_ops.has_bank())

    def _on_webview_loaded(self, event) -> None:
        # Install behavior JS once the document is loaded (run_js needs a loaded
        # page). The script guards against double-install and uses a delegated/
        # document-level listener, so it survives set_content view swaps.
        #
        # Deferred via CallLater, NOT CallAfter: AccessibleWebView's own
        # EVT_WEBVIEW_LOADED handler (bound first, inside its __init__) runs in
        # the same event dispatch and flushes show_welcome()'s queued
        # set_content with its own synchronous RunScript call. Calling
        # RunScript again right after, still nested inside that same native
        # WebView2 "loaded" callback, is a known trigger for a spurious "Error
        # running JavaScript: Unknown runtime error" from wxWidgets' Edge
        # backend. wx.CallAfter (an idle-event) isn't enough to escape this —
        # confirmed by direct testing, it can still run nested inside the same
        # native call stack as the loaded event and, even when it doesn't
        # surface that error, silently breaks all later
        # AddScriptMessageHandler/postMessage delivery for the rest of the
        # session (every in-page button and shortcut going forward becomes a
        # silent no-op, with no exception anywhere). wx.CallLater uses a real
        # OS timer instead of the idle queue, which reliably lands in a fresh
        # top-level message-loop iteration.
        wx.CallLater(50, self.view.run_js, _SHORTCUTS_JS)
        event.Skip()

    # -- views -------------------------------------------------------------

    def show_welcome(self) -> None:
        """Render the welcome screen into the webview."""
        self.view.set_content(html.render_view("welcome.html", version=__version__))
        self.view.status("Welcome to Versatile Radio Programmer.")
        self._set_title()

    def show_channels(self) -> None:
        """Render the current page of the channel grid for the loaded radio."""
        self.view.set_content(views.render_channels(self._page))
        self.view.focus()

    def _announce(self, message: str, error: bool = False) -> None:
        """Surface a result to the user: status bar, live region, and speech.

        ``error`` interrupts any in-progress speech so failures are heard now.
        """
        self.SetStatusText(message)
        self.view.status(message)  # always — the screen reader reads this
        if self._speak_enabled:    # supplemental prism speech is opt-in
            self.speaker.speak(message, interrupt=error)

    def _set_title(self) -> None:
        """Reflect the loaded radio / file in the window title bar."""
        state = radio_backend.get_state()
        if not state.loaded:
            self.SetTitle(APP_TITLE)
            return
        name = f"{state.radio.VENDOR} {state.radio.MODEL}"
        if state.image_path:
            import os

            name = f"{name} — {os.path.basename(state.image_path)}"
        self.SetTitle(f"{name} — {APP_TITLE}")

    # -- JS <-> Python bridge ---------------------------------------------

    def on_bridge_message(self, data) -> None:
        """Handle a message posted from page JS via window.vrp.postMessage().

        ``data`` is the decoded payload, a dict with an "action" — sent by both
        in-page buttons and the global keyboard shortcuts. Each handler
        announces its own result via the status live region (CLAUDE rule #3).
        """
        LOG.debug("bridge message: %r", data)
        action = data.get("action") if isinstance(data, dict) else None
        # Menu keys (Alt / Alt+letter / F10) are caught by in-page JS because a
        # focused WebView2 hides them from wx; the page bridges them here and we
        # drive the real native menu bar.
        if action == "menu_activate":
            self._activate_menu_bar()
            return
        if action == "menu_open":
            idx = data.get("index", 0) if isinstance(data, dict) else 0
            self._open_menu_bar_menu(int(idx) if idx is not None else 0)
            return
        handler = {
            "open": self.on_open,
            "save": self.on_save,
            "save_as": self.on_save_as,
            "close": self.on_close_image,
            "shortcuts": self.on_shortcuts,
            "about": self.on_about,
            "download": self.on_download,
            "upload": self.on_upload,
        }.get(action)
        if action == "edit_channel":
            self.on_edit_channel(data)
            return
        if action == "goto":
            self.on_goto(data)
            return
        if action == "page_prev":
            self._change_page(self._page - 1, "prev")
            return
        if action == "page_next":
            self._change_page(self._page + 1, "next")
            return
        if action == "operations":
            self.on_operations()
            return
        if action == "find":
            self.on_find()
            return
        if action == "find_next":
            self.on_find_next()
            return
        if action == "settings":
            self.on_settings()
            return
        if action == "channel_banks":
            self.on_channel_banks(data if isinstance(data, dict) else {})
            return
        if handler is None:
            LOG.warning("bridge message with unknown action: %r", data)
            return
        handler(None)

    def on_edit_channel(self, data: dict) -> None:
        """Open the native edit dialog for a channel, then apply + refresh.

        The big channel table stays read-only; editing happens in a separate
        top-level wx dialog (full native keyboard/screen-reader support). After
        OK the channel is written, only that row is refreshed, and focus returns
        to that row's Edit button (rule #6).
        """
        from chirp_backend import memory_ops, radio as rb
        from vrp.edit_dialog import EditChannelDialog

        try:
            number = int(data["number"])
        except (KeyError, TypeError, ValueError):
            LOG.warning("edit_channel message missing/invalid number: %r", data)
            return

        state = rb.get_state()
        if not state.loaded:
            self._announce("No radio image is open.", error=True)
            return
        mem = rb.get_memory(number)
        if mem is None:
            self._announce(f"Channel {number} could not be read.", error=True)
            return

        dlg = EditChannelDialog(self, number, mem, state.features)
        result = dlg.ShowModal()
        values = dlg.get_values() if result == wx.ID_OK else None
        dlg.Destroy()

        if values is not None:
            ok, message, _ = memory_ops.update_channel(number, values)
            self._announce(message, error=not ok)
            if ok:
                self._refresh_row(number)
        # Return focus to the row's Edit button across the native↔web boundary.
        self._focus_edit_button(number)

    def _refresh_row(self, number: int) -> None:
        """Replace one row's contents in the grid with freshly rendered HTML."""
        inner = views.render_row(number)
        if not inner:
            return
        self.view.run_js(
            f"var r=document.getElementById('ch-row-{number}');"
            f"if(r){{r.innerHTML={json.dumps(inner)};}}"
        )

    def _focus_edit_button(self, number: int) -> None:
        self._focus_element(f"edit-btn-{number}")

    def _focus_element(self, element_id: str) -> None:
        # Focus the WebView control first, then the specific element, so NVDA
        # follows focus back into the page (after a dialog or a re-render).
        if self.view.using_webview and self.view.view is not None:
            self.view.view.SetFocus()
        self.view.run_js(
            f"var b=document.getElementById({json.dumps(element_id)});if(b)b.focus();"
        )

    # -- paging ------------------------------------------------------------

    def _change_page(self, new_page: int, which: str) -> None:
        """Move to ``new_page`` (clamped), re-render, refocus, and announce."""
        tp = views.total_pages()
        new_page = min(max(new_page, 1), tp)
        if new_page == self._page:
            edge = "last" if which == "next" else "first"
            self.view.status(f"Already on the {edge} page. Page {self._page} of {tp}.")
            return

        self._page = new_page
        self.show_channels()

        # Return focus to the button pressed — unless it's now disabled at a
        # boundary (a disabled element can't hold focus), then use the other.
        has_prev = self._page > 1
        has_next = self._page < tp
        if which == "next":
            target = "page-next-btn" if has_next else "page-prev-btn"
        else:
            target = "page-prev-btn" if has_prev else "page-next-btn"
        self._focus_element(target)

        first, last = views.page_range(self._page)
        self.view.status(
            f"Page {self._page} of {tp}. Channels {first} to {last} of "
            f"{views.channel_total()}."
        )

    def on_goto(self, data: dict) -> None:
        """Jump to the page containing a channel and focus its Edit button."""
        low, high = radio_backend.get_state().memory_bounds
        raw = str(data.get("number", "")).strip()
        try:
            number = int(raw)
        except ValueError:
            number = None
        if number is None or number < low or number > high:
            shown = raw or "(blank)"
            self._announce(
                f"Channel {shown} is out of range. Enter a number from "
                f"{low} to {high}.",
                error=True,
            )
            self._focus_element("goto-input")
            return

        self._page = views.page_for_channel(number)
        self.show_channels()
        self._focus_edit_button(number)
        self.view.status(f"Channel {number}. Page {self._page} of {views.total_pages()}.")

    def on_menu_edit_channel(self, _event=None) -> None:
        """Channels ▸ Edit channel… — prompt for a number, then open the editor."""
        number = self._prompt_channel_number("Edit channel", "Channel to edit:")
        if number is not None:
            self.on_edit_channel({"number": number})

    def on_menu_goto(self, _event=None) -> None:
        """Channels ▸ Go to channel… — prompt for a number, then jump to it."""
        number = self._prompt_channel_number("Go to channel", "Channel number:")
        if number is not None:
            self.on_goto({"number": number})

    def _prompt_channel_number(self, caption: str, prompt: str):
        """Native number prompt within the radio's channel bounds, or None."""
        state = radio_backend.get_state()
        if not state.loaded:
            self._announce("No radio image is open.", error=True)
            return None
        low, high = state.memory_bounds
        number = wx.GetNumberFromUser(prompt, "Channel:", caption, low, low, high, self)
        if number < low:  # cancelled (returns -1)
            self._restore_webview_focus()
            return None
        return int(number)

    # -- bulk operations ---------------------------------------------------

    def on_operations(self, _event=None) -> None:
        """Open the Channel Operations dialog and apply the chosen operation."""
        from chirp_backend.col_defs import build_column_defs
        from vrp.ops_dialog import ChannelOperationsDialog

        state = radio_backend.get_state()
        if not state.loaded:
            self._announce("No radio image is open.", error=True)
            return
        low, high = state.memory_bounds
        default_from = views.page_range(self._page)[0]
        cols = [
            (c.name, c.label)
            for c in build_column_defs(state.features)
            if c.name != "number"
        ]

        dlg = ChannelOperationsDialog(self, low, high, default_from, cols)
        if dlg.ShowModal() == wx.ID_OK:
            numbers, _err = dlg.selected_numbers()
            op = dlg.get_operation()
            dlg.Destroy()
            self._perform_operation(numbers, op)
        else:
            dlg.Destroy()
            self._focus_element("ops-btn")

    def _perform_operation(self, numbers: list[int], op: dict) -> None:
        from chirp_backend import memory_ops as mo

        key = op["op"]
        confirm = self._confirm_message(key, op, numbers)
        if confirm and not self._confirm(confirm):
            self._focus_element("ops-btn")
            return
        if key in ("move_to", "copy_to") and self._destination_occupied(
            op["dest"], len(numbers)
        ):
            verb = "moved" if key == "move_to" else "copied"
            if not self._confirm(
                f"Channels at {op['dest']} and following are not empty and will "
                f"be overwritten by the {verb} channels. Continue?"
            ):
                self._focus_element("ops-btn")
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
            self._announce(message, error=True)
            self._focus_element("ops-btn")
            return

        target = self._op_focus_target(key, numbers, op)
        self._page = views.page_for_channel(target)
        self.show_channels()
        self._focus_edit_button(target)
        self.view.status(f"{message} Now on channel {target}.")

    def _op_focus_target(self, key: str, numbers: list[int], op: dict) -> int:
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

    def _confirm_message(self, key: str, op: dict, numbers: list[int]) -> str | None:
        """Return the confirmation text for destructive ops, else None."""
        first, last, count = numbers[0], numbers[-1], len(numbers)
        rng = f"{count} channel(s), {first} to {last}"
        if key == "delete":
            return (
                f"Delete {rng}? Their contents will be cleared. "
                "This cannot be undone."
            )
        if key == "delete_shift":
            scope = (
                "and shift all higher channels down to close the gap (this "
                "renumbers them)"
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

    def _confirm(self, message: str) -> bool:
        dlg = wx.MessageDialog(
            self, message, "Please confirm", wx.YES_NO | wx.ICON_WARNING
        )
        dlg.SetYesNoLabels("Yes", "No")
        try:
            return dlg.ShowModal() == wx.ID_YES
        finally:
            dlg.Destroy()

    def _destination_occupied(self, dest: int, count: int) -> bool:
        low, high = radio_backend.get_state().memory_bounds
        for n in range(dest, min(high, dest + count - 1) + 1):
            mem = radio_backend.get_memory(n)
            if mem is not None and not getattr(mem, "empty", True):
                return True
        return False

    # -- find --------------------------------------------------------------

    def on_find(self, _event=None) -> None:
        """Open the Find dialog; jump to and announce the first match."""
        from vrp.find_dialog import FindDialog

        if not radio_backend.get_state().loaded:
            self._announce("No radio image is open.", error=True)
            return
        dlg = FindDialog(self, self._find_from_dialog)
        found = dlg.ShowModal() == wx.ID_OK
        dlg.Destroy()
        if found and self._find_last is not None:
            self._focus_edit_button(self._find_last)
            self.view.status(self._describe_match(self._find_last, prefix="Found "))
        else:
            self._restore_webview_focus()

    def _find_from_dialog(self, query: str, fields: tuple) -> bool:
        """Search callback for the Find dialog. Navigates to the match (focus is
        applied after the dialog closes); returns True if found."""
        from chirp_backend import memory_ops

        self._find_query = query
        self._find_fields = fields
        ok, _message, affected = memory_ops.find(query, None, fields)
        if not ok:
            return False
        self._find_last = affected[0]
        self._page = views.page_for_channel(self._find_last)
        self.show_channels()
        return True

    def on_find_next(self, _event=None) -> None:
        from chirp_backend import memory_ops

        if not radio_backend.get_state().loaded:
            self._announce("No radio image is open.", error=True)
            return
        if not self._find_query:
            self.view.status("No active search. Press Control+F to find.")
            return
        low, _high = radio_backend.get_state().memory_bounds
        start = (self._find_last + 1) if self._find_last is not None else low
        ok, _message, affected = memory_ops.find(
            self._find_query, start, self._find_fields
        )
        if not ok:
            self._announce(f"No matches for '{self._find_query}'.", error=True)
            return
        prev = self._find_last
        ch = affected[0]
        self._find_last = ch
        self._page = views.page_for_channel(ch)
        self.show_channels()
        self._focus_edit_button(ch)
        if prev is not None and ch == prev:
            prefix = "Only match. "
        elif prev is not None and ch <= prev:
            prefix = "Wrapped to start. "
        else:
            prefix = "Next match. "
        self.view.status(self._describe_match(ch, prefix=prefix))

    def _describe_match(self, number: int, prefix: str = "") -> str:
        mem = radio_backend.get_memory(number)
        detail = ""
        if mem is not None and not getattr(mem, "empty", True):
            name = (getattr(mem, "name", "") or "").strip()
            mhz = f"{mem.freq / 1_000_000:.6f}".rstrip("0").rstrip(".")
            detail = f": {name or mhz}"
        return f"{prefix}'{self._find_query}' at channel {number}{detail}."

    # -- banks -------------------------------------------------------------

    def on_channel_banks(self, data: dict) -> None:
        """Assign a channel to banks. ``data`` may carry a channel number;
        otherwise prompt for one (e.g. from the Ctrl+B shortcut)."""
        from chirp_backend import bank_ops
        from vrp.bank_dialog import ChannelBanksDialog

        number = data.get("number")
        if number is None:
            number = self._prompt_channel_number("Channel banks", "Channel:")
            if number is None:
                return
        else:
            number = int(number)

        state = bank_ops.get_bank_state(number)
        if not state.get("ok"):
            self._announce(state.get("message", "Banks unavailable."), error=True)
            self._restore_webview_focus()
            return

        dlg = ChannelBanksDialog(self, state)
        applied = dlg.ShowModal() == wx.ID_OK and not state["read_only"]
        desired = dlg.get_desired_indexes() if applied else None
        dlg.Destroy()

        if desired is not None:
            ok, message, _affected = bank_ops.apply_bank_changes(number, desired)
            if ok:
                self.view.status(message)
            else:
                self._announce(message, error=True)
                wx.MessageBox(message, "Banks", wx.OK | wx.ICON_ERROR, self)

        # Return to the channel's row (navigate there so it's on the page).
        self._page = views.page_for_channel(number)
        self.show_channels()
        self._focus_edit_button(number)

    # -- preferences -------------------------------------------------------

    def on_preferences(self, _event=None) -> None:
        """File ▸ Preferences — app settings (page size, supplemental speech)."""
        from vrp.config import get_config
        from vrp.prefs_dialog import PreferencesDialog

        cfg = get_config()
        before_page = int(cfg.get("channels_per_page", 100))
        dlg = PreferencesDialog(
            self,
            {"channels_per_page": before_page, "speak_status_messages": self._speak_enabled},
        )
        if dlg.ShowModal() != wx.ID_OK:
            dlg.Destroy()
            self._restore_webview_focus()
            return
        values = dlg.get_values()
        dlg.Destroy()

        cfg.set("channels_per_page", values["channels_per_page"])
        cfg.set("speak_status_messages", values["speak_status_messages"])
        self._speak_enabled = values["speak_status_messages"]

        # Page size takes effect immediately: re-render + re-clamp the page.
        if values["channels_per_page"] != before_page and radio_backend.get_state().loaded:
            tp = views.total_pages()
            self._page = min(self._page, tp)
            self.show_channels()
            first, _last = views.page_range(self._page)
            self._focus_edit_button(first)
            self.view.status(
                f"Preferences saved. Channels per page set to "
                f"{values['channels_per_page']}. Page {self._page} of {tp}."
            )
        else:
            self.view.status("Preferences saved.")
            self._restore_webview_focus()

    # -- import / export / radio info -------------------------------------

    def on_import_file(self, _event=None) -> None:
        """File ▸ Import — import channels from another radio image file."""
        if not radio_backend.get_state().loaded:
            self._announce(
                "Open or download a radio first; imported channels go into it.",
                error=True,
            )
            return
        with wx.FileDialog(
            self, "Import channels from radio image file",
            wildcard=IMAGE_WILDCARD,
            style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST,
        ) as dlg:
            if dlg.ShowModal() == wx.ID_CANCEL:
                self._restore_webview_focus()
                return
            path = dlg.GetPath()

        src, message = radio_backend.open_image_as_source(path)
        if src is None:
            self._announce(message, error=True)
            wx.MessageBox(message, "Import", wx.OK | wx.ICON_ERROR, self)
            self._restore_webview_focus()
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
            self._announce("That image has no channels to import.", error=True)
            self._restore_webview_focus()
            return
        self._import_results(src, count)

    def on_export_csv(self, _event=None) -> None:
        """File ▸ Export — write the loaded radio's channels to a CSV file."""
        if not radio_backend.get_state().loaded:
            self._announce("No radio image is open.", error=True)
            return
        import os

        with wx.FileDialog(
            self, "Export channels to CSV file",
            wildcard="CSV files (*.csv)|*.csv|All files (*.*)|*.*",
            style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT,
        ) as dlg:
            if dlg.ShowModal() == wx.ID_CANCEL:
                self._restore_webview_focus()
                return
            path = dlg.GetPath()
        if not os.path.splitext(path)[1]:
            path += ".csv"

        ok, message, _count = radio_backend.export_to_csv(path)
        self._announce(message, error=not ok)
        if not ok:
            wx.MessageBox(message, "Export", wx.OK | wx.ICON_ERROR, self)
        self._restore_webview_focus()

    def on_radio_info(self, _event=None) -> None:
        """Radio ▸ Radio Info — read-only summary of the loaded radio."""
        state = radio_backend.get_state()
        if not state.loaded:
            self._announce("No radio image is open.", error=True)
            return
        show_message(self, "Radio information", radio_backend.describe_radio_html(state))

    # -- query sources -----------------------------------------------------

    def on_query_source(self, key: str) -> None:
        from chirp_backend import query
        from vrp.query_dialogs import QueryParamsDialog

        if not radio_backend.get_state().loaded:
            self._announce(
                "Open or download a radio first; query results import into it.",
                error=True,
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
            self._restore_webview_focus()
            return
        self._run_query(key, source, params)

    def _run_query(self, key, source, params) -> None:
        import threading
        import time
        from chirp_backend import query
        from vrp.serial_dialogs import CloneProgressDialog

        radio_result = query.make_source_radio(key)
        if radio_result is None:
            self._announce(f"Could not load source {source['label']}.", error=True)
            self._restore_webview_focus()
            return

        progress = CloneProgressDialog(self, f"Querying {source['label']}", allow_cancel=True)
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
            wx.CallAfter(self._on_query_done, source, progress, radio_result, ok, message)

        threading.Thread(target=worker, daemon=True).start()

    def _on_query_progress(self, progress, msg, percent, speak) -> None:
        progress.update(percent, 100, msg)
        if speak and msg:
            self.view.status(msg)

    def _on_query_done(self, source, progress, radio_result, ok, message) -> None:
        from chirp_backend import query

        cancelled = progress.is_cancelled()
        progress.Destroy()
        self.Enable()
        self._restore_webview_focus()

        if cancelled:
            self.view.status("Query cancelled.")
            return
        if not ok:
            self._announce(message, error=True)
            wx.MessageBox(message, "Query failed", wx.OK | wx.ICON_ERROR, self)
            return
        self.view.status(f"{source['label']}: {message}")
        if query.result_count(radio_result) > 0:
            self._import_results(radio_result, query.result_count(radio_result))

    def _import_results(self, src_radio, count) -> None:
        """Shared import flow: pick destination/overwrite, import, refresh, focus.
        Used by both query sources and Import-from-file."""
        from chirp_backend import memory_ops
        from vrp.query_dialogs import ImportDestinationDialog

        low, high = radio_backend.get_state().memory_bounds
        dlg = ImportDestinationDialog(self, count, low, high, self._first_empty_channel())
        ok = dlg.ShowModal() == wx.ID_OK
        dest = dlg.get_destination() if ok else None
        overwrite = dlg.get_overwrite() if ok else False
        dlg.Destroy()
        if not ok:
            self._restore_webview_focus()
            return

        ok, message, affected = memory_ops.import_memories(src_radio, dest, overwrite)
        if ok:
            target = affected[0] if affected else dest
            self._page = views.page_for_channel(target)
            self.show_channels()
            self._focus_edit_button(target)
            self.view.status(message)
        else:
            self._announce(message, error=True)
            wx.MessageBox(message, "Import", wx.OK | wx.ICON_ERROR, self)

    def _first_empty_channel(self) -> int:
        low, high = radio_backend.get_state().memory_bounds
        for n in range(low, high + 1):
            mem = radio_backend.get_memory(n)
            if mem is None or getattr(mem, "empty", True):
                return n
        return low

    # -- radio settings ----------------------------------------------------

    def on_settings(self, _event=None) -> None:
        """Open the radio settings editor; apply changes on OK."""
        from vrp.settings_dialog import RadioSettingsDialog

        if not radio_backend.get_state().loaded:
            self._announce("No radio image is open.", error=True)
            return
        if not radio_backend.has_settings():
            self._announce("This radio has no editable settings.", error=True)
            return
        settings = radio_backend.get_radio_settings()
        if not settings:
            self._announce("No settings are available for this radio.", error=True)
            return

        dlg = RadioSettingsDialog(self, settings)
        applied = dlg.ShowModal() == wx.ID_OK
        changed = dlg.get_changed_count() if applied else 0
        dlg.Destroy()

        if applied and changed:
            ok, message = radio_backend.apply_radio_settings(settings)
            if ok:
                self.view.status(f"Radio settings saved. {changed} setting(s) changed.")
            else:
                self._announce(message, error=True)
                wx.MessageBox(message, "Operation failed", wx.OK | wx.ICON_ERROR, self)
        elif applied:
            self.view.status("No settings were changed.")
        self._restore_webview_focus()

    # -- serial download / upload -----------------------------------------

    def on_download(self, _event=None) -> None:
        from vrp.serial_dialogs import DownloadDialog

        models = radio_backend.list_radio_models()
        dlg = DownloadDialog(self, radio_backend.list_serial_ports, models)
        ok = dlg.ShowModal() == wx.ID_OK
        port, driver_id, label = dlg.get_selection() if ok else (None, None, "")
        dlg.Destroy()
        if ok and port and driver_id:
            self._run_clone("download", port, driver_id=driver_id, label=label)
        else:
            self._restore_webview_focus()

    def on_upload(self, _event=None) -> None:
        from vrp.serial_dialogs import UploadDialog

        state = radio_backend.get_state()
        if not state.loaded:
            self._announce("No radio image is open to upload.", error=True)
            return
        dlg = UploadDialog(self, radio_backend.list_serial_ports)
        ok = dlg.ShowModal() == wx.ID_OK
        port = dlg.get_port() if ok else None
        dlg.Destroy()
        if not (ok and port):
            self._restore_webview_focus()
            return
        label = f"{state.radio.VENDOR} {state.radio.MODEL}"
        if not self._confirm(
            f"This will overwrite ALL memory channels on the {label} connected to "
            f"{port}. The radio's current contents cannot be recovered. Continue?"
        ):
            self._restore_webview_focus()
            return
        self._run_clone("upload", port, label=label)

    def _run_clone(self, kind: str, port: str, driver_id: str = "", label: str = "") -> None:
        """Run a download/upload on a background thread with live progress.

        The serial op is synchronous and not cancel-aware; for download, Cancel
        discards the result, for upload there is no Cancel. Progress is throttled
        on the worker side before marshalling to the UI thread (wx.CallAfter).
        """
        import threading
        import time
        from vrp.serial_dialogs import CloneProgressDialog

        title = "Downloading from radio" if kind == "download" else "Uploading to radio"
        progress = CloneProgressDialog(self, title, allow_cancel=(kind == "download"))
        self.Disable()  # block the main window; the dialog is a separate TLW
        progress.Show()

        throttle = {"t": 0.0, "decade": -1}

        def progress_cb(cur: int, total: int, msg: str) -> None:  # worker thread
            now = time.monotonic()
            pct = int(cur * 100 / total) if total else 0
            speak = (now - throttle["t"] >= 2.0) or (pct // 10 != throttle["decade"])
            if speak:
                throttle["t"] = now
                throttle["decade"] = pct // 10
            wx.CallAfter(self._on_clone_progress, progress, cur, total, msg, speak)

        def worker() -> None:
            if kind == "download":
                ok, message = radio_backend.download_from_radio(port, driver_id, progress_cb)
            else:
                ok, message = radio_backend.upload_to_radio(port, progress_cb)
            wx.CallAfter(self._on_clone_done, kind, progress, ok, message)

        threading.Thread(target=worker, daemon=True).start()

    def _on_clone_progress(self, progress, cur, total, msg, speak) -> None:
        progress.update(cur, total, msg)           # gauge updates every time
        if speak and msg:
            self.view.status(msg)                  # announcements are throttled

    def _on_clone_done(self, kind, progress, ok, message) -> None:
        cancelled = progress.is_cancelled()
        progress.Destroy()
        self.Enable()
        self._restore_webview_focus()

        if kind == "download":
            if cancelled:
                self._announce(
                    "Download canceled. The radio image was not changed.", error=True
                )
                return
            if ok:
                self._page = 1
                self.show_channels()
                self._update_menu_state()
                self._set_title()
                low, _high = radio_backend.get_state().memory_bounds
                self._focus_edit_button(low)
                self.view.status(f"{message}. Channel list updated.")
            else:
                self._announce(message, error=True)
                wx.MessageBox(message, "Operation failed", wx.OK | wx.ICON_ERROR, self)
        else:  # upload
            if ok:
                self.view.status(message)
            else:
                self._announce(message, error=True)
                wx.MessageBox(message, "Operation failed", wx.OK | wx.ICON_ERROR, self)

    # -- menu handlers -----------------------------------------------------

    def on_open(self, _event: wx.CommandEvent) -> None:
        with wx.FileDialog(
            self,
            "Open radio image file",
            wildcard=IMAGE_WILDCARD,
            style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST,
        ) as dlg:
            if dlg.ShowModal() == wx.ID_CANCEL:
                return
            path = dlg.GetPath()

        self._open_path(path)

    def _open_path(self, path: str) -> bool:
        """Load an image, render it, and record it in Recent files."""
        ok, message = radio_backend.load_image(path)
        self._announce(message, error=not ok)
        if ok:
            self._page = 1
            self.show_channels()
            self._set_title()
            from vrp.config import get_config

            get_config().add_recent(path)
            self._rebuild_recent_menu()
        self._update_menu_state()
        return ok

    def on_open_recent(self, path: str) -> None:
        import os
        from vrp.config import get_config

        if not os.path.exists(path):
            self._announce(
                "That file could no longer be found and was removed from Recent files.",
                error=True,
            )
            get_config().remove_recent(path)
            self._rebuild_recent_menu()
            self._restore_webview_focus()
            return
        if not self._open_path(path):
            # Won't load (corrupt/unsupported) — drop it from the list.
            get_config().remove_recent(path)
            self._rebuild_recent_menu()

    def on_clear_recent(self, _event=None) -> None:
        from vrp.config import get_config

        get_config().clear_recent()
        self._rebuild_recent_menu()
        self.view.status("Recent files list cleared.")
        self._restore_webview_focus()

    def _rebuild_recent_menu(self) -> None:
        import os
        from vrp.config import get_config

        menu = self._recent_menu
        for item in list(menu.GetMenuItems()):
            menu.Delete(item)

        recents = get_config().recent()
        if not recents:
            placeholder = menu.Append(wx.ID_ANY, "(No recent files)")
            placeholder.Enable(False)
            return

        # Disambiguate colliding basenames with the parent folder.
        basenames = [os.path.basename(p) for p in recents]
        for i, path in enumerate(recents):
            base = basenames[i]
            label = base
            if basenames.count(base) > 1:
                label = f"{base} — {os.path.basename(os.path.dirname(path))}"
            item = menu.Append(wx.ID_ANY, f"&{i + 1} {label}")
            item.SetHelp(path)
            self.Bind(wx.EVT_MENU, lambda e, p=path: self.on_open_recent(p), item)

        menu.AppendSeparator()
        clear = menu.Append(wx.ID_ANY, "&Clear recent files")
        self.Bind(wx.EVT_MENU, self.on_clear_recent, clear)

    def on_save(self, _event: wx.CommandEvent) -> None:
        state = radio_backend.get_state()
        if not state.loaded:
            self._announce("No radio image is open.", error=True)
            return
        # No original path (e.g. downloaded, never saved) → behave like Save As.
        if not state.image_path:
            self.on_save_as(_event)
            return
        ok, message = radio_backend.save_image()
        self._announce(message, error=not ok)

    def on_save_as(self, _event: wx.CommandEvent) -> None:
        state = radio_backend.get_state()
        if not state.loaded:
            self._announce("No radio image is open.", error=True)
            return
        with wx.FileDialog(
            self,
            "Save radio image file as",
            wildcard=IMAGE_WILDCARD,
            style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT,
        ) as dlg:
            if dlg.ShowModal() == wx.ID_CANCEL:
                return
            path = dlg.GetPath()
        ok, message = radio_backend.save_image(path)
        self._announce(message, error=not ok)
        if ok:
            self._set_title()

    def on_close_image(self, _event: wx.CommandEvent) -> None:
        if not radio_backend.get_state().loaded:
            self._announce("No radio image is open.", error=True)
            return
        radio_backend.unload()
        self._page = 1
        self.show_welcome()
        self._update_menu_state()
        self._announce("Closed radio image.")

    def on_exit(self, _event: wx.CommandEvent) -> None:
        self.Close()

    def on_about(self, _event: wx.CommandEvent) -> None:
        info = wx.adv.AboutDialogInfo()
        info.SetName(APP_TITLE)
        info.SetVersion(__version__)
        info.SetDescription(
            "An accessible front end to the CHIRP radio programming library.\n\n"
            "Radio driver support provided by the CHIRP project — "
            "chirpmyradio.com."
        )
        info.SetWebSite("https://chirpmyradio.com", "chirpmyradio.com")
        wx.adv.AboutBox(info, self)

    def on_shortcuts(self, _event=None) -> None:
        """Show the keyboard-shortcuts list in an accessible modal dialog.

        A modal dialog is a separate top-level window, so unlike the webview it
        receives keyboard focus normally (Tab to Close, Escape to dismiss).
        """
        rows = "".join(
            f"<tr><th scope=\"row\">{combo}</th><td>{desc}</td></tr>"
            for combo, desc, _action in APP_SHORTCUTS
        )
        body = (
            "<h2>Keyboard shortcuts</h2>"
            "<table><caption>Available keyboard shortcuts</caption>"
            '<thead><tr><th scope="col">Key</th><th scope="col">Action</th></tr></thead>'
            f"<tbody>{rows}</tbody></table>"
        )
        show_message(self, "Keyboard shortcuts", body)

    def on_not_implemented(self, _event=None) -> None:
        msg = "That feature is not yet implemented."
        self.SetStatusText(msg)
        self.view.status(msg)
        if self._speak_enabled:
            self.speaker.speak(msg, interrupt=True)


class VRPApp(wx.App):
    """The wx application object."""

    def OnInit(self) -> bool:  # noqa: N802 (wx naming)
        # Use a space-free app name. wxWidgets' Edge backend derives the
        # WebView2 user-data folder from GetUserLocalDataDir()
        # (== %LOCALAPPDATA%\<AppName>) with no override, and Edge fails with
        # "can't create its data directory" when that path contains spaces
        # ("...\Versatile Radio Programmer"). Keep the human-facing title via
        # the display name; the window title is set explicitly elsewhere.
        self.SetAppName("VRP")
        self.SetAppDisplayName(APP_TITLE)
        window = MainWindow()
        window.Show()
        self.SetTopWindow(window)
        return True


def run() -> None:
    """Create and run the VRP application."""
    app = VRPApp(False)
    app.MainLoop()
