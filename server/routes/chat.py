"""API: Chat-Läufe starten, streamen, einwerfen, stoppen."""
import asyncio
import os

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse

from server import auto_modell
from server import config as cfg
from server import hermes as hermesmod
from server import llm as llmmod

from server.core import ALLOWED_MODES, DEFAULT_CWD, sse
from server.hermes_runs import carry_over_block, start_hermes_run
from server.sessions import find_prompt
from server.runs import EFFORTS, MODEL_RE, RUNS, SSE_HEADERS, build_prompt, gc_runs, start_run, stdin_message

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
    effort = body.get("effort") if body.get("effort") in EFFORTS else ""

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

    # Bearbeitete eigene Nachricht: die Sitzung an der Stelle davor abzweigen,
    # damit Cody die alte Fassung und alles danach wirklich vergisst — nicht
    # nur in der Anzeige. Die allererste Nachricht bearbeitet = neue Sitzung.
    resume_at, forked_from, rewound = None, None, None
    edit = body.get("edit")
    if isinstance(edit, dict) and session_id:
        hit = find_prompt(session_id, str(edit.get("text") or ""),
                          int(edit.get("occurrence") or 0))
        rewound = hit is not None
        if hit:
            forked_from = session_id
            resume_at = hit[1]
            if not resume_at:
                session_id = None

    # Läuft für diese Sitzung schon ein claude-Prozess, der noch Eingaben annimmt
    # (mitten im Zug oder im Nachlauf), geht die Nachricht in DIESEN Prozess. Ein
    # zweiter per --resume würde parallel in derselben Sitzung weiterarbeiten.
    # Passiert, wenn ein anderes Fenster den laufenden Prozess nicht kennt.
    if session_id and resume_at is None:
        laufend = laufender_lauf(session_id)
        if laufend:
            ab = await einwerfen(laufend, text, images, [])
            if ab is not None:
                return {"run_id": laufend.id, "session_id": session_id, "joined": True, "ab": ab}

    # Was die Firma in dieser Session getan hat, hinten an der Nachricht (nicht im
    # Systemprompt, der soll im Zwischenspeicher bleiben). Beigabe: scheitert es,
    # geht die Nachricht trotzdem ab.
    if session_id and resume_at is None and cfg.load_settings()["team"]["aktiv"]:
        try:
            from server.team import chat as teamchat
            prompt += await teamchat.meldungen(session_id)
        except Exception as e:
            print(f"[firma] Meldung fehlgeschlagen: {type(e).__name__}: {e}", flush=True)
    # Übergaben, die bei ausgeschaltetem Team-Modus liegen blieben: unabhängig vom
    # Schalter, der steht dann meist noch auf aus.
    if session_id and resume_at is None:
        try:
            from server.team import chat as teamchat
            prompt += teamchat.nicht_angekommen(session_id)
        except Exception as e:
            print(f"[firma] Meldung fehlgeschlagen: {type(e).__name__}: {e}", flush=True)
    run = start_run(prompt, work_dir, mode, model, session_id, resume_at, effort, chat=True)
    if not session_id and not forked_from:
        # Schattenbetrieb der automatischen Modellwahl: nur protokollieren.
        auto_modell.starte(run, text, model)
    return {"run_id": run.id, "session_id": None if forked_from else session_id,
            "forked_from": forked_from, "rewound": rewound}


@router.post("/api/inject/{run_id}")
async def inject(run_id: str, req: Request):
    """Schiebt dem LAUFENDEN claude-Prozess eine weitere Nachricht nach (kein
    Warten auf das Ende, kein --resume) — wie Weitertippen im Terminal."""
    run = RUNS.get(run_id)
    if not nimmt_an(run):
        return JSONResponse({"error": "Lauf nimmt nichts mehr an"}, status_code=409)
    body = await req.json()
    text = (body.get("message") or "").strip()
    images = body.get("images") or []
    urls = body.get("urls") or []
    if not text and not images:
        return JSONResponse({"error": "leere Nachricht"}, status_code=400)
    try:
        await einwerfen(run, text, images, urls, fehler_werfen=True)
    except Exception as e:
        return JSONResponse({"error": f"Einspeisen fehlgeschlagen: {e}"}, status_code=500)
    return {"ok": True}


def nimmt_an(run):
    """Nimmt der Lauf noch Nachrichten über stdin an?"""
    return bool(run and not run.done and not run.stdin_closed and run.proc)


def laufender_lauf(session_id):
    """Der Chat-Lauf, der für diese Sitzung gerade Eingaben annimmt (oder None).
    Läufe der Firma (eigene Sitzungen, Dispatcher wartet aufs Prozessende) zählen nicht."""
    for run in RUNS.values():
        if run.session_id == session_id and nimmt_an(run) and not run.auftrag_id and not run.agent_slug:
            return run
    return None


async def einwerfen(run, text, images, urls, fehler_werfen=False):
    """Schiebt eine Nachricht in den laufenden Prozess. Gibt die Ereignis-Position
    nach dem user_inject zurück (ab dort braucht ein neu andockendes Fenster den
    Stream), bei einem Fehler None."""
    run.emit({"type": "user_inject", "text": text, "urls": urls})
    ab = len(run.events)
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
        print(f"[run] Einwerfen in {run.id} fehlgeschlagen: {type(e).__name__}: {e}", flush=True)
        if fehler_werfen:
            raise
        return None
    return ab


@router.get("/api/stream/{run_id}")
async def stream(run_id: str, ab: int = 0):
    """Hängt sich an einen Lauf: erst Backlog (Replay), dann live. Reconnect-fähig.
    ab: erst ab dieser Ereignis-Position abspielen (ein Fenster, das per
    /api/chat an einen schon laufenden Prozess angedockt hat, kennt den Anfang)."""
    run = RUNS.get(run_id)
    if not run:
        return JSONResponse({"error": "unknown run"}, status_code=404)

    async def gen():
        q = asyncio.Queue()
        run.subs.add(q)
        idx = len(run.events)        # atomar (kein await bis hier) -> keine Lücken/Dupes
        already = run.done
        try:
            for ev in run.events[max(0, ab):idx]:
                yield sse(ev)
            while not already:
                try:
                    ev = await asyncio.wait_for(q.get(), timeout=8)
                except asyncio.TimeoutError:
                    yield ": keep-alive\n\n"
                    continue
                if ev is None:
                    break             # Lauf fertig
                yield sse(ev)
            # Ausdruecklich: dieser Lauf ist zu Ende. Ein Stream, der einfach
            # endet, sieht fuer das Frontend aus wie ein Verbindungsabriss -
            # endete der Lauf im Nachlauf (ohne letztes "done"), dockte es
            # jede Sekunde neu an und baute den Verlauf leer neu auf.
            yield sse({"type": "closed"})
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


# Übergaben, die bei ausgeschaltetem Team-Modus liegen blieben (server/team/chat.py).
# Bewusst nicht unter /api/team: dort hängt alles am Team-Modus und wäre aus = 404.
@router.get("/api/firma/uebergaben/{sid}")
def uebergaben(sid: str):
    from server.team import chat as teamchat
    return {"uebergaben": teamchat.nicht_zugestellt(sid)}


@router.post("/api/firma/uebergaben/{sid}/{eid}")
async def uebergabe_nachholen(sid: str, eid: str):
    """Knopf „Firma einschalten und übergeben“. async: `uebergeben` wirft den
    Dispatcher in der laufenden Schleife an, im Threadpool gäbe es keine."""
    from server.team import chat as teamchat
    from server.team.engine import AuftragFehler
    settings = cfg.apply_patch({"team": {"aktiv": True}})
    try:
        u, t = teamchat.nachholen(sid, eid)
    except teamchat.NichtOffen:
        return JSONResponse({"error": cfg.L("Nichts offen.", "Nothing pending."),
                             "uebergaben": teamchat.nicht_zugestellt(sid)}, status_code=409)
    except AuftragFehler as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    return {"ok": True, "uebergabe": u, "auftrag": t["id"], "settings": settings}
