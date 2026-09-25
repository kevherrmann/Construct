"""
Vorlesen für CONSTRUCT über Gemini TTS (gemini-3.8-flash[-lite]-tts).

Nutzt den Gemini-Key, der unter 🧠 → KI-Anbieter hinterlegt ist (llm.py).
Liefert immer WAV — die API gibt je nach Modell WAV oder rohes PCM (L16)
zurück, Letzteres bekommt hier einen WAV-Kopf.
"""
import base64
import json
import re
import struct
import time
import urllib.error
import urllib.request

import llm as llmmod

API = "https://generativelanguage.googleapis.com/v1beta"
MAX_CHARS = 4000  # längere Antworten werden gekürzt, sonst dauert es ewig


class TTSError(Exception):
    """Verständlicher Fehler (wird dem Nutzer 1:1 angezeigt)."""


def _key() -> str:
    k = llmmod.provider_conf("gemini")["api_key"]
    if not k:
        raise TTSError("Kein Gemini-Key hinterlegt — unter ⚙ Einstellungen → "
                       "🔊 Vorlesen → „Gemini-Key eintragen“.")
    return k


def _call(url: str, body=None, timeout: int = 60) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, headers={
        "x-goog-api-key": _key(), "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        try:
            msg = json.loads(e.read()).get("error", {}).get("message", "")
        except Exception:
            msg = ""
        if e.code == 429:
            raise TTSError("Gemini-Kontingent erschöpft — kurz warten oder "
                           "morgen wieder.") from None
        raise TTSError(f"Gemini TTS: {msg or e.reason} ({e.code})") from None
    except urllib.error.URLError as e:
        raise TTSError(f"Gemini nicht erreichbar: {e.reason}") from None


def clean_text(text: str) -> str:
    """Markdown raus — sonst liest die Stimme Sternchen und Codeblöcke vor."""
    t = re.sub(r"```.*?```", " (Codeblock ausgelassen) ", text, flags=re.S)
    t = re.sub(r"`([^`]*)`", r"\1", t)
    t = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", t)
    t = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", t)
    t = re.sub(r"^\s{0,3}(#{1,6}|>|[-*+]|\d+\.)\s+", "", t, flags=re.M)
    t = re.sub(r"[*_~|]+", "", t)
    t = re.sub(r"\n{2,}", "\n", t).strip()
    if len(t) > MAX_CHARS:
        t = t[:MAX_CHARS].rsplit(" ", 1)[0] + " …"
    return t


def _wav(pcm: bytes, rate: int) -> bytes:
    """16-Bit-Mono-PCM in einen WAV-Container packen."""
    return (b"RIFF" + struct.pack("<I", 36 + len(pcm)) + b"WAVEfmt "
            + struct.pack("<IHHIIHH", 16, 1, 1, rate, rate * 2, 2, 16)
            + b"data" + struct.pack("<I", len(pcm)) + pcm)


def synthesize(text: str, model: str, voice: str, style: str = "") -> bytes:
    text = clean_text(text)
    if not text:
        raise TTSError("Nichts zum Vorlesen.")
    part = {"text": text}
    if style:
        part["speech_metadata"] = {"style": style}
    res = _call(f"{API}/models/{model}:generateContent", {
        "contents": [{"role": "user", "parts": [part]}],
        "generationConfig": {
            "responseModalities": ["AUDIO"],
            "speechConfig": {"voiceConfig": {"voice": voice}},
        },
    }, timeout=120)
    try:
        inline = next(p for p in res["candidates"][0]["content"]["parts"]
                      if "inlineData" in p)["inlineData"]
    except (KeyError, IndexError, StopIteration):
        raise TTSError("Gemini hat kein Audio geliefert.") from None
    audio = base64.b64decode(inline["data"])
    mime = inline.get("mimeType", "").lower()
    if "wav" in mime or audio[:4] == b"RIFF":
        return audio
    m = re.search(r"rate=(\d+)", mime)
    return _wav(audio, int(m.group(1)) if m else 24000)


# ---------- Stimmenkatalog ----------
_VOICE_CACHE: dict = {}  # language_code -> (zeitpunkt, liste)


def _g(v: dict, *names):
    """REST liefert camelCase, die Doku nennt snake_case — beides annehmen."""
    for n in names:
        if v.get(n):
            return v[n]
    return ""


def list_voices(lang: str = "de-DE") -> list:
    hit = _VOICE_CACHE.get(lang)
    if hit and time.time() - hit[0] < 3600:
        return hit[1]
    out, token = [], ""
    for _ in range(20):  # Sicherung gegen endloses Blättern
        q = f"language_code={lang}&page_size=1000"
        if token:
            q += f"&page_token={token}"
        res = _call(f"{API}/voices?{q}")
        for v in res.get("voices") or []:
            vid = _g(v, "id", "name")
            if not vid:
                continue
            out.append({
                "id": vid.split("/")[-1],
                "name": _g(v, "displayName", "display_name") or vid.split("/")[-1],
                "gender": _g(v, "gender"),
                "pitch": _g(v, "pitch"),
                "accent": _g(v, "accent"),
                "type": _g(v, "type"),
                "description": _g(v, "description"),
            })
        token = _g(res, "nextPageToken", "next_page_token")
        if not token:
            break
    out.sort(key=lambda v: (v["type"] != "prebuilt", v["name"].lower()))
    _VOICE_CACHE[lang] = (time.time(), out)
    return out
