# Toga Accessibility Checklist

This checklist is required before the Toga prototype can replace any wxPython
workflow. The wxPython app remains the accessibility baseline.

## Environment

- Platform:
- Toga backend:
- Screen reader:
- Radio image used:
- Tester:
- Date:

## Launch And Window

- [ ] `uv run --extra toga python main_toga.py` launches without replacing the wx app.
- [ ] Screen reader announces the window title as "Versatile Radio Programmer Toga Prototype".
- [ ] Keyboard focus starts on a useful control or reaches one with Tab.
- [ ] The required CHIRP attribution is visible and reachable.

## Commands

- [ ] Open Image File is reachable from menu and button.
- [ ] Save is disabled or unavailable before a radio is loaded.
- [ ] Previous Page and Next Page are disabled or unavailable before a radio is loaded.
- [ ] Keyboard Shortcuts opens a readable dialog.
- [ ] Organize Channels does not conflict with system shortcuts on the tested platform.
- [ ] No table workflow requires a single-letter shortcut.

## Table

- [ ] After opening an image, the table announces column headers.
- [ ] The table exposes channel number, empty state, and field values.
- [ ] Empty channels are announced with the text "(empty)".
- [ ] Row selection announces enough context to identify the channel.
- [ ] Page changes announce the visible channel range and page number.
- [ ] Large images remain responsive when moving between pages.

## Dialogs And Status

- [ ] File-open cancel returns focus and announces cancellation.
- [ ] File-open errors show an error dialog and announce the error.
- [ ] Save and Save As announce success or failure.
- [ ] Dialogs prevent interaction with the main window while open.
- [ ] Dialog dismissal returns focus to a useful control.

## Result

- [ ] Pass: Toga table behavior is acceptable for the tested screen reader.
- [ ] Fail: Record table/header/focus gaps below before proposing fallback UI.

## Notes
