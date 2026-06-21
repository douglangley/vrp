"""Command metadata for the experimental Toga UI."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CommandSpec:
    id: str
    text: str
    handler: str
    group: str
    section: int
    order: int
    shortcut: str | None = None
    requires_radio: bool = False
    requires_prev_page: bool = False
    requires_next_page: bool = False
    tooltip: str | None = None


_COMMANDS: tuple[CommandSpec, ...] = (
    CommandSpec(
        id="open",
        text="Open Image File",
        handler="on_open",
        group="file",
        section=0,
        order=0,
        shortcut="mod+o",
        tooltip="Open a CHIRP radio image file.",
    ),
    CommandSpec(
        id="save",
        text="Save",
        handler="on_save",
        group="file",
        section=0,
        order=10,
        shortcut="mod+s",
        requires_radio=True,
        tooltip="Save the current radio image.",
    ),
    CommandSpec(
        id="save_as",
        text="Save As",
        handler="on_save_as",
        group="file",
        section=0,
        order=20,
        shortcut="mod+shift+s",
        requires_radio=True,
        tooltip="Save the current radio image to a new file.",
    ),
    CommandSpec(
        id="close",
        text="Close Image",
        handler="on_close_image",
        group="file",
        section=0,
        order=30,
        requires_radio=True,
        tooltip="Close the current radio image.",
    ),
    CommandSpec(
        id="page_prev",
        text="Previous Channel Page",
        handler="on_page_prev",
        group="channels",
        section=0,
        order=0,
        shortcut="mod+alt+left",
        requires_radio=True,
        requires_prev_page=True,
        tooltip="Show the previous page of channels.",
    ),
    CommandSpec(
        id="page_next",
        text="Next Channel Page",
        handler="on_page_next",
        group="channels",
        section=0,
        order=10,
        shortcut="mod+alt+right",
        requires_radio=True,
        requires_next_page=True,
        tooltip="Show the next page of channels.",
    ),
    CommandSpec(
        id="edit_channel",
        text="Edit Channel",
        handler="on_edit_channel",
        group="channels",
        section=1,
        order=0,
        requires_radio=True,
        tooltip="Edit the selected channel.",
    ),
    CommandSpec(
        id="find",
        text="Find",
        handler="on_find",
        group="channels",
        section=1,
        order=10,
        shortcut="mod+f",
        requires_radio=True,
        tooltip="Find a channel.",
    ),
    CommandSpec(
        id="find_next",
        text="Find Next",
        handler="on_find_next",
        group="channels",
        section=1,
        order=20,
        shortcut="mod+g",
        requires_radio=True,
        tooltip="Find the next matching channel.",
    ),
    CommandSpec(
        id="operations",
        text="Organize Channels",
        handler="on_operations",
        group="channels",
        section=1,
        order=30,
        shortcut="mod+m",
        requires_radio=True,
        tooltip="Move, copy, sort, or delete channels.",
    ),
    CommandSpec(
        id="shortcuts",
        text="Keyboard Shortcuts",
        handler="on_shortcuts",
        group="help",
        section=0,
        order=0,
        shortcut="f1",
        tooltip="Show available keyboard shortcuts.",
    ),
)


def all_command_specs() -> tuple[CommandSpec, ...]:
    return _COMMANDS


def command_enabled(
    spec: CommandSpec,
    radio_loaded: bool,
    *,
    has_prev: bool = True,
    has_next: bool = True,
) -> bool:
    if spec.requires_radio and not radio_loaded:
        return False
    if spec.requires_prev_page and not has_prev:
        return False
    if spec.requires_next_page and not has_next:
        return False
    return True
