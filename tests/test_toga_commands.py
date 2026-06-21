from vrp_toga.commands import all_command_specs, command_enabled


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
        "operations": "mod+m",
        "shortcuts": "f1",
    }


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
