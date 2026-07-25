"""Plain-language help for radio settings: lookup, priority, and honesty."""

import os

import pytest

from chirp_backend import settings_help


IMAGES = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "chirp", "tests", "images")
)


def test_normalize_strips_group_paths_indices_and_punctuation():
    assert settings_help.normalize("settings.beep") == "beep"
    assert settings_help.normalize("pttid/3.code") == "code"
    assert settings_help.normalize("vfo.a.freq") == "freq"
    assert settings_help.normalize("beep_key") == "beepkey"
    assert settings_help.normalize("poweron_msg.line1") == "line"
    assert settings_help.normalize("") == ""
    assert settings_help.normalize(None) == ""


def test_the_same_feature_is_found_however_a_driver_spells_it():
    baseline = settings_help.lookup("squelch")
    assert baseline
    for spelling in ("sql", "squelchlevel", "settings.squelch", "SQUELCH"):
        assert settings_help.lookup(spelling) == baseline


def test_aliases_reach_the_shared_description():
    assert settings_help.lookup("timeouttimer") == settings_help.lookup("tot")
    assert settings_help.lookup("voxlevel") == settings_help.lookup("vox")
    assert settings_help.lookup("bclo") == settings_help.lookup("bcl")
    assert settings_help.lookup("lamp") == settings_help.lookup("backlight")


def test_unknown_settings_return_none_rather_than_a_guess():
    assert settings_help.lookup("wibble_frobnicator") is None
    assert settings_help.lookup("") is None


def test_table_row_fields_are_deliberately_not_described():
    """DTMF slots and FM presets are data rows, not features to explain."""
    for name in ("pttid/3.code", "dtmf_5", "poweron_msg.line1"):
        assert settings_help.lookup(name) is None


def test_driver_documentation_wins_over_the_generic_table():
    generic = settings_help.lookup("squelch")
    specific = "This radio mutes below level 4."

    assert settings_help.help_for("squelch", specific) == specific
    assert settings_help.help_for("squelch", None) == generic
    assert settings_help.help_for("squelch", "") == generic


def test_driver_documentation_is_collapsed_to_one_line():
    assert settings_help.help_for("anything", "line one\n   line  two") == (
        "line one line two"
    )


def test_every_alias_points_at_a_real_entry():
    for alias, target in settings_help.ALIASES.items():
        assert target in settings_help.HELP, f"{alias} -> missing {target}"


def test_no_alias_shadows_a_real_entry():
    overlap = set(settings_help.ALIASES) & set(settings_help.HELP)
    assert not overlap, f"alias also defined in HELP: {sorted(overlap)}"


def test_keys_are_already_normalized():
    for key in list(settings_help.HELP) + list(settings_help.ALIASES):
        assert settings_help.normalize(key) == key, f"{key} is not normalized"


def test_descriptions_are_sentences_not_restated_labels():
    for key, text in settings_help.HELP.items():
        assert len(text) > 40, f"{key} description is too short to help"
        assert text[0].isupper(), f"{key} description should start a sentence"
        assert text.rstrip().endswith("."), f"{key} description needs a full stop"


def test_coverage_reports_described_and_total():
    described, total = settings_help.coverage(["squelch", "wibble", "tot"])
    assert (described, total) == (2, 3)


@pytest.mark.parametrize(
    "image,minimum",
    [
        ("Yaesu_FT-60.img", 0.5),
        ("Baofeng_BF-F8HP-PRO.img", 0.15),
    ],
)
def test_real_radios_get_a_useful_share_of_their_settings_described(image, minimum):
    """A floor, not a target — it should fail loudly if lookups regress."""
    from chirp import directory

    from chirp_backend.radio import _ensure_chirp

    _ensure_chirp()
    path = os.path.join(IMAGES, image)
    if not os.path.exists(path):
        pytest.skip(f"{image} is not in the pinned corpus")
    radio = directory.get_radio_by_image(path)

    names = []

    def walk(group):
        for item in group:
            try:
                name = item.get_name()
            except Exception:  # noqa: BLE001
                continue
            if not (hasattr(item, "__iter__") and not hasattr(item, "value")):
                names.append(name)
            if hasattr(item, "__iter__"):
                try:
                    walk(item)
                except Exception:  # noqa: BLE001
                    pass

    walk(radio.get_settings())
    described, total = settings_help.coverage(names)
    assert total, "fixture exposed no settings"
    assert described / total >= minimum, (
        f"{image}: only {described}/{total} settings described"
    )
