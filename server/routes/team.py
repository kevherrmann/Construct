"""API des Team-Modus: Belegschaft, Aufträge, Direktgespräch.

Alles unter /api/team/… und nur, wenn der Team-Modus an ist (⚙ Einstellungen).
Die Arbeit selbst steht in server/team/ (engine.py: Dispatcher und Züge,
bus.py: Werkzeugaufrufe der Mitarbeiter); hier ist nur die Web-Anbindung.
"""
import asyncio
import re
import shutil
import time

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse

from server import config as cfg
from server.core import PROJECTS_DIR, WORKSPACE, claude_bin, claude_env, sse
from server.runs import RUNS, SSE_HEADERS, build_prompt, stdin_message
from server.sessions import SID_RE, _parse_transcript_lines
from server.team import agents as ag
from server.team import auftraege as auf
from server.team import bus, engine
from server.team.gedaechtnis import (CHAT_MAX_BYTES, CHAT_MAX_MSGS, chat_session_id,
                                      chat_state_file, chat_umfang, verdichten)


async def team_an():
    """Alle Routen hängen daran: ohne Team-Modus gibt es sie nicht. Mit ihm läuft
    der Dispatcher, sobald die erste Anfrage kommt."""
    if not cfg.load_settings()["team"]["aktiv"]:
        raise HTTPException(status_code=404, detail="Der Team-Modus ist aus.")
    engine.starten()


router = APIRouter(dependencies=[Depends(team_an)])


@router.get("/api/team/agents")
def agents_list(fired: int = 0):
    return {"agents": [ag.anzeige(a) for a in ag.list_agents(WORKSPACE, include_fired=bool(fired))],
            "org": ag.org_tree(WORKSPACE)}


@router.get("/api/team/agent/{slug}")
def agent_get(slug: str):
    a = ag.load_agent(slug, WORKSPACE)
    if not a:
        return JSONResponse({"error": "unbekannt"}, status_code=404)
    return ag.anzeige(a)


@router.post("/api/team/agent/{slug}")
async def agent_set(slug: str, req: Request):
    body = await req.json()
    body["slug"] = slug
    a, bad = ag.save_agent(body, WORKSPACE)
    if a is None:
        return JSONResponse({"error": bad[0] if bad else "ungueltig"}, status_code=400)
    return {"ok": True, "agent": ag.anzeige(a), "problems": bad}


@router.post("/api/team/agents")
async def agent_new(req: Request):
    body = await req.json()
    if ag.load_agent(str(body.get("slug") or ""), WORKSPACE):
        return JSONResponse({"error": "gibt es schon"}, status_code=409)
    a, bad = ag.save_agent(body, WORKSPACE)
    if a is None:
        return JSONResponse({"error": bad[0] if bad else "ungueltig"}, status_code=400)
    return {"ok": True, "agent": a, "problems": bad}


@router.delete("/api/team/agent/{slug}")
def agent_fire(slug: str):
    return {"ok": ag.fire_agent(slug, WORKSPACE)}


@router.post("/api/team/agent/{slug}/chat")
async def agent_chat(slug: str, req: Request):
    """Direktgespräch: Kevin redet mit EINEM Mitarbeiter."""
    a = ag.load_agent(slug, WORKSPACE)
    if not a:
        return JSONResponse({"error": "unbekannt"}, status_code=404)
    if a["status"] == "fired":
        return JSONResponse({"error": f"{a['name']} arbeitet hier nicht mehr."},
                            status_code=400)
    if not claude_bin():
        return JSONResponse({"error": "Claude Code ist nicht installiert."},
                            status_code=400)
    body = await req.json()
    text = str(body.get("message") or "")[:200_000]
    images = [str(x) for x in (body.get("images") or [])][:8]
    if not text.strip() and not images:
        return JSONResponse({"error": "leer"}, status_code=400)
    verdichtet = await verdichten(a)
    a = ag.load_agent(slug, WORKSPACE) or a      # MEMORY.md hat sich geaendert
    run = engine.start_agent_chat(a, build_prompt(text, images), images)
    run.verdichtet = verdichtet
    return {"run_id": run.id, "session_id": run.session_id or "", "verdichtet": verdichtet,
            "agent": {k: ag.anzeige(a)[k] for k in ("slug", "name", "title", "color", "model", "effort")}}


@router.get("/api/team/agent/{slug}/chat")
def agent_chat_history(slug: str):
    """Bisheriger Verlauf des Direktgesprächs (aus dem Claude-Code-Transkript)."""
    a = ag.load_agent(slug, WORKSPACE)
    if not a:
        return JSONResponse({"error": "unbekannt"}, status_code=404)
    sid = chat_session_id(slug)
    msgs = []
    if sid and SID_RE.match(sid):
        f = next(iter(PROJECTS_DIR.glob(f"*/{sid}.jsonl")), None)
        if f is not None:
            try:
                msgs = _parse_transcript_lines(f.read_bytes())
            except OSError:
                # Nur Lesefehler abfangen. Ein Programmfehler beim Auswerten
                # soll krachen und nicht als "Gespraech ist leer" durchgehen.
                msgs = []
    groesse, anzahl = chat_umfang(slug)
    return {"session_id": sid, "messages": msgs,
            "umfang": {"bytes": groesse, "msgs": anzahl,
                       "max_bytes": CHAT_MAX_BYTES, "max_msgs": CHAT_MAX_MSGS},
            "memory": a.get("memory", ""),
            "agent": {k: ag.anzeige(a)[k] for k in ("slug", "name", "title", "color", "model",
                                                    "effort", "cwd", "permission_mode", "avatar")}}


@router.delete("/api/team/agent/{slug}/chat")
async def agent_chat_reset(slug: str):
    """Gespräch leeren: Sitzungszeiger weg, Transkript von der Platte.

    Nur der Verlauf. MEMORY.md und USER.md bleiben, wo sie sind — was der
    Mitarbeiter gelernt hat, ueberlebt das Leeren.

    Bewusst async und ohne await zwischen Pruefung und Loeschen: Laeufe werden
    ausnahmslos im Event-Loop gestartet, also kann dazwischen keiner dazukommen.
    Als sync-Handler liefe das im Threadpool und genau das waere moeglich.
    """
    a = ag.load_agent(slug, WORKSPACE)
    if not a:
        return JSONResponse({"error": "unbekannt"}, status_code=404)
    if any(r.agent_slug == slug and not r.done for r in RUNS.values()):
        return JSONResponse({"error": "Der Mitarbeiter arbeitet gerade — "
                                      "warte, bis er fertig ist."},
                            status_code=409)
    sid = chat_session_id(slug)
    try:
        chat_state_file(slug).unlink()
    except OSError:
        pass
    # Das Transkript liegt in Claude Codes eigenem Projektordner. Ohne das
    # Loeschen bliebe der ganze Verlauf lesbar und nur abgekoppelt.
    if sid and SID_RE.match(sid):
        for f in PROJECTS_DIR.glob(f"*/{sid}.jsonl"):
            try:
                f.unlink()
            except OSError:
                pass
    return {"ok": True}


@router.get("/api/team/auftraege")
def auftraege_liste():
    """Fuer die Liste — mit Nachrichtenzahl, damit die Oberflaeche
    Ungelesenes erkennen kann."""
    out = []
    for t in auf.alle():
        out.append({k: t[k] for k in ("id", "titel", "status", "owner",
                                      "erstellt", "verbraucht")}
                   | {"eskalation": t.get("eskalation")}
                   | auf.uebersicht(t["id"]))
    return {"tickets": out}


@router.post("/api/team/auftraege")
async def auftrag_neu(req: Request):
    """Der Nutzer gibt der Firma einen Auftrag. Er geht an die Geschäftsführung."""
    body = await req.json()
    try:
        t = engine.auftrag_anlegen(body.get("titel"), body.get("brief"), body.get("cwd") or "",
                                   str(body.get("owner") or ""), body.get("bruecke"))
    except engine.AuftragFehler as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    return {"ok": True, "ticket": t}


@router.post("/api/team/auftraege/aus-ticket")
async def auftrag_aus_ticket(req: Request):
    """Der Knopf am Ticket: aus den Nachrichten eines Tickets wird ein Auftrag."""
    body = await req.json()
    try:
        t = engine.auftrag_aus_ticket(str(body.get("session") or ""), int(body.get("nr") or 0))
    except engine.AuftragVorhanden as e:
        return JSONResponse({"error": str(e), "auftrag": e.auftrag_id}, status_code=409)
    except engine.AuftragFehler as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    except ValueError:
        return JSONResponse({"error": "ungültige Angabe"}, status_code=400)
    return {"ok": True, "ticket": t}


@router.get("/api/team/auftraege/{tid}")
def auftrag_detail(tid: str):
    t = auf.laden(tid)
    if not t:
        return JSONResponse({"error": "unbekannt"}, status_code=404)
    return {"ticket": t, "verlauf": auf.verlauf(tid),
            "agents": {x["slug"]: {k: ag.anzeige(x)[k] for k in ("name", "title", "color", "avatar")}
                       for x in ag.list_agents(WORKSPACE, include_fired=True)}}


@router.get("/api/team/auftraege/{tid}/stream")
async def auftrag_stream(tid: str):
    """Wie /api/stream: erst der Rueckstand, dann live."""
    f = engine.feed(tid)

    async def gen():
        q = asyncio.Queue()
        f.subs.add(q)
        backlog = list(f.events)      # NACH dem Abonnieren: sonst fehlt, was dazwischen kam
        try:
            for ev in backlog:
                yield sse(ev)
            while True:
                try:
                    ev = await asyncio.wait_for(q.get(), timeout=8)
                except asyncio.TimeoutError:
                    yield ": ping\n\n"
                    continue
                yield sse(ev)
        finally:
            f.subs.discard(q)

    return StreamingResponse(gen(), media_type="text/event-stream", headers=SSE_HEADERS)


@router.post("/api/team/auftraege/{tid}/antwort")
async def auftrag_antwort(tid: str, req: Request):
    """Kevin antwortet auf eine Eskalation, leitet um oder bricht ab.

    Eine Bremse loest sich NIE von selbst — sie soll eine Entscheidung
    erzwingen. Sagt Kevin hier weiter, zaehlen die Bremsen wieder von vorn;
    dass er hingesehen hat, ist die Freigabe.
    """
    t = auf.laden(tid)
    if not t:
        return JSONResponse({"error": "unbekannt"}, status_code=404)
    body = await req.json()
    aktion = str(body.get("aktion") or "weiter")
    text = str(body.get("text") or "").strip()

    if aktion == "abbrechen":
        def _abbrechen(x):
            x["status"] = "abgebrochen"
            x["eskalation"] = None
        t = await engine.auftrag_aendern(tid, _abbrechen) or t
        # Laeuft gerade ein Zug, wird er beendet — vorher arbeitete der
        # Prozess weiter und gab Geld aus, fuer einen Auftrag, den es nicht
        # mehr gab. Der Dispatcher sieht den Abbruch und laesst den Auftrag in
        # Ruhe (ticket_anhalten ignoriert abgeschlossene Auftraege).
        lauf = RUNS.get((t.get("in_arbeit") or {}).get("run_id") or "")
        if lauf and lauf.task and not lauf.done:
            lauf.task.cancel()
        auf.anhaengen(tid, {"art": "system", "text": "Kevin hat den Auftrag abgebrochen."})
        engine.feed(tid).emit({"type": "abgebrochen"})
        for spf in ag.AGENTS_DIR.glob(f"*/.sysprompt-{tid}"):
            spf.unlink(missing_ok=True)
        return {"ok": True, "ticket": t}
    if t["status"] in ("fertig", "abgebrochen"):
        return JSONResponse({"error": "Der Auftrag ist abgeschlossen."}, status_code=400)
    t = await engine.kevin_weiter(tid, str(body.get("an") or "").strip(), text)
    return {"ok": True, "ticket": t}


@router.post("/api/team/auftraege/{tid}/say")
async def auftrag_say(tid: str, req: Request):
    """Dazwischenrufen, waehrend die Firma arbeitet.

    Laeuft gerade ein Zug, geht die Nachricht per stdin direkt hinein — der
    Agent liest sie noch in DIESEM Zug (dasselbe, was der Chat-Einwurf tut).
    Sonst wird sie als normale Nachricht eingereiht — und wartet der Auftrag
    gerade auf Kevin, ist das dasselbe wie eine Antwort im roten Balken.
    """
    t = auf.laden(tid)
    if not t:
        return JSONResponse({"error": "unbekannt"}, status_code=404)
    body = await req.json()
    text = str(body.get("text") or "").strip()
    if not text:
        return JSONResponse({"error": "leer"}, status_code=400)

    lauf = t.get("in_arbeit") or {}
    run = RUNS.get(lauf.get("run_id") or "")
    if run and not run.done and not run.stdin_closed and run.proc:
        try:
            run.proc.stdin.write(stdin_message(ag.anrede(
                "[Kevin wirft ein, waehrend du arbeitest. Das ist eine ERGAENZUNG zu "
                "deiner laufenden Aufgabe, kein neuer Auftrag: arbeite sie in DIESEN "
                "Zug ein und liefere danach EINMAL. Gib sie nicht zusaetzlich noch "
                "einmal weiter.]") + "\n\n" + text))
            await run.proc.stdin.drain()
            e = auf.anhaengen(tid, {"von": "kevin", "an": run.agent_slug,
                                   "art": "einwurf", "text": text})
            engine.feed(tid).emit({"type": "msg", **e})
            # Sofort quittieren: der Einwurf IST zugestellt (er steckt im
            # laufenden Prozess). Ohne die Quittung wuerde wieder_aufnehmen()
            # ihn nach einem Neustart fuer unerledigt halten und erneut
            # einreihen — im Test hat schon das Modell ihn zweimal
            # aufgegriffen und doppelt geliefert.
            auf.quittieren(tid, e["id"])
            return {"ok": True, "wohin": "laufender Zug"}
        except (OSError, AttributeError):
            pass          # Prozess ist doch schon zu — dann eben einreihen

    if t["status"] in ("fertig", "abgebrochen"):
        return JSONResponse({"error": "Der Auftrag ist abgeschlossen."}, status_code=400)
    t = await engine.kevin_weiter(tid, str(body.get("an") or "").strip(), text)
    return {"ok": True, "wohin": "eingereiht"}



@router.get("/api/team/state")
def team_state():
    """Was gerade laeuft — fuer den Aktivitaets-Streifen."""
    aktiv = []
    for r in list(RUNS.values()):     # Schnappschuss: die Schleife mutiert RUNS parallel
        if r.done or not r.agent_slug or not r.auftrag_id:
            continue
        a = ag.load_agent(r.agent_slug, WORKSPACE) or {}
        t = auf.laden(r.auftrag_id) or {}
        aktiv.append({"agent": r.agent_slug, "name": ag.anzeige(a).get("name", r.agent_slug),
                      "color": a.get("color", "126,231,135"),
                      "ticket": r.auftrag_id, "titel": t.get("titel", ""), "run": r.id,
                      "seit": int(time.time() - r.started)})
    wartend = [{"id": t["id"], "titel": t["titel"],
                "grund": (t.get("eskalation") or {}).get("bremse") or ""}
               for t in auf.alle()
               if t["status"] == "wartet_auf_kevin"]
    return {"aktiv": aktiv, "wartend": wartend, "pausiert": engine.PAUSIERT}



@router.delete("/api/team/auftraege/{tid}")
def auftrag_loeschen(tid: str):
    """Auftrag samt Verlauf entfernen. Anders als beim Entlassen eines
    Mitarbeiters wird hier wirklich geloescht — ein Auftrag hat keine
    Geschichte, auf die sich spaeter noch jemand berufen muesste."""
    if not re.fullmatch(r"[0-9a-f]{8}", tid or ""):
        return JSONResponse({"error": "ungueltig"}, status_code=400)
    d = auf.AUFTRAEGE_DIR / tid
    try:
        if d.resolve().parent != auf.AUFTRAEGE_DIR.resolve():
            return JSONResponse({"error": "ungueltig"}, status_code=400)
        shutil.rmtree(d)
    except FileNotFoundError:
        return JSONResponse({"error": "unbekannt"}, status_code=404)
    engine.FEEDS.pop(tid, None)
    engine.AUFTRAG_LOCKS.pop(tid, None)
    engine.ZUG_LOCKS.pop(tid, None)
    for f in ag.AGENTS_DIR.glob(f"*/.sysprompt-{tid}"):
        f.unlink(missing_ok=True)
    return {"ok": True}


@router.post("/api/team/pause")
async def team_pause(req: Request):
    """Not-Aus fuer die ganze Firma."""
    body = await req.json()
    engine.PAUSIERT = bool(body.get("pause"))
    return {"pausiert": engine.PAUSIERT}


@router.get("/api/team/user-md")
def user_md_get():
    """Was die Firma über den Nutzer weiss: seine USER.md und, getrennt, was die
    Mitarbeiter ergänzt haben."""
    return {"text": ag._read_capped(ag.USER_FILE, ag.MAX_USER) if ag.USER_FILE.exists() else ag.user_read(),
            "ergaenzungen": ag.ergaenzungen_read(), "protocol": ag.protocol_read()}


@router.post("/api/team/user-md")
async def user_md_set(req: Request):
    """Vollstaendiges Ueberschreiben — das darf NUR der Nutzer, nicht ein Agent.
    Die Mitarbeiter haengen ueber user_merken an die Ergaenzungen an, sie ersetzen nie."""
    body = await req.json()
    async with bus.USER_LOCK:
        if "text" in body:
            ag._atomic(ag.USER_FILE, str(body.get("text") or "")[:ag.MAX_USER])
        if "ergaenzungen" in body:
            ag._atomic(ag.ERGAENZUNGEN_FILE, str(body.get("ergaenzungen") or "")[:ag.MAX_USER])
    return {"ok": True}


@router.post("/api/team/bus")
async def team_bus(req: Request):
    """Gegenstelle von team_mcp.py: die Werkzeugaufrufe der Mitarbeiter."""
    return JSONResponse(await bus.bus_aufruf(await req.json()))
