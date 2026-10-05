"""Tickets: Zuordnung innerhalb einer Session (server/tickets.py)."""
import json

import pytest

from server import tickets as tk

SID = "abcd1234-0000-0000-0000-000000000001"


@pytest.fixture(autouse=True)
def ordner(tmp_path, monkeypatch):
    from server import config as cfg
    monkeypatch.setattr(tk, "TICKETS_DIR", tmp_path / "tickets")
    # Texte hängen an der Sprache der Installation: die Tests sollen nicht davon abhängen.
    (tmp_path / "settings.json").write_text('{"lang": "de", "names": {"user": "Kevin"}}')
    monkeypatch.setattr(cfg, "SETTINGS_FILE", tmp_path / "settings.json")
    tk._CACHE.clear()


def ids(d, nr):
    return [m["id"] for t in d["tickets"] if t["nr"] == nr for m in t["nachrichten"]]


def test_erste_nachricht_legt_ein_ticket_an():
    r = tk.nachricht(SID, "u1", "Bau die Kachel für die Tickets\n\n[Vom Nutzer hochgeladenes Bild: /x.png]")
    assert r == {"nr": 1, "titel": "Bau die Kachel für die Tickets", "neu": True}
    d = tk.laden(SID)
    assert d["aktuell"] == 1 and ids(d, 1) == ["u1"]
    # Dateihinweise gehören nicht in den Auszug
    assert d["tickets"][0]["nachrichten"][0]["text"] == "Bau die Kachel für die Tickets"


def test_ohne_zutun_gehoert_alles_zum_aktuellen_ticket():
    tk.nachricht(SID, "u1", "Aufgabe")
    tk.nachricht(SID, "u2", "Korrektur dazu")
    assert ids(tk.laden(SID), 1) == ["u1", "u2"]


def test_nachricht_ist_idempotent():
    tk.nachricht(SID, "u1", "Aufgabe")
    tk.nachricht(SID, "u1", "Aufgabe")
    assert ids(tk.laden(SID), 1) == ["u1"]


def test_kevins_beispiel_vier_nachrichten_zwei_tickets():
    """Aufgabe, Korrektur, neue Aufgabe, Korrektur zur ersten = 2 Tickets."""
    tk.nachricht(SID, "n1", "Aufgabe A")
    tk.nachricht(SID, "n2", "Korrektur zu A")
    tk.nachricht(SID, "n3", "Aufgabe B")
    tk.werkzeug_neu(SID, "n3", "Aufgabe B")
    tk.nachricht(SID, "n4", "Noch eine Korrektur zu A")
    assert tk.werkzeug_zuordnen(SID, "n4", 1) == "#1"
    d = tk.laden(SID)
    assert len(d["tickets"]) == 2
    assert ids(d, 1) == ["n1", "n2", "n4"]
    assert ids(d, 2) == ["n3"]
    assert d["aktuell"] == 1
    # Die Korrektur hat das erledigte Ticket wieder geöffnet
    assert d["tickets"][0]["status"] == "offen"


def test_nachricht_auf_erledigtes_ticket_oeffnet_es_wieder():
    tk.nachricht(SID, "u1", "A")
    tk.aendern(SID, 1, status="erledigt")
    assert tk.laden(SID)["tickets"][0]["status"] == "erledigt"
    tk.nachricht(SID, "u2", "doch noch was")
    t = tk.laden(SID)["tickets"][0]
    assert t["status"] == "offen" and t["erledigt_am"] is None


def test_ticket_neu_benennt_das_vom_server_angelegte_um():
    tk.nachricht(SID, "u1", "irgendwas langes und unhandliches")
    assert tk.werkzeug_neu(SID, "u1", "Kurzer Titel") == "#1"
    d = tk.laden(SID)
    assert len(d["tickets"]) == 1 and d["tickets"][0]["titel"] == "Kurzer Titel"


def test_ticket_neu_holt_die_nachricht_aus_dem_alten():
    tk.nachricht(SID, "u1", "A")
    tk.nachricht(SID, "u2", "B, etwas ganz anderes")
    assert tk.werkzeug_neu(SID, "u2", "B") == "#2"
    d = tk.laden(SID)
    assert ids(d, 1) == ["u1"] and ids(d, 2) == ["u2"] and d["aktuell"] == 2


def test_kevins_wahl_geht_vor_dem_assistenten():
    tk.nachricht(SID, "u1", "A")
    tk.schnitt(SID, "Mein Schnitt")
    tk.nachricht(SID, "u2", "Neue Sache")
    with pytest.raises(tk.Abgelehnt):
        tk.werkzeug_neu(SID, "u2", "Etwas anderes")
    with pytest.raises(tk.Abgelehnt):
        tk.werkzeug_zuordnen(SID, "u2", 1)
    d = tk.laden(SID)
    assert ids(d, 2) == ["u2"] and d["tickets"][1]["titel"] == "Mein Schnitt"
    # Die Sperre gilt nur für diese eine Nachricht
    assert tk.nachricht(SID, "u3", "weiter")["nr"] == 2
    assert tk.werkzeug_neu(SID, "u3", "Drittes") == "#3"


def test_zuordnen_unbekanntes_ticket_aendert_nichts():
    tk.nachricht(SID, "u1", "A")
    with pytest.raises(tk.Abgelehnt):
        tk.werkzeug_zuordnen(SID, "u1", 9)
    assert ids(tk.laden(SID), 1) == ["u1"]


def test_leeres_server_ticket_verschwindet_wenn_die_nachricht_umzieht():
    tk.nachricht(SID, "u1", "A")
    tk.werkzeug_neu(SID, "u1", "Eigenes A")      # Kevin-lose Benennung, Ticket 1
    tk.nachricht(SID, "u2", "B")
    tk.werkzeug_neu(SID, "u2", "B")               # Ticket 2
    tk.werkzeug_zuordnen(SID, "u2", 1)
    d = tk.laden(SID)
    assert ids(d, 1) == ["u1", "u2"]
    assert [t["nr"] for t in d["tickets"]] == [1, 2]   # vom Assistenten angelegt: bleibt


def test_schnitt_mit_vorgabe_fuer_neue_session():
    r = tk.nachricht(SID, "u1", "Text", "/home/k/p", vorgabe={"titel": "Gleich benannt"})
    assert r["titel"] == "Gleich benannt"
    d = tk.laden(SID)
    assert d["cwd"] == "/home/k/p" and d["project"] == "-home-k-p"


def test_ab_hier_teilt_ein_ticket():
    for u in ("u1", "u2", "u3"):
        tk.nachricht(SID, u, f"Nachricht {u}")
    d = tk.ab_hier(SID, "u2", "Zweiter Teil")
    assert ids(d, 1) == ["u1"] and ids(d, 2) == ["u2", "u3"]
    # die nächste Nachricht geht dahin, wo sie vorher hingegangen wäre: ins aktuelle
    assert d["aktuell"] == 2


def test_umhaengen_und_zusammenfuehren():
    tk.nachricht(SID, "u1", "A")
    tk.schnitt(SID, "B")
    tk.nachricht(SID, "u2", "B1")
    d = tk.umhaengen(SID, ["u2"], 1)
    assert ids(d, 1) == ["u1", "u2"]
    d = tk.zusammenfuehren(SID, 2, 1)
    assert [t["nr"] for t in d["tickets"]] == [1] and d["aktuell"] == 1


def test_aendern_titel_und_status():
    tk.nachricht(SID, "u1", "A")
    d = tk.aendern(SID, 1, titel="  Neuer   Name ", status="erledigt")
    t = d["tickets"][0]
    assert t["titel"] == "Neuer Name" and t["status"] == "erledigt" and t["erledigt_am"]
    assert tk.aendern(SID, 1, status="offen")["tickets"][0]["erledigt_am"] is None


def test_abzweigen_nimmt_nur_die_behaltenen_nachrichten_mit():
    NEU = "abcd1234-0000-0000-0000-000000000002"
    tk.nachricht(SID, "u1", "A")
    tk.schnitt(SID, "B")
    tk.nachricht(SID, "u2", "B1")
    tk.abzweigen(SID, NEU, {"u1"})
    d = tk.laden(NEU)
    assert ids(d, 1) == ["u1"] and [t["nr"] for t in d["tickets"]] == [1]
    assert d["session"] == NEU
    # Das Original bleibt wie es war
    assert ids(tk.laden(SID), 2) == ["u2"]


def test_kaputte_datei_zerlegt_nichts(tmp_path):
    (tk.TICKETS_DIR).mkdir(parents=True)
    (tk.TICKETS_DIR / f"{SID}.json").write_text("{kaputt")
    assert tk.laden(SID)["tickets"] == []
    (tk.TICKETS_DIR / f"{SID}.json").write_text(json.dumps(
        {"tickets": [{"nr": "x"}, {"nr": 2, "titel": "ok", "status": "komisch",
                                   "nachrichten": ["u1", {"id": "u1"}, 5]}], "aktuell": 7}))
    d = tk.laden(SID)
    assert [t["nr"] for t in d["tickets"]] == [2]
    assert d["tickets"][0]["status"] == "offen" and ids(d, 2) == ["u1"] and d["aktuell"] is None


def test_ungueltige_session_id():
    with pytest.raises(ValueError):
        tk.laden("../etc/passwd")


def test_uebersicht_gruppiert_nach_tag_und_projekt():
    tk.nachricht(SID, "u1", "A", "/home/k/construct")
    d = tk.laden(SID)
    d["tickets"][0]["nachrichten"][0]["ts"] = "2026-10-05T09:00:00"
    d["tickets"][0]["erstellt"] = "2026-10-05T09:00:00"
    tk.speichern(d)
    u = tk.uebersicht({SID: "Mein Chat"})
    assert [t["tag"] for t in u["tage"]] == ["2026-10-05"]
    p = u["tage"][0]["projekte"][0]
    assert p["name"] == "construct" and p["offen"] == 1 and p["erledigt"] == 0
    assert p["tickets"][0]["session_titel"] == "Mein Chat"


def test_titel_kuerzt_am_wortende():
    s = tk.titel_aus("Dies ist eine sehr lange Aufgabe, die weit über sechzig Zeichen hinausgeht und weiter")
    assert s.endswith(" …") and len(s) <= 64


# ---------- im Lauf und über die API ----------
STUB = r'''
import json, sys
sys.stdin.readline()
def out(ev):
    sys.stdout.write(json.dumps(ev) + "\n"); sys.stdout.flush()
out({"type": "system", "subtype": "init", "session_id": "abcd1234-0000-0000-0000-0000000000aa"})
out({"type": "user", "uuid": "u-erste", "session_id": "x", "isReplay": True,
     "message": {"role": "user", "content": [{"type": "text", "text": "Mach die Tafel\n\n[Tickets: noch keins]"}]}})
out({"type": "user", "uuid": "u-tool", "message": {"role": "user", "content": [
     {"type": "tool_result", "tool_use_id": "t", "content": "ok"}]}})
out({"type": "user", "uuid": "u-bg", "message": {"role": "user", "content": [
     {"type": "text", "text": "<task-notification>fertig</task-notification>"}]}})
out({"type": "result", "subtype": "success", "session_id": "abcd1234-0000-0000-0000-0000000000aa", "usage": {}})
'''


def _lauf(tmp_path, monkeypatch, **kw):
    import asyncio
    import sys

    from server import runs
    stub = tmp_path / "claude_stub.py"
    stub.write_text(STUB)
    monkeypatch.setattr(runs, "claude_bin", lambda: sys.executable)
    monkeypatch.setattr(runs, "load_persona", lambda: "")
    monkeypatch.setattr(runs, "maybe_notify", lambda run: None)

    async def los():
        run = runs.Run("t-tickets", str(tmp_path), None, "", initial_prompt="hallo", **kw)
        await runs.run_claude(run, [sys.executable, str(stub)])
        return run
    return asyncio.run(los())


def test_lauf_ordnet_nur_echte_nachrichten_zu(tmp_path, monkeypatch):
    run = _lauf(tmp_path, monkeypatch, tickets=True)
    d = tk.laden("abcd1234-0000-0000-0000-0000000000aa")
    assert ids(d, 1) == ["u-erste"]                 # kein Tool-Ergebnis, keine Systemmeldung
    assert d["tickets"][0]["nachrichten"][0]["text"] == "Mach die Tafel"
    assert d["cwd"] == str(tmp_path)
    assert run.letzte_uuid == "u-erste"


def test_lauf_ohne_tickets_schreibt_nichts(tmp_path, monkeypatch):
    _lauf(tmp_path, monkeypatch, tickets=False)
    assert not tk.TICKETS_DIR.exists()


def test_api_roundtrip(client):
    sid = "abcd1234-0000-0000-0000-0000000000bb"
    tk.nachricht(sid, "u1", "A", "/home/k/p")
    r = client.get(f"/api/tickets/{sid}").json()
    assert r["tickets"][0]["titel"] == "A"
    r = client.post(f"/api/tickets/{sid}/schnitt", json={"titel": "B"}).json()
    assert r["aktuell"] == 2 and r["gesperrt"] is True
    r = client.post(f"/api/tickets/{sid}/waehlen", json={"nr": 1}).json()
    assert r["aktuell"] == 1
    assert client.post(f"/api/tickets/{sid}/waehlen", json={"nr": 9}).status_code == 404
    r = client.post(f"/api/tickets/{sid}/1", json={"status": "erledigt"}).json()
    assert r["tickets"][0]["status"] == "erledigt"
    r = client.post(f"/api/tickets/{sid}/ab-hier", json={"uuid": "u1", "titel": "Neu"}).json()
    assert [t["titel"] for t in r["tickets"]] == ["B", "Neu"]
    assert client.post(f"/api/tickets/{sid}/umhaengen", json={"uuids": ["u1"], "nr": 2}).status_code == 200
    assert client.get("/api/tickets").json()["tage"]
    assert client.get("/api/tickets/..%2Fx").status_code in (400, 404)
    assert client.delete(f"/api/tickets/{sid}/2").status_code == 200


def test_neues_ticket_schliesst_das_vorige():
    tk.nachricht(SID, "u1", "A")
    tk.werkzeug_neu(SID, "u1", "A")
    tk.nachricht(SID, "u2", "B")
    tk.werkzeug_neu(SID, "u2", "B")
    d = tk.laden(SID)
    assert [t["status"] for t in d["tickets"]] == ["erledigt", "offen"]
    assert d["tickets"][0]["erledigt_am"]
    # eine Korrektur zu A macht A wieder auf; B bleibt, wie es ist
    tk.nachricht(SID, "u3", "Korrektur zu A")
    tk.werkzeug_zuordnen(SID, "u3", 1)
    assert [t["status"] for t in tk.laden(SID)["tickets"]] == ["offen", "offen"]


def test_schnitt_schliesst_das_vorige_aber_nicht_ein_leeres():
    tk.nachricht(SID, "u1", "A")
    tk.schnitt(SID, "B")
    assert [t["status"] for t in tk.laden(SID)["tickets"]] == ["erledigt", "offen"]
    tk.schnitt(SID, "C")          # B wartet noch auf seine erste Nachricht: wird ersetzt
    d = tk.laden(SID)
    assert [t["titel"] for t in d["tickets"]] == ["A", "C"]
    assert d["tickets"][0]["status"] == "erledigt"


def test_bus_nur_zwei_werkzeuge():
    tk.nachricht(SID, "u1", "A")
    assert tk.bus("ticket_neu", {"titel": "Neu"}, SID, "u1") == "#1"
    assert tk.bus("ticket_erledigt", {}, SID, "u1").startswith("Unbekannt")
    assert "gibt es in dieser Session nicht" in tk.bus("ticket_zuordnen", {"nr": 9}, SID, "u1")
    assert tk.bus("ticket_neu", {"titel": "x"}, SID, "")        # ohne Nachricht: Hinweistext, kein Absturz


def test_hinweiszeile():
    tk.nachricht(SID, "u1", "A")
    tk.werkzeug_neu(SID, "u1", "Erste")
    tk.nachricht(SID, "u2", "B")
    tk.werkzeug_neu(SID, "u2", "Zweite")
    z = tk.hinweis(SID)
    assert z.startswith("[Tickets: ") and z.endswith("]")
    assert "#2 „Zweite“" in z and "#1 „Erste“" in z
    assert "\n" not in z
    assert tk.hinweis("abcd1234-0000-0000-0000-00000000ffff") == "[Tickets: noch keins]"
    assert "#1 „Vorab“" in tk.hinweis("abcd1234-0000-0000-0000-00000000ffff", "Vorab")
