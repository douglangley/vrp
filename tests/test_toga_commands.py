from types import SimpleNamespace
import asyncio

from vrp.config import get_config
from vrp_toga.commands import all_command_specs, command_enabled


def _toga_app_module(monkeypatch):
    monkeypatch.setenv("TOGA_BACKEND", "toga_dummy")
    from vrp_toga import app as appmod

    return appmod


def _run_startup_without_gui(monkeypatch):
    appmod = _toga_app_module(monkeypatch)

    class SpeakerStub:
        def speak(self, message):
            raise AssertionError(f"startup should not speak: {message}")

    monkeypatch.setattr(appmod, "Speaker", SpeakerStub)
    monkeypatch.setattr(
        appmod,
        "build_table_page",
        lambda page: SimpleNamespace(status="Ready."),
    )
    monkeypatch.setattr(
        appmod.VRPTogaApp, "_build_content", lambda self, page: appmod.toga.Box()
    )
    monkeypatch.setattr(appmod.VRPTogaApp, "_install_commands", lambda self: None)
    monkeypatch.setattr(appmod.VRPTogaApp, "_refresh_command_state", lambda self: None)

    app = appmod.VRPTogaApp(
        formal_name=appmod.APP_TITLE,
        app_id="online.techopolis.vrp.toga.test",
    )
    app.startup()
    return app


def test_command_ids_are_unique_and_cover_first_slice():
    specs = all_command_specs()
    ids = [spec.id for spec in specs]

    assert len(ids) == len(set(ids))
    assert {
        "open",
        "save",
        "save_as",
        "close",
        "page_prev",
        "page_next",
        "edit_channel",
        "find",
        "find_next",
        "operations",
        "shortcuts",
    } <= set(ids)


def test_loaded_radio_commands_are_gated():
    by_id = {spec.id: spec for spec in all_command_specs()}

    assert command_enabled(by_id["open"], radio_loaded=False)
    assert command_enabled(by_id["shortcuts"], radio_loaded=False)
    assert not command_enabled(by_id["save"], radio_loaded=False)
    assert not command_enabled(by_id["page_next"], radio_loaded=False)
    assert command_enabled(by_id["save"], radio_loaded=True)
    assert command_enabled(by_id["page_next"], radio_loaded=True)


def test_expected_command_shortcuts_are_declared():
    by_id = {spec.id: spec for spec in all_command_specs()}

    assert {
        command_id: spec.shortcut
        for command_id, spec in by_id.items()
        if spec.shortcut is not None
    } == {
        "open": "mod+o",
        "save": "mod+s",
        "save_as": "mod+shift+s",
        "page_prev": "mod+alt+left",
        "page_next": "mod+alt+right",
        "find": "mod+f",
        "find_next": "mod+g",
        "operations": "mod+shift+m",
        "shortcuts": "f1",
    }


def test_toga_shortcut_translates_shift_modified_operations_shortcut(monkeypatch):
    appmod = _toga_app_module(monkeypatch)
    by_id = {spec.id: spec for spec in all_command_specs()}

    assert appmod.VRPTogaApp._toga_shortcut(by_id["operations"]) == (
        appmod.toga.Key.MOD_1 + appmod.toga.Key.SHIFT + "m"
    )


def test_toga_status_speech_defaults_on_without_live_region(monkeypatch):
    app = _run_startup_without_gui(monkeypatch)

    assert app._speak_enabled is True


def test_toga_status_speech_uses_toga_specific_config_key(monkeypatch):
    get_config().set("speak_status_messages", True)
    get_config().set("toga_speak_status_messages", False)

    app = _run_startup_without_gui(monkeypatch)

    assert app._speak_enabled is False


def test_shortcuts_avoid_bare_single_letters():
    specs = all_command_specs()

    for spec in specs:
        if spec.shortcut is None:
            continue
        assert len(spec.shortcut) != 1 or not spec.shortcut.isalpha(), spec
        assert not spec.shortcut.lower().startswith("alt+"), spec


def test_page_commands_respect_boundary_availability():
    by_id = {spec.id: spec for spec in all_command_specs()}

    assert not command_enabled(by_id["page_prev"], radio_loaded=True, has_prev=False)
    assert not command_enabled(by_id["page_next"], radio_loaded=True, has_next=False)
    assert command_enabled(by_id["page_prev"], radio_loaded=True, has_prev=True)
    assert command_enabled(by_id["page_next"], radio_loaded=True, has_next=True)


def test_toga_image_dialogs_do_not_filter_by_extension(monkeypatch):
    appmod = _toga_app_module(monkeypatch)
    app = _run_startup_without_gui(monkeypatch)

    captured_dialogs = []

    class FakeOpenFileDialog:
        def __init__(self, title, file_types=None, multiple_select=False):
            self.title = title
            self.file_types = file_types
            self.multiple_select = multiple_select

    class FakeSaveFileDialog:
        def __init__(self, title, suggested_filename=None, file_types=None):
            self.title = title
            self.suggested_filename = suggested_filename
            self.file_types = file_types

    monkeypatch.setattr(appmod.toga, "OpenFileDialog", FakeOpenFileDialog)
    monkeypatch.setattr(appmod.toga, "SaveFileDialog", FakeSaveFileDialog)

    async def fake_dialog(dialog):
        captured_dialogs.append(dialog)
        return None

    app._speak_enabled = False
    app._set_status = lambda message: None
    monkeypatch.setattr(app.main_window, "dialog", fake_dialog)

    asyncio.run(app._open_image())
    asyncio.run(app._save_as())

    assert [dialog.file_types for dialog in captured_dialogs] == [None, None]


def test_toga_content_includes_a_short_welcome_label(monkeypatch):
    appmod = _toga_app_module(monkeypatch)
    app = appmod.VRPTogaApp(
        formal_name=appmod.APP_TITLE,
        app_id="online.techopolis.vrp.toga.test",
    )

    page = SimpleNamespace(
        radio_label="No radio loaded",
        status="Ready.",
        columns=["Ch #", "State"],
        accessors=["number", "state", "channel_number", "empty"],
        rows=[],
    )

    content = app._build_content(page)

    assert content.children[1].text == (
        "Welcome. Open a CHIRP radio image to review channels."
    )


def test_shortcut_label_is_human_readable(monkeypatch):
    appmod = _toga_app_module(monkeypatch)

    assert appmod.VRPTogaApp._shortcut_label("mod+alt+left", platform="darwin") == (
        "Command+Option+Left Arrow"
    )
    assert appmod.VRPTogaApp._shortcut_label("mod+shift+m", platform="win32") == (
        "Ctrl+Shift+M"
    )
    assert appmod.VRPTogaApp._shortcut_label("f1", platform="linux") == "F1"


def test_shortcuts_dialog_uses_readable_labels(monkeypatch):
    appmod = _toga_app_module(monkeypatch)
    app = appmod.VRPTogaApp(
        formal_name=appmod.APP_TITLE,
        app_id="online.techopolis.vrp.toga.test",
    )

    captured = []

    class FakeInfoDialog:
        def __init__(self, title, message):
            self.title = title
            self.message = message

    monkeypatch.setattr(appmod.toga, "InfoDialog", FakeInfoDialog)
    monkeypatch.setattr(appmod.sys, "platform", "darwin")
    app._main_window = SimpleNamespace(dialog=lambda dialog: dialog)
    app._run_dialog = captured.append

    app.on_shortcuts(None)

    assert len(captured) == 1
    dialog = captured[0]
    assert dialog.title == "Keyboard Shortcuts"
    assert "mod+" not in dialog.message
    assert "Command+Option+Left Arrow" in dialog.message
    assert "Command+Shift+M" in dialog.message
