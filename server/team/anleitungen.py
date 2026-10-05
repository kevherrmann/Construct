"""Was die Firma KANN — erprobte Handgriffe, die jeder nachschlagen darf.

Der Unterschied zum Gedaechtnis, und warum es beides braucht:

    MEMORY.md   was EINER gelernt hat. Erkenntnisse, Zahlen, Vorlieben.
                Persoenlich, gedeckelt, wird bei Bedarf eingedickt — dabei
                geht bewusst etwas verloren.
    anleitungen/ was die FIRMA kann. Ein Ablauf, der sich bewaehrt hat und
                beim naechsten Mal wieder gebraucht wird. Gemeinsam,
                dauerhaft, wird nicht eingedickt.

Ausloeser war eine Luecke, die beim Bau von `gedaechtnis_eindicken` sichtbar
wurde: Elaras Notiz "Playwright-Klick auf `data-bestaetigen` braucht
expect_navigation, sonst geht der POST verloren" ist keine Erkenntnis, die man
zusammenfassen darf — das ist ein Handgriff, der beim naechsten Mal genau so
gebraucht wird. Im Gedaechtnis stand er auf Abruf zum Eindicken, und niemand
ausser Elara haette ihn je gesehen.

Der Kniff, damit das den Kontext nicht sprengt (das Muster kennt man von
Claude Code und von Hermes): **im Systemprompt steht nur der Index** — Name und
die Zeile "wann brauche ich das". Die eigentliche Anleitung holt sich ein
Mitarbeiter erst, wenn die Lage passt, ueber das Bus-Werkzeug `anleitung`.
Zwanzig Anleitungen kosten so rund 1200 Zeichen statt 40 000.

Ablage, wie ueberall in dieser Firma ein Ordner und keine Datenbank — Kevin
muss eine schlechte Anleitung im Editor aufmachen und wegwerfen koennen:

    firma/anleitungen/<name>/ANLEITUNG.md

Angelegt werden sie von den Mitarbeitern selbst, ohne Rueckfrage. Das ist
Kevins ausdrueckliche Entscheidung (04.09.2026): "Es hilft ja nur." Aufgeraeumt
wird spaeter von Hand oder von einem Mitarbeiter, der genau dafuer da ist.
"""
import re
from datetime import date
from pathlib import Path

from server.team.pfade import FIRMA_DIR

DIR = FIRMA_DIR / "anleitungen"

# Eine einzelne Anleitung. Grosszuegig — hier darf wirklich stehen, wie es
# geht, samt Befehlszeilen und Fallstricken. Sie liegt ja nicht im Kontext.
# Von 6000 auf 12000 gehoben, als die Druck-Anleitungen kamen: ein Ablauf mit
# Code-Schnipseln und den Fallen aus drei Projekten passt nicht in 6000.
MAX_TEXT = 12_000
# Die Index-Zeile. Knapp, denn DIE haengt an jedem Systemprompt.
MAX_WANN = 160
MAX_NAME = 48
# Deckel fuer den ganzen Index. Wird er erreicht, ist das kein Fehler, sondern
# ein Hinweis: dann sind zu viele Anleitungen da und jemand muss ausmisten.
MAX_INDEX = 4_000

NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def slug_ok(name: str) -> bool:
    """Nur Kleinbuchstaben, Ziffern und Bindestriche.

    Der Name kommt aus einem Sprachmodell und wird zu einem Pfad. Ohne diese
    Pruefung reicht ein `../../` im Namen, um ausserhalb des Ordners zu
    schreiben — dieselbe Falle, die es in der Personalverwaltung schon einmal
    gab.
    """
    return bool(name) and len(name) <= MAX_NAME and bool(NAME_RE.match(name))


def _split_frontmatter(txt: str):
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", txt, re.S)
    return (m.group(1), m.group(2)) if m else ("", txt)


def _fm(fm: str, key: str) -> str:
    m = re.search(rf"^{re.escape(key)}:[ \t]*(.*)$", fm, re.M)
    return m.group(1).strip().strip("\"'") if m else ""


def _eine(d: Path) -> dict | None:
    f = d / "ANLEITUNG.md"
    if not f.is_file() or not slug_ok(d.name):
        return None
    try:
        roh = f.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    fm, text = _split_frontmatter(roh)
    wann = " ".join(_fm(fm, "wann").split())[:MAX_WANN]
    if not wann or not text.strip():
        # Ohne "wann" taugt sie nichts: dann weiss niemand, wann er sie holen
        # soll, und sie liegt fuer immer ungenutzt herum.
        return None
    return {"name": d.name, "wann": wann, "text": text.strip()[:MAX_TEXT],
            "von": _fm(fm, "von"), "angelegt": _fm(fm, "angelegt"),
            "benutzt": _fm(fm, "benutzt")}


def alle() -> list:
    if not DIR.is_dir():
        return []
    out = [x for x in (_eine(d) for d in sorted(DIR.iterdir()) if d.is_dir()) if x]
    return out


def lesen(name: str) -> dict | None:
    if not slug_ok(name):
        return None
    return _eine(DIR / name)


def index() -> str:
    """Der Block fuer den Systemprompt — Namen und Anlaesse, sonst nichts.

    Bewusst mit dem Satz, WIE man drankommt: eine Liste von Namen, bei der
    nicht danebensteht, dass man sie holen kann und womit, wird ueberlesen.
    """
    xs = alle()
    if not xs:
        return ""
    zeilen = ["## Anleitungen der Firma", "",
              "Fuer diese Lagen hat sich schon einmal jemand einen Ablauf "
              "erarbeitet. Passt eine auf deine Aufgabe, hol sie dir mit "
              "`anleitung` — bevor du selbst probierst.", ""]
    for x in xs:
        zeilen.append(f"- **{x['name']}** — {x['wann']}")
    txt = "\n".join(zeilen)
    if len(txt) > MAX_INDEX:
        print(f"[anleitungen] Der Index ist {len(txt)} Zeichen lang, erlaubt sind "
              f"{MAX_INDEX} — der Rest fehlt im Systemprompt. Zeit zum Ausmisten.",
              flush=True)
    return txt[:MAX_INDEX]


def _atomic(p: Path, text: str):
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(p)


def anlegen(name: str, wann: str, text: str, von: str) -> tuple:
    """Anlegen oder aktualisieren. Rueckgabe: (ok, Meldung fuer den Agenten).

    Aktualisieren ist ausdruecklich erlaubt: eine Anleitung, die sich beim
    zweiten Mal als unvollstaendig erweist, soll verbessert werden und nicht
    als "anleitung-2" danebenliegen.
    """
    name = " ".join(str(name or "").split()).lower().replace(" ", "-")
    if not slug_ok(name):
        return False, ("Der Name taugt nicht. Nur Kleinbuchstaben, Ziffern und "
                       "Bindestriche, hoechstens 48 Zeichen — z. B. "
                       "`playwright-bestaetigen`.")
    wann = " ".join(str(wann or "").split())
    if len(wann) < 10:
        return False, ("Es fehlt das `wann`: in einem Satz, woran ein Kollege "
                       "erkennt, dass diese Anleitung seine Lage trifft. Ohne "
                       "das findet sie nie jemand.")
    text = str(text or "").strip()
    if len(text) < 40:
        return False, "Die Anleitung ist zu duenn. Schreib die Schritte auf."

    p = DIR / name / "ANLEITUNG.md"
    vorher = lesen(name)
    if vorher is None and len(alle()) >= 200:
        return False, ("Es gibt schon 200 Anleitungen. Sag Kevin, dass "
                       "ausgemistet werden muss.")
    kopf = [f"name: {name}", f"wann: {wann[:MAX_WANN]}",
            f"von: {(vorher or {}).get('von') or von}",
            f"angelegt: {(vorher or {}).get('angelegt') or date.today().isoformat()}"]
    if vorher:
        kopf.append(f"geaendert: {date.today().isoformat()} durch {von}")
        # Den Zaehler mitnehmen. Ohne diese Zeile stand eine verbesserte
        # Anleitung wieder bei null — und beim Ausmisten saehe die meistbenutzte
        # aus wie eine, die noch nie jemand gebraucht hat.
        if vorher.get("benutzt"):
            kopf.append(f"benutzt: {vorher['benutzt']}")
    _atomic(p, "---\n" + "\n".join(kopf) + "\n---\n\n" + text[:MAX_TEXT] + "\n")
    return True, ("Anleitung aktualisiert." if vorher else
                  "Anleitung angelegt — deine Kollegen sehen sie ab dem naechsten Zug.")


def benutzt_vermerken(name: str):
    """Zaehlt mit, wie oft eine Anleitung geholt wurde.

    Nicht fuer die Agenten, sondern fuer das Ausmisten: eine Anleitung, die in
    Monaten niemand gebraucht hat, ist der erste Kandidat zum Wegwerfen. Ohne
    diese Zahl bleibt beim Aufraeumen nur Bauchgefuehl.
    """
    x = lesen(name)
    if not x:
        return
    p = DIR / name / "ANLEITUNG.md"
    try:
        roh = p.read_text(encoding="utf-8")
    except OSError:
        return
    fm, text = _split_frontmatter(roh)
    n = 0
    m = re.match(r"(\d+)", x.get("benutzt") or "")
    if m:
        n = int(m.group(1))
    zeilen = [z for z in fm.split("\n") if not z.startswith("benutzt:")]
    zeilen.append(f"benutzt: {n + 1} zuletzt {date.today().isoformat()}")
    _atomic(p, "---\n" + "\n".join(zeilen) + "\n---\n\n" + text.strip() + "\n")
