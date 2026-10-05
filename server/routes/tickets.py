"""API: Tickets innerhalb der Sessions (Logik in server/tickets.py)."""
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from server import tickets as tk
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
