"""Bilder erzeugen (images.py) und Schattenbetrieb der Modellwahl (auto_modell.py)."""
import io
import json

import pytest

from server import auto_modell, config, images, llm


@pytest.fixture
def tmp_daten(tmp_path, monkeypatch):
    monkeypatch.setattr(llm, "CONFIG_FILE", tmp_path / ".llm-config.json")
    monkeypatch.setattr(config, "SETTINGS_FILE", tmp_path / "settings.json")
    monkeypatch.setattr(images, "UPLOAD_DIR", tmp_path / "uploads")
    monkeypatch.delenv("FAL_KEY", raising=False)
    return tmp_path


def test_ohne_key_kein_hinweis_und_klarer_fehler(tmp_daten):
    assert images.context_block() == ""
    with pytest.raises(images.BildFehler, match="Kein fal.ai-Key"):
        images.erzeuge("a cat")


def test_key_speichern_und_entfernen(tmp_daten):
    images.save_key("fal-123")
    assert images.status()["configured"]
    assert "bild.py" in images.context_block()
    images.save_key("")
    assert not images.status()["configured"]


def test_erzeugen_legt_bild_in_uploads_ab(tmp_daten, monkeypatch):
    images.save_key("fal-123")
    gesendet = {}

    def fake_post(path, body, key, timeout):
        gesendet.update(path=path, body=body, key=key)
        return {"images": [{"url": "https://cdn.example/x.png"}]}

    class Antwort(io.BytesIO):
        headers = type("H", (), {"get_content_type": staticmethod(lambda: "image/png")})()
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False

    monkeypatch.setattr(images, "_post", fake_post)
    monkeypatch.setattr(images.urllib.request, "urlopen", lambda url, timeout=0: Antwort(b"PNG"))
    pfad = images.erzeuge("a croissant", "1:1")
    assert pfad.parent == tmp_daten / "uploads" and pfad.suffix == ".png"
    assert pfad.read_bytes() == b"PNG"
    assert gesendet["path"] == "openai/gpt-image-2"
    assert gesendet["body"]["image_size"] == "square_hd"
    assert gesendet["key"] == "fal-123"


def test_falsches_format_und_modell(tmp_daten):
    images.save_key("fal-123")
    with pytest.raises(images.BildFehler, match="Format"):
        images.erzeuge("x", "4:3")
    with pytest.raises(images.BildFehler, match="Modell"):
        images.erzeuge("x", "16:9", "gibts/nicht")


def test_einstellungen_ueberleben_ein_speichern(tmp_daten):
    # apply_patch schreibt settings.json neu: unbekannte Felder gingen verloren.
    (tmp_daten / "settings.json").write_text(json.dumps({"auto": {"schatten": True}}))
    config.apply_patch({"images": {"model": "fal-ai/nano-banana-pro"}})
    s = config.load_settings()
    assert s["auto"]["schatten"] is True
    assert s["images"]["model"] == "fal-ai/nano-banana-pro"
    config.apply_patch({"images": {"model": "irgendwas"}})
    assert config.load_settings()["images"]["model"] == "fal-ai/nano-banana-pro"


def test_schattenbetrieb_ist_ab_werk_aus(tmp_daten):
    assert config.load_settings()["auto"]["schatten"] is False
    assert not auto_modell.aktiv()


@pytest.mark.parametrize("raw, erwartet", [
    (json.dumps({"result": '{"modell": "Sonnet", "sicherheit": 0.8, "grund": "normal"}'}), "sonnet"),
    (json.dumps({"result": 'Klar:\n```json\n{"modell":"opus","sicherheit":2}\n```'}), "opus"),
])
def test_klassifizierer_antwort_wird_gelesen(raw, erwartet):
    d = auto_modell._auswerten(raw)
    assert d["modell"] == erwartet
    assert d["sicherheit"] is None or 0 <= d["sicherheit"] <= 1


def test_klassifizierer_unsinn_wird_fehler():
    assert "fehler" in auto_modell._auswerten(json.dumps({"result": "weiß nicht"}))
    assert "fehler" in auto_modell._auswerten(json.dumps({"result": '{"modell": "gpt"}'}))
