"""A reusable read-only text dialog for reviewing information.

Why an edit box and not a ``wx.MessageBox``: a message box reads its static text
once and a screen-reader user can't navigate it — you can't arrow back through it
line by line, re-read a value, or copy it. A read-only multiline ``wx.TextCtrl``
is a real text field: NVDA/VoiceOver let you move by line/word/character, re-read
on demand, and Ctrl+C the contents. Focus lands in the text on open, at the top.
"""

from __future__ import annotations

import wx


class InfoDialog(wx.Dialog):
    """Modal dialog showing ``text`` in a read-only, multiline, copyable edit box
    plus a Close button. Escape closes; focus opens in the text at line 1."""

    def __init__(self, parent, title: str, text: str, *,
                 name: str = "Information", size=(520, 360),
                 ok_button: bool = False) -> None:
        super().__init__(parent, title=title,
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)

        # Errors/confirmations read more naturally with an "OK" button; reviewing
        # dialogs (Radio Info, Radio details) use "Close". Either way Escape and
        # the button dismiss it, and focus opens in the copyable text.
        button_id = wx.ID_OK if ok_button else wx.ID_CLOSE
        button_flag = wx.OK if ok_button else wx.CLOSE

        outer = wx.BoxSizer(wx.VERTICAL)
        # TE_READONLY still allows caret navigation, selection, and copy — it
        # only blocks editing, which is what we want for review.
        self.text = wx.TextCtrl(
            self, value=text,
            style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_WORDWRAP,
            size=size,
        )
        self.text.SetName(name)
        outer.Add(self.text, 1, wx.EXPAND | wx.ALL, 10)
        outer.Add(self.CreateButtonSizer(button_flag), 0, wx.EXPAND | wx.ALL, 8)

        self.SetSizerAndFit(outer)
        self.SetEscapeId(button_id)  # Escape dismisses
        self.Bind(wx.EVT_BUTTON, lambda _e: self.EndModal(button_id), id=button_id)
        self.Bind(wx.EVT_INIT_DIALOG, self._on_init_dialog)

    def _on_init_dialog(self, event) -> None:
        event.Skip()  # let wx's default focus run first, then override it
        wx.CallAfter(self._focus_text)

    def _focus_text(self) -> None:
        self.text.SetFocus()
        self.text.SetInsertionPoint(0)  # land at the top, not the end
