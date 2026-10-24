"""Scannen über SANE (scanimage), vor allem für Netzwerkscanner mit eSCL/AirScan.

Ein Scan ist eine Sitzung mit Durchgängen: erst die Vorderseiten (Einzug oder
Glas), auf Wunsch danach die Rückseiten. Für die wird der ganze Stapel
gewendet und noch einmal eingezogen. Dabei läuft er von hinten nach vorn
durch: das letzte Blatt kommt zuerst (am Canon TR4551 geprüft). Die
Rückseiten werden deshalb umgedreht und Blatt für Blatt zugeordnet. Dass sie
auf dem Kopf stehen, richtet die Texterkennung (ocr.py).

Ein Stau bricht den Durchgang ab, aber nicht die Sitzung: die fertigen Seiten
bleiben, und es geht mit dem Rest weiter.
"""
import re
import shutil
import subprocess
import tempfile
import threading
import time
import urllib.request
import uuid
from pathlib import Path

from PIL import Image

from . import ablage, ocr

DPI = 300
A4_MM = 297      # der Einzug liefert sonst Legal-Länge mit weißem Rand unten
_sitzungen: dict[str, "Sitzung"] = {}
_lock = threading.Lock()
_geraete_cache: tuple[float, list[dict]] = (0.0, [])


def verfuegbar() -> bool:
    return shutil.which("scanimage") is not None


def geraete(frisch: bool = False) -> list[dict]:
    """Scanner im Netz und am Rechner. Die Suche dauert ein paar Sekunden,
    darum eine Minute zwischengespeichert."""
    global _geraete_cache
    if not verfuegbar():
        return []
    if not frisch and time.time() - _geraete_cache[0] < 60:
        return _geraete_cache[1]
    try:
        out = subprocess.run(["scanimage", "-L"], capture_output=True, text=True, timeout=60).stdout
    except (OSError, subprocess.TimeoutExpired):
        return []
    liste = []
    for m in re.finditer(r"device `([^']+)' is a (.+)", out):
        ip = re.search(r"ip=([0-9a-fA-F.:]+)", m.group(2))
        liste.append({"id": m.group(1), "name": m.group(2).split(" ip=")[0].strip(),
                      "ip": ip.group(1) if ip else ""})
    # Netzwerkscanner über eSCL zuerst: die können sagen, ob Papier im Einzug liegt
    liste.sort(key=lambda g: (not g["id"].startswith("airscan:"), g["name"]))
    _geraete_cache = (time.time(), liste)
    return liste


def einzug_belegt(geraet: dict) -> bool | None:
    """None = weiß der Scanner nicht (nur eSCL-Geräte melden es)."""
    if not geraet.get("ip"):
        return None
    host = f"[{geraet['ip']}]" if ":" in geraet["ip"] else geraet["ip"]
    try:
        with urllib.request.urlopen(f"http://{host}/eSCL/ScannerStatus", timeout=5) as r:
            t = r.read()
    except OSError:
        return None
    if b"ScannerAdfLoaded" in t:
        return True
    if b"ScannerAdfEmpty" in t:
        return False
    return None


def leer(bild: Image.Image) -> bool:
    """Leere Rückseite? In voller Auflösung, damit dünne Bleistift- und
    Kuli-Notizen nicht weggerechnet werden. Durchscheinender Text von vorn ist
    hellgrau und zählt kaum. Im Zweifel bleibt die Seite drin.
    Gemessen: Notiz „Hinten Seite 1“ ~0,03 % dunkle Fläche, nur Durchscheinen ~0,003 %."""
    g = bild.convert("L")
    w, h = g.size
    g = g.crop((w // 12, h // 60, w - w // 12, h - h // 60))   # Ränder und Lochung
    dunkel = sum(g.histogram()[:130])
    return dunkel / (g.width * g.height) < 0.0001


class Sitzung:
    def __init__(self, geraet: dict, farbe: bool):
        self.id = uuid.uuid4().hex[:12]
        self.geraet = geraet
        self.farbe = farbe
        self.ordner = Path(tempfile.mkdtemp(prefix="construct-scan-"))
        (self.ordner / "vorne").mkdir()
        (self.ordner / "hinten").mkdir()
        self.zustand = "bereit"     # bereit | scannt | stau | fehler | fertig
        self.meldung = ""
        self.quelle = ""            # einzug | glas (des ersten Durchgangs)
        self.seite = "vorne"        # Durchgang, der zuletzt lief (für Weiter nach Stau)
        self.thread: threading.Thread | None = None
        self.erstellt = time.time()

    def seiten(self, seite: str) -> list[Path]:
        return sorted((self.ordner / seite).glob("s*.jpg"))

    def stand(self) -> dict:
        return {"id": self.id, "zustand": self.zustand, "meldung": self.meldung, "quelle": self.quelle,
                "geraet": self.geraet["name"], "farbe": self.farbe, "seite": self.seite,
                "vorne": len(self.seiten("vorne")), "hinten": len(self.seiten("hinten"))}

    def _scan(self, quelle: str, seite: str) -> None:
        ziel = self.ordner / seite
        start = len(self.seiten(seite)) + 1
        cmd = ["scanimage", "-d", self.geraet["id"], "--source", "ADF" if quelle == "einzug" else "Flatbed",
               "--mode", "Color" if self.farbe else "Gray", "--resolution", str(DPI),
               "--format=jpeg", "-y", str(A4_MM)]
        if quelle == "einzug":
            r = subprocess.run(cmd + [f"--batch={ziel}/s%03d.jpg", f"--batch-start={start}"],
                               capture_output=True, text=True, timeout=3600)
            ok = r.returncode in (0, 7)       # 7 = Stapel zu Ende, das ist der Normalfall
        else:
            with open(ziel / f"s{start:03d}.jpg", "wb") as f:
                r = subprocess.run(cmd, stdout=f, stderr=subprocess.PIPE, text=True, timeout=600)
            ok = r.returncode == 0
        # Eine beim Stau halb übertragene Seite ist kaputt und wird neu gescannt
        for p in self.seiten(seite):
            try:
                with Image.open(p) as b:
                    b.load()
            except OSError:
                p.unlink()
        if not ok:
            fertig = len(self.seiten(seite))
            self.zustand = "stau" if quelle == "einzug" else "fehler"
            self.meldung = (r.stderr.strip().splitlines() or ["Scan fehlgeschlagen"])[-1][:200]
            if quelle == "einzug":
                self.meldung = f"{self.meldung} ({fertig})"
        else:
            self.zustand = "bereit"
            self.meldung = ""

    def starten(self, quelle: str, seite: str) -> None:
        if self.zustand == "scannt":
            raise ablage.Fehler("Es wird schon gescannt")
        if seite == "vorne" and not self.quelle:
            self.quelle = quelle
        self.seite = seite
        self.zustand = "scannt"
        self.meldung = ""

        def lauf():
            try:
                self._scan(quelle, seite)
            except Exception as e:
                self.zustand, self.meldung = "fehler", str(e)[:200]
        self.thread = threading.Thread(target=lauf, name="scan", daemon=True)
        self.thread.start()

    def fertig(self, einzeln: bool, zuordnung: list[int] | None = None) -> list[dict]:
        """Seiten zu Dokumenten machen. einzeln = jedes Blatt ein Dokument.

        zuordnung: je Rückseite (in Scan-Reihenfolge) die Nummer ihres Blatts
        (ab 1, 0 = keins). Nötig, wenn nicht der ganze Stapel gewendet wurde,
        sondern nur die Blätter mit Rückseite: dann lässt sich nicht abzählen,
        welche Rückseite wohin gehört."""
        if self.zustand == "scannt":
            raise ablage.Fehler("Der Scan läuft noch")
        vorne = self.seiten("vorne")
        gescannt = self.seiten("hinten")
        if not vorne:
            raise ablage.Fehler("Es wurde nichts gescannt")
        rueck: dict[int, Path] = {}
        extra = []
        if zuordnung is not None:
            if len(zuordnung) != len(gescannt):
                raise ablage.Fehler("Zuordnung passt nicht zu den Rückseiten")
            ohne = []
            for p, blatt in zip(gescannt, zuordnung):
                if 1 <= blatt <= len(vorne) and blatt - 1 not in rueck:
                    rueck[blatt - 1] = p
                else:
                    ohne.append(p)
            extra = [ohne] if ohne else []
        elif gescannt and len(gescannt) == len(vorne):
            # Gewendeter Stapel läuft von hinten nach vorn durch
            rueck = dict(enumerate(reversed(gescannt)))
        elif gescannt:
            # Doppeleinzug oder vergessenes Blatt: nicht raten, Rückseiten getrennt ablegen
            extra = [gescannt]
        blaetter = []
        for i, v in enumerate(vorne):
            b = [v]
            if i in rueck:
                with Image.open(rueck[i]) as r:
                    if not leer(r):
                        b.append(rueck[i])
            blaetter.append(b)
        gruppen = blaetter if einzeln else [[s for b in blaetter for s in b]]
        stempel = time.strftime("%d.%m.%Y %H:%M")
        neu = []
        for n, g in enumerate(gruppen + extra, 1):
            bilder = [Image.open(p) for p in g]
            try:
                pdf = self.ordner / f"dok{n}.pdf"
                ocr.bilder_zu_pdf(bilder, pdf, DPI)
                titel = f"Scan {stempel}" + (f" ({n})" if len(gruppen) + len(extra) > 1 else "")
                if g in extra:
                    titel += " Rückseiten, bitte prüfen"
                neu.append(ablage.neu(pdf, titel=titel, quelle="scan", vorschau_bild=bilder[0]))
            finally:
                for b in bilder:
                    b.close()
        self.zustand = "fertig"
        self.aufraeumen()
        return neu

    def aufraeumen(self) -> None:
        shutil.rmtree(self.ordner, ignore_errors=True)


def neu(geraet_id: str = "", quelle: str = "auto", farbe: bool = False) -> dict:
    """Startet eine Sitzung mit dem ersten Durchgang. quelle: auto | einzug | glas."""
    gs = geraete()
    if not gs:
        raise ablage.Fehler("Kein Scanner gefunden. Ist er eingeschaltet und im selben Netz?")
    g = next((x for x in gs if x["id"] == geraet_id), gs[0])
    if quelle == "auto":
        quelle = "einzug" if einzug_belegt(g) else "glas"
    if quelle not in ("einzug", "glas"):
        raise ablage.Fehler("Quelle unbekannt")
    with _lock:
        # Alte, liegengelassene Sitzungen wegräumen (der Scanner kann eh nur einen)
        for k, s in list(_sitzungen.items()):
            if s.zustand != "scannt" and time.time() - s.erstellt > 3600:
                s.aufraeumen()
                del _sitzungen[k]
        if any(s.zustand == "scannt" for s in _sitzungen.values()):
            raise ablage.Fehler("Es wird schon gescannt")
        s = Sitzung(g, farbe)
        _sitzungen[s.id] = s
    s.starten(quelle, "vorne")
    return s.stand()


def sitzung(sid: str) -> Sitzung:
    s = _sitzungen.get(sid)
    if not s:
        raise KeyError(sid)
    return s


def weiter(sid: str, was: str) -> dict:
    """was: glas (noch eine Seite vorn), einzug (nach Stau weiter), rueckseiten."""
    s = sitzung(sid)
    if was == "rueckseiten":
        s.starten("einzug", "hinten")
    elif was == "einzug":
        s.starten("einzug", s.seite)
    elif was == "glas":
        s.starten("glas", "vorne")
    else:
        raise ablage.Fehler("unbekannter Schritt")
    return s.stand()


def abschliessen(sid: str, einzeln: bool, zuordnung: list[int] | None = None) -> list[dict]:
    s = sitzung(sid)
    neu_ = s.fertig(einzeln, zuordnung)
    _sitzungen.pop(sid, None)
    return neu_


def abbrechen(sid: str) -> None:
    s = _sitzungen.pop(sid, None)
    if s:
        s.aufraeumen()


def seitenbild(sid: str, seite: str, n: int) -> bytes:
    """Kleines Vorschaubild einer gescannten Seite (n ab 1)."""
    s = sitzung(sid)
    if seite not in ("vorne", "hinten"):
        raise KeyError(seite)
    seiten = s.seiten(seite)
    if not 1 <= n <= len(seiten):
        raise KeyError(n)
    import io
    with Image.open(seiten[n - 1]) as b:
        b.thumbnail((240, 340))
        out = io.BytesIO()
        b.save(out, "WEBP", quality=60)
        return out.getvalue()
