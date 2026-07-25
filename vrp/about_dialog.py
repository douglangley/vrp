"""Help ▸ About — build information and the CHIRP acknowledgement.

Why a hand-built dialog and not ``wx.adv.AboutBox``: AboutBox renders its
description as *static text*, which a screen-reader user hears once and cannot
navigate, re-read, or copy — the version string is the one thing a tester is
most often asked to quote into a bug report. Two read-only multiline
``wx.TextCtrl``s are real text fields: NVDA/VoiceOver move through them by
line/word/character and Ctrl+C works. AboutBox also gives no say over the
control order, which matters here (see the label note below).

The CHIRP attribution line is a GPLv3 requirement (CLAUDE.md) and lives in the
acknowledgement box, alongside its permanent home in status-bar field 1.
"""

from __future__ import annotations

import wx

from vrp import __version__, describe_version

# The acknowledgement shown in the second box. Kept in step with the "With
# thanks to the CHIRP project" section of getting started/GettingStarted.*.
# The closing line is the GPLv3-required attribution — do not drop it.
ACKNOWLEDGEMENT = (
    "VRP is an accessible front end that takes advantage of the open source "
    "CHIRP radio programming software, found at chirpmyradio.com and "
    "github.com/kk7ds/chirp. We would like to thank them, and to acknowledge "
    "that this software would not be possible without their hard work.\n\n"
    "Every radio VRP can talk to, it talks to through a driver that a CHIRP "
    "volunteer wrote, tested, and still maintains — most of them worked out by "
    "taking a radio's protocol apart by hand, without any help from the "
    "manufacturer. That is years of patient work by a lot of people, given "
    "away freely, and it is the foundation this program stands on. It keeps "
    "paying off, too: when CHIRP adds a radio or fixes a driver, VRP picks "
    "that up and ships it in a new release.\n\n"
    "VRP is released under the GPL v3 — the same licence CHIRP uses. The terms "
    "that let us build on their work are the terms we pass on to you.\n\n"
    "Radio driver support provided by the CHIRP project — chirpmyradio.com."
)


def build_info_text() -> str:
    """The build box's contents.

    Leads with describe_version()'s speakable form ("Release 3 of 15 July
    2026") because a screen reader reads the bare 20260715.3 as one huge
    number. The exact string still appears, on its own line, for copying into a
    bug report.
    """
    return (
        "Versatile Radio Programmer\n"
        f"{describe_version()}.\n"
        f"Version: {__version__}"
    )


class AboutDialog(wx.Dialog):
    """Modal About box: a build-information field, an acknowledgement field, and
    an OK button. Escape dismisses; focus opens in the build information."""

    def __init__(self, parent) -> None:
        super().__init__(
            parent,
            title="About Versatile Radio Programmer",
            style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER,
        )

        outer = wx.BoxSizer(wx.VERTICAL)

        # Each wx.StaticText is created BEFORE the control it names: wxMSW takes
        # a native control's accessible name from the preceding sibling and
        # ignores SetName, so building these in the other order makes NVDA read
        # the two boxes' labels off by one.
        build_label = wx.StaticText(self, label="&Build information:")
        outer.Add(build_label, 0, wx.LEFT | wx.RIGHT | wx.TOP, 10)
        self.build = wx.TextCtrl(
            self,
            value=build_info_text(),
            # TE_READONLY still allows caret navigation, selection, and copy —
            # it only blocks editing, which is what review wants.
            style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_WORDWRAP,
            size=(460, 80),
        )
        self.build.SetName("Build information")  # for wxGTK/wxMac, which honour it
        outer.Add(self.build, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)

        ack_label = wx.StaticText(self, label="&Acknowledgements:")
        outer.Add(ack_label, 0, wx.LEFT | wx.RIGHT, 10)
        self.acknowledgement = wx.TextCtrl(
            self,
            value=ACKNOWLEDGEMENT,
            style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_WORDWRAP,
            size=(460, 200),
        )
        self.acknowledgement.SetName("Acknowledgements")
        outer.Add(self.acknowledgement, 1, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)

        outer.Add(self.CreateButtonSizer(wx.OK), 0, wx.EXPAND | wx.ALL, 8)

        self.SetSizerAndFit(outer)
        # An About box has nothing to cancel, so OK and Escape mean the same
        # thing; SetEscapeId wires Escape to it (there is no Cancel button for
        # wx to find on its own).
        self.SetEscapeId(wx.ID_OK)
        self.Bind(wx.EVT_BUTTON, lambda _e: self.EndModal(wx.ID_OK), id=wx.ID_OK)
        self.Bind(wx.EVT_INIT_DIALOG, self._on_init_dialog)

    def _on_init_dialog(self, event) -> None:
        event.Skip()  # let wx's default focus run first, then override it
        wx.CallAfter(self._focus_build)

    def _focus_build(self) -> None:
        self.build.SetFocus()
        self.build.SetInsertionPoint(0)  # land at the top, not the end
