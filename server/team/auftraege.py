"""Auftraege — was die Firma zu tun hat, und was dabei passiert ist.

Nicht zu verwechseln mit den Tickets (server/tickets.py): ein Ticket gliedert die
Arbeit in einer Chat-Session, ein Auftrag ist das, was die Firma bekommt.

Ablage: firma/auftraege/<id>/ticket.json + firma/auftraege/<id>/thread.jsonl

Das JSON traegt den Zustand und wird atomar ersetzt; der Verlauf wird nur
ANGEHAENGT. Anhaengen ist absturzsicher (eine halb geschriebene Zeile ist
erkennbar und die davor sind heil), billig zu lesen und dasselbe Format, das
Claude Code fuer seine eigenen Transkripte benutzt.

Kein SQLite: das sind Dutzende Auftraege, keine Millionen — und Kevin muss
einen festgefahrenen Auftrag im Editor aufmachen und reparieren koennen.

Der Verlauf speichert Text und Werkzeugaufrufe SELBST und verweist nicht nur
auf eine run_id: fertige Laeufe werden nach einer Viertelstunde weggeraeumt
(gc_runs), die Auftragsansicht muss aber auch in einer Woche noch stimmen.
"""
import json
import time
import uuid
from datetime import datetime
from pathlib import Path

from server.team.pfade import FIRMA_DIR

AUFTRAEGE_DIR = FIRMA_DIR / "auftraege"

# Woran man einen Auftrag des Pruefstands erkennt — vorn im Titel. Steht hier
# und nicht nur in eval.py, weil app.py danach entscheidet, was in die
# Personalakten (HISTORIE.jsonl) geschrieben wird: Testauftraege nicht.
TEST_MARKE = "[eval]"


def _atomic(p: Path, text: str):
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(p)


def _dir(tid: str) -> Path:
    return AUFTRAEGE_DIR / tid


def neu(titel: str, brief: str, owner: str = "lumina", cwd: str = "") -> dict:
    tid = uuid.uuid4().hex[:8]
    t = {
        "id": tid,
        "titel": (titel or brief or "Auftrag")[:120],
        "brief": brief,                      # Kevins Worte, werden nie umgeschrieben
        "status": "neu",
        "owner": owner,
        "cwd": cwd,
        "erstellt": datetime.now().isoformat(timespec="seconds"),
        "in_arbeit": None,                   # {msg_id, run_id, versuch} — VOR dem Lauf gesetzt
        "sessions": {},                      # slug -> Claude-Sitzung in DIESEM Auftrag
        "artefakte": [],                     # [{pfad, von, ts, sha}]
        # Kein Budget: die Grenzen stehen fest in guards.py. Hier wird nur
        # mitgeschrieben, was der Auftrag tatsaechlich verbraucht hat — das ist
        # Anzeige fuer Kevin, keine Bremse.
        "verbraucht": {"hops": 0, "cost": 0.0, "start": time.time()},
        "eskalation": None,                  # {bremse, grund, frage, seit, an}
        "einstellung": None,                 # {rolle, warum, kandidaten, runden, seit}
        # frei_seit: ab wann die Bremsen zaehlen — nach jedem "weitermachen"
        # von Kevin faengt die Zaehlung von vorn an.
        "wache": {"ohne_artefakt": 0, "frei_seit": 0.0},
    }
    speichern(t)
    _dir(tid).joinpath("thread.jsonl").touch()
    return t


def speichern(t: dict):
    _atomic(_dir(t["id"]) / "ticket.json",
            json.dumps(t, ensure_ascii=False, indent=1))


def laden(tid: str) -> dict | None:
    try:
        return json.loads((_dir(tid) / "ticket.json").read_text(encoding="utf-8"))
    except Exception:
        return None


def alle() -> list:
    out = []
    if AUFTRAEGE_DIR.exists():
        for d in AUFTRAEGE_DIR.iterdir():
            t = laden(d.name) if (d / "ticket.json").exists() else None
            if t:
                out.append(t)
    out.sort(key=lambda x: x.get("erstellt", ""), reverse=True)
    return out


# ---------- Der Verlauf ----------
def anhaengen(tid: str, eintrag: dict) -> dict:
    eintrag.setdefault("id", "m" + uuid.uuid4().hex[:6])
    eintrag.setdefault("ts", time.time())
    with (_dir(tid) / "thread.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(eintrag, ensure_ascii=False) + "\n")
    return eintrag


def verlauf(tid: str) -> list:
    p = _dir(tid) / "thread.jsonl"
    if not p.exists():
        return []
    out = []
    for zeile in p.read_text(encoding="utf-8", errors="replace").splitlines():
        zeile = zeile.strip()
        if not zeile:
            continue
        try:
            out.append(json.loads(zeile))
        except json.JSONDecodeError:
            # Abgeschnittene letzte Zeile nach einem Absturz — der Rest bleibt gueltig.
            continue
    return out


# Kurzfassung des Verlaufs, gemerkt nach (mtime, groesse) der thread.jsonl.
_UEBERSICHT = {}


def uebersicht(tid: str) -> dict:
    """Was die Auftragsliste vom Verlauf braucht — ohne ihn jedes Mal zu lesen.

    Die Liste holt sich die Oberflaeche im Sekundentakt. Ohne diesen Cache
    liest der Server dabei JEDE thread.jsonl komplett, nur um Nachrichten zu
    zaehlen: bei fuenf Auftraegen egal, bei zweihundert nicht mehr.

    Schluessel ist (mtime, groesse). Der Verlauf wird ausschliesslich
    angehaengt, jede Aenderung veraendert also die Groesse — die mtime ist
    guertel-und-hosentraeger fuer den Fall, dass eine Datei gleich lang ersetzt
    wird. Ist die Datei nicht lesbar, wird nichts gemerkt und beim naechsten Mal
    neu versucht.
    """
    p = _dir(tid) / "thread.jsonl"
    try:
        st = p.stat()
        stand = (st.st_mtime, st.st_size)
    except OSError:
        stand = None
    gemerkt = _UEBERSICHT.get(tid)
    if gemerkt and stand and gemerkt[0] == stand:
        return gemerkt[1]
    sichtbar = [e for e in verlauf(tid) if e.get("art") != "zugestellt"]
    letzte = sichtbar[-1] if sichtbar else {}
    daten = {"msgs": len(sichtbar), "letzte_von": letzte.get("von", ""),
             "letzte_art": letzte.get("art", ""), "letzte_ts": letzte.get("ts", 0)}
    if stand:
        _UEBERSICHT[tid] = (stand, daten)
    return daten


def offene_nachrichten(tid: str) -> list:
    """Was eingereiht, aber noch nicht abgearbeitet ist.

    Zugestellt wird durch eine ANGEHAENGTE Quittung vermerkt, nicht durch
    Umschreiben der urspruenglichen Zeile — sonst waere der Verlauf nicht mehr
    nur-anhaengend und ein Absturz mittendrin koennte ihn zerreissen.
    """
    quittiert = set()
    nachrichten = []
    for e in verlauf(tid):
        if e.get("art") == "zugestellt":
            quittiert.add(e.get("ref"))
        elif e.get("an"):
            nachrichten.append(e)
    return [n for n in nachrichten if n["id"] not in quittiert]


def quittieren(tid: str, msg_id: str):
    anhaengen(tid, {"art": "zugestellt", "ref": msg_id})


# Die Groessen, die ein Verteiler beim Beauftragen mitgeben darf.
GROESSEN = ("klein", "normal", "gross")


def kleinauftrag_direkt(verlauf: list, slug: str, owner: str) -> bool:
    """Darf dieses `liefern` am Verteiler vorbei direkt zu Kevin?

    Ja, wenn die Geschaeftsfuehrung den Auftrag als **klein** eingestuft und
    seit Kevins letztem Wort genau EINE Person beauftragt hat — naemlich
    `slug`. Dann ist ihr Schlusszug ein reiner Durchreicher (ein Opus-Prozess,
    der eine Nachricht von zehn Zeilen in eine von acht uebersetzt), und der
    faellt weg.

    Warum "genau eine seit Kevins letztem Auftrag" und nicht nur "der Eintrag
    traegt klein": Hat Lumina zwei Leute parallel vergeben, gehoert die
    Zusammenfassung ihr — sonst wuerde das zweite Ergebnis den Auftrag
    schliessen, waehrend das erste nur bei ihr liegt. Und hat sie nach dem
    ersten Ergebnis doch noch einen Pruefer eingeplant, ist es kein
    Kleinauftrag mehr, egal was im ersten Briefing stand.

    Kevins Antworten auf Rueckfragen (art `antwort`) setzen den Zaehler nicht
    zurueck — sonst wuerde eine einzige Eskalation den Kleinauftrag wieder
    ueber den Umweg schicken.
    """
    seit_kevin = []
    for e in verlauf:
        if e.get("von") == "kevin" and e.get("art") == "auftrag":
            seit_kevin = []
        elif e.get("art") == "auftrag" and e.get("von") == owner:
            seit_kevin.append(e)
    if len(seit_kevin) != 1:
        return False
    e = seit_kevin[0]
    return e.get("an") == slug and e.get("groesse") == "klein"
