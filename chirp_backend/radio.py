"""
Radio backend — wraps the CHIRP library for use by Flask routes.

Manages a single "active radio" (loaded image + optional live serial
connection). All state lives here so routes stay stateless.

CHIRP library notes:
  - directory.import_drivers() must be called once before any radio ops.
  - Radio classes are looked up by image content or by (vendor, model) name.
  - Memory channel numbers start at the radio's memory_bounds[0] (usually 0
    or 1 depending on the radio).
  - mem.empty == True means the slot is unused.
  - mem.immutable is a list of field names that cannot be changed.
"""

import logging
import os
import re
import threading
from dataclasses import dataclass, field
from typing import Callable, Optional

from chirp_backend.undo import UndoManager

LOG = logging.getLogger(__name__)

# Lazily import chirp so we can give a friendly error if it's not installed
_chirp_loaded = False


def _ensure_chirp() -> None:
    global _chirp_loaded
    if _chirp_loaded:
        return
    try:
        # CHIRP driver code calls the gettext builtin _() directly (e.g. the
        # RadioPrompts strings in get_prompts(), and clone-progress/error
        # messages). CHIRP's own CLI and GUI install _ before using drivers;
        # running CHIRP headless from VRP we must too, or those calls raise
        # NameError: name '_' is not defined. Identity = no translation, the
        # same shim chirpc uses. Guarded so a real translation install (if VRP
        # adds one later) is never clobbered.
        import builtins
        if not hasattr(builtins, "_"):
            builtins._ = lambda s: s  # type: ignore[attr-defined]

        from chirp import directory
        directory.import_drivers()
        _chirp_loaded = True
        LOG.info("CHIRP drivers loaded successfully")
    except ImportError as e:
        raise RuntimeError(
            "CHIRP library not found. Install it with: pip install -e ./chirp\n"
            f"Original error: {e}"
        )


@dataclass
class RadioState:
    """Holds everything about the currently loaded radio."""
    radio: object = None            # chirp CloneModeRadio instance
    image_path: Optional[str] = None
    is_modified: bool = False
    serial_port: Optional[str] = None
    # Cache of memory objects keyed by channel number, populated on load
    _mem_cache: dict = field(default_factory=dict)

    @property
    def loaded(self) -> bool:
        return self.radio is not None

    @property
    def features(self):
        """Shortcut to RadioFeatures object."""
        return self.radio.get_features() if self.radio else None

    @property
    def memory_bounds(self) -> tuple[int, int]:
        """(first_channel, last_channel) tuple."""
        if not self.radio:
            return (0, 0)
        return self.features.memory_bounds


# Global radio state — single-user local app, one radio at a time.
_state = RadioState()
_state_lock = threading.Lock()


def get_state() -> RadioState:
    return _state


def unload() -> None:
    """Clear the active radio (e.g. File ▸ Close), returning to no-radio state."""
    global _undo
    with _state_lock:
        _state.radio = None
        _state.image_path = None
        _state.is_modified = False
        _state.serial_port = None
        _state._mem_cache = {}
    _undo = None  # drop the undo history with the radio


def load_image(path: str) -> tuple[bool, str]:
    """
    Load a CHIRP .img file from disk.
    Returns (success, message).
    """
    _ensure_chirp()
    from chirp import directory

    if not os.path.exists(path):
        return False, f"File not found: {path}"

    try:
        # get_radio_by_image inspects the image header/metadata, picks the
        # owning driver, and returns a radio instance already loaded from the
        # file (it constructs the driver with the image path).
        radio = directory.get_radio_by_image(path)
        if radio is None:
            return False, "Unrecognized image format (no matching CHIRP driver)"

        with _state_lock:
            _state.radio = radio
            _state.image_path = path
            _state.is_modified = False
            _state._mem_cache = {}
        _install_undo(radio)  # fresh, empty history for the new radio

        LOG.info("Loaded image: %s (%s %s)", path,
                 radio.VENDOR, radio.MODEL)
        return True, f"Loaded {radio.VENDOR} {radio.MODEL} from {os.path.basename(path)}"

    except Exception as e:
        LOG.exception("Failed to load image %s", path)
        return False, f"Failed to load image: {e}"


def save_image(path: Optional[str] = None) -> tuple[bool, str]:
    """
    Save current image to disk.
    If path is None, saves to the original image_path.
    Returns (success, message).
    """
    with _state_lock:
        if not _state.loaded:
            return False, "No radio loaded"
        save_path = path or _state.image_path
        if not save_path:
            return False, "No save path specified"
        try:
            _state.radio.save_mmap(save_path)
            _state.image_path = save_path
            _state.is_modified = False
            return True, f"Saved to {os.path.basename(save_path)}"
        except Exception as e:
            LOG.exception("Failed to save image")
            return False, f"Failed to save: {e}"


def get_memory(number: int) -> Optional[object]:
    """
    Get a single memory channel. Returns chirp_common.Memory or None.
    Uses a simple cache — invalidated by set_memory/erase_memory.
    """
    with _state_lock:
        if not _state.loaded:
            return None
        if number not in _state._mem_cache:
            try:
                _state._mem_cache[number] = _state.radio.get_memory(number)
            except Exception as e:
                LOG.warning("get_memory(%d) failed: %s", number, e)
                return None
        return _state._mem_cache[number]


def set_memory(mem: object) -> tuple[bool, str]:
    """
    Write a memory channel back to the radio image.
    Invalidates the cache entry for that channel.
    Returns (success, message).
    """
    with _state_lock:
        if not _state.loaded:
            return False, "No radio loaded"
        try:
            _state.radio.set_memory(mem)
            _state._mem_cache[mem.number] = mem
            _state.is_modified = True
            return True, f"Channel {mem.number} updated"
        except Exception as e:
            LOG.exception("set_memory(%d) failed", mem.number)
            return False, f"Failed to set channel {mem.number}: {e}"


def erase_memory(number: int) -> tuple[bool, str]:
    """
    Erase (blank out) a memory channel.
    Returns (success, message).
    """
    with _state_lock:
        if not _state.loaded:
            return False, "No radio loaded"
        try:
            _state.radio.erase_memory(number)
            _state._mem_cache.pop(number, None)
            _state.is_modified = True
            return True, f"Channel {number} erased"
        except Exception as e:
            LOG.exception("erase_memory(%d) failed", number)
            return False, f"Failed to erase channel {number}: {e}"


def invalidate_cache(numbers: Optional[list[int]] = None) -> None:
    """Invalidate cache entries. Pass None to clear all."""
    with _state_lock:
        if numbers is None:
            _state._mem_cache.clear()
        else:
            for n in numbers:
                _state._mem_cache.pop(n, None)


# ---------------------------------------------------------------------------
# Undo / redo history (see chirp_backend/undo.py and the undo-history plan)
# ---------------------------------------------------------------------------

# One UndoManager per loaded radio. Reset (and the radio re-wrapped) on every
# load/download; cleared on close. None when no radio is loaded.
_undo: Optional[UndoManager] = None


def get_undo_manager() -> Optional[UndoManager]:
    """The active UndoManager, or None when no radio is loaded."""
    return _undo


def _install_undo(radio) -> None:
    """Wrap the CHIRP radio's ``set_memory``/``erase_memory`` so every channel
    write records a pre-image, and (re)create a fresh UndoManager for it.

    This is the single choke point: ``memory_ops._set_mem``/``_erase_mem`` call
    ``radio.set_memory``/``radio.erase_memory`` directly, and so does this
    module's own ``set_memory``/``erase_memory`` — wrapping the radio object
    catches both. ``record`` is a no-op unless an op has opened a transaction
    (see the ``@records`` decorator), so writes during load aren't recorded.

    Restores (undo/redo) go through the *original* methods, so they never
    re-record, and invalidate the cache so the next read is fresh. If a driver
    refuses attribute assignment, undo is simply disabled for that radio."""
    global _undo
    _undo = None
    try:
        orig_get = radio.get_memory
        orig_set = radio.set_memory
        orig_erase = radio.erase_memory

        def recording_set(mem):
            if _undo is not None:
                _undo.record(mem.number)
            return orig_set(mem)

        def recording_erase(number):
            if _undo is not None:
                _undo.record(number)
            return orig_erase(number)

        radio.set_memory = recording_set
        radio.erase_memory = recording_erase

        def restore_set(mem):
            orig_set(mem)
            invalidate_cache([mem.number])

        def restore_erase(number):
            orig_erase(number)
            invalidate_cache([number])

        _undo = UndoManager(
            get_memory=lambda n: orig_get(n),
            set_memory=restore_set,
            erase_memory=restore_erase,
        )
    except Exception:  # noqa: BLE001 — undo is best-effort; never block loading
        LOG.exception("Could not install undo recorder; undo disabled for this radio")
        _undo = None


def open_image_as_source(path: str) -> tuple:
    """Load an image into a standalone radio instance for IMPORT, leaving the
    active radio untouched. Returns (radio_or_None, message)."""
    _ensure_chirp()
    from chirp import directory

    if not os.path.exists(path):
        return None, f"File not found: {path}"
    try:
        src = directory.get_radio_by_image(path)
        if src is None:
            return None, "Unrecognized image format (no matching CHIRP driver)"
        return src, f"Loaded {src.VENDOR} {src.MODEL} from {os.path.basename(path)}"
    except Exception as e:  # noqa: BLE001
        LOG.exception("open_image_as_source failed: %s", path)
        return None, f"Could not open image: {e}"


def export_to_csv(path: str) -> tuple:
    """Write the loaded radio's non-empty channels to a CSV file (a separate
    file — does NOT change the working image's saved state). Returns
    (ok, message, count)."""
    with _state_lock:
        if not _state.loaded:
            return False, "No radio loaded", 0
        radio = _state.radio

    from chirp import import_logic
    from chirp.drivers import generic_csv

    try:
        features = radio.get_features()
        lo, hi = features.memory_bounds
        rows = []
        for n in range(lo, hi + 1):
            mem = radio.get_memory(n)
            if not getattr(mem, "empty", True):
                rows.append(mem)
        if not rows:
            return False, "No channels to export.", 0

        csv = generic_csv.CSVRadio(None)
        for mem in rows:
            csv.set_memory(import_logic.import_mem(csv, features, mem))
        csv.save_mmap(path)
        return True, f"Exported {len(rows)} channel(s) to {os.path.basename(path)}.", len(rows)
    except Exception as e:  # noqa: BLE001
        LOG.exception("export_to_csv failed: %s", path)
        return False, f"Export failed: {e}", 0


def describe_radio_html(state) -> str:
    """Build an accessible label/value HTML summary of the loaded radio."""
    from html import escape

    radio = state.radio
    f = radio.get_features()
    lo, hi = f.memory_bounds

    def yn(b):
        return "Yes" if b else "No"

    bands = "; ".join(
        f"{a / 1_000_000:.3f}–{b / 1_000_000:.3f} MHz"
        for a, b in (getattr(f, "valid_bands", None) or [])
    )
    modes = ", ".join(getattr(f, "valid_modes", None) or [])
    variant = getattr(radio, "VARIANT", "") or ""
    source = os.path.basename(state.image_path) if state.image_path else "Downloaded, not yet saved"

    identity = [("Vendor", radio.VENDOR), ("Model", radio.MODEL)]
    if variant:
        identity.append(("Variant", variant))
    identity += [("Source", source), ("Unsaved changes", yn(state.is_modified))]

    capacity = [("Channels", f"{hi - lo + 1} (numbered {lo} to {hi})")]

    has_name = getattr(f, "has_name", False)
    name_detail = yn(has_name)
    if has_name and getattr(f, "valid_name_length", 0):
        name_detail += f", up to {f.valid_name_length} characters"
    capabilities = [
        ("Channel names", name_detail),
        ("Banks", yn(getattr(f, "has_bank", False))),
        ("Settings", yn(getattr(f, "has_settings", False))),
        ("Comments", yn(getattr(f, "has_comment", False))),
        ("DTCS", yn(getattr(f, "has_dtcs", False))),
        ("Bands", bands or "—"),
        ("Modes", modes or "—"),
    ]

    def table(title, rows):
        cells = "".join(
            f'<tr><th scope="row">{escape(str(k))}</th><td>{escape(str(v))}</td></tr>'
            for k, v in rows
        )
        return f"<h3>{escape(title)}</h3><table>{cells}</table>"

    return (
        f"<h2>{escape(radio.VENDOR)} {escape(radio.MODEL)}</h2>"
        + table("Identity", identity)
        + table("Capacity", capacity)
        + table("Capabilities", capabilities)
    )


def has_settings() -> bool:
    """True if the loaded radio exposes editable settings."""
    with _state_lock:
        if not _state.loaded:
            return False
        return bool(getattr(_state.radio.get_features(), "has_settings", False))


def get_radio_settings():
    """Return the loaded radio's settings tree (list of RadioSettingGroup), or
    None if unavailable. The objects are live — mutate via set_value then call
    apply_radio_settings to write them back."""
    with _state_lock:
        if not _state.loaded:
            return None
        try:
            return _state.radio.get_settings()
        except Exception as e:  # noqa: BLE001
            LOG.exception("get_settings failed")
            return None


def apply_radio_settings(settings) -> tuple[bool, str]:
    """Write a (possibly edited) settings tree back to the radio image."""
    with _state_lock:
        if not _state.loaded:
            return False, "No radio loaded"
        try:
            _state.radio.set_settings(settings)
            _state.is_modified = True
            return True, "Radio settings saved"
        except Exception as e:  # noqa: BLE001
            LOG.exception("set_settings failed")
            return False, f"Failed to save settings: {e}"


def _natural_sort_key(device: str) -> tuple:
    """Sort key splitting digits from text so 'COM10' sorts after 'COM9'.

    Plain string sort puts 'COM10' before 'COM4' (comparing '1' < '4'
    character-by-character), so on a machine with both a single- and a
    double-digit port connected, the picker's default (first list entry)
    silently lands on the wrong device.
    """
    return tuple(
        int(chunk) if chunk.isdigit() else chunk.lower()
        for chunk in re.split(r"(\d+)", device)
    )


def list_serial_ports() -> list[dict]:
    """
    List available serial ports.
    Returns list of dicts: {port, description, hwid}
    """
    try:
        import serial.tools.list_ports
        ports = serial.tools.list_ports.comports()
        return [
            {"port": p.device, "description": p.description, "hwid": p.hwid}
            for p in sorted(ports, key=lambda p: _natural_sort_key(p.device))
        ]
    except ImportError:
        return []


def list_radio_models() -> list[dict]:
    """List every radio model known to CHIRP.

    Returns dicts {id, vendor, model, variant, label}, sorted by vendor/model.
    ``id`` is CHIRP's driver id (see directory.radio_class_id) — pass it back to
    download_from_radio. ``label`` is the human "Vendor Model [Variant]".
    """
    _ensure_chirp()
    from chirp import directory

    result = []
    for ident, cls in directory.DRV_TO_RADIO.items():
        vendor = getattr(cls, "VENDOR", "")
        model = getattr(cls, "MODEL", "")
        variant = getattr(cls, "VARIANT", "") or ""
        label = f"{vendor} {model}".strip()
        if variant:
            label += f" {variant}"
        result.append(
            {
                "id": ident,
                "vendor": vendor,
                "model": model,
                "variant": variant,
                "label": label,
            }
        )
    result.sort(key=lambda r: (r["vendor"].lower(), r["model"].lower(), r["variant"]))
    return result


def _prompts_dict(radio_class_or_instance, *, upload: bool) -> dict:
    """Flatten a driver's RadioPrompts into a UI-friendly dict.

    ``pre`` already resolves to pre_upload/pre_download for the given direction
    so the UI layer never needs to know which attribute maps to which way. Both
    a driver class and a radio instance expose get_prompts() (it's a
    classmethod), so either may be passed.
    """
    prompts = radio_class_or_instance.get_prompts()
    return {
        "experimental": getattr(prompts, "experimental", None),
        "info": getattr(prompts, "info", None),
        "pre": getattr(
            prompts, "pre_upload" if upload else "pre_download", None
        ),
    }


def get_clone_prompts(driver_id: str) -> dict:
    """Download-direction clone prompts for a driver id (see _prompts_dict).

    Returns all-None on an unknown id rather than raising — a missing prompt
    must never block a download the user already initiated.
    """
    _ensure_chirp()
    from chirp import directory

    try:
        radio_class = directory.get_radio(driver_id)
    except Exception:  # noqa: BLE001
        return {"experimental": None, "info": None, "pre": None}
    return _prompts_dict(radio_class, upload=False)


def get_clone_prompts_for_loaded_radio() -> dict:
    """Upload-direction clone prompts for the currently loaded radio."""
    with _state_lock:
        if not _state.loaded:
            return {"experimental": None, "info": None, "pre": None}
        radio = _state.radio
    return _prompts_dict(radio, upload=True)


def _yesno(value) -> str:
    return "Yes" if value else "No"


def describe_features(feats) -> list[str]:
    """Build the capability/spec lines for a radio's features — shared by
    ``describe_model`` (a model) and the loaded-radio Radio Info, so both show
    the same fields. Optional fields are listed only when the radio reports them.
    """
    lo, hi = feats.memory_bounds
    lines = [
        "Capacity",
        f"  Channels:         {hi - lo + 1} (numbered {lo} to {hi})",
    ]
    special = list(getattr(feats, "valid_special_chans", None) or [])
    if special:
        lines.append(f"  Special channels: {', '.join(str(s) for s in special)}")

    has_name = bool(getattr(feats, "has_name", False))
    name_cell = "Yes" if has_name else "No"
    name_len = getattr(feats, "valid_name_length", 0) if has_name else 0
    if name_len:
        name_cell = f"Yes (up to {name_len} characters)"
    lines += [
        "",
        "Capabilities",
        f"  Channel names:    {name_cell}",
        f"  Banks:            {_yesno(getattr(feats, 'has_bank', False))}",
        f"  Settings:         {_yesno(getattr(feats, 'has_settings', False))}",
        f"  Comments:         {_yesno(getattr(feats, 'has_comment', False))}",
        f"  DTCS:             {_yesno(getattr(feats, 'has_dtcs', False))}",
    ]

    tmodes = [t for t in (getattr(feats, "valid_tmodes", None) or []) if t]
    if tmodes:
        lines.append(f"  Tone modes:       {', '.join(tmodes)}")
    powers = getattr(feats, "valid_power_levels", None) or []
    if powers:
        # repr() includes the dBm ("High (36 dBm)"); str() is just the label.
        lines.append(f"  Power levels:     {', '.join(repr(p) for p in powers)}")
    steps = getattr(feats, "valid_tuning_steps", None) or []
    if steps:
        lines.append(
            f"  Tuning steps:     {', '.join(f'{s:g}' for s in steps)} kHz"
        )

    bands = "; ".join(
        f"{a / 1_000_000:.3f}–{b / 1_000_000:.3f} MHz"
        for a, b in (getattr(feats, "valid_bands", None) or [])
    )
    modes = ", ".join(getattr(feats, "valid_modes", None) or [])
    lines += [
        f"  Bands:            {bands or '—'}",
        f"  Modes:            {modes or '—'}",
    ]
    return lines


def describe_model(driver_id: str) -> str:
    """A human-readable, multi-line description of a radio MODEL (driver class):
    its capabilities and specs, for review before downloading.

    Reads the class's features with no hardware or image — every CHIRP driver
    instantiates with a ``None`` pipe and reports static features. Returns a short
    message on an unknown/uncooperative driver rather than raising.

    The driver's clone prompts (experimental warning, pre-download steps) are
    intentionally NOT included here — they're shown in the pre-download dialog
    right before a download, so repeating them here is just noise.
    """
    _ensure_chirp()
    from chirp import directory

    try:
        cls = directory.get_radio(driver_id)
    except Exception:  # noqa: BLE001
        return f"No information is available for {driver_id}."

    vendor = getattr(cls, "VENDOR", "")
    model = getattr(cls, "MODEL", "")
    variant = getattr(cls, "VARIANT", "") or ""
    title = f"{vendor} {model}".strip()
    if variant:
        title += f" {variant}"
    lines = [title, ""]

    try:
        feats = cls(None).get_features()
    except Exception:  # noqa: BLE001 — a driver that won't describe itself
        feats = None
    if feats is not None:
        lines += describe_features(feats)
    baud = getattr(cls, "BAUD_RATE", None)
    if baud:
        lines.append(f"  Baud rate:        {baud}")

    return "\n".join(lines)


def _make_status_fn(progress_callback: Callable[[int, int, str], None]):
    """Adapt CHIRP's status_fn (called with a Status object) to our callback.

    CHIRP invokes ``radio.status_fn(status)`` during clone, where status has
    .cur/.max/.msg. (The previous code mistakenly assigned a Status *instance*.)
    """
    def status_fn(status) -> None:
        progress_callback(
            getattr(status, "cur", 0),
            getattr(status, "max", 100) or 100,
            getattr(status, "msg", "") or "",
        )

    return status_fn


def _open_radio_serial(port: str, radio_class, *, trace: bool = False):
    """Open the serial port for a clone, configured for the driver class.

    Mirrors the real-port branch of CHIRP's own ``chirp.wxui.clone.open_serial``
    (VRP never uses ``serial_for_url`` strings or the fake-serial dev backends):
    construct the port object CLOSED, set baud/timeout and the driver's
    RTS/DTR/flow-control preferences as properties, THEN assign ``port`` and
    open. Passing ``port=`` to the constructor would auto-open immediately,
    before those properties are applied — which is the bug this fixes (the old
    bare ``serial.Serial(port, baud, timeout=1)`` left RTS/DTR at pyserial's
    defaults and ignored the driver's HARDWARE_FLOW/WANTS_RTS/WANTS_DTR).

    ``radio_class`` may be a driver class or an instance — BAUD_RATE,
    HARDWARE_FLOW, WANTS_RTS and WANTS_DTR are class-level constants readable
    from either.

    Always a TracingSerial, never a plain serial.Serial: CHIRP drivers call
    ``radio.pipe.log(...)`` during sync (CHIRP's GUI always wraps the port in
    its SerialTrace), so the pipe must always expose ``.log()`` or the clone
    crashes with AttributeError. ``trace`` only controls whether the byte-level
    trace FILE is written (under --debug); the .log()/write/read methods are
    present either way. See chirp_backend.serial_trace.
    """
    from chirp_backend.serial_trace import TracingSerial

    pipe = TracingSerial(trace_enabled=trace)
    pipe.baudrate = radio_class.BAUD_RATE
    pipe.timeout = 0.25
    pipe.rtscts = radio_class.HARDWARE_FLOW
    pipe.rts = radio_class.WANTS_RTS
    pipe.dtr = radio_class.WANTS_DTR
    pipe.port = port
    pipe.open()
    LOG.debug(
        "Serial opened: %s (baud=%s rts=%s dtr=%s rtscts=%s)",
        port, pipe.baudrate, pipe.rts, pipe.dtr, pipe.rtscts,
    )
    return pipe


def _detect_radio_class(radio_class, pipe):
    """Return the radio class to actually use, honoring live submodel detection.

    Some driver families talk to the connected radio to pin down the exact
    submodel; CHIRP's own download dialog calls this and uses the detected
    class instead of the user's pick. Mirrors that:
      - returns a (possibly different) class -> use it;
      - raises NotImplementedError -> no detection available/needed (the common
        case), keep the user's pick;
      - raises errors.RadioError -> detection ran and explicitly failed; let it
        propagate so the caller reports the failure and closes the port (don't
        silently fall back to the user's pick on a real detection failure).
    """
    try:
        detected = radio_class.detect_from_serial(pipe)
    except NotImplementedError:
        return radio_class
    if detected is not None and detected is not radio_class:
        LOG.info(
            "Detected %s.%s from serial (user picked %s.%s)",
            detected.__module__, detected.__name__,
            radio_class.__module__, radio_class.__name__,
        )
        return detected
    return radio_class


def download_from_radio(
    port: str,
    driver_id: str,
    progress_callback: Callable[[int, int, str], None],
) -> tuple[bool, str]:
    """Download (read) memory from a physical radio over serial.

    ``driver_id`` is a CHIRP driver id from list_radio_models. progress_callback
    (current, total, message) is called during the transfer. Runs synchronously —
    call from a background thread. Returns (success, message).
    """
    _ensure_chirp()
    from chirp import chirp_common, directory

    try:
        radio_class = directory.get_radio(driver_id)
    except Exception:
        return False, f"Unknown radio: {driver_id}"

    label = f"{radio_class.VENDOR} {radio_class.MODEL}"

    # The model picker lists every CHIRP driver, including "live" radios that
    # talk over an always-on connection instead of doing a one-shot memory
    # clone (they have no sync_in). Guard before opening the port so the user
    # gets a clear message instead of a cryptic mid-clone AttributeError.
    # (Live-radio support itself is out of scope — see the serial plan.)
    if not issubclass(radio_class, chirp_common.CloneModeRadio):
        return False, (
            f"{label} uses a live connection, not a memory clone, so VRP "
            f"can't download from it yet."
        )

    pipe = None
    try:
        progress_callback(0, 100, f"Connecting to {label} on {port}...")
        pipe = _open_radio_serial(
            port, radio_class, trace=LOG.isEnabledFor(logging.DEBUG)
        )
        # Honor a driver's live submodel detection before reading (a RadioError
        # here propagates to the handler below, which closes the pipe).
        radio_class = _detect_radio_class(radio_class, pipe)
        label = f"{radio_class.VENDOR} {radio_class.MODEL}"
        radio = radio_class(pipe)
        radio.status_fn = _make_status_fn(progress_callback)
        radio.sync_in()
        pipe.close()

        with _state_lock:
            _state.radio = radio
            _state.serial_port = port
            _state.image_path = None   # downloaded, not yet saved to disk
            _state.is_modified = True
            _state._mem_cache = {}
        _install_undo(radio)  # a downloaded image starts with empty history

        return True, f"Downloaded {label} from {port}"

    except Exception as e:
        LOG.exception("Download from radio failed")
        if pipe is not None:
            try:
                pipe.close()
            except Exception:
                pass
        return False, f"Download failed: {e}"


def upload_to_radio(
    port: str,
    progress_callback: Callable[[int, int, str], None],
) -> tuple[bool, str]:
    """Upload (write) the loaded image to a physical radio over serial.

    Runs synchronously — call from a background thread. Returns (success, message).
    """
    with _state_lock:
        if not _state.loaded:
            return False, "No radio loaded"
        radio = _state.radio

    pipe = None
    try:
        progress_callback(0, 100, f"Connecting to radio on {port}...")
        pipe = _open_radio_serial(
            port, radio, trace=LOG.isEnabledFor(logging.DEBUG)
        )
        radio.set_pipe(pipe)
        radio.status_fn = _make_status_fn(progress_callback)
        radio.sync_out()
        pipe.close()
        return True, f"Uploaded to radio on {port}"

    except Exception as e:
        LOG.exception("Upload to radio failed")
        if pipe is not None:
            try:
                pipe.close()
            except Exception:
                pass
        return False, f"Upload failed: {e}"
