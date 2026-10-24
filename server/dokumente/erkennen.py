"""Was sich aus dem gelesenen Text ableiten lässt.

Datum: das erste plausible Datum im Kopf des Schreibens. Briefe nennen ihr
eigenes Datum fast immer vor allen anderen (Fristen, Zeiträume kommen später).

Absender, Typ und Tags: ein naiver Bayes-Klassifikator über die Wörter der
schon einsortierten Dokumente. Er wird bei jedem Vorschlag frisch aus der
Datenbank gerechnet. Bei ein paar tausend Dokumenten dauert das Millisekunden,
und es gibt kein Modell, das veralten oder kaputtgehen kann. Gelernt wird nur
aus Dokumenten, die jemand bestätigt hat (nicht mehr im Eingang): sonst lernt
er aus seinen eigenen Fehlern.
"""
import math
import re
from collections import Counter
from datetime import date

MONATE = {
    "januar": 1, "jänner": 1, "februar": 2, "märz": 3, "maerz": 3, "april": 4, "mai": 5,
    "juni": 6, "juli": 7, "august": 8, "september": 9, "oktober": 10, "november": 11,
    "dezember": 12, "january": 1, "february": 2, "march": 3, "may": 5, "june": 6,
    "july": 7, "october": 10, "december": 12,
}
_ZAHL = re.compile(r"(?<!\d)(\d{1,2})\.\s?(\d{1,2})\.\s?(\d{4}|\d{2})(?!\d)")
_WORT = re.compile(r"(?<!\d)(\d{1,2})\.?\s+(" + "|".join(MONATE) + r")\s+(\d{4})(?!\d)", re.I)
_ISO = re.compile(r"(?<!\d)(\d{4})-(\d{2})-(\d{2})(?!\d)")
KOPF = 2500          # nur so weit vorne suchen, dahinter stehen Fristen und Zeiträume


def _jahr(j: str) -> int:
    n = int(j)
    if len(j) == 2:
        n += 2000 if n <= date.today().year % 100 else 1900
    return n


def datum(text: str, heute: date | None = None) -> str | None:
    """Erstes plausibles Datum (ISO) im Kopf des Textes oder None."""
    heute = heute or date.today()
    kopf = text[:KOPF]
    funde = []
    for m in _ZAHL.finditer(kopf):
        funde.append((m.start(), int(m.group(1)), int(m.group(2)), _jahr(m.group(3))))
    for m in _WORT.finditer(kopf):
        funde.append((m.start(), int(m.group(1)), MONATE[m.group(2).lower()], int(m.group(3))))
    for m in _ISO.finditer(kopf):
        funde.append((m.start(), int(m.group(3)), int(m.group(2)), int(m.group(1))))
    for _, t, mo, j in sorted(funde):
        try:
            d = date(j, mo, t)
        except ValueError:
            continue
        # Geburtsdaten und Druckvermerke ("Fassung Juli 2016") sind älter als
        # das Schreiben, Fälligkeiten liegen in der Zukunft: beides kein Briefdatum.
        if date(1970, 1, 1) <= d <= heute:
            return d.isoformat()
    return None


# ---------- Wörter ----------

_TOKEN = re.compile(r"[a-zäöüß][a-zäöüß0-9\-]{2,}", re.I)
_STOPP = set("""
und oder der die das den dem des ein eine einer eines einem einen mit von vom für auf aus bei
bis nach über unter zum zur ist sind wird werden wurde wurden hat haben sie ihr ihre ihnen wir
uns unser nicht auch als wie wenn dass daß sich sehr bitte geehrte geehrter sehr damen herren
herr herrn frau mit freundlichen grüßen gruß seite the and for you your this that with
""".split())


def woerter(text: str) -> set[str]:
    """Wortmenge eines Dokuments. Menge statt Häufigkeit: ein Bescheid, der
    zwanzigmal "Euro" sagt, soll nicht zwanzigfach zählen."""
    return {w.lower() for w in _TOKEN.findall(text[:20000])} - _STOPP


# ---------- Klassifikator ----------

class Bayes:
    """Naiver Bayes für eine Eigenschaft (Absender oder Typ): Klasse = id."""

    def __init__(self, beispiele: list[tuple[set[str], int]]):
        self.n = len(beispiele)
        self.klassen = Counter(k for _, k in beispiele)
        self.wort_je_klasse: dict[int, Counter] = {k: Counter() for k in self.klassen}
        for ws, k in beispiele:
            self.wort_je_klasse[k].update(ws)
        self.vokabel = set().union(*(c.keys() for c in self.wort_je_klasse.values())) if beispiele else set()

    def wahrscheinlichkeiten(self, ws: set[str]) -> dict[int, float]:
        if not self.klassen:
            return {}
        ws = ws & self.vokabel
        logp = {}
        for k, anzahl in self.klassen.items():
            c = self.wort_je_klasse[k]
            # Bernoulli-Modell: Anteil der Dokumente der Klasse, die das Wort enthalten
            lp = math.log(anzahl / self.n)
            for w in ws:
                lp += math.log((c[w] + 1) / (anzahl + 2))
            logp[k] = lp
        top = max(logp.values())
        roh = {k: math.exp(v - top) for k, v in logp.items()}
        summe = sum(roh.values())
        return {k: v / summe for k, v in roh.items()}

    def bestes(self, ws: set[str], mindest: float = 0.6) -> int | None:
        # Mit nur einer bekannten Klasse wäre jede Antwort diese Klasse:
        # der erste Absender würde zum Absender von allem.
        if len(self.klassen) < 2:
            return None
        p = self.wahrscheinlichkeiten(ws)
        if not p:
            return None
        k = max(p, key=p.get)
        return k if p[k] >= mindest else None


def _name_im_text(name: str, text: str) -> bool:
    teile = [re.escape(t) for t in name.split() if t]
    if not teile:
        return False
    return re.search(r"(?<!\w)" + r"\s+".join(teile) + r"(?!\w)", text, re.I) is not None


def absender(text: str, ws: set[str], beispiele: list[tuple[set[str], int]],
             namen: dict[int, str]) -> int | None:
    """Steht genau ein bekannter Absender wörtlich im Text, gewinnt er: das
    ist sicherer als jede Statistik (ein Bescheid vom Finanzamt, adressiert an
    den Steuerberater, klingt sonst nach Steuerberater)."""
    treffer = [i for i, n in namen.items() if _name_im_text(n, text[:KOPF])]
    if len(treffer) == 1:
        return treffer[0]
    return Bayes(beispiele).bestes(ws)


def tags(ws: set[str], beispiele: list[tuple[set[str], set[int]]], alle: list[int]) -> list[int]:
    """Je Tag eine Ja/Nein-Frage. Erst ab zwei Beispielen mit und zwei ohne
    den Tag: ein einzelnes Dokument ist noch kein Muster, und ohne Gegenbeispiele
    bekäme jedes neue Dokument den Tag."""
    raus = []
    for tag in alle:
        mit = sum(1 for _, ts in beispiele if tag in ts)
        if mit < 2 or len(beispiele) - mit < 2:
            continue
        b = Bayes([(w, 1 if tag in ts else 0) for w, ts in beispiele])
        if b.bestes(ws, 0.7) == 1:
            raus.append(tag)
    return raus
