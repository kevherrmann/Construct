"""Entkoppelte Läufe mit dem claude-CLI: starten, streamen, einwerfen,
Nachlauf, Benachrichtigung wenn ein langer Lauf unbeobachtet fertig wird.
"""
import asyncio
import json
import os
import re
import threading
import time
import uuid
from pathlib import Path

from server import config as cfg
from server import telegram_bot as tgmod

from server.core import claude_bin, claude_env, friendly_claude_error, load_persona
from server.sessions import model_short


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
        self.nachlauf = False            # Zug fertig, Prozess wartet auf den Hintergrund
        self.zug_offen = False           # laeuft gerade ein Zug (fuer "neuer_zug")
        self.last_text = ""              # Text des letzten Turns (für Telegram-Notify)
        self.notify_always = False       # geplante Aufgaben melden sich immer per Telegram
        self.task_title = ""             # Titel der geplanten Aufgabe (für die Meldung)

    def emit(self, ev):
        if ev.get("type") == "text":
            # hier statt in run_claude, damit auch Hermes-Läufe eine
            # Telegram-Zusammenfassung (maybe_notify) bekommen
            self.last_text += ev.get("text", "")
        # aufeinanderfolgende Text-Events zusammenfassen -> Puffer/Replay schlank
        if ev.get("type") == "text" and self.events and self.events[-1].get("type") == "text":
            self.events[-1]["text"] += ev.get("text", "")
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
    tail = run.last_text.strip()[-600:]
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
            if t in ("assistant", "stream_event") and not run.zug_offen:
                # Der erste Inhalt eines Zuges. Kommt er im Nachlauf — also
                # ohne dass Kevin etwas geschickt hat — hat eine
                # Hintergrundaufgabe den Zug ausgeloest, und die Oberflaeche
                # braucht eine neue Sprechblase dafuer.
                run.zug_offen = True
                if run.nachlauf:
                    run.nachlauf = False
                    run.emit({"type": "neuer_zug"})
            if t == "system" and ev.get("subtype") == "init":
                run.session_id = ev.get("session_id", run.session_id)
                run.emit({"type": "session", "session_id": run.session_id})
            elif t == "system" and ev.get("subtype") == "background_tasks_changed":
                # Die eine verlaessliche Liste: claude schickt sie bei jedem
                # Start und Ende einer Hintergrundaufgabe komplett.
                run.hintergrund = {x.get("task_id"): x.get("description") or x.get("task_type") or "?"
                                   for x in (ev.get("tasks") or []) if x.get("task_id")}
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
                        run.emit({
                            "type": "tool",
                            "id": block.get("id"),
                            "name": block.get("name", "?"),
                            "input": block.get("input", {}),
                        })
            elif t == "user":
                content = ev.get("message", {}).get("content")
                if isinstance(content, list):
                    for block in content:
                        if isinstance(block, dict) and block.get("type") == "tool_result":
                            c = block.get("content")
                            if isinstance(c, list):
                                c = "\n".join(x.get("text", "") for x in c if isinstance(x, dict))
                            run.emit({
                                "type": "tool_result",
                                "id": block.get("tool_use_id"),
                                "content": str(c)[:6000],
                                "is_error": bool(block.get("is_error")),
                            })
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
                    "model": echt or run.model,
                })
                run.zug_offen = False
                if run.hintergrund and time.time() - run.started < NACHLAUF_MAX:
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
                    # zweiten auf derselben Sitzung.
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
        run.stdin_closed = True
        run.finish()
        if not getattr(run, "stopped", False):
            maybe_notify(run)


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


def start_run(prompt, work_dir, mode, model="", session_id=None):
    """Gemeinsamer Unterbau für Chat-Läufe und geplante Aufgaben."""
    cmd = [
        claude_bin() or "claude", "-p",
        "--output-format", "stream-json",
        "--input-format", "stream-json",   # Nachricht via stdin -> Inject möglich
        "--verbose",
        "--include-partial-messages",
        "--permission-mode", mode,
    ]
    if model:
        cmd += ["--model", model]
    persona = load_persona()
    if persona:
        cmd += ["--append-system-prompt", persona]
    if session_id:
        cmd += ["--resume", session_id]

    gc_runs()
    run_id = uuid.uuid4().hex
    run = Run(run_id, work_dir, session_id, model, initial_prompt=prompt)
    RUNS[run_id] = run
    run.task = asyncio.create_task(run_claude(run, cmd))
    return run
