"""Native wx dialogs for online query import.

- ImportDestinationDialog chooses the destination channel for a block of
  imported memories and how to treat occupied channels; the import itself goes
  through memory_ops.import_memories. Shared by "Import from File" and the
  query sources.
- RepeaterBookQueryDialog gathers the RepeaterBook query parameters
  (country/state + optional filters); the fetch runs on a background thread in
  main_window and its results flow through ImportDestinationDialog too.

The plural module name earns its keep again with RepeaterBook back (see
PROGRESS_LOG). Don't "tidy" it to import_dialog.py.
"""

from __future__ import annotations

import wx


class ImportDestinationDialog(wx.Dialog):
    def __init__(self, parent, count: int, low: int, high: int, default_dest: int) -> None:
        super().__init__(parent, title="Import channels")
        outer = wx.BoxSizer(wx.VERTICAL)
        outer.Add(
            wx.StaticText(self, label=f"{count} result(s) ready to import."),
            0, wx.ALL, 10,
        )

        row = wx.BoxSizer(wx.HORIZONTAL)
        row.Add(wx.StaticText(self, label="Start at channel:"), 0,
                wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 6)
        self.dest = wx.SpinCtrl(self, min=low, max=high, initial=default_dest)
        self.dest.SetName("Start at channel")
        row.Add(self.dest)
        outer.Add(row, 0, wx.ALL, 10)

        self.mode = wx.RadioBox(
            self, label="If a destination channel already has data",
            choices=["Overwrite it", "Skip it"],
            majorDimension=1, style=wx.RA_SPECIFY_COLS,
        )
        outer.Add(self.mode, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)

        buttons = self.CreateStdDialogButtonSizer(wx.OK | wx.CANCEL)
        ok = self.FindWindowById(wx.ID_OK)
        if ok:
            ok.SetLabel("Import")
        outer.Add(buttons, 0, wx.EXPAND | wx.ALL, 8)
        self.SetSizerAndFit(outer)

    def get_destination(self) -> int:
        return self.dest.GetValue()

    def get_overwrite(self) -> bool:
        return self.mode.GetSelection() == 0


class RepeaterBookQueryDialog(wx.Dialog):
    """Gather RepeaterBook query parameters (country/state + optional filters).

    Accessibility: each field's StaticText label is created immediately BEFORE
    its control — on Windows wxMSW takes a native control's accessible name from
    the static text created just before it, so control-before-label ordering
    reads every field off by one (see __init__). The state selector is disabled
    (not hidden) for countries queried whole, so its state is still
    discoverable; the dialog is a real modal wx.Dialog with an Escape-able
    Cancel button.
    """

    def __init__(self, parent, initial: dict | None = None) -> None:
        super().__init__(parent, title="Query RepeaterBook")
        from chirp_backend import repeaterbook

        self._rb = repeaterbook
        outer = wx.BoxSizer(wx.VERTICAL)

        # LABEL BEFORE CONTROL — this ordering is load-bearing for screen
        # readers on Windows. wxMSW gives a native control its accessible name
        # from the static-text sibling created immediately *before* it; SetName
        # does not propagate to MSAA for these controls. If the control is
        # created before its label (e.g. a helper that takes an already-built
        # control), every field inherits the *previous* field's label — the
        # classic "off by one" read. So each _label(...) MUST run before the
        # wx control it describes is constructed. (PreferencesDialog works for
        # exactly this reason; SetName is kept only for macOS/VoiceOver, where
        # it does map to NSAccessibility.)
        grid = wx.FlexGridSizer(cols=2, vgap=8, hgap=10)

        def _label(text: str) -> None:
            grid.Add(wx.StaticText(self, label=text), 0, wx.ALIGN_CENTER_VERTICAL)

        _label("Country:")
        countries = repeaterbook.countries()
        self.country = wx.Choice(self, choices=countries)
        default = countries.index("United States") if "United States" in countries else 0
        self.country.SetSelection(default)
        self.country.SetName("Country")
        self.country.Bind(wx.EVT_CHOICE, self._on_country)
        grid.Add(self.country)

        _label("State or province:")
        self.state = wx.Choice(self, choices=[])
        self.state.SetName("State or province")
        grid.Add(self.state)

        _label("Search (city, callsign, county):")
        self.filter = wx.TextCtrl(self, size=(220, -1))
        self.filter.SetName("Search text, city callsign or county")
        grid.Add(self.filter)

        _label("Modes (leave all clear for any):")
        self.modes = wx.CheckListBox(self, choices=repeaterbook.modes())
        self.modes.SetName("Modes, leave all clear for any")
        grid.Add(self.modes)

        outer.Add(grid, 0, wx.ALL, 12)

        # Bands: real native checkboxes (one per band, RT Systems style). Each
        # self-labels, so it reads reliably under NVDA regardless of position
        # (unlike a checkbox list). Grouped in a StaticBox for an accessible
        # group name. Leaving all clear means "any band".
        band_box = wx.StaticBoxSizer(
            wx.VERTICAL, self, "Bands (leave all clear for any)"
        )
        band_grid = wx.FlexGridSizer(cols=2, vgap=2, hgap=16)
        self._band_boxes: dict[str, wx.CheckBox] = {}
        for name, lo, hi in repeaterbook.bands():
            # "to" (not an en-dash) so screen readers speak the range cleanly.
            label = f"{name} ({lo / 1e6:g} to {hi / 1e6:g} MHz)"
            cb = wx.CheckBox(self, label=label)
            cb.SetName(label)
            self._band_boxes[name] = cb
            band_grid.Add(cb)
        band_box.Add(band_grid, 0, wx.ALL, 4)
        outer.Add(band_box, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 12)

        self.open_only = wx.CheckBox(self, label="Open repeaters only")
        self.open_only.SetName("Open repeaters only")
        outer.Add(self.open_only, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 12)

        buttons = self.CreateStdDialogButtonSizer(wx.OK | wx.CANCEL)
        ok = self.FindWindowById(wx.ID_OK)
        if ok:
            ok.SetLabel("Query")
        outer.Add(buttons, 0, wx.EXPAND | wx.ALL, 8)

        self.SetSizerAndFit(outer)
        self.SetEscapeId(wx.ID_CANCEL)
        self._populate_states()
        if initial:
            self._apply_initial(initial)
        self.country.SetFocus()

    def _on_country(self, _evt=None) -> None:
        self._populate_states()

    def _apply_initial(self, form: dict) -> None:
        """Pre-fill the form from a previous search (used by results ▸ Back)."""
        ci = self.country.FindString(form.get("country", ""))
        if ci != wx.NOT_FOUND:
            self.country.SetSelection(ci)
        self._populate_states()
        state = form.get("state", "")
        if state and self.state.IsEnabled():
            si = self.state.FindString(state)
            if si != wx.NOT_FOUND:
                self.state.SetSelection(si)
        self.filter.SetValue(form.get("filter", ""))
        self.open_only.SetValue(bool(form.get("open_only", False)))
        want = set(form.get("modes", []))
        for i in range(self.modes.GetCount()):
            self.modes.Check(i, self.modes.GetString(i) in want)
        want_bands = set(form.get("bands", []))
        for name, cb in self._band_boxes.items():
            cb.SetValue(name in want_bands)

    def _populate_states(self) -> None:
        """Fill the state selector for the chosen country, or disable it.

        US/Canada/Mexico are queried per-state; every other country is fetched
        whole, so the state control is disabled (state becomes 'all')."""
        country = self.country.GetStringSelection()
        states = self._rb.states(country)
        self.state.Clear()
        if states:
            self.state.Append(states)
            self.state.SetSelection(0)
            self.state.Enable(True)
        else:
            self.state.Enable(False)

    def _selected_bands(self) -> list[str]:
        return [name for name, cb in self._band_boxes.items() if cb.GetValue()]

    def get_form(self) -> dict:
        """Raw form values, for remembering and re-populating (results ▸ Back)."""
        return {
            "country": self.country.GetStringSelection(),
            "state": self.state.GetStringSelection() if self.state.IsEnabled() else "",
            "filter": self.filter.GetValue().strip(),
            "open_only": self.open_only.GetValue(),
            "modes": [
                self.modes.GetString(i)
                for i in range(self.modes.GetCount())
                if self.modes.IsChecked(i)
            ],
            "bands": self._selected_bands(),
        }

    def get_params(self) -> dict:
        country = self.country.GetStringSelection()
        state = self.state.GetStringSelection() if self.state.IsEnabled() else ""
        modes = [
            self.modes.GetString(i)
            for i in range(self.modes.GetCount())
            if self.modes.IsChecked(i)
        ]
        return self._rb.build_params(
            country,
            state,
            filter_text=self.filter.GetValue().strip(),
            open_only=self.open_only.GetValue(),
            modes=modes,
            bands=self._rb.band_ranges(self._selected_bands()),
        )


class FrequencyListDialog(wx.Dialog):
    """Choose one of CHIRP's stock frequency lists to import.

    A filter box + a type-ahead ``RadioListView`` (native SysListView32 on
    Windows for NVDA, NSTableView/GtkTreeView elsewhere) + an optional Details
    button that shows the list's channels in the read-only ``InfoDialog``. The
    import itself (start channel, overwrite/skip) is the shared
    ``ImportDestinationDialog``, run by the caller after this returns.

    Accessibility: each control's StaticText label is created immediately BEFORE
    the control (wxMSW names a native control from the preceding static text; see
    RepeaterBookQueryDialog). Real modal, Escape = Cancel, focus opens on the
    filter, Down-arrow from the filter drops into the list. ``get_selection``
    returns the chosen ``(display_name, path)`` or ``None``.
    """

    def __init__(self, parent, configs, *, describe_fn=None) -> None:
        super().__init__(
            parent, title="Import from frequency list",
            style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER,
        )
        from vrp.serial_dialogs import RadioListView

        self._configs = list(configs)  # [(display_name, path), …]
        self._filtered = list(self._configs)
        self._describe_fn = describe_fn
        outer = wx.BoxSizer(wx.VERTICAL)

        # LABEL BEFORE CONTROL — load-bearing for the screen-reader name on
        # Windows (see RepeaterBookQueryDialog for the full rationale).
        outer.Add(wx.StaticText(self, label="Filter:"), 0, wx.LEFT | wx.TOP, 8)
        self.filter = wx.TextCtrl(self)
        self.filter.SetName("Frequency list filter")
        outer.Add(self.filter, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 8)

        outer.Add(
            wx.StaticText(self, label="Frequency list:"), 0, wx.LEFT | wx.TOP, 8
        )
        self.list = RadioListView(
            self, name="Frequency list", on_select=self._changed, size=(360, 240)
        )
        self.list.Set([name for name, _ in self._filtered])
        outer.Add(self.list, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 8)

        self.count = wx.StaticText(self, label=self._count_label(len(self._filtered)))
        self.count.SetName("Frequency list count")
        outer.Add(self.count, 0, wx.ALL, 8)

        # Bottom row: [Details…] .... [Import] [Cancel].
        bottom = wx.BoxSizer(wx.HORIZONTAL)
        if self._describe_fn is not None:
            self.details_btn = wx.Button(self, label="&Details…")
            self.details_btn.Bind(wx.EVT_BUTTON, self._on_details)
            bottom.Add(self.details_btn, 0, wx.ALIGN_CENTER_VERTICAL)
        bottom.AddStretchSpacer()
        std = self.CreateStdDialogButtonSizer(wx.OK | wx.CANCEL)
        ok = self.FindWindowById(wx.ID_OK)
        if ok:
            ok.SetLabel("Import")
        bottom.Add(std, 0, wx.ALIGN_CENTER_VERTICAL)
        outer.Add(bottom, 0, wx.EXPAND | wx.ALL, 8)

        self.SetSizerAndFit(outer)
        self.SetEscapeId(wx.ID_CANCEL)

        self.filter.Bind(wx.EVT_TEXT, lambda _e: self._apply_filter())
        self.filter.Bind(wx.EVT_KEY_DOWN, self._on_filter_key)
        self._update_ok()
        self.filter.SetFocus()

    @staticmethod
    def _count_label(n: int) -> str:
        return "1 list matches" if n == 1 else f"{n} lists match"

    def _apply_filter(self) -> None:
        text = self.filter.GetValue().strip().lower()
        self._filtered = [
            c for c in self._configs if text in c[0].lower()
        ] if text else list(self._configs)
        self.list.Set([name for name, _ in self._filtered])  # selects row 0
        self.count.SetLabel(self._count_label(len(self._filtered)))
        self._update_ok()

    def _on_filter_key(self, event) -> None:
        # Down-arrow from the filter drops into the list without clearing it.
        if event.GetKeyCode() == wx.WXK_DOWN and self._filtered:
            self.list.SetFocus()
            if self.list.GetSelection() == wx.NOT_FOUND:
                self.list.SetSelection(0)
        else:
            event.Skip()

    def _changed(self) -> None:
        self._update_ok()

    def _update_ok(self) -> None:
        ok = self.FindWindowById(wx.ID_OK)
        if ok:
            ok.Enable(bool(self._filtered))

    def get_selection(self):
        """The chosen ``(display_name, path)``, or ``None``."""
        i = self.list.GetSelection()
        return self._filtered[i] if 0 <= i < len(self._filtered) else None

    def _on_details(self, _evt=None) -> None:
        from vrp.info_dialog import InfoDialog

        sel = self.get_selection()
        if sel is None or self._describe_fn is None:
            return
        name, path = sel
        text = self._describe_fn(path) or "No information is available."
        dlg = InfoDialog(self, f"Frequency list — {name}", text,
                         name="Frequency list details")
        dlg.ShowModal()
        dlg.Destroy()
        self.list.SetFocus()


class RepeaterBookResultsDialog(wx.Dialog):
    """Pick which fetched repeaters to import.

    A multi-select wx.ListBox (LB_MULTIPLE): arrow through the results, Space
    toggles each row in/out of the import (NVDA/VoiceOver announce the row text
    and its selected state), with Select all / Unselect all buttons. All rows
    start selected — the common case is "import the lot, drop a few". Chosen
    over a checkbox list (wx.CheckListBox), whose per-item checkboxes read
    unreliably under NVDA.

    Accessibility: the list's StaticText label is created immediately before it
    (wxMSW names the control from the preceding static text — see
    RepeaterBookQueryDialog); a real modal, Escape = Cancel. get_selected_numbers
    returns the source channel numbers still checked.
    """

    def __init__(self, parent, lines: list[tuple[int, str]]) -> None:
        super().__init__(
            parent, title="RepeaterBook results",
            style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER,
        )
        from vrp.speech import get_speaker

        self._speaker = get_speaker()
        self._numbers = [n for n, _ in lines]
        outer = wx.BoxSizer(wx.VERTICAL)

        # Label BEFORE the list (load-bearing for the screen-reader name).
        outer.Add(
            wx.StaticText(
                self,
                label="Repeaters found. Arrow through the list and press Space "
                "to include or exclude each one.",
            ),
            0, wx.ALL, 10,
        )
        self.listbox = wx.ListBox(
            self, choices=[text for _, text in lines],
            style=wx.LB_MULTIPLE | wx.LB_NEEDED_SB, size=(460, 240),
        )
        self.listbox.SetName("Repeaters found, Space toggles import")
        for i in range(self.listbox.GetCount()):
            self.listbox.SetSelection(i)  # default: all included
        self.listbox.Bind(wx.EVT_LISTBOX, lambda _e: self._update_count())
        outer.Add(self.listbox, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)

        self.count_label = wx.StaticText(self, label="")
        outer.Add(self.count_label, 0, wx.ALL, 10)

        btnrow = wx.BoxSizer(wx.HORIZONTAL)
        sel_all = wx.Button(self, label="Select &all")
        sel_none = wx.Button(self, label="&Unselect all")
        sel_all.Bind(wx.EVT_BUTTON, self._on_select_all)
        sel_none.Bind(wx.EVT_BUTTON, self._on_unselect_all)
        btnrow.Add(sel_all, 0, wx.RIGHT, 8)
        btnrow.Add(sel_none, 0)
        outer.Add(btnrow, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)

        # Bottom row: [Back to search] .... [Import selected] [Cancel]. Back ends
        # the modal with wx.ID_BACKWARD so the caller can re-open the query
        # dialog (prefilled) to refine the search instead of starting over.
        bottom = wx.BoxSizer(wx.HORIZONTAL)
        back = wx.Button(self, wx.ID_BACKWARD, "&Back to search")
        back.Bind(wx.EVT_BUTTON, lambda _e: self.EndModal(wx.ID_BACKWARD))
        bottom.Add(back, 0, wx.ALIGN_CENTER_VERTICAL)
        bottom.AddStretchSpacer()
        std = self.CreateStdDialogButtonSizer(wx.OK | wx.CANCEL)
        ok = self.FindWindowById(wx.ID_OK)
        if ok:
            ok.SetLabel("Import selected")
        bottom.Add(std, 0, wx.ALIGN_CENTER_VERTICAL)
        outer.Add(bottom, 0, wx.EXPAND | wx.ALL, 8)

        self.SetSizerAndFit(outer)
        self.SetEscapeId(wx.ID_CANCEL)
        self._update_count()
        self.listbox.SetFocus()

    def _update_count(self) -> None:
        sel = len(self.listbox.GetSelections())
        total = self.listbox.GetCount()
        self.count_label.SetLabel(f"{sel} of {total} selected")

    def _set_all(self, selected: bool) -> None:
        for i in range(self.listbox.GetCount()):
            if selected:
                self.listbox.SetSelection(i)
            else:
                self.listbox.Deselect(i)
        self._update_count()
        # Speak the outcome: the static count label alone isn't auto-announced,
        # and focus stays on the button. Supplemental speech, no-op without prism.
        total = self.listbox.GetCount()
        self._speaker.speak(
            f"All {total} selected" if selected else "All cleared", interrupt=True
        )

    def _on_select_all(self, _evt=None) -> None:
        self._set_all(True)

    def _on_unselect_all(self, _evt=None) -> None:
        self._set_all(False)

    def get_selected_numbers(self) -> list[int]:
        return [self._numbers[i] for i in self.listbox.GetSelections()]
