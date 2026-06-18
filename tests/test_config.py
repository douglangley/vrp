"""Tests for the persistent config store (vrp/config.py)."""

import os

from vrp.config import Config, MAX_RECENT


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
