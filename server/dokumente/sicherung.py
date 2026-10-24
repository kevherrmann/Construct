"""Sicherung der Dokumente-Ablage.

Wer nach dem Scannen das Papier wegwirft, hat nur noch die Ablage. Darum
zwei Ziele, jedes für sich einstellbar:

  ordner   ein Ordner, am besten auf einer anderen Platte, einem USB-Laufwerk
           oder einem NAS. Darin liegt ein Spiegel (CONSTRUCT-Dokumente/):
           dieselben PDFs in derselben Ordnerstruktur, ohne CONSTRUCT lesbar.
           Was in der Ablage verschwindet oder sich ändert (Umbenennen beim
           Einsortieren), wandert dort nach _ersetzt/ statt gelöscht zu
           werden; nach ERSETZT_TAGE räumt es sich weg.
  server   ein Server per SFTP (eigener VPS, Storage Box, NAS). Was das Haus
           verlässt, ist mit Kennwort verschlüsselt. Jede Datei liegt dort
           einmal als objekte/<sha256>.enc, dazu je Lauf ein verschlüsselter
           Stand (welche Datei welchen Inhalt hat). Ein Lauf lädt nur hoch,
           was neu ist; Umbenennen kostet nichts.

Gesichert werden die PDFs (dateien/, papierkorb/, noch nicht gelesene in
verarbeitung/) und ein Abzug der Datenbank. Die Vorschaubilder nicht, die
entstehen neu.

Der Ordner des Ziels muss schon da sein: ist die externe Platte nicht
eingesteckt, soll die Sicherung scheitern und das sagen, statt still auf die
Systemplatte zu schreiben.

Das Kennwort liegt in dokumente/geheim.json (nur für den Nutzer lesbar), nie
in einer Sicherung. Wer es verliert, kommt an die Server-Sicherung nicht mehr
heran.
"""
import hashlib
import json
import os
import shutil
import sqlite3
import tempfile
import threading
from datetime import datetime, timedelta
from pathlib import Path

from server.sicherung import Fehler, krypto
from server.sicherung.sftp import Server

from . import ablage

UNTERORDNER = "CONSTRUCT-Dokumente"
BEREICHE = ("dateien", "papierkorb", "verarbeitung")
ERSETZT_TAGE = 90
STAENDE_BEHALTEN = 30
SERVER_ORDNER = "sicherungen/dokumente"
# Nach einer Änderung kurz warten: wer einen Stapel scannt, ändert zehnmal in
# zwanzig Minuten, gesichert werden soll danach einmal.
RUHE = timedelta(minutes=15)
WIEDERHOLEN = timedelta(hours=1)
ZIELE = ("ordner", "server")

_lauf = threading.Lock()


# ---------- Einstellungen und Kennwort ----------

def _einst_pfad() -> Path:
    return ablage.DATEN / "sicherung.json"


def _geheim_pfad() -> Path:
    return ablage.DATEN / "geheim.json"


def einstellungen() -> dict:
    try:
        e = json.loads(_einst_pfad().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        e = {}
    e.setdefault("ordner", "")
    e.setdefault("server", {})
    e.setdefault("zustand", {})
    return e


def _speichern(e: dict) -> None:
    p = _einst_pfad()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(e, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(p)


def kennwort() -> str:
    try:
        return json.loads(_geheim_pfad().read_text(encoding="utf-8")).get("kennwort", "")
    except (OSError, ValueError):
        return ""


def _kennwort_setzen(neu: str) -> None:
    p = _geheim_pfad()
    if not neu:
        p.unlink(missing_ok=True)
        return
    krypto.kennwort_pruefen(neu)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps({"kennwort": neu}), encoding="utf-8")
    tmp.chmod(0o600)
    tmp.replace(p)


def _server(e: dict) -> Server | None:
    s = e.get("server") or {}
    if not s.get("host"):
        return None
    return Server(s["host"], s.get("benutzer", ""), s.get("port") or 0,
                  s.get("ordner") or SERVER_ORDNER, s.get("schluessel", ""))


def einrichten(felder: dict) -> dict:
    """Ziele ändern. ordner: Pfad oder "" (aus). server: {host, benutzer, port,
    ordner, schluessel} oder {} (aus). kennwort: nur wenn angegeben."""
    e = einstellungen()
    if "ordner" in felder:
        pfad = str(felder["ordner"] or "").strip()
        if pfad:
            p = Path(pfad).expanduser()
            if not p.is_absolute():
                raise Fehler("Bitte einen vollständigen Pfad angeben (z. B. /media/platte/Sicherung).")
            if not p.is_dir():
                raise Fehler(f"Den Ordner {p} gibt es nicht. Ist die Platte angeschlossen?")
            if _innen(p):
                raise Fehler("Der Sicherungsordner darf nicht in der Ablage selbst liegen.")
            pfad = str(p)
        if pfad != e["ordner"]:
            e["zustand"].pop("ordner", None)
        e["ordner"] = pfad
    if "server" in felder:
        s = felder["server"] or {}
        neu = {k: str(s.get(k) or "").strip() for k in ("host", "benutzer", "ordner", "schluessel")}
        neu["port"] = int(s.get("port") or 0)
        if neu["host"]:
            _server({"server": neu})            # prüft die Angaben
        else:
            neu = {}
        if neu != e["server"]:
            e["zustand"].pop("server", None)
        e["server"] = neu
    if "kennwort" in felder:
        _kennwort_setzen(str(felder["kennwort"] or ""))
    _speichern(e)
    return stand()


def _innen(p: Path) -> bool:
    try:
        p.resolve().relative_to(ablage.DATEN.resolve())
        return True
    except ValueError:
        return False


# ---------- Was gesichert wird ----------

def _quellen() -> dict[str, Path]:
    """relpath → Datei, ohne die Datenbank."""
    raus = {}
    for bereich in BEREICHE:
        wurzel = ablage.DATEN / bereich
        if not wurzel.is_dir():
            continue
        for f in wurzel.rglob("*"):
            if not f.is_file():
                continue
            if bereich == "verarbeitung" and not f.name.removesuffix(".pdf").isdigit():
                continue        # Zwischenstände (.ocr.pdf, .sperre) entstehen neu
            raus[f.relative_to(ablage.DATEN).as_posix()] = f
    return raus


def fingerabdruck() -> str:
    """Ändert sich, sobald sich an Dateien oder Datenbank etwas ändert."""
    h = hashlib.sha256()
    for rel, f in sorted(_quellen().items()):
        st = f.stat()
        h.update(f"{rel}\0{st.st_size}\0{st.st_mtime_ns}\n".encode())
    if (ablage.DATEN / "dokumente.db").exists():
        with ablage.db() as c:
            r = c.execute("SELECT COUNT(*), COALESCE(MAX(geaendert), ''), COALESCE(SUM(eingang), 0) "
                          "FROM dokumente").fetchone()
            h.update(repr(tuple(r)).encode())
            h.update(repr(c.execute("SELECT group_concat(dok_id || ':' || tag_id) FROM dok_tags")
                          .fetchone()[0]).encode())
    return h.hexdigest()


def _db_abzug(ziel: Path) -> None:
    """Konsistenter Abzug, auch während der Server schreibt."""
    with ablage.db() as c:
        neu = sqlite3.connect(ziel)
        try:
            c.backup(neu)
        finally:
            neu.close()


def _sha(f: Path) -> str:
    h = hashlib.sha256()
    with open(f, "rb") as d:
        for stueck in iter(lambda: d.read(1 << 20), b""):
            h.update(stueck)
    return h.hexdigest()


# ---------- Ziel: Ordner ----------

def _ordner_sichern(basis: Path) -> str:
    if not basis.is_dir():
        raise Fehler(f"Der Sicherungsordner {basis} ist nicht da. Ist die Platte angeschlossen?")
    ziel = basis / UNTERORDNER
    ziel.mkdir(exist_ok=True)
    probe = ziel / ".schreibprobe"
    try:
        probe.write_bytes(b"ok")
        probe.unlink()
    except OSError as e:
        raise Fehler(f"In {ziel} lässt sich nicht schreiben: {e.strerror or e}") from None
    jetzt = datetime.now()
    ersetzt = ziel / "_ersetzt" / jetzt.strftime("%Y-%m-%d_%H%M%S")
    quellen = _quellen()
    neu = geaendert = weg = 0

    def beiseite(f: Path):
        rel = f.relative_to(ziel)
        z = ersetzt / rel
        z.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(f, z)

    for rel, quelle in quellen.items():
        z = ziel / rel
        st = quelle.stat()
        if z.is_file():
            zs = z.stat()
            # 2 s Spielraum: FAT/exFAT speichern Zeiten nur auf 2 s genau
            if zs.st_size == st.st_size and abs(zs.st_mtime - st.st_mtime) <= 2:
                continue
            beiseite(z)
            geaendert += 1
        else:
            neu += 1
        z.parent.mkdir(parents=True, exist_ok=True)
        tmp = z.with_name(z.name + ".tmp")
        shutil.copy2(quelle, tmp)
        os.replace(tmp, z)
    # Was es in der Ablage nicht mehr gibt (umbenannt, endgültig gelöscht)
    for bereich in BEREICHE:
        wurzel = ziel / bereich
        if not wurzel.is_dir():
            continue
        for f in sorted(wurzel.rglob("*"), reverse=True):
            if f.is_file() and f.relative_to(ziel).as_posix() not in quellen:
                beiseite(f)
                weg += 1
            elif f.is_dir():
                try:
                    f.rmdir()           # nur leere
                except OSError:
                    pass
    db_tmp = ziel / "dokumente.db.tmp"
    _db_abzug(db_tmp)
    if (ziel / "dokumente.db").exists():
        os.replace(ziel / "dokumente.db", ziel / "dokumente.db.vorher")
    os.replace(db_tmp, ziel / "dokumente.db")
    (ziel / "LIESMICH.txt").write_text(
        "Sicherung der CONSTRUCT-Dokumente.\n\n"
        "dateien/      die Dokumente als PDF, nach Jahr und Absender\n"
        "papierkorb/   gelöschte Dokumente\n"
        "dokumente.db  Titel, Absender, Tags, gelesener Text\n"
        "_ersetzt/     ältere Fassungen umbenannter oder geänderter Dateien\n\n"
        "Zurückholen: doku.py restore --from ordner --to <neuer Ordner>\n", encoding="utf-8")
    grenze = (jetzt - timedelta(days=ERSETZT_TAGE)).strftime("%Y-%m-%d")
    if (ziel / "_ersetzt").is_dir():
        for alt in (ziel / "_ersetzt").iterdir():
            if alt.is_dir() and alt.name[:10] < grenze:
                shutil.rmtree(alt, ignore_errors=True)
    return f"{len(quellen)} Dateien, {neu} neu, {geaendert} geändert, {weg} beiseitegelegt"


# ---------- Ziel: Server ----------

def _stand_name(zeit: datetime) -> str:
    return f"stand-{zeit.strftime('%Y%m%d-%H%M%S')}.enc"


def _server_sichern(srv: Server, kw: str) -> str:
    if not kw:
        raise Fehler("Für den Server fehlt das Kennwort zum Verschlüsseln.")
    schluessel = krypto.Schluessel(kw)
    srv.testen()
    vorhanden = {n.removesuffix(".enc") for n in srv.liste("objekte") if n.endswith(".enc")}
    with tempfile.TemporaryDirectory(prefix="construct-sicherung-") as tmp:
        tmp = Path(tmp)
        db = tmp / "dokumente.db"
        _db_abzug(db)
        quellen = _quellen()
        karte = {rel: _sha(f) for rel, f in quellen.items()}
        db_sha = _sha(db)
        quelle_von = {karte[rel]: f for rel, f in quellen.items()}
        quelle_von[db_sha] = db
        fehlen = [sha for sha in quelle_von if sha not in vorhanden]
        # In Paketen: bei tausend Dokumenten nicht alles auf einmal verschlüsselt auf die Platte
        for i in range(0, len(fehlen), 40):
            paket = []
            for sha in fehlen[i:i + 40]:
                enc = tmp / f"{sha}.enc"
                enc.write_bytes(schluessel.verschluesseln(quelle_von[sha].read_bytes()))
                paket.append((enc, f"{sha}.enc"))
            srv.hochladen(paket, "objekte")
            for enc, _ in paket:
                enc.unlink()
        zeit = datetime.now()
        inhalt = {"version": 1, "zeit": zeit.isoformat(timespec="seconds"), "db": db_sha, "dateien": karte}
        name = _stand_name(zeit)
        (tmp / name).write_bytes(schluessel.verschluesseln(json.dumps(inhalt).encode()))
        srv.hochladen([(tmp / name, name)])
        # Gegenprobe: den Stand zurückholen und lesen. Ein Ziel, das nur
        # scheinbar funktioniert, soll heute auffallen und nicht im Ernstfall.
        zurueck = tmp / "probe.enc"
        srv.holen([(name, zurueck)])
        if json.loads(schluessel.entschluesseln(zurueck.read_bytes())) != inhalt:
            raise Fehler("Die Gegenprobe vom Server stimmt nicht mit der Sicherung überein.")
    _server_aufraeumen(srv, schluessel)
    return f"{len(karte)} Dateien, {len(fehlen)} neu hochgeladen"


def _server_aufraeumen(srv: Server, schluessel: krypto.Schluessel) -> None:
    """Nur die letzten Stände behalten, und nur Dateien, die einer davon braucht."""
    staende = sorted((n for n in srv.liste() if n.startswith("stand-") and n.endswith(".enc")), reverse=True)
    alt = staende[STAENDE_BEHALTEN:]
    if not alt:
        return
    gebraucht = set()
    with tempfile.TemporaryDirectory() as tmp:
        for n in staende[:STAENDE_BEHALTEN]:
            srv.holen([(n, Path(tmp) / n)])
            s = json.loads(schluessel.entschluesseln((Path(tmp) / n).read_bytes()))
            gebraucht |= set(s["dateien"].values()) | {s["db"]}
    weg = [f"{sha}.enc" for sha in {n.removesuffix(".enc") for n in srv.liste("objekte")} - gebraucht]
    srv.loeschen(alt)
    for i in range(0, len(weg), 200):
        srv.loeschen(weg[i:i + 200], "objekte")


# ---------- Ablauf ----------

def eingerichtet() -> list[str]:
    e = einstellungen()
    return [z for z in ZIELE if (e["ordner"] if z == "ordner" else (e["server"] or {}).get("host"))]


def sichern(ziele: list[str] | None = None) -> dict:
    """Sichert auf die eingerichteten Ziele. Ein Fehler bei einem Ziel hält
    das andere nicht auf; er steht im Zustand."""
    if not _lauf.acquire(blocking=False):
        raise Fehler("Es läuft schon eine Sicherung.")
    try:
        e = einstellungen()
        abdruck = fingerabdruck()
        for ziel in ziele or eingerichtet():
            z = e["zustand"].setdefault(ziel, {})
            z["versucht"] = datetime.now().isoformat(timespec="seconds")
            try:
                if ziel == "ordner":
                    z["ergebnis"] = _ordner_sichern(Path(e["ordner"]))
                else:
                    srv = _server(e)
                    if not srv:
                        raise Fehler("Kein Server eingerichtet.")
                    z["ergebnis"] = _server_sichern(srv, kennwort())
                z["letzte"] = z["versucht"]
                z["abdruck"] = abdruck
                z["fehler"] = ""
            except Fehler as f:
                z["fehler"] = str(f)
            except OSError as f:
                z["fehler"] = f"{f.strerror or f}"
            _speichern(e)
        return stand()
    finally:
        _lauf.release()


def faellig(jetzt: datetime | None = None) -> list[str]:
    """Ziele, die eine Sicherung brauchen: etwas hat sich geändert, die letzte
    Änderung ist RUHE her, und ein Fehler liegt WIEDERHOLEN zurück."""
    jetzt = jetzt or datetime.now()
    if not (ablage.DATEN / "dokumente.db").exists():
        return []
    e = einstellungen()
    abdruck = fingerabdruck()
    with ablage.db() as c:
        zuletzt = c.execute("SELECT MAX(geaendert) FROM dokumente").fetchone()[0]
    if zuletzt and jetzt - datetime.fromisoformat(zuletzt) < RUHE:
        return []
    raus = []
    for ziel in eingerichtet():
        z = e["zustand"].get(ziel, {})
        if z.get("abdruck") == abdruck and not z.get("fehler"):
            continue
        if z.get("fehler") and z.get("versucht") and \
                jetzt - datetime.fromisoformat(z["versucht"]) < WIEDERHOLEN:
            continue
        raus.append(ziel)
    return raus


def stand() -> dict:
    e = einstellungen()
    abdruck = fingerabdruck() if (ablage.DATEN / "dokumente.db").exists() else ""
    ziele = {}
    for ziel in ZIELE:
        z = e["zustand"].get(ziel, {})
        ziele[ziel] = {
            "an": ziel in eingerichtet(),
            "letzte": z.get("letzte", ""),
            "fehler": z.get("fehler", ""),
            "ergebnis": z.get("ergebnis", ""),
            "aktuell": bool(z.get("abdruck")) and z.get("abdruck") == abdruck and not z.get("fehler"),
        }
    srv = dict(e["server"] or {})
    return {"ordner": e["ordner"], "server": srv, "kennwort": bool(kennwort()), "ziele": ziele,
            "eingerichtet": bool(eingerichtet()), "laeuft": _lauf.locked()}


# ---------- Zurückholen ----------

def wiederherstellen(quelle: str, ziel: Path) -> dict:
    """Holt die Ablage aus einer Sicherung nach ziel (muss leer sein oder
    fehlen) und prüft jede Datei. Überschreibt nie die laufende Ablage."""
    ziel = Path(ziel).expanduser()
    if ziel.exists() and any(ziel.iterdir()):
        raise Fehler(f"{ziel} ist nicht leer.")
    if _innen(ziel) or ziel.resolve() == ablage.DATEN.resolve():
        raise Fehler("Nicht in die laufende Ablage zurückholen.")
    ziel.mkdir(parents=True, exist_ok=True)
    e = einstellungen()
    if quelle == "ordner":
        basis = Path(e["ordner"]) / UNTERORDNER
        if not (basis / "dokumente.db").is_file():
            raise Fehler(f"In {basis} liegt keine Sicherung.")
        n = 0
        for bereich in BEREICHE:
            if (basis / bereich).is_dir():
                shutil.copytree(basis / bereich, ziel / bereich)
                n += sum(1 for f in (ziel / bereich).rglob("*") if f.is_file())
        shutil.copy2(basis / "dokumente.db", ziel / "dokumente.db")
        return {"dateien": n, "ziel": str(ziel)}
    if quelle != "server":
        raise Fehler("Quelle ist ordner oder server.")
    srv = _server(e)
    if not srv:
        raise Fehler("Kein Server eingerichtet.")
    schluessel = krypto.Schluessel(kennwort())
    staende = sorted(n for n in srv.liste() if n.startswith("stand-") and n.endswith(".enc"))
    if not staende:
        raise Fehler("Auf dem Server liegt noch keine Sicherung.")
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        srv.holen([(staende[-1], tmp / "stand.enc")])
        s = json.loads(schluessel.entschluesseln((tmp / "stand.enc").read_bytes()))
        alle = sorted(set(s["dateien"].values()) | {s["db"]})
        for i in range(0, len(alle), 40):
            paket = alle[i:i + 40]
            srv.holen([(f"{sha}.enc", tmp / f"{sha}.enc") for sha in paket], "objekte")
            for sha in paket:
                roh = schluessel.entschluesseln((tmp / f"{sha}.enc").read_bytes())
                if hashlib.sha256(roh).hexdigest() != sha:
                    raise Fehler(f"Datei {sha[:12]}… ist beschädigt.")
                (tmp / f"{sha}.enc").write_bytes(roh)
        for rel, sha in s["dateien"].items():
            z = ziel / rel
            z.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(tmp / f"{sha}.enc", z)
        shutil.copyfile(tmp / f"{s['db']}.enc", ziel / "dokumente.db")
    return {"dateien": len(s["dateien"]), "ziel": str(ziel), "stand": s["zeit"]}


def pruefen(quelle: str) -> dict:
    """Probe: in einen leeren Ordner zurückholen und mit der Ablage vergleichen.
    Gibt an, was fehlt oder abweicht; leer heißt alles da."""
    with tempfile.TemporaryDirectory(prefix="construct-probe-") as tmp:
        ergebnis = wiederherstellen(quelle, Path(tmp) / "ablage")
        zurueck = Path(ergebnis["ziel"])
        jetzt = {rel: _sha(f) for rel, f in _quellen().items()}
        fehlt = [rel for rel, sha in jetzt.items()
                 if not (zurueck / rel).is_file() or _sha(zurueck / rel) != sha]
        con = sqlite3.connect(zurueck / "dokumente.db")
        try:
            anzahl = con.execute("SELECT COUNT(*) FROM dokumente").fetchone()[0]
        finally:
            con.close()
    with ablage.db() as c:
        soll = c.execute("SELECT COUNT(*) FROM dokumente").fetchone()[0]
    return {"dateien": len(jetzt), "fehlt": fehlt[:20], "fehlt_anzahl": len(fehlt),
            "dokumente": anzahl, "dokumente_soll": soll}


def hintergrund_schritt() -> None:
    """Ein Blick: sichert, was fällig ist. Läuft alle paar Minuten (app.py)."""
    try:
        ziele = faellig()
        if ziele:
            sichern(ziele)
    except Fehler:
        pass


async def schleife() -> None:
    import asyncio
    await asyncio.sleep(60)          # erst den Start in Ruhe lassen
    while True:
        try:
            from server import config as cfg
            if cfg.load_settings()["tiles"].get("dokumente", False):
                await asyncio.to_thread(hintergrund_schritt)
        except Exception as e:      # die Schleife darf nie sterben
            print(f"[dokumente] Sicherung: {type(e).__name__}: {e}", flush=True)
        await asyncio.sleep(300)

