"""
Externe KI-Anbieter für CONSTRUCT — ChatGPT (OpenAI), Gemini, DeepSeek,
Ollama (lokal) und beliebige OpenAI-kompatible APIs ("custom").

Alle Anbieter sprechen das OpenAI-Chat-Completions-Format (Gemini über Googles
Kompatibilitäts-Endpoint, Ollama über /v1) — dadurch reicht EIN Client für alles.
Diese Modelle sind reine Chat-Modelle: kein Tool-/Datei-/Terminal-Zugriff.
Dafür bleibt Claude zuständig (app.py, run_claude).

Konfiguration (API-Keys, URLs) liegt in .llm-config.json (chmod 600).
Gespräche liegen als eigene Dateien in llm_sessions/ (eine JSON pro Session),
damit sie wie Claude-Sessions gelistet, fortgesetzt und gelöscht werden können.
Modell-Wert im Frontend/API: "anbieter:modell", z.B. "openai:gpt-4o" oder
"ollama:gemma3:12b" (nur der ERSTE Doppelpunkt trennt).
"""
import json
import os
import platform
import re
import shutil
import subprocess
import tarfile
import threading
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

import config as cfg  # Ausbaustufe (voll/lite) + Namen

BASE_DIR = Path(__file__).parent
CONFIG_FILE = BASE_DIR / ".llm-config.json"
SESS_DIR = BASE_DIR / "llm_sessions"
SESS_DIR.mkdir(exist_ok=True)

# Anzeige-Gruppe in der Session-Liste (die UI gruppiert nach cwd)
SESS_GROUP = "KI-Chats (extern)"

PROVIDERS = {
    "openai": {
        "label": "ChatGPT (OpenAI)",
        "base_url": "https://api.openai.com/v1",
        "needs_key": True,
        "fallback_models": ["gpt-5.1", "gpt-5.1-mini", "gpt-4o", "gpt-4o-mini"],
        "hint": "API-Key von platform.openai.com → API keys",
    },
    "gemini": {
        "label": "Gemini (Google)",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
        "needs_key": True,
        "fallback_models": ["gemini-2.5-pro", "gemini-2.5-flash", "gemini-2.5-flash-lite"],
        "hint": "API-Key von aistudio.google.com/apikey (kostenloses Kontingent vorhanden)",
    },
    "deepseek": {
        "label": "DeepSeek",
        "base_url": "https://api.deepseek.com/v1",
        "needs_key": True,
        "fallback_models": ["deepseek-chat", "deepseek-reasoner"],
        "hint": "API-Key von platform.deepseek.com",
    },
    "ollama": {
        "label": "Ollama (lokal)",
        "base_url": "http://127.0.0.1:11434/v1",
        "needs_key": False,
        "fallback_models": [],
        "hint": "Lokale Modelle (Gemma & Co.) — Ollama muss laufen (Port 11434)",
    },
    "custom": {
        "label": "Eigener Anbieter",
        "base_url": "",
        "needs_key": False,
        "fallback_models": [],
        "hint": "Beliebige OpenAI-kompatible API — z.B. OpenRouter, Groq, Mistral, vLLM",
    },
}

# Zusatz-Systemprompt: die Persona (SOUL.md) erzählt von Tools/Kalender-CLI —
# das muss für Chat-only-Modelle ausdrücklich zurückgenommen werden. Sonst
# behauptet das Modell, es habe gerade einen Termin eingetragen.
def no_tools_note(model: str, has_claude: bool = True) -> str:
    """Der Ausweg-Satz hängt daran, ob Claude Code installiert IST.

    Ohne installiertes CLI auf „wähl ein Claude-Modell“ zu verweisen, schickt
    den Nutzer zu einem Menüeintrag, der bei ihm nur in einen Fehler läuft.
    """
    who = cfg.USER_NAME
    base = (f"[Modus-Hinweis: Du läufst gerade als externes Modell ({model}) in "
            f"CONSTRUCT — als REINES Chat-Modell ohne Werkzeuge. Du hast KEINEN "
            f"Zugriff auf Dateien, Terminal, Kalender, E-Mails oder Skills und "
            f"kannst nichts davon ausführen. ")
    if has_claude:
        tail = (f"Wenn {who} so etwas braucht, sag kurz, dass dafür oben im "
                f"🧠-Menü ein Claude-Modell nötig ist. ")
    else:
        tail = (f"Wenn {who} so etwas braucht, sag ehrlich, dass du das hier nicht "
                f"kannst — Termine trägt {who} selbst unter „📅 Kalender“ ein. ")
    return base + tail + "Antworte in Markdown.]"


class LLMError(Exception):
    """Verständlicher Anbieter-Fehler (wird dem Nutzer 1:1 angezeigt)."""


# ---------- Konfiguration ----------
def load_config() -> dict:
    try:
        d = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def save_config(cfg: dict):
    tmp = CONFIG_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.chmod(0o600)
    tmp.replace(CONFIG_FILE)


def save_provider(pid: str, api_key=None, base_url=None, enabled=None):
    """Teil-Update: leerer Key lässt den gespeicherten Key unangetastet."""
    cfg = load_config()
    c = cfg.setdefault(pid, {})
    if api_key is not None and str(api_key).strip():
        c["api_key"] = str(api_key).strip()
    if base_url is not None:
        b = str(base_url).strip().rstrip("/")
        if b:
            c["base_url"] = b
        else:
            c.pop("base_url", None)
    if enabled is not None:
        c["enabled"] = bool(enabled)
    save_config(cfg)
    _MODEL_CACHE.pop(pid, None)


def provider_conf(pid: str) -> dict:
    meta = PROVIDERS[pid]
    c = load_config().get(pid) or {}
    return {
        "label": meta["label"],
        "needs_key": meta["needs_key"],
        "base_url": c.get("base_url") or meta["base_url"],
        "api_key": c.get("api_key") or "",
        "enabled": c.get("enabled"),
    }


def is_configured(pid: str) -> bool:
    meta = PROVIDERS[pid]
    c = load_config().get(pid) or {}
    if c.get("enabled") is False:
        return False
    if meta["needs_key"]:
        return bool(c.get("api_key"))
    if pid == "ollama":
        return c.get("enabled") is True
    if pid == "custom":
        return bool(c.get("base_url"))
    return False


def split_model(value: str):
    """"openai:gpt-4o" -> ("openai", "gpt-4o"); Claude-Werte -> (None, "")."""
    if ":" in (value or ""):
        pid, m = value.split(":", 1)
        if pid in PROVIDERS and m:
            return pid, m
    return None, ""


# ---------- Modell-Listen (live vom Anbieter, gecacht) ----------
_MODEL_CACHE = {}  # pid -> (zeitstempel, models, error)
_CACHE_TTL = 300

# Nicht-Chat-Modelle (Embeddings, Bild, Audio …) und Datums-Snapshots ausblenden
_OPENAI_SKIP = re.compile(
    r"(embed|whisper|tts|dall-e|davinci|babbage|audio|realtime|moderation|"
    r"transcribe|image|search|codex|computer-use|-\d{4}-\d{2}-\d{2})", re.I)
_GEMINI_SKIP = re.compile(r"(embed|imagen|veo|tts|image|audio|live|aqa|learnlm|robotics)", re.I)


def _filter_models(pid: str, ids):
    ids = [i[len("models/"):] if i.startswith("models/") else i for i in ids]
    if pid == "openai":
        ids = [i for i in ids if re.match(r"^(gpt-|o\d|chatgpt)", i) and not _OPENAI_SKIP.search(i)]
    elif pid == "gemini":
        ids = [i for i in ids if "gemini" in i and not _GEMINI_SKIP.search(i)]
    seen, out = set(), []
    for i in ids:
        if i and i not in seen:
            seen.add(i)
            out.append(i)
    out.sort()
    return out[:40]


def list_remote_models(pid: str, force=False):
    """(models, error) — GET {base}/models beim Anbieter, 5 min gecacht."""
    now = time.time()
    cached = _MODEL_CACHE.get(pid)
    if cached and not force and now - cached[0] < _CACHE_TTL:
        return cached[1], cached[2]
    c = provider_conf(pid)
    base = (c["base_url"] or "").rstrip("/")
    if not base:
        return [], "keine URL konfiguriert"
    headers = {}
    if c["api_key"]:
        headers["Authorization"] = "Bearer " + c["api_key"]
    models, err = [], ""
    try:
        req = urllib.request.Request(base + "/models", headers=headers)
        with urllib.request.urlopen(req, timeout=8) as r:
            data = json.load(r)
        models = _filter_models(pid, [m.get("id", "") for m in (data.get("data") or [])
                                      if isinstance(m, dict)])
    except Exception as e:
        err = _short_error(pid, e)
    _MODEL_CACHE[pid] = (now, models, err)
    return models, err


def public_providers(force=False):
    """Anbieter-Liste fürs Frontend — OHNE Keys (nur key_set-Flag)."""
    out = []
    for pid, meta in PROVIDERS.items():
        c = provider_conf(pid)
        configured = is_configured(pid)
        entry = {
            "id": pid,
            "label": meta["label"],
            "hint": meta["hint"],
            "needs_key": meta["needs_key"],
            "key_set": bool(c["api_key"]),
            "base_url": c["base_url"],
            "default_base": meta["base_url"],
            "configured": configured,
            "models": [],
            "error": "",
        }
        if configured:
            models, err = list_remote_models(pid, force)
            entry["models"] = models or meta["fallback_models"]
            entry["error"] = err
        out.append(entry)
    return out


# ---------- Chat (Streaming) ----------
def chat_request(pid: str, model: str, messages, timeout=300):
    """Öffnet den Streaming-Request; gibt das Response-Objekt zurück
    (close() darauf bricht den Stream ab — für den Stop-Button)."""
    c = provider_conf(pid)
    base = (c["base_url"] or "").rstrip("/")
    if not base:
        raise LLMError("Keine URL konfiguriert — unter 🧠 → „⚙ KI-Anbieter“ einrichten.")
    if c["needs_key"] and not c["api_key"]:
        raise LLMError("Kein API-Key hinterlegt — unter 🧠 → „⚙ KI-Anbieter“ einrichten.")
    body = {"model": model, "messages": messages, "stream": True}
    if pid in ("openai", "deepseek"):
        body["stream_options"] = {"include_usage": True}   # Token-Zahlen im letzten Chunk
    headers = {"Content-Type": "application/json", "Accept": "text/event-stream"}
    if c["api_key"]:
        headers["Authorization"] = "Bearer " + c["api_key"]
    req = urllib.request.Request(base + "/chat/completions",
                                 data=json.dumps(body, ensure_ascii=False).encode(),
                                 headers=headers)
    return urllib.request.urlopen(req, timeout=timeout)


def iter_stream(resp):
    """SSE-Chunks -> Events: {"type":"text"|"reasoning"|"usage", ...}."""
    try:
        for raw in resp:
            line = raw.decode("utf-8", "replace").strip()
            if not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if data == "[DONE]":
                break
            try:
                ch = json.loads(data)
            except Exception:
                continue
            if ch.get("error"):
                e = ch["error"]
                raise LLMError(str(e.get("message") if isinstance(e, dict) else e))
            u = ch.get("usage")
            if u:
                yield {"type": "usage",
                       "in": u.get("prompt_tokens") or 0,
                       "out": u.get("completion_tokens") or 0}
            for choice in ch.get("choices") or []:
                d = choice.get("delta") or {}
                if d.get("reasoning_content"):        # z.B. deepseek-reasoner
                    yield {"type": "reasoning"}
                if d.get("content"):
                    yield {"type": "text", "text": d["content"]}
    finally:
        try:
            resp.close()
        except Exception:
            pass


def _short_error(pid: str, e: Exception) -> str:
    if isinstance(e, urllib.error.HTTPError):
        return f"HTTP {e.code}"
    if isinstance(e, urllib.error.URLError):
        return "nicht erreichbar" + (" — läuft Ollama?" if pid == "ollama" else "")
    return f"{type(e).__name__}"


def friendly_error(pid: str, e: Exception) -> str:
    """Anbieter-Fehler in einen verständlichen Hinweis übersetzen."""
    label = PROVIDERS.get(pid, {}).get("label", pid)
    if isinstance(e, LLMError):
        return f"⚠ {label}: {e}"
    if isinstance(e, urllib.error.HTTPError):
        detail = ""
        try:
            j = json.loads(e.read().decode("utf-8", "replace"))
            err = j.get("error") or {}
            detail = str(err.get("message") if isinstance(err, dict) else err)
        except Exception:
            pass
        hints = {401: "API-Key ungültig oder fehlt",
                 402: "kein Guthaben mehr auf dem Konto",
                 403: "Zugriff verweigert (Key/Region?)",
                 404: "Modell nicht gefunden — im 🧠-Menü ein anderes wählen",
                 429: "Rate-Limit erreicht oder Kontingent aufgebraucht"}
        h = hints.get(e.code, f"HTTP {e.code}")
        return f"⚠ {label}: {h}." + (f"\n\n{detail[:400]}" if detail else "")
    if isinstance(e, (urllib.error.URLError, ConnectionError, TimeoutError)):
        if pid == "ollama":
            return ("🦙 Ollama nicht erreichbar — läuft es? "
                    f"(Standard: Port 11434)\n\n{getattr(e, 'reason', e)}")
        return f"⚠ {label} nicht erreichbar: {getattr(e, 'reason', e)}"
    return f"⚠ {label}: {type(e).__name__}: {e}"


# ---------- Ollama-Verwaltung: Modelle ansehen, laden (pull), löschen ----------
# Läuft über die NATIVE Ollama-API (ohne /v1): /api/tags, /api/pull, /api/delete.
# Der Katalog ist kuratiert (beliebte Modelle + RAM-Hinweis); alles andere geht
# über die Freitext-Eingabe im Dialog (jeder Name von ollama.com/library).
# Größen/Tags live von ollama.com verifiziert (Stand 07/2026)
OLLAMA_CATALOG = [
    {"name": "gemma4:e2b",       "size": "7,2 GB", "desc": "Google Gemma 4, effiziente Stufe — Reasoning & multimodal"},
    {"name": "gemma4:e4b",       "size": "9,6 GB", "desc": "Google Gemma 4 (Standard) — Frontier-Klasse für lokale Modelle"},
    {"name": "gemma4:12b",       "size": "7,6 GB", "desc": "Gemma 4 12B — stark, ab ~16 GB RAM"},
    {"name": "gemma4:26b",       "size": "18 GB",  "desc": "Gemma 4 26B (MoE) — Topstufe, ab ~32 GB RAM"},
    {"name": "gemma3:4b",        "size": "3,3 GB", "desc": "Gemma 3 — leichter Allrounder, läuft ab ~8 GB RAM"},
    {"name": "gemma3:1b",        "size": "0,8 GB", "desc": "Gemma 3, winzig — läuft praktisch überall"},
    {"name": "qwen3.5:9b",       "size": "6,6 GB", "desc": "Alibaba Qwen 3.5 — aktuelle Generation, multimodal"},
    {"name": "qwen3.5:4b",       "size": "3,4 GB", "desc": "Qwen 3.5, klein & flott"},
    {"name": "qwen3.5:27b",      "size": "17 GB",  "desc": "Qwen 3.5, große Stufe — ab ~32 GB RAM"},
    {"name": "deepseek-r1:8b",   "size": "5,2 GB", "desc": "DeepSeek R1 (destilliert) — Reasoning-Modell, denkt sichtbar nach"},
    {"name": "llama3.1:8b",      "size": "4,9 GB", "desc": "Meta Llama 3.1 — bewährter 8B-Standard"},
    {"name": "qwen2.5-coder:7b", "size": "4,7 GB", "desc": "Coding-Spezialist — Code schreiben, erklären, vervollständigen"},
    {"name": "mistral:7b",       "size": "4,1 GB", "desc": "Mistral 7B — schneller Klassiker aus Frankreich"},
    {"name": "phi4:14b",         "size": "9,1 GB", "desc": "Microsoft Phi-4 — stark in Logik & Mathe für seine Größe"},
]

_OLLAMA_NAME = re.compile(r"^[A-Za-z0-9][\w.\-/:]{1,79}$")


def _ollama_api() -> str:
    """Native Ollama-API aus der konfigurierten OpenAI-URL ableiten (/v1 weg)."""
    base = (provider_conf("ollama")["base_url"] or "").rstrip("/")
    return base[:-3].rstrip("/") if base.endswith("/v1") else base


def ollama_installed():
    """Installierte Modelle mit Größe/Parametern (GET /api/tags)."""
    req = urllib.request.Request(_ollama_api() + "/api/tags")
    with urllib.request.urlopen(req, timeout=8) as r:
        data = json.load(r)
    out = []
    for m in data.get("models") or []:
        det = m.get("details") or {}
        out.append({"name": m.get("name") or m.get("model") or "?",
                    "size": m.get("size") or 0,
                    "param": det.get("parameter_size") or "",
                    "quant": det.get("quantization_level") or ""})
    out.sort(key=lambda x: x["name"])
    return out


def ollama_delete(model: str):
    if not _OLLAMA_NAME.match(model or ""):
        raise LLMError("Ungültiger Modellname")
    req = urllib.request.Request(_ollama_api() + "/api/delete",
                                 data=json.dumps({"model": model}).encode(),
                                 headers={"Content-Type": "application/json"},
                                 method="DELETE")
    urllib.request.urlopen(req, timeout=30).read()
    _MODEL_CACHE.pop("ollama", None)   # Picker-Liste sofort aktuell


# Laufende Downloads: model -> Status. Der Pull läuft in einem Hintergrund-Thread
# weiter, auch wenn der Dialog zu ist — die UI pollt nur den Fortschritt.
_PULLS = {}
_PULLS_LOCK = threading.Lock()


def ollama_pull_start(model: str) -> dict:
    model = (model or "").strip()
    if not _OLLAMA_NAME.match(model):
        raise LLMError("Ungültiger Modellname — z.B. gemma3:4b (siehe ollama.com/library)")
    with _PULLS_LOCK:
        st = _PULLS.get(model)
        if st and not st["done"]:
            return {"ok": True, "already": True}
        st = {"status": "verbinde …", "total": 0, "completed": 0,
              "done": False, "error": "", "resp": None, "cancel": False, "t": time.time()}
        _PULLS[model] = st

    def worker():
        try:
            req = urllib.request.Request(
                _ollama_api() + "/api/pull",
                data=json.dumps({"model": model, "stream": True}).encode(),
                headers={"Content-Type": "application/json"})
            resp = urllib.request.urlopen(req, timeout=120)
            st["resp"] = resp
            for raw in resp:
                try:
                    d = json.loads(raw.decode("utf-8", "replace"))
                except Exception:
                    continue
                if d.get("error"):
                    st["error"] = str(d["error"])
                    break
                st["status"] = d.get("status") or st["status"]
                if d.get("total"):
                    st["total"] = d["total"]
                    st["completed"] = d.get("completed") or 0
                if (d.get("status") or "") == "success":
                    st["completed"] = st["total"]
                    _MODEL_CACHE.pop("ollama", None)
                    break
        except Exception as e:
            if not st["error"]:
                st["error"] = "abgebrochen" if st["cancel"] else friendly_error("ollama", e)
        finally:
            # close() beim Abbruch kann den Stream auch „sauber“ enden lassen —
            # ohne success-Status ist das trotzdem kein fertiger Download
            if not st["error"] and (st["cancel"] or (st["status"] or "") != "success"):
                st["error"] = "abgebrochen" if st["cancel"] else "Verbindung abgerissen"
            st["done"] = True
            st["t"] = time.time()
            try:
                if st["resp"]:
                    st["resp"].close()
            except Exception:
                pass

    threading.Thread(target=worker, daemon=True).start()
    return {"ok": True}


def ollama_pull_cancel(model: str) -> bool:
    st = _PULLS.get(model)
    if not st or st["done"]:
        return False
    st["cancel"] = True
    try:
        if st["resp"]:
            st["resp"].close()   # bricht das blockierende Lesen im Thread ab
    except Exception:
        pass
    return True


def ollama_pulls() -> dict:
    """Fortschritt aller Downloads (Fertige nach 60 s vergessen)."""
    now = time.time()
    with _PULLS_LOCK:
        for k in [k for k, s in _PULLS.items() if s["done"] and now - s["t"] > 60]:
            _PULLS.pop(k)
        return {k: {f: s[f] for f in ("status", "total", "completed", "done", "error")}
                for k, s in _PULLS.items()}


# ---------- Ollama selbst installieren & starten ----------
# Wenn Ollama nicht läuft, kann Cody es komplett selbst besorgen: offizielles
# Linux-Paket laden, nach OLLAMA_DIR entpacken und `ollama serve` als eigenen
# Hintergrundprozess starten (kein Root nötig; Modelle landen in models/).
# OLLAMA_DIR liegt auf /workspace (persistent, überlebt Container-Neustarts).
OLLAMA_DIR = Path("/workspace/.ollama") if os.path.isdir("/workspace") else (Path.home() / ".cody-ollama")
_OLLAMA_PKG_BASE = ("https://ollama.com/download/ollama-linux-"
                    + ("arm64" if platform.machine() in ("aarch64", "arm64") else "amd64"))


def _ollama_pkg_url() -> str:
    """Aktuelle Versionen liefern .tar.zst, ältere .tgz — wie das offizielle
    install.sh erst per HEAD prüfen, dann passend laden."""
    zst = _OLLAMA_PKG_BASE + ".tar.zst"
    try:
        req = urllib.request.Request(zst, method="HEAD")
        with urllib.request.urlopen(req, timeout=15):
            return zst
    except Exception:
        return _OLLAMA_PKG_BASE + ".tgz"


def _extract_pkg(pkg: Path, dest: Path):
    if pkg.name.endswith(".tar.zst"):
        import zstandard
        with open(pkg, "rb") as f:
            with zstandard.ZstdDecompressor().stream_reader(f) as reader:
                with tarfile.open(fileobj=reader, mode="r|") as tf:
                    tf.extractall(dest)
    else:
        with tarfile.open(pkg) as tf:
            tf.extractall(dest)

_INSTALL = {"status": "", "total": 0, "completed": 0, "done": True, "error": "", "t": 0.0}
_INSTALL_LOCK = threading.Lock()


def ollama_bin() -> str:
    p = OLLAMA_DIR / "runtime" / "bin" / "ollama"
    if p.is_file():
        return str(p)
    sys_bin = shutil.which("ollama")
    return sys_bin or ""


def ollama_reachable() -> bool:
    try:
        with urllib.request.urlopen(_ollama_api() + "/api/version", timeout=2):
            return True
    except Exception:
        return False


def _serve_env() -> dict:
    env = dict(os.environ)
    env.setdefault("OLLAMA_HOST", "127.0.0.1:11434")
    env.setdefault("OLLAMA_MODELS", str(OLLAMA_DIR / "models"))
    return env


def ollama_serve_start(wait_s=25) -> str:
    """`ollama serve` im Hintergrund starten; "" bei Erfolg, sonst Fehlertext."""
    binp = ollama_bin()
    if not binp:
        return "Ollama ist nicht installiert"
    if ollama_reachable():
        return ""
    (OLLAMA_DIR / "models").mkdir(parents=True, exist_ok=True)
    log = open(OLLAMA_DIR / "serve.log", "ab")
    try:
        subprocess.Popen([binp, "serve"], stdout=log, stderr=log,
                         env=_serve_env(), start_new_session=True)
    except Exception as e:
        return f"Start fehlgeschlagen: {type(e).__name__}: {e}"
    finally:
        log.close()
    deadline = time.time() + wait_s
    while time.time() < deadline:
        if ollama_reachable():
            return ""
        time.sleep(0.5)
    tail = ""
    try:
        tail = (OLLAMA_DIR / "serve.log").read_bytes()[-400:].decode("utf-8", "replace")
    except Exception:
        pass
    return "Ollama antwortet nicht nach dem Start." + (f"\n\nLog: {tail}" if tail else "")


def ollama_autostart():
    """Beim App-Start: früher installiertes Ollama wieder hochfahren (Container-Neustart)."""
    try:
        if is_configured("ollama") and ollama_bin() and not ollama_reachable():
            base = provider_conf("ollama")["base_url"]
            if "127.0.0.1" in base or "localhost" in base:
                err = ollama_serve_start()
                print(f"[ollama] autostart: {err or 'läuft'}", flush=True)
    except Exception as e:
        print(f"[ollama] autostart-fehler: {type(e).__name__}: {e}", flush=True)


def ollama_install_start() -> dict:
    """Installation im Hintergrund: Download -> Entpacken -> Starten.
    Existiert das Binary schon, wird nur gestartet."""
    with _INSTALL_LOCK:
        if not _INSTALL["done"]:
            return {"ok": True, "already": True}
        _INSTALL.update(status="startet …", total=0, completed=0,
                        done=False, error="", t=time.time())

    def worker():
        st = _INSTALL
        try:
            if not ollama_bin():
                OLLAMA_DIR.mkdir(parents=True, exist_ok=True)
                url = _ollama_pkg_url()
                pkg = OLLAMA_DIR / ("ollama.tar.zst" if url.endswith(".tar.zst") else "ollama.tgz")
                st["status"] = "lade Ollama herunter …"
                req = urllib.request.Request(url)
                with urllib.request.urlopen(req, timeout=60) as r, open(pkg, "wb") as f:
                    st["total"] = int(r.headers.get("Content-Length") or 0)
                    while True:
                        chunk = r.read(1024 * 1024)
                        if not chunk:
                            break
                        f.write(chunk)
                        st["completed"] += len(chunk)
                st["status"] = "entpacke …"
                runtime = OLLAMA_DIR / "runtime"
                runtime.mkdir(parents=True, exist_ok=True)
                _extract_pkg(pkg, runtime)   # offizielles Paket von ollama.com
                pkg.unlink(missing_ok=True)
                binp = runtime / "bin" / "ollama"
                if not binp.is_file():   # manche Pakete legen das Binary flach ab
                    alt = runtime / "ollama"
                    if alt.is_file():
                        binp.parent.mkdir(parents=True, exist_ok=True)
                        alt.rename(binp)
                binp.chmod(0o755)
            st["status"] = "starte Ollama …"
            err = ollama_serve_start()
            if err:
                st["error"] = err
            else:
                st["status"] = "läuft"
                save_provider("ollama", enabled=True)
                _MODEL_CACHE.pop("ollama", None)
        except Exception as e:
            st["error"] = f"Installation fehlgeschlagen: {type(e).__name__}: {e}"
        finally:
            st["done"] = True
            st["t"] = time.time()

    threading.Thread(target=worker, daemon=True).start()
    return {"ok": True}


def ollama_install_status() -> dict:
    st = {f: _INSTALL[f] for f in ("status", "total", "completed", "done", "error")}
    if st["done"] and _INSTALL["t"] and time.time() - _INSTALL["t"] > 120:
        st = None   # alte Meldung nicht ewig anzeigen
    return {"bin": bool(ollama_bin()), "install": st}


# ---------- Sessions (eigene Ablage, analog zu den Claude-.jsonl) ----------
SID_OK = re.compile(r"^llm-[a-f0-9]{8,32}$")


def _spath(sid: str) -> Path:
    return SESS_DIR / (sid + ".json")


def new_session(provider: str, model: str, seed=None) -> dict:
    s = {"id": "llm-" + uuid.uuid4().hex[:20], "provider": provider, "model": model,
         "created": time.time(), "messages": list(seed or [])}
    save_session(s)
    return s


def save_session(s: dict):
    p = _spath(s["id"])
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(s, ensure_ascii=False), encoding="utf-8")
    tmp.replace(p)


def load_session(sid: str):
    if not SID_OK.match(sid or ""):
        return None
    try:
        s = json.loads(_spath(sid).read_text(encoding="utf-8"))
        return s if isinstance(s, dict) and s.get("id") == sid else None
    except Exception:
        return None


def delete_session(sid: str) -> bool:
    if not SID_OK.match(sid or ""):
        return False
    try:
        _spath(sid).unlink()
        return True
    except Exception:
        return False


def append_message(s: dict, role: str, content: str):
    s.setdefault("messages", []).append({"role": role, "content": content, "ts": time.time()})
    save_session(s)


def recent_messages(s: dict, max_n=40, max_chars=60000):
    """Letzte Nachrichten als API-Messages — gedeckelt, damit Requests klein bleiben."""
    out, total = [], 0
    for m in reversed(s.get("messages") or []):
        c = str(m.get("content") or "")
        total += len(c)
        if out and (len(out) >= max_n or total > max_chars):
            break
        out.append({"role": m.get("role") or "user", "content": c})
    return list(reversed(out))


def history_block(sid: str, max_n=30, max_chars=40000) -> str:
    """Verlauf einer externen Session als Text — für den Wechsel ZU Claude."""
    s = load_session(sid)
    if not s or not s.get("messages"):
        return ""
    lines = [f"[Kontext: Dieses Gespräch lief bisher mit {s.get('provider')}:{s.get('model')} "
             f"(externes Chat-Modell); {cfg.USER_NAME} wechselt jetzt zu dir. "
             "Bisheriger Verlauf:]"]
    for m in recent_messages(s, max_n, max_chars):
        who = cfg.USER_NAME if m["role"] == "user" else "Assistent"
        lines.append(f"{who}: {m['content']}")
    lines.append("[Ende des Verlaufs — antworte jetzt auf die folgende neue Nachricht.]")
    return "\n\n".join(lines)


def list_sessions():
    """Externe Sessions im Format der Session-Liste (app.py mischt sie dazu)."""
    out = []
    for f in SESS_DIR.glob("llm-*.json"):
        try:
            s = json.loads(f.read_text(encoding="utf-8"))
            msgs = s.get("messages") or []
            title = next((str(m.get("content") or "").replace("\n", " ").strip()[:80]
                          for m in msgs if m.get("role") == "user" and m.get("content")), "")
            st = f.stat()
            out.append({"id": s.get("id") or f.stem, "project": "llm", "cwd": SESS_GROUP,
                        "title": title or "(ohne Titel)", "mtime": st.st_mtime,
                        "size": st.st_size, "provider": s.get("provider") or "",
                        "model": s.get("model") or ""})
        except Exception:
            continue
    return out


def session_display(s: dict):
    """Messages einer Session im Anzeige-Format der Verlaufs-Ansicht."""
    return [{"role": ("user" if m.get("role") == "user" else "assistant"),
             "text": str(m.get("content") or "")}
            for m in (s.get("messages") or []) if m.get("role") in ("user", "assistant")]
