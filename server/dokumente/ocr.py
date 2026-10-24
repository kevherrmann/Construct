"""Texterkennung und Vorschaubilder.

OCRmyPDF legt eine unsichtbare Textschicht über die gescannten Seiten: das PDF
sieht aus wie vorher, ist aber durchsuchbar und kopierbar. Es dreht dabei
schiefe und kopfstehende Seiten. Die Schwelle dafür steht bewusst niedrig: die
Rückseiten eines gewendeten Stapels liegen auf dem Kopf, und mit der
Standardschwelle blieb etwa die Hälfte davon falsch herum (an echten Scans
gemessen).

Ohne OCRmyPDF wird das PDF unverändert abgelegt. Es lässt sich dann nur über
Titel, Absender und Tags finden, nicht über seinen Inhalt.
"""
import io
import shutil
import subprocess
from pathlib import Path

from PIL import Image
from pypdf import PdfReader

SPRACHEN = "deu+eng"
VORSCHAU_BREITE = 360


def verfuegbar() -> bool:
    return shutil.which("ocrmypdf") is not None


def _sprachen() -> str:
    """Nur Sprachen anfordern, die Tesseract auch hat, sonst bricht OCRmyPDF ab."""
    try:
        out = subprocess.run(["tesseract", "--list-langs"], capture_output=True, text=True,
                             timeout=20).stdout
    except (OSError, subprocess.TimeoutExpired):
        return "eng"
    da = {z.strip() for z in out.splitlines()[1:]}
    gewollt = [s for s in SPRACHEN.split("+") if s in da]
    return "+".join(gewollt) or "eng"


def text_aus_pdf(pdf: Path) -> tuple[str, int]:
    try:
        r = PdfReader(str(pdf))
        seiten = [p.extract_text() or "" for p in r.pages]
        return "\f".join(seiten).strip(), len(r.pages)
    except Exception:
        return "", 0


def verarbeiten(quelle: Path, ziel: Path) -> tuple[str, int, str]:
    """Liest quelle, schreibt das durchsuchbare PDF nach ziel.
    Gibt (Text, Seitenzahl, Hinweis) zurück; Hinweis leer = alles gut."""
    hinweis = ""
    if verfuegbar():
        r = subprocess.run(
            ["ocrmypdf", "-q", "-l", _sprachen(), "--rotate-pages", "--rotate-pages-threshold", "2",
             "--deskew", "--skip-text", "--output-type", "pdf", "--optimize", "1",
             str(quelle), str(ziel)],
            capture_output=True, text=True, timeout=1800)
        # 6 = schon Text drin (digitales PDF), 10 = PDF/A-Umwandlung unvollständig: beides brauchbar
        if r.returncode not in (0, 6, 10) or not ziel.exists():
            shutil.copyfile(quelle, ziel)
            hinweis = (r.stderr.strip().splitlines() or ["Texterkennung fehlgeschlagen"])[-1][:300]
    else:
        # Kein Hinweis je Dokument: die Oberfläche sagt es einmal oben (uebersicht.texterkennung)
        shutil.copyfile(quelle, ziel)
    text, seiten = text_aus_pdf(ziel)
    return text, seiten, hinweis


def bilder_zu_pdf(bilder: list[Image.Image], ziel: Path, dpi: int = 300) -> None:
    rgb = [b.convert("L") if b.mode in ("L", "1", "LA") else b.convert("RGB") for b in bilder]
    rgb[0].save(ziel, save_all=True, append_images=rgb[1:], resolution=dpi, quality=85)


def bild_datei_zu_pdf(datei: Path, ziel: Path) -> None:
    """Handyfoto oder Bild (auch HEIC) als einseitiges PDF."""
    try:
        from pillow_heif import register_heif_opener
        register_heif_opener()
    except ImportError:
        pass
    with Image.open(datei) as b:
        from PIL import ImageOps
        b = ImageOps.exif_transpose(b)
        dpi = b.info.get("dpi", (150, 150))[0] or 150
        bilder_zu_pdf([b], ziel, int(dpi))


def vorschau(pdf: Path, ziel: Path) -> bool:
    """Erste Seite als kleines WebP. Braucht Ghostscript (bringt OCRmyPDF mit)."""
    gs = shutil.which("gs") or shutil.which("gswin64c") or shutil.which("gswin32c")
    if not gs:
        return False
    try:
        r = subprocess.run([gs, "-q", "-dSAFER", "-dBATCH", "-dNOPAUSE", "-sDEVICE=png16m",
                            "-dFirstPage=1", "-dLastPage=1", "-r60", "-sOutputFile=-", str(pdf)],
                           capture_output=True, timeout=60)
        if r.returncode != 0 or not r.stdout:
            return False
        with Image.open(io.BytesIO(r.stdout)) as b:
            b.thumbnail((VORSCHAU_BREITE, VORSCHAU_BREITE * 2))
            ziel.parent.mkdir(parents=True, exist_ok=True)
            b.save(ziel, "WEBP", quality=70)
        return True
    except (OSError, subprocess.TimeoutExpired):
        return False
