"""Läufe mit fremden Modellen über Hermes, inklusive Verlaufs-Übernahme
zwischen den Maschinen.
"""
import asyncio
import time
import uuid

from server import bonsai as bonsaimod
from server import config as cfg
from server import hermes as hermesmod
from server import llm as llmmod

from server.core import PROJECTS_DIR
from server.runs import RUNS, Run, gc_runs, is_pdf, maybe_notify, pdf_note
from server.sessions import SID_RE, _parse_transcript_lines


# ---------- Verlaufs-Übernahme zwischen den Maschinen ----------
def claude_history_msgs(sid: str, max_n=30, max_chars=40000):
    """Verlauf einer Claude-Session als Chat-Messages — damit ein Wechsel zu
    einem externen Modell das Gespräch nahtlos fortsetzt."""
    if not SID_RE.match(sid or ""):
        return []
    f = next(iter(PROJECTS_DIR.glob(f"*/{sid}.jsonl")), None)
    if f is None:
        return []
    try:
        msgs = _parse_transcript_lines(f.read_bytes())
    except Exception:
        return []
    out, total = [], 0
    for m in reversed(msgs):
        total += len(m["text"])
        if out and (len(out) >= max_n or total > max_chars):
            break
        out.append({"role": "user" if m["role"] == "user" else "assistant",
                    "content": m["text"]})
    return list(reversed(out))


# ---------- Läufe mit Hermes (Werkzeuge für fremde Modelle) ----------
async def run_hermes(run, sess, prompt, allow_writes: bool):
    """Hintergrund-Task für Hermes-Läufe.

    Spricht dieselbe Ereignis-Sprache wie run_claude — das Frontend merkt
    keinen Unterschied zwischen den Maschinen dahinter.
    """
    run.hermes = sess
    t0 = time.time()
    is_bonsai = llmmod.split_model(run.model)[0] == "bonsai"
    try:
        if is_bonsai:
            # Der Server liegt erst im VRAM, wenn jemand ihn braucht — jetzt.
            # Das Laden dauert Sekunden; ohne Hinweis sähe es nach Hängen aus.
            if not bonsaimod.running():
                run.emit({"type": "text", "text": "_⏳ Bonsai wird in den VRAM geladen …_\n\n"})
            err = await asyncio.to_thread(bonsaimod.ensure_running)
            if err:
                raise hermesmod.AcpError(err)
        result = await sess.run(prompt, run.emit, allow_writes=allow_writes,
                                images=run.images)
        # Ohne "done" bleibt die Oberfläche im Laufzustand und merkt sich die
        # Sitzung nicht — die naechste Nachricht begaenne dann von vorn.
        run.session_id = "hermes-" + sess.session_id
        # EIN Stats-Event in den Feldnamen, die das Frontend kennt (wie bei
        # run_claude): duration_ms, out, ctx, model.
        usage = (result or {}).get("usage") or {}
        run.emit({"type": "stats",
                  "duration_ms": int((time.time() - t0) * 1000),
                  "out": usage.get("outputTokens") or 0,
                  "ctx": (usage.get("inputTokens") or 0)
                         + (usage.get("cachedReadTokens") or 0),
                  "model": run.model})
        run.emit({"type": "done", "session_id": run.session_id})
    except asyncio.CancelledError:
        print("[hermes] gestoppt", flush=True)
        run.stopped = True
        sess.cancel()          # dem Agenten sagen, dass Schluss ist
        await asyncio.sleep(0.4)   # kurz Zeit für einen sauberen Abgang
        sess.kill()
        run.emit({"type": "error", "message": "⏹ Gestoppt."})
        raise
    except hermesmod.AcpError as e:
        run.emit({"type": "error", "message": f"⚠ Hermes: {e}"})
    except Exception as e:
        print(f"[hermes] fehler: {type(e).__name__}: {e}", flush=True)
        run.emit({"type": "error", "message": f"Server-Fehler: {type(e).__name__}: {e}"})
    finally:
        if is_bonsai:
            bonsaimod.touch()   # Leerlauf zählt ab Ende des Laufs, nicht ab Start
        sess.kill()
        run.stdin_closed = True
        run.finish()
        if not getattr(run, "stopped", False):
            maybe_notify(run)


def carry_over_block(session_id: str) -> str:
    """Verlauf einer Sitzung als Textblock — für den Wechsel der Maschine.

    Claude Code und Hermes führen ihre Sitzungen in getrennten Ablagen; eine
    laufende Unterhaltung lässt sich nicht von der einen in die andere
    übergeben. Statt sie stillschweigend zu verlieren, wird der bisherige
    Verlauf als Kontext in die neue Sitzung gegeben. Das ist keine echte
    Fortsetzung — Werkzeug-Zustand und gelesene Dateien bleiben zurück — aber
    ehrlicher als ein Assistent, der plötzlich nichts mehr weiß.
    """
    sid = session_id or ""
    msgs, herkunft = [], ""
    if sid.startswith("hermes-"):
        msgs = hermesmod.session_messages(sid[len("hermes-"):])
        herkunft = "einem anderen Modell über Hermes"
    elif sid.startswith("llm-"):
        return llmmod.history_block(sid)
    elif sid:
        msgs = claude_history_msgs(sid)
        herkunft = "Claude Code"
    if not msgs:
        return ""
    lines = [cfg.L(f"[Kontext: Dieses Gespräch lief bisher mit {herkunft}; "
                   f"{cfg.user_name()} wechselt jetzt das Modell. Bisheriger Verlauf:]",
                   f"[Context: this conversation has so far run on {herkunft}; "
                   f"{cfg.user_name()} is now switching models. History so far:]")]
    total = 0
    for m in msgs[-30:]:
        t = str(m.get("text") or m.get("content") or "")
        total += len(t)
        if total > 40000:
            break
        who = cfg.user_name() if m.get("role") == "user" else cfg.L("Assistent", "Assistant")
        lines.append(f"{who}: {t}")
    lines.append(cfg.L("[Ende des Verlaufs — antworte jetzt auf die folgende neue Nachricht.]",
                       "[End of history — now reply to the following new message.]"))
    return "\n\n".join(lines)


def start_hermes_run(text, images, pid, model, work_dir, mode, session_id=None):
    """Lauf über Hermes starten.

    session_id mit Präfix "hermes-" führt die Sitzung fort; alles andere
    (Claude- oder Chat-Sitzung) beginnt eine neue — die Verläufe liegen in
    verschiedenen Ablagen und lassen sich nicht ineinander überführen.
    """
    prompt = (text or "").strip()
    # Bilder gehen als ACP-Blöcke mit (hermes._image_blocks); PDFs kennt ACP
    # nicht, die bekommt das Modell wie bei claude als Hinweis + Textauszug.
    pdfs = [p for p in (images or []) if is_pdf(p)]
    if pdfs:
        prompt = f"{prompt}\n\n{pdf_note(pdfs)}".strip()
    prev = session_id if (session_id or "").startswith("hermes-") else ""
    carried = False
    if session_id and not prev:
        # Maschinenwechsel: neue Hermes-Sitzung, aber mit dem bisherigen
        # Verlauf als Kontext — sonst stünde der Assistent ohne Gedächtnis da.
        block = carry_over_block(session_id)
        if block:
            prompt = block + "\n\n" + prompt
            carried = True
    sess = hermesmod.AcpSession(work_dir, model=f"{pid}:{model}",
                                session_id=prev[len("hermes-"):] if prev else "")
    gc_runs()
    run_id = uuid.uuid4().hex
    run = Run(run_id, work_dir, prev or None, f"{pid}:{model}", initial_prompt=prompt)
    run.images = images or []
    run.stdin_closed = True   # kein Mid-Turn-Inject: ACP kennt das nicht
    RUNS[run_id] = run
    if carried:
        # Sichtbar machen: der Nutzer soll wissen, dass eine neue Sitzung
        # begonnen hat und was davon mitgenommen wurde.
        run.emit({"type": "text", "text":
                  "_↪ Modellwechsel: neue Sitzung, bisheriger Verlauf als "
                  "Kontext übernommen._\n\n"})
    # Persona als Hermes-Identität, Kalender frisch an jede Nachricht — wie
    # bei Claude (runs.start_run → load_persona).
    hermesmod.sync_soul()
    run.task = asyncio.create_task(run_hermes(run, sess, hermesmod.with_context(prompt),
                                              mode != "plan"))
    return run
