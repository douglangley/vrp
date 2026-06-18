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
import threading
from dataclasses import dataclass, field
from typing import Callable, Generator, Optional

LOG = logging.getLogger(__name__)

# Lazily import chirp so we can give a friendly error if it's not installed
_chirp_loaded = False


def _ensure_chirp() -> None:
    global _chirp_loaded
    if _chirp_loaded:
        return
    try:
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
    with _state_lock:
        _state.radio = None
        _state.image_path = None
        _state.is_modified = False
        _state.serial_port = None
        _state._mem_cache = {}


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
            for p in sorted(ports, key=lambda p: p.device)
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
    from chirp import directory
    import serial

    try:
        radio_class = directory.get_radio(driver_id)
    except Exception:
        return False, f"Unknown radio: {driver_id}"

    label = f"{radio_class.VENDOR} {radio_class.MODEL}"
    pipe = None
    try:
        progress_callback(0, 100, f"Connecting to {label} on {port}...")
        pipe = serial.Serial(port, radio_class.BAUD_RATE, timeout=1)
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

    import serial

    pipe = None
    try:
        progress_callback(0, 100, f"Connecting to radio on {port}...")
        pipe = serial.Serial(port, radio.BAUD_RATE, timeout=1)
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
