"""Native wx dialog for the radio settings editor (Phase 5).

CHIRP exposes settings as a nested tree of RadioSettingGroup; leaves are
RadioSetting items holding typed RadioSettingValue objects. Per the
accessibility-lead model this is one modal dialog with a wx.Treebook: the tree
mirrors the top-level groups, and each page is a scrolled panel of label+control
pairs (the same FlexGridSizer pattern as edit_dialog/ops_dialog). Nested
sub-groups are flattened into their top-level page with an indented bold
heading — this keeps the tree segmented by top-level group while avoiding
wx.Treebook's sub-page ordering pitfalls.

Controls map to value types: Boolean->CheckBox, List->Choice, Integer->SpinCtrl,
String/Float->TextCtrl. Immutable values are shown disabled + "(read only)".
On OK every enabled control is written back via value.set_value (which validates
and raises InvalidValueError); a failure keeps the dialog open, reveals the
offending control's page, focuses it, and speaks the reason. The caller applies
the (now-mutated) tree via radio.set_settings only on OK.
"""

from __future__ import annotations

import wx

from chirp import settings as cs


class RadioSettingsDialog(wx.Dialog):
    def __init__(self, parent, groups) -> None:
        super().__init__(
            parent, title="Radio settings",
            style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER,
            size=(640, 520),
        )
        self._controls: list[tuple] = []      # (RadioSettingValue, wx control)
        self._page_of: dict[int, int] = {}     # ctrl id -> treebook page index

        outer = wx.BoxSizer(wx.VERTICAL)
        self.tb = wx.Treebook(self, style=wx.BK_LEFT)
        outer.Add(self.tb, 1, wx.EXPAND | wx.ALL, 8)

        for group in groups:
            self._add_top_group(group)

        self._status = wx.StaticText(self, label="")
        self._status.SetName("Settings status")
        outer.Add(self._status, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)
        outer.Add(self.CreateStdDialogButtonSizer(wx.OK | wx.CANCEL), 0,
                  wx.EXPAND | wx.ALL, 8)

        self.SetSizer(outer)
        self.Bind(wx.EVT_BUTTON, self._on_ok, id=wx.ID_OK)
        if self.tb.GetPageCount():
            self.tb.SetSelection(0)
        self.tb.SetFocus()  # land in the tree for an overview first

    # -- building ----------------------------------------------------------

    def _add_top_group(self, group) -> None:
        panel = wx.ScrolledWindow(self.tb)
        panel.SetScrollRate(0, 12)
        sizer = wx.FlexGridSizer(cols=2, vgap=6, hgap=10)
        sizer.AddGrowableCol(1, 1)
        page_controls: list[tuple] = []
        self._render_group(group, panel, sizer, 0, page_controls)
        panel.SetSizer(sizer)

        self.tb.AddPage(panel, group.get_shortname() or group.get_name())
        idx = self.tb.GetPageCount() - 1
        for value, ctrl in page_controls:
            self._controls.append((value, ctrl))
            self._page_of[ctrl.GetId()] = idx

    def _render_group(self, group, panel, sizer, depth, page_controls) -> None:
        for child in group:
            if isinstance(child, cs.RadioSetting):
                self._render_setting(child, panel, sizer, page_controls)
            elif isinstance(child, cs.RadioSettingGroup):
                heading = wx.StaticText(
                    panel,
                    label=("    " * depth) + (child.get_shortname() or child.get_name()),
                )
                font = heading.GetFont()
                font.MakeBold()
                heading.SetFont(font)
                sizer.Add(heading, 0, wx.TOP, 8)
                sizer.Add(wx.StaticText(panel, label=""))  # fill the 2nd column
                self._render_group(child, panel, sizer, depth + 1, page_controls)

    def _render_setting(self, setting, panel, sizer, page_controls) -> None:
        values = list(setting)
        name = setting.get_shortname() or setting.get_name()
        for i, value in enumerate(values):
            label_text = name if len(values) == 1 else f"{name} {i + 1}"
            sizer.Add(wx.StaticText(panel, label=label_text + ":"), 0,
                      wx.ALIGN_CENTER_VERTICAL)
            ctrl = self._make_control(panel, value, label_text)
            sizer.Add(ctrl, 0, wx.EXPAND)
            page_controls.append((value, ctrl))

    def _make_control(self, panel, value, label_text):
        mutable = value.get_mutable()
        if isinstance(value, cs.RadioSettingValueBoolean):
            ctrl = wx.CheckBox(panel)
            ctrl.SetValue(bool(value.get_value()))
        elif isinstance(value, cs.RadioSettingValueList):
            options = [str(o) for o in value.get_options()]
            ctrl = wx.Choice(panel, choices=options)
            if not ctrl.SetStringSelection(str(value.get_value())) and options:
                ctrl.SetSelection(0)
        elif isinstance(value, cs.RadioSettingValueInteger):
            ctrl = wx.SpinCtrl(panel, min=value.get_min(), max=value.get_max(),
                               initial=int(value.get_value()))
            try:
                ctrl.SetIncrement(value.get_step())
            except Exception:
                pass
        elif isinstance(value, cs.RadioSettingValueString):
            ctrl = wx.TextCtrl(panel, value=str(value.get_value()).rstrip())
            try:
                ctrl.SetMaxLength(value.maxlength)
            except Exception:
                pass
        else:  # Float and any other base value
            ctrl = wx.TextCtrl(panel, value=str(value.get_value()))

        name = label_text + ("" if mutable else " (read only)")
        ctrl.SetName(name)
        if not mutable:
            ctrl.Disable()
        return ctrl

    # -- reading / applying ------------------------------------------------

    @staticmethod
    def _read(ctrl):
        if isinstance(ctrl, wx.CheckBox):
            return ctrl.GetValue()
        if isinstance(ctrl, wx.Choice):
            return ctrl.GetStringSelection()
        if isinstance(ctrl, wx.SpinCtrl):
            return ctrl.GetValue()
        return ctrl.GetValue()  # wx.TextCtrl

    def get_changed_count(self) -> int:
        return sum(1 for value, _c in self._controls if value.changed())

    def _on_ok(self, event: wx.CommandEvent) -> None:
        for value, ctrl in self._controls:
            if not ctrl.IsEnabled():
                continue
            try:
                value.set_value(self._read(ctrl))
            except Exception as e:  # InvalidValueError etc. — keep dialog open
                idx = self._page_of.get(ctrl.GetId())
                if idx is not None:
                    self.tb.SetSelection(idx)
                msg = str(e)
                self._status.SetLabel(msg)
                wx.MessageBox(msg, "Invalid setting", wx.OK | wx.ICON_ERROR, self)
                ctrl.SetFocus()
                return
        event.Skip()  # all valid → close with wx.ID_OK
