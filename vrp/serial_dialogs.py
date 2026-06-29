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
from vrp.speech import Speaker

# Supplemental speech for transient confirmations that don't move focus (e.g.
# adding/removing a favorite). Module-level so the prism backend is acquired
# once; a no-op when speech is unavailable.
_speaker = Speaker()


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


def show_model_details(parent, model, describe_fn) -> None:
    """Open the highlighted model's capabilities + clone prompts in a read-only
    review box (vrp.info_dialog.InfoDialog). No-op when nothing is selected or no
    describer is wired."""
    if model is None or describe_fn is None:
        return
    from vrp.info_dialog import InfoDialog

    text = describe_fn(model["id"]) or "No information is available."
    dlg = InfoDialog(parent, f"Radio details — {model['label']}", text,
                     name="Radio details")
    dlg.ShowModal()
    dlg.Destroy()


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


class RadioListView(wx.ListCtrl):
    """A single-column list with **native incremental type-ahead** — typing
    several letters jumps to the first item starting with them. ``wx.ListBox``
    only does single-letter cycling on Windows; ``wx.ListCtrl`` is the native
    SysListView32 there, which does true type-ahead and is read by NVDA.

    Exposes a small ``wx.ListBox``-compatible API (Set / GetCount / GetString /
    GetSelection / SetSelection / SetStringSelection) so the dialogs and their
    tests stay simple; ``on_select`` is called when the selection changes.

    Platform note: on Windows this is the native list-view (type-ahead + NVDA).
    On macOS ``wx.ListCtrl`` is wx's generic control and may read poorly under
    VoiceOver — these serial dialogs are NVDA/Windows-verified; revisit the
    control choice if/when the macOS VoiceOver pass covers them.
    """

    def __init__(self, parent, *, name: str, on_select=None,
                 size=(280, 200)) -> None:
        super().__init__(
            parent,
            style=wx.LC_REPORT | wx.LC_SINGLE_SEL | wx.LC_NO_HEADER,
            size=size,
        )
        self.SetName(name)
        self.InsertColumn(0, "")
        self._on_select = on_select
        self.Bind(wx.EVT_LIST_ITEM_SELECTED, self._fire_select)
        self.Bind(wx.EVT_SIZE, self._on_size)

    def _on_size(self, event) -> None:
        event.Skip()
        w = self.GetClientSize().width
        if w > 0:
            self.SetColumnWidth(0, w)  # single column fills the width

    def _fire_select(self, event) -> None:
        event.Skip()
        if self._on_select:
            self._on_select()

    # -- wx.ListBox-compatible surface -------------------------------------
    def Set(self, labels) -> None:
        # Freeze around the rebuild: suppresses flicker and the burst of
        # accessibility events NVDA would announce per item at ~552 rows.
        self.Freeze()
        try:
            self.DeleteAllItems()
            for label in labels:
                self.InsertItem(self.GetItemCount(), label)
            w = self.GetClientSize().width
            self.SetColumnWidth(0, w if w > 0 else wx.LIST_AUTOSIZE)
            if labels:
                self.Select(0)
                self.Focus(0)
        finally:
            self.Thaw()

    def GetCount(self) -> int:
        return self.GetItemCount()

    def GetString(self, i: int) -> str:
        return self.GetItemText(i)

    def GetSelection(self) -> int:
        return self.GetFirstSelected()  # -1 (wx.NOT_FOUND) when none

    def SetSelection(self, i: int) -> None:
        if 0 <= i < self.GetItemCount():
            self.Select(i)
            self.Focus(i)
            self.EnsureVisible(i)

    def SetStringSelection(self, s: str) -> bool:
        for i in range(self.GetItemCount()):
            if self.GetItemText(i) == s:
                self.SetSelection(i)
                return True
        return False


class ModelPicker:
    """Accessible filter + radio-model list + count, shared by the Download and
    Favorites dialogs.

    **Not a wx.Panel.** Its controls are created as direct children of the host
    dialog and appended to a caller-provided ``sizer``. An earlier version nested
    these in a ``wx.Panel`` inside the static box, which broke screen-reader tab
    order/exposure (the filter and neighbouring buttons became unreachable). The
    controls live directly on the dialog exactly as the original inline picker
    did, so Tab and the static box behave normally.

    A real preceding StaticText names the list for screen readers (SetName alone
    is ignored, and the nearest other label, "Filter:", would otherwise misname
    the list). Down-arrow from the filter drops into the list. The list is rebuilt
    inside Freeze/Thaw to suppress flicker and the burst of accessibility events
    NVDA would otherwise announce on every keystroke at ~552 items. ``on_change``
    fires when the filtered result or the selection changes.
    """

    def __init__(self, parent, sizer, models, *, on_change=None,
                 list_label: str = "Radio model") -> None:
        self._models = list(models)
        self._filtered = list(models)
        self._on_change = on_change

        sizer.Add(wx.StaticText(parent, label="Filter:"), 0, wx.LEFT | wx.TOP, 4)
        self.filter = wx.TextCtrl(parent)
        self.filter.SetName("Model filter")
        sizer.Add(self.filter, 0, wx.EXPAND | wx.ALL, 4)
        sizer.Add(wx.StaticText(parent, label=list_label + ":"), 0, wx.LEFT | wx.TOP, 4)
        # A list-view (not a ListBox) so typing several letters jumps within the
        # list, not just first-letter cycling. on_select keeps OK/buttons in sync.
        self.list = RadioListView(parent, name=list_label, on_select=self._changed)
        self.list.Set([m["label"] for m in self._models])
        sizer.Add(self.list, 1, wx.EXPAND | wx.ALL, 4)
        self.count = wx.StaticText(parent, label=self._count_label(len(self._models)))
        self.count.SetName("Model count")
        sizer.Add(self.count, 0, wx.ALL, 4)

        self.filter.Bind(wx.EVT_TEXT, lambda _e: self._apply_filter())
        self.filter.Bind(wx.EVT_KEY_DOWN, self._on_filter_key)

    @staticmethod
    def _count_label(n: int) -> str:
        return "1 model matches" if n == 1 else f"{n} models match"

    def set_models(self, models) -> None:
        """Replace the base list (e.g. All radios <-> Favorites), reapplying the
        current filter text."""
        self._models = list(models)
        self._apply_filter()

    def _apply_filter(self) -> None:
        self._filtered = filter_models(self._models, self.filter.GetValue())
        self.list.Set([m["label"] for m in self._filtered])  # selects row 0
        self.count.SetLabel(self._count_label(len(self._filtered)))
        self._changed()

    def _on_filter_key(self, event) -> None:
        # Down-arrow from the filter drops into the list without clearing it.
        if event.GetKeyCode() == wx.WXK_DOWN and self._filtered:
            self.list.SetFocus()
            if self.list.GetSelection() == wx.NOT_FOUND:
                self.list.SetSelection(0)  # so the screen reader announces a row
        else:
            event.Skip()

    def selected_model(self):
        i = self.list.GetSelection()
        return self._filtered[i] if 0 <= i < len(self._filtered) else None

    def focus_filter(self) -> None:
        self.filter.SetFocus()

    def _changed(self) -> None:
        if self._on_change:
            self._on_change()


class DownloadDialog(wx.Dialog):
    """Pick a serial port + a radio model to download from. The model list can
    show all radios or just the user's favorites (default: all, so the prior
    behavior is unchanged)."""

    def __init__(self, parent, list_ports_fn, models, *, describe_fn=None) -> None:
        super().__init__(parent, title="Download from radio")
        self._all_models = list(models)
        self._describe_fn = describe_fn

        outer = wx.BoxSizer(wx.VERTICAL)
        self.port = PortPicker(
            self, list_ports_fn, on_change=self._update_ok,
            preferred_port=get_config().get_last_serial_port(),
        )
        outer.Add(self.port, 0, wx.EXPAND | wx.ALL, 10)

        box = wx.StaticBoxSizer(wx.VERTICAL, self, "Radio model")
        show_row = wx.BoxSizer(wx.HORIZONTAL)
        show_row.Add(wx.StaticText(self, label="Show:"), 0,
                     wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 6)
        self.show_all = wx.RadioButton(self, label="All radios", style=wx.RB_GROUP)
        self.show_favs = wx.RadioButton(self, label="Favorites")
        show_row.Add(self.show_all, 0, wx.RIGHT, 12)
        show_row.Add(self.show_favs, 0)
        box.Add(show_row, 0, wx.ALL, 4)

        self.picker = ModelPicker(self, box, self._all_models,
                                  on_change=self._update_ok)
        if self._describe_fn is not None:
            self.details_btn = wx.Button(self, label="Radio details…")
            self.details_btn.Bind(wx.EVT_BUTTON, self._on_details)
            box.Add(self.details_btn, 0, wx.ALL, 4)
        outer.Add(box, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)

        buttons = self.CreateStdDialogButtonSizer(wx.OK | wx.CANCEL)
        self._ok = self.FindWindowById(wx.ID_OK)
        if self._ok:
            self._ok.SetLabel("Download")
        outer.Add(buttons, 0, wx.EXPAND | wx.ALL, 8)

        self.SetSizerAndFit(outer)
        self.show_all.Bind(wx.EVT_RADIOBUTTON, self._on_show_changed)
        self.show_favs.Bind(wx.EVT_RADIOBUTTON, self._on_show_changed)
        self.Bind(wx.EVT_BUTTON, self._on_ok, id=wx.ID_OK)
        # Land on the serial port first (tab order then flows port -> show
        # toggle -> filter -> list -> Download). Done from EVT_INIT_DIALOG via
        # CallAfter so it runs AFTER wx's own default focus placement (which
        # would otherwise clobber it, esp. on macOS).
        self.Bind(wx.EVT_INIT_DIALOG, self._on_init_dialog)
        self._update_ok()

    def _favorite_models(self) -> list:
        favs = set(get_config().favorites())
        return [m for m in self._all_models if m["id"] in favs]

    def _on_show_changed(self, _event) -> None:
        self.picker.set_models(
            self._favorite_models() if self.show_favs.GetValue() else self._all_models
        )
        self._update_ok()

    def _on_details(self, _event) -> None:
        show_model_details(self, self.picker.selected_model(), self._describe_fn)
        self.picker.list.SetFocus()  # return focus to the list

    def _on_init_dialog(self, event) -> None:
        event.Skip()  # let wx's default init (data transfer, focus) run first
        wx.CallAfter(self.port.focus)

    def _selected_model(self):
        return self.picker.selected_model()

    def _update_ok(self) -> None:
        # May be called by the PortPicker's on_change before this dialog has
        # finished building (picker/_ok not yet assigned) — no-op until ready.
        if not getattr(self, "_ok", None) or not hasattr(self, "picker"):
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
            self.picker.list.SetFocus()
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


class FavoritesDialog(wx.Dialog):
    """Manage the user's favorite radios: a dual-list "builder".

    Left: the full radio list with a filter and an "Add to favorites" button.
    Right: the current favorites with a "Remove from favorites" button. Curating
    here is separate from using a radio — the Download dialog's All/Favorites
    toggle is what browses them. Add/remove are announced (status line + prism)
    without moving focus, so you can star several radios in a row.
    """

    def __init__(self, parent, models, *, describe_fn=None) -> None:
        super().__init__(parent, title="Favorite radios")
        self._all_models = list(models)
        self._by_id = {m["id"]: m for m in self._all_models}
        self._fav_models: list = []
        self._describe_fn = describe_fn

        outer = wx.BoxSizer(wx.VERTICAL)
        cols = wx.BoxSizer(wx.HORIZONTAL)

        left = wx.StaticBoxSizer(wx.VERTICAL, self, "All radios")
        self.picker = ModelPicker(
            self, left, self._all_models, on_change=self._update_buttons,
            list_label="All radios",
        )
        btn_row = wx.BoxSizer(wx.HORIZONTAL)
        self.add_btn = wx.Button(self, label="Add to favorites")
        btn_row.Add(self.add_btn, 0, wx.RIGHT, 6)
        if self._describe_fn is not None:
            self.details_btn = wx.Button(self, label="Radio details…")
            self.details_btn.Bind(wx.EVT_BUTTON, self._on_details)
            btn_row.Add(self.details_btn, 0)
        left.Add(btn_row, 0, wx.ALL, 4)
        cols.Add(left, 1, wx.EXPAND | wx.ALL, 6)

        right = wx.StaticBoxSizer(wx.VERTICAL, self, "Your favorites")
        right.Add(wx.StaticText(self, label="Favorites:"), 0, wx.LEFT | wx.TOP, 4)
        self.fav_list = RadioListView(self, name="Your favorites",
                                      on_select=self._update_buttons)
        right.Add(self.fav_list, 1, wx.EXPAND | wx.ALL, 4)
        self.remove_btn = wx.Button(self, label="Remove from favorites")
        right.Add(self.remove_btn, 0, wx.ALL, 4)
        cols.Add(right, 1, wx.EXPAND | wx.ALL, 6)
        outer.Add(cols, 1, wx.EXPAND)

        self._status = wx.StaticText(self, label="")
        self._status.SetName("Favorites status")
        outer.Add(self._status, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)

        outer.Add(self.CreateButtonSizer(wx.CLOSE), 0, wx.EXPAND | wx.ALL, 8)
        self.SetSizerAndFit(outer)
        self.SetEscapeId(wx.ID_CLOSE)  # Escape closes (no Cancel button here)

        self.add_btn.Bind(wx.EVT_BUTTON, self._on_add)
        self.remove_btn.Bind(wx.EVT_BUTTON, self._on_remove)
        # fav_list selection -> _update_buttons via RadioListView's on_select.
        self.Bind(wx.EVT_BUTTON, lambda _e: self.EndModal(wx.ID_CLOSE), id=wx.ID_CLOSE)
        self.Bind(wx.EVT_INIT_DIALOG, self._on_init_dialog)
        self._refresh_favorites()

    def _on_init_dialog(self, event) -> None:
        event.Skip()
        wx.CallAfter(self.picker.focus_filter)

    def _refresh_favorites(self, select_id: str | None = None) -> None:
        """Rebuild the favorites list from config (dropping ids whose driver is
        no longer present, e.g. after a CHIRP update)."""
        self._fav_models = [
            self._by_id[d] for d in get_config().favorites() if d in self._by_id
        ]
        self.fav_list.Set([m["label"] for m in self._fav_models])
        if self._fav_models:
            idx = 0
            if select_id is not None:
                idx = next((i for i, m in enumerate(self._fav_models)
                            if m["id"] == select_id), 0)
            self.fav_list.SetSelection(min(idx, len(self._fav_models) - 1))
        self._update_buttons()

    def _on_details(self, _event) -> None:
        show_model_details(self, self.picker.selected_model(), self._describe_fn)
        self.picker.list.SetFocus()

    def _selected_favorite(self):
        i = self.fav_list.GetSelection()
        return self._fav_models[i] if 0 <= i < len(self._fav_models) else None

    def _update_buttons(self) -> None:
        # Add is live whenever a model is selected (it announces "already a
        # favorite" rather than going dead); Remove needs a selected favorite.
        if not hasattr(self, "remove_btn"):
            return
        self.add_btn.Enable(self.picker.selected_model() is not None)
        self.remove_btn.Enable(self._selected_favorite() is not None)

    def _announce(self, message: str) -> None:
        self._status.SetLabel(message)
        _speaker.speak(message)

    def _on_add(self, _event) -> None:
        m = self.picker.selected_model()
        if m is None:
            return
        if get_config().is_favorite(m["id"]):
            self._announce(f"{m['label']} is already a favorite.")
            return
        get_config().add_favorite(m["id"])
        self._refresh_favorites(select_id=m["id"])
        self._announce(
            f"Added {m['label']} to favorites. {len(self._fav_models)} total."
        )

    def _on_remove(self, _event) -> None:
        i = self.fav_list.GetSelection()
        m = self._selected_favorite()
        if m is None:
            return
        get_config().remove_favorite(m["id"])
        self._refresh_favorites()
        remaining = len(self._fav_models)
        if remaining:  # keep focus in the favorites list, on the next item
            self.fav_list.SetSelection(min(i, remaining - 1))
            self.fav_list.SetFocus()
        else:
            self.picker.list.SetFocus()
        self._update_buttons()
        self._announce(
            f"Removed {m['label']} from favorites. {remaining} total."
        )


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
