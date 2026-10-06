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
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

from server import bonsai as bonsaimod
from server import config as cfg
from server import llm as llmmod
from server import telegram_bot as tgmod
from server import updates as updmod
from server import runs as runsmod
from server import uploads_gc

from server.core import (APP_DIR, STATIC_DIR, UPLOAD_DIR, WORKSPACE,
                         auth_ok, claude_bin, claude_env, fremde_herkunft, fremder_host, load_persona,
                         remember_server)
from server.scheduler import scheduler_loop
from server.team import engine
from server.routes import auth, calendar, chat, files, mail, providers, sessions, system, team, tickets, ui


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Start und Stopp des Servers (Tests ohne `with TestClient(...)` lösen das nicht aus)."""
    asyncio.create_task(scheduler_loop())
    # Läufe, die der vorige Server mitten im Zug zurückgelassen hat
    runsmod.aufnehmen()
    tgmod.init(claude_bin=lambda: claude_bin() or "claude", claude_env=claude_env,
               persona=load_persona, workspace=WORKSPACE)
    tgmod.restart()
    uploads_gc.start()   # verwaiste Anhänge nach ein paar Tagen wegräumen
    # Früher installiertes Ollama nach Container-Neustart wieder hochfahren
    asyncio.get_running_loop().run_in_executor(None, llmmod.ollama_autostart)
    # Claude Code / Hermes aktuell halten. Der Aufruf kehrt sofort zurück —
    # gearbeitet wird in einem eigenen Thread, der Start wartet nie aufs Netz.
    try:
        updmod.boot_check()
    except Exception as e:
        print(f"[updates] Start-Prüfung fehlgeschlagen: {type(e).__name__}: {e}", flush=True)
    if cfg.load_settings()["team"]["aktiv"]:
        engine.starten()      # offene Aufträge nach einem Neustart wieder aufnehmen
    yield
    engine.stoppen()
    bonsaimod.stop()   # sonst hielte der Server die GPU, obwohl CONSTRUCT weg ist
    tgmod.stop()


app = FastAPI(title="CONSTRUCT", lifespan=lifespan)


@app.middleware("http")
async def basic_auth(request: Request, call_next):
    """HTTP-Basic-Auth vor ALLEM — aber nur wenn ein Passwort konfiguriert ist.
    WebSockets laufen an Middleware vorbei und prüfen selbst (auth_ok)."""
    # Der Firmen-Bus ist der Rückweg der Mitarbeiter-Prozesse an den Server. Er weist
    # sich mit einem Einmal-Token je Zug aus (server/team/bus.py) und hat kein
    # Passwort: das stünde sonst in der Prozessliste jedes Rechners, auf dem er läuft.
    if fremder_host(request.headers):
        return PlainTextResponse(cfg.L(
            "Ohne Passwort antwortet CONSTRUCT nur unter localhost. Öffne http://127.0.0.1:…, "
            "setze MATRIX_PASS oder trag diese Adresse in CONSTRUCT_ORIGINS ein.",
            "Without a password CONSTRUCT answers only on localhost. Open http://127.0.0.1:…, "
            "set MATRIX_PASS, or add this address to CONSTRUCT_ORIGINS."), status_code=403)
    if request.url.path != "/api/team/bus" and not auth_ok(request.headers.get("Authorization", "")):
        return Response(status_code=401, headers={"WWW-Authenticate": 'Basic realm="Cody"'})
    # Auch mit Passwort: der Browser hängt gespeicherte Zugangsdaten an fremde Anfragen an.
    if fremde_herkunft(request.method, request.headers):
        return JSONResponse({"error": "Anfrage von einer fremden Webseite abgelehnt"}, status_code=403)
    remember_server(request.scope)
    return await call_next(request)


class _NachfragenStatic(StaticFiles):
    """Raumbilder, Figuren, Gesichter: Namen ohne Hash, die sich beim Update ändern
    können. Ohne Anweisung hält der Browser sie stundenlang für aktuell (am 06.10.2026
    saß so nach dem Umbau noch Cody statt Luna am Tisch). no-cache heißt: vor Gebrauch
    kurz nachfragen; unverändert kommt nur ein 304 zurück."""

    def file_response(self, *args, **kwargs):
        r = super().file_response(*args, **kwargs)
        r.headers["Cache-Control"] = "no-cache"
        return r


app.mount("/static", _NachfragenStatic(directory=str(STATIC_DIR)), name="static")
app.mount("/uploads", StaticFiles(directory=str(UPLOAD_DIR)), name="uploads")
# Oberfläche (React, frontend/ → static/app). Die Assets tragen einen Hash im
# Namen und dürfen deshalb gecacht werden; index.html liefert routes/ui.py.
app.mount("/assets", StaticFiles(directory=str(APP_DIR / "assets"), check_dir=False),
          name="assets")

# Router in fester Reihenfolge. ui zuletzt: seine Direktlinks je Ansicht
# (/{view}) würden sonst die /api-Routen verschlucken.
for r in (auth, files, providers, system, calendar, mail, sessions, chat, tickets, team, ui):
    app.include_router(r.router)


if __name__ == "__main__":
    import uvicorn
    host = os.environ.get("MATRIX_HOST", "127.0.0.1")
    port = int(os.environ.get("MATRIX_PORT", "8765"))
    uvicorn.run(app, host=host, port=port)
