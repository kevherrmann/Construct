"""Starter: Browser für das App-Fenster finden, Befehl bauen."""
import desktop


def test_exec_aus_desktop_ohne_platzhalter():
    text = """[Desktop Entry]
Name=Google Chrome
Exec=/usr/bin/flatpak run --branch=stable --command=/app/bin/chrome --file-forwarding com.google.Chrome @@u %U @@

[Desktop Action new-window]
Exec=/usr/bin/flatpak run com.google.Chrome --new-window
"""
    assert desktop.exec_aus_desktop(text) == [
        "/usr/bin/flatpak", "run", "--branch=stable", "--command=/app/bin/chrome",
        "--file-forwarding", "com.google.Chrome"]


def test_fensterbefehl_eigenes_profil(monkeypatch):
    cmd = desktop.fenster_befehl(["brave-browser"], "http://127.0.0.1:8765/?fenster=1")
    assert cmd[0] == "brave-browser"
    assert "--app=http://127.0.0.1:8765/?fenster=1" in cmd
    assert f"--user-data-dir={desktop.BASE_DIR / '.fenster'}" in cmd
    assert "--class=construct" in cmd


def test_flatpak_profil_im_eigenen_datenordner():
    p = desktop._profil(["/usr/bin/flatpak", "run", "--branch=stable", "com.google.Chrome"])
    assert p.parts[-4:] == ("app", "com.google.Chrome", "data", "construct-fenster")


def test_umgebung_bestimmt_den_browser(monkeypatch):
    monkeypatch.setenv("CONSTRUCT_BROWSER", "/opt/chromium/chrome --foo")
    assert desktop.chromium_browser() == ["/opt/chromium/chrome", "--foo"]


def test_kein_chromium_dann_tab(monkeypatch):
    geoeffnet = []
    monkeypatch.setattr(desktop, "chromium_browser", lambda: [])
    monkeypatch.setattr(desktop.webbrowser, "open", lambda u: geoeffnet.append(u))
    desktop.open_window()
    assert geoeffnet == [desktop.URL]


def test_open_url_nur_von_hier(client, monkeypatch):
    import webbrowser
    geoeffnet = []
    monkeypatch.setattr(webbrowser, "open", lambda u: geoeffnet.append(u) or True)
    # TestClient meldet sich als "testclient", nicht als Loopback
    r = client.post("/api/open-url", json={"url": "https://example.com"})
    assert r.status_code == 403 and not geoeffnet


def test_open_url_von_loopback(monkeypatch):
    import webbrowser
    from fastapi.testclient import TestClient
    import app as appmod
    geoeffnet = []
    monkeypatch.setattr(webbrowser, "open", lambda u: geoeffnet.append(u) or True)
    c = TestClient(appmod.app, client=("127.0.0.1", 50000))
    assert c.post("/api/open-url", json={"url": "https://example.com"}).json() == {"ok": True}
    assert c.post("/api/open-url", json={"url": "file:///etc/passwd"}).status_code == 400
    fremd = c.post("/api/open-url", json={"url": "https://x.example"},
                   headers={"origin": "https://boese.example"})
    assert fremd.status_code == 403
    assert geoeffnet == ["https://example.com"]


def test_beenden_nur_von_hier(monkeypatch):
    from fastapi.testclient import TestClient
    import app as appmod
    from server import core
    from server.routes import system
    gerufen = []
    # Die Route ruft beenden() zeitverzögert: hier nie den echten Prozess treffen.
    monkeypatch.setattr(system, "beenden", lambda: None)
    monkeypatch.setattr(core, "_beim_beenden", [lambda: gerufen.append(1)])
    fremd = TestClient(appmod.app)               # "testclient", kein Loopback
    assert fremd.post("/api/shutdown").status_code == 403
    c = TestClient(appmod.app, client=("127.0.0.1", 50000))
    assert c.post("/api/shutdown", headers={"origin": "https://boese.example"}).status_code == 403
    assert c.post("/api/shutdown").json() == {"ok": True}
    core.beenden()                               # was die Route verzögert aufruft
    assert gerufen == [1]
