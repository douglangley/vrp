"""Native wx dialog for editing one memory channel.

Why a dedicated dialog instead of editing inline in the grid: with large radios
(thousands of channels) putting controls in the grid forces the screen reader
to re-read the whole table on every interaction. A native ``wx.Dialog`` is a
separate top-level window with first-class keyboard/screen-reader support, so
the channel grid stays a fast, navigable table and only the edited row is
refreshed afterward. (Accessibility-lead approved model.)

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
from vrp.speech import get_speaker

# Supplemental speech for transient dialog confirmations that don't move focus
# (e.g. the auto-filled offset suggestion). The shared process-wide Speaker, so
# the prism backend is acquired once; a no-op when speech is unavailable.
_speaker = get_speaker()

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


def set_control_value(ctrl, col, value: str) -> None:
    """Set a field control to a raw column ``value`` — the inverse of
    ``control_value`` (maps a raw value to its display label for a wx.Choice)."""
    if isinstance(ctrl, wx.Choice):
        _select_choice(ctrl, list(col.choices), value, _label_for(col, value))
    else:
        ctrl.SetValue(value)


def _offset_suggestion_message(mhz: str) -> str:
    """The announcement for an auto-filled offset. Names the duplex step because
    the offset is inert until the user picks a +/- direction."""
    return f"Suggested offset {mhz} MHz — set Duplex to plus or minus to use it."


def _is_blank_offset(text: str) -> bool:
    """Whether an offset field is effectively unset (blank / zero)."""
    text = text.strip()
    return not text or text in ("0", "0.0")


class EditChannelDialog(wx.Dialog):
    """Modal editor for a single channel's fields."""

    def __init__(self, parent, number: int, mem, features, *,
                 apply_band_defaults: bool = False) -> None:
        empty = bool(getattr(mem, "empty", False))
        title = f"Edit channel {number}" + (" (empty)" if empty else "")
        super().__init__(parent, title=title)
        # When set (Preferences > Apply band-plan defaults), changing the
        # Frequency also fills mode/step/tone from the band plan, not just offset.
        self._apply_band_defaults = apply_band_defaults
        self._features = features

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

        # When the user enters a frequency, fill band-plan values: always the
        # standard repeater offset (if Offset is blank), and — when the
        # "Apply band-plan defaults" preference is on — mode/step/tone too.
        # Magnitude only; the user picks the +/- duplex direction. Tracked so we
        # only act on a real change, never retroactively on a channel just viewed.
        freq_entry = self._controls.get("freq")
        if freq_entry is not None:
            freq_ctrl = freq_entry[0]
            self._last_freq = control_value(freq_ctrl)
            freq_ctrl.Bind(wx.EVT_KILL_FOCUS, self._on_frequency_changed)

        # Focus the first editable control on open.
        for field, (ctrl, _col) in self._controls.items():
            if ctrl.IsEnabled():
                ctrl.SetFocus()
                break

    def _on_frequency_changed(self, event: wx.FocusEvent) -> None:
        """Apply band-plan values when the frequency actually changes: the
        standard repeater offset (when Offset is blank), and — when enabled —
        mode/step/tone. Announces what changed; never touches the duplex
        direction or an offset already set."""
        event.Skip()  # don't consume focus traversal

        freq_ctrl = self._controls["freq"][0]
        freq_str = control_value(freq_ctrl).strip()
        if freq_str == self._last_freq:
            return  # focus left the field but the frequency didn't change
        self._last_freq = freq_str

        parts: list[str] = []
        offset_msg = self._fill_offset(freq_str)  # always-on, magnitude only
        if self._apply_band_defaults:
            parts.extend(self._fill_band_defaults(freq_str))

        if offset_msg or parts:
            message = offset_msg or ""
            if parts:
                joined = ", ".join(parts)
                message = (message + " " if message else "") + \
                    f"Band defaults: {joined}."
            self._status.SetLabel(message)
            _speaker.speak(message)

    def _fill_offset(self, freq_str: str) -> str:
        """Fill a blank Offset with the band's standard shift; return the
        announcement (or "" when nothing was filled)."""
        from chirp_backend import bandplan

        entry = self._controls.get("offset")
        if entry is None or not entry[0].IsEnabled():
            return ""
        offset_ctrl = entry[0]
        if not _is_blank_offset(control_value(offset_ctrl)):
            return ""  # respect an offset the user/radio already set
        offset_hz = bandplan.suggest_offset_for_freq_str(freq_str)
        if not offset_hz:
            return ""
        mhz = bandplan.offset_hz_to_mhz_str(offset_hz)
        offset_ctrl.SetValue(mhz)
        return _offset_suggestion_message(mhz)

    def _fill_band_defaults(self, freq_str: str) -> list[str]:
        """Set mode/step/tone from the band plan, overwriting current values.
        Returns a short phrase per field that actually changed (for announcing)."""
        from chirp_backend import bandplan

        defaults = bandplan.suggest_band_defaults_for_freq_str(
            freq_str, self._features)
        changed: list[str] = []
        labels = {"mode": "mode", "tuning_step": "step", "rtone": "tone"}
        for field, value in defaults.items():
            entry = self._controls.get(field)
            if entry is None or not entry[0].IsEnabled():
                continue
            ctrl, col = entry
            if control_value(ctrl) == value:
                continue  # already that value — nothing to announce
            set_control_value(ctrl, col, value)
            changed.append(f"{labels.get(field, field)} {value}")
        return changed

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

        # Editing the Offset cell on its own: there's no Frequency field here, so
        # take the band's standard repeater shift from the channel's own
        # frequency and pre-fill it when Offset is blank — focused and selected so
        # the user can accept it with Enter or type over it.
        if col.name == "offset":
            self._suggest_offset(mem)

    def _suggest_offset(self, mem) -> None:
        from chirp_backend import bandplan

        if not self._ctrl.IsEnabled():
            return
        if not _is_blank_offset(control_value(self._ctrl)):
            return  # respect an offset already set
        offset_hz = bandplan.suggest_offset_hz(getattr(mem, "freq", 0))
        if not offset_hz:
            return
        mhz = bandplan.offset_hz_to_mhz_str(offset_hz)
        self._ctrl.SetValue(mhz)
        self._ctrl.SelectAll()  # type to replace, or Enter to accept
        message = _offset_suggestion_message(mhz)
        self._status.SetLabel(message)
        _speaker.speak(message)

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


class ColumnPickerDialog(wx.Dialog):
    """Pick which field of a channel to edit — F2's fallback where the grid has
    no Left/Right cell cursor.

    Windows and macOS have the cursor, so F2 edits the cell you arrowed to
    directly. On platforms where the cursor isn't wired (GTK/other), F2 can't tell
    which column you're on, so rather than guess it asks: this dialog lists the
    channel's editable fields and the chosen one then opens in
    :class:`EditCellDialog`.

    Standard accessible modal: a labelled single-select list (focus lands there),
    OK/Cancel, Escape cancels, Enter or double-click accepts. Returning focus to
    the grid row is the caller's job (it re-focuses the channel afterwards)."""

    def __init__(self, parent, number: int, columns: list) -> None:
        super().__init__(parent, title=f"Edit which field? (channel {number})")
        self._columns = list(columns)

        outer = wx.BoxSizer(wx.VERTICAL)
        # A real StaticText names the list for screen readers (SetName alone is
        # unreliable) and states the choice being made.
        outer.Add(
            wx.StaticText(self, label=f"Field to edit on channel {number}:"),
            0, wx.LEFT | wx.RIGHT | wx.TOP, 12,
        )
        self._listbox = wx.ListBox(
            self, choices=[c.label for c in self._columns], style=wx.LB_SINGLE
        )
        self._listbox.SetName("Field to edit")
        if self._columns:
            self._listbox.SetSelection(0)  # a field is always chosen / announced
        outer.Add(self._listbox, 1, wx.EXPAND | wx.ALL, 12)

        outer.Add(self.CreateStdDialogButtonSizer(wx.OK | wx.CANCEL), 0,
                  wx.EXPAND | wx.ALL, 8)
        self.SetSizerAndFit(outer)

        # Double-click, or Enter on the default OK button, accepts the highlight.
        self._listbox.Bind(wx.EVT_LISTBOX_DCLICK, self._on_accept)
        # A focused wx.ListBox doesn't reliably forward Return to the dialog's
        # default button on every platform, so handle Enter on the list directly.
        # Other keys pass through (type-ahead, etc.).
        self._listbox.Bind(wx.EVT_KEY_DOWN, self._on_list_key)
        self.Bind(wx.EVT_BUTTON, self._on_accept, id=wx.ID_OK)
        # Land focus on the list (not the default OK button) so the user is on the
        # choices immediately; wx's default focus runs first, then this overrides.
        self.Bind(wx.EVT_INIT_DIALOG, self._on_init_dialog)

    def _on_init_dialog(self, event) -> None:
        event.Skip()
        wx.CallAfter(self._listbox.SetFocus)

    def _on_list_key(self, event: wx.KeyEvent) -> None:
        if event.GetKeyCode() in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER):
            self._on_accept(event)
            return
        event.Skip()

    def _on_accept(self, _event) -> None:
        if self.get_column() is None:
            return  # nothing selected — keep the dialog open
        self.EndModal(wx.ID_OK)

    def get_column(self):
        """The selected :class:`~chirp_backend.col_defs.ColumnDef`, or ``None``."""
        i = self._listbox.GetSelection()
        return self._columns[i] if 0 <= i < len(self._columns) else None
