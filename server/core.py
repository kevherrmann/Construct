"""Grundlagen für alle Teile: Pfade, Arbeitsordner, Version, Persona,
Aufruf des claude-CLI, SSE-Hilfen.
"""
import base64
import json
import os
import re
import secrets
import shutil
import time
from pathlib import Path

import cal
from server import config as cfg


# server/core.py liegt eine Ebene unter dem Projektordner.
BASE_DIR = Path(__file__).resolve().parent.parent

STATIC_DIR = BASE_DIR / "static"

UPLOAD_DIR = BASE_DIR / "uploads"

UPLOAD_DIR.mkdir(exist_ok=True)

PROJECTS_DIR = Path.home() / ".claude" / "projects"

def _find_workspace() -> str:
    """Ordner mit den Projekten des Nutzers — Grundlage der Ordner-Auswahl im Chat.

    Meist ~/projects bzw. ~/Projekte. CODY_WORKSPACE sticht immer, damit man
    es pro Rechner setzen kann.
    """
    env = os.environ.get("CODY_WORKSPACE", "").strip()
    if env and os.path.isdir(env):
        return env
    for cand in (Path.home() / "projects", Path.home() / "Projekte"):
        if cand.is_dir():
            return str(cand)
    return str(Path.home())

WORKSPACE = _find_workspace()

DEFAULT_CWD = WORKSPACE

# Nur die Bau-Nummer. Frueher stand hier "4.0.0 · opus-5" — das las sich in der
# Statuszeile wie das gerade laufende Modell, war aber ein fester Text und
# stimmte nach jedem Modellwechsel nicht mehr. Was wirklich laeuft, meldet der
# Lauf selbst (stats-Ereignis, aus `modelUsage`).
VERSION = "5.3.1"

# Passwortschutz: greift NUR, wenn MATRIX_PASS gesetzt ist (z.B. auf einem Server).
# Lokal ohne MATRIX_PASS bleibt die Oberfläche offen (kein Login).
AUTH_USER = os.environ.get("MATRIX_USER", "Cody")

AUTH_PASS = os.environ.get("MATRIX_PASS", "")


def auth_ok(header: str) -> bool:
    """Passt der Authorization-Header ("Basic …")? Ohne MATRIX_PASS immer ja."""
    if not AUTH_PASS:
        return True
    if not header.startswith("Basic "):
        return False
    try:
        user, _, pw = base64.b64decode(header[6:]).decode("utf-8").partition(":")
    except Exception:
        return False
    # konstante Laufzeit -> kein Timing-Leak
    return secrets.compare_digest(user, AUTH_USER) and secrets.compare_digest(pw, AUTH_PASS)


def persona_text() -> str:
    """SOUL.md + USER.md + Sprachvorgabe — der feste Teil der Persona."""
    parts = []
    for which in ("soul", "user"):
        txt = cfg.persona_read(which).strip()
        if txt:
            parts.append(txt)
    # Die Persona-Vorlage legt die Sprache fest, eine eigene SOUL.md aber
    # womöglich nicht — dann entscheidet die Einstellung.
    parts.append(cfg.L("Antworte auf Deutsch, außer der Nutzer schreibt in einer anderen Sprache.",
                       "Reply in English unless the user writes in another language."))
    return "\n\n".join(parts).strip()


def calendar_text() -> str:
    """Anstehende Termine samt Anleitung zum Eintragen — ändert sich laufend."""
    try:
        return cal.context_block() or ""
    except Exception:
        return ""


def load_persona() -> str:
    """Persona + Kalender als System-Prompt-Zusatz (bei jeder Anfrage frisch gelesen)."""
    return "\n\n".join(p for p in (persona_text(), calendar_text()) if p).strip()

ALLOWED_MODES = {"acceptEdits", "auto", "bypassPermissions", "default", "plan", "dontAsk"}

# Oberfläche (React, frontend/ → static/app). Die Assets tragen einen Hash im
# Namen und dürfen deshalb gecacht werden; index.html liefert index().
APP_DIR = STATIC_DIR / "app"

# ---------- Claude-Anmeldung (Status, Web-Login, Nutzungs-Limits) ----------
# Problem bisher: headless `claude -p` kann abgelaufene OAuth-Tokens nicht selbst
# erneuern -> Kevin musste ins Terminal (claudec). Lösung: Login direkt aus der
# Web-UI über `claude setup-token` (PTY-gesteuert). Der dabei erzeugte LANGLEBIGE
# Token (sk-ant-oat…) landet in TOKEN_FILE und wird allen claude-Subprozessen als
# CLAUDE_CODE_OAUTH_TOKEN mitgegeben — unabhängig vom kurzlebigen Interactive-Login.
CRED_FILE = Path.home() / ".claude" / ".credentials.json"

TOKEN_FILE = BASE_DIR / ".oauth-token"

def claude_bin() -> str:
    """Vollständiger Pfad zum claude-CLI, oder "" wenn es nicht installiert ist.

    Über shutil.which statt schlicht "claude" im Argument-Vektor, aus zwei
    Gründen. Erstens ist die Antwort auf „ist Claude Code überhaupt da?“ sonst
    erst zu haben, wenn der Prozess schon gescheitert ist. Zweitens installiert
    npm das CLI unter Windows als `claude.cmd`; CreateProcess hängt beim Suchen
    im PATH nur `.exe` an und findet es deshalb nicht — which() wertet PATHEXT
    aus und liefert den Pfad samt Endung.
    """
    return shutil.which("claude") or ""

def load_web_token() -> str:
    try:
        t = TOKEN_FILE.read_text(encoding="utf-8").strip()
        return t if t.startswith("sk-ant-") else ""
    except Exception:
        return ""

def claude_env() -> dict:
    """Env für claude-Subprozesse: Web-Login-Token (falls da) sticht alles."""
    env = dict(os.environ)
    tok = load_web_token()
    if tok:
        env["CLAUDE_CODE_OAUTH_TOKEN"] = tok
    return env

# Der Web-Login steuert `claude setup-token` über ein Pseudo-Terminal. pty,
# termios und fcntl sind Unix-only — unter Windows gibt es diesen Weg nicht,
# dort meldet man sich einmal im Terminal mit `claude` an.
WEB_LOGIN_OK = os.name == "posix"

# Merkt sich das letzte "Limit erreicht" aus einem Lauf — Fallback für Hosts,
# deren Token die Usage-API nicht abfragen darf (403, z.B. setup-token).
LIMIT_HIT = {"resets_at": 0}

def friendly_claude_error(msg: str) -> str:
    """Rohe claude-Fehler in verständliche Hinweise übersetzen."""
    msg = (msg or "").strip()
    m = re.search(r"usage limit reached\|(\d+)", msg, re.I)
    if m:
        LIMIT_HIT["resets_at"] = int(m.group(1))   # fürs HUD merken
        reset = time.strftime("%H:%M", time.localtime(int(m.group(1))))
        return (f"⛔ Nutzungs-Limit der Subscription erreicht — geht um {reset} Uhr weiter. "
                "(Oben rechts siehst du die Auslastung.)")
    low = msg.lower()
    if any(w in low for w in ("oauth", "authentication", "invalid api key", "please run /login",
                              "token has expired", "not logged in")):
        return ("🔑 Anmeldung abgelaufen oder ungültig — oben rechts auf das Schlüssel-Symbol "
                "klicken und neu einloggen.\n\n" + msg[:300])
    if "overloaded" in low:
        return "🌊 Anthropic ist gerade überlastet — kurz warten und nochmal senden.\n\n" + msg[:200]
    return msg

def sse(obj: dict) -> str:
    return f"data: {json.dumps(obj, ensure_ascii=False)}\n\n"

def extract_text(content) -> str:
    """Zieht lesbaren Text aus einem Message-content (String ODER Block-Liste)."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    parts = []
    if isinstance(content, list):
        for b in content:
            if not isinstance(b, dict):
                continue
            bt = b.get("type")
            if bt == "text":
                parts.append(b.get("text", ""))
            elif bt == "tool_use":
                parts.append(f"› [Tool: {b.get('name', '?')}]")
            # thinking / tool_result werden in der Anzeige bewusst weggelassen
    return "\n".join(p for p in parts if p)

def code_stamp() -> str:
    """Fingerabdruck des Quelltexts, mit dem DIESE Instanz gestartet ist.

    Nur der Zeitstempel der jüngsten Quelldatei, keine Prüfsumme: es geht
    allein um die Frage "ist der Code auf der Platte neuer als das, was hier
    läuft?". Laufzeitdateien (settings.json, .update-stamp) bleiben bewusst
    außen vor — die ändern sich dauernd und würden jeden Start zum Neustart
    machen. Gegenstück: code_stamp() in desktop.py.
    """
    try:
        quellen = (list(BASE_DIR.glob("*.py")) + list((BASE_DIR / "server").rglob("*.py"))
                   + list(STATIC_DIR.rglob("*.[hjc]*")))
        return str(int(max(f.stat().st_mtime for f in quellen if f.exists())))
    except Exception:
        return ""

# Beim Import festhalten, nicht bei jeder Abfrage: gefragt ist der Stand, mit
# dem der Server hochgefahren ist, nicht der auf der Platte von jetzt.
CODE_STAMP = code_stamp()
