"""
Spracheingabe für CONSTRUCT über Gemini 3.5 Transcribe Live.

Der Browser schickt das Mikrofon als rohes PCM (16 kHz, 16 bit, mono) in
100-ms-Stücken über einen WebSocket; der Server reicht es an die Live-API
weiter und den erkannten Text sofort zurück — die Oberfläche schreibt also
schon mit, während man spricht. Der Gemini-Key bleibt dabei auf dem Server.

Gemini liefert je Äußerung (bis zur nächsten Sprechpause) laufend eine
vorläufige Fassung ("interim") und am Ende die bereinigte ("final"). Modus
SMART lässt Füllwörter und Versprecher weg ("äh, nee, ich meine …").

Protokoll zum Browser:
  Browser → Server   Binärnachrichten = PCM-Stücke, Text "end" = fertig
  Server → Browser   {"ready": true} · {"interim": "…"} · {"final": "…"}
                     · {"error": "…"} · {"done": true}
"""
import asyncio
import base64
import json

import websockets
from fastapi import WebSocket, WebSocketDisconnect

from server.gemini import GeminiError, api_key

MODEL = "models/gemini-3.5-transcribe-live"
URL = ("wss://generativelanguage.googleapis.com/ws/"
       "google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContent")
MIME = "audio/pcm;rate=16000"
# Sprache der Oberfläche als Hinweis; Gemini erkennt trotzdem automatisch.
LANG_CODES = {"de": "de-DE", "en": "en-US"}
# So lange nach "end" auf die letzte bereinigte Fassung warten.
FINAL_WAIT = 4.0


def setup_message(lang: str) -> dict:
    return {"setup": {
        "model": MODEL,
        "generationConfig": {"responseModalities": ["TEXT"]},
        "inputAudioTranscription": {
            "languageCodes": [LANG_CODES.get(lang, "de-DE")],
            "mode": "SMART",
        },
    }}


def close_error(code: int | None, reason: str) -> str:
    """Abbruch der Live-Verbindung → verständlicher Text für die Oberfläche."""
    low = (reason or "").lower()
    if "quota" in low or "exhausted" in low or "rate" in low:
        return "Gemini-Kontingent erschöpft — kurz warten oder morgen wieder."
    if "api key" in low or "api_key" in low or "permission" in low:
        return "Gemini-Key ungültig — unter ⚙ Einstellungen prüfen."
    return f"Gemini Transcribe: {reason or 'Verbindung beendet'} ({code})"


def transcripts(msg: dict) -> tuple[str | None, str | None]:
    """(vorläufig, final) aus einer Nachricht der Live-API."""
    sc = msg.get("serverContent") or {}
    interim = (sc.get("interimInputTranscription") or {}).get("text")
    final = (sc.get("inputTranscription") or {}).get("text")
    return interim, final


async def live(client: WebSocket, lang: str) -> None:
    """Eine Diktat-Sitzung zwischen Browser (client) und Gemini vermitteln."""
    async def send(**kw):
        try:
            await client.send_json(kw)
        except Exception:
            pass  # Browser schon weg

    try:
        key = api_key()
    except GeminiError as e:
        await send(error=str(e))
        return
    try:
        async with websockets.connect(f"{URL}?key={key}", max_size=None,
                                      open_timeout=10) as gem:
            await gem.send(json.dumps(setup_message(lang)))
            first = json.loads(await asyncio.wait_for(gem.recv(), 10))
            if "setupComplete" not in first:
                await send(error=f"Gemini Transcribe: unerwartete Antwort {str(first)[:120]}")
                return
            await send(ready=True)
            await _relay(client, gem, send)
    except websockets.ConnectionClosed as e:
        rcvd = e.rcvd
        await send(error=close_error(rcvd.code if rcvd else None, rcvd.reason if rcvd else ""))
    except websockets.InvalidStatus as e:
        code = e.response.status_code
        await send(error="Gemini-Key ungültig — unter ⚙ Einstellungen prüfen."
                   if code in (400, 401, 403) else f"Gemini Transcribe: HTTP {code}")
    except (OSError, asyncio.TimeoutError):
        await send(error="Gemini nicht erreichbar.")


async def _relay(client: WebSocket, gem, send) -> None:
    state = {"interim": ""}   # vorläufiger Text der laufenden Äußerung
    ended = asyncio.Event()   # Browser hat "end" geschickt
    settled = asyncio.Event()  # nach "end": nichts mehr offen

    async def up():
        try:
            while True:
                m = await client.receive()
                if m["type"] == "websocket.disconnect":
                    return
                if m.get("bytes"):
                    await gem.send(json.dumps({"realtimeInput": {"audio": {
                        "data": base64.b64encode(m["bytes"]).decode(), "mimeType": MIME}}}))
                elif m.get("text") == "end":
                    await gem.send(json.dumps({"realtimeInput": {"audioStreamEnd": True}}))
                    ended.set()
                    if not state["interim"]:
                        settled.set()
                    try:
                        await asyncio.wait_for(settled.wait(), FINAL_WAIT)
                    except asyncio.TimeoutError:
                        pass
                    return
        except WebSocketDisconnect:
            return

    async def down():
        async for raw in gem:
            interim, final = transcripts(json.loads(raw))
            if interim:
                state["interim"] = interim
                await send(interim=interim)
            if final is not None:
                state["interim"] = ""
                if final.strip():
                    await send(final=final.strip())
                if ended.is_set():
                    settled.set()

    tasks = [asyncio.create_task(up()), asyncio.create_task(down())]
    try:
        # Endet der Browser (Abbruch) oder Gemini, ist die Sitzung vorbei.
        done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for t in done:
            if t.exception():
                raise t.exception()
    finally:
        for t in tasks:
            t.cancel()
    # Schließt Gemini die letzte Äußerung nicht rechtzeitig ab (oder beendet
    # die Sitzung von sich aus), zählt die vorläufige Fassung.
    if state["interim"]:
        await send(final=state["interim"])
    await send(done=True)
