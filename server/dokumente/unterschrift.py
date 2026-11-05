"""Dokumente unterschreiben.

Die Unterschrift liegt einmal als PNG mit durchsichtigem Hintergrund in
dokumente/unterschrift.png (gezeichnet oder aus einem Foto freigestellt).
Beim Unterschreiben wird sie, und auf Wunsch eine Textzeile wie „Lengerich,
05.11.2026“, als Bild bzw. Text auf die Seiten gelegt. Das Ergebnis ist ein
neues Dokument; das Original bleibt unverändert, damit klar ist, was vorher
vorlag.

Positionen kommen als Anteile der *sichtbaren* Seite (0..1, Ursprung oben
links), also so, wie man die Seite am Bildschirm sieht. Gedrehte Seiten
(/Rotate) und ein versetzter Beschnitt (CropBox) werden hier umgerechnet,
damit die Oberfläche davon nichts wissen muss.
"""
import io
import shutil
import subprocess
import tempfile
import zlib
from pathlib import Path

from PIL import Image, ImageOps
from pypdf import PdfReader, PdfWriter
from pypdf.generic import (ArrayObject, DecodedStreamObject, DictionaryObject, NameObject, NumberObject,
                           StreamObject)

from server import config as cfg

from . import ablage

SEITE_DPI = 110
UNTERSCHRIFT_MAX = 1600     # Pixel Breite, reicht gedruckt für ~13 cm bei 300 dpi
TEXT_MAX = 120


def _pfad() -> Path:
    return ablage.DATEN / "unterschrift.png"


# ---------- Die Unterschrift selbst ----------

def vorhanden() -> bool:
    return _pfad().is_file()


def lesen() -> bytes:
    if not vorhanden():
        raise KeyError("unterschrift")
    return _pfad().read_bytes()


def freistellen(bild: Image.Image) -> Image.Image:
    """Foto oder Scan einer Unterschrift → nur die Tinte, Rest durchsichtig.
    Hell wird durchsichtig, dunkel deckend; dazwischen weich, sonst franst
    die Linie aus. Der Rand wird auf die Tinte zugeschnitten."""
    bild = ImageOps.exif_transpose(bild)
    if bild.mode in ("RGBA", "LA") or (bild.mode == "P" and "transparency" in bild.info):
        rgba = bild.convert("RGBA")
        # Schon freigestellt (etwa die gezeichnete): so lassen, nur zuschneiden
        if rgba.getchannel("A").getextrema()[0] < 250:
            return _zuschneiden(rgba)
        bild = rgba.convert("RGB")
    rgb = bild.convert("RGB")
    grau = ImageOps.autocontrast(rgb.convert("L"), cutoff=1)
    # Papier ist selten rein weiß: alles ab ~70 % Helligkeit gilt als Papier
    alpha = grau.point(lambda v: 0 if v >= 180 else 255 if v <= 90 else int((180 - v) * 255 / 90))
    rgba = rgb.convert("RGBA")
    rgba.putalpha(alpha)
    return _zuschneiden(rgba)


def _zuschneiden(rgba: Image.Image) -> Image.Image:
    box = rgba.getchannel("A").point(lambda v: 255 if v > 20 else 0).getbbox()
    if not box:
        raise ablage.Fehler("Auf dem Bild ist keine Unterschrift zu erkennen")
    rand = max(4, (box[2] - box[0]) // 50)
    box = (max(0, box[0] - rand), max(0, box[1] - rand),
           min(rgba.width, box[2] + rand), min(rgba.height, box[3] + rand))
    rgba = rgba.crop(box)
    if rgba.width > UNTERSCHRIFT_MAX:
        rgba = rgba.resize((UNTERSCHRIFT_MAX, max(1, round(rgba.height * UNTERSCHRIFT_MAX / rgba.width))),
                           Image.LANCZOS)
    return rgba


def speichern(daten: bytes) -> dict:
    try:
        from pillow_heif import register_heif_opener
        register_heif_opener()
    except ImportError:
        pass
    try:
        with Image.open(io.BytesIO(daten)) as b:
            b.load()
            rgba = freistellen(b)
    except (OSError, ValueError, Image.DecompressionBombError):
        raise ablage.Fehler("Das Bild lässt sich nicht lesen")
    ablage.DATEN.mkdir(parents=True, exist_ok=True)
    tmp = _pfad().with_suffix(".tmp")
    rgba.save(tmp, "PNG")
    tmp.replace(_pfad())
    return {"breite": rgba.width, "hoehe": rgba.height}


def loeschen() -> None:
    _pfad().unlink(missing_ok=True)


# ---------- Seiten ansehen ----------

def _sichtbar(seite) -> tuple[float, float, float, float, float, float, int]:
    """(links, unten, breite, höhe) des Beschnitts, dazu die sichtbare Breite/Höhe und die Drehung."""
    box = seite.cropbox
    l, u = float(box.left), float(box.bottom)
    b, h = float(box.width), float(box.height)
    dreh = (seite.rotation or 0) % 360
    sb, sh = (h, b) if dreh in (90, 270) else (b, h)
    return l, u, b, h, sb, sh, dreh


def seiten(id_: int) -> list[dict]:
    """Sichtbare Größe jeder Seite in Punkt: daraus setzt die Oberfläche das Seitenverhältnis."""
    r = PdfReader(str(ablage.datei(id_)))
    raus = []
    for s in r.pages:
        _, _, _, _, sb, sh, _ = _sichtbar(s)
        raus.append({"breite": round(sb, 2), "hoehe": round(sh, 2)})
    return raus


def seitenbild(id_: int, n: int) -> bytes | None:
    """Seite n (ab 1) als WebP. Ohne Ghostscript None: die Oberfläche zeigt dann
    ein leeres Blatt in der richtigen Größe, platzieren geht trotzdem."""
    gs = shutil.which("gs") or shutil.which("gswin64c") or shutil.which("gswin32c")
    if not gs:
        return None
    try:
        r = subprocess.run([gs, "-q", "-dSAFER", "-dBATCH", "-dNOPAUSE", "-dUseCropBox", "-sDEVICE=png16m",
                            f"-dFirstPage={n}", f"-dLastPage={n}", f"-r{SEITE_DPI}",
                            "-dTextAlphaBits=4", "-dGraphicsAlphaBits=4", "-sOutputFile=-",
                            str(ablage.datei(id_))],
                           capture_output=True, timeout=60)
        if r.returncode != 0 or not r.stdout:
            return None
        with Image.open(io.BytesIO(r.stdout)) as b:
            out = io.BytesIO()
            b.save(out, "WEBP", quality=80)
            return out.getvalue()
    except (OSError, subprocess.TimeoutExpired):
        return None


# ---------- Unterschreiben ----------

def _matrix_sichtbar_zu_pdf(l, u, b, h, dreh) -> list[float]:
    """Sichtbare Koordinaten (Ursprung unten links, in Punkt) → PDF-Nutzerraum.
    Ein Betrachter dreht die Seite um /Rotate Grad im Uhrzeigersinn; hier
    geht es zurück."""
    return {
        0: [1, 0, 0, 1, l, u],
        90: [0, 1, -1, 0, l + b, u],
        180: [-1, 0, 0, -1, l + b, u + h],
        270: [0, -1, 1, 0, l, u + h],
    }.get(dreh, [1, 0, 0, 1, l, u])


def _zahl(x: float) -> str:
    return f"{x:.4f}".rstrip("0").rstrip(".") or "0"


def _bild_objekt(w: PdfWriter, rgba: Image.Image):
    """PNG mit Alpha als PDF-Bild: Farbe und Deckkraft (SMask) getrennt."""
    rgb = rgba.convert("RGB")
    alpha = rgba.getchannel("A")

    def strom(daten: bytes, farbraum: str, extra: dict) -> StreamObject:
        s = StreamObject()
        s._data = zlib.compress(daten, 9)
        s.update({NameObject("/Type"): NameObject("/XObject"), NameObject("/Subtype"): NameObject("/Image"),
                  NameObject("/Width"): NumberObject(rgba.width), NameObject("/Height"): NumberObject(rgba.height),
                  NameObject("/ColorSpace"): NameObject(farbraum),
                  NameObject("/BitsPerComponent"): NumberObject(8),
                  NameObject("/Filter"): NameObject("/FlateDecode"), **extra})
        return s
    maske = w._add_object(strom(alpha.tobytes(), "/DeviceGray", {}))
    return w._add_object(strom(rgb.tobytes(), "/DeviceRGB", {NameObject("/SMask"): maske}))


def _text_pdf(s: str) -> str:
    """Für Helvetica mit WinAnsi: Umlaute als cp1252, Klammern maskiert."""
    roh = s.encode("cp1252", errors="replace")
    raus = ""
    for byte in roh:
        c = chr(byte)
        if c in "()\\":
            raus += "\\" + c
        elif byte < 32 or byte > 126:
            raus += f"\\{byte:03o}"
        else:
            raus += c
    return raus


def _ziffer(v, name: str) -> float:
    try:
        x = float(v)
    except (TypeError, ValueError):
        raise ablage.Fehler(f"{name} fehlt")
    if x != x or x < -1 or x > 2:     # NaN oder Unsinn
        raise ablage.Fehler(f"{name} liegt außerhalb der Seite")
    return x


def unterschreiben(id_: int, elemente: list[dict]) -> dict:
    """elemente: [{"art": "unterschrift" | "text", "seite": 1, "x": .., "y": .., "breite": ..,
    "text": "…"}]. x, y = obere linke Ecke, breite = Anteil der Seitenbreite;
    beim Text ist "hoehe" die Schriftgröße als Anteil der Seitenhöhe."""
    d = ablage.dokument(id_, mit_text=False)
    if d["zustand"] == "lesen":
        raise ablage.Fehler("Das Dokument wird noch gelesen")
    if not elemente:
        raise ablage.Fehler("Nichts zum Einfügen: erst die Unterschrift auf die Seite setzen")
    if len(elemente) > 50 or not all(isinstance(e, dict) for e in elemente):
        raise ablage.Fehler("Ungültige Elemente")
    if any(e.get("art") == "unterschrift" for e in elemente) and not vorhanden():
        raise ablage.Fehler("Noch keine Unterschrift hinterlegt")

    w = PdfWriter(clone_from=str(ablage.datei(id_)))
    bild_ref = None
    if vorhanden():
        with Image.open(_pfad()) as b:
            sig = b.convert("RGBA")
    pro_seite: dict[int, list[str]] = {}
    for e in elemente:
        art = e.get("art")
        try:
            n = int(e.get("seite") or 0)
        except (TypeError, ValueError):
            n = 0
        if not 1 <= n <= len(w.pages):
            raise ablage.Fehler("Seite gibt es nicht")
        l, u, b, h, sb, sh, dreh = _sichtbar(w.pages[n - 1])
        m = _matrix_sichtbar_zu_pdf(l, u, b, h, dreh)
        x, y = _ziffer(e.get("x"), "x") * sb, _ziffer(e.get("y"), "y") * sh
        ops = pro_seite.setdefault(n, [])
        if art == "unterschrift":
            breite = _ziffer(e.get("breite"), "Breite") * sb
            if breite <= 1:
                raise ablage.Fehler("Unterschrift zu klein")
            hoehe = breite * sig.height / sig.width
            if bild_ref is None:
                bild_ref = _bild_objekt(w, sig)
            ops.append(f"q {' '.join(map(_zahl, m))} cm {_zahl(breite)} 0 0 {_zahl(hoehe)} "
                       f"{_zahl(x)} {_zahl(sh - y - hoehe)} cm /CxUnterschrift Do Q")
        elif art == "text":
            text = " ".join(str(e.get("text") or "").split())[:TEXT_MAX]
            if not text:
                continue
            groesse = _ziffer(e.get("hoehe"), "Schriftgröße") * sh
            if not 3 <= groesse <= 72:
                raise ablage.Fehler("Schriftgröße zwischen 3 und 72 Punkt")
            # Grundlinie: ~80 % unter der Oberkante des Kastens
            ops.append(f"q {' '.join(map(_zahl, m))} cm BT /CxSchrift {_zahl(groesse)} Tf 0.1 0.1 0.15 rg "
                       f"{_zahl(x)} {_zahl(sh - y - groesse * 0.8)} Td ({_text_pdf(text)}) Tj ET Q")
        else:
            raise ablage.Fehler("Unbekanntes Element")
    if not any(pro_seite.values()):
        raise ablage.Fehler("Nichts zum Einfügen")

    schrift = None
    for n, ops in pro_seite.items():
        if not ops:
            continue
        seite = w.pages[n - 1]
        res = seite.get("/Resources")
        res = res.get_object() if res is not None else DictionaryObject()
        if "/Resources" not in seite:
            seite[NameObject("/Resources")] = res
        if bild_ref is not None and any("/CxUnterschrift" in o for o in ops):
            xo = res.get("/XObject")
            xo = xo.get_object() if xo is not None else DictionaryObject()
            xo[NameObject("/CxUnterschrift")] = bild_ref
            res[NameObject("/XObject")] = xo
        if any("/CxSchrift" in o for o in ops):
            if schrift is None:
                schrift = w._add_object(DictionaryObject({
                    NameObject("/Type"): NameObject("/Font"), NameObject("/Subtype"): NameObject("/Type1"),
                    NameObject("/BaseFont"): NameObject("/Helvetica"),
                    NameObject("/Encoding"): NameObject("/WinAnsiEncoding")}))
            fo = res.get("/Font")
            fo = fo.get_object() if fo is not None else DictionaryObject()
            fo[NameObject("/CxSchrift")] = schrift
            res[NameObject("/Font")] = fo
        # Der alte Inhalt kann den Grafikzustand verstellt hinterlassen: einklammern
        vorne, hinten = DecodedStreamObject(), DecodedStreamObject()
        vorne.set_data(b"q\n")
        hinten.set_data(("\nQ\n" + "\n".join(ops) + "\n").encode("latin-1"))
        alt = seite.get("/Contents")
        teile = ArrayObject()
        teile.append(w._add_object(vorne))
        if alt is not None:
            alt_o = alt.get_object()
            if isinstance(alt_o, ArrayObject):
                teile.extend(alt_o)
            else:
                teile.append(alt if hasattr(alt, "idnum") else w._add_object(alt_o))
        teile.append(w._add_object(hinten))
        seite[NameObject("/Contents")] = teile

    with tempfile.TemporaryDirectory() as tmp:
        pdf = Path(tmp) / "unterschrieben.pdf"
        with open(pdf, "wb") as f:
            w.write(f)
        titel = d["titel"] or "Dokument"
        x = ablage.neu(pdf, titel=f"{titel} {cfg.L('(unterschrieben)', '(signed)')}", quelle=d["quelle"])
    return ablage.aendern(x["id"], {"datum": d["datum"], "absender": d["absender"], "typ": d["typ"],
                                    "notiz": d["notiz"], "eingang": False,
                                    "tags": [g["name"] for g in d["tags"]]})
