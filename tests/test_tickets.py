"""Ticket-Board: Karten von Hand, aus Commits, Spalten und Push (server/tickets.py)."""
import json
import subprocess

import pytest

from server import tickets as tk


@pytest.fixture(autouse=True)
def ordner(tmp_path, monkeypatch):
    from server import config as cfg
    monkeypatch.setattr(tk, "TICKETS_DIR", tmp_path / "tickets")
    monkeypatch.setattr(tk, "BOARD", tmp_path / "tickets" / "board.json")
    tk._PUSH["zuletzt"] = 0.0
    # Tickets sind ab Werk aus, hier geht es um das eingeschaltete Board.
    (tmp_path / "settings.json").write_text(
        '{"lang": "de", "names": {"user": "Kevin"}, "tiles": {"tickets": true}}')
    monkeypatch.setattr(cfg, "SETTINGS_FILE", tmp_path / "settings.json")


def git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=True).stdout


@pytest.fixture()
def repo(tmp_path):
    r = tmp_path / "projekt"
    r.mkdir()
    git(r, "init", "-q", "-b", "main")
    git(r, "config", "user.email", "t@example.com")
    git(r, "config", "user.name", "T")
    return r


def committen(repo, betreff, rumpf=""):
    """Wie der Assistent committet: die Ausgabe von git commit ist das, was der
    Lauf als Werkzeugergebnis sieht."""
    (repo / "datei.txt").write_text(betreff)
    git(repo, "add", "-A")
    args = ["commit", "-m", betreff] + (["-m", rumpf] if rumpf else [])
    return git(repo, *args)


# ---------- von Hand ----------
def test_anlegen_aendern_loeschen():
    t = tk.anlegen("Login reparieren", "Passwort vergessen geht nicht", "/p")
    assert (t["nr"], t["spalte"], t["von"]) == (1, "neu", "kevin")
    t = tk.aendern(1, spalte="arbeit", titel="Login")
    assert t["spalte"] == "arbeit" and t["titel"] == "Login" and t["hand"]
    with pytest.raises(ValueError):
        tk.aendern(1, spalte="irgendwo")
    tk.loeschen(1)
    assert tk.laden()["tickets"] == []
    with pytest.raises(KeyError):
        tk.aendern(1, titel="x")


def test_nummern_werden_nie_wiederverwendet():
    tk.anlegen("A")
    tk.anlegen("B")
    tk.loeschen(2)
    assert tk.anlegen("C")["nr"] == 3


def test_ohne_titel_geht_nicht():
    with pytest.raises(ValueError):
        tk.anlegen("  ")


def test_kaputte_datei_wird_gesichert_statt_ueberschrieben():
    tk.TICKETS_DIR.mkdir(parents=True)
    tk.BOARD.write_text('{"tickets": [ kaputt')
    assert tk.laden()["tickets"] == []
    assert tk.BOARD.with_name("board.json.kaputt").exists()


def test_von_hand_verkorkste_karte_wird_bereinigt():
    tk.TICKETS_DIR.mkdir(parents=True)
    tk.BOARD.write_text(json.dumps({"tickets": [
        {"nr": 3, "titel": "x", "spalte": "fliegend", "commits": [{"sha": "nope"}]},
        {"nr": 3, "titel": "doppelt"}, "unsinn", {"nr": "a"}]}))
    d = tk.laden()
    assert [(t["nr"], t["spalte"], t["commits"]) for t in d["tickets"]] == [(3, "neu", [])]
    assert d["zaehler"] == 3


# ---------- aus Commits ----------
def test_titel_aus_langem_betreff_wird_gekuerzt():
    s = tk.kurz("Raum: Hat die Chefin nichts zu tun, während jemand an der Werkbank arbeitet, holt sie sich")
    assert s.endswith(" …") and len(s) <= tk.TITEL_KURZ + 2
    assert tk.kurz("Kurz und gut") == "Kurz und gut"


def test_commit_ausgabe_wird_erkannt():
    out = "[main 1a2b3c4] Login repariert\n 1 file changed\n[detached HEAD abcdef0] Zweiter"
    assert [(c["branch"], c["sha"], c["betreff"]) for c in tk.commits_aus(out)] == [
        ("main", "1a2b3c4", "Login repariert"), ("detached HEAD", "abcdef0", "Zweiter")]
    assert tk.commits_aus("[main (root-commit) 1a2b3c4] Erster")[0]["sha"] == "1a2b3c4"
    # deutsches git übersetzt die Klammer
    assert tk.commits_aus("[main (Root-Commit) 1a2b3c4] Erster")[0]["branch"] == "main"
    assert tk.commits_aus("nothing to commit, working tree clean") == []


def test_commit_wird_zur_karte_in_qa(repo):
    out = committen(repo, "Login repariert", "Passwort-Link ging ins Leere.")
    nr = tk.commit_buchen(out, "git commit -m ...", str(repo), session="s1", uuid="u1")
    t = tk.holen(nr)
    assert (t["titel"], t["spalte"], t["projekt"]) == ("Login repariert", "qa", str(repo))
    assert t["text"] == "Passwort-Link ging ins Leere."
    assert (t["session"], t["uuid"]) == ("s1", "u1")
    assert t["commits"][0]["sha"] == git(repo, "rev-parse", "HEAD").strip()


def test_mehrere_commits_eines_laufs_sind_eine_karte(repo):
    nr = tk.commit_buchen(committen(repo, "Login repariert"), "git commit", str(repo))
    nr2 = tk.commit_buchen(committen(repo, "Frontend neu gebaut"), "git commit", str(repo), ticket=nr)
    assert nr2 == nr and len(tk.laden()["tickets"]) == 1
    assert len(tk.holen(nr)["commits"]) == 2


def test_derselbe_commit_wird_nicht_doppelt_gebucht(repo):
    out = committen(repo, "Login repariert")
    nr = tk.commit_buchen(out, "git commit", str(repo))
    assert tk.commit_buchen(out, "git commit", str(repo)) == nr
    assert len(tk.laden()["tickets"]) == 1 and len(tk.holen(nr)["commits"]) == 1


def test_verweis_haengt_an_die_genannte_karte(repo):
    t = tk.anlegen("Dunkles Theme", projekt="")
    nr = tk.commit_buchen(committen(repo, "Theme dunkel", f"T-{t['nr']}"), "git commit", str(repo))
    assert nr == t["nr"] and len(tk.laden()["tickets"]) == 1
    t = tk.holen(nr)
    assert t["spalte"] == "qa" and t["projekt"] == str(repo) and t["titel"] == "Dunkles Theme"


def test_repo_aus_dem_befehl(repo, tmp_path):
    out = committen(repo, "Woanders committet")
    anderswo = tmp_path / "leer"
    anderswo.mkdir()
    nr = tk.commit_buchen(out, f"cd {repo} && git add -A && git commit -m x", str(anderswo))
    assert tk.holen(nr)["projekt"] == str(repo)


def test_stiller_commit_wird_ueber_die_zeit_gefunden(repo):
    import time
    seit = time.time()
    (repo / "datei.txt").write_text("still")
    git(repo, "add", "-A")
    out = git(repo, "commit", "-q", "-m", "Still committet")
    assert out == ""
    nr = tk.commit_buchen(out, "git commit -q -m x", str(repo), seit=seit)
    t = tk.holen(nr)
    assert t["titel"] == "Still committet" and t["commits"][0]["branch"] == "main"
    # ohne Startzeit bleibt es dabei: keine Zeile, kein Commit
    assert tk.commit_buchen("", "git commit -q", str(repo)) is None


def test_unbekannter_hash_bucht_nichts(repo):
    assert tk.commit_buchen("[main 1234567] Gibt es nicht", "git commit", str(repo)) is None
    assert tk.laden()["tickets"] == []


def test_amend_ersetzt_den_vorigen_commit(repo):
    nr = tk.commit_buchen(committen(repo, "Erster Wurf"), "git commit", str(repo))
    (repo / "datei.txt").write_text("anders")
    git(repo, "add", "-A")
    out = git(repo, "commit", "--amend", "-m", "Besserer Wurf")
    tk.commit_buchen(out, "git commit --amend -m x", str(repo), ticket=nr)
    assert [c["betreff"] for c in tk.holen(nr)["commits"]] == ["Besserer Wurf"]


# ---------- Push ----------
def test_gepusht_heisst_done(repo, tmp_path):
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "-q", "--bare", str(remote)], check=True)
    git(repo, "remote", "add", "origin", str(remote))
    nr = tk.commit_buchen(committen(repo, "Login repariert"), "git commit", str(repo))
    assert tk.push_pruefen(erzwingen=True) is False and tk.holen(nr)["spalte"] == "qa"
    git(repo, "push", "-q", "origin", "main")
    assert tk.push_pruefen(erzwingen=True) is True
    t = tk.holen(nr)
    assert t["spalte"] == "done" and t["commits"][0]["gepusht"]


def test_von_hand_zurueckgezogen_bleibt_trotz_push(repo, tmp_path):
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "-q", "--bare", str(remote)], check=True)
    git(repo, "remote", "add", "origin", str(remote))
    nr = tk.commit_buchen(committen(repo, "Login repariert"), "git commit", str(repo))
    git(repo, "push", "-q", "origin", "main")
    tk.push_pruefen(erzwingen=True)
    tk.aendern(nr, spalte="qa")                    # Fehler gefunden: zurück in die QA
    tk.push_pruefen(erzwingen=True)
    assert tk.holen(nr)["spalte"] == "qa"


def test_ohne_remote_nie_done(repo):
    nr = tk.commit_buchen(committen(repo, "Lokal"), "git commit", str(repo))
    tk.push_pruefen(erzwingen=True)
    assert tk.holen(nr)["spalte"] == "qa"


# ---------- Firma ----------
def test_auftrag_bekommt_eine_karte_in_arbeit_und_folgt_ihm(repo, monkeypatch):
    nr = tk.auftrag_angelegt("a1b2c3d4", "Dunkles Theme", "Bitte dunkel", str(repo), "s1")
    t = tk.holen(nr)
    assert (t["spalte"], t["auftrag"], t["projekt"], t["session"]) == ("arbeit", "a1b2c3d4", str(repo), "s1")
    tk.auftrag_spalte("a1b2c3d4", "review")
    assert tk.holen(nr)["spalte"] == "review"
    # Commit im Auftrag: die Karte bleibt, wo die Firma sie hat
    monkeypatch.setattr(tk, "_auftrag_laeuft", lambda aid: True)
    assert tk.commit_buchen(committen(repo, "Theme"), "git commit", str(repo), auftrag="a1b2c3d4") == nr
    assert tk.holen(nr)["spalte"] == "review"


def test_auftrag_zu_einer_karte_aus_neu(repo):
    t = tk.anlegen("Dunkles Theme")
    assert tk.auftrag_angelegt("a1b2c3d4", "x", "y", str(repo), ticket=t["nr"]) == t["nr"]
    assert tk.holen(t["nr"])["spalte"] == "arbeit"


# ---------- im Lauf ----------
STUB = r'''
import json, sys
sys.stdin.readline()
def out(ev):
    sys.stdout.write(json.dumps(ev) + "\n"); sys.stdout.flush()
out({"type": "system", "subtype": "init", "session_id": "abcd1234-0000-0000-0000-0000000000aa"})
out({"type": "user", "uuid": "u-erste", "message": {"role": "user", "content": [{"type": "text", "text": "Mach"}]}})
out({"type": "user", "uuid": "u-bg", "message": {"role": "user", "content": [
     {"type": "text", "text": "<task-notification>fertig</task-notification>"}]}})
out({"type": "assistant", "message": {"content": [
     {"type": "tool_use", "id": "t1", "name": "Bash", "input": {"command": "git commit -m 'Login repariert'"}}]}})
out({"type": "user", "message": {"role": "user", "content": [
     {"type": "tool_result", "tool_use_id": "t1", "content": AUSGABE}]}})
out({"type": "result", "subtype": "success", "session_id": "abcd1234-0000-0000-0000-0000000000aa", "usage": {}})
'''


def _lauf(tmp_path, monkeypatch, ausgabe, cwd):
    import asyncio
    import sys

    from server import runs
    stub = tmp_path / "claude_stub.py"
    stub.write_text(STUB.replace("AUSGABE", json.dumps(ausgabe)))
    monkeypatch.setattr(runs, "claude_bin", lambda: sys.executable)
    monkeypatch.setattr(runs, "maybe_notify", lambda run: None)

    async def los():
        run = runs.Run("t-tickets", str(cwd), None, "", initial_prompt="hallo")
        await runs.run_claude(run, [sys.executable, str(stub)])
        return run
    return asyncio.run(los())


def test_lauf_bucht_seinen_commit(tmp_path, monkeypatch, repo):
    run = _lauf(tmp_path, monkeypatch, committen(repo, "Login repariert"), repo)
    t = tk.laden()["tickets"][0]
    assert (t["titel"], t["session"], t["uuid"]) == ("Login repariert", "abcd1234-0000-0000-0000-0000000000aa",
                                                   "u-erste")
    assert run.board_ticket == t["nr"] and {"type": "tickets", "nr": t["nr"]} in run.events


def test_lauf_ohne_kachel_bucht_nichts(tmp_path, monkeypatch, repo):
    (tmp_path / "settings.json").write_text('{"lang": "de", "tiles": {"tickets": false}}')
    _lauf(tmp_path, monkeypatch, committen(repo, "Login repariert"), repo)
    assert not tk.BOARD.exists()


# ---------- API, CLI, Regeln ----------
def test_api_roundtrip(client):
    t = client.post("/api/tickets", json={"titel": "Neu am Board", "projekt": "/p"}).json()
    assert t["spalte"] == "neu"
    r = client.post(f"/api/tickets/{t['nr']}", json={"spalte": "arbeit"}).json()
    assert r["spalte"] == "arbeit"
    b = client.get("/api/tickets").json()
    assert b["spalten"] == list(tk.SPALTEN) and b["projekte"] == [{"pfad": "/p", "name": "p"}]
    assert client.get("/api/tickets?projekt=/anders").json()["tickets"] == []
    assert client.post(f"/api/tickets/{t['nr']}", json={"spalte": "x"}).status_code == 400
    assert client.delete(f"/api/tickets/{t['nr']}").json() == {"ok": True}
    assert client.delete(f"/api/tickets/{t['nr']}").status_code == 404


def test_ticket_routen_ohne_kachel_404(client, tmp_path):
    (tmp_path / "settings.json").write_text(json.dumps({"lang": "de", "tiles": {"tickets": False}}))
    assert client.get("/api/tickets").status_code == 404
    assert client.post("/api/tickets", json={"titel": "x"}).status_code == 404
    (tmp_path / "settings.json").write_text(json.dumps({"lang": "de", "tiles": {"tickets": True}}))
    assert client.get("/api/tickets").status_code == 200


def test_tickets_ab_werk_aus(tmp_path):
    from server import config as cfg
    (tmp_path / "settings.json").write_text('{"lang": "de"}')
    assert cfg.load_settings()["tiles"]["tickets"] is False


def test_cli(capsys):
    import tickets as cli
    assert cli.main(["new", "Dunkles Theme", "Bitte dunkel"]) == 0
    assert cli.main(["move", "T-1", "work"]) == 0
    assert tk.holen(1)["spalte"] == "arbeit"
    cli.main(["list"])
    assert "T-1" in capsys.readouterr().out
    cli.main(["show", "1"])
    assert "Bitte dunkel" in capsys.readouterr().out
    with pytest.raises(SystemExit):
        cli.main(["move", "1", "nirgendwo"])


def test_regeln_nennen_cli_und_verweis():
    text = tk.regeln()
    assert "tickets.py" in text and "T-<Nummer>" in text and "Kevin" in text


@pytest.mark.parametrize("an", [True, False])
def test_chat_lauf_bekommt_regeln_nur_mit_kachel(tmp_path, monkeypatch, an):
    import asyncio

    from server import runs
    (tmp_path / "settings.json").write_text(json.dumps({"lang": "de", "tiles": {"tickets": an}}))
    gesehen = []

    async def nichts(run, cmd):
        gesehen.append(cmd)
    monkeypatch.setattr(runs, "run_claude", nichts)
    monkeypatch.setattr(runs, "load_persona", lambda: "Persona")

    async def los():
        runs.start_run("hallo", str(tmp_path), "default", chat=True)
        await asyncio.sleep(0)
    asyncio.run(los())
    persona = gesehen[0][gesehen[0].index("--append-system-prompt") + 1]
    assert ("## Tickets" in persona) is an
