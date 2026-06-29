"""GUI smoke test for the read-only review dialog (vrp.info_dialog.InfoDialog).
Skips without a display."""

import pytest

wx = pytest.importorskip("wx")


@pytest.fixture
def app():
    try:
        a = wx.App()
    except Exception:  # noqa: BLE001 — headless CI
        pytest.skip("no GUI/display available")
    yield a
    a.Destroy()


def test_info_dialog_is_readonly_multiline_and_holds_text(app):
    from vrp.info_dialog import InfoDialog

    frame = wx.Frame(None)
    try:
        text = "Vendor: Baofeng\nModel: UV-5R\nChannels: 128"
        dlg = InfoDialog(frame, "Radio Info", text, name="Radio information")
        assert dlg.text.GetValue() == text
        assert not dlg.text.IsEditable()                    # read-only...
        assert dlg.text.GetWindowStyle() & wx.TE_MULTILINE  # ...but navigable
        assert dlg.text.GetName() == "Radio information"
        assert dlg.GetEscapeId() == wx.ID_CLOSE             # Escape closes
        dlg.Destroy()
    finally:
        frame.Destroy()
