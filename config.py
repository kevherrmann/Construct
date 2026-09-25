"""Einstellungen der Installation — die eine Stelle, die app.py und llm.py teilen.

Was hier liegt, gehört zu DIESEM Rechner, nicht zum Programm: welche Kacheln
sichtbar sind, welche Farbwelt läuft, wie der Hintergrund aussieht und wie die
Beteiligten heißen. Darum steht `settings.json` in `.gitignore` — wer das
Repository klont, startet mit den Vorgaben und richtet sich seins selbst ein.

Serverseitig und nicht im Browser, weil die Oberfläche mal aus dem eigenen
Fenster und mal aus dem Browser bedient wird; localStorage wäre pro Browser
eine andere Wahrheit.

Geprüft wird beim Lesen UND beim Schreiben: die Datei lässt sich von Hand
bearbeiten, und ein Tippfehler darin soll die Oberfläche nicht zerlegen.
"""
import json
import re
import os
from pathlib import Path

BASE_DIR = Path(__file__).parent
SETTINGS_FILE = BASE_DIR / "settings.json"

# Kacheln, die sich abschalten lassen. "sessions" (der Chat) fehlt mit Absicht:
# eine Oberfläche ohne ihren Hauptzweck wäre eine Sackgasse, aus der man sich
# nicht mehr herausklicken kann.
OPTIONAL_TILES = ("skills", "kalender", "mail", "mcp")
BG_MODES = ("matrix", "image", "plain")
# Die Farben selbst stehen im CSS. Hier nur die erlaubten Schlüssel — der
# Server soll nicht mitentscheiden, wie etwas aussieht, nur was gewählt ist.
THEMES = ("matrix", "bernstein", "eis", "space", "asche", "blut", "papier", "nebel")
# Sprache der Oberfläche UND des Assistenten. Englisch als Vorgabe: das
# Repository ist öffentlich, Deutsch schaltet man sich im ⚙-Dialog um.
LANGS = ("en", "de")

DEFAULT_SETTINGS = {
    "theme": "matrix",
    # Flüssiges Glas (Plasma UI) — unabhängig von der Farbwelt, gilt für alle Themes.
    "plasma": False,
    "lang": "en",
    # Leerer Nutzername = neutrale Anrede. Ein voreingestellter Vorname wäre in
    # einem Repository, das andere klonen, schlicht der falsche Mensch.
    "names": {"user": "", "assistant": "Cody"},
    # Eigene Bilder statt der mitgelieferten. Leer = Vorgabe (Assistent) bzw.
    # Anfangsbuchstabe (Nutzer).
    "avatars": {"user": "", "assistant": ""},
    # Ablage von Hermes. Leer = dessen Standard (~/.hermes). Konfigurierbar,
    # weil dieser Ordner belegt sein kann — etwa von einem Container, der
    # unter fremder Benutzerkennung lief und ihn unlesbar zurückließ.
    "hermes": {"home": ""},
    # Zurückhaltende Vorgabe: wer frisch klont, bekommt Chat und Kalender.
    # Alles Weitere schaltet er sich selbst dazu und weiß dann, was es tut.
    "tiles": {"skills": False, "kalender": True, "mail": False, "mcp": False},
    # dim = Abdunklung des Hintergrundbildes in Prozent. Farbige Schrift auf
    # einem hellen Foto ist unlesbar, darum ein hoher Startwert.
    "background": {"mode": "matrix", "image": "", "dim": 60},
    # Claude Code und Hermes beim Start aktuell halten (updates.py).
    # interval_h = Mindestabstand zwischen zwei Prüfungen, 0 = jeder Start.
    # construct: CONSTRUCT selbst per git beim Start (selfupdate.py).
    "updates": {"auto": True, "interval_h": 6, "construct": True},
    # Vorlesen über Gemini TTS (tts.py) — nutzt den Gemini-Key aus llm.py.
    # auto = jede neue Antwort sofort vorlesen. Stimme und Sprechanweisung
    # je Oberflächensprache: eine deutsche Stimme liest Englisch mit Akzent.
    "tts": {"auto": False, "model": "gemini-3.8-flash-lite-tts",
            "voice": {"de": "de-de-podcaster-3", "en": "en-us-podcaster-6"},
            "style": {"de": "", "en": ""}},
}

TTS_MODELS = ("gemini-3.8-flash-lite-tts", "gemini-3.8-flash-tts")


def _clean_tts(src: dict, cur: dict):
    """Übernimmt gültige TTS-Felder aus src nach cur (für Laden und Patch)."""
    if "auto" in src:
        cur["auto"] = bool(src["auto"])
    if src.get("model") in TTS_MODELS:
        cur["model"] = src["model"]
    voice, style = src.get("voice"), src.get("style")
    # Frühe Fassung speicherte eine einzelne Stimme — die gehört zur Sprache
    # ihres Kürzels (de-de-…, en-us-…), die Sprechanweisung dann zu Deutsch.
    if isinstance(voice, str):
        voice = {"en" if voice.lower().startswith("en-") else "de": voice}
    if isinstance(style, str):
        style = {"de": style}
    for lang, v in (voice or {}).items() if isinstance(voice, dict) else ():
        if lang in LANGS:
            v = re.sub(r"[^\w.\-]", "", str(v or ""))[:80]
            cur["voice"][lang] = v or DEFAULT_SETTINGS["tts"]["voice"][lang]
    for lang, v in (style or {}).items() if isinstance(style, dict) else ():
        if lang in LANGS:
            cur["style"][lang] = str(v or "").strip()[:200]


def _clean_name(v, fallback: str = "") -> str:
    v = str(v or "").strip()
    return v[:40] if v else fallback


def _clean_image(v) -> str:
    """Nur eigene Uploads zulassen.

    Ein freier Pfad hier wäre eine Einladung, sich per Einstellung beliebige
    Dateien in die Seite zu laden.
    """
    v = str(v or "").strip()
    return v if (v.startswith("/uploads/") and ".." not in v and "//" not in v[1:]) else ""


def load_settings() -> dict:
    out = json.loads(json.dumps(DEFAULT_SETTINGS))   # tiefe Kopie
    try:
        raw = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return out
    if not isinstance(raw, dict):
        return out
    if raw.get("theme") in THEMES:
        out["theme"] = raw["theme"]
    elif raw.get("theme") == "plasma":
        # Kurzzeitig war Plasma ein eigenes Theme (violett) — heute ein Schalter
        # plus Farbwelt; "space" kommt dem damaligen Violett am nächsten.
        out["theme"], out["plasma"] = "space", True
    if "plasma" in raw:
        out["plasma"] = bool(raw["plasma"])
    if raw.get("lang") in LANGS:
        out["lang"] = raw["lang"]
    h = raw.get("hermes") or {}
    out["hermes"]["home"] = str(h.get("home") or "").strip()[:400]
    av = raw.get("avatars") or {}
    out["avatars"]["user"] = _clean_image(av.get("user"))
    out["avatars"]["assistant"] = _clean_image(av.get("assistant"))
    names = raw.get("names") or {}
    out["names"]["user"] = _clean_name(names.get("user"))
    out["names"]["assistant"] = _clean_name(names.get("assistant"),
                                            DEFAULT_SETTINGS["names"]["assistant"])
    for k, v in (raw.get("tiles") or {}).items():
        if k in OPTIONAL_TILES:
            out["tiles"][k] = bool(v)
    bg = raw.get("background") or {}
    if bg.get("mode") in BG_MODES:
        out["background"]["mode"] = bg["mode"]
    out["background"]["image"] = _clean_image(bg.get("image"))
    try:
        out["background"]["dim"] = max(0, min(100, int(bg.get("dim"))))
    except Exception:
        pass
    up = raw.get("updates") or {}
    if "auto" in up:
        out["updates"]["auto"] = bool(up["auto"])
    if "construct" in up:
        out["updates"]["construct"] = bool(up["construct"])
    try:
        out["updates"]["interval_h"] = max(0, min(720, int(up.get("interval_h"))))
    except Exception:
        pass
    _clean_tts(raw.get("tts") or {}, out["tts"])
    return out


def apply_patch(patch: dict) -> dict:
    """Teil-Update: was nicht mitkommt, bleibt wie es war."""
    cur = load_settings()
    if patch.get("theme") in THEMES:
        cur["theme"] = patch["theme"]
    if "plasma" in patch:
        cur["plasma"] = bool(patch["plasma"])
    if patch.get("lang") in LANGS:
        cur["lang"] = patch["lang"]
    h = patch.get("hermes") or {}
    if "home" in h:
        cur["hermes"]["home"] = str(h.get("home") or "").strip()[:400]
    av = patch.get("avatars") or {}
    for who in ("user", "assistant"):
        if who in av:
            cur["avatars"][who] = _clean_image(av[who])
    names = patch.get("names") or {}
    if "user" in names:
        cur["names"]["user"] = _clean_name(names["user"])
    if "assistant" in names:
        cur["names"]["assistant"] = _clean_name(
            names["assistant"], DEFAULT_SETTINGS["names"]["assistant"])
    for k, v in (patch.get("tiles") or {}).items():
        if k in OPTIONAL_TILES:
            cur["tiles"][k] = bool(v)
    bg = patch.get("background") or {}
    if bg.get("mode") in BG_MODES:
        cur["background"]["mode"] = bg["mode"]
    if "image" in bg:
        cur["background"]["image"] = _clean_image(bg["image"])
    if "dim" in bg:
        try:
            cur["background"]["dim"] = max(0, min(100, int(bg["dim"])))
        except Exception:
            pass
    up = patch.get("updates") or {}
    if "auto" in up:
        cur["updates"]["auto"] = bool(up["auto"])
    if "construct" in up:
        cur["updates"]["construct"] = bool(up["construct"])
    if "interval_h" in up:
        try:
            cur["updates"]["interval_h"] = max(0, min(720, int(up["interval_h"])))
        except Exception:
            pass
    _clean_tts(patch.get("tts") or {}, cur["tts"])
    tmp = SETTINGS_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(cur, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(SETTINGS_FILE)
    return cur


# ---------- Persona ----------
# SOUL.md beschreibt den Charakter des Assistenten, USER.md was er über den
# Nutzer weiß. Beide gehören zur Installation und stehen in .gitignore —
# sonst würde ein `git pull` die eigene Persona überschreiben. Im Repository
# liegt nur SOUL.default.md als Vorlage.
PERSONA_FILES = {
    "soul": (BASE_DIR / "SOUL.md", BASE_DIR / "SOUL.default.md"),
    "user": (BASE_DIR / "USER.md", None),
}
# Englische Vorlage daneben: wer mit "en" startet, bekommt einen Cody, der
# Englisch spricht. Gilt nur fürs ERSTE Anlegen — eine vorhandene SOUL.md
# gehört dem Nutzer und wird beim Sprachwechsel nicht überschrieben.
SOUL_TEMPLATE_EN = BASE_DIR / "SOUL.default.en.md"
MAX_PERSONA = 64_000     # großzügig, aber kein unbegrenzter Systemprompt


def persona_read(which: str) -> str:
    live, template = PERSONA_FILES[which]
    try:
        return live.read_text(encoding="utf-8", errors="replace")
    except FileNotFoundError:
        pass
    if template is not None:
        if which == "soul" and lang() == "en" and SOUL_TEMPLATE_EN.is_file():
            template = SOUL_TEMPLATE_EN
        try:
            txt = template.read_text(encoding="utf-8", errors="replace")
            live.write_text(txt, encoding="utf-8")   # beim ersten Mal anlegen
            return txt
        except Exception:
            pass
    return ""


def persona_write(which: str, text: str) -> str:
    live, _ = PERSONA_FILES[which]
    text = str(text or "")[:MAX_PERSONA]
    tmp = live.with_suffix(live.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(live)
    return text


# ---------- Sprache ----------
def lang() -> str:
    # Umgebungsvariable sticht die Datei — wie bei den Namen unten.
    env = os.environ.get("CONSTRUCT_LANG", "").strip().lower()
    return env if env in LANGS else load_settings().get("lang", "en")


def L(de: str, en: str) -> str:
    """Text in der eingestellten Sprache — für alles, was ans Modell geht.
    Ein deutscher Hinweis im Prompt zieht die Antwort sonst ins Deutsche."""
    return en if lang() == "en" else de


# ---------- Namen ----------
# Umgebungsvariablen stechen die Datei: praktisch für Server-Installationen,
# die ohne Oberfläche eingerichtet werden.
def user_name() -> str:
    """Wie der Assistent den Nutzer anspricht."""
    return (os.environ.get("CONSTRUCT_USER", "").strip()
            or load_settings()["names"]["user"] or L("der Nutzer", "the user"))


def assistant_name() -> str:
    """Wie der Assistent selbst heißt. CONSTRUCT ist der Ort, er die Person."""
    return (os.environ.get("CONSTRUCT_ASSISTANT", "").strip()
            or load_settings()["names"]["assistant"]
            or DEFAULT_SETTINGS["names"]["assistant"])
