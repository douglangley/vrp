"""Native wx dialogs for serial download/upload (Phase 4).

Per the accessibility-lead's Phase 4 model:
- Model picker = a filter field + ListBox that narrows by substring (NVDA hears
  "Anytone AT-D878, 1 of 4" against the filtered count, far better than
  "5 of 552"). Never a 552-item combo.
- Port picker = a wx.Choice of full "COMx - description" labels, with a Refresh
  button and an explicit zero-ports state (disabled choice + guidance text). The
  dialog opens focused on the port, with the last-used port (persisted in
  config) preselected so a repeat clone is Enter-away; tab order then flows to
  the model filter, the list, and the Download/Upload button.
- Progress = a modeless dialog with a gauge + status text; the spoken progress
  comes from the host live region (NVDA doesn't reliably speak wx.Gauge), so the
  app throttles and announces via view.status. Download may be cancelled (the
  result is discarded); upload cannot (a half-written radio is worse).
"""

from __future__ import annotations

import re
import threading

import wx

from vrp.config import get_config


def _normalize_for_search(text: str) -> str:
    """Lowercase and drop non-alphanumerics so 'uv5r' matches 'UV-5R'."""
    return re.sub(r"[^a-z0-9]", "", text.lower())


def filter_models(models: list[dict], query: str) -> list[dict]:
    """Return the models whose label matches ``query``.

    Matching is case- and punctuation-insensitive, and multi-term: the query is
    split on whitespace and *every* term must appear in the label once both are
    normalized (lowercased, non-alphanumerics stripped). So 'uv5r' matches
    'Baofeng UV-5R Mini' (the hyphen no longer blocks the match — the original
    bug) and 'baofeng 5r' matches any Baofeng whose model contains '5r'. An
    empty/whitespace query returns all models.
    """
    terms = [t for t in (_normalize_for_search(p) for p in query.split()) if t]
    if not terms:
        return list(models)
    return [
        m for m in models
        if all(term in _normalize_for_search(m["label"]) for term in terms)
    ]


def show_radio_prompts(parent, prompts: dict, *, pre_title: str = "Instructions") -> bool:
    """Show a driver's clone prompts as native dialogs, in order, BEFORE the
    serial port is opened. Returns True to proceed, False if the user backs out.

    Native ``wx.MessageBox`` dialogs are modal and screen-reader accessible for
    free (NVDA/VoiceOver announce the title, message text, and buttons; Escape
    maps to the negative button; focus returns to ``parent`` on close). Order:
      1. ``experimental`` — Yes/No, default **No**: the user must explicitly
         accept the risk of an experimental driver to continue.
      2. ``info`` — OK/Cancel.
      3. ``pre`` — OK/Cancel; often literal required steps on the radio itself
         (e.g. "set the radio to clone mode, then click OK").
    A prompt whose text is empty/None is skipped; with no prompts set this is a
    no-op that returns True immediately.
    """
    experimental = prompts.get("experimental")
    if experimental:
        msg = (
            f"{experimental}\n\n"
            "This is an experimental driver. Do you accept the risk and want "
            "to continue?"
        )
        if wx.MessageBox(
            msg, "Experimental driver",
            wx.YES_NO | wx.NO_DEFAULT | wx.ICON_WARNING, parent,
        ) != wx.YES:
            return False

    for key, title in (("info", "Radio information"), ("pre", pre_title)):
        text = prompts.get(key)
        if text:
            if wx.MessageBox(
                text, title, wx.OK | wx.CANCEL | wx.ICON_INFORMATION, parent,
            ) != wx.OK:
                return False
    return True


def _select_index(devices: list[str], *, current=None, preferred=None) -> int:
    """Which port index to select: keep the current one if it's still present
    (e.g. after a manual Refresh), else the preferred (last-used) port, else 0."""
    if current and current in devices:
        return devices.index(current)
    if preferred and preferred in devices:
        return devices.index(preferred)
    return 0


class PortPicker(wx.Panel):
    """Serial-port chooser with Refresh and an explicit no-ports state."""

    def __init__(self, parent, list_ports_fn, on_change=None,
                 preferred_port=None) -> None:
        super().__init__(parent)
        self._list_ports_fn = list_ports_fn
        self._on_change = on_change
        self._preferred = preferred_port
        self._devices: list[str] = []

        row = wx.BoxSizer(wx.HORIZONTAL)
        row.Add(wx.StaticText(self, label="Serial port:"), 0,
                wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 6)
        self.choice = wx.Choice(self)
        self.choice.SetName("Serial port")
        row.Add(self.choice, 1, wx.EXPAND | wx.RIGHT, 6)
        self.refresh_btn = wx.Button(self, label="Refresh")
        row.Add(self.refresh_btn, 0)

        outer = wx.BoxSizer(wx.VERTICAL)
        outer.Add(row, 0, wx.EXPAND)
        self.status = wx.StaticText(self, label="")
        self.status.SetName("Serial port status")
        outer.Add(self.status, 0, wx.TOP, 4)
        self.SetSizer(outer)

        self.refresh_btn.Bind(wx.EVT_BUTTON, lambda _e: self.refresh())
        self.choice.Bind(wx.EVT_CHOICE, lambda _e: self._changed())
        self.refresh()

    def refresh(self) -> None:
        prev = self.get_port()  # preserve the user's pick across a manual Refresh
        ports = self._list_ports_fn() or []
        self._devices = [p["port"] for p in ports]
        self.choice.Clear()
        if ports:
            for p in ports:
                label = f"{p['port']} - {p.get('description', '')}".strip(" -")
                self.choice.Append(label)
            self.choice.Enable(True)
            self.choice.SetSelection(
                _select_index(self._devices, current=prev, preferred=self._preferred)
            )
            self.status.SetLabel(f"{len(ports)} serial port(s) found.")
        else:
            self.choice.Append("No serial ports detected")
            self.choice.SetSelection(0)
            self.choice.Enable(False)
            self.status.SetLabel(
                "No serial ports were found. Connect your radio's programming "
                "cable, then choose Refresh."
            )
        self._changed()

    def focus(self) -> None:
        """Put keyboard focus on the port chooser (or Refresh if no ports)."""
        if self.has_ports():
            self.choice.SetFocus()
        else:
            self.refresh_btn.SetFocus()

    def has_ports(self) -> bool:
        return bool(self._devices)

    def get_port(self):
        if not self._devices:
            return None
        i = self.choice.GetSelection()
        return self._devices[i] if 0 <= i < len(self._devices) else None

    def _changed(self) -> None:
        if self._on_change:
            self._on_change()


class DownloadDialog(wx.Dialog):
    """Pick a serial port + a radio model to download from."""

    def __init__(self, parent, list_ports_fn, models) -> None:
        super().__init__(parent, title="Download from radio")
        self._models = list(models)
        self._filtered = list(models)

        outer = wx.BoxSizer(wx.VERTICAL)
        self.port = PortPicker(
            self, list_ports_fn, on_change=self._update_ok,
            preferred_port=get_config().get_last_serial_port(),
        )
        outer.Add(self.port, 0, wx.EXPAND | wx.ALL, 10)

        box = wx.StaticBoxSizer(wx.VERTICAL, self, "Radio model")
        box.Add(wx.StaticText(self, label="Filter:"), 0, wx.LEFT | wx.TOP, 4)
        self.filter = wx.TextCtrl(self)
        self.filter.SetName("Model filter")
        box.Add(self.filter, 0, wx.EXPAND | wx.ALL, 4)
        # A real preceding StaticText is what NVDA/VoiceOver read as the list's
        # name; SetName() alone is ignored by screen readers (and the nearest
        # other label, "Filter:", would otherwise misname the list).
        box.Add(wx.StaticText(self, label="Radio model:"), 0, wx.LEFT | wx.TOP, 4)
        self.list = wx.ListBox(self, choices=[m["label"] for m in self._models])
        self.list.SetName("Radio model")
        if self._models:
            self.list.SetSelection(0)
        box.Add(self.list, 1, wx.EXPAND | wx.ALL, 4)
        self.count = wx.StaticText(self, label=self._count_label(len(self._models)))
        self.count.SetName("Model count")
        box.Add(self.count, 0, wx.ALL, 4)
        outer.Add(box, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)

        buttons = self.CreateStdDialogButtonSizer(wx.OK | wx.CANCEL)
        self._ok = self.FindWindowById(wx.ID_OK)
        if self._ok:
            self._ok.SetLabel("Download")
        outer.Add(buttons, 0, wx.EXPAND | wx.ALL, 8)

        self.SetSizerAndFit(outer)
        self.filter.Bind(wx.EVT_TEXT, self._on_filter)
        self.filter.Bind(wx.EVT_KEY_DOWN, self._on_filter_key)
        self.list.Bind(wx.EVT_LISTBOX, lambda _e: self._update_ok())
        self.Bind(wx.EVT_BUTTON, self._on_ok, id=wx.ID_OK)
        # Land on the serial port first (tab order then flows port -> filter ->
        # list -> Download, matching control creation order). Done from
        # EVT_INIT_DIALOG via CallAfter so it runs AFTER wx's own default focus
        # placement (which would otherwise clobber it, esp. on macOS).
        self.Bind(wx.EVT_INIT_DIALOG, self._on_init_dialog)
        self._update_ok()

    @staticmethod
    def _count_label(n: int) -> str:
        return "1 model matches" if n == 1 else f"{n} models match"

    def _on_init_dialog(self, event) -> None:
        event.Skip()  # let wx's default init (data transfer, focus) run first
        wx.CallAfter(self.port.focus)

    def _on_filter(self, _event) -> None:
        self._filtered = filter_models(self._models, self.filter.GetValue())
        # Freeze/Thaw around the full rebuild: at ~552 items this suppresses
        # flicker and the burst of accessibility events NVDA would otherwise
        # try to announce on every keystroke.
        self.list.Freeze()
        try:
            self.list.Set([m["label"] for m in self._filtered])
            if self._filtered:
                self.list.SetSelection(0)
        finally:
            self.list.Thaw()
        self.count.SetLabel(self._count_label(len(self._filtered)))
        self._update_ok()

    def _on_filter_key(self, event) -> None:
        # Down-arrow from the filter drops into the list without clearing it.
        if event.GetKeyCode() == wx.WXK_DOWN and self._filtered:
            self.list.SetFocus()
            if self.list.GetSelection() == wx.NOT_FOUND:
                self.list.SetSelection(0)  # so the screen reader announces a row
            # consume Down: focus moved into the list intentionally
        else:
            event.Skip()

    def _selected_model(self):
        i = self.list.GetSelection()
        return self._filtered[i] if 0 <= i < len(self._filtered) else None

    def _update_ok(self) -> None:
        # May be called by the PortPicker's on_change before this dialog has
        # finished building (port/list/_ok not yet assigned) — no-op until ready.
        if not getattr(self, "_ok", None) or not hasattr(self, "list"):
            return
        self._ok.Enable(self.port.has_ports() and self._selected_model() is not None)

    def get_selection(self):
        m = self._selected_model()
        return self.port.get_port(), (m["id"] if m else None), (m["label"] if m else "")

    def _on_ok(self, event: wx.CommandEvent) -> None:
        if not self.port.has_ports():
            wx.MessageBox("No serial port selected.", "Download", wx.OK | wx.ICON_ERROR, self)
            return
        if self._selected_model() is None:
            wx.MessageBox("Choose a radio model.", "Download", wx.OK | wx.ICON_ERROR, self)
            self.list.SetFocus()
            return
        get_config().set_last_serial_port(self.port.get_port())
        event.Skip()


class UploadDialog(wx.Dialog):
    """Pick a serial port to upload the loaded image to."""

    def __init__(self, parent, list_ports_fn) -> None:
        super().__init__(parent, title="Upload to radio")
        outer = wx.BoxSizer(wx.VERTICAL)
        self.port = PortPicker(
            self, list_ports_fn, on_change=self._update_ok,
            preferred_port=get_config().get_last_serial_port(),
        )
        outer.Add(self.port, 0, wx.EXPAND | wx.ALL, 10)
        buttons = self.CreateStdDialogButtonSizer(wx.OK | wx.CANCEL)
        self._ok = self.FindWindowById(wx.ID_OK)
        if self._ok:
            self._ok.SetLabel("Upload")
        outer.Add(buttons, 0, wx.EXPAND | wx.ALL, 8)
        self.SetSizerAndFit(outer)
        self.Bind(wx.EVT_BUTTON, self._on_ok, id=wx.ID_OK)
        # Land on the serial port, from EVT_INIT_DIALOG so it runs after wx's
        # own default focus placement (see DownloadDialog._on_init_dialog).
        self.Bind(wx.EVT_INIT_DIALOG, self._on_init_dialog)
        self._update_ok()

    def _on_init_dialog(self, event) -> None:
        event.Skip()
        wx.CallAfter(self.port.focus)

    def get_port(self):
        return self.port.get_port()

    def _update_ok(self) -> None:
        if not getattr(self, "_ok", None) or not hasattr(self, "port"):
            return
        self._ok.Enable(self.port.has_ports())

    def _on_ok(self, event: wx.CommandEvent) -> None:
        if not self.port.has_ports():
            wx.MessageBox("No serial port selected.", "Upload", wx.OK | wx.ICON_ERROR, self)
            return
        get_config().set_last_serial_port(self.port.get_port())
        event.Skip()


class CloneProgressDialog(wx.Dialog):
    """Modeless progress dialog for a download/upload (gauge + status text)."""

    def __init__(self, parent, title: str, allow_cancel: bool = True) -> None:
        super().__init__(parent, title=title)
        self._cancelled = threading.Event()
        self._allow_cancel = allow_cancel

        outer = wx.BoxSizer(wx.VERTICAL)
        self.text = wx.StaticText(self, label="Starting…")
        self.text.SetName("Status")
        outer.Add(self.text, 0, wx.ALL, 12)
        self.gauge = wx.Gauge(self, range=100, size=(300, -1))
        self.gauge.SetName("Progress")
        outer.Add(self.gauge, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 12)
        if allow_cancel:
            cancel = wx.Button(self, wx.ID_CANCEL, "Cancel")
            outer.Add(cancel, 0, wx.ALIGN_RIGHT | wx.ALL, 8)
            cancel.Bind(wx.EVT_BUTTON, self._on_cancel)
        self.SetSizerAndFit(outer)
        # The dialog is modeless and the worker thread holds a reference to it
        # (it marshals progress back via wx.CallAfter). A user pressing the
        # title-bar X / Alt+F4 would otherwise Destroy it out from under the
        # worker -> "wrapped C/C++ object deleted" crash. Intercept the close:
        # treat it as Cancel when cancellable, and never self-destroy here —
        # destruction stays the UI thread's job once the clone finishes.
        self.Bind(wx.EVT_CLOSE, self._on_close)

    def _on_close(self, event) -> None:
        if self._allow_cancel and not self._cancelled.is_set():
            self._cancelled.set()
            self.text.SetLabel("Cancelling…")
        event.Veto()

    def update(self, cur: int, total: int, msg: str) -> None:
        if total:
            self.gauge.SetRange(total)
            self.gauge.SetValue(min(max(cur, 0), total))
        if msg:
            self.text.SetLabel(msg)

    def _on_cancel(self, _event) -> None:
        self._cancelled.set()
        self.text.SetLabel("Cancelling…")

    def is_cancelled(self) -> bool:
        return self._cancelled.is_set()
