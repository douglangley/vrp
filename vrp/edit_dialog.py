"""Native wx dialog for editing one memory channel.

Why a native dialog instead of editing in the HTML grid: with large radios
(thousands of channels) putting controls in the grid forces the screen reader
to re-read the whole table on every interaction. A native ``wx.Dialog`` is a
separate top-level window with first-class keyboard/screen-reader support, so
the big channel table stays a fast, read-only HTML table and only the edited
row is refreshed afterward. (Accessibility-lead approved model.)

Fields are built from the same ``build_column_defs`` the table uses, so the
dialog never shows a field the radio doesn't support. Immutable fields are
shown but disabled (and labeled "(read only)") to keep a stable tab order;
empty channels expose only Frequency until the slot is populated. On OK the
values are validated via ``memory_ops.validate_channel_values`` — on failure
the dialog stays open, speaks the reason, and focuses the offending control.
"""

from __future__ import annotations

import wx

from chirp_backend.col_defs import build_column_defs


def _select_choice(ctrl: "wx.Choice", choices: list[str], current: str) -> None:
    """Select ``current`` in a wx.Choice, tolerating numeric formatting
    differences (e.g. DTCS "23" vs the choice "023")."""
    if ctrl.SetStringSelection(current):
        return
    cur = current.strip().lstrip("0")
    if cur:
        for i, choice in enumerate(choices):
            if choice.strip().lstrip("0") == cur:
                ctrl.SetSelection(i)
                return
    if choices:
        ctrl.SetSelection(0)


def make_field_control(parent: wx.Window, col, current: str):
    """Build the right native control for a column: a wx.Choice for ``select``
    columns (pre-selected to ``current``), else a wx.TextCtrl."""
    if col.input_type == "select":
        ctrl = wx.Choice(parent, choices=list(col.choices))
        _select_choice(ctrl, list(col.choices), current)
        return ctrl
    return wx.TextCtrl(parent, value=current)


def control_value(ctrl) -> str:
    """Read the current string value from a field control (Choice or TextCtrl)."""
    if isinstance(ctrl, wx.Choice):
        return ctrl.GetStringSelection()
    return ctrl.GetValue()


class EditChannelDialog(wx.Dialog):
    """Modal editor for a single channel's fields."""

    def __init__(self, parent, number: int, mem, features) -> None:
        empty = bool(getattr(mem, "empty", False))
        title = f"Edit channel {number}" + (" (empty)" if empty else "")
        super().__init__(parent, title=title)

        self._number = number
        self._controls: dict[str, tuple] = {}  # field -> (ctrl, col)
        immutable = mem.immutable or []
        cols = [c for c in build_column_defs(features) if c.name != "number"]

        outer = wx.BoxSizer(wx.VERTICAL)
        grid = wx.FlexGridSizer(cols=2, vgap=6, hgap=8)
        grid.AddGrowableCol(1, 1)

        for col in cols:
            is_immutable = col.name in immutable
            # Empty channels expose ALL fields so a new channel can be fully
            # defined in one pass; only immutable fields stay disabled.
            disabled = is_immutable
            current = col.format_value(mem)  # blank for an empty channel's freq

            label = wx.StaticText(self, label=col.label + ":")
            ctrl = make_field_control(self, col, current)

            name = col.label
            if is_immutable:
                name += " (read only)"
            elif empty and col.name == "freq":
                # Programmatic hint (rule #7: words, not a symbol-only marker).
                name += " (required to activate this channel; leave blank to keep it empty)"
            ctrl.SetName(name)  # NVDA reads control name + role + value
            if disabled:
                ctrl.Disable()

            grid.Add(label, 0, wx.ALIGN_CENTER_VERTICAL)
            grid.Add(ctrl, 0, wx.EXPAND)
            self._controls[col.name] = (ctrl, col)

        outer.Add(grid, 1, wx.EXPAND | wx.ALL, 12)

        # Visual error line (the reason is also spoken via a message box on OK).
        self._status = wx.StaticText(self, label="")
        outer.Add(self._status, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 12)

        buttons = self.CreateStdDialogButtonSizer(wx.OK | wx.CANCEL)
        outer.Add(buttons, 0, wx.EXPAND | wx.ALL, 8)

        self.SetSizerAndFit(outer)
        self.Bind(wx.EVT_BUTTON, self._on_ok, id=wx.ID_OK)

        # Focus the first editable control on open.
        for field, (ctrl, _col) in self._controls.items():
            if ctrl.IsEnabled():
                ctrl.SetFocus()
                break

    def get_values(self) -> dict:
        """Return {field: value_str} for every enabled, editable control."""
        values: dict[str, str] = {}
        for field, (ctrl, _col) in self._controls.items():
            if not ctrl.IsEnabled():
                continue
            values[field] = control_value(ctrl)
        return values

    def _on_ok(self, event: wx.CommandEvent) -> None:
        from chirp_backend import memory_ops

        ok, message, bad_field = memory_ops.validate_channel_values(
            self._number, self.get_values()
        )
        if ok:
            event.Skip()  # let the dialog close with wx.ID_OK
            return
        # Keep the dialog open: show the reason, speak it, focus the bad field.
        self._status.SetLabel(message)
        wx.MessageBox(message, "Invalid value", wx.OK | wx.ICON_ERROR, self)
        if bad_field and bad_field in self._controls:
            self._controls[bad_field][0].SetFocus()


class EditCellDialog(wx.Dialog):
    """Modal editor for a single column of one channel (the grid's F2 / "edit
    this cell" action).

    Same control types and validation path as :class:`EditChannelDialog`, but
    one field only — the fastest way to change a single value. On OK the value is
    validated via ``memory_ops.validate_channel_values``; on failure the dialog
    stays open, speaks the reason, and re-focuses the field. The caller applies
    the value (``update_channel``) and refreshes the row.
    """

    def __init__(self, parent, number: int, mem, col) -> None:
        super().__init__(parent, title=f"Edit {col.label} (channel {number})")
        self._number = number
        self._col = col

        outer = wx.BoxSizer(wx.VERTICAL)
        row = wx.BoxSizer(wx.HORIZONTAL)
        row.Add(wx.StaticText(self, label=col.label + ":"), 0,
                wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 8)
        self._ctrl = make_field_control(self, col, col.format_value(mem))
        self._ctrl.SetName(col.label)  # NVDA reads control name + role + value
        row.Add(self._ctrl, 1, wx.EXPAND)
        outer.Add(row, 0, wx.EXPAND | wx.ALL, 12)

        self._status = wx.StaticText(self, label="")
        outer.Add(self._status, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 12)

        outer.Add(self.CreateStdDialogButtonSizer(wx.OK | wx.CANCEL), 0,
                  wx.EXPAND | wx.ALL, 8)
        self.SetSizerAndFit(outer)
        self.Bind(wx.EVT_BUTTON, self._on_ok, id=wx.ID_OK)
        self._ctrl.SetFocus()

    def get_value(self) -> str:
        return control_value(self._ctrl)

    def _on_ok(self, event: wx.CommandEvent) -> None:
        from chirp_backend import memory_ops

        ok, message, _bad = memory_ops.validate_channel_values(
            self._number, {self._col.name: self.get_value()}
        )
        if ok:
            event.Skip()
            return
        self._status.SetLabel(message)
        wx.MessageBox(message, "Invalid value", wx.OK | wx.ICON_ERROR, self)
        self._ctrl.SetFocus()
