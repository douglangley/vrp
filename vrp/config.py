"""Persistent app preferences + recent-files list (JSON in the user config dir).

A tiny, defensive single-file store: a missing or corrupt config never blocks
startup (it falls back to defaults), and writes are atomic (temp file + replace)
so a crash mid-write can't corrupt it. Pure and unit-testable — construct
``Config(path=...)`` directly in tests; the app uses the ``get_config()``
singleton at the platform user-config location.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import tempfile

LOG = logging.getLogger(__name__)

# Upper bound on how many recent files we *store*. The user picks how many to
# *show* (0–9) via the recent_files_count preference; storing 9 lets a setting
# of 9 actually display 9.
MAX_RECENT = 9

# App config directory name. "OpenMemoryWriter" was the project's pre-rename
# name; any config found there is migrated forward to the current "VRP" dir.
_APP_DIRNAME = "VRP"
_LEGACY_DIRNAME = "OpenMemoryWriter"

_DEFAULTS = {
    "version": 1,
    "channels_per_page": 100,
    "speak_status_messages": False,  # screen reader already reads the live region
    "recent_files": [],
    "recent_files_count": 9,  # how many recent files to show in the menu (0 hides it)
    "last_serial_port": None,  # device string (e.g. "COM4") last used for a clone
}


def _config_base() -> str:
    # Plain per-user config location — deliberately NOT wx.StandardPaths, which
    # spins up an implicit wx.App (~6s) when no App exists (e.g. headless tests).
    if os.name == "nt":
        return os.environ.get("APPDATA") or os.path.expanduser("~")
    return os.environ.get("XDG_CONFIG_HOME") or os.path.join(
        os.path.expanduser("~"), ".config"
    )


def _default_path() -> str:
    base = _config_base()
    path = os.path.join(base, _APP_DIRNAME, "config.json")
    # One-time migration from the pre-rename config dir, so existing testers/
    # users keep their preferences and recent files when the dir name changed.
    legacy = os.path.join(base, _LEGACY_DIRNAME, "config.json")
    if not os.path.exists(path) and os.path.exists(legacy):
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            shutil.copy2(legacy, path)
            LOG.info("Migrated config %s -> %s", legacy, path)
        except Exception as e:  # noqa: BLE001 — best effort; fall back to defaults
            LOG.warning("Config migration failed (%s); using defaults", e)
    return path


class Config:
    def __init__(self, path: str | None = None) -> None:
        self._path = path or _default_path()
        self._data = dict(_DEFAULTS)
        self.load()

    def load(self) -> None:
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                self._data.update(data)
        except FileNotFoundError:
            pass
        except Exception as e:  # noqa: BLE001 - corrupt file: keep defaults
            LOG.warning("config load failed (%s); using defaults", e)

    def save(self) -> None:
        try:
            directory = os.path.dirname(self._path)
            os.makedirs(directory, exist_ok=True)
            fd, tmp = tempfile.mkstemp(dir=directory, suffix=".tmp")
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(self._data, f, indent=2)
            os.replace(tmp, self._path)
        except Exception as e:  # noqa: BLE001
            LOG.warning("config save failed: %s", e)

    def get(self, key: str, default=None):
        return self._data.get(key, _DEFAULTS.get(key, default))

    def set(self, key: str, value) -> None:
        self._data[key] = value
        self.save()

    # -- serial port -------------------------------------------------------

    def get_last_serial_port(self):
        """The device last used for a download/upload, or None."""
        return self._data.get("last_serial_port")

    def set_last_serial_port(self, port: str) -> None:
        self._data["last_serial_port"] = port
        self.save()

    # -- recent files ------------------------------------------------------

    def recent(self) -> list:
        return list(self._data.get("recent_files", []))

    @staticmethod
    def _same(a: str, b: str) -> bool:
        return os.path.normcase(os.path.abspath(a)) == os.path.normcase(os.path.abspath(b))

    def add_recent(self, path: str) -> None:
        path = os.path.abspath(path)
        items = [p for p in self.recent() if not self._same(p, path)]
        items.insert(0, path)
        self._data["recent_files"] = items[:MAX_RECENT]
        self.save()

    def remove_recent(self, path: str) -> None:
        self._data["recent_files"] = [
            p for p in self.recent() if not self._same(p, path)
        ]
        self.save()

    def clear_recent(self) -> None:
        self._data["recent_files"] = []
        self.save()

    # -- recent-files count preference ------------------------------------

    def recent_count(self) -> int:
        """How many recent files to show in the menu, clamped to 0..MAX_RECENT.
        0 means hide the Recent submenu entirely."""
        try:
            n = int(self._data.get("recent_files_count", _DEFAULTS["recent_files_count"]))
        except (TypeError, ValueError):
            n = _DEFAULTS["recent_files_count"]
        return max(0, min(MAX_RECENT, n))

    def set_recent_count(self, n: int) -> None:
        self._data["recent_files_count"] = max(0, min(MAX_RECENT, int(n)))
        self.save()

    def recent_to_show(self) -> list:
        """The recent files to display, newest first, capped at recent_count()."""
        return self.recent()[: self.recent_count()]


_instance: Config | None = None


def get_config() -> Config:
    global _instance
    if _instance is None:
        _instance = Config()
    return _instance
