"""Team-Modus: ein ganzer Auftrag durch Dispatcher, Züge und Bus — ohne Modell.

Statt `claude` läuft tests/fake_claude.py, das stream-json spricht und den Bus
wie ein Mitarbeiter aufruft. Der Server läuft dazu wirklich (uvicorn in einem
Thread), denn der Bus ist ein HTTP-Aufruf vom Unterprozess zurück.
"""
import json
import socket
import stat
import sys
import threading
import time
import urllib.request
from pathlib import Path

import pytest
import uvicorn

ROOT = Path(__file__).resolve().parent.parent
FAKE = Path(__file__).with_name("fake_claude.py")


def _frei() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture()
def firma(tmp_path, monkeypatch):
    from server import config as cfg
    from server import core, runs
    from server.team import agents as ag
    from server.team import anleitungen as anl
    from server.team import auftraege as auf
    from server.team import engine, lauf

    monkeypatch.setattr(ag, "FIRMA_DIR", tmp_path / "firma")
    monkeypatch.setattr(ag, "AGENTS_DIR", tmp_path / "firma" / "agents")
    monkeypatch.setattr(ag, "USER_FILE", tmp_path / "USER.md")
    monkeypatch.setattr(anl, "DIR", tmp_path / "firma" / "anleitungen")
    monkeypatch.setattr(auf, "AUFTRAEGE_DIR", tmp_path / "firma" / "auftraege")
    auf._UEBERSICHT.clear()
    from server import tickets as tickmod
    monkeypatch.setattr(tickmod, "TICKETS_DIR", tmp_path / "tickets")
    tickmod._CACHE.clear()
    (tmp_path / "settings.json").write_text(json.dumps(
        {"lang": "de", "names": {"user": "Anna", "assistant": "Momo"}, "team": {"aktiv": True}}))
    monkeypatch.setattr(cfg, "SETTINGS_FILE", tmp_path / "settings.json")

    # Das falsche claude als ausführbare Datei
    bin_ = tmp_path / "claude"
    bin_.write_text(f"#!/bin/sh\nexec {sys.executable} {FAKE} \"$@\"\n")
    bin_.chmod(bin_.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setattr(lauf, "claude_bin", lambda: str(bin_))
    monkeypatch.setattr(runs, "claude_bin", lambda: str(bin_))
    monkeypatch.setattr(runs, "maybe_notify", lambda run: None)
    monkeypatch.setattr(engine, "tg_send", lambda text: None)

    # Arbeitsordner der Mitarbeiter: der Workspace des Tests
    monkeypatch.setattr(core, "WORKSPACE", str(tmp_path))
    monkeypatch.setattr(engine, "WORKSPACE", str(tmp_path))
    import server.routes.team as rt
    monkeypatch.setattr(rt, "WORKSPACE", str(tmp_path))
    from server.team import bus as busmod
    monkeypatch.setattr(busmod, "WORKSPACE", str(tmp_path))

    port = _frei()
    core._SERVER["base"] = f"http://127.0.0.1:{port}"
    import app as appmod
    server = uvicorn.Server(uvicorn.Config(appmod.app, host="127.0.0.1", port=port,
                                           log_level="error", lifespan="off"))
    t = threading.Thread(target=server.run, daemon=True)
    t.start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.05)
    assert server.started
    base = f"http://127.0.0.1:{port}"
    ag.list_agents(str(tmp_path))                       # Vorlagen ausrollen
    yield base
    server.should_exit = True
    t.join(timeout=10)
    core._SERVER["base"] = ""
    engine._DISPATCHER["loop"] = None
    engine.PAUSIERT = False
    engine.BUS_TOKENS.clear()


def api(base, pfad, daten=None, methode=None):
    req = urllib.request.Request(
        base + pfad, data=None if daten is None else json.dumps(daten).encode(),
        headers={"Content-Type": "application/json"}, method=methode or ("POST" if daten is not None else "GET"))
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r)


def warte(base, tid, bis, sek=40):
    ende = time.time() + sek
    while time.time() < ende:
        t = api(base, f"/api/team/auftraege/{tid}")["ticket"]
        if t["status"] in bis:
            return t
        time.sleep(0.3)
    raise AssertionError(f"Auftrag steht auf {t['status']}, erwartet {bis}")


def neuer_auftrag(base, brief):
    return api(base, "/api/team/auftraege", {"brief": brief, "titel": "Test"})["ticket"]["id"]


def pfad(verlauf):
    return [(e["von"], e["an"], e["art"]) for e in verlauf if e.get("an") and e["art"] != "zugestellt"]


def test_kleinauftrag_geht_direkt_an_den_nutzer(firma):
    tid = neuer_auftrag(firma, "[klein] Bau das Ding")
    t = warte(firma, tid, ("fertig",))
    d = api(firma, f"/api/team/auftraege/{tid}")
    assert pfad(d["verlauf"])[:3] == [("kevin", "chef", "auftrag"), ("chef", "entwickler", "auftrag"),
                                     ("entwickler", "kevin", "ergebnis")]
    assert t["ergebnis"] == "gebaut"
    assert t["verbraucht"]["hops"] == 2                      # zwei Züge, kein Durchreicher
    assert t["verbraucht"]["cost"] == pytest.approx(0.02)
    assert t["verbraucht"]["je_agent"] == {"chef": 0.01, "entwickler": 0.01}
    assert t["verbraucht"]["cache_read"] == 1800
    # ein frisch angelegter Auftrag gilt nie als "beim Neustart unterbrochen"
    assert not [e for e in d["verlauf"] if e["art"] == "system"]


def test_normaler_auftrag_geht_ueber_den_pruefer_zurueck_zum_chef(firma):
    tid = neuer_auftrag(firma, "[kette] Bau das Ding gründlich")
    t = warte(firma, tid, ("fertig",))
    d = api(firma, f"/api/team/auftraege/{tid}")
    assert pfad(d["verlauf"]) == [
        ("kevin", "chef", "auftrag"), ("chef", "entwickler", "auftrag"),
        ("entwickler", "chef", "ergebnis"), ("chef", "pruefer", "auftrag"),
        ("pruefer", "chef", "ergebnis"), ("chef", "kevin", "ergebnis")]
    assert t["verbraucht"]["hops"] == 5
    # die Beteiligten haben den Auftrag in ihrer Akte
    from server.team import agents as ag
    assert "Test" in ag.historie_text("entwickler")


def test_rueckfrage_haelt_an_und_antwort_setzt_fort(firma):
    tid = neuer_auftrag(firma, "[rueckfrage] Mach etwas")
    t = warte(firma, tid, ("wartet_auf_kevin",))
    assert t["eskalation"]["frage"] == "Rot oder blau?" and t["eskalation"]["an"] == "entwickler"
    api(firma, f"/api/team/auftraege/{tid}/antwort", {"aktion": "weiter", "text": "Blau."})
    t = warte(firma, tid, ("fertig",))
    assert t["ergebnis"].startswith("gebaut")


def test_zug_ohne_bus_aufruf_holt_den_nutzer(firma):
    tid = neuer_auftrag(firma, "[still] Mach etwas")
    t = warte(firma, tid, ("wartet_auf_kevin",))
    assert t["eskalation"]["bremse"] == "stiller_zug"


def test_not_aus_stellt_nichts_zu_und_loesen_macht_weiter(firma):
    assert api(firma, "/api/team/pause", {"pause": True})["pausiert"] is True
    tid = neuer_auftrag(firma, "[klein] Bau das Ding")
    time.sleep(1.5)
    assert api(firma, f"/api/team/auftraege/{tid}")["ticket"]["status"] == "laeuft"
    assert api(firma, f"/api/team/auftraege/{tid}")["ticket"]["verbraucht"]["hops"] == 0
    api(firma, "/api/team/pause", {"pause": False})
    warte(firma, tid, ("fertig",), sek=40)


def test_abbrechen_beendet_den_laufenden_zug(firma):
    tid = neuer_auftrag(firma, "[langsam] Mach etwas")
    for _ in range(60):
        t = api(firma, f"/api/team/auftraege/{tid}")["ticket"]
        if (t.get("in_arbeit") or {}).get("run_id") and t["verbraucht"]["hops"] >= 2:
            break
        time.sleep(0.2)
    api(firma, f"/api/team/auftraege/{tid}/antwort", {"aktion": "abbrechen"})
    time.sleep(1.0)
    t = api(firma, f"/api/team/auftraege/{tid}")["ticket"]
    assert t["status"] == "abgebrochen"


def test_team_aus_gibt_404(firma, tmp_path):
    (tmp_path / "settings.json").write_text(json.dumps({"team": {"aktiv": False}}))
    with pytest.raises(urllib.error.HTTPError) as e:
        api(firma, "/api/team/agents")
    assert e.value.code == 404


def test_belegschaft_und_organigramm(firma):
    d = api(firma, "/api/team/agents")
    assert [a["slug"] for a in d["agents"]][0] == "chef"
    assert d["agents"][0]["name"] == "Momo"
    assert d["org"]["roots"][0]["slug"] == "chef"


def test_bus_mit_unbekanntem_token_wird_abgewiesen(firma):
    r = api(firma, "/api/team/bus", {"tool": "liefern", "args": {"ergebnis": "x"}, "token": "falsch"})
    assert r["error"] is True and "beendet" in r["text"]


def test_ticket_geht_an_die_firma_und_wird_mit_dem_auftrag_erledigt(firma, tmp_path):
    from server import tickets as tickmod
    sid = "abcd1234-0000-0000-0000-0000000000f1"
    tickmod.nachricht(sid, "u1", "[klein] Bau das Ding", str(tmp_path))
    tickmod.nachricht(sid, "u2", "und bitte in Blau")                 # Korrektur im selben Ticket
    r = api(firma, "/api/team/auftraege/aus-ticket", {"session": sid, "nr": 1})
    tid = r["ticket"]["id"]
    assert r["ticket"]["bruecke"] == {"session": sid, "nr": 1}
    assert "Später dazu gesagt" in r["ticket"]["brief"] and "in Blau" in r["ticket"]["brief"]
    assert tickmod.laden(sid)["tickets"][0]["auftrag"] == tid
    # ein zweites Mal geht nicht
    with pytest.raises(urllib.error.HTTPError) as e:
        api(firma, "/api/team/auftraege/aus-ticket", {"session": sid, "nr": 1})
    assert e.value.code == 409
    warte(firma, tid, ("fertig",))
    t = tickmod.laden(sid)["tickets"][0]
    assert t["status"] == "erledigt"
    # die Ticket-Zeile zeigt dem Assistenten den Stand
    assert "(Firma: fertig)" in tickmod.hinweis(sid)


def test_ticketbus_firma_werkzeuge(firma, tmp_path):
    from server import tickets as tickmod
    from server.routes import tickets as rt
    sid = "abcd1234-0000-0000-0000-0000000000f2"
    tickmod.nachricht(sid, "u1", "[klein] Bau das Ding", str(tmp_path))

    class Lauf:
        session_id, cwd = sid, str(tmp_path)

    antwort = rt._firma("firma_auftrag", {"titel": "Ding", "brief": "[klein] Bau das Ding"}, Lauf)
    assert "bei der Firma" in antwort
    assert "→" in rt._firma("firma_stand", {}, Lauf)
    assert rt._firma("firma_auftrag", {"titel": "x", "brief": ""}, Lauf) == "leer"
