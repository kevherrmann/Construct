"""Grundlagen (server/core.py) und Einstellungen (config.py)."""
import json

from server import config
from server.core import BASE_DIR, LIMIT_HIT, extract_text, friendly_claude_error, sse


def test_base_dir_ist_der_projektordner():
    # core.py liegt in server/ — der Projektordner ist eine Ebene höher.
    assert (BASE_DIR / "app.py").exists()


def test_sse_format():
    assert sse({"type": "text", "text": "ä"}) == 'data: {"type": "text", "text": "ä"}\n\n'


def test_extract_text_aus_bloecken():
    text = extract_text([{"type": "text", "text": "a"}, {"type": "tool_use", "name": "Read"}, {"type": "text", "text": "b"}])
    assert "a" in text and "b" in text
    assert extract_text(None) == ""
    assert extract_text("x") == "x"


def test_limit_fehler_wird_erklaert_und_gemerkt():
    msg = friendly_claude_error("Claude AI usage limit reached|1790000000")
    assert msg.startswith("⛔")
    assert LIMIT_HIT["resets_at"] == 1790000000


def test_anmeldefehler_wird_erklaert():
    assert friendly_claude_error("Invalid API key · Please run /login").startswith("🔑")


def test_tts_einstellungen_je_sprache_und_alte_werte():
    cur = json.loads(json.dumps(config.DEFAULT_SETTINGS["tts"]))
    # frühe Fassung: eine einzelne Stimme als Text
    config._clean_tts({"voice": "en-us-podcaster-6", "style": "locker"}, cur)
    assert cur["voice"]["en"] == "en-us-podcaster-6"
    assert cur["style"]["de"] == "locker"
    config._clean_tts({"voice": {"de": "../boese<x>", "fr": "x"}, "model": "gibtsnicht"}, cur)
    assert cur["voice"]["de"] == "..boesex"
    assert "fr" not in cur["voice"]
    assert cur["model"] == config.DEFAULT_SETTINGS["tts"]["model"]


def test_plasma_ist_ein_schalter_fuer_alle_themes(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "SETTINGS_FILE", tmp_path / "settings.json")
    cur = config.apply_patch({"theme": "bernstein", "plasma": True})
    assert (cur["theme"], cur["plasma"]) == ("bernstein", True)
    assert config.apply_patch({"plasma": False})["plasma"] is False


def test_altes_plasma_theme_wird_umgestellt(tmp_path, monkeypatch):
    f = tmp_path / "settings.json"
    f.write_text('{"theme": "plasma"}')
    monkeypatch.setattr(config, "SETTINGS_FILE", f)
    cur = config.load_settings()
    assert (cur["theme"], cur["plasma"]) == ("space", True)


def test_hintergrund_plasma_feld(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "SETTINGS_FILE", tmp_path / "settings.json")
    assert config.apply_patch({"background": {"mode": "plasma"}})["background"]["mode"] == "plasma"


def test_schriftwahl(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "SETTINGS_FILE", tmp_path / "settings.json")
    assert config.apply_patch({"font": "jetbrains-mono"})["font"] == "jetbrains-mono"
    assert config.apply_patch({"font": "comic-sans"})["font"] == "jetbrains-mono"
    assert config.apply_patch({"font": ""})["font"] == ""
