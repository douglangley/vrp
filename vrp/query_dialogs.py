"""Native wx dialogs for online query sources (Phase 7).

QueryParamsDialog gathers a source's parameters (none for the v1 sources) plus
shows its attribution and a descriptive Terms-of-Service link. ImportDestination
Dialog chooses where the fetched results land and how to treat occupied
channels. The fetch itself runs on a background thread with the shared
CloneProgressDialog; import goes through memory_ops.import_memories.
"""

from __future__ import annotations

import urllib.parse

import wx
import wx.adv


class QueryParamsDialog(wx.Dialog):
    def __init__(self, parent, source: dict) -> None:
        super().__init__(parent, title=f"Query {source['label']}")
        self._spec = source.get("params", [])
        self._controls: dict = {}

        outer = wx.BoxSizer(wx.VERTICAL)
        attribution = source.get("attribution", "")
        if attribution:
            outer.Add(wx.StaticText(self, label=attribution), 0, wx.ALL, 10)
        tos = source.get("tos")
        if tos:
            host = urllib.parse.urlparse(tos).netloc or tos
            link = wx.adv.HyperlinkCtrl(
                self, label=f"Open {host} terms of service in your browser", url=tos
            )
            link.SetName(f"Open {host} terms of service in your browser")
            outer.Add(link, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)

        if self._spec:
            grid = wx.FlexGridSizer(cols=2, vgap=6, hgap=10)
            grid.AddGrowableCol(1, 1)
            for p in self._spec:
                grid.Add(wx.StaticText(self, label=p["label"] + ":"), 0,
                         wx.ALIGN_CENTER_VERTICAL)
                if p.get("kind") == "choice":
                    ctrl = wx.Choice(self, choices=list(p.get("options", [])))
                    if ctrl.GetCount():
                        ctrl.SetSelection(0)
                else:
                    ctrl = wx.TextCtrl(self)
                ctrl.SetName(p["label"])
                grid.Add(ctrl, 0, wx.EXPAND)
                self._controls[p["name"]] = ctrl
            outer.Add(grid, 0, wx.EXPAND | wx.ALL, 10)
        else:
            outer.Add(
                wx.StaticText(self, label="No options. Choose Query to fetch results."),
                0, wx.ALL, 10,
            )

        buttons = self.CreateStdDialogButtonSizer(wx.OK | wx.CANCEL)
        ok = self.FindWindowById(wx.ID_OK)
        if ok:
            ok.SetLabel("Query")
        outer.Add(buttons, 0, wx.EXPAND | wx.ALL, 8)
        self.SetSizerAndFit(outer)

    def get_params(self) -> dict:
        # Include every declared param (some sources read params['key'] directly,
        # so a missing key would crash do_fetch). Blank text fields pass "".
        out = {}
        for name, ctrl in self._controls.items():
            if isinstance(ctrl, wx.Choice):
                out[name] = ctrl.GetStringSelection()
            else:
                out[name] = ctrl.GetValue().strip()
        return out


class ImportDestinationDialog(wx.Dialog):
    def __init__(self, parent, count: int, low: int, high: int, default_dest: int) -> None:
        super().__init__(parent, title="Import query results")
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
