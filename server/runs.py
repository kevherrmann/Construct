"""Entkoppelte Läufe mit dem claude-CLI: starten, streamen, einwerfen,
Nachlauf, Benachrichtigung wenn ein langer Lauf unbeobachtet fertig wird.
"""
import asyncio
import json
import os
import re
import secrets
import sys
import threading
import time
import uuid
from pathlib import Path

from server import config as cfg
from server import telegram_bot as tgmod
from server import tickets as tickmod

from server.core import LIMIT_HIT, BASE_DIR, bus_auth_header, claude_bin, claude_env, extract_text, friendly_claude_error, load_persona
from server.sessions import model_short, nutzer_uuids_bis


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
    def __init__(self, run_id, cwd, session_id=None, model="", initial_prompt="",
                 tickets=False, fork=None):
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
        # Tickets (server/tickets.py): nur Läufe aus dem Chat ordnen zu. `fork` =
        # (alte Session, Stelle) bei einer bearbeiteten Nachricht; `ticket_vorgabe`
        # Kevins Wahl (/ticket) für eine Session, die es noch nicht gab.
        self.tickets = tickets
        self.token = secrets.token_hex(16)   # Einmal-Token der Ticket-Werkzeuge dieses Laufs
        self.fork = fork
        self.ticket_vorgabe = None
        self.letzte_uuid = ""            # zuletzt angenommene Nachricht von Kevin
        # Team-Modus (server/team/): Läufe, die einem Mitarbeiter gehören — ein
        # Zug in einem Auftrag oder ein Gespräch mit ihm. Im Chat bleibt alles leer.
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
        elif ev.get("type") == "tool" and self.last_text and not self.last_text.endswith("\n"):
            # Zwischen zwei Textblöcken lag ein Werkzeugaufruf. Ohne Trenner klebte
            # im Verlauf "Ich schau erst nach.Passt, ich baue." zusammen.
            self.last_text += "\n\n"
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
                _tickets_abzweigen(run)
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
                if run.tickets:
                    _tickets_zuordnen(run, ev, content)
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
                run.cache_read = u.get("cache_read_input_tokens") or 0
                run.cache_write = u.get("cache_creation_input_tokens") or 0
                run.frisch = u.get("input_tokens") or 0
                # total_cost_usd ist die einzige echte Geldzahl im System — die
                # Firma zeigt sie je Auftrag an, also mitnehmen statt wegwerfen.
                run.cost_usd = ev.get("total_cost_usd") or 0.0
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
                if run.agent_slug and run.session_id and not run.auftrag_id:
                    # Langlebige Sitzung im Direktgespräch mit einem Mitarbeiter:
                    # beim nächsten Mal wird fortgesetzt. Züge in einem Auftrag
                    # gehören dem Auftrag — sie dürfen diese Beziehung nicht
                    # überschreiben, sonst landet das nächste Gespräch mitten im
                    # Auftragskontext.
                    from server.team import gedaechtnis
                    gedaechtnis.set_chat_session(run.agent_slug, run.session_id)
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


def bus_config(run, base: str, firma: bool = False) -> str:
    """--mcp-config für die Ticket-Werkzeuge dieses Laufs (construct_mcp.py).

    Als Zeichenkette statt Datei: das Token gilt nur für diesen Lauf und
    gehört auf keine Platte. Ohne --strict-mcp-config — die MCP-Server aus den
    Einstellungen des Nutzers bleiben, wir kommen dazu.
    """
    env = {"CONSTRUCT_RUN": run.id, "CONSTRUCT_TOKEN": run.token, "CONSTRUCT_BASE": base}
    if bus_auth_header():
        env["CONSTRUCT_AUTH"] = bus_auth_header()
    if firma:
        env["CONSTRUCT_FIRMA"] = "1"
    return json.dumps({"mcpServers": {"construct": {
        "command": sys.executable, "args": [str(BASE_DIR / "construct_mcp.py")], "env": env,
        # Ohne das bleiben die Werkzeuge hinter ToolSearch versteckt, sobald der
        # Nutzer viele MCP-Werkzeuge hat (gemessen 05.10.2026) — dann kostet jeder
        # Gebrauch einen eigenen Zug.
        "alwaysLoad": True}}})


def _tickets_zuordnen(run, ev, content):
    """Kevins Nachricht ist angenommen (claude meldet sie dank
    --replay-user-messages samt uuid zurück): sie bekommt ein Ticket.

    Fehler hier dürfen den Lauf nie stören — Tickets sind Buchhaltung.
    """
    try:
        uuid = ev.get("uuid")
        if not uuid or not run.session_id or ev.get("parent_tool_use_id") or ev.get("isSynthetic"):
            return
        text = extract_text(content).strip()
        # Tool-Ergebnisse (kein Text) und Meldungen des Systems (Hintergrundaufgabe
        # fertig, <task-notification> …) sind keine Nachricht von Kevin.
        if not text or text.startswith("<") or text.startswith("Caveat"):
            return
        run.letzte_uuid = uuid
        vorgabe, run.ticket_vorgabe = run.ticket_vorgabe, None
        r = tickmod.nachricht(run.session_id, uuid, text, run.cwd, vorgabe)
        # Die Oberfläche kennt die uuid ihrer eben gesendeten Nachricht sonst
        # nicht (sie baut sie selbst auf) — ohne sie gäbe es kein ✂ und keinen
        # Ticket-Trenner, bevor die Session neu geladen wird.
        run.emit({"type": "ticket", "uuid": uuid, "nr": r["nr"], "titel": r["titel"]})
    except Exception as e:
        print(f"[tickets] Zuordnung fehlgeschlagen: {type(e).__name__}: {e}", flush=True)


def _tickets_abzweigen(run):
    """Bearbeitete Nachricht: die neue Session übernimmt die Tickets der alten
    bis zu der Stelle, an der abgezweigt wurde."""
    if not (run.tickets and run.fork and run.session_id):
        return
    try:
        alt, stelle = run.fork
        if alt != run.session_id:
            tickmod.abzweigen(alt, run.session_id, nutzer_uuids_bis(alt, stelle))
    except Exception as e:
        print(f"[tickets] Abzweigen fehlgeschlagen: {type(e).__name__}: {e}", flush=True)


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
              effort="", tickets=False, ticket_vorgabe=None, bus_base=""):
    """Gemeinsamer Unterbau für Chat-Läufe und geplante Aufgaben.

    tickets: ob die Nachrichten dieses Laufs Tickets bekommen — nur im Chat,
    nicht bei geplanten Aufgaben, und nur wenn die Kachel an ist. bus_base:
    unter dieser Adresse erreichen die Ticket-Werkzeuge den Server (leer = der
    Assistent bekommt keine Werkzeuge, die Zuordnung läuft trotzdem)."""
    gc_runs()
    run_id = uuid.uuid4().hex
    conf = cfg.load_settings()
    tickets = tickets and conf["tiles"]["tickets"]
    fork = (session_id, resume_at) if (resume_at and session_id) else None
    run = Run(run_id, work_dir, session_id, model, initial_prompt=prompt,
              tickets=tickets, fork=fork)
    run.ticket_vorgabe = ticket_vorgabe
    mit_werkzeugen = tickets and bool(bus_base) and conf["tickets"]["assistent"]

    cmd = [
        claude_bin() or "claude", "-p",
        "--output-format", "stream-json",
        "--input-format", "stream-json",   # Nachricht via stdin -> Inject möglich
        "--verbose",
        "--include-partial-messages",
        # Meldet jede angenommene Nachricht samt uuid zurück: so findet
        # server/tickets.py sie im Transkript wieder.
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
    if mit_werkzeugen:
        # Fester Text: ändert sich nie während einer Session und bleibt so im
        # Zwischenspeicher. Alles Veränderliche steht hinten an der Nachricht.
        persona = (persona + "\n\n" + tickmod.regeln()).strip()
        # --strict-mcp-config ist Pflicht, nicht Zierde: ohne es lädt `claude -p`
        # mit einer --mcp-config ALLE MCP-Server des Nutzers mit (Gmail, Drive,
        # Browser …) — gemessen 05.10.2026: +1,3k Tokens Kontext je Aufruf und
        # Werkzeuge, die der Chat bisher nicht hatte. So bleibt alles wie vorher
        # und es kommen nur unsere zwei Werkzeuge dazu.
        firma = conf["team"]["aktiv"]
        erlaubt = ["mcp__construct__ticket_neu", "mcp__construct__ticket_zuordnen"]
        if firma:
            erlaubt += ["mcp__construct__firma_auftrag", "mcp__construct__firma_stand"]
        cmd += ["--mcp-config", bus_config(run, bus_base, firma), "--strict-mcp-config",
                # Auch in Modi, die sonst nachfragen würden (im -p-Modus niemand antwortet).
                "--allowedTools", *erlaubt]
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
