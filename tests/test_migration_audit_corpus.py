"""Phase 6 representative-source audit configuration."""

from pathlib import Path

from chirp import chirp_common

from tools import audit_migrations


IMAGES = (
    Path(__file__).resolve().parent.parent / "chirp" / "tests" / "images"
)


def _case_map():
    return {
        case.key: case
        for case in audit_migrations.build_corpus(IMAGES)
    }


def test_default_corpus_covers_every_phase6_category():
    cases = _case_map()

    assert set(cases) == {
        "vhf_tone",
        "uhf_dtcs",
        "hf_am",
        "airband_am",
        "cross_band_split",
        "dstar",
    }
    assert all(len(case.batch.entries) == 1 for case in cases.values())


def test_default_corpus_uses_expected_memory_semantics():
    cases = _case_map()
    memories = {
        key: case.batch.entries[0].memory for key, case in cases.items()
    }

    assert memories["vhf_tone"].freq == 147_380_000
    assert memories["vhf_tone"].tmode == "Tone"
    assert memories["uhf_dtcs"].freq == 443_100_000
    assert memories["uhf_dtcs"].tmode == "DTCS"
    assert memories["hf_am"].freq == 2_182_000
    assert memories["hf_am"].mode == "AM"
    assert "IC-M710" in cases["hf_am"].batch.source_label
    assert memories["airband_am"].freq == 119_300_000
    assert memories["airband_am"].mode == "AM"
    assert memories["cross_band_split"].duplex == "split"
    assert memories["cross_band_split"].freq == 144_325_000
    assert memories["cross_band_split"].offset == 470_175_000
    assert "WP-9900" in cases["cross_band_split"].batch.source_label
    assert isinstance(memories["dstar"], chirp_common.DVMemory)
    assert memories["dstar"].mode == "DV"


def test_source_channel_override_preserves_targeted_debugging():
    cases = audit_migrations.build_corpus(IMAGES, [25, 88])

    assert [case.key for case in cases] == [
        "generic_csv_25",
        "generic_csv_88",
    ]
    assert [
        case.batch.entries[0].memory.number for case in cases
    ] == [25, 88]


def test_rejected_state_ignores_irrelevant_simplex_offset_only():
    before = chirp_common.Memory()
    before.freq = 145_000_000
    before.offset = 600_000
    after = before.dupe()
    after.offset = 0

    assert audit_migrations._memory_state(before) == (
        audit_migrations._memory_state(after)
    )

    before.duplex = "+"
    after.duplex = "+"
    assert audit_migrations._memory_state(before) != (
        audit_migrations._memory_state(after)
    )
