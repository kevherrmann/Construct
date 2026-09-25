"""API: Version, Werkzeug-Installation und -Updates, Einstellungen,
Persona, Vorlesen, Telegram.
"""
import asyncio
import os
import re
import shutil
import subprocess
import threading
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import APIRouter, Request, Response, WebSocket
from fastapi.responses import JSONResponse

from server import config as cfg
from server import hermes as hermesmod
from server import telegram_bot as tgmod
from server import stt as sttmod
from server import tts as ttsmod
from server import updates as updmod

from server.core import (BASE_DIR, CODE_STAMP, VERSION, WEB_LOGIN_OK, WORKSPACE, auth_ok,
                         claude_bin)
from server.runs import RUNS

router = APIRouter()


@router.get("/api/version")
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
@router.get("/api/engines")
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


@router.post("/api/engines/hermes/install")
async def hermes_install():
    return hermesmod.install_start()


@router.get("/api/engines/hermes/install")
def hermes_install_state():
    return hermesmod.install_state()


@router.post("/api/engines/claude/install")
async def claude_install():
    return claude_install_start()


# ---------- Werkzeuge aktuell halten ----------
# Läuft beim Start von allein (siehe _start_scheduler) und lässt sich hier von
# Hand anstoßen. Die Arbeit selbst steckt in updates.py.
@router.get("/api/updates")
def updates_state():
    return updmod.state()


@router.post("/api/updates/run")
async def updates_run():
    # Während ein Chat läuft nicht anfassen: `claude update` tauscht das
    # Programm unter dem laufenden Prozess aus. Der Boot-Lauf hat das Problem
    # nicht — da gibt es noch keine Läufe.
    if any(not r.done for r in RUNS.values()):
        return {"ok": False, "error": "Es läuft gerade ein Chat — bitte erst abwarten."}
    return updmod.start(trigger="manuell")


@router.get("/api/engines/claude/install")
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


@router.get("/api/persona")
def persona_get():
    """SOUL.md und USER.md im Klartext — die Einstellungsseite bearbeitet sie."""
    return {k: cfg.persona_read(k) for k in cfg.PERSONA_FILES}


@router.post("/api/persona")
async def persona_set(req: Request):
    body = await req.json()
    out = {}
    for k in cfg.PERSONA_FILES:
        if k in body:
            out[k] = cfg.persona_write(k, body[k])
    return {"ok": True, **out}


@router.get("/api/settings")
def settings_get():
    return cfg.load_settings()


@router.post("/api/settings")
async def settings_set(req: Request):
    return cfg.apply_patch(await req.json())


# ---------- Vorlesen (Gemini TTS) ----------
@router.post("/api/tts")
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


def _same_origin(ws: WebSocket) -> bool:
    """WebSockets kennen keine Same-Origin-Policy: sonst könnte jede Webseite,
    die man gerade offen hat, über localhost das Mikrofon-Diktat (und damit den
    Gemini-Key) mitbenutzen. Erlaubt: gleiche Adresse oder localhost (Vite)."""
    origin = ws.headers.get("origin")
    if not origin:
        return True  # kein Browser
    netloc = urlsplit(origin).netloc
    host = urlsplit(origin).hostname or ""
    return netloc == ws.headers.get("host") or host in ("localhost", "127.0.0.1", "::1")


@router.websocket("/api/stt/live")
async def stt_live(ws: WebSocket):
    """Spracheingabe live (Gemini 3.5 Transcribe Live) — Ablauf in server/stt.py."""
    if not (_same_origin(ws) and auth_ok(ws.headers.get("authorization", ""))):
        await ws.close(code=1008)
        return
    await ws.accept()
    await sttmod.live(ws, cfg.load_settings()["lang"])
    try:
        await ws.close()
    except Exception:
        pass


@router.get("/api/tts/voices")
async def tts_voices(lang: str = "de-DE"):
    if not re.fullmatch(r"[A-Za-z]{2,3}(-[A-Za-z0-9]{2,4})?", lang):
        return JSONResponse({"error": "ungültiger Sprachcode"}, status_code=400)
    try:
        return {"voices": await asyncio.to_thread(ttsmod.list_voices, lang)}
    except ttsmod.TTSError as e:
        return JSONResponse({"error": str(e), "voices": []}, status_code=400)


# ---------- Telegram (Einrichtung unter ⚙) ----------
@router.get("/api/telegram")
def telegram_get():
    return tgmod.public_conf()


@router.post("/api/telegram")
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


@router.post("/api/telegram/test")
async def telegram_test():
    ok = await asyncio.to_thread(tgmod.send_owner, cfg.L(
        f"👋 Hallo von {cfg.assistant_name()} — Telegram ist eingerichtet.",
        f"👋 Hi from {cfg.assistant_name()} — Telegram is set up."))
    if not ok:
        return JSONResponse({"error": cfg.L("Senden fehlgeschlagen — Token und Chat-ID prüfen.",
                                            "Sending failed — check token and chat ID.")},
                            status_code=400)
    return {"ok": True}
