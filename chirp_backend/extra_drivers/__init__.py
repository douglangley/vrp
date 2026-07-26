"""VRP-maintained, out-of-tree CHIRP drivers (staging area for upstream).

``./chirp`` is vendored **unmodified** and re-cloned to a pinned commit (see
CLAUDE.md), so a driver placed inside ``chirp/chirp/drivers/`` would be wiped on
the next CHIRP update and would violate the "never edit ./chirp" rule. Drivers
for radios VRP supports *before* they are accepted upstream therefore live here,
in the VRP tree, and are registered into CHIRP's ``directory`` at runtime.

Lifecycle (see README.md for the full process):

  1. **Develop here.** Each driver module is a normal, upstream-shaped CHIRP
     driver with the standard ``@directory.register`` decorator on its class.
  2. **Ship in VRP.** ``register_all()`` (called once by
     ``chirp_backend.radio._ensure_chirp`` right after
     ``directory.import_drivers()``) imports each module so its decorator
     registers it, and it appears in ``list_radio_models()``.
  3. **Submit upstream.** The module is drop-in: copy it into
     ``chirp/chirp/drivers/`` and open a CHIRP PR (nothing here needs changing).
  4. **Retire cleanly.** Once the driver is accepted upstream *and* VRP's
     pinned ``CHIRP_COMMIT`` includes it, CHIRP registers the same id first.
     ``register_all()`` sees the id is already present and **skips importing our
     copy** — so there is never a "Duplicate radio driver id" crash during the
     window between acceptance and our deleting the local file. Delete the module
     and its ``_EXTRA_DRIVERS`` entry when convenient.

The id is hard-coded in ``_EXTRA_DRIVERS`` (not discovered by importing) exactly
so the upstream-present check can happen *before* the decorator runs.
"""
import importlib
import logging

LOG = logging.getLogger(__name__)

# (module_name, class_name, radio_class_id) for each VRP out-of-tree driver.
# radio_class_id = "<VENDOR>_<MODEL>" with spaces/slashes -> "_" (see
# chirp.directory.radio_class_id); it MUST match what the class produces.
_EXTRA_DRIVERS = [
    ("kguv96m", "KGUV96MRadio", "Wouxun_KG-UV96M"),
]


def register_all():
    """Register VRP's out-of-tree drivers into CHIRP's directory.

    Must be called after ``directory.import_drivers()``. For each driver, if
    CHIRP already provides a driver with the same id (i.e. it was accepted
    upstream and is in the pinned ./chirp), the local copy is skipped so an
    upstream driver always wins and no duplicate-id exception is raised. A
    broken/renamed dependency logs a warning instead of taking down startup.

    Returns the list of ids actually registered by VRP.
    """
    from chirp import directory

    registered = []
    for modname, clsname, rid in _EXTRA_DRIVERS:
        if rid in directory.DRV_TO_RADIO:
            LOG.info("CHIRP already provides %s upstream; "
                     "skipping VRP's out-of-tree copy", rid)
            continue
        try:
            # Importing runs the module's @directory.register decorator.
            importlib.import_module("." + modname, __name__)
            if rid in directory.DRV_TO_RADIO:
                registered.append(rid)
            else:
                LOG.warning("VRP driver module %s imported but did not register "
                            "%s (class id mismatch?)", modname, rid)
        except Exception as e:  # noqa: BLE001 — never fail app startup
            LOG.warning("Failed to load VRP out-of-tree driver %s (%s.%s): %s",
                        rid, modname, clsname, e)
    return registered
