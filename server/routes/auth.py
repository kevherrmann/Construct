"""API: Claude-Anmeldung (Status, Web-Login) und Nutzungs-Limits."""
import asyncio
import json
import os
import re
import subprocess
import sys
import threading
import time
import urllib.request

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from server.core import CRED_FILE, LIMIT_HIT, TOKEN_FILE, WEB_LOGIN_OK, claude_bin, load_web_token

router = APIRouter()


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


@router.get("/api/auth/status")
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


@router.post("/api/auth/login")
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


@router.post("/api/auth/code")
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


@router.get("/api/usage")
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
