# VRP out-of-tree CHIRP drivers

Drivers here add support for radios **before** they are accepted into upstream
CHIRP. They live in the VRP tree (committed, versioned with VRP) rather than in
`./chirp/chirp/drivers/`, because `./chirp` is vendored **unmodified** and
re-cloned to the pinned `CHIRP_COMMIT` (see the top-level `CLAUDE.md` and
`README.md`) — anything dropped inside it is wiped on the next CHIRP update, and
editing it is forbidden.

Each module is a **normal, upstream-shaped CHIRP driver** (same imports, same
`@directory.register` decorator, same `chirp_common.CloneModeRadio` API) so it
can be submitted to CHIRP as-is. `__init__.py::register_all()` registers them at
runtime; `chirp_backend.radio._ensure_chirp()` calls it once, right after
`directory.import_drivers()`.

## How registration survives updates

`register_all()` walks `_EXTRA_DRIVERS` (a list of
`(module, class, radio_class_id)`). For each entry:

- If CHIRP **already** provides that `radio_class_id` (it was accepted upstream
  and is in the pinned `./chirp`), the local module is **not imported** — so its
  `@directory.register` never runs and there is no *"Duplicate radio driver id"*
  crash. Upstream always wins.
- Otherwise the module is imported (its decorator registers the class) and the
  radio appears in `list_radio_models()` / the Download picker.
- Any failure (renamed CHIRP dependency, import error) is logged as a warning
  and never aborts app startup.

The id is hard-coded in `_EXTRA_DRIVERS` on purpose, so the "already upstream?"
check happens *before* the module is imported.

**This means the transition is safe with zero code changes:** the day a CHIRP
bump includes the upstreamed driver, VRP silently uses the upstream copy. You
then delete the local module at your leisure (see "Retiring").

## Currently staged

| Module | Radio | id | Status |
|--------|-------|----|--------|
| `kguv96m.py` | Wouxun KG-UV96M | `Wouxun_KG-UV96M` | read-only; upload not yet mapped |

## Adding a driver

1. Write `chirp_backend/extra_drivers/<name>.py` as a standard CHIRP driver
   with `@directory.register` on the class.
2. Add `(<name>, <ClassName>, "<Vendor>_<Model>")` to `_EXTRA_DRIVERS` in
   `__init__.py`. The id must equal `chirp.directory.radio_class_id(cls)`
   (`"<VENDOR>_<MODEL>"`, spaces/slashes → `_`).
3. Add a row to the table above.
4. Add/extend `tests/test_extra_drivers.py` so a future CHIRP bump that breaks
   the driver is caught by CI.

## Submitting upstream to CHIRP

The module is drop-in — no code changes needed:

1. Copy `<name>.py` into a CHIRP checkout at `chirp/chirp/drivers/<name>.py`.
2. Add a test image at `chirp/tests/images/<Vendor>_<Model>.img` (a real clone;
   for the KG-UV96M, `uv96m-live.img` from a download is suitable — scrub any
   personal call signs first if you prefer).
3. Run CHIRP's driver test suite (`tox`/`pytest`) against it.
4. Open a merge request per CHIRP's contribution guide
   (<https://chirpmyradio.com/projects/chirp/wiki/DevelopersMemoryDriver>).

## Retiring (after upstream acceptance)

1. `uv run python tools/update_chirp.py` until the pinned `CHIRP_COMMIT`
   includes the upstreamed driver (its id shows up in
   `list_radio_models()` on its own).
2. Confirm `register_all()` now logs *"CHIRP already provides … skipping"* for
   the id (it will, automatically).
3. Delete the module here and its `_EXTRA_DRIVERS` row; drop the driver-specific
   assertions from `tests/test_extra_drivers.py`.
4. Rebuild. End users move to the upstream driver transparently.
