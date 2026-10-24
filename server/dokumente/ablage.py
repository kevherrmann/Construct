"""Ablage: Datenbank, Dateien und die Verarbeitung neuer Dokumente.

Ordner dokumente/ im Projektordner (steht in .gitignore):

  dokumente.db              SQLite: Dokumente, Absender, Typen, Tags, Volltextsuche
  dateien/JAHR/ABSENDER/    die PDFs, benannt "DATUM TITEL.pdf"
  vorschau/ID.webp          erste Seite klein
  verarbeitung/ID.pdf       was gerade gelesen wird
  papierkorb/               Gelöschtes (wird nie automatisch geleert)

Die Dateien sind auch ohne CONSTRUCT brauchbar: normale PDFs mit Textschicht
in einer lesbaren Ordnerstruktur. Wer das Programm nicht mehr will, behält
seine Ablage. Die Datenbank ist nur der Index darüber.

Neue Dokumente kommen sofort in die Liste (Zustand "lesen") und werden von
einem Hintergrund-Thread nacheinander gelesen: Texterkennung, Datum,
Vorschläge für Absender, Typ und Tags. Sie bleiben im Eingang, bis jemand
sie bestätigt.
"""
import hashlib
import os
import queue
import re
import shutil
import sqlite3
import sys
import threading
import time
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path

from server.core import BASE_DIR

from . import erkennen, ocr

DATEN = BASE_DIR / "dokumente"
TITEL_MAX = 200
NOTIZ_MAX = 4000
NAME_MAX = 80

SCHEMA = """
CREATE TABLE IF NOT EXISTS absender (id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE COLLATE NOCASE);
CREATE TABLE IF NOT EXISTS typen (id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE COLLATE NOCASE);
CREATE TABLE IF NOT EXISTS tags (id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE COLLATE NOCASE);
CREATE TABLE IF NOT EXISTS dokumente (
  id INTEGER PRIMARY KEY,
  titel TEXT NOT NULL DEFAULT '', datum TEXT,
  absender_id INTEGER REFERENCES absender(id) ON DELETE SET NULL,
  typ_id INTEGER REFERENCES typen(id) ON DELETE SET NULL,
  datei TEXT, sha256 TEXT, seiten INTEGER NOT NULL DEFAULT 0,
  text TEXT NOT NULL DEFAULT '', notiz TEXT NOT NULL DEFAULT '',
  eingang INTEGER NOT NULL DEFAULT 1,
  zustand TEXT NOT NULL DEFAULT 'lesen' CHECK (zustand IN ('lesen', 'fertig', 'fehler')),
  hinweis TEXT NOT NULL DEFAULT '', quelle TEXT NOT NULL DEFAULT '',
  hinzugefuegt TEXT NOT NULL, geaendert TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS dok_tags (
  dok_id INTEGER NOT NULL REFERENCES dokumente(id) ON DELETE CASCADE,
  tag_id INTEGER NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
  PRIMARY KEY (dok_id, tag_id));
CREATE VIRTUAL TABLE IF NOT EXISTS suche USING fts5(
  titel, absender, text, tokenize = 'unicode61 remove_diacritics 2');
"""


class Fehler(Exception):
    pass


_lock = threading.RLock()
_bereit: set[Path] = set()


def _jetzt() -> str:
    return datetime.now().isoformat(timespec="seconds")


@contextmanager
def db():
    """Eine Verbindung je Aufruf, Schreibzugriffe nacheinander (Thread + API + CLI)."""
    with _lock:
        DATEN.mkdir(parents=True, exist_ok=True)
        c = sqlite3.connect(DATEN / "dokumente.db", timeout=30)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA foreign_keys = ON")
        if DATEN not in _bereit:
            c.executescript(SCHEMA)
            _bereit.add(DATEN)
        try:
            yield c
            c.commit()
        except Exception:
            c.rollback()
            raise
        finally:
            c.close()


# ---------- Namen (Absender, Typen, Tags) ----------

TABELLEN = ("absender", "typen", "tags")


def _name(s) -> str:
    return re.sub(r"\s+", " ", str(s or "")).strip()[:NAME_MAX]


def _id_fuer(c, tabelle: str, wert) -> int | None:
    """Name oder id → id. Ein neuer Name legt den Eintrag an."""
    if wert in (None, ""):
        return None
    if isinstance(wert, int) or (isinstance(wert, str) and wert.isdigit()):
        r = c.execute(f"SELECT id FROM {tabelle} WHERE id = ?", (int(wert),)).fetchone()
        if not r:
            raise Fehler(f"{tabelle} {wert} gibt es nicht")
        return r["id"]
    name = _name(wert)
    if not name:
        return None
    r = c.execute(f"SELECT id FROM {tabelle} WHERE name = ?", (name,)).fetchone()
    if r:
        return r["id"]
    return c.execute(f"INSERT INTO {tabelle} (name) VALUES (?)", (name,)).lastrowid


def namen(tabelle: str) -> list[dict]:
    if tabelle not in TABELLEN:
        raise Fehler("unbekannte Liste")
    spalte = {"absender": "absender_id", "typen": "typ_id"}.get(tabelle)
    with db() as c:
        if spalte:
            q = (f"SELECT t.id, t.name, COUNT(d.id) AS anzahl FROM {tabelle} t "
                 f"LEFT JOIN dokumente d ON d.{spalte} = t.id GROUP BY t.id ORDER BY t.name")
        else:
            q = ("SELECT t.id, t.name, COUNT(x.dok_id) AS anzahl FROM tags t "
                 "LEFT JOIN dok_tags x ON x.tag_id = t.id GROUP BY t.id ORDER BY t.name")
        return [dict(r) for r in c.execute(q)]


def umbenennen(tabelle: str, id_: int, name: str) -> None:
    if tabelle not in TABELLEN:
        raise Fehler("unbekannte Liste")
    name = _name(name)
    if not name:
        raise Fehler("Name fehlt")
    with db() as c:
        try:
            c.execute(f"UPDATE {tabelle} SET name = ? WHERE id = ?", (name, id_))
        except sqlite3.IntegrityError:
            raise Fehler(f"„{name}“ gibt es schon")
        betroffen = _betroffene(c, tabelle, id_)
    for d in betroffen:
        _ablegen(d)


def entfernen(tabelle: str, id_: int) -> None:
    """Entfernt den Namen, nicht die Dokumente (die verlieren nur die Angabe)."""
    if tabelle not in TABELLEN:
        raise Fehler("unbekannte Liste")
    with db() as c:
        betroffen = _betroffene(c, tabelle, id_)
        c.execute(f"DELETE FROM {tabelle} WHERE id = ?", (id_,))
    for d in betroffen:
        _ablegen(d)


def _betroffene(c, tabelle, id_) -> list[int]:
    if tabelle == "tags":
        return [r[0] for r in c.execute("SELECT dok_id FROM dok_tags WHERE tag_id = ?", (id_,))]
    spalte = "absender_id" if tabelle == "absender" else "typ_id"
    return [r[0] for r in c.execute(f"SELECT id FROM dokumente WHERE {spalte} = ?", (id_,))]


# ---------- Dokumente lesen ----------

_SPALTEN = """d.id, d.titel, d.datum, d.absender_id, a.name AS absender, d.typ_id, t.name AS typ,
  d.datei, d.seiten, d.notiz, d.eingang, d.zustand, d.hinweis, d.quelle, d.hinzugefuegt, d.geaendert"""
_VON = "FROM dokumente d LEFT JOIN absender a ON a.id = d.absender_id LEFT JOIN typen t ON t.id = d.typ_id"


def _tags_zu(c, ids: list[int]) -> dict[int, list[dict]]:
    raus: dict[int, list[dict]] = {i: [] for i in ids}
    if ids:
        frage = ",".join("?" * len(ids))
        for r in c.execute(f"SELECT x.dok_id, g.id, g.name FROM dok_tags x JOIN tags g ON g.id = x.tag_id "
                           f"WHERE x.dok_id IN ({frage}) ORDER BY g.name", ids):
            raus[r["dok_id"]].append({"id": r["id"], "name": r["name"]})
    return raus


def _mit_tags(c, zeilen) -> list[dict]:
    ds = [dict(z) for z in zeilen]
    tg = _tags_zu(c, [d["id"] for d in ds])
    for d in ds:
        d["tags"] = tg[d["id"]]
        d["eingang"] = bool(d["eingang"])
    return ds


def _fts(q: str) -> str:
    """Freitext → FTS5-Abfrage: jedes Wort als Präfix, alle müssen vorkommen.
    Anführungszeichen drumherum, damit Bindestriche und Doppelpunkte nicht als
    FTS-Syntax gelesen werden."""
    woerter = re.findall(r"\w+", q, re.UNICODE)
    return " ".join(f'"{w}"*' for w in woerter)


def liste(q: str = "", jahr: str = "", absender: int | None = None, typ: int | None = None,
          tag: int | None = None, eingang: bool | None = None, limit: int = 200, offset: int = 0) -> dict:
    wo, args = [], []
    von = _VON
    if q.strip():
        f = _fts(q)
        if f:
            von += " JOIN suche s ON s.rowid = d.id"
            wo.append("suche MATCH ?")
            args.append(f)
    if jahr:
        wo.append("substr(d.datum, 1, 4) = ?")
        args.append(str(jahr)[:4])
    if absender:
        wo.append("d.absender_id = ?")
        args.append(absender)
    if typ:
        wo.append("d.typ_id = ?")
        args.append(typ)
    if tag:
        wo.append("d.id IN (SELECT dok_id FROM dok_tags WHERE tag_id = ?)")
        args.append(tag)
    if eingang is not None:
        wo.append("d.eingang = ?")
        args.append(1 if eingang else 0)
    where = (" WHERE " + " AND ".join(wo)) if wo else ""
    with db() as c:
        gesamt = c.execute(f"SELECT COUNT(*) {von}{where}", args).fetchone()[0]
        reihen = c.execute(
            f"SELECT {_SPALTEN} {von}{where} ORDER BY d.datum IS NULL, d.datum DESC, d.id DESC "
            f"LIMIT ? OFFSET ?", [*args, max(1, min(limit, 1000)), max(0, offset)]).fetchall()
        return {"gesamt": gesamt, "dokumente": _mit_tags(c, reihen)}


def dokument(id_: int, mit_text: bool = True) -> dict:
    with db() as c:
        r = c.execute(f"SELECT {_SPALTEN}, d.text {_VON} WHERE d.id = ?", (id_,)).fetchone()
        if not r:
            raise KeyError(id_)
        d = _mit_tags(c, [r])[0]
    if not mit_text:
        d.pop("text", None)
    return d


def uebersicht() -> dict:
    with db() as c:
        z = lambda q, *a: c.execute(q, a).fetchone()[0]  # noqa: E731
        jahre = [dict(r) for r in c.execute(
            "SELECT substr(datum, 1, 4) AS jahr, COUNT(*) AS anzahl FROM dokumente "
            "WHERE datum IS NOT NULL GROUP BY jahr ORDER BY jahr DESC")]
        return {
            "gesamt": z("SELECT COUNT(*) FROM dokumente"),
            "eingang": z("SELECT COUNT(*) FROM dokumente WHERE eingang = 1"),
            "lesen": z("SELECT COUNT(*) FROM dokumente WHERE zustand = 'lesen'"),
            "jahre": jahre,
            "ohne_datum": z("SELECT COUNT(*) FROM dokumente WHERE datum IS NULL"),
            "texterkennung": ocr.verfuegbar(),
        }


def datei(id_: int) -> Path:
    d = dokument(id_, mit_text=False)
    if not d["datei"]:
        raise KeyError(id_)
    p = DATEN / d["datei"]
    if not p.is_file():
        raise KeyError(id_)
    return p


def vorschau(id_: int) -> Path | None:
    p = DATEN / "vorschau" / f"{id_}.webp"
    return p if p.is_file() else None


# ---------- Dokumente ändern ----------

def _datum(wert) -> str | None:
    if wert in (None, ""):
        return None
    try:
        return date.fromisoformat(str(wert)[:10]).isoformat()
    except ValueError:
        raise Fehler("Datum bitte als JJJJ-MM-TT")


def aendern(id_: int, felder: dict) -> dict:
    """Ändert die Angaben. absender/typ: Name (legt an) oder id; tags: Liste von
    Namen oder ids und ersetzt die bisherigen; eingang=False heißt bestätigt."""
    with db() as c:
        if not c.execute("SELECT 1 FROM dokumente WHERE id = ?", (id_,)).fetchone():
            raise KeyError(id_)
        sets, args = [], []
        if "titel" in felder:
            sets.append("titel = ?")
            args.append(re.sub(r"\s+", " ", str(felder["titel"] or "")).strip()[:TITEL_MAX])
        if "datum" in felder:
            sets.append("datum = ?")
            args.append(_datum(felder["datum"]))
        if "notiz" in felder:
            sets.append("notiz = ?")
            args.append(str(felder["notiz"] or "")[:NOTIZ_MAX])
        if "absender" in felder:
            sets.append("absender_id = ?")
            args.append(_id_fuer(c, "absender", felder["absender"]))
        if "typ" in felder:
            sets.append("typ_id = ?")
            args.append(_id_fuer(c, "typen", felder["typ"]))
        if "eingang" in felder:
            sets.append("eingang = ?")
            args.append(1 if felder["eingang"] else 0)
        if sets:
            sets.append("geaendert = ?")
            args.append(_jetzt())
            c.execute(f"UPDATE dokumente SET {', '.join(sets)} WHERE id = ?", [*args, id_])
        if "tags" in felder:
            ids = {_id_fuer(c, "tags", t) for t in (felder["tags"] or [])} - {None}
            c.execute("DELETE FROM dok_tags WHERE dok_id = ?", (id_,))
            c.executemany("INSERT INTO dok_tags (dok_id, tag_id) VALUES (?, ?)", [(id_, t) for t in ids])
        # Namen, die niemand mehr benutzt, räumen sich selbst weg: sonst sammelt
        # sich jeder Tippfehler in den Auswahllisten.
        c.execute("DELETE FROM absender WHERE id NOT IN (SELECT absender_id FROM dokumente "
                  "WHERE absender_id IS NOT NULL)")
        c.execute("DELETE FROM typen WHERE id NOT IN (SELECT typ_id FROM dokumente WHERE typ_id IS NOT NULL)")
        c.execute("DELETE FROM tags WHERE id NOT IN (SELECT tag_id FROM dok_tags)")
    _ablegen(id_)
    return dokument(id_, mit_text=False)


def seiten_lesen(angabe: str, anzahl: int) -> list[list[int]]:
    """ "1-2, 3, 4-6" → [[1, 2], [3], [4, 5, 6]]. Jede Seite höchstens einmal."""
    teile, gesehen = [], set()
    for stueck in re.split(r"[,;]", angabe):
        stueck = stueck.strip()
        if not stueck:
            continue
        m = re.fullmatch(r"(\d+)\s*(?:-\s*(\d+))?", stueck)
        if not m:
            raise Fehler(f"„{stueck}“ ist keine Seitenangabe (Beispiel: 1-2, 3, 4-6)")
        a, b = int(m.group(1)), int(m.group(2) or m.group(1))
        if not 1 <= a <= b <= anzahl:
            raise Fehler(f"Seiten {stueck} gibt es nicht (das Dokument hat {anzahl})")
        seiten = list(range(a, b + 1))
        if gesehen & set(seiten):
            raise Fehler("Eine Seite steht doppelt in der Angabe")
        gesehen |= set(seiten)
        teile.append(seiten)
    if len(teile) < 2:
        raise Fehler("Zum Aufteilen mindestens zwei Teile angeben")
    return teile


def teilen(id_: int, angabe: str) -> list[dict]:
    """Ein Dokument in mehrere zerlegen (etwa ein Stapel, der als eines
    gescannt wurde). Die Teile erben Absender, Typ und Tags und kommen in den
    Eingang; das Original geht in den Papierkorb. Nicht genannte Seiten fallen
    weg, liegen aber mit dem Original im Papierkorb."""
    import tempfile

    from pypdf import PdfReader, PdfWriter
    d = dokument(id_, mit_text=False)
    if d["zustand"] == "lesen":
        raise Fehler("Das Dokument wird noch gelesen")
    quelle = PdfReader(str(datei(id_)))
    teile = seiten_lesen(angabe, len(quelle.pages))
    neu_ = []
    with tempfile.TemporaryDirectory() as tmp:
        for n, seiten in enumerate(teile, 1):
            w = PdfWriter()
            for s in seiten:
                w.add_page(quelle.pages[s - 1])
            pdf = Path(tmp) / f"teil{n}.pdf"
            with open(pdf, "wb") as f:
                w.write(f)
            x = neu(pdf, titel=f"{d['titel'] or 'Dokument'} (Teil {n})", quelle=d["quelle"])
            x = aendern(x["id"], {"absender": d["absender"], "typ": d["typ"],
                              "tags": [g["name"] for g in d["tags"]]})
            neu_.append(x)
    loeschen(id_)
    return neu_


def loeschen(id_: int) -> None:
    """In den Papierkorb, nicht weg: ein falscher Klick soll keine Steuerunterlage kosten."""
    d = dokument(id_, mit_text=False)
    if d["datei"] and (DATEN / d["datei"]).is_file():
        ziel = DATEN / "papierkorb" / f"{id_} {Path(d['datei']).name}"
        ziel.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(DATEN / d["datei"], ziel)
        _leere_ordner_weg((DATEN / d["datei"]).parent)
    for p in (DATEN / "vorschau" / f"{id_}.webp", DATEN / "verarbeitung" / f"{id_}.pdf"):
        p.unlink(missing_ok=True)
    with db() as c:
        c.execute("DELETE FROM dokumente WHERE id = ?", (id_,))
        c.execute("DELETE FROM suche WHERE rowid = ?", (id_,))


# ---------- Dateiname und Suchindex ----------

_UNERLAUBT = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def _sauber(s: str, n: int) -> str:
    s = _UNERLAUBT.sub("", s).strip().strip(".")
    return s[:n].strip() or "_"


def _wunschpfad(d: dict) -> str:
    jahr = (d["datum"] or "")[:4] or "ohne Datum"
    ordner = _sauber(d["absender"] or "ohne Absender", 60)
    name = " ".join(x for x in (d["datum"] or "", d["titel"] or f"Dokument {d['id']}") if x)
    return f"dateien/{jahr}/{ordner}/{_sauber(name, 120)}.pdf"


def _leere_ordner_weg(ordner: Path) -> None:
    wurzel = (DATEN / "dateien").resolve()
    o = ordner.resolve()
    while o != wurzel and wurzel in o.parents:
        try:
            o.rmdir()
        except OSError:
            break
        o = o.parent


def _ablegen(id_: int) -> None:
    """Datei an den Ort, der zu den Angaben passt, und Suchindex auffrischen."""
    with db() as c:
        r = c.execute(f"SELECT {_SPALTEN}, d.text {_VON} WHERE d.id = ?", (id_,)).fetchone()
        if not r:
            return
        d = dict(r)
        if d["datei"] and d["zustand"] != "lesen":
            alt = DATEN / d["datei"]
            neu_rel = _wunschpfad(d)
            if neu_rel != d["datei"] and alt.is_file():
                neu = DATEN / neu_rel
                n = 2
                while neu.exists():
                    neu = neu.with_name(f"{Path(neu_rel).stem} ({n}).pdf")
                    n += 1
                neu.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(alt, neu)
                _leere_ordner_weg(alt.parent)
                c.execute("UPDATE dokumente SET datei = ? WHERE id = ?", (neu.relative_to(DATEN).as_posix(), id_))
        c.execute("DELETE FROM suche WHERE rowid = ?", (id_,))
        c.execute("INSERT INTO suche (rowid, titel, absender, text) VALUES (?, ?, ?, ?)",
                  (id_, d["titel"] or "", d["absender"] or "", d["text"] or ""))


# ---------- Neue Dokumente ----------

_warteschlange: "queue.Queue[int]" = queue.Queue()
_arbeiter: threading.Thread | None = None
# Tests schalten den Thread ab und lesen mit jetzt_lesen_alle() selbst.
HINTERGRUND = True


def neu(pdf: Path, titel: str = "", quelle: str = "", vorschau_bild=None) -> dict:
    """Nimmt ein PDF auf (wird verschoben) und stellt es zum Lesen an."""
    jetzt = _jetzt()
    with db() as c:
        id_ = c.execute("INSERT INTO dokumente (titel, quelle, hinzugefuegt, geaendert) VALUES (?, ?, ?, ?)",
                        (titel[:TITEL_MAX], quelle[:40], jetzt, jetzt)).lastrowid
    roh = DATEN / "verarbeitung" / f"{id_}.pdf"
    roh.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(pdf, roh)
    with db() as c:
        c.execute("UPDATE dokumente SET datei = ? WHERE id = ?", (roh.relative_to(DATEN).as_posix(), id_))
    if vorschau_bild is not None:
        try:
            b = vorschau_bild.copy()
            b.thumbnail((ocr.VORSCHAU_BREITE, ocr.VORSCHAU_BREITE * 2))
            (DATEN / "vorschau").mkdir(parents=True, exist_ok=True)
            b.save(DATEN / "vorschau" / f"{id_}.webp", "WEBP", quality=70)
        except OSError:
            pass
    _anstellen(id_)
    return dokument(id_, mit_text=False)


def _anstellen(id_: int) -> None:
    global _arbeiter
    _warteschlange.put(id_)
    if not HINTERGRUND:
        return
    with _lock:
        if _arbeiter is None or not _arbeiter.is_alive():
            _arbeiter = threading.Thread(target=_arbeiten, name="dokumente-lesen", daemon=True)
            _arbeiter.start()


def _arbeiten() -> None:
    while True:
        try:
            id_ = _warteschlange.get(timeout=30)
        except queue.Empty:
            return
        try:
            lesen(id_)
        except Exception as e:     # ein kaputtes Dokument darf die Schlange nicht anhalten
            with db() as c:
                c.execute("UPDATE dokumente SET zustand = 'fehler', hinweis = ? WHERE id = ?", (str(e)[:300], id_))


def _sperre_lebt(sperre: Path) -> bool:
    """Liest gerade ein anderer Prozess (Server, doku.py)? Eine Sperre, deren
    Prozess nicht mehr lebt, stammt von einem Absturz."""
    try:
        pid = int(sperre.read_text().strip() or 0)
    except (OSError, ValueError):
        return False
    if sys.platform == "win32":
        # os.kill(pid, 0) beendet unter Windows den Prozess: dort zählt das Alter
        try:
            return time.time() - sperre.stat().st_mtime < 1800
        except OSError:
            return False
    try:
        os.kill(pid, 0)
        return True
    except (OSError, ValueError):
        return False


def lesen(id_: int) -> None:
    """Texterkennung, Datum, Vorschläge, ablegen. Läuft im Hintergrund-Thread
    (Tests rufen es direkt). Server und doku.py können dasselbe Dokument
    anstellen (etwa wenn der Server gerade neu startet): eine Sperrdatei sorgt
    dafür, dass nur einer es liest."""
    roh = DATEN / "verarbeitung" / f"{id_}.pdf"
    sperre = roh.with_suffix(".sperre")
    for _ in range(2):
        try:
            fd = os.open(sperre, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            break
        except FileExistsError:
            if _sperre_lebt(sperre):
                return
            sperre.unlink(missing_ok=True)
    else:
        return
    os.write(fd, str(os.getpid()).encode())
    os.close(fd)
    try:
        if roh.is_file():
            _lesen(id_, roh)
    finally:
        sperre.unlink(missing_ok=True)


def _lesen(id_: int, roh: Path) -> None:
    tmp = roh.with_suffix(".ocr.pdf")
    text, seiten, hinweis = ocr.verarbeiten(roh, tmp)
    sha = hashlib.sha256(tmp.read_bytes()).hexdigest()
    vorschlag = vorschlagen(text)
    with db() as c:
        d = dict(c.execute("SELECT titel, datum, absender_id, typ_id, eingang FROM dokumente WHERE id = ?",
                           (id_,)).fetchone() or {})
        if not d:
            tmp.unlink(missing_ok=True)
            return
        doppelt = c.execute("SELECT id FROM dokumente WHERE sha256 = ? AND id != ?", (sha, id_)).fetchone()
        if doppelt and not hinweis:
            hinweis = f"gleiche Datei wie Dokument {doppelt[0]}"
        c.execute(
            "UPDATE dokumente SET text = ?, seiten = ?, sha256 = ?, hinweis = ?, zustand = 'fertig', "
            "datum = COALESCE(datum, ?), absender_id = COALESCE(absender_id, ?), typ_id = COALESCE(typ_id, ?), "
            "datei = ?, geaendert = ? WHERE id = ?",
            (text, seiten, sha, hinweis, erkennen.datum(text), vorschlag["absender"], vorschlag["typ"],
             f"verarbeitung/{id_}.ocr.pdf", _jetzt(), id_))
        if d.get("eingang"):
            c.executemany("INSERT OR IGNORE INTO dok_tags (dok_id, tag_id) VALUES (?, ?)",
                          [(id_, t) for t in vorschlag["tags"]])
    roh.unlink(missing_ok=True)
    _ablegen(id_)
    if not vorschau(id_):
        ocr.vorschau(datei(id_), DATEN / "vorschau" / f"{id_}.webp")


def vorschlagen(text: str) -> dict:
    """Absender, Typ, Tags aus den bestätigten Dokumenten gelernt."""
    ws = erkennen.woerter(text)
    with db() as c:
        bestaetigt = c.execute("SELECT id, text, absender_id, typ_id FROM dokumente "
                               "WHERE eingang = 0 AND zustand = 'fertig'").fetchall()
        tags_je = {}
        for r in c.execute("SELECT x.dok_id, x.tag_id FROM dok_tags x JOIN dokumente d ON d.id = x.dok_id "
                           "WHERE d.eingang = 0"):
            tags_je.setdefault(r[0], set()).add(r[1])
        namen_a = {r["id"]: r["name"] for r in c.execute("SELECT id, name FROM absender")}
        alle_tags = [r[0] for r in c.execute("SELECT id FROM tags")]
    wort = {r["id"]: erkennen.woerter(r["text"]) for r in bestaetigt}
    return {
        "absender": erkennen.absender(text, ws, [(wort[r["id"]], r["absender_id"]) for r in bestaetigt
                                                 if r["absender_id"]], namen_a),
        "typ": erkennen.Bayes([(wort[r["id"]], r["typ_id"]) for r in bestaetigt if r["typ_id"]]).bestes(ws),
        "tags": erkennen.tags(ws, [(wort[r["id"]], tags_je.get(r["id"], set())) for r in bestaetigt], alle_tags),
    }


def wieder_anstellen() -> int:
    """Nach einem Neustart: was beim Beenden noch gelesen wurde, weiterlesen."""
    if not (DATEN / "dokumente.db").exists():
        return 0
    with db() as c:
        ids = [r[0] for r in c.execute("SELECT id FROM dokumente WHERE zustand = 'lesen'")]
    for i in ids:
        _anstellen(i)
    return len(ids)


def jetzt_lesen_alle() -> None:
    """Für Tests und die CLI: Warteschlange im eigenen Thread abarbeiten."""
    while True:
        try:
            id_ = _warteschlange.get_nowait()
        except queue.Empty:
            return
        lesen(id_)
