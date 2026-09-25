"""HTTP-Ebene: Routen, Auslieferung der Oberfläche, Passwortschutz."""
from starlette.websockets import WebSocketDisconnect

from server import core
from server import stt as sttmod
from server.gemini import GeminiError


def test_version(client):
    r = client.get("/api/version")
    assert r.status_code == 200
    assert r.json()["version"]


def test_oberflaeche_und_direktlinks(client):
    for path in ("/", "/chat", "/calendar", "/mail/accounts", "/settings"):
        r = client.get(path)
        assert r.status_code == 200, path
        assert "window.CONSTRUCT={" in r.text  # Startdaten eingesetzt
        assert r.headers["cache-control"].startswith("no-store")


def test_unbekannte_pfade_ehrlich_404(client):
    assert client.get("/gibtsnicht").status_code == 404
    assert client.get("/api/gibtsnicht").status_code == 404


def test_next_leitet_um(client):
    r = client.get("/next/calendar", follow_redirects=False)
    assert r.status_code == 301
    assert r.headers["location"] == "/calendar"


def test_api_routen_werden_nicht_von_direktlinks_verschluckt(client):
    # /{view}/{rest} steht zuletzt — /api/... muss vorher greifen.
    r = client.get("/api/settings")
    assert r.status_code == 200
    assert "theme" in r.json()


def test_passwortschutz(client, monkeypatch):
    monkeypatch.setattr(core, "AUTH_PASS", "geheim")
    assert client.get("/api/version").status_code == 401
    ok = client.get("/api/version", auth=(core.AUTH_USER, "geheim"))
    assert ok.status_code == 200
    assert client.get("/api/version", auth=(core.AUTH_USER, "falsch")).status_code == 401


def _ws_abgelehnt(client, **kw):
    try:
        with client.websocket_connect("/api/stt/live", **kw):
            return False
    except WebSocketDisconnect as e:
        return e.code == 1008


def test_spracheingabe_nur_von_hier_und_mit_passwort(client, monkeypatch):
    # WebSockets laufen an der HTTP-Middleware vorbei — die Route prüft selbst.
    assert _ws_abgelehnt(client, headers={"origin": "https://fremde-seite.example"})
    monkeypatch.setattr(core, "AUTH_PASS", "geheim")
    assert _ws_abgelehnt(client, headers={"origin": "http://127.0.0.1:8765"})


def test_spracheingabe_ohne_key_meldet_sich_verstaendlich(client, monkeypatch):
    def kein_key():
        raise GeminiError("Kein Gemini-Key hinterlegt")
    monkeypatch.setattr(sttmod, "api_key", kein_key)
    with client.websocket_connect("/api/stt/live",
                                  headers={"origin": "http://localhost:5173"}) as ws:
        assert ws.receive_json() == {"error": "Kein Gemini-Key hinterlegt"}
