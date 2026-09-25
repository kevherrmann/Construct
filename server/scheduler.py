"""Geplante Aufgaben: Kalender-Termine mit Cody-Prompt zur richtigen Zeit ausführen."""
import asyncio
import json
import time

import cal
from server import config as cfg
from server import telegram_bot as tgmod

from server.core import BASE_DIR, DEFAULT_CWD
from server.runs import start_run


# ---------- Geplante Aufgaben (Kalender-Termine mit Cody-Prompt) ----------
# Läuft nur, wenn Telegram eingerichtet ist — und nur, solange CONSTRUCT läuft.
# Zur Termin-Zeit startet ein normaler Run; das Ergebnis kommt per Telegram.
TASK_STATE = BASE_DIR / "tasks_state.json"


def _task_state() -> dict:
    try:
        d = json.loads(TASK_STATE.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def _mark_task_done(key: str):
    d = _task_state()
    d[key] = int(time.time())
    cutoff = time.time() - 60 * 86400   # alte Einträge nach 60 Tagen vergessen
    d = {k: v for k, v in d.items() if v > cutoff}
    tmp = TASK_STATE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(d, indent=2), encoding="utf-8")
    tmp.replace(TASK_STATE)


def _due_tasks():
    today = time.strftime("%Y-%m-%d")
    hm = time.strftime("%H:%M")
    state = _task_state()
    for e in cal.load_events():
        prompt = (e.get("prompt") or "").strip()
        if not prompt:
            continue
        d = e.get("date") or ""
        occurs = (d[5:] == today[5:]) if e.get("repeat") == "yearly" else (d == today)
        if not occurs or (e.get("time") or "09:00") > hm:
            continue
        key = f"{e.get('id')}:{today}"
        if key not in state:
            yield e, key


async def scheduler_loop():
    # Läuft immer mit, arbeitet aber nur, solange Telegram eingerichtet ist:
    # das Ergebnis einer geplanten Aufgabe kommt per Telegram an.
    while True:
        try:
            if not tgmod.enabled():
                await asyncio.sleep(60)
                continue
            for ev, key in list(_due_tasks()):
                _mark_task_done(key)   # SOFORT markieren -> nie doppelt starten
                title = ev.get("title") or "(ohne Titel)"
                print(f"[sched] starte Aufgabe: {title}", flush=True)
                who = cfg.user_name()
                prompt = cfg.L(
                    f"[Geplante Aufgabe aus dem Kalender — Termin: „{title}“, "
                    f"{ev.get('date')} {ev.get('time') or ''}. {who} sieht deine Antwort "
                    f"als Telegram-Nachricht. Fasse dich entsprechend.]",
                    f"[Scheduled task from the calendar — event: “{title}”, "
                    f"{ev.get('date')} {ev.get('time') or ''}. {who} will read your reply "
                    f"as a Telegram message. Keep it short accordingly.]",
                ) + f"\n\n{ev['prompt']}"
                tconf = tgmod.load_conf()
                run = start_run(prompt, DEFAULT_CWD, tconf["mode"], tconf["model"])
                run.notify_always = True
                run.task_title = title
        except Exception as e:
            print(f"[sched] fehler: {type(e).__name__}: {e}", flush=True)
        await asyncio.sleep(60)
