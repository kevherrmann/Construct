"""Die Firma im Chat.

Früher gab es den Chat mit dem Assistenten UND daneben eine eigene Auftragssicht —
zweimal dasselbe, nur einmal delegiert, und im Raum stritten sich beide ums
Protokoll. Jetzt gibt es nur den Chat: der Assistent fragt bei einer großen
Aufgabe, ob sie an die Firma gehen darf, und nach dem Ja schreiben die
Mitarbeiter in DENSELBEN Chat (ein Gruppenchat). Der Auftrag bleibt als Ablage
für Bus, Bremsen und Verlauf bestehen, hängt aber fest an der Session
(`bruecke.session`).

Übergabe: Der Assistent schreibt den Auftrag als Antwort und als letzte Zeile
`[[firma: Kurztitel]]`. Eine Markerzeile statt eines Werkzeugs, aus demselben
Grund wie früher bei den Tickets: ein MCP-Server kostet je Nachricht Sekunden und
Kontext, die Zeile nur dann, wenn sie gebraucht wird.

Rückweg: Was die Firma geliefert hat (oder dass sie wartet), bekommt der
Assistent an der nächsten Nachricht des Nutzers in dieser Session mit.
"""
import re

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


def regeln() -> str:
    """Fester Teil im Systemprompt, nur mit Team-Modus."""
    wer = cfg.user_name()
    return cfg.L(
        f"""## Firma
Du hast eine Firma aus KI-Mitarbeitern, die im Hintergrund arbeiten; ihre Nachrichten erscheinen in diesem Chat. Große Aufgaben (mehrere Dateien oder Schritte, Oberfläche, Tests) schlägst du {wer} vor und fragst, ob du sie an die Firma geben darfst; Kleines machst du selbst. Verlangt {wer} es ausdrücklich, fragst du nicht nach.
Nach dem Ja schreibst du den Auftrag als Antwort (was, wo, worauf achten, wann fertig) und als allerletzte Zeile `[[firma: Kurztitel]]` (Ticket gemeint: `[[firma: T-12 Kurztitel]]`). Danach arbeitest du nicht selbst daran. Die Zeile wird vor der Anzeige entfernt, erwähne sie nicht. Was die Firma liefert, bekommst du mit der nächsten Nachricht.""",
        f"""## Company
You have a company of AI employees working in the background; their messages appear in this chat. Big tasks (several files or steps, interface, tests) you suggest to {wer} and ask whether you may give them to the company; small things you do yourself. If {wer} explicitly asks for it, don't ask back.
After a yes, write the job as your answer (what, where, what to watch, when it is done) and as the very last line `[[company: short title]]` (for a ticket: `[[company: T-12 short title]]`). Then do not work on it yourself. The line is removed before display, do not mention it. You receive what the company delivers with the next message.""")


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
