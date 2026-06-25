"""Spike: which native wx table control does VoiceOver actually read on macOS?

Throwaway harness — NOT production, imports nothing from vrp. Puts three
candidate channel-grid controls in ONE window, each with a wx.StaticText header
and a few rows of fake channel data (Ch #, Frequency, Name, Mode), so the owner
can VoiceOver-navigate each control and report which one speaks cell text.

    uv run python tools/spike_native_voiceover.py

WHY this spike exists
---------------------
The production native grid (vrp/native/channel_grid.py) is a virtual
report-mode wx.ListCtrl (LC_REPORT | LC_VIRTUAL). On macOS, wx.ListCtrl in
report mode is the GENERIC (wx-drawn) implementation: it draws its own rows and
exposes little/nothing to NSAccessibility, so VoiceOver is silent on it. On
Windows it maps to the native list-view control, which NVDA reads fine. The
candidates below wrap REAL Cocoa views, which should be exposed to VoiceOver:

    Variant A  virtual report-mode wx.ListCtrl  — known-silent baseline (current)
    Variant B  wx.dataview.DataViewListCtrl     — wraps NSTableView/NSOutlineView
    Variant C  wx.grid.Grid                     — secondary candidate

VoiceOver TEST SCRIPT (run with VO on: Cmd+F5)
----------------------------------------------
1. Press Tab to move between the three controls. As each gets focus, note what
   VoiceOver says — does it announce a table/list, a column count, a row?
2. Inside each control, use the Arrow keys (and VO+arrow: Ctrl+Opt+Arrow) to
   move through rows and cells. For EACH control write down:
     - Does VO speak the cell text (e.g. "146.520", "Calling")?
     - Does VO speak the COLUMN HEADER with the value (e.g. "Frequency 146.520")?
     - Does VO say nothing at all (silent)?
3. Report per-variant: SILENT / reads rows only / reads cells / reads cells+headers.

Variant B (DataViewListCtrl) is expected to win. If it reads cells+headers under
VoiceOver, it's the migration target for the production grid — see
docs/research/2026-06-24-native-grid-voiceover-feasibility.md.
"""

from __future__ import annotations

import wx
import wx.dataview
import wx.grid

# Fake channel rows: (number, frequency, name, mode)
ROWS = [
    ("1", "146.520", "Calling", "FM"),
    ("2", "147.000", "Repeater", "FM"),
    ("3", "446.000", "GMRS 1", "NFM"),
    ("4", "462.5625", "FRS 1", "NFM"),
    ("5", "", "(empty)", ""),
]
COLS = ["Ch #", "Frequency", "Name", "Mode"]


def _header(panel: wx.Panel, sizer: wx.BoxSizer, text: str) -> None:
    label = wx.StaticText(panel, label=text)
    font = label.GetFont()
    font.MakeBold()
    label.SetFont(font)
    sizer.Add(label, 0, wx.TOP | wx.LEFT, 8)


def _make_listctrl(panel: wx.Panel) -> wx.ListCtrl:
    """Variant A — the current production approach (virtual report-mode)."""

    class VirtualList(wx.ListCtrl):
        def OnGetItemText(self, item: int, column: int) -> str:  # noqa: N802
            return ROWS[item][column]

    ctrl = VirtualList(
        panel, style=wx.LC_REPORT | wx.LC_VIRTUAL | wx.LC_HRULES
    )
    ctrl.SetName("Variant A: virtual wx.ListCtrl")
    for i, label in enumerate(COLS):
        ctrl.InsertColumn(i, label, width=120)
    ctrl.SetItemCount(len(ROWS))
    return ctrl


def _make_dataview(panel: wx.Panel) -> wx.dataview.DataViewListCtrl:
    """Variant B — wraps a native Cocoa NSTableView/NSOutlineView."""
    ctrl = wx.dataview.DataViewListCtrl(panel)
    ctrl.SetName("Variant B: DataViewListCtrl")
    for label in COLS:
        ctrl.AppendTextColumn(label, width=120)
    for row in ROWS:
        ctrl.AppendItem(list(row))
    return ctrl


def _make_grid(panel: wx.Panel) -> wx.grid.Grid:
    """Variant C — wx.grid.Grid (also a native-ish table on macOS)."""
    ctrl = wx.grid.Grid(panel)
    ctrl.CreateGrid(len(ROWS), len(COLS))
    ctrl.SetName("Variant C: wx.grid.Grid")
    for c, label in enumerate(COLS):
        ctrl.SetColLabelValue(c, label)
        ctrl.SetColSize(c, 120)
    for r, row in enumerate(ROWS):
        for c, value in enumerate(row):
            ctrl.SetCellValue(r, c, value)
    ctrl.EnableEditing(False)
    return ctrl


class SpikeFrame(wx.Frame):
    def __init__(self) -> None:
        super().__init__(None, title="VRP spike — native grid under VoiceOver")
        panel = wx.Panel(self)
        sizer = wx.BoxSizer(wx.VERTICAL)

        intro = wx.StaticText(
            panel,
            label=(
                "Tab between the three tables. Arrow through each under "
                "VoiceOver; note which speaks cell text. See module docstring."
            ),
        )
        sizer.Add(intro, 0, wx.ALL, 8)

        _header(panel, sizer, "Variant A — virtual wx.ListCtrl (current, likely SILENT)")
        sizer.Add(_make_listctrl(panel), 1, wx.EXPAND | wx.ALL, 8)

        _header(panel, sizer, "Variant B — wx.dataview.DataViewListCtrl (most promising)")
        sizer.Add(_make_dataview(panel), 1, wx.EXPAND | wx.ALL, 8)

        _header(panel, sizer, "Variant C — wx.grid.Grid (secondary)")
        sizer.Add(_make_grid(panel), 1, wx.EXPAND | wx.ALL, 8)

        panel.SetSizer(sizer)
        self.SetSize((640, 760))


def main() -> None:
    app = wx.App(False)
    app.SetAppName("VRP native-grid VoiceOver spike")
    frame = SpikeFrame()
    frame.Show()
    frame.Raise()
    app.MainLoop()


if __name__ == "__main__":
    main()
