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
from typing import Any, Optional


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

    def to_dict(self) -> dict:
        """Serialize column definition for the frontend."""
        return {
            "name": self.name,
            "label": self.label,
            "editable": self.editable,
            "input_type": self.input_type,
            "choices": self.choices,
            "width_hint": self.width_hint,
        }


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
        mhz = freq / 1_000_000
        # Show up to 6 decimal places, strip trailing zeros
        return f"{mhz:.6f}".rstrip("0").rstrip(".")

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
            choices=[""] + list(features.valid_tmodes),
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
            choices=[""] + list(features.valid_duplexes),
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
            choices=["", "S", "P"],
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


def memory_to_dict(mem, col_defs: list[ColumnDef]) -> dict:
    """
    Serialize a Memory object to a dict for JSON response.
    Includes all column values plus metadata the frontend needs.
    """
    result = {
        "number": mem.number,
        "empty": mem.empty,
        "immutable": mem.immutable,
        "extd_number": getattr(mem, "extd_number", ""),
    }
    for col in col_defs:
        if col.name == "number":
            continue
        result[col.name] = col.format_value(mem)
    return result
