"""``RadioState.is_modified`` lifecycle.

Regression test for the bug where ordinary channel operations (edit, delete,
move, …) went through ``memory_ops`` straight to the radio's ``set_memory``/
``erase_memory`` and never marked the image dirty, so Radio Info reported
"Unsaved changes: No" after real edits. The fix marks it dirty in the recorder
wrapper (``radio._install_undo``) — the one choke point every write passes
through — so this exercises a *real* loaded radio, not the memory_ops stub.
"""

import os

from chirp_backend import memory_ops
from chirp_backend import radio as radio_backend

IMAGE = os.path.abspath(
    os.path.join(
        os.path.dirname(__file__), "..", "chirp", "tests", "images",
        "Baofeng_UV-5R.img",
    )
)


class TestIsModifiedLifecycle:
    def teardown_method(self):
        radio_backend.unload()

    def test_fresh_load_is_clean(self):
        radio_backend.load_image(IMAGE)
        assert radio_backend.get_state().is_modified is False

    def test_edit_dirties_save_clears_undo_redirties(self, tmp_path):
        radio_backend.load_image(IMAGE)
        state = radio_backend.get_state()
        assert state.is_modified is False

        n = state.memory_bounds[0]
        ok, _msg, _affected, _note = memory_ops.set_channel_field(n, "name", "DIRTY")
        assert ok
        assert state.is_modified is True  # a channel edit dirties the image

        out = tmp_path / "out.img"
        ok, _msg = radio_backend.save_image(str(out))
        assert ok
        assert state.is_modified is False  # saving clears it

        mgr = radio_backend.get_undo_manager()
        assert mgr.undo() is not None
        assert state.is_modified is True  # an undo mutates vs. disk → dirty again

    def test_delete_dirties(self):
        radio_backend.load_image(IMAGE)
        state = radio_backend.get_state()
        n = state.memory_bounds[0]
        ok, _msg, _affected = memory_ops.delete_memory(n)
        assert ok
        assert state.is_modified is True
