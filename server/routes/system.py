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

from fastapi import APIRouter, File, Request, Response, UploadFile, WebSocket
from fastapi.responses import JSONResponse

from server import config as cfg
from server import hermes as hermesmod
from server import telegram_bot as tgmod
from server import stt as sttmod
from server import tts as ttsmod
from server import tts_lokal as ttslokal
from server import updates as updmod

from server.core import (BASE_DIR, CODE_STAMP, VERSION, WEB_LOGIN_OK, WORKSPACE, auth_ok, fremder_host,
                         beenden, claude_bin)
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
    try:
        patch = await req.json()
    except ValueError:
        patch = None
    if not isinstance(patch, dict):
        return JSONResponse({"error": "bad request"}, status_code=400)
    vorher = cfg.load_settings()["team"]["aktiv"]
    neu = cfg.apply_patch(patch)
    if vorher and not neu["team"]["aktiv"]:
        from server.team import engine
        engine.abschalten()
    return neu


# ---------- Vorlesen (Gemini TTS oder lokal) ----------
@router.post("/api/tts")
async def tts_speak(req: Request):
    """Text → WAV. Stimme/Modell aus den Einstellungen, einzeln überschreibbar
    (für die Hörprobe im Einstellungsdialog).

    Lokal kommt der Text in Stücken (tts.teile): `teil` wählt eins, die Kopfzeile
    X-TTS-Teile sagt, wie viele es gibt — die Oberfläche holt das nächste,
    während das vorige spielt. Gemini liest alles am Stück (ein Stück = eine
    Anfrage ans Kontingent). engine "gemini" erzwingt Gemini, etwa für die
    Hörprobe einer Gemini-Stimme; lokal nur, wenn es eingeschaltet ist."""
    body = await req.json()
    st = cfg.load_settings()
    conf, lang = st["tts"], st["lang"]
    text = str(body.get("text") or "")
    if conf["engine"] == "lokal" and body.get("engine") != "gemini":
        teile = ttsmod.teile(text, lang)
        if not teile:
            return JSONResponse({"error": "Nichts zum Vorlesen."}, status_code=400)
        try:
            i = max(0, min(len(teile) - 1, int(body.get("teil") or 0)))
        except (TypeError, ValueError):
            i = 0
        try:
            wav = await asyncio.to_thread(ttslokal.synthesize, teile[i], lang,
                                          _probe_pfad(conf["probe"][lang]))
        except ttslokal.TTSLokalError as e:
            return JSONResponse({"error": str(e)}, status_code=400)
        return Response(wav, media_type="audio/wav", headers={"X-TTS-Teile": str(len(teile))})
    model = body.get("model") if body.get("model") in cfg.TTS_MODELS else conf["model"]
    voice = re.sub(r"[^\w.\-]", "", str(body.get("voice") or "")) or conf["voice"][lang]
    style = str(body.get("style") if "style" in body else conf["style"][lang])[:200]
    try:
        wav = await asyncio.to_thread(ttsmod.synthesize, text, model, voice, style, lang)
    except ttsmod.TTSError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    return Response(wav, media_type="audio/wav", headers={"X-TTS-Teile": "1"})


def _probe_pfad(url: str) -> str:
    """"/uploads/x.wav" (geprüft in config) → Pfad auf der Platte; "" = eingebaute Stimme."""
    from server.core import UPLOAD_DIR
    return str(UPLOAD_DIR / Path(url).name) if url else ""


@router.get("/api/tts/lokal")
def tts_lokal_status():
    """Lokale Stimme: installiert? läuft (= VRAM belegt)? Grafikkarte, Installationslauf."""
    return ttslokal.status()


@router.post("/api/tts/lokal/install")
def tts_lokal_install():
    """Installation erst, wenn die lokale Stimme unter ⚙ eingeschaltet ist —
    das Einschalten ist die ausdrückliche Zustimmung zu Download und VRAM."""
    if cfg.load_settings()["tts"]["engine"] != "lokal":
        return JSONResponse({"error": "Erst die lokale Stimme einschalten."}, status_code=400)
    return ttslokal.install_start()


@router.post("/api/tts/lokal/stop")
def tts_lokal_stop():
    """VRAM sofort freigeben, statt auf den Leerlauf-Wächter zu warten."""
    ttslokal.stop()
    return ttslokal.status()


# Stimmproben: Datei-Anfang statt Endung — die Endung sagt nur, was jemand behauptet.
_AUDIO_MAGIC = ((b"RIFF", ".wav"), (b"fLaC", ".flac"), (b"OggS", ".ogg"), (b"ID3", ".mp3"))
MAX_PROBE = 20 * 1024 * 1024


def _audio_ext(data: bytes) -> str:
    for magic, ext in _AUDIO_MAGIC:
        if data.startswith(magic) and (ext != ".wav" or data[8:12] == b"WAVE"):
            return ext
    if len(data) > 1 and data[0] == 0xFF and data[1] & 0xE0 == 0xE0:   # MP3 ohne ID3-Kopf
        return ".mp3"
    return ""


def _probe_ablegen(data: bytes, ext: str) -> dict:
    import uuid
    from server.core import UPLOAD_DIR
    UPLOAD_DIR.mkdir(exist_ok=True)
    name = f"{uuid.uuid4().hex}{ext}"
    (UPLOAD_DIR / name).write_bytes(data)
    return {"url": f"/uploads/{name}"}


@router.post("/api/tts/probe")
async def tts_probe_upload(file: UploadFile = File(...)):
    """Eigene Stimmprobe hochladen (WAV, MP3, FLAC, OGG). Gespeichert wird sie in
    den Einstellungen (tts.probe) — erst dort ist sie vor dem Aufräumen sicher."""
    data = await file.read(MAX_PROBE + 1)
    if len(data) > MAX_PROBE:
        return JSONResponse({"error": "Datei zu groß (max. 20 MB)."}, status_code=400)
    ext = _audio_ext(data)
    if not ext:
        return JSONResponse({"error": "Keine Audiodatei (erlaubt: WAV, MP3, FLAC, OGG)."},
                            status_code=400)
    return _probe_ablegen(data, ext)


@router.post("/api/tts/probe/gemini")
async def tts_probe_gemini():
    """Stimmprobe aus der eingestellten Gemini-Stimme: ~15 s, EINE Anfrage ans Kontingent."""
    st = cfg.load_settings()
    conf, lang = st["tts"], st["lang"]
    try:
        wav = await asyncio.to_thread(ttsmod.synthesize, ttsmod.PROBE_TEXT[lang], conf["model"],
                                      conf["voice"][lang], conf["style"][lang], lang)
    except ttsmod.TTSError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    return _probe_ablegen(wav, ".wav")


def _same_origin(ws: WebSocket | Request) -> bool:
    """WebSockets kennen keine Same-Origin-Policy: sonst könnte jede Webseite,
    die man gerade offen hat, über localhost das Mikrofon-Diktat (und damit den
    Gemini-Key) mitbenutzen. Erlaubt: gleiche Adresse oder localhost (Vite)."""
    origin = ws.headers.get("origin")
    if not origin:
        return True  # kein Browser
    netloc = urlsplit(origin).netloc
    host = urlsplit(origin).hostname or ""
    return netloc == ws.headers.get("host") or host in ("localhost", "127.0.0.1", "::1")


@router.post("/api/open-url")
async def open_url(req: Request):
    """Externen Link im Standardbrowser öffnen.

    Das App-Fenster (desktop.py) ist ein eigenes Browser-Profil: ein Link mit
    target=_blank ginge dort in einem nackten Fenster dieses Profils auf, nicht
    im Browser, in dem man sonst arbeitet. Darum öffnet ihn der Server, der ja
    auf demselben Rechner läuft. Nur von hier (Loopback, gleiche Herkunft) und
    nur http(s) — sonst könnte jede offene Webseite Fenster aufreißen.
    """
    if not _von_hier(req):
        return JSONResponse({"ok": False}, status_code=403)
    try:
        url = str((await req.json()).get("url", ""))
    except Exception:
        url = ""
    if not re.match(r"^https?://", url, re.I):
        return JSONResponse({"ok": False}, status_code=400)
    import webbrowser
    return {"ok": bool(await asyncio.to_thread(webbrowser.open, url))}


def _von_hier(req: Request) -> bool:
    """Anfrage vom eigenen Rechner und aus CONSTRUCT selbst (nicht von einer
    fremden Webseite, die über localhost hereinfunkt)."""
    host = req.client.host if req.client else ""
    return host in ("127.0.0.1", "::1") and _same_origin(req)


@router.post("/api/shutdown")
async def shutdown(req: Request):
    """CONSTRUCT beenden (⏻). Nur vom eigenen Rechner: aus der Ferne ließe
    sich der Server danach nicht wieder starten."""
    if not _von_hier(req):
        return JSONResponse({"ok": False}, status_code=403)
    asyncio.get_running_loop().call_later(0.4, beenden)   # erst antworten
    return {"ok": True}


@router.websocket("/api/stt/live")
async def stt_live(ws: WebSocket):
    """Spracheingabe live (Gemini 3.5 Transcribe Live) — Ablauf in server/stt.py."""
    if fremder_host(ws.headers) or not (_same_origin(ws) and auth_ok(ws.headers.get("authorization", ""))):
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
@router.get("/api/images")
def images_status():
    """Bilder erzeugen: Key hinterlegt? Welches Modell? (ohne den Key selbst)"""
    from server import images
    return images.status()


@router.post("/api/images")
async def images_save(req: Request):
    """fal.ai-Key speichern (leer = löschen)."""
    from server import images
    body = await req.json()
    if "api_key" in body:
        images.save_key(str(body.get("api_key") or ""))
    return images.status()


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
