"""
CONSTRUCT — eine eigene, hübsche Weboberfläche für Claude Code.
Läuft auf Kevins Subscription (OAuth), kein API-Key nötig.
Backend = FastAPI. Spricht im Hintergrund `claude -p` (headless) und streamt
die Antwort per SSE in die Oberfläche. Kann alte Claude-Code-Sessions
auflisten, anzeigen und darin weiterchatten (--resume).

Diese Datei setzt die App nur zusammen: Middleware, statische Dateien,
Router, Start und Stopp. Die Logik liegt im Paket server/ — die HTTP-Routen
in server/routes/, ein Modul je Bereich.
"""
import asyncio
import base64
import os
import secrets
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.staticfiles import StaticFiles

from server import bonsai as bonsaimod
from server import llm as llmmod
from server import telegram_bot as tgmod
from server import updates as updmod

from server.core import (APP_DIR, AUTH_PASS, AUTH_USER, STATIC_DIR, UPLOAD_DIR, WORKSPACE,
                         claude_bin, claude_env, load_persona)
from server.scheduler import scheduler_loop
from server.routes import auth, calendar, chat, files, mail, providers, sessions, system, ui


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Start und Stopp des Servers (Tests ohne `with TestClient(...)` lösen das nicht aus)."""
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
    yield
    bonsaimod.stop()   # sonst hielte der Server die GPU, obwohl CONSTRUCT weg ist
    tgmod.stop()


app = FastAPI(title="CONSTRUCT", lifespan=lifespan)


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
# Oberfläche (React, frontend/ → static/app). Die Assets tragen einen Hash im
# Namen und dürfen deshalb gecacht werden; index.html liefert routes/ui.py.
app.mount("/assets", StaticFiles(directory=str(APP_DIR / "assets"), check_dir=False),
          name="assets")

# Router in fester Reihenfolge. ui zuletzt: seine Direktlinks je Ansicht
# (/{view}) würden sonst die /api-Routen verschlucken.
for r in (auth, files, providers, system, calendar, mail, sessions, chat, ui):
    app.include_router(r.router)


if __name__ == "__main__":
    import uvicorn
    host = os.environ.get("MATRIX_HOST", "127.0.0.1")
    port = int(os.environ.get("MATRIX_PORT", "8765"))
    uvicorn.run(app, host=host, port=port)
