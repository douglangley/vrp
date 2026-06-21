"""Experimental BeeWare Toga application shell for VRP."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import toga
from toga.sources import AccessorColumn, ListSource
from toga.style import Pack
from toga.style.pack import COLUMN, ROW

from chirp_backend import radio as radio_backend

from vrp import __version__
from vrp.config import get_config
from vrp.speech import Speaker
from vrp_toga.commands import CommandSpec, all_command_specs, command_enabled
from vrp_toga.table_model import TablePage, build_table_page

APP_TITLE = "Versatile Radio Programmer Toga Prototype"
ATTRIBUTION = "Radio driver support provided by the CHIRP project — chirpmyradio.com."
IMAGE_TYPES = ["img"]
CHANNELS_GROUP = toga.Group("Channels", order=30)


class VRPTogaApp(toga.App):
    """Parallel native Toga prototype. The wx app remains the production UI."""

    def startup(self) -> None:
        self.speaker = Speaker()
        # Toga has no live-region wrapper yet, so prototype status speech defaults on.
        self._speak_enabled = bool(
            get_config().get("toga_speak_status_messages", True)
        )
        self._page = 1
        self._last_table_page = build_table_page(self._page)
        self._commands_by_id: dict[str, toga.Command] = {}

        self.main_window = toga.MainWindow(title=APP_TITLE, size=(1200, 800))
        self.main_window.content = self._build_content(self._last_table_page)
        self._install_commands()
        self._refresh_command_state()
        self.main_window.show()

    def _build_content(self, table_page: TablePage) -> toga.Box:
        self.heading = toga.Label(
            "Versatile Radio Programmer",
            id="toga-heading",
            style=Pack(margin_bottom=8),
        )
        self.radio_label = toga.Label(
            table_page.radio_label,
            id="toga-radio-label",
            style=Pack(margin_bottom=8),
        )
        self.status_label = toga.Label(
            table_page.status,
            id="toga-status",
            style=Pack(margin_bottom=8),
        )

        self.open_button = toga.Button(
            "Open Image File",
            on_press=self.on_open,
            id="open-button",
        )
        self.save_button = toga.Button(
            "Save",
            on_press=self.on_save,
            id="save-button",
        )
        self.prev_button = toga.Button(
            "Previous Page",
            on_press=self.on_page_prev,
            id="prev-page-button",
        )
        self.next_button = toga.Button(
            "Next Page",
            on_press=self.on_page_next,
            id="next-page-button",
        )
        self.edit_button = toga.Button(
            "Edit Channel",
            on_press=self.on_edit_channel,
            id="edit-channel-button",
        )
        self.shortcuts_button = toga.Button(
            "Keyboard Shortcuts",
            on_press=self.on_shortcuts,
            id="shortcuts-button",
        )

        button_row = toga.Box(
            children=[
                self.open_button,
                self.save_button,
                self.prev_button,
                self.next_button,
                self.edit_button,
                self.shortcuts_button,
            ],
            style=Pack(direction=ROW, gap=8, margin_bottom=8),
        )

        visible_accessors = table_page.accessors[: len(table_page.columns)]
        visible_columns = AccessorColumn.columns_from_headings_and_accessors(
            table_page.columns,
            visible_accessors,
        )
        table_data = ListSource(accessors=table_page.accessors, data=table_page.rows)
        self.table = toga.Table(
            columns=visible_columns,
            data=table_data,
            missing_value="",
            multiple_select=False,
            on_select=self.on_table_select,
            on_activate=self.on_table_activate,
            id="channel-table",
            style=Pack(flex=1),
        )

        self.attribution = toga.Label(
            ATTRIBUTION,
            id="chirp-attribution",
            style=Pack(margin_top=8),
        )

        return toga.Box(
            children=[
                self.heading,
                self.radio_label,
                self.status_label,
                button_row,
                self.table,
                self.attribution,
            ],
            style=Pack(direction=COLUMN, margin=12),
        )

    def _install_commands(self) -> None:
        loaded = radio_backend.get_state().loaded
        for spec in all_command_specs():
            command = toga.Command(
                action=getattr(self, spec.handler),
                text=spec.text,
                shortcut=self._toga_shortcut(spec),
                tooltip=spec.tooltip,
                group=self._toga_group(spec.group),
                section=spec.section,
                order=spec.order,
                enabled=command_enabled(
                    spec,
                    loaded,
                    has_prev=self._last_table_page.has_prev,
                    has_next=self._last_table_page.has_next,
                ),
                id=f"vrp_toga.{spec.id}",
            )
            self.commands.add(command)
            self._commands_by_id[spec.id] = command

    @staticmethod
    def _toga_group(name: str) -> toga.Group:
        if name == "file":
            return toga.Group.FILE
        if name == "help":
            return toga.Group.HELP
        if name == "channels":
            return CHANNELS_GROUP
        raise ValueError(f"Unknown Toga command group: {name}")

    @staticmethod
    def _toga_shortcut(spec: CommandSpec):
        shortcuts = {
            "mod+o": toga.Key.MOD_1 + "o",
            "mod+s": toga.Key.MOD_1 + "s",
            "mod+shift+s": toga.Key.MOD_1 + toga.Key.SHIFT + "s",
            "mod+alt+left": toga.Key.MOD_1 + toga.Key.MOD_2 + toga.Key.LEFT,
            "mod+alt+right": toga.Key.MOD_1 + toga.Key.MOD_2 + toga.Key.RIGHT,
            "mod+shift+m": toga.Key.MOD_1 + toga.Key.SHIFT + "m",
            "mod+f": toga.Key.MOD_1 + "f",
            "mod+g": toga.Key.MOD_1 + "g",
            "f1": toga.Key.F1,
        }
        if spec.shortcut is None:
            return None
        try:
            return shortcuts[spec.shortcut]
        except KeyError as exc:
            raise ValueError(f"Unknown Toga shortcut: {spec.shortcut}") from exc

    def _refresh_command_state(self) -> None:
        loaded = radio_backend.get_state().loaded
        has_prev = self._last_table_page.has_prev
        has_next = self._last_table_page.has_next
        for spec in all_command_specs():
            self._commands_by_id[spec.id].enabled = command_enabled(
                spec,
                loaded,
                has_prev=has_prev,
                has_next=has_next,
            )
        self.save_button.enabled = loaded
        self.prev_button.enabled = loaded and has_prev
        self.next_button.enabled = loaded and has_next
        self.edit_button.enabled = loaded

    def _refresh_table(self) -> None:
        table_page = build_table_page(self._page)
        self._last_table_page = table_page
        self._page = table_page.page

        # Table schema is fixed at construction, so rebuild on every refresh.
        self.main_window.content = self._build_content(table_page)
        self._set_status(table_page.status)
        self._refresh_command_state()
        if table_page.rows:
            self.table.scroll_to_top()

    def _set_status(self, message: str) -> None:
        self.status_label.text = message
        if self._speak_enabled:
            self.speaker.speak(message)

    def _run_dialog(self, dialog_task) -> None:
        asyncio.create_task(dialog_task)

    def on_open(self, widget, **kwargs) -> None:
        self._run_dialog(self._open_image())

    async def _open_image(self) -> None:
        path = await self.main_window.dialog(
            toga.OpenFileDialog(
                "Open radio image",
                file_types=IMAGE_TYPES,
                multiple_select=False,
            )
        )
        if path is None:
            self._set_status("Open image cancelled.")
            return

        ok, message = radio_backend.load_image(str(path))
        if ok:
            get_config().add_recent(str(path))
            self._page = 1
            self._refresh_table()
        self._set_status(message)
        if not ok:
            await self.main_window.dialog(toga.ErrorDialog("Open failed", message))

    def on_save(self, widget, **kwargs) -> None:
        state = radio_backend.get_state()
        if state.loaded and not state.image_path:
            self.on_save_as(widget, **kwargs)
            return

        ok, message = radio_backend.save_image()
        self._set_status(message)
        if not ok:
            self._run_dialog(
                self.main_window.dialog(toga.ErrorDialog("Save failed", message))
            )

    def on_save_as(self, widget, **kwargs) -> None:
        self._run_dialog(self._save_as())

    async def _save_as(self) -> None:
        state = radio_backend.get_state()
        suggested = Path(state.image_path).name if state.image_path else "radio.img"
        path = await self.main_window.dialog(
            toga.SaveFileDialog(
                "Save radio image as",
                suggested_filename=suggested,
                file_types=IMAGE_TYPES,
            )
        )
        if path is None:
            self._set_status("Save as cancelled.")
            return

        ok, message = radio_backend.save_image(str(path))
        self._set_status(message)
        if ok:
            get_config().add_recent(str(path))
        else:
            await self.main_window.dialog(toga.ErrorDialog("Save failed", message))

    def on_close_image(self, widget, **kwargs) -> None:
        if not radio_backend.get_state().loaded:
            self._set_status("No radio image is open.")
            return

        radio_backend.unload()
        self._page = 1
        self._refresh_table()
        self._set_status("Closed radio image.")

    def on_page_prev(self, widget, **kwargs) -> None:
        if not radio_backend.get_state().loaded:
            self._set_status("No radio image is open.")
            return
        if not self._last_table_page.has_prev:
            self._set_status(
                f"Already on the first page. Page {self._page} of "
                f"{self._last_table_page.total_pages}."
            )
            return

        self._page -= 1
        self._refresh_table()

    def on_page_next(self, widget, **kwargs) -> None:
        if not radio_backend.get_state().loaded:
            self._set_status("No radio image is open.")
            return
        if not self._last_table_page.has_next:
            self._set_status(
                f"Already on the last page. Page {self._page} of "
                f"{self._last_table_page.total_pages}."
            )
            return

        self._page += 1
        self._refresh_table()

    def _selected_channel_number(self) -> int | None:
        row = self.table.selection
        if row is None:
            return None
        value = self._row_value(row, "channel_number")
        if value is None:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _row_value(row: Any, key: str) -> Any:
        if isinstance(row, dict):
            return row.get(key)
        value = getattr(row, key, None)
        if value is not None:
            return value
        try:
            return row[key]
        except (KeyError, TypeError, IndexError):
            return None

    def on_table_select(self, widget, **kwargs) -> None:
        number = self._selected_channel_number()
        if number is not None:
            self._set_status(f"Selected channel {number}.")

    def on_table_activate(self, widget, row=None, **kwargs) -> None:
        self.on_edit_channel(widget)

    def on_edit_channel(self, widget, **kwargs) -> None:
        if not radio_backend.get_state().loaded:
            self._set_status("No radio image is open.")
            return

        number = self._selected_channel_number()
        if number is None:
            self._set_status("Select a channel before editing.")
            return

        self._set_status(
            f"Edit channel {number} is not available in this Toga prototype."
        )

    def on_find(self, widget, **kwargs) -> None:
        if not radio_backend.get_state().loaded:
            self._set_status("No radio image is open.")
            return
        self._set_status("Find is not available in this Toga prototype.")

    def on_find_next(self, widget, **kwargs) -> None:
        if not radio_backend.get_state().loaded:
            self._set_status("No radio image is open.")
            return
        self._set_status("Find next is not available in this Toga prototype.")

    def on_operations(self, widget, **kwargs) -> None:
        if not radio_backend.get_state().loaded:
            self._set_status("No radio image is open.")
            return
        self._set_status("Organize channels is not available in this Toga prototype.")

    def on_shortcuts(self, widget, **kwargs) -> None:
        lines = []
        for spec in all_command_specs():
            shortcut = spec.shortcut or "menu or button"
            lines.append(f"{spec.text}: {shortcut}")
        self._run_dialog(
            self.main_window.dialog(
                toga.InfoDialog("Keyboard Shortcuts", "\n".join(lines))
            )
        )


def main() -> None:
    app = VRPTogaApp(
        formal_name=APP_TITLE,
        app_id="online.techopolis.vrp.toga",
        version=__version__,
    )
    app.main_loop()
