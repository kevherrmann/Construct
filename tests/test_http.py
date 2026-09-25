"""HTTP-Ebene: Routen, Auslieferung der Oberfläche, Passwortschutz."""
import app as appmod


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
    monkeypatch.setattr(appmod, "AUTH_PASS", "geheim")
    assert client.get("/api/version").status_code == 401
    ok = client.get("/api/version", auth=(appmod.AUTH_USER, "geheim"))
    assert ok.status_code == 200
    assert client.get("/api/version", auth=(appmod.AUTH_USER, "falsch")).status_code == 401
