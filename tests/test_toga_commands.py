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


def test_shortcuts_avoid_single_letter_table_commands():
    specs = all_command_specs()

    for spec in specs:
        if spec.shortcut is None:
            continue
        assert "+" in spec.shortcut, spec
        assert not spec.shortcut.lower().startswith("alt+"), spec
