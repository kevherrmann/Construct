"""
CONSTRUCT — eine eigene, hübsche Weboberfläche für Claude Code.
Läuft auf Kevins Subscription (OAuth), kein API-Key nötig.

Backend = FastAPI. Spricht im Hintergrund `claude -p` (headless) und streamt
die Antwort per SSE ins Matrix-Frontend. Kann alte Claude-Code-Sessions
auflisten, anzeigen und darin weiterchatten (--resume).
"""
import asyncio
import base64
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

from fastapi import FastAPI, UploadFile, File, Request, Response
from fastapi.responses import StreamingResponse, HTMLResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles

import config as cfg  # Einstellungen der Installation — siehe config.py
import cal  # Kalender: gemeinsame events.json (Web-UI + cal.py-CLI + Telegram)
import llm as llmmod  # Anbieter, Schlüssel, Modell-Listen (llm.py)
import hermes as hermesmod  # Werkzeug-Zugriff mit fremden Modellen über ACP
import bonsai as bonsaimod  # lokaler llama-server, nur bei Bedarf im VRAM
import mail as mailmod  # E-Mail: IMAP/SMTP für GMX, Gmail, Outlook (mail.py)
import attach  # Anhänge: Bilder normalisieren, PDF-Textauszug (attach.py)
import updates as updmod  # hält Claude Code und Hermes aktuell (updates.py)
import telegram_bot as tgmod  # Cody über Telegram, eingerichtet unter ⚙
import tts as ttsmod  # Vorlesen über Gemini TTS (tts.py)

BASE_DIR = Path(__file__).parent
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
VERSION = "4.0.0"

# Passwortschutz: greift NUR, wenn MATRIX_PASS gesetzt ist (z.B. auf einem Server).
# Lokal ohne MATRIX_PASS bleibt die Oberfläche offen (kein Login).
AUTH_USER = os.environ.get("MATRIX_USER", "Cody")
AUTH_PASS = os.environ.get("MATRIX_PASS", "")


def load_persona() -> str:
    """SOUL.md + USER.md als System-Prompt-Zusatz (bei jeder Anfrage frisch gelesen)."""
    parts = []
    for which in ("soul", "user"):
        txt = cfg.persona_read(which).strip()
        if txt:
            parts.append(txt)
    # Die Persona-Vorlage legt die Sprache fest, eine eigene SOUL.md aber
    # womöglich nicht — dann entscheidet die Einstellung.
    parts.append(cfg.L("Antworte auf Deutsch, außer der Nutzer schreibt in einer anderen Sprache.",
                       "Reply in English unless the user writes in another language."))
    # Anstehende Termine frisch einspielen -> Cody weiß, was ansteht, und kann erinnern.
    try:
        block = cal.context_block()
        if block:
            parts.append(block)
    except Exception:
        pass
    return "\n\n".join(parts).strip()
ALLOWED_MODES = {"acceptEdits", "auto", "bypassPermissions", "default", "plan", "dontAsk"}

app = FastAPI(title="CONSTRUCT")


@app.middleware("http")
async def basic_auth(request: Request, call_next):
    """HTTP-Basic-Auth vor ALLEM — aber nur wenn ein Passwort konfiguriert ist."""
    if AUTH_PASS:
        ok = False
        header = request.headers.get("Authorization", "")
        if header.startswith("Basic "):
            try:
                user, _, pw = base64.b64decode(header[6:]).decode("utf-8").partition(":")
                # konstante Laufzeit -> kein Timing-Leak
                ok = secrets.compare_digest(user, AUTH_USER) and secrets.compare_digest(pw, AUTH_PASS)
            except Exception:
                ok = False
        if not ok:
            return Response(status_code=401, headers={"WWW-Authenticate": 'Basic realm="Cody"'})
    return await call_next(request)


app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
app.mount("/uploads", StaticFiles(directory=str(UPLOAD_DIR)), name="uploads")


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


def _read_creds() -> tuple:
    """Interactive-Login der CLI: (claudeAiOauth-Dict, Quelle "file"/"keychain").

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
        try:
            r = subprocess.run(["security", "find-generic-password",
                                "-s", "Claude Code-credentials", "-w"],
                               capture_output=True, text=True, timeout=5)
            if r.returncode == 0:
                return (json.loads(r.stdout.strip()).get("claudeAiOauth") or {}), "keychain"
        except Exception:
            pass
    return {}, ""


def _cred_info() -> dict:
    """Kurzlebiger Interactive-Login der CLI (Datei oder Mac-Schlüsselbund)."""
    try:
        c, src = _read_creds()
        exp = c.get("expiresAt") or 0
        return {
            "exists": bool(c.get("accessToken")),
            "source": src,
            "expires_at": exp,
            # Abgelaufenes Access-Token ist kein Logout: mit Refresh-Token
            # erneuert die CLI es beim nächsten Aufruf selbst.
            "expired": exp / 1000 < time.time() and not c.get("refreshToken"),
            "subscription": c.get("subscriptionType") or "",
        }
    except Exception:
        return {"exists": False, "expires_at": 0, "expired": True, "subscription": ""}


@app.get("/api/auth/status")
def auth_status():
    cred = _cred_info()
    web = bool(load_web_token())
    envtok = bool(os.environ.get("CLAUDE_CODE_OAUTH_TOKEN"))
    cli = bool(claude_bin())
    return {
        "cli": cli,                  # ist Claude Code überhaupt installiert?
        "can_web_login": WEB_LOGIN_OK,
        "ok": cli and (web or envtok or (cred["exists"] and not cred["expired"])),
        "web_token": web,            # per Web-Login erzeugter Langzeit-Token
        "env_token": envtok,         # CLAUDE_CODE_OAUTH_TOKEN aus der Umgebung
        "credentials": cred,         # Interactive-Login (claudec)
    }


ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)|\r")


# Der Web-Login steuert `claude setup-token` über ein Pseudo-Terminal. pty,
# termios und fcntl sind Unix-only — unter Windows gibt es diesen Weg nicht,
# dort meldet man sich einmal im Terminal mit `claude` an.
WEB_LOGIN_OK = os.name == "posix"


class LoginFlow:
    """Steuert `claude setup-token` über ein PTY: URL abgreifen, Code einfüttern."""

    def __init__(self):
        self.buf = b""
        self.lock = threading.Lock()
        self.proc = None
        self.master = None
        self.started = time.time()

    def start(self):
        import fcntl
        import pty
        import struct
        import termios
        master, slave = pty.openpty()
        # SEHR breites Terminal, sonst bricht das PTY die OAuth-URL um
        try:
            fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 50, 500, 0, 0))
        except Exception:
            pass
        env = dict(os.environ)
        env["BROWSER"] = "true"      # `true`-Kommando = No-Op, öffnet keinen Browser
        env.pop("CLAUDECODE", None)
        self.proc = subprocess.Popen(
            [claude_bin() or "claude", "setup-token"],
            stdin=slave, stdout=slave, stderr=slave, env=env, close_fds=True,
        )
        os.close(slave)
        self.master = master
        threading.Thread(target=self._pump, daemon=True).start()

    def _pump(self):
        while True:
            try:
                d = os.read(self.master, 4096)
            except OSError:
                break
            if not d:
                break
            with self.lock:
                self.buf += d

    def text(self) -> str:
        with self.lock:
            raw = self.buf.decode("utf-8", "replace")
        return ANSI_RE.sub("", raw)

    def url(self):
        m = re.search(r"https://claude\.(?:com|ai)/\S+", self.text())
        return m.group(0) if m else None

    def token(self):
        # Escapes hier durch Leerzeichen ersetzen, nicht löschen: die CLI setzt
        # Wortabstände per Cursor-Sprung (\x1b[1C) — gelöscht klebte der
        # Folgetext ("Store…") am Token -> 401 "OAuth access token is invalid".
        with self.lock:
            raw = self.buf.decode("utf-8", "replace")
        m = re.search(r"sk-ant-oat[0-9A-Za-z_-]{20,}", ANSI_RE.sub(" ", raw))
        return m.group(0) if m else None

    def send_code(self, code: str):
        os.write(self.master, code.strip().encode())

    def send_enter(self):
        # "\r" (Enter-Taste), nicht "\n": die Code-Maske neuerer CLIs (>=2.1.x)
        # ignoriert Ctrl-J. Und EXTRA schicken, nicht an den Code gehängt: kommt
        # beides in einem Rutsch, hält die CLI es für einen Paste und schluckt das
        # Enter -> Code wird nie abgeschickt, nach 30 s "Login fehlgeschlagen".
        os.write(self.master, b"\r")

    def alive(self) -> bool:
        return bool(self.proc) and self.proc.poll() is None

    def kill(self):
        try:
            if self.alive():
                self.proc.kill()
        except Exception:
            pass
        try:
            os.close(self.master)
        except Exception:
            pass


LOGIN = {"flow": None}


@app.post("/api/auth/login")
async def auth_login():
    """Startet den Login: liefert die OAuth-URL, die Kevin im Browser öffnet."""
    old = LOGIN.get("flow")
    if old:
        old.kill()
    if not WEB_LOGIN_OK:
        return JSONResponse(
            {"error": "Der Login über die Oberfläche braucht ein Pseudo-Terminal — "
                      "das gibt es unter Windows nicht. Einmal ein Terminal öffnen, "
                      "`claude` eingeben und sich dort anmelden; danach findet "
                      "CONSTRUCT die Anmeldung von selbst."},
            status_code=501)
    if not claude_bin():
        return JSONResponse({"error": "Claude Code ist nicht installiert."}, status_code=500)
    flow = LoginFlow()
    try:
        flow.start()
    except FileNotFoundError:
        return JSONResponse({"error": "claude-CLI nicht gefunden"}, status_code=500)
    LOGIN["flow"] = flow
    for _ in range(80):              # bis ~20 s auf die URL warten
        await asyncio.sleep(0.25)
        url = flow.url()
        if url:
            return {"url": url}
        if not flow.alive():
            break
    tail = flow.text()[-800:]
    flow.kill()
    LOGIN["flow"] = None
    return JSONResponse({"error": "Keine Login-URL bekommen. Ausgabe:\n" + tail},
                        status_code=500)


@app.post("/api/auth/code")
async def auth_code(req: Request):
    """Nimmt den Code aus dem Browser entgegen und speichert den Langzeit-Token."""
    body = await req.json()
    code = (body.get("code") or "").strip()
    flow = LOGIN.get("flow")
    if not code:
        return JSONResponse({"error": "Code fehlt"}, status_code=400)
    if not flow or not flow.alive():
        return JSONResponse({"error": "Kein Login aktiv — bitte neu starten."}, status_code=400)
    seen = len(flow.text())
    flow.send_code(code)
    await asyncio.sleep(0.5)         # Paste erst "ankommen" lassen, dann Enter
    flow.send_enter()
    for _ in range(120):             # bis ~30 s auf Erfolg warten
        await asyncio.sleep(0.25)
        tok = flow.token()
        if tok:
            TOKEN_FILE.write_text(tok + "\n", encoding="utf-8")
            TOKEN_FILE.chmod(0o600)
            flow.kill()
            LOGIN["flow"] = None
            USAGE_CACHE["t"] = 0     # Limits mit neuem Token frisch holen
            return {"ok": True}
        if not flow.alive():
            break
        if re.search(r"invalid|failed|error|denied|expired", flow.text()[seen:], re.I):
            break                    # klare Absage der CLI -> nicht sinnlos weiterwarten
    # Echo des Codes ist maskiert (nur Sternchen) -> solche Zeilen rausfiltern
    tail = flow.text()[seen:]
    tail = "\n".join(l for l in tail.splitlines() if l.strip().strip("*·")).strip()[-500:]
    flow.kill()
    LOGIN["flow"] = None
    return JSONResponse({"error": "Login fehlgeschlagen — Code richtig und vollständig kopiert? "
                         + ("Details: " + tail if tail else "Einfach nochmal auf LOGIN STARTEN klicken.")},
                        status_code=400)


# ---------- Nutzungs-Limits (5h-Fenster + Woche) ----------
USAGE_CACHE = {"t": 0.0, "data": None}
# Merkt sich das letzte "Limit erreicht" aus einem Lauf — Fallback für Hosts,
# deren Token die Usage-API nicht abfragen darf (403, z.B. setup-token).
LIMIT_HIT = {"resets_at": 0}

OAUTH_CLIENT_ID = "9d1c250a-e61b-44d9-88ed-5944d1962f5e"   # öffentl. Client-ID von Claude Code
OAUTH_TOKEN_URL = "https://api.anthropic.com/v1/oauth/token"


def _refresh_credentials() -> dict:
    """Abgelaufenen Interactive-Login per Refresh-Token erneuern (wie die CLI).
    Gibt das aktualisierte claudeAiOauth-Dict zurück, {} wenn nicht möglich."""
    try:
        data = json.loads(CRED_FILE.read_text(encoding="utf-8"))
        c = data.get("claudeAiOauth") or {}
    except Exception:
        return {}
    if not c.get("refreshToken"):
        return {}
    body = json.dumps({
        "grant_type": "refresh_token",
        "refresh_token": c["refreshToken"],
        "client_id": OAUTH_CLIENT_ID,
    }).encode()
    req = urllib.request.Request(OAUTH_TOKEN_URL, data=body,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            tok = json.load(r)
    except Exception as e:
        print(f"[auth] refresh fehlgeschlagen: {type(e).__name__}: {e}", flush=True)
        return {}
    c["accessToken"] = tok.get("access_token") or c["accessToken"]
    if tok.get("refresh_token"):
        c["refreshToken"] = tok["refresh_token"]
    c["expiresAt"] = int((time.time() + int(tok.get("expires_in") or 3600)) * 1000)
    data["claudeAiOauth"] = c
    tmp = CRED_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data), encoding="utf-8")
    tmp.chmod(0o600)
    tmp.replace(CRED_FILE)          # atomar -> kein halb geschriebenes File
    print("[auth] Interactive-Login per Refresh-Token erneuert", flush=True)
    return c


def _usage_token() -> str:
    """Frisches Interactive-Token bevorzugen (hat die nötigen Scopes), sonst oat."""
    try:
        c, src = _read_creds()
        if c.get("accessToken"):
            if (c.get("expiresAt") or 0) / 1000 > time.time() + 60:
                return c["accessToken"]
            # Selbst erneuern nur bei der Datei. Im Schlüsselbund könnten wir
            # das neue Refresh-Token nicht zurückschreiben — das alte wäre
            # danach verbraucht und die CLI abgemeldet. Dort erneuert die CLI
            # beim nächsten Chat selbst.
            if src == "file":
                c = _refresh_credentials()
                if c.get("accessToken"):
                    return c["accessToken"]
    except Exception:
        pass
    return load_web_token() or os.environ.get("CLAUDE_CODE_OAUTH_TOKEN", "")


def _limit_hit():
    """Reset-Zeit des zuletzt gerissenen Limits, falls noch in der Zukunft."""
    return LIMIT_HIT["resets_at"] if LIMIT_HIT["resets_at"] > time.time() else 0


@app.get("/api/usage")
def usage():
    """Aktuelle Auslastung der Subscription (gecacht, max. 1 Abfrage/Minute)."""
    if USAGE_CACHE["data"] and time.time() - USAGE_CACHE["t"] < 60:
        return dict(USAGE_CACHE["data"], limit_hit=_limit_hit())
    tok = _usage_token()
    if not tok:
        return {"available": False, "reason": "kein Token — bitte einloggen",
                "limit_hit": _limit_hit()}
    req = urllib.request.Request(
        "https://api.anthropic.com/api/oauth/usage",
        headers={"Authorization": f"Bearer {tok}",
                 "anthropic-beta": "oauth-2025-04-20"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            d = json.load(r)
    except Exception as e:
        return {"available": False, "reason": f"{type(e).__name__}: {e}",
                "limit_hit": _limit_hit()}
    out = {"available": True, "subscription": _cred_info().get("subscription", "")}
    for key, src in (("five_hour", d.get("five_hour")), ("seven_day", d.get("seven_day"))):
        src = src or {}
        out[key] = {"percent": src.get("utilization"), "resets_at": src.get("resets_at")}
    USAGE_CACHE.update(t=time.time(), data=out)
    return dict(out, limit_hit=_limit_hit())


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


@app.get("/api/folders")
def folders():
    """Projektordner unter WORKSPACE (für die Ordner-Auswahl im Chat)."""
    out = [WORKSPACE]
    try:
        for name in sorted(os.listdir(WORKSPACE), key=str.lower):
            p = os.path.join(WORKSPACE, name)
            if os.path.isdir(p) and not name.startswith("."):
                out.append(p)
    except Exception:
        pass
    return out


def _parse_skill_md(path):
    name = os.path.basename(os.path.dirname(path))
    desc = ""
    try:
        txt = Path(path).read_text(encoding="utf-8", errors="replace")
        m = re.search(r"^---\s*(.*?)\s*---", txt, re.S | re.M)
        fm = m.group(1) if m else txt[:500]
        nm = re.search(r"^name:\s*(.+)$", fm, re.M)
        dm = re.search(r"^description:\s*(.+)$", fm, re.M)
        if nm:
            name = nm.group(1).strip().strip("\"'")
        if dm:
            desc = dm.group(1).strip().strip("\"'")[:160]
    except Exception:
        pass
    return name, desc


GLOBAL_SKILLS_DIR = Path.home() / ".claude" / "skills"


@app.get("/api/skills")
def skills():
    """Sammelt Skills: global (~/.claude/skills) + aus allen Projekten."""
    groups = {}
    # Globale, projektübergreifende Skills zuerst (das Hermes-Gedächtnis von Cody)
    if GLOBAL_SKILLS_DIR.is_dir():
        gitems = []
        for d in sorted(os.listdir(GLOBAL_SKILLS_DIR), key=str.lower):
            md = GLOBAL_SKILLS_DIR / d / "SKILL.md"
            if md.is_file():
                nm, desc = _parse_skill_md(str(md))
                gitems.append({"name": nm, "desc": desc, "path": str(md), "kind": "md"})
        if gitems:
            groups["★ global (alle Projekte)"] = gitems
    if not os.path.isdir(WORKSPACE):
        return groups
    for proj in sorted(os.listdir(WORKSPACE), key=str.lower):
        pdir = os.path.join(WORKSPACE, proj)
        if not os.path.isdir(pdir) or proj.startswith("."):
            continue
        items = []
        for skroot in (os.path.join(pdir, ".claude", "skills"),
                       os.path.join(pdir, ".agents", "skills")):
            if os.path.isdir(skroot):
                for d in sorted(os.listdir(skroot), key=str.lower):
                    md = os.path.join(skroot, d, "SKILL.md")
                    if os.path.isfile(md):
                        nm, desc = _parse_skill_md(md)
                        items.append({"name": nm, "desc": desc, "path": md, "kind": "md"})
        pyroot = os.path.join(pdir, "skills")
        if os.path.isdir(pyroot):
            for fn in sorted(os.listdir(pyroot), key=str.lower):
                if fn.endswith(".py") and not fn.startswith("_"):
                    items.append({"name": fn[:-3], "desc": "(Python-Skill)",
                                  "path": os.path.join(pyroot, fn), "kind": "py"})
        if items:
            groups[proj] = items
    return groups


@app.get("/api/skill")
def skill_file(path: str):
    rp = os.path.realpath(path)
    roots = [os.path.realpath(WORKSPACE), os.path.realpath(str(GLOBAL_SKILLS_DIR))]
    # os.sep anhängen -> ~/projects2 zählt nicht als "unter ~/projects"
    if not any(rp == r or rp.startswith(r + os.sep) for r in roots) or not os.path.isfile(rp):
        return JSONResponse({"error": "not allowed"}, status_code=403)
    try:
        content = Path(rp).read_text(encoding="utf-8", errors="replace")[:30000]
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)
    return {"path": rp, "content": content}


# ---------- Datei-Vorschau / Download (Pfade in Codys Antworten anklickbar) ----------
MAX_FILE_SERVE = 200 * 1024 * 1024


@app.get("/api/file")
def file_get(path: str, dl: int = 0):
    """Liefert eine Datei aus dem Workspace aus. Dotfiles (.env, .oauth-token, …)
    und alles außerhalb des Workspace sind tabu."""
    rp = os.path.realpath(path)
    root = os.path.realpath(WORKSPACE)
    if not (rp == root or rp.startswith(root + os.sep)):
        return JSONResponse({"error": "nur Dateien im Workspace"}, status_code=403)
    rel = os.path.relpath(rp, root)
    if any(part.startswith(".") for part in rel.split(os.sep)):
        return JSONResponse({"error": "versteckte Dateien sind tabu"}, status_code=403)
    if not os.path.isfile(rp):
        return JSONResponse({"error": "keine Datei"}, status_code=404)
    if os.path.getsize(rp) > MAX_FILE_SERVE:
        return JSONResponse({"error": "Datei zu groß"}, status_code=400)
    fname = os.path.basename(rp)
    if dl:
        return FileResponse(rp, filename=fname)
    # Unbekannte Typen als text/plain inline zeigen statt Download zu erzwingen
    import mimetypes
    mt = mimetypes.guess_type(fname)[0] or "text/plain; charset=utf-8"
    return FileResponse(rp, media_type=mt,
                        headers={"Content-Disposition": f'inline; filename="{fname}"'})


@app.get("/api/mcp")
def mcp():
    """Liste der konfigurierten MCP-Server / Konnektoren (via `claude mcp list`)."""
    try:
        out = subprocess.run(
            [claude_bin() or "claude", "mcp", "list"],
            capture_output=True, text=True, timeout=30, cwd=WORKSPACE,
            env=claude_env(),
        ).stdout
    except Exception as e:
        return {"servers": [], "error": str(e)}
    servers = []
    for line in out.splitlines():
        line = line.strip()
        if not line or line.lower().startswith("checking"):
            continue
        if ": " in line and " - " in line:
            name, rest = line.split(": ", 1)
            url, status = rest.rsplit(" - ", 1)
            low = status.lower()
            servers.append({
                "name": name.strip(),
                "url": url.strip(),
                "status": status.strip(),
                "ok": ("✔" in status) or ("connected" in low) or ("✓" in status),
                "needs_auth": "auth" in low,
            })
    return {"servers": servers}


# ---------- Externe KI-Anbieter (ChatGPT, Gemini, DeepSeek, Ollama) ----------
@app.get("/api/llm/providers")
def llm_providers(refresh: int = 0):
    """Anbieter + verfügbare Modelle (live abgefragt, gecacht) — ohne Keys."""
    return llmmod.public_providers(bool(refresh))


@app.post("/api/llm/providers")
async def llm_providers_save(req: Request):
    """Key/URL speichern bzw. Anbieter (de)aktivieren; testet direkt die Verbindung."""
    body = await req.json()
    pid = (body.get("id") or "").strip()
    if pid not in llmmod.PROVIDERS:
        return JSONResponse({"error": "unbekannter Anbieter"}, status_code=400)
    llmmod.save_provider(pid, api_key=body.get("api_key"),
                         base_url=body.get("base_url"), enabled=body.get("enabled"))
    if body.get("enabled") is False or not llmmod.is_configured(pid):
        return {"ok": True, "models": 0, "error": ""}
    models, err = await asyncio.to_thread(llmmod.list_remote_models, pid, True)
    return {"ok": not err, "models": len(models), "error": err}


# ---------- Bonsai: läuft der lokale Server gerade (= VRAM belegt)? ----------
@app.get("/api/bonsai/status")
def bonsai_status():
    return bonsaimod.status()


@app.post("/api/bonsai/stop")
def bonsai_stop():
    """VRAM sofort freigeben, ohne auf den Leerlauf-Wächter zu warten."""
    bonsaimod.stop()
    return bonsaimod.status()


# ---------- Ollama: lokale Modelle ansehen / laden / löschen ----------
@app.get("/api/ollama/models")
def ollama_models():
    """Installierte Modelle + Katalog + laufende Downloads + Install-Status."""
    out = {"installed": [], "catalog": llmmod.OLLAMA_CATALOG,
           "pulls": llmmod.ollama_pulls(), "error": ""}
    out.update(llmmod.ollama_install_status())   # bin (vorhanden?) + install (Fortschritt)
    try:
        out["installed"] = llmmod.ollama_installed()
        out["reachable"] = True
    except Exception as e:
        out["error"] = llmmod.friendly_error("ollama", e)
        out["reachable"] = False
    return out


@app.post("/api/ollama/install")
async def ollama_install():
    """Ollama herunterladen (offizielles Linux-Paket), entpacken und starten —
    bzw. nur starten, wenn es schon installiert ist. Läuft im Hintergrund."""
    return llmmod.ollama_install_start()


@app.post("/api/ollama/pull")
async def ollama_pull(req: Request):
    """Download starten — läuft server-seitig im Hintergrund weiter."""
    body = await req.json()
    try:
        return llmmod.ollama_pull_start(body.get("model") or "")
    except llmmod.LLMError as e:
        return JSONResponse({"error": str(e)}, status_code=400)


@app.post("/api/ollama/pull_cancel")
async def ollama_pull_cancel(req: Request):
    body = await req.json()
    return {"cancelled": llmmod.ollama_pull_cancel(body.get("model") or "")}


@app.post("/api/ollama/delete")
async def ollama_delete(req: Request):
    body = await req.json()
    model = (body.get("model") or "").strip()
    try:
        await asyncio.to_thread(llmmod.ollama_delete, model)
    except llmmod.LLMError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    except Exception as e:
        return JSONResponse({"error": llmmod.friendly_error("ollama", e)}, status_code=400)
    return {"deleted": True, "model": model}


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
        quellen = list(BASE_DIR.glob("*.py")) + [STATIC_DIR / "index.html"]
        return str(int(max(f.stat().st_mtime for f in quellen if f.exists())))
    except Exception:
        return ""


# Beim Import festhalten, nicht bei jeder Abfrage: gefragt ist der Stand, mit
# dem der Server hochgefahren ist, nicht der auf der Platte von jetzt.
CODE_STAMP = code_stamp()


@app.get("/api/version")
def version():
    # runtime/home verraten, WELCHE Instanz gerade antwortet. Ohne das ist von
    # außen nicht zu sehen, ob man im alten Docker-Container gelandet ist oder
    # in der nativen App — beide hören auf 127.0.0.1:8765 und sehen gleich aus.
    in_docker = os.path.exists("/.dockerenv")
    return {
        "version": VERSION,
        "runtime": "docker" if in_docker else "nativ",
        "home": str(Path.home()),
        "workspace": WORKSPACE,
        "assistant": cfg.assistant_name(),
        "claude": bool(claude_bin()),
        # Ordner UND Version, damit ein Starter erkennen kann, ob der laufende
        # Server zum Code auf der Platte passt — siehe desktop.py.
        "dir": str(BASE_DIR),
        # Die Version allein reicht dafür nicht: sie steht oft still, während
        # sich der Code sehr wohl geändert hat. Dann hängt sich ein Neustart
        # wortlos an die alte Instanz, und neue Routen fehlen einfach.
        "code": CODE_STAMP,
    }


# ---------- Einstellungen ----------
# Speicherung, Vorgaben und Prüfung liegen in config.py — dieselbe Stelle,
# aus der auch llm.py die Namen liest.
# ---------- Werkzeug-Maschinen einrichten (Claude Code / Hermes) ----------
@app.get("/api/engines")
def engines():
    """Was installiert ist und was fehlt — Grundlage der Einstellungsseite."""
    return {
        "claude": {"installed": bool(claude_bin()), "path": claude_bin(),
                   "web_login": WEB_LOGIN_OK,
                   "npm": bool(shutil.which("npm"))},
        "hermes": {"installed": bool(hermesmod.hermes_bin()),
                   "path": hermesmod.hermes_bin(),
                   "version": hermesmod.version(),
                   "home": hermesmod.hermes_home(),
                   "posix": os.name == "posix"},
    }


@app.post("/api/engines/hermes/install")
async def hermes_install():
    return hermesmod.install_start()


@app.get("/api/engines/hermes/install")
def hermes_install_state():
    return hermesmod.install_state()


@app.post("/api/engines/claude/install")
async def claude_install():
    return claude_install_start()


# ---------- Werkzeuge aktuell halten ----------
# Läuft beim Start von allein (siehe _start_scheduler) und lässt sich hier von
# Hand anstoßen. Die Arbeit selbst steckt in updates.py.
@app.get("/api/updates")
def updates_state():
    return updmod.state()


@app.post("/api/updates/run")
async def updates_run():
    # Während ein Chat läuft nicht anfassen: `claude update` tauscht das
    # Programm unter dem laufenden Prozess aus. Der Boot-Lauf hat das Problem
    # nicht — da gibt es noch keine Läufe.
    if any(not r.done for r in RUNS.values()):
        return {"ok": False, "error": "Es läuft gerade ein Chat — bitte erst abwarten."}
    return updmod.start(trigger="manuell")


@app.get("/api/engines/claude/install")
def claude_install_state():
    st = dict(CLAUDE_INSTALL)
    st["log"] = list(st["log"])[-40:]
    st["installed"] = bool(claude_bin())
    return st


# npm-Installation im Hintergrund, damit die Oberfläche nicht blockiert.
# Dasselbe Muster wie beim Ollama-Download: geteilter Zustand, Frontend pollt.
CLAUDE_INSTALL = {"running": False, "done": True, "log": [], "error": ""}
_CLAUDE_INSTALL_LOCK = threading.Lock()


def claude_install_start():
    with _CLAUDE_INSTALL_LOCK:
        if CLAUDE_INSTALL["running"]:
            return {"ok": True, "already": True}
        CLAUDE_INSTALL.update(running=True, done=False, log=[], error="")

    def worker():
        try:
            if not shutil.which("npm"):
                raise RuntimeError(
                    "npm fehlt — Claude Code wird darüber installiert. "
                    "Node.js von nodejs.org einrichten und CONSTRUCT neu starten.")
            CLAUDE_INSTALL["log"].append("» npm install -g @anthropic-ai/claude-code")
            proc = subprocess.Popen(
                [shutil.which("npm"), "install", "-g", "@anthropic-ai/claude-code"],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            for line in proc.stdout:
                line = line.strip()
                if line:
                    CLAUDE_INSTALL["log"].append(line[:300])
            proc.wait()
            if proc.returncode != 0:
                raise RuntimeError(f"npm beendet mit Code {proc.returncode}")
            if not claude_bin():
                raise RuntimeError("Installation lief durch, aber 'claude' ist nicht "
                                   "im PATH. Meist hilft ein Neustart von CONSTRUCT.")
            CLAUDE_INSTALL["log"].append("✓ fertig — jetzt einmal anmelden")
        except Exception as e:
            CLAUDE_INSTALL["error"] = f"{type(e).__name__}: {e}"
            CLAUDE_INSTALL["log"].append("!! " + CLAUDE_INSTALL["error"])
        finally:
            CLAUDE_INSTALL.update(running=False, done=True)

    threading.Thread(target=worker, daemon=True).start()
    return {"ok": True}


@app.get("/api/persona")
def persona_get():
    """SOUL.md und USER.md im Klartext — die Einstellungsseite bearbeitet sie."""
    return {k: cfg.persona_read(k) for k in cfg.PERSONA_FILES}


@app.post("/api/persona")
async def persona_set(req: Request):
    body = await req.json()
    out = {}
    for k in cfg.PERSONA_FILES:
        if k in body:
            out[k] = cfg.persona_write(k, body[k])
    return {"ok": True, **out}


@app.get("/api/settings")
def settings_get():
    return cfg.load_settings()


@app.post("/api/settings")
async def settings_set(req: Request):
    return cfg.apply_patch(await req.json())


# ---------- Vorlesen (Gemini TTS) ----------
@app.post("/api/tts")
async def tts_speak(req: Request):
    """Text → WAV. Stimme/Modell aus den Einstellungen, einzeln überschreibbar
    (für die Hörprobe im Einstellungsdialog)."""
    body = await req.json()
    st = cfg.load_settings()
    conf, lang = st["tts"], st["lang"]
    model = body.get("model") if body.get("model") in cfg.TTS_MODELS else conf["model"]
    voice = re.sub(r"[^\w.\-]", "", str(body.get("voice") or "")) or conf["voice"][lang]
    style = str(body.get("style") if "style" in body else conf["style"][lang])[:200]
    try:
        wav = await asyncio.to_thread(ttsmod.synthesize, str(body.get("text") or ""),
                                      model, voice, style, lang)
    except ttsmod.TTSError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    return Response(wav, media_type="audio/wav")


@app.get("/api/tts/voices")
async def tts_voices(lang: str = "de-DE"):
    if not re.fullmatch(r"[A-Za-z]{2,3}(-[A-Za-z0-9]{2,4})?", lang):
        return JSONResponse({"error": "ungültiger Sprachcode"}, status_code=400)
    try:
        return {"voices": await asyncio.to_thread(ttsmod.list_voices, lang)}
    except ttsmod.TTSError as e:
        return JSONResponse({"error": str(e), "voices": []}, status_code=400)


# ---------- Telegram (Einrichtung unter ⚙) ----------
@app.get("/api/telegram")
def telegram_get():
    return tgmod.public_conf()


@app.post("/api/telegram")
async def telegram_set(req: Request):
    """Speichern und den Bot neu starten. Ein neuer Token wird vorher geprüft —
    ein Tippfehler soll hier auffallen, nicht erst als stummer Bot."""
    body = await req.json()
    tok = (body.get("token") or "").strip()
    if tok:
        try:
            await asyncio.to_thread(tgmod.check_token, tok)
        except Exception as e:
            return JSONResponse({"error": cfg.L("Token ungültig: ", "Invalid token: ") + str(e)},
                                status_code=400)
    else:
        body.pop("token", None)      # leer = unverändert lassen
    tgmod.save_conf(body)
    tgmod.restart()
    return tgmod.public_conf()


@app.post("/api/telegram/test")
async def telegram_test():
    ok = await asyncio.to_thread(tgmod.send_owner, cfg.L(
        f"👋 Hallo von {cfg.assistant_name()} — Telegram ist eingerichtet.",
        f"👋 Hi from {cfg.assistant_name()} — Telegram is set up."))
    if not ok:
        return JSONResponse({"error": cfg.L("Senden fehlgeschlagen — Token und Chat-ID prüfen.",
                                            "Sending failed — check token and chat ID.")},
                            status_code=400)
    return {"ok": True}


# ---------- Kalender ----------
@app.get("/api/events")
def events_list():
    """Alle Termine (die Web-UI rendert daraus den Kalender)."""
    return cal.load_events()


@app.post("/api/events")
async def events_add(req: Request):
    body = await req.json()
    date = (body.get("date") or "").strip()
    title = (body.get("title") or "").strip()
    if not date or not title:
        return JSONResponse({"error": "date und title sind nötig"}, status_code=400)
    repeat = "yearly" if (body.get("repeat") or "") == "yearly" else ""
    ev = cal.add_event(date, title, body.get("time", ""), body.get("notes", ""), repeat,
                       body.get("prompt", ""))
    return ev


@app.delete("/api/events/{eid}")
def events_del(eid: str):
    return {"deleted": cal.remove_event(eid)}


# ---------- E-Mail ----------
# IMAP/SMTP sind blockierend -> GET-Endpunkte als sync def (FastAPI-Threadpool),
# POST-Endpunkte (brauchen await req.json()) schieben die Arbeit per to_thread weg.
def _mail_call(fn, *a, **kw):
    try:
        return fn(*a, **kw)
    except mailmod.MailError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    except Exception as e:
        return JSONResponse({"error": f"{type(e).__name__}: {e}"}, status_code=500)


@app.get("/api/mail/accounts")
def mail_accounts():
    return {"accounts": mailmod.public_accounts()}


@app.post("/api/mail/accounts")
async def mail_accounts_save(req: Request):
    body = await req.json()
    return _mail_call(mailmod.save_account,
                      (body.get("email") or ""), body.get("password") or "")


@app.delete("/api/mail/accounts/{addr}")
def mail_accounts_del(addr: str):
    return _mail_call(mailmod.delete_account, addr)


@app.post("/api/mail/test")
async def mail_test(req: Request):
    body = await req.json()
    return await asyncio.to_thread(_mail_call, mailmod.test_account, body.get("email") or "")


@app.get("/api/mail/list")
def mail_list(account: str = "", force: int = 0, limit: int = 50):
    # limit=0 → ALLE Mails (fürs Aufräumen); sonst wie gehabt gedeckelt
    return _mail_call(mailmod.list_all, account, bool(force), max(0, min(limit, 10000)))


@app.get("/api/mail/msg")
def mail_msg(account: str, uid: str, folder: str = "INBOX"):
    return _mail_call(mailmod.get_message, account, uid, folder)


@app.get("/api/mail/att")
def mail_att(account: str, uid: str, idx: int, folder: str = "INBOX"):
    try:
        data, name, mime = mailmod.get_attachment(account, uid, idx, folder)
    except mailmod.MailError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    except Exception as e:
        return JSONResponse({"error": f"{type(e).__name__}: {e}"}, status_code=500)
    quoted = urllib.parse.quote(name)
    return Response(content=data, media_type=mime,
                    headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quoted}"})


@app.post("/api/mail/delete")
async def mail_delete(req: Request):
    body = await req.json()
    return await asyncio.to_thread(
        _mail_call, mailmod.delete_message,
        body.get("account") or "", str(body.get("uid") or ""), body.get("folder") or "INBOX")


@app.post("/api/mail/delete_many")
async def mail_delete_many(req: Request):
    body = await req.json()
    items = body.get("items") or []
    if not isinstance(items, list) or len(items) > 5000:
        return JSONResponse({"error": "items: Liste mit max. 5000 Einträgen"}, status_code=400)
    return await asyncio.to_thread(_mail_call, mailmod.delete_many, items)


@app.post("/api/mail/flag")
async def mail_flag(req: Request):
    body = await req.json()
    return await asyncio.to_thread(
        _mail_call, mailmod.set_seen,
        body.get("account") or "", str(body.get("uid") or ""),
        bool(body.get("seen")), body.get("folder") or "INBOX")


@app.post("/api/mail/send")
async def mail_send(req: Request):
    body = await req.json()
    return await asyncio.to_thread(
        _mail_call, mailmod.send_mail,
        body.get("account") or "", body.get("to") or "", body.get("cc") or "",
        body.get("bcc") or "", body.get("subject") or "", body.get("body") or "",
        body.get("attachments") or [], body.get("reply") or "")


@app.post("/api/mail/attach")
async def mail_attach(file: UploadFile = File(...)):
    """Anhang für den VERSAND hochladen — jeder Dateityp, landet in mail_attach/
    (nicht web-gemountet) und wird nur von send_mail wieder angefasst."""
    data = await file.read()
    if len(data) > attach.MAX_UPLOAD:
        return JSONResponse({"error": "Datei zu groß (max. 25 MB)"}, status_code=400)
    name = re.sub(r"[\\/\x00-\x1f]", "_", os.path.basename(file.filename or "anhang"))[:180]
    sub = mailmod.ATTACH_DIR / uuid.uuid4().hex
    sub.mkdir(parents=True, exist_ok=True)
    dest = sub / (name or "anhang")
    dest.write_bytes(data)
    return {"path": str(dest), "name": name, "size": len(data)}


@app.get("/api/mail/categories")
def mail_categories():
    return {"categories": mailmod.load_meta()["categories"]}


@app.post("/api/mail/categories")
async def mail_categories_edit(req: Request):
    body = await req.json()
    return _mail_call(mailmod.edit_categories, body.get("add") or "", body.get("remove") or "")


@app.post("/api/mail/categorize")
async def mail_categorize(req: Request):
    body = await req.json()
    return _mail_call(mailmod.set_category, body.get("key") or "", body.get("category") or "")


@app.post("/api/mail/categorize_many")
async def mail_categorize_many(req: Request):
    body = await req.json()
    return _mail_call(mailmod.set_category_many, body.get("keys") or [], body.get("category") or "")


@app.post("/api/mail/ms_login")
async def mail_ms_login(req: Request):
    body = await req.json()
    return await asyncio.to_thread(_mail_call, mailmod.ms_login_start, body.get("email") or "")


@app.get("/api/mail/ms_poll")
def mail_ms_poll(email: str):
    return _mail_call(mailmod.ms_poll, email)


@app.get("/")
def index():
    html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
    # Ausbaustufe SYNCHRON mitgeben, nicht per fetch: sonst baut sich die Seite
    # einmal mit Skills/E-Mail/Teile auf und räumt sie einen Wimpernschlag
    # später wieder weg — sichtbares Flackern und ein kurz klickbares Menü.
    # re.DOTALL ist Pflicht: das Vorgabe-Objekt in index.html geht über mehrere
    # Zeilen. Ohne das Flag greift die Ersetzung stillschweigend nicht, die Seite
    # bekommt die eingebauten Vorgaben statt der echten Einstellungen — und der
    # Fehler sieht aus wie "die Einstellungen speichern nicht".
    payload = "window.CONSTRUCT=" + json.dumps({
        "user": cfg.user_name(),
        "assistant": cfg.assistant_name(),
        "claude": bool(claude_bin()),
        "web_login": WEB_LOGIN_OK,
        "lang": cfg.lang(),
        "workspace": WORKSPACE,
        "settings": cfg.load_settings(),
    }, ensure_ascii=False) + ";"
    # Wörterbuch mit Stempel: index.html kommt nie aus dem Cache, das Script
    # schon — ohne ?v= sähe man nach einem Update die alten Übersetzungen.
    try:
        v = int((STATIC_DIR / "i18n.js").stat().st_mtime)
    except OSError:
        v = 0
    html = html.replace('src="/static/i18n.js"', f'src="/static/i18n.js?v={v}"', 1)
    # Ersatz als Funktion, nicht als Zeichenkette: in einem Ersatz-String wären
    # Backslashes und \g Steuerzeichen, und genau die stecken in JSON.
    html = re.sub(r"window\.CONSTRUCT\s*=\s*\{.*?\};", lambda _m: payload,
                  html, count=1, flags=re.DOTALL)
    # Kein Browser-Cache -> immer aktueller Stand, kein Hard-Refresh nötig
    return HTMLResponse(html, headers={
        "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
        "Pragma": "no-cache",
    })


@app.post("/api/upload")
async def upload(file: UploadFile = File(...)):
    ext = os.path.splitext(file.filename or "")[1].lower() or ".png"
    data = await file.read()
    try:
        return attach.store(data, ext, file.filename or "")
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)


SESS_META = BASE_DIR / "sessions_meta.json"


def load_meta() -> dict:
    """sessions_meta.json: {"archived": [ids], "names": {id: eigener Titel}}."""
    try:
        d = json.loads(SESS_META.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def save_meta(d: dict):
    tmp = SESS_META.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(SESS_META)


def load_archived():
    """Set archivierter Session-IDs (nur ausgeblendet, NICHT gelöscht)."""
    return set(load_meta().get("archived", []))


def save_archived(ids):
    meta = load_meta()
    meta["archived"] = sorted(ids)
    save_meta(meta)


# MCP-Server, deren Sitzungen von einer eigenstaendigen Agenten-Anwendung
# stammen und nicht von einem Gespraech mit Kevin.
#
# Warum es das braucht: FACTORIA arbeitet im selben Projektordner und legt pro
# Agentenzug eine eigene Claude-Code-Sitzung an. Gemessen am 04.09.2026 kamen
# 46 von 55 Eintraegen in dieser Uebersicht von dort — Kevins eigene Gespraeche
# gingen darin unter.
#
# Erkannt wird am MCP-Praefix in der WERKZEUGLISTE des Laufs, nicht am Text:
# ein Gespraech ueber Factoria (wie dieses hier) nennt den Namen auch, hat aber
# nie `mcp__factoria__*` als Werkzeug bekommen. Und die Liste steht im
# Transkript, egal ob der Agent die Werkzeuge am Ende benutzt hat — auch ein
# Zug, der nichts an den Bus gab, wird so erkannt.
FREMDE_MCP = ("factoria",)
MCP_RE = re.compile(r"^mcp__([a-z0-9_-]+)__")

# Arbeitsordner, deren Sitzungen gar nicht erst in der Uebersicht auftauchen.
# /tmp ist ein Wegwerfordner: dort landen Testlaeufe (auch von FACTORIA und vom
# Pruefstand), an denen Kevin nie weiterarbeitet. Sie werden uebersprungen und
# nicht bloss ausgeblendet — anders als die Sitzungen der Firma, die man sich
# mit dem Schalter noch ansehen koennen soll.
VERBORGENE_CWDS = ("/tmp",)


def _verborgen(cwd: str) -> bool:
    c = (cwd or "").rstrip("/")
    return any(c == v or c.startswith(v + "/") for v in VERBORGENE_CWDS)

# Der zweite Weg. Nicht jeder fremde Lauf hat einen Bus: FACTORIA startet fuer
# sich selbst auch werkzeuglose Laeufe (Gespraech verdichten, Gedaechtnis
# eindicken), und die saehen hier aus wie ein Gespraech von Kevin. Sie setzen
# deshalb eine Kennzeile an den Anfang ihres Prompts, die im Transkript landet.
# Das ist ein Textmerkmal — aber eines, das die andere Seite absichtlich setzt,
# und kein Erraten anhand des Inhalts.
INTERN_MARKEN = {"[factoria-intern]": "factoria"}


def _fremde_firma(ev: dict) -> str:
    """Von welcher Agenten-Anwendung stammt dieser Lauf? "" = von Kevin."""
    if ev.get("type") == "attachment":
        att = ev.get("attachment") or {}
        if att.get("type") == "deferred_tools_delta":
            for n in (att.get("addedNames") or []):
                m = MCP_RE.match(str(n))
                if m and m.group(1) in FREMDE_MCP:
                    return m.group(1)
        return ""
    if ev.get("type") == "user":
        txt = extract_text(ev.get("message", {}).get("content")).lstrip()
        for marke, firma in INTERN_MARKEN.items():
            if txt.startswith(marke):
                return firma
    return ""


@app.get("/api/sessions")
def sessions():
    """Listet alle Claude-Code-Sessions (eine .jsonl-Datei = eine Session)
    plus die Sessions externer Modelle (llm_sessions/).

    Jeder Eintrag traegt ein Feld `agent`: leer bei Kevins eigenen Gespraechen,
    sonst der Name der Anwendung, die den Lauf gestartet hat (siehe
    FREMDE_MCP). Gefiltert wird nicht hier, sondern in der Oberflaeche — weg
    ist weg, und manchmal will man doch nachsehen, was die Firma getrieben hat.
    """
    out = []
    meta = load_meta()
    archived = set(meta.get("archived", []))
    names = meta.get("names", {})
    for s in llmmod.list_sessions() + hermesmod.list_sessions():
        s["title"] = names.get(s["id"]) or s["title"]
        s["renamed"] = s["id"] in names
        s["archived"] = s["id"] in archived
        out.append(s)
    if not PROJECTS_DIR.exists():
        return out
    for f in PROJECTS_DIR.glob("*/*.jsonl"):
        try:
            stat = f.stat()
            title = None
            cwd = None
            firma = ""
            # Nur die ersten paar Zeilen lesen reicht für Titel + cwd (Performance!)
            with f.open(encoding="utf-8", errors="replace") as fh:
                for i, line in enumerate(fh):
                    if i > 60 or (title and cwd and firma):
                        break
                    try:
                        ev = json.loads(line)
                    except Exception:
                        continue
                    if not firma:
                        firma = _fremde_firma(ev)
                    if cwd is None and isinstance(ev.get("cwd"), str):
                        cwd = ev["cwd"]
                    if title is None and ev.get("type") == "user":
                        txt = extract_text(ev.get("message", {}).get("content")).strip()
                        # System-/Befehls-Wrapper überspringen
                        if txt and not txt.startswith("<") and not txt.startswith("Caveat"):
                            title = txt.replace("\n", " ")[:80]
            if _verborgen(cwd or ""):
                continue
            out.append({
                "id": f.stem,
                "project": f.parent.name,
                "cwd": cwd or "(unbekannt)",
                "title": names.get(f.stem) or title or "(ohne Titel)",
                "renamed": f.stem in names,
                "mtime": stat.st_mtime,
                "size": stat.st_size,
                "archived": f.stem in archived,
                "agent": firma,
            })
        except Exception:
            continue
    out.sort(key=lambda x: x["mtime"], reverse=True)
    return out


# Tagebuch fuer den Kalender: an welchen Tagen in welchem Projektordner
# gearbeitet wurde. Nicht als Termine gespeichert, sondern aus den Transkripten
# abgeleitet — so ist auch alles da, was VOR dieser Funktion lief, und nichts
# kann auseinanderlaufen. Gezaehlt werden nur echte Eingaben (keine Tool-
# Ergebnisse, keine System-Wrapper); ein Tag gehoert zur ORTSZEIT, nicht UTC.
# Pro Datei gecacht nach (mtime, size): ganze Transkripte zu lesen ist teuer,
# und die meisten aendern sich zwischen zwei Kalenderaufrufen nicht.
_ACTIVITY_CACHE: dict = {}


def _day_of(ts: str) -> str:
    from datetime import datetime
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone().strftime("%Y-%m-%d")
    except Exception:
        return ""


def _file_activity(f: Path) -> dict:
    """{"title", "agent", "days": {tag: {cwd: anzahl Eingaben}}} einer .jsonl."""
    st = f.stat()
    key = (st.st_mtime, st.st_size)
    hit = _ACTIVITY_CACHE.get(f)
    if hit and hit[0] == key:
        return hit[1]
    days: dict = {}
    title, firma, cwd = None, "", None
    with f.open(encoding="utf-8", errors="replace") as fh:
        for line in fh:
            # Schnellfilter vor json.loads: der Grossteil der Zeilen sind
            # Assistant-Antworten und Tool-Ergebnisse.
            if '"type":"user"' not in line and '"type":"attachment"' not in line:
                continue
            try:
                ev = json.loads(line)
            except Exception:
                continue
            if not firma:
                firma = _fremde_firma(ev)
            if ev.get("type") != "user" or ev.get("isSidechain") or ev.get("isMeta"):
                continue
            if isinstance(ev.get("cwd"), str):
                cwd = ev["cwd"]
            txt = extract_text(ev.get("message", {}).get("content")).strip()
            if not txt or txt.startswith("<") or txt.startswith("Caveat"):
                continue
            if title is None:
                title = txt.replace("\n", " ")[:80]
            day = _day_of(ev.get("timestamp") or "")
            if day and cwd and not _verborgen(cwd):
                per = days.setdefault(day, {})
                per[cwd] = per.get(cwd, 0) + 1
    res = {"title": title, "agent": firma, "days": days}
    _ACTIVITY_CACHE[f] = (key, res)
    return res


@app.get("/api/activity")
def activity(start: str = "", end: str = ""):
    """Projekte je Tag im Bereich [start, end] (YYYY-MM-DD, beide inklusive):
    {tag: [{"cwd", "n", "sessions": [{"id", "project", "cwd", "title", "n"}]}]}
    Sessions fremder Agenten-Anwendungen (FREMDE_MCP) zaehlen nicht mit."""
    from datetime import datetime
    out: dict = {}
    names = load_meta().get("names", {})

    def add(day, cwd, sess, n):
        if (start and day < start) or (end and day > end):
            return
        projs = out.setdefault(day, {})
        p = projs.setdefault(cwd, {"cwd": cwd, "n": 0, "sessions": []})
        p["n"] += n
        p["sessions"].append({**sess, "cwd": cwd, "n": n})

    if PROJECTS_DIR.exists():
        for f in PROJECTS_DIR.glob("*/*.jsonl"):
            try:
                a = _file_activity(f)
            except Exception:
                continue
            if a["agent"]:
                continue
            sess = {"id": f.stem, "project": f.parent.name,
                    "title": names.get(f.stem) or a["title"] or "(ohne Titel)"}
            for day, per in a["days"].items():
                for cwd, n in per.items():
                    add(day, cwd, sess, n)
    # Externe Modelle kennen keine Zeitstempel pro Nachricht — dort zaehlt der
    # Tag der letzten Aenderung.
    for s in llmmod.list_sessions() + hermesmod.list_sessions():
        try:
            day = datetime.fromtimestamp(s["mtime"]).strftime("%Y-%m-%d")
        except Exception:
            continue
        add(day, s.get("cwd") or "(unbekannt)",
            {"id": s["id"], "project": s["project"], "title": names.get(s["id"]) or s["title"]}, 1)
    return {day: sorted(projs.values(), key=lambda p: -p["n"]) for day, projs in out.items()}


def _parse_transcript_lines(data: bytes):
    """JSONL-Bytes -> Anzeige-Nachrichten (wie die Verlaufs-Ansicht sie braucht)."""
    msgs = []
    for line in data.split(b"\n"):
        if not line.strip():
            continue
        try:
            ev = json.loads(line.decode("utf-8", "replace"))
        except Exception:
            continue
        t = ev.get("type")
        if t not in ("user", "assistant"):
            continue
        txt = extract_text(ev.get("message", {}).get("content")).strip()
        # Meta-Rauschen fremder Sessions (System-Reminder, CLI-Wrapper) ausblenden
        if not txt or (t == "user" and (txt.startswith("<") or txt.startswith("Caveat"))):
            continue
        msgs.append({"role": t, "text": txt})
    return msgs


def model_short(mid: str) -> str:
    """Modell-ID aus einem Transkript -> der Wert, den die Auswahlliste kennt.

    Frueher wurde hier auf die Reihe verkuerzt (claude-fable-5-1 -> "fable").
    Damit ging genau die Angabe verloren, um die es geht: WELCHES Fable. Die
    Oberflaeche fuehrt inzwischen volle IDs, also wird die ID durchgereicht und
    nur um das bereinigt, was nicht zur Auswahl gehoert — der Datumsstempel
    (claude-haiku-4-5-20251001) und der Kontext-Zusatz (…[1m]).

    Unbekanntes/synthetisches -> "" (= Konto-Standard).
    """
    m = (mid or "").lower().strip()
    m = re.sub(r"\[[^\]]*\]$", "", m)          # …[1m]
    if not m.startswith("claude-"):
        return ""
    m = re.sub(r"-\d{8}$", "", m)              # …-20251001
    return m


def _last_model(data: bytes) -> str:
    """Das zuletzt in DIESER Session tatsächlich genutzte Modell (aus der letzten
    Assistant-Nachricht). So zeigt die UI beim Öffnen das Session-Modell an."""
    for line in reversed(data.split(b"\n")):
        if not line.strip() or b'"model"' not in line:
            continue
        try:
            ev = json.loads(line.decode("utf-8", "replace"))
        except Exception:
            continue
        if ev.get("type") == "assistant":
            short = model_short(ev.get("message", {}).get("model", ""))
            if short:
                return short
    return ""


@app.get("/api/sessions/{project}/{sid}")
def session_detail(project: str, sid: str):
    if project == "llm":
        s = llmmod.load_session(sid)
        if not s:
            return JSONResponse({"error": "not found"}, status_code=404)
        return {"id": sid, "project": "llm", "offset": 0,
                "model": f"{s.get('provider', '')}:{s.get('model', '')}",
                "messages": llmmod.session_display(s)}
    if project == "hermes":
        # sid kommt mit Präfix aus der Liste; die Datenbank kennt es ohne.
        raw = sid[len("hermes-"):] if sid.startswith("hermes-") else sid
        msgs = hermesmod.session_messages(raw)
        if not msgs:
            return JSONResponse({"error": "not found"}, status_code=404)
        return {"id": "hermes-" + raw, "project": "hermes", "offset": 0,
                "model": "", "messages": msgs}
    f = PROJECTS_DIR / project / f"{sid}.jsonl"
    if not f.exists():
        return JSONResponse({"error": "not found"}, status_code=404)
    data = f.read_bytes()
    # offset = Dateigröße beim Lesen -> Startpunkt für den Live-Tail der UI
    return {"id": sid, "project": project, "offset": len(data),
            "model": _last_model(data),
            "messages": _parse_transcript_lines(data)}


SID_RE = re.compile(r"^[A-Za-z0-9-]{8,64}$")


@app.get("/api/session_tail/{sid}")
def session_tail(sid: str, offset: int = -1):
    """Live-Tail: alles NEUE in der Session-Datei seit `offset` (Byte-Position).
    So sieht die UI auch Sessions wachsen, die woanders laufen (Terminal etc.)."""
    if sid.startswith("llm-"):
        # externe Sessions wachsen nur durch eigene Läufe -> nichts zu tailen
        return {"offset": 0, "messages": []}
    if not SID_RE.match(sid):
        return JSONResponse({"error": "bad id"}, status_code=400)
    f = next(iter(PROJECTS_DIR.glob(f"*/{sid}.jsonl")), None)
    if f is None:
        return JSONResponse({"error": "not found"}, status_code=404)
    size = f.stat().st_size
    if offset < 0 or offset >= size:
        # nur synchronisieren (oder Datei wurde neu geschrieben/kleiner)
        return {"offset": size, "messages": []}
    with f.open("rb") as fh:
        fh.seek(offset)
        data = fh.read()
    # halbe letzte Zeile (wird gerade geschrieben) NICHT konsumieren
    if not data.endswith(b"\n"):
        cut = data.rfind(b"\n") + 1
        data, size = data[:cut], offset + cut
    return {"offset": size, "messages": _parse_transcript_lines(data)}


@app.post("/api/sessions/{sid}/archive")
async def session_archive(sid: str, req: Request):
    """Session aus-/einblenden (archivieren) — Datei bleibt erhalten."""
    body = await req.json()
    ids = load_archived()
    if body.get("archived"):
        ids.add(sid)
    else:
        ids.discard(sid)
    save_archived(ids)
    return {"id": sid, "archived": sid in ids}


@app.post("/api/sessions/{sid}/rename")
async def session_rename(sid: str, req: Request):
    """Eigenen Namen vergeben (leer = zurück zum automatischen Titel)."""
    body = await req.json()
    name = (body.get("name") or "").strip()[:120]
    meta = load_meta()
    names = meta.setdefault("names", {})
    if name:
        names[sid] = name
    else:
        names.pop(sid, None)
    save_meta(meta)
    return {"id": sid, "name": name}


@app.delete("/api/sessions/{project}/{sid}")
def session_delete(project: str, sid: str):
    """Session-Datei endgültig löschen (mit Pfad-Schutz)."""
    if project == "llm":
        if not llmmod.delete_session(sid):
            return JSONResponse({"error": "not found"}, status_code=404)
    elif project == "hermes":
        raw = sid[len("hermes-"):] if sid.startswith("hermes-") else sid
        if not hermesmod.delete_session(raw):
            return JSONResponse({"error": "not found"}, status_code=404)
    else:
        f = PROJECTS_DIR / project / f"{sid}.jsonl"
        try:
            rp = f.resolve()
            if rp.parent.parent != PROJECTS_DIR.resolve():
                return JSONResponse({"error": "not allowed"}, status_code=403)
        except Exception:
            return JSONResponse({"error": "bad path"}, status_code=400)
        if not rp.exists():
            return JSONResponse({"error": "not found"}, status_code=404)
        rp.unlink()
    meta = load_meta()
    changed = False
    if sid in meta.get("archived", []):
        meta["archived"].remove(sid)
        changed = True
    if meta.get("names", {}).pop(sid, None) is not None:
        changed = True
    if changed:
        save_meta(meta)
    return {"deleted": True, "id": sid}


# ---------- Entkoppelte Läufe (überleben Verbindungsabbruch/Reload) ----------
# claude läuft als Hintergrund-Task, die Ausgabe wird server-seitig gepuffert.
# Ein Client verbindet sich per run_id, bekommt erst den Backlog (Replay) und dann
# live weiter. Trennt der Browser (Reload/Schlaf/Netz), läuft der Task einfach
# weiter; beim Wiederverbinden wird alles nachgespielt. (Single-Worker-Annahme:
# der Zustand lebt im Prozess -> uvicorn mit EINEM Worker betreiben.)
RUNS = {}            # run_id -> Run
RUN_TTL = 900        # fertige Läufe nach 15 min vergessen

SSE_HEADERS = {
    "Cache-Control": "no-cache, no-transform",
    "X-Accel-Buffering": "no",
    "Connection": "keep-alive",
}


class Run:
    def __init__(self, run_id, cwd, session_id=None, model="", initial_prompt=""):
        self.id = run_id
        self.cwd = cwd
        self.model = model               # gewähltes Modell ("" = Konto-Standard)
        self.session_id = session_id     # füllt sich aus dem init-Event von claude
        self.initial_prompt = initial_prompt  # erste Nachricht (geht via stdin rein)
        self.events = []                 # gepufferte SSE-Events (Backlog für Replay)
        self.subs = set()                # aktive Abonnenten-Queues (Live-Clients)
        self.done = False
        self.proc = None
        self.task = None
        self.started = time.time()
        self.finished_at = None
        self.stdin_closed = False        # nach dem result nimmt der Lauf nichts mehr an
        # Hintergrundaufgaben, die claude selbst gestartet hat (Bash mit
        # run_in_background, Agenten). Solange hier etwas steht, bleibt der
        # Prozess nach dem Ergebnis am Leben — siehe Nachlauf in run_claude.
        self.hintergrund = {}            # task_id -> Beschreibung
        self.nachlauf = False            # Zug fertig, Prozess wartet auf den Hintergrund
        self.zug_offen = False           # laeuft gerade ein Zug (fuer "neuer_zug")
        self.last_text = ""              # Text des letzten Turns (für Telegram-Notify)
        self.notify_always = False       # geplante Aufgaben melden sich immer per Telegram
        self.task_title = ""             # Titel der geplanten Aufgabe (für die Meldung)

    def emit(self, ev):
        if ev.get("type") == "text":
            # hier statt in run_claude, damit auch Hermes-Läufe eine
            # Telegram-Zusammenfassung (maybe_notify) bekommen
            self.last_text += ev.get("text", "")
        # aufeinanderfolgende Text-Events zusammenfassen -> Puffer/Replay schlank
        if ev.get("type") == "text" and self.events and self.events[-1].get("type") == "text":
            self.events[-1]["text"] += ev.get("text", "")
        else:
            self.events.append(ev)
        for q in list(self.subs):
            q.put_nowait(ev)

    def finish(self):
        self.done = True
        self.finished_at = time.time()
        for q in list(self.subs):
            q.put_nowait(None)


def gc_runs():
    now = time.time()
    for rid in [r for r, run in RUNS.items()
                if run.done and run.finished_at and now - run.finished_at > RUN_TTL]:
        RUNS.pop(rid, None)


# ---------- Telegram-Benachrichtigung (wenn ein langer Lauf unbeobachtet fertig wird) ----------
# Eingerichtet wird Telegram unter ⚙ Einstellungen (telegram_bot.py).
NOTIFY_MIN_SECS = int(os.environ.get("CODY_NOTIFY_MIN_SECS", "90"))


def maybe_notify(run):
    """Nach Lauf-Ende: Telegram-Ping, wenn (a) geplante Aufgabe oder (b) der Lauf
    lange lief UND gerade niemand im Browser zuschaut (run.subs leer)."""
    conf = tgmod.load_conf()
    if not (conf["enabled"] and conf["token"] and conf["chat_id"]):
        return
    if not run.notify_always and not conf["notify"]:
        return
    dur = time.time() - run.started
    if not run.notify_always and (dur < NOTIFY_MIN_SECS or run.subs):
        return
    mins, secs = divmod(int(dur), 60)
    tail = run.last_text.strip()[-600:]
    head = (cfg.L("🤖 Geplante Aufgabe erledigt", "🤖 Scheduled task done") if run.notify_always
            else cfg.L(f"✅ {cfg.assistant_name()} ist fertig", f"✅ {cfg.assistant_name()} is done"))
    msg = f"{head} ({mins} m {secs} s, {os.path.basename(run.cwd or '?')})"
    if run.notify_always and run.task_title:
        msg += f" — {run.task_title}"
    if tail:
        msg += f":\n\n{tail}"
    threading.Thread(target=tgmod.send_owner, args=(msg,), daemon=True).start()


def stdin_message(prompt: str) -> bytes:
    """Eine User-Nachricht im stream-json-Eingabeformat von claude."""
    return (json.dumps({
        "type": "user",
        "message": {"role": "user", "content": [{"type": "text", "text": prompt}]},
    }, ensure_ascii=False) + "\n").encode()


def is_pdf(path) -> bool:
    return str(path).lower().endswith(".pdf")


def pdf_note(pdfs) -> str:
    """Hinweisblock für hochgeladene PDFs (Liedtexte, Dokumente).

    Beim Upload wurde ein Textauszug daneben gelegt; den soll das Modell
    zuerst lesen — die PDF selbst rendert das Read-Tool seitenweise als Bild,
    das kostet ein Vielfaches an Tokens.
    """
    lines = []
    for p in pdfs:
        txt = Path(str(p) + ".txt")
        if txt.is_file():
            lines.append(cfg.L(f"[Vom Nutzer hochgeladene PDF: {p} — Textauszug: {txt}]",
                               f"[PDF uploaded by the user: {p} — text extract: {txt}]"))
        else:
            lines.append(cfg.L(f"[Vom Nutzer hochgeladene PDF: {p} — kein Text extrahierbar, "
                               "vermutlich gescannt]",
                               f"[PDF uploaded by the user: {p} — no extractable text, "
                               "probably scanned]"))
    lines.append(cfg.L("(Lies zuerst den Textauszug mit dem Read-Tool; die PDF selbst nur, "
                       "wenn Layout oder Bilder wichtig sind.)",
                       "(Read the text extract with the Read tool first; open the PDF itself "
                       "only if layout or images matter.)"))
    return "\n".join(lines)


def build_prompt(text: str, images) -> str:
    """User-Text + Hinweise auf hochgeladene Dateien (Bilder, PDFs) kombinieren."""
    prompt = (text or "").strip()
    imgs = [p for p in (images or []) if not is_pdf(p)]
    pdfs = [p for p in (images or []) if is_pdf(p)]
    if imgs:
        img_lines = "\n".join(cfg.L(f"[Vom Nutzer hochgeladenes Bild: {p}]",
                                     f"[Image uploaded by the user: {p}]") for p in imgs)
        prompt = (f"{prompt}\n\n{img_lines}\n"
                  + cfg.L("(Bitte sieh dir die Bild-Datei(en) mit dem Read-Tool an.)",
                          "(Please look at the image file(s) with the Read tool.)")).strip()
    if pdfs:
        prompt = f"{prompt}\n\n{pdf_note(pdfs)}".strip()
    return prompt


async def run_claude(run, cmd):
    """Hintergrund-Task: schreibt Events in den Run-Puffer (NICHT an einen Client)."""
    stderr_chunks = []

    async def drain_stderr(stream):
        # stderr parallel leeren — sonst blockiert claude, wenn der Puffer volläuft
        while True:
            d = await stream.read(4096)
            if not d:
                break
            if len(stderr_chunks) < 256:
                stderr_chunks.append(d)

    if not claude_bin():
        run.emit({"type": "error", "message":
                  "⚠ Claude Code ist auf diesem Rechner nicht installiert. "
                  "Entweder unten links im 🧠-Menü ein anderes Modell wählen "
                  "(ChatGPT, Gemini …) oder Claude Code nachinstallieren: "
                  "<code>npm install -g @anthropic-ai/claude-code</code>"})
        run.stdin_closed = True
        run.finish()
        return

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=run.cwd,
            env=claude_env(),
            limit=64 * 1024 * 1024,   # große stream-json-Zeilen (Tool-Ergebnisse)
        )
        run.proc = proc
        # Erste Nachricht über stdin einspeisen; die Leitung bleibt offen, damit
        # Kevin dem laufenden Cody weitere Nachrichten nachschieben kann (Inject).
        proc.stdin.write(stdin_message(run.initial_prompt))
        await proc.stdin.drain()
        stderr_task = asyncio.create_task(drain_stderr(proc.stderr))
        thinking_sent = False
        got_error = False
        while True:
            try:
                raw = await proc.stdout.readline()
            except ValueError:
                print("[run] zeile > limit, übersprungen", flush=True)
                continue
            if not raw:
                break  # EOF — Prozess fertig
            line = raw.decode("utf-8", "replace").strip()
            if not line:
                continue
            try:
                ev = json.loads(line)
            except Exception:
                continue
            t = ev.get("type")
            if t in ("assistant", "stream_event") and not run.zug_offen:
                # Der erste Inhalt eines Zuges. Kommt er im Nachlauf — also
                # ohne dass Kevin etwas geschickt hat — hat eine
                # Hintergrundaufgabe den Zug ausgeloest, und die Oberflaeche
                # braucht eine neue Sprechblase dafuer.
                run.zug_offen = True
                if run.nachlauf:
                    run.nachlauf = False
                    run.emit({"type": "neuer_zug"})
            if t == "system" and ev.get("subtype") == "init":
                run.session_id = ev.get("session_id", run.session_id)
                run.emit({"type": "session", "session_id": run.session_id})
            elif t == "system" and ev.get("subtype") == "background_tasks_changed":
                # Die eine verlaessliche Liste: claude schickt sie bei jedem
                # Start und Ende einer Hintergrundaufgabe komplett.
                run.hintergrund = {x.get("task_id"): x.get("description") or x.get("task_type") or "?"
                                   for x in (ev.get("tasks") or []) if x.get("task_id")}
            elif t == "stream_event":
                e = ev.get("event", {})
                if e.get("type") == "content_block_delta":
                    d = e.get("delta", {})
                    if d.get("type") == "text_delta":
                        run.emit({"type": "text", "text": d.get("text", "")})
            elif t == "assistant":
                for block in ev.get("message", {}).get("content", []):
                    if not isinstance(block, dict):
                        continue
                    if block.get("type") == "thinking" and not thinking_sent:
                        thinking_sent = True
                        run.emit({"type": "thinking_marker"})
                    elif block.get("type") == "tool_use":
                        run.emit({
                            "type": "tool",
                            "id": block.get("id"),
                            "name": block.get("name", "?"),
                            "input": block.get("input", {}),
                        })
            elif t == "user":
                content = ev.get("message", {}).get("content")
                if isinstance(content, list):
                    for block in content:
                        if isinstance(block, dict) and block.get("type") == "tool_result":
                            c = block.get("content")
                            if isinstance(c, list):
                                c = "\n".join(x.get("text", "") for x in c if isinstance(x, dict))
                            run.emit({
                                "type": "tool_result",
                                "id": block.get("tool_use_id"),
                                "content": str(c)[:6000],
                                "is_error": bool(block.get("is_error")),
                            })
            elif t == "result":
                run.session_id = ev.get("session_id", run.session_id)
                # Fehler-Resultate (Limit erreicht, Login abgelaufen, …) wurden
                # früher verschluckt -> jetzt sichtbar machen.
                res_text = ev.get("result") if isinstance(ev.get("result"), str) else ""
                if ev.get("is_error") or ev.get("subtype") not in (None, "success"):
                    got_error = True
                    run.emit({"type": "error",
                              "message": friendly_claude_error(
                                  res_text or str(ev.get("subtype") or "Unbekannter Fehler"))})
                u = ev.get("usage") or {}
                ctx = ((u.get("input_tokens") or 0)
                       + (u.get("cache_read_input_tokens") or 0)
                       + (u.get("cache_creation_input_tokens") or 0))
                # `run.model` ist nur die AUSWAHL — bei "Standard" ist sie leer,
                # und ein Alias wie "fable" sagt nicht, welches Fable lief.
                # `modelUsage` im Ergebnis nennt die tatsaechlich benutzte ID
                # (gemessen: {"claude-fable-5-1": {...}}). Die ist gemeint, wenn
                # in der Oberflaeche ein Modell steht.
                echt = ""
                for mid in (ev.get("modelUsage") or {}):
                    echt = model_short(mid)
                    if echt:
                        break
                run.emit({
                    "type": "stats",
                    "duration_ms": ev.get("duration_ms"),
                    "out": u.get("output_tokens") or 0,
                    "ctx": ctx,
                    "model": echt or run.model,
                })
                run.zug_offen = False
                if run.hintergrund and time.time() - run.started < NACHLAUF_MAX:
                    # NACHLAUF. Der Zug ist fertig, aber claude hat noch
                    # Hintergrundaufgaben laufen. Bleibt stdin offen, bleibt
                    # der Prozess am Leben und meldet sich von selbst wieder,
                    # sobald eine fertig ist (gemessen 04.09.2026: nach einem
                    # `sleep 15` im Hintergrund kam 14 s nach dem ersten
                    # result ein zweites, mit der Nachlieferung). Vorher wurde
                    # stdin hier immer geschlossen — und mit dem Prozess starb
                    # jede Hintergrundaufgabe, ohne dass jemand es merkte:
                    # "du kannst mich nachtraeglich nicht mehr anschreiben".
                    #
                    # Schreibt Kevin in dieser Zeit, geht seine Nachricht per
                    # /api/inject in DIESEN Prozess statt per --resume in einen
                    # zweiten auf derselben Sitzung.
                    run.nachlauf = True
                    run.emit({"type": "nachlauf", "tasks": list(run.hintergrund.values())})
                    run.emit({"type": "done", "session_id": run.session_id})
                    asyncio.get_running_loop().call_later(
                        max(60, NACHLAUF_MAX - (time.time() - run.started)),
                        _nachlauf_beenden, run)
                else:
                    # Turn fertig -> stdin schließen, claude beendet sich sauber.
                    # (Mid-Turn-Injections sind zu diesem Zeitpunkt schon in den
                    # Turn eingeflossen; spätere Nachrichten laufen über
                    # --resume weiter.)
                    if run.nachlauf:
                        run.emit({"type": "nachlauf_ende"})
                    run.nachlauf = False
                    run.stdin_closed = True
                    run.emit({"type": "done", "session_id": run.session_id})
                    try:
                        proc.stdin.close()
                    except Exception:
                        pass
        await proc.wait()
        try:
            await asyncio.wait_for(stderr_task, timeout=5)
        except Exception:
            stderr_task.cancel()
        if proc.returncode and not run.done and not got_error:
            err = b"".join(stderr_chunks).decode("utf-8", "replace").strip()
            print(f"[run] claude exit={proc.returncode}: {err[:500]}", flush=True)
            run.emit({"type": "error",
                      "message": friendly_claude_error(err[:1500] or f"claude beendet mit Code {proc.returncode}")})
    except asyncio.CancelledError:
        # Stop-Button -> Prozess hart beenden
        print("[run] gestoppt", flush=True)
        run.stopped = True
        try:
            if run.proc:
                run.proc.kill()
        except Exception:
            pass
        run.emit({"type": "error", "message": "⏹ Gestoppt."})
        raise
    except Exception as e:
        print(f"[run] fehler: {type(e).__name__}: {e}", flush=True)
        run.emit({"type": "error", "message": f"Server-Fehler: {e}"})
    finally:
        run.stdin_closed = True
        run.finish()
        if not getattr(run, "stopped", False):
            maybe_notify(run)


# So lange darf ein Prozess nach seinem Zug hoechstens auf Hintergrundaufgaben
# warten. Ein `tail -f` im Hintergrund wuerde ihn sonst fuer immer festhalten.
NACHLAUF_MAX = 1800


def _nachlauf_beenden(run):
    """Wecker: der Nachlauf ist abgelaufen, der Prozess soll gehen."""
    if run.done or run.stdin_closed or not run.nachlauf:
        return
    print(f"[run] Nachlauf nach {NACHLAUF_MAX} s beendet, "
          f"{len(run.hintergrund)} Hintergrundaufgabe(n) offen", flush=True)
    run.nachlauf = False
    run.stdin_closed = True
    run.emit({"type": "nachlauf_ende"})
    try:
        run.proc.stdin.close()
    except Exception:
        pass


MODEL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9./,:_-]{0,63}$")


def start_run(prompt, work_dir, mode, model="", session_id=None):
    """Gemeinsamer Unterbau für Chat-Läufe und geplante Aufgaben."""
    cmd = [
        claude_bin() or "claude", "-p",
        "--output-format", "stream-json",
        "--input-format", "stream-json",   # Nachricht via stdin -> Inject möglich
        "--verbose",
        "--include-partial-messages",
        "--permission-mode", mode,
    ]
    if model:
        cmd += ["--model", model]
    persona = load_persona()
    if persona:
        cmd += ["--append-system-prompt", persona]
    if session_id:
        cmd += ["--resume", session_id]

    gc_runs()
    run_id = uuid.uuid4().hex
    run = Run(run_id, work_dir, session_id, model, initial_prompt=prompt)
    RUNS[run_id] = run
    run.task = asyncio.create_task(run_claude(run, cmd))
    return run


# ---------- Verlaufs-Übernahme zwischen den Maschinen ----------
def claude_history_msgs(sid: str, max_n=30, max_chars=40000):
    """Verlauf einer Claude-Session als Chat-Messages — damit ein Wechsel zu
    einem externen Modell das Gespräch nahtlos fortsetzt."""
    if not SID_RE.match(sid or ""):
        return []
    f = next(iter(PROJECTS_DIR.glob(f"*/{sid}.jsonl")), None)
    if f is None:
        return []
    try:
        msgs = _parse_transcript_lines(f.read_bytes())
    except Exception:
        return []
    out, total = [], 0
    for m in reversed(msgs):
        total += len(m["text"])
        if out and (len(out) >= max_n or total > max_chars):
            break
        out.append({"role": "user" if m["role"] == "user" else "assistant",
                    "content": m["text"]})
    return list(reversed(out))


# ---------- Läufe mit Hermes (Werkzeuge für fremde Modelle) ----------
async def run_hermes(run, sess, prompt, allow_writes: bool):
    """Hintergrund-Task für Hermes-Läufe.

    Spricht dieselbe Ereignis-Sprache wie run_claude — das Frontend merkt
    keinen Unterschied zwischen den Maschinen dahinter.
    """
    run.hermes = sess
    t0 = time.time()
    is_bonsai = llmmod.split_model(run.model)[0] == "bonsai"
    try:
        if is_bonsai:
            # Der Server liegt erst im VRAM, wenn jemand ihn braucht — jetzt.
            # Das Laden dauert Sekunden; ohne Hinweis sähe es nach Hängen aus.
            if not bonsaimod.running():
                run.emit({"type": "text", "text": "_⏳ Bonsai wird in den VRAM geladen …_\n\n"})
            err = await asyncio.to_thread(bonsaimod.ensure_running)
            if err:
                raise hermesmod.AcpError(err)
        result = await sess.run(prompt, run.emit, allow_writes=allow_writes,
                                images=run.images)
        # Ohne "done" bleibt die Oberfläche im Laufzustand und merkt sich die
        # Sitzung nicht — die naechste Nachricht begaenne dann von vorn.
        run.session_id = "hermes-" + sess.session_id
        # EIN Stats-Event in den Feldnamen, die das Frontend kennt (wie bei
        # run_claude): duration_ms, out, ctx, model.
        usage = (result or {}).get("usage") or {}
        run.emit({"type": "stats",
                  "duration_ms": int((time.time() - t0) * 1000),
                  "out": usage.get("outputTokens") or 0,
                  "ctx": (usage.get("inputTokens") or 0)
                         + (usage.get("cachedReadTokens") or 0),
                  "model": run.model})
        run.emit({"type": "done", "session_id": run.session_id})
    except asyncio.CancelledError:
        print("[hermes] gestoppt", flush=True)
        run.stopped = True
        sess.cancel()          # dem Agenten sagen, dass Schluss ist
        await asyncio.sleep(0.4)   # kurz Zeit für einen sauberen Abgang
        sess.kill()
        run.emit({"type": "error", "message": "⏹ Gestoppt."})
        raise
    except hermesmod.AcpError as e:
        run.emit({"type": "error", "message": f"⚠ Hermes: {e}"})
    except Exception as e:
        print(f"[hermes] fehler: {type(e).__name__}: {e}", flush=True)
        run.emit({"type": "error", "message": f"Server-Fehler: {type(e).__name__}: {e}"})
    finally:
        if is_bonsai:
            bonsaimod.touch()   # Leerlauf zählt ab Ende des Laufs, nicht ab Start
        sess.kill()
        run.stdin_closed = True
        run.finish()
        if not getattr(run, "stopped", False):
            maybe_notify(run)


def carry_over_block(session_id: str) -> str:
    """Verlauf einer Sitzung als Textblock — für den Wechsel der Maschine.

    Claude Code und Hermes führen ihre Sitzungen in getrennten Ablagen; eine
    laufende Unterhaltung lässt sich nicht von der einen in die andere
    übergeben. Statt sie stillschweigend zu verlieren, wird der bisherige
    Verlauf als Kontext in die neue Sitzung gegeben. Das ist keine echte
    Fortsetzung — Werkzeug-Zustand und gelesene Dateien bleiben zurück — aber
    ehrlicher als ein Assistent, der plötzlich nichts mehr weiß.
    """
    sid = session_id or ""
    msgs, herkunft = [], ""
    if sid.startswith("hermes-"):
        msgs = hermesmod.session_messages(sid[len("hermes-"):])
        herkunft = "einem anderen Modell über Hermes"
    elif sid.startswith("llm-"):
        return llmmod.history_block(sid)
    elif sid:
        msgs = claude_history_msgs(sid)
        herkunft = "Claude Code"
    if not msgs:
        return ""
    lines = [cfg.L(f"[Kontext: Dieses Gespräch lief bisher mit {herkunft}; "
                   f"{cfg.user_name()} wechselt jetzt das Modell. Bisheriger Verlauf:]",
                   f"[Context: this conversation has so far run on {herkunft}; "
                   f"{cfg.user_name()} is now switching models. History so far:]")]
    total = 0
    for m in msgs[-30:]:
        t = str(m.get("text") or m.get("content") or "")
        total += len(t)
        if total > 40000:
            break
        who = cfg.user_name() if m.get("role") == "user" else cfg.L("Assistent", "Assistant")
        lines.append(f"{who}: {t}")
    lines.append(cfg.L("[Ende des Verlaufs — antworte jetzt auf die folgende neue Nachricht.]",
                       "[End of history — now reply to the following new message.]"))
    return "\n\n".join(lines)


def start_hermes_run(text, images, pid, model, work_dir, mode, session_id=None):
    """Lauf über Hermes starten.

    session_id mit Präfix "hermes-" führt die Sitzung fort; alles andere
    (Claude- oder Chat-Sitzung) beginnt eine neue — die Verläufe liegen in
    verschiedenen Ablagen und lassen sich nicht ineinander überführen.
    """
    prompt = (text or "").strip()
    # Bilder gehen als ACP-Blöcke mit (hermes._image_blocks); PDFs kennt ACP
    # nicht, die bekommt das Modell wie bei claude als Hinweis + Textauszug.
    pdfs = [p for p in (images or []) if is_pdf(p)]
    if pdfs:
        prompt = f"{prompt}\n\n{pdf_note(pdfs)}".strip()
    prev = session_id if (session_id or "").startswith("hermes-") else ""
    carried = False
    if session_id and not prev:
        # Maschinenwechsel: neue Hermes-Sitzung, aber mit dem bisherigen
        # Verlauf als Kontext — sonst stünde der Assistent ohne Gedächtnis da.
        block = carry_over_block(session_id)
        if block:
            prompt = block + "\n\n" + prompt
            carried = True
    sess = hermesmod.AcpSession(work_dir, model=f"{pid}:{model}",
                                session_id=prev[len("hermes-"):] if prev else "")
    gc_runs()
    run_id = uuid.uuid4().hex
    run = Run(run_id, work_dir, prev or None, f"{pid}:{model}", initial_prompt=prompt)
    run.images = images or []
    run.stdin_closed = True   # kein Mid-Turn-Inject: ACP kennt das nicht
    RUNS[run_id] = run
    if carried:
        # Sichtbar machen: der Nutzer soll wissen, dass eine neue Sitzung
        # begonnen hat und was davon mitgenommen wurde.
        run.emit({"type": "text", "text":
                  "_↪ Modellwechsel: neue Sitzung, bisheriger Verlauf als "
                  "Kontext übernommen._\n\n"})
    run.task = asyncio.create_task(run_hermes(run, sess, prompt, mode != "plan"))
    return run


@app.post("/api/chat")
async def chat(req: Request):
    """Startet einen entkoppelten Lauf und gibt sofort die run_id zurück."""
    body = await req.json()
    text = (body.get("message") or "").strip()
    session_id = body.get("session_id")
    images = body.get("images") or []  # Server-Pfade der Anhänge (Bilder und PDFs)
    if not text and not images:
        return JSONResponse({"error": "leere Nachricht"}, status_code=400)
    req_cwd = body.get("cwd")
    work_dir = req_cwd if (isinstance(req_cwd, str) and os.path.isdir(req_cwd)) else DEFAULT_CWD
    req_mode = body.get("mode")
    mode = req_mode if req_mode in ALLOWED_MODES else "bypassPermissions"
    req_model = (body.get("model") or "").strip()
    model = req_model if MODEL_RE.match(req_model) else ""

    # Fremdes Modell ("anbieter:modell") -> Hermes statt claude-CLI.
    # Reiner Chat ohne Werkzeuge gibt es nicht mehr: die Oberfläche zeigt nur
    # noch werkzeugfähige Modelle, und ein Modell, das nichts tun kann, wäre
    # in einer Werkzeug-Oberfläche eine Falle.
    pid, ext_model = llmmod.split_model(model)
    if pid:
        if not hermesmod.hermes_bin():
            return JSONResponse(
                {"error": "Für fremde Modelle wird Hermes gebraucht — es ist "
                          "nicht installiert. Unter ⚙ Einstellungen → "
                          "„Modelle & Anbieter“ lässt es sich einrichten."},
                status_code=400)
        run = start_hermes_run(text, images, pid, ext_model, work_dir, mode, session_id)
        return {"run_id": run.id, "session_id": run.session_id}

    prompt = build_prompt(text, images)
    if session_id and session_id.startswith("hermes-"):
        block = carry_over_block(session_id)
        if block:
            prompt = block + "\n\n" + prompt
        session_id = None      # Claude kann eine Hermes-Sitzung nicht fortsetzen
    if session_id and session_id.startswith("llm-"):
        # Wechsel extern -> Claude: Verlauf als Kontext mitgeben, neue Claude-Session
        hist = llmmod.history_block(session_id)
        if hist:
            prompt = hist + "\n\n" + prompt
        session_id = None

    run = start_run(prompt, work_dir, mode, model, session_id)
    return {"run_id": run.id, "session_id": session_id}


@app.post("/api/inject/{run_id}")
async def inject(run_id: str, req: Request):
    """Schiebt dem LAUFENDEN claude-Prozess eine weitere Nachricht nach (kein
    Warten auf das Ende, kein --resume) — wie Weitertippen im Terminal."""
    run = RUNS.get(run_id)
    if not run or run.done or run.stdin_closed or not run.proc:
        return JSONResponse({"error": "Lauf nimmt nichts mehr an"}, status_code=409)
    body = await req.json()
    text = (body.get("message") or "").strip()
    images = body.get("images") or []
    urls = body.get("urls") or []
    if not text and not images:
        return JSONResponse({"error": "leere Nachricht"}, status_code=400)
    run.emit({"type": "user_inject", "text": text, "urls": urls})
    if run.nachlauf:
        # Kevin schreibt, waehrend der Prozess nur noch auf den Hintergrund
        # wartet: ein neuer Zug in derselben Sitzung. Kein "neuer_zug" hier —
        # das user_inject-Ereignis oben oeffnet in der Oberflaeche schon die
        # neue Sprechblase.
        run.nachlauf = False
    try:
        run.proc.stdin.write(stdin_message(build_prompt(text, images)))
        await run.proc.stdin.drain()
    except Exception as e:
        return JSONResponse({"error": f"Einspeisen fehlgeschlagen: {e}"}, status_code=500)
    return {"ok": True}


@app.get("/api/stream/{run_id}")
async def stream(run_id: str):
    """Hängt sich an einen Lauf: erst Backlog (Replay), dann live. Reconnect-fähig."""
    run = RUNS.get(run_id)
    if not run:
        return JSONResponse({"error": "unknown run"}, status_code=404)

    async def gen():
        q = asyncio.Queue()
        run.subs.add(q)
        idx = len(run.events)        # atomar (kein await bis hier) -> keine Lücken/Dupes
        already = run.done
        try:
            for ev in run.events[:idx]:
                yield sse(ev)
            if already:
                return                # Backlog enthält bereits done/error
            while True:
                try:
                    ev = await asyncio.wait_for(q.get(), timeout=8)
                except asyncio.TimeoutError:
                    yield ": keep-alive\n\n"
                    continue
                if ev is None:
                    break             # Lauf fertig
                yield sse(ev)
        finally:
            run.subs.discard(q)

    return StreamingResponse(gen(), media_type="text/event-stream", headers=SSE_HEADERS)


@app.get("/api/runs")
def list_runs():
    """Aktive (noch laufende) Läufe — damit das Frontend nach Reload wieder andocken kann."""
    gc_runs()
    return [{"run_id": r.id, "session_id": r.session_id, "cwd": r.cwd}
            for r in RUNS.values() if not r.done]


@app.post("/api/stop/{run_id}")
def stop_run(run_id: str):
    """Stop-Button: bricht den Lauf wirklich ab (killt den claude-Prozess)."""
    run = RUNS.get(run_id)
    if not run:
        return JSONResponse({"error": "unknown run"}, status_code=404)
    if run.task and not run.done:
        run.task.cancel()
    return {"stopped": True}


# ---------- Geplante Aufgaben (Kalender-Termine mit Cody-Prompt) ----------
# Läuft nur, wenn Telegram eingerichtet ist — und nur, solange CONSTRUCT läuft.
# Zur Termin-Zeit startet ein normaler Run; das Ergebnis kommt per Telegram.
TASK_STATE = BASE_DIR / "tasks_state.json"


def _task_state() -> dict:
    try:
        d = json.loads(TASK_STATE.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def _mark_task_done(key: str):
    d = _task_state()
    d[key] = int(time.time())
    cutoff = time.time() - 60 * 86400   # alte Einträge nach 60 Tagen vergessen
    d = {k: v for k, v in d.items() if v > cutoff}
    tmp = TASK_STATE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(d, indent=2), encoding="utf-8")
    tmp.replace(TASK_STATE)


def _due_tasks():
    today = time.strftime("%Y-%m-%d")
    hm = time.strftime("%H:%M")
    state = _task_state()
    for e in cal.load_events():
        prompt = (e.get("prompt") or "").strip()
        if not prompt:
            continue
        d = e.get("date") or ""
        occurs = (d[5:] == today[5:]) if e.get("repeat") == "yearly" else (d == today)
        if not occurs or (e.get("time") or "09:00") > hm:
            continue
        key = f"{e.get('id')}:{today}"
        if key not in state:
            yield e, key


async def scheduler_loop():
    # Läuft immer mit, arbeitet aber nur, solange Telegram eingerichtet ist:
    # das Ergebnis einer geplanten Aufgabe kommt per Telegram an.
    while True:
        try:
            if not tgmod.enabled():
                await asyncio.sleep(60)
                continue
            for ev, key in list(_due_tasks()):
                _mark_task_done(key)   # SOFORT markieren -> nie doppelt starten
                title = ev.get("title") or "(ohne Titel)"
                print(f"[sched] starte Aufgabe: {title}", flush=True)
                who = cfg.user_name()
                prompt = cfg.L(
                    f"[Geplante Aufgabe aus dem Kalender — Termin: „{title}“, "
                    f"{ev.get('date')} {ev.get('time') or ''}. {who} sieht deine Antwort "
                    f"als Telegram-Nachricht. Fasse dich entsprechend.]",
                    f"[Scheduled task from the calendar — event: “{title}”, "
                    f"{ev.get('date')} {ev.get('time') or ''}. {who} will read your reply "
                    f"as a Telegram message. Keep it short accordingly.]",
                ) + f"\n\n{ev['prompt']}"
                tconf = tgmod.load_conf()
                run = start_run(prompt, DEFAULT_CWD, tconf["mode"], tconf["model"])
                run.notify_always = True
                run.task_title = title
        except Exception as e:
            print(f"[sched] fehler: {type(e).__name__}: {e}", flush=True)
        await asyncio.sleep(60)


@app.on_event("shutdown")
async def _stop_bonsai():
    bonsaimod.stop()   # sonst hielte der Server die GPU, obwohl CONSTRUCT weg ist
    tgmod.stop()


@app.on_event("startup")
async def _start_scheduler():
    asyncio.create_task(scheduler_loop())
    tgmod.init(claude_bin=lambda: claude_bin() or "claude", claude_env=claude_env,
               persona=load_persona, workspace=WORKSPACE)
    tgmod.restart()
    # Früher installiertes Ollama nach Container-Neustart wieder hochfahren
    asyncio.get_running_loop().run_in_executor(None, llmmod.ollama_autostart)
    # Claude Code / Hermes aktuell halten. Der Aufruf kehrt sofort zurück —
    # gearbeitet wird in einem eigenen Thread, der Start wartet nie aufs Netz.
    try:
        updmod.boot_check()
    except Exception as e:
        print(f"[updates] Start-Prüfung fehlgeschlagen: {type(e).__name__}: {e}", flush=True)


if __name__ == "__main__":
    import uvicorn
    host = os.environ.get("MATRIX_HOST", "127.0.0.1")
    port = int(os.environ.get("MATRIX_PORT", "8765"))
    uvicorn.run(app, host=host, port=port)
