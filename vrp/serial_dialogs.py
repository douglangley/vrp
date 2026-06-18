"""Native wx dialogs for serial download/upload (Phase 4).

Per the accessibility-lead's Phase 4 model:
- Model picker = a filter field + ListBox that narrows by substring (NVDA hears
  "Anytone AT-D878, 1 of 4" against the filtered count, far better than
  "5 of 552"). Never a 552-item combo.
- Port picker = a wx.Choice of full "COMx - description" labels, with a Refresh
  button and an explicit zero-ports state (disabled choice + guidance text).
- Progress = a modeless dialog with a gauge + status text; the spoken progress
  comes from the host live region (NVDA doesn't reliably speak wx.Gauge), so the
  app throttles and announces via view.status. Download may be cancelled (the
  result is discarded); upload cannot (a half-written radio is worse).
"""

from __future__ import annotations

import threading

import wx


class PortPicker(wx.Panel):
    """Serial-port chooser with Refresh and an explicit no-ports state."""

    def __init__(self, parent, list_ports_fn, on_change=None) -> None:
        super().__init__(parent)
        self._list_ports_fn = list_ports_fn
        self._on_change = on_change
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
        ports = self._list_ports_fn() or []
        self._devices = [p["port"] for p in ports]
        self.choice.Clear()
        if ports:
            for p in ports:
                label = f"{p['port']} - {p.get('description', '')}".strip(" -")
                self.choice.Append(label)
            self.choice.Enable(True)
            self.choice.SetSelection(0)
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
        self.port = PortPicker(self, list_ports_fn, on_change=self._update_ok)
        outer.Add(self.port, 0, wx.EXPAND | wx.ALL, 10)

        box = wx.StaticBoxSizer(wx.VERTICAL, self, "Radio model")
        box.Add(wx.StaticText(self, label="Filter:"), 0, wx.LEFT | wx.TOP, 4)
        self.filter = wx.TextCtrl(self)
        self.filter.SetName("Model filter")
        box.Add(self.filter, 0, wx.EXPAND | wx.ALL, 4)
        self.list = wx.ListBox(self, choices=[m["label"] for m in self._models])
        self.list.SetName("Radio model")
        if self._models:
            self.list.SetSelection(0)
        box.Add(self.list, 1, wx.EXPAND | wx.ALL, 4)
        self.count = wx.StaticText(self, label=f"{len(self._models)} models")
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
        self.filter.SetFocus()
        self._update_ok()

    def _on_filter(self, _event) -> None:
        q = self.filter.GetValue().strip().lower()
        self._filtered = (
            [m for m in self._models if q in m["label"].lower()] if q else list(self._models)
        )
        self.list.Set([m["label"] for m in self._filtered])
        if self._filtered:
            self.list.SetSelection(0)
        self.count.SetLabel(f"{len(self._filtered)} models match")
        self._update_ok()

    def _on_filter_key(self, event) -> None:
        # Down-arrow from the filter drops into the list without clearing it.
        if event.GetKeyCode() == wx.WXK_DOWN and self._filtered:
            self.list.SetFocus()
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
        event.Skip()


class UploadDialog(wx.Dialog):
    """Pick a serial port to upload the loaded image to."""

    def __init__(self, parent, list_ports_fn) -> None:
        super().__init__(parent, title="Upload to radio")
        outer = wx.BoxSizer(wx.VERTICAL)
        self.port = PortPicker(self, list_ports_fn, on_change=self._update_ok)
        outer.Add(self.port, 0, wx.EXPAND | wx.ALL, 10)
        buttons = self.CreateStdDialogButtonSizer(wx.OK | wx.CANCEL)
        self._ok = self.FindWindowById(wx.ID_OK)
        if self._ok:
            self._ok.SetLabel("Upload")
        outer.Add(buttons, 0, wx.EXPAND | wx.ALL, 8)
        self.SetSizerAndFit(outer)
        self.Bind(wx.EVT_BUTTON, self._on_ok, id=wx.ID_OK)
        self._update_ok()

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
        event.Skip()


class CloneProgressDialog(wx.Dialog):
    """Modeless progress dialog for a download/upload (gauge + status text)."""

    def __init__(self, parent, title: str, allow_cancel: bool = True) -> None:
        super().__init__(parent, title=title)
        self._cancelled = threading.Event()

        outer = wx.BoxSizer(wx.VERTICAL)
        self.text = wx.StaticText(self, label="Starting…")
        self.text.SetName("Progress")
        outer.Add(self.text, 0, wx.ALL, 12)
        self.gauge = wx.Gauge(self, range=100, size=(300, -1))
        outer.Add(self.gauge, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 12)
        if allow_cancel:
            cancel = wx.Button(self, wx.ID_CANCEL, "Cancel")
            outer.Add(cancel, 0, wx.ALIGN_RIGHT | wx.ALL, 8)
            cancel.Bind(wx.EVT_BUTTON, self._on_cancel)
        self.SetSizerAndFit(outer)

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
