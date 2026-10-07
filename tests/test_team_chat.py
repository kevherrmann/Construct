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


def test_regeln_fragen_vor_der_uebergabe():
    text = teamchat.regeln()
    assert "fragst, ob du sie an die Firma geben darfst" in text and "Anna" in text
    assert "[[firma: Kurztitel]]" in text


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
