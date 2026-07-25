"""Throwaway spike: are CHIRP's drivers actually REGISTERED in a frozen build?

Symptom: the release .exe fails to open any image with "Unsupported model
Baofeng UV-5R Mini".

Hypothesis: chirp/drivers/__init__.py builds __all__ by globbing *.py off the
filesystem. Frozen, the drivers live in the PYZ archive and there are no .py
files on disk, so __all__ == [] — and directory.import_drivers()'s frozen branch
(`if sys.platform == 'win32' and frozen`) iterates exactly that list, so it
imports nothing and the registry stays empty. --collect-submodules bundles the
modules but nothing imports them. Upstream converts that file to a static list
at package time; VRP does not.

Also probes the candidate fix: can pkgutil.iter_modules() enumerate the drivers
from PyInstaller's frozen importer, so VRP can repopulate __all__ at runtime
without editing ./chirp (which is forbidden)?

Run it FROZEN with the same flags build.py uses, plus --console:

  uv run pyinstaller --onedir --console --name drv_spike --noconfirm \
      --paths=chirp --collect-submodules=chirp.drivers --collect-data=lark \
      --distpath build/spike-dist --workpath build/spike-work \
      --specpath build/spike-spec tools/spike_frozen_drivers.py
  build/spike-dist/drv_spike/drv_spike.exe <path-to-test-image.img>

Delete once the fix is settled — this is a spike, not a test.
"""

import sys


def main() -> int:
    print(f"frozen: {getattr(sys, 'frozen', False)}")

    import chirp.drivers

    all_list = list(getattr(chirp.drivers, "__all__", []))
    print(f"chirp.drivers.__all__: {len(all_list)} entries")
    if all_list[:3]:
        print(f"  sample: {all_list[:3]}")

    # Candidate fix: enumerate via pkgutil against the frozen importer.
    import pkgutil

    try:
        found = [
            m.name
            for m in pkgutil.iter_modules(chirp.drivers.__path__)
            if not m.name.startswith("__")
        ]
        print(f"pkgutil.iter_modules: {len(found)} modules")
        if found[:3]:
            print(f"  sample: {found[:3]}")
    except Exception as exc:  # noqa: BLE001
        found = []
        print(f"pkgutil.iter_modules FAILED: {exc!r}")

    # Drive VRP's REAL entry point (chirp_backend.radio), not directory
    # directly — that is the path the app uses, and where the repair lives.
    from chirp_backend import radio as rb
    from chirp import directory

    rb._ensure_chirp()
    registered = len(directory.DRV_TO_RADIO)
    print(f"registered drivers after VRP's _ensure_chirp(): {registered}")
    if registered == 0:
        print("FAIL: no drivers registered — every image will be 'Unsupported'")
        return 1

    if len(sys.argv) > 1:
        path = sys.argv[1]
        print(f"\nopening {path} via radio.load_image()")
        ok, message = rb.load_image(path)
        print(f"  ok={ok}  message={message}")
        if not ok:
            print("FAIL: could not open the image")
            return 1
        state = rb.get_state()
        print(f"OK: loaded -> {state.radio.VENDOR} {state.radio.MODEL}")

    print("\nRESULT: drivers register and images open in a frozen build.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
