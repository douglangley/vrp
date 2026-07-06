"""Decision-logic tests for the unsaved-changes guard (Phase 1.2).

_confirm_discard_or_save() gates every step that would discard the working
image (close, Exit, Open, Download). We stub the native Yes/No/Cancel dialog so
the branches are exercised headless; the dialog's screen-reader behavior is
verified manually under NVDA. Skips without a GUI."""

import os

import pytest

from chirp_backend import radio as radio_backend

wx = pytest.importorskip("wx")

IMAGE = os.path.abspath(
    os.path.join(
        os.path.dirname(__file__), "..", "chirp", "tests", "images",
        "Baofeng_UV-5R.img",
    )
)


@pytest.fixture
def app():
    try:
        a = wx.App()
    except Exception:  # noqa: BLE001 — headless CI
        pytest.skip("no GUI/display available")
    yield a
    a.Destroy()


@pytest.fixture
def win(app):
    from vrp.native.main_window import MainWindow

    w = MainWindow()
    radio_backend.load_image(IMAGE)
    w._load_into_grid()
    try:
        yield w
    finally:
        radio_backend.unload()
        w.Destroy()


class _StubDialog:
    """Stand-in for wx.MessageDialog returning a preset ShowModal result."""

    result = wx.ID_CANCEL

    def __init__(self, *a, **k):
        pass

    def SetYesNoCancelLabels(self, *a):  # noqa: N802 (wx API parity)
        pass

    def ShowModal(self):  # noqa: N802
        return type(self).result

    def Destroy(self):  # noqa: N802
        pass


def _stub_dialog(monkeypatch, result):
    import vrp.native.main_window as mw

    cls = type("StubDlg", (_StubDialog,), {"result": result})
    monkeypatch.setattr(mw.wx, "MessageDialog", cls)


def test_unmodified_passes_without_prompt(win, monkeypatch):
    # Not modified → proceed, and never construct a dialog.
    import vrp.native.main_window as mw

    def _boom(*a, **k):
        pytest.fail("dialog shown for an unmodified image")

    monkeypatch.setattr(mw.wx, "MessageDialog", _boom)
    assert radio_backend.get_state().is_modified is False
    assert win._confirm_discard_or_save() is True


def test_cancel_vetoes(win, monkeypatch):
    radio_backend.get_state().is_modified = True
    _stub_dialog(monkeypatch, wx.ID_CANCEL)
    assert win._confirm_discard_or_save() is False


def test_dont_save_discards(win, monkeypatch):
    radio_backend.get_state().is_modified = True
    _stub_dialog(monkeypatch, wx.ID_NO)
    # Never touches on_save; just proceeds.
    monkeypatch.setattr(win, "on_save", lambda *a: pytest.fail("saved on discard"))
    assert win._confirm_discard_or_save() is True


def test_save_success_proceeds(win, monkeypatch):
    radio_backend.get_state().is_modified = True
    _stub_dialog(monkeypatch, wx.ID_YES)
    monkeypatch.setattr(win, "on_save", lambda *a: True)
    assert win._confirm_discard_or_save() is True


def test_save_failure_vetoes(win, monkeypatch):
    radio_backend.get_state().is_modified = True
    _stub_dialog(monkeypatch, wx.ID_YES)
    monkeypatch.setattr(win, "on_save", lambda *a: False)
    assert win._confirm_discard_or_save() is False


def test_open_over_modified_is_guarded(win, monkeypatch):
    # _open_path must abort (and not load) when the guard vetoes.
    radio_backend.get_state().is_modified = True
    _stub_dialog(monkeypatch, wx.ID_CANCEL)
    loaded = []
    monkeypatch.setattr(
        radio_backend, "load_image",
        lambda *a, **k: loaded.append(a) or (True, "loaded"),
    )
    assert win._open_path(IMAGE) is False
    assert loaded == []  # never attempted the load
