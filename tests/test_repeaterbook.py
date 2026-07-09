"""Tests for the RepeaterBook query source (chirp_backend/repeaterbook.py).

Pure backend — no GUI and no network. The geography helpers read CHIRP's own
lists; ``fetch`` is exercised with an injected fake source radio so nothing
touches data.chirpmyradio.com.
"""

from chirp_backend import repeaterbook as rb


# --- Geography --------------------------------------------------------------

def test_countries_sorted_and_include_na_and_row():
    countries = rb.countries()
    assert "United States" in countries
    assert "Canada" in countries
    assert "Germany" in countries  # a rest-of-world country
    assert countries == sorted(countries)


def test_states_for_us_include_oregon():
    states = rb.states("United States")
    assert "Oregon" in states
    assert rb.has_states("United States")


def test_states_empty_for_row_country():
    # Non-US/Canada/Mexico countries are fetched whole (keyed "all"), no states.
    assert rb.states("Germany") == []
    assert not rb.has_states("Germany")


def test_modes_are_chirps():
    assert set(rb.modes()) == {"FM", "DV", "DMR", "DN"}


# --- build_params -----------------------------------------------------------

REQUIRED_KEYS = {"lat", "lon", "dist", "openonly", "cached", "state", "country"}


def test_build_params_has_every_key_do_fetch_pops():
    # do_fetch pops these with no default; a missing one is a KeyError at fetch.
    params = rb.build_params("United States", "Oregon")
    assert REQUIRED_KEYS <= set(params)
    assert params["country"] == "United States"
    assert params["state"] == "Oregon"


def test_build_params_defaults_state_to_all():
    params = rb.build_params("Germany")
    assert params["state"] == "all"


def test_build_params_passthrough_filters():
    params = rb.build_params(
        "United States", "Oregon",
        filter_text="portland", open_only=True, modes=["FM"], bands=[(144_000_000, 148_000_000)],
    )
    assert params["filter"] == "portland"
    assert params["openonly"] is True
    assert params["modes"] == ["FM"]
    assert params["bands"] == [(144_000_000, 148_000_000)]


# --- fetch (fake radio, no network) -----------------------------------------

class _Features:
    def __init__(self, count):
        self.memory_bounds = (0, count - 1) if count else (0, -1)


class _FakeRadio:
    """Minimal stand-in for a fetched RepeaterBook source radio."""

    def __init__(self, count=0, fail=None, raises=None, statuses=None):
        self._count = count
        self._fail = fail
        self._raises = raises
        self._statuses = statuses or []
        self.received_params = None

    def do_fetch(self, status, params):
        self.received_params = params
        for msg, pct in self._statuses:
            status.send_status(msg, pct)
        if self._raises:
            raise self._raises
        if self._fail:
            status.send_fail(self._fail)
        else:
            status.send_end()

    def get_features(self):
        return _Features(self._count)


def test_fetch_success_reports_count():
    radio = _FakeRadio(count=3)
    ok, message, result = rb.fetch(rb.build_params("United States", "Oregon"), radio=radio)
    assert ok is True
    assert "3 repeater" in message
    assert result is radio


def test_fetch_zero_results_is_ok_but_empty():
    radio = _FakeRadio(count=0)
    ok, message, result = rb.fetch(rb.build_params("United States", "Oregon"), radio=radio)
    assert ok is True
    assert "No repeaters" in message
    assert result is radio


def test_fetch_server_failure_returns_reason():
    radio = _FakeRadio(fail="Got error code 500 from server")
    ok, message, result = rb.fetch(rb.build_params("United States", "Oregon"), radio=radio)
    assert ok is False
    assert "500" in message
    assert result is None


def test_fetch_exception_is_caught():
    radio = _FakeRadio(raises=RuntimeError("boom"))
    ok, message, result = rb.fetch(rb.build_params("United States", "Oregon"), radio=radio)
    assert ok is False
    assert "boom" in message
    assert result is None


def test_fetch_forwards_progress():
    seen = []
    radio = _FakeRadio(count=1, statuses=[("Downloading", 25), ("Parsing", 50)])
    rb.fetch(rb.build_params("United States", "Oregon"),
             progress_cb=lambda m, p: seen.append((m, p)), radio=radio)
    assert ("Downloading", 25) in seen
    assert ("Parsing", 50) in seen


def test_fetch_does_not_mutate_callers_params():
    radio = _FakeRadio(count=1)
    params = rb.build_params("United States", "Oregon")
    before = dict(params)
    rb.fetch(params, radio=radio)
    assert params == before  # do_fetch pops from a copy, not the caller's dict


class _Mem:
    def __init__(self, number, freq, name, comment="", mode="FM", empty=False):
        self.number = number
        self.freq = freq
        self.name = name
        self.comment = comment
        self.mode = mode
        self.empty = empty


class _ResultRadio:
    def __init__(self, mems):
        self._m = {m.number: m for m in mems}
        self._lo, self._hi = min(self._m), max(self._m)

    def get_features(self):
        lo, hi = self._lo, self._hi

        class F:
            memory_bounds = (lo, hi)

        return F()

    def get_memory(self, number):
        return self._m[number]


def test_describe_result_whole_mhz_and_fields():
    line = rb.describe_result(
        _Mem(0, 146_000_000, "COUNCIL", comment="KR7IS near Gaston, Oregon OPEN")
    )
    assert "146.000 MHz" in line  # whole MHz not truncated to "146"
    assert "FM" in line
    assert "COUNCIL" in line
    assert "Gaston" in line


def test_describe_result_handles_blank_name_and_comment():
    line = rb.describe_result(_Mem(0, 147_120_000, "", comment="", mode="DMR"))
    assert "147.12" in line
    assert "DMR" in line
    assert line  # never blank


def test_result_lines_skips_empty_and_keeps_order():
    radio = _ResultRadio([
        _Mem(0, 146_000_000, "A"),
        _Mem(1, 147_000_000, "", empty=True),
        _Mem(2, 145_000_000, "C"),
    ])
    lines = rb.result_lines(radio)
    assert [n for n, _ in lines] == [0, 2]  # empty #1 skipped, order preserved
    assert "A" in lines[0][1] and "C" in lines[1][1]


def test_gettext_shim_installed_by_fetch():
    import builtins

    had = hasattr(builtins, "_")
    try:
        rb.fetch(rb.build_params("United States", "Oregon"), radio=_FakeRadio(count=1))
        assert hasattr(builtins, "_")
        assert builtins._("x") == "x"
    finally:
        if not had and hasattr(builtins, "_"):
            del builtins._
