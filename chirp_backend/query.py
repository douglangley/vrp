"""Online query sources (Phase 7) — framework + source registry.

A source is a CHIRP NetworkResultRadio subclass whose do_fetch(status, params)
populates result memories from an online database. This module instantiates a
source by key and runs its fetch (synchronously — the caller runs it on a
background thread), adapting CHIRP's QueryStatus callbacks to a simple
progress callback. Importing the fetched memories into the loaded radio is in
memory_ops.import_memories.

Phase 7 registers the no-credential, low-param sources (AMSAT, SatNOGS). Adding
the param-heavy / credential sources (RepeaterBook, RadioReference, DMR-MARC,
przemienniki, mapy73) is mechanical: add a SOURCES entry + a param spec.
"""

from __future__ import annotations

import importlib
import logging

LOG = logging.getLogger(__name__)

# key -> source definition. params: list of {name, kind, label} for the dialog
# (empty = no parameters). attribution/tos travel with the source (shown in the
# dialog + results, per the accessibility review).
SOURCES = [
    {
        "key": "amsat",
        "label": "AMSAT (amateur satellites)",
        "module": "chirp.sources.amsats",
        "cls": "RadioAmateurSatellites",
        "attribution": "Satellite data from AMSAT.",
        "tos": "https://www.amsat.org/",
        "params": [],
    },
    {
        "key": "satnogs",
        "label": "SatNOGS (satellite transponders)",
        "module": "chirp.sources.amsats",
        "cls": "SatNOGS",
        "attribution": "Transponder data from the SatNOGS DB.",
        "tos": "https://satnogs.org/",
        "params": [],
    },
    {
        "key": "dmrmarc",
        "label": "DMR-MARC repeaters",
        "module": "chirp.sources.dmrmarc",
        "cls": "DMRMARCRadio",
        "attribution": "Repeater data from the DMR-MARC worldwide network.",
        "tos": "https://www.dmr-marc.net/",
        "params": [
            {"name": "city", "kind": "text", "label": "City"},
            {"name": "state", "kind": "text", "label": "State or province"},
            {"name": "country", "kind": "text", "label": "Country"},
        ],
    },
    {
        "key": "mapy73",
        "label": "mapy73.pl (European networks)",
        "module": "chirp.sources.mapy73pl",
        "cls": "Mapy73Pl",
        "attribution": "Repeater data from mapy73.pl.",
        "tos": "https://mapy73.pl/",
        "params": [
            {
                "name": "api_option",
                "kind": "choice",
                "label": "Network",
                "options": [
                    "FM-Poland network", "Poland FM-LINK", "Poland DMR",
                    "Poland C4FM", "Poland DSTAR", "Poland FM", "Czechia FM",
                    "Slovakia FM", "Finland FM", "Sweden FM", "Norway FM",
                    "Bulgaria FM", "Denmark FM", "Germany FM", "Slovenia FM",
                    "Iceland FM",
                ],
            },
        ],
    },
]


def get_source(key: str):
    for src in SOURCES:
        if src["key"] == key:
            return src
    return None


def make_source_radio(key: str):
    """Instantiate the NetworkResultRadio for ``key`` (or None)."""
    src = get_source(key)
    if src is None:
        return None
    try:
        module = importlib.import_module(src["module"])
        return getattr(module, src["cls"])()
    except Exception:  # noqa: BLE001
        LOG.exception("Could not load query source %s", key)
        return None


def result_count(radio) -> int:
    lo, hi = radio.get_features().memory_bounds
    return (hi - lo + 1) if hi >= lo else 0


def run_fetch(radio, params, progress_cb) -> tuple[bool, str]:
    """Run a source's do_fetch synchronously (call from a background thread).

    progress_cb(message, percent) is invoked for status updates. Returns
    (ok, message); on success the radio holds the fetched memories.
    """
    from chirp.sources import base

    fail = {"reason": None}

    class _Status(base.QueryStatus):
        def send_status(self, status, percent):
            if progress_cb:
                progress_cb(status, percent)

        def send_end(self):
            pass

        def send_fail(self, reason):
            fail["reason"] = reason

    try:
        radio.do_fetch(_Status(), params or {})
    except Exception as e:  # noqa: BLE001
        LOG.exception("Query fetch failed")
        return False, f"Query failed: {e}"

    if fail["reason"]:
        return False, str(fail["reason"])

    count = result_count(radio)
    if count <= 0:
        return True, "No results matched your query."
    return True, f"{count} result(s) found."
