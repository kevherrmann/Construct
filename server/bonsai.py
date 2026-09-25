"""Bonsai (lokal) — ein llama-server aus dem Bonsai-Demo als Anbieter.

Warum nicht über Ollama: Die Bonsai-Modelle von PrismML liegen in eigenen
Formaten (PQ2_0, Q1_0), die nur deren llama.cpp-Fork kennt — Ollama lädt sie
nicht. Der `llama-server` aus dem Bonsai-Demo spricht aber dieselbe OpenAI-API
wie Ollama, also fährt Hermes ihn genauso: als eigener Anbieter unter dem
Schlüssel `bonsai` (Hermes-Modell-ID `custom:bonsai:<modell>`).

Der Server läuft NICHT dauernd. Er belegt ~5–6 GB VRAM, die auf einer
8-GB-Karte sonst nichts anderem bleiben. Darum:
  - gestartet wird er erst, wenn eine Sitzung ihn wirklich braucht
    (ensure_running() aus app.py, unmittelbar vor dem Prompt),
  - ein Wächter beendet ihn nach IDLE_S Sekunden ohne Anfrage — aber nur,
    wenn gerade kein Slot arbeitet (/slots), sonst würde ein langer Lauf
    mittendrin sterben,
  - mit CONSTRUCT geht er mit (stop() beim Herunterfahren, plus PDEATHSIG,
    falls CONSTRUCT hart stirbt).

Ablage: BONSAI_DIR (Standard ~/projects/Bonsai-demo) mit bin/<backend>/ und
models/. Das Modell wird gesucht, nicht fest verdrahtet — wer ein anderes
Bonsai herunterlädt, muss hier nichts ändern.
"""
import ctypes
import glob
import json
import os
import signal
import subprocess
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

BONSAI_DIR = Path(os.path.expanduser(os.environ.get("BONSAI_DIR") or "~/projects/Bonsai-demo"))
PORT = int(os.environ.get("BONSAI_PORT", "8790"))
BASE_URL = f"http://127.0.0.1:{PORT}/v1"
# Kontext: Hermes weist Modelle unter 64K Kontext ab (MINIMUM_CONTEXT_LENGTH,
# fest im Code). Das 8B kostet ~140 KiB/Token KV-Cache in FP16 — 64K wären
# 9 GB. Mit 4-Bit-Cache (unten) ~41 KiB/Token: 64K ≈ 2,7 GB + 2 GB Gewichte
# + Puffer ≈ 5,5 GB. Das ist der Preis für Hermes auf einer 8-GB-Karte; 4-Bit
# kostet etwas Genauigkeit bei langen Gesprächen, ist für ein 8B aber üblich.
CTX = int(os.environ.get("BONSAI_CTX", "65536"))
KV_TYPE = os.environ.get("BONSAI_KV", "q4_0")
IDLE_S = int(os.environ.get("BONSAI_IDLE_MIN", "10")) * 60
HERMES_KEY = "bonsai"   # providers.<key> in Hermes' config.yaml

_LOCK = threading.Lock()
_PROC = None            # laufender llama-server (subprocess.Popen) oder None
_LAST_USED = 0.0
_WATCHDOG = None


# ---------- Dateien finden ----------
def _backend_dir():
    for b in ("cuda", "rocm", "hip", "vulkan", "cpu"):
        d = BONSAI_DIR / "bin" / b
        if (d / "llama-server").is_file():
            return d
    return None


def server_bin():
    d = _backend_dir()
    return str(d / "llama-server") if d else ""


def model_file() -> str:
    """Neuestes Modell unter models/ (Projektoren und Drafter ausgenommen)."""
    cands = [p for p in glob.glob(str(BONSAI_DIR / "models" / "*" / "*" / "*.gguf"))
             if "mmproj" not in p and "dspark" not in p]
    return max(cands, key=os.path.getmtime) if cands else ""


def model_name() -> str:
    """Anzeigename = Dateiname ohne Quantisierungs-Suffix (Ternary-Bonsai-8B)."""
    stem = Path(model_file()).stem
    for suf in ("-PQ2_0", "-Q2_0", "-Q1_0", "-g64"):
        if stem.endswith(suf):
            stem = stem[: -len(suf)]
    return stem


def available() -> bool:
    return bool(server_bin() and model_file())


def _env() -> dict:
    """Die vorgebauten Binaries bringen die CUDA-Runtime nicht mit; die liegt
    (per pip) in der venv des Demos. Ohne LD_LIBRARY_PATH: libcudart fehlt."""
    env = dict(os.environ)
    libs = [str(_backend_dir())]
    libs += glob.glob(str(BONSAI_DIR / ".venv" / "lib" / "python*" / "site-packages"
                          / "nvidia" / "*" / "lib"))
    old = env.get("LD_LIBRARY_PATH", "")
    env["LD_LIBRARY_PATH"] = ":".join(libs + ([old] if old else []))
    return env


# ---------- Zustand ----------
def _get(path: str, timeout=2):
    with urllib.request.urlopen(f"http://127.0.0.1:{PORT}{path}", timeout=timeout) as r:
        return json.load(r)


def reachable() -> bool:
    try:
        return (_get("/health") or {}).get("status") == "ok"
    except Exception:
        return False


def busy() -> bool:
    """Arbeitet gerade ein Slot? Unbekannt (Fehler) zählt als beschäftigt —
    lieber einmal zu lange leben als einen Lauf abschießen."""
    try:
        return any(s.get("is_processing") for s in _get("/slots"))
    except Exception:
        return True


def running() -> bool:
    return _PROC is not None and _PROC.poll() is None


def touch():
    global _LAST_USED
    _LAST_USED = time.monotonic()


def status() -> dict:
    return {"available": available(), "running": running(), "model": model_name(),
            "vram": running(), "idle_min": IDLE_S // 60}


# ---------- Start / Stop ----------
def _preexec():
    # Stirbt CONSTRUCT hart (kill -9, Absturz), nimmt der Kernel den Server mit —
    # sonst hielte ein verwaister Prozess die GPU, ohne dass jemand ihn sieht.
    try:
        libc = ctypes.CDLL("libc.so.6", use_errno=True)
        libc.prctl(1, signal.SIGTERM)   # PR_SET_PDEATHSIG
    except Exception:
        pass


def start(wait_s=120) -> str:
    """llama-server starten und auf /health warten; "" bei Erfolg, sonst Fehlertext."""
    global _PROC
    with _LOCK:
        if running() and reachable():
            touch()
            return ""
        if not available():
            return (f"Bonsai nicht gefunden unter {BONSAI_DIR} — Bonsai-Demo "
                    "einrichten (setup.sh) oder BONSAI_DIR setzen.")
        if reachable():
            # Fremder Server auf unserem Port (z.B. von Hand gestartet): nutzen,
            # aber nicht verwalten.
            touch()
            return ""
        model = model_file()
        cmd = [server_bin(), "-m", model, "--host", "127.0.0.1", "--port", str(PORT),
               "-ngl", "99", "-fa", "on", "-c", str(CTX),
               # EIN Slot: llama-server teilt den Kontext sonst auf 4 parallele
               # Slots auf, und ein Agent bekäme nur ein Viertel.
               "-np", "1", "--slots", "--jinja", "-a", model_name(),
               "--cache-type-k", KV_TYPE, "--cache-type-v", KV_TYPE,
               # Sampling wie im Bonsai-Demo; Denken aus — im Werkzeug-Betrieb
               # wären die Denk-Token nur Wartezeit.
               "--temp", "0.5", "--top-p", "0.85", "--top-k", "20", "--min-p", "0",
               "--reasoning-budget", "0", "--reasoning-format", "none",
               "--chat-template-kwargs", '{"enable_thinking": false}']
        log = open(BONSAI_DIR / "server.log", "ab")
        try:
            _PROC = subprocess.Popen(cmd, env=_env(), stdout=log, stderr=subprocess.STDOUT,
                                     cwd=str(BONSAI_DIR), preexec_fn=_preexec)
        except Exception as e:
            return f"llama-server ließ sich nicht starten: {type(e).__name__}: {e}"
        print(f"[bonsai] starte {Path(model).name} auf Port {PORT}", flush=True)
        t0 = time.time()
        while time.time() - t0 < wait_s:
            if _PROC.poll() is not None:
                return ("llama-server ist beim Start abgebrochen (Log: "
                        f"{BONSAI_DIR / 'server.log'}) — meist zu wenig freier VRAM.")
            if reachable():
                touch()
                _ensure_watchdog()
                print(f"[bonsai] bereit nach {time.time() - t0:.1f}s", flush=True)
                return ""
            time.sleep(0.5)
        stop()
        return f"llama-server antwortet nach {wait_s}s nicht."


def stop():
    global _PROC
    p = _PROC
    _PROC = None
    if p is None or p.poll() is not None:
        return
    p.terminate()
    try:
        p.wait(10)
    except subprocess.TimeoutExpired:
        p.kill()
    print("[bonsai] gestoppt — VRAM frei", flush=True)


def ensure_running() -> str:
    """Vor jedem Prompt: läuft er, nur berühren; sonst starten."""
    if running() and reachable():
        touch()
        return ""
    return start()


def _ensure_watchdog():
    global _WATCHDOG
    if _WATCHDOG and _WATCHDOG.is_alive():
        return

    def loop():
        while True:
            time.sleep(30)
            if not running():
                continue
            if time.monotonic() - _LAST_USED < IDLE_S:
                continue
            if busy():
                touch()      # ein Lauf hängt noch drin — Uhr neu stellen
                continue
            with _LOCK:
                stop()

    _WATCHDOG = threading.Thread(target=loop, daemon=True, name="bonsai-watchdog")
    _WATCHDOG.start()


# ---------- Hermes ----------
def acp_model_id(model: str) -> str:
    """CONSTRUCT-Wert "bonsai:<modell>" → Hermes-ID "custom:bonsai:<modell>"."""
    return f"custom:{HERMES_KEY}:{model}"


def ensure_hermes_provider(hermes_bin: str, hermes_env: dict) -> str:
    """providers.bonsai in Hermes' config.yaml eintragen — über `hermes config set`,
    weil Hermes die Datei selbst verwaltet (eigenes Layout, eigene Prüfungen);
    sie fremd zu beschreiben hieße, ihm ins Handwerk zu pfuschen.
    Idempotent: steht alles schon richtig drin, passiert nichts."""
    want = {"base_url": BASE_URL, "api_key": "local", "name": "Bonsai (lokal)",
            "model": model_name()}
    try:
        cur = subprocess.run([hermes_bin, "config", "get", f"providers.{HERMES_KEY}"],
                             capture_output=True, text=True, timeout=20, env=hermes_env).stdout
    except Exception:
        cur = ""
    if all(f"{k}: {v}" in cur for k, v in want.items() if k != "api_key"):
        return ""
    for k, v in want.items():
        r = subprocess.run([hermes_bin, "config", "set", f"providers.{HERMES_KEY}.{k}", v],
                           capture_output=True, text=True, timeout=20, env=hermes_env)
        if r.returncode != 0:
            return f"Hermes-Konfiguration: {(r.stderr or r.stdout).strip()[-300:]}"
    print(f"[bonsai] Hermes-Anbieter providers.{HERMES_KEY} eingetragen", flush=True)
    return ""
