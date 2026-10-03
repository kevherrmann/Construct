#!/usr/bin/env python3
"""bild.py — Cody erzeugt Bilder (fal.ai), die direkt im Chat erscheinen.

  python3 bild.py "a cozy bakery at dawn" [--format 16:9|1:1|9:16]
                  [--modell openai/gpt-image-2] [--kopie /pfad/im/projekt.png]

Ausgabe: eine Markdown-Zeile ![…](/uploads/…) für die Antwort und der Dateipfad.
"""
import argparse
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from server import images  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="Bild über fal.ai erzeugen")
    ap.add_argument("prompt")
    ap.add_argument("--format", default="16:9", choices=images.FORMATE)
    ap.add_argument("--modell", default="", choices=["", *images.MODELLE])
    ap.add_argument("--kopie", default="", help="zusätzlich hierhin kopieren")
    a = ap.parse_args()
    try:
        pfad = images.erzeuge(a.prompt, a.format, a.modell)
    except images.BildFehler as e:
        print(f"Fehler: {e}", file=sys.stderr)
        return 1
    alt = " ".join(a.prompt.split())[:80].replace("]", ")").replace("[", "(")
    print(f"![{alt}](/uploads/{pfad.name})")
    print(f"Datei: {pfad}")
    if a.kopie:
        ziel = Path(a.kopie).expanduser()
        if ziel.is_dir():
            ziel = ziel / pfad.name
        ziel.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(pfad, ziel)
        print(f"Kopie: {ziel}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
