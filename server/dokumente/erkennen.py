"""Was sich aus dem gelesenen Text ableiten lässt.

Datum: „Ort, Datum“, sonst das erste plausible Datum im Kopf des Schreibens.

Absender, Typ und Tags: von den ähnlichsten schon einsortierten Dokumenten
(siehe unten). Das wird bei jedem Vorschlag frisch aus der Datenbank gerechnet. Bei ein paar tausend Dokumenten dauert das Millisekunden,
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


def _gueltige(stueck: str, heute: date) -> list[str]:
    """Alle plausiblen Daten in stueck (ISO), in Textreihenfolge."""
    funde = []
    for m in _ZAHL.finditer(stueck):
        funde.append((m.start(), int(m.group(1)), int(m.group(2)), _jahr(m.group(3))))
    for m in _WORT.finditer(stueck):
        funde.append((m.start(), int(m.group(1)), MONATE[m.group(2).lower()], int(m.group(3))))
    for m in _ISO.finditer(stueck):
        funde.append((m.start(), int(m.group(3)), int(m.group(2)), int(m.group(1))))
    raus = []
    for _, t, mo, j in sorted(funde):
        try:
            d = date(j, mo, t)
        except ValueError:
            continue
        # Geburtsdaten und Druckvermerke ("Fassung Juli 2016") sind älter als
        # das Schreiben, Fälligkeiten liegen in der Zukunft: beides kein Briefdatum.
        if date(1970, 1, 1) <= d <= heute:
            raus.append(d.isoformat())
    return raus


# "Lengerich, 13.04.2017" / "Mettingen, den 4. Oktober 2024": so datiert man
# Briefe und unterschreibt Verträge. Verträge haben oft kein Datum im Kopf,
# dort stehen nur Zinsbeginn und Laufzeit, und die wären das falsche Datum.
_ORT_DATUM = re.compile(
    r"(?<![\w-])[A-ZÄÖÜ][a-zäöüß]+(?:[ -][A-ZÄÖÜ][a-zäöüß]+)?,\s*(?:den\s+)?"
    r"(\d{1,2}\.\s?(?:\d{1,2}\.\s?\d{2,4}|(?i:" + "|".join(MONATE) + r")\s+\d{4}))")


# "Datum: 16.05.2023" im Briefkopf schlägt die Druckzeile darüber, die das
# Versanddatum trägt ("16176910 0001/0003 0000544 17.05.2023"). Groß
# geschrieben, damit "Geburtsdatum:" nicht passt. "*06.02.2013" hinter einem
# Namen heißt geboren. "Ihr Antrag vom …", "Verordnung vom 8. April 2013"
# verweisen auf ein anderes Schriftstück, "vor dem 1. Januar 1991" ist eine Frist.
_DATUM_FELD = re.compile(r"(?<![\w-])Datum\s*:?\s*(\d{1,2}\.\s?\d{1,2}\.\s?\d{2,4})")
_KEIN_BRIEFDATUM = re.compile(
    r"(?:\*|(?:geburtsdatum|geboren(?:\s+am)?|geb\.|vom|(?:vor|ab|nach)\s+dem)\s*:?\s*)"
    r"\d{1,2}\.\s*(?:\d{1,2}\.\s?\d{2,4}|(?:" + "|".join(MONATE) + r")\s+\d{4})", re.I)


def datum(text: str, heute: date | None = None) -> str | None:
    """Datum des Schreibens (ISO) oder None: zuerst „Ort, Datum“ irgendwo im
    Text, dann „Datum:“, sonst das erste plausible Datum im Kopf, das kein
    Geburtsdatum ist."""
    heute = heute or date.today()
    for muster in (_ORT_DATUM, _DATUM_FELD):
        for m in muster.finditer(text):
            d = _gueltige(m.group(1), heute)
            if d:
                return d[0]
    d = _gueltige(_KEIN_BRIEFDATUM.sub(" ", text[:KOPF]), heute)
    return d[0] if d else None


# „information“ nur zusammengesetzt (Renteninformation): allein steht es in
# jedem Infoblatt („Information zur Überschussbeteiligung“) vor dem Vertrag.
_ART = ("vereinbarung|bescheid|rechnung|vertrag|abrechnung|mitteilung|bestätigung|angebot|kontoauszug|"
        "erklärung|kündigung|mahnung|police|bescheinigung|nachweis|antrag|tilgungsplan|sparplan|"
        "[a-zäöüß]information")
# Davor darf eine Ziffer kleben: die Texterkennung zieht Briefkopf-Nummern
# gern an das erste Wort ("DE125501924Anschlusszinsvereinbarung"). Ein Wort
# aus der Spalte daneben ("UhrGrundbesitzabgabenbescheid") schneidet titel() ab.
_TITEL = re.compile(r"(?<![A-Za-zÄÖÜäöüß-])([a-zäöüß]*(?:" + _ART + r"))(?![\w-])"
                    r"(?:\s+(?:für\s+|über\s+)?((?:19|20)\d\d(?:\s*/\s*(?:19|20)?\d\d)?)(?!\d))?", re.I)
_NAHT = re.compile(r"(?<=[a-zäöüß])(?=[A-ZÄÖÜ])")


# "Sprechzeiten … oder nach (besonderer) Vereinbarung" in der Fußzeile,
# "gemäß Vertrag": hinter einer Präposition sagt das Wort nicht, was das Papier ist.
_NACH_PRAEPOSITION = re.compile(r"(?<![\w-])(?:nach|laut|gemäß|gem\.|per|mit|ohne|zur|zum|zu|aus|von|vom)"
                                r"\s+(?:(?-i:[a-zäöüß]+)\s+)?$", re.I)


def titel(text: str) -> str | None:
    """Titelvorschlag aus dem Kopf: das erste Wort, das sagt, was das Papier
    ist (Anschlusszinsvereinbarung, Einkommensteuerbescheid 2022, …)."""
    for m in _TITEL.finditer(text[:KOPF]):
        # Am Wortanfang davor geklebt ("UhrGrundbesitzabgabenbescheid"): nur den letzten Teil
        wort = _NAHT.split(m.group(1))[-1]
        if _NACH_PRAEPOSITION.search(text[max(0, m.start() - 40):m.start()]):
            continue
        if wort.isupper():
            wort = wort.capitalize()
        elif not wort[0].isupper():
            continue        # klein geschrieben: kein Substantiv am Zeilenanfang, Fließtext
        return f"{wort} {re.sub(r'\s+', '', m.group(2))}" if m.group(2) else wort
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


# ---------- Vorschläge aus ähnlichen Dokumenten ----------
#
# Bei ein paar Dutzend Dokumenten taugt Statistik über einzelne Wörter wenig:
# ein naiver Bayes ließ jede Versicherungspost der Sparkasse („Es betreut Sie
# Stadtsparkasse Lengerich“) wie einen Darlehensvertrag aussehen, und mit
# fehlenden Wörtern gerechnet gewann einfach die größte Gruppe. Robuster ist,
# die ähnlichsten schon bestätigten Dokumente zu suchen (TF-IDF, Kosinus) und
# ihre Angaben nur zu übernehmen, wenn sie wirklich ähnlich sind. Ein neuer
# Absender bekommt so keinen falschen Vorschlag, sondern keinen.
# Gemessen an 31 echten Dokumenten (jedes einmal herausgenommen): 28 richtig,
# 0 falsch, 3 offen; die Provinzial-Post (unbekannt) blieb mit ≤ 0,18 offen.

AEHNLICH = 0.25
NACHBARN = 3


class Nachbarn:
    def __init__(self, beispiele: list[tuple[int, set[str]]]):
        self.n = len(beispiele)
        self.df = Counter(w for _, ws in beispiele for w in ws)
        self.vektoren = [(i, self._vektor(ws)) for i, ws in beispiele]

    def _vektor(self, ws: set[str]) -> dict[str, float]:
        # Auch Wörter, die kein bestätigtes Dokument kennt, zählen mit (größtes
        # Gewicht): ein Brief voller fremder Wörter ist eben nicht ähnlich, nur
        # weil Adresse und Bankname übereinstimmen.
        v = {w: math.log((self.n + 1) / (self.df[w] + 1)) + 1 for w in ws}
        laenge = math.sqrt(sum(x * x for x in v.values())) or 1.0
        return {w: x / laenge for w, x in v.items()}

    def naechste(self, ws: set[str]) -> list[tuple[float, int]]:
        """Die ähnlichsten (Ähnlichkeit, id), nur oberhalb der Schwelle."""
        q = self._vektor(ws)
        raus = []
        for i, v in self.vektoren:
            klein, gross = (q, v) if len(q) < len(v) else (v, q)
            s = sum(x * gross[w] for w, x in klein.items() if w in gross)
            if s >= AEHNLICH:
                raus.append((s, i))
        return sorted(raus, reverse=True)[:NACHBARN]


def vorschlag(ws: set[str], beispiele: list[dict]) -> dict:
    """beispiele: bestätigte Dokumente mit id, woerter, absender, typ, tags.
    Absender und Typ vom ähnlichsten, Tags, die die Mehrheit der ähnlichen hat."""
    nach = Nachbarn([(b["id"], b["woerter"]) for b in beispiele]).naechste(ws)
    if not nach:
        return {"absender": None, "typ": None, "tags": []}
    von = {b["id"]: b for b in beispiele}
    erster = von[nach[0][1]]
    zaehl = Counter(t for _, i in nach for t in von[i]["tags"])
    return {"absender": erster["absender"], "typ": erster["typ"],
            "tags": sorted(t for t, n in zaehl.items() if n * 2 > len(nach))}
