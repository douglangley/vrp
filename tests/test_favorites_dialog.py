"""GUI tests for the favorites manager and the Download dialog's All/Favorites
toggle. Skips without a display. Config is isolated per test by monkeypatching
serial_dialogs.get_config to a temp Config."""

import pytest

wx = pytest.importorskip("wx")

MODELS = [
    {"id": "Baofeng_UV-5R", "vendor": "Baofeng", "model": "UV-5R",
     "variant": "", "label": "Baofeng UV-5R"},
    {"id": "Baofeng_UV-5R_Mini", "vendor": "Baofeng", "model": "UV-5R Mini",
     "variant": "", "label": "Baofeng UV-5R Mini"},
    {"id": "Yaesu_FT-60", "vendor": "Yaesu", "model": "FT-60",
     "variant": "", "label": "Yaesu FT-60"},
]


@pytest.fixture
def app():
    try:
        a = wx.App()
    except Exception:  # noqa: BLE001 — headless CI
        pytest.skip("no GUI/display available")
    yield a
    a.Destroy()


@pytest.fixture
def isolated_config(tmp_path, monkeypatch):
    from vrp.config import Config
    import vrp.serial_dialogs as sd

    c = Config(path=str(tmp_path / "c.json"))
    monkeypatch.setattr(sd, "get_config", lambda: c)
    return c


def _select_in_picker(picker, label):
    picker.list.SetStringSelection(label)


def test_favorites_dialog_add_and_remove(app, isolated_config):
    from vrp.serial_dialogs import FavoritesDialog

    frame = wx.Frame(None)
    try:
        dlg = FavoritesDialog(frame, MODELS)
        _select_in_picker(dlg.picker, "Baofeng UV-5R")
        dlg._on_add(None)
        assert isolated_config.favorites() == ["Baofeng_UV-5R"]
        assert [dlg.fav_list.GetString(i)
                for i in range(dlg.fav_list.GetCount())] == ["Baofeng UV-5R"]
        assert "Added Baofeng UV-5R" in dlg._status.GetLabel()

        # Adding the same one again is a no-op with feedback.
        dlg._on_add(None)
        assert isolated_config.favorites() == ["Baofeng_UV-5R"]
        assert "already a favorite" in dlg._status.GetLabel()

        # Remove it.
        dlg.fav_list.SetSelection(0)
        dlg._on_remove(None)
        assert isolated_config.favorites() == []
        assert dlg.fav_list.GetCount() == 0
        assert "Removed Baofeng UV-5R" in dlg._status.GetLabel()
        dlg.Destroy()
    finally:
        frame.Destroy()


def test_favorites_dialog_picker_controls_are_direct_children_and_search_works(
        app, isolated_config):
    """Regression: the picker was once a nested wx.Panel, which broke NVDA tab
    order (filter/Add unreachable). Its controls must be direct dialog children,
    and the filter must narrow the list."""
    from vrp.serial_dialogs import FavoritesDialog

    frame = wx.Frame(None)
    try:
        dlg = FavoritesDialog(frame, MODELS)
        assert dlg.picker.filter.GetParent() is dlg
        assert dlg.picker.list.GetParent() is dlg
        assert dlg.add_btn.GetParent() is dlg
        # The lists are list-views (wx.ListCtrl) for native multi-char type-ahead,
        # not wx.ListBox (single-letter only on Windows).
        assert isinstance(dlg.picker.list, wx.ListCtrl)
        assert isinstance(dlg.fav_list, wx.ListCtrl)
        # Search narrows the list (the filter's EVT_TEXT handler).
        dlg.picker.filter.SetValue("mini")
        dlg.picker._apply_filter()
        shown = [dlg.picker.list.GetString(i)
                 for i in range(dlg.picker.list.GetCount())]
        assert shown == ["Baofeng UV-5R Mini"]
        dlg.Destroy()
    finally:
        frame.Destroy()


def test_favorites_dialog_drops_unknown_driver_ids(app, isolated_config):
    """A favorite whose driver vanished (e.g. after a CHIRP update) is ignored."""
    from vrp.serial_dialogs import FavoritesDialog

    isolated_config.add_favorite("Yaesu_FT-60")
    isolated_config.add_favorite("Gone_Driver_123")
    frame = wx.Frame(None)
    try:
        dlg = FavoritesDialog(frame, MODELS)
        shown = [dlg.fav_list.GetString(i) for i in range(dlg.fav_list.GetCount())]
        assert shown == ["Yaesu FT-60"]  # the stale id is not shown
        dlg.Destroy()
    finally:
        frame.Destroy()


def test_radio_details_button_only_when_describer_wired(app, isolated_config):
    from vrp.serial_dialogs import FavoritesDialog

    frame = wx.Frame(None)
    try:
        with_fn = FavoritesDialog(frame, MODELS, describe_fn=lambda i: "info")
        assert hasattr(with_fn, "details_btn")
        with_fn.Destroy()
        without = FavoritesDialog(frame, MODELS)  # no describer -> no button
        assert not hasattr(without, "details_btn")
        without.Destroy()
    finally:
        frame.Destroy()


def test_show_model_details_is_noop_without_selection_or_describer(app):
    from vrp.serial_dialogs import show_model_details

    # Returns before creating any (blocking) modal when there's nothing to show.
    show_model_details(None, None, lambda i: "x")
    show_model_details(None, {"id": "x", "label": "X"}, None)


def test_download_dialog_favorites_toggle(app, isolated_config):
    from vrp.serial_dialogs import DownloadDialog

    isolated_config.add_favorite("Baofeng_UV-5R")
    isolated_config.add_favorite("Yaesu_FT-60")
    frame = wx.Frame(None)
    try:
        dlg = DownloadDialog(frame, lambda: [{"port": "COM4", "description": ""}],
                             MODELS)
        assert dlg.picker.list.GetCount() == 3  # all radios by default
        assert dlg.show_all.GetValue() is True

        dlg.show_favs.SetValue(True)
        dlg._on_show_changed(None)
        shown = [dlg.picker.list.GetString(i)
                 for i in range(dlg.picker.list.GetCount())]
        assert shown == ["Baofeng UV-5R", "Yaesu FT-60"]

        # Back to all.
        dlg.show_all.SetValue(True)
        dlg._on_show_changed(None)
        assert dlg.picker.list.GetCount() == 3
        dlg.Destroy()
    finally:
        frame.Destroy()
