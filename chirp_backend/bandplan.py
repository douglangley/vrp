"""Suggested repeater offset lookup, derived from CHIRP's band plans.

VRP fills the channel's **Offset** field with the standard repeater shift
*magnitude* for the frequency's band (e.g. 0.6 MHz on 2 m, 5 MHz on 70 cm),
leaving the **Duplex** direction (+/-) to the user — many local coordinations
don't follow the band plan's nominal direction, and the magnitude is the same
either way (147.x -> 0.6 means "-" txes 146.x and "+" txes 147.x+0.6).

The data is read from CHIRP's ``chirp.bandplan`` (``bandplan_na`` etc.), so we
inherit its frequency ranges instead of hardcoding our own. ``chirp.bandplan``'s
``BandPlans`` wants a config object (normally ``chirp.wxui.config``, which VRP
must not import — CLAUDE.md); we pass a tiny stub that just enables one plan.
"""

from __future__ import annotations

import logging

LOG = logging.getLogger(__name__)

# The CHIRP band plans VRP can read offsets from, as (shortname, UI label),
# in menu order. The shortname must match each plan module's SHORTNAME
# (bandplan_na / bandplan_au / bandplan_iaru_r1/r2/r3). North America is CHIRP's
# own default for new users.
REGIONS = [
    ("north_america", "North America"),
    ("australia", "Australia"),
    ("iaru_r1", "IARU Region 1 (Europe, Africa, Northern Asia)"),
    ("iaru_r2", "IARU Region 2 (the Americas)"),
    ("iaru_r3", "IARU Region 3 (Asia-Pacific)"),
]
_VALID_REGIONS = {shortname for shortname, _ in REGIONS}
DEFAULT_REGION = "north_america"

# Active region. Read *live* by _StubConfig.get_bool, so set_region() takes
# effect without rebuilding the cached BandPlans (get_defaults_for_frequency
# re-checks which plan is enabled on every call).
_region = DEFAULT_REGION


def set_region(shortname: str) -> None:
    """Choose which CHIRP band plan supplies offset suggestions. Unknown names
    are ignored (the current region stays)."""
    global _region
    if shortname in _VALID_REGIONS:
        _region = shortname


def get_region() -> str:
    """The active band-plan region shortname."""
    return _region


def region_label(shortname: str) -> str:
    """Human-readable label for a region shortname (the shortname if unknown)."""
    for sn, label in REGIONS:
        if sn == shortname:
            return label
    return shortname


class _StubConfig:
    """Minimal config satisfying ``bandplan.BandPlans``: enable one plan only.

    BandPlans calls get/set_bool/is_defined/get_bool/remove_option during init
    and get_bool(shortname, "bandplan") when resolving. We report the active
    region (read live, so set_region works) as enabled and everything else off,
    and no legacy "autorpt" to migrate.
    """

    def get(self, key, section):
        return None

    def set_bool(self, key, value, section):
        pass

    def remove_option(self, key, section):
        pass

    def is_defined(self, key, section):
        return True

    def get_bool(self, key, section, default=False):
        return key == _region


_plans = None


def _band_plans():
    """Lazily build the CHIRP BandPlans (importing chirp only when needed)."""
    global _plans
    if _plans is None:
        from chirp import bandplan as chirp_bandplan

        _plans = chirp_bandplan.BandPlans(_StubConfig())
    return _plans


def _amateur_band_containing(plans, freq_hz: int):
    """The broad amateur band (e.g. "2 Meter Band") whose range contains
    ``freq_hz``, or None. These broad bands carry no offset themselves."""
    plan = plans.get_enabled_plan()
    if plan is None:
        return None
    best = None
    for band in plan.bands:
        name = (band.name or "").lower()
        if not (name.endswith("meter band") or name.endswith("cm band")):
            continue
        lo, hi = band.limits
        if lo <= freq_hz < hi:
            # Prefer the narrowest containing band if they ever nest.
            if best is None or band.width() < best.width():
                best = band
    return best


def _dominant_offset_in(plans, band) -> int | None:
    """The repeater offset magnitude that covers the most spectrum within
    ``band`` — i.e. the band's standard shift, robust to a stray sub-band with a
    different offset (10 m, 23 cm). Returns Hz, or None if the band has none."""
    plan = plans.get_enabled_plan()
    lo, hi = band.limits
    span_by_mag: dict[int, int] = {}
    for b in plan.bands:
        if not b.offset:
            continue
        blo, bhi = b.limits
        # Overlap of this offset-bearing sub-band with the amateur band.
        olo, ohi = max(lo, blo), min(hi, bhi)
        if ohi <= olo:
            continue
        mag = abs(b.offset)
        span_by_mag[mag] = span_by_mag.get(mag, 0) + (ohi - olo)
    if not span_by_mag:
        return None
    # Max total span wins; tie-break to the larger magnitude (deterministic).
    return max(span_by_mag, key=lambda m: (span_by_mag[m], m))


def suggest_offset_hz(freq_hz: int) -> int | None:
    """Suggested repeater offset *magnitude* (Hz) for ``freq_hz``, or None when
    the band has no standard repeater offset (HF, simplex-only bands).

    Always non-negative — the caller/user chooses the duplex direction. Uses
    CHIRP's most-specific match when the frequency sits in a repeater sub-band,
    else the band's dominant offset so simplex portions of a repeater band still
    get the band's standard shift (e.g. 147.52 -> 0.6 MHz)."""
    try:
        plans = _band_plans()
    except Exception:  # noqa: BLE001 — never let a band-plan import break editing
        LOG.warning("Band plan unavailable; no offset suggestion", exc_info=True)
        return None
    if not freq_hz:
        return None
    freq_hz = int(freq_hz)

    # 1) Frequency is inside a repeater sub-band: use CHIRP's own resolution.
    defaults = plans.get_defaults_for_frequency(freq_hz)
    if defaults.offset:
        return abs(defaults.offset)

    # 2) Simplex portion of an amateur band: use the band's standard shift.
    band = _amateur_band_containing(plans, freq_hz)
    if band is not None:
        mag = _dominant_offset_in(plans, band)
        if mag:
            return mag
    return None


def suggest_offset_for_freq_str(freq_str: str) -> int | None:
    """Like :func:`suggest_offset_hz` but takes a display frequency string in
    MHz (e.g. "146.94"), the form the editor's Frequency field holds. Returns
    None on an unparseable/empty string instead of raising."""
    if not freq_str or not freq_str.strip():
        return None
    from chirp import chirp_common

    try:
        freq_hz = chirp_common.parse_freq(freq_str.strip())
    except Exception:  # noqa: BLE001 — partial/invalid input -> no suggestion
        return None
    return suggest_offset_hz(freq_hz)


def offset_hz_to_mhz_str(offset_hz: int) -> str:
    """Format an offset magnitude (Hz) as the MHz string the Offset field uses,
    matching ``col_defs.OffsetColumn.format_value`` (trimmed to 4 decimals)."""
    mhz = offset_hz / 1_000_000
    return f"{mhz:.4f}".rstrip("0").rstrip(".")


def suggest_band_defaults(freq_hz: int, features) -> dict:
    """Band-plan defaults for **mode, tuning step, and tone** at ``freq_hz`` for a
    radio with ``features`` — the "auto edits" fields. Returns {field: value_str}
    (editor/column string form) for the fields it can resolve, empty when none
    apply. Mirrors the relevant parts of CHIRP's ``memedit._set_memory_defaults``.

    Deliberately excludes **duplex** (the +/- direction is the user's call) and
    **offset** (filled separately, magnitude-only) — see ``suggest_offset_hz``.
    """
    if not freq_hz:
        return {}
    try:
        plans = _band_plans()
    except Exception:  # noqa: BLE001 — never let a band-plan import break editing
        LOG.warning("Band plan unavailable; no defaults", exc_info=True)
        return {}
    from chirp import chirp_common

    freq_hz = int(freq_hz)
    defaults = plans.get_defaults_for_frequency(freq_hz)
    result: dict[str, str] = {}

    # Mode: the band's default, only if this radio supports it.
    valid_modes = list(features.valid_modes or [])
    if defaults.mode and defaults.mode in valid_modes:
        result["mode"] = defaults.mode

    # Tuning step: the band's default if supported and the freq lands on it,
    # otherwise the simplest step that represents the frequency exactly.
    valid_steps = list(features.valid_tuning_steps or [])
    want_step = None
    if defaults.step_khz and defaults.step_khz in valid_steps and \
            freq_hz % int(defaults.step_khz * 1000) == 0:
        want_step = defaults.step_khz
    else:
        # required_step returns the first step in list order that fits; a radio's
        # valid_steps is often ordered finest-first (2.5, 5, ...), which picks an
        # unnecessarily fine step (2.5 on a 2 m simplex). CHIRP's default ordering
        # prefers the conventional 5/10/12.5; use that, constrained to supported
        # steps, and only fall back to the radio's order if none of those fit.
        try:
            preferred = chirp_common.required_step(freq_hz)
        except Exception:  # noqa: BLE001
            preferred = None
        if preferred is not None and preferred in valid_steps:
            want_step = preferred
        else:
            try:
                want_step = chirp_common.required_step(freq_hz, valid_steps or None)
            except Exception:  # noqa: BLE001 — no representable step -> skip
                want_step = None
    if want_step is not None:
        # Match the Step column's str(step) form so the Choice can select it.
        match = next((s for s in valid_steps if s == want_step), want_step)
        result["tuning_step"] = str(match)

    # Tone: only when the band plan specifies one and the radio supports it.
    valid_tones = list(features.valid_tones or [])
    if defaults.tones and defaults.tones[0] in valid_tones:
        result["rtone"] = str(defaults.tones[0])

    return result


def suggest_band_defaults_for_freq_str(freq_str: str, features) -> dict:
    """:func:`suggest_band_defaults` from a display MHz string (editor field)."""
    if not freq_str or not freq_str.strip():
        return {}
    from chirp import chirp_common

    try:
        freq_hz = chirp_common.parse_freq(freq_str.strip())
    except Exception:  # noqa: BLE001 — partial/invalid input -> nothing
        return {}
    return suggest_band_defaults(freq_hz, features)
