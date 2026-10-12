"""Lokale Stimme — Chatterbox Multilingual V3 auf dem eigenen Rechner.

Statt Gemini TTS liest ein Modell vor, das hier läuft: kein Kontingent, keine
Kosten, kein Text verlässt den Rechner. Der Preis ist Grafikspeicher: beim
Vorlesen belegt das Modell gemessen 3,7 GB VRAM (RTX 3070 Ti). Darum ist es
standardmäßig aus und muss unter ⚙ → Vorlesen ausdrücklich eingeschaltet
werden (tts.engine = "lokal"); erst dann lässt es sich installieren.

Aufbau wie bei Bonsai (bonsai.py): der Dienst (tts_lokal_worker.py) läuft in
einer eigenen venv (VENV, torch + chatterbox, ~6 GB), weil CONSTRUCTs Python
dafür meist zu neu ist und die Abhängigkeiten nicht in CONSTRUCT gehören.
  - gestartet wird er erst beim ersten Vorlesen,
  - vorher prüft start(), ob genug VRAM frei ist — sonst bricht er mitten im
    Laden ab, und das sieht man nur im Log,
  - ein Wächter beendet ihn nach IDLE_S Sekunden ohne Anfrage (nie mitten in
    einer), dann ist der VRAM wieder frei,
  - mit CONSTRUCT geht er mit (stop() beim Herunterfahren, plus PDEATHSIG).
"""
import ctypes
import json
import os
import shutil
import signal
import subprocess
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

from server.config import BASE_DIR

VENV = Path(os.path.expanduser(os.environ.get("CONSTRUCT_TTS_VENV") or BASE_DIR / ".venv-tts"))
PORT = int(os.environ.get("CONSTRUCT_TTS_PORT", "8791"))
IDLE_S = int(os.environ.get("CONSTRUCT_TTS_IDLE_MIN", "10")) * 60
WORKER = Path(__file__).with_name("tts_lokal_worker.py")
LOG = BASE_DIR / "tts-lokal.log"
MARKER = VENV / ".construct-ok"   # erst nach erfolgreicher Prüfung: gilt als installiert
# Fester Stand statt „neueste Version“: V3 gibt es (noch) nur im Repository,
# nicht auf PyPI — und ein neuer Stand soll nicht still mitkommen.
PAKET = ("chatterbox-tts @ git+https://github.com/resemble-ai/chatterbox"
         "@5de7a54aa4e5e2baadb0182dde554908b48b85c2")
PYTHON_VERSION = "3.11"   # damit hat Resemble das Paket entwickelt und getestet
VRAM_GB = 4.0             # gemessen 3,7 GB Spitze, plus Luft
DOWNLOAD_GB = 9           # ~6 GB Umgebung (torch mit CUDA) + ~3 GB Modell

_LOCK = threading.Lock()
_ZAEHLER = threading.Lock()
_PROC = None          # laufender Dienst (subprocess.Popen) oder None
_LAST_USED = 0.0
_IN_FLIGHT = 0        # Anfragen, die gerade rechnen
_WATCHDOG = None
_GERAET = ""          # vom Dienst gemeldet: cuda / mps / cpu


class TTSLokalError(Exception):
    """Verständlicher Fehler; wird dem Nutzer so angezeigt."""


# ---------- Zustand ----------
def python_bin() -> Path:
    return VENV / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def installiert() -> bool:
    return python_bin().is_file() and MARKER.is_file()


_GPU = {"t": 0.0, "info": None}


def gpu() -> dict:
    """Erste NVIDIA-Karte laut nvidia-smi: Name, VRAM gesamt/frei in GB.
    {} ohne NVIDIA-Treiber — dann rechnet das Modell auf dem Prozessor."""
    if time.monotonic() - _GPU["t"] < 10 and _GPU["info"] is not None:
        return _GPU["info"]
    info = {}
    smi = shutil.which("nvidia-smi")
    if smi:
        try:
            out = subprocess.run(
                [smi, "--query-gpu=name,memory.total,memory.free",
                 "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=5).stdout.strip().splitlines()
            name, total, free = [x.strip() for x in out[0].split(",")]
            info = {"name": name, "total_gb": round(int(total) / 1024, 1),
                    "free_gb": round(int(free) / 1024, 1)}
        except Exception:
            info = {}
    _GPU.update(t=time.monotonic(), info=info)
    return info


def _get(path: str, timeout=2):
    with urllib.request.urlopen(f"http://127.0.0.1:{PORT}{path}", timeout=timeout) as r:
        return json.load(r)


def reachable() -> bool:
    """Antwortet auf dem Port wirklich unser Dienst (nicht irgendein anderer)?"""
    global _GERAET
    try:
        h = _get("/health")
    except Exception:
        return False
    if h.get("chatterbox"):
        _GERAET = str(h.get("device") or "")
        return True
    return False


def running() -> bool:
    return _PROC is not None and _PROC.poll() is None


def touch():
    global _LAST_USED
    _LAST_USED = time.monotonic()


def status() -> dict:
    laeuft = running()
    return {"installiert": installiert(), "laeuft": laeuft,
            "geraet": _GERAET if laeuft else "", "gpu": gpu(), "vram_gb": VRAM_GB,
            "download_gb": DOWNLOAD_GB, "idle_min": IDLE_S // 60,
            "install": install_state()}


# ---------- Start / Stop ----------
def _preexec():
    # Stirbt CONSTRUCT hart, nimmt der Kernel den Dienst mit — sonst hielte ein
    # verwaister Prozess den VRAM, ohne dass jemand ihn sieht.
    try:
        ctypes.CDLL("libc.so.6", use_errno=True).prctl(1, signal.SIGTERM)  # PR_SET_PDEATHSIG
    except Exception:
        pass


def _env() -> dict:
    # Fortschrittsbalken (tqdm) je Satz würden das Log fluten.
    return dict(os.environ, TQDM_DISABLE="1", HF_HUB_DISABLE_PROGRESS_BARS="1",
                PYTHONUNBUFFERED="1")


def start(wait_s=300) -> str:
    """Dienst starten und auf /health warten; "" bei Erfolg, sonst Fehlertext.
    wait_s großzügig: beim allerersten Start lädt er das Modell herunter."""
    global _PROC
    with _LOCK:
        if running() and reachable():
            touch()
            return ""
        if not installiert():
            return ("Die lokale Stimme ist noch nicht installiert — "
                    "⚙ Einstellungen → Vorlesen → Installieren.")
        if reachable():
            # Läuft schon, etwa von einer zweiten CONSTRUCT-Instanz: mitbenutzen,
            # aber nicht verwalten.
            touch()
            return ""
        g = gpu()
        if g and g["free_gb"] < VRAM_GB:
            return (f"Zu wenig freier Grafikspeicher für die lokale Stimme: "
                    f"{g['free_gb']:.1f} GB frei, gebraucht werden etwa {VRAM_GB:.0f} GB. "
                    "Läuft gerade Bonsai, ein Spiel oder ein anderes KI-Modell?")
        log = open(LOG, "ab")
        try:
            _PROC = subprocess.Popen(
                [str(python_bin()), "-I", str(WORKER), "--port", str(PORT)],
                env=_env(), stdout=log, stderr=subprocess.STDOUT, cwd=str(VENV),
                preexec_fn=_preexec if os.name == "posix" else None)
        except Exception as e:
            return f"Die lokale Stimme ließ sich nicht starten: {type(e).__name__}: {e}"
        finally:
            log.close()
        print(f"[tts-lokal] starte auf Port {PORT}", flush=True)
        t0 = time.time()
        while time.time() - t0 < wait_s:
            if _PROC.poll() is not None:
                return ("Die lokale Stimme ist beim Start abgebrochen — meist zu wenig "
                        f"freier Grafikspeicher. Details: {LOG}")
            if reachable():
                touch()
                _ensure_watchdog()
                print(f"[tts-lokal] bereit nach {time.time() - t0:.1f}s ({_GERAET})", flush=True)
                return ""
            time.sleep(0.5)
        _stop()
        return f"Die lokale Stimme antwortet nach {wait_s}s nicht."


def _stop():
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
    print("[tts-lokal] gestoppt — VRAM frei", flush=True)


def stop():
    with _LOCK:
        _stop()


def _ensure_watchdog():
    global _WATCHDOG
    if _WATCHDOG and _WATCHDOG.is_alive():
        return

    def loop():
        while True:
            time.sleep(20)
            if not running() or _IN_FLIGHT or time.monotonic() - _LAST_USED < IDLE_S:
                continue
            with _LOCK:
                if not _IN_FLIGHT:
                    _stop()

    _WATCHDOG = threading.Thread(target=loop, daemon=True, name="tts-lokal-watchdog")
    _WATCHDOG.start()


# ---------- Vorlesen ----------
def synthesize(text: str, lang: str, probe: str = "") -> bytes:
    """Ein Stück Text → WAV. probe = absoluter Pfad der Stimmprobe, "" = eingebaute Stimme."""
    global _IN_FLIGHT
    err = start()
    if err:
        raise TTSLokalError(err)
    with _ZAEHLER:
        _IN_FLIGHT += 1
    try:
        req = urllib.request.Request(
            f"http://127.0.0.1:{PORT}/tts",
            data=json.dumps({"text": text, "lang": lang, "probe": probe}).encode(),
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=300) as r:
            return r.read()
    except urllib.error.HTTPError as e:
        try:
            msg = json.loads(e.read()).get("error") or str(e)
        except Exception:
            msg = str(e)
        raise TTSLokalError(msg) from None
    except Exception as e:
        raise TTSLokalError(f"Lokale Stimme nicht erreichbar: {type(e).__name__}: {e}") from None
    finally:
        with _ZAEHLER:
            _IN_FLIGHT -= 1
        touch()


# ---------- Installation (nur auf Klick, nur wenn eingeschaltet) ----------
_INSTALL = {"running": False, "done": True, "log": [], "error": "", "t": 0.0}
_INSTALL_LOCK = threading.Lock()


def install_state() -> dict:
    st = dict(_INSTALL)
    st["log"] = list(st["log"])[-40:]
    return st


def _uv() -> str:
    for c in (shutil.which("uv"), Path.home() / ".local/bin/uv", Path.home() / ".cargo/bin/uv"):
        if c and Path(c).is_file():
            return str(c)
    return ""


def _schritte() -> list[list[str]]:
    """Befehle der Installation. Mit uv: das holt sich passendes Python selbst.
    Ohne: ein vorhandenes Python ab 3.10 (torch gibt es für 3.10–3.14)."""
    py = str(python_bin())
    uv = _uv()
    if uv:
        return [[uv, "venv", "--allow-existing", "-p", PYTHON_VERSION, str(VENV)],
                [uv, "pip", "install", "--python", py, PAKET]]
    for name in ("python3.11", "python3.12", "python3.13", "python3.10", "python3.14", "python3"):
        exe = shutil.which(name)
        if not exe:
            continue
        ok = subprocess.run([exe, "-c", "import sys; print(sys.version_info >= (3, 10))"],
                            capture_output=True, text=True, timeout=20).stdout.strip()
        if ok == "True":
            return [[exe, "-m", "venv", str(VENV)],
                    [py, "-m", "pip", "install", "--upgrade", "pip"],
                    [py, "-m", "pip", "install", PAKET]]
    raise RuntimeError("Kein passendes Python gefunden (ab 3.10) und kein uv. "
                       "Am einfachsten uv installieren: https://docs.astral.sh/uv/")


def install_start() -> dict:
    with _INSTALL_LOCK:
        if _INSTALL["running"]:
            return {"ok": True, "already": True}
        _INSTALL.update(running=True, done=False, log=[], error="", t=time.time())

    def log(line: str):
        _INSTALL["log"].append(line.rstrip()[:400])

    def run(cmd: list[str]):
        log("» " + " ".join(Path(c).name if i == 0 else c for i, c in enumerate(cmd)))
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True, env=_env(), cwd=str(BASE_DIR))
        for line in proc.stdout:
            if line.strip():
                log(line.strip())
        proc.wait()
        if proc.returncode != 0:
            raise RuntimeError(f"{Path(cmd[0]).name} beendet mit Code {proc.returncode}")

    def worker():
        try:
            if not shutil.which("git"):
                raise RuntimeError("git fehlt — Chatterbox wird direkt aus dem Repository geladen.")
            stop()   # ein laufender Dienst hielte Dateien der venv offen
            MARKER.unlink(missing_ok=True)
            for cmd in _schritte():
                run(cmd)
            log("» Modell laden (beim ersten Mal ~3 GB) und Probesatz sprechen …")
            run([str(python_bin()), "-I", str(WORKER), "--pruefen"])
            MARKER.write_text(PAKET + "\n", encoding="utf-8")
            log("✓ fertig")
        except Exception as e:
            _INSTALL["error"] = str(e) if isinstance(e, RuntimeError) else f"{type(e).__name__}: {e}"
            log("!! " + _INSTALL["error"])
        finally:
            _INSTALL.update(running=False, done=True)

    threading.Thread(target=worker, daemon=True, name="tts-lokal-install").start()
    return {"ok": True}
