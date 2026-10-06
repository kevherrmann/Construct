"""Die Bremsen — damit sich die Firma nicht im Kreis dreht.

Kevins Anforderung von Anfang an: die Agenten sollen untereinander reden, aber
irgendwann muss Schluss sein und ich muss geholt werden. Das ist hier
umgesetzt, in Schichten von grob nach fein.

Es gibt hier KEIN Budget mehr, das pro Auftrag mitgegeben wird — die Zahlen
unten sind feste Notbremsen fuer alle Auftraege. Sie sollen eine Endlosschleife
zwischen zwei Agenten beenden, nicht die Arbeit planen. Wer sie beim Arbeiten
im Kopf haben muss, hat schon verloren; darum sieht ein Agent sie erst, wenn es
eng wird.

Wichtig zum Verstaendnis: die WIRKSAMSTE Schicht steht gar nicht hier, sondern
in PROTOCOL.md — die Regeln im Systemprompt ("hoechstens ein beauftragen pro
Zug", "wuerdest du dieselbe Frage zweimal stellen, eskaliere"). Was hier steht,
ist das Sicherheitsnetz fuer den Fall, dass ein Modell sich nicht daran haelt.

Jede Ausloesung endet gleich: Auftrag pausiert, Kevin wird geholt, nichts
laeuft weiter. Erst wenn er "weitermachen" sagt, faengt die Zaehlung von vorn
an — genau darum geht es, eine Ausloesung soll eine menschliche Entscheidung
erzwingen.
"""
import difflib
import time

from server import config as cfg

# --- Die harten Grenzen. Gelten fuer jeden Auftrag gleich. ---
HIN_UND_HER_MAX = 10   # Nachrichten zwischen DENSELBEN zwei — Kevins Endlosschleifen-Bremse
SCHRITTE_MAX = 40      # geroutete Nachrichten im ganzen Auftrag
TIEFE_MAX = 3          # Laenge der Delegationskette
WARNUNG_AB = 6         # ab so wenig Restschritten steht ein Hinweis im Zug

# Ab dieser Aehnlichkeit gilt eine Nachricht als Wiederholung. 0.92 ist streng
# genug, dass umformulierte Nachfragen noch durchgehen, aber wortgleiches
# Nachhaken auffaellt.
AEHNLICH = 0.92
PINGPONG_ZYKLEN = 3       # A->B->A->B->A->B ohne Fortschritt
OHNE_ARTEFAKT_MAX = 6     # Lieferungen von Schreibenden ohne eine einzige Datei


def _norm(s: str) -> str:
    return " ".join(str(s or "").lower().split())


def _paar(e: dict) -> tuple:
    """Wer mit wem — ungerichtet, damit Hin und Her dasselbe Paar ist."""
    return tuple(sorted((e.get("von") or "", e.get("an") or "")))


def geroutet(t: dict, verlauf: list) -> list:
    """Die zaehlenden Nachrichten SEIT der letzten Freigabe durch Kevin.

    Nach einem "weitermachen" faengt jede Zaehlung von vorn an. Ohne diesen
    Schnitt haette Kevin nach dem ersten Anhalten nur noch einen Auftrag, der
    sofort wieder anhaelt.
    """
    frei = (t.get("wache") or {}).get("frei_seit") or 0
    # Einwuerfe von Kevin in einen laufenden Zug sind keine Schritte der
    # Firma — sie zaehlten aber mit, weil sie einen Empfaenger haben.
    return [e for e in verlauf
            if e.get("an") and e.get("art") not in ("zugestellt", "einwurf")
            and e.get("ts", 0) >= frei]


def rest_schritte(t: dict, verlauf: list) -> int:
    return max(0, SCHRITTE_MAX - len(geroutet(t, verlauf)))


def pruefe(t: dict, nachricht: dict, verlauf: list) -> tuple:
    """Vor jeder Zuteilung. Gibt (bremse, grund) zurueck oder (None, "").

    Die Reihenfolge ist Absicht: erst die billigen Zaehler, dann die teuren
    Textvergleiche (die stehen in pruefe_nach_zug).
    """
    liste = geroutet(t, verlauf)

    # --- Zwei, die nicht mehr aufhoeren ---
    a, b = _paar(nachricht)
    zwischen = sum(1 for e in liste if _paar(e) == (a, b))
    if zwischen >= HIN_UND_HER_MAX:
        return "hin_und_her", cfg.L(f"{a} und {b} haben {zwischen} Nachrichten ausgetauscht "
                                    f"(erlaubt sind {HIN_UND_HER_MAX}). Das dreht sich im Kreis.",
                                    f"{a} and {b} have exchanged {zwischen} messages "
                                    f"({HIN_UND_HER_MAX} allowed). This is going in circles.")

    if len(liste) >= SCHRITTE_MAX:
        return "schritte", cfg.L(f"Der Auftrag hat {len(liste)} Schritte gebraucht (erlaubt sind "
                                 f"{SCHRITTE_MAX}), ohne fertig zu werden.",
                                 f"The job took {len(liste)} steps ({SCHRITTE_MAX} allowed) "
                                 f"without getting done.")

    tiefe = int(nachricht.get("tiefe") or 0)
    if tiefe > TIEFE_MAX:
        return "tiefe", cfg.L(f"Die Aufgabe wurde {tiefe} Mal weitergereicht (erlaubt: "
                              f"{TIEFE_MAX}). Sie wird herumgeschoben statt erledigt.",
                              f"The task was passed on {tiefe} times ({TIEFE_MAX} allowed). "
                              f"It is being pushed around instead of done.")

    return None, ""


def pruefe_nach_zug(t: dict, verlauf: list) -> tuple:
    """Nach jedem Zug — hier stehen die Erkennungen, die Verlauf brauchen.

    Diese greifen frueher als HIN_UND_HER_MAX: zehn Nachrichten sind die harte
    Obergrenze, aber wenn schon nach dreien nichts entsteht, muss niemand
    warten, bis sie voll ist.
    """
    liste = geroutet(t, verlauf)

    # --- Ping-Pong: dieselben zwei reden hin und her, ohne dass etwas entsteht ---
    letzte = liste[-(PINGPONG_ZYKLEN * 2):]
    if len(letzte) >= PINGPONG_ZYKLEN * 2:
        paare = {(e.get("von"), e.get("an")) for e in letzte}
        wechselseitig = len(paare) == 2 and all((b, a) in paare for a, b in paare)
        # Eine ANTWORT ist Fortschritt: Frage, Antwort, naechste Frage ist genau
        # die Zusammenarbeit, die PROTOCOL.md erlaubt. Ohne "antwort" hier
        # fiel die Bremse nach drei sauber beantworteten Rueckfragen —
        # nachgestellt am 04.09.2026. Was bleibt, ist der echte Kreis: beide
        # fragen oder beauftragen, keiner antwortet oder liefert.
        fortschritt = any(e.get("art") in ("ergebnis", "artefakt", "antwort")
                          or e.get("dateien") for e in letzte)
        if wechselseitig and not fortschritt:
            a, b = list(paare)[0]
            return "pingpong", cfg.L(f"{a} und {b} schreiben seit {PINGPONG_ZYKLEN} Runden hin und "
                                     f"her, ohne dass ein Ergebnis entsteht.",
                                     f"{a} and {b} have gone back and forth for {PINGPONG_ZYKLEN} "
                                     f"rounds without producing a result.")

    # --- Stillstand: jemand wiederholt sich fast woertlich ---
    for e in liste[-1:]:
        frueher = [x for x in liste[:-1]
                   if x.get("von") == e.get("von") and x.get("an") == e.get("an")][-3:]
        for f in frueher:
            q = difflib.SequenceMatcher(None, _norm(f.get("text")), _norm(e.get("text"))).ratio()
            if q > AEHNLICH:
                return "wiederholung", cfg.L(f"{e.get('von')} schreibt fast wortgleich dasselbe wie "
                                             f"vorhin ({int(q * 100)} % Übereinstimmung) — es geht "
                                             f"nicht voran.",
                                             f"{e.get('von')} is writing almost the same as before "
                                             f"({int(q * 100)} % match) — no progress.")

    # --- Kein Artefakt seit N Lieferungen ---
    # Gezaehlt wird in app.py (_buchen): nur `liefern` von Leuten, die
    # schreiben duerfen. Antworten und Lieferungen der Geschaeftsfuehrung oder
    # eines Pruefers ohne Write zaehlen nicht — sonst hielt ein reiner
    # Recherche- oder Pruefauftrag nach sechs Texten an.
    if t["wache"].get("ohne_artefakt", 0) >= OHNE_ARTEFAKT_MAX:
        return "kein_fortschritt", cfg.L(f"{OHNE_ARTEFAKT_MAX} Lieferungen hintereinander ohne "
                                         f"eine geänderte Datei. Es wird geredet statt gearbeitet.",
                                         f"{OHNE_ARTEFAKT_MAX} deliveries in a row without a single "
                                         f"changed file. There is talk instead of work.")
    return None, ""


def freigeben(t: dict):
    """Kevin sagt weitermachen: alle Zaehler fangen von vorn an."""
    t.setdefault("wache", {})["frei_seit"] = time.time()
    t["wache"]["ohne_artefakt"] = 0


# Fuer die Oberflaeche: was der Nutzer beim Anhalten lesen soll (name() gibt
# es in seiner Sprache; die Oberflaeche uebersetzt die Kuerzel selbst).
NAMEN_EN = {
    "hin_und_her": "endless loop between two",
    "schritte": "too many steps",
    "tiefe": "delegation depth",
    "pingpong": "ping-pong detected",
    "wiederholung": "repetition detected",
    "kein_fortschritt": "no progress",
    "stille": "turn hangs",
    "fehler": "turn ended with an error",
    "zug_timeout": "turn timed out",
    "stiller_zug": "turn without a message",
    "neustart": "server restart",
    "gestoppt": "turn stopped",
    "eskaliert": "question from the company",
    "unbekannt": "unknown recipient",
    "akte": "staff file blocks the work",
}


def name(bremse: str) -> str:
    return cfg.L(NAMEN.get(bremse, bremse), NAMEN_EN.get(bremse, bremse))


NAMEN = {
    "hin_und_her": "Endlosschleife zwischen zwei",
    "schritte": "zu viele Schritte",
    "tiefe": "Delegationstiefe",
    "pingpong": "Ping-Pong erkannt",
    "wiederholung": "Wiederholung erkannt",
    "kein_fortschritt": "kein Fortschritt",
    "stille": "Zug haengt",
    "fehler": "Zug mit Fehler beendet",
    "zug_timeout": "Zug abgelaufen",          # alte Auftraege, Grenze gibt es nicht mehr
    "stiller_zug": "Zug ohne Aussage",
    "neustart": "Serverneustart",
    "gestoppt": "Zug gestoppt",
    "eskaliert": "Rückfrage aus der Firma",
    "unbekannt": "Empfänger unbekannt",
    "akte": "Personalakte blockiert die Arbeit",
}
