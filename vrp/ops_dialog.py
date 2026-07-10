"""Native wx dialog for bulk channel operations (Phase 3).

One dialog gathers BOTH the channel selection and the operation, so the user
isn't faced with nine scattered buttons or a different dialog per op. Selection
is a contiguous From/To range by default, with an optional advanced field that
accepts a channel list like ``1-5,8,10-12`` (parsed by
``memory_ops.parse_channel_spec``). The operation is chosen from a radio list;
only the parameters the chosen operation needs are shown (and focused).

Native wx = first-class keyboard/NVDA support, focus trap, and Escape-to-cancel
for free — the same reason single-channel editing uses a native dialog. On OK
the selection is validated; on failure the dialog stays open, speaks the reason,
and focuses the offending field.
"""

from __future__ import annotations

import wx

from chirp_backend import memory_ops

# (key, label) — order shown in the Operation radio list.
OPERATIONS = [
    ("delete", "Delete (clear contents)"),
    ("delete_shift", "Delete and shift up"),
    ("insert", "Insert blank channel"),
    ("move_up", "Move up by one"),
    ("move_down", "Move down by one"),
    ("move_to", "Move to…"),
    ("copy_to", "Copy to…"),
    ("sort", "Sort…"),
    ("arrange", "Arrange (compact, remove empty)"),
    ("export_csv", "Export to CSV…"),
]


class ChannelOperationsDialog(wx.Dialog):
    """Pick a channel selection + an operation to apply to it."""

    def __init__(self, parent, low: int, high: int, default_from: int, columns) -> None:
        super().__init__(parent, title="Bulk operations")
        self._low = low
        self._high = high
        self._columns = list(columns)  # [(name, label), ...] for sort

        outer = wx.BoxSizer(wx.VERTICAL)

        # -- selection ----------------------------------------------------
        sel = wx.StaticBoxSizer(wx.VERTICAL, self, "Channels")
        rng = wx.FlexGridSizer(cols=2, vgap=6, hgap=8)
        self.from_ctrl = wx.SpinCtrl(self, min=low, max=high, initial=default_from)
        self.to_ctrl = wx.SpinCtrl(self, min=low, max=high, initial=default_from)
        self.from_ctrl.SetName("From channel")
        self.to_ctrl.SetName("To channel")
        rng.Add(wx.StaticText(self, label="From channel:"), 0, wx.ALIGN_CENTER_VERTICAL)
        rng.Add(self.from_ctrl)
        rng.Add(wx.StaticText(self, label="To channel:"), 0, wx.ALIGN_CENTER_VERTICAL)
        rng.Add(self.to_ctrl)
        sel.Add(rng, 0, wx.ALL, 4)

        adv_label = wx.StaticText(
            self, label="Advanced channel list (optional, e.g. 1-5,8,10-12):"
        )
        self.adv_ctrl = wx.TextCtrl(self)
        self.adv_ctrl.SetName("Advanced channel list")
        sel.Add(adv_label, 0, wx.LEFT | wx.TOP, 4)
        sel.Add(self.adv_ctrl, 0, wx.EXPAND | wx.ALL, 4)

        self.summary = wx.StaticText(self, label="")
        self.summary.SetName("Selection summary")
        sel.Add(self.summary, 0, wx.ALL, 4)
        outer.Add(sel, 0, wx.EXPAND | wx.ALL, 10)

        # -- operation ----------------------------------------------------
        self.op_box = wx.RadioBox(
            self,
            label="Operation",
            choices=[label for _key, label in OPERATIONS],
            majorDimension=1,
            style=wx.RA_SPECIFY_COLS,
        )
        outer.Add(self.op_box, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)

        # -- contextual parameters ---------------------------------------
        self._params = wx.StaticBoxSizer(wx.VERTICAL, self, "Options")
        self.mode_box = wx.RadioBox(
            self,
            label="Shift mode",
            choices=["Shift all channels up", "Shift within the block only"],
            majorDimension=1,
            style=wx.RA_SPECIFY_COLS,
        )
        self.dest_label = wx.StaticText(self, label="Destination channel:")
        self.dest_ctrl = wx.SpinCtrl(self, min=low, max=high, initial=default_from)
        self.dest_ctrl.SetName("Destination channel")
        self.sort_label = wx.StaticText(self, label="Sort by column:")
        self.sort_col = wx.Choice(self, choices=[label for _n, label in self._columns])
        self.sort_col.SetName("Sort by column")
        if self.sort_col.GetCount():
            self.sort_col.SetSelection(0)
        self.sort_order = wx.RadioBox(
            self,
            label="Order",
            choices=["Ascending", "Descending"],
            majorDimension=1,
            style=wx.RA_SPECIFY_COLS,
        )
        for ctrl in (self.mode_box, self.dest_label, self.dest_ctrl,
                     self.sort_label, self.sort_col, self.sort_order):
            self._params.Add(ctrl, 0, wx.ALL, 4)
        outer.Add(self._params, 0, wx.EXPAND | wx.ALL, 10)

        outer.Add(
            self.CreateStdDialogButtonSizer(wx.OK | wx.CANCEL), 0, wx.EXPAND | wx.ALL, 8
        )
        self.SetSizer(outer)

        # events
        for ctrl in (self.from_ctrl, self.to_ctrl):
            ctrl.Bind(wx.EVT_SPINCTRL, self._on_change)
        self.adv_ctrl.Bind(wx.EVT_TEXT, self._on_change)
        self.op_box.Bind(wx.EVT_RADIOBOX, lambda _e: self._sync_params())
        self.Bind(wx.EVT_BUTTON, self._on_ok, id=wx.ID_OK)

        self._sync_params()
        self._update_summary()
        self.Fit()
        self.from_ctrl.SetFocus()

    # -- selection helpers -------------------------------------------------

    def selected_numbers(self):
        """Return (numbers, error). Advanced list wins when non-empty."""
        spec = self.adv_ctrl.GetValue().strip()
        if spec:
            return memory_ops.parse_channel_spec(spec, self._low, self._high)
        a, b = self.from_ctrl.GetValue(), self.to_ctrl.GetValue()
        if a > b:
            a, b = b, a
        return list(range(a, b + 1)), None

    def get_operation(self) -> dict:
        key = OPERATIONS[self.op_box.GetSelection()][0]
        info: dict = {"op": key}
        if key == "delete_shift":
            info["mode"] = "all" if self.mode_box.GetSelection() == 0 else "block"
        elif key in ("move_to", "copy_to"):
            info["dest"] = self.dest_ctrl.GetValue()
        elif key == "sort":
            idx = self.sort_col.GetSelection()
            info["attr"] = self._columns[idx][0] if idx >= 0 else "freq"
            info["reverse"] = self.sort_order.GetSelection() == 1
        return info

    # -- dynamic UI --------------------------------------------------------

    def _sync_params(self) -> None:
        key = OPERATIONS[self.op_box.GetSelection()][0]
        self.mode_box.Show(key == "delete_shift")
        show_dest = key in ("move_to", "copy_to")
        self.dest_label.Show(show_dest)
        self.dest_ctrl.Show(show_dest)
        show_sort = key == "sort"
        self.sort_label.Show(show_sort)
        self.sort_col.Show(show_sort)
        self.sort_order.Show(show_sort)
        self.Layout()
        self.Fit()

    def _on_change(self, _event) -> None:
        self._update_summary()

    def _update_summary(self) -> None:
        numbers, error = self.selected_numbers()
        if error:
            self.summary.SetLabel(error)
        elif numbers:
            self.summary.SetLabel(
                f"Will affect {len(numbers)} channel(s): {numbers[0]} to {numbers[-1]}."
            )
        else:
            self.summary.SetLabel("No channels selected.")

    def _on_ok(self, event: wx.CommandEvent) -> None:
        numbers, error = self.selected_numbers()
        if error or not numbers:
            message = error or "Select at least one channel."
            self.summary.SetLabel(message)
            wx.MessageBox(message, "Invalid selection", wx.OK | wx.ICON_ERROR, self)
            (self.adv_ctrl if self.adv_ctrl.GetValue().strip() else self.from_ctrl).SetFocus()
            return
        event.Skip()  # valid → close with wx.ID_OK
