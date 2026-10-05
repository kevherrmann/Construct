#!/usr/bin/env python3
"""Der Firmen-Bus als MCP-Server — wie Mitarbeiter miteinander reden.

Wird pro Agentenzug von der claude-CLI als Unterprozess gestartet und spricht
JSON-RPC 2.0 zeilenweise ueber stdin/stdout. Die eigentliche Arbeit macht der
CONSTRUCT-Server (server/team/bus.py): dieses Programm reicht Aufrufe nur ueber
localhost weiter.

Warum von Hand statt mit dem `mcp`-Paket: es sind vier Methoden (initialize,
notifications/initialized, tools/list, tools/call). Das Paket zoege anyio,
pydantic, httpx-sse und sse-starlette in ein Projekt mit fuenf Zeilen
requirements.txt. Der Klient derselben Protokollhaelfte stand hier schon
handgeschrieben (frueher hermes.py), das ist also Hausstil.

Wer der Aufrufer ist, steht in der Umgebung — nicht in den Argumenten. Ein
Agent kann sich damit nicht als jemand anderes ausgeben:

    FIRMA_AGENT    Slug des Mitarbeiters
    FIRMA_AUFTRAG  Auftrag, in dem er gerade arbeitet (leer im Direktgespraech)
    FIRMA_TOKEN    Einmal-Token dieses Laufs
    FIRMA_BASE     http://127.0.0.1:<port>
    FIRMA_AUTH     fertiger Authorization-Header, falls der Server ein Passwort hat
"""
import json
import os
import sys
import urllib.error
import urllib.request

AGENT = os.environ.get("FIRMA_AGENT", "")
TICKET = os.environ.get("FIRMA_AUFTRAG", "")
TOKEN = os.environ.get("FIRMA_TOKEN", "")
BASE = os.environ.get("FIRMA_BASE", "http://127.0.0.1:8765")
AUTH = os.environ.get("FIRMA_AUTH", "")
NUTZER = os.environ.get("FIRMA_NUTZER", "Kevin")

# Die Werkzeuge des Busses. Bewusst KEIN Rundruf: ein Broadcast ist der
# schnellste Weg zu kombinatorisch wachsenden Schrittzahlen.
WERKZEUGE = [
    {"name": "beauftragen",
     "description": ("Gib einem Kollegen eine Teilaufgabe. Danach beendest du deinen Zug, "
                     "das Ergebnis erreicht dich als neue Nachricht. Mehrere Aufrufe in "
                     "EINEM Zug sind nur erlaubt, wenn die Teile unabhaengig sind, an "
                     "verschiedene Kollegen gehen und nicht dieselben Dateien anfassen "
                     "(hoechstens drei). Nur fuer Leute, die verteilen duerfen."),
     "inputSchema": {"type": "object", "properties": {
         "an": {"type": "string", "description": "Slug des Kollegen, z.B. 'entwickler'"},
         "auftrag": {"type": "string", "description": "Was genau zu tun ist, mit allem noetigen Kontext"},
         "groesse": {"type": "string", "enum": ["klein", "normal", "gross"],
                     "description": ("Wie viel Ablauf der Auftrag braucht. klein = eine Person, "
                                     "ein abgegrenztes Stueck, kein Pruefer — ihr Ergebnis geht "
                                     "direkt an Kevin und schliesst den Auftrag ab (nur "
                                     "Geschaeftsfuehrung). normal = Umsetzer plus EIN Pruefer. "
                                     "gross = die volle Kette. Ohne Angabe: normal.")}},
         "required": ["an", "auftrag"]}},
    {"name": "fragen",
     "description": ("Stelle einem Kollegen EINE Frage. Beende danach deinen Zug. "
                     "Wuerdest du dieselbe Frage ein zweites Mal stellen: eskaliere stattdessen."),
     "inputSchema": {"type": "object", "properties": {
         "an": {"type": "string"}, "frage": {"type": "string"}},
         "required": ["an", "frage"]}},
    {"name": "antworten",
     "description": "Antworte auf die Frage, die dich erreicht hat.",
     "inputSchema": {"type": "object", "properties": {
         "antwort": {"type": "string"}}, "required": ["antwort"]}},
    {"name": "liefern",
     "description": ("Dein Teil ist fertig. Uebergibt das Ergebnis an den, der dich "
                     "beauftragt hat. Auch bei Teilergebnissen — dann sag dazu, was fehlt."),
     "inputSchema": {"type": "object", "properties": {
         "ergebnis": {"type": "string"},
         "dateien": {"type": "array", "items": {"type": "string"},
                     "description": "Pfade, die du angefasst hast"}},
         "required": ["ergebnis"]}},
    {"name": "eskalieren",
     "description": ("Hol Kevin dazu. Der Auftrag pausiert, bis er antwortet. "
                     "Das ist keine Niederlage — es ist besser, als im Kreis zu laufen."),
     "inputSchema": {"type": "object", "properties": {
         "grund": {"type": "string"}, "frage": {"type": "string"}},
         "required": ["grund", "frage"]}},
    {"name": "einstellen",
     "description": ("Es fehlt eine Rolle in der Firma. Kevin bekommt einen Vorschlag "
                     "und stellt ein, aendert oder lehnt ab. Nur fuer die Geschaeftsfuehrung."),
     "inputSchema": {"type": "object", "properties": {
         "rolle": {"type": "string"}, "warum": {"type": "string"}},
         "required": ["rolle", "warum"]}},
    {"name": "rechnen",
     "description": ("Rechne einen Ausdruck exakt aus. BENUTZE DAS IMMER, wenn ein Ergebnis "
                     "stimmen muss — im Kopf rechnen geht bei Geld und langen Zahlen schief. "
                     "Kann + - * / // % **, Klammern, sqrt, log, sin/cos/tan, abs, round, "
                     "min/max, pi und e. Rechnet mit Dezimalstellen statt Gleitkomma, "
                     "0.1+0.2 ergibt hier wirklich 0.3."),
     "inputSchema": {"type": "object", "properties": {
         "ausdruck": {"type": "string", "description": "z.B. '(1500 - 249.90) * 0.19'"}},
         "required": ["ausdruck"]}},
    {"name": "kontrast",
     "description": ("WCAG-Kontrast zweier Farben messen (Text 4,5:1, grosser Text und "
                     "Bedienelemente 3:1). Farben als #rrggbb, #rgb oder r,g,b. Nimm das "
                     "statt zu schaetzen — '#777 auf weiss' sieht nach AA aus und ist es nicht."),
     "inputSchema": {"type": "object", "properties": {
         "vorne": {"type": "string", "description": "Schrift- oder Elementfarbe"},
         "hinten": {"type": "string", "description": "Hintergrundfarbe"}},
         "required": ["vorne", "hinten"]}},
    {"name": "belegschaft",
     "description": "Wer arbeitet hier, mit welcher Rolle. Nur lesen.",
     "inputSchema": {"type": "object", "properties": {}}},
    {"name": "notiz",
     "description": ("Eine Anmerkung fuer den Verlauf, an niemanden gerichtet. "
                     "Zaehlt nicht als Schritt."),
     "inputSchema": {"type": "object", "properties": {
         "text": {"type": "string"}}, "required": ["text"]}},
    {"name": "merken",
     "description": "Etwas in DEIN eigenes Gedaechtnis schreiben (MEMORY.md).",
     "inputSchema": {"type": "object", "properties": {
         "text": {"type": "string"}}, "required": ["text"]}},
    {"name": "auftrag_anlegen",
     "description": ("Nur im Direktgespraech: aus dem, worueber ihr gerade redet, einen "
                     "Auftrag fuer die Firma machen. Die Geschaeftsfuehrung verteilt ihn "
                     "dann. Nimm das, wenn Kevin sagt 'kuemmer dich drum' oder "
                     "'mach das' und es echte Arbeit ist."),
     "inputSchema": {"type": "object", "properties": {
         "titel": {"type": "string"},
         "brief": {"type": "string", "description": "Die Aufgabe so beschrieben, dass "
                                                    "jemand ohne euren Gespraechsverlauf "
                                                    "sofort loslegen kann"}},
         "required": ["titel", "brief"]}},
    {"name": "user_merken",
     "description": ("Etwas Dauerhaftes ueber Kevin in die gemeinsame USER.md schreiben — "
                     "was du hier eintraegst, wissen alle Kollegen. Nur anhaengen, "
                     "nie ersetzen."),
     "inputSchema": {"type": "object", "properties": {
         "fakt": {"type": "string"}}, "required": ["fakt"]}},
    {"name": "anleitung",
     "description": ("Hol dir eine Anleitung der Firma, die im Index oben mit Namen "
                     "steht. Enthaelt den erprobten Ablauf samt Fallstricken. Mach das, "
                     "BEVOR du eine Sache selbst durchprobierst, fuer die es schon eine "
                     "gibt — dafuer stehen sie da."),
     "inputSchema": {"type": "object", "properties": {
         "name": {"type": "string", "description": "Name aus dem Index, z.B. 'playwright-bestaetigen'"}},
         "required": ["name"]}},
    {"name": "anleitung_anlegen",
     "description": ("Halte einen Ablauf fest, den die Firma wieder brauchen wird — "
                     "erst NACHDEM du ihn erfolgreich durchgezogen hast. Nimm das fuer "
                     "WIE MAN ETWAS MACHT (Schritte, Befehle, Fallstricke); fuer blosse "
                     "Erkenntnisse nimm `merken`. Existiert der Name schon, wird die "
                     "Anleitung verbessert statt verdoppelt. Alle Kollegen sehen sie."),
     "inputSchema": {"type": "object", "properties": {
         "name": {"type": "string", "description": "kurz, kleingeschrieben, mit Bindestrichen"},
         "wann": {"type": "string", "description": "Ein Satz: woran erkennt ein Kollege, "
                                                   "dass diese Anleitung seine Lage trifft? "
                                                   "Das ist das Einzige, was staendig im "
                                                   "Systemprompt steht — mach es praezise."},
         "text": {"type": "string", "description": "Die Schritte. Konkret, mit Befehlen und "
                                                   "den Fallen, in die du getappt bist."}},
         "required": ["name", "wann", "text"]}},
]


# Die Beschreibungen sind in Kevins Firma entstanden und nennen ihn beim Namen —
# hier wird daraus der Name des Nutzers dieser Installation.
if NUTZER != "Kevin":
    WERKZEUGE = json.loads(json.dumps(WERKZEUGE, ensure_ascii=False).replace("Kevin", NUTZER))


def melde(obj):
    sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def ergebnis(rid, text, fehler=False):
    melde({"jsonrpc": "2.0", "id": rid,
           "result": {"content": [{"type": "text", "text": text}], "isError": fehler}})


# Wie lange auf den Server gewartet wird. Die meisten Aufrufe kehren sofort
# zurueck; `merken` aber dickt bei vollem Gedaechtnis synchron ein und braucht
# dafuer einen eigenen claude-Lauf (bis 180 s). Mit den frueheren 30 s bekam
# der Agent "Bus nicht erreichbar", obwohl der Eintrag am Ende gespeichert
# wurde — und lernte daraus, dass merken kaputt sei.
TIMEOUT = 30
TIMEOUT_LANG = {"merken": 300}


def an_server(werkzeug: str, args: dict) -> tuple:
    """Aufruf an den Server weiterreichen. Gibt (text, fehler) zurueck."""
    daten = json.dumps({"tool": werkzeug, "args": args, "agent": AGENT,
                        "ticket": TICKET, "token": TOKEN}).encode()
    kopf = {"Content-Type": "application/json"}
    if AUTH:
        kopf["Authorization"] = AUTH
    req = urllib.request.Request(f"{BASE}/api/team/bus", data=daten, headers=kopf)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_LANG.get(werkzeug, TIMEOUT)) as r:
            j = json.loads(r.read().decode("utf-8", "replace"))
        return j.get("text") or "", bool(j.get("error"))
    except urllib.error.HTTPError as e:
        try:
            j = json.loads(e.read().decode("utf-8", "replace"))
            return j.get("text") or j.get("error") or f"HTTP {e.code}", True
        except Exception:
            return f"HTTP {e.code}", True
    except Exception as e:
        # Der Server ist die einzige Wahrheit. Faellt er aus, muss der Agent das
        # SEHEN — sonst arbeitet er weiter, als waere alles zugestellt worden.
        return f"Bus nicht erreichbar ({type(e).__name__}). Beende deinen Zug.", True


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
            # Die vom Klienten angefragte Fassung woertlich zurueckgeben, statt
            # eine eigene zu setzen: so bleibt der Server gueltig, wenn die CLI
            # ihre Protokollfassung anhebt.
            pv = (m.get("params") or {}).get("protocolVersion", "2025-06-18")
            melde({"jsonrpc": "2.0", "id": rid, "result": {
                "protocolVersion": pv,
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "firma", "version": "1.0"}}})
        elif meth == "tools/list":
            melde({"jsonrpc": "2.0", "id": rid, "result": {"tools": WERKZEUGE}})
        elif meth == "tools/call":
            p = m.get("params") or {}
            text, fehler = an_server(p.get("name") or "", p.get("arguments") or {})
            ergebnis(rid, text, fehler)
        elif rid is not None:
            # Auf eine unbekannte Anfrage MUSS geantwortet werden; Schweigen
            # laesst den Agenten haengen.
            melde({"jsonrpc": "2.0", "id": rid,
                   "error": {"code": -32601, "message": f"unbekannt: {meth}"}})


if __name__ == "__main__":
    main()
