"""Anhänge für den Chat ablegen (/api/upload). Erlaubt ist jede Datei; das
Modell bekommt nur den Pfad und öffnet sie mit seinen Werkzeugen.

Bilder werden beim Ablegen einmal normalisiert: EXIF-Drehung angewandt,
Metadaten weg, auf höchstens 2048×2048 Pixel und ~4 MB gebracht, HEIC/BMP
zu JPEG/PNG. Danach kann jedes Modell (claude wie Hermes) damit umgehen,
und Handyfotos kosten nicht mehr Tokens als nötig. Saubere, kleine
PNG/JPEG/WebP bleiben byte-gleich; SVG und animierte GIFs bleiben unangetastet.
PDFs und Office-Dateien bekommen einen Textauszug daneben (<name>.pdf.txt,
<name>.odt.txt …)."""
import io
import re
import shutil
import subprocess
import uuid
from pathlib import Path

from server import office_text

# Liegt in server/ — Daten und Einstellungen bleiben im Projektordner darüber.
BASE_DIR = Path(__file__).resolve().parent.parent
UPLOAD_DIR = BASE_DIR / "uploads"

IMG_EXT = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".svg", ".heic"}
PDF_EXT = {".pdf"}
MAX_UPLOAD = 25 * 1024 * 1024

MAX_PIXELS = 2048 * 2048          # Gesamtbudget, Seitenverhältnis bleibt
TARGET_BYTES = 4 * 1024 * 1024    # darüber wird die Qualität gesenkt
QUALITY_LADDER = (85, 75, 60)


def extract_pdf_text(pdf: Path) -> str:
    """Text einer PDF — pdftotext (poppler), sonst pypdf, sonst leer (z.B. Scan)."""
    if shutil.which("pdftotext"):
        try:
            r = subprocess.run(["pdftotext", "-layout", str(pdf), "-"],
                               capture_output=True, timeout=30)
            if r.returncode == 0 and r.stdout.strip():
                return r.stdout.decode("utf-8", "replace")
        except Exception:
            pass
    try:
        from pypdf import PdfReader
        return "\n\n".join((pg.extract_text() or "") for pg in PdfReader(str(pdf)).pages)
    except Exception:
        return ""


def normalize_image(data: bytes, ext: str) -> tuple[bytes, str]:
    """(bytes, ext) — normalisiert oder unverändert, wenn Pillow fehlt/nichts zu tun ist."""
    if ext in (".svg",):
        return data, ext
    try:
        from PIL import Image, ImageOps
        if ext == ".heic":
            import pillow_heif
            pillow_heif.register_heif_opener()
        im = Image.open(io.BytesIO(data))
        im.load()
    except Exception:
        return data, ext
    if getattr(im, "is_animated", False):
        return data, ext
    fmt = (im.format or "").upper()
    exif_rot = im.getexif().get(0x0112, 1) not in (1, None)
    w, h = im.size
    fits = w * h <= MAX_PIXELS and len(data) <= TARGET_BYTES
    if fits and not exif_rot and fmt in ("PNG", "JPEG", "WEBP") and im.mode in ("RGB", "RGBA", "L"):
        return data, ext
    im = ImageOps.exif_transpose(im)
    w, h = im.size                     # nach der Drehung neu — sonst kippt das Seitenverhältnis
    if w * h > MAX_PIXELS:
        scale = (MAX_PIXELS / (w * h)) ** 0.5
        im = im.resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.LANCZOS)
    alpha = im.mode in ("RGBA", "LA", "P") and (
        im.mode != "P" or "transparency" in im.info)
    im = im.convert("RGBA" if alpha else "RGB")
    best = None
    for q in QUALITY_LADDER:
        buf = io.BytesIO()
        if alpha:
            im.save(buf, "WEBP", quality=q, method=4)
            new_ext = ".webp"
        else:
            im.save(buf, "JPEG", quality=q, optimize=True)
            new_ext = ".jpg"
        out = buf.getvalue()
        if best is None or len(out) < len(best[0]):
            best = (out, new_ext)
        if len(out) <= TARGET_BYTES:
            break
    return best


def kind_of(ext: str) -> str:
    ext = ext.lower()
    if ext in IMG_EXT:
        return "image"
    return "pdf" if ext in PDF_EXT else "file"


def store(data: bytes, ext: str, name: str) -> dict:
    """Anhang unter zufälligem Namen in uploads/ ablegen; gibt das dict fürs Frontend."""
    ext = ext.lower()
    # Die Endung landet im Dateinamen und in der URL: nur harmlose Zeichen.
    if not re.fullmatch(r"\.[a-z0-9]{1,10}", ext):
        ext = ""
    if len(data) > MAX_UPLOAD:
        raise ValueError("Datei zu groß (max. 25 MB)")
    kind = kind_of(ext)
    if kind == "image":
        data, ext = normalize_image(data, ext)
    UPLOAD_DIR.mkdir(exist_ok=True)
    fname = f"{uuid.uuid4().hex}{ext}"
    dest = UPLOAD_DIR / fname
    dest.write_bytes(data)
    # Den Auszug liest das Modell billiger als die gerenderten Seiten, und
    # Office-Dateien kann sein Read-Tool gar nicht öffnen.
    if kind == "pdf":
        txt = extract_pdf_text(dest)
    elif ext in office_text.OFFICE_EXT:
        txt = office_text.text_of(dest)
    else:
        txt = ""
    if txt.strip():
        Path(str(dest) + ".txt").write_text(txt, encoding="utf-8")
    return {"path": str(dest), "url": f"/uploads/{fname}", "name": name or fname, "kind": kind}
