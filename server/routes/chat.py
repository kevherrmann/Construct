"""API: Chat-Läufe starten, streamen, einwerfen, stoppen."""
import asyncio
import os

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse

import hermes as hermesmod
import llm as llmmod

from server.core import ALLOWED_MODES, DEFAULT_CWD, sse
from server.hermes_runs import carry_over_block, start_hermes_run
from server.runs import MODEL_RE, RUNS, SSE_HEADERS, build_prompt, gc_runs, start_run, stdin_message

router = APIRouter()


@router.post("/api/chat")
async def chat(req: Request):
    """Startet einen entkoppelten Lauf und gibt sofort die run_id zurück."""
    body = await req.json()
    text = (body.get("message") or "").strip()
    session_id = body.get("session_id")
    images = body.get("images") or []  # Server-Pfade der Anhänge (Bilder und PDFs)
    if not text and not images:
        return JSONResponse({"error": "leere Nachricht"}, status_code=400)
    req_cwd = body.get("cwd")
    work_dir = req_cwd if (isinstance(req_cwd, str) and os.path.isdir(req_cwd)) else DEFAULT_CWD
    req_mode = body.get("mode")
    mode = req_mode if req_mode in ALLOWED_MODES else "bypassPermissions"
    req_model = (body.get("model") or "").strip()
    model = req_model if MODEL_RE.match(req_model) else ""

    # Fremdes Modell ("anbieter:modell") -> Hermes statt claude-CLI.
    # Reiner Chat ohne Werkzeuge gibt es nicht mehr: die Oberfläche zeigt nur
    # noch werkzeugfähige Modelle, und ein Modell, das nichts tun kann, wäre
    # in einer Werkzeug-Oberfläche eine Falle.
    pid, ext_model = llmmod.split_model(model)
    if pid:
        if not hermesmod.hermes_bin():
            return JSONResponse(
                {"error": "Für fremde Modelle wird Hermes gebraucht — es ist "
                          "nicht installiert. Unter ⚙ Einstellungen → "
                          "„Modelle & Anbieter“ lässt es sich einrichten."},
                status_code=400)
        run = start_hermes_run(text, images, pid, ext_model, work_dir, mode, session_id)
        return {"run_id": run.id, "session_id": run.session_id}

    prompt = build_prompt(text, images)
    if session_id and session_id.startswith("hermes-"):
        block = carry_over_block(session_id)
        if block:
            prompt = block + "\n\n" + prompt
        session_id = None      # Claude kann eine Hermes-Sitzung nicht fortsetzen
    if session_id and session_id.startswith("llm-"):
        # Wechsel extern -> Claude: Verlauf als Kontext mitgeben, neue Claude-Session
        hist = llmmod.history_block(session_id)
        if hist:
            prompt = hist + "\n\n" + prompt
        session_id = None

    run = start_run(prompt, work_dir, mode, model, session_id)
    return {"run_id": run.id, "session_id": session_id}


@router.post("/api/inject/{run_id}")
async def inject(run_id: str, req: Request):
    """Schiebt dem LAUFENDEN claude-Prozess eine weitere Nachricht nach (kein
    Warten auf das Ende, kein --resume) — wie Weitertippen im Terminal."""
    run = RUNS.get(run_id)
    if not run or run.done or run.stdin_closed or not run.proc:
        return JSONResponse({"error": "Lauf nimmt nichts mehr an"}, status_code=409)
    body = await req.json()
    text = (body.get("message") or "").strip()
    images = body.get("images") or []
    urls = body.get("urls") or []
    if not text and not images:
        return JSONResponse({"error": "leere Nachricht"}, status_code=400)
    run.emit({"type": "user_inject", "text": text, "urls": urls})
    if run.nachlauf:
        # Kevin schreibt, waehrend der Prozess nur noch auf den Hintergrund
        # wartet: ein neuer Zug in derselben Sitzung. Kein "neuer_zug" hier —
        # das user_inject-Ereignis oben oeffnet in der Oberflaeche schon die
        # neue Sprechblase.
        run.nachlauf = False
    try:
        run.proc.stdin.write(stdin_message(build_prompt(text, images)))
        await run.proc.stdin.drain()
    except Exception as e:
        return JSONResponse({"error": f"Einspeisen fehlgeschlagen: {e}"}, status_code=500)
    return {"ok": True}


@router.get("/api/stream/{run_id}")
async def stream(run_id: str):
    """Hängt sich an einen Lauf: erst Backlog (Replay), dann live. Reconnect-fähig."""
    run = RUNS.get(run_id)
    if not run:
        return JSONResponse({"error": "unknown run"}, status_code=404)

    async def gen():
        q = asyncio.Queue()
        run.subs.add(q)
        idx = len(run.events)        # atomar (kein await bis hier) -> keine Lücken/Dupes
        already = run.done
        try:
            for ev in run.events[:idx]:
                yield sse(ev)
            if already:
                return                # Backlog enthält bereits done/error
            while True:
                try:
                    ev = await asyncio.wait_for(q.get(), timeout=8)
                except asyncio.TimeoutError:
                    yield ": keep-alive\n\n"
                    continue
                if ev is None:
                    break             # Lauf fertig
                yield sse(ev)
        finally:
            run.subs.discard(q)

    return StreamingResponse(gen(), media_type="text/event-stream", headers=SSE_HEADERS)


@router.get("/api/runs")
def list_runs():
    """Aktive (noch laufende) Läufe — damit das Frontend nach Reload wieder andocken kann."""
    gc_runs()
    return [{"run_id": r.id, "session_id": r.session_id, "cwd": r.cwd}
            for r in RUNS.values() if not r.done]


@router.post("/api/stop/{run_id}")
def stop_run(run_id: str):
    """Stop-Button: bricht den Lauf wirklich ab (killt den claude-Prozess)."""
    run = RUNS.get(run_id)
    if not run:
        return JSONResponse({"error": "unknown run"}, status_code=404)
    if run.task and not run.done:
        run.task.cancel()
    return {"stopped": True}
