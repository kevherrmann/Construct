"""API: Tickets innerhalb der Sessions (Logik in server/tickets.py)."""
import secrets

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from server import tickets as tk
from server.runs import RUNS
from server.sessions import load_meta

router = APIRouter()


def _fehler(msg: str, code: int = 400):
    return JSONResponse({"error": msg}, status_code=code)


def _sid(sid: str):
    return sid if tk.SID_RE.match(sid or "") else None


@router.get("/api/tickets")
def tickets_uebersicht():
    """Tag → Projekt → Tickets, für die Kachel und die Tafel im Raum."""
    return tk.uebersicht(load_meta().get("names", {}))


@router.get("/api/tickets/{sid}")
def tickets_session(sid: str):
    """Die Tickets EINER Session — für den Chip über der Eingabe."""
    if not _sid(sid):
        return _fehler("bad id")
    return tk.laden(sid)


async def _body(req: Request) -> dict:
    try:
        b = await req.json()
    except Exception:
        return {}
    return b if isinstance(b, dict) else {}


@router.post("/api/tickets/{sid}/schnitt")
async def ticket_schnitt(sid: str, req: Request):
    """/ticket Titel: ab der nächsten Nachricht ein neues Ticket."""
    if not _sid(sid):
        return _fehler("bad id")
    b = await _body(req)
    return tk.schnitt(sid, str(b.get("titel") or "").strip(), str(b.get("cwd") or ""))


@router.post("/api/tickets/{sid}/waehlen")
async def ticket_waehlen(sid: str, req: Request):
    """Chip: die nächste Nachricht gehört zu diesem Ticket."""
    if not _sid(sid):
        return _fehler("bad id")
    try:
        return tk.waehlen(sid, int((await _body(req)).get("nr")))
    except (KeyError, TypeError, ValueError):
        return _fehler("kein solches Ticket", 404)


@router.post("/api/tickets/{sid}/{nr:int}")
async def ticket_aendern(sid: str, nr: int, req: Request):
    """Umbenennen und/oder offen/erledigt umschalten."""
    if not _sid(sid):
        return _fehler("bad id")
    b = await _body(req)
    try:
        return tk.aendern(sid, nr, b.get("titel"), b.get("status"))
    except KeyError:
        return _fehler("kein solches Ticket", 404)


@router.delete("/api/tickets/{sid}/{nr:int}")
def ticket_loeschen(sid: str, nr: int):
    if not _sid(sid):
        return _fehler("bad id")
    try:
        return tk.loeschen(sid, nr)
    except KeyError:
        return _fehler("kein solches Ticket", 404)


@router.post("/api/tickets/{sid}/{nr:int}/zusammenfuehren")
async def ticket_zusammenfuehren(sid: str, nr: int, req: Request):
    """Ticket nr in ein anderes legen (body: {"in": nr})."""
    if not _sid(sid):
        return _fehler("bad id")
    try:
        return tk.zusammenfuehren(sid, nr, int((await _body(req)).get("in")))
    except (KeyError, TypeError, ValueError):
        return _fehler("kein solches Ticket", 404)


@router.post("/api/tickets/{sid}/umhaengen")
async def ticket_umhaengen(sid: str, req: Request):
    """Nachrichten in ein anderes Ticket legen (body: {"uuids": [...], "nr": n})."""
    if not _sid(sid):
        return _fehler("bad id")
    b = await _body(req)
    uuids = [u for u in (b.get("uuids") or []) if isinstance(u, str)]
    try:
        return tk.umhaengen(sid, uuids, int(b.get("nr")))
    except (KeyError, TypeError, ValueError):
        return _fehler("kein solches Ticket", 404)


@router.post("/api/tickets/{sid}/ab-hier")
async def ticket_ab_hier(sid: str, req: Request):
    """✂ an einer Nachricht: sie und die späteren ihres Tickets werden ein neues."""
    if not _sid(sid):
        return _fehler("bad id")
    b = await _body(req)
    try:
        return tk.ab_hier(sid, str(b.get("uuid") or ""), str(b.get("titel") or "").strip())
    except KeyError:
        return _fehler("Nachricht gehört zu keinem Ticket", 404)


@router.post("/api/ticketbus")
async def ticketbus(req: Request):
    """Gegenstelle von construct_mcp.py: die Ticket-Werkzeuge des Assistenten.
    Wer ruft, weist sich mit dem Einmal-Token seines Laufs aus — Session und
    Nachricht kommen aus dem Lauf, nicht aus den Argumenten."""
    b = await _body(req)
    run = RUNS.get(str(b.get("run") or ""))
    if (not run or not run.tickets or run.done
            or not secrets.compare_digest(run.token, str(b.get("token") or ""))):
        return JSONResponse({"error": True, "text": "unbekannter Lauf"}, status_code=403)
    if not run.session_id:
        return {"text": "Session noch nicht bekannt."}
    args = b.get("args") if isinstance(b.get("args"), dict) else {}
    werkzeug = str(b.get("tool") or "")
    if werkzeug in ("firma_auftrag", "firma_stand"):
        text = _firma(werkzeug, args, run)
        if werkzeug == "firma_auftrag":
            from server.team import engine
            engine.starten()          # der Dispatcher stellt den neuen Auftrag zu
    else:
        text = tk.bus(werkzeug, args, run.session_id, run.letzte_uuid)
    run.emit({"type": "tickets"})      # die Oberfläche lädt Chip und Trenner neu
    return {"text": text}


def _firma(werkzeug: str, args: dict, run) -> str:
    """Die zwei Werkzeuge des Assistenten für die Firma (nur mit Team-Modus)."""
    from server import config as cfg
    if not cfg.load_settings()["team"]["aktiv"]:
        return cfg.L("Der Team-Modus ist aus.", "Team mode is off.")
    from server.team import auftraege as auf
    from server.team import engine
    d = tk.laden(run.session_id)
    if werkzeug == "firma_stand":
        zeilen = []
        for t in d["tickets"]:
            a = auf.laden(t.get("auftrag") or "") if t.get("auftrag") else None
            if not a:
                continue
            zeile = f"#{t['nr']} „{t['titel']}“ → {a['status']}"
            if a["status"] == "fertig" and a.get("ergebnis"):
                zeile += f"\n  Ergebnis: {a['ergebnis'][:600]}"
            elif a.get("eskalation"):
                zeile += f"\n  Wartet: {a['eskalation'].get('frage') or a['eskalation'].get('grund')}"
            zeilen.append(zeile)
        return "\n".join(zeilen) or cfg.L("Aus dieser Session ging noch nichts an die Firma.",
                                         "Nothing from this session has gone to the company yet.")
    try:
        t = engine.auftrag_anlegen(args.get("titel"), args.get("brief"), run.cwd,
                                   bruecke={"session": run.session_id, "nr": d["aktuell"]}
                                   if d.get("aktuell") else None)
    except engine.AuftragFehler as e:
        return str(e)
    return cfg.L(
        f"Auftrag „{t['titel']}“ ist bei der Firma. Sie arbeitet im Hintergrund; der Nutzer sieht "
        f"den Stand unter Aufträge und bekommt Bescheid. Sag ihm das in einem Satz — und arbeite "
        f"nicht selbst daran weiter.",
        f"Job “{t['titel']}” is with the company. It works in the background; the user sees the "
        f"state under Jobs and gets notified. Tell them in one sentence — and do not keep working "
        f"on it yourself.")
