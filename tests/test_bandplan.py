"""Tests for the suggested-offset lookup derived from CHIRP's band plans
(chirp_backend/bandplan.py). Pure backend — no GUI needed."""

import pytest

from chirp_backend import bandplan


@pytest.fixture(autouse=True)
def _restore_region():
    """Keep region changes from leaking between tests (it's a module global)."""
    saved = bandplan.get_region()
    yield
    bandplan.set_region(saved)


def _mhz(mhz: float) -> int:
    return int(round(mhz * 1_000_000))


def test_standard_offsets_by_band():
    # The well-known amateur repeater shifts, magnitude only.
    assert bandplan.suggest_offset_hz(_mhz(146.94)) == 600_000      # 2 m
    assert bandplan.suggest_offset_hz(_mhz(147.30)) == 600_000      # 2 m
    assert bandplan.suggest_offset_hz(_mhz(442.50)) == 5_000_000    # 70 cm
    assert bandplan.suggest_offset_hz(_mhz(449.00)) == 5_000_000    # 70 cm
    assert bandplan.suggest_offset_hz(_mhz(224.00)) == 1_600_000    # 1.25 m
    assert bandplan.suggest_offset_hz(_mhz(52.525)) == 500_000      # 6 m


def test_whole_band_coverage_includes_simplex_portions():
    # Simplex frequencies still get the band's standard shift so the user can
    # flip duplex to +/- and have the right offset already there.
    assert bandplan.suggest_offset_hz(_mhz(146.52)) == 600_000   # 2 m simplex
    assert bandplan.suggest_offset_hz(_mhz(147.52)) == 600_000   # 2 m gap
    assert bandplan.suggest_offset_hz(_mhz(446.00)) == 5_000_000  # 70 cm simplex


def test_magnitude_is_always_non_negative():
    # We never return the band plan's signed offset — the user picks +/-.
    for mhz in (145.45, 146.94, 449.00, 224.00):
        assert bandplan.suggest_offset_hz(_mhz(mhz)) > 0


def test_no_suggestion_off_the_repeater_bands():
    assert bandplan.suggest_offset_hz(_mhz(7.25)) is None     # 40 m HF
    assert bandplan.suggest_offset_hz(_mhz(100.1)) is None    # FM broadcast
    assert bandplan.suggest_offset_hz(0) is None              # empty channel


def test_suggest_from_freq_string():
    assert bandplan.suggest_offset_for_freq_str("146.94") == 600_000
    assert bandplan.suggest_offset_for_freq_str(" 442.5 ") == 5_000_000
    assert bandplan.suggest_offset_for_freq_str("") is None
    assert bandplan.suggest_offset_for_freq_str("not a freq") is None


def test_offset_hz_to_mhz_str_matches_offset_column_format():
    assert bandplan.offset_hz_to_mhz_str(600_000) == "0.6"
    assert bandplan.offset_hz_to_mhz_str(5_000_000) == "5"
    assert bandplan.offset_hz_to_mhz_str(1_600_000) == "1.6"


def test_region_default_and_metadata():
    assert bandplan.get_region() == bandplan.DEFAULT_REGION == "north_america"
    codes = [c for c, _ in bandplan.REGIONS]
    assert "north_america" in codes and "iaru_r1" in codes
    assert bandplan.region_label("north_america") == "North America"
    assert bandplan.region_label("unknown") == "unknown"  # graceful fallback


def test_set_region_changes_suggestions():
    bandplan.set_region("north_america")
    assert bandplan.suggest_offset_hz(_mhz(51.0)) == 500_000   # NA 6 m = 0.5
    bandplan.set_region("australia")
    assert bandplan.get_region() == "australia"
    assert bandplan.suggest_offset_hz(_mhz(51.0)) == 1_000_000  # AU 6 m = 1.0


def test_set_region_ignores_unknown():
    bandplan.set_region("north_america")
    bandplan.set_region("atlantis")  # not a real plan
    assert bandplan.get_region() == "north_america"
