"""Ein lokales Sprachmodell (Ollama) hilft beim Einsortieren.

Die Regeln und die Nachbarn (erkennen.py) sind bei bekannten Absendern
zuverlässig, schreiben aber kaum brauchbare Titel ("Gebührenbescheid" statt
"Wasser 2023: 179 m³, 434,23 € (Nachzahlung 49,23 €)"). Ein Modell auf dem
eigenen Rechner kann das, ohne dass ein Brief das Haus verlässt.

Gemessen an 136 bestätigten Dokumenten (jedes einmal herausgenommen, qwen3.5:9b
auf einer 8-GB-Karte): Titel 73 % Wortübereinstimmung statt 11 %, Betrag im
Titel 56 von 63 richtig, ~10 s pro Dokument. Darum bekommt das Modell nur, was
es besser kann:

  titel     immer vom Modell (sonst Regel)
  typ       vom Modell, wenn die Nachbarn nichts sagen (17 von 19 richtig)
  absender  vom Modell, wenn die Nachbarn nichts sagen UND der Name schon in
            der Ablage steht. Neue Namen erfindet es gern in Varianten.
  datum, tags  nie: die Regeln treffen das Datum öfter, Tags rät es schlecht.

Die drei ähnlichsten bestätigten Dokumente stehen als Beispiele im Prompt;
ohne sie liegt das Modell deutlich öfter daneben.

Ist kein Modell eingestellt oder Ollama nicht erreichbar, bleibt alles wie
ohne Modell. Das Einstellen ist Sache des Nutzers (ablage-weit, modell.json).
"""
import json
import re
import urllib.request
from pathlib import Path

from . import ablage

TEXT_MAX = 5000      # Kopf und erste Seiten reichen, mehr kostet nur Zeit
WARTEN = 240         # erster Aufruf lädt das Modell (bei 6 GB gut eine Minute)
BEHALTEN = "2m"      # danach Grafikspeicher wieder freigeben (Stimme, Spiele)
TITEL_MAX = 120

_MODELLNAME = re.compile(r"^[A-Za-z0-9][\w.\-/:]{1,79}$")


def _pfad() -> Path:
    return ablage.DATEN / "modell.json"


def eingestellt() -> str:
    try:
        m = json.loads(_pfad().read_text(encoding="utf-8")).get("modell") or ""
    except (OSError, ValueError, AttributeError):
        return ""
    return m if _MODELLNAME.match(m) else ""


def einstellen(modell: str) -> str:
    modell = (modell or "").strip()
    if modell and not _MODELLNAME.match(modell):
        raise ablage.Fehler("Ungültiger Modellname")
    ablage.DATEN.mkdir(parents=True, exist_ok=True)
    _pfad().write_text(json.dumps({"modell": modell}), encoding="utf-8")
    return modell


def stand() -> dict:
    """Was eingestellt ist, ob Ollama läuft und welche Modelle es gibt."""
    from server import llm
    raus = {"modell": eingestellt(), "erreichbar": False, "installiert": [], "ollama": bool(llm.ollama_bin())}
    try:
        raus["installiert"] = [m["name"] for m in llm.ollama_installed()]
        raus["erreichbar"] = True
    except Exception:
        pass
    return raus


def _anweisung(namen: dict, beispiele: list[dict]) -> str:
    s = f"""Du sortierst eingescannte Post in eine private Ablage ein.
Gib JSON zurück:
- "titel": kurzer deutscher Titel: was das Schreiben ist und worum es geht, mit dem wichtigsten
  Betrag oder Jahr, z. B. "Einkommensteuerbescheid 2021" oder
  "Wasser 2023: 179 m³, 434,23 € (Nachzahlung 49,23 €)". Höchstens 80 Zeichen.
  Bei Rechnungen der Endbetrag inklusive Mehrwertsteuer.
- "absender": die absendende Stelle, genau so geschrieben wie in dieser Liste, wenn sie dabei ist:
  {json.dumps(namen['absender'], ensure_ascii=False)}. Sonst ihr Name kurz und offiziell.
- "typ": genau einer aus {json.dumps(namen['typen'], ensure_ascii=False)}.
Beträge, Jahre und Namen genau so wie im Text, erfinde nichts."""
    if beispiele:
        s += "\n\nSo wurden ähnliche Schreiben einsortiert (nur zur Orientierung, prüfe gegen den Text):"
        for b in beispiele:
            s += f"\n- titel: {b['titel']} | absender: {b['absender'] or '?'} | typ: {b['typ'] or '?'}"
    return s


def _fragen(modell: str, system: str, text: str) -> dict:
    """Ein Aufruf an Ollama; hebt jeden Fehler weiter (der Aufrufer fällt zurück)."""
    from server import llm
    body = {"model": modell, "stream": False, "think": False, "format": "json", "keep_alive": BEHALTEN,
            "options": {"temperature": 0, "num_ctx": 8192},
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": "TEXT DES SCHREIBENS (Texterkennung, kann Fehler haben):\n\n"
                                                     + text[:TEXT_MAX]}]}
    req = urllib.request.Request(llm._ollama_api() + "/api/chat", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=WARTEN) as r:
        antwort = json.loads(r.read())
    j = json.loads(antwort["message"]["content"])
    return j if isinstance(j, dict) else {}


def _ollama_bereit() -> bool:
    """Läuft Ollama nicht, aber CONSTRUCT hat es installiert: anwerfen."""
    from server import llm
    if llm.ollama_reachable():
        return True
    return bool(llm.ollama_bin()) and llm.ollama_serve_start() == ""


def _passend(wert, liste: list[str]) -> str | None:
    """Nur Namen, die es schon gibt (Groß-/Kleinschreibung egal), in deren Schreibweise."""
    w = str(wert or "").strip().casefold()
    return next((n for n in liste if n.casefold() == w), None) if w else None


def vorschlag(text: str, namen: dict, beispiele: list[dict]) -> dict | None:
    """namen: {"absender": [...], "typen": [...]} (nur Namen, die es schon gibt)
    beispiele: die ähnlichsten bestätigten Dokumente mit titel, absender, typ (Namen).
    Ergebnis {"titel", "absender", "typ"} (None, wo nichts Brauchbares kam) oder
    None, wenn kein Modell eingestellt oder erreichbar ist."""
    modell = eingestellt()
    if not modell or not text.strip():
        return None
    try:
        if not _ollama_bereit():
            return None
        j = _fragen(modell, _anweisung(namen, beispiele), text)
    except Exception as e:
        print(f"[dokumente] lokales Modell {modell}: {type(e).__name__}: {e}", flush=True)
        return None
    titel = " ".join(str(j.get("titel") or "").split())[:TITEL_MAX] or None
    return {"titel": titel,
            "absender": _passend(j.get("absender"), namen.get("absender") or []),
            "typ": _passend(j.get("typ"), namen.get("typen") or [])}
