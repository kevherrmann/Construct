"""API: das Ticket-Board (Logik in server/tickets.py)."""
import asyncio

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse

from server import config as cfg
from server import tickets as tk


def _kachel_an():
    """Ist die Kachel aus, gibt es die Tickets nicht — auch nicht für Aufrufe am
    Bildschirm vorbei (wie /api/team/* bei ausgeschaltetem Team-Modus)."""
    if not cfg.load_settings()["tiles"].get("tickets", False):
        raise HTTPException(status_code=404, detail=cfg.L("Tickets sind abgeschaltet", "Tickets are switched off"))


router = APIRouter(dependencies=[Depends(_kachel_an)])


def _fehler(msg: str, code: int = 400):
    return JSONResponse({"error": msg}, status_code=code)


async def _body(req: Request) -> dict:
    try:
        b = await req.json()
    except Exception:
        return {}
    return b if isinstance(b, dict) else {}


@router.get("/api/tickets")
async def tickets_board(projekt: str = ""):
    # git fragen dauert: nicht in der Ereignisschleife
    await asyncio.to_thread(tk.push_pruefen)
    return tk.board(projekt)


@router.post("/api/tickets")
async def tickets_neu(req: Request):
    b = await _body(req)
    try:
        return tk.anlegen(b.get("titel", ""), b.get("text", ""), b.get("projekt", ""),
                          b.get("spalte", "neu"))
    except ValueError as e:
        return _fehler(str(e))


@router.post("/api/tickets/{nr}")
async def tickets_aendern(nr: int, req: Request):
    b = await _body(req)
    try:
        return tk.aendern(nr, titel=b.get("titel"), text=b.get("text"),
                          spalte=b.get("spalte"), projekt=b.get("projekt"))
    except KeyError:
        return _fehler(cfg.L("Dieses Ticket gibt es nicht.", "This ticket does not exist."), 404)
    except ValueError as e:
        return _fehler(str(e))


@router.delete("/api/tickets/{nr}")
def tickets_loeschen(nr: int):
    try:
        tk.loeschen(nr)
    except KeyError:
        return _fehler(cfg.L("Dieses Ticket gibt es nicht.", "This ticket does not exist."), 404)
    return {"ok": True}
