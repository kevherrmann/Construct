"""
Vorlesen für CONSTRUCT über Gemini TTS (gemini-3.8-flash[-lite]-tts).

Nutzt den Gemini-Key über server/gemini.py.
Liefert immer WAV — die API gibt je nach Modell WAV oder rohes PCM (L16)
zurück, Letzteres bekommt hier einen WAV-Kopf.

Die lokale Stimme (tts_lokal.py) liest nicht den ganzen Text am Stück, sondern
in Stücken (teile()): das erste ist kurz, damit sie nach einer Sekunde zu
sprechen beginnt; die übrigen rechnet sie, während das vorige läuft.
"""
import base64
import re
import struct
import time

from server.gemini import GeminiError, call
MAX_CHARS = 4000  # längere Antworten werden gekürzt, sonst dauert es ewig
# Lokal kostet ein langer Text kein Kontingent und kommt in Stücken — da darf
# es mehr sein.
LOKAL_MAX_CHARS = 12000
TEIL_ERSTER = 140   # erstes Stück: ein, zwei Sätze — schneller Beginn
TEIL_MAX = 320      # ~20 s Sprache; Chatterbox schafft höchstens ~40 s am Stück
# Jedes Stück muss fertig gerechnet sein, bevor das vorige ausgespielt ist.
# Chatterbox rechnet gut doppelt so schnell wie Echtzeit — also darf ein Stück
# höchstens um diesen Faktor länger sein als das vorige, sonst entsteht eine
# Pause (gemessen: 3 s Stück, danach 16 s Stück → knapp 4 s Stille).
WACHSTUM = 1.6
TEIL_MIN = 80

# Stimmprobe aus einer Gemini-Stimme: ~15 s natürliches Sprechen, Frage und Ausruf
# dabei, damit die lokale Stimme auch die Satzmelodie abschauen kann.
PROBE_TEXT = {
    "de": ("Hallo! Schön, dass du da bist. Ich hab mir gerade alles angeschaut, und ehrlich "
           "gesagt: Das meiste sieht richtig gut aus. Nur an einer Stelle würde ich nochmal "
           "drübergehen, die ist ein bisschen langsam. Sollen wir das zusammen machen? "
           "Dauert bestimmt nur zehn Minuten."),
    "en": ("Hi there! Good to see you. I just had a look at everything, and honestly, most "
           "of it looks really good. There's just one spot I'd go over again, it's a little "
           "slow. Want to do it together? It'll only take ten minutes."),
}


# Früherer Name — die Routen fangen TTSError.
TTSError = GeminiError


def clean_text(text: str, lang: str = "de", max_chars: int = MAX_CHARS) -> str:
    """Markdown raus — sonst liest die Stimme Sternchen und Codeblöcke vor."""
    skip = " (code block skipped) " if lang == "en" else " (Codeblock ausgelassen) "
    t = re.sub(r"```.*?```", skip, text, flags=re.S)
    t = re.sub(r"`([^`]*)`", r"\1", t)
    t = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", t)
    t = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", t)
    t = re.sub(r"^\s{0,3}(#{1,6}|>|[-*+]|\d+\.)\s+", "", t, flags=re.M)
    t = re.sub(r"[*_~|]+", "", t)
    t = re.sub(r"\n{2,}", "\n", t).strip()
    if len(t) > max_chars:
        t = t[:max_chars].rsplit(" ", 1)[0] + " …"
    return t


def _gruppen(teile: list[str], n: int) -> list[str]:
    """Stücke der Reihe nach zu Gruppen bis n Zeichen zusammenlegen."""
    out: list[str] = []
    for t in teile:
        if out and len(out[-1]) + 1 + len(t) <= n:
            out[-1] += " " + t
        else:
            out.append(t)
    return out


def _zerlege(satz: str) -> list[str]:
    """Längere Sätze an Kommas teilen — so kann ein Stück auch mitten im Satz
    enden, wenn es sonst zu groß würde (dort ist ohnehin eine kleine Pause).
    Was dann noch über TEIL_MAX liegt, an Leerzeichen, ein Riesenwort hart."""
    if len(satz) <= TEIL_ERSTER:
        return [satz]
    out = []
    for teil in re.split(r"(?<=[,;–—])\s+", satz):
        if len(teil) <= TEIL_MAX:
            out.append(teil)
            continue
        woerter = [w[i:i + TEIL_MAX] for w in teil.split() for i in range(0, len(w), TEIL_MAX)]
        out += _gruppen(woerter, TEIL_MAX)
    return out


def teile(text: str, lang: str = "de") -> list[str]:
    """Text für die lokale Stimme in Stücke an Satzgrenzen.
    Zeilen ohne Satzzeichen (Überschriften, Listenpunkte) bekommen einen Punkt —
    sonst liest die Stimme sie ohne Pause in den nächsten Satz hinein."""
    saetze = []
    for zeile in clean_text(text, lang, LOKAL_MAX_CHARS).split("\n"):
        zeile = zeile.strip()
        if not zeile:
            continue
        if zeile[-1] not in ".!?…:;":
            zeile += "."
        saetze += [x for x in re.split(r"(?<=[.!?…:;])\s+", zeile) if x]
    out: list[str] = []
    for stueck in (st for s in saetze for st in _zerlege(s)):
        # Grenze des Stücks, in das gerade gefüllt wird (out[-1]): das erste
        # kurz, jedes weitere höchstens WACHSTUM-mal so lang wie sein Vorgänger.
        grenze = (TEIL_ERSTER if len(out) <= 1 else
                  min(TEIL_MAX, max(TEIL_MIN, int(WACHSTUM * len(out[-2])))))
        # Winzige Reste („Ende.“) nicht allein: die klingen bei Chatterbox oft verschluckt.
        if len(stueck) < 30:
            grenze += 40
        if out and len(out[-1]) + 1 + len(stueck) <= grenze:
            out[-1] += " " + stueck
        else:
            out.append(stueck)
    return out


def _wav(pcm: bytes, rate: int) -> bytes:
    """16-Bit-Mono-PCM in einen WAV-Container packen."""
    return (b"RIFF" + struct.pack("<I", 36 + len(pcm)) + b"WAVEfmt "
            + struct.pack("<IHHIIHH", 16, 1, 1, rate, rate * 2, 2, 16)
            + b"data" + struct.pack("<I", len(pcm)) + pcm)


def synthesize(text: str, model: str, voice: str, style: str = "",
               lang: str = "de") -> bytes:
    text = clean_text(text, lang)
    if not text:
        raise TTSError("Nichts zum Vorlesen.")
    part = {"text": text}
    if style:
        part["speech_metadata"] = {"style": style}
    res = call(f"models/{model}:generateContent", what="Gemini TTS", body={
        "contents": [{"role": "user", "parts": [part]}],
        "generationConfig": {
            "responseModalities": ["AUDIO"],
            "speechConfig": {"voiceConfig": {"voice": voice}},
        },
    }, timeout=300)  # lange Texte brauchen über 2 Minuten
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
        res = call(f"voices?{q}", what="Gemini TTS")
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
