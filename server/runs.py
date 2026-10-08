"""Entkoppelte Läufe mit dem claude-CLI: starten, streamen, einwerfen,
Nachlauf, Benachrichtigung wenn ein langer Lauf unbeobachtet fertig wird.
"""
import asyncio
import json
import os
import re
import signal
import subprocess
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path

from server import config as cfg
from server import telegram_bot as tgmod
from server import tickets as tickmod

from server.core import (BASE_DIR, LIMIT_HIT, PROJECTS_DIR, claude_bin, claude_env, extract_text,
                         friendly_claude_error, load_persona)
from server.sessions import model_short
from server.team.chat import ohne_marke


# ---------- Entkoppelte Läufe (überleben Verbindungsabbruch/Reload) ----------
# claude läuft als Hintergrund-Task, die Ausgabe wird server-seitig gepuffert.
# Ein Client verbindet sich per run_id, bekommt erst den Backlog (Replay) und dann
# live weiter. Trennt der Browser (Reload/Schlaf/Netz), läuft der Task einfach
# weiter; beim Wiederverbinden wird alles nachgespielt. (Single-Worker-Annahme:
# der Zustand lebt im Prozess -> uvicorn mit EINEM Worker betreiben.)
RUNS = {}            # run_id -> Run


RUN_TTL = 900        # fertige Läufe nach 15 min vergessen


SSE_HEADERS = {
    "Cache-Control": "no-cache, no-transform",
    "X-Accel-Buffering": "no",
    "Connection": "keep-alive",
}


class Run:
    def __init__(self, run_id, cwd, session_id=None, model="", initial_prompt=""):
        self.id = run_id
        self.cwd = cwd
        self.model = model               # gewähltes Modell ("" = Konto-Standard)
        self.session_id = session_id     # füllt sich aus dem init-Event von claude
        self.initial_prompt = initial_prompt  # erste Nachricht (geht via stdin rein)
        self.events = []                 # gepufferte SSE-Events (Backlog für Replay)
        self.subs = set()                # aktive Abonnenten-Queues (Live-Clients)
        self.done = False
        self.proc = None
        self.task = None
        self.started = time.time()
        self.finished_at = None
        self.stdin_closed = False        # nach dem result nimmt der Lauf nichts mehr an
        # Hintergrundaufgaben, die claude selbst gestartet hat (Bash mit
        # run_in_background, Agenten). Solange hier etwas steht, bleibt der
        # Prozess nach dem Ergebnis am Leben — siehe Nachlauf in run_claude.
        self.hintergrund = {}            # task_id -> Beschreibung
        self.helfer = set()              # tool_use_ids gestarteter Helfer (Agent/Task)
        self.nachlauf = False            # Zug fertig, Prozess wartet auf den Hintergrund
        self.zug_offen = False           # laeuft gerade ein Zug (fuer "neuer_zug")
        self.last_text = ""              # Text des letzten Turns (für Telegram-Notify)
        self.notify_always = False       # geplante Aufgaben melden sich immer per Telegram
        self.task_title = ""             # Titel der geplanten Aufgabe (für die Meldung)
        # Ticket-Board (server/tickets.py): Commits dieses Laufs werden zu einer
        # Karte. git_befehle merkt sich Bash-Aufrufe mit `git commit`, bis ihr
        # Ergebnis kommt; board_ticket ist die Karte, an die weitere Commits gehen.
        self.git_befehle = {}            # tool_use_id -> (Befehl, Startzeit)
        self.board_ticket = None
        self.letzte_uuid = ""            # zuletzt angenommene Nachricht von Kevin (Sprung vom Board)
        self.marke_ab = 0                # bis wohin last_text schon auf [[firma: …]] gelesen ist
        # Team-Modus (server/team/): Läufe, die einem Mitarbeiter gehören, also
        # Züge in einem Auftrag. Im Chat bleibt alles leer.
        self.agent_slug = ""             # gehört der Lauf einem Mitarbeiter?
        self.auftrag_id = ""             # läuft er in einem Auftrag?
        self.bus_token = ""              # Einmal-Token für den Firmen-Bus
        # Lebenszeichen für die Hänger-Erkennung — MONOTON, nicht Wanduhr: time.time()
        # springt nach einem Standby des Rechners um die Schlafzeit nach vorn,
        # und zwei Züge galten als "30 Minuten still", die sechs Minuten alt waren
        # (05.09.2026 in FACTORIA). CLOCK_MONOTONIC zählt den Standby unter Linux
        # nicht mit.
        self.letztes_ereignis = time.monotonic()
        self.cost_usd = 0.0              # echte Kosten aus dem result-Ereignis
        # Wie viel vom Systemprompt aus dem Zwischenspeicher kam: nur damit lässt
        # sich belegen, ob eine Änderung am Prompt das Zwischenspeichern
        # verbessert oder kaputt macht.
        self.cache_read = 0
        self.cache_write = 0
        self.frisch = 0
        self.fehler = ""                 # letzte Fehlermeldung (Limit, Login, Absturz)
        self.limit_bis = 0               # Nutzungslimit gerissen: ab wann es weitergeht
        self.bus_calls = 0               # geroutete Nachrichten dieses Zuges
        self.bus_letztes = ""            # welches Werkzeug das war (für die Fehlermeldung)
        self.bus_ziele = []              # wen er in diesem Zug schon beauftragt hat
        self.gesagt_ab = 0               # bis wohin last_text schon im Auftragsprotokoll steht

    def emit(self, ev):
        self.letztes_ereignis = time.monotonic()
        if ev.get("type") == "text":
            # hier statt in run_claude, damit auch Hermes-Läufe eine
            # Telegram-Zusammenfassung (maybe_notify) bekommen
            self.last_text += ev.get("text", "")
        elif ev.get("type") == "error":
            # Für den Dispatcher der Firma: ein Zug, der mit Fehler endete, ist
            # kein "stiller Zug" — und ein gerissenes Limit ist gar kein Fehler
            # des Mitarbeiters, sondern eine Wartezeit.
            self.fehler = str(ev.get("message") or "")
            if LIMIT_HIT["resets_at"] > time.time() and "Nutzungs-Limit" in self.fehler:
                self.limit_bis = LIMIT_HIT["resets_at"]
        elif ev.get("type") == "tool":
            if self.last_text and not self.last_text.endswith("\n"):
                # Zwischen zwei Textblöcken lag ein Werkzeugaufruf. Ohne Trenner klebte
                # im Verlauf "Ich schau erst nach.Passt, ich baue." zusammen.
                self.last_text += "\n\n"
            befehl = str((ev.get("input") or {}).get("command") or "")
            if ev.get("name") == "Bash" and tickmod.ist_commit_befehl(befehl):
                self.git_befehle[ev.get("id")] = (befehl, time.time())
        elif ev.get("type") == "tool_result" and ev.get("id") in self.git_befehle:
            befehl, seit = self.git_befehle.pop(ev.get("id"))
            if not ev.get("is_error"):
                _commit_buchen(self, befehl, ev.get("content") or "", seit)
        # aufeinanderfolgende Text-Events zusammenfassen -> Puffer/Replay schlank
        if ev.get("type") == "text" and self.events and self.events[-1].get("type") == "text":
            # NEUES Objekt statt += am alten: ein Client, der gerade den Rückstand
            # nachspielt, hält Verweise auf die alten Objekte — in-place
            # angehängter Text käme bei ihm doppelt an (einmal im Rückstand, einmal
            # live aus der Warteschlange).
            alt = self.events[-1]
            self.events[-1] = {**alt, "text": alt.get("text", "") + ev.get("text", "")}
        else:
            self.events.append(ev)
        for q in list(self.subs):
            q.put_nowait(ev)

    def finish(self):
        self.done = True
        self.finished_at = time.time()
        for q in list(self.subs):
            q.put_nowait(None)


def gc_runs():
    now = time.time()
    for rid in [r for r, run in RUNS.items()
                if run.done and run.finished_at and now - run.finished_at > RUN_TTL]:
        RUNS.pop(rid, None)


# ---------- Telegram-Benachrichtigung (wenn ein langer Lauf unbeobachtet fertig wird) ----------
# Eingerichtet wird Telegram unter ⚙ Einstellungen (telegram_bot.py).
NOTIFY_MIN_SECS = int(os.environ.get("CODY_NOTIFY_MIN_SECS", "90"))


def maybe_notify(run):
    """Nach Lauf-Ende: Telegram-Ping, wenn (a) geplante Aufgabe oder (b) der Lauf
    lange lief UND gerade niemand im Browser zuschaut (run.subs leer)."""
    conf = tgmod.load_conf()
    if not (conf["enabled"] and conf["token"] and conf["chat_id"]):
        return
    if not run.notify_always and not conf["notify"]:
        return
    dur = time.time() - run.started
    if not run.notify_always and (dur < NOTIFY_MIN_SECS or run.subs):
        return
    mins, secs = divmod(int(dur), 60)
    # Die Markerzeile ([[firma: …]]) ist für den Server, nicht fürs Telefon.
    tail = ohne_marke(run.last_text.strip())[-600:]
    head = (cfg.L("🤖 Geplante Aufgabe erledigt", "🤖 Scheduled task done") if run.notify_always
            else cfg.L(f"✅ {cfg.assistant_name()} ist fertig", f"✅ {cfg.assistant_name()} is done"))
    msg = f"{head} ({mins} m {secs} s, {os.path.basename(run.cwd or '?')})"
    if run.notify_always and run.task_title:
        msg += f" — {run.task_title}"
    if tail:
        msg += f":\n\n{tail}"
    threading.Thread(target=tgmod.send_owner, args=(msg,), daemon=True).start()


def stdin_message(prompt: str) -> bytes:
    """Eine User-Nachricht im stream-json-Eingabeformat von claude."""
    return (json.dumps({
        "type": "user",
        "message": {"role": "user", "content": [{"type": "text", "text": prompt}]},
    }, ensure_ascii=False) + "\n").encode()


def is_pdf(path) -> bool:
    return str(path).lower().endswith(".pdf")


def pdf_note(pdfs) -> str:
    """Hinweisblock für hochgeladene PDFs (Liedtexte, Dokumente).

    Beim Upload wurde ein Textauszug daneben gelegt; den soll das Modell
    zuerst lesen — die PDF selbst rendert das Read-Tool seitenweise als Bild,
    das kostet ein Vielfaches an Tokens.
    """
    lines = []
    for p in pdfs:
        txt = Path(str(p) + ".txt")
        if txt.is_file():
            lines.append(cfg.L(f"[Vom Nutzer hochgeladene PDF: {p} — Textauszug: {txt}]",
                               f"[PDF uploaded by the user: {p} — text extract: {txt}]"))
        else:
            lines.append(cfg.L(f"[Vom Nutzer hochgeladene PDF: {p} — kein Text extrahierbar, "
                               "vermutlich gescannt]",
                               f"[PDF uploaded by the user: {p} — no extractable text, "
                               "probably scanned]"))
    lines.append(cfg.L("(Lies zuerst den Textauszug mit dem Read-Tool; die PDF selbst nur, "
                       "wenn Layout oder Bilder wichtig sind.)",
                       "(Read the text extract with the Read tool first; open the PDF itself "
                       "only if layout or images matter.)"))
    return "\n".join(lines)


def build_prompt(text: str, images) -> str:
    """User-Text + Hinweise auf hochgeladene Dateien (Bilder, PDFs) kombinieren."""
    prompt = (text or "").strip()
    imgs = [p for p in (images or []) if not is_pdf(p)]
    pdfs = [p for p in (images or []) if is_pdf(p)]
    if imgs:
        img_lines = "\n".join(cfg.L(f"[Vom Nutzer hochgeladenes Bild: {p}]",
                                     f"[Image uploaded by the user: {p}]") for p in imgs)
        prompt = (f"{prompt}\n\n{img_lines}\n"
                  + cfg.L("(Bitte sieh dir die Bild-Datei(en) mit dem Read-Tool an.)",
                          "(Please look at the image file(s) with the Read tool.)")).strip()
    if pdfs:
        prompt = f"{prompt}\n\n{pdf_note(pdfs)}".strip()
    return prompt


def _werkzeug_ereignis(block, parent=None) -> dict:
    ev = {"type": "tool", "id": block.get("id"), "name": block.get("name", "?"),
          "input": block.get("input", {})}
    if parent:
        # Ein Schritt des Helfers mit dieser tool_use_id, nicht des Assistenten.
        ev["parent"] = parent
    return ev


def _ergebnis_ereignis(block, parent=None) -> dict:
    c = block.get("content")
    if isinstance(c, list):
        c = "\n".join(x.get("text", "") for x in c if isinstance(x, dict))
    ev = {"type": "tool_result", "id": block.get("tool_use_id"), "content": str(c)[:6000],
          "is_error": bool(block.get("is_error"))}
    if parent:
        ev["parent"] = parent
    return ev


# task_notification nennt, wie ein Helfer endete; nur "completed" ist ein Erfolg
# (sonst failed, killed, stopped, cancelled — gesehen in claude 2.1.294).
def _helfer_ereignis(run, ev):
    """system/task_* -> Ereignis `helfer` für die Hologramme im Raum, oder None.

    Dieselben task_*-Meldungen schickt claude auch für Bash im Hintergrund; ein
    Helfer ist nur, was als Agent (local_agent) startet. Fortschritt und Ende
    gibt es deshalb nur für Helfer, deren Start hier durchkam."""
    sub, hid = ev.get("subtype"), ev.get("tool_use_id")
    if not hid:
        return None
    if sub == "task_started":
        if ev.get("task_type") != "local_agent" and not ev.get("subagent_type"):
            return None
        run.helfer.add(hid)
        return {"type": "helfer", "id": hid, "stand": "start",
                "beschreibung": str(ev.get("description") or ""),
                "typ": str(ev.get("subagent_type") or ""),
                "hintergrund": bool(ev.get("is_backgrounded"))}
    if hid not in run.helfer:
        return None
    if sub == "task_progress":
        return {"type": "helfer", "id": hid, "stand": "laeuft",
                "detail": str(ev.get("description") or ""),
                "werkzeug": str(ev.get("last_tool_name") or "")}
    if sub == "task_notification":
        run.helfer.discard(hid)
        return {"type": "helfer", "id": hid,
                "stand": "fertig" if ev.get("status") == "completed" else "fehler"}
    return None


async def run_claude(run, cmd):
    """Hintergrund-Task: schreibt Events in den Run-Puffer (NICHT an einen Client)."""
    stderr_chunks = []

    async def drain_stderr(stream):
        # stderr parallel leeren — sonst blockiert claude, wenn der Puffer volläuft
        while True:
            d = await stream.read(4096)
            if not d:
                break
            if len(stderr_chunks) < 256:
                stderr_chunks.append(d)

    if not claude_bin():
        run.emit({"type": "error", "message":
                  "⚠ Claude Code ist auf diesem Rechner nicht installiert. "
                  "Entweder unten links im 🧠-Menü ein anderes Modell wählen "
                  "(ChatGPT, Gemini …) oder Claude Code nachinstallieren: "
                  "<code>npm install -g @anthropic-ai/claude-code</code>"})
        run.stdin_closed = True
        run.finish()
        return

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=run.cwd,
            env=claude_env(),
            limit=64 * 1024 * 1024,   # große stream-json-Zeilen (Tool-Ergebnisse)
        )
        run.proc = proc
        merken(run, cmd[0])
        # Erste Nachricht über stdin einspeisen; die Leitung bleibt offen, damit
        # Kevin dem laufenden Cody weitere Nachrichten nachschieben kann (Inject).
        proc.stdin.write(stdin_message(run.initial_prompt))
        await proc.stdin.drain()
        stderr_task = asyncio.create_task(drain_stderr(proc.stderr))
        thinking_sent = False
        got_error = False
        while True:
            try:
                raw = await proc.stdout.readline()
            except ValueError:
                print("[run] zeile > limit, übersprungen", flush=True)
                continue
            if not raw:
                break  # EOF — Prozess fertig
            line = raw.decode("utf-8", "replace").strip()
            if not line:
                continue
            try:
                ev = json.loads(line)
            except Exception:
                continue
            t = ev.get("type")
            if (t in ("assistant", "stream_event") and not run.zug_offen
                    and not ev.get("parent_tool_use_id")):
                # Der erste Inhalt eines Zuges. Kommt er im Nachlauf — also
                # ohne dass Kevin etwas geschickt hat — hat eine
                # Hintergrundaufgabe den Zug ausgeloest, und die Oberflaeche
                # braucht eine neue Sprechblase dafuer. Schritte eines Helfers
                # im Hintergrund (parent_tool_use_id) sind kein neuer Zug.
                run.zug_offen = True
                if run.nachlauf:
                    run.nachlauf = False
                    run.emit({"type": "neuer_zug"})
            if t == "system" and ev.get("subtype") == "init":
                run.session_id = ev.get("session_id", run.session_id)
                run.emit({"type": "session", "session_id": run.session_id})
                merken(run)
            elif t == "system" and ev.get("subtype") == "background_tasks_changed":
                # Die eine verlaessliche Liste: claude schickt sie bei jedem
                # Start und Ende einer Hintergrundaufgabe komplett.
                run.hintergrund = {x.get("task_id"): x.get("description") or x.get("task_type") or "?"
                                   for x in (ev.get("tasks") or []) if x.get("task_id")}
            elif t == "system" and str(ev.get("subtype") or "").startswith("task_"):
                helfer = _helfer_ereignis(run, ev)
                if helfer:
                    run.emit(helfer)
            elif t == "stream_event":
                e = ev.get("event", {})
                if e.get("type") == "content_block_delta":
                    d = e.get("delta", {})
                    if d.get("type") == "text_delta":
                        run.emit({"type": "text", "text": d.get("text", "")})
            elif t == "assistant":
                for block in ev.get("message", {}).get("content", []):
                    if not isinstance(block, dict):
                        continue
                    if block.get("type") == "thinking" and not thinking_sent:
                        thinking_sent = True
                        run.emit({"type": "thinking_marker"})
                    elif block.get("type") == "tool_use":
                        run.emit(_werkzeug_ereignis(block, ev.get("parent_tool_use_id")))
            elif t == "user":
                content = ev.get("message", {}).get("content")
                _nutzer_merken(run, ev, content)
                if isinstance(content, list):
                    for block in content:
                        if isinstance(block, dict) and block.get("type") == "tool_result":
                            run.emit(_ergebnis_ereignis(block, ev.get("parent_tool_use_id")))
            elif t == "result":
                run.session_id = ev.get("session_id", run.session_id)
                # Fehler-Resultate (Limit erreicht, Login abgelaufen, …) wurden
                # früher verschluckt -> jetzt sichtbar machen.
                res_text = ev.get("result") if isinstance(ev.get("result"), str) else ""
                if ev.get("is_error") or ev.get("subtype") not in (None, "success"):
                    got_error = True
                    run.emit({"type": "error",
                              "message": friendly_claude_error(
                                  res_text or str(ev.get("subtype") or "Unbekannter Fehler"))})
                u = ev.get("usage") or {}
                ctx = ((u.get("input_tokens") or 0)
                       + (u.get("cache_read_input_tokens") or 0)
                       + (u.get("cache_creation_input_tokens") or 0))
                run.cache_read = u.get("cache_read_input_tokens") or 0
                run.cache_write = u.get("cache_creation_input_tokens") or 0
                run.frisch = u.get("input_tokens") or 0
                # total_cost_usd ist die einzige echte Geldzahl im System — die
                # Firma zeigt sie je Auftrag an, also mitnehmen statt wegwerfen.
                run.cost_usd = ev.get("total_cost_usd") or 0.0
                if not run.agent_slug:
                    _firma_marke(run)
                # `run.model` ist nur die AUSWAHL — bei "Standard" ist sie leer,
                # und ein Alias wie "fable" sagt nicht, welches Fable lief.
                # `modelUsage` im Ergebnis nennt die tatsaechlich benutzte ID
                # (gemessen: {"claude-fable-5-1": {...}}). Die ist gemeint, wenn
                # in der Oberflaeche ein Modell steht.
                echt = ""
                for mid in (ev.get("modelUsage") or {}):
                    echt = model_short(mid)
                    if echt:
                        break
                run.emit({
                    "type": "stats",
                    "duration_ms": ev.get("duration_ms"),
                    "out": u.get("output_tokens") or 0,
                    "ctx": ctx,
                    "cache_read": run.cache_read,
                    "cost": run.cost_usd,
                    "model": echt or run.model,
                })
                run.zug_offen = False
                if (run.hintergrund and not run.auftrag_id
                        and time.time() - run.started < NACHLAUF_MAX):
                    # NACHLAUF. Der Zug ist fertig, aber claude hat noch
                    # Hintergrundaufgaben laufen. Bleibt stdin offen, bleibt
                    # der Prozess am Leben und meldet sich von selbst wieder,
                    # sobald eine fertig ist (gemessen 04.09.2026: nach einem
                    # `sleep 15` im Hintergrund kam 14 s nach dem ersten
                    # result ein zweites, mit der Nachlieferung). Vorher wurde
                    # stdin hier immer geschlossen — und mit dem Prozess starb
                    # jede Hintergrundaufgabe, ohne dass jemand es merkte:
                    # "du kannst mich nachtraeglich nicht mehr anschreiben".
                    #
                    # Schreibt Kevin in dieser Zeit, geht seine Nachricht per
                    # /api/inject in DIESEN Prozess statt per --resume in einen
                    # zweiten auf derselben Sitzung. Züge in einem Auftrag bleiben
                    # außen vor: dort wartet der Dispatcher auf das Prozessende.
                    run.nachlauf = True
                    run.emit({"type": "nachlauf", "tasks": list(run.hintergrund.values())})
                    run.emit({"type": "done", "session_id": run.session_id})
                    asyncio.get_running_loop().call_later(
                        max(60, NACHLAUF_MAX - (time.time() - run.started)),
                        _nachlauf_beenden, run)
                else:
                    # Turn fertig -> stdin schließen, claude beendet sich sauber.
                    # (Mid-Turn-Injections sind zu diesem Zeitpunkt schon in den
                    # Turn eingeflossen; spätere Nachrichten laufen über
                    # --resume weiter.)
                    if run.nachlauf:
                        run.emit({"type": "nachlauf_ende"})
                    run.nachlauf = False
                    run.stdin_closed = True
                    run.emit({"type": "done", "session_id": run.session_id})
                    try:
                        proc.stdin.close()
                    except Exception:
                        pass
        await proc.wait()
        try:
            await asyncio.wait_for(stderr_task, timeout=5)
        except Exception:
            stderr_task.cancel()
        if proc.returncode and not run.done and not got_error:
            err = b"".join(stderr_chunks).decode("utf-8", "replace").strip()
            print(f"[run] claude exit={proc.returncode}: {err[:500]}", flush=True)
            run.emit({"type": "error",
                      "message": friendly_claude_error(err[:1500] or f"claude beendet mit Code {proc.returncode}")})
    except asyncio.CancelledError:
        # Stop-Button -> Prozess hart beenden
        print("[run] gestoppt", flush=True)
        run.stopped = True
        try:
            if run.proc:
                run.proc.kill()
        except Exception:
            pass
        run.emit({"type": "error", "message": "⏹ Gestoppt."})
        raise
    except Exception as e:
        print(f"[run] fehler: {type(e).__name__}: {e}", flush=True)
        run.emit({"type": "error", "message": f"Server-Fehler: {e}"})
    finally:
        vergessen(run.id)
        run.stdin_closed = True
        if run.bus_token:
            # Der Firmen-Bus nimmt von diesem Zug nichts mehr an.
            from server.team import engine
            engine.BUS_TOKENS.pop(run.bus_token, None)
        if run.nachlauf:
            # claude ist gegangen, waehrend noch Hintergrundaufgaben offen
            # waren (von selbst oder abgeschossen). Ohne diese Meldung bleibt
            # die Oberflaeche im Nachlauf haengen.
            run.nachlauf = False
            run.emit({"type": "nachlauf_ende"})
        run.finish()
        if not getattr(run, "stopped", False) and not run.agent_slug:
            # Züge der Firma melden sich nicht einzeln — sonst pingt jeder Schritt
            # das Telefon.
            maybe_notify(run)


def _nutzer_merken(run, ev, content):
    """Kevins Nachricht ist angenommen (claude meldet sie dank
    --replay-user-messages samt uuid zurück): gemerkt für den Sprung vom Board
    an die Stelle im Chat."""
    uuid = ev.get("uuid")
    if not uuid or ev.get("parent_tool_use_id") or ev.get("isSynthetic"):
        return
    text = extract_text(content).strip()
    # Tool-Ergebnisse (kein Text) und Meldungen des Systems (Hintergrundaufgabe
    # fertig, <task-notification> …) sind keine Nachricht von Kevin.
    if text and not text.startswith("<") and not text.startswith("Caveat"):
        run.letzte_uuid = uuid


def _commit_buchen(run, befehl, ausgabe, seit=None):
    """Der Lauf hat committet: der Commit kommt aufs Board. Fehler hier stören
    den Lauf nie — das Board ist Buchhaltung."""
    try:
        if not cfg.load_settings()["tiles"]["tickets"]:
            return
        nr = tickmod.commit_buchen(ausgabe, befehl, run.cwd, session=run.session_id or "",
                                   uuid=run.letzte_uuid, von=run.agent_slug, auftrag=run.auftrag_id,
                                   ticket=run.board_ticket, seit=seit)
        if nr:
            run.board_ticket = nr
            run.emit({"type": "tickets", "nr": nr})
    except Exception as e:
        print(f"[tickets] Commit nicht gebucht: {type(e).__name__}: {e}", flush=True)


def _firma_marke(run):
    """Der Zug ist fertig: endet die Antwort mit `[[firma: …]]`, geht die Aufgabe
    an die Firma (server/team/chat.py). Fehler hier stören den Lauf nie."""
    try:
        neu = run.last_text[run.marke_ab:]
        run.marke_ab = len(run.last_text)
        if not run.session_id or "[[" not in neu or not cfg.load_settings()["team"]["aktiv"]:
            return
        from server.team import chat as teamchat
        from server.team.engine import AuftragFehler
        try:
            t = teamchat.uebergeben(neu, run.session_id, run.cwd)
        except AuftragFehler as e:
            print(f"[firma] Übergabe: {e}", flush=True)
            return
        if t:
            run.emit({"type": "firma", "auftrag": t["id"]})
    except Exception as e:
        print(f"[firma] Übergabe fehlgeschlagen: {type(e).__name__}: {e}", flush=True)


# So lange darf ein Prozess nach seinem Zug hoechstens auf Hintergrundaufgaben
# warten. Ein `tail -f` im Hintergrund wuerde ihn sonst fuer immer festhalten.
NACHLAUF_MAX = 1800


def _nachlauf_beenden(run):
    """Wecker: der Nachlauf ist abgelaufen, der Prozess soll gehen."""
    if run.done or run.stdin_closed or not run.nachlauf:
        return
    print(f"[run] Nachlauf nach {NACHLAUF_MAX} s beendet, "
          f"{len(run.hintergrund)} Hintergrundaufgabe(n) offen", flush=True)
    run.nachlauf = False
    run.stdin_closed = True
    run.emit({"type": "nachlauf_ende"})
    try:
        run.proc.stdin.close()
    except Exception:
        pass


MODEL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9./,:_-]{0,63}$")
EFFORTS = {"low", "medium", "high", "xhigh", "max"}


def start_run(prompt, work_dir, mode, model="", session_id=None, resume_at=None,
              effort="", chat=False):
    """Gemeinsamer Unterbau für Chat-Läufe und geplante Aufgaben.

    chat: ein Lauf aus dem Chat — nur er kennt das Ticket-Board und die Firma,
    geplante Aufgaben nicht."""
    gc_runs()
    run_id = uuid.uuid4().hex
    conf = cfg.load_settings()
    run = Run(run_id, work_dir, session_id, model, initial_prompt=prompt)

    cmd = [
        claude_bin() or "claude", "-p",
        "--output-format", "stream-json",
        "--input-format", "stream-json",   # Nachricht via stdin -> Inject möglich
        "--verbose",
        "--include-partial-messages",
        # Meldet jede angenommene Nachricht samt uuid zurück: so springt eine
        # Karte des Ticket-Boards an die Stelle im Chat.
        "--replay-user-messages",
        "--permission-mode", mode,
        "--chrome",   # Claude in Chrome: im -p-Modus nicht automatisch aktiv
    ]
    if model:
        cmd += ["--model", model]
    cmd += ["--fallback-model", cfg.fallback_models(model)]
    if effort in EFFORTS:
        cmd += ["--effort", effort]
    persona = load_persona()
    # Feste Texte: ändern sich nie während einer Session und bleiben so im
    # Zwischenspeicher. Alles Veränderliche steht hinten an der Nachricht.
    if chat and conf["tiles"]["tickets"]:
        persona = (persona + "\n\n" + tickmod.regeln()).strip()
    if chat and conf["team"]["aktiv"]:
        from server.team import chat as teamchat
        persona = (persona + "\n\n" + teamchat.regeln()).strip()
    if persona:
        cmd += ["--append-system-prompt", persona]
    if session_id:
        cmd += ["--resume", session_id]
        if resume_at:
            # Bearbeitete Nachricht: bis zu dieser Stelle fortsetzen, als
            # eigene neue Sitzung — das Original bleibt unangetastet.
            cmd += ["--resume-session-at", resume_at, "--fork-session"]

    RUNS[run_id] = run
    run.task = asyncio.create_task(run_claude(run, cmd))
    return run


# ---------- Läufe über einen Server-Neustart retten ----------
# Ein Lauf lebt nur im Speicher dieses Prozesses (RUNS). Endet der Server, ohne
# herunterzufahren (kill, ein neuer Start mit neuerem Code beendet den alten,
# Absturz), läuft der claude-Prozess trotzdem weiter und schreibt seine Antwort
# fertig in die Sitzungsdatei — nur kannte der neue Server die Lauf-ID nicht.
# Die Oberfläche bekam 404 („Lauf nicht mehr verfügbar"), die Antwort sah
# niemand, im Raum fehlte die Sprechblase (06.10.2026 zweimal hintereinander).
#
# Darum steht jeder laufende claude-Prozess in laeufe.json. Der neue Server
# nimmt ihn beim Start unter DERSELBEN Lauf-ID wieder auf und liest die Antwort
# aus der Sitzungsdatei mit; die Oberfläche dockt einfach wieder an. Text kommt
# dabei blockweise statt Wort für Wort. ⏻ fährt dagegen sauber herunter und
# beendet die Läufe selbst — dort bleibt nichts übrig, was zu retten wäre.
LAEUFE = BASE_DIR / "laeufe.json"
NACHLESEN_TAKT = 1.0


def _laeufe_lesen() -> dict:
    try:
        d = json.loads(LAEUFE.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def _laeufe_schreiben(d: dict):
    try:
        if not d:
            LAEUFE.unlink(missing_ok=True)
            return
        tmp = LAEUFE.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(LAEUFE)
    except OSError as e:
        print(f"[run] laeufe.json: {e}", flush=True)


def merken(run, programm=None):
    """Laufenden claude-Prozess vermerken: beim Start und sobald die Sitzung feststeht."""
    if not run.proc:
        return
    d = _laeufe_lesen()
    e = d.get(run.id) or {"pid": run.proc.pid, "kennung": _kennung(run.proc.pid),
                          "programm": programm or "", "cwd": run.cwd,
                          "start": run.started, "model": run.model}
    if run.auftrag_id:
        e["auftrag"] = run.auftrag_id
    e["session_id"] = run.session_id
    d[run.id] = e
    _laeufe_schreiben(d)


def vergessen(run_id):
    d = _laeufe_lesen()
    if d.pop(run_id, None) is not None:
        _laeufe_schreiben(d)


def _kennung(pid) -> str:
    """Woran sich ein Prozess über seine PID hinaus wiedererkennen lässt: seine
    Startzeit. PIDs werden wiederverwendet, und laeufe.json übersteht auch einen
    Neustart des Rechners — ohne diesen Abgleich beendete die Rettung irgendein
    Programm, das zufällig dieselbe PID bekam. "" = läuft nicht oder nicht
    feststellbar; dann gilt der Prozess als fremd und wird nie angefasst."""
    if not isinstance(pid, int) or pid <= 0:
        return ""
    try:
        if os.name == "nt":
            # os.kill(pid, 0) wäre hier CTRL_C_EVENT, kein Nachsehen.
            import ctypes
            k = ctypes.windll.kernel32
            h = k.OpenProcess(0x1000, False, pid)        # PROCESS_QUERY_LIMITED_INFORMATION
            if not h:
                return ""
            try:
                code = ctypes.c_ulong()
                if not k.GetExitCodeProcess(h, ctypes.byref(code)) or code.value != 259:  # STILL_ACTIVE
                    return ""
                t = [ctypes.c_ulonglong() for _ in range(4)]   # Erzeugung, Ende, Kernel, User
                if not k.GetProcessTimes(h, *(ctypes.byref(x) for x in t)):
                    return ""
                return str(t[0].value)
            finally:
                k.CloseHandle(h)
        if Path("/proc/self/stat").exists():
            # Der Programmname in Klammern darf Leerzeichen enthalten: erst hinter
            # der letzten ")" zählen. Danach Feld 3 (Zustand) … Feld 22 (Startzeit).
            felder = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()
            if felder[0] in ("Z", "X"):                  # beendet, noch nicht abgeholt
                return ""
            boot = Path("/proc/sys/kernel/random/boot_id").read_text().strip()
            return f"{boot}:{felder[19]}"
        # macOS und andere ohne /proc
        # LC_ALL=C: sonst hinge der Vergleich an der Sprache, mit der der Server startete
        r = subprocess.run(["ps", "-o", "lstart=", "-p", str(pid)], capture_output=True, text=True,
                           timeout=5, env={**os.environ, "LC_ALL": "C"})
        return r.stdout.strip() if r.returncode == 0 else ""
    except (OSError, IndexError, ValueError, subprocess.SubprocessError):
        return ""


def _lebt(pid, kennung) -> bool:
    """Läuft der Prozess noch — und ist es noch derselbe, den wir gestartet haben?"""
    return bool(kennung) and _kennung(pid) == kennung


def _zeit(ts) -> float:
    try:
        return datetime.fromisoformat(str(ts).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 0.0


class _Leser:
    """Neue Zeilen der Sitzungsdatei -> dieselben Ereignisse, die run_claude aus
    dem Live-Strom macht. Gelesen wird nur, was nach dem Start des Laufs kam."""

    def __init__(self, run):
        self.run = run
        self.ab = run.started - 2       # die Zeitstempel schreibt claude selbst
        self.pos = 0
        self.rest = b""
        self.prompt_gesehen = False
        self.thinking = False
        self.fertig = False             # letzte Antwort regulär abgeschlossen

    def lesen(self, datei):
        try:
            with datei.open("rb") as fh:
                fh.seek(self.pos)
                data = fh.read()
        except OSError:
            return
        self.pos += len(data)
        data = self.rest + data
        cut = data.rfind(b"\n") + 1          # halbe letzte Zeile wird gerade geschrieben
        data, self.rest = data[:cut], data[cut:]
        for line in data.split(b"\n"):
            if not line.strip():
                continue
            try:
                ev = json.loads(line.decode("utf-8", "replace"))
            except Exception:
                continue
            if isinstance(ev, dict):
                self.eintrag(ev)

    def eintrag(self, ev):
        if ev.get("isSidechain") or _zeit(ev.get("timestamp")) < self.ab:
            return
        msg = ev.get("message") if isinstance(ev.get("message"), dict) else {}
        content = msg.get("content")
        if ev.get("type") == "user":
            if isinstance(content, list) and any(isinstance(b, dict) and b.get("type") == "tool_result"
                                                 for b in content):
                for b in content:
                    if isinstance(b, dict) and b.get("type") == "tool_result":
                        self.run.emit(_ergebnis_ereignis(b))
                return
            txt = extract_text(content).strip()
            if ev.get("isMeta") or not txt or txt.startswith("<"):
                return
            if not self.prompt_gesehen:      # die Nachricht, mit der der Lauf begann
                self.prompt_gesehen = True
                # Auf sie bezieht sich eine Markerzeile am Ende der Antwort
                self.run.letzte_uuid = str(ev.get("uuid") or "")
                return
            self.fertig = False
            self.run.emit({"type": "user_inject", "text": txt, "urls": []})
        elif ev.get("type") == "assistant" and isinstance(content, list):
            for b in content:
                if not isinstance(b, dict):
                    continue
                if b.get("type") == "text" and b.get("text"):
                    # Zwei Textblöcke ohne Werkzeug dazwischen klebten sonst ohne
                    # Leerzeile aneinander (live trennt sie der Stream selbst).
                    davor = self.run.events and self.run.events[-1].get("type") == "text"
                    self.run.emit({"type": "text", "text": ("\n\n" if davor else "") + b["text"]})
                elif b.get("type") == "thinking" and not self.thinking:
                    self.thinking = True
                    self.run.emit({"type": "thinking_marker"})
                elif b.get("type") == "tool_use":
                    self.run.emit(_werkzeug_ereignis(b))
            self.fertig = msg.get("stop_reason") in ("end_turn", "stop_sequence")


async def _nachlesen(run, pid, kennung):
    """Hintergrund-Task für einen aufgenommenen Lauf: Sitzungsdatei mitlesen,
    bis der claude-Prozess weg ist."""
    # Im Thread: unter macOS startet _kennung jedes Mal `ps` (bis 5 s), und das
    # hielte im Sekundentakt die ganze Ereignisschleife an.
    def lebt_noch():
        return asyncio.to_thread(_lebt, pid, kennung)
    lief = await lebt_noch()
    leser = _Leser(run)
    datei = None
    try:
        while True:
            lebt = await lebt_noch()
            if datei is None:
                datei = next(iter(PROJECTS_DIR.glob(f"*/{run.session_id}.jsonl")), None)
            if datei is not None:
                leser.lesen(datei)           # nach dem Lebenszeichen: steht dann alles drin
            if not lebt:
                break
            await asyncio.sleep(NACHLESEN_TAKT)
        if leser.fertig:
            if not run.agent_slug:
                _firma_marke(run)
            run.emit({"type": "done", "session_id": run.session_id})
        else:
            run.emit({"type": "error", "message": cfg.L(
                "⚠ CONSTRUCT wurde neu gestartet, bevor die Antwort fertig war. Schick einfach nochmal.",
                "⚠ CONSTRUCT restarted before the answer was finished. Just send it again.")})
    except asyncio.CancelledError:
        # Stop-Knopf: wie bei einem eigenen Lauf den Prozess beenden
        run.stopped = True
        if await lebt_noch():
            try:
                os.kill(pid, signal.SIGTERM)
            except OSError:
                pass
        run.emit({"type": "error", "message": "⏹ Gestoppt."})
        raise
    except Exception as e:
        print(f"[run] nachlesen: {type(e).__name__}: {e}", flush=True)
        run.emit({"type": "error", "message": f"Server-Fehler: {e}"})
    finally:
        vergessen(run.id)
        run.finish()
        if lief and not getattr(run, "stopped", False):
            maybe_notify(run)


def aufnehmen():
    """Beim Serverstart: Läufe des vorigen Servers unter ihrer Lauf-ID wieder
    aufnehmen. Auch schon beendete — deren Antwort steht dann fertig da."""
    for rid, e in _laeufe_lesen().items():
        if rid in RUNS or not isinstance(e, dict):
            continue
        if e.get("auftrag"):
            # Ein Zug der Firma: sein Bus-Token starb mit dem alten Server, liefern
            # kann er nicht mehr — und der Dispatcher stellt dieselbe Nachricht
            # gleich neu zu (engine.wieder_aufnehmen), mit --resume auf DIESELBE
            # Sitzung. Liefe der alte weiter, schrieben zwei Prozesse in eine.
            if _lebt(e.get("pid"), e.get("kennung") or ""):
                try:
                    os.kill(e["pid"], signal.SIGTERM)
                except OSError:
                    pass
            vergessen(rid)
            continue
        sid = e.get("session_id")
        if not sid:
            # Vor dem ersten Lebenszeichen abgerissen: keine Sitzung, nichts nachzulesen
            vergessen(rid)
            continue
        run = Run(rid, e.get("cwd") or "", sid, e.get("model") or "")
        run.started = float(e.get("start") or time.time())
        run.stdin_closed = True       # stdin hing am alten Server; Nachgeschobenes wartet
        RUNS[rid] = run
        run.emit({"type": "session", "session_id": sid})
        run.task = asyncio.create_task(_nachlesen(run, e.get("pid"), e.get("kennung") or ""))
        print(f"[run] Lauf {rid[:8]} nach Neustart wieder aufgenommen (Sitzung {sid[:8]})", flush=True)
