"""Tests for the port-picker's selection logic (vrp.serial_dialogs._select_index).

Pure function — picks which port index to select so the dialog can default to
the last-used port while not clobbering a manual choice across a Refresh.
"""

from vrp.serial_dialogs import _select_index

PORTS = ["COM3", "COM4", "COM5"]


def test_keeps_current_selection_when_still_present():
    # A manual Refresh shouldn't move the user off their current pick.
    assert _select_index(PORTS, current="COM5", preferred="COM3") == 2


def test_uses_preferred_when_no_current():
    # Dialog open: no current selection yet -> default to the last-used port.
    assert _select_index(PORTS, current=None, preferred="COM4") == 1


def test_preferred_used_when_current_no_longer_present():
    assert _select_index(PORTS, current="COM9", preferred="COM4") == 1


def test_falls_back_to_first_port():
    assert _select_index(PORTS, current=None, preferred=None) == 0
    assert _select_index(PORTS, current="COMX", preferred="COMY") == 0


def test_empty_device_list_is_safe():
    assert _select_index([], current="COM3", preferred="COM3") == 0
