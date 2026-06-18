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
            ctrl = self._make_control(col, current)

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

    def _make_control(self, col, current: str):
        if col.input_type == "select":
            ctrl = wx.Choice(self, choices=list(col.choices))
            self._select_choice(ctrl, list(col.choices), current)
            return ctrl
        ctrl = wx.TextCtrl(self, value=current)
        return ctrl

    @staticmethod
    def _select_choice(ctrl: "wx.Choice", choices: list[str], current: str) -> None:
        if ctrl.SetStringSelection(current):
            return
        # Tolerant numeric match (e.g. DTCS "23" vs choice "023").
        cur = current.strip().lstrip("0")
        if cur:
            for i, choice in enumerate(choices):
                if choice.strip().lstrip("0") == cur:
                    ctrl.SetSelection(i)
                    return
        if choices:
            ctrl.SetSelection(0)

    def get_values(self) -> dict:
        """Return {field: value_str} for every enabled, editable control."""
        values: dict[str, str] = {}
        for field, (ctrl, _col) in self._controls.items():
            if not ctrl.IsEnabled():
                continue
            if isinstance(ctrl, wx.Choice):
                values[field] = ctrl.GetStringSelection()
            else:
                values[field] = ctrl.GetValue()
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
