"""MCP-Server einrichten und entfernen: nur gegen ein gemocktes subprocess.

Nie echt gegen die Claude-Konfiguration, die gehört dem Nutzer."""
import json
import subprocess

import pytest

from server.routes import files

EXE = "/opt/claude/bin/claude"


@pytest.fixture(autouse=True)
def kachel_an(tmp_path, monkeypatch):
    from server import config as cfg
    (tmp_path / "settings.json").write_text(json.dumps({"lang": "de", "tiles": {"mcp": True}}))
    monkeypatch.setattr(cfg, "SETTINGS_FILE", tmp_path / "settings.json")
    return tmp_path / "settings.json"


def test_ohne_kachel_gibt_es_die_routen_nicht(client, cli, kachel_an):
    kachel_an.write_text(json.dumps({"tiles": {"mcp": False}}))
    calls, _ = cli
    assert client.get("/api/mcp").status_code == 404
    assert client.post("/api/mcp", json={"name": "x", "command": "y"}).status_code == 404
    assert client.delete("/api/mcp/x").status_code == 404
    assert not calls


@pytest.fixture
def cli(monkeypatch):
    """Fängt jeden subprocess.run ab und merkt sich Argumente und Schalter."""
    calls = []
    result = {"returncode": 0, "stdout": "", "stderr": ""}

    def fake_run(argv, **kw):
        calls.append({"argv": argv, **kw})
        if "exc" in result:
            raise result["exc"]
        return subprocess.CompletedProcess(argv, result["returncode"],
                                           result["stdout"], result["stderr"])

    monkeypatch.setattr(files.subprocess, "run", fake_run)
    monkeypatch.setattr(files, "claude_bin", lambda: EXE)
    monkeypatch.setattr(files, "claude_env", lambda: {"PATH": "/usr/bin"})
    return calls, result


def _json_arg(call):
    argv = call["argv"]
    assert argv[:3] == [EXE, "mcp", "add-json"]
    return json.loads(argv[4])


def test_stdio_hinzufuegen(client, cli):
    calls, _ = cli
    r = client.post("/api/mcp", json={
        "name": "files_1", "transport": "stdio", "command": "npx",
        "args": ["-y", "@x/server", "--flag"], "env": {"API_KEY": "s3cr3t"}})
    assert r.status_code == 200 and r.json() == {"ok": True}
    (c,) = calls
    assert c["argv"][3] == "files_1" and c["argv"][5:] == ["-s", "user"]
    assert _json_arg(c) == {"type": "stdio", "command": "npx",
                            "args": ["-y", "@x/server", "--flag"],
                            "env": {"API_KEY": "s3cr3t"}}
    assert not c.get("shell") and c["timeout"] and c["cwd"] == files.WORKSPACE


@pytest.mark.parametrize("transport", ["http", "sse"])
def test_http_und_sse_hinzufuegen(client, cli, transport):
    calls, _ = cli
    r = client.post("/api/mcp", json={
        "name": "remote", "transport": transport, "scope": "local",
        "url": "https://mcp.example.com/mcp",
        "headers": {"Authorization": "Bearer abc"}})
    assert r.status_code == 200
    (c,) = calls
    assert c["argv"][5:] == ["-s", "local"]
    assert _json_arg(c) == {"type": transport, "url": "https://mcp.example.com/mcp",
                            "headers": {"Authorization": "Bearer abc"}}
    assert not c.get("shell")


def test_leere_env_und_header_fallen_weg(client, cli):
    calls, _ = cli
    client.post("/api/mcp", json={"name": "a", "command": "srv", "env": {}})
    client.post("/api/mcp", json={"name": "b", "transport": "http",
                                  "url": "http://localhost:3000"})
    assert _json_arg(calls[0]) == {"type": "stdio", "command": "srv", "args": []}
    assert _json_arg(calls[1]) == {"type": "http", "url": "http://localhost:3000"}


def test_entfernen(client, cli):
    calls, _ = cli
    assert client.delete("/api/mcp/files_1").json() == {"ok": True}
    assert client.delete("/api/mcp/files_1?scope=local").status_code == 200
    assert calls[0]["argv"] == [EXE, "mcp", "remove", "files_1"]
    assert calls[1]["argv"] == [EXE, "mcp", "remove", "files_1", "-s", "local"]
    assert not any(c.get("shell") for c in calls)


@pytest.mark.parametrize("name", [
    "", "-s", "_x", "a b", "a;rm -rf ~", "$(id)", "ä", "a/b", "x" * 65, None, 5])
def test_ungueltige_namen(client, cli, name):
    calls, _ = cli
    r = client.post("/api/mcp", json={"name": name, "command": "srv"})
    assert r.status_code == 400
    assert calls == []


@pytest.mark.parametrize("name", ["-s", "a b", "x" * 65, "%24(id)"])
def test_ungueltige_namen_beim_entfernen(client, cli, name):
    calls, _ = cli
    assert client.delete(f"/api/mcp/{name}").status_code == 400
    assert calls == []


@pytest.mark.parametrize("body", [
    {"transport": "ws", "url": "ws://x"},
    {"scope": "project", "command": "srv"},
    {"transport": "stdio"},
    {"transport": "stdio", "command": "  "},
    {"command": "srv", "args": "-y x"},
    {"command": "srv", "args": [1, 2]},
    {"command": "srv", "env": {"1BAD": "x"}},
    {"command": "srv", "env": {"A-B": "x"}},
    {"command": "srv", "env": {"OK": 5}},
    {"command": "srv", "env": ["A=b"]},
    {"transport": "http"},
    {"transport": "http", "url": "file:///etc/passwd"},
    {"transport": "http", "url": "javascript:alert(1)"},
    {"transport": "http", "url": "https://"},
    {"transport": "http", "url": "https://a b"},
    {"transport": "http", "url": "https://x", "headers": {"Bad Name": "v"}},
    {"transport": "http", "url": "https://x", "headers": {"X": "a\r\nInjected: 1"}},
])
def test_ungueltige_eingaben(client, cli, body):
    calls, _ = cli
    r = client.post("/api/mcp", json={"name": "srv", **body})
    assert r.status_code == 400, body
    assert isinstance(r.json()["detail"], str)
    assert calls == []


def test_kein_objekt(client, cli):
    calls, _ = cli
    assert client.post("/api/mcp", json=["name"]).status_code == 400
    assert calls == []


def test_ungueltiger_scope_beim_entfernen(client, cli):
    calls, _ = cli
    assert client.delete("/api/mcp/srv?scope=project").status_code == 400
    assert calls == []


def test_geheimer_wert_nicht_in_eingabefehler(client, cli):
    r = client.post("/api/mcp", json={"name": "srv", "command": "x",
                                      "env": {"TOKEN": "geheim\nzwei"}})
    assert r.status_code == 400
    assert "geheim" not in r.text


def test_cli_fehler_ohne_geheimnisse(client, cli):
    _, result = cli
    env_secret, hdr_secret = 'tok"en-123\\x', "Bearer hdr-456"
    body = {"name": "srv", "command": "x", "env": {"K": env_secret}}
    raw = json.dumps({"type": "stdio", "command": "x", "args": [], "env": {"K": env_secret}})
    result.update(returncode=1, stderr=(
        f"Invalid configuration in {raw}: value {env_secret} / "
        f"{json.dumps(env_secret)[1:-1]} rejected"))
    r = client.post("/api/mcp", json=body)
    assert r.status_code == 502
    assert "tok" not in r.text and "123" not in r.text
    assert "Claude Code meldet" in r.json()["detail"]

    result.update(stderr=f"bad header Authorization: {hdr_secret}")
    r = client.post("/api/mcp", json={"name": "srv", "transport": "sse",
                                      "url": "https://x", "headers": {"Authorization": hdr_secret}})
    assert r.status_code == 502
    assert "hdr-456" not in r.text


def test_server_gibt_es_schon(client, cli):
    _, result = cli
    result.update(returncode=1, stderr="MCP server srv already exists in user config")
    r = client.post("/api/mcp", json={"name": "srv", "command": "x"})
    assert r.status_code == 400 and "schon" in r.json()["detail"]


def test_entfernen_nicht_gefunden(client, cli):
    _, result = cli
    result.update(returncode=1,
                  stderr='No MCP server named "srv". Run `claude mcp add` to add one.')
    r = client.delete("/api/mcp/srv")
    assert r.status_code == 404 and "srv" in r.json()["detail"]


def test_zeitueberschreitung(client, cli):
    _, result = cli
    result["exc"] = subprocess.TimeoutExpired(["claude"], 30)
    assert client.delete("/api/mcp/srv").status_code == 504


def test_claude_fehlt(client, cli, monkeypatch):
    calls, _ = cli
    monkeypatch.setattr(files, "claude_bin", lambda: "")
    r = client.post("/api/mcp", json={"name": "srv", "command": "x"})
    assert r.status_code == 502 and "nicht installiert" in r.json()["detail"]
    assert calls == []


def test_zeilenumbruch_am_ende_abgewiesen(client, cli):
    # re.match mit $ ließe "abc\n" durch, darum fullmatch.
    calls, _ = cli
    for body in ({"name": "abc\n", "command": "x"},
                 {"name": "abc", "command": "x", "env": {"KEY\n": "v"}},
                 {"name": "abc", "transport": "http", "url": "https://x",
                  "headers": {"X-Key\n": "v"}}):
        assert client.post("/api/mcp", json=body).status_code == 400, body
    assert client.delete("/api/mcp/abc%0A").status_code == 400
    assert calls == []


def test_geheimnis_mit_leerzeichen_am_ende_geschwaerzt(client, cli):
    _, result = cli
    result.update(returncode=1, stderr="Invalid value: abc   ")
    r = client.post("/api/mcp", json={"name": "srv", "command": "x",
                                      "env": {"K": "abc   "}})
    assert r.status_code == 502
    assert "abc" not in r.json()["detail"]


def test_text_plain_abgewiesen(client, cli):
    # Fremde Webseiten dürfen ohne CORS-Preflight nur "einfache" Rümpfe wie
    # text/plain schicken. Wird der angenommen, könnte jede Seite Server anlegen.
    calls, _ = cli
    r = client.post("/api/mcp", content=json.dumps({"name": "srv", "command": "x"}),
                    headers={"Content-Type": "text/plain"})
    assert r.status_code in (400, 415, 422)
    assert calls == []


def test_meldungen_auf_englisch(client, cli, kachel_an):
    kachel_an.write_text(json.dumps({"lang": "en", "tiles": {"mcp": True}}))
    r = client.post("/api/mcp", json={"name": "x", "transport": "stdio"})
    assert r.status_code == 400 and r.json()["detail"] == "stdio needs a command."
