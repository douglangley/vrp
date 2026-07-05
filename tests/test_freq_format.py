"""Frequency display formatting (col_defs.format_freq_mhz + FrequencyColumn).

Regression for the "a channel just shows 146" bug: whole-MHz frequencies must
show at least 3 decimals ("146.000"), and nothing finer than that may be
truncated.
"""

from chirp_backend.col_defs import FrequencyColumn, format_freq_mhz


def test_whole_mhz_shows_three_decimals():
    # The reported bug: 146 MHz must read "146.000", not "146".
    assert format_freq_mhz(146_000_000) == "146.000"
    assert format_freq_mhz(440_000_000) == "440.000"


def test_kilohertz_precision_kept():
    assert format_freq_mhz(146_520_000) == "146.520"  # trailing zero to kHz kept
    assert format_freq_mhz(146_940_000) == "146.940"


def test_finer_than_khz_is_not_truncated():
    assert format_freq_mhz(146_012_500) == "146.0125"   # 12.5 kHz step
    assert format_freq_mhz(145_987_500) == "145.9875"
    assert format_freq_mhz(146_006_250) == "146.00625"  # 6.25 kHz step


def test_no_float_rounding_error():
    # 146.006250 would round badly through float MHz; the integer path is exact.
    assert format_freq_mhz(146_006_250).startswith("146.00625")


class _Mem:
    def __init__(self, freq, empty=False):
        self.freq = freq
        self.empty = empty


def test_frequency_column_uses_the_formatter():
    col = FrequencyColumn()
    assert col.format_value(_Mem(146_000_000)) == "146.000"
    assert col.format_value(_Mem(146_012_500)) == "146.0125"


def test_frequency_column_empty_and_zero_stay_blank():
    col = FrequencyColumn()
    assert col.format_value(_Mem(0, empty=True)) == ""
    assert col.format_value(_Mem(0)) == ""
