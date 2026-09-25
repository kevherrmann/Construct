"""Auslieferung der Oberfläche (React-Build in static/app) mit den
Startdaten der Installation. Wird als LETZTER Router eingebunden: die
Direktlinks je Ansicht würden sonst /api-Routen verschlucken.
"""
import json
import re

from fastapi import APIRouter
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from server import config as cfg

from server.core import APP_DIR, WEB_LOGIN_OK, WORKSPACE, claude_bin

router = APIRouter()


def _inject_bootstrap(html: str) -> str:
    """Ausbaustufe SYNCHRON mitgeben, nicht per fetch: sonst baut sich die Seite
    einmal mit Skills/E-Mail/Teile auf und räumt sie einen Wimpernschlag
    später wieder weg — sichtbares Flackern und ein kurz klickbares Menü.

    re.DOTALL ist Pflicht: das Vorgabe-Objekt in index.html geht über mehrere
    Zeilen. Ohne das Flag greift die Ersetzung stillschweigend nicht, die Seite
    bekommt die eingebauten Vorgaben statt der echten Einstellungen — und der
    Fehler sieht aus wie "die Einstellungen speichern nicht".
    """
    payload = "window.CONSTRUCT=" + json.dumps({
        "user": cfg.user_name(),
        "assistant": cfg.assistant_name(),
        "claude": bool(claude_bin()),
        "web_login": WEB_LOGIN_OK,
        "lang": cfg.lang(),
        "workspace": WORKSPACE,
        "settings": cfg.load_settings(),
    }, ensure_ascii=False) + ";"
    # Ersatz als Funktion, nicht als Zeichenkette: in einem Ersatz-String wären
    # Backslashes und \g Steuerzeichen, und genau die stecken in JSON.
    return re.sub(r"window\.CONSTRUCT\s*=\s*\{.*?\};", lambda _m: payload,
                  html, count=1, flags=re.DOTALL)


# Kein Browser-Cache -> immer aktueller Stand, kein Hard-Refresh nötig
_NO_CACHE = {"Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
             "Pragma": "no-cache"}


def _app_page() -> HTMLResponse:
    f = APP_DIR / "index.html"
    if not f.exists():
        return HTMLResponse("Oberfläche noch nicht gebaut: cd frontend && npm run build",
                            status_code=500)
    return HTMLResponse(_inject_bootstrap(f.read_text(encoding="utf-8")), headers=_NO_CACHE)


@router.get("/")
def index():
    return _app_page()


# Die React-Oberfläche lief während des Umbaus unter /next — alte Lesezeichen
# und offene Fenster landen jetzt auf der gleichen Seite ohne Präfix.
@router.get("/next")
@router.get("/next/{rest:path}")
def next_redirect(rest: str = ""):
    return RedirectResponse("/" + rest, status_code=301)


# ---------- Oberfläche: Direktlinks ----------
# Jede Ansicht hat eine eigene Adresse (/chat, /calendar, /mail/accounts …);
# das Routing macht React. Bewusst nur die bekannten Ansichten und ganz am
# Ende deklariert: ein allgemeiner Platzhalter weiter oben würde die
# /api-Routen verschlucken, und Tippfehler sollen ein ehrliches 404 bekommen.
APP_VIEWS = {"chat", "skills", "calendar", "mail", "mcp", "settings"}


@router.get("/{view}")
@router.get("/{view}/{_rest:path}")
def app_view(view: str, _rest: str = ""):
    if view not in APP_VIEWS:
        return JSONResponse({"error": "not found"}, status_code=404)
    return _app_page()
