#!/usr/bin/env python3
"""
Cody über Telegram.

- Reagiert NUR auf die eigene Chat-ID (Whitelist, CODY_CHAT_ID).
- Text- UND Sprachnachrichten (Sprache via faster-whisper, lokal/offline/kostenlos).
- Pro Tag eine frische claude-Session (Kontext bleibt schlank) + Persona aus SOUL.md/USER.md.
- Befehle: /neu (Session zurücksetzen), /ordner <name> (Arbeitsordner wechseln), /status.
"""
import os
import json
import time
import datetime
import threading
import subprocess
import urllib.request
import urllib.parse
import socket
from pathlib import Path

import cal  # gemeinsamer Kalender (events.json)

# Auf dem Hostinger-Server hängt IPv6 (~20s Stall pro Request); curl/node weichen
# auf IPv4 aus, Pythons urllib nicht. Darum getaddrinfo auf IPv4 beschränken ->
# alle Telegram-API-Calls (getUpdates/sendMessage/...) gehen sofort durch.
_orig_getaddrinfo = socket.getaddrinfo
def _getaddrinfo_ipv4(host, *args, **kwargs):
    res = _orig_getaddrinfo(host, *args, **kwargs)
    v4 = [r for r in res if r[0] == socket.AF_INET]
    return v4 or res
socket.getaddrinfo = _getaddrinfo_ipv4

BASE_DIR = Path(__file__).parent
TOKEN = os.environ.get("TELEGRAM_TOKEN", "").strip()
# Nur DIESE Telegram-Chat-ID darf den Bot benutzen. Ohne CODY_CHAT_ID bleibt sie 0
# und damit weist der Bot jeden ab — lieber stumm als fuer Fremde offen.
ALLOWED_CHAT = int(os.environ.get("CODY_CHAT_ID", "0") or 0)
WHISPER_MODEL = os.environ.get("CODY_WHISPER_MODEL", "small")
DEFAULT_CWD = "/workspace" if os.path.isdir("/workspace") else str(Path.home())
API = f"https://api.telegram.org/bot{TOKEN}"
FILE_API = f"https://api.telegram.org/file/bot{TOKEN}"
STATE_FILE = BASE_DIR / "telegram_state.json"
REMINDER_HOUR = int(os.environ.get("CODY_REMINDER_HOUR", "8"))    # Uhrzeit der Morgens-Übersicht
REMINDER_LEAD = int(os.environ.get("CODY_REMINDER_LEAD", "30"))   # Minuten Vorlauf vor terminierten Events

_whisper = None  # lazy

# ---------- State (Session pro Tag + aktueller Ordner) ----------
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

def today():
    # Europe/Berlin grob: Server-TZ; reicht für "frische Session pro Tag"
    return datetime.date.today().isoformat()

# ---------- Persona (gleich wie Web-Cody) ----------
def load_persona():
    parts = []
    for fn in ("SOUL.md", "USER.md"):
        p = BASE_DIR / fn
        if p.is_file():
            try:
                t = p.read_text(encoding="utf-8", errors="replace").strip()
                if t:
                    parts.append(t)
            except Exception:
                pass
    # Anstehende Termine mitgeben -> Cody kann auch per Telegram erinnern.
    try:
        import cal
        block = cal.context_block()
        if block:
            parts.append(block)
    except Exception:
        pass
    return "\n\n".join(parts).strip()

# ---------- Telegram API ----------
def _get(method, params=None):
    url = f"{API}/{method}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(url, timeout=60) as r:
        return json.loads(r.read().decode())

def _post(method, data):
    body = urllib.parse.urlencode(data).encode()
    req = urllib.request.Request(f"{API}/{method}", data=body)
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode())

def send(chat_id, text):
    # Telegram-Limit 4096 -> stückeln
    for i in range(0, len(text) or 1, 3900):
        chunk = text[i:i + 3900] or "(leer)"
        try:
            _post("sendMessage", {"chat_id": chat_id, "text": chunk})
        except Exception as e:
            print("[tg] sendMessage-Fehler:", e, flush=True)

def typing(chat_id):
    try:
        _get("sendChatAction", {"chat_id": chat_id, "action": "typing"})
    except Exception:
        pass

def download_file(file_id):
    info = _get("getFile", {"file_id": file_id})
    fp = info["result"]["file_path"]
    dest = BASE_DIR / "uploads" / f"tg_{int(time.time())}_{os.path.basename(fp)}"
    dest.parent.mkdir(exist_ok=True)
    urllib.request.urlretrieve(f"{FILE_API}/{fp}", dest)
    return str(dest)

# ---------- Sprache -> Text ----------
def transcribe(path):
    global _whisper
    if _whisper is None:
        from faster_whisper import WhisperModel
        print(f"[tg] lade Whisper-Modell '{WHISPER_MODEL}' …", flush=True)
        _whisper = WhisperModel(WHISPER_MODEL, device="cpu", compute_type="int8")
    segments, _ = _whisper.transcribe(path, language="de", vad_filter=True)
    return "".join(s.text for s in segments).strip()

# ---------- claude -p ----------
def ask_cody(prompt, cwd, session_id):
    cmd = ["claude", "-p", "--output-format", "json", "--permission-mode", "bypassPermissions"]
    persona = load_persona()
    if persona:
        cmd += ["--append-system-prompt", persona]
    if session_id:
        cmd += ["--resume", session_id]
    cmd += [prompt]
    proc = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd, timeout=900)
    if proc.returncode != 0:
        return f"⚠ Fehler: {(proc.stderr or '')[:500]}", session_id
    try:
        data = json.loads(proc.stdout)
        reply = data.get("result") or "(keine Antwort)"
        u = data.get("usage") or {}
        tout = u.get("output_tokens") or 0
        dur = data.get("duration_ms")
        dur_s = f"{dur / 1000:.1f}s" if isinstance(dur, (int, float)) else "?"
        reply += f"\n\n⏱ {dur_s} · 🧮 {tout} Tokens"
        return reply, data.get("session_id", session_id)
    except Exception:
        return (proc.stdout or "(keine Antwort)")[:3900], session_id

# ---------- Nachrichten-Handling ----------
def handle(msg):
    chat = msg.get("chat", {})
    chat_id = chat.get("id")
    if chat_id != ALLOWED_CHAT:
        print(f"[tg] ignoriere fremde Chat-ID {chat_id}", flush=True)
        return

    state = load_state()
    conv = state.get("conv", {})
    cwd = state.get("cwd", DEFAULT_CWD)

    text = (msg.get("text") or "").strip()

    # Sprachnachricht?
    voice = msg.get("voice") or msg.get("audio")
    if voice and not text:
        typing(chat_id)
        try:
            path = download_file(voice["file_id"])
            text = transcribe(path)
        except ImportError:
            send(chat_id, "🎤 Sprach-Transkription ist noch nicht installiert (faster-whisper fehlt).")
            return
        except Exception as e:
            send(chat_id, f"🎤 Konnte die Sprachnachricht nicht verstehen: {e}")
            return
        if not text:
            send(chat_id, "🎤 Da war leider nichts zu hören.")
            return
        send(chat_id, f"🎤 verstanden: {text}")

    if not text:
        return

    # Befehle
    if text.startswith("/neu"):
        conv.pop(today(), None); state["conv"] = conv; save_state(state)
        send(chat_id, "🆕 Neue Session — frischer Kontext.")
        return
    if text.startswith("/ordner"):
        name = text[len("/ordner"):].strip()
        target = DEFAULT_CWD if not name or name in ("/", "workspace") else os.path.join("/workspace", name)
        if os.path.isdir(target):
            state["cwd"] = target; save_state(state)
            send(chat_id, f"📂 Arbeitsordner → {target}")
        else:
            send(chat_id, f"📂 Ordner nicht gefunden: {target}")
        return
    if text.startswith("/status"):
        sid = conv.get(today())
        send(chat_id, f"📊 Ordner: {cwd}\nSession heute: {'aktiv' if sid else 'neu'}")
        return

    # Normale Nachricht -> Cody
    typing(chat_id)
    sid = conv.get(today())
    reply, new_sid = ask_cody(text, cwd, sid)
    if new_sid:
        conv[today()] = new_sid
        # alte Tage aufräumen (nur die letzten 3 behalten)
        for k in sorted(conv.keys())[:-3]:
            conv.pop(k, None)
        state["conv"] = conv; save_state(state)
    send(chat_id, reply)

# ---------- Erinnerungen (Push, ohne dass Kevin schreiben muss) ----------
def reminder_tick(now=None):
    """Ein Durchlauf: Morgens-Übersicht + Vorlauf-Pings fällig? Dann senden.

    Merkt sich Gesendetes in telegram_state.json ("reminders_sent"), damit nichts
    doppelt rausgeht. Zeitbasis = Server-Zeit (grob Europe/Berlin), reicht hier.
    """
    now = now or datetime.datetime.now()
    today = now.date().isoformat()
    state = load_state()
    sent = state.get("reminders_sent", {})
    changed = False

    todays = cal.events_on(now.date())

    # 1) Morgens-Übersicht (einmal pro Tag, ab REMINDER_HOUR)
    dkey = "digest:" + today
    if now.hour >= REMINDER_HOUR and dkey not in sent:
        if todays:
            lines = ["🔔 Guten Morgen, Kevin! Heute steht an:"]
            for e in sorted(todays, key=lambda e: e.get("time", "")):
                t = e["time"] if e.get("time") else "ganztägig"
                note = f" — {e['notes']}" if e.get("notes") else ""
                lines.append(f"• {t}  {e['title']}{note}")
            send(ALLOWED_CHAT, "\n".join(lines))
        sent[dkey] = True   # auch ohne Termine markieren -> nicht erneut prüfen
        changed = True

    # 2) Vorlauf-Ping vor terminierten Events von heute
    live_leads = set()
    for e in todays:
        if not e.get("time"):
            continue
        try:
            hh, mm = map(int, e["time"].split(":"))
        except Exception:
            continue
        lkey = "lead:" + e.get("id", "")
        live_leads.add(lkey)
        evt = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
        delta_min = (evt - now).total_seconds() / 60
        if 0 <= delta_min <= REMINDER_LEAD and lkey not in sent:
            note = f" — {e['notes']}" if e.get("notes") else ""
            mins = int(round(delta_min))
            when = "jetzt gleich" if mins <= 1 else f"in {mins} Min"
            send(ALLOWED_CHAT, f"⏰ {when}: {e['time']} {e['title']}{note}")
            sent[lkey] = True
            changed = True

    # alte Marker aufräumen (vergangene Tage / gelöschte Events)
    for k in list(sent.keys()):
        stale = (k.startswith("digest:") and k != dkey) or \
                (k.startswith("lead:") and k not in live_leads)
        if stale:
            del sent[k]
            changed = True

    if changed:
        state["reminders_sent"] = sent
        save_state(state)
    return changed


def reminder_loop():
    """Leiser Hintergrund-Thread: ruft reminder_tick() im 45s-Takt."""
    print(f"[tg] Erinnerungs-Scheduler läuft (Übersicht {REMINDER_HOUR}:00, Vorlauf {REMINDER_LEAD} min)", flush=True)
    while True:
        try:
            reminder_tick()
        except Exception as e:
            print("[tg] reminder-Fehler:", e, flush=True)
        time.sleep(45)


# ---------- Long-Polling-Loop ----------
def main():
    if not TOKEN:
        print("[tg] FEHLER: TELEGRAM_TOKEN fehlt.", flush=True)
        return
    # Schutz vor Doppel-Start: der Bot darf nur da laufen, wo CODY_BOT_OK=1 gesetzt
    # ist (Hostinger, .cody-tg-env). Zwei Poller auf demselben Token = 409-Chaos.
    if os.environ.get("CODY_BOT_OK") != "1":
        print("[tg] ÜBERSPRUNGEN: CODY_BOT_OK=1 fehlt — dieser Bot läuft nur auf "
              "Hostinger (cody-telegram.service). Lokal nicht starten!", flush=True)
        return
    me = _get("getMe").get("result", {})
    print(f"[tg] Cody-Bot @{me.get('username')} läuft. Whitelist-Chat: {ALLOWED_CHAT}", flush=True)
    if not ALLOWED_CHAT:
        print("[tg] ⚠ CODY_CHAT_ID ist nicht gesetzt — der Bot antwortet niemandem. "
              "Eigene Chat-ID setzen (z.B. über @userinfobot).", flush=True)
    threading.Thread(target=reminder_loop, daemon=True).start()
    offset = None
    while True:
        try:
            params = {"timeout": 30}
            if offset is not None:
                params["offset"] = offset
            res = _get("getUpdates", params)
            for u in res.get("result", []):
                offset = u["update_id"] + 1
                msg = u.get("message") or u.get("edited_message")
                if msg:
                    try:
                        handle(msg)
                    except Exception as e:
                        print("[tg] handle-Fehler:", e, flush=True)
        except Exception as e:
            print("[tg] loop-Fehler:", e, flush=True)
            time.sleep(3)

if __name__ == "__main__":
    main()
