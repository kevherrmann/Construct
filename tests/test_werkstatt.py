"""Werkbank und Fernseher im Construct-Raum: Dateien und Befehle aus dem Protokoll."""
import json
import subprocess

from server.routes import sessions as routes
from server.sessions import werkstatt_aus_transcript


def _zeilen(*evs):
    return ("\n".join(json.dumps(e) for e in evs) + "\n").encode()


def _assistent(*bloecke):
    return {"type": "assistant", "cwd": "/tmp/projekt", "timestamp": "2026-10-04T10:00:00Z",
            "message": {"role": "assistant", "content": list(bloecke)}}


def _ergebnis(tid, text, fehler=False):
    return {"type": "user", "message": {"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": tid, "content": text, "is_error": fehler}]}}


def test_dateien_und_befehle_aus_dem_protokoll():
    data = _zeilen(
        {"type": "user", "cwd": "/tmp/projekt", "message": {"role": "user", "content": "los"}},
        _assistent({"type": "tool_use", "id": "t1", "name": "Write", "input": {"file_path": "/tmp/projekt/a.py"}}),
        _ergebnis("t1", "ok"),
        _assistent({"type": "tool_use", "id": "t2", "name": "Bash",
                    "input": {"command": "pytest -q", "description": "Tests"}}),
        _ergebnis("t2", [{"type": "text", "text": "1 failed"}], fehler=True),
        _assistent({"type": "tool_use", "id": "t3", "name": "Edit", "input": {"file_path": "/tmp/projekt/a.py"}},
                   {"type": "tool_use", "id": "t4", "name": "Edit", "input": {"file_path": "/tmp/projekt/b.py"}}),
        _assistent({"type": "tool_use", "id": "t5", "name": "Bash", "input": {"command": "sleep 99"}}),
    )
    w = werkstatt_aus_transcript(data)
    assert w["cwd"] == "/tmp/projekt"
    # je Pfad einmal, zuletzt bearbeitete hinten; neu bleibt neu
    assert [d["path"] for d in w["dateien"]] == ["/tmp/projekt/a.py", "/tmp/projekt/b.py"]
    assert w["dateien"][0] == {**w["dateien"][0], "neu": True, "mal": 2}
    assert w["dateien"][1]["neu"] is False
    assert w["befehle"][0] == {"command": "pytest -q", "description": "Tests", "output": "1 failed",
                               "isError": True, "ts": "2026-10-04T10:00:00Z"}
    assert w["befehle"][1]["output"] is None  # läuft noch


def test_git_aenderungen(tmp_path):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    (tmp_path / "neu.txt").write_text("x")
    g = routes._git_aenderungen(str(tmp_path))
    assert g["repo"] is True
    assert g["dateien"] == [{"path": str(tmp_path / "neu.txt"), "status": "??"}]
    assert routes._git_aenderungen(str(tmp_path / "gibtsnicht"))["repo"] is False


def test_route(client, tmp_path, monkeypatch):
    monkeypatch.setattr(routes, "PROJECTS_DIR", tmp_path)
    (tmp_path / "proj").mkdir()
    (tmp_path / "proj" / "abcdefgh-1234.jsonl").write_bytes(_zeilen(
        _assistent({"type": "tool_use", "id": "t1", "name": "Write", "input": {"file_path": "/tmp/projekt/a.py"}})))
    r = client.get("/api/werkstatt/abcdefgh-1234")
    assert r.status_code == 200
    assert r.json()["dateien"][0]["path"] == "/tmp/projekt/a.py"
    assert "git" in r.json()
    assert client.get("/api/werkstatt/kurz").status_code == 400
    assert client.get("/api/werkstatt/abcdefgh-9999").status_code == 404
