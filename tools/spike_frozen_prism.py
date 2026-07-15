"""Throwaway spike: does prism survive PyInstaller freezing, and at what cost?

Context: build.py excludes prism/win32more, so the release .exe has no speech.
That was decided in the webview era, when an ARIA live region did the announcing
and prism was genuinely supplemental. The native UI has no live region, and the
Windows cell cursor (Left/Right) is announced ONLY through prism — so a
prism-less build navigates cells silently. Before changing build.py, establish:

  1. Can a frozen app import prism and acquire a speech backend at all?
     (win32more's bindings are generated/lazily imported, which PyInstaller's
     static analysis may not follow — the open question.)
  2. What does bundling it cost in MB?

Run it FROZEN (a console build, so stdout is readable):

  uv run pyinstaller --onedir --console --name prism_spike \
      --distpath build/spike-dist --workpath build/spike-work \
      --specpath build/spike-spec tools/spike_frozen_prism.py
  build/spike-dist/prism_spike/prism_spike.exe

Delete this file once build.py is settled — it is a spike, not a test.
"""

import sys


def main() -> int:
    print(f"frozen: {getattr(sys, 'frozen', False)}")
    print(f"_MEIPASS: {getattr(sys, '_MEIPASS', '(none)')}")

    try:
        import prism
    except Exception as exc:  # noqa: BLE001
        print(f"FAIL: import prism -> {exc!r}")
        return 1
    print(f"OK: import prism from {getattr(prism, '__file__', '?')}")

    try:
        ctx = prism.Context()
    except Exception as exc:  # noqa: BLE001
        print(f"FAIL: prism.Context() -> {exc!r}")
        return 1
    print("OK: prism.Context() constructed")

    try:
        count = int(ctx.backends_count)
    except Exception as exc:  # noqa: BLE001
        print(f"FAIL: backends_count -> {exc!r}")
        return 1
    print(f"backends_count: {count}")
    if count <= 0:
        print("FAIL: no speech backends available in the frozen app")
        return 1

    try:
        backend = ctx.create_best()
    except Exception as exc:  # noqa: BLE001
        print(f"FAIL: create_best() -> {exc!r}")
        return 1
    try:
        name = backend.name
    except Exception as exc:  # noqa: BLE001
        name = f"(name unreadable: {exc!r})"
    print(f"OK: backend acquired -> {name}")

    # Speak something so a listening human can confirm audio actually comes out;
    # the exit code only proves the API worked, not that it was audible.
    try:
        backend.speak("Frozen prism spike: speech is working.", interrupt=True)
        print("OK: speak() returned (listen for it)")
    except Exception as exc:  # noqa: BLE001
        print(f"FAIL: speak() -> {exc!r}")
        return 1

    print("\nRESULT: prism works frozen.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
