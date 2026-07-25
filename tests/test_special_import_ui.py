"""MainWindow wiring for explicit regular/special one-memory import."""

import os

import pytest

from chirp_backend import migration
from chirp_backend import radio as radio_backend

wx = pytest.importorskip("wx")


IMAGES = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "chirp", "tests", "images")
)
IC2100 = os.path.join(IMAGES, "Icom_IC-2100H.img")
IC208 = os.path.join(IMAGES, "Icom_IC-208H.img")


@pytest.fixture
def app():
    try:
        instance = wx.App()
    except Exception:  # noqa: BLE001 - headless CI
        pytest.skip("no GUI/display available")
    yield instance
    instance.Destroy()


@pytest.fixture
def win(app):
    from vrp.native.main_window import MainWindow

    window = MainWindow()
    ok, message = radio_backend.load_image(IC208)
    assert ok, message
    window._load_into_grid()
    try:
        yield window
    finally:
        radio_backend.unload()
        window.Destroy()


def _source():
    source, message = radio_backend.open_image_as_source(IC2100)
    assert source is not None, message
    return source


def test_single_special_maps_only_after_explicit_source_and_target_choices(
    win, monkeypatch
):
    source = _source()
    before = radio_backend.get_state().radio.get_memory("C1").dupe()
    calls = []
    monkeypatch.setattr(win, "_choose_import_mode", lambda *args: "single")
    monkeypatch.setattr(win, "_choose_destination_type", lambda label: "special")
    monkeypatch.setattr(win, "_confirm_special_overwrite", lambda location: True)

    def choose(locations, **kwargs):
        calls.append(kwargs)
        wanted = "C" if "source" in kwargs["title"].lower() else "C1"
        return next(
            location for location in locations
            if location.identifier == wanted
        )

    monkeypatch.setattr(win, "_choose_memory_location", choose)

    win._import_open_source(source)

    after = radio_backend.get_state().radio.get_memory("C1")
    assert after.freq == source.get_memory("C").freq
    assert after.freq != before.freq
    # The same-name source "C" is offered only as a default; C1 still required
    # an explicit destination choice.
    assert calls[1]["current_identifier"] is None


def test_same_name_special_is_preselected_but_not_silently_applied(win, monkeypatch):
    source = _source()
    monkeypatch.setattr(win, "_choose_import_mode", lambda *args: "single")
    monkeypatch.setattr(win, "_choose_destination_type", lambda label: "special")
    selected = iter(
        [
            next(
                location for location in migration.list_memory_locations(
                    source, include_regular=False
                )
                if location.identifier == "1A"
            ),
            None,  # Cancel the destination picker.
        ]
    )
    seen = []

    def choose(_locations, **kwargs):
        seen.append(kwargs)
        return next(selected)

    monkeypatch.setattr(win, "_choose_memory_location", choose)

    win._import_open_source(source)

    assert seen[1]["current_identifier"] == "1A"
    assert not radio_backend.get_state().is_modified


def test_bulk_mode_never_builds_a_special_source_batch(win, monkeypatch):
    source = _source()
    captured = {}
    monkeypatch.setattr(win, "_choose_import_mode", lambda *args: "bulk")
    monkeypatch.setattr(
        win,
        "_choose_memory_location",
        lambda *args, **kwargs: pytest.fail("single-memory picker opened"),
    )
    monkeypatch.setattr(
        win,
        "_import_results",
        lambda src, count, numbers=None: captured.update(
            src=src, count=count, numbers=numbers
        ),
    )

    win._import_open_source(source)

    assert captured["src"] is source
    assert captured["count"] > 0
    assert captured["numbers"] is None


def test_special_undo_announcement_does_not_treat_virtual_number_as_grid_row(
    win, monkeypatch
):
    source = _source()
    batch = migration.batch_from_identifiers(source, ["C"])
    win._confirm_special_overwrite = lambda location: True
    win._import_batch_to_special(batch, "C1")
    announcements = []
    monkeypatch.setattr(
        win.announce,
        "announce",
        lambda message, **kwargs: announcements.append(message),
    )

    win.on_undo()

    assert announcements
    assert "Special memory C1" in announcements[-1]
