"""Betriebsmodus und Namen — die eine Stelle, die app.py und llm.py gemeinsam lesen.

CONSTRUCT gibt es in zwei Ausbaustufen:

  **voll**  Claude Code im Rücken: Dateien, Terminal, Skills, MCP, E-Mail, Teile.
  **lite**  dasselbe ohne Skills, MCP, E-Mail und Teile — die Bereiche, die auf
            einen bestimmten Nutzer zugeschnitten sind. Gedacht für Leute, denen
            man die Oberfläche weitergibt, ohne ihnen den ganzen Apparat und die
            eigenen Daten mitzugeben.

Lite schaltet die Datei `.lite` neben app.py ein. Eine Datei statt nur einer
Umgebungsvariable, weil der Modus dann am ORDNER hängt: egal ob start.sh,
desktop.py oder uvicorn von Hand — alle sehen ihn, und eine versehentlich
vergessene Variable kann nicht plötzlich den vollen Zugriff freischalten.
Steht in der Datei eine Zeile Text, ist das der Name des Nutzers.
"""
import os
from pathlib import Path

BASE_DIR = Path(__file__).parent
_MARKER = BASE_DIR / ".lite"


def _env_flag(name: str):
    v = os.environ.get(name, "").strip().lower()
    if v in ("1", "true", "yes", "on"):
        return True
    if v in ("0", "false", "no", "off"):
        return False
    return None


_forced = _env_flag("CONSTRUCT_LITE")
LITE = _forced if _forced is not None else _MARKER.exists()


def _marker_name() -> str:
    try:
        return _MARKER.read_text(encoding="utf-8").strip().splitlines()[0].strip()
    except Exception:
        return ""


# Wie der Assistent den Nutzer anspricht (Persona-Notizen, Verlaufs-Protokolle).
USER_NAME = (os.environ.get("CONSTRUCT_USER", "").strip()
             or (_marker_name() if LITE else "")
             or ("der Nutzer" if LITE else "Kevin"))

# Wie der Assistent selbst heißt. CONSTRUCT ist der Ort, der Assistent die Person.
ASSISTANT_NAME = os.environ.get("CONSTRUCT_ASSISTANT", "").strip() or "Cody"
