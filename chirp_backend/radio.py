"""
Radio backend — wraps the CHIRP library for the wx UI.

Manages a single "active radio" (loaded image + optional live serial
connection). All radio state lives here, framework-agnostic, so the UI layer
holds no CHIRP objects of its own.

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
import uuid
from dataclasses import dataclass, field
from typing import Callable, Optional

from chirp_backend.undo import UndoManager

LOG = logging.getLogger(__name__)

# Lazily import chirp so we can give a friendly error if it's not installed
_chirp_loaded = False


def _ensure_driver_modules() -> int:
    """Make CHIRP's driver modules importable in a frozen build. Returns the
    number of driver modules known.

    Why this exists: ``chirp/drivers/__init__.py`` builds ``__all__`` by
    globbing ``*.py`` **off the filesystem**. Frozen, the drivers live inside
    PyInstaller's PYZ archive and there are no .py files on disk, so ``__all__``
    comes out **empty** — and ``directory.import_drivers()``'s frozen branch
    iterates exactly that list, so it imports nothing, the registry stays empty,
    and every image fails with "Unsupported model". ``--collect-submodules``
    bundles the modules; nothing ever imports them. Upstream CHIRP rewrites that
    file to a static list when packaging; we can't, because ./chirp is used
    unmodified (CLAUDE.md).

    So: when ``__all__`` is empty, rebuild it via ``pkgutil.iter_modules``,
    which PyInstaller's frozen importer implements (verified: 191 modules ->
    552 registered drivers), and import the modules here rather than relying on
    ``import_drivers()``'s branch — that branch is ``win32``-only, and a frozen
    macOS build would fall through to the same broken glob.

    On a source run ``__all__`` is already populated by the glob, so this is a
    no-op and CHIRP behaves exactly as upstream intends.
    """
    import chirp.drivers

    names = list(getattr(chirp.drivers, "__all__", []) or [])
    if names:
        return len(names)  # source run: the glob worked, leave CHIRP alone

    import pkgutil

    names = sorted(
        m.name
        for m in pkgutil.iter_modules(chirp.drivers.__path__)
        if not m.name.startswith("__")
    )
    if not names:
        LOG.error(
            "No CHIRP driver modules found in the frozen build — no radio will "
            "be supported. Check --collect-submodules=chirp.drivers in build.py."
        )
        return 0
    chirp.drivers.__all__ = names
    # Import them ourselves: import_drivers()'s frozen branch only fires on
    # win32. One bad driver must not abort the rest (upstream tolerates this
    # too), so failures are logged and skipped.
    failed = 0
    for name in names:
        try:
            __import__("chirp.drivers.%s" % name)
        except Exception as exc:  # noqa: BLE001
            failed += 1
            LOG.warning("Failed to import driver %s: %s", name, exc)
    LOG.info(
        "Frozen build: repopulated chirp.drivers.__all__ with %d modules (%d "
        "failed to import)", len(names), failed,
    )
    return len(names)


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

        # Frozen builds have no driver .py files on disk for CHIRP to glob —
        # see _ensure_driver_modules. Must run BEFORE import_drivers().
        _ensure_driver_modules()
        directory.import_drivers()
        _chirp_loaded = True
        LOG.info(
            "CHIRP drivers loaded successfully (%d registered)",
            len(getattr(directory, "DRV_TO_RADIO", {})),
        )
    except ImportError as e:
        raise RuntimeError(
            "CHIRP library not found. Install it with: pip install -e ./chirp\n"
            f"Original error: {e}"
        )


@dataclass(frozen=True)
class RadioImageSet:
    """A complete image plus the memory views CHIRP exposes for it.

    ``parent`` owns the mmap, file metadata, settings and serial clone.  The
    entries in ``devices`` are the objects whose memories can be shown in the
    grid.  Ordinary radios have a one-item tuple containing the parent itself.
    """

    parent: object
    devices: tuple[object, ...]
    path: Optional[str] = None

    @property
    def labels(self) -> tuple[str, ...]:
        return _subdevice_labels(self.devices)


@dataclass
class RadioState:
    """Holds the physical radio and the active memory view."""
    radio: object = None            # selected grid/memory radio
    parent_radio: object = None     # complete image/settings/clone owner
    subdevices: tuple[object, ...] = field(default_factory=tuple)
    subdevice_index: int = 0
    image_path: Optional[str] = None
    # A new identity for every open/download operation. Clipboard cut may erase
    # its source only while this exact document is still active.
    document_id: Optional[str] = None
    is_modified: bool = False
    # Cache of memory objects keyed by channel number, populated on load
    _mem_cache: dict = field(default_factory=dict)

    @property
    def loaded(self) -> bool:
        return self.radio is not None

    @property
    def physical_radio(self):
        """The object that owns save/settings/upload for the complete image."""
        return self.parent_radio if self.parent_radio is not None else self.radio

    @property
    def has_multiple_subdevices(self) -> bool:
        return len(self.subdevices) > 1

    @property
    def subdevice_labels(self) -> tuple[str, ...]:
        return _subdevice_labels(self.subdevices)

    @property
    def context_id(self) -> Optional[str]:
        """Identity of this exact document *and* selected memory section."""
        if self.document_id is None:
            return None
        return f"{self.document_id}:{self.subdevice_index}"

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
    _remove_undo_wrapper()
    with _state_lock:
        _state.radio = None
        _state.parent_radio = None
        _state.subdevices = ()
        _state.subdevice_index = 0
        _state.image_path = None
        _state.document_id = None
        _state.is_modified = False
        _state._mem_cache = {}


def _subdevice_labels(devices) -> tuple[str, ...]:
    """Build concise, stable labels without exposing generated class names."""
    if not devices:
        return ()
    titles = []
    for index, device in enumerate(devices):
        variant = str(getattr(device, "VARIANT", "") or "").strip()
        titles.append(variant or f"Memory section {index + 1}")
    counts = {title: titles.count(title) for title in set(titles)}
    labels = []
    for index, (device, title) in enumerate(zip(devices, titles)):
        if counts[title] > 1:
            title = f"{title} (section {index + 1})"
        try:
            low, high = device.get_features().memory_bounds
            labels.append(f"{title} — channels {low} to {high}")
        except Exception:  # noqa: BLE001 - a label must never block opening
            labels.append(title)
    return tuple(labels)


def _build_image_set(parent, path: Optional[str] = None) -> RadioImageSet:
    """Expand a parsed/downloaded parent using CHIRP's sub-device contract."""
    features = parent.get_features()
    if getattr(features, "has_sub_devices", False):
        devices = tuple(parent.get_sub_devices())
        if not devices:
            LOG.warning(
                "%s %s reports sub-devices but returned none; using parent",
                getattr(parent, "VENDOR", ""), getattr(parent, "MODEL", ""),
            )
            devices = (parent,)
        else:
            # This is the same post-get_sub_devices hook CHIRP's editor uses.
            # It makes external per-memory metadata survive a later parent save.
            from chirp import chirp_common

            if isinstance(parent, chirp_common.ExternalMemoryProperties):
                parent.link_device_metadata(devices)
    else:
        devices = (parent,)
    return RadioImageSet(parent=parent, devices=devices, path=path)


def load_image_set(path: str) -> tuple[Optional[RadioImageSet], str]:
    """
    Parse an image and discover its memory sections without activating it.

    The two-step API lets the UI ask which section to open while leaving the
    current document untouched if the user cancels that chooser.
    """
    _ensure_chirp()
    from chirp import directory

    if not os.path.exists(path):
        return None, f"File not found: {path}"

    try:
        # get_radio_by_image inspects the image header/metadata, picks the
        # owning driver, and returns a radio instance already loaded from the
        # file (it constructs the driver with the image path).
        parent = directory.get_radio_by_image(path)
        if parent is None:
            return None, "Unrecognized image format (no matching CHIRP driver)"
        image_set = _build_image_set(parent, path)
        return image_set, (
            f"Loaded {parent.VENDOR} {parent.MODEL} "
            f"from {os.path.basename(path)}"
        )

    except Exception as e:
        LOG.exception("Failed to load image %s", path)
        return None, f"Failed to load image: {e}"


def activate_image_set(
    image_set: RadioImageSet,
    subdevice_index: int = 0,
    *,
    modified: bool = False,
) -> tuple[bool, str]:
    """Make one memory view active while retaining the complete parent."""
    if not 0 <= subdevice_index < len(image_set.devices):
        return False, f"Memory section {subdevice_index + 1} is not available"

    _remove_undo_wrapper()
    radio = image_set.devices[subdevice_index]
    with _state_lock:
        _state.radio = radio
        _state.parent_radio = image_set.parent
        _state.subdevices = image_set.devices
        _state.subdevice_index = subdevice_index
        _state.image_path = image_set.path
        _state.document_id = uuid.uuid4().hex
        _state.is_modified = modified
        _state._mem_cache = {}
    _install_undo(radio)

    label = f"{image_set.parent.VENDOR} {image_set.parent.MODEL}"
    if len(image_set.devices) > 1:
        label += f", {image_set.labels[subdevice_index]}"
    LOG.info("Activated image: %s (%s)", image_set.path or "download", label)
    source = os.path.basename(image_set.path) if image_set.path else "radio"
    return True, f"Loaded {label} from {source}"


def load_image(path: str, subdevice_index: int = 0) -> tuple[bool, str]:
    """Load an image and activate one of its CHIRP memory sections."""
    image_set, message = load_image_set(path)
    if image_set is None:
        return False, message
    return activate_image_set(image_set, subdevice_index)


def select_subdevice(subdevice_index: int) -> tuple[bool, str]:
    """Switch the active memory section without replacing the parent image."""
    with _state_lock:
        if not _state.loaded:
            return False, "No radio loaded"
        if not 0 <= subdevice_index < len(_state.subdevices):
            return False, f"Memory section {subdevice_index + 1} is not available"
        if subdevice_index == _state.subdevice_index:
            return True, f"Already showing {_state.subdevice_labels[subdevice_index]}"
        next_radio = _state.subdevices[subdevice_index]

    _remove_undo_wrapper()
    with _state_lock:
        _state.radio = next_radio
        _state.subdevice_index = subdevice_index
        _state._mem_cache = {}
        label = _state.subdevice_labels[subdevice_index]
    _install_undo(next_radio)
    return True, f"Showing {label}. Undo history was reset"


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
            _state.physical_radio.save_mmap(save_path)
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
    Write a memory channel back to the radio image, updating the read cache.
    Returns (success, message).

    Write-path note (see also ``_install_undo``): every channel write in the app
    funnels through **one physical choke point** — the loaded radio's
    ``set_memory``/``erase_memory``, which ``_install_undo`` wraps to record undo
    and mark the image ``is_modified``. There are two *entry points* to it:

      - ``memory_ops`` (the app path): calls ``radio.set_memory`` directly and
        keeps the cache fresh by calling ``invalidate_cache`` after each op.
      - this module-level pair (used by tests and available programmatically):
        the same write, but it updates ``_mem_cache`` in place instead of
        invalidating — a convenience for a single coherent read-after-write.

    Both hit the same wrapped methods, so undo recording and ``is_modified`` are
    identical regardless of entry point.
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
    Erase (blank out) a memory channel, dropping its cache entry.
    Returns (success, message). See :func:`set_memory` for the write-path note
    (one wrapped choke point; this is the cache-updating entry point).
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

# One UndoManager per selected memory section. Reset (and the selected device
# re-wrapped) on every load/download/section switch; cleared on close.
_undo: Optional[UndoManager] = None
_undo_wrapped_radio: object = None
_undo_original_methods: Optional[tuple[object, object]] = None


def get_undo_manager() -> Optional[UndoManager]:
    """The active UndoManager, or None when no radio is loaded."""
    return _undo


def _remove_undo_wrapper() -> None:
    """Restore methods on the previously selected device before leaving it."""
    global _undo, _undo_wrapped_radio, _undo_original_methods
    radio = _undo_wrapped_radio
    originals = _undo_original_methods
    if radio is not None and originals is not None:
        try:
            radio.set_memory, radio.erase_memory = originals
        except Exception:  # noqa: BLE001 - cleanup is best effort
            LOG.exception("Could not remove undo recorder from radio")
    _undo = None
    _undo_wrapped_radio = None
    _undo_original_methods = None


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
    global _undo, _undo_wrapped_radio, _undo_original_methods
    _remove_undo_wrapper()
    try:
        orig_get = radio.get_memory
        orig_set = radio.set_memory
        orig_erase = radio.erase_memory
        _undo_wrapped_radio = radio
        _undo_original_methods = (orig_set, orig_erase)

        # This wrapper is the single choke point every channel write funnels
        # through (memory_ops._set_mem/_erase_mem call the radio methods directly,
        # and so do this module's own set_memory/erase_memory), so it is also
        # where we mark the image dirty. Without this, ordinary edits/deletes/
        # moves left is_modified False and Radio Info wrongly said "Unsaved
        # changes: No" (and any unsaved-changes prompt would be built on a lie).
        # It never fires during load/download: the wrapper is installed *after*
        # the image is read, and reading an image doesn't call set_memory.
        def recording_set(mem):
            if _undo is not None:
                _undo.record(getattr(mem, "extd_number", "") or mem.number)
            result = orig_set(mem)
            _state.is_modified = True
            return result

        def recording_erase(number):
            if _undo is not None:
                _undo.record(number)
            result = orig_erase(number)
            _state.is_modified = True
            return result

        radio.set_memory = recording_set
        radio.erase_memory = recording_erase

        # Undo/redo also mutate the image relative to the file on disk, so they
        # too mark it dirty (conservatively — undoing back to the exact saved
        # state still flags modified, which at worst prompts a redundant save).
        def restore_set(mem):
            orig_set(mem)
            _state.is_modified = True
            invalidate_cache([mem.number])

        def restore_erase(number):
            orig_erase(number)
            _state.is_modified = True
            invalidate_cache([number])

        _undo = UndoManager(
            get_memory=lambda n: orig_get(n),
            set_memory=restore_set,
            erase_memory=restore_erase,
        )
    except Exception:  # noqa: BLE001 — undo is best-effort; never block loading
        LOG.exception("Could not install undo recorder; undo disabled for this radio")
        _remove_undo_wrapper()


def open_image_as_source(path: str, subdevice_index: int = 0) -> tuple:
    """Load an image into a standalone radio instance for IMPORT, leaving the
    active radio untouched. Returns (radio_or_None, message)."""
    image_set, message = load_image_set(path)
    if image_set is None:
        return None, message
    if not 0 <= subdevice_index < len(image_set.devices):
        return None, f"Memory section {subdevice_index + 1} is not available"
    return image_set.devices[subdevice_index], message


def export_to_csv(path: str, numbers=None) -> tuple:
    """Write channels to a CSV file (a separate file — does NOT change the
    working image's saved state). With ``numbers`` (an iterable of channel
    numbers) only those channels are exported, so a user can send just the
    relevant portion of their memories; with ``numbers=None`` the whole image's
    non-empty channels are exported. Empty slots in the requested set are
    skipped. Returns (ok, message, count)."""
    with _state_lock:
        if not _state.loaded:
            return False, "No radio loaded", 0
        radio = _state.radio

    from chirp import chirp_common, import_logic
    from chirp.drivers import generic_csv

    try:
        features = radio.get_features()
        lo, hi = features.memory_bounds
        if numbers is None:
            wanted = range(lo, hi + 1)
        else:
            # De-dupe, sort, and keep only in-range slots so an out-of-bounds or
            # repeated selection can't error or double-export a channel.
            wanted = sorted({n for n in numbers if lo <= n <= hi})
        rows = []
        for n in wanted:
            mem = radio.get_memory(n)
            if not getattr(mem, "empty", True):
                rows.append(mem)
        if not rows:
            return False, "No channels to export.", 0

        # CSVRadio(None) creates a synthetic blank channel zero. Size the
        # in-memory CSV to the real maximum and explicitly erase zero so radios
        # whose first channel is 1 do not gain a phantom row on export.
        csv = generic_csv.CSVRadio(None, max_memory=max(mem.number for mem in rows))
        csv.erase_memory(0)
        for mem in rows:
            csv.set_memory(
                import_logic.import_mem(
                    csv, features, mem, mem_cls=chirp_common.Memory
                )
            )
        csv.save_mmap(path)
        return True, f"Exported {len(rows)} channel(s) to {os.path.basename(path)}.", len(rows)
    except Exception as e:  # noqa: BLE001
        LOG.exception("export_to_csv failed: %s", path)
        return False, f"Export failed: {e}", 0


def has_settings() -> bool:
    """True if the loaded radio exposes editable settings."""
    with _state_lock:
        if not _state.loaded:
            return False
        return bool(
            getattr(_state.physical_radio.get_features(), "has_settings", False)
        )


def get_radio_settings():
    """Return the loaded radio's settings tree (list of RadioSettingGroup), or
    None if unavailable. The objects are live — mutate via set_value then call
    apply_radio_settings to write them back."""
    with _state_lock:
        if not _state.loaded:
            return None
        try:
            return _state.physical_radio.get_settings()
        except Exception as e:  # noqa: BLE001
            LOG.exception("get_settings failed")
            return None


def apply_radio_settings(settings) -> tuple[bool, str]:
    """Write a (possibly edited) settings tree back to the radio image."""
    with _state_lock:
        if not _state.loaded:
            return False, "No radio loaded"
        try:
            _state.physical_radio.set_settings(settings)
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
        radio = _state.physical_radio
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

        image_set = _build_image_set(radio)
        ok, activate_message = activate_image_set(image_set, modified=True)
        if not ok:
            return False, activate_message

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
        radio = _state.physical_radio

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
