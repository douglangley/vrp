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
from vrp.speech import Speaker

# Supplemental speech for transient dialog confirmations that don't move focus
# (e.g. the auto-filled offset suggestion). Module-level so the prism backend is
# acquired once, not per dialog; a no-op when speech is unavailable.
_speaker = Speaker()

# Several choice columns store terse tokens — a blank ("no value") entry, single
# letters, "+"/"-" — that a screen reader reads poorly or as nothing. We show a
# spoken word instead, mapping the raw CHIRP value -> a label and round-tripping
# it back in ``control_value`` so the stored value is unchanged. A blank with no
# explicit override falls back to "None". Cross-checked against chirp_common's
# value lists (CHIRP's own editor renders these raw, so the words are a VRP a11y
# add):
#   tmode  TONE_MODES ("", "Tone", ...)        "" = no tone -> "None"
#   duplex ["", "+", "-", "split", "off"]      "" simplex, +/- offset, off = TX off
#   skip   SKIP_VALUES ("", "S", "P")          "" none, S = skip, P = priority scan
_DEFAULT_EMPTY_LABEL = "None"
_CHOICE_LABELS: dict[str, dict[str, str]] = {
    "duplex": {"": "Simplex", "+": "Plus", "-": "Minus",
               "split": "Split", "off": "Off"},
    "skip": {"": "None", "S": "Skip", "P": "Priority scan"},
}


def _label_for(col, value: str) -> str:
    """Display label for the raw choice ``value`` in ``col``: a per-column word
    where defined, "None" for an otherwise-blank option, else the value as-is."""
    overrides = _CHOICE_LABELS.get(col.name, {})
    if value in overrides:
        return overrides[value]
    if value == "":
        return _DEFAULT_EMPTY_LABEL
    return value


def _select_choice(
    ctrl: "wx.Choice", raw_choices: list[str], current: str, target_label: str
) -> None:
    """Select ``current`` (a raw column value) in a wx.Choice whose entries are
    display labels, tolerating the relabel and numeric formatting differences
    (e.g. DTCS "23" vs the choice "023")."""
    if ctrl.SetStringSelection(target_label):
        return
    cur = current.strip().lstrip("0")
    if cur:
        for i, choice in enumerate(raw_choices):
            if choice.strip().lstrip("0") == cur:
                ctrl.SetSelection(i)
                return
    if raw_choices:
        ctrl.SetSelection(0)


def make_field_control(parent: wx.Window, col, current: str):
    """Build the right native control for a column: a wx.Choice for ``select``
    columns (pre-selected to ``current``), else a wx.TextCtrl."""
    if col.input_type == "select":
        raw = list(col.choices)
        labels = [_label_for(col, v) for v in raw]
        ctrl = wx.Choice(parent, choices=labels)
        # Reverse map (display label -> raw value) so control_value restores the
        # value CHIRP stores. Labels are unique per column.
        ctrl._vrp_label_to_value = dict(zip(labels, raw))
        _select_choice(ctrl, raw, current, _label_for(col, current))
        return ctrl
    return wx.TextCtrl(parent, value=current)


def control_value(ctrl) -> str:
    """Read the current string value from a field control (Choice or TextCtrl).

    A display label maps back to the raw value CHIRP expects (e.g. "Simplex" ->
    "", "Priority scan" -> "P")."""
    if isinstance(ctrl, wx.Choice):
        val = ctrl.GetStringSelection()
        reverse = getattr(ctrl, "_vrp_label_to_value", None)
        if reverse is not None:
            return reverse.get(val, val)
        return val
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

        # Suggest the standard repeater offset for the band when the user enters
        # a frequency (and the Offset field is still blank). Magnitude only —
        # the user picks the +/- duplex direction. Tracked so we only act on a
        # real change, never retroactively on a channel the user just views.
        freq_entry = self._controls.get("freq")
        if freq_entry is not None and "offset" in self._controls:
            freq_ctrl = freq_entry[0]
            self._last_freq = control_value(freq_ctrl)
            freq_ctrl.Bind(wx.EVT_KILL_FOCUS, self._maybe_suggest_offset)

        # Focus the first editable control on open.
        for field, (ctrl, _col) in self._controls.items():
            if ctrl.IsEnabled():
                ctrl.SetFocus()
                break

    def _maybe_suggest_offset(self, event: wx.FocusEvent) -> None:
        """Fill the Offset field with the band's standard repeater shift when
        the frequency changes and Offset is still blank/zero. Never overwrites
        an existing offset and never changes the duplex direction."""
        event.Skip()  # don't consume focus traversal
        from chirp_backend import bandplan

        freq_ctrl = self._controls["freq"][0]
        offset_ctrl = self._controls["offset"][0]
        freq_str = control_value(freq_ctrl).strip()
        if freq_str == self._last_freq:
            return  # focus left the field but the frequency didn't change
        self._last_freq = freq_str

        if not offset_ctrl.IsEnabled():
            return  # immutable offset — leave it alone
        current = control_value(offset_ctrl).strip()
        if current and current not in ("0", "0.0"):
            return  # respect an offset the user/radio already set

        offset_hz = bandplan.suggest_offset_for_freq_str(freq_str)
        if offset_hz:
            mhz = bandplan.offset_hz_to_mhz_str(offset_hz)
            offset_ctrl.SetValue(mhz)
            # Announce it: the user has tabbed past the Offset field, so a screen
            # reader won't read the change on its own. Show it on the status line
            # (sighted) and speak it (don't interrupt the reader's field read).
            message = f"Suggested offset {mhz} MHz — set Duplex to plus or minus to use it."
            self._status.SetLabel(message)
            _speaker.speak(message)

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
