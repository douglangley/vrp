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
    ("F1", "Show this list of keyboard shortcuts"),
]


class MainWindow(wx.Frame):
    def __init__(self) -> None:
        super().__init__(None, title="Versatile Radio Programmer", size=(900, 600))
        self.CreateStatusBar()

        # Build speech: Speaker is a class, not a bare function. Create an
        # instance and pass its .speak method; if prism is unavailable the
        # method is a no-op, so Announcer degrades gracefully.
        self._speaker = Speaker()
        self.announce = Announcer(
            set_status=self.SetStatusText,
            speak=lambda m: self._speaker.speak(m, interrupt=True),
        )

        self.grid = ChannelGrid(self)
        self._menu_items: dict[str, wx.MenuItem] = {}
        self._radio_gated_keys: set[str] = set()
        self._build_menubar()
        self._update_menu_state()
        self.grid.SetFocus()

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
        m = wx.Menu()
        self._add(m, "download", "&Download from Radio\tCtrl+Shift+D", self.on_download)
        self._add(m, "upload", "&Upload to Radio\tCtrl+Shift+U", self.on_upload, needs_radio=True)
        self._add(m, "settings", "&Settings…\tCtrl+Shift+P", self.on_settings, needs_radio=True)
        self._add(m, "radio_info", "Radio &Info…", self.on_radio_info, needs_radio=True)
        return m

    def _build_channels_menu(self) -> wx.Menu:
        # Filled in by the reorganization task; empty for now so the bar builds.
        return wx.Menu()

    def _build_help_menu(self) -> wx.Menu:
        m = wx.Menu()
        self._add(m, "shortcuts", "&Keyboard Shortcuts\tF1", self.on_shortcuts)
        self._add(m, "about", "&About", self.on_about)
        return m

    def _update_menu_state(self) -> None:
        loaded = radio_backend.get_state().loaded
        for key in self._radio_gated_keys:
            self._menu_items[key].Enable(loaded)

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
