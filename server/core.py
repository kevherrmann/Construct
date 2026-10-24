"""Grundlagen für alle Teile: Pfade, Arbeitsordner, Version, Persona,
Aufruf des claude-CLI, SSE-Hilfen.
"""
import base64
import json
import os
import re
import secrets
import shutil
import sys
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
VERSION = "8.7.0"

# Passwortschutz: greift NUR, wenn MATRIX_PASS gesetzt ist (z.B. auf einem Server).
# Lokal ohne MATRIX_PASS bleibt die Oberfläche offen (kein Login).
AUTH_USER = os.environ.get("MATRIX_USER", "Cody")

AUTH_PASS = os.environ.get("MATRIX_PASS", "")


# Unter welcher Adresse der Server auf diesem Rechner erreichbar ist — gebraucht
# vom Firmen-Bus (team_mcp.py), der als Unterprozess von claude zurück an den Server
# telefoniert. Der Port steht erst fest, wenn der Server läuft
# und die erste Anfrage kommt (uvicorn kennt ihn, wir nicht), deshalb merkt die
# Middleware in app.py ihn sich dort.
_SERVER = {"base": ""}


def remember_server(scope: dict):
    if _SERVER["base"]:
        return
    host, port = (scope.get("server") or ("127.0.0.1", 0))[:2]
    if port:
        ziel = "127.0.0.1" if host in ("0.0.0.0", "::", "") else host
        _SERVER["base"] = f"http://[{ziel}]:{port}" if ":" in ziel else f"http://{ziel}:{port}"


def bus_base() -> str:
    return _SERVER["base"] or f"http://127.0.0.1:{os.environ.get('MATRIX_PORT', '8765')}"


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


# Fremde Webseiten dürfen an localhost schreiben, ohne dass der Browser vorher
# fragt (POST mit text/plain, Formulare) — und req.json() liest so einen Body
# trotzdem. Ohne Prüfung konnte jede besuchte Seite einem Mitarbeiter Bash und
# bypassPermissions geben und ihm einen Auftrag schicken (Janus' Audit, 06.10.2026).
# Lesen bleibt frei: die Antwort darf eine fremde Seite ohnehin nicht sehen.
SCHREIBEND = ("POST", "PUT", "PATCH", "DELETE")
# Zusätzlich erlaubte Herkünfte für Reverse-Proxys, die weder Host noch
# X-Forwarded-Host durchreichen und mit alten Browsern ohne Sec-Fetch-Site benutzt
# werden: CONSTRUCT_ORIGINS="https://cody.example.org,https://…"
_ORIGINS = {o.strip().rstrip("/").lower() for o in os.environ.get("CONSTRUCT_ORIGINS", "").split(",")
            if o.strip()}


def fremde_herkunft(method: str, headers) -> bool:
    """Kommt diese schreibende Anfrage von einer fremden Webseite?

    Erlaubt ist, was keine Herkunft nennt (curl, Telegram, der Firmen-Bus, das
    App-Fenster beim direkten Aufruf), was der Browser selbst als gleiche Herkunft
    ausweist (Sec-Fetch-Site lässt sich von einer Seite nicht fälschen; das trägt
    auch hinter einem Reverse-Proxy und durch den Vite-Proxy beim Entwickeln) und
    eine Origin, die zum Host passt."""
    if method.upper() not in SCHREIBEND:
        return False
    seite = (headers.get("sec-fetch-site") or "").lower()
    if seite in ("same-origin", "none"):
        return False
    origin = (headers.get("origin") or "").strip().rstrip("/").lower()
    if origin in _ORIGINS and origin:
        return False
    # Sagt der Browser selbst „fremd“, zählen Origin und Host nicht mehr: beide
    # ließen sich mit einem umgeschriebenen X-Forwarded-Host passend machen.
    if not origin or seite == "cross-site":
        return seite in ("cross-site", "same-site")
    netloc = origin.split("://", 1)[-1]
    eigene = {(headers.get(h) or "").split(",")[0].strip().lower() for h in ("host", "x-forwarded-host")}
    return netloc not in eigene - {""}


_LOOPBACK = {"127.0.0.1", "localhost", "[::1]"}


def _hostname(host: str) -> str:
    """"[::1]:8765" → "[::1]", "localhost:8765" → "localhost"."""
    host = host.strip().lower()
    return host[:host.index("]") + 1] if host.startswith("[") and "]" in host else host.split(":")[0]


def fremder_host(headers) -> bool:
    """DNS-Rebinding: Eine fremde Seite lässt ihren Namen auf 127.0.0.1 zeigen und
    ist für den Browser dann „gleiche Herkunft“ — mit Lese- und Schreibzugriff auf
    die ganze API. Ohne Passwort gilt deshalb nur, wer den Server unter einem
    lokalen Namen anspricht, unter MATRIX_HOST oder unter CONSTRUCT_ORIGINS. Mit
    MATRIX_PASS schützt das Passwort, das kennt die fremde Seite nicht."""
    if AUTH_PASS:
        return False
    host = (headers.get("host") or "").strip().lower()
    if not host:
        return False                      # HTTP/1.0 ohne Host: kein Browser
    name = _hostname(host)
    if name in _LOOPBACK or name.endswith(".localhost"):
        return False
    gebunden = os.environ.get("MATRIX_HOST", "").strip().lower()
    if gebunden and gebunden not in ("0.0.0.0", "::") and name in (gebunden, f"[{gebunden}]"):
        return False
    erlaubt = {o.split("://", 1)[-1] for o in _ORIGINS}
    return host not in erlaubt and name not in {_hostname(o) for o in erlaubt}


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


def context_text(bilder: bool = True) -> str:
    """Was sich laufend ändert: Kalender, dazu die Bild-Anleitung, falls ein Key da ist.

    bilder=False für kleine lokale Modelle: jede Zeile Kontext ist für sie
    eine Zeile, die sie verwechseln oder nachplappern können."""
    try:
        from server import images
        bilder = images.context_block() if bilder else ""
    except Exception:
        bilder = ""
    return "\n\n".join(p for p in (calendar_text(), bilder) if p)


def load_persona() -> str:
    """Persona + Kontext als System-Prompt-Zusatz (bei jeder Anfrage frisch gelesen)."""
    return "\n\n".join(p for p in (persona_text(), context_text()) if p).strip()

ALLOWED_MODES = {"acceptEdits", "auto", "bypassPermissions", "default", "plan", "dontAsk"}

# Oberfläche (React, frontend/ → static/app). Die Assets tragen einen Hash im
# Namen und dürfen deshalb gecacht werden; index.html liefert index().
APP_DIR = STATIC_DIR / "app"

# ---------- Claude-Anmeldung (Status, Web-Login, Nutzungs-Limits) ----------
# Der Web-Login steuert `claude auth login` über ein Pseudo-Terminal und erneuert
# damit die normale Kontoanmeldung der CLI (Datei bzw. Mac-Schlüsselbund) — ohne
# Terminal. Früher war es `claude setup-token`: dessen Langzeit-Token (sk-ant-oat…,
# TOKEN_FILE) ging allen claude-Läufen als CLAUDE_CODE_OAUTH_TOKEN mit. Der darf
# aber nur Modelle aufrufen: mit ihm ließ `claude --chrome` die Chrome-Werkzeuge
# und die claude.ai-Connectors stumm weg. Er bleibt nur noch die Notlösung, wenn
# keine Kontoanmeldung da ist.
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

def read_creds() -> tuple:
    """Kontoanmeldung der CLI: (claudeAiOauth-Dict, Quelle "file"/"keychain").

    Linux/Windows: ~/.claude/.credentials.json. Auf dem Mac legt Claude Code den
    Login aber im Schlüsselbund ab ("Claude Code-credentials") — die Datei gibt
    es dort gar nicht. Ohne diesen zweiten Weg stand oben "LOGIN NÖTIG",
    obwohl die CLI angemeldet war und jeder Chat lief. `security` ist genau
    das Werkzeug, mit dem die CLI selbst liest; der Schlüsselbund fragt darum
    nicht nach.
    """
    try:
        c = json.loads(CRED_FILE.read_text(encoding="utf-8")).get("claudeAiOauth") or {}
        if c:
            return c, "file"
    except Exception:
        pass
    if sys.platform == "darwin":
        import subprocess
        try:
            r = subprocess.run(["security", "find-generic-password",
                                "-s", "Claude Code-credentials", "-w"],
                               capture_output=True, text=True, timeout=5)
            if r.returncode == 0:
                return (json.loads(r.stdout.strip()).get("claudeAiOauth") or {}), "keychain"
        except Exception:
            pass
    return {}, ""

def konto_login(c: dict | None = None) -> bool:
    """Gilt die Kontoanmeldung? Ein abgelaufenes Access-Token ist kein Logout:
    mit Refresh-Token erneuert die CLI es beim nächsten Aufruf selbst."""
    if c is None:
        c = read_creds()[0]
    return bool(c.get("accessToken")) and (
        bool(c.get("refreshToken")) or (c.get("expiresAt") or 0) / 1000 > time.time())

def claude_env() -> dict:
    """Env für claude-Subprozesse: die Kontoanmeldung, wenn sie gilt — dann auch
    kein geerbtes CLAUDE_CODE_OAUTH_TOKEN, das stäche sie aus und nähme Chrome
    mit. Sonst der alte Web-Login-Token, damit der Chat wenigstens läuft."""
    env = dict(os.environ)
    if konto_login():
        env.pop("CLAUDE_CODE_OAUTH_TOKEN", None)
        return env
    tok = load_web_token()
    if tok:
        env["CLAUDE_CODE_OAUTH_TOKEN"] = tok
    return env

# Was `claude --help` nennt, gemerkt je Programmdatei: ein Update legt eine neue
# Fassung ab (anderer Pfad hinter dem Link, andere Änderungszeit), dann wird neu
# gefragt. Gebraucht für Schalter, die erst neuere Fassungen kennen — einen
# unbekannten Schalter quittiert claude mit "unknown option", und der Lauf startet nicht.
_HILFE = {"key": None, "text": ""}

def claude_kann(schalter: str) -> bool:
    exe = claude_bin()
    if not exe:
        return False
    try:
        real = os.path.realpath(exe)
        key = (real, os.stat(real).st_mtime)
    except OSError:
        return False
    if _HILFE["key"] != key:
        import subprocess
        try:
            p = subprocess.run([exe, "--help"], capture_output=True, text=True, timeout=20,
                               stdin=subprocess.DEVNULL)
            _HILFE["text"] = p.stdout or ""
        except (OSError, subprocess.SubprocessError):
            _HILFE["text"] = ""
        _HILFE["key"] = key
    return schalter in _HILFE["text"]

def frischer_systemprompt() -> list:
    """Schalter, damit ein fortgesetzter Chat den Systemprompt von JETZT bekommt.

    Seit Claude Code 2.1.267 hält eine Sitzung ihren Systemprompt beim ersten
    Request fest und schickt ihn bei jedem --resume unverändert wieder — ein
    neues --append-system-prompt kam nicht mehr an. Bei uns stehen darin aber
    Kalender und Datum (context_text), dazu SOUL.md, USER.md und die Regeln für
    Board und Firma: ein Chat von Montag kannte am Donnerstag noch Montags
    Termine. Zwischengespeichert wird trotzdem: innerhalb eines Laufs ist der
    Prompt gleich, über Läufe hinweg, solange sich nichts geändert hat."""
    return ["--system-prompt-snapshot", "off"] if claude_kann("--system-prompt-snapshot") else []

# Der Web-Login steuert `claude auth login` über ein Pseudo-Terminal. pty,
# termios und fcntl sind Unix-only — unter Windows gibt es diesen Weg nicht,
# dort meldet man sich einmal im Terminal mit `claude` an.
WEB_LOGIN_OK = os.name == "posix"

# Merkt sich das letzte "Limit erreicht" aus einem Lauf — Fallback für Hosts,
# deren Token die Usage-API nicht abfragen darf (403, z.B. setup-token).
LIMIT_HIT = {"resets_at": 0}

# Auslastung, wie claude sie nach jeder Antwort selbst meldet (rate_limit_event).
# Kommt auch mit dem setup-token an, das die Usage-API nicht abfragen darf.
# Je Fenster: {"percent": 0..100, "resets_at": Unix-Zeit}; "t" = Zeitpunkt der Meldung.
STREAM_USAGE = {"t": 0.0, "five_hour": None, "seven_day": None}

def note_rate_limit(ev: dict):
    """rate_limit_event aus dem claude-Stream fürs HUD merken."""
    fenster = (ev.get("rate_limit_info") or {}).get("unifiedWindows") or {}
    for key in ("five_hour", "seven_day"):
        w = fenster.get(key)
        if isinstance(w, dict) and isinstance(w.get("utilization"), (int, float)):
            STREAM_USAGE[key] = {"percent": w["utilization"] * 100,
                                 "resets_at": int(w.get("resetsAt") or 0)}
            STREAM_USAGE["t"] = time.time()

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


# ---------- Beenden ----------
# Seit das Fenster ein Browser ist, läuft der Server nach dem Schließen weiter.
# Beenden geht darum über die Oberfläche (⏻). Wer den Server startet, meldet
# hier, wie er sauber herunterfährt (desktop.py: uvicorn.should_exit); dann
# laufen die Aufräumarbeiten aus app.lifespan (lokale Stimme, Telegram) noch durch.
_beim_beenden: list = []


def beim_beenden(fn) -> None:
    _beim_beenden.append(fn)


def beenden() -> None:
    if _beim_beenden:
        for fn in _beim_beenden:
            fn()
        return
    # Ohne Starter (python app.py, uvicorn direkt): wie Strg+C — uvicorn fährt
    # dann selbst sauber herunter. Windows kennt das Signal für sich selbst
    # nicht verlässlich; dort hart.
    import signal
    if os.name == "nt":
        os._exit(0)
    os.kill(os.getpid(), signal.SIGINT)
