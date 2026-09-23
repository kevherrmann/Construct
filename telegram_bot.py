#!/usr/bin/env python3
"""
Cody über Telegram — läuft IN CONSTRUCT, eingerichtet unter ⚙ Einstellungen.

- Reagiert NUR auf die eigene Chat-ID (Whitelist). Solange keine eingetragen
  ist, merkt sich der Bot, wer ihm schreibt, und bietet das in den
  Einstellungen zum Übernehmen an — so muss niemand seine ID nachschlagen.
- Text- und Sprachnachrichten (Sprache via faster-whisper, lokal/offline,
  optional: `pip install faster-whisper`).
- Pro Tag eine frische claude-Session + Persona aus SOUL.md/USER.md.
- Befehle: /neu (/new), /ordner (/folder) <name>, /status.
- Erinnerungen: Morgens-Übersicht und ein Ping vor terminierten Terminen.
- Außerdem der Kanal für "Cody ist fertig" und geplante Kalender-Aufgaben
  (beides steuert app.py über send_owner()).

Konfiguration liegt in .telegram.json (chmod 600, in .gitignore) — NICHT in
settings.json, denn die geht an den Browser und der Token ist ein Schlüssel.
Für Server ohne Oberfläche stechen TELEGRAM_TOKEN / CODY_CHAT_ID aus der
Umgebung die Datei; dann lässt sich der Bot auch direkt starten:
    python3 telegram_bot.py

Ein Token darf nur EINE Stelle abfragen. Läuft derselbe Bot schon woanders,
antwortet Telegram mit 409 — das landet als Status in den Einstellungen,
statt dass sich zwei Instanzen still die Nachrichten wegschnappen.
"""
import datetime
import json
import os
import shutil
import subprocess
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import cal
import config as cfg

BASE_DIR = Path(__file__).parent
CONF_FILE = BASE_DIR / ".telegram.json"
STATE_FILE = BASE_DIR / "telegram_state.json"
WHISPER_MODEL = os.environ.get("CODY_WHISPER_MODEL", "small")
POLL_TIMEOUT = 25
# Nur diese Modi: "default" würde headless auf eine Rückfrage warten, die
# über Telegram niemand beantworten kann.
MODES = ("bypassPermissions", "plan")

DEFAULTS = {
    "enabled": False,
    "token": "",
    "chat_id": 0,
    "model": "",                  # leer = Konto-Standard von Claude Code
    "mode": "bypassPermissions",
    "reminders": True,
    "reminder_hour": 8,
    "reminder_lead": 30,
    "notify": True,               # "Cody ist fertig" nach langen, unbeobachteten Läufen
}

def _persona_standalone() -> str:
    parts = [cfg.persona_read(w).strip() for w in ("soul", "user")]
    try:
        parts.append(cal.context_block())
    except Exception:
        pass
    return "\n\n".join(p for p in parts if p)


# Von app.py gesetzt (init): claude-Aufruf, Umgebung, Persona, Arbeitsordner.
# Standalone greifen die schlichten Rückfälle unten.
HOOKS = {
    "claude_bin": lambda: shutil.which("claude") or "claude",
    "claude_env": lambda: dict(os.environ),
    "persona": _persona_standalone,
    "workspace": str(Path.home()),
}

_lock = threading.Lock()
_whisper = None
STATUS = {"state": "off", "error": "", "bot": "", "candidate": None}
_worker = {"thread": None, "stop": None}


# ---------- Konfiguration ----------
def load_conf() -> dict:
    c = dict(DEFAULTS)
    try:
        raw = json.loads(CONF_FILE.read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            c.update({k: raw[k] for k in DEFAULTS if k in raw})
    except Exception:
        pass
    env_tok = os.environ.get("TELEGRAM_TOKEN", "").strip()
    if env_tok:
        c["token"] = env_tok
        c["enabled"] = True
    env_chat = os.environ.get("CODY_CHAT_ID", "").strip()
    if env_chat:
        c["chat_id"] = env_chat
    try:
        c["chat_id"] = int(c.get("chat_id") or 0)
    except (TypeError, ValueError):
        c["chat_id"] = 0
    if c.get("mode") not in MODES:
        c["mode"] = DEFAULTS["mode"]
    return c


def save_conf(patch: dict) -> dict:
    c = load_conf()
    for k in ("enabled", "reminders", "notify"):
        if k in patch:
            c[k] = bool(patch[k])
    if "token" in patch and patch["token"] is not None:
        c["token"] = str(patch["token"]).strip()
    if "chat_id" in patch:
        try:
            c["chat_id"] = int(str(patch["chat_id"]).strip() or 0)
        except ValueError:
            pass
    if "model" in patch:
        c["model"] = str(patch["model"] or "").strip()[:80]
    if patch.get("mode") in MODES:
        c["mode"] = patch["mode"]
    for k, lo, hi in (("reminder_hour", 0, 23), ("reminder_lead", 0, 240)):
        if k in patch:
            try:
                c[k] = max(lo, min(hi, int(patch[k])))
            except (TypeError, ValueError):
                pass
    tmp = CONF_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(c, indent=2), encoding="utf-8")
    try:
        tmp.chmod(0o600)
    except OSError:
        pass
    tmp.replace(CONF_FILE)
    return c


def public_conf() -> dict:
    """Für den Browser: alles außer dem Token selbst."""
    c = load_conf()
    tok = c.pop("token")
    c["has_token"] = bool(tok)
    c["from_env"] = bool(os.environ.get("TELEGRAM_TOKEN"))
    with _lock:
        c["status"] = dict(STATUS)
    return c


def enabled() -> bool:
    c = load_conf()
    return bool(c["enabled"] and c["token"])


# ---------- Telegram API ----------
class TgError(Exception):
    def __init__(self, code, desc):
        super().__init__(desc)
        self.code = code


def _call(token, method, params=None, timeout=30):
    url = f"https://api.telegram.org/bot{token}/{method}"
    data = urllib.parse.urlencode(params or {}).encode()
    try:
        with urllib.request.urlopen(urllib.request.Request(url, data=data), timeout=timeout) as r:
            j = json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        try:
            j = json.loads(e.read().decode())
        except Exception:
            j = {"description": str(e)}
        raise TgError(e.code, j.get("description") or str(e))
    if not j.get("ok"):
        raise TgError(0, j.get("description") or "?")
    return j.get("result")


def check_token(token: str) -> str:
    """Bot-Name zum Token — prüft ihn gleichzeitig. Wirft TgError."""
    me = _call(token, "getMe", timeout=15) or {}
    return me.get("username") or ""


def send(chat_id, text, token=None):
    token = token or load_conf()["token"]
    if not token or not chat_id:
        return False
    text = text or "(leer)"
    ok = True
    for i in range(0, len(text), 3900):         # Telegram-Grenze 4096
        try:
            _call(token, "sendMessage", {"chat_id": chat_id, "text": text[i:i + 3900]}, timeout=20)
        except Exception as e:
            print(f"[tg] senden fehlgeschlagen: {e}", flush=True)
            ok = False
    return ok


def send_owner(text: str) -> bool:
    """An die eingetragene eigene Chat-ID — für app.py (Fertig-Meldung, Aufgaben)."""
    c = load_conf()
    if not (c["enabled"] and c["token"] and c["chat_id"]):
        return False
    return send(c["chat_id"], text, c["token"])


def _typing(token, chat_id):
    try:
        _call(token, "sendChatAction", {"chat_id": chat_id, "action": "typing"}, timeout=10)
    except Exception:
        pass


def _download(token, file_id):
    info = _call(token, "getFile", {"file_id": file_id}, timeout=20)
    fp = info["file_path"]
    dest = BASE_DIR / "uploads" / f"tg_{int(time.time())}_{os.path.basename(fp)}"
    dest.parent.mkdir(exist_ok=True)
    urllib.request.urlretrieve(f"https://api.telegram.org/file/bot{token}/{fp}", dest)
    return str(dest)


# ---------- Zustand (Session pro Tag, Ordner, gesendete Erinnerungen) ----------
def load_state():
    try:
        return json.loads(STATE_FILE.read_text())
    except Exception:
        return {}


def save_state(s):
    try:
        STATE_FILE.write_text(json.dumps(s))
    except Exception:
        pass


def _today():
    return datetime.date.today().isoformat()


# ---------- Sprache -> Text ----------
def transcribe(path):
    global _whisper
    if _whisper is None:
        from faster_whisper import WhisperModel
        print(f"[tg] lade Whisper-Modell '{WHISPER_MODEL}' …", flush=True)
        _whisper = WhisperModel(WHISPER_MODEL, device="cpu", compute_type="int8")
    segments, _ = _whisper.transcribe(path, language=cfg.lang(), vad_filter=True)
    return "".join(s.text for s in segments).strip()


# ---------- claude -p ----------
def ask_cody(prompt, cwd, session_id, conf):
    cmd = [HOOKS["claude_bin"](), "-p", "--output-format", "json",
           "--permission-mode", conf["mode"]]
    if conf.get("model"):
        cmd += ["--model", conf["model"]]
    persona = HOOKS["persona"]()
    if persona:
        cmd += ["--append-system-prompt", persona]
    if session_id:
        cmd += ["--resume", session_id]
    cmd += [prompt]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd,
                              timeout=900, env=HOOKS["claude_env"]())
    except subprocess.TimeoutExpired:
        return cfg.L("⚠ Zeitüberschreitung nach 15 Minuten.", "⚠ Timed out after 15 minutes."), session_id
    except FileNotFoundError:
        return cfg.L("⚠ Claude Code ist nicht installiert.", "⚠ Claude Code is not installed."), session_id
    if proc.returncode != 0:
        return cfg.L("⚠ Fehler: ", "⚠ Error: ") + (proc.stderr or proc.stdout or "")[:500], session_id
    try:
        data = json.loads(proc.stdout)
        reply = data.get("result") or cfg.L("(keine Antwort)", "(no reply)")
        tout = (data.get("usage") or {}).get("output_tokens") or 0
        dur = data.get("duration_ms")
        dur_s = f"{dur / 1000:.1f}s" if isinstance(dur, (int, float)) else "?"
        reply += f"\n\n⏱ {dur_s} · 🧮 {tout} Tokens"
        return reply, data.get("session_id", session_id)
    except Exception:
        return (proc.stdout or cfg.L("(keine Antwort)", "(no reply)"))[:3900], session_id


# ---------- Nachrichten ----------
def handle(msg, conf):
    token = conf["token"]
    chat = msg.get("chat", {})
    chat_id = chat.get("id")
    if not conf["chat_id"]:
        # Noch niemand eingetragen: merken, wer schreibt — die Einstellungen
        # bieten es zum Übernehmen an. Keine Antwort an Unbekannte.
        name = chat.get("username") or " ".join(
            x for x in (chat.get("first_name"), chat.get("last_name")) if x)
        with _lock:
            STATUS["candidate"] = {"id": chat_id, "name": name or str(chat_id)}
        print(f"[tg] Nachricht von Chat {chat_id} ({name}) — in den Einstellungen übernehmen", flush=True)
        return
    if chat_id != conf["chat_id"]:
        print(f"[tg] ignoriere fremde Chat-ID {chat_id}", flush=True)
        return

    state = load_state()
    conv = state.get("conv", {})
    ws = HOOKS["workspace"]
    cwd = state.get("cwd") if os.path.isdir(state.get("cwd") or "") else ws
    text = (msg.get("text") or "").strip()

    voice = msg.get("voice") or msg.get("audio")
    if voice and not text:
        _typing(token, chat_id)
        try:
            text = transcribe(_download(token, voice["file_id"]))
        except ImportError:
            send(chat_id, cfg.L("🎤 Sprachnachrichten brauchen faster-whisper "
                                "(pip install faster-whisper).",
                                "🎤 Voice messages need faster-whisper "
                                "(pip install faster-whisper)."), token)
            return
        except Exception as e:
            send(chat_id, cfg.L(f"🎤 Konnte die Sprachnachricht nicht verstehen: {e}",
                                f"🎤 Couldn't understand the voice message: {e}"), token)
            return
        if not text:
            send(chat_id, cfg.L("🎤 Da war leider nichts zu hören.",
                                "🎤 Couldn't hear anything, sorry."), token)
            return
        send(chat_id, cfg.L(f"🎤 verstanden: {text}", f"🎤 heard: {text}"), token)
    if not text:
        return

    cmd = text.split()[0].lower()
    if cmd in ("/neu", "/new", "/start"):
        conv.pop(_today(), None)
        state["conv"] = conv
        save_state(state)
        send(chat_id, cfg.L("🆕 Neue Session — frischer Kontext.",
                            "🆕 New session — fresh context."), token)
        return
    if cmd in ("/ordner", "/folder"):
        name = text[len(cmd):].strip()
        target = ws if not name else os.path.join(ws, name)
        if os.path.isdir(target):
            state["cwd"] = target
            save_state(state)
            send(chat_id, cfg.L(f"📂 Arbeitsordner → {target}", f"📂 Working folder → {target}"), token)
        else:
            send(chat_id, cfg.L(f"📂 Ordner nicht gefunden: {target}",
                                f"📂 Folder not found: {target}"), token)
        return
    if cmd == "/status":
        active = bool(conv.get(_today()))
        send(chat_id, cfg.L(f"📊 Ordner: {cwd}\nSession heute: {'aktiv' if active else 'neu'}",
                            f"📊 Folder: {cwd}\nToday's session: {'active' if active else 'new'}"),
             token)
        return

    _typing(token, chat_id)
    reply, new_sid = ask_cody(text, cwd, conv.get(_today()), conf)
    if new_sid:
        conv[_today()] = new_sid
        for k in sorted(conv.keys())[:-3]:     # nur die letzten drei Tage behalten
            conv.pop(k, None)
        state["conv"] = conv
        save_state(state)
    send(chat_id, reply, token)


# ---------- Erinnerungen ----------
def reminder_tick(conf, now=None):
    """Morgens-Übersicht + Vorlauf-Pings; Gesendetes wird in telegram_state.json
    gemerkt, damit nichts doppelt rausgeht."""
    if not (conf["reminders"] and conf["chat_id"]):
        return False
    now = now or datetime.datetime.now()
    day = now.date().isoformat()
    state = load_state()
    sent = state.get("reminders_sent", {})
    changed = False
    todays = cal.events_on(now.date())
    who = cfg.user_name()

    dkey = "digest:" + day
    if now.hour >= conf["reminder_hour"] and dkey not in sent:
        if todays:
            lines = [cfg.L(f"🔔 Guten Morgen, {who}! Heute steht an:",
                           f"🔔 Good morning, {who}! Today's schedule:")]
            for e in sorted(todays, key=lambda e: e.get("time", "")):
                t = e["time"] if e.get("time") else cfg.L("ganztägig", "all day")
                note = f" — {e['notes']}" if e.get("notes") else ""
                lines.append(f"• {t}  {e['title']}{note}")
            send(conf["chat_id"], "\n".join(lines), conf["token"])
        sent[dkey] = True
        changed = True

    live = set()
    for e in todays:
        if not e.get("time"):
            continue
        try:
            hh, mm = map(int, e["time"].split(":"))
        except Exception:
            continue
        lkey = "lead:" + e.get("id", "")
        live.add(lkey)
        delta = (now.replace(hour=hh, minute=mm, second=0, microsecond=0) - now).total_seconds() / 60
        if 0 <= delta <= conf["reminder_lead"] and lkey not in sent:
            note = f" — {e['notes']}" if e.get("notes") else ""
            mins = int(round(delta))
            when = cfg.L("jetzt gleich" if mins <= 1 else f"in {mins} Min",
                         "right now" if mins <= 1 else f"in {mins} min")
            send(conf["chat_id"], f"⏰ {when}: {e['time']} {e['title']}{note}", conf["token"])
            sent[lkey] = True
            changed = True

    for k in list(sent):
        if (k.startswith("digest:") and k != dkey) or (k.startswith("lead:") and k not in live):
            del sent[k]
            changed = True
    if changed:
        state["reminders_sent"] = sent
        save_state(state)
    return changed


# ---------- Hintergrund-Thread ----------
def _set(**kw):
    with _lock:
        STATUS.update(kw)


def _run(stop: threading.Event):
    conf = load_conf()
    try:
        _set(state="starting", error="", bot=check_token(conf["token"]))
    except Exception as e:
        _set(state="error", error=str(e))
        print(f"[tg] Token ungültig: {e}", flush=True)
        return
    print(f"[tg] Bot @{STATUS['bot']} läuft, Chat-ID {conf['chat_id'] or '(noch keine)'}", flush=True)
    offset = None
    last_tick = 0.0
    while not stop.is_set():
        conf = load_conf()
        if time.time() - last_tick > 45:
            last_tick = time.time()
            try:
                reminder_tick(conf)
            except Exception as e:
                print(f"[tg] Erinnerung fehlgeschlagen: {e}", flush=True)
        try:
            params = {"timeout": POLL_TIMEOUT}
            if offset is not None:
                params["offset"] = offset
            updates = _call(conf["token"], "getUpdates", params, timeout=POLL_TIMEOUT + 10)
            _set(state="running", error="")
            for u in updates or []:
                offset = u["update_id"] + 1
                msg = u.get("message") or u.get("edited_message")
                if msg:
                    try:
                        handle(msg, conf)
                    except Exception as e:
                        print(f"[tg] Nachricht fehlgeschlagen: {e}", flush=True)
        except TgError as e:
            if e.code == 409:
                # Derselbe Token wird woanders abgefragt (oder hat einen Webhook).
                _set(state="conflict", error=str(e))
                stop.wait(30)
            elif e.code in (401, 404):
                _set(state="error", error=str(e))
                return
            else:
                _set(state="error", error=str(e))
                stop.wait(5)
        except Exception as e:
            _set(state="error", error=f"{type(e).__name__}: {e}")
            stop.wait(5)
    _set(state="off")


def init(**hooks):
    HOOKS.update({k: v for k, v in hooks.items() if v is not None})


def restart():
    """Nach jeder Änderung an der Konfiguration: alten Poller beenden, neuen
    starten. Asynchron, weil der alte bis zu POLL_TIMEOUT im Long-Poll hängt —
    zwei gleichzeitig ergäben selbst einen 409."""
    def worker():
        old_t, old_s = _worker["thread"], _worker["stop"]
        if old_s:
            old_s.set()
        if old_t and old_t.is_alive():
            old_t.join(POLL_TIMEOUT + 15)
        if not enabled():
            _set(state="off", error="")
            _worker.update(thread=None, stop=None)
            return
        stop = threading.Event()
        t = threading.Thread(target=_run, args=(stop,), daemon=True, name="telegram")
        _worker.update(thread=t, stop=stop)
        t.start()
    threading.Thread(target=worker, daemon=True, name="telegram-restart").start()


def stop():
    if _worker["stop"]:
        _worker["stop"].set()


if __name__ == "__main__":
    # Server ohne Oberfläche: TELEGRAM_TOKEN / CODY_CHAT_ID aus der Umgebung
    # oder .telegram.json, dann im Vordergrund laufen lassen.
    if not enabled():
        print("[tg] Kein Token — in CONSTRUCT unter ⚙ Einstellungen einrichten "
              "oder TELEGRAM_TOKEN setzen.", flush=True)
    else:
        _run(threading.Event())
