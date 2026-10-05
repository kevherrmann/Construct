"""Tickets — die Aufgaben innerhalb einer Session.

Kevin arbeitet den ganzen Tag in EINER Session je Projekt und gibt darin viele
Aufgaben. Ein Ticket ist deshalb ein Abschnitt einer Session, nicht die
Session: es sammelt die Nachrichten, die zu einer Aufgabe gehören, auch mit
Lücken dazwischen (Aufgabe, Korrektur, neue Aufgabe, noch eine Korrektur zur
ersten = zwei Tickets).

Ablage: tickets/<session_id>.json, eine Datei je Session. Wie bei den
Personalakten und Aufträgen von FACTORIA keine Datenbank — Kevin muss eine
verrutschte Zuordnung im Editor geradeziehen können. Steht in .gitignore.

Wer zuordnet, in dieser Reihenfolge:

  1. Kevin, ohne Tokens: `/ticket Titel`, der Chip über der Eingabe, ✂ an einer
     Nachricht. Seine Wahl sperrt die nächste Nachricht gegen den Assistenten.
  2. Der Assistent, mit einer Markerzeile als LETZTER Zeile seiner Antwort
     (`[[ticket neu: Titel]]`, `[[ticket zu: 2]]`, `[[ticket firma]]`). Kein
     Werkzeug und kein MCP-Server: ein MCP-Server kostet gemessen 2–3 s je Nachricht
     und +1,3k Tokens Kontext, oder — mit --strict-mcp-config — die MCP-Server des
     Nutzers (05.10.2026). Eine Markerzeile kostet nur, wenn sie gebraucht wird,
     funktioniert in Antworten ohne Werkzeugaufruf und braucht keine Berechtigung.
  3. Die Vorgabe, ohne Modell: eine Nachricht gehört zum aktuellen Ticket. Gibt
     es keins, entsteht eins mit dem Anfang der Nachricht als Titel.

Ein "erledigt" gibt es für den Assistenten nicht: jedes NEUE Ticket schließt das
vorige.

Die Nachrichten werden über ihre uuid im Claude-Code-Transkript gefunden; der
Lauf meldet sie dank --replay-user-messages, sobald sie angenommen sind. Text
und Uhrzeit stehen zusätzlich hier, damit die Übersicht keine Transkripte
lesen muss.
"""
import json
import re
import shutil
import threading
from datetime import datetime
from pathlib import Path

from server import config as cfg
from server.core import BASE_DIR

TICKETS_DIR = BASE_DIR / "tickets"

SID_RE = re.compile(r"^[A-Za-z0-9-]{8,64}$")
TITEL_MAX = 80
AUSZUG_MAX = 160
# So viele erledigte Tickets sieht der Assistent noch (Kevins Vorgabe: mehr
# braucht es nicht — wer sich auf etwas bezieht, meint das aktuelle).
ERLEDIGT_SICHTBAR = 3
# Und so viele offene. Mehr wird gezählt statt aufgezählt, sonst wächst die
# Zeile an jeder Nachricht mit jedem liegengebliebenen Ticket.
OFFEN_SICHTBAR = 8

STATUS = ("offen", "erledigt")
VON = ("kevin", "assistent", "auto")


# ---------- Datei ----------
_LOCKS: dict[str, threading.Lock] = {}
_LOCKS_LOCK = threading.Lock()


def _lock(sid: str) -> threading.Lock:
    """Ein Schloss je Session: Werkzeugaufruf, Vorgabe und Oberfläche können
    gleichzeitig an derselben Datei drehen."""
    with _LOCKS_LOCK:
        return _LOCKS.setdefault(sid, threading.Lock())


def _pfad(sid: str) -> Path:
    if not SID_RE.match(sid or ""):
        raise ValueError("ungültige Session-ID")
    return TICKETS_DIR / f"{sid}.json"


def _jetzt() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _leer(sid: str) -> dict:
    return {"session": sid, "cwd": "", "project": "", "aktuell": None,
            "gesperrt": False, "zaehler": 0, "tickets": []}


def _bereinigt(d: dict, sid: str) -> dict:
    """Gelesene Datei auf Form bringen. Von Hand bearbeitet darf sie unvollständig
    sein; ein Tippfehler macht ein Ticket kaputt, nicht die Oberfläche."""
    out = _leer(sid)
    for k in ("cwd", "project"):
        if isinstance(d.get(k), str):
            out[k] = d[k]
    out["gesperrt"] = bool(d.get("gesperrt"))
    try:
        out["zaehler"] = max(0, int(d.get("zaehler") or 0))
    except (TypeError, ValueError):
        pass
    gesehen: set[str] = set()
    for t in d.get("tickets") if isinstance(d.get("tickets"), list) else []:
        if not isinstance(t, dict):
            continue
        try:
            nr = int(t.get("nr"))
        except (TypeError, ValueError):
            continue
        if nr < 1 or any(x["nr"] == nr for x in out["tickets"]):
            continue
        msgs = []
        for m in t.get("nachrichten") if isinstance(t.get("nachrichten"), list) else []:
            if isinstance(m, str):
                m = {"id": m}
            if not isinstance(m, dict) or not isinstance(m.get("id"), str) or m["id"] in gesehen:
                continue
            gesehen.add(m["id"])
            msg = {"id": m["id"], "ts": str(m.get("ts") or ""),
                   "text": str(m.get("text") or "")[:AUSZUG_MAX],
                   "von": m.get("von") if m.get("von") in VON else "auto"}
            if m.get("oeffnete"):
                msg["oeffnete"] = str(m["oeffnete"])
            msgs.append(msg)
        out["tickets"].append({
            "nr": nr,
            "titel": str(t.get("titel") or f"Ticket {nr}")[:TITEL_MAX],
            "status": t.get("status") if t.get("status") in STATUS else "offen",
            "von": t.get("von") if t.get("von") in VON else "auto",
            "erstellt": str(t.get("erstellt") or ""),
            "erledigt_am": str(t.get("erledigt_am") or "") or None,
            # Team-Modus: der Auftrag der Firma, der aus diesem Ticket entstand.
            "auftrag": str(t.get("auftrag") or "") or None,
            "nachrichten": msgs,
        })
    nrs = {t["nr"] for t in out["tickets"]}
    out["zaehler"] = max([out["zaehler"], *nrs])
    aktuell = d.get("aktuell")
    out["aktuell"] = aktuell if isinstance(aktuell, int) and aktuell in nrs else None
    return out


def laden(sid: str) -> dict:
    p = _pfad(sid)
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except OSError:
        return _leer(sid)
    except ValueError:
        # Von Hand kaputtgespeichert (fehlendes Komma): NICHT stillschweigend durch
        # eine leere Datei ersetzen, die der nächste Speichervorgang darüber
        # schriebe — erst eine Sicherung, damit sich die Datei reparieren lässt.
        sicher = p.with_name(p.name + ".kaputt")
        try:
            if not sicher.exists():
                shutil.copy2(p, sicher)
        except OSError:
            pass
        return _leer(sid)
    return _bereinigt(d if isinstance(d, dict) else {}, sid)


def entfernen(sid: str):
    """Die Tickets einer gelöschten Session wegräumen."""
    try:
        with _lock(sid):
            _pfad(sid).unlink(missing_ok=True)
            _CACHE.pop(sid, None)
    except ValueError:
        pass


def speichern(d: dict):
    p = _pfad(d["session"])
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(p)


def vorhanden(sid: str) -> bool:
    try:
        return _pfad(sid).exists()
    except ValueError:
        return False


# ---------- Hilfen ----------
def projekt_ordner(cwd: str) -> str:
    """Name des Transkript-Ordners, den Claude Code für einen Arbeitsordner
    anlegt (/home/k/projects → -home-k-projects). Gebraucht für den Sprung
    aus der Übersicht in den Verlauf."""
    return re.sub(r"[^A-Za-z0-9]", "-", cwd or "")


# Was build_prompt hinter Kevins Text hängt: Datei-Hinweise und die Ticketzeile.
# Für Auszug und Titel zählt nur, was er geschrieben hat.
_ANHANG_RE = re.compile(r"(?:^|\n\n)\[(?:Vom Nutzer hochgeladene|Image uploaded|PDF uploaded"
                        r"|Tickets:)[\s\S]*$")
# Beim Wechsel von einem anderen Modell steht vor Kevins Text ein Verlaufsblock
# (hermes_runs.carry_over_block, llm.history_block), der mit dieser Zeile endet.
_KONTEXT_RE = re.compile(r"^\[(?:Kontext|Context):[\s\S]*?\[(?:Ende des Verlaufs|End of history)[^\]]*\]\s*")


def kevins_text(text: str) -> str:
    return _ANHANG_RE.sub("", _KONTEXT_RE.sub("", text or "")).strip()


def titel_aus(text: str) -> str:
    """Titel für ein Ticket, das ohne Zutun entsteht: der Anfang der Nachricht,
    auf ein Wortende gekürzt."""
    s = " ".join(kevins_text(text).split())
    if len(s) <= 60:
        return s or cfg.L("Ohne Titel", "Untitled")
    cut = s[:60].rsplit(" ", 1)[0]
    return (cut if len(cut) > 30 else s[:60]) + " …"


def _ticket(d: dict, nr) -> dict | None:
    return next((t for t in d["tickets"] if t["nr"] == nr), None)


def _naechste_nr(d: dict) -> int:
    """Nummern werden nie wiederverwendet: ein Auftrag der Firma verweist über
    (Session, Nummer) auf sein Ticket, und eine gelöschte oder zusammengeführte
    Nummer darf nicht ein späteres, fremdes Ticket treffen."""
    d["zaehler"] = max(d.get("zaehler", 0), *(t["nr"] for t in d["tickets"]), 0) + 1
    return d["zaehler"]


def verknuepfen(sid: str, nr: int, auftrag_id: str | None) -> dict:
    """Das Ticket mit einem Auftrag der Firma verbinden (oder lösen)."""
    with _lock(sid):
        d = laden(sid)
        t = _ticket(d, nr)
        if t is None:
            raise KeyError(nr)
        t["auftrag"] = auftrag_id
        speichern(d)
        return d


def briefing(t: dict, volltexte: dict | None = None) -> str:
    """Aus den Nachrichten eines Tickets das Briefing für die Firma: die erste ist die
    Aufgabe, die späteren sind Korrekturen dazu — in dieser Reihenfolge, wörtlich.
    volltexte (uuid → Text) ersetzt die Auszüge der Ticket-Datei."""
    volltexte = volltexte or {}
    teile = [volltexte.get(m["id"]) or m["text"] for m in t["nachrichten"]]
    teile = [x for x in teile if x]
    if not teile:
        return t["titel"]
    kopf = teile[0]
    if len(teile) == 1:
        return kopf
    return kopf + "\n\nSpäter dazu gesagt:\n" + "\n".join(f"- {x}" for x in teile[1:])


def _wo(d: dict, uuid: str):
    """(ticket, nachricht) einer Nachricht oder (None, None)."""
    for t in d["tickets"]:
        for m in t["nachrichten"]:
            if m["id"] == uuid:
                return t, m
    return None, None


def _heraus(d: dict, uuid: str) -> dict | None:
    t, m = _wo(d, uuid)
    if t is None:
        return None
    t["nachrichten"].remove(m)
    if m.get("oeffnete"):
        # Diese Nachricht hatte das erledigte Ticket wieder aufgemacht — zieht sie in
        # ein anderes, war es keine Korrektur und das Ticket bleibt zu.
        t["status"], t["erledigt_am"] = "erledigt", m.pop("oeffnete")
    _aufraeumen(d, t)
    return m


def _aufraeumen(d: dict, t: dict):
    """Ein Ticket, das der Server oder der Assistent angelegt hat und das leer
    geworden ist (die Nachricht zog in ein anderes), hat niemand gewollt — weg
    damit. Von Kevin angelegte bleiben, auch leer: das ist ein Schnitt, der auf
    seine Nachricht wartet."""
    if not t["nachrichten"] and t["von"] != "kevin" and t in d["tickets"]:
        d["tickets"].remove(t)
        if d["aktuell"] == t["nr"]:
            d["aktuell"] = None


def _abschliessen(t: dict):
    if t["status"] != "erledigt":
        t["status"], t["erledigt_am"] = "erledigt", _jetzt()


def _anlegen(d: dict, titel: str, von: str) -> dict:
    """Neues Ticket. Das bisher aktuelle gilt damit als erledigt: Kevin bezieht sich
    auf das, woran er gerade arbeitet, oder fängt etwas Neues an — "erledigt
    ist erledigt". Ein leeres (ein Schnitt, der auf seine Nachricht wartet)
    bleibt unberührt."""
    alt = _ticket(d, d["aktuell"])
    if alt is not None and alt["nachrichten"]:
        _abschliessen(alt)
    t = {"nr": _naechste_nr(d), "titel": " ".join((titel or "").split())[:TITEL_MAX] or titel_aus(""),
         "status": "offen", "von": von, "erstellt": _jetzt(), "erledigt_am": None,
         "nachrichten": []}
    d["tickets"].append(t)
    d["aktuell"] = t["nr"]
    return t


def _oeffnen(t: dict):
    t["status"] = "offen"
    t["erledigt_am"] = None


# ---------- Die Vorgabe (ohne Modell) ----------
def nachricht(sid: str, uuid: str, text: str, cwd: str = "", vorgabe: dict | None = None) -> dict:
    """Eine neue Nachricht von Kevin ist angenommen. Ordnet sie zu und gibt
    {nr, titel, neu} zurück.

    vorgabe: Kevins Wahl aus dem Chat für eine Session, die es noch nicht gab
    ({"titel": …} oder {"nr": …}); bei bestehenden Sessions steht sie schon
    in der Datei (schnitt/waehlen).
    """
    with _lock(sid):
        d = laden(sid)
        if cwd and not d["cwd"]:
            d["cwd"], d["project"] = cwd, projekt_ordner(cwd)
        t, _m = _wo(d, uuid)
        if t is not None:
            return {"nr": t["nr"], "titel": t["titel"], "neu": False}
        gesperrt = d["gesperrt"]
        if vorgabe and vorgabe.get("titel"):
            ziel, gesperrt = _anlegen(d, str(vorgabe["titel"]), "kevin"), True
        elif vorgabe and _ticket(d, vorgabe.get("nr")):
            ziel, gesperrt = _ticket(d, vorgabe["nr"]), True
            d["aktuell"] = ziel["nr"]
        else:
            ziel = _ticket(d, d["aktuell"])
        neu = ziel is None
        if neu:
            ziel = _anlegen(d, titel_aus(text), "auto")
        # Eine Nachricht auf ein erledigtes Ticket ist eine Korrektur dazu: es
        # geht wieder auf. War sie etwas Neues, legt der Assistent ein neues an
        # (und das alte schließt sich wieder, siehe _heraus).
        msg = {"id": uuid, "ts": _jetzt(), "text": kevins_text(text)[:AUSZUG_MAX],
               "von": "kevin" if gesperrt else "auto"}
        if ziel["status"] == "erledigt" and ziel["erledigt_am"]:
            msg["oeffnete"] = ziel["erledigt_am"]
        _oeffnen(ziel)
        ziel["nachrichten"].append(msg)
        d["gesperrt"] = False
        speichern(d)
        return {"nr": ziel["nr"], "titel": ziel["titel"], "neu": neu}


# ---------- Die Marker des Assistenten ----------
class Abgelehnt(Exception):
    """Eine Zuordnung, die nichts ändert (Kevin hat gewählt, Ticket unbekannt …)."""


def _letzte_frei(d: dict, uuid: str) -> tuple:
    t, m = _wo(d, uuid)
    if m is not None and m["von"] == "kevin":
        raise Abgelehnt(cfg.L(f"{cfg.user_name() or 'Der Nutzer'} hat diese Nachricht selbst "
                              f"#{t['nr']} zugeordnet. Nichts zu tun.",
                              f"{cfg.user_name() or 'The user'} assigned this message to "
                              f"#{t['nr']} themselves. Nothing to do."))
    return t, m


def werkzeug_neu(sid: str, uuid: str, titel: str) -> str:
    titel = " ".join((titel or "").split())[:TITEL_MAX]
    if not titel:
        raise Abgelehnt(cfg.L("Titel fehlt.", "Title missing."))
    with _lock(sid):
        d = laden(sid)
        t, m = _letzte_frei(d, uuid)
        if t is not None and t["von"] == "auto" and [x["id"] for x in t["nachrichten"]] == [uuid]:
            # Der Server hat für genau diese Nachricht schon eins angelegt,
            # weil es keins gab — das ist dasselbe Ticket, es bekommt nur
            # endlich einen richtigen Namen.
            t["titel"], t["von"] = titel, "assistent"
            m["von"] = "assistent"
            d["aktuell"] = t["nr"]
            speichern(d)
            return f"#{t['nr']}"
        if m is not None:
            _heraus(d, uuid)
        neu = _anlegen(d, titel, "assistent")
        if m is not None:
            m["von"] = "assistent"
            neu["nachrichten"].append(m)
        speichern(d)
        return f"#{neu['nr']}"


def werkzeug_zuordnen(sid: str, uuid: str, nr) -> str:
    with _lock(sid):
        d = laden(sid)
        ziel = _ticket(d, _als_nr(nr))
        if ziel is None:
            raise Abgelehnt(cfg.L(f"Ticket #{nr} gibt es in dieser Session nicht.",
                                  f"There is no ticket #{nr} in this session."))
        t, m = _letzte_frei(d, uuid)
        if t is ziel:
            return f"#{ziel['nr']}"
        if m is not None:
            _heraus(d, uuid)
            m["von"] = "assistent"
            ziel["nachrichten"].append(m)
            ziel["nachrichten"].sort(key=lambda x: x["ts"])
        _oeffnen(ziel)
        d["aktuell"] = ziel["nr"]
        speichern(d)
        return f"#{ziel['nr']}"


def _als_nr(v):
    try:
        return int(str(v).lstrip("#"))
    except (TypeError, ValueError):
        return None


# Die Markerzeilen stehen ganz unten in der Antwort. `[[ticket neu: Titel]]`,
# `[[ticket zu: 2]]`, `[[ticket firma]]`.
MARKE_RE = re.compile(r"^\[\[ticket (neu|new|zu|to|firma|company)(?::[ \t]*(.*?))?\]\][ \t]*$", re.I)


def marken_am_ende(text: str) -> tuple:
    """Zerlegt eine Antwort in (Text ohne Marker, [(art, wert), …]).

    Nur zusammenhängende Markerzeilen GANZ UNTEN zählen: ein Marker mitten im Text
    (ein Beispiel, ein Zitat, eine Erklärung dieser Funktion) tut nichts."""
    zeilen = (text or "").rstrip().split("\n")
    marken = []
    while zeilen:
        z = zeilen[-1].strip()
        if not z:
            zeilen.pop()
            continue
        m = MARKE_RE.match(z)
        if not m:
            break
        art = {"new": "neu", "to": "zu", "company": "firma"}.get(m.group(1).lower(), m.group(1).lower())
        marken.append((art, (m.group(2) or "").strip()))
        zeilen.pop()
    marken.reverse()
    return "\n".join(zeilen).rstrip(), marken


def marken_anwenden(sid: str, uuid: str, marken: list) -> list:
    """Setzt die Marker einer Antwort um. Gibt zurück, was die Firma betrifft
    (["firma"]) — das macht der Aufrufer, hier steht nur die Ticket-Arbeit."""
    rest = []
    for art, wert in marken:
        try:
            if art == "neu":
                werkzeug_neu(sid, uuid, wert)
            elif art == "zu":
                werkzeug_zuordnen(sid, uuid, wert)
            elif art == "firma":
                rest.append("firma")
        except Abgelehnt:
            pass          # Kevins Wahl oder unbekanntes Ticket: es bleibt, wie es ist
    return rest


# ---------- Was der Assistent sieht ----------
def hinweis(sid: str | None, vorgabe: str = "") -> str:
    """Die Zeile, die an Kevins Nachricht gehängt wird.

    Absichtlich NICHT im Systemprompt: der steht vor dem ganzen Verlauf, und
    jede Änderung daran macht den Zwischenspeicher der Session wertlos — in
    einer Tages-Session mit 150 000 Tokens Kontext wäre jedes neue Ticket ein
    voller Neuaufbau. Hinten an der Nachricht kostet die Zeile ihre paar
    Tokens und sonst nichts.
    """
    d = laden(sid) if sid and vorhanden(sid) else _leer(sid or "x" * 8)
    if vorgabe:
        # Kevin hat mit /ticket vorab einen Titel gewählt: die Nachricht, an der
        # diese Zeile hängt, wird gleich dessen Ticket.
        d["gesperrt"] = True
        d["tickets"].append({"nr": _naechste_nr(d), "titel": vorgabe[:TITEL_MAX], "status": "offen",
                             "von": "kevin", "erstellt": "", "erledigt_am": None, "nachrichten": []})
        d["aktuell"] = d["tickets"][-1]["nr"]
    ak = _ticket(d, d["aktuell"])
    teile = []

    firma = _firma_stand()

    def kurz(t):
        z = firma(t.get("auftrag"))
        return f"#{t['nr']} „{t['titel']}“" + (f" (Firma {t['auftrag']}: {z})" if z else "")

    if ak:
        zusatz = []
        if ak["status"] == "erledigt":
            zusatz.append(cfg.L("erledigt", "done"))
        if d["gesperrt"]:
            zusatz.append(cfg.L(f"von {cfg.user_name() or 'Nutzer'} gewählt",
                                f"chosen by {cfg.user_name() or 'user'}"))
        teile.append(cfg.L("aktuell ", "current ") + kurz(ak)
                     + (f" ({', '.join(zusatz)})" if zusatz else ""))
    offen = [t for t in reversed(d["tickets"]) if t["status"] == "offen" and t is not ak]
    if offen:
        rest = len(offen) - OFFEN_SICHTBAR
        teile.append(cfg.L("offen ", "open ") + ", ".join(kurz(t) for t in offen[:OFFEN_SICHTBAR])
                     + (cfg.L(f" (+{rest} ältere)", f" (+{rest} older)") if rest > 0 else ""))
    fertig = sorted((t for t in d["tickets"] if t["status"] == "erledigt" and t is not ak),
                    key=lambda t: t["erledigt_am"] or "", reverse=True)[:ERLEDIGT_SICHTBAR]
    if fertig:
        teile.append(cfg.L("erledigt ", "done ") + ", ".join(kurz(t) for t in fertig))
    if not teile:
        teile.append(cfg.L("noch keins", "none yet"))
    return "[Tickets: " + " · ".join(teile) + "]"


def _firma_stand():
    """Funktion auftrag-id → Kurztext ("arbeitet", "wartet auf dich", "fertig") — nur mit
    Team-Modus, sonst immer leer. Die Auftragsdateien liest sie bei Bedarf."""
    if not cfg.load_settings()["team"]["aktiv"]:
        return lambda _id: ""
    from server.team import auftraege as auf
    text = {"neu": "arbeitet", "laeuft": "arbeitet", "wartet_auf_kevin": "wartet auf den Nutzer",
            "wartet_auf_einstellung": "wartet auf den Nutzer", "fertig": "fertig",
            "abgebrochen": "abgebrochen"}

    def stand(aid):
        a = auf.laden(aid) if aid else None
        return text.get(a["status"], "") if a else ""
    return stand


def regeln() -> str:
    """Der feste Teil im Systemprompt. Ändert sich nie während einer Session —
    nur so bleibt er im Zwischenspeicher."""
    wer = cfg.user_name() or cfg.L("der Nutzer", "the user")
    return _tickets_regeln(wer) + _firma_regeln(wer) + _tickets_schluss(wer)


def _firma_regeln(wer: str) -> str:
    """Nur mit Team-Modus: wann eine Aufgabe an die Firma geht. Steht wie der Rest
    im festen Teil des Systemprompts und ändert sich nur, wenn der Nutzer den
    Modus umstellt."""
    team = cfg.load_settings()["team"]
    if not team["aktiv"]:
        return ""
    if team["modus"] == "auto":
        wann = (f"Große Aufgaben (mehrere Dateien oder Schritte, eine Oberfläche, Tests) "
                f"schlägst du {wer} für die Firma vor und fragst, ob sie sie übernehmen soll — "
                f"erst nach seinem Ja schreibst du die Zeile. Alles Kleine erledigst du selbst.")
        when = (f"Big tasks (several files or steps, an interface, tests) you suggest to {wer} "
                f"for the company and ask whether it should take them — only after a yes do you "
                f"write the line. Small things you do yourself.")
    else:
        wann = (f"Die Firma bekommt nur etwas, wenn {wer} es ausdrücklich verlangt "
                f"(„gib das an die Firma“); alles andere erledigst du selbst.")
        when = (f"The company only gets something when {wer} explicitly asks for it "
                f"(“give this to the company”); everything else you do yourself.")
    return cfg.L(
        f"""
- `[[ticket firma]]` — gib dieses Ticket an die Firma (mehrere KI-Mitarbeiter, arbeiten im Hintergrund); ihr Briefing sind {wer}s Nachrichten des Tickets. {wann} Sag {wer} im selben Text, dass du es getan hast, und arbeite nicht selbst daran weiter. Den Stand zeigt die Ticket-Zeile; das Ergebnis steht, wenn es fertig ist, in `firma/auftraege/<Kennung aus der Ticket-Zeile>/ticket.json` (Feld `ergebnis`) — nur lesen, wenn {wer} danach fragt.""",
        f"""
- `[[ticket firma]]` — give this ticket to the company (several AI employees, working in the background); their briefing is {wer}'s messages of the ticket. {when} Tell {wer} in the same text that you did it, and do not keep working on it yourself. The ticket line shows the state; when done, the result is in `firma/auftraege/<id from the ticket line>/ticket.json` (field `ergebnis`) — only read it when {wer} asks.""")


def _tickets_regeln(wer: str) -> str:
    return cfg.L(
        f"""## Tickets
Jede Nachricht von {wer} gehört zu einem Ticket dieser Session; welche es gibt, steht am Ende seiner Nachricht in eckigen Klammern. Ohne dein Zutun landet sie im aktuellen. Willst du das ändern, schreibst du als allerletzte Zeile deiner Antwort:
- `[[ticket neu: Kurztitel]]` — eine neue, eigenständige Aufgabe (3–6 Wörter; das vorige Ticket gilt damit als erledigt)
- `[[ticket zu: 2]]` — die Nachricht gehört zu einem anderen der genannten Tickets""",
        f"""## Tickets
Every message from {wer} belongs to a ticket in this session; the tickets are listed in square brackets at the end of the message. Without action from you it goes to the current one. To change that, write as the very last line of your answer:
- `[[ticket new: short title]]` — a new, separate task (3–6 words; the previous ticket then counts as done)
- `[[ticket to: 2]]` — the message belongs to another listed ticket""")


def _tickets_schluss(wer: str) -> str:
    return cfg.L(
        f"""
Sonst schreibst du nichts davon. Die Zeile wird vor der Anzeige entfernt: erwähne sie nicht. Ist {wer}s Wahl in der Ticket-Zeile vermerkt oder bist du unsicher: nichts.""",
        f"""
Otherwise write none of this. The line is removed before display: do not mention it. If {wer}'s choice is noted in the ticket line or you are unsure: nothing.""")


# ---------- Kevins Eingriffe ----------
def schnitt(sid: str, titel: str, cwd: str = "") -> dict:
    """/ticket Titel: ab der nächsten Nachricht ein neues Ticket."""
    with _lock(sid):
        d = laden(sid)
        if cwd and not d["cwd"]:
            d["cwd"], d["project"] = cwd, projekt_ordner(cwd)
        # Ein leerer Schnitt, der noch auf seine Nachricht wartet, wird ersetzt
        # statt ein zweites leeres Ticket daneben zu stellen.
        ak = _ticket(d, d["aktuell"])
        if ak and not ak["nachrichten"] and d["gesperrt"]:
            d["tickets"].remove(ak)
        _anlegen(d, titel or cfg.L("Neues Ticket", "New ticket"), "kevin")
        d["gesperrt"] = True
        speichern(d)
        return d


def waehlen(sid: str, nr: int) -> dict:
    """Chip über der Eingabe: die nächste Nachricht gehört zu #nr."""
    with _lock(sid):
        d = laden(sid)
        if _ticket(d, nr) is None:
            raise KeyError(nr)
        d["aktuell"], d["gesperrt"] = nr, True
        speichern(d)
        return d


def aendern(sid: str, nr: int, titel=None, status=None) -> dict:
    with _lock(sid):
        d = laden(sid)
        t = _ticket(d, nr)
        if t is None:
            raise KeyError(nr)
        if titel is not None and " ".join(str(titel).split()):
            t["titel"] = " ".join(str(titel).split())[:TITEL_MAX]
            t["von"] = "kevin" if t["von"] == "auto" else t["von"]
        if status in STATUS and status != t["status"]:
            if status == "erledigt":
                t["status"], t["erledigt_am"] = "erledigt", _jetzt()
            else:
                _oeffnen(t)
        speichern(d)
        return d


def umhaengen(sid: str, uuids: list, nr: int) -> dict:
    """Nachrichten von Hand in ein anderes Ticket legen."""
    with _lock(sid):
        d = laden(sid)
        ziel = _ticket(d, nr)
        if ziel is None:
            raise KeyError(nr)
        for u in uuids:
            t, m = _wo(d, u)
            if m is None or t is ziel:
                continue
            _heraus(d, u)
            m["von"] = "kevin"
            ziel["nachrichten"].append(m)
        ziel["nachrichten"].sort(key=lambda x: x["ts"])
        speichern(d)
        return d


def ab_hier(sid: str, uuid: str, titel: str) -> dict:
    """✂ an einer Nachricht: sie und alle späteren ihres Tickets bilden ein neues."""
    with _lock(sid):
        d = laden(sid)
        t, m = _wo(d, uuid)
        if m is None:
            raise KeyError(uuid)
        i = t["nachrichten"].index(m)
        weg = t["nachrichten"][i:]
        del t["nachrichten"][i:]
        vorher = d["aktuell"]
        neu = _anlegen(d, titel or titel_aus(m["text"]), "kevin")
        for x in weg:
            x["von"] = "kevin"
        neu["nachrichten"] = weg
        if vorher != t["nr"]:
            # Ein Schnitt weiter oben im Verlauf verschiebt nicht, wohin die
            # nächste Nachricht geht. War das zerschnittene Ticket das
            # aktuelle, ist es jetzt sein hinterer Teil — der neue.
            d["aktuell"] = vorher
        _aufraeumen(d, t)
        speichern(d)
        return d


def zusammenfuehren(sid: str, von_nr: int, in_nr: int) -> dict:
    with _lock(sid):
        d = laden(sid)
        a, b = _ticket(d, von_nr), _ticket(d, in_nr)
        if a is None or b is None or a is b:
            raise KeyError(von_nr if a is None else in_nr)
        b["nachrichten"] = sorted(b["nachrichten"] + a["nachrichten"], key=lambda x: x["ts"])
        if a.get("auftrag") and not b.get("auftrag"):
            b["auftrag"] = a["auftrag"]       # der Auftrag der Firma bleibt dem Ticket erhalten
        d["tickets"].remove(a)
        if d["aktuell"] == a["nr"]:
            d["aktuell"] = b["nr"]
        if a["status"] == "offen":
            _oeffnen(b)
        speichern(d)
        return d


def loeschen(sid: str, nr: int) -> dict:
    """Ticket weg. Seine Nachrichten gehören danach zu keinem mehr."""
    with _lock(sid):
        d = laden(sid)
        t = _ticket(d, nr)
        if t is None:
            raise KeyError(nr)
        d["tickets"].remove(t)
        if d["aktuell"] == nr:
            d["aktuell"], d["gesperrt"] = None, False
        speichern(d)
        return d


def abzweigen(alt: str, neu: str, behalten: set):
    """✎ Bearbeiten zweigt die Session ab (--fork-session): die neue hat eine
    eigene ID, die Nachrichten bis zur bearbeiteten behalten ihre uuid
    (gemessen 05.10.2026). Die Tickets ziehen mit, ohne die verworfenen
    Nachrichten."""
    if not vorhanden(alt) or vorhanden(neu):
        return
    with _lock(alt):
        d = laden(alt)
    d["session"] = neu
    for t in list(d["tickets"]):
        vorher = len(t["nachrichten"])
        t["nachrichten"] = [m for m in t["nachrichten"] if m["id"] in behalten]
        if vorher and not t["nachrichten"]:
            # Alles, was dieses Ticket ausmachte, ist abgeschnitten.
            d["tickets"].remove(t)
            if d["aktuell"] == t["nr"]:
                d["aktuell"] = None
    # Es geht dort weiter, wo die letzte behaltene Nachricht stand — und das Ticket
    # ist wieder offen, auch wenn die verworfene Fortsetzung es geschlossen hatte.
    rest = [(m["ts"], t) for t in d["tickets"] for m in t["nachrichten"]]
    if rest:
        letztes = max(rest, key=lambda x: x[0])[1]
        d["aktuell"] = letztes["nr"]
        _oeffnen(letztes)
    d["gesperrt"] = False
    with _lock(neu):
        speichern(d)


# ---------- Übersicht ----------
_CACHE: dict[str, tuple] = {}


def _alle() -> list:
    """Alle Session-Dateien, gelesen nur, wenn sie sich geändert haben."""
    out = []
    if not TICKETS_DIR.exists():
        return out
    for p in TICKETS_DIR.glob("*.json"):
        if not SID_RE.match(p.stem):
            continue                      # eine Kopie oder Sicherung von Hand — gehört nicht dazu
        try:
            st = p.stat()
        except OSError:
            continue
        stand = (st.st_mtime_ns, st.st_size)
        hit = _CACHE.get(p.stem)
        if not hit or hit[0] != stand:
            try:
                hit = (stand, laden(p.stem))
            except Exception:
                continue                  # eine kaputte Datei darf die Übersicht nicht zerlegen
            _CACHE[p.stem] = hit
        out.append(hit[1])
    return out


def _tag(ts: str) -> str:
    return (ts or "")[:10]


def uebersicht(namen: dict | None = None) -> dict:
    """Tag → Projekt → Tickets, für Kachel und Tafel.

    Ein Ticket steht an jedem Tag, an dem es eine Nachricht bekam — wer am
    nächsten Morgen in derselben Session weitermacht, sieht es dort wieder.
    Ohne Nachricht zählt der Tag, an dem es angelegt wurde.
    """
    namen = namen or {}
    tage: dict[str, dict] = {}
    for d in _alle():
        name = Path(d["cwd"]).name if d["cwd"] else "?"
        for t in d["tickets"]:
            an = sorted({_tag(m["ts"]) for m in t["nachrichten"] if m["ts"]} or {_tag(t["erstellt"])})
            for tag in an:
                if not tag:
                    continue
                projekte = tage.setdefault(tag, {})
                p = projekte.setdefault(d["cwd"], {"cwd": d["cwd"], "name": name, "tickets": []})
                p["tickets"].append({
                    "session": d["session"], "project": d["project"],
                    "session_titel": namen.get(d["session"], ""),
                    "nr": t["nr"], "titel": t["titel"], "status": t["status"],
                    "von": t["von"], "erstellt": t["erstellt"], "erledigt_am": t["erledigt_am"],
                    "auftrag": t.get("auftrag"),
                    "aktuell": d["aktuell"] == t["nr"],
                    "nachrichten": [m for m in t["nachrichten"] if _tag(m["ts"]) == tag],
                    "gesamt": len(t["nachrichten"]),
                })
    out = []
    for tag in sorted(tage, reverse=True):
        projekte = []
        for p in tage[tag].values():
            p["tickets"].sort(key=lambda t: (t["nachrichten"][0]["ts"] if t["nachrichten"]
                                             else t["erstellt"]))
            p["offen"] = sum(1 for t in p["tickets"] if t["status"] == "offen")
            p["erledigt"] = len(p["tickets"]) - p["offen"]
            projekte.append(p)
        projekte.sort(key=lambda p: max((t["nachrichten"][-1]["ts"] if t["nachrichten"]
                                         else t["erstellt"]) for t in p["tickets"]), reverse=True)
        out.append({"tag": tag, "projekte": projekte})
    return {"tage": out}
