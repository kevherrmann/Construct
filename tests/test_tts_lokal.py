"""Lokale Stimme: Einstellungen, Aufteilung in Stücke, Routen (ohne echtes Modell)."""
import json

import pytest

from server import config
from server import tts as ttsmod
from server import tts_lokal
from server.core import UPLOAD_DIR

WAV = b"RIFF\x24\x00\x00\x00WAVEfmt " + b"\x00" * 28


@pytest.fixture
def einstellungen(tmp_path, monkeypatch):
    """Eigene settings.json; gibt eine Funktion zum Setzen von tts-Werten zurück."""
    monkeypatch.setattr(config, "SETTINGS_FILE", tmp_path / "settings.json")
    return lambda **tts: config.apply_patch({"lang": "de", "tts": tts})


def test_lokal_ist_standardmaessig_aus_und_nimmt_nur_eigene_uploads():
    cur = json.loads(json.dumps(config.DEFAULT_SETTINGS["tts"]))
    assert cur["engine"] == "gemini"
    config._clean_tts({"engine": "irgendwas", "probe": {"de": "/etc/passwd", "fr": "/uploads/x.wav"}}, cur)
    assert cur["engine"] == "gemini"
    assert cur["probe"] == {"de": "", "en": ""}
    config._clean_tts({"engine": "lokal", "probe": {"de": "/uploads/abc.wav"}}, cur)
    assert cur["engine"] == "lokal"
    assert cur["probe"]["de"] == "/uploads/abc.wav"


def test_teile_erst_kurz_dann_bis_zur_grenze():
    satz = "Das ist ein ganz normaler Satz mit ein paar Wörtern darin. "
    teile = ttsmod.teile("Hallo Kevin! " + satz * 20)
    assert teile[0].startswith("Hallo Kevin!")
    assert len(teile[0]) <= ttsmod.TEIL_ERSTER
    assert all(len(t) <= ttsmod.TEIL_MAX for t in teile)
    # nichts verloren, nichts doppelt
    assert " ".join(teile).count("normaler Satz") == 20


def test_teile_wachsen_nur_so_schnell_wie_die_stimme_rechnet():
    # Sonst ist das nächste Stück nicht fertig, wenn das vorige endet → Pause.
    satz = "Ein kurzer Satz. Noch einer, mit Komma. Und ein dritter, etwas längerer Satz hier. "
    teile = ttsmod.teile("Hallo! " + satz * 15)
    assert len(teile) > 4
    for vor, nach in zip(teile, teile[1:]):
        assert len(nach) <= max(ttsmod.TEIL_MIN, ttsmod.WACHSTUM * len(vor))
    assert len(teile[-2]) > 2 * len(teile[0])   # wächst aber tatsächlich


def test_teile_ueberschriften_bekommen_eine_pause_und_code_faellt_weg():
    teile = ttsmod.teile("# Plan\n- erster Punkt\n- zweiter Punkt\n```py\nprint(1)\n```")
    text = " ".join(teile)
    assert "Plan. erster Punkt. zweiter Punkt." in text
    assert "print" not in text


def test_teile_zerlegt_riesensaetze_und_laesst_keine_winzigen_reste():
    lang = "Das geht immer weiter, " * 40 + "Ende."
    teile = ttsmod.teile(lang)
    assert len(teile) > 1
    assert teile[-1] != "Ende."
    assert all(len(t) <= ttsmod.TEIL_MAX + 40 for t in teile)
    assert ttsmod.teile("") == [] and ttsmod.teile("   ") == []


def test_lokal_vorlesen_in_stuecken(client, einstellungen, monkeypatch):
    einstellungen(engine="lokal")
    gesprochen = []
    monkeypatch.setattr(tts_lokal, "synthesize",
                        lambda text, lang, probe="": gesprochen.append((text, lang, probe)) or WAV)
    text = "Erster Satz. " + "Noch ein Satz, der etwas länger ist als der erste. " * 10
    r = client.post("/api/tts", json={"text": text, "teil": 1})
    assert r.status_code == 200
    assert r.headers["content-type"] == "audio/wav"
    n = int(r.headers["x-tts-teile"])
    assert n == len(ttsmod.teile(text)) > 1
    assert gesprochen[-1] == (ttsmod.teile(text)[1], "de", "")
    # Teilnummer außerhalb → letztes Stück statt Fehler
    client.post("/api/tts", json={"text": text, "teil": 999})
    assert gesprochen[-1][0] == ttsmod.teile(text)[-1]


def test_lokal_nutzt_die_stimmprobe_als_pfad(client, einstellungen, monkeypatch):
    einstellungen(engine="lokal", probe={"de": "/uploads/abc.wav"})
    gesprochen = []
    monkeypatch.setattr(tts_lokal, "synthesize",
                        lambda text, lang, probe="": gesprochen.append(probe) or WAV)
    client.post("/api/tts", json={"text": "Hallo."})
    assert gesprochen == [str(UPLOAD_DIR / "abc.wav")]


def test_gemini_erzwingen_und_fehler_der_lokalen_stimme(client, einstellungen, monkeypatch):
    einstellungen(engine="lokal")
    monkeypatch.setattr(ttsmod, "synthesize", lambda *a, **k: WAV)

    def kaputt(*a, **k):
        raise tts_lokal.TTSLokalError("Zu wenig freier Grafikspeicher")
    monkeypatch.setattr(tts_lokal, "synthesize", kaputt)
    r = client.post("/api/tts", json={"text": "Hallo", "engine": "gemini"})
    assert r.status_code == 200 and r.headers["x-tts-teile"] == "1"
    r = client.post("/api/tts", json={"text": "Hallo"})
    assert r.status_code == 400
    assert "Grafikspeicher" in r.json()["error"]


def test_nicht_installiert_meldet_sich_verstaendlich(einstellungen, monkeypatch, tmp_path):
    monkeypatch.setattr(tts_lokal, "VENV", tmp_path / "venv")
    monkeypatch.setattr(tts_lokal, "MARKER", tmp_path / "venv" / ".construct-ok")
    monkeypatch.setattr(tts_lokal, "reachable", lambda: False)
    with pytest.raises(tts_lokal.TTSLokalError, match="nicht installiert"):
        tts_lokal.synthesize("Hallo", "de")


def test_start_prueft_den_freien_vram(monkeypatch, tmp_path):
    py = tmp_path / "venv" / "bin" / "python"
    py.parent.mkdir(parents=True)
    py.write_text("")
    monkeypatch.setattr(tts_lokal, "VENV", tmp_path / "venv")
    monkeypatch.setattr(tts_lokal, "MARKER", py)   # gilt als installiert
    monkeypatch.setattr(tts_lokal, "reachable", lambda: False)
    monkeypatch.setattr(tts_lokal, "gpu", lambda: {"name": "X", "total_gb": 8.0, "free_gb": 2.1})
    started = []
    monkeypatch.setattr(tts_lokal.subprocess, "Popen", lambda *a, **k: started.append(a))
    err = tts_lokal.start()
    # Wortlaut fest: die englische Oberfläche übersetzt ihn per Muster (serverText.ts).
    assert err == ("Zu wenig freier Grafikspeicher für die lokale Stimme: 2.1 GB frei, gebraucht "
                   "werden etwa 4 GB. Läuft gerade Bonsai, ein Spiel oder ein anderes KI-Modell?")
    assert not started


def test_installation_nur_wenn_eingeschaltet(client, einstellungen, monkeypatch):
    gestartet = []
    monkeypatch.setattr(tts_lokal, "install_start", lambda: gestartet.append(1) or {"ok": True})
    einstellungen(engine="gemini")
    assert client.post("/api/tts/lokal/install").status_code == 400
    einstellungen(engine="lokal")
    assert client.post("/api/tts/lokal/install").json() == {"ok": True}
    assert gestartet == [1]


def test_stimmprobe_hochladen_nur_audio(client, monkeypatch, tmp_path):
    from server import core
    monkeypatch.setattr(core, "UPLOAD_DIR", tmp_path)
    r = client.post("/api/tts/probe", files={"file": ("x.wav", b"<html>nope</html>")})
    assert r.status_code == 400
    r = client.post("/api/tts/probe", files={"file": ("aufnahme.bin", WAV)})
    url = r.json()["url"]
    assert url.startswith("/uploads/") and url.endswith(".wav")
    assert (tmp_path / url.rsplit("/", 1)[1]).read_bytes() == WAV
    r = client.post("/api/tts/probe", files={"file": ("a.mp3", b"ID3\x04" + b"\x00" * 50)})
    assert r.json()["url"].endswith(".mp3")


def test_stimmprobe_aus_gemini(client, einstellungen, monkeypatch, tmp_path):
    from server import core
    monkeypatch.setattr(core, "UPLOAD_DIR", tmp_path)
    einstellungen(voice={"de": "de-de-csagent-2"})
    aufrufe = []
    monkeypatch.setattr(ttsmod, "synthesize", lambda *a: aufrufe.append(a) or WAV)
    r = client.post("/api/tts/probe/gemini")
    assert r.status_code == 200
    assert aufrufe[0][0] == ttsmod.PROBE_TEXT["de"] and aufrufe[0][2] == "de-de-csagent-2"
    assert (tmp_path / r.json()["url"].rsplit("/", 1)[1]).read_bytes() == WAV
