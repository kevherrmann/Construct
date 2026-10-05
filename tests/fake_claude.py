#!/usr/bin/env python3
"""Ein falsches `claude`: spricht stream-json und ruft den Firmen-Bus wie ein Modell.

Nur für tests/test_team_engine.py. Was der Mitarbeiter tut, hängt an einem
Szenario-Stichwort im Auftragstext:

    [klein]      Chef gibt an den Entwickler ab (klein), der liefert direkt
    [kette]      Chef -> Entwickler -> Prüfer -> Chef liefert
    [rueckfrage] der Entwickler eskaliert; nach der Antwort liefert er
    [still]      der Entwickler sagt etwas, ruft aber den Bus nicht auf
    [langsam]    der Entwickler braucht ein paar Sekunden (Not-Aus, Abbrechen)
"""
import json
import os
import sys
import time
import urllib.request


def arg(name):
    a = sys.argv
    return a[a.index(name) + 1] if name in a else ""


cfg = json.loads(arg("--mcp-config") or "{}")
srv = (cfg.get("mcpServers") or {}).get("firma") or {}
env = srv.get("env") or {}
AGENT = env.get("FIRMA_AGENT", "")
BASE = env.get("FIRMA_BASE", "")
TOKEN = env.get("FIRMA_TOKEN", "")
AUFTRAG = env.get("FIRMA_AUFTRAG", "")


def out(ev):
    sys.stdout.write(json.dumps(ev) + "\n")
    sys.stdout.flush()


def bus(tool, **args):
    out({"type": "assistant", "message": {"content": [
        {"type": "tool_use", "id": f"t{time.time_ns()}", "name": f"mcp__firma__{tool}", "input": args}]}})
    d = json.dumps({"tool": tool, "args": args, "agent": AGENT, "ticket": AUFTRAG, "token": TOKEN}).encode()
    r = urllib.request.Request(BASE + "/api/team/bus", data=d, headers={"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(r, timeout=20))


msg = json.loads(sys.stdin.readline())
text = msg["message"]["content"][0]["text"]
sid = arg("--resume") or f"fake-{AGENT}-{os.getpid()}"
out({"type": "system", "subtype": "init", "session_id": sid})

if not AUFTRAG:
    out({"type": "stream_event", "event": {"type": "content_block_delta",
                                           "delta": {"type": "text_delta", "text": f"hier spricht {AGENT}"}}})
else:
    art = ("frage" if "fragt dich:" in text else
           "ergebnis" if "liefert dir:" in text else
           "antwort" if "antwortet dir:" in text else "auftrag")
    out({"type": "stream_event", "event": {"type": "content_block_delta",
                                           "delta": {"type": "text_delta", "text": f"{AGENT} liest ({art})"}}})
    if "[langsam]" in text and AGENT == "cody":
        time.sleep(4)
    if AGENT == "chef" and art == "auftrag":
        if "[klein]" in text:
            bus("beauftragen", an="cody", auftrag="Baue das Ding. [klein]", groesse="klein")
        elif "[kette]" in text:
            bus("beauftragen", an="cody", auftrag="Baue das Ding. [kette]", groesse="normal")
        elif "[rueckfrage]" in text:
            bus("beauftragen", an="cody", auftrag="Baue das Ding. [rueckfrage]", groesse="klein")
        elif "[still]" in text:
            bus("beauftragen", an="cody", auftrag="Baue das Ding. [still]", groesse="klein")
        elif "[langsam]" in text:
            bus("beauftragen", an="cody", auftrag="Baue das Ding. [langsam]", groesse="klein")
        else:
            bus("liefern", ergebnis="Nichts zu tun.")
    elif AGENT == "chef" and art == "ergebnis":
        if "[kette]" in text and "geprüft" not in text:
            bus("beauftragen", an="miranda", auftrag="Prüfe das Ergebnis.", groesse="normal")
        else:
            bus("liefern", ergebnis="Alles fertig, so sieht es jetzt aus.")
    elif AGENT == "cody" and art == "auftrag":
        if "[rueckfrage]" in text:
            bus("eskalieren", grund="Welche Farbe?", frage="Rot oder blau?")
        elif "[still]" in text:
            pass                                  # sagt etwas, gibt aber nichts an den Bus
        else:
            bus("liefern", ergebnis="gebaut", dateien=[])
    elif AGENT == "cody" and art == "antwort":
        bus("liefern", ergebnis="gebaut, in der gewünschten Farbe")
    elif AGENT == "miranda":
        bus("liefern", ergebnis="geprüft: in Ordnung")

out({"type": "result", "subtype": "success", "session_id": sid, "total_cost_usd": 0.01,
     "duration_ms": 5, "usage": {"input_tokens": 10, "cache_read_input_tokens": 900,
                                 "cache_creation_input_tokens": 100, "output_tokens": 20}})
