"""Schreibende Anfragen fremder Webseiten werden abgewiesen (CSRF), alles andere nicht."""
import pytest

from server.core import fremde_herkunft

FREMD = "https://evil.example"


@pytest.mark.parametrize("methode,kopf,fremd", [
    ("POST", {"host": "127.0.0.1:8765", "origin": FREMD}, True),
    ("DELETE", {"host": "127.0.0.1:8765", "origin": FREMD, "sec-fetch-site": "cross-site"}, True),
    ("POST", {"host": "127.0.0.1:8765", "origin": "null"}, True),           # Sandbox, file://
    ("POST", {"host": "127.0.0.1:8765", "origin": "http://localhost:9999"}, True),  # andere lokale Seite
    ("POST", {"host": "127.0.0.1:8765", "sec-fetch-site": "cross-site"}, True),     # ohne Origin, aber fremd
    ("GET", {"host": "127.0.0.1:8765", "origin": FREMD}, False),            # lesen bleibt frei
    ("POST", {"host": "127.0.0.1:8765"}, False),                            # curl, Telegram, Firmen-Bus
    ("POST", {"host": "127.0.0.1:8765", "origin": "http://127.0.0.1:8765"}, False),  # App-Fenster
    ("POST", {"host": "[::1]:8765", "origin": "http://[::1]:8765"}, False),
    # Reverse-Proxy, der Host umschreibt: der Browser sagt trotzdem "same-origin"
    ("POST", {"host": "127.0.0.1:8765", "origin": "https://cody.example.org",
              "sec-fetch-site": "same-origin"}, False),
    # … oder reicht den Host als X-Forwarded-Host durch
    ("POST", {"host": "127.0.0.1:8765", "origin": "https://cody.example.org",
              "x-forwarded-host": "cody.example.org"}, False),
    # Vite beim Entwickeln: Origin localhost:5173, Host nach changeOrigin der Server
    ("POST", {"host": "127.0.0.1:8765", "origin": "http://localhost:5173",
              "sec-fetch-site": "same-origin"}, False),
])
def test_herkunft(methode, kopf, fremd):
    assert fremde_herkunft(methode, kopf) is fremd


def test_middleware_weist_fremde_seite_ab_und_laesst_eigene_durch(client, tmp_path, monkeypatch):
    from server import config as cfg
    monkeypatch.setattr(cfg, "SETTINGS_FILE", tmp_path / "settings.json")
    r = client.post("/api/settings", content=b'{"team": {"aktiv": true}}',
                    headers={"origin": FREMD, "content-type": "text/plain"})
    assert r.status_code == 403
    assert not (tmp_path / "settings.json").exists()
    assert client.post("/api/settings", json={"theme": "matrix"},
                       headers={"origin": "http://testserver"}).status_code == 200
    assert client.post("/api/settings", json={"theme": "matrix"}).status_code == 200
    assert client.get("/api/settings", headers={"origin": FREMD}).status_code == 200
