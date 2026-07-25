"""Radio-level bank management: rename a bank, and see what is in one.

Ctrl+B stays the per-channel membership editor. This dialog is radio-level:
it renames banks (where the driver actually stores a name) and lists a bank's
channels read-only, with Go to channel.

Bank membership is deliberately not editable here. Ctrl+B already owns that
path, and it is verified, rolled back on failure, and undoable.
"""

from __future__ import annotations

import wx

from vrp.serial_dialogs import RadioListView


def _mhz(frequency: int) -> str:
    """Speak a frequency the way the rest of VRP does."""
    return f"{frequency / 1000000.0:.5f}".rstrip("0").rstrip(".") + " MHz"


class BankChannelsDialog(wx.Dialog):
    """Read-only list of the channels in one bank, with Go to channel."""

    def __init__(self, parent, bank_label: str, channels) -> None:
        super().__init__(
            parent,
            title=f"Channels in {bank_label}",
            style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER,
        )
        self._channels = list(channels)

        outer = wx.BoxSizer(wx.VERTICAL)
        # State in words (a11y rule 7) — an empty list must say so, not just
        # present an empty control.
        intro = (
            f"{bank_label} has no channels."
            if not self._channels
            else f"{bank_label} contains {self._count_phrase()}."
        )
        outer.Add(wx.StaticText(self, label=intro), 0, wx.ALL, 8)

        # LABEL BEFORE CONTROL — wxMSW derives the accessible name from the
        # preceding sibling.
        outer.Add(wx.StaticText(self, label="Channels:"), 0, wx.LEFT | wx.TOP, 8)
        self.list = RadioListView(
            self,
            name="Channels in bank",
            on_select=self._update_buttons,
            size=(420, 220),
        )
        self.list.Set([self._row_label(channel) for channel in self._channels])
        if self._channels:
            self.list.SetSelection(0)
        outer.Add(self.list, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 8)

        buttons = self.CreateStdDialogButtonSizer(wx.OK | wx.CANCEL)
        self._go = self.FindWindowById(wx.ID_OK)
        if self._go:
            self._go.SetLabel("Go to channel")
        close = self.FindWindowById(wx.ID_CANCEL)
        if close:
            close.SetLabel("Close")
        outer.Add(buttons, 0, wx.ALIGN_RIGHT | wx.ALL, 8)

        self.SetSizerAndFit(outer)
        self.SetEscapeId(wx.ID_CANCEL)
        self._update_buttons()
        if self._channels:
            self.list.SetFocus()

    def _count_phrase(self) -> str:
        count = len(self._channels)
        return "1 channel" if count == 1 else f"{count} channels"

    @staticmethod
    def _row_label(channel) -> str:
        parts = [f"Channel {channel.number}", _mhz(channel.frequency)]
        if channel.name:
            parts.append(channel.name)
        if channel.order is not None:
            parts.append(f"position {channel.order}")
        return " — ".join(parts)

    def _update_buttons(self) -> None:
        if self._go:
            self._go.Enable(self.get_channel() is not None)

    def get_channel(self) -> int | None:
        row = self.list.GetSelection()
        if 0 <= row < len(self._channels):
            return self._channels[row].number
        return None


class BankManagerDialog(wx.Dialog):
    """Filterable bank list with Rename and Show channels."""

    def __init__(self, parent, catalog, channels_by_position) -> None:
        super().__init__(
            parent,
            title="Manage banks",
            style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER,
        )
        self._catalog = catalog
        self._channels = channels_by_position
        self._banks = list(catalog.banks)
        self._filtered = list(self._banks)
        # Set instead of navigating inline: the caller must finish closing and
        # any grid rebuild before moving focus, or the rebuild discards it.
        self.goto_channel: int | None = None

        outer = wx.BoxSizer(wx.VERTICAL)
        self.intro = wx.StaticText(self, label=self._intro_text())
        outer.Add(self.intro, 0, wx.ALL, 8)

        outer.Add(wx.StaticText(self, label="Filter:"), 0, wx.LEFT | wx.TOP, 8)
        self.filter = wx.TextCtrl(self)
        self.filter.SetName("Bank filter")
        outer.Add(self.filter, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 8)

        outer.Add(wx.StaticText(self, label="Banks:"), 0, wx.LEFT | wx.TOP, 8)
        self.list = RadioListView(
            self,
            name="Bank",
            on_select=self._update_buttons,
            size=(420, 220),
        )
        self.list.Set([self._row_label(bank) for bank in self._filtered])
        if self._filtered:
            self.list.SetSelection(0)
        outer.Add(self.list, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 8)

        self.count = wx.StaticText(self, label=self._count_label(len(self._filtered)))
        self.count.SetName("Bank count")
        outer.Add(self.count, 0, wx.ALL, 8)

        row = wx.BoxSizer(wx.HORIZONTAL)
        self.rename_button = wx.Button(self, label="&Rename…")
        self.channels_button = wx.Button(self, label="&Show channels…")
        row.Add(self.rename_button, 0, wx.RIGHT, 8)
        row.Add(self.channels_button, 0, wx.RIGHT, 8)
        outer.Add(row, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)

        buttons = self.CreateStdDialogButtonSizer(wx.CANCEL)
        close = self.FindWindowById(wx.ID_CANCEL)
        if close:
            close.SetLabel("Close")
        outer.Add(buttons, 0, wx.ALIGN_RIGHT | wx.ALL, 8)

        self.SetSizerAndFit(outer)
        self.SetEscapeId(wx.ID_CANCEL)
        self.filter.Bind(wx.EVT_TEXT, lambda _event: self._apply_filter())
        self.filter.Bind(wx.EVT_KEY_DOWN, self._on_filter_key)
        self._update_buttons()
        self.filter.SetFocus()

    # -- labels -------------------------------------------------------

    def _intro_text(self) -> str:
        count = len(self._catalog.banks)
        banks = "1 bank" if count == 1 else f"{count} banks"
        if self._catalog.renameable:
            return f"This radio has {banks}. Bank names can be changed."
        return (
            f"This radio has {banks}. Bank names cannot be changed on this "
            "radio."
        )

    def _row_label(self, bank) -> str:
        channels = self._channels.get(bank.position, ())
        count = len(channels)
        suffix = "1 channel" if count == 1 else f"{count} channels"
        return f"{bank.label} — {suffix}"

    @staticmethod
    def _count_label(count: int) -> str:
        return "1 bank matches" if count == 1 else f"{count} banks match"

    # -- behaviour ----------------------------------------------------

    def _apply_filter(self) -> None:
        text = self.filter.GetValue().strip().lower()
        self._filtered = (
            [bank for bank in self._banks if text in self._row_label(bank).lower()]
            if text
            else list(self._banks)
        )
        self.list.Set([self._row_label(bank) for bank in self._filtered])
        if self._filtered:
            self.list.SetSelection(0)
        self.count.SetLabel(self._count_label(len(self._filtered)))
        self._update_buttons()

    def _on_filter_key(self, event) -> None:
        if event.GetKeyCode() == wx.WXK_DOWN and self._filtered:
            self.list.SetFocus()
            if self.list.GetSelection() == wx.NOT_FOUND:
                self.list.SetSelection(0)
        else:
            event.Skip()

    def _update_buttons(self) -> None:
        bank = self.get_bank()
        self.channels_button.Enable(bank is not None)
        self.rename_button.Enable(bank is not None and bank.renameable)

    def get_bank(self):
        row = self.list.GetSelection()
        if 0 <= row < len(self._filtered):
            return self._filtered[row]
        return None

    def channels_for(self, bank) -> tuple:
        """Channels already scanned for ``bank`` — no rescan per open."""
        return self._channels.get(bank.position, ())

    def refresh(self, catalog, channels_by_position) -> None:
        """Re-read after a rename, keeping the selected bank selected."""
        selected = self.get_bank()
        self._catalog = catalog
        self._channels = channels_by_position
        self._banks = list(catalog.banks)
        self.intro.SetLabel(self._intro_text())
        self._apply_filter()
        if selected is not None:
            for row, bank in enumerate(self._filtered):
                if bank.position == selected.position:
                    self.list.SetSelection(row)
                    break
        self._update_buttons()
