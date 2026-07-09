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

    def __init__(self, parent) -> None:
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
        self.country.SetFocus()

    def _on_country(self, _evt=None) -> None:
        self._populate_states()

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
        )


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

        buttons = self.CreateStdDialogButtonSizer(wx.OK | wx.CANCEL)
        ok = self.FindWindowById(wx.ID_OK)
        if ok:
            ok.SetLabel("Import selected")
        outer.Add(buttons, 0, wx.EXPAND | wx.ALL, 8)

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
