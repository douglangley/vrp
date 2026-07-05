"""
Column definitions for the memory channel table.

Mirrors the ChirpMemoryColumn hierarchy in chirp/wxui/memedit.py but
decoupled from wx. Each column knows how to:
  - Extract a display value from a Memory object
  - Determine if it should be hidden for a given memory/features set
  - Provide valid choices (for choice columns)
  - Format a value for display
  - Parse a user-entered string back to the internal value

This is used both by the Flask routes (to know what columns to include
in JSON) and by the frontend (column headers, input types, valid values).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


def format_freq_mhz(freq_hz: int) -> str:
    """Format a frequency (integer Hz) as an MHz display string.

    Keeps the exact stored precision but always shows **at least 3 decimals**, so
    a whole-MHz channel reads "146.000" rather than "146" (the reported bug — a
    lone "146" hides that it's a real frequency, and trailing zeros are
    meaningful to the operator). Digits finer than kHz are preserved, never
    truncated: 146_012_500 Hz -> "146.0125", 145_987_500 -> "145.9875",
    146_006_250 -> "146.00625". Computed from the integer Hz (not float MHz) so
    there is no binary-float rounding error in the displayed value.
    """
    whole, frac = divmod(int(freq_hz), 1_000_000)
    frac_str = f"{frac:06d}".rstrip("0")
    if len(frac_str) < 3:
        frac_str = frac_str.ljust(3, "0")  # pad up to kHz so "146" -> "146.000"
    return f"{whole}.{frac_str}"


@dataclass
class ColumnDef:
    """Base column definition."""
    name: str           # Memory attribute name (e.g. 'freq', 'name')
    label: str          # Human-readable column header
    editable: bool = True
    input_type: str = "text"   # 'text', 'number', 'select'
    choices: list[str] = field(default_factory=list)
    width_hint: str = "auto"   # 'narrow', 'wide', 'auto'

    def get_value(self, mem) -> Any:
        """Extract the display value from a Memory object."""
        return getattr(mem, self.name, "")

    def format_value(self, mem) -> str:
        """Format the value for display in the table cell."""
        val = self.get_value(mem)
        if val is None:
            return ""
        return str(val)

    def hidden_for(self, mem, features) -> bool:
        """Return True if this column should be hidden for this memory/radio."""
        return False


@dataclass
class FrequencyColumn(ColumnDef):
    """Frequency column — stored as integer Hz, displayed as MHz."""
    name: str = "freq"
    label: str = "Frequency"
    input_type: str = "text"
    width_hint: str = "wide"

    def format_value(self, mem) -> str:
        if mem.empty:
            return ""
        freq = mem.freq
        if freq == 0:
            return ""
        return format_freq_mhz(freq)

    def hidden_for(self, mem, features) -> bool:
        return False


@dataclass
class OffsetColumn(ColumnDef):
    """Duplex offset — stored as integer Hz, displayed as MHz."""
    name: str = "offset"
    label: str = "Offset"
    input_type: str = "text"
    width_hint: str = "narrow"

    def format_value(self, mem) -> str:
        if mem.empty or mem.duplex in ("", "off"):
            return ""
        offset = mem.offset
        if offset == 0:
            return "0"
        mhz = offset / 1_000_000
        return f"{mhz:.4f}".rstrip("0").rstrip(".")

    def hidden_for(self, mem, features) -> bool:
        return mem.duplex not in ("+", "-", "split")


@dataclass
class ChoiceColumn(ColumnDef):
    """Column with a fixed set of valid choices."""
    input_type: str = "select"

    def hidden_for(self, mem, features) -> bool:
        return False


@dataclass
class ToneColumn(ChoiceColumn):
    """CTCSS/DTCS tone column — choices depend on tone mode."""

    def hidden_for(self, mem, features) -> bool:
        if self.name == "rtone":
            return mem.tmode not in ("Tone", "TSQL", "Cross")
        if self.name == "ctone":
            return mem.tmode not in ("TSQL", "Cross")
        return False


@dataclass
class DTCSColumn(ChoiceColumn):
    """DTCS code column."""

    def hidden_for(self, mem, features) -> bool:
        if self.name == "dtcs":
            return "DTCS" not in (mem.tmode or "") and "DTCS" not in (mem.cross_mode or "")
        if self.name == "rx_dtcs":
            return "DTCS" not in (mem.cross_mode or "")
        return False


def _blank_first(values) -> list[str]:
    """Return ``values`` with exactly one blank ('') choice at the front.

    The blank choice is the "no value" option (e.g. tone mode "none", simplex
    duplex). CHIRP's ``valid_tmodes``/``valid_duplexes`` already include '',
    so prepending '' unconditionally produced a *duplicate* empty entry — two
    blank rows in the combo box. Dedupe to a single leading blank, order of the
    remaining values preserved.
    """
    rest = [v for v in values if v != ""]
    return [""] + rest


def build_column_defs(features) -> list[ColumnDef]:
    """
    Build the list of column definitions for a radio with the given features.
    Columns that are not valid for this radio are omitted entirely.
    """
    from chirp import chirp_common

    # Tone choices
    tones = [str(t) for t in sorted(chirp_common.TONES)]
    dtcs_codes = [f"{c:03d}" for c in sorted(chirp_common.DTCS_CODES)]
    cross_modes = list(chirp_common.CROSS_MODES) if hasattr(chirp_common, "CROSS_MODES") else [
        "Tone->Tone", "Tone->DTCS", "DTCS->Tone", "DTCS->DTCS",
        "->Tone", "->DTCS", "Tone->", "DTCS->",
    ]

    cols: list[ColumnDef] = [
        ColumnDef(
            name="number",
            label="Ch #",
            editable=False,
            width_hint="narrow",
        ),
        FrequencyColumn(),
        ColumnDef(name="name", label="Name", width_hint="narrow"),
        ChoiceColumn(
            name="tmode",
            label="Tone Mode",
            choices=_blank_first(features.valid_tmodes),
            width_hint="narrow",
        ),
        ToneColumn(
            name="rtone",
            label="Tone",
            choices=tones,
            width_hint="narrow",
        ),
        ToneColumn(
            name="ctone",
            label="ToneSql",
            choices=tones,
            width_hint="narrow",
        ),
        DTCSColumn(
            name="dtcs",
            label="DTCS Code",
            choices=dtcs_codes,
            width_hint="narrow",
        ),
        DTCSColumn(
            name="rx_dtcs",
            label="RX DTCS",
            choices=dtcs_codes,
            width_hint="narrow",
        ),
        ChoiceColumn(
            name="dtcs_polarity",
            label="DTCS Pol.",
            choices=["NN", "NR", "RN", "RR"],
            width_hint="narrow",
        ),
        ChoiceColumn(
            name="cross_mode",
            label="Cross Mode",
            choices=cross_modes,
            width_hint="narrow",
        ),
        ChoiceColumn(
            name="duplex",
            label="Duplex",
            choices=_blank_first(features.valid_duplexes),
            width_hint="narrow",
        ),
        OffsetColumn(),
        ChoiceColumn(
            name="mode",
            label="Mode",
            choices=list(features.valid_modes),
            width_hint="narrow",
        ),
        ChoiceColumn(
            name="tuning_step",
            label="Step",
            choices=[str(s) for s in features.valid_tuning_steps],
            width_hint="narrow",
        ),
        ChoiceColumn(
            name="skip",
            label="Skip",
            # Only the skip values this radio supports (CHIRP's ChirpSkipColumn
            # uses features.valid_skips too); many radios omit "P" (Pscan).
            choices=_blank_first(features.valid_skips),
            width_hint="narrow",
        ),
        ColumnDef(name="comment", label="Comment", width_hint="wide"),
    ]

    # Filter out columns the radio doesn't support
    valid = []
    for col in cols:
        if col.name == "number":
            valid.append(col)
            continue
        # Check features for validity
        if col.name == "rtone" and not features.has_ctone:
            continue
        if col.name == "ctone" and not features.has_ctone:
            continue
        if col.name in ("dtcs", "rx_dtcs", "dtcs_polarity") and not features.has_dtcs:
            continue
        if col.name == "cross_mode" and not features.has_cross:
            continue
        if col.name == "tuning_step" and not features.has_tuning_step:
            continue
        if col.name == "skip" and not features.valid_skips:
            continue
        if col.name == "comment" and not features.has_comment:
            continue
        if col.name == "mode" and len(features.valid_modes) <= 1:
            continue
        valid.append(col)

    return valid


def editable_columns(
    columns: list[ColumnDef], immutable: list[str] | None = None
) -> list[ColumnDef]:
    """The single-cell-editable columns from ``columns``: ``editable`` is True,
    the column is not the ``number`` row header, and its name is not in
    ``immutable`` (the fields that can't be changed for a given memory).

    This is the field set F2's macOS column-picker offers (``on_edit_cell`` /
    ``MainWindow._editable_columns``). Pure and wx-free so it's unit-testable
    headless."""
    blocked = set(immutable or [])
    return [
        c for c in columns
        if c.editable and c.name != "number" and c.name not in blocked
    ]
