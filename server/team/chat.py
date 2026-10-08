"""Die Firma im Chat.

Früher gab es den Chat mit dem Assistenten UND daneben eine eigene Auftragssicht —
zweimal dasselbe, nur einmal delegiert, und im Raum stritten sich beide ums
Protokoll. Jetzt gibt es nur den Chat: der Assistent gibt die Aufgabe an die
Firma, und die Mitarbeiter schreiben in DENSELBEN Chat (ein Gruppenchat). Der Auftrag bleibt als Ablage
für Bus, Bremsen und Verlauf bestehen, hängt aber fest an der Session
(`bruecke.session`).

Ob übergeben wird, entscheidet seit 8.1.0 der Schalter (Team-Modus an = die Firma
arbeitet), nicht mehr der Assistent nach Größe der Aufgabe: das Abwägen und
Nachfragen war Komplexität ohne Nutzen.

Übergabe: Der Assistent schreibt den Auftrag als Antwort und als letzte Zeile
`[[firma: Kurztitel]]`. Eine Markerzeile statt eines Werkzeugs, aus demselben
Grund wie früher bei den Tickets: ein MCP-Server kostet je Nachricht Sekunden und
Kontext, die Zeile nur dann, wenn sie gebraucht wird.

Rückweg: Was die Firma geliefert hat (oder dass sie wartet), bekommt der
Assistent an der nächsten Nachricht des Nutzers in dieser Session mit.
"""
import json
import re
import threading
import time
import uuid

from server import config as cfg

# Nur ganze Zeilen am Ende zählen; `[[ticket …]]` steht noch in alten Verläufen.
MARKE_RE = re.compile(r"^\s*\[\[(?:firma|company|ticket)\b[^\]\n]*\]\]\s*$", re.I)
FIRMA_RE = re.compile(r"^\s*\[\[(?:firma|company)\s*:?\s*(?P<titel>[^\]\n]*)\]\]\s*$", re.I)
# Was an die Nachricht des Nutzers gehängt wird (meldungen): für den Assistenten,
# nicht für die Anzeige.
MELDUNG_RE = re.compile(r"\n\n\[(?:Firma|Company|Tickets): [\s\S]*?\]\s*$")


def ohne_marke(text: str) -> str:
    """Antwort ohne die Markerzeilen am Ende."""
    if "[[" not in (text or ""):
        return text
    zeilen = text.rstrip().split("\n")
    while zeilen and MARKE_RE.match(zeilen[-1]):
        zeilen.pop()
    return "\n".join(zeilen).rstrip()


def ohne_meldung(text: str) -> str:
    return MELDUNG_RE.sub("", text or "")


def marke(text: str) -> str | None:
    """Kurztitel aus `[[firma: Titel]]` am Ende, "" ohne Titel, None ohne Zeile."""
    for zeile in reversed((text or "").rstrip().split("\n")):
        if not zeile.strip():
            continue
        m = FIRMA_RE.match(zeile)
        if m:
            return m.group("titel").strip()
        if not MARKE_RE.match(zeile):
            return None
    return None


def _belegschaft() -> str:
    """„Elara: Frontend und Gestaltung; Luna: …“ — die Namen verankern den Begriff.
    Ohne sie fand der Assistent in einer anderen Session „die Firma“ nicht und hielt
    ein altes Projekt namens FACTORIA dafür (07.10.2026)."""
    from server.core import WORKSPACE
    from server.team import agents as ag
    try:
        leute = [a for a in ag.list_agents(WORKSPACE) if a["slug"] != ag.OWNER_SLUG and a["status"] == "active"]
    except Exception:
        return ""
    return "; ".join(f"{a['name']}: {a['title']}" if a.get("title") else a["name"] for a in leute)


def regeln() -> str:
    """Fester Teil im Systemprompt, nur mit Team-Modus. Ändert sich nur, wenn sich
    die Belegschaft ändert — so bleibt er im Zwischenspeicher."""
    wer = cfg.user_name()
    leute = _belegschaft()
    return cfg.L(
        f"""## Firma
„Die Firma“ ist der Team-Modus dieser CONSTRUCT-Installation: KI-Mitarbeiter, die du als Geschäftsführung leitest{f': {leute}' if leute else ''}. Spricht {wer} von der Firma, ist immer sie gemeint, kein anderes Programm oder Projekt, und das in jeder Session und jedem Projektordner. Ihre Nachrichten erscheinen in diesem Chat.
Ob die Firma arbeitet, entscheidet der Schalter, nicht du: Solange der Team-Modus an ist, gibst du jede Aufgabe, bei der etwas gebaut, geändert, geprüft oder getestet wird, ohne Rückfrage an die Firma, egal wie klein. Selbst machst du nur Fragen, Erklärungen, Plaudern, Kalender, Mails und was {wer} ausdrücklich dir aufträgt („mach du“). Ist unklar, was {wer} will, fragst du vor der Übergabe nach.
Übergeben wird nur so: Du schreibst den Auftrag als Antwort (was, wo, worauf achten, wann fertig) und als allerletzte Zeile `[[firma: Kurztitel]]` (Ticket gemeint: `[[firma: T-12 Kurztitel]]`). Keine API, kein Skript: nur über diese Zeile schreibt die Firma in diesen Chat. Danach arbeitest du nicht selbst daran. Die Zeile wird vor der Anzeige entfernt, erwähne sie nicht. Was die Firma liefert, bekommst du mit der nächsten Nachricht.""",
        f"""## Company
"The company" is the team mode of this CONSTRUCT installation: AI employees you lead as managing director{f': {leute}' if leute else ''}. When {wer} talks about the company, it always means them, no other program or project, in every session and project folder. Their messages appear in this chat.
Whether the company works is decided by the switch, not by you: as long as team mode is on, every task that builds, changes, reviews or tests something goes to the company without asking, however small. You only handle questions, explanations, chatting, calendar, mail and whatever {wer} explicitly gives to you ("do it yourself"). If it is unclear what {wer} wants, ask before handing over.
Handing over works only like this: write the job as your answer (what, where, what to watch, when it is done) and as the very last line `[[company: short title]]` (for a ticket: `[[company: T-12 short title]]`). No API, no script: only through this line does the company write in this chat. Then do not work on it yourself. The line is removed before display, do not mention it. You receive what the company delivers with the next message.""")


def uebergeben(text: str, session: str, cwd: str) -> dict | None:
    """Steht am Ende der Antwort `[[firma: …]]`, geht die Aufgabe an die Firma.
    Der Auftrag ist die Antwort selbst (ohne die Zeile)."""
    titel = marke(text)
    if titel is None:
        return None
    from server import tickets as tk
    from server.team import engine
    ticket = None
    m = tk.VERWEIS_RE.search(titel)
    if m:
        ticket = int(m.group(1))
        titel = tk.VERWEIS_RE.sub("", titel).strip(" :–-")
    brief = ohne_marke(text).strip()
    if ticket:
        t = tk.holen(ticket)
        if t and t["text"]:
            brief = f"T-{ticket} {t['titel']}\n\n{t['text']}\n\n{brief}".strip()
    engine.starten()            # zuerst: der Dispatcher nimmt Altes wieder auf, dann kommt Neues
    return engine.auftrag_anlegen(titel or brief[:80], brief or titel, cwd,
                                  bruecke={"session": session}, ticket=ticket)


def auftraege_der_session(session: str) -> list:
    from server.team import auftraege as auf
    return [t for t in auf.alle() if (t.get("bruecke") or {}).get("session") == session]


STAND = {"de": {"fertig": "fertig", "abgebrochen": "abgebrochen", "wartet_auf_kevin": "wartet auf {wer}"},
         "en": {"fertig": "done", "abgebrochen": "cancelled", "wartet_auf_kevin": "waiting for {wer}"}}


async def meldungen(session: str) -> str:
    """Was sich bei der Firma getan hat, seit der Assistent zuletzt hingesehen hat —
    als Zeile an die Nachricht des Nutzers. Jeder Stand wird einmal gemeldet."""
    if not session:
        return ""
    from server.team import engine
    teile = []
    wer = cfg.user_name()
    for t in auftraege_der_session(session):
        if t["status"] not in ("fertig", "abgebrochen", "wartet_auf_kevin"):
            continue
        if t.get("gemeldet") == t["status"]:
            continue
        stand = STAND[cfg.lang() if cfg.lang() in STAND else "de"][t["status"]].format(wer=wer)
        zeile = f"„{t['titel']}“ ({t['id']}): {stand}"
        if t["status"] == "fertig" and t.get("ergebnis"):
            zeile += cfg.L(". Ergebnis: ", ". Result: ") + " ".join(str(t["ergebnis"]).split())[:1500]
        elif t["status"] == "wartet_auf_kevin":
            esk = t.get("eskalation") or {}
            frage = esk.get("frage") or esk.get("grund") or ""
            if frage:
                zeile += ": " + " ".join(str(frage).split())[:400]
        teile.append(zeile)
        status = t["status"]
        # Unter dem Schloss des Auftrags: der Dispatcher schreibt dieselbe Datei.
        await engine.auftrag_aendern(t["id"], lambda x, s=status: x.update({"gemeldet": s}))
    if not teile:
        return ""
    return "\n\n[" + cfg.L("Firma", "Company") + ": " + " · ".join(teile) + "]"


# ---------- Nicht zugestellt ----------
# War der Team-Modus am Zugende aus, ging die Übergabe früher still verloren: die
# Oberfläche blendet die Markerzeile aus, also sah niemand, dass nichts ankam
# (08.10.2026). Jetzt bleibt sie hier liegen, bis der Nutzer sie per Knopf
# nachreicht. Einschalten allein startet nichts: ob eine alte Aufgabe noch gilt,
# entscheidet der Nutzer, nicht der Schalter.
# Ablage: firma/nicht_zugestellt.json, {session: [eintrag, …]}.
_SPERRE = threading.Lock()
PRO_SESSION = 20


def _ablage():
    from server.team import agents as ag
    return ag.FIRMA_DIR / "nicht_zugestellt.json"


def _lesen() -> dict:
    try:
        d = json.loads(_ablage().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return d if isinstance(d, dict) else {}


def _schreiben(d: dict):
    p = _ablage()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(p)


def _anzeige(e: dict) -> dict:
    return {k: e.get(k) for k in ("id", "titel", "status", "erstellt", "auftrag")}


def zurueckhalten(text: str, session: str, cwd: str) -> dict | None:
    """Übergabe bei ausgeschaltetem Team-Modus: nicht anlegen, sondern merken.
    Gemerkt wird die ganze Antwort samt Zeile — `nachholen` gibt sie dann genau so
    an `uebergeben`, wie es am Zugende passiert wäre (Ticketverweis inklusive)."""
    titel = marke(text)
    if titel is None or not session:
        return None
    e = {"id": uuid.uuid4().hex[:8], "titel": titel or ohne_marke(text).strip()[:80],
         "text": text, "cwd": cwd, "status": "offen", "erstellt": time.time(),
         "gemeldet": False, "auftrag": None}
    with _SPERRE:
        d = _lesen()
        d[session] = (d.get(session) or [])[-(PRO_SESSION - 1):] + [e]
        _schreiben(d)
    return _anzeige(e)


def nicht_zugestellt(session: str) -> list:
    return [_anzeige(e) for e in _lesen().get(session) or []]


class NichtOffen(Exception):
    pass


def nachholen(session: str, eid: str) -> tuple[dict, dict]:
    """Der Knopf: die gemerkte Übergabe jetzt an die Firma. Unter der Sperre, damit
    ein Doppelklick nicht zwei Aufträge anlegt. AuftragFehler geht durch, der
    Eintrag bleibt dann offen."""
    with _SPERRE:
        d = _lesen()
        e = next((x for x in d.get(session) or [] if x.get("id") == eid), None)
        if not e or e.get("status") != "offen":
            raise NichtOffen(eid)
        t = uebergeben(e["text"], session, e.get("cwd") or "")
        if not t:
            raise NichtOffen(eid)
        e.update(status="uebergeben", auftrag=t["id"])
        _schreiben(d)
    return _anzeige(e), t


def nicht_angekommen(session: str) -> str:
    """Wie `meldungen`, aber unabhängig vom Schalter: offene Übergaben, von denen
    der Assistent noch nichts weiß, einmal an die Nachricht des Nutzers."""
    if not session:
        return ""
    with _SPERRE:
        d = _lesen()
        neu = [e for e in d.get(session) or [] if e.get("status") == "offen" and not e.get("gemeldet")]
        if not neu:
            return ""
        for e in neu:
            e["gemeldet"] = True
        _schreiben(d)
    titel = ", ".join(f"„{e['titel']}“" for e in neu)
    if len(neu) == 1:
        satz = cfg.L(f"Übergabe {titel} nicht angekommen, der Team-Modus war aus.",
                     f"handover {titel} did not arrive, team mode was off.")
    else:
        satz = cfg.L(f"Übergaben {titel} nicht angekommen, der Team-Modus war aus.",
                     f"handovers {titel} did not arrive, team mode was off.")
    return "\n\n[" + cfg.L("Firma", "Company") + ": " + satz + "]"
