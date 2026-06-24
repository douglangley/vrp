"""Tests for the Download dialog's model filter (vrp.serial_dialogs.filter_models).

Pure function — no wx needed. Regression for the bug where typing 'uv5r' or
'UV5' returned nothing/the wrong models because the labels contain a hyphen
('Baofeng UV-5R') and the old filter did a raw substring match.
"""

from vrp.serial_dialogs import filter_models

MODELS = [
    {"id": "Baofeng_UV-5R", "label": "Baofeng UV-5R"},
    {"id": "Baofeng_UV-5R_Mini", "label": "Baofeng UV-5R Mini"},
    {"id": "Baojie_BJ-UV55", "label": "Baojie BJ-UV55"},
    {"id": "Yaesu_FT-60", "label": "Yaesu FT-60"},
]


def test_match_ignores_punctuation_between_query_and_label():
    labels = [m["label"] for m in filter_models(MODELS, "uv5r")]
    assert "Baofeng UV-5R" in labels          # hyphen no longer blocks it
    assert "Baofeng UV-5R Mini" in labels
    assert "Yaesu FT-60" not in labels


def test_match_is_case_insensitive():
    assert filter_models(MODELS, "UV5R") == filter_models(MODELS, "uv5r")


def test_multiple_terms_all_required():
    labels = [m["label"] for m in filter_models(MODELS, "baofeng 5r")]
    assert labels == ["Baofeng UV-5R", "Baofeng UV-5R Mini"]
    # Baojie has UV55 (not 5r) and isn't Baofeng -> excluded by the AND.
    assert "Baojie BJ-UV55" not in labels


def test_empty_query_returns_all():
    assert filter_models(MODELS, "") == MODELS
    assert filter_models(MODELS, "   ") == MODELS


def test_no_match_returns_empty():
    assert filter_models(MODELS, "icom") == []


def test_real_models_uv5r_matches_the_mini_and_more():
    # Guards against the real CHIRP labels regressing. Before the fix, 'uv5r'
    # matched zero real models and 'UV5' matched only 2 unrelated ones.
    import vrp  # noqa: F401 — applies the chirp sys.meta_path fix
    from chirp_backend import radio as radio_backend

    models = radio_backend.list_radio_models()
    uv5r_ids = [m["id"] for m in filter_models(models, "uv5r")]
    assert "Baofeng_UV-5R_Mini" in uv5r_ids
    assert len(uv5r_ids) >= 5
    # 'UV5' should now find many UV-5x models, not just 2.
    assert len(filter_models(models, "UV5")) > 2
