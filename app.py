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
import socket
import subprocess
import threading
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

# Hostinger routet IPv6 ins Leere -> urllib hängt ~20s pro Request (siehe
# telegram_bot.py). getaddrinfo auf IPv4 beschränken; lokal schadet das nicht.
_orig_getaddrinfo = socket.getaddrinfo
def _getaddrinfo_ipv4(host, *args, **kwargs):
    res = _orig_getaddrinfo(host, *args, **kwargs)
    v4 = [r for r in res if r[0] == socket.AF_INET]
    return v4 or res
socket.getaddrinfo = _getaddrinfo_ipv4

from fastapi import FastAPI, UploadFile, File, Request, Response
from fastapi.responses import StreamingResponse, HTMLResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles

import config as cfg  # Ausbaustufe (voll/lite) + Namen — siehe config.py
import cal  # Kalender: gemeinsame events.json (Web-UI + cal.py-CLI + Telegram)
import llm as llmmod  # Externe Modelle: ChatGPT, Gemini, DeepSeek, Ollama (llm.py)
# E-Mail gibt es nur in der Vollversion. Der Import steht unter der Abfrage,
# damit eine abgespeckte Installation die Datei schlicht weglassen kann.
# Benutzt wird sie ausschließlich in Routen, die LITE_BLOCKED sperrt.
if cfg.LITE:
    mailmod = None
else:
    import mail as mailmod  # E-Mail: IMAP/SMTP für GMX, Gmail, Outlook (mail.py)

BASE_DIR = Path(__file__).parent
STATIC_DIR = BASE_DIR / "static"
UPLOAD_DIR = BASE_DIR / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)
PROJECTS_DIR = Path.home() / ".claude" / "projects"
def _find_workspace() -> str:
    """Ordner mit Kevins Projekten — Grundlage der Ordner-Auswahl im Chat.

    Im Container ist das /workspace, nativ auf dem Desktop z.B. ~/projects.
    CODY_WORKSPACE sticht immer, damit man es pro Rechner setzen kann.
    """
    env = os.environ.get("CODY_WORKSPACE", "").strip()
    if env and os.path.isdir(env):
        return env
    if os.path.isdir("/workspace"):
        return "/workspace"
    for cand in (Path.home() / "projects", Path.home() / "Projekte"):
        if cand.is_dir():
            return str(cand)
    return str(Path.home())


WORKSPACE = _find_workspace()
DEFAULT_CWD = WORKSPACE
VERSION = "3.8.0 · opus-5" + (" · lite" if cfg.LITE else "")

# Passwortschutz: greift NUR, wenn MATRIX_PASS gesetzt ist (z.B. auf Hostinger).
# Lokal ohne MATRIX_PASS bleibt die Oberfläche offen (kein Login).
AUTH_USER = os.environ.get("MATRIX_USER", "Cody")
AUTH_PASS = os.environ.get("MATRIX_PASS", "")


def load_persona() -> str:
    """SOUL.md + USER.md als System-Prompt-Zusatz (bei jeder Anfrage frisch gelesen)."""
    parts = []
    for fn in ("SOUL.md", "USER.md"):
        p = BASE_DIR / fn
        if p.is_file():
            try:
                txt = p.read_text(encoding="utf-8", errors="replace").strip()
                if txt:
                    parts.append(txt)
            except Exception:
                pass
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


# Lite lässt genau die vier Bereiche weg, die auf Kevin zugeschnitten sind.
# Alles Übrige — Chat, Kalender, Ordnerwahl, Modell- und Mode-Auswahl, die
# Claude-Anmeldung — bleibt: wer die Kopie bekommt, soll sie grundsätzlich
# genauso benutzen können, inklusive Claude Code, falls er es später
# installiert. Die Sperre sitzt in der Middleware und nicht in jedem Handler,
# damit eine später ergänzte Route unter denselben Präfixen nicht versehentlich
# offen bleibt. Das Frontend blendet dieselben Bereiche aus; hier ist der
# Riegel, dort die Kosmetik.
LITE_BLOCKED = ("/api/skill", "/api/mcp", "/api/mail")


@app.middleware("http")
async def basic_auth(request: Request, call_next):
    """HTTP-Basic-Auth vor ALLEM — aber nur wenn ein Passwort konfiguriert ist."""
    if cfg.LITE and request.url.path.startswith(LITE_BLOCKED):
        return JSONResponse({"error": "in dieser Version nicht verfügbar"}, status_code=404)
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


def _cred_info() -> dict:
    """Kurzlebiger Interactive-Login aus ~/.claude/.credentials.json (falls da)."""
    try:
        c = json.loads(CRED_FILE.read_text(encoding="utf-8")).get("claudeAiOauth") or {}
        exp = c.get("expiresAt") or 0
        return {
            "exists": bool(c.get("accessToken")),
            "expires_at": exp,
            "expired": exp / 1000 < time.time(),
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
        "env_token": envtok,         # z.B. .cody-env auf Hostinger
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
        m = re.search(r"sk-ant-oat[0-9A-Za-z_-]{20,}", self.text())
        return m.group(0) if m else None

    def send_code(self, code: str):
        # "\r" (Enter-Taste), nicht "\n": die Code-Maske neuerer CLIs (>=2.1.x)
        # ignoriert Ctrl-J und wartet sonst ewig -> "Login fehlgeschlagen"
        os.write(self.master, (code.strip() + "\r").encode())

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
        c = json.loads(CRED_FILE.read_text(encoding="utf-8")).get("claudeAiOauth") or {}
        if c.get("accessToken"):
            if (c.get("expiresAt") or 0) / 1000 > time.time() + 60:
                return c["accessToken"]
            c = _refresh_credentials()          # abgelaufen -> selbst erneuern
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
    """Projektordner unter /workspace (für die Ordner-Auswahl im Chat)."""
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
    # os.sep anhängen -> /workspace2 zählt nicht als "unter /workspace"
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


# ---------- Externe KI-Anbieter (ChatGPT, Gemini, DeepSeek, Ollama, custom) ----------
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
        "lite": cfg.LITE,
        "assistant": cfg.ASSISTANT_NAME,
        "claude": bool(claude_bin()),
    }


# ---------- Einstellungen ----------
# Was der Nutzer selbst zusammenstellt: welche Kacheln er sieht, wie der
# Hintergrund aussieht. Serverseitig und nicht im Browser, weil die App
# vom Desktop-Fenster UND vom Browser aus bedient wird — localStorage wäre
# pro Browser eine andere Wahrheit. Die Datei gehört zur Installation und
# steht darum in .gitignore.
SETTINGS_FILE = BASE_DIR / "settings.json"

# Kacheln, die sich abschalten lassen. "sessions" (der Chat) fehlt hier mit
# Absicht: eine Oberfläche ohne ihren Hauptzweck wäre nur eine Sackgasse,
# aus der man sich nicht mehr herausklicken kann.
OPTIONAL_TILES = ("skills", "kalender", "mail", "mcp")
BG_MODES = ("matrix", "image", "plain")
# Farbwelten. Die Namen sind Schlüssel für data-theme im Frontend; die Farben
# selbst stehen im CSS, nicht hier — der Server soll nicht mitentscheiden,
# wie etwas aussieht, nur was gewählt ist.
THEMES = ("matrix", "bernstein", "eis", "space", "asche", "blut")

DEFAULT_SETTINGS = {
    # Vorgabe bewusst zurückhaltend: wer die App frisch klont, bekommt Chat
    # und Kalender. Alles Weitere schaltet er sich selbst dazu und weiß dann
    # auch, was es tut.
    "theme": "matrix",
    "tiles": {"skills": False, "kalender": True, "mail": False, "mcp": False},
    # dim = Abdunklung des Hintergrundbildes in Prozent. Grün auf Foto ist
    # ohne kräftiges Abdunkeln kaum lesbar, darum ein hoher Startwert.
    "background": {"mode": "matrix", "image": "", "dim": 60},
}


def load_settings() -> dict:
    out = {"theme": DEFAULT_SETTINGS["theme"],
           "tiles": dict(DEFAULT_SETTINGS["tiles"]),
           "background": dict(DEFAULT_SETTINGS["background"])}
    try:
        raw = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return out
    if not isinstance(raw, dict):
        return out
    if raw.get("theme") in THEMES:
        out["theme"] = raw["theme"]
    for k, v in (raw.get("tiles") or {}).items():
        if k in OPTIONAL_TILES:
            out["tiles"][k] = bool(v)
    bg = raw.get("background") or {}
    if bg.get("mode") in BG_MODES:
        out["background"]["mode"] = bg["mode"]
    img = str(bg.get("image") or "").strip()
    # Nur eigene Uploads zulassen: ein freier Pfad hier wäre eine Einladung,
    # sich per Einstellung beliebige Dateien in die Seite zu laden.
    if img.startswith("/uploads/") and "//" not in img[1:] and ".." not in img:
        out["background"]["image"] = img
    try:
        dim = int(bg.get("dim"))
        out["background"]["dim"] = max(0, min(100, dim))
    except Exception:
        pass
    return out


def save_settings(d: dict) -> dict:
    tmp = SETTINGS_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(SETTINGS_FILE)
    return d


@app.get("/api/settings")
def settings_get():
    return load_settings()


@app.post("/api/settings")
async def settings_set(req: Request):
    """Teil-Update: was nicht mitkommt, bleibt wie es war."""
    body = await req.json()
    cur = load_settings()
    if body.get("theme") in THEMES:
        cur["theme"] = body["theme"]
    for k, v in (body.get("tiles") or {}).items():
        if k in OPTIONAL_TILES:
            cur["tiles"][k] = bool(v)
    bg = body.get("background") or {}
    if bg.get("mode") in BG_MODES:
        cur["background"]["mode"] = bg["mode"]
    if "image" in bg:
        img = str(bg.get("image") or "").strip()
        cur["background"]["image"] = img if (img.startswith("/uploads/")
                                             and ".." not in img) else ""
    if "dim" in bg:
        try:
            cur["background"]["dim"] = max(0, min(100, int(bg["dim"])))
        except Exception:
            pass
    return save_settings(cur)


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
    if len(data) > MAX_UPLOAD:
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
        "lite": cfg.LITE,
        "user": cfg.USER_NAME,
        "assistant": cfg.ASSISTANT_NAME,
        "claude": bool(claude_bin()),
        "web_login": WEB_LOGIN_OK,
        "settings": load_settings(),
    }, ensure_ascii=False) + ";"
    # Ersatz als Funktion, nicht als Zeichenkette: in einem Ersatz-String wären
    # Backslashes und \g Steuerzeichen, und genau die stecken in JSON.
    html = re.sub(r"window\.CONSTRUCT\s*=\s*\{.*?\};", lambda _m: payload,
                  html, count=1, flags=re.DOTALL)
    # Kein Browser-Cache -> immer aktueller Stand, kein Hard-Refresh nötig
    return HTMLResponse(html, headers={
        "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
        "Pragma": "no-cache",
    })


ALLOWED_IMG_EXT = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".svg", ".heic"}
MAX_UPLOAD = 25 * 1024 * 1024


@app.post("/api/upload")
async def upload(file: UploadFile = File(...)):
    ext = os.path.splitext(file.filename or "")[1].lower() or ".png"
    if ext not in ALLOWED_IMG_EXT:
        return JSONResponse({"error": f"Nur Bilder erlaubt (nicht {ext})"}, status_code=400)
    data = await file.read()
    if len(data) > MAX_UPLOAD:
        return JSONResponse({"error": "Bild zu groß (max. 25 MB)"}, status_code=400)
    name = f"{uuid.uuid4().hex}{ext}"
    dest = UPLOAD_DIR / name
    dest.write_bytes(data)
    return {"path": str(dest), "url": f"/uploads/{name}", "name": file.filename or name}


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


@app.get("/api/sessions")
def sessions():
    """Listet alle Claude-Code-Sessions (eine .jsonl-Datei = eine Session)
    plus die Sessions externer Modelle (llm_sessions/)."""
    out = []
    meta = load_meta()
    archived = set(meta.get("archived", []))
    names = meta.get("names", {})
    for s in llmmod.list_sessions():
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
            # Nur die ersten paar Zeilen lesen reicht für Titel + cwd (Performance!)
            with f.open(encoding="utf-8", errors="replace") as fh:
                for i, line in enumerate(fh):
                    if i > 60 or (title and cwd):
                        break
                    try:
                        ev = json.loads(line)
                    except Exception:
                        continue
                    if cwd is None and isinstance(ev.get("cwd"), str):
                        cwd = ev["cwd"]
                    if title is None and ev.get("type") == "user":
                        txt = extract_text(ev.get("message", {}).get("content")).strip()
                        # System-/Befehls-Wrapper überspringen
                        if txt and not txt.startswith("<") and not txt.startswith("Caveat"):
                            title = txt.replace("\n", " ")[:80]
            out.append({
                "id": f.stem,
                "project": f.parent.name,
                "cwd": cwd or "(unbekannt)",
                "title": names.get(f.stem) or title or "(ohne Titel)",
                "renamed": f.stem in names,
                "mtime": stat.st_mtime,
                "size": stat.st_size,
                "archived": f.stem in archived,
            })
        except Exception:
            continue
    out.sort(key=lambda x: x["mtime"], reverse=True)
    return out


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
    """Volle Modell-ID (claude-opus-4-8 …) -> UI-Kurzname (opus/sonnet/haiku/
    fable). Unbekanntes/synthetisches -> "" (= Konto-Standard)."""
    m = (mid or "").lower()
    for name in ("fable", "opus", "sonnet", "haiku"):
        if name in m:
            return name
    return ""


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
        self.last_text = ""              # Text des letzten Turns (für Telegram-Notify)
        self.notify_always = False       # geplante Aufgaben melden sich immer per Telegram
        self.task_title = ""             # Titel der geplanten Aufgabe (für die Meldung)

    def emit(self, ev):
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
TG_TOKEN = os.environ.get("TELEGRAM_TOKEN", "").strip()
TG_CHAT = os.environ.get("CODY_CHAT_ID", "6515451491").strip()
NOTIFY_MIN_SECS = int(os.environ.get("CODY_NOTIFY_MIN_SECS", "90"))


def tg_send(text: str):
    if not TG_TOKEN:
        return
    try:
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
            data=json.dumps({"chat_id": int(TG_CHAT), "text": text[:3900]}).encode(),
            headers={"Content-Type": "application/json"},
        )
        urllib.request.urlopen(req, timeout=15).read()
    except Exception as e:
        print(f"[tg] senden fehlgeschlagen: {type(e).__name__}: {e}", flush=True)


def maybe_notify(run):
    """Nach Lauf-Ende: Telegram-Ping, wenn (a) geplante Aufgabe oder (b) der Lauf
    lange lief UND gerade niemand im Browser zuschaut (run.subs leer)."""
    if not TG_TOKEN:
        return
    dur = time.time() - run.started
    if not run.notify_always and (dur < NOTIFY_MIN_SECS or run.subs):
        return
    mins, secs = divmod(int(dur), 60)
    tail = run.last_text.strip()[-600:]
    head = "🤖 Geplante Aufgabe erledigt" if run.notify_always else "✅ Cody ist fertig"
    msg = f"{head} ({mins} m {secs} s, {os.path.basename(run.cwd or '?')})"
    if run.notify_always and run.task_title:
        msg += f" — {run.task_title}"
    if tail:
        msg += f":\n\n{tail}"
    threading.Thread(target=tg_send, args=(msg,), daemon=True).start()


def stdin_message(prompt: str) -> bytes:
    """Eine User-Nachricht im stream-json-Eingabeformat von claude."""
    return (json.dumps({
        "type": "user",
        "message": {"role": "user", "content": [{"type": "text", "text": prompt}]},
    }, ensure_ascii=False) + "\n").encode()


def build_prompt(text: str, images) -> str:
    """User-Text + Hinweise auf hochgeladene Bilder zu einem Prompt kombinieren."""
    prompt = (text or "").strip()
    if images:
        img_lines = "\n".join(f"[Vom Nutzer hochgeladenes Bild: {p}]" for p in images)
        prompt = (f"{prompt}\n\n{img_lines}\n"
                  "(Bitte sieh dir die Bild-Datei(en) mit dem Read-Tool an.)").strip()
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
            if t == "system" and ev.get("subtype") == "init":
                run.session_id = ev.get("session_id", run.session_id)
                run.emit({"type": "session", "session_id": run.session_id})
            elif t == "stream_event":
                e = ev.get("event", {})
                if e.get("type") == "content_block_delta":
                    d = e.get("delta", {})
                    if d.get("type") == "text_delta":
                        run.last_text += d.get("text", "")
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
                run.emit({
                    "type": "stats",
                    "duration_ms": ev.get("duration_ms"),
                    "out": u.get("output_tokens") or 0,
                    "ctx": ctx,
                    "model": run.model,
                })
                # Turn fertig -> stdin schließen, claude beendet sich sauber.
                # (Mid-Turn-Injections sind zu diesem Zeitpunkt schon in den Turn
                # eingeflossen; spätere Nachrichten laufen über --resume weiter.)
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


# ---------- Läufe mit externen Modellen (ChatGPT, Gemini, DeepSeek, Ollama) ----------
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


async def run_llm(run, sess, prompt):
    """Hintergrund-Task für externe Modelle — spricht dieselbe Event-Sprache wie
    run_claude (text/thinking_marker/stats/done/error), das Frontend merkt also
    keinen Unterschied. Der blockierende HTTP-Stream läuft in einem Thread."""
    loop = asyncio.get_running_loop()
    q = asyncio.Queue()
    state = {"resp": None}
    pid, model = sess["provider"], sess["model"]
    persona = load_persona()
    system = ((persona + "\n\n") if persona else "") + llmmod.no_tools_note(f"{pid}:{model}", bool(claude_bin()))
    messages = ([{"role": "system", "content": system}]
                + llmmod.recent_messages(sess)
                + [{"role": "user", "content": prompt}])

    def worker():
        put = lambda ev: loop.call_soon_threadsafe(q.put_nowait, ev)
        try:
            resp = llmmod.chat_request(pid, model, messages)
            state["resp"] = resp
            for ev in llmmod.iter_stream(resp):
                put(ev)
        except Exception as e:
            put({"type": "error", "message": llmmod.friendly_error(pid, e)})
        finally:
            put(None)

    run.emit({"type": "session", "session_id": sess["id"]})
    llmmod.append_message(sess, "user", prompt)
    t0 = time.time()
    threading.Thread(target=worker, daemon=True).start()
    usage, thinking_sent, got_error = {}, False, False
    try:
        while True:
            ev = await q.get()
            if ev is None:
                break
            et = ev.get("type")
            if et == "text":
                run.last_text += ev["text"]
                run.emit(ev)
            elif et == "reasoning" and not thinking_sent:
                thinking_sent = True
                run.emit({"type": "thinking_marker"})
            elif et == "usage":
                usage = ev
            elif et == "error":
                got_error = True
                run.emit(ev)
        if run.last_text.strip():
            llmmod.append_message(sess, "assistant", run.last_text)
        if not got_error:
            run.emit({"type": "stats", "duration_ms": int((time.time() - t0) * 1000),
                      "out": usage.get("out") or 0, "ctx": usage.get("in") or 0,
                      "model": run.model})
            run.emit({"type": "done", "session_id": sess["id"]})
    except asyncio.CancelledError:
        print("[llm] gestoppt", flush=True)
        run.stopped = True
        try:
            if state["resp"]:
                state["resp"].close()   # bricht den blockierenden Stream im Thread ab
        except Exception:
            pass
        if run.last_text.strip():
            llmmod.append_message(sess, "assistant", run.last_text)
        run.emit({"type": "error", "message": "⏹ Gestoppt."})
        raise
    except Exception as e:
        print(f"[llm] fehler: {type(e).__name__}: {e}", flush=True)
        run.emit({"type": "error", "message": f"Server-Fehler: {e}"})
    finally:
        run.finish()
        if not getattr(run, "stopped", False):
            maybe_notify(run)


def start_llm_run(text, images, pid, model, session_id=None):
    """Lauf mit externem Modell starten. session_id kann eine externe Session
    (weiterführen) ODER eine Claude-Session sein (Verlauf wird übernommen)."""
    sess = None
    if session_id:
        if session_id.startswith("llm-"):
            sess = llmmod.load_session(session_id)
        else:
            seed = claude_history_msgs(session_id)
            if seed:
                sess = llmmod.new_session(pid, model, seed=seed)
    if sess is None:
        sess = llmmod.new_session(pid, model)
    sess["provider"], sess["model"] = pid, model   # Modellwechsel innerhalb der Session
    prompt = (text or "").strip()
    if images:
        prompt += ("\n\n[Hinweis: Kevin hat Bild(er) angehängt — als externes "
                   "Chat-Modell kannst du sie NICHT sehen. Sag ihm kurz, dass er "
                   "dafür ein Claude-Modell wählen soll.]")
    gc_runs()
    run_id = uuid.uuid4().hex
    run = Run(run_id, DEFAULT_CWD, sess["id"], f"{pid}:{model}", initial_prompt=prompt)
    run.stdin_closed = True   # kein Mid-Turn-Inject bei externen Läufen
    RUNS[run_id] = run
    run.task = asyncio.create_task(run_llm(run, sess, prompt))
    return run


@app.post("/api/chat")
async def chat(req: Request):
    """Startet einen entkoppelten Lauf und gibt sofort die run_id zurück."""
    body = await req.json()
    text = (body.get("message") or "").strip()
    session_id = body.get("session_id")
    images = body.get("images") or []  # Liste von Server-Pfaden
    if not text and not images:
        return JSONResponse({"error": "leere Nachricht"}, status_code=400)
    req_cwd = body.get("cwd")
    work_dir = req_cwd if (isinstance(req_cwd, str) and os.path.isdir(req_cwd)) else DEFAULT_CWD
    req_mode = body.get("mode")
    mode = req_mode if req_mode in ALLOWED_MODES else "bypassPermissions"
    req_model = (body.get("model") or "").strip()
    model = req_model if MODEL_RE.match(req_model) else ""

    # Externes Modell ("anbieter:modell") -> eigener Runner statt claude-CLI
    pid, ext_model = llmmod.split_model(model)
    if pid:
        run = start_llm_run(text, images, pid, ext_model, session_id)
        return {"run_id": run.id, "session_id": run.session_id}

    prompt = build_prompt(text, images)
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
# Läuft nur, wenn Telegram konfiguriert ist (= auf Hostinger, der 24/7 an ist).
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
    print("[sched] Aufgaben-Scheduler aktiv (Telegram konfiguriert)", flush=True)
    while True:
        try:
            for ev, key in list(_due_tasks()):
                _mark_task_done(key)   # SOFORT markieren -> nie doppelt starten
                title = ev.get("title") or "(ohne Titel)"
                print(f"[sched] starte Aufgabe: {title}", flush=True)
                prompt = (
                    f"[Geplante Aufgabe aus Kevins Kalender — Termin: „{title}“, "
                    f"{ev.get('date')} {ev.get('time') or ''}. Kevin sieht deine Antwort "
                    f"als Telegram-Nachricht. Fasse dich entsprechend.]\n\n{ev['prompt']}"
                )
                run = start_run(prompt, DEFAULT_CWD, "bypassPermissions")
                run.notify_always = True
                run.task_title = title
        except Exception as e:
            print(f"[sched] fehler: {type(e).__name__}: {e}", flush=True)
        await asyncio.sleep(60)


@app.on_event("startup")
async def _start_scheduler():
    if TG_TOKEN:
        asyncio.create_task(scheduler_loop())
    # Früher installiertes Ollama nach Container-Neustart wieder hochfahren
    asyncio.get_running_loop().run_in_executor(None, llmmod.ollama_autostart)


if __name__ == "__main__":
    import uvicorn
    host = os.environ.get("MATRIX_HOST", "127.0.0.1")
    port = int(os.environ.get("MATRIX_PORT", "8765"))
    uvicorn.run(app, host=host, port=port)
