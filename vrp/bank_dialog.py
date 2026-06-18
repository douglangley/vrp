"""Native wx dialog to assign one channel to banks (Phase 6).

Built from a state dict produced by chirp_backend.bank_ops.get_bank_state:
- mode "multi"  -> a CheckBox per bank (memory may be in several banks);
- mode "single" -> a RadioBox of ["None"] + banks (zero-or-one);
- mode "fixed"  -> controls shown disabled, Close-only (banks can't be changed).

An intro line states the current membership in words (rule #7 — state in text,
not just control appearance). On OK the caller reads get_desired_indexes() and
applies the diff via bank_ops.apply_bank_changes.
"""

from __future__ import annotations

import wx


class ChannelBanksDialog(wx.Dialog):
    def __init__(self, parent, state: dict) -> None:
        self._number = state["number"]
        self._mode = state["mode"]
        self._read_only = state["read_only"]
        self._banks = state["banks"]          # [(index, label), ...]
        self._member = state["member_indexes"]

        title = f"Banks for channel {self._number}"
        if self._read_only:
            title += " (read only)"
        super().__init__(parent, title=title)

        outer = wx.BoxSizer(wx.VERTICAL)
        current = [lbl for idx, lbl in self._banks if idx in self._member]
        intro = wx.StaticText(
            self,
            label=f"Channel {self._number} is currently in: "
            + (", ".join(current) if current else "no banks") + ".",
        )
        outer.Add(intro, 0, wx.ALL, 10)

        self._checks: dict = {}
        self._radio = None
        if self._mode == "multi":
            box = wx.StaticBoxSizer(wx.VERTICAL, self, "Banks")
            for idx, label in self._banks:
                cb = wx.CheckBox(self, label=label)
                cb.SetName(label)
                cb.SetValue(idx in self._member)
                if self._read_only:
                    cb.Disable()
                box.Add(cb, 0, wx.ALL, 3)
                self._checks[idx] = cb
            outer.Add(box, 1, wx.EXPAND | wx.ALL, 10)
        else:  # single (zero-or-one) — None plus each bank
            choices = ["None"] + [lbl for _idx, lbl in self._banks]
            self._radio = wx.RadioBox(
                self, label="Bank", choices=choices,
                majorDimension=1, style=wx.RA_SPECIFY_COLS,
            )
            sel = 0
            for i, (idx, _lbl) in enumerate(self._banks):
                if idx in self._member:
                    sel = i + 1
                    break
            self._radio.SetSelection(sel)
            if self._read_only:
                self._radio.Disable()
            outer.Add(self._radio, 0, wx.EXPAND | wx.ALL, 10)

        flags = wx.CANCEL if self._read_only else (wx.OK | wx.CANCEL)
        buttons = self.CreateStdDialogButtonSizer(flags)
        if self._read_only:
            close = self.FindWindowById(wx.ID_CANCEL)
            if close:
                close.SetLabel("Close")
        outer.Add(buttons, 0, wx.EXPAND | wx.ALL, 8)

        self.SetSizerAndFit(outer)

    def get_desired_indexes(self) -> set:
        if self._mode == "multi":
            return {idx for idx, cb in self._checks.items() if cb.GetValue()}
        sel = self._radio.GetSelection()
        if sel <= 0:  # "None"
            return set()
        idx, _label = self._banks[sel - 1]
        return {idx}
