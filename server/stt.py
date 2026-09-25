"""
Spracheingabe für CONSTRUCT über Gemini 3.5 Transcribe (Interactions API).

Die Aufnahme kommt als kurze Audiodatei aus dem Browser (webm/opus, in
Safari/WKWebView mp4) und geht direkt eingebettet an Gemini — bis 20 MB je
Anfrage, das sind viele Minuten Sprache. Modus "smart" lässt Füllwörter und
Versprecher weg ("äh, nee, ich meine …"): beim Diktieren genau das Richtige.
"""
import base64
import re

from server.gemini import GeminiError, call

MODEL = "gemini-3.5-transcribe"
# Unter der 20-MB-Grenze der API bleiben (Base64 bläht um ein Drittel auf).
MAX_BYTES = 14 * 1024 * 1024
# Sprache der Oberfläche als Hinweis; Gemini erkennt trotzdem automatisch.
LANG_CODES = {"de": "de-DE", "en": "en-US"}


def clean_mime(mime: str) -> str:
    """"audio/webm;codecs=opus" → "audio/webm". Nur Audio-Typen durchlassen."""
    m = (mime or "").split(";")[0].strip().lower()
    if m == "video/webm":  # manche Browser melden Audio-only-WebM so
        return "audio/webm"
    return m if re.fullmatch(r"audio/[a-z0-9.+-]{1,30}", m) else "audio/webm"


def transcribe(audio: bytes, mime: str, lang: str = "de") -> str:
    if not audio:
        raise GeminiError("Keine Aufnahme angekommen.")
    if len(audio) > MAX_BYTES:
        raise GeminiError("Aufnahme zu lang — bitte in kürzeren Stücken sprechen.")
    body = {
        "model": MODEL,
        "input": [{
            "type": "audio",
            "data": base64.b64encode(audio).decode(),
            "mime_type": clean_mime(mime),
        }],
        "generation_config": {"transcription_config": {
            "mode": "smart",
            "language_codes": [LANG_CODES.get(lang, "de-DE")],
        }},
    }
    res = call("interactions", body, timeout=120, what="Gemini Transcribe")
    texts = [c.get("text", "") for st in res.get("steps") or []
             for c in st.get("content") or [] if c.get("type") == "text"]
    text = " ".join(t.strip() for t in texts if t and t.strip())
    if not text and res.get("output_text"):
        text = str(res["output_text"]).strip()
    return text
