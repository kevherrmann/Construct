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
    # Browser sagt cross-site: ein passend gefälschter X-Forwarded-Host hilft nicht
    ("POST", {"host": "127.0.0.1:8765", "origin": FREMD, "sec-fetch-site": "cross-site",
              "x-forwarded-host": "evil.example"}, True),
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
                       headers={"origin": "http://127.0.0.1"}).status_code == 200
    assert client.post("/api/settings", json={"theme": "matrix"}).status_code == 200
    assert client.get("/api/settings", headers={"origin": FREMD}).status_code == 200


@pytest.mark.parametrize("host,fremd", [
    ("127.0.0.1:8765", False), ("localhost:8765", False), ("[::1]:8765", False),
    ("localhost", False), ("", False),
    ("evil.example:8765", True),          # DNS-Rebinding: fremder Name zeigt auf 127.0.0.1
    ("192.168.1.5:8765", True),
])
def test_ohne_passwort_nur_lokale_namen(host, fremd, monkeypatch):
    from server import core
    monkeypatch.setattr(core, "AUTH_PASS", "")
    monkeypatch.delenv("MATRIX_HOST", raising=False)
    assert core.fremder_host({"host": host}) is fremd


def test_host_ausnahmen(monkeypatch):
    from server import core
    monkeypatch.setattr(core, "AUTH_PASS", "")
    monkeypatch.setattr(core, "_ORIGINS", {"https://cody.example.org"})
    monkeypatch.setenv("MATRIX_HOST", "192.168.1.5")
    assert not core.fremder_host({"host": "cody.example.org"})
    assert not core.fremder_host({"host": "192.168.1.5:8765"})
    assert core.fremder_host({"host": "evil.example"})
    monkeypatch.setattr(core, "AUTH_PASS", "geheim")
    assert not core.fremder_host({"host": "evil.example"})   # das Passwort schützt


def test_middleware_weist_fremden_host_ab(client):
    r = client.get("/api/settings", headers={"host": "evil.example:8765"})
    assert r.status_code == 403
    assert client.get("/api/settings").status_code == 200


@pytest.mark.parametrize("pfad", ["/next//evil.com", "/next/%2F%2Fevil.com", "/next/\\evil.com",
                                  "/next/%5C%5Cevil.com"])
def test_next_leitet_nicht_nach_draussen(client, pfad):
    r = client.get(pfad, follow_redirects=False)
    assert r.status_code == 301
    ziel = r.headers["location"]
    assert ziel.startswith("/") and not ziel.startswith("//") and not ziel.startswith("/\\")


def test_websocket_mit_fremdem_host_wird_abgewiesen(client):
    from starlette.websockets import WebSocketDisconnect
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/api/stt/live", headers={
                "host": "evil.example:8765", "origin": "http://evil.example:8765"}) as ws:
            ws.receive_json()
