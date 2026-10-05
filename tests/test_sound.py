"""Klang-Einstellungen im Construct-Raum (config.py → "sound")."""
import json

import pytest

from server import config


@pytest.fixture
def tmp_settings(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "SETTINGS_FILE", tmp_path / "settings.json")
    return tmp_path / "settings.json"


def test_ab_werk_an_und_leise(tmp_settings):
    s = config.load_settings()["sound"]
    assert s == {"effekte": True, "musik": True, "lautstaerke": 40}


def test_patch_schaltet_einzeln_und_begrenzt(tmp_settings):
    config.apply_patch({"sound": {"musik": False}})
    s = config.load_settings()["sound"]
    assert s["musik"] is False and s["effekte"] is True
    assert config.apply_patch({"sound": {"lautstaerke": 250}})["sound"]["lautstaerke"] == 100
    assert config.apply_patch({"sound": {"lautstaerke": -3}})["sound"]["lautstaerke"] == 0
    # Unsinn ändert nichts
    assert config.apply_patch({"sound": {"lautstaerke": "laut"}})["sound"]["lautstaerke"] == 0


def test_kaputte_datei_faellt_auf_vorgaben(tmp_settings):
    tmp_settings.write_text(json.dumps({"sound": {"effekte": 0, "lautstaerke": "x"}}))
    s = config.load_settings()["sound"]
    assert s["effekte"] is False
    assert s["lautstaerke"] == 40
