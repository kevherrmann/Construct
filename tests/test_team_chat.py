"""Die Firma im Chat: Übergabe per Markerzeile, Spalten der Akten (server/team/chat.py)."""
import json

import pytest

from server import config as cfg
from server.team import agents as ag
from server.team import chat as teamchat


@pytest.fixture(autouse=True)
def einstellungen(tmp_path, monkeypatch):
    monkeypatch.setattr(ag, "FIRMA_DIR", tmp_path / "firma")
    monkeypatch.setattr(ag, "AGENTS_DIR", tmp_path / "firma" / "agents")
    (tmp_path / "settings.json").write_text(json.dumps(
        {"lang": "de", "names": {"user": "Anna"}, "team": {"aktiv": True}, "tiles": {"tickets": True}}))
    monkeypatch.setattr(cfg, "SETTINGS_FILE", tmp_path / "settings.json")


@pytest.mark.parametrize("text,titel", [
    ("Auftrag.\n\n[[firma: Dunkles Theme]]", "Dunkles Theme"),
    ("Auftrag.\n[[firma]]\n", ""),
    ("Job.\n\n[[company: Dark theme]]", "Dark theme"),
    ("Auftrag.\n\n[[firma: T-12 Theme]]", "T-12 Theme"),
    ("Erst [[firma: x]] mitten im Text", None),
    ("[[firma: Alt]]\n\nDanach kam noch Text.", None),
    ("Nichts davon.", None),
])
def test_marke_zaehlt_nur_am_ende(text, titel):
    assert teamchat.marke(text) == titel


def test_ohne_marke_entfernt_auch_alte_ticketzeilen():
    assert teamchat.ohne_marke("Gemacht.\n\n[[firma: X]]") == "Gemacht."
    assert teamchat.ohne_marke("Gemacht.\n[[ticket neu: Uhr]]\n[[ticket zu: 2]]") == "Gemacht."
    assert teamchat.ohne_marke("Bleibt [[firma: X]] stehen.") == "Bleibt [[firma: X]] stehen."


def test_ohne_meldung():
    assert teamchat.ohne_meldung("Mach weiter\n\n[Firma: „X“ (a1): fertig]") == "Mach weiter"
    assert teamchat.ohne_meldung("Alt\n\n[Tickets: aktuell #1]") == "Alt"


def test_regeln_schalter_entscheidet():
    text = teamchat.regeln()
    assert "entscheidet der Schalter, nicht du" in text and "ohne Rückfrage" in text
    assert "Anna" in text
    assert "[[firma: Kurztitel]]" in text
    # Der Begriff ist verankert: wer zur Firma gehört, steht dabei
    assert "„Die Firma“ ist der Team-Modus" in text and "Janus: Code-Auditor" in text


def test_uebergabe_mit_ticketverweis(monkeypatch, tmp_path):
    from server import tickets as tk
    from server.team import engine
    monkeypatch.setattr(tk, "TICKETS_DIR", tmp_path / "tickets")
    monkeypatch.setattr(tk, "BOARD", tmp_path / "tickets" / "board.json")
    karte = tk.anlegen("Dunkles Theme", "Alles in dunkel, auch die Dialoge")
    angelegt = []
    monkeypatch.setattr(engine, "starten", lambda: None)
    monkeypatch.setattr(engine, "auftrag_anlegen",
                        lambda titel, brief, cwd, **kw: angelegt.append((titel, brief, kw)) or {"id": "a1"})
    teamchat.uebergeben(f"Elara übernimmt.\n\n[[firma: T-{karte['nr']} Theme]]", "s1", str(tmp_path))
    titel, brief, kw = angelegt[0]
    assert titel == "Theme" and kw == {"bruecke": {"session": "s1"}, "ticket": karte["nr"]}
    assert "Alles in dunkel" in brief and "Elara übernimmt." in brief


def test_janus_und_miranda_haben_ihre_spalte():
    ag.list_agents("/tmp/construct-test-ws")
    assert ag.load_agent("janus", "/tmp/construct-test-ws")["spalte"] == "review"
    assert ag.load_agent("miranda", "/tmp/construct-test-ws")["spalte"] == "qa"
    assert ag.load_agent("luna", "/tmp/construct-test-ws")["spalte"] == ""


def test_angepasste_akte_ohne_feld_nimmt_die_spalte_der_vorlage():
    ag.list_agents("/tmp/construct-test-ws")
    akte = ag.AGENTS_DIR / "janus" / "AGENT.md"
    akte.write_text(akte.read_text().replace("spalte: review\n", "").replace("title: ", "title: Eigener "))
    ag._ABGEGLICHEN.clear()
    a = ag.load_agent("janus", "/tmp/construct-test-ws")
    assert a["title"].startswith("Eigener") and a["spalte"] == "review"


@pytest.mark.parametrize("slug,erwartet", [("janus", "review"), ("miranda", "qa"), ("luna", "arbeit"),
                                          ("chef", None)])
def test_karte_folgt_dem_mitarbeiter(monkeypatch, slug, erwartet):
    from server import tickets as tk
    from server.team import engine
    gezogen = []
    monkeypatch.setattr(tk, "auftrag_spalte", lambda aid, spalte: gezogen.append(spalte))
    ag.list_agents("/tmp/construct-test-ws")
    a = ag.load_agent(slug, "/tmp/construct-test-ws")
    engine.board_spalte({"id": "a1", "owner": "chef", "board": 3}, a)
    assert gezogen == ([erwartet] if erwartet else [])
    engine.board_spalte({"id": "a1", "owner": "chef", "board": 3}, fertig=True)
    assert gezogen[-1] == "qa"


@pytest.mark.parametrize("ev,firma", [
    ({"type": "attachment", "attachment": {"type": "deferred_tools_delta",
                                           "addedNames": ["Read", "mcp__firma__liefern"]}}, "firma"),
    # Claude Code 2.1.29x: bei wenigen Werkzeugen steht die Liste nur noch im prompt_snapshot
    ({"type": "attachment", "attachment": {"type": "prompt_snapshot",
                                           "tools": [{"name": "Read"}, {"name": "mcp__firma__beauftragen"}]}}, "firma"),
    ({"type": "attachment", "attachment": {"type": "prompt_snapshot", "tools": [{"name": "Read"}]}}, ""),
])
def test_zuege_der_firma_werden_erkannt(ev, firma):
    from server.sessions import _fremde_firma
    assert _fremde_firma(ev) == firma


def test_gebuchte_sitzungen_der_firma(monkeypatch, tmp_path):
    from server import sessions
    from server.team import auftraege as auf
    monkeypatch.setattr(auf, "AUFTRAEGE_DIR", tmp_path / "auftraege")
    t = auf.neu("x", "y")
    t["sessions"] = {"luna": "sess-luna"}
    auf.speichern(t)
    assert "sess-luna" in sessions.firma_sessions()


# ---------- Übergabe bei ausgeschaltetem Team-Modus ----------
SID = "abcd1234-0000-0000-0000-000000firma"


def _team(an: bool, tmp_path):
    s = json.loads((tmp_path / "settings.json").read_text())
    s["team"]["aktiv"] = an
    (tmp_path / "settings.json").write_text(json.dumps(s))


def _zug(text: str):
    from server import runs
    run = runs.Run("r-firma", "/tmp/projekt", SID, "")
    run.emit = lambda ev: run.ereignisse.append(ev)
    run.ereignisse = []
    run.last_text = text
    runs._firma_marke(run)
    return run


def test_team_aus_kein_auftrag_aber_ereignis_und_einmal_meldung(monkeypatch, tmp_path):
    from server.team import engine
    _team(False, tmp_path)
    monkeypatch.setattr(engine, "auftrag_anlegen", lambda *a, **kw: pytest.fail("Auftrag trotz Team aus"))
    run = _zug("Baut die Uhr.\n\n[[firma: Uhr bauen]]")
    [ev] = run.ereignisse
    assert ev["type"] == "firma_aus" and ev["session_id"] == SID
    assert ev["uebergabe"]["titel"] == "Uhr bauen" and ev["uebergabe"]["status"] == "offen"
    # übersteht einen Neustart: liegt in der Datei, nicht im Speicher
    gespeichert = json.loads((tmp_path / "firma" / "nicht_zugestellt.json").read_text())[SID][0]
    assert gespeichert["cwd"] == "/tmp/projekt" and "Baut die Uhr." in gespeichert["text"]
    assert teamchat.nicht_zugestellt(SID) == [ev["uebergabe"]]
    # Einschalten allein startet nichts
    _team(True, tmp_path)
    assert teamchat.nicht_zugestellt(SID)[0]["status"] == "offen"
    assert teamchat.nicht_angekommen(SID) == \
        "\n\n[Firma: Übergabe „Uhr bauen“ nicht angekommen, der Team-Modus war aus.]"
    assert teamchat.nicht_angekommen(SID) == ""
    assert teamchat.ohne_meldung("Und?" + "\n\n[Firma: Übergabe „Uhr bauen“ nicht angekommen, der Team-Modus war aus.]") == "Und?"


def test_meldung_haengt_an_der_naechsten_nachricht(monkeypatch, client, tmp_path):
    from server.routes import chat as chatroute
    _team(False, tmp_path)
    _zug("Baut die Uhr.\n\n[[firma: Uhr bauen]]")
    prompts = []

    class Lauf:
        id = "r-x"
    monkeypatch.setattr(chatroute, "start_run", lambda prompt, *a, **kw: prompts.append(prompt) or Lauf())
    for _ in range(2):
        assert client.post("/api/chat", json={"message": "Und?", "session_id": SID}).status_code == 200
    assert prompts[0].endswith("[Firma: Übergabe „Uhr bauen“ nicht angekommen, der Team-Modus war aus.]")
    assert "nicht angekommen" not in prompts[1]


def test_team_an_geht_wie_bisher_an_die_firma(monkeypatch, tmp_path):
    from server.team import engine
    monkeypatch.setattr(engine, "starten", lambda: None)
    monkeypatch.setattr(engine, "auftrag_anlegen", lambda titel, brief, cwd, **kw: {"id": "a1"})
    run = _zug("Baut die Uhr.\n\n[[firma: Uhr bauen]]")
    assert run.ereignisse == [{"type": "firma", "auftrag": "a1"}]
    assert teamchat.nicht_zugestellt(SID) == []


def test_knopf_schaltet_ein_und_uebergibt_an_die_session(monkeypatch, client, tmp_path):
    from server.team import engine
    _team(False, tmp_path)
    run = _zug("Baut die Uhr.\n\n[[firma: Uhr bauen]]")
    eid = run.ereignisse[0]["uebergabe"]["id"]
    angelegt = []
    monkeypatch.setattr(engine, "starten", lambda: None)
    monkeypatch.setattr(engine, "auftrag_anlegen",
                        lambda titel, brief, cwd, **kw: angelegt.append((titel, brief, cwd, kw)) or {"id": "a7"})
    r = client.post(f"/api/firma/uebergaben/{SID}/{eid}")
    assert r.status_code == 200, r.text
    assert r.json()["auftrag"] == "a7" and r.json()["settings"]["team"]["aktiv"]
    assert r.json()["uebergabe"] == {**run.ereignisse[0]["uebergabe"], "status": "uebergeben", "auftrag": "a7"}
    assert angelegt == [("Uhr bauen", "Baut die Uhr.", "/tmp/projekt", {"bruecke": {"session": SID}, "ticket": None})]
    assert cfg.load_settings()["team"]["aktiv"]
    # nach dem Neuladen: übergeben, und der Assistent bekommt keine Meldung mehr
    assert client.get(f"/api/firma/uebergaben/{SID}").json()["uebergaben"][0]["status"] == "uebergeben"
    assert teamchat.nicht_angekommen(SID) == ""
    # Doppelklick legt keinen zweiten Auftrag an
    assert client.post(f"/api/firma/uebergaben/{SID}/{eid}").status_code == 409
    assert len(angelegt) == 1
