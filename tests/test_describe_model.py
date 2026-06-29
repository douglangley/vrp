"""Tests for the per-model description (chirp_backend.radio.describe_model)."""

import vrp  # noqa: F401 — applies the chirp sys.meta_path fix
from chirp_backend import radio as radio_backend


def test_describe_model_includes_capabilities():
    text = radio_backend.describe_model("Baofeng_UV-5R")
    assert "Baofeng UV-5R" in text
    assert "Channels:" in text
    assert "Capabilities" in text
    assert "Modes:" in text


def test_describe_model_omits_clone_prompts():
    # The pre-download dialog already shows these; they'd just be noise here.
    text = radio_backend.describe_model("Baofeng_UV-5R")
    assert "Before downloading" not in text
    assert "Experimental driver" not in text


def test_describe_model_includes_the_extra_spec_fields():
    text = radio_backend.describe_model("Baofeng_UV-5R")
    assert "Name length" in text or "up to 7 characters" in text
    assert "Tone modes:" in text
    assert "Power levels:" in text and "dBm" in text  # repr includes the dBm
    assert "Tuning steps:" in text and "kHz" in text


def test_describe_features_optional_fields_omitted_when_absent():
    # A minimal stub with none of the optional fields -> no crash, no extra lines.
    class _Min:
        memory_bounds = (1, 10)
        has_name = False
        valid_special_chans = []
        valid_tmodes = [""]          # only the blank "none" -> skipped
        valid_power_levels = []
        valid_tuning_steps = []
        valid_bands = []
        valid_modes = ["FM"]

    lines = radio_backend.describe_features(_Min())
    text = "\n".join(lines)
    assert "Channel names:    No" in text
    assert "Power levels" not in text
    assert "Tone modes" not in text
    assert "Tuning steps" not in text


def test_describe_model_unknown_id_is_graceful():
    text = radio_backend.describe_model("Definitely_Not_A_Driver")
    assert "No information" in text
