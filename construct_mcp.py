#!/usr/bin/env python3
"""Die Ticket-Werkzeuge des Assistenten als MCP-Server.

Wird pro Lauf von der claude-CLI als Unterprozess gestartet (siehe
server/runs.py → bus_config) und spricht JSON-RPC 2.0 zeilenweise über
stdin/stdout. Die Arbeit macht der CONSTRUCT-Server (server/tickets.py);
dieses Programm reicht Aufrufe nur über localhost weiter — dasselbe Muster
wie factoria_mcp.py, und wie dort von Hand statt mit dem `mcp`-Paket: es sind
vier Methoden.

Wer aufruft und in welcher Session, steht in der Umgebung, nicht in den
Argumenten:

    CONSTRUCT_RUN    Lauf, in dem der Assistent gerade arbeitet
    CONSTRUCT_TOKEN  Einmal-Token dieses Laufs
    CONSTRUCT_BASE   http://127.0.0.1:<port>
    CONSTRUCT_AUTH   fertiger Authorization-Header, falls ein Passwort gesetzt ist

Die Beschreibungen sind absichtlich kurz: sie stehen in jedem Zug im Kontext.
"""
import json
import os
import sys
import urllib.error
import urllib.request

RUN = os.environ.get("CONSTRUCT_RUN", "")
TOKEN = os.environ.get("CONSTRUCT_TOKEN", "")
BASE = os.environ.get("CONSTRUCT_BASE", "http://127.0.0.1:8765")
AUTH = os.environ.get("CONSTRUCT_AUTH", "")

WERKZEUGE = [
    {"name": "ticket_neu",
     "description": "Die aktuelle Nachricht ist eine neue, eigenständige Aufgabe: eigenes Ticket mit kurzem Titel (das vorige gilt damit als erledigt).",
     "inputSchema": {"type": "object", "properties": {
         "titel": {"type": "string", "description": "3-6 Wörter"}},
         "required": ["titel"]}},
    {"name": "ticket_zuordnen",
     "description": "Die aktuelle Nachricht gehört zu einem anderen, in der Ticket-Zeile genannten Ticket.",
     "inputSchema": {"type": "object", "properties": {
         "nr": {"type": "integer"}}, "required": ["nr"]}},
]


def melde(obj):
    sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def ergebnis(rid, text, fehler=False):
    melde({"jsonrpc": "2.0", "id": rid,
           "result": {"content": [{"type": "text", "text": text}], "isError": fehler}})


def an_server(werkzeug: str, args: dict) -> tuple:
    """Aufruf an CONSTRUCT weiterreichen. Gibt (text, fehler) zurück."""
    daten = json.dumps({"tool": werkzeug, "args": args, "run": RUN, "token": TOKEN}).encode()
    kopf = {"Content-Type": "application/json"}
    if AUTH:
        kopf["Authorization"] = AUTH
    req = urllib.request.Request(f"{BASE}/api/ticketbus", data=daten, headers=kopf)
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            j = json.loads(r.read().decode("utf-8", "replace"))
        return j.get("text") or "", bool(j.get("error"))
    except urllib.error.HTTPError as e:
        return f"HTTP {e.code}", True
    except Exception as e:
        return f"Ticket-Dienst nicht erreichbar ({type(e).__name__}). Weiter ohne Ticket.", True


def main():
    for zeile in sys.stdin:
        zeile = zeile.strip()
        if not zeile:
            continue
        try:
            m = json.loads(zeile)
        except Exception:
            continue
        meth, rid = m.get("method"), m.get("id")
        if meth == "initialize":
            # Die vom Klienten angefragte Fassung wörtlich zurückgeben: so bleibt
            # der Server gültig, wenn die CLI ihre Protokollfassung anhebt.
            pv = (m.get("params") or {}).get("protocolVersion", "2025-06-18")
            melde({"jsonrpc": "2.0", "id": rid, "result": {
                "protocolVersion": pv, "capabilities": {"tools": {}},
                "serverInfo": {"name": "construct", "version": "1.0"}}})
        elif meth == "tools/list":
            melde({"jsonrpc": "2.0", "id": rid, "result": {"tools": WERKZEUGE}})
        elif meth == "tools/call":
            p = m.get("params") or {}
            text, fehler = an_server(p.get("name") or "", p.get("arguments") or {})
            ergebnis(rid, text, fehler)
        elif rid is not None:
            # Auf jede Anfrage MUSS geantwortet werden; Schweigen lässt den Lauf hängen.
            melde({"jsonrpc": "2.0", "id": rid,
                   "error": {"code": -32601, "message": f"unbekannt: {meth}"}})


if __name__ == "__main__":
    main()
