"""Tests for the persistent config store (vrp/config.py)."""

import json
import os

from vrp import config as cfg
from vrp.config import Config, MAX_RECENT


def _point_config_base(monkeypatch, tmp_path):
    # Cover both platforms' base-dir env vars so _config_base() resolves to
    # tmp_path regardless of os.name.
    monkeypatch.setenv("APPDATA", str(tmp_path))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))


def test_defaults_on_missing_file(tmp_path):
    c = Config(path=str(tmp_path / "c.json"))
    assert c.get("channels_per_page") == 100
    assert c.get("speak_status_messages") is False
    assert c.recent() == []


def test_set_persists_across_instances(tmp_path):
    path = str(tmp_path / "c.json")
    Config(path=path).set("channels_per_page", 50)
    assert Config(path=path).get("channels_per_page") == 50


def test_corrupt_file_falls_back_to_defaults(tmp_path):
    p = tmp_path / "c.json"
    p.write_text("{ this is not valid json", encoding="utf-8")
    c = Config(path=str(p))
    assert c.get("channels_per_page") == 100  # didn't raise; used defaults


def test_add_recent_dedup_cap_and_order(tmp_path):
    c = Config(path=str(tmp_path / "c.json"))
    for i in range(10):
        c.add_recent(f"/tmp/f{i}.img")
    recent = c.recent()
    assert len(recent) == MAX_RECENT  # capped
    assert os.path.basename(recent[0]) == "f9.img"  # most recent first
    # re-adding an existing entry moves it to the front without duplicating
    c.add_recent("/tmp/f5.img")
    assert os.path.basename(c.recent()[0]) == "f5.img"
    assert sum(1 for p in c.recent() if p.endswith("f5.img")) == 1


def test_clear_recent(tmp_path):
    c = Config(path=str(tmp_path / "c.json"))
    c.add_recent("/tmp/a.img")
    c.clear_recent()
    assert c.recent() == []


def test_last_serial_port_round_trips(tmp_path):
    path = str(tmp_path / "c.json")
    assert Config(path=path).get_last_serial_port() is None  # default
    Config(path=path).set_last_serial_port("COM7")
    assert Config(path=path).get_last_serial_port() == "COM7"  # persisted


def test_default_path_uses_vrp_dir(monkeypatch, tmp_path):
    _point_config_base(monkeypatch, tmp_path)
    p = cfg._default_path()
    assert os.path.basename(os.path.dirname(p)) == "VRP"  # not OpenMemoryWriter
    assert os.path.basename(p) == "config.json"


def test_migrates_legacy_openmemorywriter_config(monkeypatch, tmp_path):
    _point_config_base(monkeypatch, tmp_path)
    legacy = tmp_path / "OpenMemoryWriter"
    legacy.mkdir()
    (legacy / "config.json").write_text(
        json.dumps({"channels_per_page": 250}), encoding="utf-8"
    )
    p = cfg._default_path()  # triggers migration
    assert os.path.basename(os.path.dirname(p)) == "VRP"
    assert os.path.exists(p)
    assert json.loads(open(p, encoding="utf-8").read())["channels_per_page"] == 250


def test_no_migration_when_new_config_already_exists(monkeypatch, tmp_path):
    _point_config_base(monkeypatch, tmp_path)
    new = tmp_path / "VRP"
    new.mkdir()
    (new / "config.json").write_text(
        json.dumps({"channels_per_page": 50}), encoding="utf-8"
    )
    legacy = tmp_path / "OpenMemoryWriter"
    legacy.mkdir()
    (legacy / "config.json").write_text(
        json.dumps({"channels_per_page": 250}), encoding="utf-8"
    )
    p = cfg._default_path()
    # Existing VRP config must NOT be overwritten by the legacy one.
    assert json.loads(open(p, encoding="utf-8").read())["channels_per_page"] == 50
