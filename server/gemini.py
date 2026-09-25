"""
Gemeinsamer Zugang zur Gemini-API für Vorlesen (tts.py) und Spracheingabe
(stt.py). Nutzt den Gemini-Key, der unter ⚙ → Modelle & Anbieter hinterlegt
ist (llm.py); Fehler kommen als verständlicher Text für die Oberfläche.
"""
import json
import urllib.error
import urllib.request

from server import llm as llmmod

API = "https://generativelanguage.googleapis.com/v1beta"


class GeminiError(Exception):
    """Verständlicher Fehler (wird dem Nutzer 1:1 angezeigt)."""


def api_key() -> str:
    k = llmmod.provider_conf("gemini")["api_key"]
    if not k:
        raise GeminiError("Kein Gemini-Key hinterlegt — unter ⚙ Einstellungen → "
                          "🔊 Vorlesen → „Gemini-Key eintragen“.")
    return k


def call(path: str, body=None, timeout: int = 60, what: str = "Gemini") -> dict:
    """GET (ohne body) bzw. POST an API/path; `what` benennt den Dienst in Fehlern."""
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(f"{API}/{path}", data=data, headers={
        "x-goog-api-key": api_key(), "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        try:
            msg = json.loads(e.read()).get("error", {}).get("message", "")
        except Exception:
            msg = ""
        if e.code == 429:
            raise GeminiError("Gemini-Kontingent erschöpft — kurz warten oder "
                              "morgen wieder.") from None
        raise GeminiError(f"{what}: {msg or e.reason} ({e.code})") from None
    except urllib.error.URLError as e:
        raise GeminiError(f"Gemini nicht erreichbar: {e.reason}") from None
