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

    Accessibility: every control has a preceding label and a matching SetName so
    NVDA/VoiceOver announce it; the state selector is disabled (not hidden) for
    countries queried whole, so its state is still discoverable; the dialog is a
    real modal wx.Dialog with an Escape-able Cancel button.
    """

    def __init__(self, parent) -> None:
        super().__init__(parent, title="Query RepeaterBook")
        from chirp_backend import repeaterbook

        self._rb = repeaterbook
        outer = wx.BoxSizer(wx.VERTICAL)

        intro = wx.StaticText(
            self,
            label="Search the RepeaterBook directory. Results import into the "
            "open radio.",
        )
        outer.Add(intro, 0, wx.ALL, 10)

        grid = wx.FlexGridSizer(cols=2, vgap=8, hgap=8)
        grid.AddGrowableCol(1, 1)

        def _row(label_text: str, control: wx.Window, name: str) -> None:
            label = wx.StaticText(self, label=label_text)
            control.SetName(name)
            grid.Add(label, 0, wx.ALIGN_CENTER_VERTICAL)
            grid.Add(control, 0, wx.EXPAND)

        countries = repeaterbook.countries()
        self.country = wx.Choice(self, choices=countries)
        default = countries.index("United States") if "United States" in countries else 0
        self.country.SetSelection(default)
        self.country.Bind(wx.EVT_CHOICE, self._on_country)
        _row("&Country:", self.country, "Country")

        self.state = wx.Choice(self, choices=[])
        _row("&State or province:", self.state, "State or province")

        self.filter = wx.TextCtrl(self)
        _row("&Search (city, callsign, county):", self.filter, "Search text")

        self.modes = wx.CheckListBox(self, choices=repeaterbook.modes())
        _row("&Modes (leave all clear for any):", self.modes, "Modes")

        outer.Add(grid, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)

        self.open_only = wx.CheckBox(self, label="&Open repeaters only")
        self.open_only.SetName("Open repeaters only")
        outer.Add(self.open_only, 0, wx.ALL, 10)

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
