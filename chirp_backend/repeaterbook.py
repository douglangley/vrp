"""RepeaterBook query source — purpose-built for VRP.

Fetches repeater listings and turns them into importable channels (via
:func:`chirp_backend.memory_ops.import_memories`, the same path Import-from-File
uses).

**Data path (today): CHIRP's mirror.** We wrap CHIRP's tested
``chirp.sources.repeaterbook.RepeaterBook`` source, which does *not* query
RepeaterBook's API directly. It downloads pre-built, state/country-cached,
xz-compressed JSON dumps from CHIRP's own server
(``https://data.chirpmyradio.com/rb/``) using the generic ``CHIRP/<ver>``
User-Agent. So this path needs **no RepeaterBook credential or custom
User-Agent** — it works today for testing while we wait on RepeaterBook to
issue VRP its own per-application User-Agent.

**Seam for the direct RepeaterBook API.** When RepeaterBook grants VRP a
User-Agent, set :data:`USER_AGENT` and override ``get_data`` on
:class:`VRPRepeaterBook` to hit RepeaterBook's endpoint with that header
instead of the mirror. Everything above ``get_data`` (the filtering, the
``item_to_memory`` conversion, ``do_fetch``) is reused unchanged — the swap is
localized to one method.

All chirp imports are lazy (mirroring ``chirp_backend.radio``) so importing this
module never forces the CHIRP library to load.
"""

from __future__ import annotations

import logging
from typing import Callable, Optional

LOG = logging.getLogger(__name__)

# The per-application User-Agent RepeaterBook requires for *direct* API access.
# None until they issue it; while it is None we use CHIRP's mirror (which needs
# no credential — see the module docstring). This is the flag the direct-API
# override keys off of.
USER_AGENT: Optional[str] = None

# Progress callback: (message, percent) -> None. percent is 0..100 (or None).
ProgressCallback = Callable[[str, "Optional[float]"], None]


def _install_gettext_shim() -> None:
    """Ensure the gettext builtin ``_`` exists before a fetch.

    ``RepeaterBook.do_fetch`` calls ``_('No results!')`` directly. CHIRP's own
    CLI/GUI install ``_`` before using drivers; running headless we must too or
    that call raises ``NameError``. Identity = no translation, the same shim
    ``chirp_backend.radio._ensure_chirp`` installs. Guarded so a real
    translation install is never clobbered. (A network query needs none of the
    552 drivers, so we install just the shim rather than loading all of CHIRP.)
    """
    import builtins

    if not hasattr(builtins, "_"):
        builtins._ = lambda s: s  # type: ignore[attr-defined]


_radio_cls = None


def _radio_class():
    """Return VRP's RepeaterBook source class (cached; chirp import is lazy)."""
    global _radio_cls
    if _radio_cls is None:
        from chirp.sources import repeaterbook

        class VRPRepeaterBook(repeaterbook.RepeaterBook):
            """VRP's RepeaterBook source.

            Currently identical to CHIRP's: fetches from CHIRP's mirror with the
            generic CHIRP User-Agent. Override ``get_data`` here for the direct
            RepeaterBook API once :data:`USER_AGENT` is set (see module docstring).
            """

        _radio_cls = VRPRepeaterBook
    return _radio_cls


def _make_radio():
    return _radio_class()()


# --- Geography (single source of truth: CHIRP's own lists) -----------------

def countries() -> list[str]:
    """All selectable countries, sorted (CHIRP's ``COUNTRIES``)."""
    from chirp.sources import repeaterbook

    return list(repeaterbook.COUNTRIES)


def states(country: str) -> list[str]:
    """States/provinces for a country, or ``[]`` if it has none.

    Only the US, Canada, and Mexico are queried per-state (to stay under
    RepeaterBook's result cap). Every other country has no sub-region — CHIRP
    fetches its whole dataset, keyed ``all`` — so this returns ``[]`` and the
    UI should omit the state control for it.
    """
    from chirp.sources import repeaterbook

    return list(repeaterbook.STATES.get(country, []))


def modes() -> list[str]:
    """Selectable modes for filtering (CHIRP's ``MODES``: FM, DV, DMR, DN)."""
    from chirp.sources import repeaterbook

    return list(repeaterbook.MODES)


# Amateur bands offered as result filters, (label, low_hz, high_hz). Ranges are
# generous (US/Region-2 edges, which also cover the narrower Region-1 allocations
# for the same bands) — they only bucket repeaters for filtering, so erring wide
# never hides a valid repeater. Filtering is client-side (do_fetch's
# included_band), so it works on the mirror path with no server support.
BANDS: list[tuple[str, int, int]] = [
    ("10 m", 28_000_000, 29_700_000),
    ("6 m", 50_000_000, 54_000_000),
    ("2 m", 144_000_000, 148_000_000),
    ("1.25 m", 222_000_000, 225_000_000),
    ("70 cm", 420_000_000, 450_000_000),
    ("33 cm", 902_000_000, 928_000_000),
    ("23 cm", 1_240_000_000, 1_300_000_000),
]


def bands() -> list[tuple[str, int, int]]:
    """Selectable amateur bands for filtering, (label, low_hz, high_hz)."""
    return list(BANDS)


def band_ranges(names) -> list[tuple[int, int]]:
    """Map selected band labels to the (low_hz, high_hz) ranges do_fetch wants.

    Unknown labels are ignored; ranges come back in BANDS order.
    """
    wanted = set(names)
    return [(lo, hi) for (name, lo, hi) in BANDS if name in wanted]


def has_states(country: str) -> bool:
    """True if ``country`` is queried per-state (US/Canada/Mexico)."""
    return bool(states(country))


# --- Query parameters -------------------------------------------------------

def build_params(
    country: str,
    state: str = "",
    *,
    filter_text: str = "",
    open_only: bool = False,
    bands: Optional[list] = None,
    modes: Optional[list[str]] = None,
    service: str = "",
) -> dict:
    """Build the full parameter dict ``RepeaterBook.do_fetch`` expects.

    ``do_fetch`` ``pop``s several keys with no default (``lat``/``lon``/``dist``/
    ``openonly``/``cached``/``state``), so every one must be present — this
    helper is the single place that guarantees that. Proximity search
    (lat/lon/dist) is off in this first version; ``state`` defaults to ``all``
    for countries without sub-regions.
    """
    return {
        "country": country,
        "state": state or "all",
        "service": service,
        "service_display": "Repeaters",
        "filter": filter_text,
        "openonly": bool(open_only),
        "bands": list(bands or []),
        "modes": list(modes or []),
        "fmconv": False,
        # Proximity search disabled for v1 (no lat/lon UI yet). Keys still
        # required by do_fetch; cached-merge is only used when dist is set.
        "lat": 0,
        "lon": 0,
        "dist": 0,
        "cached": False,
    }


# --- Fetch ------------------------------------------------------------------

def result_count(radio) -> int:
    """Number of result memories a fetched source radio holds."""
    lo, hi = radio.get_features().memory_bounds
    return (hi - lo + 1) if hi >= lo else 0


def describe_result(mem) -> str:
    """One-line, screen-reader-friendly summary of a result memory.

    Frequency + mode + name + location (the parsed comment RepeaterBook builds,
    e.g. "W7ABC near Portland, Multnomah County, Oregon OPEN"). Used to label
    each row in the results picker.
    """
    from chirp_backend.col_defs import format_freq_mhz

    freq = format_freq_mhz(getattr(mem, "freq", 0))
    mode = getattr(mem, "mode", "") or ""
    name = (getattr(mem, "name", "") or "").strip()
    comment = (getattr(mem, "comment", "") or "").strip()
    parts = [p for p in (f"{freq} MHz" if freq else "", mode, name) if p]
    line = "  ".join(parts)
    if comment:
        line = f"{line} — {comment}" if line else comment
    return line or "(empty)"


def result_lines(radio) -> list[tuple[int, str]]:
    """(source_number, summary) for every result memory, in channel order."""
    lo, hi = radio.get_features().memory_bounds
    out: list[tuple[int, str]] = []
    for n in range(lo, hi + 1):
        try:
            mem = radio.get_memory(n)
        except Exception:  # noqa: BLE001
            continue
        if getattr(mem, "empty", False):
            continue
        out.append((n, describe_result(mem)))
    return out


def fetch(
    params: dict,
    progress_cb: Optional[ProgressCallback] = None,
    radio=None,
) -> tuple[bool, str, object]:
    """Run a RepeaterBook query synchronously — call on a background thread.

    ``params`` comes from :func:`build_params`. ``progress_cb(message, percent)``
    is invoked for status updates (marshal it to the UI thread with
    ``wx.CallAfter``). Returns ``(ok, message, result_radio)``; on success
    ``result_radio`` holds the fetched memories, ready for
    ``memory_ops.import_memories``. ``radio`` is injectable for tests; leave it
    None to build the real (mirror-backed) source.
    """
    _install_gettext_shim()
    from chirp.sources import base

    if radio is None:
        radio = _make_radio()

    fail = {"reason": None}

    class _Status(base.QueryStatus):
        def send_status(self, status, percent):
            if progress_cb:
                progress_cb(status, percent)

        def send_end(self):
            pass

        def send_fail(self, reason):
            fail["reason"] = reason

    # do_fetch pops keys from the dict it is given; pass a copy so the caller's
    # params survive (e.g. for a retry).
    try:
        radio.do_fetch(_Status(), dict(params))
    except Exception as e:  # noqa: BLE001
        LOG.exception("RepeaterBook fetch failed")
        return False, f"RepeaterBook query failed: {e}", None

    if fail["reason"]:
        return False, str(fail["reason"]), None

    count = result_count(radio)
    if count <= 0:
        return True, "No repeaters matched your query.", radio
    return True, f"{count} repeater(s) found.", radio
