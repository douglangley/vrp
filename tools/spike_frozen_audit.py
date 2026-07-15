"""Throwaway spike: audit EVERY CHIRP subsystem VRP uses, inside a frozen build.

Context: the frozen app registered zero drivers because chirp/drivers/__init__.py
globs *.py off the filesystem and a frozen build has no .py files on disk. That
was one instance of a class of bug — "CHIRP finds things dynamically / via the
filesystem, PyInstaller's static analysis can't see it, and it fails only when
frozen". The developer asked the obvious follow-up: what ELSE is broken?
Serial and RepeaterBook especially, since build.py's comments claim chirp.sources
is not collected (stale — RepeaterBook returned 2026-07-09) and that `requests`
is therefore absent.

So: don't reason, run it. Each check exercises VRP's real backend entry point
(chirp_backend.*), frozen, and prints PASS/FAIL. Anything that fails here is
broken in the shipped .exe today.

Build it with build.py's REAL flags plus --console and --paths=. :

  uv run pyinstaller --onedir --console --name audit_spike --noconfirm \
      --paths=. --paths=chirp --collect-submodules=chirp.drivers \
      --collect-binaries=prism --collect-data=lark \
      --exclude-module=win32more --exclude-module=numpy \
      --add-data="chirp/chirp/stock_configs;chirp/stock_configs" \
      --distpath build/spike-dist --workpath build/spike-work \
      --specpath build/spike-spec tools/spike_frozen_audit.py
  build/spike-dist/audit_spike/audit_spike.exe <image.img>

Delete once the frozen surface is trusted — this is a spike, not a test.
"""

import os
import sys
import tempfile
import traceback

RESULTS = []


def check(name):
    """Decorator: run a check, record PASS/FAIL, never abort the audit."""
    def wrap(fn):
        try:
            detail = fn()
            RESULTS.append((True, name, detail))
            print(f"PASS  {name}: {detail}")
        except Exception as exc:  # noqa: BLE001
            RESULTS.append((False, name, f"{type(exc).__name__}: {exc}"))
            print(f"FAIL  {name}: {type(exc).__name__}: {exc}")
            traceback.print_exc()
        return fn
    return wrap


def main() -> int:
    image = sys.argv[1] if len(sys.argv) > 1 else None
    print(f"frozen: {getattr(sys, 'frozen', False)}\n")

    from chirp_backend import radio as rb

    @check("drivers registered")
    def _drivers():
        from chirp import directory
        rb._ensure_chirp()
        n = len(directory.DRV_TO_RADIO)
        if n < 500:
            raise AssertionError(f"only {n} drivers registered")
        return f"{n} drivers"

    @check("radio model list (Download dialog)")
    def _models():
        models = rb.list_radio_models()
        if len(models) < 500:
            raise AssertionError(f"only {len(models)} models")
        return f"{len(models)} models, e.g. {models[0]['label']!r}"

    @check("describe_model (Radio details)")
    def _describe():
        models = rb.list_radio_models()
        text = rb.describe_model(models[0]["id"])
        if not text:
            raise AssertionError("empty model description")
        return f"{len(text)} chars for {models[0]['label']!r}"

    @check("serial port enumeration")
    def _serial():
        ports = rb.list_serial_ports()
        # An empty list is legitimate (no cable attached); the point is that
        # pyserial's platform-specific list_ports backend imports at all.
        import serial.tools.list_ports  # noqa: F401
        return f"{len(ports)} port(s) — pyserial backend imported"

    @check("band plans (offset suggestion)")
    def _bandplan():
        from chirp_backend import bandplan
        bandplan.set_region("north_america")
        offset = bandplan.suggest_offset_hz(146520000)
        if not offset:
            raise AssertionError("no 2m offset suggested — band plan not loaded")
        return f"2m offset suggestion = {offset} Hz"

    @check("stock configs / frequency lists (data files)")
    def _stock():
        from chirp_backend import stock_configs
        configs = stock_configs.list_configs()
        if not configs:
            raise AssertionError("no stock configs found — --add-data missing?")
        name, path = configs[0]
        desc = stock_configs.describe_config(path)
        return f"{len(configs)} lists; first={name!r} describes in {len(desc)} chars"

    @check("open a stock config as an import source (generic_csv driver)")
    def _stock_open():
        from chirp_backend import stock_configs
        target = next(
            (p for n, p in stock_configs.list_configs() if "NOAA" in n), None
        ) or stock_configs.list_configs()[0][1]
        src, message = rb.open_image_as_source(target)
        if src is None:
            raise AssertionError(f"could not open stock config: {message}")
        return f"opened {os.path.basename(target)!r}"

    @check("RepeaterBook backend import (chirp.sources + requests)")
    def _rb_import():
        import requests  # noqa: F401  — build.py's comment claims this is absent
        from chirp.sources import repeaterbook as chirp_rb  # noqa: F401
        from chirp_backend import repeaterbook
        countries = repeaterbook.countries()
        states = repeaterbook.states("United States")
        modes = repeaterbook.modes()
        if not countries or not states or not modes:
            raise AssertionError("empty geography lists")
        return (f"{len(countries)} countries, {len(states)} US states, "
                f"{len(modes)} modes; requests {requests.__version__}")

    @check("RepeaterBook params + cache dir (chirp_platform.config_file)")
    def _rb_params():
        from chirp_backend import repeaterbook
        params = repeaterbook.build_params(country="United States", state="Oregon")
        from chirp import platform as chirp_platform
        db_dir = chirp_platform.get_platform().config_file("repeaterbook")
        return f"{len(params)} params; cache dir resolves to {db_dir!r}"

    if "--network" in sys.argv:
        @check("RepeaterBook LIVE fetch (requests + TLS/certifi, frozen)")
        def _rb_fetch():
            # The check that actually matters: importing the module proves
            # nothing about whether a real HTTPS fetch works from a frozen app
            # (TLS needs certifi's CA bundle bundled as data).
            from chirp_backend import repeaterbook
            params = repeaterbook.build_params(
                country="United States", state="Delaware", open_only=True,
            )
            seen = []
            ok, message, result = repeaterbook.fetch(
                params, lambda m, p: seen.append(m)
            )
            if not ok:
                raise AssertionError(message)
            count = repeaterbook.result_count(result) if result else 0
            if count <= 0:
                raise AssertionError(f"fetch ok but no results: {message}")
            lines = repeaterbook.result_lines(result)
            return f"{count} repeaters; first={lines[0][:60]!r}"

    if image:
        @check("load a radio image")
        def _load():
            ok, message = rb.load_image(image)
            if not ok:
                raise AssertionError(message)
            return message

        @check("radio settings editor")
        def _settings():
            if not rb.has_settings():
                return "this radio exposes no settings (not a failure)"
            settings = rb.get_radio_settings()
            return f"{len(settings)} settings group(s)"

        @check("banks editor")
        def _banks():
            from chirp_backend import bank_ops
            state = bank_ops.get_bank_state(0)
            return f"ok={state.get('ok')} message={state.get('message', '')!r}"

        @check("export to CSV")
        def _export():
            path = os.path.join(tempfile.gettempdir(), "vrp_audit_export.csv")
            ok, message, count = rb.export_to_csv(path)
            if not ok:
                raise AssertionError(message)
            os.remove(path)
            return f"{count} channels exported"

    failed = [r for r in RESULTS if not r[0]]
    print(f"\n==== {len(RESULTS) - len(failed)}/{len(RESULTS)} passed ====")
    for _ok, name, detail in failed:
        print(f"  BROKEN: {name} -> {detail}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
