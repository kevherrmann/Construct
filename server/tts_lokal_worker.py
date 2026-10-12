"""Lokale Stimme (Chatterbox Multilingual V3) als kleiner HTTP-Dienst.

Läuft NICHT in CONSTRUCTs Python, sondern in der eigenen Umgebung (.venv-tts,
torch + chatterbox, einige GB). server/tts_lokal.py startet ihn bei Bedarf und
beendet ihn nach Leerlauf wieder: nur solange er läuft, belegt das Modell den
Grafikspeicher. Gestartet wird er mit `python -I` — sonst läge server/ auf dem
Importpfad, und eine Bibliothek, die `import config` sagt, bekäme CONSTRUCTs
config.py.

Nur Standardbibliothek und was die venv mitbringt. Gerechnet wird eine
Anfrage nach der anderen (_RECHNET) — die GPU kann ohnehin nur eine —, aber
/health antwortet sofort, auch mitten in einem Satz: sonst hielte CONSTRUCT
den beschäftigten Dienst für tot und startete einen zweiten.

Nach --idle Sekunden ohne Anfrage beendet er sich selbst. Normalerweise stoppt
ihn CONSTRUCT vorher; das hier fängt den Fall ab, dass CONSTRUCT hart beendet
wurde und es kein PDEATHSIG gibt (Windows, macOS) — sonst hielte ein
verwaister Dienst den VRAM, bis man den Rechner neu startet.

  GET  /health   {"chatterbox": true, "device": "cuda"}
  POST /tts      {"text", "lang", "probe": absoluter Pfad oder ""} → audio/wav
  --pruefen      Modell laden (beim ersten Mal ~3 GB Download), einen Satz
                 sprechen, Gerät und Tempo melden, beenden — für die Installation.
"""
import argparse
import io
import json
import os
import sys
import threading
import time
import wave
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import torch
from chatterbox.mtl_tts import SUPPORTED_LANGUAGES, ChatterboxMultilingualTTS

MAX_TEXT = 1000   # CONSTRUCT schickt Stücke um 300 Zeichen (tts.teile)

MODEL = None
DEVICE = "cpu"
_STANDARD = None  # eingebaute Stimme (conds.pt) — gilt ohne Stimmprobe
_PROBEN = {}      # (pfad, mtime) → vorberechnete Stimmprobe
_RECHNET = threading.Lock()
_LETZTE = time.monotonic()   # letzte Anfrage (Beginn oder Ende)


def geraet() -> str:
    if torch.cuda.is_available():
        return "cuda"
    if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def laden():
    global MODEL, DEVICE, _STANDARD
    DEVICE = geraet()
    MODEL = ChatterboxMultilingualTTS.from_pretrained(device=DEVICE, t3_model="v3")
    _STANDARD = MODEL.conds


def _stimme(probe: str):
    """Stimmprobe vorbereiten — einmal je Datei, nicht bei jedem Satz."""
    if not probe:
        MODEL.conds = _STANDARD
        return
    key = (probe, os.path.getmtime(probe))
    if key not in _PROBEN:
        if len(_PROBEN) >= 4:
            _PROBEN.pop(next(iter(_PROBEN)))
        MODEL.prepare_conditionals(probe, exaggeration=0.5)
        _PROBEN[key] = MODEL.conds
    MODEL.conds = _PROBEN[key]


def sprechen(text: str, lang: str, probe: str = "") -> bytes:
    _stimme(probe)
    lang = lang if lang in SUPPORTED_LANGUAGES else "en"
    wav = MODEL.generate(text[:MAX_TEXT], language_id=lang)
    pcm = (wav.squeeze().clamp(-1, 1) * 32767).to(torch.int16).cpu().numpy().tobytes()
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(MODEL.sr)
        w.writeframes(pcm)
    return buf.getvalue()


class Handler(BaseHTTPRequestHandler):
    def _json(self, code: int, obj: dict):
        data = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path == "/health":
            self._json(200, {"chatterbox": True, "device": DEVICE})
        else:
            self._json(404, {"error": "unbekannt"})

    def _von_constructs_server(self) -> bool:
        """Jede Webseite im Browser kann an 127.0.0.1 schicken. Verlangt wird
        darum JSON (das erzwingt beim Browser eine Vorab-Anfrage, die hier nie
        beantwortet wird) und der eigene Host (gegen DNS-Rebinding)."""
        host = (self.headers.get("Host") or "").rsplit(":", 1)[0]
        return (host in ("127.0.0.1", "localhost")
                and (self.headers.get("Content-Type") or "").startswith("application/json"))

    def do_POST(self):
        if self.path != "/tts":
            return self._json(404, {"error": "unbekannt"})
        if not self._von_constructs_server():
            return self._json(403, {"error": "nur für CONSTRUCT"})
        global _LETZTE
        try:
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)))
            probe = str(body.get("probe") or "")
            if probe and not os.path.isfile(probe):
                return self._json(400, {"error": "Stimmprobe nicht gefunden."})
            with _RECHNET:
                _LETZTE = time.monotonic()
                try:
                    data = sprechen(str(body.get("text") or ""), str(body.get("lang") or "en"), probe)
                finally:
                    _LETZTE = time.monotonic()
        except torch.cuda.OutOfMemoryError:
            torch.cuda.empty_cache()
            return self._json(500, {"error": "Zu wenig Grafikspeicher (VRAM)."})
        except Exception as e:
            return self._json(500, {"error": f"{type(e).__name__}: {e}"})
        self.send_response(200)
        self.send_header("Content-Type", "audio/wav")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *a):   # kein Zugriffsprotokoll je Satz
        pass


def pruefen() -> int:
    t = time.time()
    laden()
    print(f"Modell geladen in {time.time() - t:.0f} s, Gerät: {DEVICE}", flush=True)
    t = time.time()
    wav = sprechen("Hallo, das ist ein kurzer Test der lokalen Stimme.", "de")
    dauer = time.time() - t
    laenge = (len(wav) - 44) / 2 / MODEL.sr
    print(f"Probesatz: {laenge:.1f} s Audio in {dauer:.1f} s", flush=True)
    return 0


def _waechter(idle_s: int):
    while True:
        time.sleep(15)
        if not _RECHNET.locked() and time.monotonic() - _LETZTE > idle_s:
            print(f"{idle_s} s ohne Anfrage — beende mich", flush=True)
            os._exit(0)


class Server(ThreadingHTTPServer):
    daemon_threads = True


def main() -> int:
    global _LETZTE
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8791)
    ap.add_argument("--idle", type=int, default=0, help="Sekunden ohne Anfrage bis zum Selbst-Ende")
    ap.add_argument("--pruefen", action="store_true")
    a = ap.parse_args()
    if a.pruefen:
        return pruefen()
    laden()
    srv = Server(("127.0.0.1", a.port), Handler)
    _LETZTE = time.monotonic()
    if a.idle:
        threading.Thread(target=_waechter, args=(a.idle,), daemon=True).start()
    print(f"bereit auf Port {a.port} ({DEVICE})", flush=True)
    srv.serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
