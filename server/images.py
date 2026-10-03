"""Bilder erzeugen über fal.ai — für Cody (bild.py) und die Einstellungen.

Fertige Bilder landen in uploads/ und erscheinen per Markdown direkt im Chat
(`![…](/uploads/…)`). Weil der Dateiname damit im Verlauf steht, räumt
uploads_gc sie erst mit der Session weg.

Der Key liegt wie die anderen Anbieter-Keys in .llm-config.json (chmod 600).
"""
import json
import os
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

from server import config as cfg
from server import llm as llmmod
from server.core import UPLOAD_DIR

FORMATE = ("16:9", "1:1", "9:16")

# Vergleich vom 03.10.2026 (gleicher Prompt mit Händen, fester Anordnung und
# deutscher Schrift): GPT Image 2 traf alles, Flux setzte das Motiv in die Mitte
# und verschrieb sich, Nano Banana Pro malte eine fremde Hand dazu.
_GPT_GROESSE = {"16:9": "landscape_16_9", "1:1": "square_hd", "9:16": "portrait_16_9"}
MODELLE = {
    "openai/gpt-image-2": {
        "label": "GPT Image 2", "preis": "≈ 5 ct",
        "body": lambda p, f: {"prompt": p, "image_size": _GPT_GROESSE[f], "quality": "medium"},
    },
    "fal-ai/flux-pro/v1.1-ultra": {
        "label": "Flux 1.1 Ultra", "preis": "≈ 6 ct",
        "body": lambda p, f: {"prompt": p, "aspect_ratio": f, "output_format": "jpeg"},
    },
    "fal-ai/nano-banana-pro": {
        "label": "Nano Banana Pro", "preis": "≈ 15 ct",
        "body": lambda p, f: {"prompt": p, "aspect_ratio": f},
    },
}
assert set(MODELLE) == set(cfg.IMAGE_MODELS)


class BildFehler(Exception):
    """Verständlicher Fehler (wird so angezeigt)."""


def fal_key() -> str:
    c = llmmod.load_config().get("fal") or {}
    return (c.get("api_key") or os.environ.get("FAL_KEY") or "").strip()


def save_key(key: str):
    """Leerer Key löscht den gespeicherten."""
    conf = llmmod.load_config()
    key = (key or "").strip()
    if key:
        conf["fal"] = {"api_key": key}
    else:
        conf.pop("fal", None)
    llmmod.save_config(conf)


def status() -> dict:
    return {
        "configured": bool(fal_key()),
        "model": cfg.load_settings()["images"]["model"],
        "models": [{"id": k, "label": v["label"], "price": v["preis"]} for k, v in MODELLE.items()],
    }


def _post(path: str, body: dict, key: str, timeout: int) -> dict:
    req = urllib.request.Request(
        "https://fal.run/" + path, data=json.dumps(body).encode(),
        headers={"Authorization": "Key " + key, "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def erzeuge(prompt: str, fmt: str = "16:9", modell: str = "", timeout: int = 300) -> Path:
    """Erzeugt ein Bild und legt es in uploads/ ab. Rückgabe: Pfad der Datei."""
    prompt = (prompt or "").strip()
    if not prompt:
        raise BildFehler("Leerer Prompt.")
    if fmt not in FORMATE:
        raise BildFehler(f"Unbekanntes Format {fmt!r} — erlaubt: {', '.join(FORMATE)}.")
    modell = modell or cfg.load_settings()["images"]["model"]
    if modell not in MODELLE:
        raise BildFehler(f"Unbekanntes Modell {modell!r} — erlaubt: {', '.join(MODELLE)}.")
    key = fal_key()
    if not key:
        raise BildFehler("Kein fal.ai-Key hinterlegt (⚙ Einstellungen → Bilder).")
    body = MODELLE[modell]["body"](prompt, fmt)
    for versuch in (1, 2):
        try:
            data = _post(modell, body, key, timeout)
            break
        except urllib.error.HTTPError as e:
            # fal antwortet unter Last gelegentlich mit 502/504 — einmal nachfassen.
            if e.code >= 500 and versuch == 1:
                time.sleep(2)
                continue
            detail = e.read()[:300].decode("utf-8", "replace")
            if e.code in (401, 403):
                raise BildFehler("fal.ai lehnt den Key ab (falsch oder kein Guthaben).") from e
            raise BildFehler(f"fal.ai meldet {e.code}: {detail}") from e
        except urllib.error.URLError as e:
            raise BildFehler(f"fal.ai nicht erreichbar: {e.reason}") from e
    try:
        url = data["images"][0]["url"]
    except (KeyError, IndexError, TypeError):
        raise BildFehler("fal.ai hat kein Bild geliefert.")
    with urllib.request.urlopen(url, timeout=120) as r:
        raw = r.read()
        typ = r.headers.get_content_type()
    ext = {"image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp"}.get(typ, ".png")
    UPLOAD_DIR.mkdir(exist_ok=True)
    ziel = UPLOAD_DIR / f"{uuid.uuid4().hex}{ext}"
    ziel.write_bytes(raw)
    return ziel


def context_block() -> str:
    """Hinweis für Codys Kontext — nur wenn ein Key da ist."""
    if not fal_key():
        return ""
    bild = Path(__file__).resolve().parent.parent / "bild.py"
    return cfg.L(
        "## Bilder erzeugen\n"
        f'Möchte der Nutzer ein Bild: `python3 "{bild}" "<Prompt auf Englisch>" '
        "[--format 16:9|1:1|9:16] [--kopie <Zieldatei>]`. Die Ausgabe enthält eine Zeile "
        "`![…](/uploads/…)`. Übernimm sie unverändert in deine Antwort, dann erscheint das "
        "Bild im Chat. Mit --kopie liegt zusätzlich eine Kopie im Projekt. Beschreibe Motiv, "
        "Anordnung und Licht genau. Jedes Bild kostet ein paar Cent: nur auf Wunsch erzeugen.",
        "## Generating images\n"
        f'If the user wants an image: `python3 "{bild}" "<prompt in English>" '
        "[--format 16:9|1:1|9:16] [--kopie <target file>]`. The output contains a line "
        "`![…](/uploads/…)`. Copy it unchanged into your reply and the image shows up in the "
        "chat. With --kopie a copy is also saved in the project. Describe subject, layout and "
        "light precisely. Each image costs a few cents: only generate on request.",
    )
