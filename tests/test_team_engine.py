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
    monkeypatch.setattr(ag, "ERGAENZUNGEN_FILE", tmp_path / "firma" / "USER-ergaenzungen.md")
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
    assert pfad(d["verlauf"])[:3] == [("kevin", "chef", "auftrag"), ("chef", "luna", "auftrag"),
                                     ("luna", "kevin", "ergebnis")]
    assert t["ergebnis"] == "gebaut"
    assert t["verbraucht"]["hops"] == 2                      # zwei Züge, kein Durchreicher
    assert t["verbraucht"]["cost"] == pytest.approx(0.02)
    assert t["verbraucht"]["cache_read"] == 1800
    # ein frisch angelegter Auftrag gilt nie als "beim Neustart unterbrochen"
    assert not [e for e in d["verlauf"] if e["art"] == "system"]


def test_normaler_auftrag_geht_ueber_den_pruefer_zurueck_zum_chef(firma):
    tid = neuer_auftrag(firma, "[kette] Bau das Ding gründlich")
    t = warte(firma, tid, ("fertig",))
    d = api(firma, f"/api/team/auftraege/{tid}")
    assert pfad(d["verlauf"]) == [
        ("kevin", "chef", "auftrag"), ("chef", "luna", "auftrag"),
        ("luna", "chef", "ergebnis"), ("chef", "miranda", "auftrag"),
        ("miranda", "chef", "ergebnis"), ("chef", "kevin", "ergebnis")]
    assert t["verbraucht"]["hops"] == 5
    # die Beteiligten haben den Auftrag in ihrer Akte
    from server.team import agents as ag
    assert "Test" in ag.historie_text("luna")


def test_rueckfrage_haelt_an_und_antwort_setzt_fort(firma):
    tid = neuer_auftrag(firma, "[rueckfrage] Mach etwas")
    t = warte(firma, tid, ("wartet_auf_kevin",))
    assert t["eskalation"]["frage"] == "Rot oder blau?" and t["eskalation"]["an"] == "luna"
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
    zeile = tickmod.hinweis(sid)
    assert f"(Firma {tid}: fertig)" in zeile


def test_marker_firma_am_zugende_gibt_das_ticket_an_die_firma(firma, tmp_path, monkeypatch):
    from server import runs
    from server import tickets as tickmod
    from server.team import engine
    sid = "abcd1234-0000-0000-0000-0000000000f2"
    tickmod.nachricht(sid, "u1", "[klein] Bau das Ding", str(tmp_path))

    class Lauf:
        session_id, letzte_uuid, marke_ab = sid, "u1", 0
        last_text = "Ich gebe das weiter.\n\n[[ticket firma]]"
        events = []

        def emit(self, ev):
            self.events.append(ev)

    angelegt = []
    monkeypatch.setattr(engine, "starten", lambda: None)
    monkeypatch.setattr(engine, "auftrag_aus_ticket", lambda s_, nr: angelegt.append((s_, nr)) or {})
    lauf = Lauf()
    runs._tickets_marken(lauf)
    assert angelegt == [(sid, 1)] and lauf.marke_ab == len(lauf.last_text)
    assert lauf.events == [{"type": "tickets"}]
    runs._tickets_marken(lauf)                    # zweites Zugende ohne neuen Text: nichts doppelt
    assert angelegt == [(sid, 1)]


def test_ticket_darf_nach_abbruch_erneut_an_die_firma(firma, tmp_path):
    from server import tickets as tickmod
    sid = "abcd1234-0000-0000-0000-0000000000f3"
    tickmod.nachricht(sid, "u1", "[klein] Bau das Ding", str(tmp_path))
    erst = api(firma, "/api/team/auftraege/aus-ticket", {"session": sid, "nr": 1})["ticket"]["id"]
    warte(firma, erst, ("fertig",))
    tickmod.aendern(sid, 1, status="offen")
    zweit = api(firma, "/api/team/auftraege/aus-ticket", {"session": sid, "nr": 1})["ticket"]["id"]
    assert zweit != erst                           # ein fertiger Auftrag blockiert nicht
    warte(firma, zweit, ("fertig",))


def test_abbrechen_eines_abgeschlossenen_auftrags_wird_abgewiesen(firma):
    tid = neuer_auftrag(firma, "[klein] Bau das Ding")
    warte(firma, tid, ("fertig",))
    with pytest.raises(urllib.error.HTTPError) as e:
        api(firma, f"/api/team/auftraege/{tid}/antwort", {"aktion": "abbrechen"})
    assert e.value.code == 400
    assert api(firma, f"/api/team/auftraege/{tid}")["ticket"]["status"] == "fertig"


def test_abbruch_nennt_den_nutzer_nicht_kevin(firma):
    tid = neuer_auftrag(firma, "[rueckfrage] Mach etwas")
    warte(firma, tid, ("wartet_auf_kevin",))
    api(firma, f"/api/team/auftraege/{tid}/antwort", {"aktion": "abbrechen"})
    texte = [e.get("text", "") for e in api(firma, f"/api/team/auftraege/{tid}")["verlauf"]
             if e["art"] == "system"]
    assert any("Anna" in x for x in texte) and not any("Kevin" in x for x in texte)


def test_antwort_an_einen_unbrauchbaren_empfaenger_wird_abgewiesen(firma):
    tid = neuer_auftrag(firma, "[rueckfrage] Mach etwas")
    warte(firma, tid, ("wartet_auf_kevin",))
    with pytest.raises(urllib.error.HTTPError) as e:
        api(firma, f"/api/team/auftraege/{tid}/antwort", {"aktion": "weiter", "an": "../.."})
    assert e.value.code == 400


def test_loeschen_beendet_den_laufenden_zug(firma):
    from server.runs import RUNS
    tid = neuer_auftrag(firma, "[langsam] Mach etwas")
    for _ in range(60):
        t = api(firma, f"/api/team/auftraege/{tid}")["ticket"]
        rid = (t.get("in_arbeit") or {}).get("run_id")
        if rid and t["verbraucht"]["hops"] >= 2:
            break
        time.sleep(0.2)
    api(firma, f"/api/team/auftraege/{tid}", methode="DELETE")
    for _ in range(25):
        if RUNS[rid].done:
            break
        time.sleep(0.1)
    assert RUNS[rid].done


def test_wartender_zug_startet_nicht_mehr_nach_dem_ausschalten(firma, tmp_path):
    from server.team import auftraege as auf
    api(firma, "/api/team/pause", {"pause": True})
    tid = neuer_auftrag(firma, "[klein] Bau das Ding")
    (tmp_path / "settings.json").write_text(json.dumps({"lang": "de", "team": {"aktiv": False}}))
    from server.team import engine
    engine.PAUSIERT = False                       # die Route dafür ist jetzt aus
    ende = time.time() + 15
    while time.time() < ende and auf.laden(tid)["status"] == "laeuft":
        time.sleep(0.3)
    t = auf.laden(tid)
    assert t["status"] == "wartet_auf_kevin" and t["eskalation"]["bremse"] == "gestoppt"
    assert t["sessions"] == {}                    # kein Zug ist gelaufen


@pytest.mark.parametrize("pfad,body", [("/api/team/auftraege", b"kaputt"), ("/api/team/auftraege", b"[]"),
                                       ("/api/team/auftraege/aus-ticket", b'{"session": "abcd1234", "nr": [1]}')])
def test_kaputter_body_ist_kein_serverfehler(firma, pfad, body):
    req = urllib.request.Request(firma + pfad, data=body, headers={"Content-Type": "application/json"})
    with pytest.raises(urllib.error.HTTPError) as e:
        urllib.request.urlopen(req, timeout=10)
    assert e.value.code == 400


def test_bus_ohne_objekt_wird_abgewiesen(firma):
    req = urllib.request.Request(firma + "/api/team/bus", data=b"[]", headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as r:
        assert json.load(r)["error"] is True


def test_bus_token_steht_nicht_in_der_kommandozeile(firma, tmp_path, monkeypatch):
    import os
    from server.team import engine
    gesehen = []
    echt = engine.build_claude_cmd

    def mitschreiben(**kw):
        cmd = echt(**kw)
        datei = Path(kw["mcp_config"])
        gesehen.append((cmd, datei, stat.S_IMODE(os.stat(datei).st_mode), datei.read_text()))
        return cmd
    monkeypatch.setattr(engine, "build_claude_cmd", mitschreiben)
    tid = neuer_auftrag(firma, "[klein] Bau das Ding")
    warte(firma, tid, ("fertig",))
    assert gesehen
    for cmd, datei, modus, inhalt in gesehen:
        token = json.loads(inhalt)["mcpServers"]["firma"]["env"]["FIRMA_TOKEN"]
        assert token and not any(token in a for a in cmd)     # nicht in `ps`
        if os.name != "nt":
            assert modus == 0o600
    time.sleep(0.5)                                          # letzter Zug räumt ab
    assert not list((tmp_path / "firma" / "agents").glob("*/.bus-*.json"))


def test_stream_fuer_unbekannten_auftrag_ist_404(firma):
    from server.team import engine
    import urllib.error
    with pytest.raises(urllib.error.HTTPError) as e:
        urllib.request.urlopen(firma + "/api/team/auftraege/deadbeef/stream", timeout=5)
    assert e.value.code == 404 and "deadbeef" not in engine.FEEDS


def test_werkzeuge_der_akte_sind_eine_sperre_nicht_nur_freigabe(firma, monkeypatch):
    # --allowedTools gibt nur frei; unter auto/bypassPermissions lief sonst Bash bei
    # der Chefin und WebFetch bei Janus. Gesperrt wird mit --tools.
    from server.team import engine
    kommandos = []
    echt = engine.build_claude_cmd

    def mitschreiben(**kw):
        cmd = echt(**kw)
        kommandos.append(cmd)
        return cmd
    monkeypatch.setattr(engine, "build_claude_cmd", mitschreiben)
    tid = neuer_auftrag(firma, "[klein] Bau das Ding")
    warte(firma, tid, ("fertig",))
    assert len(kommandos) == 2                        # Chefin und Luna
    for cmd in kommandos:
        assert "--tools" in cmd
        tools = cmd[cmd.index("--tools") + 1].split(",")
        assert not ("Bash" in tools and {"WebSearch", "WebFetch"} & set(tools)), tools
        assert not any(t.startswith("mcp__") for t in tools)   # der Bus bleibt erreichbar
    chef = kommandos[0][kommandos[0].index("--tools") + 1].split(",")
    assert "Bash" not in chef and "WebSearch" in chef      # die Chefin recherchiert, ohne Shell


def test_leere_werkzeugliste_heisst_keine_eingebauten():
    from server.team.lauf import build_claude_cmd
    cmd = build_claude_cmd(mode="auto", tools=[])
    assert cmd[cmd.index("--tools") + 1] == ""
    assert "--tools" not in build_claude_cmd(mode="auto")


# ---------- A4: was jemand sagt, steht auf JEDEM Ausgang im Protokoll ----------
def gesagt(base, tid, von="luna"):
    return [e["text"] for e in api(base, f"/api/team/auftraege/{tid}")["verlauf"]
            if e["art"] == "gesagt" and e["von"] == von]


def warte_auf_lauf(base, tid, slug="luna"):
    for _ in range(100):
        t = api(base, f"/api/team/auftraege/{tid}")["ticket"]
        st = api(base, "/api/team/state")["aktiv"]
        z = next((x for x in st if x["agent"] == slug and x["ticket"] == tid), None)
        if z:
            return z["run"]
        time.sleep(0.1)
    raise AssertionError(f"{slug} kam nie dran ({t['status']})")


def test_gestoppter_zug_hinterlaesst_sein_gesagtes(firma):
    tid = neuer_auftrag(firma, "[langsam] Mach etwas")
    run = warte_auf_lauf(firma, tid)
    time.sleep(1.0)                                   # Text ist raus, er schläft noch
    api(firma, f"/api/stop/{run}", {})
    t = warte(firma, tid, ("wartet_auf_kevin",))
    assert t["eskalation"]["bremse"] == "gestoppt"
    assert gesagt(firma, tid) == ["luna liest (auftrag)"]


def test_haengender_zug_hinterlaesst_sein_gesagtes(firma, monkeypatch):
    import asyncio
    from server.team import engine

    async def haengt(run, stille_max):
        await asyncio.sleep(1.0)
        raise asyncio.TimeoutError
    monkeypatch.setattr(engine, "warte_auf_zug", haengt)
    tid = neuer_auftrag(firma, "[langsam] Mach etwas")
    t = warte(firma, tid, ("wartet_auf_kevin",))
    assert t["eskalation"]["bremse"] == "stille"
    # die Chefin hing schon im ersten Zug: auch ihr Text steht da
    assert gesagt(firma, tid, "chef") == ["chef liest (auftrag)"]


def test_zug_mit_fehler_hinterlaesst_sein_gesagtes(firma):
    tid = neuer_auftrag(firma, "[fehler] Mach etwas")
    t = warte(firma, tid, ("wartet_auf_kevin",))
    assert t["eskalation"]["bremse"] == "fehler"
    assert gesagt(firma, tid) == ["luna liest (auftrag)"]


def test_ueberlanges_gesagtes_behaelt_das_ende(firma):
    tid = neuer_auftrag(firma, "[lang] Mach etwas")
    warte(firma, tid, ("fertig",))
    [text] = gesagt(firma, tid)
    assert text.startswith("luna liest (auftrag)") and text.endswith("ENDE-DER-BLASE")
    assert "[…]" in text and len(text) <= 20000
