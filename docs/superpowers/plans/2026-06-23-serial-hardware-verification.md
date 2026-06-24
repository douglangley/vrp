# Serial Radio Hardware — Verification & Hardening Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Status:** ◐ in progress — started 2026-06-23. Tracked from
[ROADMAP.md](ROADMAP.md).

**Goal:** Get VRP's Radio ▸ Download from Radio / Upload to Radio commands
working end-to-end against a real radio on a real serial port, using CHIRP's
own driver/clone machinery exclusively — no custom protocol code. The user
has a confirmed-working connection on **COM4** (verified with RT Systems
software), so the cable/driver/OS layer is known-good; what's unverified is
VRP's own use of CHIRP's clone API.

**Tech stack:** Python 3.11, `chirp_backend/radio.py` (CHIRP wrapper),
`vrp/serial_dialogs.py` + `vrp/native/main_window.py` (UI), pytest with
mocked `serial.Serial`. Run everything with `uv run ...`.

**No hardware access for the agent.** Tasks 1-6 are headless-testable
(mocked serial) and can be implemented and verified without the radio. Task 7
(the actual go/no-go) requires the user to run it locally on COM4 with the
physical radio — that step is explicitly the user's to run, not something to
attempt or claim as verified without them.

---

## Findings (read before starting)

`chirp_backend/radio.py`'s `download_from_radio`/`upload_to_radio` already do
this the right way in spirit: they call `directory.get_radio(driver_id)`,
construct `radio_class(pipe)`, set `radio.status_fn`, and call
`radio.sync_in()`/`radio.sync_out()` — the same calls CHIRP's own GUI makes.
Comparing line-by-line against CHIRP's actual GUI implementation
(`chirp/chirp/wxui/clone.py`: `open_serial()`, `ChirpDownloadDialog`,
`ChirpUploadDialog`) found four gaps. Every fix below is reading more
driver-class metadata that's already in the library — not protocol
reverse-engineering:

1. **No RTS/DTR/flow-control setup.** For a real COM/tty port (not a
   `serial_for_url` string), CHIRP's `open_serial()` actually does (via its
   `SerialTrace` subclass, see point 1a below) the equivalent of:
   ```python
   pipe = serial.Serial()        # NO port= here -> stays closed
   pipe.baudrate = rclass.BAUD_RATE
   pipe.timeout = 0.25
   pipe.rtscts = rclass.HARDWARE_FLOW
   pipe.rts = rclass.WANTS_RTS
   pipe.dtr = rclass.WANTS_DTR
   pipe.port = port
   pipe.open()
   ```
   (Verified against the installed pyserial: `serial.Serial.__init__` only
   auto-opens when `port=` is passed to the constructor; `do_not_open` is a
   `serial_for_url`-only kwarg, not a plain-`Serial` one — my first read of
   this conflated the two. `rts`/`dtr`/`rtscts` are settable as properties
   before `.open()`.) VRP currently just does
   `serial.Serial(port, radio_class.BAUD_RATE, timeout=1)`, which auto-opens
   immediately with RTS/DTR at pyserial's defaults (both asserted true) and
   never consults `HARDWARE_FLOW`/`WANTS_RTS`/`WANTS_DTR` at all. Base class
   defaults in `chirp_common.Radio`: `HARDWARE_FLOW = False`,
   `WANTS_DTR = True`, `WANTS_RTS = True` (`chirp/chirp/chirp_common.py`
   ~line 1264) — most drivers don't override these, so this gap is silent
   for most radios, but it's a real footgun for the ones that do, and is the
   single most likely cause of "connects but the radio never responds."

   **1a. CHIRP traces every byte to a file already — use that instead of a
   generic debug log.** The class CHIRP actually constructs for a real port
   is `chirp.wxui.serialtrace.SerialTrace`, a `serial.Serial` subclass that
   hex-dumps every byte written/read (with a timestamp and explicit
   `# timeout` markers) to a per-session temp file
   (`chirp-trace-*.txt`) — exactly the "write a lot to a file, read the
   file" capability the user wants for debugging a real clone session, and
   far more useful than a Python `logging` file handler (it shows the actual
   wire bytes, not just driver log statements). **However**, it lives under
   `chirp.wxui`, which CLAUDE.md forbids importing ("Never import from
   chirp.wxui — that's the inaccessible GUI we're replacing"). The class
   itself has no `wx` dependency (only `chirp.util` + a `CONF` import that
   the visible code doesn't even use), so this is a packaging-boundary rule,
   not a real coupling problem — the fix is to **port a copy of this ~90-line
   class into `chirp_backend/` as VRP's own**, crediting the original, rather
   than importing across the forbidden boundary. This replaces the
   generic-logging idea in the original Task 1 below.
2. **No `detect_from_serial()`.** After opening the pipe, CHIRP does:
   ```python
   try:
       rclass = rclass.detect_from_serial(serial)
   except NotImplementedError:
       pass  # no detection available/needed
   except errors.RadioError as e:
       fail(e)  # detection explicitly failed
   ```
   Driver families with submodel auto-detection (e.g. several Baofeng/BTECH
   variants) rely on this. VRP downloads with whatever `driver_id` the user
   picked and never re-detects — a close-but-wrong variant pick can produce
   a corrupted read that looks like random failure.
3. **No `get_prompts()`.** `chirp_common.Radio.get_prompts()` returns a
   `RadioPrompts` with `experimental`, `info`, `pre_download`, `pre_upload`,
   and `display_pre_upload_prompt_before_opening_port`. CHIRP's dialogs show
   these, in order, **before** (or for `pre_upload`, sometimes after,
   depending on the flag) opening the serial port. Some of these are literal
   required manual steps for the radio's clone mode (e.g. "turn the radio
   off, hold MONI+PTT, plug in the cable, then click OK"). VRP shows none of
   them — for a radio that needs the manual step, the transfer will simply
   fail or hang with no indication why.
4. **Serial timeout 1s vs CHIRP's 0.25s.** Minor; match it for consistency
   with how drivers are tuned/tested upstream.

**Second tool, not a dependency:** CHIRP ships a CLI, `./chirp/chirpc` (→
`chirp.cli.main`), supporting `--list-radios`, and
`--serial PORT --radio ID --download-mmap out.img` /
`--upload-mmap in.img`. Use it as ground truth when debugging, run directly
by the user — **not** something VRP shells out to:
- If `chirpc` succeeds against COM4 and VRP doesn't (yet), the gaps above are
  almost certainly why.
- If `chirpc` *also* fails the same way, the problem is below VRP's code
  entirely (cable/driver/OS) — stop and diagnose there instead of chasing
  the app.

**Debug logging ("write to a file, read the file"):** see finding 1a above —
Task 1 ports CHIRP's own byte-level serial trace file rather than adding a
generic Python log handler, so a real clone session can be captured and
handed back for diagnosis (raw bytes in/out, with timeouts marked) without
the agent needing console/hardware access.

---

## Task 1: Port CHIRP's byte-level serial trace into `chirp_backend`

**Files:** New `chirp_backend/serial_trace.py` (ported from
`chirp/chirp/wxui/serialtrace.py` — read it first). Maybe modify:
`README.md` ("Debug logging").

- [ ] Create `chirp_backend/serial_trace.py` with a `TracingSerial(serial.Serial)`
  class: same behavior as `chirp.wxui.serialtrace.SerialTrace` (`open()`
  creates a per-session trace file and hex-dumps writes/reads with
  timestamps; `close()` finalizes it) — but **do not import
  `chirp.wxui.serialtrace`** (CLAUDE.md: never import from `chirp.wxui`).
  Port the logic as VRP's own module; a one-line comment noting it mirrors
  `chirp/chirp/wxui/serialtrace.py` is enough attribution (same GPLv3
  codebase, not a foreign license). Drop the unused `warn_timeout`
  baud-rate-vs-timeout warning decorator and the global `purge_trace_files`
  history-of-10 bookkeeping — VRP only needs one trace per clone session,
  not a rolling history; keep `get_trace_entry`'s hexdump formatting as-is
  (it's the useful part).
- [ ] Trace file location: alongside the existing config dir (see
  `vrp/config.py::_default_path` — the directory is named
  `OpenMemoryWriter`, the project's pre-rename name, kept deliberately so
  existing installs don't need a migration; reuse that same directory, do
  **not** introduce a new `VRP` folder name), e.g.
  `.../OpenMemoryWriter/serial-trace.txt`, one file per clone session
  (overwritten each time — simplest for "read the most recent one").
- [ ] Use `TracingSerial` (not plain `serial.Serial`) in the port-open helper
  added in Task 2, gated on `--debug` (no point tracing every normal run).
- [ ] Log the resolved trace-file path at INFO level when a clone starts, so
  it's visible in console/`--debug` output and easy to point the user at.
- [ ] Test: construct a `TracingSerial` against a closed/fake port (or mock
  the underlying open) and assert a trace file is created on `open()` and
  finalized on `close()`; assert `get_trace_entry`-style formatting on a
  known byte string produces the expected hexdump lines (port directly from
  CHIRP's own test coverage style if one exists for `serialtrace.py`).
- [ ] Document the trace-file path + that it's debug-only in README.
- [ ] Commit.

## Task 2: Fix serial port setup (RTS/DTR/flow control + timeout)

**Files:** Modify `chirp_backend/radio.py`. New test in `tests/`.

- [ ] Add `_open_radio_serial(port: str, radio_class, *, trace: bool = False) -> serial.Serial`:
  mirrors the **non-URL** branch of `open_serial()` in
  `chirp/chirp/wxui/clone.py` (VRP only deals with real COM/tty ports, never
  `serial_for_url` strings or the fake-serial dev backends):
  ```python
  cls = TracingSerial if trace else serial.Serial   # Task 1
  pipe = cls()                  # NO port kwarg here — must stay closed
  pipe.baudrate = radio_class.BAUD_RATE
  pipe.timeout = 0.25
  pipe.rtscts = radio_class.HARDWARE_FLOW
  pipe.rts = radio_class.WANTS_RTS
  pipe.dtr = radio_class.WANTS_DTR
  pipe.port = port
  pipe.open()
  ```
  Note the order: `port` is set last and `.open()` is called explicitly —
  passing `port=` to the constructor would auto-open before RTS/DTR/flow
  control are configured, defeating the point. (Confirmed against the
  installed pyserial's `SerialBase.__init__`: a port is opened immediately
  *only* if `port=` is given to the constructor; there is no `do_not_open`
  kwarg on plain `Serial`, only on `serial_for_url`, which VRP doesn't use.)
- [ ] Use it in both `download_from_radio` and `upload_to_radio`, replacing
  the current bare `serial.Serial(port, radio_class.BAUD_RATE, timeout=1)`.
- [ ] Test (mock `serial.Serial`/`TracingSerial`, no real port): construct a
  fake radio class with `HARDWARE_FLOW=True, WANTS_RTS=False,
  WANTS_DTR=True, BAUD_RATE=19200` and assert the mock received exactly
  those values, that `port` was assigned after `rts`/`dtr`/`rtscts`, and
  that `.open()` was called last.
- [ ] `uv run pytest` green.
- [ ] Commit.

## Task 3: `detect_from_serial()` before `sync_in()`

**Files:** Modify `chirp_backend/radio.py::download_from_radio`. New test.

- [ ] After opening the pipe and before constructing the radio used for
  `sync_in()`, call `radio_class.detect_from_serial(pipe)`:
  - Returns a class → rebuild `radio = detected_class(pipe)` instead of
    `radio_class(pipe)` (mirrors `ChirpDownloadDialog._actual_action`).
  - Raises `NotImplementedError` → keep `radio_class` unchanged (this is the
    common case — most drivers don't implement detection).
  - Raises `chirp.errors.RadioError` → treat as a download failure with that
    error's message (don't silently fall back).
- [ ] Test with 3 fake driver classes exercising each branch (returns a
  class / raises `NotImplementedError` / raises `RadioError`) — no real
  serial needed, pipe can be a `unittest.mock.Mock()`.
- [ ] `uv run pytest` green.
- [ ] Commit.

## Task 4: Surface `get_prompts()` through the dialogs

**Files:** Modify `chirp_backend/radio.py` (new helper — keeps the
chirp-touching code in the existing seam), `vrp/serial_dialogs.py` and/or
`vrp/native/main_window.py::on_download`/`on_upload`. New tests.

- [ ] **Layering note:** every file under `vrp/` other than
  `settings_dialog.py` (one narrow, pre-existing exception for a type
  import) goes through `chirp_backend`, never `chirp.*`, directly —
  `main_window.py` only ever does `from chirp_backend import radio as
  radio_backend`. Don't break that pattern here: add
  `chirp_backend.radio.get_clone_prompts(driver_id: str) -> dict` (download)
  and a `get_clone_prompts_for_loaded_radio() -> dict` (upload, reads
  `_state.radio`'s class) returning a plain
  `{"experimental": str|None, "info": str|None, "pre": str|None}` dict (`pre`
  already picks `pre_download`/`pre_upload` server-side so the UI layer
  doesn't need to know which direction maps to which attribute name) — this
  is what `vrp/serial_dialogs.py` consumes, not `RadioPrompts`/`directory`
  directly.
- [ ] Add `serial_dialogs.show_radio_prompts(parent, prompts: dict) -> bool`:
  shows, **in this order, each as a native accessible dialog, before the
  serial port is opened**:
  1. `experimental` — Yes/No, **default No**, must explicitly accept to
     continue (`wx.MessageBox` with `wx.YES_NO | wx.NO_DEFAULT`).
  2. `info` — OK/Cancel.
  3. `pre` — OK/Cancel, exact wording from the driver (these are often
     literal required steps).
  Returns `False` (abort, don't touch the port) if any prompt is
  cancelled/declined; `True` to proceed. A driver with no prompts set (the
  common case — all three dict values `None`) shows nothing and returns
  `True` immediately.
- [ ] Wire into `on_download` (call right after the model/port picker dialog
  returns OK, before `_run_clone`) and `on_upload`. **Open product question,
  not yet decided — flag for the user rather than guessing:** for upload,
  should the CHIRP driver prompts show before or after VRP's own "this will
  overwrite ALL memory channels" confirm? CHIRP's own dialog has no
  equivalent destructive-confirm (VRP added it independently), so there's no
  existing-behavior answer to mirror. Default assumption for this task:
  prompts first (tell the user what they need to do), destructive confirm
  second (then ask if they're sure) — but confirm this ordering with the
  user before or during implementation rather than treating it as settled.
- [ ] Test: `get_clone_prompts`/`get_clone_prompts_for_loaded_radio` against
  a fake driver class with all `RadioPrompts` fields set, and one with none
  set (dict values all `None`). `show_radio_prompts` test: a prompts dict
  with all three keys set drives the right sequence of (mocked) dialog
  calls in order; all-`None` shows nothing and returns `True` immediately;
  declining `experimental` short-circuits before `info`/`pre` are shown.
- [ ] `uv run pytest` green.
- [ ] Commit.

## Task 5: Full test suite + review

- [ ] `uv run pytest` — full suite green (existing + new tests from 1-4, all
  headless/mocked, no hardware needed).
- [ ] Re-read `chirp_backend/radio.py::download_from_radio`/`upload_to_radio`
  end to end once more after tasks 2-4 land, to confirm the call order
  matches CHIRP's `ChirpDownloadDialog`/`ChirpUploadDialog` exactly: open
  port → detect (download only) → prompts already shown earlier, before
  open, per Task 4 → construct/rebuild radio → set `status_fn` → `sync_in`/
  `sync_out` → close pipe.
- [ ] Commit (if anything changed during the re-read).

## Task 6: Find the exact CHIRP driver id for the user's radio

This step doesn't require the radio connected — `chirpc --list-radios` lists
every driver CHIRP knows about, so the right `driver_id` (and exact
vendor/model/variant spelling for the model-filter field in VRP's
`DownloadDialog`) can be confirmed ahead of the live test.

- [ ] User runs (from the repo root, with `./chirp` present):
  `uv run python ./chirp/chirpc --list-radios` and finds the vendor/model
  matching the physical radio (cross-check against what RT Systems was
  configured for).
- [ ] Note the exact label here once known, so Task 7 doesn't waste time on
  driver selection: _(fill in after running)_.

## Task 7: Manual hardware verification on COM4 (the user runs this — no agent hardware access)

This is the actual go/no-go. Cannot be done or simulated by the agent;
report back results (success, or the debug log + exact error) for the next
diagnosis step if it fails.

- [ ] **a.** `uv run python main.py --debug --native` — confirm the serial
  trace file path (Task 1) appears in the startup log output.
- [ ] **b.** Radio ▸ Download from Radio. In the model filter, use the
  exact label found in Task 6. Pick COM4.
- [ ] **c.** Start the download. Follow any prompt dialogs from Task 4
  exactly as worded (if the driver has none, none will appear — that's
  expected, not a bug).
- [ ] **d.** On success: confirm the channel grid populates and the channel
  contents look right (spot-check a few channels the user knows from RT
  Systems). On failure: capture the serial trace file (Task 1's path) and
  the exact on-screen error message — that's the data needed to diagnose
  further without hardware access.
- [ ] **e.** Repeat for Upload to Radio: make a small, easily-verified change
  in VRP (e.g. rename one channel to something distinctive), upload, then
  either re-download and confirm the change persisted, or check the radio's
  own front-panel display.
- [ ] **f.** If either direction is ever in doubt, cross-check directly with
  `chirpc` (`uv run python ./chirp/chirpc --serial COM4 --radio <id>
  --download-mmap test.img`) using the same id from Task 6 — same
  ground-truth role described in Findings.

## Task 8: Close out

- [ ] Update `docs/chirp-feature-coverage.md`: Download/Upload rows drop the
  "(HW test owed)" qualifier once Task 7 passes.
- [ ] Add a `PROGRESS_LOG.md` entry: what was fixed (tasks 1-4), what radio/
  cable/driver id was actually tested, and which of the 4 gaps (if any)
  turned out to matter for this specific radio — that's useful signal for
  whichever radio someone tests next.
- [ ] Update [ROADMAP.md](ROADMAP.md): mark serial hardware verification ☑
  and remove it from "current priority".

---

## Out of scope (explicitly deferred, don't pull into this plan)

- **True download cancellation.** `sync_in()` isn't interruptible — CHIRP's
  own dialog only closes the pipe out from under it and lets the exception
  propagate. VRP's current "Cancel discards the result" model already
  matches this. Revisit only if a real radio is found to hang long enough
  that this matters in practice.
- **`LiveRadio`/`LiveAdapter` support** (D-STAR/DMR "live" radios that don't
  do a single clone-mode memory dump) — out of scope unless the user's
  target radio turns out to need it, which isn't expected for a COM4/
  RT-Systems-style cable setup.
- **Any change inside `./chirp`.** Never edit the vendored library (see
  CLAUDE.md). If a driver bug is found during Task 7, that's a fix for
  upstream CHIRP, not a local patch.

## Self-review notes

- Every fix (Tasks 2-4) is implemented by reading existing CHIRP driver-class
  attributes/methods (`HARDWARE_FLOW`, `WANTS_RTS`, `WANTS_DTR`, `BAUD_RATE`,
  `detect_from_serial`, `get_prompts`) — no protocol code is written, per the
  user's stated preference to maximize use of CHIRP's libraries for
  future-proofing.
- Tasks 1-5 are fully headless/mocked-serial testable; only Task 7 needs the
  physical radio, and it's explicitly called out as the user's step, not
  something to claim as verified without them actually running it.
- **Precedent set by Task 1:** porting `chirp.wxui.serialtrace.SerialTrace`'s
  logic into `chirp_backend/serial_trace.py` instead of importing it is the
  first time this project copies code out of `chirp/` rather than either
  using it unmodified or avoiding it. CLAUDE.md's "never import from
  chirp.wxui" rule is about not depending on the inaccessible GUI module,
  not about the specific logic in that module being off-limits — but this
  is a judgment call, not an explicit prior ruling, so flag it for the user
  to confirm before/while implementing Task 1, the same as the prompt-
  ordering question in Task 4.
