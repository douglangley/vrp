"""The startup welcome screen: pick a band-plan region, offer the guide.

Two things are worth asking a new user once, and they are asked together rather
than as two dialogs stacked on top of each other at launch:

1. **Which band plan region.** VRP suggests the standard repeater offset for a
   frequency's band, and which offsets are standard depends on where you are.
   The default (North America, CHIRP's own) is silently wrong for most of the
   world, and a user who never opens Preferences would never learn there was a
   choice.
2. **Whether to read the Getting Started guide.**

Neither is a one-way door: the region is also in File > Preferences, and the
guide is always in Help > Getting Started. That is what makes "Don't show this
again" safe to offer — nothing here is lost by dismissing it.

A pure value collector, like PreferencesDialog: it decides nothing and persists
nothing. ShowModal()'s return says which button was pressed and region() says
what was picked; MainWindow.maybe_show_welcome applies both.
"""

from __future__ import annotations

import wx

from chirp_backend.bandplan import DEFAULT_REGION, REGIONS

_INTRO = (
    "Welcome to VRP — the Versatile Radio Programmer.\n\n"
    "When you type a frequency, VRP fills in the standard repeater offset for "
    "that band. Which offsets count as standard depends on where you are, so "
    "please pick your region below. You can change it later in File, "
    "Preferences."
)

_GUIDE_PROMPT = (
    "New to VRP? The Getting Started guide covers downloading from your radio, "
    "editing channels, and the keyboard commands. It opens in your browser."
)


class WelcomeDialog(wx.Dialog):
    """Modal welcome screen. Escape means "Not now" — never "don't show again",
    so a stray Escape can't silently switch the screen off for good."""

    #: ShowModal() returns one of these.
    OPEN_GUIDE = wx.ID_YES
    NOT_NOW = wx.ID_NO
    DONT_SHOW = wx.ID_NOTOALL

    def __init__(self, parent, current_region: str = DEFAULT_REGION) -> None:
        super().__init__(parent, title="Welcome to VRP")

        outer = wx.BoxSizer(wx.VERTICAL)
        intro = wx.StaticText(self, label=_INTRO)
        intro.Wrap(430)  # StaticText does not wrap on its own
        outer.Add(intro, 0, wx.ALL, 12)

        # The label is created BEFORE the control it names: wxMSW takes a native
        # control's accessible name from the preceding sibling and ignores
        # SetName, so the order here is what makes NVDA say "Band plan region"
        # rather than reading the intro paragraph at the user.
        row = wx.BoxSizer(wx.HORIZONTAL)
        row.Add(wx.StaticText(self, label="Band plan &region:"), 0,
                wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 8)
        self._region_codes = [code for code, _ in REGIONS]
        self.region = wx.Choice(self, choices=[label for _, label in REGIONS])
        self.region.SetName(  # honoured on wxGTK/wxMac
            "Band plan region for suggested repeater offsets"
        )
        try:
            self.region.SetSelection(self._region_codes.index(current_region))
        except ValueError:  # an unknown region in config.json
            self.region.SetSelection(self._region_codes.index(DEFAULT_REGION))
        row.Add(self.region, 1)
        outer.Add(row, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 12)

        prompt = wx.StaticText(self, label=_GUIDE_PROMPT)
        prompt.Wrap(430)
        outer.Add(prompt, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 12)

        # Three plain buttons rather than a checkbox plus OK: each is one
        # decisive keystroke for a screen-reader user, with no state to find and
        # toggle first. The region is saved whichever one is pressed.
        buttons = wx.BoxSizer(wx.HORIZONTAL)
        for button_id, label in (
            (self.OPEN_GUIDE, "&Open Getting Started"),
            (self.NOT_NOW, "&Not now"),
            (self.DONT_SHOW, "&Don't show this again"),
        ):
            button = wx.Button(self, button_id, label)
            buttons.Add(button, 0, wx.RIGHT, 8)
            self.Bind(wx.EVT_BUTTON, self._on_button, button)
            if button_id == self.OPEN_GUIDE:
                button.SetDefault()
        outer.Add(buttons, 0, wx.ALIGN_RIGHT | wx.ALL, 8)

        self.SetSizerAndFit(outer)
        self.SetEscapeId(self.NOT_NOW)
        self.Bind(wx.EVT_INIT_DIALOG, self._on_init_dialog)

    def _on_button(self, event) -> None:
        self.EndModal(event.GetId())

    def _on_init_dialog(self, event) -> None:
        event.Skip()  # let wx's default focus run first, then override it
        wx.CallAfter(self.region.SetFocus)  # the decision, not a button

    def region_code(self) -> str:
        """The band-plan region shortname the user picked."""
        return self._region_codes[self.region.GetSelection()]
